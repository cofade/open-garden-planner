"""One simulated plan date and time for every sun- and growth-dependent view.

Phase 17, Package L1.0 (#385, ADR-052). Before this module, four places each
kept their own idea of the simulated moment. The sun toolbar kept its widgets.
The shadow overlay kept a UTC instant and grew plants for that instant's *UTC*
date. The hours-of-sun heatmap used the toolbar's *local* date. The 3D view
read the overlay's UTC instant and UTC date. After local midnight east of UTC
(or before it west of UTC) the overlay and the heatmap grew plants for
different days. The clock is now the one source of truth:

- ``plan_date`` is the user's LOCAL calendar day. The clock **stores** it and
  never derives it from the UTC instant, so no time-of-day change, DST
  transition or UTC offset can move it. A time change never fires
  ``date_changed``: this holds by construction.
- ``utc`` is derived from the stored wall-clock reading for the solar math
  (``core/solar`` takes UTC instants).

The clock is **Qt-free** by design (epic #383: the sim clock is one of the
engine-independent cores). It notifies through two plain synchronous
:class:`Channel` objects instead of Qt signals. Consequence: a listener is a
plain callable that the channel holds strongly. Nothing disconnects it when a
Qt receiver dies, so subscribers must live as long as the clock. The app owns
the clock and is its only subscriber besides the shadow overlay (a child of
the app).

Zone: ``tz=None`` means the system zone. That is the zone ``SunSimToolbar``
edits in, so the app's clock and the toolbar always agree. Wall-time rules
follow PEP 495. In a repeated (fall-back) hour, ``fold`` selects the
occurrence, and an aware instant read into the clock round-trips exactly. A
wall time inside a skipped (spring-forward) hour is converted by the
platform's rule. Neither case touches the plan date.

The sim moment is deliberately not persisted (FR-SUN-04): every session
starts at "now".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Generic, TypeVar

T = TypeVar("T")

#: The plan dates the clock accepts. The system zone converts through the
#: platform's ``localtime``/``mktime``, which on Windows raise ``OSError``
#: outside 1970–3000 (measured: 1960 and 3001 fail, 1970 and 2999 work). A
#: day of margin on each side keeps every UTC offset (±14 h) inside that
#: window, so no consumer ever meets the platform error; ``SunSimToolbar``
#: limits its date picker to the same range.
MIN_PLAN_DATE = date(1971, 1, 1)
MAX_PLAN_DATE = date(2999, 12, 31)


def _check_range(day: date, margin: timedelta = timedelta(0)) -> None:
    if not MIN_PLAN_DATE - margin <= day <= MAX_PLAN_DATE + margin:
        raise ValueError(
            f"plan date {day.isoformat()} is outside the supported range "
            f"{MIN_PLAN_DATE.isoformat()} to {MAX_PLAN_DATE.isoformat()}"
        )


class Channel(Generic[T]):
    """A minimal synchronous observer channel: ``connect`` / ``disconnect`` / ``emit``.

    Qt-free stand-in for a signal. ``connect`` is idempotent; bound methods
    compare by their target, so connecting ``obj.slot`` twice registers it once.
    A listener disconnected during an emission is not called afterwards (Qt's
    rule); exceptions propagate to the emitter (loud, never swallowed).
    """

    __slots__ = ("_listeners",)

    def __init__(self) -> None:
        self._listeners: list[Callable[[T], object]] = []

    def connect(self, listener: Callable[[T], object]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def disconnect(self, listener: Callable[[T], object]) -> None:
        """Remove ``listener``; ``ValueError`` if it is not connected."""
        self._listeners.remove(listener)

    def emit(self, value: T) -> None:
        for listener in tuple(self._listeners):
            if listener in self._listeners:
                listener(value)

    def receiver_count(self) -> int:
        return len(self._listeners)


def _utc_of(wall: datetime, tz: tzinfo | None) -> datetime:
    """The UTC instant of a naive wall-clock reading in ``tz`` (None = system)."""
    if tz is None:
        return wall.astimezone(UTC)  # naive → system zone, honouring ``fold``
    return wall.replace(tzinfo=tz).astimezone(UTC)


def _wall_reading(moment: datetime, tz: tzinfo | None) -> datetime:
    """Read an aware instant as a naive wall time in ``tz``, with the right ``fold``.

    ``ZoneInfo`` sets ``fold`` itself; the system zone (``astimezone()``) and
    fixed offsets do not, so both occurrences are tried and the one that names
    the same instant wins — an exact round trip through the repeated hour.
    """
    target = moment.astimezone(UTC)
    wall = moment.astimezone(tz).replace(tzinfo=None)
    for fold in (wall.fold, 1 - wall.fold):
        candidate = wall.replace(fold=fold)
        if _utc_of(candidate, tz) == target:
            return candidate
    return wall  # unreachable for real zones; keep the platform's reading


@dataclass(frozen=True, slots=True, eq=False)
class SimInstant:
    """One simulated moment: the plan's local calendar day plus a wall-clock time.

    ``time_of_day`` is naive, in ``tz`` (None = the system zone), at seconds
    resolution (microseconds are dropped). Its ``fold`` selects the occurrence
    in a repeated DST hour and is part of equality — plain ``time`` equality
    ignores it, which would merge two different instants.
    """

    plan_date: date
    time_of_day: time
    tz: tzinfo | None = None

    def __post_init__(self) -> None:
        if isinstance(self.plan_date, datetime) or not isinstance(self.plan_date, date):
            raise TypeError(
                f"plan_date must be a date, not {type(self.plan_date).__name__}"
            )
        if self.time_of_day.tzinfo is not None:
            raise ValueError("time_of_day must be a naive wall-clock time")
        _check_range(self.plan_date)  # before any conversion can hit the platform
        t = self.time_of_day.replace(microsecond=0)
        if t.fold == 1:
            # Canonical fold: keep 1 only where it names a different instant
            # (inside a repeated or skipped hour), so equal moments compare equal.
            wall = datetime.combine(self.plan_date, t)
            if _utc_of(wall, self.tz) == _utc_of(wall.replace(fold=0), self.tz):
                t = t.replace(fold=0)
        object.__setattr__(self, "time_of_day", t)

    @classmethod
    def from_datetime(cls, dt: datetime, tz: tzinfo | None = None) -> SimInstant:
        """Aware ``dt``: the same instant read in ``tz``. Naive ``dt``: wall time in ``tz``.

        ``ValueError`` outside :data:`MIN_PLAN_DATE` … :data:`MAX_PLAN_DATE`.
        """
        if dt.tzinfo is None:
            wall = dt
        else:
            # Guard the platform call only (UTC needs none): the local date may
            # sit a day off the UTC one; ``__post_init__`` enforces the range.
            _check_range(dt.astimezone(UTC).date(), margin=timedelta(days=1))
            wall = _wall_reading(dt, tz)
        return cls(wall.date(), wall.time(), tz)  # ``time()`` keeps ``fold``

    def _key(self) -> tuple[object, ...]:
        return (self.plan_date, self.time_of_day, self.time_of_day.fold, self.tz)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SimInstant):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    @property
    def wall(self) -> datetime:
        """The naive local wall-clock reading (``fold`` included)."""
        return datetime.combine(self.plan_date, self.time_of_day)

    @property
    def utc(self) -> datetime:
        """The instant, timezone-aware in UTC — what ``core/solar`` consumes."""
        return _utc_of(self.wall, self.tz)

    @property
    def local(self) -> datetime:
        """The instant, timezone-aware in the clock's zone."""
        return self.utc.astimezone(self.tz)

    @property
    def minute_of_day(self) -> int:
        return self.time_of_day.hour * 60 + self.time_of_day.minute


@dataclass(frozen=True, slots=True)
class SimChange:
    """What one clock write changed — delivered on :attr:`SimClock.instant_changed`."""

    previous: SimInstant
    current: SimInstant

    @property
    def date_changed(self) -> bool:
        return self.previous.plan_date != self.current.plan_date

    @property
    def time_changed(self) -> bool:
        before, after = self.previous.time_of_day, self.current.time_of_day
        return before != after or before.fold != after.fold


def _now_to_the_minute() -> datetime:
    # An aware UTC "now" (not a naive local one): read through
    # ``SimInstant.from_datetime`` it lands on the right occurrence even inside
    # a repeated DST hour. Whole-minute truncation matches the toolbar's slider.
    return datetime.now(UTC).replace(second=0, microsecond=0)


class SimClock:
    """The open session's one simulated moment (not persisted).

    Writers call :meth:`set_datetime`, :meth:`set_date` or
    :meth:`set_time_of_day`; each returns the :class:`SimChange`, or ``None``
    when nothing changed (nothing is emitted then). A change emits
    ``date_changed(plan_date)`` first — only when the plan date moved — then
    ``instant_changed(change)``. Listeners see the new state. Writing the clock
    from inside its own notification raises ``RuntimeError``: such a chain would
    hand the remaining listeners a stale change.
    """

    def __init__(
        self, initial: datetime | None = None, *, tz: tzinfo | None = None
    ) -> None:
        self._tz = tz
        seed = initial if initial is not None else _now_to_the_minute()
        self._instant = SimInstant.from_datetime(seed, tz)
        self._notifying = False
        #: Fired with the new plan date — never by a time-of-day change.
        self.date_changed: Channel[date] = Channel()
        #: Fired with the :class:`SimChange` on every change (date and/or time).
        self.instant_changed: Channel[SimChange] = Channel()

    # ── reads ────────────────────────────────────────────────────────────

    @property
    def tz(self) -> tzinfo | None:
        return self._tz

    @property
    def instant(self) -> SimInstant:
        return self._instant

    @property
    def plan_date(self) -> date:
        """The local calendar day — the growth date of shadows, heatmap and 3D."""
        return self._instant.plan_date

    @property
    def time_of_day(self) -> time:
        return self._instant.time_of_day

    @property
    def wall(self) -> datetime:
        return self._instant.wall

    @property
    def utc(self) -> datetime:
        """The instant for the solar math."""
        return self._instant.utc

    @property
    def local(self) -> datetime:
        return self._instant.local

    # ── writes ───────────────────────────────────────────────────────────

    def set_datetime(self, dt: datetime) -> SimChange | None:
        """Aware ``dt`` = an instant; naive ``dt`` = a wall time in the clock's zone."""
        return self._commit(SimInstant.from_datetime(dt, self._tz))

    def set_date(self, day: date) -> SimChange | None:
        """Move to another plan date at the same time of day."""
        return self._commit(SimInstant(day, self._instant.time_of_day, self._tz))

    def set_time_of_day(self, t: time) -> SimChange | None:
        """Move within the plan date — never fires ``date_changed``."""
        return self._commit(SimInstant(self._instant.plan_date, t, self._tz))

    def _commit(self, new: SimInstant) -> SimChange | None:
        if self._notifying:
            raise RuntimeError(
                "SimClock written from inside its own notification; listeners "
                "must not write the clock"
            )
        if new == self._instant:
            return None
        change = SimChange(self._instant, new)
        self._instant = new
        self._notifying = True
        try:
            if change.date_changed:
                self.date_changed.emit(new.plan_date)
            self.instant_changed.emit(change)
        finally:
            self._notifying = False
        return change
