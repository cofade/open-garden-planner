"""Split closed shapes along a two-point cutting axis (#664).

The operation is a geometry-only helper. :func:`segment_crosses_path` decides
whether the DRAWN segment reaches a shape; :func:`split_path` cuts a
``QPainterPath`` into the pieces on each side of the segment's infinite
supporting axis; and :func:`split_item_into_local_polygons` runs that cut in an
item's **local** frame so the source's position, rotation and fill pattern stay
aligned with the pieces.

The pieces are ordinary polygons. Curves (circles, ellipses) therefore become
polygons, and a concave shape may produce more than two pieces; both are
documented limits of the tool. The caller owns the UI policy (locked layers,
constraints, plant links, the vertex cap) because those depend on the scene and
the project, not on the geometry.

Qt-touching but layer-neutral: it may import the item classes only inside the
function (the same cycle-avoidance rule as ``shape_boolean``).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPolygonF

from open_garden_planner.core.shape_boolean import (
    MIN_RESULT_AREA_CM2,
    _polygon_area,
    item_to_local_painter_path,
    path_has_hole,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

    from open_garden_planner.core.object_types import ObjectType

#: A cutting axis shorter than this cannot define a direction.
MIN_AXIS_LENGTH_CM = 1e-6


def split_path(path: QPainterPath, a: QPointF, b: QPointF) -> list[QPolygonF]:
    """Cut *path* into the filled pieces on each side of the infinite axis a-b.

    Returns the pieces in local path coordinates. An empty list means the cut
    was refused: a degenerate axis, an empty path, a line that misses (or only
    touches) the shape, a result Qt cannot represent as polygons (a hole), or
    a piece below the degeneracy floor. The two sides are clipped by half-plane
    rectangles built from the path's own bounds, so the axis needs no finite
    extent and the caller does not have to extend it.
    """
    if path.isEmpty():
        return []

    dx = b.x() - a.x()
    dy = b.y() - a.y()
    length = math.hypot(dx, dy)
    if not math.isfinite(length) or length < MIN_AXIS_LENGTH_CM:
        return []
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux  # left-perpendicular

    bounds = path.boundingRect()
    if not bounds.isValid() or bounds.width() <= 0.0 or bounds.height() <= 0.0:
        return []
    corners = (
        bounds.topLeft(),
        bounds.topRight(),
        bounds.bottomLeft(),
        bounds.bottomRight(),
    )
    along = [(p.x() - a.x()) * ux + (p.y() - a.y()) * uy for p in corners]
    across = [(p.x() - a.x()) * nx + (p.y() - a.y()) * ny for p in corners]
    pad = max(bounds.width(), bounds.height(), 1.0)

    def point(along_cm: float, across_cm: float) -> QPointF:
        return QPointF(
            a.x() + along_cm * ux + across_cm * nx,
            a.y() + along_cm * uy + across_cm * ny,
        )

    low_along = min(along) - pad
    high_along = max(along) + pad
    low_across = min(across) - pad
    high_across = max(across) + pad

    pieces: list[QPolygonF] = []
    # The two open half-planes touching the axis. They overlap only on the
    # zero-width line itself, which has no area in either clipped result.
    for side_low, side_high in (
        (0.0, high_across),
        (low_across, 0.0),
    ):
        if side_high <= side_low:
            return []
        clip = QPainterPath()
        clip.addPolygon(
            QPolygonF(
                [
                    point(low_along, side_low),
                    point(high_along, side_low),
                    point(high_along, side_high),
                    point(low_along, side_high),
                ]
            )
        )
        clip.closeSubpath()
        clipped = path.intersected(clip).simplified()
        if clipped.isEmpty() or path_has_hole(clipped):
            # A hole cannot be carried by a PolygonItem. The supported source
            # shapes cannot contain one; refusing the cut is safer than
            # silently filling it.
            return []
        side_pieces = [
            polygon
            for polygon in clipped.toSubpathPolygons()
            if _polygon_area(polygon) >= MIN_RESULT_AREA_CM2
        ]
        if not side_pieces:
            return []
        pieces.extend(side_pieces)

    return pieces


def segment_crosses_path(path: QPainterPath, a: QPointF, b: QPointF) -> bool:
    """Whether the finite segment ``a``-``b`` touches the filled *path*.

    The split tool uses this before :func:`split_path`: a two-click line only
    cuts the shapes the user actually drew across, not every shape on its
    infinite extension (#664). A segment wholly inside the shape counts (the
    user drew inside it); a segment that only approaches the extension does
    not.
    """
    if path.isEmpty():
        return False
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    length = math.hypot(dx, dy)
    if not math.isfinite(length) or length < MIN_AXIS_LENGTH_CM:
        return False
    segment = QPainterPath()
    segment.moveTo(a)
    segment.lineTo(b)
    return path.intersects(segment)


def segment_crosses_item(item: QGraphicsItem, first: QPointF, second: QPointF) -> bool:
    """Whether the scene-space segment ``first``-``second`` touches *item*.

    Works in the item's local frame, like :func:`split_item_into_local_polygons`,
    so a rotated or grouped source is tested against its real footprint.
    Unsupported items are never crossed.
    """
    local_path = item_to_local_painter_path(item)
    if local_path is None:
        return False
    return segment_crosses_path(
        local_path,
        item.mapFromScene(first),
        item.mapFromScene(second),
    )


def split_item_into_local_polygons(
    item: QGraphicsItem,
    first: QPointF,
    second: QPointF,
) -> list[QPolygonF]:
    """Cut *item* along the scene-space axis ``first``-``second``.

    The result is in the item's local frame, ready to construct pieces that
    keep the source's ``pos``, rotation and fill transform. An empty list means
    the item is unsupported or the cut was refused.
    """
    local_path = item_to_local_painter_path(item)
    if local_path is None:
        return []
    local_first = item.mapFromScene(first)
    local_second = item.mapFromScene(second)
    return split_path(local_path, local_first, local_second)


def polygon_type_for_split(source_type: object) -> ObjectType | None:
    """The type a split piece carries, or None when the source has no form.

    ``polygon_equivalent_object_type`` owns the established conversions
    (rectangle, raised bed, hedge section, already-polygonal types). The two
    generic curves are the split-specific addition: their pieces are polygons,
    so they become ``GENERIC_POLYGON`` rather than losing their identity.
    """
    from open_garden_planner.core.object_types import (
        ObjectType,
        polygon_equivalent_object_type,
    )

    if source_type in {ObjectType.GENERIC_CIRCLE, ObjectType.GENERIC_ELLIPSE}:
        return ObjectType.GENERIC_POLYGON
    return polygon_equivalent_object_type(source_type)  # type: ignore[arg-type]


__all__ = [
    "MIN_AXIS_LENGTH_CM",
    "polygon_type_for_split",
    "segment_crosses_item",
    "segment_crosses_path",
    "split_item_into_local_polygons",
    "split_path",
]
