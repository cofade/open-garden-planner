"""Boolean shape operations using QPainterPath."""

from PyQt6.QtGui import QPainterPath, QPainterPathStroker, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem

#: A contact narrower than this is still a contact for a UNION (#550). Two
#: rectangles snapped to the same edge share it exactly; a curved outline and a
#: straight edge can miss by a few floating-point units. 0.001 cm is a
#: hundredth of a millimetre, far below any drawn stroke.
TOUCH_TOLERANCE_CM = 1e-3

#: The same degeneracy threshold the two-shape operations have always used.
MIN_RESULT_AREA_CM2 = 1.0

#: A real input overlap may be much smaller than a usable result: two shapes
#: crossing by 0.5 cm^2 are a legitimate intersect/subtract selection, even
#: though the result itself is below the 1 cm^2 degeneracy floor.
INPUT_OVERLAP_AREA_CM2 = 1e-4


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

    Supports PolygonItem, RectangleItem, CircleItem and EllipseItem. Returns
    None for unsupported item types.
    """
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    local_path = QPainterPath()

    if isinstance(item, PolygonItem):
        local_path.addPolygon(item.polygon())
    elif isinstance(item, RectangleItem):
        local_path.addRect(item.rect())
    elif isinstance(item, CircleItem):
        # ``rect()``, never ``boundingRect()``: the latter includes the drop
        # shadow, so a circle would boolean 4 cm wider on every side than the
        # shape the user sees, and a circle+ellipse pair would disagree.
        local_path.addEllipse(item.rect())
    elif isinstance(item, EllipseItem):
        local_path.addEllipse(item.rect())
    else:
        return None

    # Map to scene coordinates to handle position, rotation, transforms
    scene_polygon = item.mapToScene(local_path.toFillPolygon())
    scene_path = QPainterPath()
    scene_path.addPolygon(scene_polygon)
    scene_path.closeSubpath()
    return scene_path


def _polygon_result(path: QPainterPath) -> QPolygonF | None:
    poly = path.simplified().toFillPolygon()
    if _polygon_area(poly) < MIN_RESULT_AREA_CM2:
        return None
    return poly


def union_path_many(paths: list[QPainterPath]) -> QPainterPath | None:
    """Union every path and keep the contour structure. None when degenerate.

    Callers that need to know whether the result contains a hole (a ring of
    touching shapes) inspect ``toSubpathPolygons()`` before flattening; a plain
    polygon cannot carry a hole without drawing the connector as a stroke.
    """
    if not paths:
        return None
    result = QPainterPath(paths[0])
    for path in paths[1:]:
        result = result.united(path)
    result = result.simplified()
    if _polygon_area(result.toFillPolygon()) < MIN_RESULT_AREA_CM2:
        return None
    return result


#: A point-contact union is grown by this much before the final union so the
#: result is ONE contour (a self-touching figure-eight cannot be handed to a
#: QGraphicsPolygonItem: its fill rule and connector pen are both wrong). 0.1 mm
#: is invisible at plan scale and is the same order as TOUCH_TOLERANCE_CM.
POINT_CONTACT_MERGE_CM = 0.01


def union_outline_many(
    paths: list[QPainterPath],
) -> tuple[QPainterPath, QPolygonF] | None:
    """Union every path ONCE, returning its contour and its flattened polygon.

    The contour still holds the subpath structure a hole test reads; the polygon
    is what a ``PolygonItem`` can carry. A caller that must check for a hole
    before flattening therefore pays for one union, not two (#550).
    """
    result = union_path_many(paths)
    if result is None:
        return None
    if len(result.toSubpathPolygons()) > 1 and not path_has_hole(result):
        stroker = QPainterPathStroker()
        stroker.setWidth(2.0 * POINT_CONTACT_MERGE_CM)
        grown = [path.united(stroker.createStroke(path)) for path in paths]
        grown_result = union_path_many(grown)
        if grown_result is not None:
            result = grown_result
    return result, result.toFillPolygon()


def boolean_union_many(paths: list[QPainterPath]) -> QPolygonF | None:
    """Union every path, then flatten once. None when the result is degenerate.

    Pairwise ``united()`` keeps holes and curved boundaries until the single
    ``toFillPolygon()`` at the end; the old two-path union did the same for two.
    A point-contact union is re-unioned after growing each shape by a hair, so
    the result is one contour rather than separate subpaths whose flattening
    draws a connector (a diagonal across corner-touching rectangles) and whose
    self-touch defeats the polygon item's fill rule.

    This is the raw geometry: it does not apply the UI policy (refuse a hole, a
    result above ``MAX_POLYGON_VERTICES``, or a cross-layer selection). A caller
    that creates an item must use ``union_outline_many`` and those checks, as
    ``CanvasView.boolean_operation`` does.
    """
    union = union_outline_many(paths)
    return None if union is None else union[1]


def boolean_union(
    path_a: QPainterPath, path_b: QPainterPath
) -> QPolygonF | None:
    """Compute the union of two paths. Returns None if result is degenerate.

    Raw geometry, like :func:`boolean_union_many`: it applies no UI policy
    (hole, vertex cap, layer). A caller that creates an item must go through
    ``union_outline_many`` and those checks, as ``CanvasView`` does.
    """
    return boolean_union_many([path_a, path_b])


def boolean_intersect(
    path_a: QPainterPath, path_b: QPainterPath
) -> QPolygonF | None:
    """Compute the intersection of two paths. Returns None if result is degenerate."""
    return _polygon_result(path_a.intersected(path_b))


def boolean_subtract(
    path_a: QPainterPath, path_b: QPainterPath
) -> QPolygonF | None:
    """Subtract path_b from path_a. Returns None if result is degenerate."""
    return _polygon_result(path_a.subtracted(path_b))


def paths_overlap(path_a: QPainterPath, path_b: QPainterPath) -> bool:
    """Whether two paths share a real area (not merely a boundary).

    ``QPainterPath.intersects`` is true for shapes that only touch, which is the
    wrong answer for INTERSECT and SUBTRACT: their result would be empty or the
    operation ambiguous. Measure the intersection instead.
    """
    return bool(
        _polygon_area(path_a.intersected(path_b).toFillPolygon())
        >= INPUT_OVERLAP_AREA_CM2
    )


def paths_touch_or_overlap(
    path_a: QPainterPath, path_b: QPainterPath
) -> bool:
    """Whether two paths meet: share an edge, cross, or touch within tolerance.

    ``QPainterPath.intersects`` already covers exact contact on this Qt version,
    but a tessellated arc and a straight edge can miss by floating-point noise,
    and the union's connectivity test must not depend on which shape was drawn
    first. The stroked-outline fallback treats a near miss within
    :data:`TOUCH_TOLERANCE_CM` as contact; two visibly disjoint shapes still
    stay disconnected.
    """
    tolerance = TOUCH_TOLERANCE_CM
    if not path_a.boundingRect().adjusted(
        -tolerance, -tolerance, tolerance, tolerance
    ).intersects(path_b.boundingRect()):
        return False
    if path_a.intersects(path_b):
        return True
    stroker = QPainterPathStroker()
    stroker.setWidth(2.0 * tolerance)
    return stroker.createStroke(path_a).intersects(path_b)


def path_has_hole(path: QPainterPath) -> bool:
    """Whether a path contains a contour strictly inside another (a real hole).

    ``toSubpathPolygons()`` also returns separate subpaths for shapes that only
    touch at a corner or a tangent point. Those are legal unions; a hole is a
    contour whose first point is inside another contour. A point on the
    boundary (the touching case) is not "inside" for this test.
    """
    subpaths = path.toSubpathPolygons()
    if len(subpaths) < 2:
        return False
    contours: list[tuple[QPainterPath, float]] = []
    for polygon in subpaths:
        contour = QPainterPath()
        contour.addPolygon(polygon)
        contour.closeSubpath()
        contours.append((contour, _polygon_area(polygon)))
    for outer_index, (outer, _outer_area) in enumerate(contours):
        for inner_index, (inner, inner_area) in enumerate(contours):
            if outer_index == inner_index or inner_area < 0.01:
                # A tangent/corner contact can tessellate into a near-zero-area
                # sliver; that is not a hole.
                continue
            samples = (0.1, 0.3, 0.5, 0.7, 0.9)
            if all(outer.contains(inner.pointAtPercent(t)) for t in samples):
                return True
    return False


def all_paths_connected(paths: list[QPainterPath]) -> bool:
    """Whether the whole selection is one contact/overlap chain (#550).

    Connectivity is checked across the entire selection, not just against the
    first shape: a middle rectangle can connect two otherwise distant circles.
    """
    if len(paths) < 2:
        return True
    connected = {0}
    pending = [0]
    while pending:
        index = pending.pop()
        for other in range(len(paths)):
            if other not in connected and paths_touch_or_overlap(
                paths[index], paths[other]
            ):
                connected.add(other)
                pending.append(other)
    return len(connected) == len(paths)
