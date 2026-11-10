"""The colour tags of a tour's MP4 (#807, ``core/mp4_colour.py``). Qt-free.

The SPS units here are written bit by bit from the H.264 syntax (7.3.2.1.1, Annex E), and the
MP4s are built box by box, so every branch the rewriter takes is one a test chose. The real
encoder's own file is read in ``tests/integration/test_video_writer.py``.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from open_garden_planner.core import mp4_colour
from open_garden_planner.core.mp4_colour import (
    BT709_LIMITED,
    ColourTags,
    Mp4Error,
    parse_sps,
    patch_sps_colour,
    read_stream,
    tag_colour,
)

#: The SPS Windows' H.264 encoder wrote for a 1280 x 720 tour (Constrained Baseline 3.1, a VUI
#: with timing only, two emulation prevention bytes): ``tests`` read the real thing too.
MEDIA_FOUNDATION_SPS = bytes.fromhex("6742c01f95a014016e84000003000400000300f03682211a80")


class Bits:
    """An RBSP written field by field."""

    def __init__(self) -> None:
        self.bits: list[int] = []

    def u(self, count: int, value: int) -> Bits:
        self.bits += [(value >> shift) & 1 for shift in range(count - 1, -1, -1)]
        return self

    def ue(self, value: int) -> Bits:
        code = value + 1
        length = code.bit_length()
        return self.u(length - 1, 0).u(length, code)

    def se(self, value: int) -> Bits:
        return self.ue(2 * value - 1 if value > 0 else -2 * value)

    def nal(self) -> bytes:
        bits = [*self.bits, 1]
        bits += [0] * (-len(bits) % 8)
        rbsp = bytes(sum(bit << (7 - k) for k, bit in enumerate(bits[i:i + 8]))
                     for i in range(0, len(bits), 8))
        return b"\x67" + mp4_colour._escape(rbsp)


def sps(*, profile: int = 66, width_mbs: int = 80, height_mbs: int = 45, crop_bottom: int = 0,
        vui: Bits | None = None, scaling: bool = False) -> bytes:
    """An SPS of a progressive 4:2:0 stream, ``vui`` its VUI's bits (None: no VUI)."""
    bits = Bits().u(8, profile).u(8, 0xC0 if profile == 66 else 0).u(8, 40).ue(0)
    if profile == 100:
        bits.ue(1).ue(0).ue(0).u(1, 0).u(1, int(scaling))
        if scaling:
            for index in range(8):
                present = index in (0, 6)
                bits.u(1, int(present))
                if present:   # a list of deltas that ends early (next scale 0)
                    bits.se(4).se(-3).se(-9)
    bits.ue(0).ue(2).ue(1).u(1, 0).ue(width_mbs - 1).ue(height_mbs - 1).u(1, 1).u(1, 1)
    if crop_bottom:
        bits.u(1, 1).ue(0).ue(0).ue(0).ue(crop_bottom)
    else:
        bits.u(1, 0)
    if vui is None:
        bits.u(1, 0)
    else:
        bits.u(1, 1).bits += vui.bits
    return bits.nal()


def timing_vui(*, sar: bool = False, signal: tuple[int, ...] | None = None) -> Bits:
    """Aspect ratio (optionally an explicit SAR), a video signal type (``signal``: format and
    range, or format, range and three colour code points), timing at 30 fps, then a
    bitstream restriction: the fields on both sides of what the patch rewrites."""
    vui = Bits()
    vui.u(1, 1).u(8, 255).u(16, 4).u(16, 3) if sar else vui.u(1, 0)
    vui.u(1, 0)                                          # overscan
    if signal is None:
        vui.u(1, 0)
    else:
        vui.u(1, 1).u(3, signal[0]).u(1, signal[1])
        if len(signal) == 5:
            vui.u(1, 1).u(8, signal[2]).u(8, signal[3]).u(8, signal[4])
        else:
            vui.u(1, 0)
    vui.u(1, 0)                                          # chroma loc
    vui.u(1, 1).u(32, 1).u(32, 60).u(1, 1)               # timing
    vui.u(1, 0).u(1, 0).u(1, 0)                          # HRDs, pic_struct
    vui.u(1, 1).u(1, 1).ue(0).ue(0).ue(16).ue(16).ue(0).ue(1)   # bitstream restriction
    return vui


def without_colour(nal: bytes) -> tuple[object, ...]:
    info = parse_sps(nal)
    return (info.profile_idc, info.constraints, info.level_idc, info.width, info.height, info.timing)


VARIANTS = {
    "media foundation": MEDIA_FOUNDATION_SPS,
    "no VUI": sps(),
    "VUI with timing": sps(vui=timing_vui()),
    "explicit SAR": sps(vui=timing_vui(sar=True)),
    "signal type, no colour": sps(vui=timing_vui(signal=(5, 1))),
    "signal type, BT.601": sps(vui=timing_vui(signal=(2, 0, 6, 6, 6))),
    "High with scaling lists": sps(profile=100, scaling=True, vui=timing_vui()),
    "cropped 1080p": sps(width_mbs=120, height_mbs=68, crop_bottom=4, vui=timing_vui()),
}


def test_the_media_foundation_sps_reads_as_the_encoder_wrote_it() -> None:
    info = parse_sps(MEDIA_FOUNDATION_SPS)
    assert info.profile == "Constrained Baseline" and info.level == 3.1
    assert (info.width, info.height) == (1280, 720)
    assert info.colour is None, "the encoder states no colour: the reason for this module"
    assert info.timing == (1, 60, False)


@pytest.mark.parametrize("nal", VARIANTS.values(), ids=VARIANTS.keys())
def test_a_patched_sps_states_bt709_and_keeps_every_other_field(nal: bytes) -> None:
    patched = patch_sps_colour(nal)
    assert parse_sps(patched).colour == BT709_LIMITED
    assert without_colour(patched) == without_colour(nal)
    assert patch_sps_colour(patched) == patched, "patching twice changes nothing"


@pytest.mark.parametrize("nal", VARIANTS.values(), ids=VARIANTS.keys())
def test_a_patched_sps_keeps_the_bits_after_the_signal_type_and_is_well_escaped(nal: bytes) -> None:
    """The bitstream restriction and everything else behind the rewritten fields survive bit
    for bit; no start code can appear inside the unit."""
    before, after = mp4_colour._layout(nal), mp4_colour._layout(patch_sps_colour(nal))
    if before.after_signal is not None:
        assert after.after_signal is not None
        tail = before.rbsp, before.after_signal, before.stop
        new_tail = after.rbsp, after.after_signal, after.stop

        def bits(rbsp: bytes, start: int, end: int) -> list[int]:
            return [(rbsp[i >> 3] >> (7 - (i & 7))) & 1 for i in range(start, end)]

        assert bits(*tail) == bits(*new_tail)
    payload = patch_sps_colour(nal)[1:]
    assert not any(payload[i:i + 2] == b"\0\0" and payload[i + 2] <= 3 and payload[i + 2] != 3
                   for i in range(len(payload) - 2))


def test_the_sizes_come_from_the_macroblocks_and_the_crop() -> None:
    assert (parse_sps(VARIANTS["cropped 1080p"]).width, parse_sps(VARIANTS["cropped 1080p"]).height) == (1920, 1080)


def test_other_tags_are_written_as_asked() -> None:
    full = ColourTags(9, 16, 9, True)
    assert parse_sps(patch_sps_colour(MEDIA_FOUNDATION_SPS, full)).colour == full


@pytest.mark.parametrize("nal", [b"", b"\x68\xce\x38\x80", b"\x67\x42"])
def test_what_is_not_a_whole_sps_is_refused(nal: bytes) -> None:
    with pytest.raises(Mp4Error):
        patch_sps_colour(nal)


def test_colour_code_points_are_bytes() -> None:
    with pytest.raises(ValueError):
        ColourTags(256, 1, 1, False)


# ── MP4s built box by box ────────────────────────────────────────────────────


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def full_box(kind: bytes, payload: bytes) -> bytes:
    return box(kind, b"\0\0\0\0" + payload)


def nal(kind: int, body: bytes) -> bytes:
    unit = bytes([0x60 | kind]) + body
    return struct.pack(">I", len(unit)) + unit


PPS = b"\xce\x38\x80"
AUD, SEI = nal(9, b"\xf0"), nal(6, b"\x05\x01\x00\x80")


def samples_of(sps_unit: bytes, count: int = 6, gop: int = 3) -> list[bytes]:
    """IDR samples (with the SPS and PPS in-band, as Media Foundation writes them) every
    ``gop`` frames, P frames between."""
    out = []
    for index in range(count):
        if index % gop == 0:
            out.append(AUD + struct.pack(">I", len(sps_unit)) + sps_unit + nal(8, PPS) + SEI
                       + nal(5, bytes([0x88, index]) * 40))
        else:
            out.append(AUD + nal(1, bytes([0x9A, index]) * 25))
    return out


def mp4(samples: list[bytes], *, sps_unit: bytes = MEDIA_FOUNDATION_SPS, entry: bytes = b"avc1",
        per_chunk: int = 4, moov_first: bool = False, tracks: int = 1, gap: bytes = b"") -> bytes:
    """ftyp, free, mdat, moov as FFmpeg's muxer writes them (or moov first)."""
    ftyp = box(b"ftyp", b"iso4\0\0\2\0iso4isomiso2avc1mp41")
    free = box(b"free", b"")
    chunks = [samples[i:i + per_chunk] for i in range(0, len(samples), per_chunk)]
    body = b"".join(gap + b"".join(chunk) for chunk in chunks)

    def moov_bytes(mdat_body_at: int) -> bytes:
        offsets, position = [], mdat_body_at
        for chunk in chunks:
            position += len(gap)
            offsets.append(position)
            position += sum(map(len, chunk))
        fields = bytearray(78)
        fields[6:8] = b"\0\1"
        fields[24:28] = struct.pack(">HH", 1280, 720)
        avcc = box(b"avcC", bytes([1, 0x42, 0xC0, 0x1F, 0xFF, 0xE1]) + struct.pack(">H", len(sps_unit))
                   + sps_unit + b"\1" + struct.pack(">H", len(PPS) + 1) + b"\x68" + PPS)
        children = (avcc if entry != b"mp4v" else box(b"esds", b"\0" * 20)) + box(b"pasp", b"\0\0\0\1\0\0\0\1") \
            + box(b"btrt", b"\0" * 12)
        stsd = full_box(b"stsd", struct.pack(">I", 1) + box(entry, bytes(fields) + children))
        stbl = box(b"stbl", stsd
                   + full_box(b"stts", struct.pack(">III", 1, len(samples), 512))
                   + full_box(b"stss", struct.pack(">III", 2, 1, 4))
                   + full_box(b"stsc", struct.pack(">IIII", 1, 1, per_chunk, 1)
                              if len(samples) % per_chunk == 0 else
                              struct.pack(">IIIIIII", 2, 1, per_chunk, 1, len(chunks),
                                          len(samples) % per_chunk, 1))
                   + full_box(b"stsz", struct.pack(f">II{len(samples)}I", 0, len(samples),
                                                   *map(len, samples)))
                   + full_box(b"stco", struct.pack(f">I{len(offsets)}I", len(offsets), *offsets)))
        mdhd = full_box(b"mdhd", struct.pack(">IIIIHH", 0, 0, 15360, 512 * len(samples), 0x55C4, 0))
        trak = box(b"trak", full_box(b"tkhd", b"\0" * 80) + box(b"mdia", mdhd + full_box(b"hdlr", b"\0" * 21)
                                                                 + box(b"minf", stbl)))
        return box(b"moov", full_box(b"mvhd", b"\0" * 96) + trak * tracks)

    if moov_first:
        guess = moov_bytes(0)
        return ftyp + free + moov_bytes(len(ftyp) + len(free) + len(guess) + 8) + box(b"mdat", body)
    return ftyp + free + box(b"mdat", body) + moov_bytes(len(ftyp) + len(free) + 8)


def write(tmp_path: Path, data: bytes, name: str = "tour.part.mp4") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def nal_bodies(path: Path) -> list[list[bytes]]:
    """Every sample's NAL units, through the file's own tables (offsets, sizes, chunks)."""
    data = path.read_bytes()
    with path.open("rb") as handle:
        _boxes, _mdat, moov = mp4_colour._layout_of(handle, len(data))
    track = mp4_colour._video_track(moov)
    out = []
    for offset, size in track.spans():
        sample = data[offset:offset + size]
        out.append([sample[s:e] for s, e in mp4_colour._nal_units(sample, 4)])
    return out


def test_an_untagged_file_reads_as_untagged(tmp_path: Path) -> None:
    info = read_stream(write(tmp_path, mp4(samples_of(MEDIA_FOUNDATION_SPS))))
    assert info.codec == "avc1" and (info.width, info.height) == (1280, 720)
    assert info.sps is not None and info.sps.profile == "Constrained Baseline"
    assert info.colr is None and info.inband_colour == (None, None) and info.tagged is None
    assert info.samples == 6 and info.timescale == 15360 and info.durations == ((6, 512),)
    assert info.duration_s == pytest.approx(0.2)


@pytest.mark.parametrize("per_chunk", [1, 4, 6])
def test_a_tagged_file_states_bt709_everywhere_and_keeps_every_frame(tmp_path: Path, per_chunk: int) -> None:
    samples = samples_of(MEDIA_FOUNDATION_SPS, count=7)
    source = write(tmp_path, mp4(samples, per_chunk=per_chunk))
    original = source.read_bytes()
    target = tmp_path / "tour.tagged.mp4"
    said = tag_colour(source, target)
    assert source.read_bytes() == original, "the render itself is never changed"
    assert said.colr == BT709_LIMITED and said.sps is not None and said.sps.colour == BT709_LIMITED
    full = read_stream(target)
    assert full.tagged == BT709_LIMITED and full.inband_colour == (BT709_LIMITED,) * 3
    assert (full.samples, full.timescale, full.durations) == (7, 15360, ((7, 512),))
    before, after = nal_bodies(source), nal_bodies(target)
    assert [len(units) for units in before] == [len(units) for units in after]
    for old_units, new_units in zip(before, after, strict=True):
        for old, new in zip(old_units, new_units, strict=True):
            if old[0] & 0x1F == 7:
                assert without_colour(new) == without_colour(old)
            else:
                assert new == old, "every unit but the SPS is the same, byte for byte"


def test_the_colr_box_sits_before_btrt_and_an_old_one_is_replaced(tmp_path: Path) -> None:
    source = write(tmp_path, mp4(samples_of(MEDIA_FOUNDATION_SPS)))
    once, twice = tmp_path / "once.mp4", tmp_path / "twice.mp4"
    tag_colour(source, once, ColourTags(6, 6, 6, False))
    tag_colour(once, twice)
    with twice.open("rb") as handle:
        _boxes, _mdat, moov = mp4_colour._layout_of(handle, twice.stat().st_size)
    entry = mp4_colour._video_track(moov).entry
    assert [child.kind for child in entry.children or ()] == [b"avcC", b"pasp", b"colr", b"btrt"]
    assert read_stream(twice).tagged == BT709_LIMITED
    tag_colour(twice, tmp_path / "thrice.mp4")
    assert (tmp_path / "thrice.mp4").read_bytes() == twice.read_bytes(), "tagging is idempotent"


def test_bytes_between_chunks_are_kept_and_the_offsets_follow(tmp_path: Path) -> None:
    source = write(tmp_path, mp4(samples_of(MEDIA_FOUNDATION_SPS), per_chunk=2, gap=b"pad!"))
    target = tmp_path / "tagged.mp4"
    tag_colour(source, target)
    assert read_stream(target).tagged == BT709_LIMITED
    assert len(nal_bodies(target)) == 6


def test_an_sps_without_a_vui_gets_one_in_the_file_too(tmp_path: Path) -> None:
    plain = sps()
    source = write(tmp_path, mp4(samples_of(plain), sps_unit=plain))
    target = tmp_path / "tagged.mp4"
    tag_colour(source, target)
    assert read_stream(target).tagged == BT709_LIMITED


def test_an_mpeg4_part2_file_gets_the_colr_box(tmp_path: Path) -> None:
    """The fallback codec has no SPS; the container states the colour."""
    samples = [b"\0\0\1\xb6" + bytes([index]) * 30 for index in range(4)]
    source = write(tmp_path, mp4(samples, entry=b"mp4v"))
    target = tmp_path / "tagged.mp4"
    said = tag_colour(source, target)
    assert said.codec == "mp4v" and said.sps is None and said.colr == BT709_LIMITED
    assert said.tagged == BT709_LIMITED


def test_a_file_that_could_outgrow_a_32_bit_mdat_takes_the_free_box(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FFmpeg leaves an 8-byte ``free`` box in front of the mdat to widen it later; a file
    whose samples could grow past 4 GB takes it (the limit is lowered to test it)."""
    source = write(tmp_path, mp4(samples_of(MEDIA_FOUNDATION_SPS)))
    monkeypatch.setattr(mp4_colour, "_MDAT_32_LIMIT", 64)
    target = tmp_path / "tagged.mp4"
    tag_colour(source, target)
    data = target.read_bytes()
    assert source.stat().st_size + 40 > target.stat().st_size >= source.stat().st_size
    with target.open("rb") as handle:
        kinds = [(box.kind, box.header) for box in mp4_colour._top_level(handle, len(data))]
    assert kinds == [(b"ftyp", 8), (b"mdat", 16), (b"moov", 8)]
    assert read_stream(target).tagged == BT709_LIMITED


@pytest.mark.parametrize("layout", ["moov first", "two tracks", "truncated", "not mp4", "constant size"])
def test_a_layout_it_does_not_rewrite_is_refused_and_leaves_no_file(tmp_path: Path, layout: str) -> None:
    samples = samples_of(MEDIA_FOUNDATION_SPS)
    data = {
        "moov first": lambda: mp4(samples, moov_first=True),
        "two tracks": lambda: mp4(samples, tracks=2),
        "truncated": lambda: mp4(samples)[:-30],
        "not mp4": lambda: b"\0\0\0\x10junkjunkjunkjunk",
        "constant size": lambda: mp4([samples[1]] * 4).replace(
            struct.pack(">II", 0, 4), struct.pack(">II", len(samples[1]), 4), 1),
    }[layout]()
    source = write(tmp_path, data)
    target = tmp_path / "tagged.mp4"
    with pytest.raises(Mp4Error):
        tag_colour(source, target)
    assert not target.exists()
    assert source.read_bytes() == data


def test_a_write_that_fails_leaves_no_partial_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write(tmp_path, mp4(samples_of(MEDIA_FOUNDATION_SPS)))
    target = tmp_path / "tagged.mp4"

    def full_disk(*_arguments: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(mp4_colour, "_set_samples", full_disk)
    with pytest.raises(OSError):
        tag_colour(source, target)
    assert not target.exists()


def test_the_bit_rate_is_the_samples_over_their_duration(tmp_path: Path) -> None:
    samples = samples_of(MEDIA_FOUNDATION_SPS)
    info = read_stream(write(tmp_path, mp4(samples)))
    assert info.video_bytes == sum(map(len, samples))
    assert info.bit_rate == pytest.approx(sum(map(len, samples)) * 8 / 0.2)
