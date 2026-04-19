"""Offset tool — creates a parallel copy of a shape inward or outward (US-11.15)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QInputDialog

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


def _item_shape_path(item: QGraphicsItem):  # type: ignore[return]
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
        return _offset_polyline(item, d)
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
    return CircleItem(cx, cy, new_r, object_type=item.object_type, layer_id=item.layer_id)


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
    new_item.setPen(QPen(item.pen()))
    new_item.setBrush(QBrush(item.brush()))
    return new_item


def _offset_polyline(item: PolylineItem, d: float) -> QGraphicsItem | None:
    try:
        import pyclipper
    except ImportError:
        return None

    pts = _polyline_points_scene(item)
    if len(pts) < 2:
        return None

    pco = pyclipper.PyclipperOffset()
    pco.AddPath(
        _to_clipper(pts),
        pyclipper.JT_ROUND,
        pyclipper.ET_OPENROUND,
    )
    result = pco.Execute(int(abs(d) * _CLIPPER_SCALE))
    if not result:
        return None

    out_pts = _from_clipper(result[0])
    if len(out_pts) < 2:
        return None

    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    new_item = PolygonItem(
        vertices=out_pts,
        object_type=item.object_type,
        layer_id=item.layer_id,
    )
    new_item.setPen(QPen(item.pen()))
    new_item.setBrush(QBrush(item.brush()))
    return new_item


class OffsetTool(BaseTool):
    """Offset a selected shape inward or outward by a specified distance.

    Usage:
        1. Select a shape (rectangle, circle, ellipse, polygon, or polyline)
        2. Activate the Offset tool
        3. Hover inside shape for inward preview, outside for outward preview
        4. Click to confirm — enter distance in the dialog
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
        preview_item = _compute_offset_item(self._target, abs(preview_d), self._inward)
        self._set_preview(preview_item)
        return True

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        self._update_target_from_selection()
        if self._target is None:
            self._view.set_status_message(
                self._view.tr("Select a shape to offset")
            )
            return False

        local_pos = self._target.mapFromScene(scene_pos)
        self._inward = self._target.shape().contains(local_pos)

        self._clear_preview()

        dist, ok = QInputDialog.getDouble(
            self._view,
            self._view.tr("Offset"),
            self._view.tr("Offset distance (cm):"),
            value=10.0,
            min=0.1,
            max=9999.0,
            decimals=1,
        )
        if not ok or dist <= 0:
            return True

        result = _compute_offset_item(self._target, dist, self._inward)
        if result is None:
            self._view.set_status_message(
                self._view.tr("Offset result is empty — try a smaller distance")
            )
            return True

        self._view.add_item(result, "offset")
        direction = self._view.tr("inward") if self._inward else self._view.tr("outward")
        self._view.set_status_message(
            self._view.tr("Created {dir} offset of {dist} cm").format(dir=direction, dist=dist)
        )
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

        path = item.shape()
        path_item = QGraphicsPathItem()
        path_item.setPath(item.mapToScene(path))
        pen = QPen(QColor(0, 150, 255, 200), 1.5, Qt.PenStyle.DashLine)
        path_item.setPen(pen)
        path_item.setBrush(QBrush(QColor(0, 150, 255, 30)))
        path_item.setZValue(9999)
        self._view.scene().addItem(path_item)
        self._preview = path_item
