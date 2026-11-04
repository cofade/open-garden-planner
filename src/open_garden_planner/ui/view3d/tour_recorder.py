"""A tour rendered frame by frame, on the event loop (L6.2, #390, ADR-072).

One frame per pass, and control goes back to the event loop in between: the window stays
alive, the Cancel button works and the pipeline gets the turns it needs. A frame:

1. the clock moves, when the tour says so (``set_clock``);
2. the recorder waits for what follows from that — the regrown plants, the sky of the new
   sun (``settled``) — so that no frame shows a plant of yesterday under today's sun;
3. the host renders it (``capture``) and the writer takes it, or is offered it again.

The frames are computed, not timed (``core/camera_path.py``): a slow machine takes longer
and writes the same video. Only a PREVIEW follows the wall clock, and skips what it is
late for: it shows how the tour will move, at whatever the machine manages.

A view that cannot give a frame right now (``HostStateError``: the window was minimised,
the pane is mid-resize) pauses the recording and it goes on when the view is back; a frame
is never skipped or repeated for it. Anything else that fails ends the recording, and
the partial file goes with it (``video_writer.py``).

No Qt Quick here: ``capture`` is a callable the workspace hands in, and the tests hand in
theirs. The memory rule of ADR-060 decision 17 holds through the shape of the thing: a
frame is taken for a tour the user started, never by a timer of the view's steady state.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from datetime import time as day_time
from typing import Final

from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QImage

from open_garden_planner.core.camera_path import TourFrame, TourSpec, frame_count, tour_frames
from open_garden_planner.core.plain_text import log_text

from .quick3d.lifecycle import HostStateError  # engine-free: the state contract's module
from .video_writer import FrameSink, VideoError

__all__ = ["CaptureFrame", "SetClock", "Settled", "TourRecorder", "TourResult"]

_LOG: Final = logging.getLogger(__name__)

CaptureFrame = Callable[[TourFrame], QImage]
SetClock = Callable[[date | None, day_time | None], None]
Settled = Callable[[], bool]

#: How often an unsettled pipeline or a full writer is asked again, ms.
_RETRY_MS: Final = 5
#: How often a view that gives no frame is asked again.
_PAUSED_RETRY_MS: Final = 250
#: A frame that has not settled after this long is rendered anyway and counted: a pipeline
#: that cannot settle must not hold a recording for ever (``TourResult.unsettled``).
SETTLE_LIMIT_S: Final = 20.0
#: The first frame also waits for the plants the whole flight passes close by: a plan's worth
#: of forging, once (``WorkspaceCaptureCoordinator.start_tour``).
FIRST_FRAME_SETTLE_FACTOR: Final = 9
#: The thumbnail a preview shows of each frame, at most, in logical pixels of the dialog.
_THUMBNAIL_WIDTH: Final = 480


@dataclass(frozen=True, slots=True)
class TourResult:
    """How a recording ended."""

    ok: bool
    cancelled: bool
    frames: int
    message: str = ""
    #: Frames rendered although the pipeline had not settled (``SETTLE_LIMIT_S``).
    unsettled: int = 0


class TourRecorder(QObject):
    """One run of one tour (module docstring). Use once: ``start``, then ``finished``."""

    #: Frames done, frames in all, and a small picture of the last one.
    progress = pyqtSignal(int, int, object)
    #: True: the view gives no frame right now, and the recording waits for it.
    paused_changed = pyqtSignal(bool)
    #: The last frame is out and the writer is closing the file: too late to cancel.
    finishing = pyqtSignal()
    finished = pyqtSignal(object)   # TourResult

    def __init__(self, spec: TourSpec, writer: FrameSink, capture: CaptureFrame,
                 set_clock: SetClock, settled: Settled, *, realtime: bool = False,
                 view_showing: Callable[[], bool] = lambda: True,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._writer = writer
        self._capture = capture
        self._set_clock = set_clock
        self._settled = settled
        self._view_showing = view_showing
        self._realtime = realtime
        self.total = frame_count(spec)
        self._frames: Iterator[TourFrame] = tour_frames(spec)
        self._frame: TourFrame | None = None
        self._image: QImage | None = None      # rendered, not yet taken by the writer
        self._settling_since = 0.0
        self._started_at = 0.0
        self._done = 0
        self._unsettled = 0
        self._paused = False
        self._cancelled = False
        self._ending = False
        self._message = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._step)

    @property
    def running(self) -> bool:
        return self._timer.isActive() and not self._ending

    def start(self) -> None:
        """Start the writer and the first frame. ``VideoError`` when the writer cannot
        start: nothing has moved then."""
        self._writer.start()
        self._writer.finished.connect(self._on_writer_finished)
        self._started_at = time.monotonic()
        self._timer.start(0)

    def cancel(self) -> bool:
        """End it at the next step; ``finished`` follows with ``cancelled``. False: too late,
        the writer is closing a finished file, and ``finished`` says how that ended."""
        if self._ending:
            return False
        self._cancelled = True
        return True

    # ── the steps ────────────────────────────────────────────────────────────

    def _step(self) -> None:
        if self._ending:
            return
        if self._cancelled:
            self._end(abort=True)
            return
        try:
            self._advance()
        except VideoError as error:
            self._fail(str(error))
        except Exception as error:  # noqa: BLE001 - a recording must never take the app down
            _LOG.error("Camera tour: frame %d failed (%s: %s)", self._done,
                       type(error).__name__, log_text(error))
            self._fail(f"{type(error).__name__}: {error}")

    def _advance(self) -> None:
        if self._image is not None:
            self._offer()
            return
        if self._frame is None and not self._next_frame():
            self._end(abort=False)
            return
        frame = self._frame
        assert frame is not None
        if not self._view_showing():
            self._wait_for_the_view()   # nothing settles behind a hidden view: say so at once
            return
        settled = self._settled()
        if not settled:
            limit = SETTLE_LIMIT_S if self._done else SETTLE_LIMIT_S * FIRST_FRAME_SETTLE_FACTOR
            if time.monotonic() - self._settling_since < limit:
                self._timer.start(_RETRY_MS)
                return
        try:
            self._image = self._capture(frame)
        except HostStateError as error:
            self._wait_for_the_view(error)
            return
        if not settled:
            self._unsettled += 1   # this frame, once: not every retry while it could not be taken
        self._pause(False)
        self._offer()

    def _wait_for_the_view(self, error: Exception | None = None) -> None:
        self._pause(True, error)
        self._settling_since = time.monotonic()   # its time to settle starts when it is back
        self._timer.start(_PAUSED_RETRY_MS)

    def _next_frame(self) -> bool:
        """The next frame, with the clock moved for it. False: there is none."""
        frame = next(self._frames, None)
        if self._realtime and frame is not None:   # a preview skips what it is late for
            due = int((time.monotonic() - self._started_at) * self._spec.fps)
            while frame is not None and frame.index < min(due, self.total - 1):
                frame = next(self._frames, None)
        if frame is None:
            return False
        self._frame = frame
        self._set_clock(frame.plan_date, frame.time_of_day)
        self._settling_since = time.monotonic()
        return True

    def _offer(self) -> None:
        image = self._image
        assert image is not None
        if not self._writer.write(image):
            self._timer.start(_RETRY_MS)   # the queue is full: the same frame again
            return
        frame = self._frame
        self._image = None
        self._frame = None
        self._done = frame.index + 1 if frame is not None else self._done + 1
        self.progress.emit(self._done, self.total, image.scaledToWidth(_THUMBNAIL_WIDTH))
        self._timer.start(0)

    def _pause(self, paused: bool, error: Exception | None = None) -> None:
        if paused != self._paused:
            self._paused = paused
            if error is not None:
                _LOG.info("Camera tour: waiting for the 3D view (%s)", log_text(error))
            self.paused_changed.emit(paused)

    # ── the end ──────────────────────────────────────────────────────────────

    def _fail(self, message: str) -> None:
        self._message = message
        self._end(abort=True)

    def _end(self, *, abort: bool) -> None:
        if self._ending:
            return
        self._ending = True
        self._timer.stop()
        if abort:
            self._writer.abort()
        else:
            self.finishing.emit()
            self._writer.finish()

    def _on_writer_finished(self, ok: bool, message: str) -> None:
        text = self._message or message
        self.finished.emit(TourResult(
            ok=bool(ok) and not self._cancelled and not self._message,
            cancelled=self._cancelled, frames=self._done, message=text,
            unsettled=self._unsettled))


def translated_failure(message: str) -> str:
    """What the dialog says about a failed recording."""
    return QCoreApplication.translate("TourDialog", "The recording failed: {message}").format(
        message=message)
