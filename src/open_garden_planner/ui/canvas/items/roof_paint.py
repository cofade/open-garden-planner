"""Paint a HOUSE's roof as two tile planes — the one ridge-aware brush path.

A HOUSE is drawn as its roof seen from above: the fill pattern is roof tiles,
and the ridge divides two planes whose tiles lap DOWN-SLOPE, away from the
ridge. The tile texture itself has one fixed direction — its rounded free edge
points ``+Y`` and laps the tile below it — so the half on one side of the ridge
must be mirrored, and the brush frame rotated to the ridge. Doing this in one
module is what makes a rectangle converted into a HOUSE (#690) draw the same
roof as a house drawn with the polygon tool; before it, ``RectangleItem`` fell
back to the flat fill and its tiles lapped back up toward the ridge.

Both item classes call :func:`paint_roof_with_ridge` with their own outline in
item coordinates. The item supplies ``mapFromScene`` (the ridge points are
stored in scene space since #364), its brush, pen and optional
``fill_transform`` (#665); this module owns the split, the mirrored brush and
the SVG-safe two-pass paint.

Facts pinned by ``tests/unit/test_roof_tile_orientation.py`` over eight
house/rotation cases: the two halves are mirror images, and walking outward
from the ridge the tile phase runs down-slope (R then B in the probe's
colours). Reversing the brush assignment or negating the rotation makes those
tests fail.
"""

from __future__ import annotations

import math
from typing import Any, cast

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.fill_patterns import FillTransform, brush_for_painter


def _split_path_by_line(
    path: QPainterPath, line: QLineF
) -> tuple[QPainterPath, QPainterPath]:
    """Split a QPainterPath into two halves along a line.

    Returns (left_half, right_half) where "left" is the side that the
    perpendicular points toward negative when walking from line.p1 to p2.

    Args:
        path: The path to split
        line: The dividing line (will be extended far beyond the path bounds)

    Returns:
        Tuple of (left_path, right_path)
    """
    bounds = path.boundingRect()
    ext = max(bounds.width(), bounds.height()) * 10.0 + 1000.0

    dx = line.dx()
    dy = line.dy()
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return path, QPainterPath()

    # Unit direction and unit perpendicular
    ux, uy = dx / length, dy / length
    px, py = -uy, ux  # left-perpendicular

    # Midpoint of the supplied line segment
    mid_x = (line.x1() + line.x2()) / 2.0
    mid_y = (line.y1() + line.y2()) / 2.0

    # Extended ridge endpoints
    e1 = QPointF(mid_x - ux * ext, mid_y - uy * ext)
    e2 = QPointF(mid_x + ux * ext, mid_y + uy * ext)

    # Left half-plane polygon (perpendicular direction is "left")
    left_rect = QPainterPath()
    left_rect.moveTo(e1)
    left_rect.lineTo(e2)
    left_rect.lineTo(QPointF(e2.x() + px * ext, e2.y() + py * ext))
    left_rect.lineTo(QPointF(e1.x() + px * ext, e1.y() + py * ext))
    left_rect.closeSubpath()

    # Right half-plane polygon
    right_rect = QPainterPath()
    right_rect.moveTo(e1)
    right_rect.lineTo(e2)
    right_rect.lineTo(QPointF(e2.x() - px * ext, e2.y() - py * ext))
    right_rect.lineTo(QPointF(e1.x() - px * ext, e1.y() - py * ext))
    right_rect.closeSubpath()

    return path.intersected(left_rect), path.intersected(right_rect)


def paint_roof_with_ridge(
    painter: QPainter,
    host: QGraphicsItem,
    polygon: QPolygonF,
    ridge: QGraphicsItem,
    brush: QBrush,
    pen: QPen,
    fill_transform: FillTransform | None = None,
) -> None:
    """Paint HOUSE *polygon* with the tile texture mirrored on each side of the ridge.

    Args:
        painter: The painter already painting *host* in its local frame.
        host: The item being painted — supplies ``mapFromScene`` so a rotated
            house's scene-space ridge is mapped back into its own frame.
        polygon: The house outline in *host*'s local coordinates.
        ridge: The linked ``ROOF_RIDGE``; its points are scene-space.
        brush: The item's own brush (pattern pixmap + colour).
        pen: The item's own pen, used for the outline on top.
        fill_transform: The per-object pattern transform (#665), composed INTO
            the ridge frame rather than replacing it.
    """
    # Get ridge endpoints in item-local coordinates of THIS shape.
    #
    # Since #364 the ridge's points are SCENE coordinates, not ridge-item
    # locals: `_update_ridge_on_boundary` computes them in the polygon's
    # local frame and maps them out with `mapToScene`. So scene -> local is
    # `ridge.mapToScene` then `host.mapFromScene`. Do not add a second
    # `host.mapToScene` on top — that rotates the axis twice and is
    # precisely the bug that made the #372 test sample off-axis (§11.4).
    pts = cast(Any, ridge).points
    if len(pts) < 2:
        return
    p1 = host.mapFromScene(ridge.mapToScene(pts[0]))
    p2 = host.mapFromScene(ridge.mapToScene(pts[-1]))

    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return
    mid_x = (p1.x() + p2.x()) / 2.0
    mid_y = (p1.y() + p2.y()) / 2.0
    angle_deg = math.degrees(math.atan2(dy, dx))

    # Build polygon QPainterPath
    poly_path = QPainterPath()
    if polygon.count() > 0:
        poly_path.moveTo(polygon.at(0))
        for i in range(1, polygon.count()):
            poly_path.lineTo(polygon.at(i))
        poly_path.closeSubpath()

    # Build half-plane clipping paths along the ridge line
    left_path, right_path = _split_path_by_line(poly_path, QLineF(p1, p2))

    # Rotate the tile texture to the ridge, tiling origin at the midpoint.
    # QBrush.setTransform(T) means: a local point (x,y) samples the texture
    # at T^-1.(x,y). Because the sampling is the inverse, the texture's own
    # +Y (its down-slope, see the assignment note below) lands in the world
    # at R(angle).(0,1) = the ridge's left-perpendicular.
    # A per-object pattern transform (#665) is composed INTO the ridge
    # frame, not instead of it: angle 0 keeps the canonical tiles, and a
    # user angle turns them relative to the roof, so the two planes stay
    # mirror images of each other.
    user_tx = None
    if fill_transform is not None and not fill_transform.is_identity:
        user_tx = fill_transform.brush_transform()

    normal_tx = QTransform()
    normal_tx.translate(mid_x, mid_y)
    normal_tx.rotate(angle_deg)
    if user_tx is not None:
        normal_tx = normal_tx * user_tx
    normal_brush = QBrush(brush)
    normal_brush.setTransform(normal_tx)
    # the tile at the painter's resolution, inside the same ridge frame (#785)
    normal_brush = brush_for_painter(normal_brush, painter) or normal_brush

    # Mirrored brush: reflects the down-slope across the ridge, for the
    # half that faces the other way (issue #372).
    mirrored_tx = QTransform()
    mirrored_tx.translate(mid_x, mid_y)
    mirrored_tx.rotate(angle_deg)
    mirrored_tx.scale(1.0, -1.0)
    if user_tx is not None:
        mirrored_tx = mirrored_tx * user_tx
    mirrored_brush = QBrush(brush)
    mirrored_brush.setTransform(mirrored_tx)
    mirrored_brush = brush_for_painter(mirrored_brush, painter) or mirrored_brush

    # Bounding rect for fill (clip handles actual shape)
    bounds = poly_path.boundingRect()
    ext = max(bounds.width(), bounds.height()) + 100.0
    fill_rect = QRectF(
        bounds.center().x() - ext,
        bounds.center().y() - ext,
        ext * 2.0,
        ext * 2.0,
    )

    # Paint the two halves of the roof (issue #372).
    #
    # The assignment is gravity-relative, and it used to be name-relative.
    # ``_split_path_by_line`` names its halves by the left-perpendicular
    # ``n = (-uy, ux)``, which follows the ridge's *direction* and has
    # nothing to do with which side is downhill -- for a +X ridge
    # ``left_path`` is the LOWER half, for a +Y ridge it is the LEFT half.
    #
    # Meanwhile the roof-tile texture has a fixed, non-negotiable
    # direction: each tile's rounded free edge points +Y and laps the tile
    # below it, so +Y is down-slope. Measured from the texture, a dark
    # lapse line sits near y=10 with the light free edge beneath.
    #
    # The arithmetic that decides the assignment: ``normal_tx`` is
    # ``translate(mid) . rotate(angle)`` and a QBrush transform samples the
    # texture at ``T^-1 . p``, so the texture's +Y lands in the world at
    # ``R(angle).(0,1) = (-sin a, cos a)`` -- exactly ``n``. So
    # ``left_path`` is the half the texture's true down-slope points into,
    # and it is the half that must keep the NORMAL brush. The previous
    # code handed it the mirrored one, so its tiles lapped back up toward
    # the ridge: water would run uphill under the laps.
    #
    # Note this is NOT a one-sided defect. The two clip halves are mirror
    # images across the ridge, so they read the same outward sequence and
    # the inversion appeared on BOTH halves (``BRRBRR`` either way) rather
    # than on one. It was wrong at EVERY ridge angle -- measured identical
    # across all 24 fifteen-degree steps from 0 to 345 -- which is why
    # horizontal and vertical houses were both affected.
    #
    # This depends on the ridge's point ORDER only through the *along-ridge*
    # axis, and it does NOT change the lap direction. Reversing the two
    # points flips the texture coordinate u while leaving v alone, i.e. it
    # mirrors the tile pattern along the ridge: measured with a probe
    # symmetric in x, reversal changes 0.00% of the painted pixels, while a
    # probe asymmetric in x changes 44-93%. So a reversed ridge is a
    # cosmetic along-ridge mirror, not the laps defect this fix is about.
    #
    # The order is nevertheless canonical, and every production writer
    # emits it: `compute_roof_ridge_endpoints` orders its two crossings by
    # the line parameter (verified: 0 inversions across 36 shape variants),
    # and both callers -- creation and `_update_ridge_on_boundary` -- keep
    # that order. A hand drag of a ridge endpoint can reorder them, but it
    # is not sticky: the next polygon edit recomputes them canonically.
    #
    # The two-sided clip + oversized drawRect shape is load-bearing and
    # must not be flattened: Qt does not serialize the painter clip into
    # SVG, and ``ExportService._fix_svg_qt_texture_clipping`` pairs each
    # shadow group with the next texture group 1:1 (§11.4).
    #
    # Pinned by tests/unit/test_roof_tile_orientation.py over eight
    # house/rotation cases spanning landscape, portrait and square; 8 of its
    # 11 cases fail against the previous brush assignment.
    painter.save()
    painter.setClipPath(left_path)
    painter.setBrush(normal_brush)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(fill_rect)
    painter.restore()

    painter.save()
    painter.setClipPath(right_path)
    painter.setBrush(mirrored_brush)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(fill_rect)
    painter.restore()

    # Draw outline on top
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    painter.drawPath(poly_path)
