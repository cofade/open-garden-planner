"""Shared infrastructure for tools that modify a single corner of a shape.

The fillet (US-B3a) and chamfer (US-B3b) tools both pick a corner on a
polyline / polygon / rectangle, then transform that corner. They share
most of the picking, highlighting, and rectangle→polygon conversion
logic; this module factors it out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from open_garden_planner.core.tools.base_tool import BaseTool

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


# Visual constants — same family as the trim tool's highlight palette so
# they read as "this corner is the action target".
HIGHLIGHT_COLOR = QColor(220, 80, 20, 220)
HIGHLIGHT_WIDTH = 3.0
HIGHLIGHT_Z = 999.0
PICK_TOLERANCE = 16.0  # cm — generous so users don't need pixel-perfect aim


@dataclass
class CornerTarget:
    """Identified corner ready for fillet/chamfer.

    Fields are in *scene* coordinates so geometry helpers operate on
    plain world points without needing to know the item type.
    """

    item: QGraphicsItem
    vertex_index: int
    p_prev_scene: QPointF
    p_corner_scene: QPointF
    p_next_scene: QPointF


def _is_corner_editable(item: object) -> bool:
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    return isinstance(item, (PolylineItem, PolygonItem, RectangleItem))


def _item_corners_scene(
    item: QGraphicsItem,
) -> list[tuple[int, QPointF, QPointF, QPointF]]:
    """Yield ``(index, p_prev, p_corner, p_next)`` triples in scene coords.

    For a polyline only *internal* vertices are corners — the two
    endpoints have no second adjacent edge so they cannot be filleted
    or chamfered. Polygons and rectangles wrap around so every vertex
    is a corner.
    """
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    out: list[tuple[int, QPointF, QPointF, QPointF]] = []
    if isinstance(item, PolylineItem):
        pts = item.points
        for i in range(1, len(pts) - 1):
            out.append(
                (
                    i,
                    item.mapToScene(pts[i - 1]),
                    item.mapToScene(pts[i]),
                    item.mapToScene(pts[i + 1]),
                )
            )
    elif isinstance(item, PolygonItem):
        poly = item.polygon()
        n = poly.count()
        for i in range(n):
            out.append(
                (
                    i,
                    item.mapToScene(poly.at((i - 1) % n)),
                    item.mapToScene(poly.at(i)),
                    item.mapToScene(poly.at((i + 1) % n)),
                )
            )
    elif isinstance(item, RectangleItem):
        rect = item.rect()
        corners_local = [
            QPointF(rect.left(), rect.top()),
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()),
        ]
        n = 4
        for i in range(n):
            out.append(
                (
                    i,
                    item.mapToScene(corners_local[(i - 1) % n]),
                    item.mapToScene(corners_local[i]),
                    item.mapToScene(corners_local[(i + 1) % n]),
                )
            )
    return out


def find_nearest_corner(
    view: CanvasView,
    cursor_scene: QPointF,
    tolerance: float = PICK_TOLERANCE,
) -> CornerTarget | None:
    """Pick the closest corner to ``cursor_scene`` within ``tolerance`` cm."""
    best_dist = tolerance
    best: CornerTarget | None = None
    for item in view.scene().items():
        if not _is_corner_editable(item):
            continue
        for idx, p_prev, p_corner, p_next in _item_corners_scene(item):
            d = math.hypot(
                cursor_scene.x() - p_corner.x(),
                cursor_scene.y() - p_corner.y(),
            )
            if d < best_dist:
                best_dist = d
                best = CornerTarget(
                    item=item,
                    vertex_index=idx,
                    p_prev_scene=p_prev,
                    p_corner_scene=p_corner,
                    p_next_scene=p_next,
                )
    return best


def rectangle_corners_local(item: QGraphicsItem) -> list[QPointF]:
    """Return the 4 rectangle vertices in item-local coords (TL,TR,BR,BL)."""
    rect = item.rect()  # type: ignore[attr-defined]
    return [
        QPointF(rect.left(), rect.top()),
        QPointF(rect.right(), rect.top()),
        QPointF(rect.right(), rect.bottom()),
        QPointF(rect.left(), rect.bottom()),
    ]


class CornerEditTool(BaseTool):
    """Base class for tools that act on a single picked corner.

    Subclasses implement ``current_parameter`` (radius / distance) and
    ``apply_to_target`` to perform the actual modification when the
    user clicks.
    """

    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._target: CornerTarget | None = None
        self._highlight: QGraphicsPathItem | None = None

    # ── Mouse handling ─────────────────────────────────────────────────

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        target = find_nearest_corner(self._view, scene_pos)
        if target is None:
            self._clear_highlight()
            self._target = None
            return True
        self._target = target
        self._draw_highlight(target)
        return True

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        target = find_nearest_corner(self._view, scene_pos)
        if target is None:
            return False
        self._target = target
        self._clear_highlight()
        self.apply_to_target(target)
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        self._clear_highlight()
        self._target = None

    def deactivate(self) -> None:
        self._clear_highlight()
        super().deactivate()

    # ── Highlight ──────────────────────────────────────────────────────

    def _draw_highlight(self, target: CornerTarget) -> None:
        self._clear_highlight()
        from PyQt6.QtGui import QPainterPath

        path = QPainterPath()
        path.moveTo(target.p_prev_scene)
        path.lineTo(target.p_corner_scene)
        path.lineTo(target.p_next_scene)

        hi = QGraphicsPathItem()
        hi.setPath(path)
        pen = QPen(HIGHLIGHT_COLOR, HIGHLIGHT_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        hi.setPen(pen)
        hi.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        hi.setZValue(HIGHLIGHT_Z)
        self._view.scene().addItem(hi)
        self._highlight = hi

    def _clear_highlight(self) -> None:
        if self._highlight is not None:
            scene = self._view.scene()
            if self._highlight.scene() is scene:
                scene.removeItem(self._highlight)
            self._highlight = None

    # ── Subclass interface ─────────────────────────────────────────────

    def apply_to_target(self, target: CornerTarget) -> None:
        """Subclasses override to execute the actual modification."""
        raise NotImplementedError
