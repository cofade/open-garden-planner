"""The 2D picture of a greenhouse (#768) — glass plus aluminium glazing bars.

A glasshouse is a first-class building now: its plan is the item's own polygon
(a rectangle or a free outline), its glass is the ``GLASS`` fill pattern, and
this module draws the frame over it — the bars the 3D builder puts at every
glazing bay (``core.greenhouse.bay_count``), two rails parallel to the ridge at
half the roof's reach on each side, and the anodised-aluminium ridge cap itself.

The ridge is the plan's ridge: the linked ``ROOF_RIDGE`` when the item has one,
else ``core.roof_ridge``'s canonical long-axis line. The caller supplies it in
the item's local frame (the canvas and every export paint through the same
one), so a rotated glasshouse's bars turn with it.
"""

from __future__ import annotations

import math
from typing import Final

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from open_garden_planner.core.greenhouse import (
    RIDGE_ALUMINIUM_HEX,
    RIDGE_ALUMINIUM_SHADOW_HEX,
    bay_count,
)
from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints

#: Anodised aluminium (#768): the bar's body and its shadowed edge.
ALUMINIUM: Final = QColor(RIDGE_ALUMINIUM_HEX)
ALUMINIUM_DARK: Final = QColor(RIDGE_ALUMINIUM_SHADOW_HEX)
#: A bar's width as a share of the outline's shorter side, held to a readable band.
BAR_SHARE: Final = 0.018
BAR_MIN_CM: Final = 0.7
BAR_MAX_CM: Final = 3.2


def _ridge_of(polygon: QPolygonF) -> tuple[QPointF, QPointF] | None:
    """The plan's ridge in the polygon's own frame (the canonical long axis)."""
    if polygon.count() < 3:
        return None
    first, second = compute_roof_ridge_endpoints(polygon, QPointF(0.0, 0.0))
    return QPointF(first), QPointF(second)


def paint_greenhouse(
    painter: QPainter,
    polygon: QPolygonF,
    pen: QPen,
    ridge: tuple[QPointF, QPointF] | None = None,
) -> None:
    """Draw a greenhouse's glazing bars and ridge cap over its already-filled plan.

    The caller fills and strokes the outline (``RectangleItem.paint`` /
    ``PolygonItem.paint`` call this after their normal paint) and supplies the
    linked ridge in the item's LOCAL frame when the plan has one; without it the
    canonical long-axis ridge is used. Nothing is drawn for a degenerate outline.
    """
    if polygon.count() < 3:
        return
    ends = ridge if ridge is not None else _ridge_of(polygon)
    if ends is None:
        return
    p1, p2 = ends
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    length = math.hypot(dx, dy)
    if not math.isfinite(length) or length < 1e-6:
        return
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    mid = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)

    path = QPainterPath()
    path.addPolygon(polygon)
    path.closeSubpath()
    bounds = path.boundingRect()
    short = min(bounds.width(), bounds.height())
    bar = min(BAR_MAX_CM, max(BAR_MIN_CM, BAR_SHARE * short))
    reach = math.hypot(bounds.width(), bounds.height()) + 10.0

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    def line(centre: QPointF, along_x: float, along_y: float, width: float) -> None:
        painter.setPen(QPen(ALUMINIUM_DARK, width * 1.8))
        painter.drawLine(QPointF(centre.x() - along_x * reach, centre.y() - along_y * reach),
                         QPointF(centre.x() + along_x * reach, centre.y() + along_y * reach))
        painter.setPen(QPen(ALUMINIUM, width))
        painter.drawLine(QPointF(centre.x() - along_x * reach, centre.y() - along_y * reach),
                         QPointF(centre.x() + along_x * reach, centre.y() + along_y * reach))

    # Glazing bars at every bay line, including the two gable ends.
    bays = bay_count(length)
    for index in range(bays + 1):
        t = -length / 2.0 + length * index / bays
        centre = QPointF(mid.x() + ux * t, mid.y() + uy * t)
        line(centre, nx, ny, bar)

    # Two rails parallel to the ridge, half way to each side's farthest edge:
    # the 1/4 and 3/4 lines across the roof.
    signed = [
        (polygon.at(index).x() - mid.x()) * nx + (polygon.at(index).y() - mid.y()) * ny
        for index in range(polygon.count())
    ]
    near, far = min(signed), max(signed)
    for offset in (far / 2.0, near / 2.0):
        centre = QPointF(mid.x() + nx * offset, mid.y() + ny * offset)
        line(centre, ux, uy, bar)

    # The ridge cap: a wider dark edge under a bright anodised body.
    painter.setPen(QPen(ALUMINIUM_DARK, bar * 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(p1, p2)
    painter.setPen(QPen(ALUMINIUM, bar * 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(p1, p2)

    painter.restore()

    # The outline last, above the bars (the caller's own silver pen).
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    painter.drawPolygon(polygon)
    painter.restore()


__all__ = ["ALUMINIUM", "ALUMINIUM_DARK", "paint_greenhouse"]
