"""How a styled path or fence line is painted — from plain values.

The ten style painters of ``PolylineItem`` (gravel path, stepping stones, paved
path, boardwalk, dirt path; wooden, metal and chain-link fence, hedge, stone
wall), moved here unchanged so that ONE implementation serves two callers:

- ``PolylineItem.paint`` for the live canvas item, and
- the 3D ground bake (``ui/view3d/ground_bake.py``, Phase 17 L1.5), which paints
  a path from a scene record and must not touch the live scene.

A painter reads three things and nothing else: the polyline's points in the
ITEM's own coordinates (two styles derive a colour from them), its pen (width
and colour) and its path. Selection is the item's own business and is drawn by
the item, after the style.

WHAT A STYLE COSTS, AND ITS BOUND. A style draws ELEMENTS along the line —
stones, planks, posts, bars, dots — one every ``spacing``: their number is the
line's LENGTH over the spacing, whatever its vertex count (two points a
kilometre apart are 25,000 gravel dots). The canvas item paints them all, as it
always has. A caller that paints a line into a small window — the ground bake,
one tile at a time — passes that window as ``clip`` and a ``WalkBudget`` that
ALL the paths of the window share:

- only the elements inside ``clip`` are generated. Segments outside it are
  stepped over by arithmetic, a long segment is entered at its first element
  inside — and every element keeps its GLOBAL index and its place on the line,
  so the pattern's phase is the canvas's and two neighbouring windows meet
  without a seam;
- what is bounded is the WORK, not what comes out of it. A segment may be
  walked with the canvas's own running sum (element for element the same
  floats) — and every STEP of that walk, inside the clip or not, is charged to
  the budget's ``steps`` before it is taken; a segment the budget does not
  cover is entered by multiplication instead (the same places to a few units in
  the last place), which costs only what it hands out;
- every element handed out is charged to the budget's ``elements``; when they
  are spent the walk stops and ``truncated`` says so. A budget of zero is a
  budget: nothing is handed out.

A spacing outside ``MIN_SPACING_CM`` … ``MAX_SPACING_CM`` — a pen width of
1e-300, of zero, of infinity, a NaN — draws no elements at all (zero used to
never return): elements closer than half a millimetre are no pattern, and the
arithmetic above is only ever done with numbers from that range.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Final

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from open_garden_planner.core.object_types import PathFenceStyle

#: The spacings a style draws elements at, in cm (module docstring). The smallest a
#: preset pen gives is 0.35 cm x its width; 0.05 cm is a pen of 1.4 mm.
MIN_SPACING_CM: Final = 0.05
MAX_SPACING_CM: Final = 1e7

# Shared by canvas cache containment and ground tile admission (#471).
_STYLE_MITRE_LIMIT: Final = float(QPen().miterLimit())


def style_paint_reach(width_cm: float) -> float:
    """Conservative cm beyond the centre-line box, including fixed decorations.

    Metal bars reach 1.25 widths plus a 1.2 cm tip. Acute mitred joins can reach
    Qt's default mitre limit in widths; 4 cm also covers fixed pens and bumps.
    Raster consumers add their own pixel-spill allowance.
    """
    return max(1.5, _STYLE_MITRE_LIMIT) * width_cm + 4.0


class WalkBudget:
    """What the clipped walks of ONE window — a ground tile — may still cost, all
    its paths together (module docstring).

    ``elements``: elements that may still be handed out. ``steps``: steps of the
    exact, summing walk that may still be taken. ``dashes``: dashes of dashed
    pens that may still be stroked (the ground bake charges them; this module
    draws none). All only ever go down; ``elements_spent`` / ``steps_spent`` /
    ``dashes_spent`` count what was used, ``truncated`` says that a walk had to
    stop for want of elements, or a dashed stroke for want of dashes.
    """

    __slots__ = ("dashes", "dashes_spent", "elements", "elements_spent", "steps", "steps_spent",
                 "truncated")

    def __init__(self, elements: int, steps: int, dashes: int = 0) -> None:
        if elements < 0 or steps < 0 or dashes < 0:
            raise ValueError(f"a budget is not negative, got {elements} elements, {steps} steps, "
                             f"{dashes} dashes")
        self.elements = elements
        self.steps = steps
        self.dashes = dashes
        self.elements_spent = 0
        self.steps_spent = 0
        self.dashes_spent = 0
        self.truncated = False

    def take_element(self) -> bool:
        """Charge one element; False — nothing charged — when none is left."""
        if self.elements <= 0:
            self.truncated = True
            return False
        self.elements -= 1
        self.elements_spent += 1
        return True

    def take_steps(self, count: int) -> bool:
        """Charge ``count`` steps of an exact walk, all or none: False when the
        budget does not cover them (the segment is then entered by arithmetic)."""
        if count > self.steps:
            return False
        self.steps -= count
        self.steps_spent += count
        return True

    def take_dashes(self, count: int) -> bool:
        """Charge ``count`` dashes of one dashed stroke, all or none: False — nothing
        charged, ``truncated`` set — when the budget does not cover them (the
        stroke is then drawn solid)."""
        if count > self.dashes:
            self.truncated = True
            return False
        self.dashes -= count
        self.dashes_spent += count
        return True

#: A caller that paints a whole scene into a SMALL surface (the minimap) may
#: cap every styled walk for the duration of that render. The cap applies only
#: to non-interactive paints; exports that want full detail do not set it.
_RENDER_WALK_CAP: ContextVar[tuple[int, int, int] | None] = ContextVar(
    "ogp_page_walk_cap", default=None
)


@contextmanager
def temporary_walk_cap(
    elements: int = 4_096, steps: int = 8_192, dashes: int = 8_192
) -> Iterator[None]:
    """Bound styled-path walks for a whole-scene render into a small image.

    The minimap renders the entire plan into 240 x 160 px every 100 ms; walking
    a 19 km path's 475 001 elements there is pure waste. The cap keeps the
    pattern visible near the start of the line and truncates the rest, while a
    normal export (no context) still gets every element. Each styled item gets
    a FRESH budget from these limits, so a second path is not starved by the
    first one's elements.
    """
    token = _RENDER_WALK_CAP.set((elements, steps, dashes))
    try:
        yield
    finally:
        _RENDER_WALK_CAP.reset(token)


def current_render_walk_cap() -> WalkBudget | None:
    """A fresh whole-scene render budget for one item, or None for an ordinary paint."""
    limits = _RENDER_WALK_CAP.get()
    return None if limits is None else WalkBudget(*limits)


Element = tuple[QPointF, float, float, float, float]
"""``(point, dir_x, dir_y, normal_x, normal_y)`` — one place along the line."""


def segment_inside(px: float, py: float, dir_x: float, dir_y: float, length: float,
                   clip: tuple[float, float, float, float]) -> tuple[float, float] | None:
    """The part ``[t0, t1]`` of the segment ``p + dir · t``, ``0 <= t <= length``,
    that lies inside the box ``clip`` (x0, y0, x1, y1) — None when none does."""
    t0, t1 = 0.0, length
    for origin, direction, low, high in ((px, dir_x, clip[0], clip[2]),
                                         (py, dir_y, clip[1], clip[3])):
        if direction == 0.0:
            if not low <= origin <= high:
                return None
            continue
        first, second = (low - origin) / direction, (high - origin) / direction
        if first > second:
            first, second = second, first
        t0, t1 = max(t0, first), min(t1, second)
        if t0 > t1:
            return None
    return (t0, t1)


class PathStylePaint:
    """Paints one polyline in a path / fence style (module docstring).

    ``points``: the polyline in item coordinates. ``pen``: the item's pen.
    ``path``: the item's path through those points (built from them when not
    given). ``clip``: the window ``(x0, y0, x1, y1)``, in item coordinates, outside
    of which no element need be generated — the caller grows it by an element's
    reach; None (the canvas item) generates them all. ``budget``: what the walks
    of that window may cost, shared by its paths (``WalkBudget``; required with a
    clip — a clipped walk without a bound is the thing this module prevents).
    """

    def __init__(self, points: Sequence[QPointF], pen: QPen,
                 path: QPainterPath | None = None, *,
                 clip: tuple[float, float, float, float] | None = None,
                 budget: WalkBudget | None = None) -> None:
        if (clip is None) != (budget is None):
            raise ValueError("a clipped walk needs a budget, and a budget a clip")
        # read only, never changed: the canvas item's own list is used as it is (this
        # object lives for one paint)
        self._points = points if isinstance(points, list) else list(points)
        self._pen = pen
        self._clip = clip
        self._budget = budget
        if path is None:
            path = QPainterPath()
            if self._points:
                path.moveTo(self._points[0])
                for point in self._points[1:]:
                    path.lineTo(point)
        self._path = path

    def pen(self) -> QPen:
        return self._pen

    def path(self) -> QPainterPath:
        return self._path

    def paint(self, painter: QPainter, style: PathFenceStyle) -> bool:
        """Paint the polyline in ``style``. False — and nothing painted — for
        ``PathFenceStyle.NONE`` and for a style without a painter of its own: the
        caller then strokes the plain path. (A caller that paints often asks
        ``STYLES_PAINTED`` first and builds no object for a plain line.)"""
        style_painter = _STYLE_PAINTERS.get(style)
        if style_painter is None:
            return False
        style_painter(self, painter)
        return True

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

    def _paint_gravel_path(self, painter: QPainter) -> None:
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
        for i, (pt, _dir_x, _dir_y, nx, ny) in self._walk_indexed(spacing):
            dot_color = dot_colors[i % len(dot_colors)]
            painter.setBrush(QBrush(dot_color))
            # Vary position slightly across width
            offset = ((i * 7) % 5 - 2) * width / 6.0
            cx = pt.x() + nx * offset
            cy = pt.y() + ny * offset
            r = 1.0 + (i % 3) * 0.5
            painter.drawEllipse(QPointF(cx, cy), r, r)

        painter.restore()

    def _paint_stepping_stones(self, painter: QPainter) -> None:
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

    def _paint_paved_path(self, painter: QPainter) -> None:
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

    def _paint_wooden_boardwalk(self, painter: QPainter) -> None:
        """Wooden boardwalk: planks across the path with gaps."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.pen().widthF()
        color = self.pen().color()

        plank_spacing = width * 0.35
        plank_w = width * 0.3
        half_w = width / 2.0

        for i, (pt, dir_x, dir_y, _nx, _ny) in self._walk_indexed(plank_spacing):
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
        # … stroked, not filled. Without this the rails were drawn with the brush the LAST
        # plank left behind: Qt fills an open path as if it were closed, so a path with
        # a bend got a patch in that plank's colour between its rail and the rail's
        # chord — over its own planks (found by L1.5's parity test: the patch's colour
        # depends on the last element, which a tile does not always draw).
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rail_pen = QPen(color.darker(140))
        rail_pen.setWidthF(1.5)
        painter.setPen(rail_pen)
        for offset_sign in (-1, 1):
            offset_path = self._offset_path(half_w * offset_sign)
            if offset_path:
                painter.drawPath(offset_path)

        painter.restore()

    def _paint_dirt_path(self, painter: QPainter) -> None:
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

    # ── Fence style renderers ──

    def _paint_wooden_fence(self, painter: QPainter) -> None:
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

    def _paint_metal_fence(self, painter: QPainter) -> None:
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

    def _paint_chain_link(self, painter: QPainter) -> None:
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

        # the zigzag by the element's INDEX (up on even ones), a line only between two
        # neighbours: a clipped walk leaves elements out, and must neither flip the
        # zigzag nor span the gap
        prev_pt: QPointF | None = None
        prev_index = -2
        for i, (pt, _dir_x, _dir_y, nx, ny) in self._walk_indexed(mesh_spacing):
            offset = half_w * (0.5 if i % 2 == 0 else -0.5)
            mesh_pt = QPointF(pt.x() + nx * offset, pt.y() + ny * offset)
            if prev_pt is not None and i == prev_index + 1:
                painter.drawLine(prev_pt, mesh_pt)
            prev_pt = mesh_pt
            prev_index = i

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

    def _paint_hedge_fence(self, painter: QPainter) -> None:
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

        for i, (pt, _dir_x, _dir_y, nx, ny) in self._walk_indexed(bump_spacing):
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

    def _paint_stone_wall(self, painter: QPainter) -> None:
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

        for i, (pt, dir_x, dir_y, nx, ny) in self._walk_indexed(stone_spacing):
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
        # … stroked, not filled. Without this the borders were drawn with the brush the LAST
        # stone left behind: Qt fills an open path as if it were closed, so a path with
        # a bend got a patch in that stone's colour between its border and the border's
        # chord — over its own stones (found by L1.5's parity test: the patch's colour
        # depends on the last element, which a tile does not always draw).
        painter.setBrush(Qt.BrushStyle.NoBrush)
        border_pen = QPen(color.darker(140))
        border_pen.setWidthF(0.8)
        painter.setPen(border_pen)
        for offset_sign in (-1, 1):
            offset_path = self._offset_path(half_w * offset_sign)
            if offset_path:
                painter.drawPath(offset_path)

        painter.restore()

    # ── Helper methods ──

    def _walk_path(self, spacing: float) -> Iterator[Element]:
        """Walk along the polyline yielding points at regular intervals.

        Yields:
            Tuples of (point, dir_x, dir_y, normal_x, normal_y)
        """
        for _index, element in self._walk_indexed(spacing):
            yield element

    def _walk_indexed(self, spacing: float) -> Iterator[tuple[int, Element]]:
        """``_walk_path`` with every element's index along the WHOLE line — what a
        style alternates its colours by. Without a clip: every element, by the
        running sum the painters have always used. With one: only the elements
        inside it (module docstring), their indices unchanged.
        """
        points = self._points
        if len(points) < 2 or not MIN_SPACING_CM <= spacing <= MAX_SPACING_CM:  # a NaN too
            return
        clip = self._clip
        budget = self._budget

        index = 0
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
            if clip is None:
                while t <= seg_len:
                    pt = QPointF(p1.x() + dir_x * t, p1.y() + dir_y * t)
                    yield index, (pt, dir_x, dir_y, nx, ny)
                    index += 1
                    t += spacing
            elif budget is not None and t <= seg_len:
                count = int((seg_len - t) // spacing) + 1  # the elements this segment holds
                span = segment_inside(p1.x(), p1.y(), dir_x, dir_y, seg_len, clip)
                if budget.take_steps(count):
                    # the canvas's own walk, sum for sum — ALL its steps were just paid
                    # for, also those of a segment outside the clip (its running sum is
                    # what the next segment starts from); only what is inside is handed out
                    while t <= seg_len:
                        if span is not None and span[0] <= t <= span[1]:
                            if not budget.take_element():
                                return
                            pt = QPointF(p1.x() + dir_x * t, p1.y() + dir_y * t)
                            yield index, (pt, dir_x, dir_y, nx, ny)
                        index += 1
                        t += spacing
                else:
                    if span is not None:  # entered at its first element inside, by arithmetic
                        step = max(0, math.ceil((span[0] - t) / spacing))
                        last = min(count - 1, math.floor((span[1] - t) / spacing))
                        while step <= last:
                            if not budget.take_element():
                                return
                            at = t + step * spacing
                            pt = QPointF(p1.x() + dir_x * at, p1.y() + dir_y * at)
                            yield index + step, (pt, dir_x, dir_y, nx, ny)
                            step += 1
                    index += count
                    t += count * spacing

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


#: The painter of each style — built once, not per paint.
_STYLE_PAINTERS: Final[dict[PathFenceStyle, Callable[[PathStylePaint, QPainter], None]]] = {
    PathFenceStyle.GRAVEL_PATH: PathStylePaint._paint_gravel_path,
    PathFenceStyle.STEPPING_STONES: PathStylePaint._paint_stepping_stones,
    PathFenceStyle.PAVED_PATH: PathStylePaint._paint_paved_path,
    PathFenceStyle.WOODEN_BOARDWALK: PathStylePaint._paint_wooden_boardwalk,
    PathFenceStyle.DIRT_PATH: PathStylePaint._paint_dirt_path,
    PathFenceStyle.WOODEN_FENCE: PathStylePaint._paint_wooden_fence,
    PathFenceStyle.METAL_FENCE: PathStylePaint._paint_metal_fence,
    PathFenceStyle.CHAIN_LINK: PathStylePaint._paint_chain_link,
    PathFenceStyle.HEDGE_FENCE: PathStylePaint._paint_hedge_fence,
    PathFenceStyle.STONE_WALL: PathStylePaint._paint_stone_wall,
}

#: The styles ``PathStylePaint.paint`` paints. Every other one — ``NONE`` first of all,
#: the plain line — is the caller's own stroke, and needs no ``PathStylePaint`` at all.
STYLES_PAINTED: Final[frozenset[PathFenceStyle]] = frozenset(_STYLE_PAINTERS)
