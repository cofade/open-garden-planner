"""Qt-free validation + ``.ogp``-dict building for ``create_object`` (US-D2.1).

Kept import-light like :mod:`~open_garden_planner.agent_api.mapping`: no PyQt6.
The object-type name sets are inlined rather than importing
``core.object_types`` (which pulls in ``QColor`` and the rest of Qt);
``tests/unit/test_agent_api_creates.py`` guards every set against drift from the
real ``ObjectType`` definitions.

The dict this module builds is handed straight to
``ProjectManager._deserialize_item_core`` — the same factory the ``.ogp`` file
loader uses. That is deliberate: an agent-created object is then constructed by
exactly the code path a loaded one is, so there is no second item-construction
path to drift (see the "two divergent item serializers" weak point in
``ogp-architecture-contract`` §4).

Coordinates follow the rest of the Agent API: ``x``/``y`` are the object's
**centre** in scene cm, CAD Y-up (a larger y is further north). Rectangles are
serialised top-left-anchored, so the centre is converted to the stored anchor
here — ``anchor = centre - extent / 2`` holds in either y-direction reading, so
this conversion is frame-agnostic and cannot introduce a Y-flip bug.
"""

from __future__ import annotations

import math
from typing import Any

# Plant object types — mirrors ``plant_renderer.is_plant_type``.
_PLANT_TYPE_NAMES = frozenset({"TREE", "SHRUB", "PERENNIAL"})

# Soil-bearing parents — mirrors ObjectType ``SOIL_CONTAINER_TYPES`` (ADR-031).
_SOIL_CONTAINER_TYPE_NAMES = frozenset(
    {"GARDEN_BED", "RAISED_BED", "CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"}
)

# How each creatable type is serialised. A type is built as the shape the GUI's
# own gallery builds it as (``object_types.valid_object_types_for_shape``):
# CONTAINER_ROUND is circle-only, the other soil containers are rectangle-based,
# and plants are circles. GARDEN_BED is also legal as a circle/ellipse/polygon in
# the app; this first write slice creates it as a rectangle only.
_CIRCLE_TYPE_NAMES = _PLANT_TYPE_NAMES | {"CONTAINER_ROUND"}
_RECT_TYPE_NAMES = frozenset({"GARDEN_BED", "RAISED_BED", "CONTAINER", "WALL_PLANTER"})

#: Every object type ``create_object`` can build (US-D2.1's agreed scope:
#: plants + soil containers). Later slices widen this.
CREATABLE_TYPE_NAMES: frozenset[str] = _CIRCLE_TYPE_NAMES | _RECT_TYPE_NAMES

# Default plant footprint when the caller gives no radius — the SAME numbers the
# gallery-drop path uses (``CanvasView`` drop handler ``size_map``), as diameters.
_DEFAULT_PLANT_DIAMETER_CM: dict[str, float] = {
    "TREE": 200.0,
    "SHRUB": 100.0,
    "PERENNIAL": 60.0,
}


def is_plant_type_name(object_type: str) -> bool:
    """Whether ``object_type`` names a plant (TREE/SHRUB/PERENNIAL)."""
    return object_type in _PLANT_TYPE_NAMES


def _require_finite(value: float, field: str) -> float:
    """Reject NaN/inf before they reach Qt geometry as a silent corruption."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    return number


def _require_positive(value: float, field: str) -> float:
    """Reject zero/negative extents — a degenerate item the GUI can never draw."""
    number = _require_finite(value, field)
    if number <= 0:
        raise ValueError(f"{field} must be greater than 0, got {number}")
    return number


def build_create_dict(
    *,
    object_type: str,
    x: float,
    y: float,
    width: float | None = None,
    height: float | None = None,
    radius: float | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Validate creation parameters and build an ``.ogp``-shaped item dict.

    Args:
        object_type: An ``ObjectType`` name from :data:`CREATABLE_TYPE_NAMES`.
        x: Centre X in scene cm.
        y: Centre Y in scene cm (Y-up: a larger y is further north).
        width: Width in cm — required for rectangle-based types, rejected for
            circle-based ones.
        height: Height in cm — same rule as ``width``.
        radius: Radius in cm — for circle-based types. Optional for plants
            (they fall back to the GUI's default footprint); required for
            ``CONTAINER_ROUND``, which has no meaningful default size.
        name: Optional display name.

    Returns:
        A dict accepted by ``ProjectManager._deserialize_item_core``.

    Raises:
        ValueError: On an unsupported type, a missing required dimension, a
            dimension that doesn't belong to the type's shape, or a
            non-finite/non-positive extent. Refusing beats silently creating
            something the caller didn't ask for (the D2.0 precedent).
    """
    if object_type not in CREATABLE_TYPE_NAMES:
        supported = ", ".join(sorted(CREATABLE_TYPE_NAMES))
        raise ValueError(
            f"create_object cannot create {object_type!r} yet. "
            f"Supported object types: {supported}."
        )

    centre_x = _require_finite(x, "x")
    centre_y = _require_finite(y, "y")

    common: dict[str, Any] = {"object_type": object_type}
    if name:
        common["name"] = name

    if object_type in _CIRCLE_TYPE_NAMES:
        if width is not None or height is not None:
            raise ValueError(
                f"{object_type} is round — pass 'radius', not 'width'/'height'."
            )
        if radius is not None:
            resolved_radius = _require_positive(radius, "radius")
        elif object_type in _DEFAULT_PLANT_DIAMETER_CM:
            resolved_radius = _DEFAULT_PLANT_DIAMETER_CM[object_type] / 2
        else:
            raise ValueError(f"{object_type} requires an explicit 'radius' in cm.")
        return {
            **common,
            "type": "circle",
            "center_x": centre_x,
            "center_y": centre_y,
            "radius": resolved_radius,
        }

    if radius is not None:
        raise ValueError(
            f"{object_type} is rectangular — pass 'width'/'height', not 'radius'."
        )
    if width is None or height is None:
        raise ValueError(f"{object_type} requires both 'width' and 'height' in cm.")
    resolved_width = _require_positive(width, "width")
    resolved_height = _require_positive(height, "height")
    return {
        **common,
        "type": "rectangle",
        # Serialised rectangles are anchor-based; the API speaks centres.
        "x": centre_x - resolved_width / 2,
        "y": centre_y - resolved_height / 2,
        "width": resolved_width,
        "height": resolved_height,
    }
