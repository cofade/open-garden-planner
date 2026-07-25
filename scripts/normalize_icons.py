"""Deterministic SVG normalizer for the themed UI icon set (#279, ADR-039).

Brings vendored (Tabler) and bespoke icons onto the single house contract
consumed by ``ui/icons.py``:

- 24x24 viewBox; root attrs exactly ``fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round"``
- geometry-only children (path/circle/rect/line/polyline/polygon/ellipse)
- colors restricted to ``none`` / ``currentColor`` / the accent sentinel
  ``#3D8B37`` (any other color is rewritten to ``currentColor``, or rejected
  with ``--strict``)
- editor junk removed: width/height/class/id/style/data-* attributes,
  comments, title/desc/metadata/defs elements, and Tabler's leading
  ``M0 0h24v24H0z`` reset path
- float literals rounded to 2 decimals, canonical attribute order,
  2-space indentation -> byte-stable output.  Idempotence (normalizing a
  normalized file is a byte-for-byte no-op) is itself a conformance check.

Usage:
  venv/Scripts/python.exe scripts/normalize_icons.py <files-or-dirs> [--out DIR] [--check] [--strict]

``--check``: verify files are already normalized (no writes; exit 1 on drift).

Input SVGs are repo-controlled, so stdlib ElementTree is acceptable here
(the bandit gate scans ``src/`` only, and there is no untrusted input).
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"

#: Reserved accent color — replaced with the active theme's accent at render
#: time by ui/icons.py.  Equals the light-theme accent so raw files preview
#: correctly in a browser or editor.
ACCENT_SENTINEL = "#3D8B37"

#: The binding root-attribute contract (order = serialization order).
ROOT_ATTRS: tuple[tuple[str, str], ...] = (
    ("xmlns", SVG_NS),
    ("viewBox", "0 0 24 24"),
    ("fill", "none"),
    ("stroke", "currentColor"),
    ("stroke-width", "2"),
    ("stroke-linecap", "round"),
    ("stroke-linejoin", "round"),
)

#: Only pure geometry may appear inside an icon.
ALLOWED_TAGS = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse"}

#: Dropped silently — metadata/editor baggage with no visual meaning.
DROPPED_TAGS = {"title", "desc", "metadata", "defs"}

#: Child attributes that merely repeat the root contract are stripped.
_REDUNDANT_CHILD_ATTRS = {
    "stroke": "currentColor",
    "stroke-width": "2",
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
    "fill": "none",
}

#: Canonical attribute order for serialized child elements.
_ATTR_ORDER = [
    "d", "points", "x", "y", "x1", "y1", "x2", "y2",
    "cx", "cy", "r", "rx", "ry", "width", "height",
    "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
]

_DROPPED_ATTRS = {"class", "id", "style"}

_NUMBER_RE = re.compile(r"-?(?:\d+\.\d+|\.\d+)(?:[eE]-?\d+)?")
_RESET_PATH_RE = re.compile(r"^M\s*0\s+0\s*h\s*24\s*v\s*24\s*H\s*0\s*z\s*$", re.IGNORECASE)

_ICONS_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "icons"
    / "ui"
)


class NormalizationError(ValueError):
    """Raised when an icon cannot be brought onto the contract."""


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _round_numbers(value: str) -> str:
    """Round every float literal to 2 decimals, trimming trailing zeros."""

    def _fmt(match: re.Match[str]) -> str:
        rounded = round(float(match.group(0)), 2)
        text = f"{rounded:.2f}".rstrip("0").rstrip(".")
        return text if text not in ("", "-") else "0"

    return _NUMBER_RE.sub(_fmt, value)


def _normalize_color(value: str, *, strict: bool, context: str) -> str:
    stripped = value.strip()
    if stripped == "none":
        return "none"
    if stripped.lower() == "currentcolor":
        return "currentColor"
    if stripped.lower() == ACCENT_SENTINEL.lower():
        return ACCENT_SENTINEL
    if strict:
        raise NormalizationError(f"{context}: baked color {stripped!r} (strict mode)")
    return "currentColor"


def normalize_svg_text(text: str, *, strict: bool = False) -> str:
    """Return the canonical, byte-stable form of an icon SVG.

    Raises:
        NormalizationError: on structures the normalizer must not silently
            repair (non-24x24 viewBox, text/raster/group elements, …).
    """
    try:
        root = ET.fromstring(text)  # noqa: S314 - repo-controlled input only
    except ET.ParseError as exc:
        raise NormalizationError(f"not well-formed XML: {exc}") from exc

    if _localname(root.tag) != "svg":
        raise NormalizationError(f"root element is <{_localname(root.tag)}>, not <svg>")

    view_box = " ".join((root.get("viewBox") or "").split())
    if view_box != "0 0 24 24":
        raise NormalizationError(
            f"viewBox is {view_box or '(missing)'!r} — icons must be authored at 0 0 24 24"
        )

    children: list[tuple[str, dict[str, str]]] = []
    for element in root.iter():
        if element is root:
            continue
        tag = _localname(element.tag)
        if tag in DROPPED_TAGS:
            continue
        if tag not in ALLOWED_TAGS:
            raise NormalizationError(f"forbidden element <{tag}>")

        attrs: dict[str, str] = {}
        for raw_name, raw_value in element.attrib.items():
            name = _localname(raw_name)
            if name in _DROPPED_ATTRS or name.startswith("data-"):
                if name == "style":
                    raise NormalizationError(
                        f"<{tag}> carries a style attribute — use plain fill/stroke"
                    )
                continue
            value = raw_value.strip()
            if name in ("fill", "stroke"):
                value = _normalize_color(value, strict=strict, context=f"<{tag}> {name}")
            elif name in ("d", "points") or name in _ATTR_ORDER:
                value = _round_numbers(" ".join(value.split()))
            else:
                raise NormalizationError(f"<{tag}> has unsupported attribute {name!r}")
            attrs[name] = value

        # Tabler ships a leading transparent reset rectangle — pure noise.
        if tag == "path" and _RESET_PATH_RE.match(attrs.get("d", "")):
            continue

        # Attributes that just restate the root contract are redundant.
        for name, default in _REDUNDANT_CHILD_ATTRS.items():
            if attrs.get(name) == default:
                del attrs[name]

        children.append((tag, attrs))

    if not children:
        raise NormalizationError("icon has no drawable geometry")

    lines = [
        "<svg " + " ".join(f'{name}="{value}"' for name, value in ROOT_ATTRS) + ">",
    ]
    for tag, attrs in children:
        ordered = [name for name in _ATTR_ORDER if name in attrs]
        ordered += [name for name in attrs if name not in _ATTR_ORDER]
        attr_text = " ".join(f'{name}="{attrs[name]}"' for name in ordered)
        lines.append(f"  <{tag} {attr_text}/>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _collect(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*.svg")))
        else:
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="SVG files or directories")
    parser.add_argument("--out", type=Path, default=None, help="write results here")
    parser.add_argument("--check", action="store_true", help="verify only, no writes")
    parser.add_argument("--strict", action="store_true", help="reject baked colors")
    args = parser.parse_args(argv)

    files = _collect(args.paths or [_ICONS_DIR])
    failures = 0
    for path in files:
        original = path.read_text(encoding="utf-8")
        try:
            normalized = normalize_svg_text(original, strict=args.strict)
        except NormalizationError as exc:
            print(f"{path.name:30s} ERROR  {exc}")
            failures += 1
            continue

        if args.check:
            verdict = "ok" if normalized == original else "DRIFT"
            if verdict != "ok":
                failures += 1
            print(f"{path.name:30s} {verdict}")
            continue

        target = (args.out / path.name) if args.out else path
        target.parent.mkdir(parents=True, exist_ok=True)
        changed = not target.exists() or target.read_text(encoding="utf-8") != normalized
        target.write_text(normalized, encoding="utf-8", newline="\n")
        print(f"{path.name:30s} {'written' if changed else 'unchanged'}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
