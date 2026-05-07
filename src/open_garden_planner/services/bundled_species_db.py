"""Bundled species database loaded from plant_species.json.

Single source of truth for curated species records — including soil pH,
NPK demands, calendar timing, growth, sun/water needs, and hardiness.
Used by the canvas drop flow to auto-populate item metadata, and by the
plant-detail UI as the calendar overlay (replaces the former
planting_calendar_db). Drop callers should use ``populate_item_species_metadata``;
calendar callers should keep using ``get_calendar_entry`` / ``merge_calendar_data``
with their original signatures.
"""

import json
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent.parent / "resources" / "data"


_CALENDAR_FIELDS = (
    "indoor_sow_start",
    "indoor_sow_end",
    "direct_sow_start",
    "direct_sow_end",
    "transplant_start",
    "transplant_end",
    "harvest_start",
    "harvest_end",
    "days_to_germination_min",
    "days_to_germination_max",
    "days_to_maturity_min",
    "days_to_maturity_max",
    "frost_tolerance",
    "min_germination_temp_c",
    "seed_depth_cm",
    "prick_out_after_days",
    "harden_off_days",
    "family",
    "nutrient_demand",
)


def _load_species_db() -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    """Load the bundled species JSON and build the lookup indexes.

    Returns:
        (by_scientific, by_common, by_alias) — each maps a lower-cased name
        to the record dict. ``by_alias`` covers optional ``aliases`` arrays
        per record so gallery name variants (e.g. "pepper" → "Sweet Pepper",
        "apple tree" → "Malus domestica") resolve. On any IO/parse error,
        all three indexes are empty.
    """
    by_scientific: dict[str, dict[str, Any]] = {}
    by_common: dict[str, dict[str, Any]] = {}
    by_alias: dict[str, dict[str, Any]] = {}
    try:
        species_path = _DATA_DIR / "plant_species.json"
        with open(species_path, encoding="utf-8") as f:
            parsed: dict[str, Any] = json.load(f)
    except Exception:
        return by_scientific, by_common, by_alias

    for entry in parsed.get("plants", []):
        sci = entry.get("scientific_name", "").lower()
        if sci:
            by_scientific[sci] = entry
        com = entry.get("common_name", "").lower()
        # First record listed wins on common-name ties (none today, but the
        # check is cheap insurance against future drift).
        if com and com not in by_common:
            by_common[com] = entry
        # Aliases is optional. Guard against a non-list (e.g. someone
        # mistypes `"aliases": "pepper"`) — without this, a bare string
        # would silently iterate one character at a time.
        aliases = entry.get("aliases")
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
            if not isinstance(alias, str):
                continue
            key = alias.lower().strip()
            if key and key not in by_alias:
                by_alias[key] = entry
    return by_scientific, by_common, by_alias


# Module-level singletons — loaded once on first import
_BY_SCIENTIFIC: dict[str, dict[str, Any]] | None = None
_BY_COMMON: dict[str, dict[str, Any]] | None = None
_BY_ALIAS: dict[str, dict[str, Any]] | None = None


def _ensure_loaded() -> None:
    global _BY_SCIENTIFIC, _BY_COMMON, _BY_ALIAS
    if _BY_SCIENTIFIC is None or _BY_COMMON is None or _BY_ALIAS is None:
        _BY_SCIENTIFIC, _BY_COMMON, _BY_ALIAS = _load_species_db()


def get_species_db() -> dict[str, dict[str, Any]]:
    """Return the cached species database keyed by lowercased scientific name."""
    _ensure_loaded()
    assert _BY_SCIENTIFIC is not None
    return _BY_SCIENTIFIC


def get_species_entry(scientific_name: str) -> dict[str, Any] | None:
    """Look up a species record by scientific name (case-insensitive)."""
    if not scientific_name:
        return None
    _ensure_loaded()
    assert _BY_SCIENTIFIC is not None
    return _BY_SCIENTIFIC.get(scientific_name.lower())


def get_species_by_common_name(common_name: str) -> dict[str, Any] | None:
    """Look up a species record by common name (case-insensitive)."""
    if not common_name:
        return None
    _ensure_loaded()
    assert _BY_COMMON is not None
    return _BY_COMMON.get(common_name.lower())


def get_species_by_alias(alias: str) -> dict[str, Any] | None:
    """Look up a species record by an alias declared on the record."""
    if not alias:
        return None
    _ensure_loaded()
    assert _BY_ALIAS is not None
    return _BY_ALIAS.get(alias.lower().strip())


def lookup_species(name: str) -> dict[str, Any] | None:
    """Look up a species by scientific → common → alias (case-insensitive).

    The drop flow passes whatever string the gallery / tool exposed (which
    is derived from the SVG filename, e.g. "apple tree", "pea"); aliases
    on each record cover the cases where that doesn't match the canonical
    common name.
    """
    if not name:
        return None
    return (
        get_species_entry(name)
        or get_species_by_common_name(name)
        or get_species_by_alias(name)
    )


# ---------------------------------------------------------------------------
# Calendar-overlay API (signatures preserved from the former
# planting_calendar_db module so existing callers keep working).
# ---------------------------------------------------------------------------


def get_calendar_db() -> dict[str, dict[str, Any]]:
    """Backwards-compatible alias used by the legacy calendar tests."""
    return get_species_db()


def get_calendar_entry(scientific_name: str) -> dict[str, Any] | None:
    """Backwards-compatible alias used by callers that only need calendar fields."""
    return get_species_entry(scientific_name)


def merge_calendar_data(
    plant_dict: dict[str, Any],
    api_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge calendar fields into a plant dict.

    Priority: bundled DB > existing plant_dict value > api_dict.
    """
    scientific_name = plant_dict.get("scientific_name", "")
    local_entry = get_species_entry(scientific_name) if scientific_name else None

    result = dict(plant_dict)

    for field in _CALENDAR_FIELDS:
        if local_entry is not None and local_entry.get(field) is not None:
            result[field] = local_entry[field]
        elif result.get(field) is not None:
            pass
        elif api_dict is not None and api_dict.get(field) is not None:
            result[field] = api_dict[field]

    return result


# ---------------------------------------------------------------------------
# Drop-flow hook
# ---------------------------------------------------------------------------


def populate_item_species_metadata(item: Any, name: str) -> bool:
    """Populate ``item.metadata['plant_species']`` from the bundled DB.

    Called from canvas drop / tool-draw paths. Looks up ``name`` (scientific
    name first, common name fallback) and writes the full record onto the
    item, with ``merge_calendar_data`` applied so the result behaves
    identically to a record that's been through the calendar overlay.

    Args:
        item: A canvas item exposing a ``metadata`` dict (CircleItem, etc.).
        name: Scientific or common name of the species.

    Returns:
        True if a record was found and written, False otherwise.
    """
    record = lookup_species(name)
    if record is None:
        return False

    metadata = getattr(item, "metadata", None)
    if metadata is None:
        return False

    metadata["plant_species"] = merge_calendar_data(dict(record))
    return True
