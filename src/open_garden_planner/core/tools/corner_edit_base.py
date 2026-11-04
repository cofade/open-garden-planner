"""Shared infrastructure for tools that modify a single corner of a shape.

The fillet (US-B3a) and chamfer (US-B3b) tools both pick a corner on a
polyline / polygon / rectangle, then transform that corner. They share
most of the picking, highlighting, and rectangle→polygon conversion
logic; this module factors it out.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from open_garden_planner.core.object_types import (
    polygon_equivalent_object_type,
)
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


class CornerEditRefusal(Enum):
    """Why a corner edit cannot proceed (translated by the tool)."""

    GROUPED = "grouped"
    UNSUPPORTED_TYPE = "unsupported_type"
    CONSTRAINT = "constraint"


def _is_corner_editable(item: object) -> bool:
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    # A grouped child is not a top-level shape: the replacement commands add the
    # new item to the scene's top level, which would move it out of its group
    # (round-3 review P2).  Group members are not individually selectable, so
    # this only closes a programmatic path, but it must not be silent.
    if getattr(item, "parentItem", lambda: None)() is not None:
        return False
    if isinstance(item, PolylineItem):
        return True
    if isinstance(item, (PolygonItem, RectangleItem)):
        # An item whose type has no polygonal form must not even highlight: the
        # click could only be refused (#owner manual test 2026-10-31).
        return polygon_equivalent_object_type(
            getattr(item, "object_type", None)
        ) is not None
    return False


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


def corner_edit_refusal(target: CornerTarget) -> CornerEditRefusal | None:
    """The reason ``target`` cannot be edited, or ``None`` when it can.

    This is checked before any geometry is computed so the user gets the right
    message.  The constraint check is deliberately CORNER-SCOPED: replacing one
    vertex only renumbers anchors after it, and the vertex itself plus its two
    incident edges are the only references that cannot be preserved.  The old
    item-wide rule refused every corner of a rectangle as soon as one unrelated
    corner carried a constraint (owner manual test 2026-10-31).
    """
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    item = target.item
    if getattr(item, "parentItem", lambda: None)() is not None:
        return CornerEditRefusal.GROUPED

    if isinstance(item, PolylineItem):
        is_rectangle = False
        closed = False
        vertex_count = len(item.points)
    elif isinstance(item, PolygonItem):
        is_rectangle = False
        closed = True
        vertex_count = item.polygon().count()
    elif isinstance(item, RectangleItem):
        is_rectangle = True
        closed = True
        vertex_count = 4
    else:
        return CornerEditRefusal.UNSUPPORTED_TYPE

    # Only the items that become a polygon (or already are one) need a
    # polygon-valid type; a polyline keeps its fence/path type unchanged.
    if not isinstance(item, PolylineItem) and polygon_equivalent_object_type(
        getattr(item, "object_type", None)
    ) is None:
        return CornerEditRefusal.UNSUPPORTED_TYPE

    vertex_index = target.vertex_index
    if is_rectangle:
        # The picker walks TL,TR,BR,BL; a rectangle's anchors are TL,TR,BL,BR.
        from open_garden_planner.core.measure_snapper import (
            RECT_CORNER_POLYGON_ORDER,
        )

        vertex_index = RECT_CORNER_POLYGON_ORDER[vertex_index]

    scene = item.scene()
    graph = getattr(scene, "constraint_graph", None) if scene is not None else None
    item_id = getattr(item, "item_id", None)
    if (
        graph is not None
        and item_id is not None
        and graph.corner_edit_is_blocked(
            item_id,
            vertex_index,
            closed=closed,
            rectangle=is_rectangle,
            vertex_count=vertex_count,
        )
    ):
        return CornerEditRefusal.CONSTRAINT
    return None


def _insert_replacement_vertices(
    original: Sequence[QPointF],
    index: int,
    replacement: Sequence[QPointF],
) -> list[QPointF]:
    """Replace ``original[index]`` with ``replacement``, keeping the rest in order."""
    return [
        *original[:index],
        *replacement,
        *original[index + 1 :],
    ]


def rebuild_with_corner_replaced(
    target: CornerTarget,
    replacement_points_scene: Sequence[QPointF],
) -> QGraphicsItem | None:
    """Return a copy of the host item with one corner replaced by new vertices.

    Used by both fillet (an arc sampled into vertices, baked into the host) and
    chamfer (two vertices and a straight cut).  Polyline / polygon copies keep
    their styling; rectangles are destructively converted to a polygon because
    rectangles have no slot for per-corner geometry — the undo command keeps a
    reference to the original rectangle so "undo" restores it whole
    (ADR-022).  A rectangle's object type is mapped to its polygonal equivalent
    (raised bed → garden bed); types with no polygonal form are refused.
    """
    from open_garden_planner.core.item_look import (
        adopt_type_fill,
        copy_visual_style,
        inherit_item_identity,
    )
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    item = target.item

    # A grouped member's replacement is added to the scene's top level, which
    # would move it out of its group; the picker already skips groups, and this
    # guard closes the programmatic path too (round-4 review P2).
    if getattr(item, "parentItem", lambda: None)() is not None:
        return None

    if not replacement_points_scene:
        return None

    if isinstance(item, PolylineItem):
        pts_local = item.points
        replacement_local = [
            item.mapFromScene(point) for point in replacement_points_scene
        ]
        new_pts = _insert_replacement_vertices(
            pts_local, target.vertex_index, replacement_local
        )
        clone = item.clone_with_points(new_pts)
        # #668: the corner edit replaces the item; it must not replace its UUID
        # (constraints, garden records and plant links are keyed by it).
        inherit_item_identity(item, clone)
        return clone

    if isinstance(item, (PolygonItem, RectangleItem)):
        mapped_type = polygon_equivalent_object_type(
            getattr(item, "object_type", None)
        )
        if mapped_type is None:
            return None
        if isinstance(item, PolygonItem):
            poly = item.polygon()
            verts_local = [poly.at(j) for j in range(poly.count())]
        else:
            verts_local = rectangle_corners_local(item)
        replacement_local = [
            item.mapFromScene(point) for point in replacement_points_scene
        ]
        new_verts = _insert_replacement_vertices(
            verts_local, target.vertex_index, replacement_local
        )
        polygon_clone = PolygonItem(
            vertices=new_verts,
            object_type=mapped_type,
            layer_id=item.layer_id,
        )
        copy_visual_style(item, polygon_clone)
        adopt_type_fill(
            polygon_clone,
            getattr(item, "object_type", None),
            mapped_type,
        )
        inherit_item_identity(item, polygon_clone)
        return polygon_clone

    return None
