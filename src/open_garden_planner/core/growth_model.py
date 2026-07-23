"""Qt-free plant growth-over-time model (US-E8, #263).

One interpolation, used everywhere: the US-E2 height resolver routes plant
heights through this module when asked for a date-projected value, so the
2D shadow overlay (US-E3), the hours-of-sun heatmap (US-E4) and the 3D
view (US-E6) all see the SAME grown size — there is deliberately no second
interpolation anywhere (issue #263's fenced path).

MVP model (linear + clamp, ADR-037/US-E8 note — owner-chosen
"current-height anchors it" redesign):
    size(t) = current + (max − current) · clamp(years_since_planting / years_to_maturity, 0, 1)

The low end is the plant's OWN measured size — ``current_height_cm`` /
``current_spread_cm`` on the ``plant_instance`` — NOT the species minimum:
the user sets how tall the plant is *at its planting date* and it grows
toward the species ``max`` at maturity. Growth therefore engages ONLY when
BOTH a planting date AND a current size are set; otherwise this returns
``None`` and the height resolver falls back to the static current size,
else the mature ``max`` (behaviour unchanged for un-measured plants). An
already-oversized plant (current ≥ max) stays flat at ``max``.

``years_to_maturity`` comes from the species' ``days_to_maturity_min/max``
when present (annual vegetables ripen within the season), else a
per-kind default: TREE 10 y, everything else (perennial/shrub/unknown)
3 y, annuals ~150 days. No seasonal dieback, no sigmoid curves — stated
MVP exclusions.

Planting dates and current sizes both live in the EXISTING
``metadata["plant_instance"]`` dict (``planting_date`` ISO string,
``current_height_cm`` / ``current_spread_cm`` floats — editable in the
Plant Details panel since US-8.x). New plants default ``planting_date`` to
their creation day so scrubbing the sim date grows them without extra
steps. No new metadata key was added.
"""

from __future__ import annotations

import contextlib
from datetime import date, datetime
from typing import Any

#: Default years to full size when the species carries no maturity data.
YEARS_TO_MATURITY_TREE = 10.0
YEARS_TO_MATURITY_DEFAULT = 3.0  # perennials, shrubs, unknown
YEARS_TO_MATURITY_ANNUAL = 150.0 / 365.0  # ≈ a growing season

def _is_number(value: Any) -> bool:
    """True for real numbers — bools excluded (mirrors object_height)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive(value: Any) -> float | None:
    """Coerce to a positive float, else None (bools rejected)."""
    if not _is_number(value):
        return None
    number = float(value)
    return number if number > 0 else None


def _instance_value(metadata: dict[str, Any] | None, key: str) -> float | None:
    """A positive float from the ``plant_instance`` dict, else None."""
    if not metadata:
        return None
    instance = metadata.get("plant_instance")
    if not isinstance(instance, dict):
        return None
    return _positive(instance.get(key))


def current_height_from_metadata(metadata: dict[str, Any] | None) -> float | None:
    """The plant's user-measured current height (``plant_instance``)."""
    return _instance_value(metadata, "current_height_cm")


def current_spread_from_metadata(metadata: dict[str, Any] | None) -> float | None:
    """The plant's user-measured current canopy spread (``plant_instance``).

    Honours the legacy ``current_diameter_cm`` alias, like
    ``PlantInstance.from_dict`` / the CSV export / the shopping list — else
    an old plan would show a spread everywhere except the shadow.
    """
    value = _instance_value(metadata, "current_spread_cm")
    if value is None:
        value = _instance_value(metadata, "current_diameter_cm")
    return value


def _derive_from_other(
    other_current: float | None,
    other_max: Any,
    this_max: Any,
) -> float | None:
    """Scale ``this_max`` by how far along its range the OTHER dimension is.

    Users measure one field far more often than both (a shrub's spread is
    easier to eyeball than its height). Without this, the unmeasured
    dimension stays at the species maximum and the plant renders as a
    nonsense shape — an 8 m pole 1 m wide, or a 1.5 m pancake 6 m across.
    Proportional is the neutral assumption in the absence of data.
    """
    high_other = _positive(other_max)
    high_this = _positive(this_max)
    if other_current is None or high_other is None or high_this is None:
        return None
    return high_this * min(1.0, other_current / high_other)


def effective_current_height_cm(
    species: dict[str, Any], metadata: dict[str, Any] | None
) -> float | None:
    """The plant's current height — measured, else implied by its spread."""
    measured = current_height_from_metadata(metadata)
    if measured is not None:
        return measured
    return _derive_from_other(
        current_spread_from_metadata(metadata),
        species.get("max_spread_cm"),
        species.get("max_height_cm"),
    )


def effective_current_spread_cm(
    species: dict[str, Any], metadata: dict[str, Any] | None
) -> float | None:
    """The plant's current spread — measured, else implied by its height."""
    measured = current_spread_from_metadata(metadata)
    if measured is not None:
        return measured
    return _derive_from_other(
        current_height_from_metadata(metadata),
        species.get("max_height_cm"),
        species.get("max_spread_cm"),
    )


def stamp_default_planting_date(
    metadata: dict[str, Any] | None, today: date
) -> None:
    """Default a fresh plant's planting date to ``today`` (US-E8).

    Writes ``metadata["plant_instance"]["planting_date"]`` (ISO) only when
    absent, so growth-over-time engages for newly placed plants without the
    user opening the Plant Details panel. Never overwrites a user-set or
    loaded date; idempotent. Called ONLY at fresh-creation sites — never on
    file load, which must preserve saved metadata verbatim.
    """
    if metadata is None:
        return
    instance = metadata.setdefault("plant_instance", {})
    if not isinstance(instance, dict):
        return
    if not instance.get("planting_date"):
        instance["planting_date"] = today.isoformat()


def _parse_iso_date(value: Any) -> date | None:
    # datetime subclasses date, so narrow it FIRST — otherwise a datetime
    # would flow through and `at_date - planted` raises TypeError.
    if isinstance(value, datetime):
        return value.date()
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
    # days_to_maturity is days to HARVEST, not days to full size. For a tree
    # that would grow an 8 m specimen in a single season, so trees always use
    # the decade default. No bundled tree carries the field today, but an
    # API-sourced or custom fruit-tree record easily could.
    if days and object_type_name != "TREE":
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


def _grown_dimension(
    species: dict[str, Any],
    metadata: dict[str, Any] | None,
    at_date: date,
    object_type_name: str,
    current: float | None,
    maximum: Any,
) -> float | None:
    """Interpolate ``current → max`` by age; None unless both ends are set."""
    if current is None:
        return None
    high = _positive(maximum)
    if high is None:
        return None
    fraction = growth_fraction(
        planting_date_from_metadata(metadata),
        at_date,
        years_to_maturity(species, object_type_name),
    )
    if fraction is None:
        return None
    # A plant measured at or beyond its species maximum is simply already
    # mature. Return the MEASUREMENT rather than clamping down to the max:
    # silently shrinking it would make this dated path disagree with the
    # undated one (which returns the measured value as-is), so the
    # properties panel would read 900 cm while the shadow cast 800.
    if current >= high:
        return current
    return current + (high - current) * fraction


def grown_height_cm(
    species: dict[str, Any],
    metadata: dict[str, Any] | None,
    at_date: date,
    object_type_name: str = "",
) -> float | None:
    """Date-projected height from the plant's CURRENT height up to the
    species max, or None (no planting date / no current height / no max)."""
    return _grown_dimension(
        species,
        metadata,
        at_date,
        object_type_name,
        effective_current_height_cm(species, metadata),
        species.get("max_height_cm"),
    )


def grown_spread_cm(
    species: dict[str, Any],
    metadata: dict[str, Any] | None,
    at_date: date,
    object_type_name: str = "",
) -> float | None:
    """Date-projected canopy spread from the plant's CURRENT spread up to
    the species max, or None. Drives the shadow footprint."""
    return _grown_dimension(
        species,
        metadata,
        at_date,
        object_type_name,
        effective_current_spread_cm(species, metadata),
        species.get("max_spread_cm"),
    )
