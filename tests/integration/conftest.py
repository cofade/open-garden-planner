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
import warnings
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
    """Stop any Agent API server still attached to a live app, and SAY SO if one survives.

    **A safety net, not a fix.** An unresolved CI segfault (exit 139) has a stack
    naming ``agent_api/server.py`` ``_run`` — a live uvicorn event loop — so a
    leaked server thread is the standing suspect. This fixture stops any server a
    top-level app still owns and reports one that outlives the test.

    Two corrections to an earlier version of this docstring, both found by the
    final pre-merge review, and both the kind of thing that sends the next
    person down a dead end:

    * It claimed the ``QTimer.singleShot(1500, _maybe_start_agent_api)`` in
      ``GardenPlannerApp.__init__`` lets an app auto-start a server during tests.
      **It cannot.** ``tests/conftest.py``'s autouse
      ``_disable_agent_api_server`` sets ``KEY_AGENT_API_ENABLED = False`` for
      every test, so ``_maybe_start_agent_api`` returns immediately. That claim
      was never verified and is falsified by the suite's own fixture.
    * It reached the app via ``_stop_agent_api()``, which reaches only the app's
      OWN server. The tests that construct ``AgentApiServer(...)`` directly
      (``test_agent_api_exports.py``, ``test_agent_api_frozen_exe.py``) are
      outside its reach — though all of those do call ``stop()`` themselves.

    So this catches a leak through the *app*, and the true source of the
    remaining crash is **not established**. It is kept because a leak warning
    that survives to the pytest summary is worth having; it is not evidence that
    the crash is understood.

    **Requesting ``qtbot`` is load-bearing**: pytest finalises fixtures in
    REVERSE setup order, so depending on ``qtbot`` makes this tear down LAST,
    while the app still exists. Without it this could run after the window is
    destroyed — stopping a server whose providers already point at a dead
    QObject.
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
        # `warnings.warn`, not `print`: pytest captures stdout by default (the
        # suite runs without `-s`), so a printed warning is discarded — and in a
        # segfault the process is already dead. A warning reaches the summary.
        warnings.warn(
            f"{len(leaked)} live {SERVER_THREAD_NAME} thread(s) outlived a test. "
            "A leaked uvicorn loop keeps its sockets and its MainThreadBridge "
            "alive, which is the standing suspect for the unresolved exit-139 "
            "segfault (see docs §11.4). Note that a test constructing "
            "AgentApiServer(...) directly is NOT covered by this fixture.",
            ResourceWarning,
            stacklevel=1,
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
