"""Integration test for :class:`ConnectAiAssistantDialog` (US-D1.6).

Exercises the actual UI-to-service wiring end-to-end: clicking "Add to
Cursor" really calls through to ``services.ai_client_onboarding`` and writes
a real (tmp_path-redirected) config file, not a mocked call — the mandatory
integration-test policy (§8.10) wants the real workflow covered, not just
the pure service unit tests.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
)

from open_garden_planner.services import ai_client_onboarding as onboarding
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
    """Redirect client detection/install to tmp_path; only Cursor is detected by
    default (a test may seed ~/.claude.json to make Claude Code detected too).

    Clearing ``CLAUDE_CONFIG_DIR`` is load-bearing: ``_claude_code_user_config
    _path`` honours it, so leaving a real value set would make the Claude Code
    direct-merge tests write to the developer's actual config location instead
    of ``tmp_path``."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        "open_garden_planner.services.ai_client_onboarding.shutil.which", lambda _cmd: None
    )
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
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

    def test_claude_desktop_has_no_add_button_and_no_snippet(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """Claude Desktop can't reach a localhost server, so its row is an honest
        redirect note only — no add button and no (misleading) snippet to paste
        (issue #253)."""
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        desktop_group = _group(dialog, "Claude Desktop")
        assert desktop_group.findChildren(QPushButton) == []
        assert desktop_group.findChild(QPlainTextEdit) is None
        note = " ".join(w.text() for w in desktop_group.findChildren(QLabel))
        assert "claude code or cursor" in note.lower()

    def test_client_rows_are_in_a_resizable_scroll_area(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """Client rows scroll so a revealed snippet grows the scroll region
        instead of pushing Close off a fixed-size dialog (issue #253)."""
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        scroll = dialog.findChild(QScrollArea)
        assert scroll is not None
        assert scroll.widgetResizable() is True

    def test_show_manual_snippet_reveals_snippet(self, qtbot, isolated_clients: Path) -> None:
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)
        dialog.show()  # isVisible() composes with ancestor visibility

        cursor_group = _group(dialog, "Cursor")
        toggle = next(
            b for b in cursor_group.findChildren(QPushButton) if b.text() == "Show manual snippet"
        )
        snippet = cursor_group.findChild(QPlainTextEdit)
        assert snippet.isVisible() is False

        qtbot.mouseClick(toggle, Qt.MouseButton.LeftButton)

        assert snippet.isVisible() is True
        assert _URL in snippet.toPlainText()


_TOKEN = "connect-dialog-token-xyz"


class TestConnectAiAssistantDialogClaudeCodeOneClick:
    """The headline of issue #253: one-click Claude Code registration works
    WITHOUT the `claude` CLI — via a direct ~/.claude.json merge — end-to-end
    through the dialog (§8.10 mandatory integration coverage for the new
    user-facing capability)."""

    def test_add_to_claude_code_merges_config_and_shows_reconnect_note(
        self, qtbot, isolated_clients: Path
    ) -> None:
        # isolated_clients mocks `shutil.which` -> None (no CLI on PATH); an
        # existing ~/.claude.json makes Claude Code detected, so the button is
        # enabled and install falls back to a direct atomic merge.
        claude_json = isolated_clients / ".claude.json"
        claude_json.write_text(
            json.dumps({"projects": {"/x": {"trust": True}}}), encoding="utf-8"
        )

        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        cc_group = _group(dialog, "Claude Code")
        add_btn = next(
            b for b in cc_group.findChildren(QPushButton) if b.text() == "Add to Claude Code"
        )
        assert add_btn.isEnabled()
        qtbot.mouseClick(add_btn, Qt.MouseButton.LeftButton)

        data = json.loads(claude_json.read_text(encoding="utf-8"))
        # type:"http" is required (a url-only entry is ignored), and the
        # pre-existing top-level keys must survive the merge.
        assert data["mcpServers"]["open-garden-planner"] == {"type": "http", "url": _URL}
        assert data["projects"] == {"/x": {"trust": True}}
        # The Claude-Code-specific reconnect note is shown (a user-scope server
        # is only read at session start), not the generic "Added to {client}.".
        assert "new claude code session" in dialog._status_label.text().lower()

    def test_add_to_claude_code_embeds_token_in_merged_url(
        self, qtbot, isolated_clients: Path
    ) -> None:
        claude_json = isolated_clients / ".claude.json"
        claude_json.write_text("{}", encoding="utf-8")

        dialog = ConnectAiAssistantDialog(_URL, token=_TOKEN)
        qtbot.addWidget(dialog)

        cc_group = _group(dialog, "Claude Code")
        add_btn = next(
            b for b in cc_group.findChildren(QPushButton) if b.text() == "Add to Claude Code"
        )
        qtbot.mouseClick(add_btn, Qt.MouseButton.LeftButton)

        entry = json.loads(claude_json.read_text(encoding="utf-8"))["mcpServers"][
            "open-garden-planner"
        ]
        assert entry == {"type": "http", "url": f"{_URL}?token={_TOKEN}"}


class TestConnectAiAssistantDialogWithToken:
    """When AI editing is on, a token is passed and must ride the URL (the
    delivery route that works with clients that drop auth headers)."""

    def test_default_copy_is_read_only_and_carries_no_token(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """Issue #366, inverted from the old behaviour.

        The primary copy action used to copy the WRITE url, so the default
        thing a user pasted into an assistant chat was a live credential that
        could edit their plan. The default is now read-only; the write URL is
        behind its own explicitly-worded button.
        """
        dialog = ConnectAiAssistantDialog(_URL, token=_TOKEN)
        qtbot.addWidget(dialog)

        group = _group(dialog, "Connect URL")
        copy_btn = next(
            b for b in group.findChildren(QPushButton) if b.text() == "Copy read-only URL"
        )
        qtbot.mouseClick(copy_btn, Qt.MouseButton.LeftButton)

        clipboard = QApplication.clipboard()
        assert clipboard is not None
        assert clipboard.text() == _URL
        assert "token" not in clipboard.text()

    def test_explicit_write_url_copy_includes_token(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """The write URL is still one click away — it is just no longer the
        default, and the status says the token is in it."""
        dialog = ConnectAiAssistantDialog(_URL, token=_TOKEN)
        qtbot.addWidget(dialog)

        group = _group(dialog, "Connect URL")
        copy_btn = next(
            b for b in group.findChildren(QPushButton)
            if b.text() == "Copy URL with edit token"
        )
        qtbot.mouseClick(copy_btn, Qt.MouseButton.LeftButton)

        clipboard = QApplication.clipboard()
        assert clipboard is not None
        assert clipboard.text() == f"{_URL}?token={_TOKEN}"
        assert "do not share" in dialog._status_label.text().lower()

    def test_write_url_button_absent_when_editing_is_off(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """With no token there is no write URL to hand out, so the button that
        would leak one must not exist at all."""
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        group = _group(dialog, "Connect URL")
        assert not any(
            b.text() == "Copy URL with edit token" for b in group.findChildren(QPushButton)
        )

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


# ---------------------------------------------------------------------------
# Issue #366: the dialog renders from the service's TARGETS registry, so a new
# client needs no change here. These tests prove that by exercising clients
# this file has never heard of.
# ---------------------------------------------------------------------------


def _add_button(group: QGroupBox, client: str) -> QPushButton:
    return next(
        b for b in group.findChildren(QPushButton) if b.text() == f"Add to {client}"
    )


def _row_text(group: QGroupBox) -> str:
    return " ".join(w.text() for w in group.findChildren(QLabel))


class TestRegistryDrivenRows:
    def test_every_registry_client_gets_a_row(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """No UI change adds a client: the dialog builds a row per registry
        record. This is the acceptance criterion in test form."""
        from open_garden_planner.services import ai_client_onboarding as registry

        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        for target in registry.TARGETS:
            _group(dialog, target.display_name)

    def test_every_reachable_client_has_a_manual_note(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """A client in the registry with no note here would render an EMPTY
        string — the failure a `dict.get(id, "")` lookup invites. A note that
        is present but blank is the defect this pins."""
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        for client in onboarding.detect_clients():
            note = dialog._manual_note_for(client.client_id)
            assert note.strip(), f"{client.client_id} has no manual-setup note"

    def test_opencode_without_the_cli_has_no_button_and_keeps_comments(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """With no CLI, OpenCode's row offers NO Add button.

        A button whose only possible outcome is a refusal is a dead end with a
        polite message — the exact shape #366 was opened to close. So
        `detect_clients` reports `manual` when the merge is unsupported and the
        CLI is absent, and the dialog hides the button. The user's config is
        never touched, and the manual snippet below carries the correct NESTED
        container (`mcp.servers`).
        """
        config = isolated_clients / ".config" / "opencode"
        config.mkdir(parents=True)
        original = '{\n  // my own note\n  "theme": "dark"\n}\n'
        (config / "opencode.jsonc").write_text(original, encoding="utf-8")

        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        group = _group(dialog, "OpenCode")
        assert not any(
            b.text() == "Add to OpenCode" for b in group.findChildren(QPushButton)
        )
        # Byte-for-byte untouched: nothing in this flow writes the file.
        assert (config / "opencode.jsonc").read_text(encoding="utf-8") == original

        # The manual snippet is offered, and it uses the OBSERVED container.
        toggle = next(
            b for b in group.findChildren(QPushButton) if b.text() == "Show manual snippet"
        )
        qtbot.mouseClick(toggle, Qt.MouseButton.LeftButton)
        snippet = json.loads(group.findChild(QPlainTextEdit).toPlainText())
        assert snippet["mcp"]["servers"]["open-garden-planner"]["url"] == _URL
        assert "og" not in snippet["mcp"]

    def test_add_to_opencode_with_the_cli_uses_it(
        self, qtbot, isolated_clients: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With `opencode` on PATH the CLI is the route, and `--global` is
        load-bearing: without it the CLI writes the PROJECT config, silently
        dropping an opencode.json into the user's working directory."""
        calls: list[list[str]] = []

        def fake_run(args, **_kwargs):  # noqa: ANN001, ANN003
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout="added", stderr="")

        monkeypatch.setattr(
            "open_garden_planner.services.ai_client_onboarding.shutil.which",
            lambda cmd: "/usr/bin/opencode" if cmd == "opencode" else None,
        )
        monkeypatch.setattr(
            "open_garden_planner.services.ai_client_onboarding.subprocess.run", fake_run
        )

        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        group = _group(dialog, "OpenCode")
        qtbot.mouseClick(_add_button(group, "OpenCode"), Qt.MouseButton.LeftButton)

        assert calls, "the CLI should have been used"
        assert "--global" in calls[0]
        assert _URL in calls[0]

    def test_add_to_codex_writes_toml_and_keeps_user_comments(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """The surgical-append guarantee, end to end: Codex's file is not
        OGP's, so its comments must come through untouched."""
        import tomllib

        codex_dir = isolated_clients / ".codex"
        codex_dir.mkdir()
        (codex_dir / "config.toml").write_text(
            '# my codex settings\nmodel = "gpt-5"\n', encoding="utf-8"
        )

        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        group = _group(dialog, "Codex")
        qtbot.mouseClick(_add_button(group, "Codex"), Qt.MouseButton.LeftButton)

        text = (codex_dir / "config.toml").read_text(encoding="utf-8")
        assert text.startswith('# my codex settings\nmodel = "gpt-5"\n')
        data = tomllib.loads(text)
        assert data["model"] == "gpt-5"
        assert data["mcp_servers"]["open-garden-planner"]["url"] == _URL

    def test_codex_failure_on_corrupt_config_leaves_file_untouched(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """Refusal path, end to end: a corrupt FOREIGN file must be reported,
        not replaced."""
        codex_dir = isolated_clients / ".codex"
        codex_dir.mkdir()
        corrupt = "this is = = not toml"
        (codex_dir / "config.toml").write_text(corrupt, encoding="utf-8")

        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        group = _group(dialog, "Codex")
        qtbot.mouseClick(_add_button(group, "Codex"), Qt.MouseButton.LeftButton)

        assert "Could not add to Codex" in dialog._status_label.text()
        assert (codex_dir / "config.toml").read_text(encoding="utf-8") == corrupt


class TestGenericFallbackAlwaysPresent:
    def test_present_even_when_nothing_is_detected(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """The vendor-agnostic route is what stops 'OGP has never heard of my
        client' from degrading into 'paste your token into a chat'."""
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        group = _group(dialog, "Other AI clients")
        boxes = group.findChildren(QPlainTextEdit)
        assert len(boxes) == 3
        joined = " ".join(b.toPlainText() for b in boxes)
        assert "mcpServers" in joined
        assert _URL in joined

    def test_generic_snippets_never_carry_the_token(
        self, qtbot, isolated_clients: Path
    ) -> None:
        """Even with editing ON, the hand-out-for-pasting text stays
        read-only. This is the leak, closed at the last mile."""
        dialog = ConnectAiAssistantDialog(_URL, token=_TOKEN)
        qtbot.addWidget(dialog)

        group = _group(dialog, "Other AI clients")
        joined = " ".join(b.toPlainText() for b in group.findChildren(QPlainTextEdit))
        assert _TOKEN not in joined


class TestRegistrationStateIsHonest:
    def test_reports_not_registered_yet(self, qtbot, isolated_clients: Path) -> None:
        # `isolated_clients` already seeds ~/.cursor, so Cursor is detected
        # with no config file written yet.
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        assert "not registered yet" in _row_text(_group(dialog, "Cursor")).lower()

    def test_reports_up_to_date_after_add(self, qtbot, isolated_clients: Path) -> None:
        dialog = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(dialog)

        cursor_group = _group(dialog, "Cursor")
        qtbot.mouseClick(_add_button(cursor_group, "Cursor"), Qt.MouseButton.LeftButton)

        # Re-open: detection re-reads the file it just wrote.
        reopened = ConnectAiAssistantDialog(_URL)
        qtbot.addWidget(reopened)
        assert "up to date" in _row_text(_group(reopened, "Cursor")).lower()

    def test_reports_a_stale_registration(self, qtbot, isolated_clients: Path) -> None:
        """The failure that motivated the issue: a rotated token or a changed
        port leaves an entry that looks fine and cannot connect."""
        cursor_dir = isolated_clients / ".cursor"  # already created by the fixture
        (cursor_dir / "mcp.json").write_text(
            json.dumps(
                {"mcpServers": {"open-garden-planner": {"url": "http://127.0.0.1:9999/mcp"}}}
            ),
            encoding="utf-8",
        )

        dialog = ConnectAiAssistantDialog(_URL, token=_TOKEN)
        qtbot.addWidget(dialog)

        assert "different address" in _row_text(_group(dialog, "Cursor")).lower()
