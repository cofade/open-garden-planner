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

from open_garden_planner.core.cad_geometry import segment_segment_intersection
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

#: How far beside an interval midpoint a crossing test looks to tell interior
#: from a segment lying along an edge: 1 micron, far below any drawable stroke.
_INTERIOR_PROBE_CM = 1e-4


def split_path(path: QPainterPath, a: QPointF, b: QPointF) -> list[QPolygonF]:
    """Cut *path* into the filled pieces on each side of the infinite axis a-b.

    Returns the pieces in local path coordinates. An empty list means the cut
    was refused: a degenerate axis, an empty path, a supporting axis that misses
    (or only touches) the shape, a result Qt cannot represent as polygons (a
    hole), or a piece below the degeneracy floor. The two sides are clipped by
    half-plane rectangles built from the path's own bounds, so the axis needs no
    finite extent and the caller does not have to extend it.

    This function has no idea where the user's drawn segment starts and ends. A
    caller that must honour the segment (the split tool does) checks
    :func:`segment_crosses_path` first; without that check a line merely
    collinear with a shape's extension would cut it.
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
    """Whether the finite segment ``a``-``b`` passes through the filled *path*.

    A **touch** is not a crossing: a segment that ends on the outline, runs
    along an edge, or is tangent to it never enters the shape and returns False.
    The segment must own a non-zero length inside the fill. That is what stops a
    snapped pick on a bed's corner from cutting the bed it merely grazed (#664).

    The test walks the segment's parameter intervals split at its crossings
    with the (flattened) outline and asks whether any interval midpoint is
    strictly inside. A midpoint is accepted only when points offset to BOTH
    sides of the line are inside, which rejects a segment lying along an edge.
    ``split_path`` still needs the caller's permission: it cuts along the
    segment's infinite supporting axis.
    """
    if path.isEmpty():
        return False
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    length = math.hypot(dx, dy)
    if not math.isfinite(length) or length < MIN_AXIS_LENGTH_CM:
        return False
    normal_x, normal_y = -dy / length, dx / length

    outline = path.toFillPolygon()
    if outline.count() < 3:
        return False
    stops = [0.0, 1.0]
    for index in range(outline.count()):
        edge_start = outline.at(index)
        edge_end = outline.at((index + 1) % outline.count())
        hit = segment_segment_intersection(a, b, edge_start, edge_end)
        if hit is not None:
            stops.append(hit[0])
    stops.sort()
    unique: list[float] = []
    for stop in stops:
        if not unique or stop - unique[-1] > 1e-9:
            unique.append(stop)
    for low, high in zip(unique, unique[1:], strict=False):
        if high - low <= 1e-9:
            continue
        middle = 0.5 * (low + high)
        mid_x = a.x() + dx * middle
        mid_y = a.y() + dy * middle
        left = QPointF(mid_x + normal_x * _INTERIOR_PROBE_CM,
                       mid_y + normal_y * _INTERIOR_PROBE_CM)
        right = QPointF(mid_x - normal_x * _INTERIOR_PROBE_CM,
                        mid_y - normal_y * _INTERIOR_PROBE_CM)
        if path.contains(left) and path.contains(right):
            return True
    return False


def segment_crosses_item(item: QGraphicsItem, first: QPointF, second: QPointF) -> bool:
    """Whether the scene-space segment ``first``-``second`` passes through *item*.

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
