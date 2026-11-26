"""Qt-free bounding boxes over serialised ``.ogp`` objects.

Shared by the plan numeric boundary (which refuses a composed transform that
overflows) and the Agent API region queries. Coordinates are the plan's native
scene frame: centimetres, CAD Y-up. A shape's own ``rotation_angle`` is reported
separately (its box is the stored one); a group's box composes its members' own
angles, the group transform, and every nested group's compensating base
translation.
"""

from __future__ import annotations

import math
from typing import Any


def _anchor_point(obj: dict[str, Any]) -> tuple[float, float]:
    """Best-effort anchor for a shape with no width/height (point-like)."""
    if "center_x" in obj:
        return float(obj["center_x"]), float(obj.get("center_y", 0.0))
    if "target_x" in obj:  # callout
        return float(obj["target_x"]), float(obj.get("target_y", 0.0))
    if "x1" in obj:  # line segment (construction_line) — defensive
        return float(obj["x1"]), float(obj.get("y1", 0.0))
    if "x" in obj:  # group, journal_pin
        return float(obj["x"]), float(obj.get("y", 0.0))
    pos = obj.get("position")  # background_image
    if isinstance(pos, dict):
        return float(pos.get("x", 0.0)), float(pos.get("y", 0.0))
    return 0.0, 0.0


def object_bbox(obj: dict[str, Any]) -> tuple[float, float, float, float]:
    """Return ``(x, y, width, height)`` in scene cm for any serialised object.

    A shape's own ``rotation_angle`` is reported separately (its box is the
    stored one); a GROUP's box composes its members' own angles and the group
    transform, because otherwise a region query misses the real footprint.
    Members with a true curved outline (a circle, an ellipse) keep their exact
    extent instead of growing their bounding square.
    """
    if obj.get("children"):
        return _primitives_bbox(_group_primitives(obj))
    return _object_bbox_unrotated(obj)


def object_bounds_parts(
    obj: dict[str, Any],
) -> list[tuple[float, float, float, float]]:
    """Every transformed primitive's box, before the union hides a bad one.

    The plan boundary checks these individually: ``min``/``max`` on a union can
    discard a NaN member, so a finite aggregate must not be taken as proof that
    every child is finite (#1022 review).
    """
    if obj.get("children"):
        return [_primitive_bounds(primitive) for primitive in _group_primitives(obj)]
    return [_object_bbox_unrotated(obj)]


def _bbox_of(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return (x0, y0, x1 - x0, y1 - y0)


def _box_corners(
    box: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    x, y, w, h = box
    return [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]


def _rotate_points(
    points: list[tuple[float, float]],
    origin: tuple[float, float],
    angle: float,
) -> list[tuple[float, float]]:
    if not angle:
        return points
    ox, oy = origin
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return [
        (
            ox + (px - ox) * cos_a - (py - oy) * sin_a,
            oy + (px - ox) * sin_a + (py - oy) * cos_a,
        )
        for px, py in points
    ]


# A member primitive is one of
#   ("circle", cx, cy, r)
#   ("ellipse", cx, cy, semi_x, semi_y, angle_deg)
#   ("points", [(x, y), ...])
# Keeping the curved kinds symbolic is what stops a 45° turn from inflating a
# circle's box to its bounding square.
_Primitive = tuple[Any, ...]


def _leaf_primitives(obj: dict[str, Any]) -> list[_Primitive]:
    """A member's own geometry in the group's local frame, its turn applied."""
    if "radius" in obj and "center_x" in obj:  # circle, arc
        return [
            (
                "circle",
                float(obj["center_x"]),
                float(obj.get("center_y", 0.0)),
                float(obj["radius"]),
            )
        ]
    if "semi_x" in obj and "center_x" in obj:  # ellipse
        return [
            (
                "ellipse",
                float(obj["center_x"]),
                float(obj.get("center_y", 0.0)),
                float(obj["semi_x"]),
                float(obj["semi_y"]),
                float(obj.get("rotation_angle", obj.get("rotation", 0.0)) or 0.0),
            )
        ]
    box = _object_bbox_unrotated(obj)
    angle = float(obj.get("rotation_angle", obj.get("rotation", 0.0)) or 0.0)
    centre = (box[0] + box[2] / 2.0, box[1] + box[3] / 2.0)
    points = obj.get("points")
    if isinstance(points, list) and points:
        raw = [(float(point["x"]), float(point["y"])) for point in points]
    elif "anchors" in obj:
        raw = [
            (float(point["x"]), float(point["y"]))
            for point in (
                list(obj["anchors"])
                + list(obj.get("handles_in") or [])
                + list(obj.get("handles_out") or [])
            )
        ]
    elif "x1" in obj and "x2" in obj:  # construction_line segment
        raw = [
            (float(obj["x1"]), float(obj.get("y1", 0.0))),
            (float(obj["x2"]), float(obj.get("y2", 0.0))),
        ]
    else:
        raw = _box_corners(box)
    return [("points", _rotate_points(raw, centre, angle))]


def _primitive_bounds(primitive: _Primitive) -> tuple[float, float, float, float]:
    kind = primitive[0]
    if kind == "circle":
        _, cx, cy, r = primitive
        return (cx - r, cy - r, 2 * r, 2 * r)
    if kind == "ellipse":
        _, cx, cy, sx, sy, angle = primitive
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        hx = math.hypot(sx * cos_a, sy * sin_a)
        hy = math.hypot(sx * sin_a, sy * cos_a)
        return (cx - hx, cy - hy, 2 * hx, 2 * hy)
    points = primitive[1]
    if not all(math.isfinite(value) for point in points for value in point):
        return (math.nan, math.nan, math.nan, math.nan)
    return _bbox_of(points)


def _primitives_bbox(
    primitives: list[_Primitive],
) -> tuple[float, float, float, float]:
    if not primitives:
        return (0.0, 0.0, 0.0, 0.0)
    boxes = [_primitive_bounds(primitive) for primitive in primitives]
    if any(
        not all(math.isfinite(value) for value in box) for box in boxes
    ):
        return (math.nan, math.nan, math.nan, math.nan)
    x0 = min(box[0] for box in boxes)
    y0 = min(box[1] for box in boxes)
    x1 = max(box[0] + box[2] for box in boxes)
    y1 = max(box[1] + box[3] for box in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def _group_base_offset(obj: dict[str, Any]) -> tuple[float, float]:
    """The group's compensating base transform, which is translation-only."""
    base = obj.get("transform")
    if isinstance(base, dict):
        return float(base.get("dx", 0.0)), float(base.get("dy", 0.0))
    return 0.0, 0.0


def _transform_primitives(
    primitives: list[_Primitive],
    origin: tuple[float, float],
    angle: float,
    base_dx: float,
    base_dy: float,
    dx: float,
    dy: float,
) -> list[_Primitive]:
    moved: list[_Primitive] = []
    for primitive in primitives:
        kind = primitive[0]
        shift_x = base_dx + dx
        shift_y = base_dy + dy
        if kind == "points":
            points = _rotate_points(primitive[1], origin, angle)
            moved.append(
                ("points", [(px + shift_x, py + shift_y) for px, py in points])
            )
        elif kind == "circle":
            _, cx, cy, r = primitive
            centre = _rotate_points([(cx, cy)], origin, angle)[0]
            moved.append(("circle", centre[0] + shift_x, centre[1] + shift_y, r))
        else:  # ellipse
            _, cx, cy, sx, sy, own_angle = primitive
            centre = _rotate_points([(cx, cy)], origin, angle)[0]
            moved.append(
                (
                    "ellipse",
                    centre[0] + shift_x,
                    centre[1] + shift_y,
                    sx,
                    sy,
                    own_angle + angle,
                )
            )
    return moved


def _group_primitives(obj: dict[str, Any]) -> list[_Primitive]:
    """The group's member primitives in its PARENT frame, every turn composed.

    Children serialise in the group's local frame. A nested group is recursed
    (its own turn and translation included) rather than boxed to an
    axis-aligned rectangle first: two opposing turns must cancel instead of
    compounding their bounding boxes. Qt's compensating base translation on a
    regrouped child is applied after its rotation, before the group's x/y.
    """
    primitives: list[_Primitive] = []
    for child in obj.get("children") or []:
        if child.get("children"):
            primitives.extend(_group_primitives(child))
        else:
            primitives.extend(_leaf_primitives(child))
    angle = float(obj.get("rotation", 0.0) or 0.0)
    group_origin = obj.get("transform_origin")
    if isinstance(group_origin, dict):
        pivot = (
            float(group_origin.get("x", 0.0)),
            float(group_origin.get("y", 0.0)),
        )
    elif isinstance(obj.get("smart_symbol"), dict):
        # A pre-#1009 symbol had no centre pivot; the loader rotates it about
        # its local (0, 0). The numeric gate must share that rule (#1022).
        pivot = (0.0, 0.0)
    else:
        bx, by, bw, bh = _primitives_bbox(primitives)
        pivot = (bx + bw / 2.0, by + bh / 2.0)
    base_dx, base_dy = _group_base_offset(obj)
    return _transform_primitives(
        primitives,
        pivot,
        angle,
        base_dx,
        base_dy,
        float(obj.get("x", 0.0)),
        float(obj.get("y", 0.0)),
    )


def _object_bbox_unrotated(
    obj: dict[str, Any],
) -> tuple[float, float, float, float]:
    """The axis-aligned box of an ungrouped *obj* before its own angle."""
    if "width" in obj and "x" in obj:  # rectangle (group has x but no width)
        return (
            float(obj["x"]),
            float(obj["y"]),
            float(obj.get("width", 0.0)),
            float(obj.get("height", 0.0)),
        )
    if "radius" in obj and "center_x" in obj:  # circle, arc
        cx, cy, r = float(obj["center_x"]), float(obj["center_y"]), float(obj["radius"])
        return (cx - r, cy - r, 2 * r, 2 * r)
    if "semi_x" in obj and "center_x" in obj:  # ellipse
        cx, cy = float(obj["center_x"]), float(obj["center_y"])
        sx, sy = float(obj["semi_x"]), float(obj["semi_y"])
        return (cx - sx, cy - sy, 2 * sx, 2 * sy)
    if "target_x" in obj and ("box_dx" in obj or "box_dy" in obj):
        # Callout: the arrow tip plus its serialized box. The live item's own
        # turn uses the bounding box centre, so a saved bounds block is the
        # pivot-exact form; older files fall back to the leader segment.
        tx, ty = float(obj["target_x"]), float(obj.get("target_y", 0.0))
        bounds = obj.get("bounds")
        if isinstance(bounds, dict):
            return (
                tx + float(bounds.get("x", 0.0)),
                ty + float(bounds.get("y", 0.0)),
                float(bounds.get("width", 0.0)),
                float(bounds.get("height", 0.0)),
            )
        bx = tx + float(obj.get("box_dx", 0.0))
        by = ty + float(obj.get("box_dy", 0.0))
        return (min(tx, bx), min(ty, by), abs(bx - tx), abs(by - ty))
    if "x1" in obj and "x2" in obj:  # construction_line segment
        x1, y1 = float(obj["x1"]), float(obj.get("y1", 0.0))
        x2, y2 = float(obj["x2"]), float(obj.get("y2", 0.0))
        return (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
    points = obj.get("points")  # polyline / polygon
    if points is None and "anchors" in obj:  # bezier — bound by the control hull
        points = (
            list(obj["anchors"])
            + list(obj.get("handles_in") or [])
            + list(obj.get("handles_out") or [])
        )
    if points:
        xs = [float(p["x"]) for p in points]
        ys = [float(p["y"]) for p in points]
        return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    ax, ay = _anchor_point(obj)
    return (ax, ay, 0.0, 0.0)
