"""A shipped example is seen at its own moment; the user's reading comes back (#795).

The session's one clock (``core/sim_clock.SimClock``, ADR-053) starts at the wall
clock's "now". An example opened in the evening was therefore drawn at night, on
a date its plants were not planted for. Its sidecar names the moment it is made
for (``core/templates.example_showcase_moment``); this holder puts the clock
there while the UNSAVED example copy is the open document and gives the user's
own reading back when that ends: with the next document, or when the copy is
saved and so becomes the user's own file.

It is not a second clock and holds no time of its own: it writes the one clock
through the clock's own writers and remembers one reading. The moment itself is
never persisted: no setting and no plan key carries it, and a copy the user
saved opens at the user's "now" like any other plan of theirs.

What a plan file CAN carry is a planting date. A plant is stamped with the plan
date it is made on (ADR-062), so a plant the user adds while the unsaved copy
still shows the example's moment is planted on the example's date, and stays so
after the copy is saved. A plant added after the save is planted on the user's
date, because the save ended the showcase.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Protocol

from open_garden_planner.core.sim_clock import SimClock


class InnerClockHold(Protocol):
    """Someone who moves the clock for a while INSIDE a document and puts it back.

    A camera tour that sweeps a date or a time range is the one such holder
    (``ui/view3d/workspace_capture``). The order is fixed: the showcase is the
    outer holder (one reading per run of example documents), the tour the inner
    one (one reading per recording), and the inner one is released first.
    """

    def held_reading(self) -> datetime | None:
        """The wall reading it will put back, or ``None`` while it holds nothing."""

    def rebase_hold(self) -> None:
        """The document's own reading changed under it: put THAT back, not the old one."""


class ShowcaseMoment:
    """Moves the clock to an example's moment and back to the user's reading."""

    def __init__(self, clock: SimClock,
                 inner_hold: Callable[[], InnerClockHold | None] | None = None) -> None:
        self._clock = clock
        #: Resolves the inner holder (see :class:`InnerClockHold`), if there is one.
        self._inner_hold = inner_hold
        #: The wall reading the user had before the first example moved the
        #: clock; ``None`` while no example holds it.
        self._user_reading: datetime | None = None

    @property
    def active(self) -> bool:
        """Whether an example moved the clock and the user's reading is held."""
        return self._user_reading is not None

    def document_opened(self, moment: tuple[date, time] | None) -> None:
        """The open document was replaced; *moment* is its showcase moment, if any.

        An example (*moment* given: its local date and a UTC time of day) takes
        the clock there. The reading to return to is taken once: a second
        example opened after a first keeps the user's own reading, not the first
        example's.

        Any other document (``None``) gives the clock back to that reading, also
        when the user moved the clock while the example was open: a date picked
        while looking at an example belongs to the example, and the user's own
        plan must not open on it without them choosing it.
        """
        if moment is not None:
            if self._user_reading is None:
                self._user_reading = self._document_reading()
            try:
                self._clock.set_utc_time_on(*moment)
            finally:
                self._rebase_inner_hold()
        else:
            self._give_back()

    def copy_saved(self) -> bool:
        """The open document was saved to a file of the user's; whether that ended a showcase.

        A saved example copy is the user's plan: the clock returns to their own
        reading and nothing is held any more, so a clock setting they make from
        here on is theirs and no later document replaces it. Saving any other
        document changes nothing.
        """
        return self._give_back()

    def _give_back(self) -> bool:
        """Put the user's reading back and forget it; ``False`` when none was held.

        The reading is forgotten BEFORE the clock is written: a clock listener
        that raises must not leave a reading behind that a later document would
        put over the user's own setting.
        """
        if self._user_reading is None:
            return False
        reading, self._user_reading = self._user_reading, None
        try:
            self._clock.set_datetime(reading)
        finally:
            self._rebase_inner_hold()
        return True

    def _inner(self) -> InnerClockHold | None:
        return self._inner_hold() if self._inner_hold is not None else None

    def _document_reading(self) -> datetime:
        """The reading the open document has: the clock's, or, while a tour moves the
        clock frame by frame, the one the tour holds for it."""
        inner = self._inner()
        held = inner.held_reading() if inner is not None else None
        return held if held is not None else self._clock.wall

    def _rebase_inner_hold(self) -> None:
        """This holder just wrote the document's reading: a running tour returns to it.

        Without this the tour's finish would put the reading of the document it
        started over back onto the document that is open now (an example's
        moment onto the user's plan, when an agent opened it during a tour).
        Runs also when a clock listener raised: the clock did move.
        """
        inner = self._inner()
        if inner is not None:
            inner.rebase_hold()
