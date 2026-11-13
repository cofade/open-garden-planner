"""Lint gate: no hardcoded colors in widget QSS strings (#279, ADR-039).

Every chrome color must come from ``ui/theme.py`` — either via the global
stylesheet (dynamic properties like textRole/colorRole/buttonRole/
weatherCard) or via the live-palette helpers (``theme_color``/``rgba``/…).
A widget-level ``setStyleSheet`` with a baked color silently overrides the
theme in one mode forever, which is exactly the class of bug the visual
refresh removed (dark-mode weather cards, the Google-blue update bar, three
different "error" reds).

Mechanism: a pure text scan (no Qt) over ``src/open_garden_planner/ui`` and
``src/open_garden_planner/app`` — excluding ``theme.py``, the single allowed
home of chrome hex values. Flagged: QSS-looking lines (``color:`` /
``background`` / ``border`` properties) whose VALUE contains a literal hex
color, a CSS named color, or a literal numeric ``rgba(...)``. Painter/QColor
drawing code (canvas items, Gantt palette) never matches — it has no
``property: value`` shape. f-string interpolations of theme helpers carry no
literal color and pass. ``palette(...)`` values also pass: since #791 the
application palette is built from the theme's tokens (``theme.build_palette``,
PF-UI-37), so a ``palette(...)`` value IS a theme colour and follows a theme
switch by itself. (Before #791 it was the operating system's, and a light app
on a dark Windows painted white text on cream.) Known structural blind spot:
lines without a quote character are skipped (docstrings), so a triple-quoted
QSS block whose property lines carry no quotes would evade the scan.

The allowlist below must stay EMPTY — a new entry needs a documented
architectural reason in ADR-039, not convenience.

A second gate covers what the first cannot see: colours a widget PAINTS with
(``QColor(40, 40, 40)``, ``Qt.GlobalColor.white``). The Planting Calendar
chart, the soil sparkline and the seed-viability cells each painted a light
picture in the dark theme that way (#791). Chrome reads ``theme_qcolor(token)``
while it paints; a literal is allowed only where the colour is DATA or is
drawn on something that is not chrome, and every such place is listed with
its reason and its count.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).parents[2] / "src" / "open_garden_planner"
_SCAN_DIRS = (_SRC / "ui", _SRC / "app")
_EXCLUDED = {_SRC / "ui" / "theme.py"}

#: file (repo-relative posix path) -> set of allowed line snippets.
#: MUST stay empty — see module docstring.
ALLOWLIST: dict[str, set[str]] = {}

_NAMED_COLORS = (
    "red", "blue", "green", "orange", "yellow", "white", "black",
    "gray", "grey", "cyan", "magenta", "purple", "brown", "pink",
)

# Named colors must stand alone as a QSS value (not `.red()` attribute
# access, not a `rgba(...)` call argument) — hence the lookarounds.
_QSS_COLOR_LINE = re.compile(
    r"(?:color|background(?:-color)?|border(?:-[\w-]+)?)\s*:\s*"
    r"[^;\"'\n]*?(?:"
    r"#[0-9a-fA-F]{3,8}\b"
    r"|\brgba?\(\s*\d"
    r"|(?<![.\w])(?:" + "|".join(_NAMED_COLORS) + r")\b(?!\s*\()"
    r")"
)


def _scan() -> list[str]:
    violations: list[str] = []
    for scan_dir in _SCAN_DIRS:
        for path in sorted(scan_dir.rglob("*.py")):
            if path in _EXCLUDED:
                continue
            rel = path.relative_to(_SRC.parents[1]).as_posix()
            allowed = ALLOWLIST.get(rel, set())
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue  # comments may cite old hex values
                if '"' not in line and "'" not in line:
                    continue  # docstring prose — QSS lives in string literals
                match = _QSS_COLOR_LINE.search(line)
                if match and not any(snippet in line for snippet in allowed):
                    violations.append(f"{rel}:{lineno}: {stripped}")
    return violations


#: Painted colour literals that may stay: file -> (count, why it is not chrome).
#: Shrink-only. A new entry needs the same kind of reason; "it looked fine" is
#: not one — check the widget in BOTH themes first.
PAINTED_LITERALS: dict[str, tuple[int, str]] = {
    "ui/dialogs/calibration_dialog.py": (
        2, "the measuring line is drawn on the user's photo, not on chrome"),
    "ui/dialogs/insert_guild_dialog.py": (
        1, "a preview marker drawn on the plan (the canvas is bright in both themes)"),
    "ui/dialogs/print_dialog.py": (4, "drawn on paper"),
    "ui/dialogs/properties_dialog.py": (
        2, "default values of an object's own fill and stroke colour (data)"),
    "ui/dialogs/succession_plan_dialog.py": (
        7, "season bands and crop pills are data colours, with their own ink on top"),
    "ui/guild_coordinator.py": (1, "a badge drawn on the plan"),
    "ui/views/planting_calendar_view.py": (
        8, "the chart's series colours (data); _series_qcolor adapts them to the theme's rows"),
    "ui/widgets/minimap_widget.py": (
        4, "an overlay on the always-bright canvas, constant like the overlay_* tokens"),
}

_PAINTED_LITERAL = re.compile(
    r"QColor\(\s*\d|QColor\(\s*[\"']#|Qt\.GlobalColor\.(?!transparent)\w+"
)
#: Not chrome: the plan's own painters, the 3D view, and the two modules that
#: own colour values (the theme and the icon tints).
_PAINTED_EXCLUDED_DIRS = ("ui/canvas/", "ui/view3d/")
_PAINTED_EXCLUDED_FILES = {"ui/theme.py", "ui/icons.py"}


def _painted_literals() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for scan_dir in _SCAN_DIRS:
        for path in sorted(scan_dir.rglob("*.py")):
            rel = path.relative_to(_SRC).as_posix()
            if rel in _PAINTED_EXCLUDED_FILES or rel.startswith(_PAINTED_EXCLUDED_DIRS):
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if _PAINTED_LITERAL.search(line):
                    found.setdefault(rel, []).append(f"{rel}:{lineno}: {stripped}")
    return found


def test_no_painted_colour_literals_in_chrome() -> None:
    """A widget that paints takes its colours from the theme (#791)."""
    found = _painted_literals()
    unexpected = [
        line for rel, lines in found.items() if rel not in PAINTED_LITERALS for line in lines
    ]
    assert unexpected == [], (
        "Painted colour literals in chrome — read theme_qcolor(token) while "
        "painting, or list the file in PAINTED_LITERALS with the reason the "
        "colour is not chrome:\n" + "\n".join(unexpected)
    )
    drifted = {
        rel: (len(found.get(rel, [])), allowed)
        for rel, (allowed, _why) in PAINTED_LITERALS.items()
        if len(found.get(rel, [])) != allowed
    }
    assert drifted == {}, (
        "PAINTED_LITERALS counts are exact (file: (found, listed)) — a literal "
        f"was added to a listed file, or one was removed and the list not updated: {drifted}"
    )


def test_no_hardcoded_qss_colors_outside_theme() -> None:
    violations = _scan()
    assert violations == [], (
        "Hardcoded QSS colors found outside ui/theme.py — use theme tokens "
        "(theme_color()/rgba()/set_text_role()/dynamic-property rules):\n"
        + "\n".join(violations)
    )
