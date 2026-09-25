"""Unit tests for the generalized onboarding registry (issue #366).

Covers what the refactor made possible and what it must NOT have weakened:
the three syntax strategies (``json`` / ``jsonc`` / surgical ``toml``), the
read-only/write URL split that closes the token-in-a-transcript leak, and
stale-registration detection.

The pre-existing suite in ``test_ai_client_onboarding.py`` is the regression
net for the refactor itself — every one of its 49 tests still passes unchanged.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from open_garden_planner.services import ai_client_onboarding as onboarding

_URL = "http://127.0.0.1:8765/mcp"
_TOKEN = "write-token-abc123"


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Every client config path resolves under ``tmp_path``.

    Load-bearing: without this the registry's ``detect_installed`` /
    ``config_path`` callables would read and WRITE the developer's real
    ``~/.claude.json``, ``~/.codex/config.toml`` and
    ``~/.config/opencode/opencode.jsonc``. Also clears both env vars that
    relocate a config, for the same reason.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return tmp_path


# ---------------------------------------------------------------------------
# Registry drift guards
# ---------------------------------------------------------------------------


class TestRegistryDriftGuards:
    """The registry is only worth having if it cannot silently rot. Each guard
    below catches a class of mistake that a per-client branch would have made
    structurally impossible."""

    def test_client_ids_are_unique(self) -> None:
        ids = [t.client_id for t in onboarding.TARGETS]
        assert len(ids) == len(set(ids))

    def test_every_target_has_a_known_syntax(self) -> None:
        known = {"json", "jsonc", "toml"}
        for target in onboarding.TARGETS:
            assert target.syntax in known, target.client_id

    def test_every_target_has_callables(self) -> None:
        """A target missing a detect/entry callable is a crash at click time,
        not at import time — the dialog builds rows for ALL targets eagerly."""
        for target in onboarding.TARGETS:
            assert callable(target.detect_installed), target.client_id
            assert callable(target.config_path), target.client_id
            assert callable(target.entry), target.client_id

    def test_cli_targets_have_add_argv(self) -> None:
        """A ``cli_name`` with no ``cli_argv`` would detect a CLI and then
        silently fall through to a merge, which is a bug, not a fallback."""
        for target in onboarding.TARGETS:
            if target.cli_name is not None:
                assert target.cli_argv is not None, target.client_id

    def test_foreign_targets_are_the_ones_that_fail_closed(self) -> None:
        """``ownership`` is what drives fail-closed, so every target that holds
        state OGP does not own must be marked foreign — and nothing else may
        be, or OGP starts clobbering a file it should leave alone."""
        expected_foreign = {"claude_code", "opencode", "codex"}
        actual_foreign = {t.client_id for t in onboarding.TARGETS if t.ownership == "foreign"}
        assert actual_foreign == expected_foreign

    def test_targets_that_cannot_reach_localhost_are_detection_only(self) -> None:
        """A target that can't reach a loopback server must not offer a write
        path — that was the Claude Desktop bug (#253)."""
        for target in onboarding.TARGETS:
            if not target.supports_local_http:
                assert target.cli_name is None, target.client_id

    def test_unknown_client_id_raises_in_every_entry_point(self) -> None:
        """An unknown id is a programming error, and it must fail the same way
        everywhere rather than being an ``else`` branch somewhere."""
        for call in (
            lambda: onboarding.get_target("nope"),
            lambda: onboarding.install_to_client("nope", url=_URL),
            lambda: onboarding.snippet_for_client("nope", url=_URL),
        ):
            with pytest.raises(ValueError):
                call()


# ---------------------------------------------------------------------------
# JSONC: the superset-of-JSON trap (issue #366)
# ---------------------------------------------------------------------------


class TestStripJsonc:
    def test_removes_line_comments(self) -> None:
        assert json.loads(onboarding._strip_jsonc('{"a": 1} // trailing')) == {"a": 1}

    def test_removes_block_comments(self) -> None:
        text = '{/* header */ "a": 1 /* inline */}'
        assert json.loads(onboarding._strip_jsonc(text)) == {"a": 1}

    def test_removes_trailing_commas(self) -> None:
        text = '{"a": [1, 2, ], "b": 3, }'
        assert json.loads(onboarding._strip_jsonc(text)) == {"a": [1, 2], "b": 3}

    def test_preserves_comment_like_text_inside_strings(self) -> None:
        """A regex-based stripper would corrupt these. This is the reason the
        implementation is a character scan and not a regex."""
        text = '{"url": "http://x/y", "note": "/* not a comment */", "h": "#tag"}'
        assert json.loads(onboarding._strip_jsonc(text)) == {
            "url": "http://x/y",
            "note": "/* not a comment */",
            "h": "#tag",
        }

    def test_preserves_escaped_quote_inside_string(self) -> None:
        text = r'{"a": "say \"hi\" // still string"}'
        assert json.loads(onboarding._strip_jsonc(text)) == {"a": 'say "hi" // still string'}


class TestJsoncReaderTolerance:
    def test_commented_config_is_registerable(self, tmp_path: Path) -> None:
        """The acceptance criterion: a user's commented OpenCode config must be
        registerable, NOT fail closed into a dead end."""
        path = tmp_path / "opencode.jsonc"
        path.write_text(
            '{\n  // my own note\n  "theme": "dark",\n}\n', encoding="utf-8"
        )

        backup = onboarding._merge_into_config(
            path,
            name="og",
            entry={"type": "remote", "url": _URL},
            container_key="mcp",
            syntax="jsonc",
        )

        assert backup is not None
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["theme"] == "dark"
        assert data["mcp"]["og"]["url"] == _URL

    def test_strict_json_reader_still_raises_on_comments(self, tmp_path: Path) -> None:
        """Negative guard. If the lenient reader leaked into the strict path, a
        genuinely corrupt ``mcp.json`` would be silently replaced — losing the
        fail-closed guarantee the foreign-file rule depends on."""
        path = tmp_path / "mcp.json"
        path.write_text('{"a": 1} // not json', encoding="utf-8")

        with pytest.raises(onboarding._ConfigMergeError):
            onboarding._merge_into_config(
                path,
                name="og",
                entry={"url": _URL},
                syntax="json",
                replace_on_parse_error=False,
            )
        assert path.read_text(encoding="utf-8") == '{"a": 1} // not json'


# ---------------------------------------------------------------------------
# Surgical TOML: a foreign file keeps its comments (issue #366)
# ---------------------------------------------------------------------------


class TestSurgicalToml:
    def test_appends_table_and_preserves_user_comments(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        original = (
            "# my codex config\n"
            "model = \"gpt-5\"\n"
            "\n"
            "[mcp_servers.other]\n"
            "url = \"http://elsewhere/mcp\"\n"
        )
        path.write_text(original, encoding="utf-8")

        onboarding._merge_into_config(
            path,
            name=onboarding.SERVER_NAME,
            entry={"url": _URL},
            container_key="mcp_servers",
            syntax="toml",
        )

        text = path.read_text(encoding="utf-8")
        # The user's own content survives verbatim.
        assert text.startswith(original)
        data = tomllib.loads(text)
        assert data["model"] == "gpt-5"
        assert data["mcp_servers"]["other"]["url"] == "http://elsewhere/mcp"
        assert data["mcp_servers"][onboarding.SERVER_NAME]["url"] == _URL

    def test_replaces_only_our_table_span(self, tmp_path: Path) -> None:
        """Re-registering after a token rotation must rewrite OUR table and
        leave the neighbouring one — and the comments around it — alone."""
        path = tmp_path / "config.toml"
        path.write_text(
            f'[mcp_servers.{onboarding.SERVER_NAME}]\n'
            'url = "http://127.0.0.1:9999/mcp?token=stale"\n'
            "\n"
            "[mcp_servers.other]\n"
            'url = "http://elsewhere/mcp"\n',
            encoding="utf-8",
        )

        onboarding._merge_into_config(
            path,
            name=onboarding.SERVER_NAME,
            entry={"url": _URL},
            container_key="mcp_servers",
            syntax="toml",
        )

        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["mcp_servers"][onboarding.SERVER_NAME]["url"] == _URL
        assert data["mcp_servers"]["other"]["url"] == "http://elsewhere/mcp"

    def test_is_idempotent_across_repeat_merges(self, tmp_path: Path) -> None:
        """Re-running must update, not append a second copy of the table —
        TOML forbids redefining a table, so a duplicate would make the file
        unparseable."""
        path = tmp_path / "config.toml"
        for url in (_URL, "http://127.0.0.1:9999/mcp", _URL):
            onboarding._merge_into_config(
                path,
                name=onboarding.SERVER_NAME,
                entry={"url": url},
                container_key="mcp_servers",
                syntax="toml",
            )

        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["mcp_servers"][onboarding.SERVER_NAME]["url"] == _URL

    def test_unparseable_foreign_toml_is_left_untouched(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        corrupt = "this is not = = toml"
        path.write_text(corrupt, encoding="utf-8")

        with pytest.raises(onboarding._ConfigMergeError):
            onboarding._merge_into_config(
                path,
                name=onboarding.SERVER_NAME,
                entry={"url": _URL},
                container_key="mcp_servers",
                syntax="toml",
                replace_on_parse_error=False,
            )

        assert path.read_text(encoding="utf-8") == corrupt
        assert (tmp_path / "config.toml.bak").read_text(encoding="utf-8") == corrupt

    def test_escapes_quotes_and_backslashes(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        entry = {"url": 'http://x/mcp?a="b"\\c'}
        onboarding._merge_into_config(
            path,
            name="og",
            entry=entry,
            container_key="mcp_servers",
            syntax="toml",
        )
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["mcp_servers"]["og"]["url"] == entry["url"]

    def test_booleans_render_as_toml_booleans_not_strings(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        onboarding._merge_into_config(
            path,
            name="og",
            entry={"oauth": False, "enabled": True},
            container_key="mcp_servers",
            syntax="toml",
        )
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["mcp_servers"]["og"] == {"oauth": False, "enabled": True}


# ---------------------------------------------------------------------------
# Read-only / write split — the regression pin for the token leak
# ---------------------------------------------------------------------------


class TestReadOnlySplit:
    def test_read_only_url_has_no_token(self) -> None:
        """THE regression pin. This is what would have prevented the write
        token being pasted into an assistant chat."""
        write_url = onboarding.url_with_token(_URL, _TOKEN)
        assert "token=" in write_url
        assert "token=" not in onboarding.read_only_url(write_url)

    def test_read_only_url_is_stable_when_idempotent(self) -> None:
        once = onboarding.read_only_url(onboarding.url_with_token(_URL, _TOKEN))
        assert onboarding.read_only_url(once) == once

    def test_no_token_yields_a_token_free_url(self) -> None:
        assert onboarding.url_with_token(_URL, None) == _URL
        assert "token" not in onboarding.read_only_url(_URL)

    def test_read_only_install_writes_no_token(self, _isolated_home: Path) -> None:
        cursor = _isolated_home / ".cursor"
        cursor.mkdir()

        result = onboarding.install_to_client("cursor", url=_URL)  # no token

        assert result.success is True
        data = json.loads((cursor / "mcp.json").read_text(encoding="utf-8"))
        assert "token" not in json.dumps(data)

    def test_write_install_carries_the_token(self, _isolated_home: Path) -> None:
        cursor = _isolated_home / ".cursor"
        cursor.mkdir()

        result = onboarding.install_to_client("cursor", url=_URL, token=_TOKEN)

        assert result.success is True
        entry = json.loads((cursor / "mcp.json").read_text(encoding="utf-8"))[
            "mcpServers"
        ][onboarding.SERVER_NAME]
        assert entry["url"] == onboarding.url_with_token(_URL, _TOKEN)

    def test_generic_snippets_default_to_read_only(self, _isolated_home: Path) -> None:
        """The vendor-agnostic path is the one a user is most likely to paste
        somewhere public, so it must be the safe one by default."""
        snippets = onboarding.generic_snippets(url=_URL, token=_TOKEN)

        assert "token=" not in snippets["json"]
        assert "token=" not in snippets["cli"]
        assert snippets["url"] == _URL
        # The write URL is still reachable, but only on an explicit key.
        assert _TOKEN in snippets["write_url"]

    def test_generic_snippets_tolerate_a_query_string(self) -> None:
        snippets = onboarding.generic_snippets(url=f"{_URL}?foo=bar")
        assert snippets["url"] == f"{_URL}?foo=bar"


# ---------------------------------------------------------------------------
# Per-client entry shapes and CLI argv
# ---------------------------------------------------------------------------


class TestOpenCodeTarget:
    def test_entry_shape(self) -> None:
        entry = onboarding._opencode_entry(_URL, _TOKEN)
        # Both `type` and `url` are REQUIRED by OpenCode's schema; without
        # `type` the entry is not recognised as a remote server.
        assert entry["type"] == "remote"
        assert entry["url"] == onboarding.url_with_token(_URL, _TOKEN)
        # OAuth auto-detection against a ?token= local server is at best
        # pointless and at worst an error the user must diagnose.
        assert entry["oauth"] is False
        assert entry["enabled"] is True

    def test_add_args_include_global(self) -> None:
        """Without --global the CLI writes the PROJECT config, silently
        dropping an opencode.json into the user's working directory."""
        args = onboarding._opencode_add_args(onboarding.SERVER_NAME, _URL, None)
        assert "--global" in args
        assert args[:2] == ("mcp", "add")

    def test_no_timeout_is_hard_coded(self) -> None:
        """OpenCode's default is 5000 ms. Setting a value before measuring
        render_canvas_image would be a guess dressed as a fix."""
        assert "timeout" not in onboarding._opencode_entry(_URL, None)


class TestCodexTarget:
    def test_add_args_shape(self) -> None:
        args = onboarding._codex_add_args(onboarding.SERVER_NAME, _URL, None)
        assert args == ("mcp", "add", onboarding.SERVER_NAME, "--url", _URL)

    def test_install_writes_a_real_toml_table(self, _isolated_home: Path) -> None:
        codex_dir = _isolated_home / ".codex"
        codex_dir.mkdir()
        (codex_dir / "config.toml").write_text('model = "gpt-5"\n', encoding="utf-8")
        # No `codex` CLI on PATH in the test env, so this exercises the
        # surgical-append fallback — the route a CLI-less machine takes.
        import shutil as _shutil

        original_which = _shutil.which
        try:
            _shutil.which = lambda _cmd: None  # type: ignore[assignment]
            result = onboarding.install_to_client("codex", url=_URL)
        finally:
            _shutil.which = original_which  # type: ignore[assignment]

        assert result.success is True, result.detail
        data = tomllib.loads((codex_dir / "config.toml").read_text(encoding="utf-8"))
        assert data["model"] == "gpt-5"
        assert data["mcp_servers"][onboarding.SERVER_NAME]["url"] == _URL

    def test_snippet_is_toml_not_json(self) -> None:
        snippet = onboarding.snippet_for_client("codex", url=_URL)
        assert snippet.startswith(f"[mcp_servers.{onboarding.SERVER_NAME}]")


# ---------------------------------------------------------------------------
# Stale-registration detection
# ---------------------------------------------------------------------------


class TestStaleRegistration:
    def test_unregistered_reads_as_none(self, _isolated_home: Path) -> None:
        assert onboarding.registered_url("cursor") is None

    def test_registered_url_is_read_back(self, _isolated_home: Path) -> None:
        cursor = _isolated_home / ".cursor"
        cursor.mkdir()
        onboarding.install_to_client("cursor", url=_URL)

        assert onboarding.registered_url("cursor") == _URL
        assert onboarding.is_stale("cursor", _URL) is False

    def test_rotated_token_is_detected_as_stale(self, _isolated_home: Path) -> None:
        """The failure in the issue that motivated this work: a hand-pasted
        entry keeps looking fine while being unable to connect."""
        cursor = _isolated_home / ".cursor"
        cursor.mkdir()
        onboarding.install_to_client("cursor", url=_URL, token="old-token")

        assert onboarding.is_stale("cursor", onboarding.url_with_token(_URL, _TOKEN)) is True

    def test_changed_port_is_detected_as_stale(self, _isolated_home: Path) -> None:
        cursor = _isolated_home / ".cursor"
        cursor.mkdir()
        onboarding.install_to_client("cursor", url=_URL)

        assert onboarding.is_stale("cursor", "http://127.0.0.1:9999/mcp") is True

    def test_unparseable_file_reads_as_unregistered_not_an_error(
        self, _isolated_home: Path
    ) -> None:
        """Detection is advisory: it must never raise into the dialog."""
        cursor = _isolated_home / ".cursor"
        cursor.mkdir()
        (cursor / "mcp.json").write_text("{{{ not json", encoding="utf-8")

        assert onboarding.registered_url("cursor") is None
        assert onboarding.is_stale("cursor", _URL) is False

    def test_toml_registration_is_detected(self, _isolated_home: Path) -> None:
        codex_dir = _isolated_home / ".codex"
        codex_dir.mkdir()
        onboarding._merge_into_config(
            codex_dir / "config.toml",
            name=onboarding.SERVER_NAME,
            entry={"url": _URL},
            container_key="mcp_servers",
            syntax="toml",
        )

        assert onboarding.registered_url("codex") == _URL

    def test_jsonc_registration_is_detected(self, _isolated_home: Path) -> None:
        """The commented-config case again, on the READ path: if the tolerant
        reader were missing here, every OpenCode user would see their own
        working registration reported as absent."""
        config = _isolated_home / ".config" / "opencode"
        config.mkdir(parents=True)
        (config / "opencode.jsonc").write_text(
            "{\n  // keep me\n  \"mcp\": {}\n}\n", encoding="utf-8"
        )

        assert onboarding.registered_url("opencode") is None  # empty container
        onboarding._merge_into_config(
            config / "opencode.jsonc",
            name=onboarding.SERVER_NAME,
            entry=onboarding._opencode_entry(_URL, None),
            container_key="mcp",
            syntax="jsonc",
        )
        assert onboarding.registered_url("opencode") == _URL


# ---------------------------------------------------------------------------
# detect_clients is derived from the registry
# ---------------------------------------------------------------------------


class TestDetectClientsDerived:
    def test_every_target_appears(self, _isolated_home: Path) -> None:
        found = {c.client_id for c in onboarding.detect_clients()}
        assert found == {t.client_id for t in onboarding.TARGETS}

    def test_no_target_is_detected_in_an_empty_home(
        self, monkeypatch: pytest.MonkeyPatch, _isolated_home: Path
    ) -> None:
        # PATH must be neutralised too: a client whose CLI is genuinely
        # installed (this dev machine has `opencode`) is correctly detected
        # even with an empty home, because the CLI is a real install signal.
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: None)
        assert all(c.detected is False for c in onboarding.detect_clients())

    def test_cli_on_path_alone_is_enough_to_detect(
        self, monkeypatch: pytest.MonkeyPatch, _isolated_home: Path
    ) -> None:
        """The converse: a CLI with no config file yet is still a real install
        (and the CLI is what the one-click path will use)."""
        monkeypatch.setattr(
            onboarding.shutil, "which", lambda cmd: "/usr/bin/opencode" if cmd == "opencode" else None
        )
        info = {c.client_id: c for c in onboarding.detect_clients()}["opencode"]
        assert info.detected is True
        assert info.install_method == "cli"

    def test_claude_desktop_is_manual_and_unreachable(self, _isolated_home: Path) -> None:
        info = {c.client_id: c for c in onboarding.detect_clients()}["claude_desktop"]
        assert info.install_method == "manual"
        assert info.supports_local_http is False

    def test_xdg_config_home_is_honoured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """OpenCode lives under XDG on Linux; hardcoding ~/.config would miss
        every user who relocates it."""
        custom = tmp_path / "xdg"
        custom.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(custom))
        (custom / "opencode").mkdir()
        (custom / "opencode" / "opencode.jsonc").write_text("{}", encoding="utf-8")

        info = {c.client_id: c for c in onboarding.detect_clients()}["opencode"]
        assert info.detected is True
        assert info.config_path == custom / "opencode" / "opencode.jsonc"
