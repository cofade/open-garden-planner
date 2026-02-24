"""Polyline item for the garden canvas."""

import math
import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.object_types import (
    ObjectType,
    PathFenceStyle,
    get_path_fence_style_info,
    get_style,
)

from .garden_item import GardenItemMixin
from .resize_handle import PolylineVertexEditMixin, RotationHandleMixin


class PolylineItem(PolylineVertexEditMixin, RotationHandleMixin, GardenItemMixin, QGraphicsPathItem):
    """A polyline (open path) on the garden canvas.

    Used for fences, walls, paths, and other linear features.
    Supports selection, movement, rotation, and style presets.
    """

    def __init__(
        self,
        points: list[QPointF],
        object_type: ObjectType = ObjectType.FENCE,
        name: str = "",
        layer_id: uuid.UUID | None = None,
        path_fence_style: PathFenceStyle = PathFenceStyle.NONE,
    ) -> None:
        """Initialize the polyline item.

        Args:
            points: List of points defining the polyline
            object_type: Type of property object
            name: Optional name/label for the object
            layer_id: Layer ID this item belongs to (optional)
            path_fence_style: Visual style preset for paths/fences
        """
        GardenItemMixin.__init__(self, object_type=object_type, name=name, layer_id=layer_id)

        self._path_fence_style = path_fence_style

        # Create path from points
        path = QPainterPath()
        if points:
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)

        QGraphicsPathItem.__init__(self, path)

        self._points = points.copy()

        # Initialize rotation handle and vertex editing
        self.init_rotation_handle()
        self.init_vertex_edit()

        self._setup_styling()
        self._setup_flags()
        self.initialize_label()

    @property
    def points(self) -> list[QPointF]:
        """Get the polyline points."""
        return self._points.copy()

    @property
    def path_fence_style(self) -> PathFenceStyle:
        """Get the path/fence style preset."""
        return self._path_fence_style

    @path_fence_style.setter
    def path_fence_style(self, value: PathFenceStyle) -> None:
        """Set the path/fence style preset and update visuals."""
        self._path_fence_style = value
        if hasattr(self, 'prepareGeometryChange'):
            self.prepareGeometryChange()
        if hasattr(self, 'update'):
            self.update()

    def apply_style_preset(self) -> None:
        """Apply visual properties from the current style preset.

        Updates stroke color and width from the preset defaults.
        """
        if self._path_fence_style == PathFenceStyle.NONE:
            return
        info = get_path_fence_style_info(self._path_fence_style)
        pen = self.pen()
        pen.setColor(info.stroke_color)
        pen.setWidthF(info.stroke_width)
        self.setPen(pen)
        self._stroke_color = info.stroke_color
        self._stroke_width = info.stroke_width

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type and style preset."""
        style = get_style(self.object_type)

        pen = QPen(style.stroke_color)
        pen.setWidthF(style.stroke_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

        # Polylines typically don't have fill
        self.setBrush(QBrush(QColor(0, 0, 0, 0)))

        # Apply style preset if set
        if self._path_fence_style != PathFenceStyle.NONE:
            self.apply_style_preset()

    def _setup_flags(self) -> None:
        """Configure item interaction flags."""
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsFocusable, True)

    def boundingRect(self) -> QRectF:
        """Return bounding rect, expanded for shadow and style decorations."""
        base = super().boundingRect()
        # Extra margin for styled rendering (wider than stroke)
        style_margin = self.pen().widthF() / 2.0 + 2.0
        base = base.adjusted(-style_margin, -style_margin, style_margin, style_margin)
        m = self._shadow_margin()
        if m > 0:
            base = base.adjusted(-m, -m, m, m)
        return base

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the polyline with style-specific rendering and optional shadow."""
        # Draw shadow first
        if self._shadows_enabled:
            self._paint_shadow(painter)

        # Draw style-specific rendering
        style = self._path_fence_style
        if style == PathFenceStyle.NONE:
            super().paint(painter, option, widget)
        elif style == PathFenceStyle.GRAVEL_PATH:
            self._paint_gravel_path(painter, option)
        elif style == PathFenceStyle.STEPPING_STONES:
            self._paint_stepping_stones(painter, option)
        elif style == PathFenceStyle.PAVED_PATH:
            self._paint_paved_path(painter, option)
        elif style == PathFenceStyle.WOODEN_BOARDWALK:
            self._paint_wooden_boardwalk(painter, option)
        elif style == PathFenceStyle.DIRT_PATH:
            self._paint_dirt_path(painter, option)
        elif style == PathFenceStyle.WOODEN_FENCE:
            self._paint_wooden_fence(painter, option)
        elif style == PathFenceStyle.METAL_FENCE:
            self._paint_metal_fence(painter, option)
        elif style == PathFenceStyle.CHAIN_LINK:
            self._paint_chain_link(painter, option)
        elif style == PathFenceStyle.HEDGE_FENCE:
            self._paint_hedge_fence(painter, option)
        elif style == PathFenceStyle.STONE_WALL:
            self._paint_stone_wall(painter, option)
        else:
            super().paint(painter, option, widget)

    def _paint_shadow(self, painter: QPainter) -> None:
        """Paint drop shadow for the polyline."""
        painter.save()
        shadow_pen = QPen(self.SHADOW_COLOR)
        shadow_pen.setWidthF(self.pen().widthF())
        shadow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        shadow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(shadow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        shadow_path = self.path().translated(
            self.SHADOW_OFFSET_X, self.SHADOW_OFFSET_Y,
        )
        painter.drawPath(shadow_path)
        painter.restore()

    def _get_segment_normal(self, p1: QPointF, p2: QPointF) -> tuple[float, float]:
        """Get unit normal vector perpendicular to segment p1->p2."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 0.001:
            return (0.0, 1.0)
        return (-dy / length, dx / length)

    def _get_segment_direction(self, p1: QPointF, p2: QPointF) -> tuple[float, float]:
        """Get unit direction vector from p1 to p2."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 0.001:
            return (1.0, 0.0)
        return (dx / length, dy / length)

    # ── Path style renderers ──

    def _paint_gravel_path(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Gravel path: wide stippled stroke with border lines."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.pen().widthF()
        color = self.pen().color()

        # Wide base fill
        base_pen = QPen(QColor(color.red(), color.green(), color.blue(), 100))
        base_pen.setWidthF(width)
        base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        base_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(base_pen)
        painter.drawPath(self.path())

        # Border lines
        border_pen = QPen(QColor(color.red() - 30, color.green() - 30, color.blue() - 30))
        border_pen.setWidthF(1.0)
        for offset_sign in (-1, 1):
            offset_path = self._offset_path(width / 2.0 * offset_sign)
            if offset_path:
                painter.setPen(border_pen)
                painter.drawPath(offset_path)

        # Stipple dots along the path
        dot_pen = QPen(Qt.PenStyle.NoPen)
        painter.setPen(dot_pen)
        dot_colors = [
            QColor(color.red() + 20, color.green() + 15, color.blue() + 10),
            QColor(color.red() - 10, color.green() - 15, color.blue() - 10),
            QColor(color.red(), color.green() - 5, color.blue() + 5),
        ]
        spacing = 4.0
        for i, (pt, _dir_x, _dir_y, nx, ny) in enumerate(self._walk_path(spacing)):
            dot_color = dot_colors[i % len(dot_colors)]
            painter.setBrush(QBrush(dot_color))
            # Vary position slightly across width
            offset = ((i * 7) % 5 - 2) * width / 6.0
            cx = pt.x() + nx * offset
            cy = pt.y() + ny * offset
            r = 1.0 + (i % 3) * 0.5
            painter.drawEllipse(QPointF(cx, cy), r, r)

        painter.restore()
        self._paint_selection(painter, option)

    def _paint_stepping_stones(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Stepping stones: rounded rectangles spaced along the path."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.pen().widthF()
        color = self.pen().color()

        stone_spacing = width * 1.8
        stone_w = width * 0.8
        stone_h = width * 0.6

        for pt, dir_x, dir_y, _nx, _ny in self._walk_path(stone_spacing):
            painter.save()
            painter.translate(pt.x(), pt.y())
            angle = math.degrees(math.atan2(dir_y, dir_x))
            painter.rotate(angle)

            stone_color = QColor(
                color.red() + ((int(pt.x()) * 7) % 15 - 7),
                color.green() + ((int(pt.y()) * 11) % 15 - 7),
                color.blue() + ((int(pt.x() + pt.y()) * 13) % 15 - 7),
            )
            painter.setBrush(QBrush(stone_color))
            painter.setPen(QPen(stone_color.darker(130), 0.5))
            painter.drawRoundedRect(
                QRectF(-stone_w / 2, -stone_h / 2, stone_w, stone_h),
                2.0, 2.0,
            )
            painter.restore()

        painter.restore()
        self._paint_selection(painter, option)

    def _paint_paved_path(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Paved path: solid wide stroke with brick-like cross lines."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.pen().widthF()
        color = self.pen().color()

        # Wide base fill
        base_pen = QPen(color)
        base_pen.setWidthF(width)
        base_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        base_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(base_pen)
        painter.drawPath(self.path())

        # Cross lines (brick pattern)
        line_pen = QPen(color.darker(120))
        line_pen.setWidthF(0.5)
        painter.setPen(line_pen)

        brick_spacing = width * 0.8
        half_w = width / 2.0
        for pt, _dir_x, _dir_y, nx, ny in self._walk_path(brick_spacing):
            x1 = pt.x() + nx * half_w
            y1 = pt.y() + ny * half_w
            x2 = pt.x() - nx * half_w
            y2 = pt.y() - ny * half_w
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Border lines
        border_pen = QPen(color.darker(140))
        border_pen.setWidthF(0.8)
        painter.setPen(border_pen)
        for offset_sign in (-1, 1):
            offset_path = self._offset_path(width / 2.0 * offset_sign)
            if offset_path:
                painter.drawPath(offset_path)

        painter.restore()
        self._paint_selection(painter, option)

    def _paint_wooden_boardwalk(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Wooden boardwalk: planks across the path with gaps."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.pen().widthF()
        color = self.pen().color()

        plank_spacing = width * 0.35
        plank_w = width * 0.3
        half_w = width / 2.0

        for i, (pt, dir_x, dir_y, _nx, _ny) in enumerate(self._walk_path(plank_spacing)):
            # Alternate plank color slightly
            shade = 10 if i % 2 == 0 else -10
            plank_color = QColor(
                max(0, min(255, color.red() + shade)),
                max(0, min(255, color.green() + shade)),
                max(0, min(255, color.blue() + shade)),
            )
            painter.setBrush(QBrush(plank_color))
            painter.setPen(QPen(plank_color.darker(130), 0.5))

            # Draw plank as rotated rectangle
            painter.save()
            painter.translate(pt.x(), pt.y())
            angle = math.degrees(math.atan2(dir_y, dir_x))
            painter.rotate(angle)
            painter.drawRect(QRectF(-plank_w / 2, -half_w, plank_w, width))
            painter.restore()

        # Side rails
        rail_pen = QPen(color.darker(140))
        rail_pen.setWidthF(1.5)
        painter.setPen(rail_pen)
        for offset_sign in (-1, 1):
            offset_path = self._offset_path(half_w * offset_sign)
            if offset_path:
                painter.drawPath(offset_path)

        painter.restore()
        self._paint_selection(painter, option)

    def _paint_dirt_path(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Dirt path: soft-edged wide stroke with organic feel."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.pen().widthF()
        color = self.pen().color()

        # Soft wide base
        base_pen = QPen(QColor(color.red(), color.green(), color.blue(), 140))
        base_pen.setWidthF(width)
        base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        base_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(base_pen)
        painter.drawPath(self.path())

        # Softer outer edge
        edge_pen = QPen(QColor(color.red(), color.green(), color.blue(), 50))
        edge_pen.setWidthF(width + 3.0)
        edge_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        edge_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(edge_pen)
        painter.drawPath(self.path())

        # Core center line
        core_pen = QPen(color.darker(110))
        core_pen.setWidthF(width * 0.4)
        core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        core_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(core_pen)
        painter.drawPath(self.path())

        painter.restore()
        self._paint_selection(painter, option)

    # ── Fence style renderers ──

    def _paint_wooden_fence(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Wooden fence: posts with horizontal rails."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.pen().color()
        width = self.pen().widthF()

        # Horizontal rails (two parallel lines)
        rail_pen = QPen(color)
        rail_pen.setWidthF(1.2)
        painter.setPen(rail_pen)
        for offset_sign in (-0.3, 0.3):
            offset_path = self._offset_path(width * offset_sign)
            if offset_path:
                painter.drawPath(offset_path)

        # Fence posts
        post_spacing = width * 3.0
        post_size = width * 0.6

        painter.setPen(QPen(color.darker(130), 0.8))
        painter.setBrush(QBrush(color))

        for pt, dir_x, dir_y, _nx, _ny in self._walk_path(post_spacing):
            painter.save()
            painter.translate(pt.x(), pt.y())
            angle = math.degrees(math.atan2(dir_y, dir_x))
            painter.rotate(angle)
            painter.drawRect(QRectF(-post_size / 3, -post_size / 2, post_size / 1.5, post_size))
            painter.restore()

        painter.restore()
        self._paint_selection(painter, option)

    def _paint_metal_fence(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Metal/wrought iron fence: thin posts with decorative tops."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.pen().color()
        width = self.pen().widthF()

        # Base rail
        rail_pen = QPen(color)
        rail_pen.setWidthF(1.5)
        painter.setPen(rail_pen)
        painter.drawPath(self.path())

        # Vertical bars
        bar_spacing = width * 2.0
        bar_height = width * 2.5

        for pt, _dir_x, _dir_y, nx, ny in self._walk_path(bar_spacing):
            painter.setPen(QPen(color, 0.8))
            # Draw vertical bar (perpendicular to path)
            x1 = pt.x() + nx * bar_height / 2
            y1 = pt.y() + ny * bar_height / 2
            x2 = pt.x() - nx * bar_height / 2
            y2 = pt.y() - ny * bar_height / 2
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

            # Decorative spear top
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            tip = QPointF(x1, y1)
            painter.drawEllipse(tip, 1.2, 1.2)

        painter.restore()
        self._paint_selection(painter, option)

    def _paint_chain_link(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Chain link fence: diamond/zigzag pattern between posts."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.pen().color()
        width = self.pen().widthF()

        # Top and bottom rails
        rail_pen = QPen(color.darker(120))
        rail_pen.setWidthF(1.0)
        painter.setPen(rail_pen)
        for offset_sign in (-1, 1):
            offset_path = self._offset_path(width * offset_sign)
            if offset_path:
                painter.drawPath(offset_path)

        # Diamond/zigzag mesh pattern
        mesh_pen = QPen(QColor(color.red(), color.green(), color.blue(), 150))
        mesh_pen.setWidthF(0.5)
        painter.setPen(mesh_pen)

        mesh_spacing = width * 0.8
        half_w = width

        zigzag_up = True
        prev_pt: QPointF | None = None
        for pt, _dir_x, _dir_y, nx, ny in self._walk_path(mesh_spacing):
            offset = half_w * (0.5 if zigzag_up else -0.5)
            mesh_pt = QPointF(pt.x() + nx * offset, pt.y() + ny * offset)
            if prev_pt is not None:
                painter.drawLine(prev_pt, mesh_pt)
            prev_pt = mesh_pt
            zigzag_up = not zigzag_up

        # Posts at intervals
        post_spacing = width * 8.0
        painter.setPen(QPen(color.darker(130), 1.5))
        for pt, _dir_x, _dir_y, nx, ny in self._walk_path(post_spacing):
            x1 = pt.x() + nx * half_w
            y1 = pt.y() + ny * half_w
            x2 = pt.x() - nx * half_w
            y2 = pt.y() - ny * half_w
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        painter.restore()
        self._paint_selection(painter, option)

    def _paint_hedge_fence(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Hedge: wide organic green stroke with leaf-like bumps."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.pen().color()
        width = self.pen().widthF()

        # Wide green base
        base_pen = QPen(color)
        base_pen.setWidthF(width)
        base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        base_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(base_pen)
        painter.drawPath(self.path())

        # Leaf bumps along edges
        bump_spacing = width * 0.5
        half_w = width / 2.0
        painter.setPen(Qt.PenStyle.NoPen)

        for i, (pt, _dir_x, _dir_y, nx, ny) in enumerate(self._walk_path(bump_spacing)):
            shade = 15 if i % 2 == 0 else -15
            leaf_color = QColor(
                max(0, min(255, color.red() + shade)),
                max(0, min(255, color.green() + shade + 10)),
                max(0, min(255, color.blue() + shade)),
            )
            painter.setBrush(QBrush(leaf_color))
            # Alternate bumps on each side
            side = 1 if i % 2 == 0 else -1
            offset = half_w * 0.7 * side
            cx = pt.x() + nx * offset
            cy = pt.y() + ny * offset
            r = width * 0.25 + (i % 3) * 0.5
            painter.drawEllipse(QPointF(cx, cy), r, r * 0.8)

        painter.restore()
        self._paint_selection(painter, option)

    def _paint_stone_wall(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Stone wall: irregular stone blocks along the path."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.pen().color()
        width = self.pen().widthF()

        # Base fill
        base_pen = QPen(color)
        base_pen.setWidthF(width)
        base_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        base_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(base_pen)
        painter.drawPath(self.path())

        # Stone blocks
        stone_spacing = width * 0.6
        half_w = width / 2.0

        for i, (pt, dir_x, dir_y, nx, ny) in enumerate(self._walk_path(stone_spacing)):
            # Vary stone color
            shade = ((i * 17) % 30) - 15
            stone_color = QColor(
                max(0, min(255, color.red() + shade)),
                max(0, min(255, color.green() + shade)),
                max(0, min(255, color.blue() + shade - 5)),
            )
            painter.setBrush(QBrush(stone_color))
            painter.setPen(QPen(stone_color.darker(130), 0.5))

            # Draw stone as a slightly irregular rectangle
            stone_w = width * (0.4 + (i % 3) * 0.1)
            stone_h = width * (0.35 + (i % 2) * 0.15)
            # Offset for two rows
            row_offset = half_w * 0.3 * (1 if i % 2 == 0 else -1)

            painter.save()
            painter.translate(pt.x() + nx * row_offset, pt.y() + ny * row_offset)
            angle = math.degrees(math.atan2(dir_y, dir_x))
            painter.rotate(angle)
            painter.drawRoundedRect(
                QRectF(-stone_w / 2, -stone_h / 2, stone_w, stone_h),
                1.5, 1.5,
            )
            painter.restore()

        # Border lines
        border_pen = QPen(color.darker(140))
        border_pen.setWidthF(0.8)
        painter.setPen(border_pen)
        for offset_sign in (-1, 1):
            offset_path = self._offset_path(half_w * offset_sign)
            if offset_path:
                painter.drawPath(offset_path)

        painter.restore()
        self._paint_selection(painter, option)

    # ── Helper methods ──

    def _walk_path(self, spacing: float):
        """Walk along the polyline yielding points at regular intervals.

        Yields:
            Tuples of (point, dir_x, dir_y, normal_x, normal_y)
        """
        points = self._points
        if len(points) < 2:
            return

        dist_remaining = 0.0
        for seg_idx in range(len(points) - 1):
            p1 = points[seg_idx]
            p2 = points[seg_idx + 1]
            seg_dx = p2.x() - p1.x()
            seg_dy = p2.y() - p1.y()
            seg_len = math.hypot(seg_dx, seg_dy)
            if seg_len < 0.001:
                continue

            dir_x = seg_dx / seg_len
            dir_y = seg_dy / seg_len
            nx, ny = -dir_y, dir_x  # Normal

            t = dist_remaining
            while t <= seg_len:
                pt = QPointF(p1.x() + dir_x * t, p1.y() + dir_y * t)
                yield (pt, dir_x, dir_y, nx, ny)
                t += spacing

            dist_remaining = t - seg_len

    def _offset_path(self, offset: float) -> QPainterPath | None:
        """Create an offset path parallel to the polyline.

        Args:
            offset: Perpendicular offset distance (positive = left of direction)

        Returns:
            Offset QPainterPath, or None if not enough points
        """
        points = self._points
        if len(points) < 2:
            return None

        path = QPainterPath()
        first = True
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            nx, ny = self._get_segment_normal(p1, p2)
            op1 = QPointF(p1.x() + nx * offset, p1.y() + ny * offset)
            op2 = QPointF(p2.x() + nx * offset, p2.y() + ny * offset)
            if first:
                path.moveTo(op1)
                first = False
            else:
                path.lineTo(op1)
            path.lineTo(op2)
        return path

    def _paint_selection(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Draw selection highlight if the item is selected."""
        from PyQt6.QtWidgets import QStyle
        if option.state & QStyle.StateFlag.State_Selected:
            painter.save()
            sel_pen = QPen(QColor(0, 120, 215), 1.0, Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
            painter.restore()

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: Any,
    ) -> Any:
        """Handle item state changes.

        Shows/hides rotation handle based on selection state.
        Exits vertex edit mode when deselected.
        Updates annotations when position changes.
        """
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value:  # Being selected
                if not self.is_vertex_edit_mode:
                    self.show_rotation_handle()
            else:  # Being deselected
                if self.is_vertex_edit_mode:
                    self.exit_vertex_edit_mode()
                self.hide_rotation_handle()
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.is_vertex_edit_mode:
            self._update_annotations()

        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle double-click to enter vertex edit mode and start label edit."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.is_vertex_edit_mode:
                self.enter_vertex_edit_mode()
            self.start_label_edit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key presses - Escape exits vertex edit mode."""
        if event.key() == Qt.Key.Key_Escape and self.is_vertex_edit_mode:
            self.exit_vertex_edit_mode()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _on_rotation_end(self, initial_angle: float) -> None:
        """Called when rotation operation completes. Registers undo command."""
        scene = self.scene()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        # Get current angle
        current_angle = self.rotation_angle

        # Only register command if angle actually changed
        if abs(initial_angle - current_angle) < 0.01:
            return

        from open_garden_planner.core.commands import RotateItemCommand

        def apply_rotation(item: QGraphicsItem, angle: float) -> None:
            """Apply rotation to the item."""
            if isinstance(item, PolylineItem):
                item._apply_rotation(angle)

        command = RotateItemCommand(
            self,
            initial_angle,
            current_angle,
            apply_rotation,
        )

        # Add to undo stack without executing (rotation already applied)
        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show context menu on right-click."""
        # Select this item if not already selected
        if not self.isSelected():
            self.scene().clearSelection()
            self.setSelected(True)

        menu = QMenu()

        # Edit vertices action
        if self.is_vertex_edit_mode:
            exit_edit_action = menu.addAction("Exit Vertex Edit Mode")
            edit_vertices_action = None
        else:
            edit_vertices_action = menu.addAction("Edit Vertices")
            exit_edit_action = None

        # Edit label action
        edit_label_action = menu.addAction("Edit Label")

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction("Delete")

        menu.addSeparator()

        # Duplicate action
        duplicate_action = menu.addAction("Duplicate")

        # Linear array action
        linear_array_action = menu.addAction("Create Linear Array...")

        # Grid array action
        grid_array_action = menu.addAction("Create Grid Array...")

        # Execute menu and handle result
        action = menu.exec(event.screenPos())

        if action == edit_vertices_action and edit_vertices_action is not None:
            # Enter vertex edit mode and switch to Select tool
            self.enter_vertex_edit_mode()
            self.setFocus()
            scene = self.scene()
            if scene:
                for v in scene.views():
                    if hasattr(v, "_tool_manager"):
                        from open_garden_planner.core.tools import ToolType
                        v._tool_manager.set_active_tool(ToolType.SELECT)
                        break
        elif action == exit_edit_action and exit_edit_action is not None:
            self.exit_vertex_edit_mode()
        elif action == edit_label_action:
            self.start_label_edit()
        elif action == delete_action:
            # Delete this item and any other selected items
            scene = self.scene()
            for item in scene.selectedItems():
                scene.removeItem(item)
        elif action == duplicate_action:
            # Duplicate via canvas view
            scene = self.scene()
            if scene:
                views = scene.views()
                if views:
                    view = views[0]
                    if hasattr(view, "duplicate_selected"):
                        view.duplicate_selected()
        elif action == linear_array_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views:
                    view = views[0]
                    if hasattr(view, "create_linear_array"):
                        view.create_linear_array()
        elif action == grid_array_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views:
                    view = views[0]
                    if hasattr(view, "create_grid_array"):
                        view.create_grid_array()
