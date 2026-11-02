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
on its 12 cm posts. The colours are the 3D builder's (``builders.palette``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

from open_garden_planner.core.scene3d.builders import palette
from open_garden_planner.core.string_lights import Layout, layout

#: Radius of a bulb's glow, of the bulb, and the wire's width — shares of the stroke width.
GLOW_SHARE: Final = 0.92
BULB_SHARE: Final = 0.27
WIRE_SHARE: Final = 0.12
#: The post's side, as a share of the stroke width; its corner radius, of its side.
POST_SHARE: Final = 1.0
POST_ROUND: Final = 0.18
#: The colour of the glow at its centre (alpha: how strong).
_GLOW: Final = QColor(255, 206, 120, 180)


def _colour(swatch: palette.PaletteColor) -> QColor:
    return QColor(*swatch.srgb)


def reach(width: float) -> float:
    """How far the picture reaches beyond the line: a glow's radius or half a post,
    whichever is larger."""
    return max(GLOW_SHARE, POST_SHARE / 2.0) * max(width, 0.0)


def string_layout(points: Sequence[QPointF]) -> Layout:
    """The layout of a line given as ``QPointF``s (its item-local points)."""
    return layout([(p.x(), p.y()) for p in points])


def paint_string_lights(painter: QPainter, points: Sequence[QPointF], width: float,
                        wire: QColor) -> None:
    """Paint a string drawn through ``points`` (item-local cm) with the stroke
    ``width`` and the wire colour ``wire`` (the line's pen colour)."""
    lay = string_layout(points)
    w = width if width > 0.0 else 12.0
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    bulbs = lay.bulbs_xy()
    glow = GLOW_SHARE * w
    painter.setPen(Qt.PenStyle.NoPen)
    for x, y in bulbs:
        gradient = QRadialGradient(QPointF(x, y), glow)
        gradient.setColorAt(0.0, _GLOW)
        gradient.setColorAt(1.0, QColor(_GLOW.red(), _GLOW.green(), _GLOW.blue(), 0))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(x, y), glow, glow)
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
    bulb = BULB_SHARE * w
    painter.setPen(QPen(_colour(palette.CANVAS_CREAM_DARK), 0.12 * bulb))
    painter.setBrush(_colour(palette.CANVAS_CREAM))
    for x, y in bulbs:
        painter.drawEllipse(QPointF(x, y), bulb, bulb)
    side = POST_SHARE * w
    painter.setPen(QPen(_colour(palette.GREY_WOOD_DARK), 0.1 * side))
    painter.setBrush(_colour(palette.GREY_WOOD))
    for x, y in lay.posts:
        rect = QRectF(x - side / 2.0, y - side / 2.0, side, side)
        painter.drawRoundedRect(rect, POST_ROUND * side, POST_ROUND * side)
    painter.restore()
