"""Shared fixtures for integration tests.

All tests here exercise full UI workflows:
  tool activate → mouse gesture → scene state assertion.

Coordinate note (see arc42 section 8.10):
  - Tools receive *scene* coordinates (Qt Y-down, (0,0) = top-left).
  - Canvas coordinates (Y-up, (0,0) = bottom-left) are what the user sees.
  - Always pass scene coordinates to tool.mouse_press/move/release.
  - Disable snapping to get predictable test results.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    """Minimal canvas setup with snapping disabled for predictable coordinates."""
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


@pytest.fixture()
def mouse_event() -> MagicMock:
    """Standard left-click mouse event mock.

    The tool API reads event.button() and event.modifiers(); both are stubbed here.
    """
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def draw_rect(
    view: CanvasView,
    event: MagicMock,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> None:
    """Simulate a rectangle drag in scene coordinates (Y-down).

    Args:
        view: The canvas view (tool manager is read from here).
        event: Left-click mouse event mock.
        x1, y1: Start corner in scene coords.
        x2, y2: End corner in scene coords.
    """
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(x1, y1))
    tool.mouse_move(event, QPointF(x2, y2))
    tool.mouse_release(event, QPointF(x2, y2))
