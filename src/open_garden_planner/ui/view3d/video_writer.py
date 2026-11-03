"""Where a tour's frames go: an MP4 file, a PNG sequence or nowhere (L6.2, #390, ADR-071).

``Mp4Writer`` is the app's only use of Qt Multimedia, and it imports it when it is first
asked for: the module costs the app's start nothing. The verified path (ADR-071):

- ``QVideoFrameInput`` → ``QMediaCaptureSession`` → ``QMediaRecorder``, inside the pinned
  PyQt6-Qt6 wheel. Its FFmpeg reports ``LGPL version 2.1 or later`` at run time and was
  configured without ``--enable-gpl``; the bundle grows by about 20 MB.
- H.264 comes from the operating system's own encoder (Windows Media Foundation through
  FFmpeg's ``h264_mf``), so the app ships none. Where a system has none — a Windows N
  edition, Linux — FFmpeg's own MPEG-4 Part 2 encoder writes the file instead (``CODECS``).
- The frames are BT.709 YUV computed here, never RGB (``core/video_yuv.py`` says why: the
  recorder's own conversion gets the colours wrong in every player).

A writer takes frames as they come and says when it has had enough: ``write`` returns
False while its queue is full, and the caller offers the same frame again. ``finish`` ends
the file; ``finished(ok, message)`` says how it went. Until then the file has a name of its
own (``<stem>.part.mp4``), so a cancelled or failed tour never replaces a good video and
never leaves half of one under the name the user chose.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
from PyQt6.QtCore import QCoreApplication, QObject, QSize, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QImage

from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.video_yuv import rgb_to_yuv420

__all__ = ["CODECS", "FrameSink", "Mp4Writer", "NullWriter", "PngSequenceWriter", "VideoError",
           "best_codec", "frame_name"]

_LOG: Final = logging.getLogger(__name__)

#: What a file may be encoded with, best first, by ``QMediaFormat.VideoCodec`` name. H.264
#: plays everywhere and is what the video platforms ask for; MPEG-4 is the fallback every
#: FFmpeg build can write.
CODECS: Final = ("H264", "MPEG4")
#: Bits per pixel of the stream: a garden's leaves are hard on an encoder, and Media
#: Foundation's H.264 stays in the Constrained Baseline profile. At 30 fps: 12 Mbit/s for
#: 1080p, 50 for 4K.
BITS_PER_PIXEL: Final = 0.2
#: How often ``finish`` looks whether the recorder or the PNG writers are done, ms.
_POLL_MS: Final = 20
#: A recorder that takes longer than this to close its file has failed, seconds.
_STOP_LIMIT_S: Final = 120.0
#: PNG frames being written at once. More would only hold 4K frames in memory: the writers
#: spend their time compressing, and each frame then waits for a free writer anyway.
_PNG_WRITERS: Final = 2
_PNG_QUEUE: Final = 4
#: Qt's PNG quality: speed over a few percent of size, for frames that are an intermediate.
_PNG_QUALITY: Final = 30


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
    """An MP4 of ``size`` (even sides) at ``fps``. GUI thread (module docstring)."""

    def __init__(self, path: Path, size: tuple[int, int], fps: int,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        if size[0] % 2 or size[1] % 2:
            raise ValueError(f"a video's sides must be even, got {size}")
        self.path = Path(path)
        self.part_path = self.path.with_name(f"{self.path.stem}.part{self.path.suffix}")
        self.size = (int(size[0]), int(size[1]))
        self.fps = int(fps)
        self.codec: str | None = None
        self.frames_sent = 0
        self._input: Any = None
        self._session: Any = None
        self._recorder: Any = None
        self._format: Any = None
        self._error = ""
        self._aborted = False
        self._waited_ms = 0
        self._poll = QTimer(self)
        self._poll.setInterval(_POLL_MS)
        self._poll.timeout.connect(self._look_if_stopped)

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
        self._recorder.setEncodingMode(media.QMediaRecorder.EncodingMode.AverageBitRateEncoding)
        self._recorder.setVideoBitRate(int(width * height * self.fps * BITS_PER_PIXEL))
        self._recorder.setOutputLocation(QUrl.fromLocalFile(str(self.part_path)))
        # errorOccurred carries an enum PyQt6 cannot connect (measured): errorChanged has none
        self._recorder.errorChanged.connect(self._on_error)
        self.part_path.unlink(missing_ok=True)
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
            return False
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
            self.part_path.unlink(missing_ok=True)
            self.finished.emit(False, self._error)
            return
        try:
            os.replace(self.part_path, self.path)
        except OSError as error:
            self.part_path.unlink(missing_ok=True)
            self.finished.emit(False, str(error))
            return
        self.finished.emit(True, "")

    def _release(self) -> None:
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
