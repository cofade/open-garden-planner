"""Succession planting data model (US-12.8).

Tracks multiple sequential crops planned for the same bed within a season.
Storage: serialised under top-level ``succession_plans`` key in the .ogp file
as ``{bed_id: SuccessionPlan.to_dict()}``.

Season segments are computed frost-relative from the project location:
  - early_spring : last_frost - 8w  →  last_frost - 2w
  - late_spring  : last_frost - 2w  →  last_frost + 4w
  - summer       : last_frost + 4w  →  fall_frost  - 4w
  - fall         : fall_frost  - 4w →  fall_frost  + 2w

A plan with no geo-location has no frost dates, so
:func:`compute_fallback_segments` supplies calendar-month boundaries instead.
It lives HERE, beside :func:`compute_season_segments`, rather than in the dialog
that first needed it (US-D3.2): the Agent API's ``get_succession_plan`` needs
the same answer, and two copies of a month table would let an agent and the GUI
disagree about what "summer" means for the same bed.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any

SEASON_SEGMENTS = ("early_spring", "late_spring", "summer", "fall")

# Frost-relative week offsets that bound each segment.
# (start_weeks_from_last_frost, end_weeks_from_last_frost)
# Negative = before last spring frost; positive = after.
_SEGMENT_OFFSETS: dict[str, tuple[int, int]] = {
    "early_spring": (-8, -2),
    "late_spring": (-2, 4),
    "summer": (4, -4),   # end is relative to fall frost
    "fall": (-4, 2),     # start/end relative to fall frost
}


def compute_season_segments(
    last_frost_str: str,
    first_fall_frost_str: str,
    year: int,
) -> dict[str, tuple[datetime.date, datetime.date]]:
    """Return frost-relative date ranges for each season segment.

    Parses both frost dates through :mod:`core.frost_dates`, the single rule
    every reader shares (#414, ADR-049). This function used to slice the strings
    and call ``datetime.date`` directly, which made it a fourth independent
    notion of a frost date: for a ``'02-29'`` frost in a non-leap year the task
    windows anchored on the substituted 1 March while the bed's season segments
    raised and fell back to month-only boundaries — the same plan disagreeing
    with itself on the same day.

    Args:
        last_frost_str: "MM-DD" last spring frost date.
        first_fall_frost_str: "MM-DD" first fall frost date.
        year: Calendar year for absolute date calculation.

    Returns:
        Dict mapping segment key → (start_date, end_date).

    Raises:
        ValueError: if either stored value is not a real frost date.
    """
    from open_garden_planner.core.frost_dates import parse_frost

    last = parse_frost(last_frost_str, year)
    fall = parse_frost(first_fall_frost_str, year)
    if last is None or fall is None:
        raise ValueError(
            f"not a usable frost date pair for {year}: "
            f"{last_frost_str!r} / {first_fall_frost_str!r}"
        )

    return {
        "early_spring": (
            last + datetime.timedelta(weeks=-8),
            last + datetime.timedelta(weeks=-2),
        ),
        "late_spring": (
            last + datetime.timedelta(weeks=-2),
            last + datetime.timedelta(weeks=4),
        ),
        "summer": (
            last + datetime.timedelta(weeks=4),
            fall + datetime.timedelta(weeks=-4),
        ),
        "fall": (
            fall + datetime.timedelta(weeks=-4),
            fall + datetime.timedelta(weeks=2),
        ),
    }


def date_to_segment(
    d: datetime.date,
    segments: dict[str, tuple[datetime.date, datetime.date]],
) -> str | None:
    """Return the segment key that contains ``d``, or None if outside all segments.

    Boundaries are INCLUSIVE on both sides and segments are contiguous, so a
    date exactly on a shared boundary (e.g. ``last_frost - 2w``, which is both
    ``early_spring``'s end and ``late_spring``'s start) belongs to the FIRST
    matching segment in :data:`SEASON_SEGMENTS` order. Callers that care must
    not assume the boundary belongs to the later segment.
    """
    for key in SEASON_SEGMENTS:
        start, end = segments[key]
        if start <= d <= end:
            return key
    return None


# Calendar-month boundaries used when no geo-location (hence no frost dates) is
# set. Each entry is ``((start_month, start_day), (end_month, end_day))``.
# Moved here from succession_plan_dialog by US-D3.2 — see the module docstring.
_FALLBACK_BOUNDARIES: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "early_spring": ((2, 1), (3, 31)),
    "late_spring": ((4, 1), (5, 31)),
    "summer": ((6, 1), (8, 31)),
    "fall": ((9, 1), (11, 15)),
}


def compute_fallback_segments(
    year: int,
) -> dict[str, tuple[datetime.date, datetime.date]]:
    """Return month-based season segments for a plan with no frost dates.

    These are a rough climate-agnostic approximation, NOT the frost-relative
    segments :func:`compute_season_segments` produces. Callers that use them
    must say so in their output (the agent's ``segments_are_fallback`` flag)
    rather than presenting them as if they were computed from a location.

    Args:
        year: Calendar year for absolute date calculation.

    Returns:
        Dict mapping segment key → (start_date, end_date).
    """
    return {
        key: (
            datetime.date(year, start[0], start[1]),
            datetime.date(year, end[0], end[1]),
        )
        for key, (start, end) in _FALLBACK_BOUNDARIES.items()
    }


def resolve_season_segments(
    year: int,
    location: dict[str, Any] | None,
) -> tuple[dict[str, tuple[datetime.date, datetime.date]], bool]:
    """Return ``(segments, are_fallback)`` for a plan, preferring real frost dates.

    The single entry point both the GUI dialog and the Agent API use, so a bed
    can never be segmented one way on screen and another way for an agent. The
    bool reports whether frost-relative segmentation was actually possible.

    Args:
        year: Calendar year.
        location: The plan's ``ProjectManager.location`` dict, or None. Only its
            nested ``frost_dates`` sub-dict is read.

    Returns:
        ``(segments, False)`` when both frost dates are present and parse,
        otherwise ``(compute_fallback_segments(year), True)``.
    """
    frost_dates = (location or {}).get("frost_dates")
    if not frost_dates:
        return compute_fallback_segments(year), True
    last = frost_dates.get("last_spring_frost", "")
    fall = frost_dates.get("first_fall_frost", "")
    if last and fall:
        try:
            return compute_season_segments(last, fall, year), False
        except (ValueError, KeyError):
            pass
    return compute_fallback_segments(year), True


@dataclass
class SuccessionEntry:
    """A single crop slot in a succession plan."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    species_key: str = ""       # canonical species key for companion lookup
    common_name: str = ""       # display name (may be free-text if no species data)
    scientific_name: str = ""   # used by companion service lookups
    start_date: str = ""        # ISO date "YYYY-MM-DD"
    end_date: str = ""          # ISO date "YYYY-MM-DD"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "species_key": self.species_key,
            "common_name": self.common_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }
        if self.scientific_name:
            d["scientific_name"] = self.scientific_name
        if self.notes:
            d["notes"] = self.notes
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SuccessionEntry:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            species_key=data.get("species_key", ""),
            common_name=data.get("common_name", ""),
            scientific_name=data.get("scientific_name", ""),
            start_date=data.get("start_date", ""),
            end_date=data.get("end_date", ""),
            notes=data.get("notes", ""),
        )


@dataclass
class SuccessionPlan:
    """Ordered list of crop slots planned for one bed in one season year."""

    bed_id: str
    year: int
    entries: list[SuccessionEntry] = field(default_factory=list)

    def entries_sorted(self) -> list[SuccessionEntry]:
        """Return entries sorted ascending by start_date (invalid dates last)."""
        def _key(e: SuccessionEntry) -> str:
            return e.start_date or "9999-99-99"

        return sorted(self.entries, key=_key)

    def current_entry(self, today: datetime.date) -> SuccessionEntry | None:
        """Return the entry whose date range contains today, or None."""
        for entry in self.entries:
            if not entry.start_date or not entry.end_date:
                continue
            try:
                start = datetime.date.fromisoformat(entry.start_date)
                end = datetime.date.fromisoformat(entry.end_date)
            except ValueError:
                continue
            if start <= today <= end:
                return entry
        return None

    def next_entry(self, today: datetime.date) -> SuccessionEntry | None:
        """Return the first entry whose start_date is strictly after today."""
        for entry in self.entries_sorted():
            if not entry.start_date:
                continue
            try:
                start = datetime.date.fromisoformat(entry.start_date)
            except ValueError:
                continue
            if start > today:
                return entry
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bed_id": self.bed_id,
            "year": self.year,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SuccessionPlan:
        return cls(
            bed_id=data.get("bed_id", ""),
            year=data.get("year", datetime.date.today().year),
            entries=[SuccessionEntry.from_dict(e) for e in data.get("entries", [])],
        )
