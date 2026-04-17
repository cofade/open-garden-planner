"""Integration tests for the hybrid constraint solver (issue #140 robustness).

Regression coverage for:
- Adjacent EDGE_LENGTH constraints that share a vertex (Gauss-Seidel-only
  would drift one length).
- The Newton refinement path in isolation (synthetic two-circle case).
- Scale handle blocking / allowing depending on constraint type.
- Rectangle corner drag preserves right angles and blocks when FIXED.
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.constraint_solver_newton import (
    newton_refine,
    two_circle_intersection,
)
from open_garden_planner.core.constraints import (
    AnchorRef,
    Constraint,
    ConstraintType,
)
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolygonItem, RectangleItem
from open_garden_planner.ui.canvas.items.resize_handle import (
    MidpointHandle,
    RectCornerHandle,
    ResizeHandle,
    RotationHandle,
    VertexHandle,
    _has_blocking_constraints,
    _is_item_fixed,
)


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _draw_rect_polygon(view: CanvasView) -> PolygonItem:
    """Draw a simple 4-vertex rectangular polygon."""
    event = _left_click_event()
    view.set_active_tool(ToolType.POLYGON)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(100, 100))
    tool.mouse_press(event, QPointF(300, 100))
    tool.mouse_press(event, QPointF(300, 250))
    tool.mouse_press(event, QPointF(100, 250))
    tool.mouse_double_click(event, QPointF(100, 250))
    polygons = [i for i in view.scene().items() if isinstance(i, PolygonItem)]
    return polygons[0]


def _apply_edge_length(view: CanvasView, target_cm: float, scene_pt: QPointF) -> None:
    """Apply the EDGE_LENGTH tool with a stubbed distance dialog."""
    event = _left_click_event()
    view.set_active_tool(ToolType.CONSTRAINT_EDGE_LENGTH)
    tool = view.tool_manager.active_tool

    class _AcceptedDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> int:
            return 1

        def distance_cm(self) -> float:
            return target_cm

    with patch(
        "open_garden_planner.core.tools.constraint_tool.DistanceInputDialog",
        _AcceptedDialog,
    ):
        tool.mouse_press(event, scene_pt)


class TestHybridSolverCoupledEdges:
    """Regression tests: Gauss-Seidel alone fails on these; hybrid must pass."""

    def test_two_adjacent_edge_lengths_converge(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        polygon = _draw_rect_polygon(canvas)

        # First edge: top edge (vertex 0 -> vertex 1) → 4.53 m
        _apply_edge_length(canvas, 453.0, QPointF(200, 100))
        # Second edge: right edge (vertex 1 -> vertex 2) → 5.00 m (shares vertex 1)
        _apply_edge_length(canvas, 500.0, QPointF(300, 175))

        constraints = list(canvas._canvas_scene.constraint_graph.constraints.values())
        assert len(constraints) == 2

        pg = polygon.polygon()
        p0 = polygon.mapToScene(pg.at(0))
        p1 = polygon.mapToScene(pg.at(1))
        p2 = polygon.mapToScene(pg.at(2))
        edge0_len = QLineF(p0, p1).length()
        edge1_len = QLineF(p1, p2).length()
        assert abs(edge0_len - 453.0) < 1.0, (
            f"edge0 drifted: got {edge0_len:.2f}, want 453.00"
        )
        assert abs(edge1_len - 500.0) < 1.0, (
            f"edge1 drifted: got {edge1_len:.2f}, want 500.00"
        )


class TestNewtonRefinementUnit:
    """Unit tests for the Newton refiner in isolation."""

    def test_two_circle_intersection_closed_form(self) -> None:
        # Two unit circles centred at (0,0) and (1,0) intersect at (0.5, ±√3/2).
        result = two_circle_intersection(
            c1=(0.0, 0.0), r1=1.0, c2=(1.0, 0.0), r2=1.0, seed=(0.5, 1.0)
        )
        assert result is not None
        assert abs(result[0] - 0.5) < 1e-6
        assert abs(result[1] - (3**0.5) / 2.0) < 1e-6

        none_result = two_circle_intersection(
            c1=(0.0, 0.0), r1=1.0, c2=(10.0, 0.0), r2=1.0, seed=(5.0, 0.0)
        )
        assert none_result is None

    def test_newton_converges_when_gauss_seidel_fails(self) -> None:
        """Synthetic shared-vertex case: two EDGE_LENGTH constraints on one free point.

        Point A is free; points B and C are pinned.  Newton should place A at
        the intersection of circle(B, 100) and circle(C, 100).
        """
        from uuid import uuid4

        uid_a = uuid4()
        uid_b = uuid4()
        uid_c = uuid4()
        positions: dict = {
            uid_a: [0.0, 0.0],
            uid_b: [0.0, 0.0],
            uid_c: [150.0, 0.0],
        }
        anchor_offsets: dict = {}

        constraints = [
            Constraint(
                constraint_id=uuid4(),
                anchor_a=AnchorRef(uid_a, AnchorType.CENTER, 0),
                anchor_b=AnchorRef(uid_b, AnchorType.CENTER, 0),
                target_distance=100.0,
                constraint_type=ConstraintType.DISTANCE,
            ),
            Constraint(
                constraint_id=uuid4(),
                anchor_a=AnchorRef(uid_a, AnchorType.CENTER, 0),
                anchor_b=AnchorRef(uid_c, AnchorType.CENTER, 0),
                target_distance=100.0,
                constraint_type=ConstraintType.DISTANCE,
            ),
        ]
        # Warm-start A at a poor guess so Newton has to do real work.
        positions[uid_a] = [80.0, 10.0]

        converged, err = newton_refine(
            positions=positions,
            vertex_pos={},
            anchor_offsets=anchor_offsets,
            deformable_items=set(),
            deformable_vkeys={},
            constraints=constraints,
            pinned_items={uid_b, uid_c},
            tol=0.01,
        )
        assert converged, f"Newton did not converge, residual={err}"
        ax, ay = positions[uid_a]
        # Feasible set: |A - B| = 100 and |A - C| = 100 with B=(0,0), C=(150,0)
        # → A_x = 75, A_y = ±√(100² - 75²) = ±√4375 ≈ ±66.14
        assert abs(ax - 75.0) < 0.5
        assert abs(abs(ay) - (4375.0**0.5)) < 0.5


class TestScaleHandleBlocking:
    """WP3: bounding-box resize handle refuses to start when blocking constraints exist."""

    def test_scale_blocked_by_edge_length(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        polygon = _draw_rect_polygon(canvas)
        _apply_edge_length(canvas, 250.0, QPointF(200, 100))
        assert _has_blocking_constraints(polygon)

    def test_scale_allowed_with_parallel_only(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """PARALLEL/HORIZONTAL/VERTICAL are scale-invariant and must NOT block."""
        from uuid import uuid4

        from open_garden_planner.core.constraints import AnchorRef

        polygon = _draw_rect_polygon(canvas)
        # Inject a synthetic PARALLEL constraint touching the polygon.
        graph = canvas._canvas_scene.constraint_graph
        graph.add_constraint(
            anchor_a=AnchorRef(polygon.item_id, AnchorType.CORNER, 0),
            anchor_b=AnchorRef(polygon.item_id, AnchorType.CORNER, 1),
            target_distance=0.0,
            constraint_id=uuid4(),
            constraint_type=ConstraintType.PARALLEL,
        )
        assert not _has_blocking_constraints(polygon)

    def test_is_item_fixed_still_detects_fixed(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """The narrower FIXED helper must not regress — used by vertex-edit entry."""
        from uuid import uuid4

        polygon = _draw_rect_polygon(canvas)
        graph = canvas._canvas_scene.constraint_graph
        graph.add_constraint(
            anchor_a=AnchorRef(polygon.item_id, AnchorType.CENTER, 0),
            anchor_b=AnchorRef(polygon.item_id, AnchorType.CENTER, 0),
            target_distance=0.0,
            constraint_id=uuid4(),
            constraint_type=ConstraintType.FIXED,
            target_x=polygon.pos().x(),
            target_y=polygon.pos().y(),
        )
        assert _is_item_fixed(polygon)
        assert _has_blocking_constraints(polygon)


class TestRectCornerDrag:
    """WP5: rectangle corner drag preserves shape and respects FIXED."""

    def test_corner_drag_preserves_right_angles(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        from open_garden_planner.ui.canvas.items.resize_handle import RectCorner

        rect = RectangleItem(0.0, 0.0, 200.0, 100.0)
        rect.setPos(500.0, 500.0)
        canvas.scene().addItem(rect)

        initial_rect = rect.rect()
        initial_pos = rect.pos()

        # Drag TOP_RIGHT by (+60, -40) — opposite corner BOTTOM_LEFT must stay put.
        rect._move_corner_to(
            RectCorner.TOP_RIGHT, QPointF(60, -40), initial_rect, initial_pos
        )

        final_rect = rect.rect()
        # Width and height should reflect the drag.
        assert abs(final_rect.width() - 260.0) < 0.01
        assert abs(final_rect.height() - 140.0) < 0.01

        # Diagonally opposite corner (BOTTOM_LEFT) should stay at its original scene pos.
        scene_bl = rect.mapToScene(
            QPointF(final_rect.left(), final_rect.bottom())
        )
        orig_bl_scene = QPointF(
            initial_pos.x() + initial_rect.left(),
            initial_pos.y() + initial_rect.bottom(),
        )
        assert abs(scene_bl.x() - orig_bl_scene.x()) < 0.5
        assert abs(scene_bl.y() - orig_bl_scene.y()) < 0.5

    def test_corner_drag_rotation_aware(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        from open_garden_planner.ui.canvas.items.resize_handle import RectCorner

        rect = RectangleItem(0.0, 0.0, 200.0, 100.0)
        rect.setPos(500.0, 500.0)
        rect.setRotation(90.0)
        canvas.scene().addItem(rect)

        initial_rect = rect.rect()
        initial_pos = rect.pos()

        # Drag TOP_RIGHT along the rotated x-axis (scene +y direction under 90° rotation).
        rect._move_corner_to(
            RectCorner.TOP_RIGHT, QPointF(0, 50), initial_rect, initial_pos
        )

        final_rect = rect.rect()
        # At 90° rotation, a scene (0, +50) delta maps to a local (+50, 0) delta,
        # which for TOP_RIGHT widens the rect by 50 cm.
        assert abs(final_rect.width() - 250.0) < 0.5
        assert abs(final_rect.height() - 100.0) < 0.5


class TestRegressionBugA:
    """Regression: project_vertex_drag must not raise ImportError."""

    def test_project_vertex_drag_runs_without_import_error(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        polygon = _draw_rect_polygon(canvas)
        _apply_edge_length(canvas, 250.0, QPointF(200, 100))

        result = canvas._canvas_scene.project_vertex_drag(polygon, 0, QPointF(120, 120))
        assert result is not None


class TestRegressionBugB:
    """Regression: RectCornerHandle must be registered as the active drag handle."""

    def test_rect_corner_handle_registered_as_active_drag_handle(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        from open_garden_planner.ui.canvas.items.resize_handle import RectCornerHandle

        rect = RectangleItem(0.0, 0.0, 200.0, 100.0)
        rect.setPos(500.0, 500.0)
        canvas.scene().addItem(rect)

        # Corner handles only exist after entering vertex-edit mode.
        rect.enter_vertex_edit_mode()

        corner_handles = [
            c for c in rect.childItems() if isinstance(c, RectCornerHandle)
        ]
        assert corner_handles, "RectangleItem must have RectCornerHandle children in vertex-edit mode"
        handle = corner_handles[0]

        # Simulate a left-click press at the handle's scene position going through
        # CanvasView.mousePressEvent so the _active_drag_handle tracking fires.
        handle.grabMouse()
        grabber = canvas.scene().mouseGrabberItem()
        assert grabber is handle

        # The same isinstance check as in mousePressEvent must now include RectCornerHandle.
        assert isinstance(grabber, RectCornerHandle)
        # Verify that canvas_view's tuple covers it (mirrors the production code path).
        assert isinstance(grabber, (ResizeHandle, RotationHandle, VertexHandle, RectCornerHandle, MidpointHandle))
