"""Qt-free validation + ``.ogp``-dict building for ``create_object`` (US-D2.1/D2.5).

Kept import-light like :mod:`~open_garden_planner.agent_api.mapping`: no PyQt6.
The object-type name sets are inlined rather than importing
``core.object_types`` (which pulls in ``QColor`` and the rest of Qt);
``tests/unit/test_agent_api_creates.py`` guards every set against drift from the
real ``ObjectType`` definitions — including the US-D2.5 whole-roster guard:
creatable ∪ excluded must equal every ``ObjectType`` member, so a NEW enum
member fails the tests until someone decides whether an agent may create it.

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
this conversion is frame-agnostic and cannot introduce a Y-flip bug. Polygons
and polylines take their vertices as ``points`` in the SAME Y-up scene frame —
no conversion at all (the loader's polygon/polyline branches store scene
coordinates directly), which is what makes the #267-style Y-flip impossible
here and numerically pinnable in the tests.
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

# --- Shape families (US-D2.5) -----------------------------------------------
#
# Each creatable type gets exactly ONE canonical shape — the shape the GUI's
# own tool registration builds it as (``CanvasView._setup_tools`` pairs each
# ObjectType with a RectangleTool/CircleTool/EllipseTool/PolygonTool/
# PolylineTool). Types the GUI accepts in several shapes keep the toolbar's
# choice: HOUSE & co. are PolygonTool types (a rectangular footprint is still
# expressible via the centre+width/height convenience below), POND_POOL is a
# PolygonTool type, BBQ_GRILL is a CircleTool type, and GARDEN_BED stays
# rectangle-only (D2.1's documented scope decision). The drift guard asserts
# every set is a subset of ``get_valid_types_for_shape`` for its shape.

#: Circle-based: plants, the round soil container, and the round furniture /
#: infrastructure / generic circle (GUI: CircleTool registrations).
_CIRCLE_TYPE_NAMES = _PLANT_TYPE_NAMES | {
    "CONTAINER_ROUND",
    "GENERIC_CIRCLE",
    "TABLE_ROUND",
    "PARASOL",
    "BBQ_GRILL",
    "FIRE_PIT",
    "PLANTER_POT",
    "TRAMPOLINE",
    "RAIN_BARREL",
    "WATER_TAP",
    "BIRD_BATH",
}

#: Rectangle-based: the D2.1 soil containers plus generic rectangle,
#: rectangular furniture, garden infrastructure, and TRELLIS (GUI:
#: RectangleTool registrations). HEDGE_SECTION is NOT here — see
#: ``EXCLUDED_TYPE_REASONS`` (the loader migrates it to HEDGE_POLYGON).
_RECT_TYPE_NAMES = frozenset(
    {
        "GARDEN_BED",
        "RAISED_BED",
        "CONTAINER",
        "WALL_PLANTER",
        "GENERIC_RECTANGLE",
        "TABLE_RECTANGULAR",
        "CHAIR",
        "BENCH",
        "LOUNGER",
        "SANDBOX",
        "HOT_TUB",
        "SWING",
        "PICNIC_TABLE",
        "HAMMOCK",
        "COMPOST_BIN",
        "COLD_FRAME",
        "TOOL_SHED",
        "WHEELBARROW",
        "PERGOLA",
        "TRELLIS",
    }
)

#: Ellipse-based (GUI: EllipseTool). GARDEN_BED is also ellipse-valid in the
#: GUI but stays rectangle-only here, as in D2.1.
_ELLIPSE_TYPE_NAMES = frozenset({"GENERIC_ELLIPSE"})

#: Polygon-based structures (GUI: PolygonTool registrations). A HOUSE created
#: here gets its linked ROOF_RIDGE built by the caller (application.py) via
#: ``core.roof_ridge`` — the same geometry the interactive polygon tool uses —
#: inside the SAME single undo step.
_POLYGON_TYPE_NAMES = frozenset(
    {
        "GENERIC_POLYGON",
        "HOUSE",
        "GARAGE_SHED",
        "TERRACE_PATIO",
        "DRIVEWAY",
        "POND_POOL",
        "GREENHOUSE",
        "LAWN",
        "HEDGE_POLYGON",
    }
)

#: Polyline-based (GUI: PolylineTool registrations). Note polylines have NO
#: width/thickness parameter anywhere in the app — visual thickness comes from
#: the PathFenceStyle presets (or the pen width), not a dimension.
_POLYLINE_TYPE_NAMES = frozenset({"FENCE", "WALL", "PATH"})

#: Text callout with a leader line (GUI: CalloutTool).
_CALLOUT_TYPE_NAMES = frozenset({"GENERIC_CALLOUT"})

#: Types refused BY NAME, with the reason the error message must state.
#: The whole-roster drift guard asserts creatable ∪ excluded == ObjectType.
EXCLUDED_TYPE_REASONS: dict[str, str] = {
    "ROOF_RIDGE": (
        "roof ridges are auto-created together with a HOUSE — create the house "
        "(create_object HOUSE) and its ridge is built and linked in the same "
        "undo step; a directly created ridge would have no house"
    ),
    "GARDEN_JOURNAL_PIN": (
        "journal pins keep their note record in the project data, not just the "
        "scene — the write tools don't support them (consistent with "
        "delete_object/move_object)"
    ),
    "GENERIC_TEXT": (
        "text annotations have no serialization support in the app yet (a "
        "TextItem does not survive save/load), so creating one would build an "
        "object the plan silently loses — tracked as a follow-up issue"
    ),
    "HEDGE_SECTION": (
        "legacy type — the app migrates HEDGE_SECTION rectangles to "
        "HEDGE_POLYGON polygons on load, so creating one would not round-trip; "
        "create a HEDGE_POLYGON (from points, or from a rectangular footprint) "
        "instead"
    ),
}

#: Every object type ``create_object`` can build. D2.1 shipped plants + soil
#: containers; US-D2.5 widens it to the full roster minus
#: :data:`EXCLUDED_TYPE_REASONS`.
CREATABLE_TYPE_NAMES: frozenset[str] = (
    _CIRCLE_TYPE_NAMES
    | _RECT_TYPE_NAMES
    | _ELLIPSE_TYPE_NAMES
    | _POLYGON_TYPE_NAMES
    | _POLYLINE_TYPE_NAMES
    | _CALLOUT_TYPE_NAMES
)

# Default plant footprint when the caller gives no radius — the SAME numbers the
# gallery-drop path uses (``CanvasView`` drop handler ``size_map``), as diameters.
_DEFAULT_PLANT_DIAMETER_CM: dict[str, float] = {
    "TREE": 200.0,
    "SHRUB": 100.0,
    "PERENNIAL": 60.0,
}

# Callout text-box offset from the arrow tip when the caller gives none — the
# CalloutItem/GUI CalloutTool default (callout_item.from_dict's own fallbacks).
_DEFAULT_CALLOUT_BOX_DX = 80.0
_DEFAULT_CALLOUT_BOX_DY = -60.0

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

# Vertex-count bound for polygon/polyline creation. The GUI builds these one
# click at a time; an agent could submit an arbitrarily huge list that the
# scene would then re-layout on every repaint. 1000 vertices is far beyond any
# real garden outline (the D2.1 ethos: bound agent input harder than the GUI).
_MAX_POINTS = 1000

#: Minimum point counts — the loader's own thresholds (``_deserialize_item_core``
#: builds a polygon only with >= 3 points and a polyline only with >= 2;
#: anything fewer silently yields None). Inlined; the drift guard pins them
#: against the loader's behaviour.
_MIN_POLYGON_POINTS = 3
_MIN_POLYLINE_POINTS = 2


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


def _require_centre(
    x: float | None, y: float | None, object_type: str
) -> tuple[float, float]:
    """Validate a required centre pair; refuse a half-given one loudly."""
    if x is None and y is None:
        raise ValueError(
            f"{object_type} needs its centre position — pass 'x' and 'y' in "
            "scene cm (CAD Y-up: a larger y is further north)."
        )
    if x is None or y is None:
        raise ValueError(
            f"{object_type} needs BOTH 'x' and 'y' (got only one of them)."
        )
    return require_finite(x, "x"), require_finite(y, "y")


def _validate_points(
    points: Any,
    *,
    object_type: str,
    min_count: int,
    canvas_width_cm: float,
    canvas_height_cm: float,
    closed: bool,
) -> list[tuple[float, float]]:
    """Validate a ``points`` vertex list and return it as ``(x, y)`` tuples.

    Points are scene cm in the SAME CAD Y-up frame every read tool reports and
    every other create_object parameter uses — they are passed straight through
    to the loader's polygon/polyline dict (which stores scene coordinates), so
    there is no frame conversion here that could flip.

    ``closed`` selects the degeneracy rule: a closed polygon whose bounding box
    has zero width or height encloses no area (the loader would build an
    invisible sliver); an open polyline may legitimately be axis-aligned
    (a due-east fence has zero bbox height) and is refused only when EVERY
    point is identical.
    """
    if not isinstance(points, (list, tuple)):
        raise ValueError(
            f"{object_type} is built from vertices — pass 'points' as a list of "
            f"[x, y] pairs in scene cm, got {type(points).__name__}."
        )
    if len(points) < min_count:
        raise ValueError(
            f"{object_type} needs at least {min_count} points, got {len(points)}."
        )
    if len(points) > _MAX_POINTS:
        raise ValueError(
            f"{object_type} was given {len(points)} points; the limit is "
            f"{_MAX_POINTS}."
        )
    validated: list[tuple[float, float]] = []
    for index, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(
                f"points[{index}] must be an [x, y] pair in scene cm, got "
                f"{point!r}."
            )
        px = require_finite(point[0], f"points[{index}][0]")
        py = require_finite(point[1], f"points[{index}][1]")
        _require_within_canvas(px, py, canvas_width_cm, canvas_height_cm)
        validated.append((px, py))

    xs = [p[0] for p in validated]
    ys = [p[1] for p in validated]
    bbox_w = max(xs) - min(xs)
    bbox_h = max(ys) - min(ys)
    require_sane_extent(
        max(bbox_w, bbox_h), "point spread", object_type, canvas_width_cm, canvas_height_cm
    )
    if closed and (bbox_w <= 0.0 or bbox_h <= 0.0):
        raise ValueError(
            f"{object_type}'s points enclose no area (their bounding box is "
            f"{bbox_w:g} x {bbox_h:g} cm). A polygon needs at least 3 points "
            "spanning both axes."
        )
    if not closed and bbox_w <= 0.0 and bbox_h <= 0.0:
        raise ValueError(
            f"{object_type}'s points are all identical — a polyline needs at "
            "least two distinct points."
        )
    return validated


def _rect_footprint_points(
    centre_x: float, centre_y: float, width: float, height: float
) -> list[tuple[float, float]]:
    """Expand a centre + width/height rectangular footprint to four points.

    The convenience for "a 10 x 8 m house": the same four vertices, in the
    same cyclic order, as passing them explicitly (pinned by test), and the
    same order the loader's own HEDGE_SECTION→HEDGE_POLYGON migration uses
    (anchor corner first, then +x, then +x+y, then +y).
    """
    x0 = centre_x - width / 2
    y0 = centre_y - height / 2
    return [
        (x0, y0),
        (x0 + width, y0),
        (x0 + width, y0 + height),
        (x0, y0 + height),
    ]


def build_create_dict(
    *,
    object_type: str,
    x: float | None = None,
    y: float | None = None,
    canvas_width_cm: float,
    canvas_height_cm: float,
    width: float | None = None,
    height: float | None = None,
    radius: float | None = None,
    points: Any = None,
    text: str | None = None,
    box_dx: float | None = None,
    box_dy: float | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Validate creation parameters and build an ``.ogp``-shaped item dict.

    One canonical shape per type (see the family sets above); the parameters
    that fit that shape are required and every other parameter is REFUSED —
    refusing beats silently creating something the caller didn't ask for (the
    D2.0/D2.1 precedent).

    Args:
        object_type: An ``ObjectType`` name from :data:`CREATABLE_TYPE_NAMES`.
        x: Centre X in scene cm — required for circle/rectangle/ellipse types;
            for polygon types required only with the width/height rectangular-
            footprint convenience; refused for polyline types (their ``points``
            carry their own coordinates). For GENERIC_CALLOUT this is the
            arrow-TIP (leader target) position, not a centre.
        y: Centre Y in scene cm (Y-up: a larger y is further north). Same rules
            as ``x``.
        canvas_width_cm: The plan's canvas width, for the sanity bounds below.
        canvas_height_cm: The plan's canvas height, likewise. Both are required
            rather than optional so a caller cannot silently skip the bounds
            check (the same no-defaults reasoning as ``AgentProviders``).
        width: Width in cm — required for rectangle/ellipse types, part of the
            polygon rectangular-footprint convenience, refused elsewhere.
        height: Height in cm — same rule as ``width``.
        radius: Radius in cm — for circle-based types. Optional for plants
            (they fall back to the GUI's default footprint); required for every
            other circle type, which has no meaningful default size.
        points: Vertex list ``[[x, y], ...]`` in scene cm (Y-up) — required for
            polyline types; for polygon types either this OR the centre +
            width/height convenience, never both.
        text: Callout text — required for GENERIC_CALLOUT, refused elsewhere.
        box_dx: Callout text-box offset from the arrow tip, X (default 80 cm).
        box_dy: Callout text-box offset from the arrow tip, Y (default -60 cm).
        name: Optional display name.

    Returns:
        A dict accepted by ``ProjectManager._deserialize_item_core``.

    Raises:
        ValueError: On an unsupported or excluded type, a missing required
            parameter, a parameter that doesn't belong to the type's shape, a
            non-finite/non-positive extent, an implausibly large extent, a
            degenerate vertex list, too many vertices, or a position
            unreachably far outside the plan.
    """
    if object_type in EXCLUDED_TYPE_REASONS:
        raise ValueError(
            f"create_object cannot create {object_type!r}: "
            f"{EXCLUDED_TYPE_REASONS[object_type]}."
        )
    if object_type not in CREATABLE_TYPE_NAMES:
        raise ValueError(
            f"create_object cannot create {object_type!r} — it is not a known "
            "creatable object type. Call list_creatable_types for the full "
            "roster with each type's shape and required parameters."
        )
    if points is not None and object_type not in (
        _POLYGON_TYPE_NAMES | _POLYLINE_TYPE_NAMES
    ):
        raise ValueError(
            f"{object_type} is not built from vertices — pass the dimensions "
            "for its shape instead ('points' is for polygon and polyline "
            "types). Use list_creatable_types to see each type's parameters."
        )
    if text is not None and object_type not in _CALLOUT_TYPE_NAMES:
        raise ValueError(
            f"{object_type} has no text — 'text' belongs to GENERIC_CALLOUT "
            "only."
        )
    if (box_dx is not None or box_dy is not None) and object_type not in (
        _CALLOUT_TYPE_NAMES
    ):
        raise ValueError(
            f"'box_dx'/'box_dy' belong to GENERIC_CALLOUT only, not to "
            f"{object_type}."
        )

    canvas_w = require_positive(canvas_width_cm, "canvas_width_cm")
    canvas_h = require_positive(canvas_height_cm, "canvas_height_cm")

    common: dict[str, Any] = {"object_type": object_type}
    if name:
        common["name"] = name

    if object_type in _CIRCLE_TYPE_NAMES:
        return _build_circle_dict(
            common,
            object_type=object_type,
            x=x,
            y=y,
            width=width,
            height=height,
            radius=radius,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
        )

    if object_type in _RECT_TYPE_NAMES:
        centre_x, centre_y = _require_centre(x, y, object_type)
        _require_within_canvas(centre_x, centre_y, canvas_w, canvas_h)
        if radius is not None:
            raise ValueError(
                f"{object_type} is rectangular — pass 'width'/'height', not "
                "'radius'."
            )
        if width is None or height is None:
            raise ValueError(
                f"{object_type} requires both 'width' and 'height' in cm."
            )
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

    if object_type in _ELLIPSE_TYPE_NAMES:
        centre_x, centre_y = _require_centre(x, y, object_type)
        _require_within_canvas(centre_x, centre_y, canvas_w, canvas_h)
        if radius is not None:
            raise ValueError(
                f"{object_type} takes a bounding box — pass 'width'/'height' "
                "(the full east-west / north-south extents), not 'radius'. "
                "For a round object use GENERIC_CIRCLE."
            )
        if width is None or height is None:
            raise ValueError(
                f"{object_type} requires both 'width' and 'height' in cm (the "
                "bounding box the ellipse is drawn inside)."
            )
        resolved_width = require_positive(width, "width")
        resolved_height = require_positive(height, "height")
        require_sane_extent(resolved_width, "width", object_type, canvas_w, canvas_h)
        require_sane_extent(resolved_height, "height", object_type, canvas_w, canvas_h)
        return {
            **common,
            "type": "ellipse",
            # Serialised ellipses are centre + semi-axes.
            "center_x": centre_x,
            "center_y": centre_y,
            "semi_x": resolved_width / 2,
            "semi_y": resolved_height / 2,
        }

    if object_type in _POLYGON_TYPE_NAMES:
        return _build_polygon_dict(
            common,
            object_type=object_type,
            x=x,
            y=y,
            width=width,
            height=height,
            radius=radius,
            points=points,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
        )

    if object_type in _POLYLINE_TYPE_NAMES:
        if x is not None or y is not None:
            raise ValueError(
                f"{object_type} is an open vertex-built shape — pass 'points' "
                "only; 'x'/'y' would be ambiguous next to a vertex list (and "
                "the rectangular-footprint convenience is for closed polygon "
                "types)."
            )
        if width is not None or height is not None or radius is not None:
            raise ValueError(
                f"{object_type} has no width/height/radius — polylines are "
                "built from 'points' only. A fence or path has no thickness "
                "parameter in the app; its visual style comes from the "
                "path/fence style presets."
            )
        if points is None:
            raise ValueError(
                f"{object_type} requires 'points': at least "
                f"{_MIN_POLYLINE_POINTS} [x, y] pairs in scene cm."
            )
        validated = _validate_points(
            points,
            object_type=object_type,
            min_count=_MIN_POLYLINE_POINTS,
            canvas_width_cm=canvas_w,
            canvas_height_cm=canvas_h,
            closed=False,
        )
        return {
            **common,
            "type": "polyline",
            "points": [{"x": px, "y": py} for px, py in validated],
        }

    # _CALLOUT_TYPE_NAMES — the only remaining creatable family.
    tip_x, tip_y = _require_centre(x, y, object_type)
    _require_within_canvas(tip_x, tip_y, canvas_w, canvas_h)
    if width is not None or height is not None or radius is not None:
        raise ValueError(
            f"{object_type} has no width/height/radius — pass 'text' plus the "
            "arrow-tip position ('x'/'y') and, optionally, the text-box offset "
            "('box_dx'/'box_dy')."
        )
    if text is None or not str(text).strip():
        raise ValueError(
            f"{object_type} requires non-empty 'text' — a callout without text "
            "has nothing to show."
        )
    resolved_dx = (
        require_finite(box_dx, "box_dx")
        if box_dx is not None
        else _DEFAULT_CALLOUT_BOX_DX
    )
    resolved_dy = (
        require_finite(box_dy, "box_dy")
        if box_dy is not None
        else _DEFAULT_CALLOUT_BOX_DY
    )
    return {
        **common,
        "type": "callout",
        # 'target_*' is the serialized name for the arrow tip (the leader-line
        # target); 'box_d*' offsets the text box from it (CalloutItem.to_dict).
        "target_x": tip_x,
        "target_y": tip_y,
        "box_dx": resolved_dx,
        "box_dy": resolved_dy,
        "content": str(text),
    }


def _build_circle_dict(
    common: dict[str, Any],
    *,
    object_type: str,
    x: float | None,
    y: float | None,
    width: float | None,
    height: float | None,
    radius: float | None,
    canvas_w: float,
    canvas_h: float,
) -> dict[str, Any]:
    """The circle family: plants (default footprint), containers, furniture."""
    centre_x, centre_y = _require_centre(x, y, object_type)
    _require_within_canvas(centre_x, centre_y, canvas_w, canvas_h)
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
    require_sane_extent(2 * resolved_radius, "diameter", object_type, canvas_w, canvas_h)
    return {
        **common,
        "type": "circle",
        "center_x": centre_x,
        "center_y": centre_y,
        "radius": resolved_radius,
    }


def _build_polygon_dict(
    common: dict[str, Any],
    *,
    object_type: str,
    x: float | None,
    y: float | None,
    width: float | None,
    height: float | None,
    radius: float | None,
    points: Any,
    canvas_w: float,
    canvas_h: float,
) -> dict[str, Any]:
    """The polygon family: explicit vertices OR a rectangular footprint.

    Exactly one of the two phrasings must be given — both together is refused
    rather than silently preferring one (a half-specified footprint usually
    means the caller mixed up the vocabularies).
    """
    if radius is not None:
        raise ValueError(
            f"{object_type} is a polygon — pass 'points' (a vertex list) or "
            "'x'/'y' + 'width'/'height' (a rectangular footprint), not "
            "'radius'."
        )
    footprint = x is not None or y is not None or width is not None or height is not None
    if points is not None and footprint:
        raise ValueError(
            f"{object_type}: pass EITHER 'points' OR 'x'/'y' + 'width'/"
            "'height' — not both. The rectangular-footprint form is a "
            "convenience that expands to four points around the centre."
        )
    if points is not None:
        validated = _validate_points(
            points,
            object_type=object_type,
            min_count=_MIN_POLYGON_POINTS,
            canvas_width_cm=canvas_w,
            canvas_height_cm=canvas_h,
            closed=True,
        )
    elif footprint:
        centre_x, centre_y = _require_centre(x, y, object_type)
        _require_within_canvas(centre_x, centre_y, canvas_w, canvas_h)
        if width is None or height is None:
            raise ValueError(
                f"{object_type}'s rectangular-footprint form requires BOTH "
                "'width' and 'height' in cm (or pass an explicit 'points' "
                "vertex list instead)."
            )
        resolved_width = require_positive(width, "width")
        resolved_height = require_positive(height, "height")
        require_sane_extent(resolved_width, "width", object_type, canvas_w, canvas_h)
        require_sane_extent(resolved_height, "height", object_type, canvas_w, canvas_h)
        validated = _rect_footprint_points(
            centre_x, centre_y, resolved_width, resolved_height
        )
    else:
        raise ValueError(
            f"{object_type} requires either 'points' (at least "
            f"{_MIN_POLYGON_POINTS} [x, y] pairs in scene cm) or a rectangular "
            "footprint ('x'/'y' centre + 'width'/'height')."
        )
    return {
        **common,
        "type": "polygon",
        "points": [{"x": px, "y": py} for px, py in validated],
    }


# --- discovery (US-D2.5) ------------------------------------------------------


def _family_entry(
    object_type: str,
    shape: str,
    required: list[str],
    optional: list[str],
    notes: str = "",
) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "creatable": True,
        "shape": shape,
        "required": required,
        "optional": optional,
        "notes": notes,
        "reason": None,
    }


def list_creatable_types() -> list[dict[str, Any]]:
    """The full ``ObjectType`` roster as machine-readable creation specs.

    Backs the ``list_creatable_types`` read tool so an agent can DISCOVER the
    contract instead of parsing ``create_object``'s prose docstring (which at
    ~48 types would be unusable). Every type appears exactly once: creatable
    ones with their shape + parameters, excluded ones with ``creatable=False``
    and the reason. The whole-roster drift guard in
    ``tests/unit/test_agent_api_creates.py`` keeps this list equal to the real
    ``ObjectType`` enum.
    """
    entries: list[dict[str, Any]] = []

    for name in sorted(_CIRCLE_TYPE_NAMES):
        if name in _PLANT_TYPE_NAMES:
            entries.append(
                _family_entry(
                    name,
                    "circle",
                    ["x", "y"],
                    ["radius", "name", "species"],
                    notes=(
                        "Plant. 'radius' omits to the app's default footprint "
                        f"(diameter {_DEFAULT_PLANT_DIAMETER_CM[name]:g} cm). "
                        "Created inside a bed/container/trellis it links to it "
                        "automatically."
                    ),
                )
            )
        else:
            notes = "Round object; 'radius' required."
            if name == "CONTAINER_ROUND":
                notes += " Soil container: plants created inside it link to it."
            entries.append(
                _family_entry(name, "circle", ["x", "y", "radius"], ["name"], notes)
            )

    for name in sorted(_RECT_TYPE_NAMES):
        notes = "Rectangular object; 'x'/'y' is the CENTRE."
        if name in _SOIL_CONTAINER_TYPE_NAMES:
            notes = "Rectangular soil container: plants created inside it link to it."
        elif name == "TRELLIS":
            notes = (
                "Plant parent WITHOUT soil: plants created inside it link to "
                "it, but it carries no soil readings."
            )
        entries.append(
            _family_entry(
                name, "rectangle", ["x", "y", "width", "height"], ["name"], notes
            )
        )

    for name in sorted(_ELLIPSE_TYPE_NAMES):
        entries.append(
            _family_entry(
                name,
                "ellipse",
                ["x", "y", "width", "height"],
                ["name"],
                notes=(
                    "'width'/'height' are the full east-west / north-south "
                    "extents of the bounding box the ellipse fills."
                ),
            )
        )

    for name in sorted(_POLYGON_TYPE_NAMES):
        notes = (
            "Closed structure built from vertices: pass 'points' (>= 3 [x, y] "
            "pairs, scene cm) OR a rectangular footprint ('x'/'y' centre + "
            "'width'/'height', expanded to four points)."
        )
        if name == "HOUSE":
            notes += (
                " A HOUSE automatically gets its linked ROOF_RIDGE polyline in "
                "the same single undo step (reported as linked_items_created)."
            )
        entries.append(
            _family_entry(name, "polygon", ["points OR x+y+width+height"], ["name"], notes)
        )

    for name in sorted(_POLYLINE_TYPE_NAMES):
        entries.append(
            _family_entry(
                name,
                "polyline",
                ["points"],
                ["name"],
                notes=(
                    "Open linear feature: >= 2 [x, y] pairs, scene cm. No "
                    "width/height/radius — a fence/path has no thickness "
                    "parameter in the app."
                ),
            )
        )

    for name in sorted(_CALLOUT_TYPE_NAMES):
        entries.append(
            _family_entry(
                name,
                "callout",
                ["x", "y", "text"],
                ["box_dx", "box_dy", "name"],
                notes=(
                    "'x'/'y' is the arrow TIP (the leader-line target); the "
                    "text box sits at tip + (box_dx, box_dy), default "
                    f"({_DEFAULT_CALLOUT_BOX_DX:g}, {_DEFAULT_CALLOUT_BOX_DY:g}) cm."
                ),
            )
        )

    for name, reason in sorted(EXCLUDED_TYPE_REASONS.items()):
        entries.append(
            {
                "object_type": name,
                "creatable": False,
                "shape": None,
                "required": [],
                "optional": [],
                "notes": "",
                "reason": reason,
            }
        )

    return entries
