"""AI client onboarding (US-D1.6): detect installed MCP clients and register
the Agent API server's connect URL into their config, or hand back a
copy-paste snippet when automatic registration isn't safe or possible.

Qt-free (unit-testable without a GUI); the dialog is a thin shell over this
module. Three targets, three different strategies — chosen per what each
client's own docs actually support, not a one-size-fits-all writer:

* **Cursor** — direct JSON merge into ``~/.cursor/mcp.json``. Documented flat
  schema (``{"mcpServers": {"<name>": {"url": "..."}}}``), safe to read-modify
  -write.
* **Claude Code** — ``claude mcp add --transport http --scope user`` via the
  CLI when it's on PATH (it validates its own writes and self-heals an existing
  entry); otherwise a direct atomic merge into the TOP-LEVEL ``mcpServers`` of
  ``~/.claude.json`` (the same user-scope location the CLI writes, read by both
  the CLI and the VS Code extension). The CLI is frequently NOT on PATH (e.g.
  the native ``~/.local/bin`` installer dir, or an extension-only install), so
  the direct-merge fallback is what makes one-click work without a terminal.
  The merge fails CLOSED on an unreadable ``~/.claude.json`` (it also holds
  OAuth / projects / trust) rather than replacing it.
* **Claude Desktop** — detection only, and *cannot* connect to this server:
  Anthropic's connector UI reaches servers from its own cloud and rejects
  ``localhost`` / ``http://`` URLs, and ``claude_desktop_config.json`` is
  stdio-only (writing a ``url`` field makes Claude Desktop silently delete the
  whole ``mcpServers`` block). So OGP writes nothing here and the dialog
  redirects the user to Claude Code or Cursor.

Every write path preserves unknown keys/other servers, backs up the original
file before touching it, and writes atomically (temp file + ``os.replace``) —
the first such pattern in this codebase (see ADR-035): every prior JSON writer
here does a bare ``open(path, "w")`` because it only ever writes *our own*
file. This module writes into files owned by *other* applications, so the
bar is higher.
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
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

ClientId = Literal["cursor", "claude_code", "claude_desktop"]
InstallMethod = Literal["json_merge", "cli", "manual"]

#: Fixed, English server identifier written into every client's config.
#: MCP server names are an API contract, not UI copy (mirrors ADR-033's
#: "tool/resource descriptions are English" precedent) — never translated.
SERVER_NAME = "open-garden-planner"


@dataclass(frozen=True)
class ClientInfo:
    """One onboarding target's detection state."""

    client_id: ClientId
    display_name: str
    detected: bool
    install_method: InstallMethod
    config_path: Path | None


@dataclass(frozen=True)
class InstallResult:
    """Outcome of an install attempt.

    ``detail`` is a short, English, technical description (raw CLI
    stderr/exception text) meant to be embedded inside a translated sentence
    by the caller (mirrors ``preferences_dialog._test_api``'s
    ``tr("Error testing {api}: {error}").format(error=str(e))`` pattern) —
    it is not itself a complete user-facing message.
    """

    client_id: ClientId
    success: bool
    detail: str
    backup_path: Path | None = None


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _cursor_config_path() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def _cursor_dir_exists() -> bool:
    return (Path.home() / ".cursor").is_dir()


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


# ---------------------------------------------------------------------------
# Atomic read-modify-write JSON merge
# ---------------------------------------------------------------------------


class _ConfigMergeError(Exception):
    """A config file existed but could not be safely merged (unparseable /
    non-object). Raised only when ``replace_on_parse_error=False`` so the caller
    reports failure and leaves a file OGP doesn't own (``~/.claude.json``)
    untouched instead of replacing it."""


def _atomic_merge_mcp_server(
    path: Path,
    *,
    name: str,
    entry: dict[str, object],
    replace_on_parse_error: bool = True,
) -> Path | None:
    """Read-modify-write ``path``'s ``mcpServers.<name>`` entry.

    Preserves every other key in the file (other servers, unrelated config).
    Backs up the file's current contents to ``<name>.bak`` first if it
    existed (returns that path; ``None`` if there was nothing to back up) —
    note a second call overwrites ``.bak`` with the state from just before
    *that* call, not the original file from before OGP ever touched it; only
    the most recent pre-write snapshot survives. Writes via a same-directory
    temp file + ``os.replace`` so a crash mid-write can never leave a
    truncated/partial config behind.

    A malformed or non-object existing file is, by default
    (``replace_on_parse_error=True``), treated as untrusted input and replaced
    (mirrors ``smart_symbol_library``'s user-file trust boundary) — fine for a
    small file OGP effectively owns (Cursor's ``mcp.json``). Pass
    ``replace_on_parse_error=False`` for a file OGP must NOT clobber
    (``~/.claude.json`` also holds OAuth / projects / trust state): an
    unreadable or non-object file then raises ``_ConfigMergeError`` and is left
    untouched (the ``.bak`` copy is still made first).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    backup_path: Path | None = None
    data: dict[str, object] = {}
    if path.exists():
        backup_path = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup_path)
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
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

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[name] = entry
    data["mcpServers"] = servers

    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".ogp-onboarding-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_name)
        raise
    return backup_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_clients() -> list[ClientInfo]:
    """Detect which known AI clients appear to be installed on this machine."""
    clients: list[ClientInfo] = []

    clients.append(
        ClientInfo(
            client_id="cursor",
            display_name="Cursor",
            detected=_cursor_dir_exists(),
            install_method="json_merge",
            config_path=_cursor_config_path(),
        )
    )

    claude_cli = shutil.which("claude")
    claude_code_config = _claude_code_user_config_path()
    clients.append(
        ClientInfo(
            client_id="claude_code",
            display_name="Claude Code",
            detected=claude_cli is not None or claude_code_config.exists(),
            # Even without the `claude` CLI on PATH, we can register by a direct
            # atomic merge into ~/.claude.json (the user-scope location shared by
            # the CLI AND the VS Code extension), so a CLI-less machine still
            # gets a working one-click instead of a dead terminal command.
            install_method="cli" if claude_cli is not None else "json_merge",
            config_path=claude_code_config,
        )
    )

    desktop_dir = _claude_desktop_config_dir()
    clients.append(
        ClientInfo(
            client_id="claude_desktop",
            display_name="Claude Desktop",
            detected=desktop_dir is not None and desktop_dir.is_dir(),
            install_method="manual",
            config_path=_claude_desktop_config_path(),
        )
    )

    return clients


def url_with_token(url: str, token: str | None) -> str:
    """Return ``url`` carrying the write token as a ``?token=<token>`` query param.

    We deliver the D2 write token in the URL rather than an ``Authorization``
    header because some MCP clients — notably Claude Code on streamable-HTTP
    (anthropics/claude-code#50464 / #28293) — store a configured header but omit
    it on tool-call POSTs, while the configured URL (query string included) is
    always transmitted since it's the request target. This preserves the same
    threat model (a caller without the token can't write) without depending on
    header transmission. Merges with any existing query string, replaces a stale
    ``token`` param, and returns ``url`` unchanged when ``token`` is falsy.
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


def install_to_client(
    client_id: ClientId,
    *,
    url: str,
    name: str = SERVER_NAME,
    token: str | None = None,
) -> InstallResult:
    """Register ``url`` under ``name`` in the given client's config.

    When ``token`` is given, the client is configured to reach the Agent API's
    write tools (D2) by carrying the token as a ``?token=<token>`` query param
    on the server URL (see ``url_with_token``); without it the client can still
    use all read tools.

    Raises ``ValueError`` for an unknown ``client_id`` (a programming error,
    not a runtime condition the caller should handle) — everything else comes
    back as an ``InstallResult`` so a failed install never raises into the UI.
    """
    if client_id == "cursor":
        return _install_cursor(url=url, name=name, token=token)
    if client_id == "claude_code":
        return _install_claude_code(url=url, name=name, token=token)
    if client_id == "claude_desktop":
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
    raise ValueError(f"Unknown client_id: {client_id}")


def _cursor_entry(url: str, token: str | None) -> dict[str, object]:
    """Cursor's ``mcpServers.<name>`` entry — the token rides the URL as a
    ``?token=`` query param (see ``url_with_token``), the delivery route that
    works uniformly across clients."""
    return {"url": url_with_token(url, token)}


def _claude_code_entry(url: str, token: str | None) -> dict[str, object]:
    """Claude Code / VS Code extension ``mcpServers.<name>`` entry for
    ``~/.claude.json``. ``type: "http"`` is REQUIRED — an entry with only a
    ``url`` is parsed as a stdio *command* server and ignored (worse, could be
    run as a command). The token rides the URL (``url_with_token``); no
    ``headers`` (Claude Code omits configured headers on tool calls)."""
    return {"type": "http", "url": url_with_token(url, token)}


def _install_cursor(*, url: str, name: str, token: str | None = None) -> InstallResult:
    path = _cursor_config_path()
    try:
        backup = _atomic_merge_mcp_server(
            path, name=name, entry=_cursor_entry(url, token)
        )
    except OSError as exc:
        return InstallResult(client_id="cursor", success=False, detail=str(exc))
    return InstallResult(client_id="cursor", success=True, detail=str(path), backup_path=backup)


def _run_claude_mcp(claude: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [claude, "mcp", *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _claude_code_add_args(name: str, url: str, token: str | None) -> tuple[str, ...]:
    """Args for ``claude mcp add``; the token rides the URL as ``?token=``.

    Claude Code stores a configured ``--header`` but does not send it on
    tool-call requests for streamable-HTTP servers (anthropics/claude-code
    #50464 / #28293), so a header would leave write tools unreachable. The URL
    (query string included) is always transmitted, so the token goes there via
    ``url_with_token`` — no ``--header``, which also removes the variadic-
    ordering footgun the old header form carried.
    """
    return ("add", "--transport", "http", "--scope", "user", name, url_with_token(url, token))


def _install_claude_code(*, url: str, name: str, token: str | None = None) -> InstallResult:
    claude = shutil.which("claude")
    if claude is None:
        # No `claude` on PATH — register by a direct atomic merge into the
        # top-level `mcpServers` of ~/.claude.json (the exact user-scope entry
        # `claude mcp add --scope user` writes, read by both the CLI and the VS
        # Code extension). Fail CLOSED on a parse error: this file also holds
        # OAuth / projects / trust and must never be replaced if unreadable.
        path = _claude_code_user_config_path()
        try:
            backup = _atomic_merge_mcp_server(
                path,
                name=name,
                entry=_claude_code_entry(url, token),
                replace_on_parse_error=False,
            )
        except (OSError, _ConfigMergeError) as exc:
            return InstallResult(client_id="claude_code", success=False, detail=str(exc))
        return InstallResult(
            client_id="claude_code", success=True, detail=str(path), backup_path=backup
        )

    add_args = _claude_code_add_args(name, url, token)

    # Every module docstring/ADR-035 promise is "a failed install never raises
    # into the UI" — the CLI can hang (first-run login prompt, network stall)
    # or simply not exist despite shutil.which finding a stale PATH entry, so
    # every subprocess call in this function is inside this one try/except.
    try:
        result = _run_claude_mcp(claude, *add_args)
        if result.returncode == 0:
            return InstallResult(client_id="claude_code", success=True, detail=result.stdout.strip())

        stderr = result.stderr.strip()
        if "already exists" in stderr.lower():
            # Re-registering under the same name is an update, not a clobber —
            # remove-then-add so a changed port/token takes effect. Other servers
            # in ~/.claude.json are untouched either way.
            removed = _run_claude_mcp(claude, "remove", name, "--scope", "user")
            if removed.returncode == 0:
                retry = _run_claude_mcp(claude, *add_args)
                if retry.returncode == 0:
                    return InstallResult(client_id="claude_code", success=True, detail=retry.stdout.strip())
                stderr = (
                    f"Removed the existing entry but could not re-add it: "
                    f"{retry.stderr.strip()}"
                )
            else:
                stderr = f"Could not remove the existing entry to update it: {removed.stderr.strip()}"
    except (subprocess.SubprocessError, OSError) as exc:
        return InstallResult(client_id="claude_code", success=False, detail=str(exc))

    return InstallResult(client_id="claude_code", success=False, detail=stderr or "claude mcp add failed.")


def snippet_for_client(
    client_id: ClientId, *, url: str, name: str = SERVER_NAME, token: str | None = None
) -> str:
    """Copy-paste fallback text for a client — raw payload only (JSON/command),
    no descriptive prose; the dialog supplies its own translated "where to put
    this" note per client.

    When ``token`` is given the snippet carries it in the server URL as a
    ``?token=`` query param (see ``url_with_token``) so a hand-registered
    client can reach the write tools too.
    """
    if client_id == "cursor":
        return json.dumps(
            {"mcpServers": {name: _cursor_entry(url, token)}}, indent=2
        )
    if client_id == "claude_code":
        return json.dumps(
            {"mcpServers": {name: _claude_code_entry(url, token)}}, indent=2
        )
    if client_id == "claude_desktop":
        return url_with_token(url, token)
    raise ValueError(f"Unknown client_id: {client_id}")
