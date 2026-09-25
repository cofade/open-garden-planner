"""Qt-free validation for the Agent API's edit tools (US-D2.2/D2.3/D2.6).

The counterpart to :mod:`~open_garden_planner.agent_api.creates`: that module
validates and builds a *new* object, this one validates a change to an object
that already exists — ``resize_object`` / ``rotate_object`` (US-D2.2),
``set_species`` / ``set_parent_bed`` (US-D2.3), and the D2.6 scene-point and
vertex-index validation used by the low-level geometry escape hatches.

Kept import-light on the same terms as ``creates``: no PyQt6, so the object-type
name sets are inlined rather than importing ``core.object_types`` (which pulls
in ``QColor`` and the rest of Qt). ``tests/unit/test_agent_api_edits.py`` guards
every set below against drift from the real ``ObjectType`` definitions — the
inlining is only safe because that guard exists.

Shape validation deliberately lives *outside* this module. Whether an object can
be resized at all is a question about the Qt item backing it (rect-backed vs
vertex-backed), not about its type name, so it is answered by
``ui.canvas.geometry_apply.is_resizable_rect_like`` on the main thread; this
module validates the *numbers* and the *relationships*.
"""

from __future__ import annotations

import math

from open_garden_planner.agent_api.creates import (
    require_finite,
    require_positive,
    require_reachable_position,
    require_sane_extent,
)

# Soil-bearing parents — mirrors ObjectType ``SOIL_CONTAINER_TYPES`` (ADR-031).
_SOIL_CONTAINER_TYPE_NAMES = frozenset(
    {"GARDEN_BED", "RAISED_BED", "CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"}
)

#: Everything a plant may be a child of — mirrors ObjectType
#: ``PLANT_PARENT_TYPES`` (section 8.14 / ADR-017). Note the asymmetry that trips
#: people up: ``TRELLIS`` is a plant parent but is **not** a soil container, so a
#: plant on a trellis has a parent yet no soil readings. ``set_parent_bed``
#: accepts every name here; anything else is refused by name.
PLANT_PARENT_TYPE_NAMES: frozenset[str] = _SOIL_CONTAINER_TYPE_NAMES | {"TRELLIS"}

#: The smallest extent the GUI itself will produce: ``resize_handle`` clamps a
#: drag at ``MINIMUM_SIZE_CM`` and the properties panel's spin boxes start at
#: 1.0 cm. An agent must not be able to create geometry the user cannot then
#: grab — D2.1's ethos is to bound agent input *harder* than the GUI, never
#: softer, so this floor is applied to every resulting extent. Inlined (not
#: imported) to keep this module Qt-free; ``tests/unit/test_agent_api_edits.py``
#: asserts it still equals ``resize_handle.MINIMUM_SIZE_CM``.
MIN_EXTENT_CM = 1.0

#: Beyond this many degrees of absolute rotation a request is almost certainly a
#: unit mix-up (radians passed as degrees is the classic one). Angles are
#: normalised into [0, 360) anyway, so a legitimate caller never needs more —
#: this bound exists to make the mistake loud instead of silently plausible.
MAX_ABSOLUTE_ROTATION_DEG = 3600.0

#: Minimum vertex counts for the two vertex-backed geometry families. These
#: mirror the interactive mixins in ``resize_handle`` and are drift-guarded by
#: ``tests/unit/test_agent_api_edits.py``.
POLYGON_MIN_VERTICES = 3
POLYLINE_MIN_VERTICES = 2


def validate_scene_point(
    x: float,
    y: float,
    *,
    canvas_width_cm: float,
    canvas_height_cm: float,
) -> tuple[float, float]:
    """Validate a scene-frame point using the D2.1 reachability contract.

    One full canvas of staging slack is allowed on every side, matching
    ``create_object``. This rejects NaN/Infinity and effectively unreachable
    coordinates before they reach ``QPointF`` or ``QGraphicsItem.mapFromScene``.
    """
    resolved_x = require_finite(x, "x")
    resolved_y = require_finite(y, "y")
    resolved_canvas_width = require_positive(canvas_width_cm, "canvas_width_cm")
    resolved_canvas_height = require_positive(canvas_height_cm, "canvas_height_cm")
    require_reachable_position(
        resolved_x,
        resolved_y,
        resolved_canvas_width,
        resolved_canvas_height,
    )
    return resolved_x, resolved_y


def validate_vertex_index(
    index: int,
    *,
    vertex_count: int,
    operation: str,
    minimum_count: int | None = None,
) -> int:
    """Validate a polygon/polyline vertex index for ``set``/``add``/``delete``.

    ``add`` uses list-insertion semantics and therefore accepts ``vertex_count``
    as an append index. The other operations accept only existing vertices.
    ``minimum_count`` applies to deletion and prevents the raw item method's
    otherwise silent no-op from becoming a false-success tool response.
    """
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError(f"vertex index must be an integer, got {index!r}")
    if vertex_count < 0:
        raise ValueError(f"vertex_count cannot be negative, got {vertex_count}")
    if operation == "add":
        valid = 0 <= index <= vertex_count
        upper = vertex_count
    elif operation in {"set", "delete"}:
        valid = 0 <= index < vertex_count
        upper = vertex_count - 1
    else:
        raise ValueError(f"Unknown vertex operation {operation!r}")
    if not valid:
        raise ValueError(
            f"{operation} vertex index {index} is outside the valid range "
            f"0..{upper} for {vertex_count} vertices"
        )
    if operation == "delete" and minimum_count is not None and vertex_count <= minimum_count:
        raise ValueError(
            f"delete_vertex would leave {vertex_count - 1} vertices; this shape "
            f"requires at least {minimum_count}"
        )
    return index


def normalise_angle_deg(angle: float) -> float:
    """Fold ``angle`` into ``[0, 360)`` degrees.

    Applied to the *resulting* angle so ``rotate_object`` is idempotent in the
    absolute case (calling it twice with 90 leaves the item at 90, not 180) and
    accumulates predictably in the relative case.
    """
    return angle % 360.0


def validate_rotation(
    angle: float, *, relative: bool, current_angle: float
) -> float:
    """Validate a rotation request and return the resulting absolute angle.

    Args:
        angle: The requested angle in degrees.
        relative: When ``True``, ``angle`` is added to ``current_angle``;
            when ``False`` it replaces it.
        current_angle: The item's present rotation in degrees.

    Returns:
        The resulting angle, normalised into ``[0, 360)``.

    Raises:
        ValueError: If ``angle`` is not finite, or is so large it is more
            likely a unit mistake than an intent.
    """
    requested = require_finite(angle, "angle")
    if abs(requested) > MAX_ABSOLUTE_ROTATION_DEG:
        raise ValueError(
            f"angle {requested:g} is implausibly large. Rotation is in DEGREES "
            f"(0-360); values beyond +/-{MAX_ABSOLUTE_ROTATION_DEG:g} are "
            "refused as a likely unit mistake."
        )
    resulting = requested + current_angle if relative else requested
    if not math.isfinite(resulting):
        raise ValueError(f"The resulting angle is not finite: {resulting!r}")
    return normalise_angle_deg(resulting)


def validate_resize_request(
    *,
    object_type: str,
    is_round: bool,
    current_width: float,
    current_height: float,
    canvas_width_cm: float,
    canvas_height_cm: float,
    width: float | None = None,
    height: float | None = None,
    radius: float | None = None,
) -> tuple[float, float]:
    """Validate a resize request and return the resulting ``(width, height)`` in cm.

    The tool speaks **absolute target dimensions** in centimetres, the same
    vocabulary ``create_object`` uses. Either axis of a rectangular object may
    be given alone; the other keeps its current value.

    Args:
        object_type: The object's ``ObjectType`` name, used only in messages.
        is_round: Whether the object is circle-backed (takes ``radius``) rather
            than rectangle-backed (takes ``width``/``height``).
        current_width: The object's present width in cm.
        current_height: The object's present height in cm.
        canvas_width_cm: The plan's canvas width, for the sanity bounds.
        canvas_height_cm: The plan's canvas height, likewise.
        width: Requested width in cm — rectangular objects only.
        height: Requested height in cm — rectangular objects only.
        radius: Requested radius in cm — round objects only.

    Returns:
        ``(width, height)`` of the resulting object in cm. For a round object
        both are the diameter.

    Raises:
        ValueError: On a dimension that doesn't fit the object's shape, no
            dimension at all, a non-finite or non-positive extent, or an
            implausibly large one. Refusing beats silently resizing to
            something the caller didn't ask for (the D2.0 precedent).
    """
    if is_round:
        if width is not None or height is not None:
            raise ValueError(
                f"{object_type} is round — pass 'radius', not 'width'/'height'."
            )
        if radius is None:
            raise ValueError(
                f"{object_type} is round — pass 'radius' in cm to resize it."
            )
        resolved_radius = require_positive(radius, "radius")
        diameter = 2 * resolved_radius
        _require_min_extent(diameter, "diameter", object_type)
        require_sane_extent(
            diameter, "diameter", object_type, canvas_width_cm, canvas_height_cm
        )
        return diameter, diameter

    if radius is not None:
        raise ValueError(
            f"{object_type} is rectangular — pass 'width'/'height', not 'radius'."
        )
    if width is None and height is None:
        raise ValueError(
            f"{object_type} is rectangular — pass 'width' and/or 'height' in cm "
            "to resize it. Omit one to leave that axis unchanged."
        )
    resolved_width = (
        require_positive(width, "width") if width is not None else current_width
    )
    resolved_height = (
        require_positive(height, "height") if height is not None else current_height
    )
    _require_min_extent(resolved_width, "width", object_type)
    _require_min_extent(resolved_height, "height", object_type)
    require_sane_extent(
        resolved_width, "width", object_type, canvas_width_cm, canvas_height_cm
    )
    require_sane_extent(
        resolved_height, "height", object_type, canvas_width_cm, canvas_height_cm
    )
    return resolved_width, resolved_height


def _require_min_extent(extent: float, field: str, object_type: str) -> None:
    """Refuse an extent below the smallest one the GUI can produce."""
    if extent < MIN_EXTENT_CM:
        raise ValueError(
            f"{field} {extent:g} cm is below the minimum of {MIN_EXTENT_CM:g} cm "
            f"for {object_type}. An object smaller than that cannot be selected "
            "or resized in the app."
        )


def is_plant_parent_type_name(object_type: str) -> bool:
    """Whether ``object_type`` names something a plant can be a child of.

    Mirrors ``core.object_types.is_plant_parent_type`` without importing Qt.
    """
    return object_type in PLANT_PARENT_TYPE_NAMES


def require_plant_parent_type(object_type: str, bed_id: str) -> None:
    """Raise unless ``object_type`` can parent a plant.

    Refusing by name matters here: ``set_parent_bed`` pointed at a HOUSE is a
    plausible mistake for an agent that has only seen the object list, and a
    silent no-op would leave it believing the link exists.
    """
    if is_plant_parent_type_name(object_type):
        return
    supported = ", ".join(sorted(PLANT_PARENT_TYPE_NAMES))
    raise ValueError(
        f"{bed_id} is a {object_type}, which cannot hold plants. A plant's "
        f"parent must be one of: {supported}."
    )
