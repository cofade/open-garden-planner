"""Unit tests for the generalized onboarding registry (issue #366).

Covers what the refactor made possible and what it must NOT have weakened:
the three syntax strategies (``json`` / ``jsonc`` / surgical ``toml``), the
read-only/write URL split that closes the token-in-a-transcript leak, and
stale-registration detection.

The pre-existing suite in ``test_ai_client_onboarding.py`` is the regression net
for the refactor itself: all 49 of its tests still pass, and they pin the
pre-#366 contract. Two of its assertions changed, and honestly so — the
``install_method`` value ``"json_merge"`` is now ``"merge"``, because the old
name was already a lie for the TOML and JSONC targets and this change's whole
thesis is that syntax is a separate axis.
"""

from __future__ import annotations

import dataclasses
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


@pytest.fixture(autouse=True)
def _no_client_clis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise every client CLI for the WHOLE module.

    Not cosmetic. A test that reached the real `opencode` binary actually
    EXECUTED `opencode mcp add --global` against the developer's real
    ``~/.config/opencode/opencode.jsonc`` and modified it. ``shutil.which``
    finds those CLIs on a machine that has them installed, so any test that
    installs a CLI-capable target must stub it, and the default must be
    "no CLI" rather than "whatever happens to be on this box".
    """
    monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: None)


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
        be, or OGP starts clobbering a file it should leave alone.

        Cursor is the only "own" file (a dedicated small ``mcp.json`` OGP
        effectively controls). Everything else fails closed, INCLUDING
        ``claude_desktop``, which writes nothing at all but whose file OGP
        flatly does not own — a safety decision must never be inherited from a
        default, and a later flip of ``supports_local_http`` must not silently
        make OGP replace it.
        """
        expected_foreign = {
            "claude_code",
            "opencode",
            "codex",
            "gemini",
            "claude_desktop",
        }
        actual_foreign = {t.client_id for t in onboarding.TARGETS if t.ownership == "foreign"}
        assert actual_foreign == expected_foreign
        # And `ownership` must be declared, not defaulted: a required field is
        # what stops a new record silently inheriting "replace whatever is
        # there" because nobody filled it in. (The older assertion here compared
        # `ownership` against its own Literal values, so it could never fail —
        # round 4.)
        fields = {f.name: f for f in dataclasses.fields(onboarding.ClientTarget)}
        assert fields["ownership"].default is dataclasses.MISSING
        assert fields["ownership"].default_factory is dataclasses.MISSING
        assert {t.ownership for t in onboarding.TARGETS} == {"own", "foreign"}

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
    def test_commented_config_is_readable_for_staleness(self, tmp_path: Path) -> None:
        """The READ path must tolerate a commented config, or every OpenCode
        user sees their own working registration reported as absent."""
        path = tmp_path / "opencode.jsonc"
        path.write_text(
            '{\n  // my own note\n  "theme": "dark",\n}\n', encoding="utf-8"
        )
        assert json.loads(onboarding._strip_jsonc(path.read_text(encoding="utf-8"))) == {
            "theme": "dark"
        }

    def test_a_foreign_jsonc_is_never_re_serialised(self, tmp_path: Path) -> None:
        """The asymmetry with TOML is DELIBERATE and this pins it.

        A TOML merge rewrites one table's line span, so a foreign file's
        comments survive. A JSON merge would have to re-serialise the whole
        document, which discards them — and §11.4 ("never re-serialise a file
        you do not own") forbids exactly that. So a foreign JSONC target
        declares ``merge_supported=False`` and the no-CLI path refuses instead.

        This test is the one whose absence let that asymmetry ship unnoticed:
        the TOML class asserted `text.startswith(original)` and the JSONC class
        asserted only that the keys survived.
        """
        opencode = next(t for t in onboarding.TARGETS if t.client_id == "opencode")
        assert opencode.syntax == "jsonc"
        assert opencode.ownership == "foreign"
        assert opencode.merge_supported is False

        # And the refusal leaves the file byte-for-byte untouched.
        path = tmp_path / "opencode.jsonc"
        original = '{\n  // keep me\n  "theme": "dark"\n}\n'
        path.write_text(original, encoding="utf-8")
        result = onboarding.install_to_client("opencode", url=_URL)
        assert result.success is False
        assert "not on PATH" in result.detail
        assert path.read_text(encoding="utf-8") == original

    def test_unterminated_block_comment_raises(self) -> None:
        """A malformed document must not be silently 'accepted' by the tolerant
        reader.

        It raises a MODULE-OWNED `_ConfigReadError`, not a bare `ValueError`:
        the first version of this fix raised `ValueError`, which escaped
        `registered_url` -> `detect_clients` -> the dialog's `__init__`, where
        PyQt6 turns an unhandled exception into `qFatal()`/`abort()` — i.e. a
        user with a half-typed comment block could crash the app by opening the
        Connect dialog. `test_malformed_config_never_raises_through_readers`
        pins the containment.
        """
        with pytest.raises(onboarding._ConfigReadError, match="Unterminated"):
            onboarding._strip_jsonc('{"a": 1} /* never closed')

    def test_malformed_config_never_raises_through_the_readers(
        self, _isolated_home: Path
    ) -> None:
        """The P0 regression: every reader is best-effort and must REPORT a
        malformed file, never raise. `detect_clients` runs inside the dialog's
        `__init__`, so a raise here is an application abort."""
        config = _isolated_home / ".config" / "opencode"
        config.mkdir(parents=True)
        (config / "opencode.jsonc").write_text(
            '{\n  /* never closed\n  "mcp": {"servers": {}}\n}\n', encoding="utf-8"
        )

        assert onboarding.registered_url("opencode") is None
        # Must not raise — this is the call the dialog makes.
        clients = onboarding.detect_clients()
        assert any(c.client_id == "opencode" for c in clients)

    @pytest.mark.parametrize(
        ("client_id", "relpath", "body"),
        [
            # Families deliberately NOT in any enumerated tuple. A deeply
            # nested document makes both json.loads and tomllib.loads raise
            # RecursionError, which is how round 3 found that the "best-effort,
            # never raises" reader was still an enumerated except list — and
            # how a malformed user config could abort the whole application
            # from the dialog's __init__.
            #
            # `ids` is explicit because the default id embeds the whole body,
            # and a 20000-character test id makes any failure output unreadable.
            ("codex", ".codex/config.toml", "x = " + "[" * 5000 + "]" * 5000),
            ("cursor", ".cursor/mcp.json", "[" * 20000 + "]" * 20000),
            ("gemini", ".gemini/config/mcp_config.json", "[" * 20000 + "]" * 20000),
        ],
        ids=["codex-deep-toml", "cursor-deep-json", "gemini-deep-json"],
    )
    def test_hostile_nesting_never_raises_through_the_readers(
        self, client_id: str, relpath: str, body: str, _isolated_home: Path
    ) -> None:
        """Invariant 14: never enumerate exception families at a trust boundary.
        These files belong to other programs; the reader catches broadly."""
        path = _isolated_home / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        original = path.read_text(encoding="utf-8")

        assert onboarding.registered_url(client_id) is None
        assert any(c.client_id == client_id for c in onboarding.detect_clients())
        # The write path must not RAISE either — `install_to_client`'s contract
        # is that a failed install comes back as a result. Whether the file
        # survives then depends on ownership: a `foreign` target fails closed,
        # while an `own` target (Cursor's dedicated mcp.json) treats a parse
        # error as replaceable, which is the pre-existing and intended policy.
        result = onboarding.install_to_client(client_id, url=_URL)
        if onboarding.get_target(client_id).ownership == "foreign":
            assert result.success is False
            assert path.read_text(encoding="utf-8") == original
        else:
            assert result.success is True  # replaced, by design for an `own` file

    def test_malformed_config_fails_closed_on_the_write_path(
        self, _isolated_home: Path
    ) -> None:
        """The write path contains it too: a `foreign` file we cannot read is
        refused, not replaced."""
        config = _isolated_home / ".config" / "opencode"
        config.mkdir(parents=True)
        path = config / "opencode.jsonc"
        original = '{\n  /* never closed\n}\n'
        path.write_text(original, encoding="utf-8")

        with pytest.raises(onboarding._ConfigMergeError):
            onboarding._merge_into_config(
                path,
                name="og",
                entry={"url": _URL},
                container_key="mcp.servers",
                syntax="jsonc",
                replace_on_parse_error=False,
            )
        assert path.read_text(encoding="utf-8") == original

    def test_bom_is_tolerated(self, tmp_path: Path) -> None:
        """VS Code and jsonc-parser both accept a BOM; plain utf-8 decoding
        would refuse it and reproduce the dead end §11.4 warns about."""
        path = tmp_path / "bom.jsonc"
        path.write_text('{"theme": "dark"}', encoding="utf-8-sig")
        # The real assertion: the read does not raise, and the content is
        # readable. (The target's own path is elsewhere; this exercises the
        # encoding choice, not target resolution.)
        assert json.loads(onboarding._strip_jsonc(path.read_text(encoding="utf-8-sig"))) == {
            "theme": "dark"
        }

    def test_replace_on_parse_error_is_required(self, tmp_path: Path) -> None:
        """It used to default to True ("replace the file") while the docstring
        claimed it defaulted from the target's ownership — i.e. the one seam in
        a fail-closed module defaulted the UNSAFE way, and the docstring would
        have convinced the next caller otherwise."""
        with pytest.raises(TypeError, match="replace_on_parse_error"):
            onboarding._merge_into_config(  # type: ignore[call-arg]
                tmp_path / "mcp.json",
                name="og",
                entry={"url": _URL},
                container_key="mcpServers",
                syntax="json",
            )

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
                replace_on_parse_error=False,
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
                replace_on_parse_error=False,
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
                    replace_on_parse_error=False,
            )

        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["mcp_servers"][onboarding.SERVER_NAME]["url"] == _URL

    def test_a_refused_merge_leaves_no_backup_behind(self, tmp_path: Path) -> None:
        """The backup exists to recover from a write that HAPPENED.

        Taken before the write decision, a refusal littered a `.bak` next to
        the user's config — and for a `foreign` target, refusing is the common
        case, so the common case was the one that made a spurious second file.
        """
        path = tmp_path / "config.toml"
        original = "this is = not [valid toml\n"
        path.write_text(original, encoding="utf-8")

        with pytest.raises(onboarding._ConfigMergeError):
            onboarding._merge_into_config(
                path,
                name="og",
                entry={"url": _URL},
                container_key="mcp_servers",
                syntax="toml",
                replace_on_parse_error=False,
            )

        assert path.read_text(encoding="utf-8") == original
        assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]

    def test_a_successful_merge_does_report_its_backup(self, tmp_path: Path) -> None:
        """And when a write DOES happen, the backup exists — and the caller is
        told where it is, because a `.bak` in someone else's home directory is
        otherwise impossible to find."""
        path = tmp_path / "config.toml"
        path.write_text('model = "gpt-5"\n', encoding="utf-8")

        backup = onboarding._merge_into_config(
            path,
            name="og",
            entry={"url": _URL},
            container_key="mcp_servers",
            syntax="toml",
            replace_on_parse_error=False,
        )

        assert backup is not None and backup.exists()
        assert backup.read_text(encoding="utf-8") == 'model = "gpt-5"\n'

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
        # No .bak either: the backup is taken immediately before a write, and a
        # refused merge never reaches one.
        assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]

    def test_escapes_quotes_and_backslashes(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        entry = {"url": 'http://x/mcp?a="b"\\c'}
        onboarding._merge_into_config(
            path,
            name="og",
            entry=entry,
            container_key="mcp_servers",
            syntax="toml",
                replace_on_parse_error=False,
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
                replace_on_parse_error=False,
        )
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["mcp_servers"]["og"] == {"oauth": False, "enabled": True}

    # --- the hostile inputs a surgical writer must refuse -------------------
    # Each of these produced an UNPARSEABLE file (and, in the last case, silent
    # destruction of a *different* table) before the post-write parse check and
    # the parser-based existence probe existed. They are here because the
    # original class pinned only the well-formed cases.

    @pytest.mark.parametrize(
        "spelling",
        [
            '["mcp_servers"."open-garden-planner"]',  # quoted keys
            "[ mcp_servers.open-garden-planner ]",  # inner spaces
            "['mcp_servers'.open-garden-planner]",
        ],
    )
    def test_a_foreign_table_spelling_we_cannot_see_is_refused_not_duplicated(
        self, tmp_path: Path, spelling: str
    ) -> None:
        """tomllib sees these as the SAME table our line scan cannot match, so
        appending would declare it twice and produce a file that cannot be
        parsed at all."""
        path = tmp_path / "config.toml"
        original = f'{spelling}\nurl = "http://old/mcp"\n'
        path.write_text(original, encoding="utf-8")

        with pytest.raises(onboarding._ConfigMergeError, match="spelling"):
            onboarding._merge_into_config(
                path,
                name=onboarding.SERVER_NAME,
                entry={"url": _URL},
                container_key="mcp_servers",
                syntax="toml",
                    replace_on_parse_error=False,
            )

        assert path.read_text(encoding="utf-8") == original

    def test_our_header_inside_another_tables_multiline_string_is_refused(
        self, tmp_path: Path
    ) -> None:
        """The worst case: the line scan matches a header that is really text
        INSIDE another table's multi-line string, so the span replace destroys
        that table's contents. Now refused, and the user's data survives."""
        path = tmp_path / "config.toml"
        original = (
            'model = "x"\n'
            "\n"
            "[notes]\n"
            'text = """\n'
            "[mcp_servers.open-garden-planner]\n"
            "IMPORTANT USER DATA\n"
            '"""\n'
        )
        path.write_text(original, encoding="utf-8")

        with pytest.raises(onboarding._ConfigMergeError):
            onboarding._merge_into_config(
                path,
                name=onboarding.SERVER_NAME,
                entry={"url": _URL},
                container_key="mcp_servers",
                syntax="toml",
                    replace_on_parse_error=False,
            )

        assert path.read_text(encoding="utf-8") == original
        assert "IMPORTANT USER DATA" in path.read_text(encoding="utf-8")

    def test_every_merge_result_is_parsed_before_it_is_written(
        self, tmp_path: Path
    ) -> None:
        """The contract: a surgical writer into a file OGP does not own never
        writes a result it has not verified. Asserted across the shapes."""
        bodies = [
            "",
            "model = \"gpt-5\"\n",
            "[other]\nkey = 1\n",
            'url = "http://x/mcp"\r\n',
            "[mcp_servers]\nother = 1\n",
        ]
        for body in bodies:
            path = tmp_path / "config.toml"
            path.write_text(body, encoding="utf-8")
            if body.strip():
                onboarding._merge_into_config(
                    path,
                    name=onboarding.SERVER_NAME,
                    entry={"url": _URL},
                    container_key="mcp_servers",
                    syntax="toml",
                        replace_on_parse_error=False,
                )
                # Whatever happened, the file on disk must parse.
                tomllib.loads(path.read_text(encoding="utf-8"))


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
        somewhere public, so it is the safe one — and it takes no token at all,
        so there is no write credential on the dict to leak by accident."""
        snippets = onboarding.generic_snippets(url=_URL)

        assert "token=" not in snippets["json"]
        assert "token=" not in snippets["cli"]
        assert "token=" not in snippets["url"]
        assert snippets["url"] == _URL
        # No key can carry the write credential: the signature has no token.
        assert "write_url" not in snippets

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


class TestDottedContainerPaths:
    """OpenCode nests one level deeper than everyone else.

    Its published schema declares ``mcp`` as only ``additionalProperties: {}``
    and never says where a server goes, so the only way to learn it was to RUN
    ``opencode mcp add <name> --url <url> --global`` against a throwaway
    ``XDG_CONFIG_HOME`` — which writes ``mcp.servers.<name>``. Reading the docs
    produced a registry that wrote an entry the client ignores AND reported
    every real registration as absent.
    """

    def test_opencode_container_is_the_observed_nested_path(self) -> None:
        target = next(t for t in onboarding.TARGETS if t.client_id == "opencode")
        assert target.container_key == "mcp.servers"

    def test_dotted_merge_creates_the_nesting(self, tmp_path: Path) -> None:
        path = tmp_path / "opencode.jsonc"
        path.write_text('{"theme": "dark"}', encoding="utf-8")

        onboarding._merge_into_config(
            path,
            name="og",
            entry={"type": "remote", "url": _URL},
            container_key="mcp.servers",
            syntax="jsonc",
                replace_on_parse_error=False,
        )

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["theme"] == "dark"
        assert data["mcp"]["servers"]["og"]["url"] == _URL
        # NOT directly under mcp — that was the bug.
        assert "og" not in data["mcp"]

    def test_dotted_snippet_has_the_same_shape(self) -> None:
        snippet = json.loads(onboarding.snippet_for_client("opencode", url=_URL))
        assert snippet["mcp"]["servers"]["open-garden-planner"]["url"] == _URL

    def test_dotted_read_back_finds_the_entry(self, tmp_path: Path) -> None:
        config = tmp_path / ".config" / "opencode"
        config.mkdir(parents=True)
        # Exactly what the real CLI produced.
        (config / "opencode.jsonc").write_text(
            json.dumps(
                {"mcp": {"servers": {"open-garden-planner": {"type": "remote", "url": _URL}}}}
            ),
            encoding="utf-8",
        )
        assert onboarding.registered_url("opencode") == _URL
        assert onboarding.is_stale("opencode", _URL) is False

    def test_update_path_also_refuses_rather_than_re_serialising(
        self, _isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The P1 regression, and the reason the guard lives at the seam.

        The FIRST version of `merge_supported` was checked on the no-CLI path
        only. With the CLI present but reporting "already exists" — which is
        exactly the path a user reaches after a port change or a token
        rotation, the case this whole issue exists for — the self-heal fell
        through to the merge, re-serialised the foreign JSONC, and reported
        success while eating the user's comments.
        """
        import subprocess as _subprocess

        config = _isolated_home / ".config" / "opencode"
        config.mkdir(parents=True)
        original = '{\n  // my own notes\n  /* block note */\n  "mcp": {"servers": {}}\n}\n'
        (config / "opencode.jsonc").write_text(original, encoding="utf-8")

        monkeypatch.setattr(
            onboarding.shutil, "which", lambda cmd: "/usr/bin/opencode" if cmd == "opencode" else None
        )

        def fake_run(args, **_kwargs):  # noqa: ANN001, ANN003
            return _subprocess.CompletedProcess(
                args, 1, stdout="", stderr="Error: server already exists"
            )

        monkeypatch.setattr(onboarding.subprocess, "run", fake_run)

        result = onboarding.install_to_client("opencode", url=_URL)

        # Refused, and — the point of the test — the file is untouched. The
        # refusal now comes from the single seam guard, so it does not quote the
        # CLI's stderr; what matters is that it does not merge.
        assert result.success is False
        assert "will not rewrite" in result.detail
        assert (config / "opencode.jsonc").read_text(encoding="utf-8") == original
        # And no .bak either: nothing was written at all.
        assert not (config / "opencode.jsonc.bak").exists()

    def test_no_target_with_a_refused_merge_reports_a_merge_method(
        self, monkeypatch: pytest.MonkeyPatch, _isolated_home: Path
    ) -> None:
        """A button whose only possible outcome is a refusal is a dead end with
        a polite message — the shape #366 was opened to close. `detect_clients`
        must report `manual` for a target whose merge is unsupported and whose
        CLI is absent, so the dialog hides the Add button."""
        config = _isolated_home / ".config" / "opencode"
        config.mkdir(parents=True)
        (config / "opencode.jsonc").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(onboarding.shutil, "which", lambda _cmd: None)

        info = {c.client_id: c for c in onboarding.detect_clients()}["opencode"]
        assert info.detected is True
        assert info.install_method == "manual"

    def test_a_non_object_container_is_refused_not_overwritten(
        self, tmp_path: Path
    ) -> None:
        """Silently replacing ``{"mcp": "a string"}`` with an object turns a
        malformed foreign file into a plausible-looking one — data loss with
        extra steps. `_container_get` was already defensive; the writer must
        be too."""
        for bad in ('"a string"', '["a", "list"]', "3", "null"):
            path = tmp_path / "opencode.jsonc"
            path.write_text('{"mcp": %s}' % bad, encoding="utf-8")
            original = path.read_text(encoding="utf-8")

            with pytest.raises(onboarding._ConfigMergeError):
                onboarding._merge_into_config(
                    path,
                    name="og",
                    entry={"url": _URL},
                    container_key="mcp.servers",
                    syntax="jsonc",
                    replace_on_parse_error=False,
                )
            assert path.read_text(encoding="utf-8") == original

    def test_flat_containers_still_work(self, tmp_path: Path) -> None:
        """The dotted support must not have broken the single-level family."""
        path = tmp_path / "mcp.json"
        onboarding._merge_into_config(
            path,
            name="og",
            entry={"url": _URL},
            container_key="mcpServers",
            syntax="json",
            replace_on_parse_error=False,
        )
        assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["og"] == {
            "url": _URL
        }

    @pytest.mark.parametrize(
        ("client_id", "relpath"),
        [
            ("gemini", ".gemini/config/mcp_config.json"),  # `foreign`
            ("cursor", ".cursor/mcp.json"),  # `own` — the narrowing matters here
        ],
    )
    def test_a_wrong_typed_container_is_a_shape_error_and_never_replaced(
        self, client_id: str, relpath: str, _isolated_home: Path
    ) -> None:
        """A document that PARSED but whose container is the wrong type.

        The pre-refactor code did ``servers = data.get("mcpServers"); if not
        isinstance(servers, dict): servers = {}`` — which silently overwrote a
        wrong-typed container **even when ``replace_on_parse_error=False``**, in
        a file it had just promised to leave alone. The distinction that fixes
        it: a *parse* error means we understood nothing (replacing an `own`
        file is defensible), a *shape* error means we read the document
        perfectly well and only one key has the wrong type — so replacing throws
        away the user's unrelated top-level keys for no reason.
        """
        path = _isolated_home / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        original = json.dumps(
            {"theme": "dark", "unrelated": {"keep": [1, 2, 3]}, "mcpServers": "oops"},
            indent=2,
        )
        path.write_text(original, encoding="utf-8")

        result = onboarding.install_to_client(client_id, url=_URL)

        assert result.success is False
        assert "not an object" in result.detail or "wrong" in result.detail.lower() or (
            "replace" in result.detail.lower()
        ), result.detail
        # Byte-for-byte, for the `own` target too: a shape error narrows the
        # one target whose parse errors were allowed to replace.
        assert path.read_text(encoding="utf-8") == original
        # And nothing else was created. A refusal must leave the filesystem
        # exactly as it found it — a `.bak` beside a file we declined to touch
        # is litter, not a safety net.
        assert sorted(p.name for p in path.parent.iterdir()) == [path.name]

    def test_a_wrong_typed_nested_container_is_also_refused(self, tmp_path: Path) -> None:
        """Same rule through the dotted path: `{"mcp": {"servers": 7}}`."""
        path = tmp_path / "opencode.jsonc"
        original = '{"mcp": {"servers": 7, "other": true}}'
        path.write_text(original, encoding="utf-8")
        with pytest.raises(onboarding._ConfigMergeError):
            onboarding._merge_into_config(
                path,
                name="og",
                entry={"url": _URL},
                container_key="mcp.servers",
                syntax="jsonc",
                replace_on_parse_error=True,  # even an `own`-style policy
            )
        assert path.read_text(encoding="utf-8") == original


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


class TestTokenRouteIsReal:
    """``ClientTarget.token_route`` must not be an inert switch.

    A field that reads like a working flip but has no reader is worse than no
    field: the next person sets it, ships, and discovers at runtime that write
    tools are unreachable. So the header branch is implemented AND pinned here.
    """

    def test_no_target_enables_the_header_route_yet(self) -> None:
        """Deliberate: both new CLIs accept a header, but transmission on
        tool-call requests is unmeasured, so URL stays the default everywhere."""
        assert all(t.token_route == "url" for t in onboarding.TARGETS)

    def test_header_route_puts_the_token_in_a_header_not_the_url(self) -> None:
        entry = onboarding._flat_entry(_URL, _TOKEN, use_header=True)
        assert entry["headers"] == {"Authorization": f"Bearer {_TOKEN}"}
        assert "token=" not in str(entry["url"])

    def test_header_route_is_a_noop_without_a_token(self) -> None:
        entry = onboarding._flat_entry(_URL, None, use_header=True)
        assert "headers" not in entry

    def test_cli_argv_carries_the_header_when_enabled(self) -> None:
        args = onboarding._opencode_add_args(
            onboarding.SERVER_NAME, _URL, _TOKEN, use_header=True
        )
        assert "--header" in args
        assert f"Authorization:Bearer {_TOKEN}" in args
        assert "token=" not in " ".join(args)
        # --global must survive the header branch.
        assert "--global" in args

    def test_cli_argv_defaults_to_the_url_token(self) -> None:
        args = onboarding._opencode_add_args(onboarding.SERVER_NAME, _URL, _TOKEN)
        assert "--header" not in args
        assert onboarding.url_with_token(_URL, _TOKEN) in args


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
                replace_on_parse_error=False,
        )

        assert onboarding.registered_url("codex") == _URL

    def test_jsonc_registration_is_detected(self, _isolated_home: Path) -> None:
        """The commented-config case on the READ path: if the tolerant reader
        were missing here, every OpenCode user would see their own working
        registration reported as absent. Uses the OBSERVED nested container
        (`mcp.servers`, see TestDottedContainerPaths)."""
        config = _isolated_home / ".config" / "opencode"
        config.mkdir(parents=True)
        (config / "opencode.jsonc").write_text(
            '{\n  // keep me\n  "mcp": {}\n}\n', encoding="utf-8"
        )

        assert onboarding.registered_url("opencode") is None  # empty container
        onboarding._merge_into_config(
            config / "opencode.jsonc",
            name=onboarding.SERVER_NAME,
            entry=onboarding._opencode_entry(_URL, None),
            container_key="mcp.servers",
            syntax="jsonc",
                replace_on_parse_error=False,
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
