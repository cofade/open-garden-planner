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
literal color and pass. ``palette(...)`` values also pass — note honestly:
they track the PLATFORM palette (this app themes via its stylesheet, not
QPalette), so they are acceptable only for incidental accents, never for
surfaces; the visible offenders (dropdown/search popup frames) moved to
theme tokens in the ADR-039 review round. Known structural blind spot:
lines without a quote character are skipped (docstrings), so a triple-quoted
QSS block whose property lines carry no quotes would evade the scan.

The allowlist below must stay EMPTY — a new entry needs a documented
architectural reason in ADR-039, not convenience.
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


def test_no_hardcoded_qss_colors_outside_theme() -> None:
    violations = _scan()
    assert violations == [], (
        "Hardcoded QSS colors found outside ui/theme.py — use theme tokens "
        "(theme_color()/rgba()/set_text_role()/dynamic-property rules):\n"
        + "\n".join(violations)
    )
