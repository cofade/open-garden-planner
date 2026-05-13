"""Succession planting data model (US-12.8).

Tracks multiple sequential crops planned for the same bed within a season.
Storage: serialised under top-level ``succession_plans`` key in the .ogp file
as ``{bed_id: SuccessionPlan.to_dict()}``.

Season segments are computed frost-relative from the project location:
  - early_spring : last_frost - 8w  →  last_frost - 2w
  - late_spring  : last_frost - 2w  →  last_frost + 4w
  - summer       : last_frost + 4w  →  fall_frost  - 4w
  - fall         : fall_frost  - 4w →  fall_frost  + 2w
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

    Args:
        last_frost_str: "MM-DD" last spring frost date.
        first_fall_frost_str: "MM-DD" first fall frost date.
        year: Calendar year for absolute date calculation.

    Returns:
        Dict mapping segment key → (start_date, end_date).
    """
    last = datetime.date(year, int(last_frost_str[:2]), int(last_frost_str[3:]))
    fall = datetime.date(year, int(first_fall_frost_str[:2]), int(first_fall_frost_str[3:]))

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
    """Return the segment key that contains ``d``, or None if outside all segments."""
    for key in SEASON_SEGMENTS:
        start, end = segments[key]
        if start <= d <= end:
            return key
    return None


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
