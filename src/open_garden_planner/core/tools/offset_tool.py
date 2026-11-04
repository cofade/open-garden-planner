"""Offset tool — creates a parallel copy of a shape (US-11.15).

Closed shapes get an inward/outward copy (polygon).  An open polyline (fence,
wall, path) has no inside: the result is a parallel *line* on the cursor's side.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from open_garden_planner.core.item_look import copy_visual_style
from open_garden_planner.core.tools.base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

# Scale factor for converting float cm coords to pyclipper integers
_CLIPPER_SCALE = 1000


def _item_shape_path(item: QGraphicsItem):
    """Return the item's shape() path in scene coordinates, or None."""
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    if isinstance(item, (RectangleItem, CircleItem, EllipseItem, PolygonItem, PolylineItem)):
        return item.mapToScene(item.shape())
    return None


def _is_offsettable(item: QGraphicsItem) -> bool:
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    return isinstance(item, (RectangleItem, CircleItem, EllipseItem, PolygonItem, PolylineItem))


def _nearest_boundary_distance(item: QGraphicsItem, scene_pos: QPointF) -> float:
    """Approximate distance from scene_pos to the item's boundary."""
    local_pos = item.mapFromScene(scene_pos)
    shape = item.shape()
    # Sample points along the path boundary and find nearest
    length = shape.length()
    if length <= 0:
        return 0.0
    steps = max(64, int(length / 5))
    best = math.inf
    for i in range(steps + 1):
        t = i / steps
        pt = shape.pointAtPercent(t)
        d = math.hypot(local_pos.x() - pt.x(), local_pos.y() - pt.y())
        if d < best:
            best = d
    return best


def _compute_offset_item(
    item: QGraphicsItem,
    distance: float,
    inward: bool,
    scene_pos: QPointF | None = None,
) -> QGraphicsItem | None:
    """Create an offset copy of item at the given distance. Returns None if invalid."""
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    d = distance if not inward else -distance

    if isinstance(item, RectangleItem):
        return _offset_rectangle(item, d)
    if isinstance(item, CircleItem):
        return _offset_circle(item, d)
    if isinstance(item, EllipseItem):
        return _offset_ellipse(item, d)
    if isinstance(item, PolygonItem):
        return _offset_polygon(item, d)
    if isinstance(item, PolylineItem):
        # An open line has no inside; the cursor picks the side instead.
        return _offset_polyline(item, abs(distance), scene_pos)
    return None


def _offset_rectangle(item: RectangleItem, d: float) -> QGraphicsItem | None:
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    rect = item.rect()
    # Convert to scene coords for the new item position
    scene_rect = QRectF(
        item.pos().x() + rect.x() - d,
        item.pos().y() + rect.y() - d,
        rect.width() + 2 * d,
        rect.height() + 2 * d,
    )
    if scene_rect.width() <= 0 or scene_rect.height() <= 0:
        return None
    result = RectangleItem(
        scene_rect.x(), scene_rect.y(), scene_rect.width(), scene_rect.height(),
        object_type=item.object_type,
        layer_id=item.layer_id,
    )
    copy_visual_style(item, result)
    if hasattr(item, 'rotation_angle') and abs(item.rotation_angle) > 0.01:
        result._apply_rotation(item.rotation_angle)
    return result


def _offset_circle(item: CircleItem, d: float) -> QGraphicsItem | None:
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    new_r = item.radius + d
    if new_r <= 0:
        return None
    cx = item.pos().x() + item.center.x()
    cy = item.pos().y() + item.center.y()
    result = CircleItem(cx, cy, new_r, object_type=item.object_type, layer_id=item.layer_id)
    copy_visual_style(item, result)
    return result


def _offset_ellipse(item: EllipseItem, d: float) -> QGraphicsItem | None:
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem

    rect = item.rect()
    new_rx = rect.width() / 2 + d
    new_ry = rect.height() / 2 + d
    if new_rx <= 0 or new_ry <= 0:
        return None
    cx = item.pos().x() + rect.center().x()
    cy = item.pos().y() + rect.center().y()
    result = EllipseItem(
        cx - new_rx, cy - new_ry, new_rx * 2, new_ry * 2,
        object_type=item.object_type,
        layer_id=item.layer_id,
    )
    copy_visual_style(item, result)
    if hasattr(item, 'rotation_angle') and abs(item.rotation_angle) > 0.01:
        result._apply_rotation(item.rotation_angle)
    return result


def _polygon_points_scene(item: QGraphicsItem) -> list[QPointF]:
    """Return polygon vertices in scene coordinates."""
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

    assert isinstance(item, PolygonItem)
    poly = item.polygon()
    return [item.mapToScene(poly.at(i)) for i in range(poly.count())]


def _polyline_points_scene(item: QGraphicsItem) -> list[QPointF]:
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

    assert isinstance(item, PolylineItem)
    return [item.mapToScene(p) for p in item.points]


def _to_clipper(points: list[QPointF]) -> list[tuple[int, int]]:
    return [(int(p.x() * _CLIPPER_SCALE), int(p.y() * _CLIPPER_SCALE)) for p in points]


def _from_clipper(points: list[tuple[int, int]]) -> list[QPointF]:
    s = _CLIPPER_SCALE
    return [QPointF(x / s, y / s) for x, y in points]


def _offset_polygon(item: PolygonItem, d: float) -> QGraphicsItem | None:
    try:
        import pyclipper
    except ImportError:
        return None

    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

    pts = _polygon_points_scene(item)
    if len(pts) < 3:
        return None

    pco = pyclipper.PyclipperOffset()
    pco.AddPath(
        _to_clipper(pts),
        pyclipper.JT_MITER,
        pyclipper.ET_CLOSEDPOLYGON,
    )
    result = pco.Execute(int(d * _CLIPPER_SCALE))
    if not result:
        return None

    out_pts = _from_clipper(result[0])
    if len(out_pts) < 3:
        return None

    new_item = PolygonItem(
        vertices=out_pts,
        object_type=item.object_type,
        layer_id=item.layer_id,
    )
    copy_visual_style(item, new_item)
    return new_item


def _offset_polyline(
    item: PolylineItem,
    distance: float,
    scene_pos: QPointF | None = None,
) -> QGraphicsItem | None:
    """A parallel LINE on the cursor's side — never an area.

    An open fence/wall/path has no inside; the old code wrapped the offset
    contour in a filled ``PolygonItem``, which produced a meaningless rounded
    band on the ground (owner manual test 2026-11-01).  A polyline is offset
    segment by segment (miter joins, bevelled past the miter limit), giving one
    open line.  Both sides are computed and the one nearer the cursor wins, so
    moving the mouse across the line flips the side.
    """
    pts = _polyline_points_scene(item)
    if len(pts) < 2:
        return None

    candidates = [
        points
        for side in (1.0, -1.0)
        if (points := _offset_open_points(pts, abs(distance), side))
    ]
    if not candidates:
        return None
    if scene_pos is None:
        out_pts = candidates[0]
    else:

        def _closest(points: list[QPointF]) -> float:
            return min(
                math.hypot(point.x() - scene_pos.x(), point.y() - scene_pos.y())
                for point in points
            )

        out_pts = min(candidates, key=_closest)

    from open_garden_planner.core.item_look import (
        apply_line_look,
        capture_line_look,
    )
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

    new_item = PolylineItem(
        points=out_pts,
        object_type=item.object_type,
        layer_id=item.layer_id,
    )
    apply_line_look(new_item, capture_line_look(item))
    return new_item


#: A miter longer than this multiple of the offset distance becomes a bevel
#: (two points).  sqrt(2) is a 90° corner; 4 keeps normal corners sharp and
#: refuses spikes on acute turns.
_MITER_LIMIT = 4.0


def _segment_normal(start: QPointF, end: QPointF) -> QPointF | None:
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    return QPointF(-dy / length, dx / length)


def _line_intersection(
    a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF
) -> QPointF | None:
    rx, ry = a2.x() - a1.x(), a2.y() - a1.y()
    sx, sy = b2.x() - b1.x(), b2.y() - b1.y()
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-9:
        return None
    t = ((b1.x() - a1.x()) * sy - (b1.y() - a1.y()) * sx) / denom
    return QPointF(a1.x() + t * rx, a1.y() + t * ry)


def _offset_open_points(
    points: list[QPointF], distance: float, side: float
) -> list[QPointF] | None:
    """One open offset line of a polyline, ``distance`` to the chosen side."""
    segments: list[tuple[QPointF, QPointF, QPointF]] = []
    for start, end in zip(points, points[1:], strict=False):
        normal = _segment_normal(start, end)
        if normal is None:
            continue
        offset = QPointF(
            normal.x() * distance * side, normal.y() * distance * side
        )
        segments.append((start, end, offset))
    if not segments:
        return None

    offset_segments = [
        (
            QPointF(start.x() + offset.x(), start.y() + offset.y()),
            QPointF(end.x() + offset.x(), end.y() + offset.y()),
        )
        for start, end, offset in segments
    ]

    out: list[QPointF] = [offset_segments[0][0]]
    for index in range(1, len(offset_segments)):
        prev_start, prev_end = offset_segments[index - 1]
        cur_start, cur_end = offset_segments[index]
        corner = _line_intersection(prev_start, prev_end, cur_start, cur_end)
        base_vertex = segments[index][0]
        if corner is None:
            # Collinear or reversed: the shared offset point is the vertex.
            offset = segments[index - 1][2]
            out.append(QPointF(base_vertex.x() + offset.x(), base_vertex.y() + offset.y()))
        elif math.hypot(
            corner.x() - base_vertex.x(), corner.y() - base_vertex.y()
        ) > _MITER_LIMIT * abs(distance):
            out.append(prev_end)
            out.append(cur_start)
        else:
            out.append(corner)
    out.append(offset_segments[-1][1])

    deduped: list[QPointF] = []
    for point in out:
        if not deduped or math.hypot(
            point.x() - deduped[-1].x(), point.y() - deduped[-1].y()
        ) > 1e-9:
            deduped.append(point)
    return deduped if len(deduped) >= 2 else None


class OffsetTool(BaseTool):
    """Offset a selected shape by a specified distance.

    Closed shapes get an inward or outward area copy; a polyline gets a
    parallel line on the cursor's side.

    Usage:
        1. Select a shape (rectangle, circle, ellipse, polygon, or polyline)
        2. Activate the Offset tool
        3. Closed shapes: hover inside for inward / outside for outward.
           Polylines: hover on the side the parallel line should take.
        4. Click to confirm — the distance follows the cursor.
    """

    tool_type = ToolType.OFFSET
    display_name = QT_TR_NOOP("Offset")
    shortcut = "O"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._target: QGraphicsItem | None = None
        self._inward: bool = False
        self._preview: QGraphicsPathItem | None = None

    def activate(self) -> None:
        super().activate()
        self._update_target_from_selection()

    def deactivate(self) -> None:
        self._clear_preview()
        super().deactivate()

    def cancel(self) -> None:
        self._clear_preview()

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self._clear_preview()
            return True
        return False

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        self._update_target_from_selection()
        if self._target is None:
            self._clear_preview()
            return False

        local_pos = self._target.mapFromScene(scene_pos)
        self._inward = self._target.shape().contains(local_pos)

        dist = _nearest_boundary_distance(self._target, scene_pos)
        if dist < 0.5:
            self._clear_preview()
            return True

        preview_d = dist if not self._inward else -dist
        preview_item = _compute_offset_item(
            self._target, abs(preview_d), self._inward, scene_pos
        )
        self._set_preview(preview_item)
        return True

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        self._update_target_from_selection()
        if self._target is None:
            self._view.set_status_message(QCoreApplication.translate("CanvasView", "Select a shape to offset"))
            return False

        local_pos = self._target.mapFromScene(scene_pos)
        self._inward = self._target.shape().contains(local_pos)
        dist = _nearest_boundary_distance(self._target, scene_pos)

        self._clear_preview()

        if dist < 0.5:
            return True

        result = _compute_offset_item(
            self._target, dist, self._inward, scene_pos
        )
        if result is None:
            self._view.set_status_message(
                QCoreApplication.translate("CanvasView", "Offset result is empty — try a smaller distance")
            )
            return True

        self._view.add_item(result, "offset")
        from open_garden_planner.ui.canvas.items.polyline_item import (
            PolylineItem,
        )

        if isinstance(self._target, PolylineItem):
            self._view.set_status_message(
                QCoreApplication.translate(
                    "CanvasView", "Created a parallel line at {dist:.1f} cm"
                ).format(dist=dist)
            )
        else:
            direction = QCoreApplication.translate("CanvasView", "inward") if self._inward else QCoreApplication.translate("CanvasView", "outward")
            self._view.set_status_message(
                QCoreApplication.translate("CanvasView", "Created {dir} offset of {dist:.1f} cm").format(dir=direction, dist=dist)
            )
        self._view._tool_manager.set_active_tool(ToolType.SELECT)
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def _update_target_from_selection(self) -> None:
        scene = self._view.scene()
        selected = [i for i in scene.selectedItems() if _is_offsettable(i)]
        self._target = selected[0] if len(selected) == 1 else None

    def _clear_preview(self) -> None:
        if self._preview is not None:
            scene = self._view.scene()
            if self._preview.scene() is scene:
                scene.removeItem(self._preview)
            self._preview = None

    def _set_preview(self, item: QGraphicsItem | None) -> None:
        self._clear_preview()
        if item is None:
            return

        from open_garden_planner.ui.canvas.items.polyline_item import (
            PolylineItem,
        )

        path_item = QGraphicsPathItem()
        if isinstance(item, PolylineItem):
            # A line's shape() is its stroke band; preview the line itself.
            points = [item.mapToScene(p) for p in item.points]
            path = QPainterPath()
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
            path_item.setPath(path)
            path_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        else:
            path = item.shape()
            path_item.setPath(item.mapToScene(path))
            path_item.setBrush(QBrush(QColor(0, 150, 255, 30)))
        pen = QPen(QColor(0, 150, 255, 200), 1.5, Qt.PenStyle.DashLine)
        path_item.setPen(pen)
        path_item.setZValue(9999)
        self._view.scene().addItem(path_item)
        self._preview = path_item
