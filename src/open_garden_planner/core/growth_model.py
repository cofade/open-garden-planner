"""Qt-free plant growth-over-time model (US-E8, #263).

One interpolation, used everywhere: the US-E2 height resolver routes plant
heights through this module when asked for a date-projected value, so the
2D shadow overlay (US-E3), the hours-of-sun heatmap (US-E4) and the 3D
view (US-E6) all see the SAME grown size — there is deliberately no second
interpolation anywhere (issue #263's fenced path).

MVP model (linear + clamp, ADR-037/US-E8 note):
    size(t) = min + (max − min) · clamp(years_since_planting / years_to_maturity, 0, 1)

``years_to_maturity`` comes from the species' ``days_to_maturity_min/max``
when present (annual vegetables ripen within the season), else a
per-kind default: TREE 10 y, everything else (perennial/shrub/unknown)
3 y, annuals ~150 days. No planting date → ``None`` (callers fall back to
the mature/stored size — behavior unchanged for undated plants). No
seasonal dieback, no sigmoid curves — stated MVP exclusions.

Planting dates live in the EXISTING ``metadata["plant_instance"]
["planting_date"]`` (ISO date string, editable in the Plant Details panel
since US-8.x) — verified before building: no new key was added.
"""

from __future__ import annotations

import contextlib
from datetime import date
from typing import Any

#: Default years to full size when the species carries no maturity data.
YEARS_TO_MATURITY_TREE = 10.0
YEARS_TO_MATURITY_DEFAULT = 3.0  # perennials, shrubs, unknown
YEARS_TO_MATURITY_ANNUAL = 150.0 / 365.0  # ≈ a growing season

#: Fraction of the mature size a just-planted plant starts at when the
#: species has no explicit minimum (a seedling is not size zero).
_MIN_FRACTION_FALLBACK = 0.1


def _is_number(value: Any) -> bool:
    """True for real numbers — bools excluded (mirrors object_height)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_iso_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        with contextlib.suppress(ValueError):
            return date.fromisoformat(value[:10])
    return None


def planting_date_from_metadata(metadata: dict[str, Any] | None) -> date | None:
    """The plant's planting date from the existing ``plant_instance`` dict."""
    if not metadata:
        return None
    instance = metadata.get("plant_instance")
    if not isinstance(instance, dict):
        return None
    return _parse_iso_date(instance.get("planting_date"))


def years_to_maturity(
    species: dict[str, Any], object_type_name: str = ""
) -> float:
    """Species maturity horizon in years (see module docstring)."""
    days_min = species.get("days_to_maturity_min")
    days_max = species.get("days_to_maturity_max")
    days: list[float] = [
        float(d) for d in (days_min, days_max) if _is_number(d) and d > 0
    ]
    if days:
        return max(sum(days) / len(days) / 365.0, 1.0 / 365.0)
    if object_type_name == "TREE":
        return YEARS_TO_MATURITY_TREE
    # Real species dicts serialize the life cycle under "cycle"
    # (PlantSpeciesData.to_dict) — review-caught: "plant_cycle" never exists.
    cycle = str(species.get("cycle", "")).lower()
    if "annual" in cycle and "perennial" not in cycle:
        return YEARS_TO_MATURITY_ANNUAL
    return YEARS_TO_MATURITY_DEFAULT


def growth_fraction(
    planted: date | None, at_date: date, maturity_years: float
) -> float | None:
    """clamp(years since planting / years to maturity, 0, 1); None undated."""
    if planted is None or maturity_years <= 0:
        return None
    years = (at_date - planted).days / 365.0
    return max(0.0, min(1.0, years / maturity_years))


def _interpolate(
    minimum: Any, maximum: Any, fraction: float
) -> float | None:
    if not _is_number(maximum) or maximum <= 0:
        return None
    if _is_number(minimum) and 0 < minimum <= maximum:
        low = float(minimum)
    else:
        low = float(maximum) * _MIN_FRACTION_FALLBACK
    return low + (float(maximum) - low) * fraction


def grown_height_cm(
    species: dict[str, Any],
    metadata: dict[str, Any] | None,
    at_date: date,
    object_type_name: str = "",
) -> float | None:
    """Date-projected height, or None (no planting date / no species max)."""
    fraction = growth_fraction(
        planting_date_from_metadata(metadata),
        at_date,
        years_to_maturity(species, object_type_name),
    )
    if fraction is None:
        return None
    return _interpolate(
        species.get("min_height_cm"), species.get("max_height_cm"), fraction
    )


def grown_spread_cm(
    species: dict[str, Any],
    metadata: dict[str, Any] | None,
    at_date: date,
    object_type_name: str = "",
) -> float | None:
    """Date-projected canopy spread, or None. Drives the shadow footprint."""
    fraction = growth_fraction(
        planting_date_from_metadata(metadata),
        at_date,
        years_to_maturity(species, object_type_name),
    )
    if fraction is None:
        return None
    return _interpolate(
        species.get("min_spread_cm"), species.get("max_spread_cm"), fraction
    )
