"""Pure, Qt-free harvest aggregation (US-C1, epic #188).

Turns the project's ``harvest_logs`` mapping (``{target_id: HarvestHistory
dict}``) into per-species, per-year totals for the garden-wide Harvest
dashboard and its CSV / PDF exports.

The functions here take no Qt widgets, perform no I/O and never reach into the
live scene — each :class:`HarvestHistory` already caches ``species_key`` +
``species_name``, so totals resolve even after the plant item is deleted. That
keeps the engine trivially unit-testable and importable without a GUI.

Entries are grouped by ``(species, year, unit)``: a species harvested in two
different units within one year (e.g. some in ``kg`` and some in ``pcs``)
yields two rows — quantities in different units must never be summed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from open_garden_planner.models.harvest_log import HarvestHistory


@dataclass(frozen=True)
class AggregatedHarvest:
    """One species' total harvest for one year in one unit."""

    species_key: str
    species_name: str
    year: int
    unit: str
    total_quantity: float
    entry_count: int


def _year_of(date_iso: str) -> int | None:
    """Extract the 4-digit year from an ISO date string, or ``None``."""
    if not date_iso or len(date_iso) < 4:
        return None
    try:
        return int(date_iso[:4])
    except (TypeError, ValueError):
        return None


def aggregate_by_species_year(
    harvest_logs: dict[str, Any],
) -> list[AggregatedHarvest]:
    """Aggregate harvest records into per-species, per-year, per-unit totals.

    Args:
        harvest_logs: ``ProjectManager.harvest_logs`` — ``{target_id:
            HarvestHistory.to_dict()}``.

    Returns:
        Rows sorted by year (descending), then species name (ascending),
        then unit (ascending). Records with an unparseable date are skipped.
    """
    # key -> [total_quantity, entry_count, species_name]
    buckets: dict[tuple[str, int, str], list[Any]] = {}

    for target_id, raw in harvest_logs.items():
        try:
            history = HarvestHistory.from_dict(raw)
        except Exception:
            continue
        # Stable grouping key: prefer the cached species key; fall back to the
        # target id so distinct unkeyed targets (e.g. beds) never merge.
        species_key = history.species_key or f"target:{target_id}"
        species_name = history.species_name or species_key

        for rec in history.records:
            year = _year_of(rec.date)
            if year is None:
                continue
            unit = rec.unit or ""
            key = (species_key, year, unit)
            bucket = buckets.get(key)
            if bucket is None:
                buckets[key] = [rec.quantity, 1, species_name]
            else:
                bucket[0] += rec.quantity
                bucket[1] += 1

    rows = [
        AggregatedHarvest(
            species_key=key[0],
            species_name=val[2],
            year=key[1],
            unit=key[2],
            total_quantity=val[0],
            entry_count=val[1],
        )
        for key, val in buckets.items()
    ]
    rows.sort(key=lambda a: (-a.year, a.species_name.lower(), a.unit))
    return rows


#: CSV header for the garden-wide harvest export.
HARVEST_CSV_HEADERS = ["species", "year", "total_quantity", "unit", "entry_count"]


def harvest_csv_rows(aggregates: list[AggregatedHarvest]) -> list[dict[str, Any]]:
    """Convert aggregated rows into CSV-ready dicts keyed by ``HARVEST_CSV_HEADERS``."""
    return [
        {
            "species": a.species_name,
            "year": a.year,
            "total_quantity": f"{a.total_quantity:g}",
            "unit": a.unit,
            "entry_count": a.entry_count,
        }
        for a in aggregates
    ]


__all__ = [
    "AggregatedHarvest",
    "HARVEST_CSV_HEADERS",
    "aggregate_by_species_year",
    "harvest_csv_rows",
]
