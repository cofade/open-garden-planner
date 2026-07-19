"""Integration test for :class:`ConnectAiAssistantDialog` (US-D1.6).

Exercises the actual UI-to-service wiring end-to-end: clicking "Add to
Cursor" really calls through to ``services.ai_client_onboarding`` and writes
a real (tmp_path-redirected) config file, not a mocked call — the mandatory
integration-test policy (§8.10) wants the real workflow covered, not just
the pure service unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QGroupBox, QLabel, QPlainTextEdit, QPushButton

from open_garden_planner.ui.dialogs.connect_ai_assistant_dialog import (
    ConnectAiAssistantDialog,
)

_URL = "http://127.0.0.1:8765/mcp"


def _group(dialog: ConnectAiAssistantDialog, title: str) -> QGroupBox:
    for group in dialog.findChildren(QGroupBox):
        if group.title() == title:
            return group
    raise AssertionError(f"No group box titled {title!r}")


@pytest.fixture()
def isolated_clients(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect client detection/install to tmp_path; only Cursor is detected."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        "open_garden_planner.services.ai_client_onboarding.shutil.which", lambda _cmd: None
    )
    (tmp_path / ".cursor").mkdir()
    return tmp_path


class TestConnectAiAssistantDialogEnabled:
    def test_shows_url_and_all_client_rows(self, qtbot, isolated_clients: Path) -> None:
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        labels = [w.text() for w in dialog.findChildren(QLabel)]
        assert any(_URL in text for text in labels)
        for title in ("Cursor", "Claude Code", "Claude Desktop"):
            _group(dialog, title)  # raises if missing

    def test_copy_url_button_sets_clipboard(self, qtbot, isolated_clients: Path) -> None:
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        copy_btn = _group(dialog, "Connect URL").findChild(QPushButton)
        qtbot.mouseClick(copy_btn, Qt.MouseButton.LeftButton)

        clipboard = QApplication.clipboard()
        assert clipboard is not None
        assert clipboard.text() == _URL

    def test_add_to_cursor_writes_real_config(self, qtbot, isolated_clients: Path) -> None:
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        cursor_group = _group(dialog, "Cursor")
        add_btn = next(
            b for b in cursor_group.findChildren(QPushButton) if b.text() == "Add to Cursor"
        )
        assert add_btn.isEnabled()
        qtbot.mouseClick(add_btn, Qt.MouseButton.LeftButton)

        config_path = isolated_clients / ".cursor" / "mcp.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["mcpServers"]["open-garden-planner"] == {"url": _URL}
        assert "Added to Cursor" in dialog._status_label.text()

    def test_add_to_cursor_failure_shows_translated_status(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """A real (not mocked) fs-level failure — mcp.json is a directory, so
        the write really raises IsADirectoryError — exercises the dialog's
        failure branch end-to-end, not just its success branch."""
        config_path = isolated_clients / ".cursor" / "mcp.json"
        config_path.mkdir()  # a directory where a file is expected

        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        cursor_group = _group(dialog, "Cursor")
        add_btn = next(
            b for b in cursor_group.findChildren(QPushButton) if b.text() == "Add to Cursor"
        )
        qtbot.mouseClick(add_btn, Qt.MouseButton.LeftButton)

        status = dialog._status_label.text()
        assert "Could not add to Cursor" in status
        assert config_path.is_dir()  # untouched — the failure didn't corrupt anything

    def test_claude_desktop_has_no_add_button_only_snippet(
        self, qtbot, isolated_clients: Path
    ) -> None:
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        desktop_group = _group(dialog, "Claude Desktop")
        add_buttons = [
            b for b in desktop_group.findChildren(QPushButton) if b.text().startswith("Add to")
        ]
        assert add_buttons == []

    def test_show_manual_snippet_reveals_url(self, qtbot, isolated_clients: Path) -> None:
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)
        dialog.show()  # isVisible() composes with ancestor visibility

        desktop_group = _group(dialog, "Claude Desktop")
        toggle = next(
            b for b in desktop_group.findChildren(QPushButton) if b.text() == "Show manual snippet"
        )
        snippet = desktop_group.findChild(QPlainTextEdit)
        assert snippet.isVisible() is False

        qtbot.mouseClick(toggle, Qt.MouseButton.LeftButton)

        assert snippet.isVisible() is True
        assert snippet.toPlainText() == _URL


_TOKEN = "connect-dialog-token-xyz"


class TestConnectAiAssistantDialogWithToken:
    """When AI editing is on, a token is passed and must ride the URL (the
    delivery route that works with clients that drop auth headers)."""

    def test_copy_url_includes_token(self, qtbot, isolated_clients: Path) -> None:
        dialog = ConnectAiAssistantDialog(_URL, token=_TOKEN)
        qtbot.addWidget(dialog)

        copy_btn = _group(dialog, "Connect URL").findChild(QPushButton)
        qtbot.mouseClick(copy_btn, Qt.MouseButton.LeftButton)

        clipboard = QApplication.clipboard()
        assert clipboard is not None
        assert clipboard.text() == f"{_URL}?token={_TOKEN}"

    def test_add_to_cursor_embeds_token_in_url(self, qtbot, isolated_clients: Path) -> None:
        dialog = ConnectAiAssistantDialog(_URL, token=_TOKEN)
        qtbot.addWidget(dialog)

        cursor_group = _group(dialog, "Cursor")
        add_btn = next(
            b for b in cursor_group.findChildren(QPushButton) if b.text() == "Add to Cursor"
        )
        qtbot.mouseClick(add_btn, Qt.MouseButton.LeftButton)

        data = json.loads(
            (isolated_clients / ".cursor" / "mcp.json").read_text(encoding="utf-8")
        )
        entry = data["mcpServers"]["open-garden-planner"]
        assert entry == {"url": f"{_URL}?token={_TOKEN}"}


class TestConnectAiAssistantDialogDisabled:
    def test_shows_warning_and_no_client_rows(self, qtbot) -> None:
        dialog = ConnectAiAssistantDialog(None)
        qtbot.addWidget(dialog)

        assert dialog.findChildren(QGroupBox) == []
        labels = " ".join(w.text() for w in dialog.findChildren(QLabel))
        assert "disabled" in labels.lower()
