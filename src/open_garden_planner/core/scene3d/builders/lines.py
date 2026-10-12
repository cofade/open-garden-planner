"""FENCE and WALL: from a polyline's kind and style to its solid (Phase 17 L1.6).

The ONE place that decides what a line item is built as. The geometry lives in
``fences.py`` and ``walls.py``; neither knows about the other or about kinds.

A polyline's style is ``params["path_style"]``: a ``PathFenceStyle`` name, absent
for the plain line (``NONE``).

==========  ================================  ================================
kind        style                             built as
==========  ================================  ================================
``FENCE``   none                              the default fence: posts, rails,
                                              pickets (``WOODEN_FENCE``)
``WALL``    none                              the wall (``STONE_WALL``)
either      one of the five fence styles      that style, whatever the kind —
                                              the style is what 2D draws
either      anything else: a path style, a    a PLAIN panel — the stroke as
            name no builder knows             wide as drawn, up to the height
==========  ================================  ================================

The last row is the honest fallback. A style this module has no solid for —
a path style on a fence, or a fence style added to ``PATH_FENCE_STYLES`` after
this was written — is NOT quietly given some other style's look (it used to
become a picket fence). It gets the one body the plan itself describes: its
line, its stroke width, its height — the same solid the 2D shadow model casts.
A new fence style is caught before that, at development time: the mirror
``fences.FENCE_STYLES`` is pinned against the 2D table by a test. At run time
the fallback is not silent either: the first build of a line in such a style
writes ONE warning to the application's log, per style name (``line_parts``).
"""

from __future__ import annotations

import logging
from typing import Final

from ..build import BuilderRegistry
from ..mesh import MeshPart
from ..record import PARAM_PATH_STYLE, Record
from . import fences, walls
from .common import BuiltBuilder, centre_line

_log = logging.getLogger(__name__)

#: kind -> what a line of that kind is built as when it carries no style
DEFAULT_SOLID: Final = {"FENCE": fences.DEFAULT_FENCE_STYLE, "WALL": "STONE_WALL"}
#: How many style names the one-warning-per-name memory holds (a hand-edited plan
#: can name anything; the 2D table has a dozen styles). Bounded in memory AND in
#: volume: once it is full nothing new is logged for the rest of the session,
#: and one line says so — starting over instead would log every unknown style
#: again on every rebuild pass.
REPORTED_STYLES_MAX: Final = 64
#: The style names already reported as built plain — per process, not per build:
#: every edit rebuilds the items it touches.
_reported_styles: set[str] = set()
#: In ``_reported_styles`` once the line "no further ones are logged" was written.
#: No ``repr`` of a style equals it.
_NO_MORE: Final = "<no more>"


def solid_of(record: Record) -> str:
    """What the line is built as: one of the five fence styles, or ``fences.PLAIN``
    (the table in the module docstring). A pure question: it reports nothing."""
    style = record.params.get(PARAM_PATH_STYLE)
    if style is None:
        return DEFAULT_SOLID.get(record.kind, fences.PLAIN)
    if fences.is_fence_style(style):
        return str(style)
    return fences.PLAIN


def _report_plain(record: Record) -> None:
    """One warning per style name that has no solid of its own — for the first
    ``REPORTED_STYLES_MAX`` names of a session; then one line that says no more
    follow, and silence."""
    style = record.params.get(PARAM_PATH_STYLE)
    name = repr(style)
    if style is None or name in _reported_styles:
        return
    if len(_reported_styles) >= REPORTED_STYLES_MAX:
        if _NO_MORE not in _reported_styles:
            _reported_styles.add(_NO_MORE)
            _log.warning(
                "3D: %d line styles without a solid have been logged; further ones are built "
                "as plain panels without a log line", REPORTED_STYLES_MAX)
        return
    _reported_styles.add(name)
    _log.warning(
        "3D: no solid for the line style %s (first met on %s item %r); every line in that "
        "style is built as a plain panel - its stroke, as wide as drawn, up to its height",
        name, record.kind, record.item_id)


def line_parts(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """The parts of a FENCE or WALL record, built from its centre line."""
    line, closed = centre_line(record)
    if len(line) < 2:
        return ()
    solid = solid_of(record)
    if solid == "STONE_WALL":
        return walls.wall_parts(record, line, closed, height_cm)
    if solid == fences.PLAIN:
        _report_plain(record)
    return fences.fence_parts(record, line, closed, height_cm, solid)


build_fence: Final = BuiltBuilder(line_parts, "fence")
build_wall: Final = BuiltBuilder(line_parts, "wall")


def triangle_budget(record: Record) -> int:
    """The most triangles a FENCE or WALL record may have, by what it is built as
    (``walls.triangle_budget``, ``fences.triangle_budget``)."""
    solid = solid_of(record)
    if solid == "STONE_WALL":
        return walls.triangle_budget(record)
    line, closed = centre_line(record)
    return fences.triangle_budget(line, closed, max(len(record.path) - 1, 1), solid)


def register(registry: BuilderRegistry) -> None:
    registry.register("FENCE", build_fence)
    registry.register("WALL", build_wall)
