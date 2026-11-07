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

#: Python constructs that open a network connection or load a web page.
_NETWORK = re.compile(
    r"import requests|requests\.(get|post|put|delete|head|request|Session)\b|urllib\.request|"
    r"\burlopen\b|http\.client|QNetworkAccessManager|QWebEngineView|\bhttpx\b|\baiohttp\b|"
    r"socket\.(create_connection|socket)\b"
)
#: Bundled web pages that load remote scripts.
_REMOTE_SCRIPT = re.compile(r"""<script[^>]+src=["']https?://|maps\.googleapis\.com|https?://[a-z0-9.-]+/[^"']*\.js""")

#: Module (relative to the package) -> the PRIVACY.md text that discloses its traffic.
DISCLOSED: dict[str, tuple[str, ...]] = {
    # Loopback only: the Agent API server and the self-test's free-port probe.
    "agent_api/server.py": ("127.0.0.1",),
    "main.py": ("127.0.0.1",),
    "services/weather_service.py": ("Weather forecast and frost alerts",),
    "services/climate_service.py": ("Frost dates and hardiness zone",),
    "services/image_download.py": ("Satellite background",),
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
    for path in (PACKAGE / "resources").rglob("*.htm*"):
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
    assert "deletes them when you" in text and "seed inventory" in text
    assert "nothing leaves your computer" not in text
