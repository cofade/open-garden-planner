"""The 2D picture of a pergola (#769) — one painter, one layout.

A pergola is four posts carrying a perimeter of beams, nine rafters across the
depth and five purlins on top. The canvas, the gallery thumbnail and the 3D
builder all read the SAME layout (``core.pergola``), so the picture cannot drift
from the model: the posts are at the posts' places, the rafters at the rafters'.

The picture is drawn in the item's own frame, centred on its rectangle. The
colours are the 3D builder's (``builders.palette``): dark oak posts, mid oak
beams and rafters, light oak purlins. Nothing is stretched from a fixed sprite;
the members keep their real widths (14 cm posts, 8 cm rafters) however large the
footprint is, and every one is bounded (``core.pergola``).
"""

from __future__ import annotations

from typing import Final

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap

from open_garden_planner.core.pergola import PergolaLayout
from open_garden_planner.core.pergola import layout as pergola_layout
from open_garden_planner.core.scene3d.builders import palette

#: Gallery and properties-panel thumbnail size.
THUMB_SIZE: Final = 64
#: The footprint the thumbnail draws, in cm (the old sprite's proportions).
THUMB_WIDTH_CM: Final = 400.0
THUMB_DEPTH_CM: Final = 300.0
#: The thumbnail's height: the item's default (``object_height.DEFAULT_HEIGHTS_CM``).
THUMB_HEIGHT_CM: Final = 250.0

_POST = QColor(*palette.PLANK_GROOVE.srgb)
_BEAM = QColor(*palette.PLANK.srgb)
_RAFTER = QColor(*palette.OAK_LIGHT.srgb)
_EDGE = QColor(70, 45, 20)


def _member(painter: QPainter, x0: float, y0: float, x1: float, y1: float,
            fill: QColor, edge: QColor, width: float) -> None:
    painter.setBrush(fill)
    painter.setPen(QPen(edge, max(0.25, width)))
    painter.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))


def paint_pergola(painter: QPainter, rect: QRectF, height_cm: float) -> bool:
    """Paint a pergola into *rect* (the item's own rectangle, in cm).

    Returns False — nothing painted — when the rectangle or the height cannot
    make a layout (a degenerate size), so the caller can fall back to a plain
    fill. The painter is left as it was found.
    """
    plan = pergola_layout(rect.width(), rect.height(), height_cm)
    if plan is None:
        return False
    painter.save()
    painter.translate(rect.center())
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _paint_members(painter, plan)
    painter.restore()
    return True


def _paint_members(painter: QPainter, plan: PergolaLayout) -> None:
    """Draw the layout's members in the order they stack: posts, beams, rafters,
    purlins (the purlins are on top, as in 3D)."""
    edge = max(0.2, min(0.9, 0.06 * plan.post))
    for member in plan.posts:
        _member(painter, member.x0, member.y0, member.x1, member.y1, _POST, _EDGE, edge)
    for member in plan.beams:
        _member(painter, member.x0, member.y0, member.x1, member.y1, _BEAM, _EDGE, edge)
    for member in plan.rafters:
        _member(painter, member.x0, member.y0, member.x1, member.y1, _BEAM, _EDGE, edge)
    for member in plan.purlins:
        _member(painter, member.x0, member.y0, member.x1, member.y1, _RAFTER, _BEAM, edge)


def render_pergola_thumbnail(size: int = THUMB_SIZE) -> QPixmap:
    """A pergola for the gallery and the properties panel: the canvas's own
    painter at the item's default proportions, fitted into the square."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    margin = 0.06 * size
    scale = min((size - 2.0 * margin) / THUMB_WIDTH_CM,
                (size - 2.0 * margin) / THUMB_DEPTH_CM)
    painter.translate(size / 2.0, size / 2.0)
    painter.scale(scale, scale)
    plan = pergola_layout(THUMB_WIDTH_CM, THUMB_DEPTH_CM, THUMB_HEIGHT_CM)
    if plan is not None:
        _paint_members(painter, plan)
    painter.end()
    return QPixmap.fromImage(image)
