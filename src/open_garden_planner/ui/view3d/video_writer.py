"""Where a tour's frames go: an MP4 file, a PNG sequence or nowhere (L6.2, #390, ADR-072).

``Mp4Writer`` is the app's only use of Qt Multimedia, and it imports it when it is first
asked for: the module costs the app's start nothing. The verified path (ADR-072):

- ``QVideoFrameInput`` → ``QMediaCaptureSession`` → ``QMediaRecorder``, inside the pinned
  PyQt6-Qt6 wheel. Its FFmpeg reports ``LGPL version 2.1 or later`` at run time and was
  configured without ``--enable-gpl``; the bundle grows by about 20 MB.
- H.264 comes from the operating system's own encoder (Windows Media Foundation through
  FFmpeg's ``h264_mf``), so the app ships none. Where a system has none — a Windows N
  edition, Linux — FFmpeg's own MPEG-4 Part 2 encoder writes the file instead (``CODECS``).
- The frames are BT.709 YUV computed here, never RGB (``core/video_yuv.py`` says why: the
  recorder's own conversion gets the colours wrong in every player).
- The encoder works at constant quality (``VIDEO_QUALITIES``), and Qt gives it no way to ask
  for a profile: Media Foundation writes H.264 Constrained Baseline (#807, measured).
- The finished file states what it is (``core/mp4_stream.py``): BT.709 limited range in its
  ``colr`` box and every SPS, and the level its frames need. The recorder states neither.
  That copy is made on a worker thread before the file gets the user's name; if it cannot
  be made, the untagged video is saved, and the log says so.

A writer takes frames as they come and says when it has had enough: ``write`` returns
False while its queue is full, and the caller offers the same frame again. ``finish`` ends
the file; ``finished(ok, message)`` says how it went. Until then the file has a name of its
own (``<stem>.part.mp4``, or a numbered one when that name is kept from an earlier render),
so a cancelled or failed tour never replaces a good video and never leaves half of one under
the name the user chose.
"""

from __future__ import annotations

import logging
import os
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
from PyQt6.QtCore import QCoreApplication, QObject, QSize, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QImage

from open_garden_planner.core.mp4_stream import Mp4Error, StreamInfo, tag_colour
from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.video_yuv import rgb_to_yuv420

__all__ = ["CODECS", "DEFAULT_VIDEO_QUALITY", "VIDEO_QUALITIES", "FrameSink", "Mp4Writer", "NullWriter",
           "PngSequenceWriter", "VideoError", "best_codec", "frame_name"]

_LOG: Final = logging.getLogger(__name__)

#: What a file may be encoded with, best first, by ``QMediaFormat.VideoCodec`` name. H.264
#: plays everywhere and is what the video platforms ask for; MPEG-4 is the fallback every
#: FFmpeg build can write.
CODECS: Final = ("H264", "MPEG4")
#: The dialog's video qualities, as ``Mp4Writer(quality=)`` names them (#807). A video is
#: encoded at CONSTANT QUALITY: Qt's average-bit-rate mode is Media Foundation's CBR, which
#: starves the first second of every video and stops buying detail near 32 Mbit/s (ADR-072
#: addendum "review-grade video"). Qt hands Media Foundation the quality as 90 or 100.
VIDEO_QUALITIES: Final = ("standard", "best")
DEFAULT_VIDEO_QUALITY: Final = "standard"
_RECORDER_QUALITY: Final = {"standard": "HighQuality", "best": "VeryHighQuality"}
#: How often ``finish`` looks whether the recorder or the PNG writers are done, ms.
_POLL_MS: Final = 20
#: A recorder that takes longer than this to close its file has failed, seconds.
_STOP_LIMIT_S: Final = 120.0
#: PNG frames being written at once. More would only hold 4K frames in memory: the writers
#: spend their time compressing, and each frame then waits for a free writer anyway.
_PNG_WRITERS: Final = 2
_PNG_QUEUE: Final = 4
#: Qt's PNG quality: speed over a few percent of size, for frames that are an intermediate.
#: Measured on a 4K picture: 495 ms and 15.5 MB, against 1384 ms and 14.5 MB at the default.
_PNG_QUALITY: Final = 70


class VideoError(RuntimeError):
    """A writer could not start (no encoder, a folder that cannot be written)."""


class FrameSink(Protocol):
    """What ``TourRecorder`` writes to."""

    finished: Any

    def start(self) -> None: ...
    def write(self, image: QImage) -> bool: ...
    def finish(self) -> None: ...
    def abort(self) -> None: ...


def _tr(text: str) -> str:
    return QCoreApplication.translate("TourDialog", text)


def _multimedia() -> Any:
    """Qt Multimedia, or ``VideoError`` when this build cannot load it."""
    try:
        from PyQt6 import QtMultimedia
    except ImportError as error:
        raise VideoError(_tr("Video is not available in this build of the app.")) from error
    return QtMultimedia


def best_codec() -> str | None:
    """The first of ``CODECS`` this system can encode into an MP4; None: none of them."""
    media = _multimedia()
    wanted = media.QMediaFormat(media.QMediaFormat.FileFormat.MPEG4)
    available = {codec.name for codec in
                 wanted.supportedVideoCodecs(media.QMediaFormat.ConversionMode.Encode)}
    return next((codec for codec in CODECS if codec in available), None)


class _Sink(QObject):
    finished = pyqtSignal(bool, str)


class NullWriter(_Sink):
    """A preview's writer: the frames go nowhere."""

    def start(self) -> None:
        pass

    def write(self, _image: QImage) -> bool:
        return True

    def finish(self) -> None:
        self.finished.emit(True, "")

    def abort(self) -> None:
        self.finished.emit(False, "")


class Mp4Writer(_Sink):
    """An MP4 of ``size`` (even sides) at ``fps`` and one of ``VIDEO_QUALITIES``. GUI thread
    (module docstring)."""

    def __init__(self, path: Path, size: tuple[int, int], fps: int,
                 parent: QObject | None = None, *, quality: str = DEFAULT_VIDEO_QUALITY) -> None:
        super().__init__(parent)
        if size[0] % 2 or size[1] % 2:
            raise ValueError(f"a video's sides must be even, got {size}")
        if quality not in VIDEO_QUALITIES:
            raise ValueError(f"a video's quality is one of {VIDEO_QUALITIES}, got {quality!r}")
        self.quality = quality
        self.path = Path(path)
        #: The render's own name. A kept render (its target was held open by a player)
        #: must not be deleted by the NEXT recording of the same name, so a part that is
        #: already there is given a fresh number (issue #731).
        self.part_path = self._free_part_path(self.path)
        self.size = (int(size[0]), int(size[1]))
        self.fps = int(fps)
        self.codec: str | None = None
        self.frames_sent = 0
        #: What the finished file states (profile, level, colour), once it is delivered;
        #: None before, or when the file could not be read back.
        self.stream: StreamInfo | None = None
        self._input: Any = None
        self._session: Any = None
        self._recorder: Any = None
        self._format: Any = None
        self._error = ""
        self._aborted = False
        self._waited_ms = 0
        #: The frame a full queue refused, with the picture it came from: a retry offers
        #: the very same frame instead of computing its YUV planes again (#738).
        self._retry: tuple[int, Any] | None = None
        self._poll = QTimer(self)
        self._poll.setInterval(_POLL_MS)
        self._poll.timeout.connect(self._look_if_stopped)
        #: The finished file being tagged and moved to its name (``_deliver``), off the GUI
        #: thread: a 4K render is gigabytes to copy.
        self._delivery: Future[tuple[bool, str]] | None = None
        self._delivery_pool: ThreadPoolExecutor | None = None

    @staticmethod
    def _free_part_path(path: Path) -> Path:
        """``<stem>.part<suffix>``, or a numbered one when that name is taken: a finished
        render whose target could not be replaced is kept, and this is how the next
        recording leaves it alone."""
        candidate = path.with_name(f"{path.stem}.part{path.suffix}")
        index = 2
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}.part{index}{path.suffix}")
            index += 1
        return candidate

    def start(self) -> None:
        media = _multimedia()
        self.codec = best_codec()
        if self.codec is None:
            raise VideoError(_tr("This computer has no video encoder for MP4 files. "
                                 "Save a PNG sequence instead."))
        width, height = self.size
        frames = media.QVideoFrameFormat(QSize(width, height),
                                         media.QVideoFrameFormat.PixelFormat.Format_YUV420P)
        frames.setStreamFrameRate(self.fps)
        frames.setColorSpace(media.QVideoFrameFormat.ColorSpace.ColorSpace_BT709)
        frames.setColorRange(media.QVideoFrameFormat.ColorRange.ColorRange_Video)
        frames.setColorTransfer(media.QVideoFrameFormat.ColorTransfer.ColorTransfer_BT709)
        self._format = frames
        self._input = media.QVideoFrameInput(frames)
        self._session = media.QMediaCaptureSession()
        self._recorder = media.QMediaRecorder()
        self._session.setVideoFrameInput(self._input)
        self._session.setRecorder(self._recorder)
        wanted = media.QMediaFormat(media.QMediaFormat.FileFormat.MPEG4)
        wanted.setVideoCodec(getattr(media.QMediaFormat.VideoCodec, self.codec))
        self._recorder.setMediaFormat(wanted)
        self._recorder.setVideoResolution(QSize(width, height))
        self._recorder.setVideoFrameRate(self.fps)
        self._recorder.setEncodingMode(media.QMediaRecorder.EncodingMode.ConstantQualityEncoding)
        self._recorder.setQuality(getattr(media.QMediaRecorder.Quality,
                                          _RECORDER_QUALITY[self.quality]))
        self._recorder.setOutputLocation(QUrl.fromLocalFile(str(self.part_path)))
        # errorOccurred carries an enum PyQt6 cannot connect (measured): errorChanged has none
        self._recorder.errorChanged.connect(self._on_error)
        try:
            self.part_path.unlink(missing_ok=True)
        except OSError as error:   # nothing moved yet: the dialog says it, and nothing is lost
            self._release()
            raise VideoError(_tr("The video file {path} cannot be written: {error}").format(
                path=self.part_path, error=error)) from error
        self._recorder.record()

    def _on_error(self) -> None:
        recorder = self._recorder
        if recorder is not None and recorder.error() != _multimedia().QMediaRecorder.Error.NoError:
            self._error = str(recorder.errorString())
            _LOG.error("Video: the recorder failed: %s", log_text(self._error))

    @property
    def error(self) -> str:
        return self._error

    def write(self, image: QImage) -> bool:
        """Offer one frame: True when it was taken, False when the queue is full (offer it
        again). ``VideoError`` when the recorder has failed."""
        if self._error:
            raise VideoError(self._error)
        media = _multimedia()
        key = image.cacheKey()
        retry = self._retry
        if retry is not None and retry[0] == key:
            frame = retry[1]   # the same frame, not its YUV planes a second time
        else:
            self._retry = None
            frame = media.QVideoFrame(self._format)
            if not frame.map(media.QVideoFrame.MapMode.WriteOnly):
                raise VideoError(_tr("A video frame could not be prepared."))
            try:
                self._fill(frame, image)
            finally:
                frame.unmap()
            step = 1_000_000 / self.fps
            frame.setStartTime(round(self.frames_sent * step))
            frame.setEndTime(round((self.frames_sent + 1) * step))
        if not self._input.sendVideoFrame(frame):
            self._retry = (key, frame)
            return False
        self._retry = None
        self.frames_sent += 1
        return True

    def _fill(self, frame: Any, image: QImage) -> None:
        width, height = self.size
        if (image.width(), image.height()) != (width, height):
            raise VideoError(f"a frame of {image.width()} x {image.height()} for a "
                             f"{width} x {height} video")
        pixels = image.convertToFormat(QImage.Format.Format_RGBX8888)
        bits = pixels.constBits()
        if bits is None:
            raise VideoError(_tr("A video frame could not be prepared."))
        rows = np.frombuffer(bits.asstring(pixels.sizeInBytes()), np.uint8).reshape(
            height, pixels.bytesPerLine())
        planes = rgb_to_yuv420(rows[:, :width * 4].reshape(height, width, 4))
        for plane, values in enumerate(planes):
            stride = frame.bytesPerLine(plane)
            target = frame.bits(plane)
            target.setsize(frame.mappedBytes(plane))
            view = np.frombuffer(target, np.uint8).reshape(-1, stride)
            view[:values.shape[0], :values.shape[1]] = values

    def finish(self) -> None:
        """End the file; ``finished`` follows when it is closed."""
        if self._delivery is not None:   # closed, being tagged: its own end says how it went
            return
        if self._recorder is None:
            self.finished.emit(False, self._error)
            return
        self._recorder.stop()
        self._waited_ms = 0
        self._poll.start()

    def abort(self) -> None:
        """Cancel: the recording ends and its file goes; ``finished`` follows."""
        self._aborted = True
        self.finish()

    def _look_if_stopped(self) -> None:
        recorder = self._recorder
        media = _multimedia()
        self._waited_ms += _POLL_MS
        stopped = recorder.recorderState() == media.QMediaRecorder.RecorderState.StoppedState
        if not stopped and self._waited_ms < _STOP_LIMIT_S * 1000.0:
            return
        self._poll.stop()
        if not stopped:
            self._error = self._error or _tr("The video file could not be closed.")
        self._close(stopped)

    def _close(self, stopped: bool) -> None:
        self._release()
        if self._aborted or self._error or not stopped:
            self._discard_part()
            self.finished.emit(False, self._error)
            return
        # The rest copies a file of up to gigabytes: a worker does it, the GUI thread polls.
        # The thread is not a daemon, so a closing app still ends with the file in its place.
        self._delivery_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tour-mp4")
        self._delivery = self._delivery_pool.submit(self._deliver)
        self._poll.timeout.disconnect(self._look_if_stopped)
        self._poll.timeout.connect(self._look_if_delivered)
        self._poll.start()

    def _deliver(self) -> tuple[bool, str]:
        """Worker thread, no Qt: the finished part tagged (``core/mp4_stream.py``) and moved
        to the user's name. A part that cannot be tagged is moved as it is: the tags are a
        statement about the render, never a reason to lose it."""
        source = self.part_path
        tagged: Path | None = None
        try:
            handle, name = tempfile.mkstemp(prefix=f"{self.path.stem}.", suffix=".tmp.mp4",
                                            dir=self.part_path.parent)
            os.close(handle)
            tagged = Path(name)
            self.stream = tag_colour(self.part_path, tagged)
            source = tagged
        except (Mp4Error, OSError) as error:
            if tagged is not None:
                tagged.unlink(missing_ok=True)
            tagged = None
            _LOG.warning("Video: %s is saved untagged (%s: %s)", log_text(self.path),
                         type(error).__name__, log_text(error))
        try:
            os.replace(source, self.path)
        except OSError as error:   # the old file is open somewhere: the render is finished, keep it
            _LOG.warning("Video: %s could not be replaced (%s)", log_text(self.path), log_text(error))
            if tagged is not None:
                try:   # the render kept by the part's name is the tagged one, where it can be
                    os.replace(tagged, self.part_path)
                except OSError:
                    tagged.unlink(missing_ok=True)   # the part itself is the whole render
            return False, _tr(
                "{path} could not be replaced ({error}). The video is saved as {part}.").format(
                    path=self.path, error=error, part=self.part_path)
        if tagged is not None:
            self._discard_part()
        self._log_delivered()
        return True, ""

    def _log_delivered(self) -> None:
        stream = self.stream
        if stream is None:
            return
        sps = stream.sps
        _LOG.info("Video: %s - %s, %s level %s, %d x %d, %d frames, %.1f Mbit/s, quality %s, "
                  "colour %s", log_text(self.path), stream.codec,
                  sps.profile if sps is not None else "-", sps.level if sps is not None else "-",
                  stream.width, stream.height, stream.samples, stream.bit_rate / 1e6,
                  self.quality, stream.tagged)

    def _look_if_delivered(self) -> None:
        delivery = self._delivery
        if delivery is None or not delivery.done():
            return
        self._poll.stop()
        pool, self._delivery_pool = self._delivery_pool, None
        if pool is not None:
            pool.shutdown(wait=False)
        failure = delivery.exception()
        if failure is not None:   # a bug in the delivery itself: say it, never hang the dialog
            _LOG.error("Video: delivering %s failed (%s: %s)", log_text(self.path),
                       type(failure).__name__, log_text(failure))
            self.finished.emit(False, f"{type(failure).__name__}: {failure}")
            return
        ok, message = delivery.result()
        self.finished.emit(ok, message)

    def _discard_part(self) -> None:
        """The part file goes, if it can: whoever holds it (a thumbnailer, a scanner) must not
        stop ``finished``. A kept render is never deleted by a later run; each run takes a
        free part name of its own (``_free_part_path``)."""
        try:
            self.part_path.unlink(missing_ok=True)
        except OSError as error:
            _LOG.warning("Video: %s stays behind (%s)", log_text(self.part_path), log_text(error))

    def _release(self) -> None:
        self._retry = None
        self._input = self._session = self._recorder = self._format = None


def frame_name(index: int) -> str:
    """A PNG frame's file name: numbered from 1, the way every video editor reads them."""
    return f"frame_{index + 1:06d}.png"


class PngSequenceWriter(_Sink):
    """One PNG per frame in ``folder`` (created; refused when it already holds frames, so
    two tours never mix). Written on a small pool: a 4K PNG takes about a second, and the
    GUI thread stays with the render."""

    def __init__(self, folder: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.folder = Path(folder)
        self.frames_sent = 0
        self._pool: ThreadPoolExecutor | None = None
        self._pending: list[Future[bool]] = []
        self._error = ""
        self._poll = QTimer(self)
        self._poll.setInterval(_POLL_MS)
        self._poll.timeout.connect(self._look_if_done)

    def start(self) -> None:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise VideoError(str(error)) from error
        if any(self.folder.glob("frame_*.png")):
            raise VideoError(_tr("This folder already holds the frames of another tour. "
                                 "Choose an empty one."))
        self._pool = ThreadPoolExecutor(max_workers=_PNG_WRITERS, thread_name_prefix="tour-png")

    def _collect(self) -> None:
        for future in [future for future in self._pending if future.done()]:
            self._pending.remove(future)
            failure = future.exception()
            if failure is not None:
                self._error = str(failure)
            elif not future.result():
                self._error = _tr("A frame could not be saved. Is the disk full?")

    def write(self, image: QImage) -> bool:
        self._collect()
        if self._error:
            raise VideoError(self._error)
        pool = self._pool
        if pool is None:
            raise VideoError("the writer was not started")
        if len(self._pending) >= _PNG_QUEUE:
            return False
        path = self.folder / frame_name(self.frames_sent)
        # QImage is implicitly shared and the worker only reads it
        self._pending.append(pool.submit(image.save, str(path), "PNG", _PNG_QUALITY))
        self.frames_sent += 1
        return True

    def finish(self) -> None:
        self._poll.start()

    def abort(self) -> None:
        """Cancel: the frames written so far stay (a sequence is usable to where it got)."""
        self.finish()

    def _look_if_done(self) -> None:
        self._collect()
        if self._pending:
            return
        self._poll.stop()
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=False)
        self.finished.emit(not self._error, self._error)
