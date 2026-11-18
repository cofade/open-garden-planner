"""Paint a building's roof in its plan footprint.

A HOUSE is drawn as its roof seen from above: the fill pattern is roof tiles,
and the ridge divides two planes whose tiles lap DOWN-SLOPE, away from the
ridge. The tile texture itself has one fixed direction — its rounded free edge
points ``+Y`` and laps the tile below it — so the half on one side of the ridge
must be mirrored, and the brush frame rotated to the ridge. Doing this in one
module is what makes a rectangle converted into a HOUSE (#690) draw the same
roof as a house drawn with the polygon tool; before it, ``RectangleItem`` fell
back to the flat fill and its tiles lapped back up toward the ridge.

Both item classes call :func:`paint_building_roof` with their own outline.
The house's linked ridge is mapped from scene to local coordinates (#364).
The hip uses the 3D builder's nearest-eave faces. The mono-pitch brush
descends from local +Y, and a flat roof is one surface.

Facts pinned by ``tests/unit/test_roof_tile_orientation.py`` over eight
house/rotation cases: the two halves are mirror images, and walking outward
from the ridge the tile phase runs down-slope (R then B in the probe's
colours). Reversing the brush assignment or negating the rotation makes those
tests fail.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import TYPE_CHECKING

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.fill_patterns import FillTransform, brush_for_painter
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.roof_style import BUILDING_KINDS, FLAT, GABLE, HIP, SHED, roof_style
from open_garden_planner.core.scene3d.builders.primitives import ccw_ring
from open_garden_planner.core.scene3d.builders.roofs import (
    MAX_HIP_CORNERS,
    HipPlan,
    bounding_box_ridge,
    hip_plan,
    is_convex,
)
from open_garden_planner.core.scene3d.polygon import is_buildable_region
from open_garden_planner.ui.canvas.roof_ridge_link import ridge_points_local

if TYPE_CHECKING:
    from .polygon_item import PolygonItem
    from .rectangle_item import RectangleItem


def _polygon_path(polygon: QPolygonF) -> QPainterPath:
    path = QPainterPath()
    path.addPolygon(polygon)
    path.closeSubpath()
    return path


@lru_cache(maxsize=128)
def _hip_faces(points: tuple[tuple[float, float], ...]) -> HipPlan | None:
    if not is_buildable_region(points) or not is_convex(points):
        return None
    plan = hip_plan(ccw_ring(points))
    return plan if plan.faces else None


def _face_brush(
    painter: QPainter,
    brush: QBrush,
    origin: QPointF,
    angle: float,
    fill_transform: FillTransform | None,
    *,
    mirrored: bool,
) -> QBrush:
    frame = QTransform()
    frame.translate(origin.x(), origin.y())
    frame.rotate(angle)
    if mirrored:
        frame.scale(1.0, -1.0)
    if fill_transform is not None and not fill_transform.is_identity:
        frame = frame * fill_transform.brush_transform()
    result = QBrush(brush)
    result.setTransform(frame)
    return brush_for_painter(result, painter) or result


def paint_building_roof(
    painter: QPainter,
    item: RectangleItem | PolygonItem,
    polygon: QPolygonF,
    ridge: QGraphicsItem | None,
) -> bool:
    """Draw the style shared with the caster and 3D builder. Return whether painted."""
    kind = item.object_type
    if kind is None or kind.name not in BUILDING_KINDS or polygon.count() < 3:
        return False
    style = roof_style(item.metadata)
    ridge_points = ridge_points_local(item, ridge)
    if style is None:
        if kind == ObjectType.TOOL_SHED:
            return False  # its automatic roof is already painted by the sprite
        style = GABLE if kind == ObjectType.GARAGE_SHED or ridge_points else FLAT

    brush = item.brush()
    pen = item.pen()
    transform = item.fill_transform
    path = _polygon_path(polygon)

    if style == FLAT:
        painter.fillPath(path, brush_for_painter(brush, painter) or brush)
    elif style == SHED:
        box = polygon.boundingRect()
        high = QPointF(box.center().x(), box.bottom())
        low = QPointF(high.x(), box.top())
        painter.fillPath(path, _face_brush(painter, brush, high, 0.0, transform, mirrored=True))
        # Local +Y is the high eave, the same direction as the mono-pitch builder.
        shade = QLinearGradient(high, low)
        tone = pen.color().darker(150)
        tone.setAlpha(0)
        shade.setColorAt(0.0, tone)
        tone.setAlpha(42)
        shade.setColorAt(1.0, tone)
        painter.fillPath(path, QBrush(shade))
    else:
        points = tuple((p.x(), p.y()) for p in (polygon.at(i) for i in range(polygon.count())))
        hip = _hip_faces(points) if style == HIP and len(points) <= MAX_HIP_CORNERS else None
        if hip is not None:
            _paint_hip(painter, hip, brush, pen, transform)
        else:
            # Non-convex or over-budget hips fall back to a gable, as in 3D.
            # A shed without a linked ridge uses the same local long axis.
            if ridge_points is None:
                if kind == ObjectType.TOOL_SHED and hasattr(item, "rect"):
                    box = polygon.boundingRect()
                    x = box.center().x()
                    ridge_points = (QPointF(x, box.top()), QPointF(x, box.bottom()))
                elif ends := bounding_box_ridge(points):
                    ridge_points = (QPointF(*ends[0]), QPointF(*ends[1]))
            if ridge_points is None or not _paint_gable(
                painter, path, *ridge_points, brush, pen, transform
            ):
                return False
            if ridge is None or style == HIP:
                painter.save()
                painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
                painter.setPen(pen)
                painter.drawLine(*ridge_points)
                painter.restore()
            return True

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    painter.drawPath(path)
    return True


def _paint_hip(
    painter: QPainter, plan: HipPlan, brush: QBrush, pen: QPen, transform: FillTransform | None
) -> None:
    seams = QPainterPath()
    for index, face in plan.faces:
        dx, dy = plan.edge[index]
        polygon = QPolygonF([QPointF(x, y) for x, y in face])
        painter.fillPath(_polygon_path(polygon), _face_brush(
            painter, brush, polygon.boundingRect().center(),
            math.degrees(math.atan2(dy, dx)), transform, mirrored=True,
        ))
        seams.addPolygon(polygon)
        seams.closeSubpath()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    painter.drawPath(seams)


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


def _paint_gable(
    painter: QPainter,
    poly_path: QPainterPath,
    p1: QPointF,
    p2: QPointF,
    brush: QBrush,
    pen: QPen,
    fill_transform: FillTransform | None,
) -> bool:
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return False
    mid_x = (p1.x() + p2.x()) / 2.0
    mid_y = (p1.y() + p2.y()) / 2.0
    angle_deg = math.degrees(math.atan2(dy, dx))

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
    origin = QPointF(mid_x, mid_y)
    normal_brush = _face_brush(painter, brush, origin, angle_deg, fill_transform, mirrored=False)
    mirrored_brush = _face_brush(painter, brush, origin, angle_deg, fill_transform, mirrored=True)

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
    # Each half is clipped with IntersectClip, never the default ReplaceClip:
    # a paint() that replaces the clip throws away the one it was handed, and
    # a print tile or a PDF frame is exactly such a clip (#788, PF-CAN-54).
    # The SVG export needs nothing from this shape: it records the clip and
    # the brush transform below the painter (services/svg_export.py, #787).
    #
    # Pinned by tests/unit/test_roof_tile_orientation.py over eight
    # house/rotation cases spanning landscape, portrait and square; 8 of its
    # 11 cases fail against the previous brush assignment.
    painter.save()
    painter.setClipPath(left_path, Qt.ClipOperation.IntersectClip)
    painter.setBrush(normal_brush)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(fill_rect)
    painter.restore()

    painter.save()
    painter.setClipPath(right_path, Qt.ClipOperation.IntersectClip)
    painter.setBrush(mirrored_brush)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(fill_rect)
    painter.restore()

    # Draw outline on top
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    painter.drawPath(poly_path)
    return True
