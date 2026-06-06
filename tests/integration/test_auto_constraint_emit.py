"""Integration tests for snap → auto-constraint emit (PR #191 follow-up).

When a drawing tool commits a vertex at a snapped point, the snap kind
should be turned into a real constraint stored on the scene's
ConstraintGraph. Tests use the polyline tool because it exercises the
multi-click path that motivated the user feedback (B4/B5/B6).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.constraints import ConstraintType
from open_garden_planner.core.snap.provider import (
    SnapCandidate,
    SnapCandidateKind,
)
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    PolylineItem,
    RectangleItem,
)


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _commit_polyline_with_snap_on_second_vertex(
    canvas: CanvasView,
    snap: SnapCandidate | None,
    p1: QPointF,
    p2: QPointF,
) -> PolylineItem:
    """Click p1 free, click p2 with the given snap candidate as the
    'current snap', then press Enter to finalize the polyline."""
    canvas.set_active_tool(ToolType.FENCE)
    tool = canvas.tool_manager.active_tool

    # First click — no snap.
    canvas._current_snap = None
    tool.mouse_press(_left_click_event(), p1)
    # Second click — snap candidate injected.
    canvas._current_snap = snap
    tool.mouse_press(_left_click_event(), p2)

    # Finalize via Enter.
    from PyQt6.QtGui import QKeyEvent
    enter = MagicMock(spec=QKeyEvent)
    enter.key.return_value = Qt.Key.Key_Return
    tool.key_press(enter)

    polys = [i for i in canvas.scene().items() if isinstance(i, PolylineItem)]
    return polys[-1]


class TestPolylineAutoConstraint:
    def test_nearest_snap_on_rectangle_emits_point_on_edge(
        self, canvas: CanvasView
    ) -> None:
        rect = RectangleItem(0, 0, 200, 100)
        canvas.scene().addItem(rect)
        # Edge 0 = top edge (topLeft→topRight); point (50,0) lies on it.
        snap = SnapCandidate(
            point=QPointF(50, 0),
            kind=SnapCandidateKind.NEAREST,
            priority=45,
            item=rect,
            source_edge_index=0,
        )

        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(500, 500), QPointF(50, 0)
        )

        graph = canvas.scene().constraint_graph
        # POINT_ON_EDGE must name BOTH edge endpoints (anchor_b + anchor_c) so
        # the solver can resolve the edge line; the malformed CENTER-only emit
        # is gone.
        matches = [
            c
            for c in graph.constraints.values()
            if c.constraint_type == ConstraintType.POINT_ON_EDGE
            and c.anchor_a.item_id == poly.item_id
            and c.anchor_b.item_id == rect.item_id
        ]
        assert len(matches) == 1
        assert matches[0].anchor_c is not None
        assert matches[0].anchor_c.item_id == rect.item_id

    def test_nearest_snap_on_circle_emits_point_on_circle(
        self, canvas: CanvasView
    ) -> None:
        circle = CircleItem(center_x=200, center_y=200, radius=60)
        canvas.scene().addItem(circle)
        snap = SnapCandidate(
            point=QPointF(260, 200),
            kind=SnapCandidateKind.NEAREST,
            priority=45,
            item=circle,
        )

        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(500, 500), QPointF(260, 200)
        )

        graph = canvas.scene().constraint_graph
        assert any(
            c.constraint_type == ConstraintType.POINT_ON_CIRCLE
            and c.anchor_a.item_id == poly.item_id
            and c.anchor_b.item_id == circle.item_id
            for c in graph.constraints.values()
        )

    def test_midpoint_snap_on_rectangle_emits_coincident(
        self, canvas: CanvasView
    ) -> None:
        """MIDPOINT snap → COINCIDENT between the drawn vertex and the source
        edge midpoint (issue #196)."""
        rect = RectangleItem(0, 0, 200, 100)
        canvas.scene().addItem(rect)
        # Edge 0 = top; its midpoint is (100, 0) → rect EDGE_TOP anchor.
        snap = SnapCandidate(
            point=QPointF(100, 0),
            kind=SnapCandidateKind.MIDPOINT,
            priority=30,
            item=rect,
            source_edge_index=0,
        )

        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(500, 500), QPointF(100, 0)
        )

        graph = canvas.scene().constraint_graph
        assert any(
            c.constraint_type == ConstraintType.COINCIDENT
            and c.anchor_a.item_id == poly.item_id
            and c.anchor_b.item_id == rect.item_id
            for c in graph.constraints.values()
        )

    def test_perpendicular_snap_on_rectangle_emits_point_on_edge(
        self, canvas: CanvasView
    ) -> None:
        """PERPENDICULAR snap → POINT_ON_EDGE on the snapped edge (issue #196).

        The vertex rides the source edge; the rotation-only PERPENDICULAR type
        is intentionally NOT used (it would rotate the whole polyline)."""
        rect = RectangleItem(0, 0, 200, 100)
        canvas.scene().addItem(rect)
        # Edge 3 = left (bottomLeft→topLeft); foot of perpendicular at (0,50).
        snap = SnapCandidate(
            point=QPointF(0, 50),
            kind=SnapCandidateKind.PERPENDICULAR,
            priority=25,
            item=rect,
            source_edge_index=3,
        )

        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(500, 500), QPointF(0, 50)
        )

        graph = canvas.scene().constraint_graph
        matches = [
            c
            for c in graph.constraints.values()
            if c.constraint_type == ConstraintType.POINT_ON_EDGE
            and c.anchor_a.item_id == poly.item_id
            and c.anchor_b.item_id == rect.item_id
        ]
        assert len(matches) == 1
        assert matches[0].anchor_c is not None

    def test_no_snap_emits_nothing(self, canvas: CanvasView) -> None:
        rect = RectangleItem(0, 0, 200, 100)
        canvas.scene().addItem(rect)
        graph = canvas.scene().constraint_graph
        before = len(graph.constraints)

        _commit_polyline_with_snap_on_second_vertex(
            canvas, None, QPointF(500, 500), QPointF(600, 500)
        )

        assert len(graph.constraints) == before

    def test_tangent_snap_on_circle_emits_point_on_circle_and_tangent(
        self, canvas: CanvasView
    ) -> None:
        """TANGENT snap → POINT_ON_CIRCLE (radial weld) + TANGENT (edge⊥radius).
        The pair is non-degenerate (orthogonal gradients) — see ADR-024. #192."""
        circle = CircleItem(center_x=200, center_y=200, radius=60)
        canvas.scene().addItem(circle)
        # Tangent point on the circle for a line drawn from the first vertex.
        snap = SnapCandidate(
            point=QPointF(260, 200),
            kind=SnapCandidateKind.TANGENT,
            priority=26,
            item=circle,
        )

        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(260, 500), QPointF(260, 200)
        )

        graph = canvas.scene().constraint_graph
        tangents = [
            c
            for c in graph.constraints.values()
            if c.constraint_type == ConstraintType.TANGENT
            and c.anchor_a.item_id == poly.item_id
            and c.anchor_b.item_id == circle.item_id
        ]
        assert len(tangents) == 1
        c = tangents[0]
        # anchor_c is the previous polyline vertex (the line's other endpoint).
        assert c.anchor_c is not None
        assert c.anchor_c.item_id == poly.item_id

        # POINT_ON_CIRCLE companion welds the contact to the rim (radius 60).
        on_circle = [
            c
            for c in graph.constraints.values()
            if c.constraint_type == ConstraintType.POINT_ON_CIRCLE
            and c.anchor_a.item_id == poly.item_id
            and c.anchor_b.item_id == circle.item_id
        ]
        assert len(on_circle) == 1
        assert abs(on_circle[0].target_distance - 60.0) < 1e-6

    def test_tangent_snap_on_first_vertex_emits_nothing(
        self, canvas: CanvasView
    ) -> None:
        """A tangent line needs a previous vertex; on the *first* vertex there is
        no edge yet, so nothing is emitted."""
        circle = CircleItem(center_x=200, center_y=200, radius=60)
        canvas.scene().addItem(circle)
        snap = SnapCandidate(
            point=QPointF(260, 200),
            kind=SnapCandidateKind.TANGENT,
            priority=26,
            item=circle,
        )
        graph = canvas.scene().constraint_graph
        before = len(graph.constraints)

        # Snap on the FIRST vertex (vertex index 0).
        canvas.set_active_tool(ToolType.FENCE)
        tool = canvas.tool_manager.active_tool
        canvas._current_snap = snap
        tool.mouse_press(_left_click_event(), QPointF(260, 200))
        canvas._current_snap = None
        tool.mouse_press(_left_click_event(), QPointF(260, 500))
        from PyQt6.QtGui import QKeyEvent

        enter = MagicMock(spec=QKeyEvent)
        enter.key.return_value = Qt.Key.Key_Return
        tool.key_press(enter)

        assert len(graph.constraints) == before


def _tangent_state(poly: object, circle: object) -> tuple[float, float, float]:
    """Return (signed perp distance centre→line, |contact−centre|, |edge|).

    For a proper tangent (POINT_ON_CIRCLE + TANGENT): |perp distance| == radius
    (tangent) AND |contact−centre| == radius (contact welded to the rim). The
    sign of the perp distance encodes the side (used to detect flips).
    """
    import math

    from open_garden_planner.core.measure_snapper import (
        AnchorType,
        get_anchor_points,
    )

    pts = {
        a.anchor_index: a.point
        for a in get_anchor_points(poly)
        if a.anchor_type == AnchorType.ENDPOINT
    }
    cen = next(
        a.point
        for a in get_anchor_points(circle)
        if a.anchor_type == AnchorType.CENTER
    )
    v0, v1 = pts[0], pts[1]
    edx, edy = v0.x() - v1.x(), v0.y() - v1.y()
    elen = math.hypot(edx, edy)
    cross = (cen.x() - v1.x()) * edy - (cen.y() - v1.y()) * edx
    contact_dist = math.hypot(cen.x() - v1.x(), cen.y() - v1.y())
    return cross / elen, contact_dist, elen


class TestTangentDragHolds:
    """When the circle moves, the contact must stay welded to the rim AND the
    edge must stay tangent — on the drawn side (no flip). This is the
    non-degenerate POINT_ON_CIRCLE + TANGENT(edge⟂radius) pair (ADR-024)."""

    def _draw_right_tangent(self, canvas, cx, cy, r, v0):
        import math

        d = math.hypot(v0[0] - cx, v0[1] - cy)
        ang = math.atan2(v0[1] - cy, v0[0] - cx) - math.acos(r / d)
        v1 = (cx + r * math.cos(ang), cy + r * math.sin(ang))
        circle = CircleItem(center_x=cx, center_y=cy, radius=r)
        canvas.scene().addItem(circle)
        snap = SnapCandidate(
            point=QPointF(*v1),
            kind=SnapCandidateKind.TANGENT,
            priority=26,
            item=circle,
        )
        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(*v0), QPointF(*v1)
        )
        return circle, poly

    def test_tangency_and_weld_hold_single_frame(self, canvas: CanvasView) -> None:
        circle, poly = self._draw_right_tangent(canvas, 300.0, 300.0, 100.0, (300.0, 600.0))
        signed0, contact0, _ = _tangent_state(poly, circle)
        assert abs(abs(signed0) - 100.0) < 1.0  # starts tangent
        assert abs(contact0 - 100.0) < 1.0  # contact on the rim

        delta = QPointF(-60.0, 0.0)
        propagated = canvas._compute_constraint_propagation([circle], delta)  # noqa: SLF001
        circle.setPos(circle.pos() + delta)
        for item, d_item in propagated:
            item.moveBy(d_item.x(), d_item.y())

        signed1, contact1, _ = _tangent_state(poly, circle)
        assert abs(abs(signed1) - 100.0) < 1.5  # still tangent
        assert abs(contact1 - 100.0) < 1.5  # contact still welded to the rim
        assert (signed0 > 0) == (signed1 > 0)  # same side, no flip

    def test_tangency_and_weld_hold_large_drag_user_geometry(
        self, canvas: CanvasView
    ) -> None:
        """The user's manual-test geometry + a large rightward circle drag: the
        contact stays welded to the rim AND tangent, same side, every frame."""
        cx, cy, r = 1550.0, 2000.0, 320.2
        v0, v1 = (1600.0, 1150.0), (1853.2, 1897.2)  # from the [TANGENT] emit log
        circle = CircleItem(center_x=cx, center_y=cy, radius=r)
        canvas.scene().addItem(circle)
        snap = SnapCandidate(
            point=QPointF(*v1),
            kind=SnapCandidateKind.TANGENT,
            priority=26,
            item=circle,
        )
        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(*v0), QPointF(*v1)
        )
        signed0, _, _ = _tangent_state(poly, circle)

        circle.setSelected(True)
        canvas._drag_start_positions = {circle: circle.pos()}  # noqa: SLF001
        canvas._constraint_propagated_starts = {}  # noqa: SLF001
        for frame in range(40):
            circle.moveBy(7.0, 0.0)  # drag right, like the user did
            canvas._propagate_constraints_during_drag()  # noqa: SLF001
            signed, contact, _ = _tangent_state(poly, circle)
            assert abs(abs(signed) - r) < 2.0, (
                f"frame {frame}: tangency lost, |dist|={abs(signed):.1f} r={r:.1f}"
            )
            assert abs(contact - r) < 2.0, (
                f"frame {frame}: contact left the rim, |contact−c|={contact:.1f}"
            )
            assert (signed > 0) == (signed0 > 0), (
                f"frame {frame}: tangent flipped to the opposite side"
            )


class TestEmittedConstraintEnforcement:
    """#197: emitted constraints participate in the existing drag propagation."""

    def test_point_on_circle_propagates_when_source_dragged(
        self, canvas: CanvasView
    ) -> None:
        circle = CircleItem(center_x=200, center_y=200, radius=60)
        canvas.scene().addItem(circle)
        snap = SnapCandidate(
            point=QPointF(260, 200),
            kind=SnapCandidateKind.NEAREST,
            priority=45,
            item=circle,
        )
        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(260, 500), QPointF(260, 200)
        )

        # Dragging the circle (the constraint's reference side) must drag the
        # constrained polyline along via _compute_constraint_propagation.
        deltas = canvas._compute_constraint_propagation(  # noqa: SLF001
            [circle], QPointF(50.0, 0.0)
        )
        moved_ids = {
            getattr(item, "item_id", None) for item, _delta in deltas
        }
        assert poly.item_id in moved_ids

    def test_point_on_edge_propagates_when_source_dragged(
        self, canvas: CanvasView
    ) -> None:
        rect = RectangleItem(0, 0, 200, 100)
        canvas.scene().addItem(rect)
        snap = SnapCandidate(
            point=QPointF(50, 0),
            kind=SnapCandidateKind.NEAREST,
            priority=45,
            item=rect,
            source_edge_index=0,
        )
        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(500, 500), QPointF(50, 0)
        )

        deltas = canvas._compute_constraint_propagation(  # noqa: SLF001
            [rect], QPointF(0.0, 40.0)
        )
        moved_ids = {
            getattr(item, "item_id", None) for item, _delta in deltas
        }
        assert poly.item_id in moved_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
