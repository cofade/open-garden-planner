"""Unit tests for AI client onboarding (US-D1.6).

Pure/Qt-free: path resolution is tested via ``monkeypatch`` on ``Path.home``/
``sys.platform``/``os.environ`` (mirrors ``tests/unit/test_paths.py``); the
atomic JSON merge is tested directly against ``tmp_path`` files; the Claude
Code CLI path is tested by monkeypatching ``subprocess.run``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from open_garden_planner.services import ai_client_onboarding as onboarding

_URL = "http://127.0.0.1:8765/mcp"


# ---------------------------------------------------------------------------
# _atomic_merge_mcp_server
# ---------------------------------------------------------------------------


class TestAtomicMergeMcpServer:
    def test_creates_file_and_parent_dir(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "mcp.json"

        backup = onboarding._atomic_merge_mcp_server(path, name="og", entry={"url": _URL})

        assert backup is None
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"mcpServers": {"og": {"url": _URL}}}

    def test_preserves_other_servers_and_keys(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        path.write_text(
            json.dumps({"mcpServers": {"other": {"url": "http://elsewhere"}}, "extra": 1}),
            encoding="utf-8",
        )

        onboarding._atomic_merge_mcp_server(path, name="og", entry={"url": _URL})

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["extra"] == 1
        assert data["mcpServers"]["other"] == {"url": "http://elsewhere"}
        assert data["mcpServers"]["og"] == {"url": _URL}

    def test_backs_up_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        original = json.dumps({"mcpServers": {}})
        path.write_text(original, encoding="utf-8")

        backup = onboarding._atomic_merge_mcp_server(path, name="og", entry={"url": _URL})

        assert backup == path.with_name("mcp.json.bak")
        assert backup.read_text(encoding="utf-8") == original

    def test_reinstall_updates_own_entry_not_duplicated(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"

        onboarding._atomic_merge_mcp_server(path, name="og", entry={"url": _URL})
        onboarding._atomic_merge_mcp_server(path, name="og", entry={"url": "http://127.0.0.1:9999/mcp"})

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["mcpServers"] == {"og": {"url": "http://127.0.0.1:9999/mcp"}}

    def test_corrupted_existing_file_is_replaced_not_fatal(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        path.write_text("not valid json {{{", encoding="utf-8")

        backup = onboarding._atomic_merge_mcp_server(path, name="og", entry={"url": _URL})

        assert backup is not None
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["mcpServers"]["og"] == {"url": _URL}

    def test_non_object_existing_file_is_replaced_not_fatal(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")

        onboarding._atomic_merge_mcp_server(path, name="og", entry={"url": _URL})

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["mcpServers"]["og"] == {"url": _URL}

    def test_no_leftover_temp_file(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        onboarding._atomic_merge_mcp_server(path, name="og", entry={"url": _URL})

        assert list(tmp_path.iterdir()) == [path]


# ---------------------------------------------------------------------------
# detect_clients
# ---------------------------------------------------------------------------


class TestDetectClients:
    def test_cursor_detected_when_dir_exists(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        (tmp_path / ".cursor").mkdir()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        clients = {c.client_id: c for c in onboarding.detect_clients()}

        assert clients["cursor"].detected is True
        assert clients["cursor"].install_method == "json_merge"
        assert clients["cursor"].config_path == tmp_path / ".cursor" / "mcp.json"

    def test_cursor_not_detected_without_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        clients = {c.client_id: c for c in onboarding.detect_clients()}

        assert clients["cursor"].detected is False

    def test_claude_code_detected_via_cli(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: "/usr/local/bin/claude")

        clients = {c.client_id: c for c in onboarding.detect_clients()}

        assert clients["claude_code"].detected is True
        assert clients["claude_code"].install_method == "cli"

    def test_claude_code_detected_via_config_without_cli(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: None)
        (tmp_path / ".claude.json").write_text("{}", encoding="utf-8")

        clients = {c.client_id: c for c in onboarding.detect_clients()}

        assert clients["claude_code"].detected is True
        assert clients["claude_code"].install_method == "manual"

    def test_claude_code_not_detected_without_cli_or_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: None)

        clients = {c.client_id: c for c in onboarding.detect_clients()}

        assert clients["claude_code"].detected is False

    def test_claude_desktop_detected_on_windows(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        appdata = tmp_path / "AppData" / "Roaming"
        (appdata / "Claude").mkdir(parents=True)
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", str(appdata))

        clients = {c.client_id: c for c in onboarding.detect_clients()}

        assert clients["claude_desktop"].detected is True
        assert clients["claude_desktop"].install_method == "manual"
        assert clients["claude_desktop"].config_path == appdata / "Claude" / "claude_desktop_config.json"

    def test_claude_desktop_not_available_on_linux(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        clients = {c.client_id: c for c in onboarding.detect_clients()}

        assert clients["claude_desktop"].detected is False
        assert clients["claude_desktop"].config_path is None


# ---------------------------------------------------------------------------
# install_to_client
# ---------------------------------------------------------------------------


class TestInstallToClient:
    def test_cursor_writes_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = onboarding.install_to_client("cursor", url=_URL)

        assert result.success is True
        path = tmp_path / ".cursor" / "mcp.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["mcpServers"][onboarding.SERVER_NAME] == {"url": _URL}

    def test_claude_desktop_is_always_manual(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = onboarding.install_to_client("claude_desktop", url=_URL)

        assert result.success is False
        assert "custom connector" in result.detail.lower()

    def test_claude_code_cli_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: None)

        result = onboarding.install_to_client("claude_code", url=_URL)

        assert result.success is False
        assert "not found" in result.detail.lower()

    def test_claude_code_cli_timeout_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression: a hung `claude` CLI must surface as a failed InstallResult,
        not crash the caller — the module's whole contract is 'never raises into
        the UI', but subprocess.TimeoutExpired isn't an OSError subclass."""
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: "/usr/local/bin/claude")

        def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout", 15))

        monkeypatch.setattr(onboarding.subprocess, "run", fake_run)

        result = onboarding.install_to_client("claude_code", url=_URL)

        assert result.success is False
        assert result.detail

    def test_claude_code_cli_missing_at_runtime_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: shutil.which found it, but a TOCTOU removal before the
        actual subprocess.run call raises FileNotFoundError (an OSError)."""
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: "/usr/local/bin/claude")

        def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("claude")

        monkeypatch.setattr(onboarding.subprocess, "run", fake_run)

        result = onboarding.install_to_client("claude_code", url=_URL)

        assert result.success is False
        assert result.detail

    def test_claude_code_already_exists_but_readd_fails_reports_removal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: if remove succeeds but the retry add fails, the user
        must be told the old entry is gone, not just given the raw add error."""
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: "/usr/local/bin/claude")
        responses = iter(
            [
                subprocess.CompletedProcess([], 1, stdout="", stderr="Error: server already exists"),
                subprocess.CompletedProcess([], 0, stdout="removed", stderr=""),
                subprocess.CompletedProcess([], 1, stdout="", stderr="network unreachable"),
            ]
        )

        def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return next(responses)

        monkeypatch.setattr(onboarding.subprocess, "run", fake_run)

        result = onboarding.install_to_client("claude_code", url=_URL)

        assert result.success is False
        assert "removed" in result.detail.lower()
        assert "network unreachable" in result.detail

    def test_claude_code_already_exists_but_remove_itself_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: if `claude mcp remove` itself fails, the detail must
        say so — not silently repeat the original 'already exists' message,
        which would misleadingly suggest nothing was attempted."""
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: "/usr/local/bin/claude")
        responses = iter(
            [
                subprocess.CompletedProcess([], 1, stdout="", stderr="Error: server already exists"),
                subprocess.CompletedProcess([], 1, stdout="", stderr="permission denied"),
            ]
        )

        def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return next(responses)

        monkeypatch.setattr(onboarding.subprocess, "run", fake_run)

        result = onboarding.install_to_client("claude_code", url=_URL)

        assert result.success is False
        assert "remove" in result.detail.lower()
        assert "permission denied" in result.detail
        assert "already exists" not in result.detail.lower()

    def test_claude_code_cli_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: "/usr/local/bin/claude")
        calls: list[list[str]] = []

        def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout="Added.", stderr="")

        monkeypatch.setattr(onboarding.subprocess, "run", fake_run)

        result = onboarding.install_to_client("claude_code", url=_URL)

        assert result.success is True
        assert calls[0] == [
            "/usr/local/bin/claude",
            "mcp",
            "add",
            "--transport",
            "http",
            "--scope",
            "user",
            onboarding.SERVER_NAME,
            _URL,
        ]

    def test_claude_code_already_exists_self_heals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: "/usr/local/bin/claude")
        responses = iter(
            [
                subprocess.CompletedProcess([], 1, stdout="", stderr="Error: server already exists"),
                subprocess.CompletedProcess([], 0, stdout="removed", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="added", stderr=""),
            ]
        )

        def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return next(responses)

        monkeypatch.setattr(onboarding.subprocess, "run", fake_run)

        result = onboarding.install_to_client("claude_code", url=_URL)

        assert result.success is True

    def test_claude_code_failure_surfaces_stderr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: "/usr/local/bin/claude")

        def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="boom")

        monkeypatch.setattr(onboarding.subprocess, "run", fake_run)

        result = onboarding.install_to_client("claude_code", url=_URL)

        assert result.success is False
        assert result.detail == "boom"

    def test_unknown_client_raises(self) -> None:
        with pytest.raises(ValueError):
            onboarding.install_to_client("bogus", url=_URL)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# snippet_for_client
# ---------------------------------------------------------------------------


class TestSnippetForClient:
    def test_cursor_snippet_is_valid_json_with_url(self) -> None:
        snippet = onboarding.snippet_for_client("cursor", url=_URL)
        data = json.loads(snippet)
        assert data["mcpServers"][onboarding.SERVER_NAME]["url"] == _URL

    def test_claude_code_snippet_is_cli_command(self) -> None:
        snippet = onboarding.snippet_for_client("claude_code", url=_URL)
        assert snippet == f"claude mcp add --transport http --scope user {onboarding.SERVER_NAME} {_URL}"

    def test_claude_desktop_snippet_is_bare_url(self) -> None:
        assert onboarding.snippet_for_client("claude_desktop", url=_URL) == _URL

    def test_unknown_client_raises(self) -> None:
        with pytest.raises(ValueError):
            onboarding.snippet_for_client("bogus", url=_URL)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# url_with_token (US-D2.0): the write-access token rides the server URL as a
# ``?token=`` query param — the delivery route that reaches clients (notably
# Claude Code) which don't transmit auth headers on tool-call requests.
# ---------------------------------------------------------------------------

_TOKEN = "write-token-abc123"


class TestUrlWithToken:
    def test_appends_token(self) -> None:
        assert onboarding.url_with_token(_URL, _TOKEN) == f"{_URL}?token={_TOKEN}"

    def test_no_token_returns_url_unchanged(self) -> None:
        assert onboarding.url_with_token(_URL, None) == _URL
        assert onboarding.url_with_token(_URL, "") == _URL

    def test_merges_with_existing_query(self) -> None:
        got = onboarding.url_with_token(f"{_URL}?foo=bar", _TOKEN)
        assert got == f"{_URL}?foo=bar&token={_TOKEN}"

    def test_replaces_stale_token_and_is_idempotent(self) -> None:
        once = onboarding.url_with_token(_URL, _TOKEN)
        twice = onboarding.url_with_token(once, _TOKEN)
        # Re-applying the same token doesn't accumulate duplicate params.
        assert twice == once
        assert twice.count("token=") == 1


class TestWriteTokenThreading:
    """The write token must be threaded into each client's config (in the URL)
    so a one-click install can actually reach the D2 write tools."""

    def test_cursor_install_embeds_token_in_url(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = onboarding.install_to_client("cursor", url=_URL, token=_TOKEN)

        assert result.success is True
        data = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"][onboarding.SERVER_NAME]
        assert entry["url"] == onboarding.url_with_token(_URL, _TOKEN)
        # Token rides the URL now, not a header.
        assert "headers" not in entry

    def test_cursor_install_without_token_uses_bare_url(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        onboarding.install_to_client("cursor", url=_URL)

        data = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"][onboarding.SERVER_NAME] == {"url": _URL}

    def test_cursor_snippet_embeds_token_in_url(self) -> None:
        data = json.loads(
            onboarding.snippet_for_client("cursor", url=_URL, token=_TOKEN)
        )
        entry = data["mcpServers"][onboarding.SERVER_NAME]
        assert entry["url"] == onboarding.url_with_token(_URL, _TOKEN)
        assert "headers" not in entry

    def test_claude_code_add_args_embed_token_in_url(self) -> None:
        args = onboarding._claude_code_add_args(onboarding.SERVER_NAME, _URL, _TOKEN)
        assert args == (
            "add", "--transport", "http", "--scope", "user",
            onboarding.SERVER_NAME, onboarding.url_with_token(_URL, _TOKEN),
        )
        # No --header at all: dropping it removes the variadic-ordering footgun.
        assert "--header" not in args

    def test_claude_code_add_args_bare_url_without_token(self) -> None:
        args = onboarding._claude_code_add_args(onboarding.SERVER_NAME, _URL, None)
        assert "--header" not in args
        assert args == (
            "add", "--transport", "http", "--scope", "user", onboarding.SERVER_NAME, _URL
        )

    def test_claude_code_snippet_embeds_token_in_url(self) -> None:
        snippet = onboarding.snippet_for_client("claude_code", url=_URL, token=_TOKEN)
        assert onboarding.url_with_token(_URL, _TOKEN) in snippet
        assert "--header" not in snippet

    def test_claude_desktop_snippet_embeds_token_in_url(self) -> None:
        snippet = onboarding.snippet_for_client("claude_desktop", url=_URL, token=_TOKEN)
        assert snippet == onboarding.url_with_token(_URL, _TOKEN)

    def test_claude_code_install_passes_token_url_to_cli(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: "/usr/local/bin/claude")
        seen: dict[str, list[str]] = {}

        def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            seen["args"] = args
            return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

        monkeypatch.setattr(onboarding.subprocess, "run", fake_run)

        result = onboarding.install_to_client("claude_code", url=_URL, token=_TOKEN)

        assert result.success is True
        assert "--header" not in seen["args"]
        assert onboarding.url_with_token(_URL, _TOKEN) in seen["args"]
