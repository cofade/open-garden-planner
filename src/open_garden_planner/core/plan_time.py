"""The plan's own time zone, read from its garden location (#945, ADR-053 addendum).

A plan may name an IANA zone in ``location["timezone"]`` (the bundled examples
do). The simulation clock, the toolbar's wall time and "Today", and a camera
tour's wall-time range read it; a plan without one keeps the computer's zone,
which is what every plan did before this module existed.

The module is Qt-free. ``ZoneInfo`` needs the ``tzdata`` package on Windows,
where the operating system ships no IANA database; the project depends on it so
the same zone name resolves on every platform and in the frozen exe.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

#: The location key that names the plan's zone (IANA, e.g. ``"Europe/Berlin"``).
LOCATION_TIMEZONE_KEY = "timezone"


def plan_timezone_name(location: Mapping[str, Any] | None) -> str | None:
    """The zone name a plan's location carries, or ``None``.

    A blank or non-string value means "no plan zone": the caller falls back to
    the computer's zone rather than failing to open the plan.
    """
    raw = (location or {}).get(LOCATION_TIMEZONE_KEY)
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    return name or None


def plan_timezone(location: Mapping[str, Any] | None) -> ZoneInfo | None:
    """Resolve the plan's zone, or ``None`` for the computer's zone.

    An unknown or malformed name is treated as no plan zone: a hand-edited or
    newer plan must open, and its wall time then follows the computer exactly as
    it did before #945.
    """
    name = plan_timezone_name(location)
    if name is None:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def timezone_names() -> tuple[str, ...]:
    """Every IANA zone name available on this machine, sorted for a picker."""
    return tuple(sorted(available_timezones()))


def plan_today(
    location: Mapping[str, Any] | None, *, now: datetime | None = None
) -> date:
    """Today's date at the plan's place (the computer's when it has no zone).

    ``now`` is an aware moment for tests; the default is the current UTC
    instant. A plan in another zone can be a day away from the computer's date
    near midnight, which is the date its "Today" button must use.
    """
    moment = now if now is not None else datetime.now(UTC)
    zone = plan_timezone(location)
    if zone is None:
        return moment.astimezone().date()
    return moment.astimezone(zone).date()
