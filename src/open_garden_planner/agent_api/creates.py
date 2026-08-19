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

# --- Size sanity bounds ---------------------------------------------------
#
# A finite, positive extent is not automatically a *sane* one, and an agent is
# exactly where a unit slip (metres typed as centimetres) shows up. Two bounds,
# each for its own stated reason — this mirrors `render.py`'s precedent of
# clamping agent-supplied sizes harder than the GUI does.
#
# 1. Canvas-relative, applied to every type: an object may be at most this
#    multiple of the plan's larger dimension. Generous enough for a bed that
#    spans the whole plot (the user may enlarge the canvas later), tight enough
#    that a 100x unit slip is refused with an error naming the real plan size.
_MAX_EXTENT_CANVAS_MULTIPLE = 2.0
#
# 2. Absolute, applied to plants only, because a plant's footprint feeds
#    `plant_renderer.render_plant_pixmap`, which does `size = max(int(diameter), 4)`
#    and allocates a `size x size` ARGB QImage -- in scene CM, not device pixels.
#    That is quadratic and runs on the Qt main thread: measured on a dev machine,
#    diameter 8000 cm costs ~0.26 GB / 0.5 s, 24000 cm costs ~2.3 GB / 3.0 s, and
#    a large enough value fails allocation and yields a NULL (not None) QPixmap
#    that the paint path forwards to drawPixmap unchecked. 5000 cm (a 50 m
#    canopy) bounds the worst case at ~100 MB and is far beyond any real garden
#    plant, so this only ever fires on nonsense input.
_MAX_PLANT_DIAMETER_CM = 5000.0


def is_plant_type_name(object_type: str) -> bool:
    """Whether ``object_type`` names a plant (TREE/SHRUB/PERENNIAL)."""
    return object_type in _PLANT_TYPE_NAMES


def require_finite(value: float, field: str) -> float:
    """Reject NaN/inf before they reach Qt geometry as a silent corruption."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    return number


def require_positive(value: float, field: str) -> float:
    """Reject zero/negative extents — a degenerate item the GUI can never draw."""
    number = require_finite(value, field)
    if number <= 0:
        raise ValueError(f"{field} must be greater than 0, got {number}")
    return number


def _require_within_canvas(
    centre_x: float,
    centre_y: float,
    canvas_width_cm: float,
    canvas_height_cm: float,
) -> None:
    """Refuse a centre far outside the plan, which no GUI gesture could reach.

    The canvas spans ``(0, 0)`` to ``(width, height)``; we allow one full canvas
    of slack on every side so an agent can stage an object just off-plan, but
    refuse coordinates that are effectively unreachable (an object at 1e9 is
    invisible, unselectable, and un-deletable through the GUI — yet the tool
    would otherwise report success and echo the coordinates back).
    """
    if not (-canvas_width_cm <= centre_x <= 2 * canvas_width_cm) or not (
        -canvas_height_cm <= centre_y <= 2 * canvas_height_cm
    ):
        raise ValueError(
            f"Position ({centre_x:g}, {centre_y:g}) cm is too far outside the plan "
            f"to be reachable. This plan's canvas is "
            f"{canvas_width_cm:g} x {canvas_height_cm:g} cm, spanning (0, 0) to "
            f"({canvas_width_cm:g}, {canvas_height_cm:g}); positions up to one "
            "canvas beyond each edge are accepted."
        )


def require_sane_extent(
    extent: float,
    field: str,
    object_type: str,
    canvas_width_cm: float,
    canvas_height_cm: float,
) -> None:
    """Refuse an extent that is finite and positive but not plausible.

    See the ``_MAX_*`` constants for why each bound exists.
    """
    canvas_limit = _MAX_EXTENT_CANVAS_MULTIPLE * max(canvas_width_cm, canvas_height_cm)
    if extent > canvas_limit:
        raise ValueError(
            f"{field} {extent:g} cm is implausibly large for this plan, whose canvas "
            f"is {canvas_width_cm:g} x {canvas_height_cm:g} cm (limit "
            f"{canvas_limit:g} cm). Note all sizes are in CENTIMETRES — if you meant "
            "metres, multiply by 100."
        )
    if is_plant_type_name(object_type) and extent > _MAX_PLANT_DIAMETER_CM:
        raise ValueError(
            f"A plant's {field} may not exceed {_MAX_PLANT_DIAMETER_CM:g} cm "
            f"(got {extent:g} cm). Sizes are in CENTIMETRES."
        )


def build_create_dict(
    *,
    object_type: str,
    x: float,
    y: float,
    canvas_width_cm: float,
    canvas_height_cm: float,
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
        canvas_width_cm: The plan's canvas width, for the sanity bounds below.
        canvas_height_cm: The plan's canvas height, likewise. Both are required
            rather than optional so a caller cannot silently skip the bounds
            check (the same no-defaults reasoning as ``AgentProviders``).
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
            dimension that doesn't belong to the type's shape, a
            non-finite/non-positive extent, an implausibly large extent, or a
            position unreachably far outside the plan. Refusing beats silently
            creating something the caller didn't ask for (the D2.0 precedent).
    """
    if object_type not in CREATABLE_TYPE_NAMES:
        supported = ", ".join(sorted(CREATABLE_TYPE_NAMES))
        raise ValueError(
            f"create_object cannot create {object_type!r} yet. "
            f"Supported object types: {supported}."
        )

    centre_x = require_finite(x, "x")
    centre_y = require_finite(y, "y")
    canvas_w = require_positive(canvas_width_cm, "canvas_width_cm")
    canvas_h = require_positive(canvas_height_cm, "canvas_height_cm")
    _require_within_canvas(centre_x, centre_y, canvas_w, canvas_h)

    common: dict[str, Any] = {"object_type": object_type}
    if name:
        common["name"] = name

    if object_type in _CIRCLE_TYPE_NAMES:
        if width is not None or height is not None:
            raise ValueError(
                f"{object_type} is round — pass 'radius', not 'width'/'height'."
            )
        if radius is not None:
            resolved_radius = require_positive(radius, "radius")
        elif object_type in _DEFAULT_PLANT_DIAMETER_CM:
            resolved_radius = _DEFAULT_PLANT_DIAMETER_CM[object_type] / 2
        else:
            raise ValueError(f"{object_type} requires an explicit 'radius' in cm.")
        require_sane_extent(
            2 * resolved_radius, "diameter", object_type, canvas_w, canvas_h
        )
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
    resolved_width = require_positive(width, "width")
    resolved_height = require_positive(height, "height")
    require_sane_extent(resolved_width, "width", object_type, canvas_w, canvas_h)
    require_sane_extent(resolved_height, "height", object_type, canvas_w, canvas_h)
    return {
        **common,
        "type": "rectangle",
        # Serialised rectangles are anchor-based; the API speaks centres.
        "x": centre_x - resolved_width / 2,
        "y": centre_y - resolved_height / 2,
        "width": resolved_width,
        "height": resolved_height,
    }
