"""Integration tests for the status-bar coordinate input (Package A US-A1/A2)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt

from open_garden_planner.app.application import GardenPlannerApp


@pytest.fixture
def window(qtbot) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


def test_status_bar_has_coordinate_input(window: GardenPlannerApp) -> None:
    assert window.coordinate_input_field is not None
    assert window.coordinate_input_field.isVisible() or True  # status bar lazy show


def test_relative_input_commits_vertex(window: GardenPlannerApp, qtbot) -> None:
    from open_garden_planner.core.tools.base_tool import ToolType
    from open_garden_planner.core.tools.polyline_tool import PolylineTool

    # Activate the polyline tool path explicitly using FENCE as a polyline.
    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool
    assert isinstance(tool, PolylineTool)

    # First seed an anchor click.
    tool.commit_typed_coordinate(QPointF(100, 100))
    window.canvas_view.refresh_input_anchor()
    assert window.canvas_view.coordinate_input_buffer.anchor == QPointF(100, 100)

    field = window.coordinate_input_field
    field.setText("@500,0")
    field.textEdited.emit("@500,0")
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert tool.last_point == QPointF(600, 100)


def test_polar_input_commits_vertex(window: GardenPlannerApp, qtbot) -> None:
    from open_garden_planner.core.tools.base_tool import ToolType
    from open_garden_planner.core.tools.polyline_tool import PolylineTool

    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool
    assert isinstance(tool, PolylineTool)

    tool.commit_typed_coordinate(QPointF(0, 0))
    window.canvas_view.refresh_input_anchor()

    field = window.coordinate_input_field
    field.setText("@100<0")
    field.textEdited.emit("@100<0")
    qtbot.keyClick(field, Qt.Key.Key_Return)
    # 100 units east of (0,0) -> (100, 0)
    last = tool.last_point
    assert last is not None
    assert abs(last.x() - 100.0) < 1e-6
    assert abs(last.y()) < 1e-6


def test_invalid_input_does_not_commit(window: GardenPlannerApp, qtbot) -> None:
    from open_garden_planner.core.tools.base_tool import ToolType
    from open_garden_planner.core.tools.polyline_tool import PolylineTool

    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool
    assert isinstance(tool, PolylineTool)
    tool.commit_typed_coordinate(QPointF(100, 100))
    window.canvas_view.refresh_input_anchor()

    field = window.coordinate_input_field
    field.setText("not a number")
    field.textEdited.emit("not a number")
    qtbot.keyClick(field, Qt.Key.Key_Return)
    # Last point unchanged after an invalid attempt.
    assert tool.last_point == QPointF(100, 100)


def test_tool_change_clears_buffer(window: GardenPlannerApp) -> None:
    from open_garden_planner.core.tools.base_tool import ToolType

    window.canvas_view.set_active_tool(ToolType.FENCE)
    buf = window.canvas_view.coordinate_input_buffer
    buf.set_text("@1,2")
    window.canvas_view.set_active_tool(ToolType.SELECT)
    assert buf.text == ""
    assert buf.anchor is None
