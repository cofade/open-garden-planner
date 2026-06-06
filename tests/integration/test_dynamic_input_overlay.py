"""Integration tests for the Dynamic Input overlay (Package A US-A4)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.core.tools.polyline_tool import PolylineTool
from open_garden_planner.ui.canvas.items import PolylineItem


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch) -> GardenPlannerApp:
    """Build the app with autosave isolated to ``tmp_path`` (issue #190).

    Untitled auto-saves and the startup recovery scan both resolve through
    ``tempfile.gettempdir()``; redirecting it at ``tmp_path`` sandboxes the
    deferred autosave write so it can't corrupt a later test's startup
    recovery scan on Windows. The autosave timer is also stopped on teardown
    so no write fires during widget destruction — which lets these tests
    exercise the *real* polyline finalize path instead of monkeypatching it.
    """
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.resize(800, 600)
    win.show()
    qtbot.waitExposed(win)
    yield win
    if getattr(win, "_autosave_manager", None) is not None:
        win._autosave_manager.stop()


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


def _press_text(view, text: str) -> None:
    """Synthesize a printable key press whose `event.text()` is ``text``."""
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_unknown,
        Qt.KeyboardModifier.NoModifier,
        text,
    )
    view.keyPressEvent(event)


def test_canvas_typing_routes_to_overlay_polar(
    window: GardenPlannerApp,
) -> None:
    """Typing `@300<45` on the canvas commits a polar point."""
    view = window.canvas_view
    view.set_active_tool(ToolType.FENCE)
    tool = view._tool_manager.active_tool
    assert isinstance(tool, PolylineTool)
    tool.commit_typed_coordinate(QPointF(0, 0))
    view.refresh_input_anchor()
    _move_cursor(view, QPoint(100, 100))

    for ch in "@300<45":
        _press_text(view, ch)

    overlay = view._dynamic_overlay
    assert overlay is not None
    assert overlay.isVisible()
    assert overlay._distance_edit.text() == "@300<45"  # noqa: SLF001
    # Buffer mirrors the raw distance text in raw-mode.
    assert view.coordinate_input_buffer.text == "@300<45"

    # Commit via Return on the distance edit.
    enter = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier,
        "\r",
    )
    overlay._distance_edit.keyPressEvent(enter)  # noqa: SLF001

    pts = tool._points  # noqa: SLF001
    assert len(pts) == 2
    # 300 east, math-up-positive angle 45deg -> dx=300*cos45, dy=-300*sin45.
    assert pts[1].x() == pytest.approx(300 * 0.7071, abs=0.01)
    assert pts[1].y() == pytest.approx(-300 * 0.7071, abs=0.01)


def test_canvas_typing_routes_to_overlay_relative_cartesian(
    window: GardenPlannerApp,
) -> None:
    """Typing `@500,0` on the canvas commits a relative-cartesian point.

    The distance field carries the raw `@500,0` string and the overlay
    passes it to the buffer untouched (raw-mode), not as a polar
    `@500,0<0`.  Both happen to coincide for this input but the test
    verifies the buffer text path.
    """
    view = window.canvas_view
    view.set_active_tool(ToolType.FENCE)
    tool = view._tool_manager.active_tool
    tool.commit_typed_coordinate(QPointF(100, 200))
    view.refresh_input_anchor()
    _move_cursor(view, QPoint(50, 50))

    for ch in "@500,0":
        _press_text(view, ch)

    assert view.coordinate_input_buffer.text == "@500,0"

    overlay = view._dynamic_overlay
    enter = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier,
        "\r",
    )
    overlay._distance_edit.keyPressEvent(enter)  # noqa: SLF001

    pts = tool._points  # noqa: SLF001
    assert len(pts) == 2
    assert pts[1].x() == pytest.approx(600.0)  # 100 + 500
    # Parser interprets user-entered Y math-up-positive and subtracts on
    # apply: anchor.y() - 0 = 200.
    assert pts[1].y() == pytest.approx(200.0)


def test_overlay_freezes_while_user_is_typing(
    window: GardenPlannerApp,
) -> None:
    """Once a character is typed, mouseMove must not re-position the overlay."""
    view = window.canvas_view
    view.set_active_tool(ToolType.FENCE)
    tool = view._tool_manager.active_tool
    tool.commit_typed_coordinate(QPointF(0, 0))
    view.refresh_input_anchor()
    _move_cursor(view, QPoint(100, 100))

    overlay = view._dynamic_overlay
    assert overlay is not None
    pos_before_typing = overlay.pos()

    _press_text(view, "5")
    pos_while_typing = overlay.pos()

    # Move the mouse far away — the overlay must stay put.
    _move_cursor(view, QPoint(400, 400))
    pos_after_move = overlay.pos()

    assert pos_while_typing == pos_after_move, (
        "Overlay shifted while user was mid-typing — fields became unreachable."
    )
    # Sanity: typing did not displace the overlay from where it was shown.
    assert pos_before_typing == pos_while_typing


def test_typed_enter_does_not_finalize_polyline(
    window: GardenPlannerApp,
) -> None:
    """Regression: Enter on a typed coordinate must NOT also finalize the polyline.

    The polyline tool's ``key_press`` finalizes on Enter when ``len(points) >=
    2``.  QLineEdit's default keyPressEvent calls ``event.ignore()`` for
    Return, so without an explicit accept in ``_DynamicLineEdit`` the Enter
    would propagate to ``CanvasView.keyPressEvent`` and finish the polyline
    immediately after the typed vertex committed.
    """
    view = window.canvas_view
    view.set_active_tool(ToolType.FENCE)
    tool = view._tool_manager.active_tool
    assert isinstance(tool, PolylineTool)
    tool.commit_typed_coordinate(QPointF(0, 0))
    view.refresh_input_anchor()
    _move_cursor(view, QPoint(100, 100))

    # Type "500" then Enter via the overlay routing path.
    for ch in "500":
        _press_text(view, ch)

    overlay = view._dynamic_overlay
    assert overlay is not None
    enter = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier,
        "\r",
    )
    overlay._distance_edit.keyPressEvent(enter)  # noqa: SLF001

    # Two vertices placed, tool still in drawing mode — the polyline must
    # NOT have been finalized.
    assert len(tool._points) == 2  # noqa: SLF001
    assert tool._is_drawing  # noqa: SLF001


def test_empty_enter_forwards_to_active_tool(
    window: GardenPlannerApp,
) -> None:
    """Empty-Enter on the overlay forwards Return to the active tool, which
    finalizes the real polyline.

    Exercises the genuine ``PolylineTool`` finalize path end-to-end (issue
    #190): two vertices are committed, then an empty-Enter on the overlay
    forwards a synthetic Return that the tool turns into a committed
    ``PolylineItem``. The autosave write this triggers is sandboxed by the
    ``window`` fixture, so no heap corruption leaks into later tests.
    """
    view = window.canvas_view
    view.set_active_tool(ToolType.FENCE)
    tool = view._tool_manager.active_tool
    assert isinstance(tool, PolylineTool)
    tool.commit_typed_coordinate(QPointF(0, 0))
    tool.commit_typed_coordinate(QPointF(100, 0))
    view.refresh_input_anchor()
    _move_cursor(view, QPoint(100, 100))

    overlay = view._dynamic_overlay
    assert overlay is not None
    assert overlay.isVisible()

    polys_before = [i for i in view.scene().items() if isinstance(i, PolylineItem)]

    enter = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier,
        "\r",
    )
    overlay._distance_edit.keyPressEvent(enter)  # noqa: SLF001

    # Real finalize: a new PolylineItem is committed and the tool stops drawing.
    polys_after = [i for i in view.scene().items() if isinstance(i, PolylineItem)]
    assert len(polys_after) == len(polys_before) + 1, (
        "Empty-Enter on the overlay must forward Return so the polyline tool "
        "finalizes a real PolylineItem."
    )
    assert not tool._is_drawing  # noqa: SLF001
    # Overlay hidden after the empty-Enter forward.
    assert not overlay.isVisible()


def test_overlay_resumes_tracking_after_commit(
    window: GardenPlannerApp,
) -> None:
    """After commit clears the fields, the overlay follows the cursor again."""
    view = window.canvas_view
    view.set_active_tool(ToolType.FENCE)
    tool = view._tool_manager.active_tool
    tool.commit_typed_coordinate(QPointF(0, 0))
    view.refresh_input_anchor()
    _move_cursor(view, QPoint(100, 100))

    for ch in "@200<0":
        _press_text(view, ch)

    overlay = view._dynamic_overlay
    enter = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier,
        "\r",
    )
    overlay._distance_edit.keyPressEvent(enter)  # noqa: SLF001

    # Fields cleared, focus returned to view -> not capturing.
    assert not overlay.is_capturing_input()

    pos_after_commit = overlay.pos()
    _move_cursor(view, QPoint(400, 400))
    pos_after_move = overlay.pos()
    assert pos_after_move != pos_after_commit, (
        "Overlay did not resume cursor-tracking after commit."
    )
