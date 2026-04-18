"""CAD-style Trim / Extend tool (US-11.16).

Trim mode  (default): hover highlights the sub-segment of a polyline or
  polygon edge that lies between two consecutive intersection points; left-
  click removes it.  The removed portion may split a polyline into two
  pieces, or convert a polygon to an open polyline.

Extend mode (X to toggle): hover previews an outward extension of the
  nearest polyline endpoint to the first cutting edge along the extension
  ray; left-click commits the extension.

All scene polylines and polygons act as implicit cutting edges — no
selection phase is required.

Shortcut: I (trIm).  Toggle trim/extend: X.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsPathItem

from open_garden_planner.core.cad_geometry import (
    HOVER_TOLERANCE,
    collect_intersections_on_segment,
    interpolate,
    point_to_segment_distance,
    polygon_to_scene_segments,
    polyline_to_scene_segments,
    rectangle_to_scene_segments,
)
from open_garden_planner.core.commands import (
    ExtendPolylineCommand,
    TrimPolygonCommand,
    TrimPolylineCommand,
    TrimRectangleCommand,
)
from open_garden_planner.core.tools.base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

# ── Visual constants ──────────────────────────────────────────────────────────

_TRIM_COLOR = QColor(220, 80, 20, 220)
_EXTEND_COLOR = QColor(20, 140, 200, 220)
_HIGHLIGHT_EXTRA_WIDTH = 4.0
_HIGHLIGHT_Z = 999.0
_EXTEND_TOLERANCE_MULT = 3.0


# ── Internal state dataclasses ────────────────────────────────────────────────


class TrimExtendMode(Enum):
    TRIM = auto()
    EXTEND = auto()


@dataclass
class _TrimTarget:
    item: object
    seg_index: int
    t_start: float
    t_end: float
    p1_scene: QPointF
    p2_scene: QPointF


@dataclass
class _ExtendTarget:
    item: object
    endpoint_index: int  # 0 = start, -1 = end
    origin_scene: QPointF
    dest_scene: QPointF


# ── Scene-item helpers ────────────────────────────────────────────────────────


def _is_trimmable(item: object) -> bool:
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    return isinstance(item, (PolylineItem, PolygonItem, RectangleItem))


def _item_to_scene_segs(
    item: object,
) -> list[tuple[QPointF, QPointF]]:
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    if isinstance(item, PolylineItem):
        return polyline_to_scene_segments(item)
    if isinstance(item, RectangleItem):
        return rectangle_to_scene_segments(item)
    return polygon_to_scene_segments(item)


# ── TrimExtendTool ────────────────────────────────────────────────────────────


class TrimExtendTool(BaseTool):
    """Trim or extend polylines and polygon edges at intersection points.

    Press X while the tool is active to toggle between TRIM and EXTEND modes.
    """

    tool_type = ToolType.TRIM_EXTEND
    display_name = "Trim/Extend"
    shortcut = "I"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._mode: TrimExtendMode = TrimExtendMode.TRIM
        self._highlight: QGraphicsPathItem | None = None
        self._trim_target: _TrimTarget | None = None
        self._extend_target: _ExtendTarget | None = None

    # ── BaseTool interface ────────────────────────────────────────────────────

    def activate(self) -> None:
        super().activate()
        self._mode = TrimExtendMode.TRIM

    def deactivate(self) -> None:
        self._clear_highlight()
        super().deactivate()

    def cancel(self) -> None:
        self._clear_highlight()

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_X:
            self._mode = (
                TrimExtendMode.EXTEND
                if self._mode == TrimExtendMode.TRIM
                else TrimExtendMode.TRIM
            )
            self._clear_highlight()
            return True
        return False

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        if self._mode == TrimExtendMode.TRIM:
            self._update_trim_highlight(scene_pos)
        else:
            self._update_extend_highlight(scene_pos)
        return True

    def mouse_press(self, event: QMouseEvent, _scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._mode == TrimExtendMode.TRIM:
            return self._execute_trim()
        return self._execute_extend()

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    # ── Highlight management ──────────────────────────────────────────────────

    def _clear_highlight(self) -> None:
        if self._highlight is not None:
            scene = self._view.scene()
            if self._highlight.scene() is scene:
                scene.removeItem(self._highlight)
            self._highlight = None
        self._trim_target = None
        self._extend_target = None

    def _show_highlight(self, path_item: QGraphicsPathItem) -> None:
        # Remove the old highlight graphic only — do NOT call _clear_highlight()
        # here because that would reset _trim_target/_extend_target.
        if self._highlight is not None:
            scene = self._view.scene()
            if self._highlight.scene() is scene:
                scene.removeItem(self._highlight)
            self._highlight = None
        path_item.setZValue(_HIGHLIGHT_Z)
        self._view.scene().addItem(path_item)
        self._highlight = path_item

    # ── Trim hover ────────────────────────────────────────────────────────────

    def _update_trim_highlight(self, cursor: QPointF) -> None:
        self._clear_highlight()
        target = self._find_trim_target(cursor)
        if target is None:
            return
        self._trim_target = target

        sub_p1 = interpolate(target.p1_scene, target.p2_scene, target.t_start)
        sub_p2 = interpolate(target.p1_scene, target.p2_scene, target.t_end)

        from PyQt6.QtGui import QPainterPath as _QPP

        path = _QPP()
        path.moveTo(sub_p1)
        path.lineTo(sub_p2)

        item_pen_width = getattr(target.item, "pen", lambda: QPen())().widthF()
        pen = QPen(_TRIM_COLOR, item_pen_width + _HIGHLIGHT_EXTRA_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        hi = QGraphicsPathItem()
        hi.setPath(path)
        hi.setPen(pen)
        self._show_highlight(hi)

    def _find_trim_target(self, cursor: QPointF) -> _TrimTarget | None:
        scene = self._view.scene()
        all_items = [i for i in scene.items() if _is_trimmable(i)]

        # Collect all scene-space segments with metadata
        all_segs: list[tuple[QPointF, QPointF, object, int]] = []
        for item in all_items:
            for seg_i, (p1, p2) in enumerate(_item_to_scene_segs(item)):
                all_segs.append((p1, p2, item, seg_i))

        # Find the closest segment within tolerance
        best_dist = HOVER_TOLERANCE
        best: tuple[QPointF, QPointF, object, int] | None = None
        best_t_cursor = 0.0

        for p1, p2, item, seg_i in all_segs:
            dist, t = point_to_segment_distance(cursor, p1, p2)
            if dist < best_dist:
                best_dist = dist
                best = (p1, p2, item, seg_i)
                best_t_cursor = t

        if best is None:
            return None

        p1, p2, target_item, target_seg_i = best

        # Build "other" segments (everything except the hovered segment itself)
        other_segs = [
            (q1, q2)
            for q1, q2, other_item, other_seg_i in all_segs
            if not (other_item is target_item and other_seg_i == target_seg_i)
        ]

        t_cuts = collect_intersections_on_segment(p1, p2, other_segs)
        cuts = [0.0, *t_cuts, 1.0]

        # Find the sub-interval containing the cursor projection
        t_start = 0.0
        t_end = 1.0
        for i in range(len(cuts) - 1):
            if cuts[i] <= best_t_cursor <= cuts[i + 1]:
                t_start = cuts[i]
                t_end = cuts[i + 1]
                break

        return _TrimTarget(
            item=target_item,
            seg_index=target_seg_i,
            t_start=t_start,
            t_end=t_end,
            p1_scene=p1,
            p2_scene=p2,
        )

    # ── Extend hover ──────────────────────────────────────────────────────────

    def _update_extend_highlight(self, cursor: QPointF) -> None:
        self._clear_highlight()
        target = self._find_extend_target(cursor)
        if target is None:
            return
        self._extend_target = target

        from PyQt6.QtGui import QPainterPath as _QPP

        path = _QPP()
        path.moveTo(target.origin_scene)
        path.lineTo(target.dest_scene)

        pen = QPen(_EXTEND_COLOR, _HIGHLIGHT_EXTRA_WIDTH)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        hi = QGraphicsPathItem()
        hi.setPath(path)
        hi.setPen(pen)
        self._show_highlight(hi)

    def _find_extend_target(self, cursor: QPointF) -> _ExtendTarget | None:
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

        scene = self._view.scene()
        tol = HOVER_TOLERANCE * _EXTEND_TOLERANCE_MULT

        # Find the nearest polyline endpoint within tolerance
        best_dist = tol
        best_item: PolylineItem | None = None
        best_ep_index = 0
        best_ep_scene = QPointF()
        best_dir = QPointF()

        for item in scene.items():
            if not isinstance(item, PolylineItem):
                continue
            pts = item.points
            if len(pts) < 2:
                continue
            # Start endpoint
            start_s = item.mapToScene(pts[0])
            d = math.hypot(cursor.x() - start_s.x(), cursor.y() - start_s.y())
            if d < best_dist:
                best_dist = d
                best_item = item
                best_ep_index = 0
                best_ep_scene = start_s
                # Outward direction: pts[0] → pts[1] reversed
                p1s = item.mapToScene(pts[1])
                dx = start_s.x() - p1s.x()
                dy = start_s.y() - p1s.y()
                length = math.hypot(dx, dy)
                best_dir = QPointF(dx / length, dy / length) if length > 1e-9 else QPointF(1, 0)

            # End endpoint
            end_s = item.mapToScene(pts[-1])
            d = math.hypot(cursor.x() - end_s.x(), cursor.y() - end_s.y())
            if d < best_dist:
                best_dist = d
                best_item = item
                best_ep_index = -1
                best_ep_scene = end_s
                # Outward direction: pts[-2] → pts[-1]
                p2s = item.mapToScene(pts[-2])
                dx = end_s.x() - p2s.x()
                dy = end_s.y() - p2s.y()
                length = math.hypot(dx, dy)
                best_dir = QPointF(dx / length, dy / length) if length > 1e-9 else QPointF(1, 0)

        if best_item is None:
            return None

        # Cast ray from endpoint and find nearest intersection
        dest = self._find_ray_intersection(best_ep_scene, best_dir, best_item)
        if dest is None:
            return None

        return _ExtendTarget(
            item=best_item,
            endpoint_index=best_ep_index,
            origin_scene=best_ep_scene,
            dest_scene=dest,
        )

    def _find_ray_intersection(
        self,
        origin: QPointF,
        direction: QPointF,
        exclude_item: object,
    ) -> QPointF | None:
        """Find the nearest point where a ray intersects any scene segment."""
        scene = self._view.scene()
        # Build a very long segment in the direction
        ray_len = 1e6
        ray_end = QPointF(
            origin.x() + direction.x() * ray_len,
            origin.y() + direction.y() * ray_len,
        )

        best_t: float | None = None

        for item in scene.items():
            if item is exclude_item or not _is_trimmable(item):
                continue
            for p1, p2 in _item_to_scene_segs(item):
                result = self._ray_segment_intersect(origin, ray_end, p1, p2)
                if result is not None and (best_t is None or result < best_t):
                    best_t = result

        if best_t is None:
            return None
        return interpolate(origin, ray_end, best_t)

    @staticmethod
    def _ray_segment_intersect(
        ray_o: QPointF,
        ray_e: QPointF,
        seg_p1: QPointF,
        seg_p2: QPointF,
    ) -> float | None:
        """Return the t-parameter along ray_o→ray_e where it hits seg_p1→seg_p2."""
        from open_garden_planner.core.cad_geometry import segment_segment_intersection

        result = segment_segment_intersection(ray_o, ray_e, seg_p1, seg_p2)
        if result is None:
            return None
        t_ray, _ = result
        # Require a minimum forward distance so the endpoint itself isn't a hit
        if t_ray < 1e-4:
            return None
        return t_ray

    # ── Trim execute ──────────────────────────────────────────────────────────

    def _execute_trim(self) -> bool:
        target = self._trim_target
        if target is None:
            return False

        from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

        self._clear_highlight()

        from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

        if isinstance(target.item, PolylineItem):
            self._trim_polyline(target)
        elif isinstance(target.item, PolygonItem):
            self._trim_polygon(target)
        elif isinstance(target.item, RectangleItem):
            self._trim_rectangle(target)
        return True

    def _trim_polyline(self, target: _TrimTarget) -> None:
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

        item: PolylineItem = target.item  # type: ignore[assignment]
        seg_i = target.seg_index
        pts = item.points  # item-local, copy

        cut_start_local = item.mapFromScene(
            interpolate(target.p1_scene, target.p2_scene, target.t_start)
        )
        cut_end_local = item.mapFromScene(
            interpolate(target.p1_scene, target.p2_scene, target.t_end)
        )

        # Piece A: points from start up to (and including) cut_start
        if target.t_start < 1e-6:
            # Cut starts at the very beginning of this segment
            piece_a_pts = pts[: seg_i + 1]
        else:
            piece_a_pts = pts[: seg_i + 1] + [cut_start_local]

        # Piece B: points from cut_end to the end
        if target.t_end > 1.0 - 1e-6:
            # Cut ends at the very end of this segment
            piece_b_pts = pts[seg_i + 1 :]
        else:
            piece_b_pts = [cut_end_local] + pts[seg_i + 1 :]

        new_pieces = [
            item.clone_with_points(p)
            for p in (piece_a_pts, piece_b_pts)
            if len(p) >= 2
        ]

        cmd = TrimPolylineCommand(self._view.scene(), item, new_pieces)
        self._view.command_manager.execute(cmd)

    def _trim_polygon(self, target: _TrimTarget) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

        item: PolygonItem = target.item  # type: ignore[assignment]
        seg_i = target.seg_index

        cut_start_local = item.mapFromScene(
            interpolate(target.p1_scene, target.p2_scene, target.t_start)
        )
        cut_end_local = item.mapFromScene(
            interpolate(target.p1_scene, target.p2_scene, target.t_end)
        )

        poly = item.polygon()
        n = poly.count()
        raw_verts = [poly.at(j) for j in range(n)]

        # Wrap around the perimeter excluding the trimmed segment
        piece_pts: list[QPointF] = [cut_end_local]
        idx = (seg_i + 1) % n
        while idx != seg_i:
            piece_pts.append(raw_verts[idx])
            idx = (idx + 1) % n
        piece_pts.append(cut_start_local)

        if len(piece_pts) < 2:
            return

        result_polyline = PolylineItem(
            points=piece_pts,
            object_type=ObjectType.FENCE,
        )
        result_polyline.setPen(QPen(item.pen()))
        result_polyline.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        cmd = TrimPolygonCommand(self._view.scene(), item, result_polyline)
        self._view.command_manager.execute(cmd)

    def _trim_rectangle(self, target: _TrimTarget) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
        from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

        item: RectangleItem = target.item  # type: ignore[assignment]
        seg_i = target.seg_index

        cut_start_local = item.mapFromScene(
            interpolate(target.p1_scene, target.p2_scene, target.t_start)
        )
        cut_end_local = item.mapFromScene(
            interpolate(target.p1_scene, target.p2_scene, target.t_end)
        )

        rect = item.rect()
        corners_local = [
            QPointF(rect.left(), rect.top()),
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()),
        ]
        n = len(corners_local)

        # Walk the perimeter excluding the trimmed portion, same logic as polygon trim
        piece_pts: list[QPointF] = [cut_end_local]
        idx = (seg_i + 1) % n
        while idx != seg_i:
            piece_pts.append(corners_local[idx])
            idx = (idx + 1) % n
        piece_pts.append(cut_start_local)

        if len(piece_pts) < 2:
            return

        result_polyline = PolylineItem(
            points=piece_pts,
            object_type=ObjectType.FENCE,
        )
        result_polyline.setPen(QPen(item.pen()))
        result_polyline.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        cmd = TrimRectangleCommand(self._view.scene(), item, result_polyline)
        self._view.command_manager.execute(cmd)

    # ── Extend execute ────────────────────────────────────────────────────────

    def _execute_extend(self) -> bool:
        target = self._extend_target
        if target is None:
            return False

        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

        item: PolylineItem = target.item  # type: ignore[assignment]
        new_end_local = item.mapFromScene(target.dest_scene)

        self._clear_highlight()

        cmd = ExtendPolylineCommand(item, target.endpoint_index, new_end_local)
        self._view.command_manager.execute(cmd)
        return True
