"""PRIVACY.md is a public promise about the network surface (ADR-073, Store listing).

The statement is the Microsoft Store listing's privacy-policy URL. A new module that
talks to the network without a row there makes the published statement false without
anyone noticing, so the set of network-using modules is pinned here and every module
is mapped to the PRIVACY.md text that discloses it.

Limit: a NEW CALLER of an existing client (a second button that calls the Permapeople
client, say) is not detected; the review of such a change has to check PRIVACY.md's
"When" column. The companion panel was exactly such a caller (review round 4 on #761).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "open_garden_planner"
PRIVACY = ROOT / "PRIVACY.md"

#: Python constructs that open a network connection or load a web page: import lines of the
#: network libraries (plain and ``from`` forms) and the Qt network / web classes.
_NETWORK = re.compile(
    r"^\s*(?:import|from)\s+(?:requests|httpx|aiohttp|websockets|websocket|ftplib|smtplib|"
    r"urllib\.request|urllib3|http\.client)\b|"
    r"^\s*from\s+urllib\s+import\s+[^\n]*\brequest\b|^\s*from\s+http\s+import\s+[^\n]*\bclient\b|"
    r"\burlopen\b|QNetworkAccessManager|QTcpSocket|QSslSocket|QUdpSocket|QWebSocket|"
    r"QWebEngine(?:View|Page)|socket\.(?:create_connection|socket)\b",
    re.MULTILINE,
)
#: Bundled web/QML pages that load remote content.
_REMOTE_SCRIPT = re.compile(
    r"""<script[^>]+src=["']https?://|maps\.googleapis\.com|https?://[a-z0-9.-]+/[^"']*\.js|"""
    r"""XMLHttpRequest|\bfetch\s*\(\s*["'`]https?://|source:\s*["']https?://"""
)

#: Module (relative to the package) -> the PRIVACY.md text that discloses its traffic.
DISCLOSED: dict[str, tuple[str, ...]] = {
    # Loopback only: the Agent API server and the self-test's free-port probe.
    "agent_api/server.py": ("127.0.0.1",),
    "main.py": ("127.0.0.1",),
    "services/weather_service.py": ("Weather forecast and frost alerts",),
    "services/climate_service.py": ("Frost dates and hardiness zone",),
    "services/image_download.py": ("Satellite background", "Plant thumbnail download"),
    "services/google_maps_js_capture.py": ("Satellite background",),
    "ui/dialogs/map_picker_dialog.py": ("Satellite background", "type into the map's search box"),
    "resources/web/map_picker.html": ("Satellite background", "type into the map's search box"),
    "services/plant_api/trefle_client.py": ("Online plant search", "Trefle"),
    "services/plant_api/perenual_client.py": ("Online plant search", "Perenual"),
    "services/plant_api/permapeople_client.py": ("Online plant search", "Companion plants", "Permapeople"),
    "services/update_checker.py": ("Update check",),
    "services/verified_update.py": ("Update check", "Download & Install"),
}


def _network_modules() -> set[str]:
    found: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if _NETWORK.search(path.read_text(encoding="utf-8", errors="replace")):
            found.add(path.relative_to(PACKAGE).as_posix())
    for pattern in ("*.htm*", "*.qml", "*.js"):
        for path in PACKAGE.rglob(pattern):
            if _REMOTE_SCRIPT.search(path.read_text(encoding="utf-8", errors="replace")):
                found.add(path.relative_to(PACKAGE).as_posix())
    return found


def test_every_network_module_is_disclosed_and_the_list_is_not_stale() -> None:
    found = _network_modules()
    undisclosed = sorted(found - DISCLOSED.keys())
    stale = sorted(DISCLOSED.keys() - found)
    assert not undisclosed, (
        f"{undisclosed} talk to the network: add a row to PRIVACY.md (what is sent, to whom, "
        "when) and an entry to DISCLOSED here"
    )
    assert not stale, f"{stale} no longer talk to the network: drop them from DISCLOSED (and PRIVACY.md if unused)"


def test_privacy_statement_names_what_each_module_sends() -> None:
    text = PRIVACY.read_text(encoding="utf-8")
    missing = {module: phrase for module, phrases in DISCLOSED.items() for phrase in phrases if phrase not in text}
    assert not missing, f"PRIVACY.md no longer discloses: {missing}"


def test_privacy_statement_covers_the_ai_assistant_channel_and_the_store_uninstall() -> None:
    """The two flows review round 4 found missing: a connected assistant reads the plan, and a
    Store uninstall deletes the data kept outside plans."""
    text = PRIVACY.read_text(encoding="utf-8")
    assert "can read your whole plan" in text
    assert "deletes them when you" in text
    assert all(word in text for word in ("custom plants", "seed inventory", "guild templates"))
    assert "nothing leaves your computer" not in text


def test_plant_thumbnail_download_is_disclosed_and_has_expected_caller() -> None:
    """``fetch_thumbnail`` loads images from the hosts a plant provider returns, which
    PRIVACY.md discloses in its plant thumbnail download row (US-G2, issue #765)."""
    callers = sorted(
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if "__pycache__" not in path.parts
        and path.name != "thumbnail_loader.py"
        and "fetch_thumbnail" in path.read_text(encoding="utf-8", errors="replace")
    )
    assert callers == ["ui/panels/plant_database_panel.py"], f"Unexpected callers of fetch_thumbnail: {callers}"
    text = PRIVACY.read_text(encoding="utf-8")
    assert "Plant thumbnail download" in text
