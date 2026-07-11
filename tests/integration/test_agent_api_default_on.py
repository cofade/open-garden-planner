"""Default-on containment (US-D1.1).

The Agent API server defaults to ON in production, so the test harness must keep
it disabled and the app's auto-start path must honour that — otherwise a full-app
test that pumps the event loop past the 1500 ms deferred start would bind a real
loopback port and hang. These tests are the positive proof that containment
holds (they fail loudly if the autouse guard regresses).
"""

from __future__ import annotations

from typing import Any

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings


def test_guard_keeps_agent_api_disabled_in_tests() -> None:
    # The autouse `_disable_agent_api_server` fixture must win over the new
    # default-ON, so no test ever binds 127.0.0.1:8765.
    assert get_settings().agent_api_enabled is False


def test_app_does_not_autostart_server_when_disabled(qtbot: Any) -> None:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    # Invoke the deferred auto-start path directly (no 1500 ms wait). With the
    # guard keeping the setting off, it must NOT construct or bind a server.
    win._maybe_start_agent_api()
    try:
        assert win._agent_server is None
    finally:
        win._stop_agent_api()  # defensive no-op when None


class _StubAgentServer:
    """Minimal stand-in for AgentApiServer — no real socket bound."""

    def __init__(self, *, is_running: bool, url: str = "http://127.0.0.1:8765/mcp") -> None:
        self.is_running = is_running
        self.url = url


def test_agent_api_running_url_is_none_without_a_server(qtbot: Any) -> None:
    """US-D1.6: both the Help menu and Preferences 'Connect…' entry points
    derive their URL from this one method — pin it directly, not just
    through the fake-parent-window stand-ins used in the dialog-level tests."""
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        assert win._agent_server is None
        assert win.agent_api_running_url() is None
    finally:
        win._stop_agent_api()


def test_agent_api_running_url_reflects_is_running(qtbot: Any) -> None:
    """The exact bug US-D1.6 round 3 fixed: a *constructed* server that
    isn't actually running (e.g. it failed to bind) must still yield None,
    not its (dead) URL — is_running is the only source of truth."""
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        win._agent_server = _StubAgentServer(is_running=False)
        assert win.agent_api_running_url() is None

        win._agent_server = _StubAgentServer(is_running=True, url="http://127.0.0.1:9191/mcp")
        assert win.agent_api_running_url() == "http://127.0.0.1:9191/mcp"
    finally:
        win._agent_server = None
        win._stop_agent_api()


# ---------------------------------------------------------------------------
# US-D2.0: the app's own write-provider bodies + write-token accessor.
# The end-to-end server test (test_agent_api_writes.py) reimplements the write
# logic against a bare view; these pin GardenPlannerApp's actual delegation
# (_do_agent_move_object/_do_agent_delete_object/_resolve_agent_item), run
# directly on the main thread (no server, no networking, deterministic).
# ---------------------------------------------------------------------------


def _add_tree(win: GardenPlannerApp) -> Any:
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import CircleItem

    item = CircleItem(300, 300, 20, object_type=ObjectType.TREE)
    win.canvas_scene.addItem(item)
    return item


def _discard_on_close(monkeypatch: Any) -> None:
    """Mutating a plan dirties it; qtbot's teardown close would then block on the
    unsaved-changes modal. Auto-answer Discard (mirrors test_tasks.py)."""
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: QMessageBox.StandardButton.Discard,
    )


def test_do_agent_move_object_is_one_undoable_step(qtbot: Any, monkeypatch: Any) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        item = _add_tree(win)
        start = item.sceneBoundingRect().center()

        result = win._do_agent_move_object(str(item.item_id), 40.0, 10.0)

        moved = item.sceneBoundingRect().center()
        assert moved.x() == start.x() + 40.0
        assert moved.y() == start.y() + 10.0
        assert result["action"] == "move"
        assert result["x"] == moved.x() and result["y"] == moved.y()
        # Exactly one undo step, and it reverses cleanly.
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        back = item.sceneBoundingRect().center()
        assert back.x() == start.x() and back.y() == start.y()
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_do_agent_delete_object_is_one_undoable_step(qtbot: Any, monkeypatch: Any) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        item = _add_tree(win)
        item_id = item.item_id

        result = win._do_agent_delete_object(str(item_id))

        assert result["action"] == "delete"
        assert win.canvas_scene.find_item_by_id(item_id) is None
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert win.canvas_scene.find_item_by_id(item_id) is not None
    finally:
        win._stop_agent_api()


def test_resolve_agent_item_raises_on_unknown_or_bad_id(qtbot: Any) -> None:
    import pytest

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        with pytest.raises(ValueError):
            win._resolve_agent_item("not-a-uuid")
        with pytest.raises(ValueError):
            win._resolve_agent_item("00000000-0000-0000-0000-000000000000")
    finally:
        win._stop_agent_api()


def test_agent_api_write_token_only_when_running_and_writes_enabled(qtbot: Any) -> None:
    from open_garden_planner.app.settings import get_settings

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        settings = get_settings()
        settings.agent_api_writes_enabled = True
        # No running server -> None regardless of settings.
        assert win._agent_server is None
        assert win.agent_api_write_token() is None

        win._agent_server = _StubAgentServer(is_running=True)
        # Running + writes enabled -> the real token.
        assert win.agent_api_write_token() == settings.agent_api_token

        # Running but writes disabled -> None.
        settings.agent_api_writes_enabled = False
        assert win.agent_api_write_token() is None
    finally:
        win._agent_server = None
        win._stop_agent_api()
