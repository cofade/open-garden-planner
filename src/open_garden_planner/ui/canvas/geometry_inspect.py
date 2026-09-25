"""Live, Qt-side geometry inspection for the Agent API (US-D2.6).

This module deliberately reads the **live** graphics item instead of mapping the
raw ``.ogp`` serializer. Polygon and polyline serializer points are stored before
item rotation; ``get_geometry`` promises where vertices are now, so every point
must pass through ``mapToScene``. The result remains plain data and is validated
by :mod:`open_garden_planner.agent_api.schema` at the MCP boundary.

Qt-touching and main-thread only. Application code reaches it through
``MainThreadBridge`` just like the other Agent API scene providers.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.ui.canvas.geometry_apply import (
    is_vertex_editable,
    scene_vertex_positions,
)


def _point(point: QPointF) -> dict[str, float]:
    return {"x_cm": float(point.x()), "y_cm": float(point.y())}


def _anchor(anchor: Any) -> dict[str, Any]:
    return {
        "item_id": str(anchor.item_id),
        "anchor_type": anchor.anchor_type.name,
        "anchor_index": int(anchor.anchor_index),
    }


def _constraint(constraint: Any) -> dict[str, Any]:
    return {
        "constraint_id": str(constraint.constraint_id),
        "constraint_type": constraint.constraint_type.name,
        "anchor_a": _anchor(constraint.anchor_a),
        "anchor_b": _anchor(constraint.anchor_b),
        "anchor_c": (
            _anchor(constraint.anchor_c) if constraint.anchor_c is not None else None
        ),
        "target_distance": float(constraint.target_distance),
        "target_x": (
            float(constraint.target_x) if constraint.target_x is not None else None
        ),
        "target_y": (
            float(constraint.target_y) if constraint.target_y is not None else None
        ),
        "visible": bool(constraint.visible),
    }


def _geometry_type(item: QGraphicsItem) -> str:
    from open_garden_planner.ui.canvas.items import (
        ArcItem,
        BackgroundImageItem,
        BezierItem,
        CalloutItem,
        CircleItem,
        ConstructionCircleItem,
        ConstructionLineItem,
        EllipseItem,
        GroupItem,
        JournalPinItem,
        PolygonItem,
        PolylineItem,
        RectangleItem,
        SmartSymbolItem,
        TextItem,
    )

    if isinstance(item, ConstructionLineItem):
        return "construction_line"
    if isinstance(item, ConstructionCircleItem):
        return "construction_circle"
    if isinstance(item, ArcItem):
        return "arc"
    if isinstance(item, BezierItem):
        return "bezier"
    if isinstance(item, CalloutItem):
        return "callout"
    if isinstance(item, PolygonItem):
        return "polygon"
    if isinstance(item, PolylineItem):
        return "polyline"
    if isinstance(item, RectangleItem):
        return "rectangle"
    if isinstance(item, EllipseItem):
        return "ellipse"
    if isinstance(item, CircleItem):
        return "circle"
    if isinstance(item, SmartSymbolItem):
        return "group"
    if isinstance(item, GroupItem):
        return "group"
    if isinstance(item, JournalPinItem):
        return "journal_pin"
    if isinstance(item, BackgroundImageItem):
        return "background_image"
    if isinstance(item, TextItem):
        return "text"
    return type(item).__name__


def _object_type(item: QGraphicsItem) -> str | None:
    object_type = getattr(item, "object_type", None)
    name = getattr(object_type, "name", None)
    return str(name) if name else None


def _rotation_deg(item: QGraphicsItem) -> float:
    explicit = getattr(item, "rotation_angle", None)
    if explicit is not None:
        return float(explicit)
    return float(item.rotation())


def describe_geometry(
    item: QGraphicsItem,
    *,
    center: tuple[float, float],
    constraints: list[Any],
) -> dict[str, Any]:
    """Return a plain, schema-shaped live geometry description for ``item``."""
    geometry_type = _geometry_type(item)
    center_x, center_y = center
    payload: dict[str, Any] = {
        "item_id": str(item.item_id),
        "type": geometry_type,
        "object_type": _object_type(item),
        "coordinate_frame": "scene_cm_y_up",
        "center_x_cm": float(center_x),
        "center_y_cm": float(center_y),
        "rotation_deg": _rotation_deg(item),
        "width_cm": None,
        "height_cm": None,
        "radius_cm": None,
        "vertices": [],
        "closed": None,
        "vertex_editable": False,
        "vertex_count": None,
        "minimum_vertex_count": None,
        "endpoints": [],
        "curve": None,
        "leader": None,
        "child_count": None,
    }

    from open_garden_planner.ui.canvas.items import (
        ArcItem,
        BackgroundImageItem,
        BezierItem,
        CalloutItem,
        CircleItem,
        ConstructionCircleItem,
        ConstructionLineItem,
        EllipseItem,
        GroupItem,
        RectangleItem,
    )

    if isinstance(item, (RectangleItem, EllipseItem)):
        payload["width_cm"] = float(item.rect().width())
        payload["height_cm"] = float(item.rect().height())
    elif isinstance(item, CircleItem):
        payload["radius_cm"] = float(item.radius)
    elif is_vertex_editable(item):
        vertices = scene_vertex_positions(item)
        payload["vertices"] = [_point(vertex) for vertex in vertices]
        payload["closed"] = geometry_type == "polygon"
        payload["vertex_editable"] = True
        payload["vertex_count"] = len(vertices)
        payload["minimum_vertex_count"] = int(item._get_minimum_vertex_count())  # type: ignore[attr-defined]
    elif isinstance(item, ArcItem):
        payload["radius_cm"] = float(item.radius)
        payload["endpoints"] = [
            _point(item.start_point()),
            _point(item.end_point()),
        ]
        payload["curve"] = {
            "kind": "arc",
            "center": _point(item.center),
            "radius_cm": float(item.radius),
            "start_deg": float(item.start_deg),
            "span_deg": float(item.span_deg),
            "through": _point(item.through_point()),
            "anchors": [],
            "handles_in": [],
            "handles_out": [],
        }
    elif isinstance(item, BezierItem):
        payload["endpoints"] = [
            _point(item.start_point()),
            _point(item.end_point()),
        ]
        payload["curve"] = {
            "kind": "bezier",
            "center": None,
            "radius_cm": None,
            "start_deg": None,
            "span_deg": None,
            "through": None,
            "anchors": [
                _point(item.mapToScene(point)) for point in item.anchors
            ],
            "handles_in": [
                _point(item.mapToScene(point)) for point in item.handles_in
            ],
            "handles_out": [
                _point(item.mapToScene(point)) for point in item.handles_out
            ],
        }
    elif isinstance(item, CalloutItem):
        payload["leader"] = {
            "tip": _point(item.scenePos()),
            "box_corner": _point(item.mapToScene(item.box_offset)),
        }
    elif isinstance(item, ConstructionLineItem):
        # p1/p2 already expose scene coordinates; mapping them again would
        # double-apply the item transform after a move.
        payload["endpoints"] = [_point(item.p1), _point(item.p2)]
    elif isinstance(item, ConstructionCircleItem):
        payload["radius_cm"] = float(item.radius)
    elif isinstance(item, GroupItem):
        payload["child_count"] = len(item.childItems())
    elif isinstance(item, BackgroundImageItem):
        scene_rect = item.mapRectToScene(item.boundingRect())
        payload["width_cm"] = float(scene_rect.width())
        payload["height_cm"] = float(scene_rect.height())

    ordered_constraints = sorted(
        (_constraint(constraint) for constraint in constraints),
        key=lambda value: (value["constraint_type"], value["constraint_id"]),
    )
    payload["constraints"] = ordered_constraints
    payload["is_constrained"] = bool(ordered_constraints)
    return payload


__all__ = ["describe_geometry"]
