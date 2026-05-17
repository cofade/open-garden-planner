"""Coordinate string parser.

Accepts three forms of point input as a single string:

* ``x, y``                  — absolute scene coordinates (cm).
* ``@dx, dy``               — relative to the active tool's last point.
* ``@dist<angle``           — polar, distance + angle in degrees from last point.

Smart-parse decimal/separator rules (top-down):

A. If ``;`` appears, it is the field separator. Each side may use ``.`` or ``,``
   as decimal mark.
B. If both ``.`` and ``,`` appear, ``,`` is the field separator and ``.`` is the
   decimal mark.
C. If the token contains ``<``, the LHS is distance, the RHS is the angle in
   degrees. Polar terms allow either decimal mark.
D. If only commas appear:
   * 1 comma  -> field separator (``@1,2`` => dx=1, dy=2).
   * 3 commas -> field separator with locale decimal (``@1,5,2,5`` =>
     dx=1.5, dy=2.5).
   * 2 commas -> ambiguous; prefer locale decimal (``@1,5,2`` => dx=1.5, dy=2).
     Pure-separator interpretation is offered via ``parse_alternative`` so
     callers can preview both readings to the user.
E. Whitespace acts as a field separator everywhere.
F. Leading/trailing whitespace is stripped. ``<`` is case-insensitive.

Angle convention: ``0deg = east``, counter-clockwise positive (math convention).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from PyQt6.QtCore import QPointF

_NUMBER_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


@dataclass(frozen=True)
class ParsedCoordinate:
    """Successfully parsed coordinate input.

    The ``kind`` describes how the values were derived; the ``point`` is the
    final absolute scene coordinate that callers should commit.
    """

    kind: Literal["absolute", "relative", "polar"]
    point: QPointF
    raw_dx: float = 0.0
    raw_dy: float = 0.0
    raw_distance: float = 0.0
    raw_angle_deg: float = 0.0


class ParseError(ValueError):
    """Raised when a coordinate string cannot be parsed."""


def parse(
    text: str,
    last_point: QPointF | None = None,
    *,
    prefer_locale_decimal: bool = True,
) -> ParsedCoordinate:
    """Parse a coordinate string into a ``ParsedCoordinate``.

    Args:
        text: Raw user input.
        last_point: The active tool's anchor point, required for relative and
            polar forms. Absolute form ignores it.
        prefer_locale_decimal: Tie-break for the 2-comma ambiguity. Defaults to
            True (locale-style ``1,5`` reads as 1.5).

    Raises:
        ParseError: On any malformed input.
    """
    if text is None:
        raise ParseError("Empty input")
    s = text.strip()
    if not s:
        raise ParseError("Empty input")

    relative = s.startswith("@")
    if relative:
        s = s[1:].strip()
        if not s:
            raise ParseError("Missing coordinate after '@'")

    # Rule C: polar
    if "<" in s.lower():
        # Normalize the angle separator. There must be exactly one.
        lower = s.lower()
        if lower.count("<") != 1:
            raise ParseError("Polar input requires exactly one '<'")
        idx = lower.index("<")
        dist_str = s[:idx].strip()
        ang_str = s[idx + 1 :].strip()
        if not dist_str or not ang_str:
            raise ParseError("Polar input requires distance and angle")
        distance = _parse_number(dist_str)
        angle_deg = _parse_number(ang_str)
        # Polar input always implies a base point — CAD convention.
        # We require an anchor whether or not the user typed '@'; a silent
        # fallback to origin would place a vertex far from the cursor
        # without feedback.
        if last_point is None:
            raise ParseError(
                "Polar input requires an existing point to anchor to"
            )
        base = last_point
        rad = math.radians(angle_deg)
        # Scene Y axis points down; we keep math convention (CCW positive) and
        # flip Y when applying so 45 deg points up-and-to-the-right on screen.
        dx = distance * math.cos(rad)
        dy = -distance * math.sin(rad)
        return ParsedCoordinate(
            kind="polar",
            point=QPointF(base.x() + dx, base.y() + dy),
            raw_distance=distance,
            raw_angle_deg=angle_deg,
        )

    # Cartesian: split into two terms using the disambiguation rules
    a_str, b_str = _split_cartesian(s, prefer_locale_decimal=prefer_locale_decimal)
    a = _parse_number(a_str)
    b = _parse_number(b_str)

    if relative:
        if last_point is None:
            raise ParseError(
                "Relative input requires an existing point to anchor to"
            )
        return ParsedCoordinate(
            kind="relative",
            point=QPointF(last_point.x() + a, last_point.y() - b),
            raw_dx=a,
            raw_dy=b,
        )
    # Absolute. Y axis flip: a user-entered Y is interpreted in math
    # convention (up positive) and converted to scene Y (down positive).
    return ParsedCoordinate(
        kind="absolute",
        point=QPointF(a, -b),
        raw_dx=a,
        raw_dy=b,
    )


def _split_cartesian(s: str, *, prefer_locale_decimal: bool) -> tuple[str, str]:
    """Split a cartesian term per rules A, B, D, E."""
    # Rule A: semicolon is always the separator
    if ";" in s:
        parts = [p.strip() for p in s.split(";") if p.strip()]
        if len(parts) != 2:
            raise ParseError("Expected two values separated by ';'")
        return parts[0], parts[1]

    # Rule E: whitespace as separator (only when no ambiguity)
    if re.search(r"\s", s) and "," not in s:
        parts = s.split()
        if len(parts) != 2:
            raise ParseError("Expected two whitespace-separated values")
        return parts[0], parts[1]

    # Rule B: both '.' and ',' present -> ',' is separator, '.' decimal
    if "." in s and "," in s:
        parts = [p.strip() for p in s.split(",")]
        if len(parts) != 2:
            raise ParseError("Expected two values when mixing '.' and ','")
        return parts[0], parts[1]

    # Whitespace combined with commas -> whitespace splits, commas are decimal
    if re.search(r"\s", s) and "," in s:
        parts = re.split(r"\s+", s)
        parts = [p for p in parts if p]
        if len(parts) != 2:
            raise ParseError("Expected two whitespace-separated values")
        return parts[0], parts[1]

    # Rule D: only commas
    comma_count = s.count(",")
    if comma_count == 0:
        raise ParseError("Expected two values; no separator found")
    if comma_count == 1:
        a, b = s.split(",", 1)
        return a.strip(), b.strip()
    if comma_count == 3:
        parts = s.split(",")
        return f"{parts[0]},{parts[1]}", f"{parts[2]},{parts[3]}"
    if comma_count == 2:
        parts = s.split(",")
        # Two equally valid readings; prefer locale decimal by default:
        #   "1,5,2"  -> ("1,5", "2")
        # The non-locale reading is: ("1", "5,2")
        if prefer_locale_decimal:
            return f"{parts[0]},{parts[1]}", parts[2]
        return parts[0], f"{parts[1]},{parts[2]}"
    raise ParseError("Too many ',' separators to disambiguate")


def _parse_number(token: str) -> float:
    """Parse a single numeric token. Accepts ``.`` or ``,`` as decimal mark."""
    token = token.strip()
    if not _NUMBER_RE.match(token):
        raise ParseError(f"Not a number: '{token}'")
    return float(token.replace(",", "."))


def parse_alternative(
    text: str,
    last_point: QPointF | None = None,
) -> ParsedCoordinate | None:
    """Return the alternative interpretation for the 2-comma ambiguity.

    Returns ``None`` when the input is unambiguous.
    """
    s = text.strip()
    body = s[1:] if s.startswith("@") else s
    if "<" in body.lower():
        return None
    if ";" in body or "." in body or re.search(r"\s", body):
        return None
    if body.count(",") != 2:
        return None
    try:
        return parse(text, last_point, prefer_locale_decimal=False)
    except ParseError:
        return None
