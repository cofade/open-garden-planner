"""Vendor the Tabler subset of the UI icon set (#279, ADR-039).

Downloads each mapped glyph from the pinned Tabler release, renames it to
our semantic name, runs it through ``normalize_icons.normalize_svg_text``
and writes it into ``resources/icons/ui/``.  Deterministic and re-runnable:
same tag -> same bytes.  This script IS the reproduction recipe recorded in
PROVENANCE.md.

Bespoke icons (garden_bed, greenhouse, terrace, the geometric-relation
constraint glyphs, chamfer) are NOT produced here — they are authored
in-repo on the same contract.

Usage:  venv/Scripts/python.exe scripts/vendor_tabler_icons.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from normalize_icons import normalize_svg_text

#: Pinned Tabler release — bump deliberately, then re-run + re-check gates.
TABLER_TAG = "v3.45.0"

_RAW_URL = "https://raw.githubusercontent.com/tabler/tabler-icons/{tag}/icons/outline/{glyph}.svg"

_ICONS_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "icons"
    / "ui"
)

#: semantic icon name -> Tabler outline glyph name.
MAPPING: dict[str, str] = {
    # Main toolbar
    "select": "pointer",
    "measure": "ruler-measure",
    "text_annotation": "typography",
    "callout_annotation": "message",
    "journal_pin": "map-pin",
    # Shapes (gallery + category chips)
    "rectangle": "rectangle",
    "polygon": "polygon",
    "circle": "circle",
    "ellipse": "oval",
    "arc": "vector-spline",
    "bezier": "vector-bezier-2",
    # Plant / object categories
    "tree": "tree",
    "shrub": "plant",
    "flower": "flower",
    "vegetable": "carrot",
    "house": "home",
    "shed": "building-warehouse",
    "furniture": "armchair",
    "fence": "fence",
    "wall": "wall",
    "path": "route",
    "infrastructure": "tools",
    "driveway": "car",
    "pond": "ripple",
    # Constraint toolbar (dimensional + advanced + CAD editing)
    "constraint_distance": "arrows-horizontal",
    "constraint_edge_length": "ruler-2",
    "constraint_h_distance": "arrow-autofit-width",
    "constraint_v_distance": "arrow-autofit-height",
    "constraint_equal": "equal",
    "constraint_fixed": "lock",
    "constraint_angle": "angle",
    "construction_line": "line-dashed",
    "construction_circle": "circle-dashed",
    "trim_extend": "scissors",
    "offset": "box-margin",
    "fillet": "border-radius",
    "mirror": "flip-horizontal",
    # Menu actions
    "file_new": "file-plus",
    "file_open": "folder-open",
    "file_save": "device-floppy",
    "file_save_as": "files",
    "file_import": "file-import",
    "file_export": "file-export",
    "print": "printer",
    "undo": "arrow-back-up",
    "redo": "arrow-forward-up",
    "cut": "cut",
    "copy": "copy",
    "paste": "clipboard",
    "duplicate": "copy-plus",
    "delete": "trash",
    "select_all": "select-all",
    "find_replace": "list-search",
    "preferences": "settings",
    "zoom_in": "zoom-in",
    "zoom_out": "zoom-out",
    "zoom_fit": "zoom-scan",
    "shortcuts": "keyboard",
    "connect_ai": "sparkles",
    "about": "info-circle",
    "theme": "sun-moon",
}


def main() -> int:
    _ICONS_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for name in sorted(MAPPING):
        glyph = MAPPING[name]
        url = _RAW_URL.format(tag=TABLER_TAG, glyph=glyph)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - pinned https URL
                raw = response.read().decode("utf-8")
        except OSError as exc:
            print(f"{name:26s} FETCH FAILED  {glyph}: {exc}")
            failures += 1
            continue
        if "<svg" not in raw:
            print(f"{name:26s} NOT AN SVG    {glyph}")
            failures += 1
            continue
        try:
            normalized = normalize_svg_text(raw, strict=True)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"{name:26s} NORMALIZE FAILED  {glyph}: {exc}")
            failures += 1
            continue
        target = _ICONS_DIR / f"{name}.svg"
        changed = not target.exists() or target.read_text(encoding="utf-8") != normalized
        target.write_text(normalized, encoding="utf-8", newline="\n")
        print(f"{name:26s} {'written' if changed else 'unchanged'}  ({glyph})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
