"""Yield aggregation for the harvest log (US-C1, issue #188).

Pure, Qt-free helpers that roll a ``{target_id: HarvestLogHistory.to_dict()}``
map up into per-species, per-year totals for the Harvest Log tab, CSV export,
and the PDF summary page. Quantities are grouped by ``(species, unit)`` so a
crop logged in both grams and pieces never sums incompatible units.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import QCoreApplication

from open_garden_planner.models.harvest_log import HarvestLogHistory


@dataclass
class YieldRow:
    """Aggregated yield for one (species, unit) pair."""

    species: str
    unit: str
    totals_by_year: dict[int, float] = field(default_factory=dict)
    total: float = 0.0


def _plant_fallback() -> str:
    """Translated label for a harvest target that has no resolvable name."""
    return QCoreApplication.translate("HarvestLog", "Plant")


def crop_display_name_map(scene: Any) -> dict[str, str]:
    """Map each scene item's UUID string to a crop label (US-C1, #188).

    The single source of truth for crop-name resolution shared by the Harvest
    Log tab, CSV export, and the PDF summary page — prefers the item's ``name``,
    then the bound species' common name. Items without a usable name are omitted
    so ``resolve_crop_name`` supplies the one translated ``Plant`` fallback
    (this also covers harvest history whose target object no longer exists, e.g.
    a plant removed on season rollover).
    """
    names: dict[str, str] = {}
    if scene is None:
        return names
    for item in scene.items():
        item_id = getattr(item, "item_id", None)
        if item_id is None:
            continue
        label = (getattr(item, "name", "") or "").strip()
        if not label:
            metadata = getattr(item, "metadata", None) or {}
            species = metadata.get("plant_species") if isinstance(metadata, dict) else None
            if isinstance(species, dict):
                label = (species.get("common_name") or "").strip()
        if label:
            names[str(item_id)] = label
    return names


def resolve_crop_name(target_id: str, display_name_by_target: dict[str, str]) -> str:
    """Resolve a harvest target's crop label, with one translated fallback."""
    return display_name_by_target.get(target_id) or _plant_fallback()


def aggregate_yields(
    harvest_logs: dict[str, dict],
    display_name_by_target: dict[str, str],
) -> list[YieldRow]:
    """Aggregate harvest entries into per-(species, unit) yearly totals.

    Args:
        harvest_logs: ``{target_id: HarvestLogHistory.to_dict()}`` as stored on
            the project.
        display_name_by_target: maps each ``target_id`` to a human label
            (resolved by the caller via ``crop_display_name_map``); unknown
            targets fall back to a single translated ``Plant`` label.

    Returns:
        ``YieldRow`` list sorted by species then unit. ``totals_by_year`` holds
        only entries with a parseable year; ``total`` includes every entry.
    """
    by_key: dict[tuple[str, str], YieldRow] = {}
    for target_id, hist_dict in harvest_logs.items():
        history = HarvestLogHistory.from_dict(hist_dict)
        species = resolve_crop_name(target_id, display_name_by_target)
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
