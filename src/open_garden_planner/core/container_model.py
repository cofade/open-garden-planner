"""Pure-function helpers for container gardening (US-C3).

Containers (pots, wall planters) ride the existing rectangle/circle shape
items tagged with a container :class:`~open_garden_planner.core.object_types.ObjectType`.
Their extra properties live in the item's ``metadata`` dict (additive, so old
``.ogp`` files round-trip unchanged):

* ``container_height_cm`` — fill height in centimetres (default 30).
* ``container_material`` — one of :data:`MATERIALS` (default ``"plastic"``).
* ``container_drainage`` — drainage holes present (default ``True``).
* ``container_soil_volume_l`` — explicit soil-volume override in litres, or
  absent/``None`` to auto-compute from footprint × height.

This module is intentionally Qt-free so the soil-volume, watering-hint, and
capacity rules can be unit-tested in isolation (mirrors ``core/plant_sizing``).
Watering-hint strings are returned as source English; the UI layer translates
them under the ``"ContainerModel"`` context.
"""

from __future__ import annotations

from typing import Any

# --- Material identifiers (stored verbatim in metadata) ---------------------
TERRACOTTA = "terracotta"
PLASTIC = "plastic"
WOOD = "wood"
METAL = "metal"
MATERIALS: tuple[str, ...] = (TERRACOTTA, PLASTIC, WOOD, METAL)

# --- Defaults ---------------------------------------------------------------
DEFAULT_HEIGHT_CM = 30.0
DEFAULT_MATERIAL = PLASTIC
DEFAULT_DRAINAGE = True

# --- Watering hints (source English, translated at the UI layer) ------------
# Per-material base hint, keyed by material identifier.
_MATERIAL_HINTS: dict[str, str] = {
    TERRACOTTA: "Porous terracotta dries out fast — water frequently.",
    PLASTIC: "Plastic retains moisture — water sparingly to avoid root rot.",
    WOOD: "Wood holds moisture moderately, but can rot if kept waterlogged.",
    METAL: "Metal heats up in sun and dries the root zone — monitor on hot days.",
}
# Appended when the container has no drainage holes.
_NO_DRAINAGE_HINT = "No drainage holes: water carefully — risk of waterlogging."


def _positive_number(value: Any) -> float | None:
    """Coerce ``value`` to a positive float, or ``None`` if it is not one.

    ``bool`` is rejected so ``True`` is never mistaken for ``1.0``.
    """
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def container_height_cm(metadata: dict[str, Any] | None) -> float:
    """Return the container fill height in cm (default :data:`DEFAULT_HEIGHT_CM`)."""
    if not metadata:
        return DEFAULT_HEIGHT_CM
    return _positive_number(metadata.get("container_height_cm")) or DEFAULT_HEIGHT_CM


def container_material(metadata: dict[str, Any] | None) -> str:
    """Return the container material (default :data:`DEFAULT_MATERIAL`)."""
    if not metadata:
        return DEFAULT_MATERIAL
    value = metadata.get("container_material")
    return value if value in MATERIALS else DEFAULT_MATERIAL


def container_has_drainage(metadata: dict[str, Any] | None) -> bool:
    """Return whether the container has drainage holes (default ``True``)."""
    if not metadata:
        return DEFAULT_DRAINAGE
    value = metadata.get("container_drainage")
    return DEFAULT_DRAINAGE if value is None else bool(value)


def auto_soil_volume_litres(footprint_cm2: float, height_cm: float) -> float:
    """Auto-compute soil volume in litres from footprint area × fill height.

    1 litre = 1000 cm³. A non-positive footprint or height yields ``0.0``.
    """
    if footprint_cm2 <= 0 or height_cm <= 0:
        return 0.0
    return footprint_cm2 * height_cm / 1000.0


def effective_soil_volume_litres(
    metadata: dict[str, Any] | None,
    footprint_cm2: float,
    height_cm: float | None = None,
) -> float:
    """Resolve soil volume in litres: explicit override wins, else auto-compute.

    Precedence: ``metadata["container_soil_volume_l"]`` (if a positive number)
    overrides; otherwise :func:`auto_soil_volume_litres` from ``footprint_cm2``
    and the container height (``height_cm`` arg or the metadata height).
    """
    if metadata:
        override = _positive_number(metadata.get("container_soil_volume_l"))
        if override is not None:
            return override
    resolved_height = height_cm if height_cm is not None else container_height_cm(metadata)
    return auto_soil_volume_litres(footprint_cm2, resolved_height)


def watering_hint(material: str, drainage: bool) -> str:
    """Return a source-English watering hint for a material + drainage combo.

    The returned strings are registered for translation under the
    ``"ContainerModel"`` context and translated by the caller (UI layer).
    """
    base = _MATERIAL_HINTS.get(material, _MATERIAL_HINTS[DEFAULT_MATERIAL])
    if not drainage:
        return f"{base} {_NO_DRAINAGE_HINT}"
    return base


def total_child_footprint_cm2(child_footprints_cm2: list[float]) -> float:
    """Sum child plant footprint areas (cm²), ignoring non-positive entries.

    Uses true plant footprint (the drawn circle area), NOT the spacing-circle
    area — spacing is reported separately by the per-plant overlap badge.
    """
    return sum(area for area in child_footprints_cm2 if area > 0)


def is_capacity_exceeded(
    container_footprint_cm2: float, child_footprints_cm2: list[float]
) -> bool:
    """Whether the combined plant footprint overflows the container footprint."""
    if container_footprint_cm2 <= 0:
        return False
    return total_child_footprint_cm2(child_footprints_cm2) > container_footprint_cm2
