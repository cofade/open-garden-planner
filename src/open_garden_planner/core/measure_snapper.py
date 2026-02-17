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


def get_anchor_points(item: QGraphicsItem) -> list[AnchorPoint]:
    """Compute all anchor points for a garden item in scene coordinates.

    Supports RectangleItem, CircleItem, PolygonItem, and PolylineItem.
    Returns center plus edge midpoints appropriate for each type.

    Args:
        item: A graphics item on the scene.

    Returns:
        List of AnchorPoint instances in scene coordinates.
    """
    from open_garden_planner.ui.canvas.items import (
        CircleItem,
        PolygonItem,
        PolylineItem,
        RectangleItem,
    )

    anchors: list[AnchorPoint] = []

    if isinstance(item, RectangleItem):
        anchors = _rect_anchors(item)
    elif isinstance(item, CircleItem):
        anchors = _circle_anchors(item)
    elif isinstance(item, PolygonItem):
        anchors = _polygon_anchors(item)
    elif isinstance(item, PolylineItem):
        anchors = _polyline_anchors(item)

    return anchors


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

    best: AnchorPoint | None = None
    best_dist = threshold

    for item in scene_items:
        # Only snap to garden items (skip background images, handles, etc.)
        if not isinstance(item, GardenItemMixin):
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
