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
        snap = SnapCandidate(
            point=QPointF(50, 0),
            kind=SnapCandidateKind.NEAREST,
            priority=45,
            item=rect,
        )

        poly = _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(500, 500), QPointF(50, 0)
        )

        graph = canvas.scene().constraint_graph
        assert any(
            c.constraint_type == ConstraintType.POINT_ON_EDGE
            and c.anchor_a.item_id == poly.item_id
            and c.anchor_b.item_id == rect.item_id
            for c in graph.constraints.values()
        )

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

    def test_perpendicular_snap_is_noop_pending_us_b12(
        self, canvas: CanvasView
    ) -> None:
        """PERPENDICULAR auto-emit needs edge-level identification on the
        SnapCandidate to construct a solver-enforceable constraint. The
        previous draft emitted against the source's CENTER which produced
        phantom violated constraints. Deferred to issue #196 (US-B12)."""
        rect = RectangleItem(0, 0, 200, 100)
        canvas.scene().addItem(rect)
        snap = SnapCandidate(
            point=QPointF(150, 50),
            kind=SnapCandidateKind.PERPENDICULAR,
            priority=25,
            item=rect,
        )
        graph = canvas.scene().constraint_graph
        before = len(graph.constraints)

        _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(500, 500), QPointF(150, 50)
        )

        assert len(graph.constraints) == before

    def test_no_snap_emits_nothing(self, canvas: CanvasView) -> None:
        rect = RectangleItem(0, 0, 200, 100)
        canvas.scene().addItem(rect)
        graph = canvas.scene().constraint_graph
        before = len(graph.constraints)

        _commit_polyline_with_snap_on_second_vertex(
            canvas, None, QPointF(500, 500), QPointF(600, 500)
        )

        assert len(graph.constraints) == before

    def test_tangent_snap_is_noop_pending_us_b8(
        self, canvas: CanvasView
    ) -> None:
        """Tangent has no constraint type yet; the emitter must skip it
        rather than crash or emit a placeholder."""
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

        _commit_polyline_with_snap_on_second_vertex(
            canvas, snap, QPointF(500, 500), QPointF(260, 200)
        )

        assert len(graph.constraints) == before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
