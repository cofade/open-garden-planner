"""Update checker service for US-8.3.

Checks GitHub Releases API for newer versions in a background thread.
Only active when running from the installed .exe (sys.frozen).
Uses only stdlib (urllib) — no extra dependencies.
"""

import json
import logging
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from open_garden_planner.services.verified_update import validate_release_asset

logger = logging.getLogger(__name__)

_RELEASES_URL = "https://api.github.com/repos/cofade/open-garden-planner/releases/latest"
_REQUEST_TIMEOUT = 10


@dataclass(frozen=True)
class ReleaseInfo:
    """Parsed information from a GitHub release."""

    tag_name: str
    body: str
    download_url: str | None
    html_url: str
    installer_name: str = ""
    installer_size: int = 0
    checksum_url: str | None = None

    @property
    def installable(self) -> bool:
        return bool(self.download_url and self.checksum_url and self.installer_size > 0)


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
    html_url = (
        f"https://github.com/cofade/open-garden-planner/releases/tag/{tag_name}"
        if re.fullmatch(r"v\d+\.\d+\.\d+", tag_name) else ""
    )

    download_url: str | None = None
    filename = f"OpenGardenPlanner-{tag_name}-Setup.exe"
    assets = data.get("assets") or []
    installers = [a for a in assets if isinstance(a, dict) and a.get("name") == filename]
    manifests = [a for a in assets if isinstance(a, dict) and a.get("name") == "SHA256SUMS.txt"]
    checksum_url = None
    size = 0
    try:
        if len(installers) == 1 and len(manifests) == 1 and html_url:
            installer_url = str(installers[0]["browser_download_url"])
            manifest_url = str(manifests[0]["browser_download_url"])
            validate_release_asset(installer_url, tag_name, filename)
            validate_release_asset(manifest_url, tag_name, "SHA256SUMS.txt")
            raw_size = installers[0]["size"]
            if isinstance(raw_size, int) and not isinstance(raw_size, bool) and raw_size > 0:
                download_url, checksum_url, size = installer_url, manifest_url, raw_size
    except Exception:
        logger.warning("Release assets cannot be verified")
    return ReleaseInfo(tag_name, body, download_url, html_url, filename, size, checksum_url)


def get_current_version() -> str:
    """Return the running application version string.

    When running from a PyInstaller bundle (``sys.frozen``), reads from the
    ``_version`` module written at build time.  Otherwise falls back to the
    package ``__version__``.
    """
    if getattr(sys, "frozen", False):
        try:
            from open_garden_planner import _version

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
    update_available = pyqtSignal(object)

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
                content = resp.read(1_048_577)
                if len(content) > 1_048_576:
                    return
                data: dict[str, Any] = json.loads(content.decode())

            info = parse_release_info(data)
            if info.tag_name and compare_versions(current, info.tag_name):
                self.update_available.emit(info)
        except Exception:  # noqa: BLE001
            logger.debug("Update check skipped (offline or error)", exc_info=True)
