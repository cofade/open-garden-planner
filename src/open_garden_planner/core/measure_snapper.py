"""Anchor-point snapper for the measure tool.

Detects object anchor points (centers and edge midpoints) near a given
scene position, enabling precise object-to-object distance measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem


class AnchorType(Enum):
    """Type of anchor point on an object."""

    CENTER = auto()
    EDGE_TOP = auto()
    EDGE_BOTTOM = auto()
    EDGE_LEFT = auto()
    EDGE_RIGHT = auto()
    CORNER = auto()
    ENDPOINT = auto()


@dataclass
class AnchorPoint:
    """A snap-able anchor point on an object."""

    point: QPointF
    anchor_type: AnchorType
    item: QGraphicsItem
    anchor_index: int = 0  # Distinguishes same-type anchors (e.g. vertex 0 vs 2)


#: The four edge-anchor kinds.  Polygon / polyline edges are re-classified by
#: their current dominant axis every time anchors are computed, so a stored
#: reference of one of these types can stop identifying its edge (#670).
EDGE_ANCHOR_TYPES = frozenset(
    {
        AnchorType.EDGE_TOP,
        AnchorType.EDGE_BOTTOM,
        AnchorType.EDGE_LEFT,
        AnchorType.EDGE_RIGHT,
    }
)


def _has_indexed_edges(item: QGraphicsItem) -> bool:
    """True for items whose edges are numbered, so the index alone names one."""
    from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem

    return isinstance(item, (PolygonItem, PolylineItem))


def resolve_anchor_point(
    item: QGraphicsItem,
    anchor_type: AnchorType,
    anchor_index: int = 0,
    *,
    fallback_to_center: bool = False,
) -> QPointF | None:
    """The scene position of one anchor, robust to a dynamic edge classification.

    Polygon and polyline edge anchors are typed by the edge's CURRENT dominant
    axis (``measure_snapper._polygon_anchors``), so a stored ``EDGE_RIGHT``
    reference either finds nothing or finds a *different* edge once that edge
    turns horizontal.  For those items the index alone identifies the edge, so
    an edge-typed lookup matches on the index (#670 cause 6).  Everything else
    is matched by the stored type and index, then by type alone for the unique
    anchor kinds.

    This is the single resolver the dimension lines, the drag enforcement and
    the panel share — a second copy is how they drifted apart.
    """
    anchors = get_anchor_points(item)
    if anchor_type in EDGE_ANCHOR_TYPES and _has_indexed_edges(item):
        for anchor in anchors:
            if (
                anchor.anchor_type in EDGE_ANCHOR_TYPES
                and anchor.anchor_index == anchor_index
            ):
                return anchor.point
        # The edge this reference names no longer exists (a vertex was deleted).
        # Falling through to the first edge of the same type would project the
        # anchor onto the wrong edge; no answer is safer than a wrong one
        # (#670 review, P2).
        return None
    for anchor in anchors:
        if (
            anchor.anchor_type == anchor_type
            and anchor.anchor_index == anchor_index
        ):
            return anchor.point
    for anchor in anchors:
        if anchor.anchor_type == anchor_type:
            return anchor.point
    if fallback_to_center:
        # Display-only leniency: a dimension line for a reference whose anchor
        # kind no longer exists (a converted shape) still draws at the centre.
        # Enforcement paths must NOT use this — projecting an anchor onto the
        # item's origin is a silent, wrong correction.
        for anchor in anchors:
            if anchor.anchor_type == AnchorType.CENTER:
                return anchor.point
    return None


def anchor_offset_table(
    item: QGraphicsItem,
) -> dict[tuple[AnchorType, int], tuple[float, float]]:
    """Anchor offsets relative to ``item.pos()``, keyed as a *stored* ref looks up.

    ``ConstraintGraph.solve_anchored`` reads one offset per
    ``(item_id, anchor_type, anchor_index)``.  A stored polygon / polyline edge
    reference keeps its old axis type after the edge turns, so its key would be
    missing and the solver would silently treat the anchor as the item's
    origin.  For those items every edge type is registered for the same index —
    the index is what identifies the edge (#670 cause 6).
    """
    position = item.pos()
    table: dict[tuple[AnchorType, int], tuple[float, float]] = {}
    indexed_edges = _has_indexed_edges(item)
    for anchor in get_anchor_points(item):
        offset = (
            anchor.point.x() - position.x(),
            anchor.point.y() - position.y(),
        )
        table[(anchor.anchor_type, anchor.anchor_index)] = offset
        if indexed_edges and anchor.anchor_type in EDGE_ANCHOR_TYPES:
            for edge_type in EDGE_ANCHOR_TYPES:
                table[(edge_type, anchor.anchor_index)] = offset
    return table


def get_anchor_points(item: QGraphicsItem) -> list[AnchorPoint]:
    """Compute all anchor points for a garden item in scene coordinates.

    Supports RectangleItem, CircleItem, PolygonItem, PolylineItem, and
    construction geometry items.
    Returns center plus edge midpoints appropriate for each type.

    Args:
        item: A graphics item on the scene.

    Returns:
        List of AnchorPoint instances in scene coordinates.
    """
    from open_garden_planner.ui.canvas.items import (
        ArcItem,
        CircleItem,
        EllipseItem,
        PolygonItem,
        PolylineItem,
        RectangleItem,
    )
    from open_garden_planner.ui.canvas.items.construction_item import (
        ConstructionCircleItem,
        ConstructionLineItem,
    )

    anchors: list[AnchorPoint] = []

    if isinstance(item, RectangleItem):
        anchors = _rect_anchors(item)
    elif isinstance(item, EllipseItem):
        anchors = _ellipse_anchors(item)
    elif isinstance(item, CircleItem):
        anchors = _circle_anchors(item)
    elif isinstance(item, PolygonItem):
        anchors = _polygon_anchors(item)
    elif isinstance(item, PolylineItem):
        anchors = _polyline_anchors(item)
    elif isinstance(item, ConstructionLineItem):
        anchors = _construction_line_anchors(item)
    elif isinstance(item, ConstructionCircleItem):
        anchors = _construction_circle_anchors(item)
    elif isinstance(item, ArcItem):
        anchors = _arc_anchors(item)

    return anchors


def _arc_anchors(item: QGraphicsItem) -> list[AnchorPoint]:
    """Anchors for an arc: center + two endpoints.

    The angular midpoint of the arc is exposed separately by
    ``MidpointSnapProvider`` (see ``core/snap/providers/midpoint.py``)
    so it gets the correct snap glyph and priority.
    """
    from open_garden_planner.ui.canvas.items import ArcItem

    assert isinstance(item, ArcItem)
    return [
        AnchorPoint(point=item.center, anchor_type=AnchorType.CENTER, item=item),
        AnchorPoint(
            point=item.start_point(), anchor_type=AnchorType.ENDPOINT, item=item,
            anchor_index=0,
        ),
        AnchorPoint(
            point=item.end_point(), anchor_type=AnchorType.ENDPOINT, item=item,
            anchor_index=1,
        ),
    ]


def _rect_anchors(item: QGraphicsItem) -> list[AnchorPoint]:
    """Get anchors for a rectangle item."""
    from open_garden_planner.ui.canvas.items import RectangleItem

    assert isinstance(item, RectangleItem)
    rect = item.rect()

    # Non-corner anchors (unique types, no index needed)
    single_anchors = [
        (QPointF(rect.center().x(), rect.center().y()), AnchorType.CENTER),
        (QPointF(rect.center().x(), rect.top()), AnchorType.EDGE_TOP),
        (QPointF(rect.center().x(), rect.bottom()), AnchorType.EDGE_BOTTOM),
        (QPointF(rect.left(), rect.center().y()), AnchorType.EDGE_LEFT),
        (QPointF(rect.right(), rect.center().y()), AnchorType.EDGE_RIGHT),
    ]

    anchors = [
        AnchorPoint(
            point=item.mapToScene(lp),
            anchor_type=at,
            item=item,
        )
        for lp, at in single_anchors
    ]

    # Corners need anchor_index to distinguish same-type anchors
    corners = [
        QPointF(rect.left(), rect.top()),      # 0: top-left
        QPointF(rect.right(), rect.top()),     # 1: top-right
        QPointF(rect.left(), rect.bottom()),   # 2: bottom-left
        QPointF(rect.right(), rect.bottom()),  # 3: bottom-right
    ]
    for i, corner in enumerate(corners):
        anchors.append(AnchorPoint(
            point=item.mapToScene(corner),
            anchor_type=AnchorType.CORNER,
            item=item,
            anchor_index=i,
        ))

    return anchors


def _circle_anchors(item: QGraphicsItem) -> list[AnchorPoint]:
    """Get anchors for a circle item."""
    from open_garden_planner.ui.canvas.items import CircleItem

    assert isinstance(item, CircleItem)
    rect = item.rect()
    cx = rect.x() + rect.width() / 2
    cy = rect.y() + rect.height() / 2

    local_points = [
        (QPointF(cx, cy), AnchorType.CENTER),
        (QPointF(cx, rect.top()), AnchorType.EDGE_TOP),
        (QPointF(cx, rect.bottom()), AnchorType.EDGE_BOTTOM),
        (QPointF(rect.left(), cy), AnchorType.EDGE_LEFT),
        (QPointF(rect.right(), cy), AnchorType.EDGE_RIGHT),
    ]

    return [
        AnchorPoint(
            point=item.mapToScene(lp),
            anchor_type=at,
            item=item,
        )
        for lp, at in local_points
    ]


def _ellipse_anchors(item: QGraphicsItem) -> list[AnchorPoint]:
    """Get anchors for an ellipse item: center + 4 quadrant points (N/E/S/W)."""
    from open_garden_planner.ui.canvas.items import EllipseItem

    assert isinstance(item, EllipseItem)
    rect = item.rect()
    cx = rect.x() + rect.width() / 2
    cy = rect.y() + rect.height() / 2

    local_points = [
        (QPointF(cx, cy), AnchorType.CENTER),
        (QPointF(cx, rect.top()), AnchorType.EDGE_TOP),
        (QPointF(cx, rect.bottom()), AnchorType.EDGE_BOTTOM),
        (QPointF(rect.left(), cy), AnchorType.EDGE_LEFT),
        (QPointF(rect.right(), cy), AnchorType.EDGE_RIGHT),
    ]

    return [
        AnchorPoint(
            point=item.mapToScene(lp),
            anchor_type=at,
            item=item,
        )
        for lp, at in local_points
    ]


def _polygon_anchors(item: QGraphicsItem) -> list[AnchorPoint]:
    """Get anchors for a polygon item.

    Returns center of bounding rect plus midpoints of each edge.
    """
    from open_garden_planner.ui.canvas.items import PolygonItem

    assert isinstance(item, PolygonItem)
    polygon = item.polygon()
    count = polygon.count()

    anchors: list[AnchorPoint] = []

    # Center of the polygon bounding rect
    brect = polygon.boundingRect()
    center = QPointF(brect.center().x(), brect.center().y())
    anchors.append(AnchorPoint(
        point=item.mapToScene(center),
        anchor_type=AnchorType.CENTER,
        item=item,
    ))

    # Vertices (corners)
    for i in range(count):
        vertex = polygon.at(i)
        anchors.append(AnchorPoint(
            point=item.mapToScene(vertex),
            anchor_type=AnchorType.CORNER,
            item=item,
            anchor_index=i,
        ))

    # Edge midpoints (including closing edge)
    if count >= 2:
        for i in range(count):
            p1 = polygon.at(i)
            p2 = polygon.at((i + 1) % count)
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            # Classify edge direction based on dominant axis
            dx = abs(p2.x() - p1.x())
            dy = abs(p2.y() - p1.y())
            if dy > dx:
                # More vertical edge -> LEFT or RIGHT
                at = AnchorType.EDGE_LEFT if mid.x() < center.x() else AnchorType.EDGE_RIGHT
            else:
                # More horizontal edge -> TOP or BOTTOM
                at = AnchorType.EDGE_TOP if mid.y() < center.y() else AnchorType.EDGE_BOTTOM
            anchor_type = at
            anchors.append(AnchorPoint(
                point=item.mapToScene(mid),
                anchor_type=anchor_type,
                item=item,
                anchor_index=i,
            ))

    return anchors


def _polyline_anchors(item: QGraphicsItem) -> list[AnchorPoint]:
    """Get anchors for a polyline item.

    Returns center of bounding rect, endpoints, and segment midpoints.
    """
    from open_garden_planner.ui.canvas.items import PolylineItem

    assert isinstance(item, PolylineItem)
    points = item.points

    anchors: list[AnchorPoint] = []

    if not points:
        return anchors

    # Center of the bounding rect
    brect = item.boundingRect()
    center = QPointF(brect.center().x(), brect.center().y())
    anchors.append(AnchorPoint(
        point=item.mapToScene(center),
        anchor_type=AnchorType.CENTER,
        item=item,
    ))

    # All vertices (endpoints and intermediate points)
    for i, pt in enumerate(points):
        anchors.append(AnchorPoint(
            point=item.mapToScene(pt),
            anchor_type=AnchorType.ENDPOINT,
            item=item,
            anchor_index=i,
        ))

    # Segment midpoints
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        # Classify edge direction based on dominant axis
        dx = abs(p2.x() - p1.x())
        dy = abs(p2.y() - p1.y())
        anchor_type = AnchorType.EDGE_LEFT if dy > dx else AnchorType.EDGE_TOP
        anchors.append(AnchorPoint(
            point=item.mapToScene(mid),
            anchor_type=anchor_type,
            item=item,
            anchor_index=i,
        ))

    return anchors


def _construction_line_anchors(item: QGraphicsItem) -> list[AnchorPoint]:
    """Get anchors for a construction line item (endpoints + midpoint)."""
    from open_garden_planner.ui.canvas.items.construction_item import ConstructionLineItem

    assert isinstance(item, ConstructionLineItem)
    line = item.line()
    scene_p1 = item.mapToScene(line.p1())
    scene_p2 = item.mapToScene(line.p2())
    mid = QPointF(
        (scene_p1.x() + scene_p2.x()) / 2,
        (scene_p1.y() + scene_p2.y()) / 2,
    )

    return [
        AnchorPoint(point=scene_p1, anchor_type=AnchorType.ENDPOINT, item=item, anchor_index=0),
        AnchorPoint(point=scene_p2, anchor_type=AnchorType.ENDPOINT, item=item, anchor_index=1),
        AnchorPoint(point=mid, anchor_type=AnchorType.CENTER, item=item),
    ]


def _construction_circle_anchors(item: QGraphicsItem) -> list[AnchorPoint]:
    """Get anchors for a construction circle item (center + 4 cardinal points)."""
    from open_garden_planner.ui.canvas.items.construction_item import ConstructionCircleItem

    assert isinstance(item, ConstructionCircleItem)
    rect = item.rect()
    cx = rect.x() + rect.width() / 2
    cy = rect.y() + rect.height() / 2

    local_points = [
        (QPointF(cx, cy), AnchorType.CENTER),
        (QPointF(cx, rect.top()), AnchorType.EDGE_TOP),
        (QPointF(cx, rect.bottom()), AnchorType.EDGE_BOTTOM),
        (QPointF(rect.left(), cy), AnchorType.EDGE_LEFT),
        (QPointF(rect.right(), cy), AnchorType.EDGE_RIGHT),
    ]

    return [
        AnchorPoint(point=item.mapToScene(lp), anchor_type=at, item=item)
        for lp, at in local_points
    ]


def find_nearest_anchor(
    scene_pos: QPointF,
    scene_items: list[QGraphicsItem],
    threshold: float = 15.0,
) -> AnchorPoint | None:
    """Find the nearest anchor point to a scene position within threshold.

    Args:
        scene_pos: The mouse position in scene coordinates.
        scene_items: All items in the scene.
        threshold: Maximum distance in scene units (cm) to snap.

    Returns:
        The nearest AnchorPoint, or None if nothing is within threshold.
    """
    from open_garden_planner.ui.canvas.items import GardenItemMixin
    from open_garden_planner.ui.canvas.items.construction_item import (
        ConstructionCircleItem,
        ConstructionLineItem,
    )

    best: AnchorPoint | None = None
    best_dist = threshold

    for item in scene_items:
        # Include garden items and construction geometry items
        is_garden = isinstance(item, GardenItemMixin)
        is_construction = isinstance(item, (ConstructionLineItem, ConstructionCircleItem))
        if not (is_garden or is_construction):
            continue
        # Skip items that aren't selectable (hidden/locked layers)
        if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
            continue

        for anchor in get_anchor_points(item):
            dx = anchor.point.x() - scene_pos.x()
            dy = anchor.point.y() - scene_pos.y()
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best = anchor

    return best
