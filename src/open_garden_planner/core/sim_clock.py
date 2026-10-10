"""One simulated plan date and time for every sun- and growth-dependent view.

Phase 17, Package L1.0 (#385, ADR-052). Before this module, four places each
kept their own idea of the simulated moment. The sun toolbar kept its widgets.
The shadow overlay kept a UTC instant and grew plants for that instant's *UTC*
date. The hours-of-sun heatmap used the toolbar's *local* date. The 3D view
read the overlay's UTC instant and UTC date. After local midnight east of UTC
(or before it west of UTC) the overlay and the heatmap grew plants for
different days. The clock is now the one source of truth:

- ``plan_date`` is the user's LOCAL calendar day. The clock **stores** it. A
  writer that hands over a wall reading — ``set_time_of_day``, ``set_date``,
  or a NAIVE ``set_datetime``, which is the sun toolbar's path — keeps the date
  it was given, so no time-of-day change, DST transition or UTC offset can move
  it: a time change never fires ``date_changed``, by construction.
- ``utc`` is derived from the stored wall-clock reading for the solar math
  (``core/solar`` takes UTC instants).

An AWARE ``set_datetime`` is an instant, and its date is read in the clock's
zone. That is right for an instant, but a wall time first turned into an
instant can land on another day: inside a spring-forward gap that starts
before midnight (America/Nuuk: Saturday 23:00 jumps to Sunday 00:00), the
instant of "Saturday 23:30" reads back as Sunday 00:30. User-facing writers
therefore hand over wall readings, never instants.

There is deliberately no ``local`` (aware) read: its ``.date()`` is an
instant's date, which differs from ``plan_date`` inside such a gap — the bug
this module exists to prevent, one attribute away. Read ``plan_date`` /
``time_of_day`` / ``wall`` for the user's reading and ``utc`` for the sun.

The clock is **Qt-free** by design (epic #383: the sim clock is one of the
engine-independent cores). It notifies through two plain synchronous
:class:`Channel` objects instead of Qt signals. Two Qt-like properties: a
subscription never keeps its receiver alive (a bound method is held weakly,
so a controller that owns a clock and listens to it forms no reference
cycle; any other callable is held strongly), and every listener runs even
when one raises (the first error is re-raised afterwards). One Qt property it
does NOT have: nothing disconnects a QObject receiver when its C++ side is
destroyed. A Qt subscriber therefore disconnects in its own teardown (or on
``destroyed``), and never connects a bound signal's ``emit`` — that is a
builtin, held strongly, and raises on every write once its QObject is gone.

Zone: ``tz=None`` means the system zone, which is the app's choice (the
garden and the computer share one in practice). Wall-time rules follow
PEP 495: in a repeated (fall-back) hour ``fold`` selects the occurrence, and an
aware instant read into the clock round-trips exactly; a wall time inside a
skipped (spring-forward) hour is converted by PEP 495's rule (the offset in
force before the gap, ``fold=0``). Neither case touches the plan date.

The sim moment is deliberately not persisted (FR-SUN-04): every session
starts at "now".
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from types import MethodType
from typing import Any, Generic, TypeVar

T = TypeVar("T")

#: The plan dates the clock accepts. The system zone converts through the
#: platform's ``localtime``/``mktime``, which on Windows raise ``OSError`` near
#: and before the 1970 epoch and during 3001 (measured on Windows 11, CPython
#: 3.12, Europe/Berlin: 1960, 1970-01-01 12:00 and 1970-01-02 00:00 fail,
#: 1970-01-02 01:00 works; 2999-12-31 and 3001-01-02 work, 3001-06-01 fails —
#: CPython probes about a day either side of the instant). The range keeps a
#: year of margin at both ends and is safe for every UTC offset;
#: ``SunSimToolbar`` limits its date picker to it.
MIN_PLAN_DATE = date(1971, 1, 1)
MAX_PLAN_DATE = date(2999, 12, 31)


def _check_range(day: date, margin: timedelta = timedelta(0)) -> None:
    if not MIN_PLAN_DATE - margin <= day <= MAX_PLAN_DATE + margin:
        raise ValueError(
            f"plan date {day.isoformat()} is outside the supported range "
            f"{MIN_PLAN_DATE.isoformat()} to {MAX_PLAN_DATE.isoformat()}"
        )


class _Slot:
    """One connection: a bound method held weakly, any other callable strongly."""

    __slots__ = ("_strong", "_weak", "key")

    def __init__(self, listener: Callable[[Any], object]) -> None:
        self._strong: Callable[[Any], object] | None
        self._weak: weakref.WeakMethod[Callable[[Any], object]] | None
        self.key: object
        if isinstance(listener, MethodType):
            self._strong = None
            self._weak = weakref.WeakMethod(listener)
            self.key = (id(listener.__self__), listener.__func__)
        else:
            self._strong = listener
            self._weak = None
            self.key = listener

    def resolve(self) -> Callable[[Any], object] | None:
        """The listener, or None once a weakly held receiver has been collected."""
        return self._strong if self._weak is None else self._weak()


class Channel(Generic[T]):
    """A minimal synchronous observer channel: ``connect`` / ``disconnect`` / ``emit``.

    Qt-free stand-in for a signal:

    - ``connect`` is idempotent; bound methods compare by their target, so
      connecting ``obj.slot`` twice registers it once.
    - A bound method is held weakly — a subscription never keeps its receiver
      alive; a collected receiver is skipped and pruned. Other callables
      (functions, lambdas, builtins such as a bound signal's ``emit``) are held
      strongly. A bound method of an object that cannot be weakly referenced
      (``__slots__`` without ``__weakref__``) is refused with ``TypeError``.
    - Unlike Qt, a QObject receiver whose C++ side is destroyed while its
      Python wrapper lives is NOT disconnected: Qt subscribers disconnect in
      their own teardown.
    - A listener disconnected during an emission is not called afterwards.
    - Every listener runs even when one raises; the first exception is re-raised
      after the last listener (later ones are attached to it as notes) — loud,
      never swallowed, and one failing consumer cannot starve the others.
    """

    __slots__ = ("_slots",)

    def __init__(self) -> None:
        self._slots: list[_Slot] = []

    def _prune(self) -> None:
        self._slots = [slot for slot in self._slots if slot.resolve() is not None]

    def connect(self, listener: Callable[[T], object]) -> None:
        self._prune()
        slot = _Slot(listener)
        if all(existing.key != slot.key for existing in self._slots):
            self._slots.append(slot)

    def disconnect(self, listener: Callable[[T], object]) -> None:
        """Remove ``listener``; ``ValueError`` if it is not connected."""
        self._prune()
        key = _Slot(listener).key
        for index, slot in enumerate(self._slots):
            if slot.key == key:
                del self._slots[index]
                return
        raise ValueError("listener is not connected")

    def emit(self, value: T) -> None:
        first_error: Exception | None = None
        for slot in tuple(self._slots):
            if slot not in self._slots:  # disconnected during this emission
                continue
            listener = slot.resolve()
            if listener is None:
                continue
            try:
                listener(value)
            except Exception as exc:  # deliver to the rest, then re-raise
                if first_error is None:
                    first_error = exc
                else:
                    first_error.add_note(f"a further listener also raised: {exc!r}")
        self._prune()
        if first_error is not None:
            raise first_error

    def receiver_count(self) -> int:
        self._prune()
        return len(self._slots)


def _utc_of(wall: datetime, tz: tzinfo | None) -> datetime:
    """The UTC instant of a naive wall-clock reading in ``tz`` (None = system)."""
    if tz is None:
        return wall.astimezone(UTC)  # naive → system zone, honouring ``fold``
    return wall.replace(tzinfo=tz).astimezone(UTC)


def _wall_reading(moment: datetime, tz: tzinfo | None) -> datetime:
    """Read an aware instant as a naive wall time in ``tz``, with the right ``fold``.

    Converted through UTC: ``moment.astimezone(tz)`` would hand ``moment`` back
    unchanged when it already carries ``tz``, un-normalised inside a gap.
    ``ZoneInfo`` sets ``fold`` itself; the system zone (``astimezone()``) and
    fixed offsets do not, so both occurrences are tried and the one that names
    the same instant wins — an exact round trip through the repeated hour.
    """
    target = moment.astimezone(UTC)
    wall = target.astimezone(tz).replace(tzinfo=None)
    for fold in (wall.fold, 1 - wall.fold):
        candidate = wall.replace(fold=fold)
        if _utc_of(candidate, tz) == target:
            return candidate
    return wall  # unreachable for real zones; keep the conversion's reading


@dataclass(frozen=True, slots=True, eq=False)
class SimInstant:
    """One simulated moment: the plan's local calendar day plus a wall-clock time.

    ``time_of_day`` is naive, in ``tz`` (None = the system zone), at seconds
    resolution (microseconds are dropped). Equality compares the WALL READING
    (date, time, ``fold``, zone): ``fold`` is included because plain ``time``
    equality ignores it, which would merge the two occurrences of a repeated
    hour. Inside a skipped hour two different readings can name one instant
    (Berlin 02:30 and 03:30 on a spring-forward day) and still compare unequal
    — they are different things the user picked.
    """

    plan_date: date
    time_of_day: time
    tz: tzinfo | None = None

    def __post_init__(self) -> None:
        if isinstance(self.plan_date, datetime) or not isinstance(self.plan_date, date):
            raise TypeError(
                f"plan_date must be a date, not {type(self.plan_date).__name__}"
            )
        if not isinstance(self.time_of_day, time):
            # A datetime here (an easy slip for a time-control caller) would be
            # accepted and then make every ``wall`` / ``utc`` read raise.
            raise TypeError(
                f"time_of_day must be a time, not {type(self.time_of_day).__name__}"
            )
        if self.time_of_day.tzinfo is not None:
            raise ValueError("time_of_day must be a naive wall-clock time")
        _check_range(self.plan_date)  # before any conversion can hit the platform
        t = self.time_of_day.replace(microsecond=0)
        if t.fold == 1:
            # Canonical fold: keep 1 only where it names a different instant
            # (inside a repeated or skipped hour), so readings that cannot
            # differ do not compare unequal by their fold alone.
            wall = datetime.combine(self.plan_date, t)
            if _utc_of(wall, self.tz) == _utc_of(wall.replace(fold=0), self.tz):
                t = t.replace(fold=0)
        object.__setattr__(self, "time_of_day", t)

    @classmethod
    def from_datetime(cls, dt: datetime, tz: tzinfo | None = None) -> SimInstant:
        """Naive ``dt``: a wall reading in ``tz``, kept as given (its date is the
        plan date). Aware ``dt``: an instant, read as wall time in ``tz``.

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
    ``instant_changed(change)``, and ``instant_changed`` is delivered even when
    a ``date_changed`` listener raised (the first error is re-raised after
    both). Listeners see the new state. Writing the clock from inside its own
    notification raises ``RuntimeError``: such a chain would hand the remaining
    listeners a stale change.
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

    # ── writes ───────────────────────────────────────────────────────────

    def set_datetime(self, dt: datetime) -> SimChange | None:
        """Naive ``dt`` = a wall reading in the clock's zone (UI writers: the date
        is kept by construction); aware ``dt`` = an instant (see the module note)."""
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
        first_error: Exception | None = None
        try:
            if change.date_changed:
                try:
                    self.date_changed.emit(new.plan_date)
                except Exception as exc:  # still notify instant listeners
                    first_error = exc
            try:
                self.instant_changed.emit(change)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                else:
                    first_error.add_note(f"an instant listener also raised: {exc!r}")
        finally:
            self._notifying = False
        if first_error is not None:
            raise first_error
        return change
