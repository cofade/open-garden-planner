"""Qt-free plant lifetime rules for the shared plan date (US-F4, ADR-062).

Missing or malformed dates are open bounds. Planting is inclusive, removal
exclusive. These are instance dates, never species traits or season copies.
"""

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any


def instance_date(metadata: Any, key: str) -> date | None:
    """Read a strict ISO day, tolerating old/sparse/hostile instance metadata."""
    if not isinstance(metadata, Mapping):
        return None
    instance = metadata.get("plant_instance")
    value = instance.get(key) if isinstance(instance, Mapping) else None
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def plant_present(metadata: Any, day: date | None) -> bool:
    """Whether a plant exists on ``day``; None means no timeline is attached."""
    if day is None:
        return True
    planted = instance_date(metadata, "planting_date")
    removed = instance_date(metadata, "removal_date")
    return (planted is None or day >= planted) and (removed is None or day < removed)


def month_number(day: date) -> int:
    return day.year * 12 + day.month - 1


def month_start(number: int) -> date:
    year, month = divmod(number, 12)
    return date(year, month + 1, 1)


def timeline_month_range(metadata: Iterable[Any], today: date, current: date) -> tuple[int, int]:
    """One year before earliest planting through latest removal or ten years out.

    Include today/current and clamp to SimClock's supported range. No private
    date state: callers always supply the clock's current plan date.
    """
    from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE

    records = list(metadata)
    planted = [d for m in records if (d := instance_date(m, "planting_date"))]
    removed = [d for m in records if (d := instance_date(m, "removal_date"))]
    first = min([today, *planted])
    low = max(month_number(MIN_PLAN_DATE), min(month_number(first) - 12, month_number(current)))
    high = min(month_number(MAX_PLAN_DATE), max(
        month_number(today) + 120, month_number(current),
        *(month_number(d) for d in removed),
    ))
    return low, high
