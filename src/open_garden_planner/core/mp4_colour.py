"""The colour tags of a tour's MP4: read them, and write them where the recorder left none (#807). Qt-free.

Why this module exists (measured, ADR-072 addendum "review-grade video"). Qt's recorder hands
FFmpeg's Media Foundation encoder (``h264_mf``) no colour description, and FFmpeg's MP4 muxer
writes none either: the stream's sequence parameter set (SPS) carries a VUI with timing only,
and the sample entry has no ``colr`` box. A player then guesses the colours from the picture's
size; Qt's own decoder reported ``ColorSpace_Undefined``. The frames ARE BT.709, limited range
(``core/video_yuv.py``), so the file should say so.

``tag_colour`` rewrites a finished file once, before it gets the user's name:

- a ``colr`` box (``nclx``: primaries, transfer and matrix 1 = BT.709, ``full_range_flag`` 0) in
  the video sample entry, which MP4 readers (FFmpeg, browsers, Media Foundation, QuickTime) take
  as the container's statement;
- the same values in every H.264 SPS, the one in ``avcC`` and each one in the stream (Media
  Foundation repeats it at every IDR frame), as ``video_signal_type`` with a colour description,
  which a decoder reading only the bit stream takes. The rest of each SPS is copied bit for bit.

Nothing else changes: the samples' order and timing, every other NAL unit, every other box.
``read_stream`` is the check: the profile and level the encoder chose, the colour of the SPS
and of the ``colr`` box, the number of samples and their timing.

The layout it rewrites is the one FFmpeg's muxer writes for one video track: ``ftyp``,
``free``, ``mdat``, then ``moov``. Anything else (``moov`` first, a fragmented file, a second
track, a constant sample size) raises ``Mp4Error`` and the caller keeps the file as it is: an
untagged video is still a video, a lost render is not.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final

__all__ = ["BT709_LIMITED", "ColourTags", "Mp4Error", "SpsInfo", "StreamInfo", "parse_sps",
           "patch_sps_colour", "read_stream", "tag_colour"]

#: Boxes whose payload is boxes, on the way from ``moov`` to the sample entry.
_CONTAINERS: Final = frozenset({b"moov", b"trak", b"mdia", b"minf", b"stbl"})
#: Visual sample entries this module knows: H.264 (``avc1``/``avc3``) and MPEG-4 Part 2.
_VISUAL_ENTRIES: Final = frozenset({b"avc1", b"avc3", b"mp4v"})
_AVC_ENTRIES: Final = frozenset({b"avc1", b"avc3"})
#: A VisualSampleEntry's own fields before its child boxes (ISO/IEC 14496-12 §12.1.3).
_VISUAL_ENTRY_FIELDS: Final = 78
#: H.264 profiles whose SPS carries chroma format, bit depths and scaling matrices (7.3.2.1.1).
_HIGH_PROFILES: Final = frozenset({100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135})
_PROFILE_NAMES: Final = {66: "Baseline", 77: "Main", 88: "Extended", 100: "High", 110: "High 10",
                         122: "High 4:2:2", 244: "High 4:4:4 Predictive", 44: "CAVLC 4:4:4 Intra"}
#: (SubWidthC, SubHeightC) by chroma_format_idc (Table 6-1); 0 crops in whole luma samples.
_CHROMA_SUBSAMPLING: Final = {0: (1, 1), 1: (2, 2), 2: (2, 1), 3: (1, 1)}
_COPY_BLOCK: Final = 1 << 20
_NAL_SPS: Final = 7
#: video_format in the VUI: 5 is "unspecified" (Table E-2): the frames are not from a camera.
_VIDEO_FORMAT_UNSPECIFIED: Final = 5
#: The most an SPS grows by when its colour is written: 33 bits of VUI and up to two
#: emulation prevention bytes. Bounds the mdat's growth before the samples are read.
_SPS_GROWTH_BOUND: Final = 8
_MAX_32: Final = 0xFFFFFFFF
#: The largest mdat a 32-bit size field holds (a name of its own, so a test can lower it).
_MDAT_32_LIMIT = _MAX_32


class Mp4Error(ValueError):
    """The file is not one this module can read or rewrite."""


@dataclass(frozen=True, slots=True)
class ColourTags:
    """A colour description in the code points of ISO/IEC 23091-2 (H.264 Annex E, ``nclx``)."""

    primaries: int
    transfer: int
    matrix: int
    full_range: bool

    def __post_init__(self) -> None:
        if not all(0 <= value <= 255 for value in (self.primaries, self.transfer, self.matrix)):
            raise ValueError(f"colour code points are 0..255, got {self!r}")


#: What the app's frames are: BT.709 primaries, transfer and matrix, limited range (16-235).
BT709_LIMITED: Final = ColourTags(1, 1, 1, False)


@dataclass(frozen=True, slots=True)
class SpsInfo:
    """What a sequence parameter set says that this module reads."""

    profile_idc: int
    constraints: int
    level_idc: int
    width: int
    height: int
    colour: ColourTags | None
    #: The VUI's timing: (num_units_in_tick, time_scale, fixed_frame_rate_flag), or None.
    timing: tuple[int, int, bool] | None

    @property
    def profile(self) -> str:
        """The profile's name as players show it (Constrained Baseline: constraint_set1)."""
        if self.profile_idc == 66 and self.constraints & 0x40:
            return "Constrained Baseline"
        if self.profile_idc == 100 and self.constraints & 0x0C == 0x0C:
            return "Constrained High"
        return _PROFILE_NAMES.get(self.profile_idc, f"profile {self.profile_idc}")

    @property
    def level(self) -> float:
        return self.level_idc / 10.0


@dataclass(frozen=True, slots=True)
class StreamInfo:
    """The video track of an MP4 as ``read_stream`` found it."""

    codec: str
    width: int
    height: int
    samples: int
    #: The media's timescale and each run of equal sample durations (``stts``: count, delta).
    timescale: int
    durations: tuple[tuple[int, int], ...]
    video_bytes: int
    sps: SpsInfo | None
    colr: ColourTags | None
    #: The colour of each SPS the samples carry (Media Foundation repeats one at each IDR);
    #: empty when the samples were not read.
    inband_colour: tuple[ColourTags | None, ...]

    @property
    def duration_s(self) -> float:
        return sum(count * delta for count, delta in self.durations) / self.timescale

    @property
    def bit_rate(self) -> float:
        """Bits per second of the video samples."""
        return self.video_bytes * 8.0 / self.duration_s if self.duration_s > 0 else 0.0

    @property
    def tagged(self) -> ColourTags | None:
        """The colour the file states, when every place that states one agrees; else None."""
        stated = {self.colr, *self.inband_colour}
        if self.sps is not None:
            stated.add(self.sps.colour)
        return self.colr if len(stated) == 1 else None


# ── the bit stream (H.264 7.3.2.1.1 and Annex E) ─────────────────────────────


class _BitReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.position = 0

    def u(self, count: int) -> int:
        if self.position + count > len(self._data) * 8:
            raise Mp4Error("the SPS ends early")
        value = 0
        for _ in range(count):
            byte = self._data[self.position >> 3]
            value = (value << 1) | ((byte >> (7 - (self.position & 7))) & 1)
            self.position += 1
        return value

    def ue(self) -> int:
        zeros = 0
        while self.u(1) == 0:
            zeros += 1
            if zeros > 31:
                raise Mp4Error("an Exp-Golomb code longer than 32 bits")
        return (1 << zeros) - 1 + (self.u(zeros) if zeros else 0)

    def se(self) -> int:
        code = self.ue()
        return (code + 1) // 2 if code & 1 else -(code // 2)


class _BitWriter:
    def __init__(self) -> None:
        self._bits: list[int] = []

    def u(self, count: int, value: int) -> None:
        self._bits.extend((value >> shift) & 1 for shift in range(count - 1, -1, -1))

    def copy(self, data: bytes, start: int, end: int) -> None:
        self._bits.extend((data[index >> 3] >> (7 - (index & 7))) & 1 for index in range(start, end))

    def with_trailing_bits(self) -> bytes:
        """The bits, then rbsp_trailing_bits: a stop bit and zeros to the next byte."""
        bits = [*self._bits, 1]
        bits.extend([0] * (-len(bits) % 8))
        return bytes(sum(bit << (7 - offset) for offset, bit in enumerate(bits[index:index + 8]))
                     for index in range(0, len(bits), 8))


def _unescape(payload: bytes) -> bytes:
    """A NAL unit's payload without its emulation prevention bytes (7.4.1)."""
    out = bytearray()
    zeros = 0
    for byte in payload:
        if zeros >= 2 and byte == 3:
            zeros = 0
            continue
        out.append(byte)
        zeros = zeros + 1 if byte == 0 else 0
    return bytes(out)


def _escape(rbsp: bytes) -> bytes:
    """The payload with an emulation prevention byte wherever two zeros meet a byte below 4."""
    out = bytearray()
    zeros = 0
    for byte in rbsp:
        if zeros >= 2 and byte <= 3:
            out.append(3)
            zeros = 0
        out.append(byte)
        zeros = zeros + 1 if byte == 0 else 0
    return bytes(out)


def _skip_scaling_list(bits: _BitReader, size: int) -> None:
    last = upcoming = 8
    for _ in range(size):
        if upcoming:
            upcoming = (last + bits.se() + 256) % 256
        last = upcoming or last


def _stop_bit(rbsp: bytes) -> int:
    """The position of rbsp_stop_one_bit: the last 1 bit of the payload."""
    for index in range(len(rbsp) - 1, -1, -1):
        byte = rbsp[index]
        if byte:
            return index * 8 + 8 - (byte & -byte).bit_length()
    raise Mp4Error("an SPS without a stop bit")


@dataclass(frozen=True, slots=True)
class _SpsLayout:
    info: SpsInfo
    rbsp: bytes
    #: Bit positions in the RBSP (the payload after the NAL header byte).
    vui_flag: int                 # vui_parameters_present_flag
    signal_flag: int | None       # video_signal_type_present_flag; None: the SPS has no VUI
    after_signal: int | None      # the first bit after the video signal type's fields
    stop: int


def _layout(nal: bytes) -> _SpsLayout:
    if not nal or nal[0] & 0x1F != _NAL_SPS:
        raise Mp4Error("not an SPS NAL unit")
    rbsp = _unescape(nal[1:])
    bits = _BitReader(rbsp)
    profile, constraints, level = bits.u(8), bits.u(8), bits.u(8)
    bits.ue()                                    # seq_parameter_set_id
    chroma_format = 1
    if profile in _HIGH_PROFILES:
        chroma_format = bits.ue()
        if chroma_format == 3 and bits.u(1):     # separate_colour_plane_flag
            chroma_format = 0
        bits.ue()
        bits.ue()                                # bit_depth_luma / chroma
        bits.u(1)                                # qpprime_y_zero_transform_bypass_flag
        if bits.u(1):                            # seq_scaling_matrix_present_flag
            for index in range(8 if chroma_format != 3 else 12):
                if bits.u(1):
                    _skip_scaling_list(bits, 16 if index < 6 else 64)
    bits.ue()                                    # log2_max_frame_num_minus4
    order = bits.ue()                            # pic_order_cnt_type
    if order == 0:
        bits.ue()
    elif order == 1:
        bits.u(1)
        bits.se()
        bits.se()
        for _ in range(bits.ue()):
            bits.se()
    bits.ue()                                    # max_num_ref_frames
    bits.u(1)                                    # gaps_in_frame_num_value_allowed_flag
    width_mbs, height_units = bits.ue() + 1, bits.ue() + 1
    frames_only = bits.u(1)
    if not frames_only:
        bits.u(1)                                # mb_adaptive_frame_field_flag
    bits.u(1)                                    # direct_8x8_inference_flag
    crop = (bits.ue(), bits.ue(), bits.ue(), bits.ue()) if bits.u(1) else (0, 0, 0, 0)
    sub_width, sub_height = _CHROMA_SUBSAMPLING.get(chroma_format, (1, 1))
    width = width_mbs * 16 - sub_width * (crop[0] + crop[1])
    height = (height_units * 16 * (2 - frames_only)
              - sub_height * (2 - frames_only) * (crop[2] + crop[3]))
    vui_flag = bits.position
    colour: ColourTags | None = None
    timing: tuple[int, int, bool] | None = None
    signal_flag = after_signal = None
    if bits.u(1):
        if bits.u(1) and bits.u(8) == 255:       # aspect_ratio_info, Extended_SAR
            bits.u(32)
        if bits.u(1):                            # overscan_info_present_flag
            bits.u(1)
        signal_flag = bits.position
        if bits.u(1):                            # video_signal_type_present_flag
            bits.u(3)                            # video_format
            full_range = bits.u(1)
            if bits.u(1):                        # colour_description_present_flag
                colour = ColourTags(bits.u(8), bits.u(8), bits.u(8), bool(full_range))
        after_signal = bits.position
        if bits.u(1):                            # chroma_loc_info_present_flag
            bits.ue()
            bits.ue()
        if bits.u(1):                            # timing_info_present_flag
            timing = (bits.u(32), bits.u(32), bool(bits.u(1)))
    info = SpsInfo(profile, constraints, level, width, height, colour, timing)
    return _SpsLayout(info, rbsp, vui_flag, signal_flag, after_signal, _stop_bit(rbsp))


def parse_sps(nal: bytes) -> SpsInfo:
    """What an SPS NAL unit (header byte included, emulation prevention in place) says.
    ``Mp4Error`` when it is not one."""
    return _layout(nal).info


def patch_sps_colour(nal: bytes, tags: ColourTags = BT709_LIMITED) -> bytes:
    """The SPS with ``tags`` as its VUI's video signal type; every other bit as it was.

    An SPS without a VUI gets one that says only that: every other VUI flag 0, which is what
    a decoder assumes without a VUI. ``Mp4Error`` when ``nal`` is not an SPS."""
    layout = _layout(nal)
    out = _BitWriter()

    def signal_type() -> None:
        out.u(1, 1)                              # video_signal_type_present_flag
        out.u(3, _VIDEO_FORMAT_UNSPECIFIED)
        out.u(1, int(tags.full_range))
        out.u(1, 1)                              # colour_description_present_flag
        out.u(8, tags.primaries)
        out.u(8, tags.transfer)
        out.u(8, tags.matrix)

    if layout.signal_flag is None or layout.after_signal is None:
        out.copy(layout.rbsp, 0, layout.vui_flag)
        out.u(1, 1)                              # vui_parameters_present_flag
        out.u(2, 0)                              # aspect ratio, overscan
        signal_type()
        out.u(6, 0)                              # chroma loc, timing, NAL HRD, VCL HRD,
        #                                          pic_struct, bitstream_restriction
    else:
        out.copy(layout.rbsp, 0, layout.signal_flag)
        signal_type()
        out.copy(layout.rbsp, layout.after_signal, layout.stop)
    return nal[:1] + _escape(out.with_trailing_bits())


# ── the boxes (ISO/IEC 14496-12, 14496-15) ───────────────────────────────────


@dataclass(slots=True)
class _Box:
    kind: bytes
    payload: bytes = b""
    children: list[_Box] | None = None
    #: Bytes before the children: a full box's version and count, a sample entry's fields.
    lead: bytes = b""

    def find(self, kind: bytes) -> _Box | None:
        return next((child for child in self.children or () if child.kind == kind), None)

    def path(self, *kinds: bytes) -> _Box | None:
        box: _Box | None = self
        for kind in kinds:
            box = box.find(kind) if box is not None else None
        return box

    def encode(self) -> bytes:
        body = (self.lead + b"".join(child.encode() for child in self.children)
                if self.children is not None else self.payload)
        if len(body) + 8 > _MAX_32:
            raise Mp4Error(f"a {self.kind!r} box larger than 4 GB")
        return struct.pack(">I4s", len(body) + 8, self.kind) + body


def _box_spans(data: bytes, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """(kind, payload start, box end) of each box in ``data[start:end]``."""
    position = start
    while position < end:
        if position + 8 > end:
            raise Mp4Error("a box header runs past its parent")
        size, kind = struct.unpack_from(">I4s", data, position)
        header = 8
        if size == 1:
            if position + 16 > end:
                raise Mp4Error("a box header runs past its parent")
            size = struct.unpack_from(">Q", data, position + 8)[0]
            header = 16
        elif size == 0:
            size = end - position
        if size < header or position + size > end:
            raise Mp4Error(f"the {kind!r} box's size is wrong")
        yield kind, position + header, position + size
        position += size


def _parse(data: bytes, kind: bytes, start: int, end: int) -> _Box:
    lead = 0
    if kind == b"stsd":
        lead = 8                                 # version, flags, entry_count
    elif kind in _VISUAL_ENTRIES:
        lead = _VISUAL_ENTRY_FIELDS
    elif kind not in _CONTAINERS:
        return _Box(kind, payload=data[start:end])
    if start + lead > end:
        raise Mp4Error(f"the {kind!r} box is too short")
    return _Box(kind, lead=data[start:start + lead],
                children=[_parse(data, k, s, e) for k, s, e in _box_spans(data, start + lead, end)])


@dataclass(frozen=True, slots=True)
class _TopBox:
    kind: bytes
    start: int
    header: int
    size: int


def _top_level(handle: BinaryIO, length: int) -> list[_TopBox]:
    """Each top-level box, reading only its header."""
    found = []
    position = 0
    while position < length:
        handle.seek(position)
        head = handle.read(16)
        if len(head) < 8:
            raise Mp4Error("the file ends inside a box header")
        size, kind = struct.unpack_from(">I4s", head)
        header = 8
        if size == 1:
            if len(head) < 16:
                raise Mp4Error("the file ends inside a box header")
            size = struct.unpack_from(">Q", head, 8)[0]
            header = 16
        elif size == 0:
            size = length - position
        if size < header or position + size > length:
            raise Mp4Error(f"the top-level {kind!r} box's size is wrong")
        found.append(_TopBox(kind, position, header, size))
        position += size
    return found


@dataclass(slots=True)
class _Track:
    entry: _Box
    stbl: _Box
    sizes: list[int]
    chunk_offsets: list[int]
    chunk_samples: list[int]
    timescale: int
    durations: tuple[tuple[int, int], ...]

    def spans(self) -> Iterator[tuple[int, int]]:
        """(offset, size) of every sample, in order."""
        index = 0
        for offset, count in zip(self.chunk_offsets, self.chunk_samples, strict=True):
            for _ in range(count):
                size = self.sizes[index]
                yield offset, size
                offset += size
                index += 1


def _table(box: _Box | None, name: str) -> bytes:
    """A full box's payload after version and flags."""
    if box is None or len(box.payload) < 8:
        raise Mp4Error(f"the sample table has no {name}")
    return box.payload[4:]


def _video_track(moov: _Box) -> _Track:
    if moov.find(b"mvex") is not None:
        raise Mp4Error("a fragmented file")
    tracks = [child for child in moov.children or () if child.kind == b"trak"]
    if len(tracks) != 1:
        raise Mp4Error(f"expected one track, found {len(tracks)}")
    mdhd = tracks[0].path(b"mdia", b"mdhd")
    stbl = tracks[0].path(b"mdia", b"minf", b"stbl")
    if stbl is None or mdhd is None or len(mdhd.payload) < 24:
        raise Mp4Error("the track has no sample table")
    stsd = stbl.find(b"stsd")
    entries = stsd.children if stsd is not None and stsd.children is not None else []
    if len(entries) != 1 or entries[0].kind not in _VISUAL_ENTRIES:
        raise Mp4Error("the track is not one video sample entry this module knows")
    timescale = struct.unpack_from(">I", mdhd.payload, 20 if mdhd.payload[0] == 1 else 12)[0]
    sizes_table = _table(stbl.find(b"stsz"), "stsz")
    constant, count = struct.unpack_from(">II", sizes_table)
    if constant:
        raise Mp4Error("a constant sample size")
    sizes = list(struct.unpack_from(f">{count}I", sizes_table, 8))
    offsets_box = stbl.find(b"stco") or stbl.find(b"co64")
    offsets_table = _table(offsets_box, "stco")
    chunks = struct.unpack_from(">I", offsets_table)[0]
    wide = offsets_box is not None and offsets_box.kind == b"co64"
    offsets = list(struct.unpack_from(f">{chunks}{'Q' if wide else 'I'}", offsets_table, 4))
    runs_table = _table(stbl.find(b"stsc"), "stsc")
    runs = [struct.unpack_from(">III", runs_table, 4 + 12 * index)
            for index in range(struct.unpack_from(">I", runs_table)[0])]
    per_chunk: list[int] = []
    for index, (first, per, _description) in enumerate(runs):
        last = runs[index + 1][0] - 1 if index + 1 < len(runs) else chunks
        per_chunk.extend([per] * max(0, last - first + 1))
    if len(per_chunk) != chunks or sum(per_chunk) != count:
        raise Mp4Error("the sample-to-chunk table does not add up")
    times_table = _table(stbl.find(b"stts"), "stts")
    durations = tuple(struct.unpack_from(">II", times_table, 4 + 8 * index)
                      for index in range(struct.unpack_from(">I", times_table)[0]))
    return _Track(entries[0], stbl, sizes, offsets, per_chunk, timescale, durations)


def _layout_of(handle: BinaryIO, length: int) -> tuple[list[_TopBox], _TopBox, _Box]:
    """The top-level boxes, the mdat and the parsed moov, for the one layout rewritten here."""
    boxes = _top_level(handle, length)
    kinds = [box.kind for box in boxes]
    if kinds.count(b"moov") != 1 or kinds.count(b"mdat") != 1 or b"moof" in kinds:
        raise Mp4Error(f"an MP4 layout this module does not read: {kinds}")
    if kinds.index(b"moov") < kinds.index(b"mdat"):
        raise Mp4Error("the moov box comes before the mdat")
    mdat = boxes[kinds.index(b"mdat")]
    moov = boxes[kinds.index(b"moov")]
    handle.seek(moov.start + moov.header)
    data = handle.read(moov.size - moov.header)
    return boxes, mdat, _parse(data, b"moov", 0, len(data))


def _nal_units(sample: bytes, length_size: int) -> Iterator[tuple[int, int]]:
    """(start, end) of each NAL unit of an AVC sample (length-prefixed)."""
    position = 0
    while position < len(sample):
        if position + length_size > len(sample):
            raise Mp4Error("a sample ends inside a NAL length")
        size = int.from_bytes(sample[position:position + length_size], "big")
        start = position + length_size
        if size == 0 or start + size > len(sample):
            raise Mp4Error("a NAL unit runs past its sample")
        yield start, start + size
        position = start + size


def _avcc(entry: _Box) -> tuple[_Box, list[bytes], int]:
    """The avcC box, its SPS units and the NAL length size."""
    box = entry.find(b"avcC")
    if box is None or len(box.payload) < 7:
        raise Mp4Error("an H.264 entry without its avcC")
    payload = box.payload
    position = 6
    sets = []
    for _ in range(payload[5] & 0x1F):
        if position + 2 > len(payload):
            raise Mp4Error("the avcC ends early")
        size = struct.unpack_from(">H", payload, position)[0]
        sets.append(payload[position + 2:position + 2 + size])
        position += 2 + size
    if position > len(payload) or not sets:
        raise Mp4Error("the avcC holds no SPS")
    return box, sets, (payload[4] & 3) + 1


def _colr(entry: _Box) -> ColourTags | None:
    box = entry.find(b"colr")
    if box is None or len(box.payload) < 11 or box.payload[:4] != b"nclx":
        return None
    primaries, transfer, matrix = struct.unpack_from(">HHH", box.payload, 4)
    if max(primaries, transfer, matrix) > 255:
        return None
    return ColourTags(primaries, transfer, matrix, bool(box.payload[10] >> 7))


def read_stream(path: Path, *, read_samples: bool = True) -> StreamInfo:
    """The video track of ``path``: codec, profile, colour statements, samples and timing.
    ``read_samples`` False skips the SPS units inside the samples (no full read of a large
    file). ``Mp4Error`` when it is not a file this module reads."""
    path = Path(path)
    with path.open("rb") as handle:
        _boxes, _mdat, moov = _layout_of(handle, path.stat().st_size)
        track = _video_track(moov)
        entry = track.entry
        width, height = struct.unpack_from(">HH", entry.lead, 24)
        sps: SpsInfo | None = None
        inband: list[ColourTags | None] = []
        if entry.kind in _AVC_ENTRIES:
            _box, sets, length_size = _avcc(entry)
            sps = parse_sps(sets[0])
            for offset, size in track.spans() if read_samples else ():
                handle.seek(offset)
                sample = handle.read(size)
                inband.extend(parse_sps(sample[start:end]).colour
                              for start, end in _nal_units(sample, length_size)
                              if sample[start] & 0x1F == _NAL_SPS)
    return StreamInfo(entry.kind.decode("latin1"), width, height, len(track.sizes), track.timescale,
                      track.durations, sum(track.sizes), sps, _colr(entry), tuple(inband))


def _set_colr(entry: _Box, tags: ColourTags) -> None:
    """The ``nclx`` box in the sample entry: in place of an old one, else before ``btrt``
    (where FFmpeg's muxer puts it), else last."""
    children = entry.children
    assert children is not None
    box = _Box(b"colr", payload=b"nclx" + struct.pack(">HHHB", tags.primaries, tags.transfer,
                                                       tags.matrix, 0x80 if tags.full_range else 0))
    for index, child in enumerate(children):
        if child.kind == b"colr":
            children[index] = box
            return
    at = next((index for index, child in enumerate(children) if child.kind == b"btrt"),
              len(children))
    children.insert(at, box)


def _patched_avcc(avcc: _Box, sets: list[bytes], tags: ColourTags) -> bytes:
    payload = avcc.payload
    rebuilt = bytearray(payload[:6])
    position = 6
    for nal in sets:
        patched = patch_sps_colour(nal, tags)
        rebuilt += struct.pack(">H", len(patched)) + patched
        position += 2 + len(nal)
    return bytes(rebuilt + payload[position:])


def _patched_sample(sample: bytes, length_size: int, tags: ColourTags) -> bytes:
    pieces = []
    position = 0
    for start, end in _nal_units(sample, length_size):
        if sample[start] & 0x1F == _NAL_SPS:
            nal = patch_sps_colour(sample[start:end], tags)
            pieces += [sample[position:start - length_size], len(nal).to_bytes(length_size, "big"),
                       nal]
            position = end
    if not pieces:
        return sample
    pieces.append(sample[position:])
    return b"".join(pieces)


def tag_colour(source: Path, target: Path, tags: ColourTags = BT709_LIMITED) -> StreamInfo:
    """Write ``source`` to ``target`` with ``tags`` stated in the ``colr`` box and in every
    SPS (module docstring); returns what ``target`` says, its samples unread. ``target`` is
    written whole or not at all: ``Mp4Error`` (a layout this module does not rewrite) or
    ``OSError`` remove it, and ``source`` is never changed."""
    source, target = Path(source), Path(target)
    try:
        with source.open("rb") as reading, target.open("wb") as writing:
            _rewrite(reading, source.stat().st_size, writing, tags)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return read_stream(target, read_samples=False)


def _rewrite(reading: BinaryIO, length: int, writing: BinaryIO, tags: ColourTags) -> None:
    boxes, mdat, moov = _layout_of(reading, length)
    track = _video_track(moov)
    entry = track.entry
    _set_colr(entry, tags)
    avc = entry.kind in _AVC_ENTRIES
    length_size = 4
    if avc:
        avcc, sets, length_size = _avcc(entry)
        avcc.payload = _patched_avcc(avcc, sets, tags)
    body_start, body_end = mdat.start + mdat.header, mdat.start + mdat.size
    if any(not body_start <= offset <= body_end for offset in track.chunk_offsets):
        raise Mp4Error("a chunk lies outside the mdat box")
    # A 32-bit mdat that could outgrow 4 GB takes the 8-byte "free" box FFmpeg leaves in front
    # of it for exactly this, and becomes a 64-bit one.
    growth_bound = _SPS_GROWTH_BOUND * len(track.sizes) if avc else 0
    wide = mdat.header == 16 or mdat.size + growth_bound > _MDAT_32_LIMIT
    index = boxes.index(mdat)
    spare = (index > 0 and boxes[index - 1].kind == b"free" and boxes[index - 1].size == 8
             and mdat.header == 8)
    if wide and mdat.header == 8 and not spare:
        raise Mp4Error("the mdat could outgrow its 32-bit size and has no room to widen")
    for box in boxes[:index]:
        if not (spare and wide and box is boxes[index - 1]):
            reading.seek(box.start)
            _copy(reading, writing, box.size)
    header_at = writing.tell()
    header_size = 16 if wide else 8
    writing.write(b"\0" * header_size)
    shift = header_at + header_size - body_start    # where the old body's first byte goes now
    new_sizes: list[int] = []
    new_offsets: list[int] = []
    growth = 0
    cursor = body_start
    sample = 0
    for chunk, count in zip(track.chunk_offsets, track.chunk_samples, strict=True):
        if chunk < cursor:
            raise Mp4Error("chunks overlap or run backwards")
        reading.seek(cursor)
        _copy(reading, writing, chunk - cursor)     # bytes between chunks: none in FFmpeg's files
        new_offsets.append(chunk + shift + growth)
        reading.seek(chunk)
        for _ in range(count):
            old = reading.read(track.sizes[sample])
            if len(old) != track.sizes[sample]:
                raise Mp4Error("the file ends inside a sample")
            new = _patched_sample(old, length_size, tags) if avc else old
            writing.write(new)
            new_sizes.append(len(new))
            growth += len(new) - len(old)
            sample += 1
        cursor = reading.tell()
    reading.seek(cursor)
    _copy(reading, writing, body_end - cursor)
    body = body_end - body_start + growth
    after_mdat = writing.tell()
    writing.seek(header_at)
    writing.write(struct.pack(">I4sQ", 1, b"mdat", body + 16) if wide
                  else struct.pack(">I4s", body + 8, b"mdat"))
    writing.seek(after_mdat)
    _set_samples(track, new_sizes, new_offsets)
    for box in boxes[index + 1:]:
        if box.kind == b"moov":
            writing.write(moov.encode())
        else:
            reading.seek(box.start)
            _copy(reading, writing, box.size)


def _set_samples(track: _Track, sizes: list[int], offsets: list[int]) -> None:
    stsz = track.stbl.find(b"stsz")
    offsets_box = track.stbl.find(b"stco") or track.stbl.find(b"co64")
    assert stsz is not None and offsets_box is not None
    stsz.payload = stsz.payload[:4] + struct.pack(f">II{len(sizes)}I", 0, len(sizes), *sizes)
    if offsets_box.kind == b"stco" and max(offsets, default=0) > _MAX_32:
        offsets_box.kind = b"co64"
    code = "Q" if offsets_box.kind == b"co64" else "I"
    offsets_box.payload = offsets_box.payload[:4] + struct.pack(f">I{len(offsets)}{code}",
                                                                len(offsets), *offsets)


def _copy(reading: BinaryIO, writing: BinaryIO, count: int) -> None:
    while count > 0:
        block = reading.read(min(count, _COPY_BLOCK))
        if not block:
            raise Mp4Error("the file ends early")
        writing.write(block)
        count -= len(block)
