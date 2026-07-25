"""Mechanical conformance gate for the themed UI icon set (#279, ADR-039).

Mirrors ``check_texture_tileability.py``: a fast, deterministic check every
icon must pass before merge (pinned into pytest by
``tests/unit/test_icon_conformance.py``).  Checks per SVG:

1.  well-formed XML, root ``<svg>`` in the SVG namespace
2.  ``viewBox`` exactly ``0 0 24 24`` (square canvas)
3.  root attributes exactly match the house contract
    (``fill=none stroke=currentColor stroke-width=2`` + round caps/joins)
4.  geometry-only elements — no ``<text>``/``<image>``/``<style>``/``<use>``/
    ``<defs>``/``<g>``/gradients/filters (i18n rule: no rendered text)
5.  no raster embeds, data URIs, external refs or ``url(...)`` anywhere
6.  every ``fill``/``stroke`` value in {none, currentColor, #3D8B37} and no
    ``style`` attributes (the runtime tint substitution must reach every part)
7.  every explicit ``stroke-width`` within [1.25, 2.5]
8.  byte-stable: ``normalize_icons.normalize_svg_text`` is a no-op on the file
9.  provenance: the filename appears in this directory's PROVENANCE.md
    (and every PROVENANCE icon reference points at an existing file)

Usage:  venv/Scripts/python.exe scripts/check_icon_conformance.py [paths...]
(no paths = check every SVG in resources/icons/ui/)
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from normalize_icons import (
    ACCENT_SENTINEL,
    ALLOWED_TAGS,
    ROOT_ATTRS,
    NormalizationError,
    normalize_svg_text,
)

_ICONS_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "icons"
    / "ui"
)

_ALLOWED_COLORS = {"none", "currentcolor", ACCENT_SENTINEL.lower()}
_STROKE_WIDTH_RANGE = (1.25, 2.5)
_FORBIDDEN_SUBSTRINGS = ("data:", "url(", "<script", "xlink", "href=")
_PROVENANCE_ICON_RE = re.compile(r"\b([a-z0-9_]+\.svg)\b")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def check_icon(path: Path, provenance_text: str | None) -> list[str]:
    """Return the list of conformance violations for one icon (empty = ok)."""
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")

    lowered = text.lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            problems.append(f"forbidden content {needle!r}")

    try:
        root = ET.fromstring(text)  # noqa: S314 - repo-controlled input only
    except ET.ParseError as exc:
        return [*problems, f"not well-formed XML: {exc}"]

    if _localname(root.tag) != "svg":
        problems.append("root element is not <svg>")
    for name, expected in ROOT_ATTRS:
        if name == "xmlns":
            continue  # carried by the element tag namespace after parsing
        actual = root.get(name)
        if actual != expected:
            problems.append(f"root {name}={actual!r}, contract requires {expected!r}")

    for element in root.iter():
        if element is root:
            continue
        tag = _localname(element.tag)
        if tag not in ALLOWED_TAGS:
            problems.append(f"forbidden element <{tag}>")
            continue
        for raw_name, raw_value in element.attrib.items():
            name = _localname(raw_name)
            value = raw_value.strip()
            if name == "style":
                problems.append(f"<{tag}> uses a style attribute")
            elif name in ("fill", "stroke") and value.lower() not in _ALLOWED_COLORS:
                problems.append(f"<{tag}> {name}={value!r} outside the color whitelist")
            elif name == "stroke-width":
                try:
                    width = float(value)
                except ValueError:
                    problems.append(f"<{tag}> stroke-width={value!r} is not numeric")
                else:
                    lo, hi = _STROKE_WIDTH_RANGE
                    if not lo <= width <= hi:
                        problems.append(
                            f"<{tag}> stroke-width={width} outside [{lo}, {hi}]"
                        )

    try:
        if normalize_svg_text(text) != text:
            problems.append("not in canonical form (run scripts/normalize_icons.py)")
    except NormalizationError as exc:
        problems.append(f"normalizer rejects file: {exc}")

    if provenance_text is None:
        problems.append("PROVENANCE.md missing next to the icon")
    elif path.name not in provenance_text:
        problems.append("no PROVENANCE.md entry (no entry, no merge)")

    return problems


def check_provenance_orphans(icons_dir: Path, provenance_text: str) -> list[str]:
    """PROVENANCE entries that reference icons which do not exist."""
    existing = {p.name for p in icons_dir.glob("*.svg")}
    referenced = set(_PROVENANCE_ICON_RE.findall(provenance_text))
    return sorted(referenced - existing)


def main(argv: list[str]) -> int:
    paths = (
        [Path(p) for p in argv[1:]]
        if len(argv) > 1
        else sorted(_ICONS_DIR.glob("*.svg"))
    )
    failures = 0
    provenance_cache: dict[Path, str | None] = {}
    for path in paths:
        prov_path = path.parent / "PROVENANCE.md"
        if prov_path not in provenance_cache:
            provenance_cache[prov_path] = (
                prov_path.read_text(encoding="utf-8") if prov_path.exists() else None
            )
        problems = check_icon(path, provenance_cache[prov_path])
        if problems:
            failures += 1
            print(f"{path.name:30s} FAIL")
            for problem in problems:
                print(f"    - {problem}")
        else:
            print(f"{path.name:30s} ok")

    provenance_text = provenance_cache.get(_ICONS_DIR / "PROVENANCE.md")
    if provenance_text:
        for orphan in check_provenance_orphans(_ICONS_DIR, provenance_text):
            failures += 1
            print(f"{orphan:30s} FAIL")
            print("    - PROVENANCE.md references a file that does not exist")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
