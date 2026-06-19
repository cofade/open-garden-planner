"""Yield aggregation for the harvest log (US-C1, issue #188).

Pure, Qt-free helpers that roll a ``{target_id: HarvestLogHistory.to_dict()}``
map up into per-species, per-year totals for the Harvest Log tab, CSV export,
and the PDF summary page. Quantities are grouped by ``(species, unit)`` so a
crop logged in both grams and pieces never sums incompatible units.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from open_garden_planner.models.harvest_log import HarvestLogHistory


@dataclass
class YieldRow:
    """Aggregated yield for one (species, unit) pair."""

    species: str
    unit: str
    totals_by_year: dict[int, float] = field(default_factory=dict)
    total: float = 0.0


def aggregate_yields(
    harvest_logs: dict[str, dict],
    display_name_by_target: dict[str, str],
) -> list[YieldRow]:
    """Aggregate harvest entries into per-(species, unit) yearly totals.

    Args:
        harvest_logs: ``{target_id: HarvestLogHistory.to_dict()}`` as stored on
            the project.
        display_name_by_target: maps each ``target_id`` to a human label
            (resolved by the caller from the scene; falls back to the raw id).

    Returns:
        ``YieldRow`` list sorted by species then unit. ``totals_by_year`` holds
        only entries with a parseable year; ``total`` includes every entry.
    """
    by_key: dict[tuple[str, str], YieldRow] = {}
    for target_id, hist_dict in harvest_logs.items():
        history = HarvestLogHistory.from_dict(hist_dict)
        species = display_name_by_target.get(target_id, target_id)
        for entry in history.entries:
            key = (species, entry.unit)
            row = by_key.get(key)
            if row is None:
                row = YieldRow(species=species, unit=entry.unit)
                by_key[key] = row
            row.total += entry.quantity
            year = entry.year
            if year is not None:
                row.totals_by_year[year] = (
                    row.totals_by_year.get(year, 0.0) + entry.quantity
                )
    return sorted(by_key.values(), key=lambda r: (r.species.lower(), r.unit))


def all_years(rows: list[YieldRow]) -> list[int]:
    """Return the sorted union of years present across all rows."""
    years: set[int] = set()
    for row in rows:
        years.update(row.totals_by_year)
    return sorted(years)
