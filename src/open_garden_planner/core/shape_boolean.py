"""Boolean shape operations using QPainterPath."""

from PyQt6.QtGui import QPainterPath, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem


def _polygon_area(poly: QPolygonF) -> float:
    """Compute the absolute area of a QPolygonF using the shoelace formula."""
    n = poly.count()
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        p1 = poly.at(i)
        p2 = poly.at((i + 1) % n)
        area += p1.x() * p2.y() - p2.x() * p1.y()
    return abs(area) / 2.0


def item_to_painter_path(item: QGraphicsItem) -> QPainterPath | None:
    """Convert a shape item to a QPainterPath in scene coordinates.

    Supports PolygonItem, RectangleItem, and CircleItem.
    Returns None for unsupported item types.
    """
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    local_path = QPainterPath()

    if isinstance(item, PolygonItem):
        local_path.addPolygon(item.polygon())
    elif isinstance(item, RectangleItem):
        local_path.addRect(item.rect())
    elif isinstance(item, CircleItem):
        local_path.addEllipse(item.boundingRect())
    else:
        return None

    # Map to scene coordinates to handle position, rotation, transforms
    scene_polygon = item.mapToScene(local_path.toFillPolygon())
    scene_path = QPainterPath()
    scene_path.addPolygon(scene_polygon)
    scene_path.closeSubpath()
    return scene_path


def boolean_union(
    path_a: QPainterPath, path_b: QPainterPath
) -> QPolygonF | None:
    """Compute the union of two paths. Returns None if result is degenerate."""
    result = path_a.united(path_b).simplified()
    poly = result.toFillPolygon()
    if _polygon_area(poly) < 1.0:
        return None
    return poly


def boolean_intersect(
    path_a: QPainterPath, path_b: QPainterPath
) -> QPolygonF | None:
    """Compute the intersection of two paths. Returns None if result is degenerate."""
    result = path_a.intersected(path_b).simplified()
    poly = result.toFillPolygon()
    if _polygon_area(poly) < 1.0:
        return None
    return poly


def boolean_subtract(
    path_a: QPainterPath, path_b: QPainterPath
) -> QPolygonF | None:
    """Subtract path_b from path_a. Returns None if result is degenerate."""
    result = path_a.subtracted(path_b).simplified()
    poly = result.toFillPolygon()
    if _polygon_area(poly) < 1.0:
        return None
    return poly
