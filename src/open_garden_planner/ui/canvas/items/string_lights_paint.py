"""The 2D picture of a string of lights (Phase 17 L5.4, #389; ADR-070 addendum).

Seen from above: a dark wire along the line, a warm glowing bulb wherever
``core/string_lights.layout`` hangs one, and a slim wooden post at every point of the
line — the same posts and bulbs the 3D builder builds (``core/scene3d/builders/
lights.py``). One painter: the canvas item (``PolylineItem``) and the gallery's
picture both draw with it.

A string is a line, not an area: nothing here is stretched to fit a box. The sizes
follow the line's stroke width ``w`` (``STRING_LIGHTS``' style: 12 cm, the post's
side): the glow is ``GLOW_SHARE · w`` round a bulb, the bulb ``BULB_SHARE · w``, the
wire ``WIRE_SHARE · w`` — the first sprite's 11 cm glow, 3.2 cm bulb and 1.4 cm wire
on its 12 cm posts. The width sizes this SYMBOL only, as a fence's stroke does: the 3D
model builds real 4 cm posts and 2.6 cm bulbs (``builders/lights.py``) at the same
places. The colours are the 3D builder's (``builders.palette``).

The symbol's post is much wider than the 3D one (a full stroke width against 4 cm), so
the layout's 6 cm clearance is not enough to keep a bulb off the picture's post. Two
rules keep the bulb visible: the drawn post's side is capped at twice the clearance, and
the wire and posts are painted BEFORE the bulbs, so a clamped bulb reads on top of the
post instead of being bitten in half (senior review round 12).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

from open_garden_planner.core.scene3d.builders import palette
from open_garden_planner.core.string_lights import POST_CLEAR_CM, Layout, layout

#: Radius of a bulb's glow, of the bulb, and the wire's width — shares of the stroke width.
GLOW_SHARE: Final = 0.92
BULB_SHARE: Final = 0.27
WIRE_SHARE: Final = 0.12
#: The post's side, as a share of the stroke width; its corner radius, of its side.
POST_SHARE: Final = 1.0
POST_ROUND: Final = 0.18
#: The colour of the glow at its centre (alpha: how strong).
_GLOW: Final = QColor(255, 206, 120, 180)
#: The width a string is drawn at when its line has none (a stroke width of 0, which a
#: file may hold): ``STRING_LIGHTS``' style.
DEFAULT_WIDTH: Final = 12.0


def _colour(swatch: palette.PaletteColor) -> QColor:
    return QColor(*swatch.srgb)


def drawn_width(width: float) -> float:
    """The width a line of stroke ``width`` is drawn at — ``DEFAULT_WIDTH`` for none.
    ``reach`` and the paint both read it: an item's bounds that assumed another width
    than its paint clipped the glow and left trails behind a move."""
    return width if math.isfinite(width) and width > 0.0 else DEFAULT_WIDTH


def drawn_post_side(width: float) -> float:
    """The side a post is drawn at: ``POST_SHARE`` of the stroke width, capped at
    ``2 * POST_CLEAR_CM`` so a widened stroke cannot swallow the bulbs the layout keeps
    6 cm clear (a 24 cm stroke's 12 cm half-side buried 96 % of a clamped ball)."""
    return min(POST_SHARE * drawn_width(width), 2.0 * POST_CLEAR_CM)


def reach(width: float) -> float:
    """How far the picture reaches beyond the line: a glow's radius or half a post,
    whichever is larger."""
    return max(GLOW_SHARE * drawn_width(width), drawn_post_side(width) / 2.0)


def string_layout(points: Sequence[QPointF]) -> Layout:
    """The layout of a line given as ``QPointF``s (its item-local points)."""
    return layout([(p.x(), p.y()) for p in points])


def paint_string_lights(painter: QPainter, lay: Layout, width: float, wire: QColor) -> None:
    """Paint a string laid out as ``lay`` (item-local cm; ``string_layout`` — the item
    keeps it, a paint never walks the line) with the stroke ``width`` and the wire colour
    ``wire`` (the line's pen colour). At most ``MAX_POSTS`` posts and ``MAX_BULBS_PER_STRING``
    bulbs: bounded whatever the line."""
    w = drawn_width(width)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    bulbs = lay.bulbs_xy()
    # 1. the wire, 2. the posts — both UNDER the bulbs. A bulb kept 6 cm from a post's
    #    centre still overlaps the symbol's much wider post; painted last it read as
    #    buried (59 % of the ball at the default width, 96 % at 24 cm).
    if lay.spans:
        pen = QPen(wire, WIRE_SHARE * w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        for span in lay.spans:
            (ax, ay), (bx, by) = lay.posts[span.a], lay.posts[span.b]
            path.moveTo(ax, ay)
            path.lineTo(bx, by)
        painter.drawPath(path)
    side = drawn_post_side(width)
    painter.setPen(QPen(_colour(palette.GREY_WOOD_DARK), 0.1 * side))
    painter.setBrush(_colour(palette.GREY_WOOD))
    for x, y in lay.posts:
        rect = QRectF(x - side / 2.0, y - side / 2.0, side, side)
        painter.drawRoundedRect(rect, POST_ROUND * side, POST_ROUND * side)
    # 3. the glow and the bulbs, on top of the post
    glow = GLOW_SHARE * w
    painter.setPen(Qt.PenStyle.NoPen)
    for x, y in bulbs:
        gradient = QRadialGradient(QPointF(x, y), glow)
        gradient.setColorAt(0.0, _GLOW)
        gradient.setColorAt(1.0, QColor(_GLOW.red(), _GLOW.green(), _GLOW.blue(), 0))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(x, y), glow, glow)
    bulb = BULB_SHARE * w
    painter.setPen(QPen(_colour(palette.CANVAS_CREAM_DARK), 0.12 * bulb))
    painter.setBrush(_colour(palette.CANVAS_CREAM))
    for x, y in bulbs:
        painter.drawEllipse(QPointF(x, y), bulb, bulb)
    painter.restore()
