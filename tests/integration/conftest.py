"""Shared fixtures for integration tests.

All tests here exercise full UI workflows:
  tool activate → mouse gesture → scene state assertion.

Coordinate note (see arc42 section 8.10):
  - Tools receive *scene* coordinates (Qt Y-down, (0,0) = top-left).
  - Canvas coordinates (Y-up, (0,0) = bottom-left) are what the user sees.
  - Always pass scene coordinates to tool.mouse_press/move/release.
  - Disable snapping to get predictable test results.
"""

import contextlib
import threading
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from open_garden_planner.agent_api.server import SERVER_THREAD_NAME
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView


@pytest.fixture(autouse=True)
def _no_leaked_agent_api_thread(qtbot: object):
    """Stop any Agent API server a test's app auto-started, and say so if one survives.

    ``GardenPlannerApp.__init__`` schedules ``QTimer.singleShot(1500,
    _maybe_start_agent_api)``, so an app built by a test can start a REAL
    uvicorn server on its own — 1.5 s later, on whatever event loop happens to
    run then, which is frequently a *later* test.

    That server is not untidy, it is a **crash**. The CI stack for the exit-139
    segfault names ``server.py:1624`` in ``_run`` — the crashing thread IS the
    event loop — and the loop holds a ``MainThreadBridge`` plus provider
    callables that close over the app. If the app is destroyed first, the loop
    is left touching a dead QObject.

    **Requesting ``qtbot`` is load-bearing.** pytest finalises fixtures in
    REVERSE setup order, so depending on ``qtbot`` guarantees it is set up first
    and torn down LAST — which is what makes the code below run while the app
    still exists. Without that, this fixture can run after ``qtbot`` has already
    deleted the window, and stopping the server afterwards is stopping something
    that can already crash. (The first version did not request it; the segfault
    survived it, at 16% of the run instead of 68%.)

    A warning rather than a hard assert: a test that deliberately exercises a
    running server owns stopping it, and this must not become a confusing second
    failure. The real invariant is pinned deterministically in
    ``test_agent_api_lifecycle.py``.
    """
    yield

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        stop = getattr(widget, "_stop_agent_api", None)
        if callable(stop):
            # Teardown must never mask the test that just failed.
            with contextlib.suppress(Exception):
                stop()
    leaked = [
        t
        for t in threading.enumerate()
        if t.name == SERVER_THREAD_NAME and t.is_alive()
    ]
    if leaked:
        print(
            f"\n[conftest] WARNING: {len(leaked)} live {SERVER_THREAD_NAME} thread(s) "
            f"after this test — a GardenPlannerApp auto-started the Agent API "
            f"(QTimer.singleShot 1500) and nothing stopped it."
        )


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
