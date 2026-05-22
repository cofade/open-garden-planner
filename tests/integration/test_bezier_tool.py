"""End-to-end integration test for the cubic Bezier pen tool (Phase 13 B1)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import BezierItem


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


def _enter_event() -> MagicMock:
    event = MagicMock(spec=QKeyEvent)
    event.key.return_value = Qt.Key.Key_Return
    return event


def _escape_event() -> MagicMock:
    event = MagicMock(spec=QKeyEvent)
    event.key.return_value = Qt.Key.Key_Escape
    return event


def _backspace_event() -> MagicMock:
    event = MagicMock(spec=QKeyEvent)
    event.key.return_value = Qt.Key.Key_Backspace
    return event


def _click_anchor(tool, x: float, y: float) -> None:
    """Press + release at the same scene position — a 'click' with no drag."""
    event = _left_click_event()
    tool.mouse_press(event, QPointF(x, y))
    tool.mouse_release(event, QPointF(x, y))


def _bezier_items(view: CanvasView) -> list[BezierItem]:
    return [it for it in view.scene().items() if isinstance(it, BezierItem)]


class TestBezierToolWorkflow:
    def test_three_clicks_plus_enter_creates_bezier(self, canvas: CanvasView) -> None:
        canvas.set_active_tool(ToolType.BEZIER)
        tool = canvas.tool_manager.active_tool
        _click_anchor(tool, 0, 0)
        _click_anchor(tool, 100, 100)
        _click_anchor(tool, 200, 0)
        assert tool.key_press(_enter_event()) is True

        items = _bezier_items(canvas)
        assert len(items) == 1
        assert items[0].anchor_count == 3

    def test_escape_cancels_and_creates_nothing(self, canvas: CanvasView) -> None:
        canvas.set_active_tool(ToolType.BEZIER)
        tool = canvas.tool_manager.active_tool
        _click_anchor(tool, 0, 0)
        _click_anchor(tool, 50, 50)
        assert tool.key_press(_escape_event()) is True
        assert len(_bezier_items(canvas)) == 0
        assert tool.last_point is None

    def test_backspace_removes_last_anchor(self, canvas: CanvasView) -> None:
        canvas.set_active_tool(ToolType.BEZIER)
        tool = canvas.tool_manager.active_tool
        _click_anchor(tool, 0, 0)
        _click_anchor(tool, 50, 50)
        _click_anchor(tool, 100, 0)
        # Three anchors → backspace once → two anchors, last_point is the 2nd.
        assert tool.key_press(_backspace_event()) is True
        assert tool.last_point is not None
        assert tool.last_point.x() == 50
        # Enter finalizes with 2 anchors.
        assert tool.key_press(_enter_event()) is True
        items = _bezier_items(canvas)
        assert len(items) == 1
        assert items[0].anchor_count == 2

    def test_enter_with_single_anchor_does_nothing(self, canvas: CanvasView) -> None:
        canvas.set_active_tool(ToolType.BEZIER)
        tool = canvas.tool_manager.active_tool
        _click_anchor(tool, 0, 0)
        # Returns False because curve isn't complete yet.
        assert tool.key_press(_enter_event()) is False
        assert len(_bezier_items(canvas)) == 0

    def test_drag_sets_handles_smoothly(self, canvas: CanvasView) -> None:
        """Press + move (still pressed) + release → outgoing handle stretches
        to the drag end; incoming handle is the mirror around the anchor."""
        canvas.set_active_tool(ToolType.BEZIER)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()
        tool.mouse_press(event, QPointF(50, 50))
        tool.mouse_move(event, QPointF(80, 50))  # drag handle 30 units to the right
        tool.mouse_release(event, QPointF(80, 50))
        # The single in-progress anchor has handle_out at (80, 50) and
        # handle_in mirrored to (20, 50).
        assert tool._handles_out[0].x() == 80
        assert tool._handles_in[0].x() == 20

    def test_click_only_anchors_get_catmull_rom_tangents(
        self, canvas: CanvasView
    ) -> None:
        """Manual-test feedback from PR #191: plain-click authoring should
        produce a smooth curve through the clicked points, not a polyline."""
        canvas.set_active_tool(ToolType.BEZIER)
        tool = canvas.tool_manager.active_tool
        _click_anchor(tool, 0, 0)
        _click_anchor(tool, 100, 50)
        _click_anchor(tool, 200, 0)
        assert tool.key_press(_enter_event()) is True

        item = _bezier_items(canvas)[0]
        # First anchor: handle_out at 1/3 of the way to anchor[1].
        assert item.handles_out[0].x() == pytest.approx(100 / 3.0)
        assert item.handles_out[0].y() == pytest.approx(50 / 3.0)
        # Middle anchor: symmetric Catmull-Rom (tension 0.5).
        #   tx = (200 - 0) / 6 = 33.333..., ty = (0 - 0) / 6 = 0
        assert item.handles_out[1].x() == pytest.approx(100 + 200 / 6.0)
        assert item.handles_out[1].y() == pytest.approx(50)
        assert item.handles_in[1].x() == pytest.approx(100 - 200 / 6.0)
        assert item.handles_in[1].y() == pytest.approx(50)
        # Last anchor: handle_in at 1/3 of the way back to anchor[n-2].
        assert item.handles_in[2].x() == pytest.approx(200 - 100 / 3.0)
        assert item.handles_in[2].y() == pytest.approx(50 / 3.0)

    def test_dragged_anchor_keeps_explicit_handles(
        self, canvas: CanvasView
    ) -> None:
        """Auto-smooth only fires on click-only anchors. Explicitly-dragged
        anchors must keep their user-set tangents."""
        canvas.set_active_tool(ToolType.BEZIER)
        tool = canvas.tool_manager.active_tool
        # Anchor 0: click only (no drag).
        _click_anchor(tool, 0, 0)
        # Anchor 1: press, drag handle to (150, 50), release.
        event = _left_click_event()
        tool.mouse_press(event, QPointF(100, 0))
        tool.mouse_move(event, QPointF(150, 50))
        tool.mouse_release(event, QPointF(150, 50))
        # Anchor 2: click only.
        _click_anchor(tool, 200, 0)
        assert tool.key_press(_enter_event()) is True

        item = _bezier_items(canvas)[0]
        # Middle anchor was dragged → handle_out at (150, 50), handle_in
        # mirrored to (50, -50). Auto-smooth must leave these alone.
        assert item.handles_out[1].x() == pytest.approx(150)
        assert item.handles_out[1].y() == pytest.approx(50)
        assert item.handles_in[1].x() == pytest.approx(50)
        assert item.handles_in[1].y() == pytest.approx(-50)

    def test_persists_through_save_and_reload(
        self, canvas: CanvasView, tmp_path
    ) -> None:
        canvas.set_active_tool(ToolType.BEZIER)
        tool = canvas.tool_manager.active_tool
        _click_anchor(tool, 0, 0)
        _click_anchor(tool, 80, 60)
        _click_anchor(tool, 160, 0)
        assert tool.key_press(_enter_event()) is True

        before = _bezier_items(canvas)
        assert len(before) == 1
        orig_count = before[0].anchor_count

        from open_garden_planner.core.project import ProjectManager

        pm = ProjectManager()
        out_path = tmp_path / "bezier_roundtrip.ogp"
        pm.save(canvas.scene(), out_path)
        assert out_path.exists()

        canvas.scene().clear()
        pm.load(canvas.scene(), out_path)

        after = _bezier_items(canvas)
        assert len(after) == 1
        assert after[0].anchor_count == orig_count


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
