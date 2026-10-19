"""Qt-free classification of completed ground exposure (ADR-056, US-F3).

No computation or I/O: consumers supply cached minutes, or an explicit reason
why the exposure has not been evaluated. UNKNOWN is never a warning.
"""

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from open_garden_planner.core.shade_aggregation import BAND_THRESHOLDS_MINUTES
from open_garden_planner.models.plant_data import PermacultureLayer, SunRequirement

_SHADE, _PARTIAL, _FULL = (value / 60 for value in BAND_THRESHOLDS_MINUTES)
SUN_BANDS: dict[SunRequirement, tuple[float | None, float | None]] = {
    SunRequirement.FULL_SUN: (_FULL, None),
    SunRequirement.PARTIAL_SUN: (_PARTIAL, _FULL),
    SunRequirement.PARTIAL_SHADE: (_SHADE, _PARTIAL),
    SunRequirement.FULL_SHADE: (None, _SHADE),
}
TOLERANCE_HOURS = 1.0
MEASUREMENT_METHOD = "ground_cell_centre_excluding_self"


@dataclass(frozen=True)
class SunEvaluation:
    item_id: str
    required: SunRequirement
    hours: float | None
    reference_date: date
    reason: str | None = None


@dataclass(frozen=True)
class SunMismatch:
    item_id: str
    required: SunRequirement
    hours: float
    reference_date: date
    direction: str
    severity: str = "warning"


def evaluate_sun(item_id: str, required: Any, minutes: float | None, reference_date: date,
                 *, reason: str = "absent") -> SunEvaluation:
    try:
        requirement = SunRequirement(required)
    except (ValueError, TypeError):
        requirement = SunRequirement.UNKNOWN
    if minutes is None:
        return SunEvaluation(item_id, requirement, None, reference_date, reason)
    if not isinstance(minutes, (int, float)) or isinstance(minutes, bool) or not math.isfinite(minutes) or minutes < 0:
        return SunEvaluation(item_id, requirement, None, reference_date, "invalid")
    return SunEvaluation(item_id, requirement, minutes / 60, reference_date)


def classify_mismatch(evaluation: SunEvaluation) -> SunMismatch | None:
    if evaluation.hours is None or evaluation.required not in SUN_BANDS:
        return None
    lower, upper = SUN_BANDS[evaluation.required]
    direction = ("too_little" if lower is not None and evaluation.hours < lower - TOLERANCE_HOURS
                 else "too_much" if upper is not None and evaluation.hours > upper + TOLERANCE_HOURS else None)
    if direction is None:
        return None
    return SunMismatch(evaluation.item_id, evaluation.required, evaluation.hours, evaluation.reference_date, direction)


@dataclass(frozen=True)
class CanopyPlant:
    item_id: str
    name: str
    x_cm: float
    y_cm: float
    layer: str = "unknown"


def canopy_members(tree_id: str, centre: tuple[float, float], mature_spread_cm: float | None,
                   plants: list[CanopyPlant]) -> list[CanopyPlant] | None:
    """Centre membership in a mature circle; None means no recorded spread."""
    if (not isinstance(mature_spread_cm, (int, float)) or isinstance(mature_spread_cm, bool)
            or not math.isfinite(mature_spread_cm) or mature_spread_cm <= 0):
        return None
    layers = {layer.value: index for index, layer in enumerate(PermacultureLayer)}
    members = [plant for plant in plants if plant.item_id != tree_id
               and math.hypot(plant.x_cm - centre[0], plant.y_cm - centre[1]) <= mature_spread_cm / 2]
    return sorted(members, key=lambda plant: (layers.get(plant.layer, layers["unknown"]),
                                             plant.name.casefold(), plant.item_id))
