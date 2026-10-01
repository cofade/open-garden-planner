"""Integration tests: distance constraint creation applies CAD convention.

Verifies the fix for issue #139: when a distance constraint is created between
two free-floating items, only the first-clicked item (A) moves to satisfy the
distance; the second-clicked item (B) stays in place as the reference.
"""

# ruff: noqa: ARG002

import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.commands import AddConstraintCommand
from open_garden_planner.core.constraints import AnchorRef, ConstraintType
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolygonItem, RectangleItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _draw_rect(
    view: CanvasView, x1: float, y1: float, x2: float, y2: float
) -> RectangleItem:
    """Draw a rectangle and return the resulting item."""
    event = _left_click_event()
    view.set_active_tool(ToolType.RECTANGLE)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(x1, y1))
    tool.mouse_move(event, QPointF(x2, y2))
    tool.mouse_release(event, QPointF(x2, y2))
    rects = [i for i in view.scene().items() if isinstance(i, RectangleItem)]
    return rects[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _draw_polygon(view: CanvasView, points: list[QPointF]) -> PolygonItem:
    """Draw a polygon and return the resulting item."""
    event = _left_click_event()
    view.set_active_tool(ToolType.POLYGON)
    tool = view.tool_manager.active_tool
    for point in points:
        tool.mouse_press(event, point)
    tool.mouse_double_click(event, points[-1])
    polygons = [i for i in view.scene().items() if isinstance(i, PolygonItem)]
    return polygons[0]


class TestDistanceConstraintCreation:
    """Issue #139 regression tests for the 'both items move' bug."""

    def test_only_item_a_moves_when_distance_constraint_added(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Adding a distance constraint moves only item A; item B stays fixed.

        Scenario from issue #139: two items 10 m apart, constraint set to 8 m.
        Expected: item A (first anchor) moves 2 m toward B; B does not move.
        """
        # Two rectangles, each 100×100 cm.
        # rect_a centre at (50, 50), rect_b centre at (1050, 50) → 1000 cm apart.
        rect_a = _draw_rect(canvas, 0, 0, 100, 100)
        rect_b = _draw_rect(canvas, 1000, 0, 1100, 100)

        pos_b_before = rect_b.pos()

        # Build a distance constraint: A = rect_a centre, B = rect_b centre.
        ref_a = AnchorRef(rect_a.item_id, AnchorType.CENTER)
        ref_b = AnchorRef(rect_b.item_id, AnchorType.CENTER)
        target_cm = 800.0  # 8 m

        graph = canvas._canvas_scene.constraint_graph
        command = AddConstraintCommand(
            graph, ref_a, ref_b, target_cm, constraint_type=ConstraintType.DISTANCE
        )
        canvas._execute_constraint_with_solve(command)

        pos_b_after = rect_b.pos()

        # B must not have moved at all (pos() is the Qt item position offset).
        assert pos_b_after.x() == pytest.approx(
            pos_b_before.x(), abs=0.1
        ), "Item B (reference) must not move when a distance constraint is added"
        assert pos_b_after.y() == pytest.approx(
            pos_b_before.y(), abs=0.1
        ), "Item B (reference) must not move when a distance constraint is added"

        # The resulting anchor-to-anchor (centre-to-centre) distance must equal
        # the target.  RectangleItem uses QGraphicsRectItem(x, y, w, h) which
        # stores the rect in local coords, so the scene centre is
        # item.mapToScene(item.rect().center()), NOT just item.pos().
        centre_a = rect_a.mapToScene(rect_a.rect().center())
        centre_b = rect_b.mapToScene(rect_b.rect().center())
        dist = math.sqrt(
            (centre_b.x() - centre_a.x()) ** 2 + (centre_b.y() - centre_a.y()) ** 2
        )
        assert (
            abs(dist - target_cm) < 1.0
        ), f"Distance constraint not satisfied: got {dist:.1f} cm, expected {target_cm} cm"

    def test_item_a_moves_full_correction_not_half(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """A moves by the full correction (not just half) when B is the reference.

        Before the fix, each item moved by half the error (50/50 split).
        After the fix, A moves by the full 200 cm correction; B stays.
        """
        rect_a = _draw_rect(canvas, 0, 0, 100, 100)
        rect_b = _draw_rect(canvas, 1000, 0, 1100, 100)

        # Use scene-space centre because RectangleItem stores the rect in local
        # coordinates; pos() alone is not sufficient.
        centre_a_before = rect_a.mapToScene(rect_a.rect().center())

        ref_a = AnchorRef(rect_a.item_id, AnchorType.CENTER)
        ref_b = AnchorRef(rect_b.item_id, AnchorType.CENTER)
        target_cm = 800.0

        graph = canvas._canvas_scene.constraint_graph
        command = AddConstraintCommand(
            graph, ref_a, ref_b, target_cm, constraint_type=ConstraintType.DISTANCE
        )
        canvas._execute_constraint_with_solve(command)

        centre_a_after = rect_a.mapToScene(rect_a.rect().center())
        # A should have moved ~200 cm (the full correction), not ~100 cm (the half).
        delta_a = abs(centre_a_after.x() - centre_a_before.x())
        assert (
            delta_a > 150.0
        ), f"A moved only {delta_a:.1f} cm — looks like the old 50/50 split is still active"

    def test_polygon_adjacent_edges_can_have_distinct_edge_length_constraints(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Adjacent polygon edges remain distinguishable via anchor_index."""
        polygon = _draw_polygon(
            canvas,
            [QPointF(0, 0), QPointF(300, 0), QPointF(300, 200), QPointF(0, 200)],
        )
        graph = canvas._canvas_scene.constraint_graph
        c1 = graph.add_constraint(
            AnchorRef(polygon.item_id, AnchorType.CORNER, 0),
            AnchorRef(polygon.item_id, AnchorType.CORNER, 1),
            300.0,
            constraint_type=ConstraintType.EDGE_LENGTH,
        )
        c2 = graph.add_constraint(
            AnchorRef(polygon.item_id, AnchorType.CORNER, 1),
            AnchorRef(polygon.item_id, AnchorType.CORNER, 2),
            200.0,
            constraint_type=ConstraintType.EDGE_LENGTH,
        )
        assert c1.constraint_id != c2.constraint_id
        assert len(graph.constraints) == 2

    def test_solver_restore_rederives_a_house_ridge(
        self, canvas: CanvasView, qtbot: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The solver's trial-geometry restore must re-derive the linked ridge.

        ``_compute_edge_length_constraint_moves`` snapshots a polygon's
        geometry, lets the solver move it, and restores the snapshot in a
        ``finally``. That restore used a bare ``setPolygon`` while its
        polyline sibling restored through ``_move_vertex_to`` -- the one
        override that re-derives a HOUSE's roof ridge (ADR-046).

        On a *successful* solve the leftover is transient, because the caller
        re-applies the moves through a command. When the solve **raises**,
        nothing re-applies them: the polygon is restored and the ridge is left
        computed for the trial geometry, on a dirty-able document. That is the
        case pinned here.
        """
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints
        from open_garden_planner.ui.canvas.items import PolylineItem

        house = _draw_polygon(
            canvas,
            [QPointF(0, 0), QPointF(300, 0), QPointF(300, 200), QPointF(0, 200)],
        )
        # Build the linked ridge the way PolygonTool._create_roof_ridge does.
        p1, p2 = compute_roof_ridge_endpoints(house.polygon(), house.pos())
        ridge = PolylineItem([p1, p2], object_type=ObjectType.ROOF_RIDGE)
        house.set_metadata("ridge_item_id", str(ridge.item_id))
        ridge.set_metadata("owner_polygon_id", str(house.item_id))
        canvas.scene().addItem(ridge)

        def ridge_deviation_cm() -> float:
            n1, n2 = compute_roof_ridge_endpoints(house.polygon(), QPointF(0.0, 0.0))
            canonical = (house.mapToScene(n1), house.mapToScene(n2))
            live = (
                ridge.mapToScene(ridge.points[0]),
                ridge.mapToScene(ridge.points[-1]),
            )
            return max(
                math.dist(
                    (live[i].x(), live[i].y()),
                    (canonical[i].x(), canonical[i].y()),
                )
                for i in (0, 1)
            )

        graph = canvas._canvas_scene.constraint_graph
        # Two constraints, both touching vertex 0, so the method takes the
        # solver branch (a single constraint would early-return before the
        # try/finally this test is about).
        graph.add_constraint(
            AnchorRef(house.item_id, AnchorType.CORNER, 0),
            AnchorRef(house.item_id, AnchorType.CORNER, 1),
            300.0,
            constraint_type=ConstraintType.EDGE_LENGTH,
        )
        graph.add_constraint(
            AnchorRef(house.item_id, AnchorType.CORNER, 3),
            AnchorRef(house.item_id, AnchorType.CORNER, 0),
            200.0,
            constraint_type=ConstraintType.EDGE_LENGTH,
        )
        assert len(graph.constraints) == 2
        original = [house.polygon().at(i) for i in range(house.polygon().count())]

        def _explode(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("solver exploded")

        monkeypatch.setattr(canvas, "_compute_constraint_solve_moves", _explode)

        command = AddConstraintCommand(
            graph,
            AnchorRef(house.item_id, AnchorType.CORNER, 0),
            AnchorRef(house.item_id, AnchorType.CORNER, 1),
            400.0,
            constraint_type=ConstraintType.EDGE_LENGTH,
        )
        with pytest.raises(RuntimeError):
            canvas._compute_edge_length_constraint_moves(command)

        # The polygon is restored...
        assert [
            house.polygon().at(i) for i in range(house.polygon().count())
        ] == original
        # ...and so must the ridge derived from it, not left on trial geometry.
        deviation = ridge_deviation_cm()
        assert deviation <= 0.5, (
            f"ridge left {deviation:.2f} cm from canonical after the solver "
            "restored the polygon — the restore must re-derive derived geometry"
        )
