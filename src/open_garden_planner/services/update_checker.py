"""Update checker service for US-8.3.

Checks GitHub Releases API for newer versions in a background thread.
Only active when running from the installed .exe (sys.frozen).
Uses only stdlib (urllib) — no extra dependencies.
"""

import json
import logging
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

_RELEASES_URL = "https://api.github.com/repos/cofade/open-garden-planner/releases/latest"
_REQUEST_TIMEOUT = 10


@dataclass
class ReleaseInfo:
    """Parsed information from a GitHub release."""

    tag_name: str
    body: str
    download_url: str | None
    html_url: str


def compare_versions(current: str, latest: str) -> bool:
    """Return True if *latest* is strictly newer than *current*.

    Args:
        current: Current version string (e.g. ``"1.5.1"`` or ``"v1.5.1"``).
        latest:  Latest version string from GitHub (e.g. ``"v1.6.0"``).

    Returns:
        True if an update is available.
    """

    def _parse(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.lstrip("v").split("."))

    try:
        return _parse(latest) > _parse(current)
    except (ValueError, AttributeError):
        return False


def parse_release_info(data: dict[str, Any]) -> ReleaseInfo:
    """Parse the JSON payload from the GitHub Releases API.

    Args:
        data: Parsed JSON dict from ``GET /repos/:owner/:repo/releases/latest``.

    Returns:
        :class:`ReleaseInfo` with tag name, release notes snippet (≤ 300 chars),
        and the download URL for the ``*-Setup.exe`` asset (or ``None``).
    """
    tag_name = str(data.get("tag_name", ""))
    body_raw = data.get("body") or ""
    body = str(body_raw)[:300]
    html_url = str(data.get("html_url", ""))

    download_url: str | None = None
    for asset in data.get("assets", []):
        name = str(asset.get("name", ""))
        if name.endswith("-Setup.exe"):
            download_url = str(asset.get("browser_download_url", "")) or None
            break

    return ReleaseInfo(tag_name=tag_name, body=body, download_url=download_url, html_url=html_url)


def get_current_version() -> str:
    """Return the running application version string.

    When running from a PyInstaller bundle (``sys.frozen``), reads from the
    ``_version`` module written at build time.  Otherwise falls back to the
    package ``__version__``.
    """
    if getattr(sys, "frozen", False):
        try:
            from open_garden_planner import _version  # type: ignore[import-not-found]

            return str(_version.__version__)
        except ImportError:
            pass
    from open_garden_planner import __version__

    return __version__


class UpdateChecker(QThread):
    """Background QThread that polls the GitHub Releases API once at startup.

    Emits :attr:`update_available` when a newer release is found.
    Silently swallows all network / parse errors so it never blocks the UI.
    """

    #: Emitted with (tag_name, release_body_snippet, download_url, html_url).
    #: ``download_url`` may be an empty string if no Setup.exe asset was found.
    update_available = pyqtSignal(str, str, str, str)

    def run(self) -> None:
        """Perform the update check in the background thread."""
        try:
            current = get_current_version()
            req = urllib.request.Request(
                _RELEASES_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "OpenGardenPlanner-UpdateChecker",
                },
            )
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode())

            info = parse_release_info(data)
            if info.tag_name and compare_versions(current, info.tag_name):
                self.update_available.emit(
                    info.tag_name,
                    info.body,
                    info.download_url or "",
                    info.html_url,
                )
        except Exception:  # noqa: BLE001
            logger.debug("Update check skipped (offline or error)", exc_info=True)
