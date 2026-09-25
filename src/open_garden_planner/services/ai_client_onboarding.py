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
  / ``mcp`` (OpenCode). Three names for the same semantic model.
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
  is on PATH; otherwise a **JSONC** merge into ``~/.config/opencode/opencode.jsonc``
  (container ``mcp``, entry ``{type: "remote", url}``, ``oauth: false``). That
  config is a *commented* JSON variant, which plain ``json.load()`` rejects — see
  :func:`_strip_jsonc`.
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

InstallMethod = Literal["json_merge", "cli", "manual"]
Syntax = Literal["json", "jsonc", "toml"]
Ownership = Literal["own", "foreign"]

#: Fixed, English server identifier written into every client's config.
#: MCP server names are an API contract, not UI copy (mirrors ADR-033's
#: "tool/resource descriptions are English" precedent) — never translated.
SERVER_NAME = "open-garden-planner"

#: How a target carries the write token when it is configured. ``"url"`` puts
#: it in a ``?token=`` query param; ``"header"`` sends it as an HTTP header.
#:
#: Default is ``"url"`` for every target, including the two whose CLIs accept
#: ``--header``: a header is the better home for a secret, but *documented*
#: support is not evidence that a client transmits it on streamable-HTTP
#: **tool-call** requests — the exact failure Claude Code has open upstream
#: (anthropics/claude-code#50464 / #28293). Shipping the header as the default
#: before that is measured would make write tools silently unreachable. The
#: header form is implemented and unit-tested; flipping a target's default is a
#: one-field data change once the live dogfood run confirms transmission.
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
    #: Builds the server entry. ``(url, token) -> dict``. ``token`` is ``None``
    #: for a read-only registration.
    entry: Callable[[str, str | None], dict[str, object]]
    #: CLI executable name, when the client ships a documented ``mcp add``.
    cli_name: str | None = None
    #: Argv (after the executable) for an ``mcp add``. Omitted means the direct
    #: merge is the only path.
    cli_argv: Callable[[str, str | None], tuple[str, ...]] | None = None
    #: Argv for a remove, used to self-heal an existing entry. Codex and
    #: OpenCode have no ``mcp remove``, so they fall back to the merge.
    cli_remove_argv: Callable[[str], tuple[str, ...]] | None = None
    #: ``"own"`` = a file OGP effectively owns (a parse error may be recovered
    #: by replacing); ``"foreign"`` = a file holding state OGP does not own
    #: (OAuth / projects / trust / the user's own comments), which must be left
    #: untouched if it cannot be parsed.
    ownership: Ownership = "own"
    #: ``False`` for a client that cannot reach a local HTTP server at all —
    #: detection only, never written (Claude Desktop, issue #253).
    supports_local_http: bool = True
    #: Where the token rides when this target is registered write-capable.
    token_route: TokenRoute = "url"
    #: The client reads its user-scope config only at session start, so the
    #: dialog must tell the user to restart rather than leave them wondering.
    requires_restart: bool = False


# --- per-client entry builders ------------------------------------------------


def _flat_entry(url: str, token: str | None) -> dict[str, object]:
    """The common ``{"url": ...}`` shape (Cursor, Gemini, Codex)."""
    return {"url": url_with_token(url, token)}


def _claude_code_entry(url: str, token: str | None) -> dict[str, object]:
    """Claude Code / VS Code extension entry for ``~/.claude.json``.
    ``type: "http"`` is REQUIRED — without it the entry is not recognised as an
    HTTP server and is silently ignored (a ``url``-only entry doesn't match the
    stdio-*command* shape either, so it simply never connects)."""
    return {"type": "http", "url": url_with_token(url, token)}


def _opencode_entry(url: str, token: str | None) -> dict[str, object]:
    """OpenCode's ``mcp.<name>`` entry.

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
        "url": url_with_token(url, token),
        "oauth": False,
        "enabled": True,
    }
    return entry


# --- per-client CLI argv builders ---------------------------------------------


def _claude_code_add_args(name: str, url: str, token: str | None) -> tuple[str, ...]:
    """Args for ``claude mcp add``.

    Claude Code stores a configured ``--header`` but does not send it on
    tool-call requests for streamable-HTTP servers (anthropics/claude-code
    #50464 / #28293), so a header would leave write tools unreachable. The URL
    (query string included) is always transmitted, so the token goes there via
    ``url_with_token`` — no ``--header``, which also removes the variadic-
    ordering footgun the old header form carried.
    """
    return (
        "add",
        "--transport",
        "http",
        "--scope",
        "user",
        name,
        url_with_token(url, token),
    )


def _claude_code_remove_args(name: str) -> tuple[str, ...]:
    return ("remove", name, "--scope", "user")


def _opencode_add_args(name: str, url: str, token: str | None) -> tuple[str, ...]:
    """Args for ``opencode mcp add``.

    ``--global`` is LOAD-BEARING: without it the CLI writes the *project*
    config (``opencode.json`` in the current directory), so a user who ran
    "Add to OpenCode" from a random working directory would silently get a
    config file dropped into their project.
    """
    return ("mcp", "add", name, "--url", url_with_token(url, token), "--global")


def _codex_add_args(name: str, url: str, token: str | None) -> tuple[str, ...]:
    """Args for ``codex mcp add`` (streamable HTTP)."""
    return ("mcp", "add", name, "--url", url_with_token(url, token))


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
        cli_argv=lambda name, url, token: ("mcp",) + _claude_code_add_args(name, url, token),
        cli_remove_argv=_claude_code_remove_args,
        ownership="foreign",
        requires_restart=True,
    ),
    ClientTarget(
        client_id="opencode",
        display_name="OpenCode",
        # Detected by its own config file: the CLI is optional, and the
        # no-CLI merge path is a real supported route.
        detect_installed=lambda: _opencode_config_path().exists()
        or shutil.which("opencode") is not None,
        config_path=_opencode_config_path,
        container_key="mcp",
        syntax="jsonc",
        entry=_opencode_entry,
        cli_name="opencode",
        cli_argv=_opencode_add_args,
        ownership="foreign",
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
        ownership="own",
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


def _strip_jsonc(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments and trailing commas from a JSONC
    document so ``json.loads`` accepts it.

    Comment-stripped by character scan, NOT by regex: a ``#`` or ``//`` inside
    a string literal is data, and a regex cannot tell. Trailing commas are
    removed in the same pass (a comma immediately before a closing ``}``/``]``
    is legal in JSONC and illegal in JSON).
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
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1

    stripped = "".join(out)
    # Drop trailing commas: a "," whose next non-space character closes an
    # object or array. Done on the comment-free text so a comma inside a
    # string is never touched.
    result: list[str] = []
    j = 0
    m = len(stripped)
    in_str = False
    while j < m:
        ch = stripped[j]
        if in_str:
            result.append(ch)
            if ch == "\\" and j + 1 < m:
                result.append(stripped[j + 1])
                j += 2
                continue
            if ch == '"':
                in_str = False
            j += 1
            continue
        if ch == '"':
            in_str = True
            result.append(ch)
            j += 1
            continue
        if ch == ",":
            k = j + 1
            while k < m and stripped[k] in " \t\r\n":
                k += 1
            if k < m and stripped[k] in "}]":
                j += 1  # skip the comma, keep the closer
                continue
        result.append(ch)
        j += 1
    return "".join(result)


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

    backup_path: Path | None = None
    data: dict[str, object] = {}
    if path.exists():
        backup_path = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup_path)
        try:
            text = path.read_text(encoding="utf-8")
            loaded = json.loads(_strip_jsonc(text) if tolerant else text)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
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

    servers = data.get(container_key)
    if not isinstance(servers, dict):
        servers = {}
    servers[name] = entry
    data[container_key] = servers

    _atomic_write(path, json.dumps(data, indent=2) + "\n")
    return backup_path


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

    backup_path: Path | None = None
    original = ""
    if path.exists():
        backup_path = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup_path)
        try:
            original = path.read_text(encoding="utf-8")
            tomllib.loads(original)
        except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
            if not replace_on_parse_error:
                raise _ConfigMergeError(
                    f"Could not read existing {path} ({exc}); left untouched."
                ) from exc
            logger.warning("Could not parse existing %s (%s); replacing it", path, exc)
            original = ""

    header = f"[{container_key}.{name}]"
    lines = original.splitlines(keepends=True)
    span = _toml_table_span(lines, header)
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

    _atomic_write(path, new_text)
    return backup_path


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
    replace_on_parse_error: bool | None = None,
) -> Path | None:
    """Read-modify-write a client's config, routing on ``syntax``.

    Preserves every other key in the file (other servers, unrelated config).
    Backs up the file's current contents to ``<name>.bak`` first if it existed
    (returns that path; ``None`` if there was nothing to back up) — note a
    second call overwrites ``.bak`` with the state from just before *that*
    call, not the original file from before OGP ever touched it.

    ``replace_on_parse_error`` defaults from the target's ``ownership``, so the
    fail-closed decision travels with the registry record rather than being
    re-decided at each call site.
    """
    if replace_on_parse_error is None:
        replace_on_parse_error = True
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
    """Backwards-compatible JSON-only wrapper (kept for existing callers/tests).

    The real entry point is :func:`_merge_into_config`, which routes on the
    target's ``syntax`` and derives fail-closed from its ``ownership``.
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
        text = path.read_text(encoding="utf-8")
        if target.syntax == "toml":
            data: object = tomllib.loads(text)
        else:
            data = json.loads(_strip_jsonc(text) if target.syntax == "jsonc" else text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    servers = data.get(target.container_key)
    if not isinstance(servers, dict):
        return None
    entry = servers.get(name)
    if not isinstance(entry, dict):
        return None
    url = entry.get("url")
    return url if isinstance(url, str) else None


def is_stale(client_id: ClientId, expected_url: str, name: str = SERVER_NAME) -> bool:
    """Whether this client has a registration that no longer matches the live
    server URL (different port, or a token that has since been rotated)."""
    current = registered_url(client_id, name)
    return current is not None and current != expected_url


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
        elif target.supports_local_http:
            install_method = "json_merge"
        else:
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

    replace_on_parse_error = target.ownership == "own"

    def _merge() -> InstallResult:
        try:
            backup = _merge_into_config(
                path,
                name=name,
                entry=target.entry(url, token),
                container_key=target.container_key,
                syntax=target.syntax,
                replace_on_parse_error=replace_on_parse_error,
            )
        except (OSError, _ConfigMergeError) as exc:
            return InstallResult(client_id=client_id, success=False, detail=str(exc))
        return InstallResult(
            client_id=client_id, success=True, detail=str(path), backup_path=backup
        )

    if target.cli_name is None or target.cli_argv is None:
        return _merge()

    exe = shutil.which(target.cli_name)
    if exe is None:
        # No CLI on PATH — the direct merge is what makes one-click work
        # without a terminal (issue #253). This is a supported route, not a
        # degraded one.
        return _merge()

    add_args = target.cli_argv(name, url, token)

    # Every module docstring/ADR-035 promise is "a failed install never raises
    # into the UI" — the CLI can hang (first-run login prompt, network stall)
    # or simply not exist despite shutil.which finding a stale PATH entry, so
    # every subprocess call here is inside this one try/except.
    try:
        result = _run_client_cli(exe, add_args)
        if result.returncode == 0:
            return InstallResult(
                client_id=client_id, success=True, detail=result.stdout.strip()
            )

        stderr = result.stderr.strip()
        if "already exists" in stderr.lower() or "already registered" in stderr.lower():
            if target.cli_remove_argv is not None:
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
            else:
                # No documented remove subcommand (OpenCode): the merge
                # replaces the entry wholesale, so it IS the update path.
                return _merge()
    except (subprocess.SubprocessError, OSError) as exc:
        return InstallResult(client_id=client_id, success=False, detail=str(exc))

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
    if target.syntax == "toml":
        return _toml_render_table(target.container_key, name, target.entry(url, token))
    return json.dumps(
        {target.container_key: {name: target.entry(url, token)}}, indent=2
    )


def generic_snippets(*, url: str, name: str = SERVER_NAME, token: str | None = None) -> dict[str, str]:
    """Vendor-agnostic onboarding text for a client OGP has never heard of.

    Always available, detected client or not — this is what makes the registry
    an optimisation rather than a gate. It degrades gracefully rather than
    universally: the JSON block matches the ``mcpServers`` family, and a client
    using a different container key (Codex, OpenCode) needs a registry entry or
    its own documented snippet. The default URLs are **read-only**; a
    write-capable URL is only ever handed out on an explicit request.
    """
    return {
        "json": json.dumps(
            {"mcpServers": {name: _claude_code_entry(read_only_url(url), None)}}, indent=2
        ),
        "cli": f"<client> mcp add --transport http {name} {read_only_url(url)}",
        "url": read_only_url(url),
        "write_url": url_with_token(url, token),
    }
