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
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtWidgets import QApplication

from open_garden_planner.agent_api.server import SERVER_THREAD_NAME
from open_garden_planner.core.item_look import fill_brush, style_gaps
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

      **SUPERSEDED (#509) — read this before relying on the paragraph above.**
      The fixture's guarantee used to have a hole: the write lived in
      ``_disable_agent_api_server`` while the key wipe lived in the autouse
      ``_reset_app_settings`` it merely depended on, so the instant BETWEEN them had
      no ``agent_api/enabled`` key at all. A read in that window returned the
      production default (True) and the port read 8765, and a timer landing there
      started a REAL server — measured under ``pytest -n 8`` as
      ``OSError: [Errno 10048]``. The write now happens inside the wipe, so the
      window is gone; see ``tests/conftest.py``'s ``_reset()``.

      And the whole hazard class is now closed at its source. What is passed to
      ``singleShot`` is the **bound method** ``self._maybe_start_agent_api``, and
      PyQt auto-disconnects a bound-method slot when its receiver is destroyed. The
      new ``_reclaim_widgets`` fixture destroys every top-level widget at the end of
      each test, so a pending 1500 ms timer cannot outlive the app that armed it —
      which is why the fix is a reclaim fixture rather than a settings write.
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


@contextlib.contextmanager
def watched_scenes() -> Iterator[list[CanvasScene]]:
    """Every ``CanvasScene`` built inside the block, in the order built — the list
    keeps them alive, so a scene the code under test let go of can still be judged."""
    scenes: list[CanvasScene] = []
    build = CanvasScene.__init__

    def tracked(self: CanvasScene, *args: object, **kwargs: object) -> None:
        build(self, *args, **kwargs)
        scenes.append(self)

    CanvasScene.__init__ = tracked  # type: ignore[method-assign]
    try:
        yield scenes
    finally:
        CanvasScene.__init__ = build  # type: ignore[method-assign]


def style_gaps_in(scenes: list[CanvasScene]) -> list[str]:
    """Every item of ``scenes`` whose style attributes do not describe its brush and
    pen (``core.item_look.style_gaps``) — one line an item, [] when all are in step.
    A scene whose C++ object is gone is skipped."""
    found: list[str] = []
    for scene in scenes:
        if sip.isdeleted(scene):
            continue
        for item in scene.items():
            if not (callable(getattr(item, "pen", None)) and callable(getattr(item, "brush", None))):
                continue
            gaps = style_gaps(item)
            if gaps:
                kind = getattr(getattr(item, "object_type", None), "name", "-")
                found.append(f"{type(item).__name__} {kind}: {'; '.join(gaps)}")
    return found


def fail_on_style_gaps(scenes: list[CanvasScene]) -> None:
    """Fail the running test if an item of ``scenes`` is out of step (``style_gaps_in``)."""
    found = style_gaps_in(scenes)
    if found:
        shown = "\n  ".join(found[:12])
        more = f"\n  … and {len(found) - 12} more" if len(found) > 12 else ""
        pytest.fail(
            f"{len(found)} item(s) whose style attributes do not describe their brush and pen "
            f"(core/item_look.py — give an item its pen with adopt_pen, its look with "
            f"copy_visual_style):\n  {shown}{more}", pytrace=False)


def recolour(item: Any, colour: QColor | str) -> None:
    """Give an item a fill colour the way the properties panel does: the attribute
    AND the brush (a test that sets only the brush builds an item no user can make —
    and the guard below says so)."""
    item.fill_color = QColor(colour)
    item.setBrush(fill_brush(item, QColor(colour)))


def guarded(node: Any) -> Iterator[None]:
    """What the guard below does around ONE test, as a generator: up to its ``yield``
    the set-up, after it the judgement. ``node``: the test (anything that answers
    ``get_closest_marker``). A function of its own so that a test can drive it by
    hand and see it fail — a fixture's teardown cannot be caught from inside its test."""
    marker = node.get_closest_marker("style_gaps_allowed")
    if marker is not None:
        assert marker.args and str(marker.args[0]).strip(), "style_gaps_allowed needs its reason"
        yield
        return
    with watched_scenes() as scenes:
        yield
        fail_on_style_gaps(scenes)


@pytest.fixture(autouse=True)
def _every_item_says_what_it_paints(request: pytest.FixtureRequest, qtbot: object):
    """THE GUARD of the rule in ``core/item_look.py``: at the end of every test in
    this folder, every item of every ``CanvasScene`` the test built states the look it
    paints — its style attributes describe its live brush and pen.

    Behavioural on purpose. The rule was first guarded by reading the source for
    functions that build an item from an item (the map in
    ``test_item_style_in_step.py``); a review planted six forgetful operations and
    the scan saw one. This fixture does not care HOW a writer is spelled or where it
    lives: whatever a test drives — a tool, the properties panel, an undo, the
    loader, the Agent API, the test's own hand — leaves its items here to be judged.

    What it cannot see: a writer no test in this folder drives; an item that has
    left its scene before the test ends; a scene built before the test's own
    fixtures were set up (by a module- or session-scoped fixture).

    ``@pytest.mark.style_gaps_allowed("why")`` takes a test out — for a test that
    puts an item out of step ON PURPOSE (to show that a reader does not trust the
    attributes, or to pin a defect that is left open: the reason then names its
    follow-up issue). The reason is mandatory.

    Requests ``qtbot`` so that it is finalised BEFORE the widgets that own the
    scenes are closed (fixtures are torn down in reverse setup order).
    """
    yield from guarded(request.node)


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
