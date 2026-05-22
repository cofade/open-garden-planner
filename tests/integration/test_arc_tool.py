"""End-to-end integration test for the 3-point Arc tool (Phase 13 B2)."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import ArcItem, PolylineItem


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    """Canvas with snapping disabled — keeps integration test coordinates predictable."""
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


def _arc_items(view: CanvasView) -> list[ArcItem]:
    return [it for it in view.scene().items() if isinstance(it, ArcItem)]


def _polyline_items(view: CanvasView) -> list[PolylineItem]:
    return [it for it in view.scene().items() if isinstance(it, PolylineItem)]


class TestArcToolWorkflow:
    def test_three_clicks_create_an_arc(self, canvas: CanvasView) -> None:
        """Click start → through-point → end produces a single ArcItem."""
        canvas.set_active_tool(ToolType.ARC)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        tool.mouse_press(event, QPointF(0, 0))
        tool.mouse_press(event, QPointF(50, 50))
        tool.mouse_press(event, QPointF(100, 0))

        arcs = _arc_items(canvas)
        assert len(arcs) == 1
        arc = arcs[0]
        # The through-point (50, 50) must lie on the arc within tolerance.
        center = arc.center
        dist = math.hypot(50 - center.x(), 50 - center.y())
        assert abs(dist - arc.radius) < 1e-3

    def test_collinear_clicks_fall_back_to_polyline(self, canvas: CanvasView) -> None:
        """Three collinear clicks create a 2-vertex polyline (line fallback)."""
        canvas.set_active_tool(ToolType.ARC)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        tool.mouse_press(event, QPointF(0, 0))
        tool.mouse_press(event, QPointF(50, 0))
        tool.mouse_press(event, QPointF(100, 0))

        assert len(_arc_items(canvas)) == 0
        polylines = _polyline_items(canvas)
        assert len(polylines) == 1

    def test_escape_cancels_in_progress_arc(self, canvas: CanvasView) -> None:
        """Pressing Escape after the first click resets the tool state."""
        from PyQt6.QtGui import QKeyEvent

        canvas.set_active_tool(ToolType.ARC)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()
        tool.mouse_press(event, QPointF(10, 10))

        esc_event = MagicMock(spec=QKeyEvent)
        esc_event.key.return_value = Qt.Key.Key_Escape
        assert tool.key_press(esc_event) is True

        # No arc and no polyline should exist after cancel.
        assert len(_arc_items(canvas)) == 0
        # last_point clears after cancel.
        assert tool.last_point is None

    def test_arc_persists_through_save_and_reload(
        self, canvas: CanvasView, tmp_path
    ) -> None:
        """Save → reload preserves the arc through the project pipeline."""
        canvas.set_active_tool(ToolType.ARC)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()
        tool.mouse_press(event, QPointF(0, 0))
        tool.mouse_press(event, QPointF(100, 150))
        tool.mouse_press(event, QPointF(200, 0))

        arcs_before = _arc_items(canvas)
        assert len(arcs_before) == 1
        original = arcs_before[0]
        orig_center = original.center
        orig_radius = original.radius

        # Save → reload via ProjectManager.save / .load.
        from open_garden_planner.core.project import ProjectManager

        pm = ProjectManager()
        out_path = tmp_path / "arc_roundtrip.ogp"
        pm.save(canvas.scene(), out_path)
        assert out_path.exists()

        # Reload into a fresh scene to prove the on-disk dict is sufficient.
        canvas.scene().clear()
        pm.load(canvas.scene(), out_path)

        arcs_after = _arc_items(canvas)
        assert len(arcs_after) == 1
        reloaded = arcs_after[0]
        assert abs(reloaded.radius - orig_radius) < 1e-6
        new_center = reloaded.center
        assert abs(new_center.x() - orig_center.x()) < 1e-6
        assert abs(new_center.y() - orig_center.y()) < 1e-6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
