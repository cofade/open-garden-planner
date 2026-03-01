"""Local planting calendar database for curated species timing data.

Provides merge logic: local curated data takes priority, API data fills gaps.
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
)


def _load_calendar_db() -> dict[str, dict[str, Any]]:
    """Load the bundled planting calendar JSON and index by scientific name.

    Returns:
        Mapping of lower-cased scientific name → calendar entry dict.
    """
    try:
        calendar_path = _DATA_DIR / "planting_calendar.json"
        with open(calendar_path, encoding="utf-8") as f:
            parsed: dict[str, Any] = json.load(f)
    except Exception:
        return {}

    index: dict[str, dict[str, Any]] = {}
    for entry in parsed.get("plants", []):
        key = entry.get("scientific_name", "").lower()
        if key:
            index[key] = entry
    return index


# Module-level singleton — loaded once on first import
_DB: dict[str, dict[str, Any]] | None = None


def get_calendar_db() -> dict[str, dict[str, Any]]:
    """Return the cached planting calendar database.

    Returns:
        Mapping of lower-cased scientific name → calendar entry dict.
    """
    global _DB
    if _DB is None:
        _DB = _load_calendar_db()
    return _DB


def get_calendar_entry(scientific_name: str) -> dict[str, Any] | None:
    """Look up calendar data for a species by scientific name.

    The lookup is case-insensitive.

    Args:
        scientific_name: The scientific name to look up.

    Returns:
        Calendar entry dict or None if not found.
    """
    return get_calendar_db().get(scientific_name.lower())


def merge_calendar_data(
    plant_dict: dict[str, Any],
    api_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge planting calendar fields into a plant data dict.

    Priority: local DB > plant_dict existing values > api_dict.

    Args:
        plant_dict: Base plant data dict (may already have some calendar fields).
        api_dict: Optional dict of calendar fields from an external API.

    Returns:
        Updated plant_dict with calendar fields filled in.
    """
    scientific_name = plant_dict.get("scientific_name", "")
    local_entry = get_calendar_entry(scientific_name) if scientific_name else None

    result = dict(plant_dict)

    for field in _CALENDAR_FIELDS:
        # Local DB takes highest priority
        if local_entry is not None and local_entry.get(field) is not None:
            result[field] = local_entry[field]
        # Keep existing value if already set
        elif result.get(field) is not None:
            pass
        # Fall back to API data
        elif api_dict is not None and api_dict.get(field) is not None:
            result[field] = api_dict[field]

    return result
