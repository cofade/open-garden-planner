"""AI client onboarding (US-D1.6, generalized by issue #366): detect installed
MCP clients and register the Agent API server's connect URL into their config,
or hand back a copy-paste snippet when automatic registration isn't safe or
possible.

Qt-free (unit-testable without a GUI); the dialog is a thin shell over this
module.

**Clients are data, not control flow (issue #366).** A client used to be a
``Literal`` plus an ``if``/``elif`` chain through ``install_to_client`` and
``snippet_for_client``, so every new vendor meant a new branch in two places
and the only route for an *unknown* client was "Copy URL and paste it into a
chat" — which publishes the D2 write token into a transcript and produces
registrations that silently rot. Each client is now one frozen
:class:`ClientTarget` record in :data:`TARGETS`, and the three things that
actually differ between clients are three independent *fields* rather than
three branches:

* ``container_key`` — ``mcpServers`` (the JSON family) / ``mcp_servers`` (TOML)
  / ``mcp.servers`` (OpenCode, and NESTED). Three names for the same semantic
  model; the OpenCode spelling is known only by running its CLI, and its
  published schema does not say — see the ``opencode`` record below.
* ``syntax`` — ``json`` / ``jsonc`` / ``toml``, which selects a *serializer*
  strategy rather than a client branch.
* ``entry`` / ``cli_argv`` — the per-client entry shape and CLI, when it has one.

The hard parts were never per-client: backup-before-write, atomic replace,
fail-closed on a file OGP does not own, and preserving foreign keys. Those live
once, in :func:`_merge_into_config`, and every syntax routes through it.

Per-client strategy, chosen from what each client's own docs support:

* **Cursor** — direct JSON merge into ``~/.cursor/mcp.json`` (documented flat
  ``mcpServers`` schema). OGP effectively owns this file, so a parse error may
  be recovered by replacing.
* **Claude Code** — ``claude mcp add --transport http --scope user`` via the
  CLI when it's on PATH (it validates its own writes and self-heals an existing
  entry); otherwise a direct atomic merge into the TOP-LEVEL ``mcpServers`` of
  ``~/.claude.json`` (the same user-scope location the CLI writes, read by both
  the CLI and the VS Code extension). The CLI is frequently NOT on PATH (e.g.
  the native ``~/.local/bin`` installer dir, or an extension-only install), so
  the direct-merge fallback is what makes one-click work without a terminal.
  The merge fails CLOSED on an unreadable ``~/.claude.json`` (it also holds
  OAuth / projects / trust) rather than replacing it.
* **OpenCode** — ``opencode mcp add <name> --url <url> --global`` when the CLI
  is on PATH (entry ``{type: "remote", url, oauth: false}`` under
  ``mcp.servers``). **Without the CLI there is no merge at all**, by decision:
  its config is commented JSON that any merge would have to re-serialise whole,
  discarding the user's own comments, so the record sets
  ``merge_supported=False`` and registration refuses with an explanation plus
  the manual snippet. The config is a *commented* JSON variant that plain
  ``json.load()`` rejects, which is why the READER (:func:`_strip_jsonc`) is
  tolerant and the writer is not.
* **Codex** — ``codex mcp add <name> --url <url>`` when the CLI is on PATH;
  otherwise a **surgical TOML append** into ``~/.codex/config.toml``
  (container ``mcp_servers``). Surgical, not a re-serialise: ``tomllib`` reads
  and validates, and only the one table's line span is rewritten, so the user's
  own comments and formatting survive (issue #366 — a full ``tomli_w``-style
  rewrite of a file OGP does not own would destroy them).
* **Gemini CLI** — direct JSON merge into
  ``~/.gemini/config/mcp_config.json`` (same flat ``mcpServers`` shape as
  Cursor).
* **Claude Desktop** — detection only, and *cannot* connect to this server:
  Anthropic's connector UI reaches servers from its own cloud and rejects
  ``localhost`` / ``http://`` URLs, and ``claude_desktop_config.json`` is
  stdio-only. So OGP writes nothing here and the dialog redirects the user.

Every write path preserves unknown keys/other servers, backs up the original
file before touching it, and writes atomically (temp file + ``os.replace``) —
the first such pattern in this codebase (see ADR-035): every prior JSON writer
here does a bare ``open(path, "w")`` because it only ever writes *our own*
file. This module writes into files owned by *other* applications, so the bar
is higher.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

#: Client ids are plain strings, not a ``Literal``. The registry is the
#: authority on which ids exist (:data:`TARGETS`); a closed union here would be
#: a second list to keep in step with it. An unknown id is still a programming
#: error and still raises (see :func:`install_to_client`).
ClientId = str

#: How a client gets registered. "merge" is syntax-neutral on purpose — the
#: name used to be "json_merge", which was already a lie for the TOML and JSONC
#: targets and welded the syntax axis back onto a field whose whole point is
#: that syntax is separate (issue #366).
InstallMethod = Literal["merge", "cli", "manual"]
Syntax = Literal["json", "jsonc", "toml"]
Ownership = Literal["own", "foreign"]

#: Fixed, English server identifier written into every client's config.
#: MCP server names are an API contract, not UI copy (mirrors ADR-033's
#: "tool/resource descriptions are English" precedent) — never translated.
SERVER_NAME = "open-garden-planner"

#: How a target carries the write token when it is configured.
#:
#: Default is ``"url"`` for every target, including the two whose CLIs accept
#: ``--header``: a header is the better home for a secret, but *documented*
#: support is not evidence that a client transmits it on streamable-HTTP
#: **tool-call** requests — the exact failure Claude Code has open upstream
#: (anthropics/claude-code#50464 / #28293). Shipping the header as the default
#: before that is measured would make write tools silently unreachable.
#:
#: The header route is genuinely implemented (it puts the token in the entry's
#: ``headers`` map, or in the CLI's ``--header`` argv) and unit-tested; what is
#: deliberately NOT done is *enabling* it for any target. Flipping one is a
#: single-field data change once the live dogfood run confirms transmission.
TokenRoute = Literal["url", "header"]

#: Header name used by the ``header`` token route.
AUTH_HEADER = "Authorization"


# ---------------------------------------------------------------------------
# Path resolution (per-client, referenced by the registry records below)
# ---------------------------------------------------------------------------


def _cursor_dir() -> Path:
    return Path.home() / ".cursor"


def _cursor_config_path() -> Path:
    return _cursor_dir() / "mcp.json"


def _claude_code_user_config_path() -> Path:
    # $CLAUDE_CONFIG_DIR overrides the location (matches the Claude CLI).
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(env) if env else Path.home()) / ".claude.json"


def _claude_desktop_config_dir() -> Path | None:
    """Claude Desktop's config directory for this OS, or ``None`` (Linux —
    Claude Desktop only ships for macOS/Windows)."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude"
    return None


def _claude_desktop_config_path() -> Path | None:
    config_dir = _claude_desktop_config_dir()
    return None if config_dir is None else config_dir / "claude_desktop_config.json"


def _xdg_config_home() -> Path:
    """``$XDG_CONFIG_HOME``, else ``~/.config`` (the default on every platform
    OpenCode uses that path on, including Windows)."""
    env = os.environ.get("XDG_CONFIG_HOME")
    return Path(env) if env else Path.home() / ".config"


def _opencode_config_path() -> Path:
    # NOTE: a ``.jsonc``, not a ``.json``. Detecting this client by globbing
    # for "opencode.json" would miss every real installation.
    return _xdg_config_home() / "opencode" / "opencode.jsonc"


def _codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def _gemini_config_path() -> Path:
    return Path.home() / ".gemini" / "config" / "mcp_config.json"


# ---------------------------------------------------------------------------
# The target registry (issue #366)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientTarget:
    """One onboarding target, expressed as data.

    Every field is a *per-client* fact; nothing here is control flow. Adding a
    client is one record in :data:`TARGETS`.
    """

    client_id: ClientId
    #: English, untranslated product name (ADR-033: client/server names are an
    #: API contract, not UI copy). Used as the dialog's group-box title.
    display_name: str
    #: Whether the client appears installed. Advisory only — a client with an
    #: unusual install layout reads as "not detected" and falls through to the
    #: generic fallback, which is the correct degradation.
    detect_installed: Callable[[], bool]
    #: The config file this target writes into (``None`` when it has none).
    config_path: Callable[[], Path | None]
    #: Key under which MCP servers live in that file.
    container_key: str
    #: Serialisation strategy for the config file.
    syntax: Syntax
    #: Builds the server entry. ``(url, token, use_header) -> dict``. ``token``
    #: is ``None`` for a read-only registration.
    entry: Callable[[str, str | None, bool], dict[str, object]]
    #: ``"own"`` = a file OGP effectively owns (a parse error may be recovered
    #: by replacing); ``"foreign"`` = a file holding state OGP does not own
    #: (OAuth / projects / trust / the user's own comments), which must be left
    #: untouched if it cannot be parsed.
    #:
    #: REQUIRED, with no default: a safety decision must never be inherited
    #: silently. The issue's own design sketch made it mandatory and it should
    #: stay that way — defaulting it to ``"own"`` is how the Claude Desktop
    #: record came to declare a file OGP flatly does not own as replaceable.
    ownership: Ownership
    #: CLI executable name, when the client ships a documented ``mcp add``.
    cli_name: str | None = None
    #: Argv (after the executable) for an ``mcp add``. Omitted means the direct
    #: merge is the only path.
    cli_argv: Callable[[str, str | None, bool], tuple[str, ...]] | None = None
    #: Argv for a remove, used to self-heal an existing entry. A client with no
    #: documented remove (OpenCode) falls back to the merge instead, which
    #: replaces the entry wholesale and is therefore also an update.
    cli_remove_argv: Callable[[str], tuple[str, ...]] | None = None
    #: Whether a DIRECT MERGE can register this client without rewriting the
    #: whole file. False for a ``jsonc`` foreign file: a merge would have to
    #: re-serialise, and re-serialising a file you do not own discards the
    #: user's own comments — which is exactly what the TOML path refuses to do
    #: and what §11.4 forbids. Refusing is the honest answer for the no-CLI
    #: case, and it has precedent in this very module: Claude Desktop is
    #: detection-only because it genuinely cannot be registered.
    merge_supported: bool = True
    #: ``False`` for a client that cannot reach a local HTTP server at all —
    #: detection only, never written (Claude Desktop, issue #253).
    supports_local_http: bool = True
    #: Where the token rides when this target is registered write-capable.
    token_route: TokenRoute = "url"
    #: The client reads its user-scope config only at session start, so the
    #: dialog must tell the user to restart rather than leave them wondering.
    requires_restart: bool = False


# --- per-client entry builders ------------------------------------------------


def _token_url(url: str, token: str | None, use_header: bool) -> str:
    """The URL as it should be written for this token route.

    The whole POINT of the header route is that the secret leaves the URL, so
    this must return the READ-ONLY url when the token is riding a header —
    otherwise the token is in BOTH places and the route buys nothing.
    """
    if use_header and token:
        return read_only_url(url)
    return url_with_token(url, token)


def _flat_entry(url: str, token: str | None, use_header: bool = False) -> dict[str, object]:
    """The common ``{"url": ...}`` shape (Cursor, Gemini, Codex)."""
    entry: dict[str, object] = {"url": _token_url(url, token, use_header)}
    if use_header and token:
        entry["headers"] = {AUTH_HEADER: f"Bearer {token}"}
    return entry


def _claude_code_entry(
    url: str, token: str | None, use_header: bool = False
) -> dict[str, object]:
    """Claude Code / VS Code extension entry for ``~/.claude.json``.
    ``type: "http"`` is REQUIRED — without it the entry is not recognised as an
    HTTP server and is silently ignored (a ``url``-only entry doesn't match the
    stdio-*command* shape either, so it simply never connects).

    ``use_header`` is never enabled for this target: Claude Code stores a
    configured header but does not send it on tool-call requests, so the URL is
    the only route that works. The parameter exists so the contract is uniform.
    """
    entry: dict[str, object] = {
        "type": "http",
        "url": _token_url(url, token, use_header),
    }
    if use_header and token:
        entry["headers"] = {AUTH_HEADER: f"Bearer {token}"}
    return entry


def _opencode_entry(
    url: str, token: str | None, use_header: bool = False
) -> dict[str, object]:
    """OpenCode's ``mcp.servers.<name>`` entry.

    ``type: "remote"`` and ``url`` are both required by OpenCode's published
    schema. ``oauth: false`` disables its OAuth auto-detection, which is at
    best pointless against a ``?token=`` local server and at worst an error the
    user has to diagnose. ``timeout`` is deliberately NOT set: OpenCode's
    default is 5000 ms, which is worth measuring against
    ``render_canvas_image`` on a large plan before hard-coding a value that
    then has to be maintained.
    """
    entry: dict[str, object] = {
        "type": "remote",
        "url": _token_url(url, token, use_header),
        "oauth": False,
        "enabled": True,
    }
    if use_header and token:
        entry["headers"] = {AUTH_HEADER: f"Bearer {token}"}
    return entry


# --- per-client CLI argv builders ---------------------------------------------


def _claude_code_add_args(
    name: str, url: str, token: str | None, use_header: bool = False
) -> tuple[str, ...]:
    """Args for ``claude mcp add``.

    Claude Code stores a configured ``--header`` but does not send it on
    tool-call requests for streamable-HTTP servers (anthropics/claude-code
    #50464 / #28293), so a header would leave write tools unreachable. The URL
    (query string included) is always transmitted, so the token goes there via
    ``url_with_token`` — no ``--header``, which also removes the variadic-
    ordering footgun the old header form carried.
    """
    args = ["add", "--transport", "http", "--scope", "user", name]
    args += _header_args(url, token, use_header)
    return tuple(args)


def _header_args(url: str, token: str | None, use_header: bool) -> list[str]:
    """Either the token in the URL, or as a ``--header`` pair — never both."""
    if use_header and token:
        return [read_only_url(url), "--header", f"{AUTH_HEADER}:Bearer {token}"]
    return [url_with_token(url, token)]


def _claude_code_remove_args(name: str) -> tuple[str, ...]:
    return ("remove", name, "--scope", "user")


def _opencode_add_args(
    name: str, url: str, token: str | None, use_header: bool = False
) -> tuple[str, ...]:
    """Args for ``opencode mcp add``.

    ``--global`` is LOAD-BEARING: without it the CLI writes the *project*
    config (``opencode.json`` in the current directory), so a user who ran
    "Add to OpenCode" from a random working directory would silently get a
    config file dropped into their project.
    """
    args = ["mcp", "add", name, "--url"]
    args += _header_args(url, token, use_header)
    args.append("--global")
    return tuple(args)


def _codex_add_args(
    name: str, url: str, token: str | None, use_header: bool = False
) -> tuple[str, ...]:
    """Args for ``codex mcp add`` (streamable HTTP)."""
    args = ["mcp", "add", name, "--url"]
    args += _header_args(url, token, use_header)
    return tuple(args)


def _codex_remove_args(name: str) -> tuple[str, ...]:
    return ("mcp", "remove", name)


# --- the registry --------------------------------------------------------------


TARGETS: tuple[ClientTarget, ...] = (
    ClientTarget(
        client_id="cursor",
        display_name="Cursor",
        detect_installed=lambda: _cursor_dir().is_dir(),
        config_path=_cursor_config_path,
        container_key="mcpServers",
        syntax="json",
        entry=_flat_entry,
        ownership="own",
    ),
    ClientTarget(
        client_id="claude_code",
        display_name="Claude Code",
        detect_installed=lambda: shutil.which("claude") is not None
        or _claude_code_user_config_path().exists(),
        config_path=_claude_code_user_config_path,
        container_key="mcpServers",
        syntax="json",
        entry=_claude_code_entry,
        cli_name="claude",
        cli_argv=lambda name, url, token, use_header=False: (
            "mcp",
        ) + _claude_code_add_args(name, url, token, use_header),
        cli_remove_argv=_claude_code_remove_args,
        ownership="foreign",
        requires_restart=True,
    ),
    ClientTarget(
        client_id="opencode",
        display_name="OpenCode",
        # Detected by its own config file or its CLI on PATH.
        detect_installed=lambda: _opencode_config_path().exists()
        or shutil.which("opencode") is not None,
        config_path=_opencode_config_path,
        # NESTED, and known only by OBSERVATION: running
        # `opencode mcp add <name> --url <url> --global` writes
        # `mcp.servers.<name>`, not `mcp.<name>`. OpenCode's published schema
        # does not say so — the `mcp` property is only
        # `additionalProperties: {}` — so reading this from the docs would have
        # produced a registry that writes an entry the client ignores and
        # reports every real registration as absent. See the DottedContainer
        # tests.
        container_key="mcp.servers",
        syntax="jsonc",
        entry=_opencode_entry,
        cli_name="opencode",
        cli_argv=_opencode_add_args,
        ownership="foreign",
        # A merge here would re-serialise a JSONC file, discarding the user's
        # own comments. The CLI (`opencode mcp add --global`, verified by
        # running it) is the supported route; without it, the manual snippet
        # is offered rather than silently rewriting their config.
        merge_supported=False,
        requires_restart=True,
    ),
    ClientTarget(
        client_id="codex",
        display_name="Codex",
        detect_installed=lambda: _codex_config_path().exists()
        or shutil.which("codex") is not None,
        config_path=_codex_config_path,
        container_key="mcp_servers",
        syntax="toml",
        entry=_flat_entry,
        cli_name="codex",
        cli_argv=_codex_add_args,
        cli_remove_argv=_codex_remove_args,
        ownership="foreign",
        requires_restart=True,
    ),
    ClientTarget(
        client_id="gemini",
        display_name="Gemini CLI",
        detect_installed=lambda: _gemini_config_path().exists(),
        config_path=_gemini_config_path,
        container_key="mcpServers",
        syntax="json",
        entry=_flat_entry,
        # NOT "own". A dedicated mcp_config.json is a small file, but it is
        # still the user's configuration, and this shape was read off a local
        # filesystem rather than verified against Gemini's current docs — so it
        # fails closed, the safe default for anything unverified.
        ownership="foreign",
    ),
    ClientTarget(
        client_id="claude_desktop",
        display_name="Claude Desktop",
        detect_installed=lambda: _claude_desktop_config_dir() is not None
        and (_claude_desktop_config_dir() or Path()).is_dir(),
        config_path=_claude_desktop_config_path,
        container_key="mcpServers",
        syntax="json",
        entry=_flat_entry,
        # Cannot reach a local server at all — detection only, never written.
        # `foreign` is stated even though nothing is ever written, so flipping
        # `supports_local_http` can never silently make OGP replace a file it
        # does not own.
        ownership="foreign",
        supports_local_http=False,
    ),
)


def get_target(client_id: ClientId) -> ClientTarget:
    """Look up a target by id. Raises ``ValueError`` for an unknown id — a
    programming error, not a runtime condition the caller should handle."""
    for target in TARGETS:
        if target.client_id == client_id:
            return target
    raise ValueError(f"Unknown client_id: {client_id}")


# ---------------------------------------------------------------------------
# Public data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientInfo:
    """One onboarding target's detection state, derived from its record."""

    client_id: ClientId
    display_name: str
    detected: bool
    install_method: InstallMethod
    config_path: Path | None
    #: The URL currently registered in the client's config, if any — used to
    #: tell "registered", "stale" and "not registered" apart (issue #366: a
    #: hand-pasted or token-rotated entry otherwise fails silently).
    registered_url: str | None = None
    syntax: Syntax = "json"
    supports_local_http: bool = True
    requires_restart: bool = False


@dataclass(frozen=True)
class InstallResult:
    """Outcome of an install attempt.

    ``detail`` is a short, English, technical description (raw CLI
    stderr/exception text) meant to be embedded inside a translated sentence
    by the caller (mirrors ``preferences_dialog._test_api``'s
    ``tr("Error testing {api}: {error}").format(error=str(e))`` pattern) — it is
    not itself a complete user-facing message.
    """

    client_id: ClientId
    success: bool
    detail: str
    backup_path: Path | None = None


# ---------------------------------------------------------------------------
# Syntax strategies
# ---------------------------------------------------------------------------


class _ConfigMergeError(Exception):
    """A config file existed but could not be safely merged (unparseable /
    non-object). Raised only for a ``foreign`` file so the caller reports
    failure and leaves a file OGP doesn't own untouched instead of replacing
    it."""


class _ConfigReadError(_ConfigMergeError):
    """A config file could not be READ at all (as opposed to read-and-refused).

    #: A marker type for "this file could not be READ at all", as distinct from
    #: read-and-understood-but-refused. Nothing catches it by type — the readers
    #: catch broadly on purpose (see ``registered_url``) — so it exists to name
    #: the condition in one place, not to drive control flow. A bare
    #: ``ValueError`` here was a real crash: it escaped the reader, reached the
    #: dialog's ``__init__``, and PyQt6 turned it into ``qFatal()``/``abort()``.
    """


class _ConfigShapeError(_ConfigMergeError):
    """A config file parsed fine, but the MCP container is the wrong type.

    Deliberately distinct from a parse error: we UNDERSTOOD the document, so
    replacing it would discard the user's other top-level keys for no reason.
    Fails closed whatever the target's ``ownership`` says.
    """


def _scan_outside_strings(
    text: str, handle: Callable[[int, str, list[str]], int | None]
) -> str:
    """Walk ``text``, letting ``handle`` rewrite the parts NOT inside a string.

    ``handle(i, ch, out)`` is called for every character outside a string
    literal and returns how far to advance:

    * ``None`` — keep ``ch`` and advance one.
    * ``0`` — drop ``ch`` and advance one (the following character is then
      processed normally, which is how a comma is dropped but its closer kept).
    * ``k > 0`` — drop ``ch`` and the next ``k - 1`` characters, advancing ``k``.

    It may raise, which is how an unterminated block comment becomes an error
    instead of a silently truncated document.

    Both halves of :func:`_strip_jsonc` need exactly this walk, and they used to
    be two near-verbatim copies of the same state machine — which is the shape
    in which a fix lands in one copy and not the other. "A ``//`` inside a
    string literal is data, and a regex cannot tell" is the property that makes
    this parser correct at all, so it gets written once. (This scanner handles
    ``//`` and ``/* */`` only — no ``#``, which is not a JSONC comment and would
    break a URL fragment.)
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        advance = handle(i, ch, out)
        if advance is None:
            out.append(ch)
            i += 1
        else:
            i += max(advance, 1)
    return "".join(out)


def _strip_jsonc(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments and trailing commas from a JSONC
    document so ``json.loads`` accepts it.

    Comment-stripped by character scan, NOT by regex: a ``#`` or ``//`` inside
    a string literal is data, and a regex cannot tell. Trailing commas are
    removed in a second pass (a comma immediately before a closing ``}``/``]``
    is legal in JSONC and illegal in JSON) over the comment-free text, so a
    comma inside a string is never even a candidate.
    """
    n = len(text)

    def _comment(i: int, _ch: str, _out: list[str]) -> int | None:
        if text[i + 1 : i + 2] != "/":
            close = text.find("*/", i + 2)
            if close < 0:
                # An unterminated block comment means the rest of the file is
                # comment. Swallowing it silently would let the tolerant reader
                # "accept" a malformed document, so raise a MODULE-OWNED error
                # that every reader catches — never a bare ValueError, which
                # would escape into the Qt slot and abort the app.
                raise _ConfigReadError("Unterminated /* comment in JSONC input")
            return close + 2 - i
        end = text.find("\n", i)  # the newline itself is kept
        return (n if end < 0 else end) - i

    def _drop_comment(i: int, ch: str, out: list[str]) -> int | None:
        if ch == "/" and i + 1 < n and text[i + 1] in "/*":
            return _comment(i, ch, out)
        return None

    stripped = _scan_outside_strings(text, _drop_comment)
    m = len(stripped)

    def _drop_trailing_comma(i: int, ch: str, _out: list[str]) -> int | None:
        if ch != ",":
            return None
        k = i + 1
        while k < m and stripped[k] in " \t\r\n":
            k += 1
        if k < m and stripped[k] in "}]":
            return 0  # drop the comma, keep the closer
        return None

    return _scan_outside_strings(stripped, _drop_trailing_comma)


def _toml_escape(value: str) -> str:
    """Render a Python string as a TOML basic string (quotes included)."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _toml_render_table(container_key: str, name: str, entry: dict[str, object]) -> str:
    """Render one ``[container.name]`` table as TOML text."""
    lines = [f"[{container_key}.{name}]"]
    for key, value in entry.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key} = {value}")
        else:
            lines.append(f"{key} = {_toml_escape(str(value))}")
    return "\n".join(lines) + "\n"


def _toml_table_span(lines: list[str], table_header: str) -> tuple[int, int] | None:
    """Line span ``[start, end)`` of ``table_header`` in ``lines``, or ``None``.

    A TOML table runs from its own header to the next header line or EOF, so
    the span is found by scanning rather than by re-serialising the document.
    That is what keeps the user's comments and formatting intact.
    """
    start = None
    for index, line in enumerate(lines):
        if line.strip() == table_header:
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("["):
            end = index
            break
    return (start, end)


def _container_get(data: dict[str, object], container_key: str) -> object:
    """Read a possibly-DOTTED container path, e.g. ``mcp.servers``.

    OpenCode nests one level deeper than the rest: running
    ``opencode mcp add --global`` writes ``mcp.servers.<name>``, and its
    published schema does not say so (the ``mcp`` property is only
    ``additionalProperties: {}``), so this shape is known by OBSERVATION.
    """
    node: object = data
    for part in container_key.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _container_set(data: dict[str, object], container_key: str, name: str, entry: dict) -> None:
    """Create the container path if needed and set ``<path>.<name> = entry``.

    Refuses rather than overwrites when an INTERMEDIATE node exists but is not
    an object. Silently replacing ``{"mcp": "a string"}`` with
    ``{"mcp": {...}}`` turns a malformed foreign file into a plausible-looking
    one, which is data loss with extra steps. ``_container_get`` is defensive
    about the same shapes; the writer must be too.
    """
    parts = container_key.split(".")
    node = data
    for part in parts[:-1]:
        if part in node:
            child = node[part]
            if not isinstance(child, dict):
                raise _ConfigShapeError(
                    f"Cannot write {container_key!r}: {part!r} already exists and "
                    f"is not an object ({type(child).__name__}). Left untouched."
                )
        else:
            child = {}
            node[part] = child
        node = child
    leaf = parts[-1]
    servers = node.get(leaf)
    if servers is None:
        servers = {}
    elif not isinstance(servers, dict):
        raise _ConfigShapeError(
            f"Cannot write {container_key!r}: it already exists and is not an "
            f"object ({type(servers).__name__}). Left untouched."
        )
    servers[name] = entry
    node[leaf] = servers


def _nested_dict(container_key: str, name: str, entry: dict) -> dict:
    """Build ``{"mcp": {"servers": {name: entry}}}``-shaped data for a snippet."""
    out: dict = {}
    _container_set(out, container_key, name, entry)
    return out


def _merge_json_like(
    path: Path,
    *,
    name: str,
    entry: dict[str, object],
    container_key: str,
    replace_on_parse_error: bool,
    tolerant: bool,
) -> Path | None:
    """Shared read-modify-write for the ``json`` and ``jsonc`` syntaxes.

    ``tolerant`` selects the JSONC reader (comments + trailing commas); the
    ``json`` reader stays strict on purpose, so leniency can never leak into
    the fail-closed path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, object] = {}
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8-sig")
            loaded = json.loads(_strip_jsonc(text) if tolerant else text)
        except Exception as exc:  # noqa: BLE001 — TRUST BOUNDARY (invariant 14)
            # Another program's file. See the note on `registered_url`: the
            # family is deliberately not enumerated, because a deeply nested
            # document alone makes `json.loads` raise `RecursionError`, and the
            # list would have been wrong the moment that was discovered.
            if not replace_on_parse_error:
                raise _ConfigMergeError(
                    f"Could not read existing {path} ({exc}); left untouched."
                ) from exc
            logger.warning("Could not parse existing %s (%s); replacing it", path, exc)
            loaded = {}
        if isinstance(loaded, dict):
            data = loaded
        elif not replace_on_parse_error:
            raise _ConfigMergeError(f"{path} is not a JSON object; left untouched.")
        else:
            logger.warning("%s does not contain a JSON object; replacing it", path)

    try:
        _container_set(data, container_key, name, entry)
    except _ConfigShapeError as exc:
        # A SHAPE complaint is not a PARSE error, and must not share its policy.
        # We READ this document successfully — only the container key is the
        # wrong type — so replacing the file would throw away the user's other
        # top-level keys for no reason. Fail closed regardless of `ownership`.
        raise _ConfigMergeError(f"{exc} in {path}") from exc

    backup = _backup_existing(path)
    _atomic_write(path, json.dumps(data, indent=2) + "\n")
    return backup


def _backup_existing(path: Path) -> Path | None:
    """Copy ``path`` aside, called IMMEDIATELY before a write that overwrites it.

    Taken as late as possible on purpose. A backup is a recovery route for a
    write that actually happened; making one before deciding to write leaves a
    second file next to someone else's config every time a merge is merely
    *refused* — and for a ``foreign`` target, refusing IS the common case. A
    refusal must leave the filesystem exactly as it found it.
    """
    if not path.exists():
        return None
    backup = path.with_name(path.name + ".bak")
    shutil.copy2(path, backup)
    return backup


def _toml_has_table(text: str, container_key: str, name: str) -> bool:
    """Whether ``text`` already defines ``[container_key.name]``, per the PARSER.

    Used to catch a spelling the textual line scan cannot see (quoted keys,
    inner spaces). Returns False on a parse error, because the caller has
    already validated the document at that point.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return False
    container = data.get(container_key)
    return isinstance(container, dict) and name in container


def _merge_toml(
    path: Path,
    *,
    name: str,
    entry: dict[str, object],
    container_key: str,
    replace_on_parse_error: bool,
) -> Path | None:
    """Surgical TOML merge: only the ``[container.name]`` table's lines change.

    Deliberately NOT a re-serialise. ``~/.codex/config.toml`` is a file OGP
    does not own, and a full rewrite (``tomli_w``-style) would discard the
    user's comments and formatting — a silent data loss in someone else's
    file. So: parse with ``tomllib`` to validate and to see whether our table
    already exists, then either append it or replace exactly its line span.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    original = ""
    if path.exists():
        try:
            original = path.read_text(encoding="utf-8-sig")
            tomllib.loads(original)
        except Exception as exc:  # noqa: BLE001 — TRUST BOUNDARY (invariant 14)
            # Another program's file; see the note on `registered_url` for why
            # the family is not enumerated. `tomllib.loads` raises
            # `RecursionError` on a deeply nested document, which is in no
            # sensible tuple.
            if not replace_on_parse_error:
                raise _ConfigMergeError(
                    f"Could not read existing {path} ({exc}); left untouched."
                ) from exc
            logger.warning("Could not parse existing %s (%s); replacing it", path, exc)
            original = ""

    header = f"[{container_key}.{name}]"
    lines = original.splitlines(keepends=True)
    span = _toml_table_span(lines, header)

    # The line scan is textual, TOML is not: `["mcp_servers"."name"]` and
    # `[ mcp_servers.name ]` are the SAME table to tomllib but invisible to
    # `line.strip() == header`. Apending in that case would declare the table
    # twice and produce a file that cannot be parsed at all — so detect it via
    # the parser and refuse, naming the spelling we actually found.
    if span is None and _toml_has_table(original, container_key, name):
        raise _ConfigMergeError(
            f"{path} already has a [{container_key}.{name}] table written in a "
            f"spelling this merge does not recognise; left untouched. Remove it "
            f"by hand, or install this client with its own CLI."
        )

    rendered = _toml_render_table(container_key, name, entry)

    if span is None:
        new_text = original
        if new_text and not new_text.endswith("\n"):
            new_text += "\n"
        if new_text.strip():
            new_text += "\n"  # blank line between tables
        new_text += rendered
    else:
        start, end = span
        head = "".join(lines[:start])
        tail = "".join(lines[end:])
        new_text = head + rendered + tail

    # A surgical writer OWES a parse check. The span arithmetic can be wrong
    # (a `[`-leading line inside a multi-line string truncates the span early,
    # and a header textually present inside ANOTHER table's multi-line string
    # makes the scan match the wrong span and destroy that table's contents).
    # Both produce a file the user's other program cannot parse, and this is a
    # file OGP does not own — so never write an unverified result. See §11.4.
    try:
        tomllib.loads(new_text)
    except Exception as exc:  # noqa: BLE001 — untrusted/derived input, not ours
        # Anything at all the parser objects to means we are about to write a
        # file the user's own program cannot read, into a file OGP does not
        # own. Never write an unverified result. See §11.4.
        raise _ConfigMergeError(
            f"Merging into {path} would produce invalid TOML ({exc}); left "
            f"untouched. Install this client with its own CLI instead."
        ) from exc

    backup = _backup_existing(path)
    _atomic_write(path, new_text)
    return backup


def _atomic_write(path: Path, text: str) -> None:
    """Same-directory temp file + ``os.replace`` so a crash mid-write can never
    leave a truncated/partial config behind."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".ogp-onboarding-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_name)
        raise


def _merge_into_config(
    path: Path,
    *,
    name: str,
    entry: dict[str, object],
    container_key: str = "mcpServers",
    syntax: Syntax = "json",
    replace_on_parse_error: bool,
) -> Path | None:
    """Read-modify-write a client's config, routing on ``syntax``.

    Preserves every other key in the file (other servers, unrelated config).
    Backs up the file's current contents to ``<name>.bak`` first if it existed
    (returns that path; ``None`` if there was nothing to back up) — note a
    second call overwrites ``.bak`` with the state from just before *that*
    call, not the original file from before OGP ever touched it.

    ``replace_on_parse_error`` is REQUIRED, with no default. It used to default
    to ``True`` ("replace the file") while the docstring claimed it "defaults
    from the target's ``ownership``" — so the one seam in this module whose
    whole design is fail-closed defaulted the unsafe way, and the docstring
    would have convinced the next caller that ownership drove it. Every call
    site now states the policy explicitly.
    """
    if syntax == "toml":
        return _merge_toml(
            path,
            name=name,
            entry=entry,
            container_key=container_key,
            replace_on_parse_error=replace_on_parse_error,
        )
    return _merge_json_like(
        path,
        name=name,
        entry=entry,
        container_key=container_key,
        replace_on_parse_error=replace_on_parse_error,
        tolerant=syntax == "jsonc",
    )


def _atomic_merge_mcp_server(
    path: Path,
    *,
    name: str,
    entry: dict[str, object],
    replace_on_parse_error: bool = True,
) -> Path | None:
    """LEGACY JSON-only shim, kept for the pre-#366 unit tests. No production
    caller: ``install_to_client`` routes every target through
    :func:`_merge_into_config`, which selects the serializer from the record's
    ``syntax`` and derives fail-closed from its ``ownership``. It survives only
    because ``tests/unit/test_ai_client_onboarding.py`` — the regression net
    for the registry refactor, deliberately left unmodified so the refactor is
    measured against its old contract — calls it directly. New code must not.
    """
    return _merge_into_config(
        path,
        name=name,
        entry=entry,
        container_key="mcpServers",
        syntax="json",
        replace_on_parse_error=replace_on_parse_error,
    )


# ---------------------------------------------------------------------------
# Reading back what is registered (issue #366: detect drift)
# ---------------------------------------------------------------------------


def registered_url(client_id: ClientId, name: str = SERVER_NAME) -> str | None:
    """The server URL currently written into this client's config, or ``None``.

    Read-only and best-effort: a file that cannot be parsed yields ``None``
    (reported as "not registered"), never an error. The dialog uses this to
    tell *registered* from *stale* — a changed port or a rotated token
    otherwise leaves an entry that looks fine and silently cannot connect.
    """
    try:
        target = get_target(client_id)
    except ValueError:
        return None
    if not target.supports_local_http:
        return None
    path = target.config_path()
    if path is None or not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
        if target.syntax == "toml":
            data: object = tomllib.loads(text)
        else:
            data = json.loads(_strip_jsonc(text) if target.syntax == "jsonc" else text)
    except Exception as exc:  # noqa: BLE001 — TRUST BOUNDARY, see below
        # This is the ONE reader in the module and it runs from the dialog's
        # `__init__`, so a config file OGP cannot read must report
        # "unregistered", never raise: PyQt6 turns an unhandled exception in a
        # slot into `qFatal()`/`abort()`, i.e. the whole application dies.
        #
        # The tuple is deliberately NOT enumerated (invariant 14 — "never
        # enumerate exception families at a trust boundary"). This file belongs
        # to another program and is untrusted input. Enumerating cost two
        # review rounds: a module-owned `_ConfigReadError` was added to the
        # list, and the very next family found was `RecursionError`, which both
        # `json.loads` and `tomllib.loads` raise on a deeply nested document.
        # Every family added is a family still missing; the broad catch is the
        # fix, not the concession.
        logger.debug("Could not read %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    servers = _container_get(data, target.container_key)
    if not isinstance(servers, dict):
        return None
    entry = servers.get(name)
    if not isinstance(entry, dict):
        return None
    url = entry.get("url")
    return url if isinstance(url, str) else None


def is_stale(client_id: ClientId, expected_url: str, name: str = SERVER_NAME) -> bool:
    """Whether this client has a registration that no longer matches the live
    server (different port, or a token that has since been rotated).

    A READ-ONLY registration counts as current, not stale. The dialog moved
    that rule into ``_registration_is_current`` because comparing the full
    write-capable URL alone reported a deliberately read-only client as stale
    forever, with the write credential as the only offered remedy — so the rule
    lives here and the dialog delegates, rather than existing twice.
    """
    current = registered_url(client_id, name)
    if current is None:
        return False
    return current not in (expected_url, read_only_url(expected_url))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def url_with_token(url: str, token: str | None) -> str:
    """Return ``url`` carrying the write token as a ``?token=<token>`` query param.

    We deliver the D2 write token in the URL rather than an ``Authorization``
    header because some MCP clients — notably Claude Code on streamable-HTTP
    (anthropics/claude-code#50464 / #28293) — store a configured header but omit
    it on tool-call POSTs, while the configured URL (query string included) is
    always transmitted since it's the request target. This preserves the same
    threat model (a caller without the token can't write) without depending on
    header transmission. Merges with any existing query string, replaces a stale
    ``token`` param, and returns ``url`` unchanged when ``token`` is falsy —
    which is exactly the read-only case.
    """
    if not token:
        return url
    parts = urllib.parse.urlsplit(url)
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if k != "token"
    ]
    query.append(("token", token))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def read_only_url(url: str) -> str:
    """The connect URL with any ``?token=`` stripped.

    This is what the dialog hands out by default (issue #366). The write URL
    carries the Agent API's write token, and pasting it into an assistant chat
    publishes that credential to whatever stores the transcript — which is
    precisely how a token leaked out of the onboarding dialog in the first
    place. A read-only URL is strictly safer to share and still reaches every
    read tool.
    """
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if k != "token"
    ]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def detect_clients() -> list[ClientInfo]:
    """Detect which known AI clients appear installed, and what is registered.

    Derived entirely from :data:`TARGETS` — adding a client adds a row here
    with no change to this function. ``detected`` is advisory: a client with an
    unusual install layout reads as "not detected" and falls through to the
    generic fallback, which is the correct degradation.
    """
    clients: list[ClientInfo] = []
    for target in TARGETS:
        detected = target.detect_installed()
        if target.cli_name and shutil.which(target.cli_name) is not None:
            install_method: InstallMethod = "cli"
        elif target.supports_local_http and target.merge_supported:
            install_method = "merge"
        else:
            # Either it cannot reach a local server at all (Claude Desktop), or
            # its only route is a merge we refuse to perform (OpenCode without
            # its CLI). Reporting "merge" here would hand the dialog an ENABLED
            # button whose only possible outcome is a refusal — a dead end with
            # a polite message, which is the shape #366 was opened to close.
            install_method = "manual"
        clients.append(
            ClientInfo(
                client_id=target.client_id,
                display_name=target.display_name,
                detected=detected,
                install_method=install_method,
                config_path=target.config_path(),
                registered_url=registered_url(target.client_id) if detected else None,
                syntax=target.syntax,
                supports_local_http=target.supports_local_http,
                requires_restart=target.requires_restart,
            )
        )
    return clients


def _run_client_cli(exe: str, args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _report(path: Path, backup: Path | None) -> str:
    """Human-readable success line, INCLUDING where the backup went.

    A ``.bak`` next to a config file in someone else's home directory is easy
    to miss and impossible to guess. A backup that is made but never *reported*
    is not a safety feature, it is litter — so this string is not optional
    decoration, it is the last step of the backup's contract. The dialog's
    success branch renders it, and a test drives the whole path to prove it.
    """
    if backup is None:
        return str(path)
    return f"{path} (previous contents backed up to {backup})"


def install_to_client(
    client_id: ClientId,
    *,
    url: str,
    name: str = SERVER_NAME,
    token: str | None = None,
) -> InstallResult:
    """Register ``url`` under ``name`` in the given client's config.

    Strategy is chosen from the target's record, not branched on: a CLI when
    the client ships one and it is on PATH, otherwise a direct merge. Every
    target's merge is fail-closed iff its ``ownership`` is ``"foreign"``.

    When ``token`` is given, the client is configured to reach the Agent API's
    write tools (D2) by carrying the token as a ``?token=`` query param on the
    server URL (see :func:`url_with_token`); without it the client can still
    use all read tools.

    Raises ``ValueError`` for an unknown ``client_id`` (a programming error,
    not a runtime condition the caller should handle) — everything else comes
    back as an ``InstallResult`` so a failed install never raises into the UI.
    """
    target = get_target(client_id)

    if not target.supports_local_http:
        return InstallResult(
            client_id=client_id,
            success=False,
            detail=(
                "Claude Desktop can't reach a local server: its connectors are "
                "reached from Anthropic's servers, and it rejects localhost / "
                "http:// URLs. Use Claude Code or Cursor for this local Agent "
                "API instead."
            ),
        )

    path = target.config_path()
    if path is None:
        return InstallResult(
            client_id=client_id,
            success=False,
            detail=f"No config file location is known for {target.display_name}.",
        )

    exe = shutil.which(target.cli_name) if target.cli_name else None
    if exe is None and not target.merge_supported and target.cli_name:
        # Neither route available: no CLI on PATH, and the merge would
        # re-serialise a file we do not own. Say which one is missing, and do
        # not interpolate `cli_name` unguarded (a record without one would
        # render the literal string "None" to the user).
        return InstallResult(
            client_id=client_id,
            success=False,
            detail=(
                f"{target.display_name} can only be registered with its own CLI "
                f"(`{target.cli_name}`), which is not on PATH. OGP will not "
                f"rewrite {path} directly, because that would discard the "
                f"comments in it. Use the manual snippet instead."
            ),
        )

    replace_on_parse_error = target.ownership == "own"
    # The header token route is implemented and tested but enabled for NO
    # target yet (see TokenRoute). Reading it here means flipping
    # `token_route` on a record is a real behaviour change, not a dead field.
    use_header = target.token_route == "header"

    def _merge() -> InstallResult:
        # THE seam. `merge_supported` is checked HERE, not at the call sites
        # that happen to reach the merge: there were three of them, and a
        # registry record with a `cli_name` on PATH but no `cli_argv` slipped
        # past the earlier checks and re-serialised a foreign file. A guard
        # checked on some paths is not a guard — the check belongs on the
        # operation it protects, so a fourth path cannot bypass it either.
        if not target.merge_supported:
            return InstallResult(
                client_id=client_id,
                success=False,
                detail=(
                    f"OGP will not rewrite {path} directly, because that would "
                    f"discard the comments in a file it does not own. Use the "
                    f"manual snippet, or {target.display_name}'s own CLI."
                ),
            )
        try:
            backup = _merge_into_config(
                path,
                name=name,
                entry=target.entry(url, token, use_header),
                container_key=target.container_key,
                syntax=target.syntax,
                replace_on_parse_error=replace_on_parse_error,
            )
        except Exception as exc:  # noqa: BLE001 — "never raises into the UI"
            # TRUST BOUNDARY again: the file is another program's, and the
            # parser family is deliberately not enumerated (a deeply nested
            # document alone yields RecursionError). This function's contract
            # is that a failed install comes back as an InstallResult.
            return InstallResult(client_id=client_id, success=False, detail=str(exc))
        return InstallResult(
            client_id=client_id, success=True, detail=_report(path, backup), backup_path=backup
        )

    if target.cli_name is None or target.cli_argv is None:
        return _merge()

    if exe is None:
        # No CLI on PATH — the direct merge is what makes one-click work
        # without a terminal (issue #253). This is a supported route, not a
        # degraded one.
        return _merge()

    add_args = target.cli_argv(name, url, token, use_header)

    # Every module docstring/ADR-035 promise is "a failed install never raises
    # into the UI" — the CLI can hang (first-run login prompt, network stall)
    # or simply not exist despite shutil.which finding a stale PATH entry, so
    # every subprocess call here is inside this one try/except.
    #
    # The self-heal is deliberately OUTSIDE it: it calls `_merge()`, and a
    # failure there is a merge failure. Running it inside this try would
    # misreport a refused merge as a broken CLI.
    self_heal = False
    try:
        result = _run_client_cli(exe, add_args)
        if result.returncode == 0:
            return InstallResult(
                client_id=client_id, success=True, detail=result.stdout.strip()
            )

        stderr = result.stderr.strip()
        if "already exists" in stderr.lower() or "already registered" in stderr.lower():
            if target.cli_remove_argv is None:
                self_heal = True
            else:
                # Re-registering under the same name is an update, not a
                # clobber — remove-then-add so a changed port/token takes
                # effect. Other servers in the file are untouched either way.
                removed = _run_client_cli(exe, target.cli_remove_argv(name))
                if removed.returncode == 0:
                    retry = _run_client_cli(exe, add_args)
                    if retry.returncode == 0:
                        return InstallResult(
                            client_id=client_id, success=True, detail=retry.stdout.strip()
                        )
                    stderr = (
                        f"Removed the existing entry but could not re-add it: "
                        f"{retry.stderr.strip()}"
                    )
                else:
                    stderr = (
                        f"Could not remove the existing entry to update it: "
                        f"{removed.stderr.strip()}"
                    )
    except Exception as exc:  # noqa: BLE001 — "never raises into the UI"
        # The CLI can hang, vanish, or produce a family nobody enumerated;
        # this function's contract is that a failed install comes back as an
        # InstallResult rather than an exception.
        return InstallResult(client_id=client_id, success=False, detail=str(exc))

    if self_heal:
        # No documented remove subcommand (OpenCode). The merge would be the
        # natural self-heal — but it re-serialises a file OGP does not own, so
        # defer to `_merge()`, which owns that decision at the seam. If the
        # merge is refused it returns the honest message, which beats silently
        # doing the destructive thing.
        return _merge()

    return InstallResult(
        client_id=client_id, success=False, detail=stderr or f"{target.cli_name} mcp add failed."
    )


def snippet_for_client(
    client_id: ClientId, *, url: str, name: str = SERVER_NAME, token: str | None = None
) -> str:
    """Copy-paste fallback text for a client — raw payload only (JSON/command),
    no descriptive prose; the dialog supplies its own translated "where to put
    this" note per client.

    When ``token`` is given the snippet carries it in the server URL as a
    ``?token=`` query param (see :func:`url_with_token`) so a hand-registered
    client can reach the write tools too.
    """
    target = get_target(client_id)
    if not target.supports_local_http:
        return url_with_token(url, token)
    # Honour the target's route, so the manual snippet and the one-click install
    # can never disagree about where the token lives.
    use_header = target.token_route == "header"
    if target.syntax == "toml":
        return _toml_render_table(
            target.container_key, name, target.entry(url, token, use_header)
        )
    return json.dumps(
        _nested_dict(target.container_key, name, target.entry(url, token, use_header)),
        indent=2,
    )


def generic_snippets(*, url: str, name: str = SERVER_NAME) -> dict[str, str]:
    """Vendor-agnostic onboarding text for a client OGP has never heard of.

    Always available, detected client or not — this is what makes the registry
    an optimisation rather than a gate. It degrades gracefully rather than
    universally: the JSON block matches the ``mcpServers`` family, and a client
    using a different container key (Codex, OpenCode) needs a registry entry or
    its own documented snippet.

    Every value here is **read-only**. A live write credential does not belong
    on a dict whose whole purpose is to be pasted somewhere public, and the
    dialog has a separate, explicitly-worded action for the write URL.
    """
    return {
        "json": json.dumps(
            {"mcpServers": {name: _claude_code_entry(read_only_url(url), None)}}, indent=2
        ),
        "cli": f"<client> mcp add --transport http {name} {read_only_url(url)}",
        "url": read_only_url(url),
    }
