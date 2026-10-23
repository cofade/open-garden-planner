"""The growth jump: +1 / +3 / +10 years on the plan date, with a before/after (L2.3, #386).

Engine-free. A jump moves the ONE sim clock's plan date (``SimClock.set_date``) —
nothing else: the 3D pipeline regrows the dated plants for the new date as it does
for any date change, the 2D canvas, the heatmap and the info card follow the clock
as they always do — and remembers where the first jump started, so "Back" returns
there. The date moves by whole years; 29 February lands on 1 March in a year that
has none (ADR-049's rule for the plan's frost dates), and the clock's range
(1971–2999) bounds it.

THE BEFORE/AFTER TAKES TWO FRAMES FROM THE LIVE VIEW, and they are the only frames
the workspace takes besides the click that picks (ADR-060 decision 17: a readback
renders a frame that is never presented, and what it holds comes back only when a
presented frame ends). Both are the USER'S action, once each: ``_grab`` runs from
``jump`` — the picture before the date moves — and from ``on_applied`` only while
that jump's after-picture is owed: the first pass of the pipeline that read the
new date (the controller's ``applied`` signal: the readback is taken inside the
pass, the established place, ADR-060). A host that cannot answer
(``HostStateError``: mid-resize, collapsed) means no comparison — the jump still
happens. A source scan pins that ``_grab`` is the module's one frame-taking call.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Final

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE, SimClock

from .analysis_controller import add_years
from .analysis_modes import JUMP_YEARS
from .quick3d.lifecycle import HostStateError  # engine-free: the state contract's module

_LOG: Final = logging.getLogger(__name__)

__all__ = ["JUMP_YEARS", "GrowthJump"]


class GrowthJump(QObject):
    """The jump and its before/after (module docstring)."""

    #: The before/after is ready: ``(before, after, from_day, to_day)``.
    wipe_ready = pyqtSignal(object, object, object, object)
    #: Where "Back" returns changed (``origin``; None: nothing to go back to).
    changed = pyqtSignal()

    def __init__(self, clock: SimClock, host: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._clock = clock
        self._host = host
        self._origin: date | None = None
        #: ``(before, from_day, to_day)`` while a jump's after-picture is owed.
        self._pending: tuple[QImage, date, date] | None = None
        #: Frames taken (an instrument: two per jump with a comparison, never more).
        self.frames_taken = 0

    @property
    def origin(self) -> date | None:
        """The plan date before the first jump since the last "Back" — None: none."""
        return self._origin

    @property
    def pending(self) -> bool:
        return self._pending is not None

    def jump(self, years: int, before: QImage | None = None) -> date | None:
        """Move the plan date by ``years`` — and, when the view can give a frame, owe a
        before/after. None when the date cannot move (it is at the clock's bound).

        ``before``: a picture of the view at the CURRENT date that is already at hand —
        the after-picture of the comparison on screen when the user jumps again from it
        (the view is not shown then, and could give no frame) — instead of a grab."""
        current = self._clock.plan_date
        target = add_years(current, years, lowest=MIN_PLAN_DATE, highest=MAX_PLAN_DATE)
        if target == current:
            return None
        if self._origin is None:
            self._origin = current
        if before is None or before.isNull():
            before = self._grab()
        self._pending = (before, current, target) if before is not None else None
        self._clock.set_date(target)
        self.changed.emit()
        return target

    def back(self) -> None:
        """Back to the plan date before the first jump."""
        origin, self._origin = self._origin, None
        self._pending = None
        if origin is not None:
            self._clock.set_date(origin)
        self.changed.emit()

    def forget(self) -> None:
        """A new document (or the engine went): nothing owed, nothing to go back to."""
        self._pending = None
        if self._origin is not None:
            self._origin = None
            self.changed.emit()

    def on_applied(self, snapshot: bool, pass_date: date | None) -> None:
        """A pass of the pipeline reached the engine. When it READ the jump's date, the
        after-picture is taken now — once (module docstring)."""
        pending = self._pending
        if pending is None or not snapshot or pass_date != pending[2]:
            return
        self._pending = None
        after = self._grab()
        if after is not None:
            self.wipe_ready.emit(pending[0], after, pending[1], pending[2])

    def _grab(self) -> QImage | None:
        """THE frame-taking call of this module: one picture of the live view, or None."""
        try:
            image = self._host.grab("growth jump")
        except HostStateError:
            return None  # "not now": the jump happens without a comparison
        except Exception as error:  # noqa: BLE001 - a picture must never stop the jump
            _LOG.error("3D view: the growth jump could not take a picture (%s: %s)",
                       log_text(type(error).__name__), log_text(error))
            return None
        self.frames_taken += 1
        return image if isinstance(image, QImage) and not image.isNull() else None
