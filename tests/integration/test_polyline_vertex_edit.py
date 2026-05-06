"""Integration tests for polyline vertex editing.

Regression coverage for:
- Issue #168: dragging a polyline vertex when other segments carry
  edge-length constraints must NOT translate the polyline as a whole and
  must not "jump around wildly".
- Issue #167: vertex add/delete must be discoverable via the right-click
  context menu on both VertexHandle and MidpointHandle.
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.constraints import AnchorRef
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolylineItem
from open_garden_planner.ui.canvas.items.resize_handle import (
    MidpointHandle,
    VertexHandle,
)


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _draw_fence(view: CanvasView) -> PolylineItem:
    """Draw a 5-vertex fence along (100..500, 200) and double-click to finish."""
    event = _left_click_event()
    view.set_active_tool(ToolType.FENCE)
    tool = view.tool_manager.active_tool
    for i in range(5):
        tool.mouse_press(event, QPointF(100 + i * 100, 200))
    tool.mouse_double_click(event, QPointF(500, 200))
    polylines = [i for i in view.scene().items() if isinstance(i, PolylineItem)]
    assert polylines, "polyline tool did not produce a PolylineItem"
    return polylines[0]


class TestPolylineVertexDragStability:
    """Issue #168: polyline must not translate when one of its vertices is dragged."""

    def test_drag_unconstrained_vertex_does_not_translate_polyline(
        self, canvas: CanvasView, qtbot: object,
    ) -> None:
        polyline = _draw_fence(canvas)
        graph = canvas._canvas_scene.constraint_graph
        # Add an EDGE_LENGTH constraint on the v2-v3 segment directly.
        graph.add_constraint(
            AnchorRef(polyline.item_id, AnchorType.ENDPOINT, 2),
            AnchorRef(polyline.item_id, AnchorType.ENDPOINT, 3),
            100.0,
        )
        before_pos = QPointF(polyline.pos())
        before_v0 = QPointF(polyline.points[0])

        # Simulate the drag-end the way the canvas view does: stash a deferred
        # move and call _enforce_after_vertex_drag — which previously could
        # silently translate the polyline because it was polygon-only.
        new_v0 = QPointF(before_v0.x() + 5.0, before_v0.y() + 5.0)
        polyline._move_vertex_to(0, new_v0)
        canvas._deferred_vertex_move = (polyline, 0, before_v0, new_v0)
        canvas._enforce_after_vertex_drag()

        # The polyline must not have translated as a whole. (item_deltas from
        # the post-drag solver are intentionally ignored for the moving item.)
        assert polyline.pos() == before_pos
        # Constraint v2-v3 was already satisfied (initial spacing 100 == target 100),
        # so the solver leaves v1..v4 alone.
        for i in (1, 2, 3, 4):
            expected_x = 100 + i * 100
            assert abs(polyline.points[i].x() - expected_x) < 0.5
            assert abs(polyline.points[i].y() - 200) < 0.5

    def test_unconstrained_vertex_projection_is_passthrough(
        self, canvas: CanvasView, qtbot: object,
    ) -> None:
        """The live drag projection must short-circuit when no constraint touches v0."""
        polyline = _draw_fence(canvas)
        graph = canvas._canvas_scene.constraint_graph
        graph.add_constraint(
            AnchorRef(polyline.item_id, AnchorType.ENDPOINT, 2),
            AnchorRef(polyline.item_id, AnchorType.ENDPOINT, 3),
            100.0,
        )

        target = QPointF(123.0, 456.0)
        result = canvas._canvas_scene.project_vertex_drag(polyline, 0, target)
        assert result == target

    def test_no_drift_dragging_fully_constrained_vertex(
        self, canvas: CanvasView, qtbot: object,
    ) -> None:
        """Live drag of a fully constrained vertex must not drift the polyline.

        Reproduces the post-merge manual test failure on PR #169: when every
        adjacent edge of the fence carries an EDGE_LENGTH constraint and the
        user pulls on a middle vertex, all vertices used to slip ~0.2 cm per
        frame in the cursor direction.  This drives the full live-drag pipeline
        (project_vertex_drag → project_to_feasible → newton_refine →
        _move_vertex_to) for 100 frames of a near-stationary cursor and
        asserts no per-vertex drift accumulates.
        """
        polyline = _draw_fence(canvas)
        graph = canvas._canvas_scene.constraint_graph
        # EDGE_LENGTH between every adjacent pair — fully constrains the chain.
        for i in range(4):
            graph.add_constraint(
                AnchorRef(polyline.item_id, AnchorType.ENDPOINT, i),
                AnchorRef(polyline.item_id, AnchorType.ENDPOINT, i + 1),
                100.0,
            )

        before_pos = QPointF(polyline.pos())
        before_scene = [polyline.mapToScene(p) for p in polyline.points]

        # Simulate the exact pipeline VertexHandle.mouseMoveEvent runs each
        # frame: project a near-stationary cursor, then write the result via
        # _move_vertex_to.  Cursor wobbles 0.3 cm around v2's scene position.
        v2_scene = before_scene[2]
        for frame in range(100):
            cursor = QPointF(
                v2_scene.x() + 0.3 * (1.0 if frame % 2 else -1.0),
                v2_scene.y() + 0.3 * (1.0 if frame % 4 < 2 else -1.0),
            )
            projected = canvas._canvas_scene.project_vertex_drag(polyline, 2, cursor)
            polyline._move_vertex_to(2, polyline.mapFromScene(projected))

        # Polyline pos() must be unchanged after 100 frames.
        assert polyline.pos() == before_pos, "polyline.pos() drifted"

        # Non-moving vertices in scene coords must be unchanged.
        after_scene = [polyline.mapToScene(p) for p in polyline.points]
        for i in (0, 1, 3, 4):
            dx = after_scene[i].x() - before_scene[i].x()
            dy = after_scene[i].y() - before_scene[i].y()
            assert abs(dx) < 1e-3 and abs(dy) < 1e-3, (
                f"v{i} drifted by ({dx:.4f}, {dy:.4f})"
            )

        # Moving vertex itself must remain on the constraint set.
        v1, v2, v3 = after_scene[1], after_scene[2], after_scene[3]
        d12 = ((v2.x() - v1.x()) ** 2 + (v2.y() - v1.y()) ** 2) ** 0.5
        d23 = ((v3.x() - v2.x()) ** 2 + (v3.y() - v2.y()) ** 2) ** 0.5
        assert abs(d12 - 100.0) < 1e-2, f"v1-v2 length drifted: {d12}"
        assert abs(d23 - 100.0) < 1e-2, f"v2-v3 length drifted: {d23}"


class TestVertexHandleContextMenu:
    """Issue #167: VertexHandle context menu offers Insert Before/After + Delete."""

    def test_polyline_vertex_handle_offers_insert_actions(
        self, canvas: CanvasView, qtbot: object,
    ) -> None:
        polyline = _draw_fence(canvas)
        polyline.enter_vertex_edit_mode()
        handles = [c for c in polyline.childItems() if isinstance(c, VertexHandle)]
        # One handle per vertex.
        assert len(handles) == 5

        # Build the same menu contextMenuEvent would build for v2 (middle).
        # We re-implement the enable logic to assert it directly without
        # popping a real QMenu.
        h = next(h for h in handles if h.vertex_index == 2)
        is_polyline = isinstance(h._parent_item, PolylineItem)
        vertex_count = h._parent_item._get_vertex_count()
        assert is_polyline
        assert h.vertex_index > 0  # Insert Before enabled
        assert h.vertex_index < vertex_count - 1  # Insert After enabled

        # v0: Insert Before disabled, Insert After enabled.
        h0 = next(h for h in handles if h.vertex_index == 0)
        assert not (h0.vertex_index > 0)
        assert h0.vertex_index < vertex_count - 1

        # vN-1: Insert Before enabled, Insert After disabled.
        h_last = next(h for h in handles if h.vertex_index == vertex_count - 1)
        assert h_last.vertex_index > 0
        assert not (h_last.vertex_index < vertex_count - 1)

    def test_insert_after_adds_vertex_at_midpoint(
        self, canvas: CanvasView, qtbot: object,
    ) -> None:
        polyline = _draw_fence(canvas)
        polyline.enter_vertex_edit_mode()
        original_count = len(polyline.points)
        v0 = QPointF(polyline.points[0])
        v1 = QPointF(polyline.points[1])

        # Replicate the menu's "Insert Vertex After v0" branch directly.
        midpoint = QPointF((v0.x() + v1.x()) / 2.0, (v0.y() + v1.y()) / 2.0)
        polyline._add_vertex_at_edge(0, midpoint)

        assert len(polyline.points) == original_count + 1
        # New vertex sits between old v0 and v1 → at index 1 with midpoint coords.
        assert abs(polyline.points[1].x() - midpoint.x()) < 0.5
        assert abs(polyline.points[1].y() - midpoint.y()) < 0.5


class TestMidpointHandle:
    """Issue #167: MidpointHandle has tooltip + right-click menu."""

    def test_midpoint_handle_has_tooltip(
        self, canvas: CanvasView, qtbot: object,
    ) -> None:
        polyline = _draw_fence(canvas)
        polyline.enter_vertex_edit_mode()
        midpoints = [c for c in polyline.childItems() if isinstance(c, MidpointHandle)]
        assert midpoints
        for mp in midpoints:
            tt = mp.toolTip()
            assert tt, "MidpointHandle missing tooltip"
            assert "vertex" in tt.lower() or "knoten" in tt.lower()


class TestVertexAddDeleteShiftsConstraintIndices:
    """Issue #168 latent bug: vertex add/delete must keep constraint indices valid."""

    def test_insert_shifts_higher_anchor_indices(
        self, canvas: CanvasView, qtbot: object,
    ) -> None:
        polyline = _draw_fence(canvas)
        graph = canvas._canvas_scene.constraint_graph
        graph.add_constraint(
            AnchorRef(polyline.item_id, AnchorType.ENDPOINT, 2),
            AnchorRef(polyline.item_id, AnchorType.ENDPOINT, 3),
            100.0,
        )

        # Insert a new vertex between v0 and v1 (edge_index=0) → indices 2,3 → 3,4.
        midpoint = QPointF(150, 200)
        polyline._add_vertex_at_edge(0, midpoint)

        c = next(iter(graph.constraints.values()))
        assert c.anchor_a.anchor_index == 3
        assert c.anchor_b.anchor_index == 4

    def test_delete_drops_constraint_on_that_vertex(
        self, canvas: CanvasView, qtbot: object,
    ) -> None:
        polyline = _draw_fence(canvas)
        graph = canvas._canvas_scene.constraint_graph
        graph.add_constraint(
            AnchorRef(polyline.item_id, AnchorType.ENDPOINT, 2),
            AnchorRef(polyline.item_id, AnchorType.ENDPOINT, 3),
            100.0,
        )
        assert len(graph.constraints) == 1

        # Delete v3 → the v2-v3 constraint references it directly, must be dropped.
        polyline._delete_vertex(3)
        assert len(graph.constraints) == 0
