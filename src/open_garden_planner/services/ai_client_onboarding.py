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
  CLI when found on PATH. Preferred over hand-editing ``~/.claude.json``,
  which nests per-project scopes and isn't meant to be edited directly; the
  CLI is the officially documented registration path and validates its own
  writes.
* **Claude Desktop** — detection only. Its local config
  (``claude_desktop_config.json``) only documents *stdio* servers
  (``command``/``args``); a plain local HTTP endpoint like ours is registered
  through the app's own Settings -> Connectors -> "Add custom connector" flow,
  not a static config edit. Writing to that file with a guessed schema would
  risk corrupting it for no guaranteed benefit, so this target is always
  "manual" here.

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
    return Path.home() / ".claude.json"


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


def _atomic_merge_mcp_server(path: Path, *, name: str, entry: dict[str, object]) -> Path | None:
    """Read-modify-write ``path``'s ``mcpServers.<name>`` entry.

    Preserves every other key in the file (other servers, unrelated config).
    Backs up the file's current contents to ``<name>.bak`` first if it
    existed (returns that path; ``None`` if there was nothing to back up) —
    note a second call overwrites ``.bak`` with the state from just before
    *that* call, not the original file from before OGP ever touched it; only
    the most recent pre-write snapshot survives. Writes via a same-directory
    temp file + ``os.replace`` so a crash mid-write can never leave a
    truncated/partial config behind.

    A malformed or non-object existing file is treated as untrusted input
    (this reads a config OGP doesn't own) — logged and replaced rather than
    raised, mirroring ``smart_symbol_library``'s user-file trust boundary.
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
            if isinstance(loaded, dict):
                data = loaded
            else:
                logger.warning("%s does not contain a JSON object; replacing it", path)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not parse existing %s (%s); replacing it", path, exc)

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
            install_method="cli" if claude_cli is not None else "manual",
            config_path=claude_code_config if claude_code_config.exists() else None,
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


def _auth_header_value(token: str) -> str:
    """The ``Authorization`` header value a client sends to reach write tools."""
    return f"Bearer {token}"


def install_to_client(
    client_id: ClientId,
    *,
    url: str,
    name: str = SERVER_NAME,
    token: str | None = None,
) -> InstallResult:
    """Register ``url`` under ``name`` in the given client's config.

    When ``token`` is given, the client is configured to send it as an
    ``Authorization: Bearer <token>`` header so the Agent API's write tools
    (D2) are reachable; without it the client can still use all read tools.

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
                "Claude Desktop registers local MCP servers through its own "
                'Settings > Connectors > "Add custom connector" dialog, not a '
                "config file OGP can safely edit."
            ),
        )
    raise ValueError(f"Unknown client_id: {client_id}")


def _cursor_entry(url: str, token: str | None) -> dict[str, object]:
    """Cursor's ``mcpServers.<name>`` entry — with the bearer header if a token
    is given (Cursor's documented remote-server schema supports ``headers``)."""
    entry: dict[str, object] = {"url": url}
    if token:
        entry["headers"] = {"Authorization": _auth_header_value(token)}
    return entry


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
    """Args for ``claude mcp add``, with ``--header`` when a token is set.

    ``--header`` is a *variadic* option in the Claude CLI — it consumes every
    following token — so it MUST come AFTER the positional ``name`` and ``url``,
    or it swallows them and the CLI fails with "missing required argument
    'name'". This matches the official syntax:
    ``claude mcp add --transport http <name> <url> --header "Authorization: ..."``.
    """
    header: tuple[str, ...] = (
        ("--header", f"Authorization: {_auth_header_value(token)}") if token else ()
    )
    return ("add", "--transport", "http", "--scope", "user", name, url, *header)


def _install_claude_code(*, url: str, name: str, token: str | None = None) -> InstallResult:
    claude = shutil.which("claude")
    if claude is None:
        return InstallResult(
            client_id="claude_code",
            success=False,
            detail="claude CLI not found on PATH.",
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

    When ``token`` is given the snippet includes the ``Authorization: Bearer``
    header so a hand-registered client can reach the write tools too.
    """
    if client_id == "cursor":
        return json.dumps(
            {"mcpServers": {name: _cursor_entry(url, token)}}, indent=2
        )
    if client_id == "claude_code":
        # --header is variadic and must come AFTER name+url (see _claude_code_add_args).
        header = f' --header "Authorization: {_auth_header_value(token)}"' if token else ""
        return f"claude mcp add --transport http --scope user {name} {url}{header}"
    if client_id == "claude_desktop":
        return url
    raise ValueError(f"Unknown client_id: {client_id}")
