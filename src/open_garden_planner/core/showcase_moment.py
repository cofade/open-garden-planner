"""A shipped example is seen at its own moment; the user's reading comes back (#795).

The session's one clock (``core/sim_clock.SimClock``, ADR-053) starts at the wall
clock's "now". An example opened in the evening was therefore drawn at night, on
a date its plants were not planted for. Its sidecar names the moment it is made
for (``core/templates.example_showcase_moment``); this holder puts the clock
there while the example is the open document and gives the user's own reading
back with the next document.

It is not a second clock and holds no time of its own: it writes the one clock
through the clock's own writers and remembers one reading. Nothing is persisted,
so no setting and no plan file ever carries an example's date: a copy the user
saved opens at the user's "now" like any other plan of theirs.
"""

from __future__ import annotations

from datetime import date, datetime, time

from open_garden_planner.core.sim_clock import SimClock


class ShowcaseMoment:
    """Moves the clock to an example's moment and back to the user's reading."""

    def __init__(self, clock: SimClock) -> None:
        self._clock = clock
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
                self._user_reading = self._clock.wall
            self._clock.set_utc_time_on(*moment)
        elif self._user_reading is not None:
            reading, self._user_reading = self._user_reading, None
            self._clock.set_datetime(reading)
