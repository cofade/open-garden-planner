"""Integration tests for the Dynamic Input overlay (Package A US-A4)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.core.tools.polyline_tool import PolylineTool


@pytest.fixture
def window(qtbot) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.resize(800, 600)
    win.show()
    qtbot.waitExposed(win)
    return win


def _move_cursor(view, viewport_pos: QPoint) -> None:
    """Simulate a mouseMove inside the view."""
    event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(viewport_pos),
        QPointF(viewport_pos),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseMoveEvent(event)


def test_overlay_hidden_without_anchor(window: GardenPlannerApp) -> None:
    window.canvas_view.set_active_tool(ToolType.FENCE)
    _move_cursor(window.canvas_view, QPoint(100, 100))
    # No commit has happened yet -> last_point is None -> overlay hidden.
    overlay = window.canvas_view._dynamic_overlay
    if overlay is not None:
        assert not overlay.isVisible()


def test_overlay_shown_after_anchor(window: GardenPlannerApp) -> None:
    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool
    assert isinstance(tool, PolylineTool)
    tool.commit_typed_coordinate(QPointF(0, 0))
    window.canvas_view.refresh_input_anchor()

    _move_cursor(window.canvas_view, QPoint(100, 100))
    overlay = window.canvas_view._dynamic_overlay
    assert overlay is not None
    assert overlay.isVisible()


def test_overlay_hides_for_select_tool(window: GardenPlannerApp) -> None:
    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool
    tool.commit_typed_coordinate(QPointF(0, 0))
    window.canvas_view.refresh_input_anchor()
    _move_cursor(window.canvas_view, QPoint(100, 100))
    overlay = window.canvas_view._dynamic_overlay
    assert overlay is not None and overlay.isVisible()

    window.canvas_view.set_active_tool(ToolType.SELECT)
    _move_cursor(window.canvas_view, QPoint(100, 100))
    assert not overlay.isVisible()


def test_overlay_disabled_via_setting(window: GardenPlannerApp) -> None:
    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool
    tool.commit_typed_coordinate(QPointF(0, 0))
    window.canvas_view.refresh_input_anchor()

    window.canvas_view.set_dynamic_input_enabled(False)
    _move_cursor(window.canvas_view, QPoint(100, 100))
    overlay = window.canvas_view._dynamic_overlay
    # Either the overlay was never created, or it is hidden.
    if overlay is not None:
        assert not overlay.isVisible()


def test_overlay_mirrors_buffer(window: GardenPlannerApp) -> None:
    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool
    tool.commit_typed_coordinate(QPointF(0, 0))
    window.canvas_view.refresh_input_anchor()
    _move_cursor(window.canvas_view, QPoint(100, 100))

    buf = window.canvas_view.coordinate_input_buffer
    buf.set_text("@300<45")

    overlay = window.canvas_view._dynamic_overlay
    assert overlay is not None
    # Internal accessors (test-only) - distance/angle fields reflect buffer.
    assert overlay._distance_edit.text() == "300"  # noqa: SLF001
    assert overlay._angle_edit.text() == "45"  # noqa: SLF001
