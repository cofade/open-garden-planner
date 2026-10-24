"""Plan snapshot for the 3D view — live items → plain data.

Runs on the GUI thread; the output contains no Qt object references (the
same snapshot-boundary discipline as the US-E4 worker). Footprints reuse
the US-E3 extraction (rotation/position are Qt's answer via ``mapToScene``)
so the 3D solids can never disagree with the 2D shadow footprints.

``snapshot_records`` (Phase 17 L1.1, #385, ADR-059) produces contract v2: one
``core.scene3d.Record`` per item, in the item-local frame with a rigid
transform, for ``SceneSync`` and the Qt Quick 3D sink. (The US-E6 collector of
the retired Qt 3D window, ``collect_scene3d_records``, left with it in L1.10.)

Four things on record about the contract-v2 half (reviews of fix rounds 1, 3 and 4):

- What it remembers is module-global, for ONE snapshotting scene per process,
  and stays until ``clear_outline_cache()`` is called (on a document change,
  when the 3D view closes). ``_polyline_regions``
  and ``_polygon_regions`` are keyed by whole rings (``core.scene3d.polygon.
  ring_keyed``). What the plan asks for is LIVE and never dropped: a snapshot
  is one ``snapshot_generation``, and an answer asked for in this snapshot or
  the one before stays, so an unchanged plan costs lookups whatever its size.
  What is bounded is the STALE answers — an outline of 4,000 vertices that is
  being edited leaves one per tick, and 2,048 of those were a gigabyte: at
  most 262,144 vertices each, keys and answers together. ``_circle_ring``,
  ``_circle_regions`` and ``_material`` are keyed by a number or a few short
  strings (``lru_cache``, 1,024 to 4,096 entries of at most 24 vertices).
- The outline of an item comes out of a plan file, and anybody can write one.
  So the INPUT is bounded before the work (an item's stored vertex count before
  one vertex is read; the pairs of a path before the clipper sees it; what the
  clipper returns before one ring of it is read), and what is bounded is the
  SUM: one ``WorkBudget`` of ``MAX_REGION_WORK`` units pays for everything one
  item's outline needs — the clipper, the sorting, every region's cut. See
  ``_stroke_regions`` and ``_outline_regions``, and section 8.11.
- This module is a second place that knows the clipper's scale
  (``CLIPPER_SCALE``; the first is ``core/shadow_geometry``): it resolves a
  self-crossing outline and sorts rings into regions itself. Both belong in ONE
  ``core`` function that the 2D footprints call as well — the follow-up that
  makes the 2D shadow of a closed stroke right should move them there.
- Until then 2D and 3D disagree ON PURPOSE for two shapes: a closed stroke (2D:
  every ring a solid; 3D: the stroke, with its hole) and a polygon that crosses
  itself (2D: the ring as drawn; 3D: the resolved regions).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Final

import numpy as np
import pyclipper
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.container_model import container_material
from open_garden_planner.core.object_height import effective_height_cm
from open_garden_planner.core.object_types import PathFenceStyle, is_container_type
from open_garden_planner.core.plant_art import PLANT_KINDS
from open_garden_planner.core.scene3d import (
    PARAM_CONTAINER_MATERIAL,
    PARAM_PATH_STYLE,
    PARAM_PLANT_CATEGORY,
    PARAM_RADIUS_CM,
    PARAM_RIDGE,
    PARAM_SEED,
    PARAM_SPECIES_KEY,
    PARAM_SPECIES_NAME,
    PARAM_SPRITE_SPECIES,
    LocalFrame,
    Material,
    Paint,
    Params,
    ParamValue,
    Record,
    Region,
    Rgba,
    Ring,
    ccw,
    group_rings,
    local_frame,
    quantize_cm,
    ring_area,
)
from open_garden_planner.core.scene3d.polygon import (
    MAX_ITEM_VERTICES,
    RegionTooLargeError,
    WorkBudget,
    clear_ring_memories,
    is_buildable_region,
    is_convex_ring,
    pay_for_region,
    regions_area,
    ring_keyed,
    snapshot_generation,
    stack_height,
    touching_pairs,
)
from open_garden_planner.core.scene3d.record import (
    MAX_LENGTH_CM,
    PARAM_OUTLINE_RESOLVED,
    PARAM_PAINT_ORIGIN,
    PEN_CAPS,
    PEN_JOINS,
    PEN_STYLES,
    RecordRangeError,
)
from open_garden_planner.core.shadow_geometry import (
    CLIPPER_SCALE,
    circle_footprint,
    polyline_footprint,
)
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.ui.canvas.footprints import (
    OUTLINE_CIRCLE,
    OUTLINE_POLYGON,
    OUTLINE_POLYLINE,
    ItemLookup,
    item_base_cm,
    item_outline,
)
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.footprints import ItemOutline

_log = logging.getLogger(__name__)



# ── contract v2 (Phase 17 L1.1) ──────────────────────────────────────────────

#: A ROOF_RIDGE is not an object of its own in 3D: it reaches the pipeline only
#: as its HOUSE's ``ridge`` param. The app re-derives the ridge item's points
#: whenever the house turns, so a record of its own would change GEOMETRY on a
#: rotation of the house (measured: on 400 of 400) — "rotate → transform only"
#: would be false for the one item a house owns.
_NO_RECORD_KINDS = frozenset({"ROOF_RIDGE"})


class SkipReason(StrEnum):
    """Why an item got no record — a stable CODE. A UI maps it to a ``tr()`` text;
    the value is never shown to the user as it is."""

    #: Building its record raised (malformed metadata, geometry that is not finite …).
    RECORD_FAILED = "record_failed"
    #: Another item, lower in the paint order, already has this id.
    DUPLICATE_ID = "duplicate_id"
    #: Its outline cannot be turned into regions a builder can build
    #: (``core.scene3d.is_buildable_region``), not even after resolving it.
    OUTLINE_UNBUILDABLE = "outline_unbuildable"
    #: Its outline is too LARGE for the 3D view: more vertices than one item may
    #: have (``core.scene3d.polygon.MAX_ITEM_VERTICES``), or turning it into
    #: regions would cost more than the work bound (``MAX_REGION_WORK``). Nothing
    #: is wrong with its shape; the 2D plan shows it as it is.
    OUTLINE_TOO_LARGE = "outline_too_large"
    #: One of its lengths — height, width, radius, a coordinate, its position —
    #: is out of range: beyond ``core.scene3d.MAX_LENGTH_CM`` or infinite, or a
    #: height below ``MIN_HEIGHT_CM`` (a hand-edited plan).
    OUT_OF_RANGE = "out_of_range"


@dataclass(frozen=True, slots=True)
class SkippedItem:
    """A visible, typed canvas item that got no record, and why.

    Plain data, safe to keep: ``reason`` is a ``SkipReason`` code; of an exception
    it holds the type's name and the message as strings, never the exception
    itself (its traceback would keep the scene and the item alive). Two reports of
    the same failure are equal.
    """

    item_id: str
    kind: str
    reason: SkipReason
    error_type: str = ""  # the exception's class name; "" when none was raised
    error_message: str = ""


#: What has been logged already — one line per item and KIND of failure (the
#: reason and the exception's type), not one per edit: the pipeline snapshots on
#: every change, and an exception message may carry a value that changes with
#: every mouse move. Bounded in memory AND in volume: once it is full nothing new
#: is logged for the rest of the session (one line says so) — clearing it instead
#: would log every broken item again on every snapshot.
_reported: set[tuple[str, str, str]] = set()
_REPORTED_MAX = 2048
_NO_MORE = ("", "no more", "")  # the marker of "the one line that says so was written"
#: The LOG's words for a code (English, for whoever reads ``app.log``; never shown in the UI).
_LOG_TEXT: dict[SkipReason, str] = {
    SkipReason.RECORD_FAILED: "its record could not be built",
    SkipReason.DUPLICATE_ID: "another item already has this id",
    SkipReason.OUTLINE_UNBUILDABLE: "its outline cannot be made into regions a builder can build",
    SkipReason.OUTLINE_TOO_LARGE: "its outline is too large for the 3D view",
    SkipReason.OUT_OF_RANGE: "one of its lengths is outside what a plan can hold",
}


def _report(skipped: SkippedItem, into: list[SkippedItem] | None,
            error: BaseException | None = None) -> None:
    """Hand a skipped item to the caller's list (every time) and to the log (once).
    ``error``, the exception itself, goes to the log only."""
    if into is not None:
        into.append(skipped)
    key = (skipped.item_id, str(skipped.reason), skipped.error_type)
    if key in _reported:
        return
    if len(_reported) >= _REPORTED_MAX:
        if _NO_MORE not in _reported:
            _reported.add(_NO_MORE)
            _log.warning("3D snapshot: %d different failures have been logged; further ones are "
                         "left out of the log (they are still reported to the caller)",
                         _REPORTED_MAX)
        return
    _reported.add(key)
    line = "3D snapshot: %s item %r is left out of the 3D view: %s [%s]"
    words = (skipped.kind, skipped.item_id, _LOG_TEXT[skipped.reason], skipped.reason.value)
    if error is not None:
        _log.error(line, *words, exc_info=error)
    elif skipped.error_message:
        _log.warning(line + " — %s", *words, skipped.error_message)
    else:
        _log.warning(line, *words)


@dataclass(frozen=True, slots=True)
class _Refused:
    """Why an outline has no regions a builder can build — the words of the report."""

    why: str


#: Refused for its SIZE: it has more vertices than one item's outline may have, or
#: turning it into regions would cost more than the work bound. Nothing else is
#: tried on such an outline — no other reading of it is smaller.
_TOO_LARGE: Final = _Refused(
    "the outline is too large for the 3D view: beyond what one item's outline may hold "
    f"(core.scene3d.polygon.MAX_ITEM_VERTICES = {MAX_ITEM_VERTICES:,} vertices) or cost "
    "(MAX_REGION_WORK units of work)")
_NO_READING: Final = _Refused("the outline cannot be made into regions a builder can build")


@lru_cache(maxsize=4096)
def _circle_ring(radius_cm: float) -> Ring:
    """A circle's item-local footprint: ``circle_footprint`` about the origin.

    Cached: a plan has few distinct radii, and the ring is a function of the
    radius alone (a circle's footprint does not turn with its item).
    """
    return tuple((quantize_cm(x), quantize_cm(y))
                 for x, y in circle_footprint(0.0, 0.0, radius_cm))


def _quantized(ring: Any) -> Ring:
    return tuple((quantize_cm(x), quantize_cm(y)) for x, y in ring)


class _UnbuildableOutline(ValueError):
    """An outline that cannot be turned into regions a builder can build."""


class _OutlineTooLarge(_UnbuildableOutline):
    """… because of its SIZE (``SkipReason.OUTLINE_TOO_LARGE``)."""


# What the CLIPPER costs, in the work units of ``core.scene3d.polygon`` (about a
# nanosecond each on the development box). Its work is not ours to count, so it is
# priced from what it depends on — all of it known BEFORE the clipper is asked:
# the vertices; the STACK (``stack_height``: a sweep line carries every edge it
# crosses, so teeth standing side by side cost their number squared without
# crossing anything); and the pairs of segments that cross or lie within a
# stroke's reach of each other (``touching_pairs``). Each price is the dearest
# case measured (``scripts/measure_region_work.py`` prints price against cost for
# every family it knows, and fails when one costs more than 12 times its price).
# What a price cannot see is HOW the clipper is asked: a union as a tree costs by
# the rings it joins — so no union is (``_union_rings``).
_CLIP_UNITS: Final = 10_000  # any call of the clipper
_OFFSET_POINT_UNITS: Final = 2_500  # inflating a path, a band along rings: per point …
_OFFSET_STACK_UNITS: Final = 70  # … per point and edge in the stack (a path)
_BAND_STACK_UNITS: Final = 420  # … (a band, and the difference it is cut out with)
_OFFSET_NEAR_UNITS: Final = 600  # … per pair of segments whose strokes can overlap
_OFFSET_CROSSING_UNITS: Final = 5_000  # … and per pair whose centre lines cross
_UNION_VERTEX_UNITS: Final = 500  # a union: per vertex …
_UNION_STACK_UNITS: Final = 15  # … per vertex and edge in the stack
_UNION_CROSSING_UNITS: Final = 600  # … per pair of edges that cross
_STRICT_VERTEX_UNITS: Final = 1_000  # the same with StrictlySimple (``_strict_rings``): per vertex …
_STRICT_SQUARE_UNITS: Final = 3  # … per vertex² of each ring that comes back (it compares them all)
_STRICT_CROSSING_UNITS: Final = 2_500  # … per pair of edges that cross
_BAND_CROSSING_UNITS: Final = 8_000  # a band along the union's rings: per such pair
_OWN_BAND_CROSSING_UNITS: Final = 30_000  # a band along the drawn rings themselves: per such pair
_RING_UNITS: Final = 2_000  # reading a ring the clipper made …
_RING_VERTEX_UNITS: Final = 1_000  # … per vertex: off its grid, onto the record's, its area
#: A square join reaches half the stroke width times the square root of two from the
#: centre line — how far a segment's part of the stroke can lie from the segment.
_SQUARE_JOIN: Final = 0.7072


def _pay_for_reading(made: list[Any], budget: WorkBudget) -> None:
    """Rings as the clipper returned them: counted — all of them together, which
    costs nothing — and paid for BEFORE one of them is read. More vertices than
    one item may have are refused outright."""
    vertices = sum(len(ring) for ring in made)
    if vertices > MAX_ITEM_VERTICES:
        budget.refuse()
    budget.spend(_RING_UNITS * len(made) + _RING_VERTEX_UNITS * vertices)


def _region_vertices(regions: tuple[Region, ...] | _Refused) -> int:
    """How many vertices an answer of ``_polyline_regions`` holds (a refusal: none)."""
    if isinstance(regions, _Refused):
        return 0
    return sum(len(outer) + sum(len(hole) for hole in holes) for outer, holes in regions)


#: How far a region whose rings TOUCH is drawn in, in clipper units (1/1000 cm):
#: 0.002 cm, twenty micrometres. Where two parts of a resolved outline meet in a
#: single point — the pocket of a self-crossing polygon touching its outer ring,
#: a neck pinched to nothing — no triangulation is possible as it stands; drawn
#: in by this much the parts stand a hair apart and each can be built. Only such
#: outlines pay it; the rest keep their exact coordinates.
_SEPARATION: int = 2
#: A resolved outline is compared with the DRAWN one on a lattice of this many
#: points a side; points closer to a drawn edge than the tolerance are not
#: judged (the separation and the clipper grid both live there).
_LATTICE: int = 48
_OUTLINE_TOLERANCE_CM = 0.01


def _to_grid(ring: Ring) -> list[tuple[int, int]]:
    return [(round(x * CLIPPER_SCALE), round(y * CLIPPER_SCALE)) for x, y in ring]


def _tree_regions(tree: Any) -> tuple[Region, ...]:
    """The regions of a pyclipper PolyTree: every outer ring with the holes
    pyclipper itself says are its own — the hierarchy is the clipper's, not a
    guess from a point test. An island inside a hole is a region of its own.
    Orientation is set from the ring's PLACE in the tree, never read off the
    contour: pyclipper hands a split-off piece out the wrong way round now and
    then (measured)."""
    regions: list[Region] = []
    outers = list(tree.Childs)
    at = 0
    while at < len(outers):  # in the order they are found — and no ``pop(0)``: that is the list, squared
        node = outers[at]
        at += 1
        outer = _quantized((x / CLIPPER_SCALE, y / CLIPPER_SCALE) for x, y in node.Contour)
        holes: list[Ring] = []
        for child in node.Childs:
            hole = _quantized((x / CLIPPER_SCALE, y / CLIPPER_SCALE) for x, y in child.Contour)
            if len(hole) >= 3 and ring_area(hole) != 0.0:
                holes.append(hole if ring_area(hole) < 0.0 else hole[::-1])
            outers.extend(child.Childs)
        if len(outer) >= 3 and ring_area(outer) != 0.0:
            regions.append((ccw(outer), tuple(holes)))
    return tuple(regions)


def _in_order(regions: tuple[Region, ...]) -> tuple[Region, ...]:
    """``regions`` in THE order a record carries them: by the smallest vertex of
    each outer ring (x, then y); outer rings that share it, by their vertices as
    they come. A stated property, so that a record does not depend on the order
    in which the clipper happened to hand its rings out — which changed when the
    plain union went from a tree to a list (review of fix round 4: seven
    outlines, the same regions in another order). Every answer of the clipper is
    put in this order BEFORE it is judged: regions are paid for and cut one
    after the other out of one budget, so their order decides where a budget
    runs out. A region's holes stay as the reading gave them — the cut joins
    them from the right, and holes that reach equally far right in that order."""
    return tuple(sorted(regions, key=lambda region: (min(region[0]), region[0])))


def _tree_rings(tree: Any) -> list[Any]:
    """Every contour of a PolyTree, as the clipper holds it (nothing is read)."""
    rings: list[Any] = []
    nodes = list(tree.Childs)
    while nodes:
        node = nodes.pop()
        rings.append(node.Contour)
        nodes.extend(node.Childs)
    return rings


def _buildable(regions: tuple[Region, ...], budget: WorkBudget | None = None) -> bool:
    """True when every region can be built; False at the first whose SHAPE cannot.

    All of them are paid out of ONE budget (the item's; one of its own when
    none is given — ``core.scene3d.polygon.pay_for_region``): a region is not
    looked at unless the least it can cost is still there, it is cut out of
    what is LEFT, and what it cost is paid when it is known — a thousand regions
    that each fit the bound do not fit it together. A region or a sum beyond
    the bound raises ``RegionTooLargeError``: nothing else is tried on an
    outline like that.
    """
    budget = budget if budget is not None else WorkBudget("the regions of an outline")
    for outer, holes in regions:
        pay_for_region(outer, holes, budget)  # what asking costs — out of what the item has left
        if not is_buildable_region(outer, holes):  # THE predicate, asked of every region
            return False
    return True


def _inside_ring(px: Any, py: Any, ring: Ring) -> Any:
    """Even-odd point-in-ring for arrays of points."""
    inside = np.zeros(len(px), dtype=bool)
    x1, y1 = ring[-1]
    for x2, y2 in ring:
        if y1 != y2:
            inside ^= ((y1 > py) != (y2 > py)) & (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1)
        x1, y1 = x2, y2
    return inside


def _matches_outline(outline: Ring, regions: tuple[Region, ...]) -> bool:
    """True when ``regions`` cover what the DRAWN outline fills by the non-zero
    rule and nothing else — checked where it can be checked without trusting
    the clipper: at ``_LATTICE`` x ``_LATTICE`` points over the outline's
    bounding box, each one's winding number about the drawn ring against its
    being inside a region. A reading that put a hole where there is ground, or
    lost a piece, differs at every lattice point of that piece."""
    xs = [x for x, _y in outline]
    ys = [y for _x, y in outline]
    steps = (np.arange(_LATTICE) + 0.5) / _LATTICE
    gx, gy = np.meshgrid(min(xs) + steps * (max(xs) - min(xs)), min(ys) + steps * (max(ys) - min(ys)))
    px, py = gx.ravel(), gy.ravel()
    winding = np.zeros(len(px), dtype=np.int64)
    judged = np.ones(len(px), dtype=bool)
    x1, y1 = outline[-1]
    for x2, y2 in outline:
        dx, dy = x2 - x1, y2 - y1
        if dx or dy:
            along = np.clip(((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy), 0.0, 1.0)
            judged &= np.hypot(px - (x1 + along * dx), py - (y1 + along * dy)) >= _OUTLINE_TOLERANCE_CM
        if y1 != y2:
            crossed = ((y1 > py) != (y2 > py)) & (px < dx * (py - y1) / dy + x1)
            winding += np.where(crossed, 1 if y2 > y1 else -1, 0)
        x1, y1 = x2, y2
    covered = np.zeros(len(px), dtype=bool)
    for outer, holes in regions:
        mine = _inside_ring(px, py, outer)
        for hole in holes:
            mine &= ~_inside_ring(px, py, hole)
        covered |= mine
    return bool(np.all((winding != 0)[judged] == covered[judged]))


def _union_rings(subject: list[list[tuple[int, int]]], fill: int, *, strictly_simple: bool) -> list[Any]:
    """The union of ``subject`` under ``fill`` as a FLAT list of rings
    (``Execute``): outer rings counter-clockwise, holes clockwise. [] when no
    ring of ``subject`` has an area.

    A union is NEVER asked for a tree. As a PolyTree (``Execute2``) the clipper
    looks through every ring it has made each time two of them are joined: its
    cost follows the rings and the joins, and the price of a union is read off
    vertices, stack and crossings. Twice that was seconds inside the budget —
    with ``StrictlySimple``, a two-level zigzag of 340 vertices, 3.6 s (review
    of fix round 3); without it, a slab with 720 bridged holes, 5.3 s, for a
    tree that was flattened on the next line (review of fix round 4; pyclipper
    alone, 801 rings: 23 ms as a list, 7,078 ms as a tree). Which hole belongs
    to which ring is ``group_rings``' to say — counted, and paid before it runs."""
    clipper = pyclipper.Pyclipper()
    clipper.StrictlySimple = strictly_simple
    try:
        clipper.AddPaths(subject, pyclipper.PT_SUBJECT, True)
    except pyclipper.ClipperException:
        return []
    return list(clipper.Execute(pyclipper.CT_UNION, fill, fill))


def _plain_rings(subject: list[list[tuple[int, int]]], fill: int) -> list[Any]:
    """The plain union's rings (``_union_rings``): what the outline covers, its
    rings as they lie — they may touch themselves and each other."""
    return _union_rings(subject, fill, strictly_simple=False)


def _strict_rings(subject: list[list[tuple[int, int]]], fill: int) -> list[Any]:
    """The union's rings with ``StrictlySimple`` (``_union_rings``): rings that
    do not touch themselves."""
    return _union_rings(subject, fill, strictly_simple=True)


def _grouped(made: list[Any], budget: WorkBudget) -> tuple[Region, ...]:
    """Rings on the clipper grid, oriented, → regions: paid for, read, and sorted
    by ``group_rings`` out of ``budget``. () when they cannot be sorted (a hole
    in no outer ring: the reading does not hold)."""
    _pay_for_reading(made, budget)
    rings = [_quantized((x / CLIPPER_SCALE, y / CLIPPER_SCALE) for x, y in ring) for ring in made]
    try:
        return _in_order(group_rings(rings, budget))
    except RegionTooLargeError:
        raise
    except ValueError:
        return ()


def _band_tree(subject: list[list[tuple[int, int]]], fill: int,
               band: list[list[tuple[int, int]]]) -> Any:
    """``subject``'s union under ``fill`` MINUS a band ``_SEPARATION`` wide along
    every ring of ``band``, as a pyclipper PolyTree (``Execute2``). None when no
    ring of ``subject`` has an area.

    The ONE call that asks the clipper for a hierarchy, made only by the two
    band readings of ``_resolved_regions``, which read it (``_tree_regions``:
    whose hole is whose comes from the clipper, where a point test would have
    to guess between parts a hair apart). Its price does not count its rings,
    and need not: a tree is dear where rings are JOINED (``_union_rings``), and
    the band cuts every ring a hair free of every other — nothing is left to
    join. Measured, pyclipper alone, the same call as a list and as a tree: 801
    rings in and out 1.8 / 3.0 ms; 1,600 rings out 123 / 144 ms; 800 diamonds
    touching tip to tip 28 / 28 ms; bridges walked back 1 to 8 grid units beside
    the way out, 800 of them, 19 to 33 ms either way."""
    clipper = pyclipper.Pyclipper()
    try:
        clipper.AddPaths(subject, pyclipper.PT_SUBJECT, True)
    except pyclipper.ClipperException:
        return None
    stroke = pyclipper.PyclipperOffset()
    stroke.AddPaths(band, pyclipper.JT_SQUARE, pyclipper.ET_CLOSEDLINE)
    clipper.AddPaths(stroke.Execute(_SEPARATION), pyclipper.PT_CLIP, True)
    return clipper.Execute2(pyclipper.CT_DIFFERENCE, fill, pyclipper.PFT_NONZERO)


def _resolved_regions(rings: list[list[tuple[int, int]]], fill: int, outline: Ring | None = None,
                      budget: WorkBudget | None = None,
                      crossings: int = 0) -> tuple[Region, ...] | _Refused:
    """Rings on the clipper grid → regions a builder can build, or why not.

    Three readings of the rings' union under ``fill``, the first that holds:

    1. the union with ``StrictlySimple`` — rings that do not touch themselves,
       the outline's own vertices — as a flat list (``_strict_rings``), sorted
       into outer rings and their holes by ``group_rings``;
    2. the plain union (``_plain_rings``, a flat list as well) with a band of
       ``_SEPARATION`` cut away along its rings — for parts that meet in a
       point: drawn apart by a hair, each can be built. Read off a tree
       (``_band_tree``), the only one this function asks for;
    3. the rings themselves with that band cut away along every one of THEM —
       no reading of the clipper's is trusted, at the price of a cut along every
       drawn edge, also those inside the solid.

    "Holds" is checked, not assumed, because pyclipper's answer for an outline
    that retraces or touches itself is not always right (measured: a piece
    handed out the wrong way round, a hole hung under the wrong ring): every
    region must be buildable (``is_buildable_region``), and — for a drawn
    ``outline`` — the regions must cover exactly what the outline fills
    (``_matches_outline``); for a stroke (no outline) the regions' area must be
    the rings' own, less at most the band.

    ``()`` when nothing with an area is there; ``_NO_READING`` when no reading
    holds. The regions of a reading stand in a stated order (``_in_order``).

    Every call of the clipper, every ring read and every check is PAID out of
    ``budget`` (the item's; one of its own when none is given) before it runs —
    priced from the rings' vertices, their stack and ``crossings``, the pairs of
    their edges that cross (``touching_pairs``; the caller counts them, because
    only the caller knows that a stroke's rings do not cross). A reading the
    budget does not cover raises ``RegionTooLargeError``, and so does a region
    that is refused for its size: the next reading would only be refused again.
    The dearest reading is the last — a band along every drawn edge is 30,000
    units for each crossing (800 points scribbled across a plan cross 73,000
    times; that reading alone took ten seconds).
    """
    budget = budget if budget is not None else WorkBudget("resolving an outline")
    vertices = sum(len(ring) for ring in rings)
    sweep = stack_height(rings, closed=True) * vertices
    # the first reading is two unions, plain and strict, and both are paid before either
    # runs: an outline that cannot afford them is not handed to the clipper at all
    budget.spend(2 * _CLIP_UNITS + (_UNION_VERTEX_UNITS + _STRICT_VERTEX_UNITS) * vertices
                 + 2 * _UNION_STACK_UNITS * sweep
                 + (_UNION_CROSSING_UNITS + _STRICT_CROSSING_UNITS) * crossings)
    paths = _plain_rings(rings, fill)
    if not paths:
        return ()
    _pay_for_reading(paths, budget)
    made = sum(len(path) for path in paths)
    scale2 = float(CLIPPER_SCALE) ** 2
    area = sum(pyclipper.Area(ring) for ring in rings) / scale2  # a stroke's rings are oriented
    rim = (sum(math.dist(path[i - 1], path[i]) for path in paths for i in range(len(path)))
           * (2.0 * _SEPARATION + 2.0) / scale2)  # both sides of the band, and the grid's own unit

    def read(tree: Any) -> tuple[Region, ...]:
        _pay_for_reading(_tree_rings(tree), budget)
        return _in_order(_tree_regions(tree))

    def holds(regions: tuple[Region, ...], *, drawn_in: bool) -> bool:
        if not regions or not _buildable(regions, budget):
            return False
        if outline is not None:
            budget.spend(_LATTICE * _LATTICE * (_OUTLINE_CHECK_UNITS * len(outline)
                                                + _REGION_CHECK_UNITS * _region_vertices(regions)))
            return _matches_outline(outline, regions)
        got = regions_area(regions)
        return bool((area - rim if drawn_in else area - 1e-6) <= got <= area + 1e-6)

    budget.spend(_STRICT_SQUARE_UNITS * sum(len(path) ** 2 for path in paths))
    regions = _grouped(_strict_rings(rings, fill), budget)
    if holds(regions, drawn_in=False):
        return regions
    for band, along, per_crossing in ((paths, made, _BAND_CROSSING_UNITS),
                                      (rings, vertices, _OWN_BAND_CROSSING_UNITS)):
        budget.spend(_CLIP_UNITS + per_crossing * crossings + along * (
            _OFFSET_POINT_UNITS + _BAND_STACK_UNITS * stack_height(band, closed=True)))
        regions = read(_band_tree(band, fill, band))
        if holds(regions, drawn_in=True):
            return regions
    return _NO_READING


def _stroke_regions(path: Ring, width_cm: float,
                    budget: WorkBudget) -> tuple[Region, ...] | _Refused:
    """``_polyline_regions``, paying into ``budget`` — in this order, each step
    paid for before it runs:

    1. the pairs of the centre line's segments, counted on arrays (the count is
       the square of the points, and is itself paid first): those that cross,
       and those near enough for their strokes to overlap;
    2. the inflation, priced from the points, their stack and those pairs — the
       clipper is not asked about a path it would take seconds to answer;
    3. the rings that came back, ALL of them together, counted before one is
       read (a scribble of 800 points comes back as 53,000 rings);
    4. sorting them — every hole asks every outer ring, the product is the price;
    5. every region's cut, out of the same budget.
    """
    if width_cm <= 0.0:
        return ()
    reach = _SQUARE_JOIN * width_cm
    near, crossings = touching_pairs(path, budget, closed=False, reach=reach)
    budget.spend(_CLIP_UNITS + _OFFSET_NEAR_UNITS * near + _OFFSET_CROSSING_UNITS * crossings
                 + len(path) * (_OFFSET_POINT_UNITS + _OFFSET_STACK_UNITS
                                * stack_height((path,), closed=False, reach=reach, flat=False)))
    made = polyline_footprint(list(path), width_cm)
    _pay_for_reading(made, budget)
    rings = [_quantized(ring) for ring in made]
    try:
        regions = _in_order(group_rings(rings, budget))
    except RegionTooLargeError:
        raise
    except ValueError:
        regions = None
    if regions is not None and _buildable(regions, budget):
        return regions
    # the stroke's rings are oriented (outers counter-clockwise, holes clockwise):
    # their non-zero union is the stroke. They touch; they do not cross
    return _resolved_regions([_to_grid(ring) for ring in rings if len(ring) >= 3],
                             pyclipper.PFT_NONZERO, budget=budget)


@ring_keyed(vertices=lambda path, _width_cm: len(path), holds=_region_vertices)
def _polyline_regions(path: Ring, width_cm: float) -> tuple[Region, ...] | _Refused:
    """A polyline's item-local stroke as buildable regions, or why it has none.

    The centre line inflated by half its width (``polyline_footprint`` —
    pyclipper, a 1/1000 cm grid), its rings taken as they come and sorted into
    outer rings and the holes they enclose: a closed fence is one outer and one
    hole.

    Everything this costs is paid out of ONE budget of ``MAX_REGION_WORK`` units,
    each step before it runs (``_stroke_regions``): a stroke that is refused for
    its size — before the clipper is asked, when its rings come back, or while a
    region of it is cut — is not looked at again. Refusing costs less than
    building, and the refusal is remembered like any other answer.

    A stroke that is not buildable for another reason goes through
    ``_resolved_regions``. That is no rare path: two butt ends that meet corner
    to corner — a fence drawn back to a point half its width beside its start —
    make pyclipper return ONE ring that touches itself, and every such fence
    takes it (the reading that holds is the stroke drawn in by ``_SEPARATION``:
    its outline 0.002 cm inside the drawn one, its two ends a hair apart). The
    regions are checked like any other; there is no flag for it in the record —
    a stroke's rings never were the drawn vertices, and what builds a fence or a
    wall reads ``path`` and ``path_width_cm``.
    """
    try:
        return _stroke_regions(path, width_cm, WorkBudget("the stroke of a path"))
    except RegionTooLargeError:
        return _TOO_LARGE


def _without_repeats(ring: Ring) -> Ring:
    """``ring`` without a vertex placed twice in a row (a doubled click, a closing
    vertex that repeats the first): the same outline, said once. The FIRST of
    such a run is the one kept, so the ring still starts where it was drawn."""
    kept: list[tuple[float, float]] = []
    for point in ring:
        if not kept or point != kept[-1]:
            kept.append(point)
    while len(kept) > 1 and kept[-1] == kept[0]:
        kept.pop()
    return tuple(kept) if len(kept) != len(ring) else ring


#: What comparing ONE reading of a resolved outline with the drawn one costs, in
#: ``core.scene3d``'s work units (``_matches_outline``): per lattice point and
#: vertex of the drawn outline, and per lattice point and vertex of the reading's
#: regions. Paid for each reading that is compared, so an outline that crosses
#: itself is resolved while the budget lasts — about 2,500 vertices for one
#: reading, about 1,000 for all three.
_OUTLINE_CHECK_UNITS: Final = 20
_REGION_CHECK_UNITS: Final = 5


@lru_cache(maxsize=4096)  # of rings of 4 or 24 vertices: here a bound on entries bounds the memory
def _convex_region(ring: Ring) -> bool:
    """THE predicate for a ring that is convex BY CONSTRUCTION — a circle's, an
    ellipse's, a rectangle's: buildable when arithmetic says it is strictly
    convex on the record grid too (``is_convex_ring``; no cut — a date scrub
    gives every dated plant a new radius per tick, and cutting each 24-gon made
    that snapshot 2.9 times slower), and only a ring that is NOT is asked the
    cut: a shape squeezed to a few grid steps, whose verdict stays what it was."""
    return is_convex_ring(ring) or is_buildable_region(ring)


#: From this radius on a circle's 24-gon needs no look at its corners either: they
#: turn by 15 degrees and the record grid moves a vertex by 1e-7 cm, so the ring is
#: strictly convex with four orders of magnitude to spare (pinned against
#: ``is_convex_ring`` from here to 10 km). The floor of "a circle is a circle".
_ROUND_FROM_CM: Final = 1e-3


@lru_cache(maxsize=4096)
def _circle_regions(radius_cm: float) -> tuple[Region, ...] | _Refused:
    """A circle's footprint ring as its one region — judged like every other
    shape (a radius of 2e-7 cm leaves a ring on the record grid that is no
    polygon at all): by its radius from ``_ROUND_FROM_CM`` on, below it by its
    corners, and by the cut when those do not say."""
    ring = _circle_ring(radius_cm)
    return ((ring, ()),) if radius_cm >= _ROUND_FROM_CM or _convex_region(ring) else _NO_READING


def _outline_regions(ring: Ring,
                     budget: WorkBudget) -> tuple[tuple[Region, ...] | _Refused, bool]:
    """``_polygon_regions``, paying into ``budget``: the ring as it is when it can
    be cut — its SIZE judged before the simplicity test or anything else that
    costs — and otherwise resolved, after counting how often it crosses itself:
    that count is what the clipper's work on it depends on."""
    if len(ring) > MAX_ITEM_VERTICES:
        budget.refuse()
    ring = _without_repeats(ring)
    if len(ring) < 3:
        return (), False
    outer = ccw(ring)
    if _buildable(((outer, ()),), budget):  # a simple polygon that was cut, and the cut proven
        return ((outer, ()),), False
    _near, crossings = touching_pairs(ring, budget, closed=True)
    return _resolved_regions([_to_grid(ring)], pyclipper.PFT_NONZERO, ring, budget, crossings), True


@ring_keyed(holds=lambda answer: _region_vertices(answer[0]))
def _polygon_regions(ring: Ring) -> tuple[tuple[Region, ...] | _Refused, bool]:
    """A drawn polygon as ``(regions, resolved)`` — or, for regions, why it has none.

    A simple polygon is itself, turned counter-clockwise, vertex for vertex
    (``resolved`` False) — also when a vertex was merely placed twice in a row.
    One that crosses or touches itself is RESOLVED: the non-zero rule — the rule
    the 2D shadow fills the caster's own footprint with — so the 3D solid stands
    on the ground the 2D shadow treats as built on; its vertices then sit on the
    clipper grid, it may be one ring, several, or rings with holes, and parts
    that met in a point are drawn in by ``_SEPARATION``. (The canvas PAINTS such
    a polygon with Qt's odd-even rule: the same for a bow-tie, not for a
    pentagram, whose centre the shadow fills and the paint leaves open.)

    One budget of ``MAX_REGION_WORK`` units pays for all of it
    (``_outline_regions``); an outline that is refused for its size — as a ring,
    or because resolving it would cost more than is left — is never resolved,
    and the refusal is remembered like any other answer.
    """
    try:
        return _outline_regions(ring, WorkBudget("a drawn outline"))
    except RegionTooLargeError:
        return _TOO_LARGE, False


def clear_outline_cache() -> None:
    """Drop everything ``snapshot_records`` remembers about outlines — LIVE and
    stale: the regions of every polygon and stroke, their cuts, areas and ring
    facts (every ``core.scene3d.polygon.ring_keyed`` memory), and the rings and
    verdicts of circles. The next snapshot is a first one: every outline is
    judged and cut again.

    What a snapshot asks for is never dropped while snapshots go on, so a plan
    that is gone stays remembered until two more snapshots have run — and with
    no 3D view open, none does (measured: 160 polygons of 1,000 vertices,
    321,280 vertices held, about 30 MB). Call this when the document changes
    (a plan is opened, a new one made) and when the 3D view closes. It is also
    the way to snapshot a SECOND scene in one process without the first one's
    answers in the way: the memories serve one snapshotting scene
    (``core.scene3d.polygon.snapshot_generation``). Safe at any time, also
    while nothing is held; the plant builder's ``clear_shape_cache`` is the
    same call for plant shapes."""
    clear_ring_memories()
    for cache in (_circle_ring, _circle_regions, _convex_region):
        cache.cache_clear()


@lru_cache(maxsize=1024)
def _material(key: str, fill: Rgba | None, stroke: Rgba | None, pattern: str | None,
              paint: Paint | None = None) -> Material:
    return Material(key, fill, stroke, pattern, paint)


#: Kinds that are never painted on the ground, height or no height: a plant is a
#: plant — without a height it is the plant builder's placeholder, never its 2D
#: sprite laid flat on the lawn.
_NEVER_ON_THE_GROUND: Final = PLANT_KINDS


@lru_cache(maxsize=256)
def _paint(width_cm: float, style: str, cap: str, join: str, opacity: float,
           turn_deg: float = 0.0) -> Paint:
    return Paint(
        stroke_width_cm=width_cm,
        stroke_style=style if style in PEN_STYLES else "SolidLine",  # a custom dash pattern
        stroke_cap=cap if cap in PEN_CAPS else "SquareCap",
        stroke_join=join if join in PEN_JOINS else "BevelJoin",
        opacity=min(max(opacity, 0.0), 1.0),
        rotation_deg=turn_deg,
    )


def _paint_of(item: Any, shape: str, turn_deg: float = 0.0) -> tuple[Paint, Any]:
    """How the canvas paints ``item``'s surface (``core.scene3d.Paint``), and its
    pen's colour (None for an item that strokes nothing) — read from the LIVE pen:
    it is what ``paint()`` strokes with, whatever the item's stored
    ``stroke_color`` says (``core.item_look`` keeps the two in step; a writer
    that does not is not painted from). A polyline's pen width is its geometry
    (``path_width_cm``) and is not repeated here. ``turn_deg``: the turn the
    record's transform does not carry — a circle's (``Paint.rotation_deg``)."""
    pen = item.pen()
    style = pen.style().name
    width = 0.0 if shape == OUTLINE_POLYLINE else float(pen.widthF())
    return (_paint(width, style, pen.capStyle().name, pen.joinStyle().name,
                   float(item.effectiveOpacity()), turn_deg),
            pen.color() if style != "NoPen" else None)


def _drawn_only(outline: ItemOutline, frame: LocalFrame, made: list[Ring]
                ) -> tuple[tuple[Region, ...], Ring, float | None, float | None, bool]:
    """What ``_regions_of`` returns, for an outline it REFUSED — without regions:
    only what is drawn (a polyline's centre line and width; a polygon's ring is the
    caller's to add, as ``Record.outline``). For a shape that has nothing else to
    paint with — a sliver of a rectangle, a circle of no radius — None. ``made``:
    the outline in the record's frame as ``_regions_of`` made it before it
    refused — it is not made a second time."""
    if outline.shape == OUTLINE_POLYLINE:
        ring = made[0] if made else frame.local_ring(outline.points)
        return (), ring, outline.width_cm, None, False
    return (), (), None, None, False


def _rgba(color: Any) -> Rgba | None:
    if isinstance(color, str):
        color = QColor(color)
    if isinstance(color, QColor) and color.isValid():
        red, green, blue, alpha = color.getRgb()
        return (red, green, blue, alpha)
    return None


def _finite_ring(ring: Ring) -> bool:
    return math.isfinite(sum(x + y for x, y in ring))


def _frame_of(item: Any, anchor: tuple[float, float], *, rotatable: bool) -> LocalFrame:
    """The item's scene transform — Qt's ``sceneTransform()``, never a
    re-derivation from pos / rotation / transformOriginPoint — split about ``anchor``."""
    matrix = item.sceneTransform()
    return local_frame(matrix.m11(), matrix.m12(), matrix.m21(), matrix.m22(),
                       matrix.dx(), matrix.dy(), anchor[0], anchor[1], rotatable=rotatable)


def _ridge_param(house_frame: LocalFrame, ridge: Any) -> ParamValue | None:
    """A HOUSE's ridge ends in the HOUSE's local frame, from the LIVE ridge item
    (ADR-046: an edited ridge is the ridge), or None when there is no usable one.

    The ridge is ANOTHER item's geometry, and the app re-writes its points by
    ``+ delta`` on every move of the house, so its float error grows with each
    move. Measured: 1.1e-10 cm after 20,000 random moves — three orders of
    magnitude below the record grid, so it never reaches the HOUSE's geometry
    signature (0 changes in those 20,000 moves; pinned over 1,000 by
    ``test_scene3d_snapshot.py::TestHouseRidge``).
    """
    if not isinstance(ridge, PolylineItem):
        return None
    points = ridge.points
    if len(points) < 2:
        return None
    ends: list[tuple[float, float]] = []
    for point in (points[0], points[-1]):
        scene_point = ridge.mapToScene(point)
        end = house_frame.local_from_scene(scene_point.x(), scene_point.y())  # on the record grid
        if not (math.isfinite(end[0]) and math.isfinite(end[1])):
            return None
        ends.append(end)
    return (ends[0], ends[1])


def _drawn_vertices(item: Any) -> int:
    """How many vertices the item's outline holds as it is STORED — asked before
    one of them is read (``item_outline`` reads them all, and a plan file can
    hold a polyline of 200,000 points). 0 for the shapes whose vertex count is
    the code's and not the plan's: a rectangle's 4, an ellipse's and a circle's 24."""
    if isinstance(item, PolylineItem):
        return item.point_count  # a count: ``len(item.points)`` would copy all of them first
    if isinstance(item, PolygonItem):
        return int(item.polygon().count())  # Qt shares the polygon's data: no copy either
    return 0


def _regions_of(outline: ItemOutline, frame: LocalFrame, made: list[Ring] | None = None
                ) -> tuple[tuple[Region, ...], Ring, float | None, float | None, bool]:
    """``(regions, path, path_width_cm, radius_cm, resolved)`` of an outline in
    the record's frame; no regions means the item covers no ground, ``resolved``
    that the regions are not the drawn outline (``PARAM_OUTLINE_RESOLVED``).
    Raises ``ValueError`` for geometry that is not finite and
    ``_UnbuildableOutline`` for an outline no builder could build
    (``_OutlineTooLarge`` when the reason is its size). ``made``, when given,
    receives the outline's points in the record's frame once they are made — the
    ONE conversion of a tick: a caller that needs the drawn ring as well (a flat
    item's, also when this function refuses the outline) reads it there."""
    if outline.shape == OUTLINE_CIRCLE:
        radius = outline.radius_cm
        if radius is None or math.isnan(radius):
            raise ValueError(f"a circle of radius {radius!r}")
        if abs(radius) > MAX_LENGTH_CM:  # before a ring of that size is made
            raise RecordRangeError(f"a radius of {radius!r} cm is beyond ±{MAX_LENGTH_CM:g} cm")
        if radius <= 0.0:
            return (), (), None, None, False
        radius = quantize_cm(radius)
        disc = _circle_regions(radius)
        if isinstance(disc, _Refused):
            raise _UnbuildableOutline(f"a circle of radius {radius!r} cm: {disc.why}")
        return disc, (), None, radius, False
    if len(outline.points) > MAX_ITEM_VERTICES:  # before one of them is moved into the frame
        raise _OutlineTooLarge(_TOO_LARGE.why)
    ring = frame.local_ring(outline.points)
    if made is not None:
        made.append(ring)
    if not _finite_ring(ring):
        raise ValueError("geometry that is not finite")
    if any(abs(x) > MAX_LENGTH_CM or abs(y) > MAX_LENGTH_CM for x, y in ring):
        # before the clipper sees it: its integers end at 4.6e18, and a record
        # could not hold the result anyway
        raise RecordRangeError(f"an outline that reaches beyond ±{MAX_LENGTH_CM:g} cm")
    if outline.shape == OUTLINE_POLYLINE:
        width = outline.width_cm
        if width is None or math.isnan(width):
            raise ValueError(f"a stroke width of {width!r}")
        if abs(width) > MAX_LENGTH_CM:
            raise RecordRangeError(f"a stroke width of {width!r} cm is beyond ±{MAX_LENGTH_CM:g} cm")
        if len(ring) < 2:
            return (), ring, width, None, False
        stroke = _polyline_regions(ring, width)
        if isinstance(stroke, _Refused):
            raise (_OutlineTooLarge if stroke is _TOO_LARGE else _UnbuildableOutline)(stroke.why)
        return stroke, ring, width, None, False
    if outline.shape == OUTLINE_POLYGON:
        regions, resolved = _polygon_regions(ring)
        if isinstance(regions, _Refused):
            raise (_OutlineTooLarge if regions is _TOO_LARGE else _UnbuildableOutline)(regions.why)
        return regions, (), None, None, resolved
    # an ellipse or a rectangle: convex by construction; a mirrored scene transform
    # (baked into the ring) turns it clockwise, and without an area it covers nothing
    if len(ring) < 3 or ring_area(ring) == 0.0:
        return (), (), None, None, False
    outer = ccw(ring)
    if not _convex_region(outer):  # … and judged like every other shape: a sliver of
        raise _UnbuildableOutline(_NO_READING.why)  # 2e-7 cm is no polygon on the record grid
    return ((outer, ()),), (), None, None, False


def _record_of(item: Any, object_type: Any, item_id: str, at_date: date | None,
               lookup: ItemLookup) -> Record | None:
    """One item → its record; None when it covers no ground (not an error).
    Anything it raises is contained by ``snapshot_records``. ``lookup`` finds
    another item by id (a HOUSE's ridge)."""
    drawn = _drawn_vertices(item)
    if drawn > MAX_ITEM_VERTICES:  # one comparison — before a single vertex is read
        raise _OutlineTooLarge(f"an outline of {drawn:,} vertices: {_TOO_LARGE.why}")
    outline = item_outline(item, at_date)
    if outline is None:
        return None
    kind: str = object_type.name
    shape = outline.shape
    frame = _frame_of(item, outline.anchor, rotatable=shape != OUTLINE_CIRCLE)
    if not math.isfinite(frame.east_cm + frame.north_cm):
        raise ValueError("a position that is not finite")
    refused: _UnbuildableOutline | None = None
    made: list[Ring] = []  # the outline in the record's frame, made ONCE (``_regions_of``)
    try:
        regions, path, width, radius, resolved = _regions_of(outline, frame, made)
    except _UnbuildableOutline as error:
        # No solid can be built of this outline. An item that is PAINTED on the ground
        # needs none — the bake fills and strokes what was drawn — so the verdict waits
        # until the item's height is known (below): only then is it left out.
        # … but never an outline beyond the SIZE bound: that one is not copied, kept or
        # painted, whatever the item is (the first statement of this function has
        # already answered it from the stored vertex count; said again here, where the
        # copy would be made)
        if (shape not in (OUTLINE_POLYGON, OUTLINE_POLYLINE)
                or len(outline.points) > MAX_ITEM_VERTICES):
            raise
        refused = error
        regions, path, width, radius, resolved = _drawn_only(outline, frame, made)
    if not regions and refused is None:
        return None
    params: dict[str, ParamValue] = {PARAM_SEED: item_id}
    if resolved:
        params[PARAM_OUTLINE_RESOLVED] = True
    if radius is not None:
        params[PARAM_RADIUS_CM] = radius
    if shape == OUTLINE_POLYLINE:
        style = getattr(item, "path_fence_style", PathFenceStyle.NONE)
        if style is not PathFenceStyle.NONE:
            params[PARAM_PATH_STYLE] = style.name
    metadata = getattr(item, "metadata", None) or {}
    species = metadata.get("plant_species")
    species_name = ""
    if isinstance(species, dict):
        params[PARAM_SPECIES_KEY] = species_key(species)
        species_name = str(species.get("common_name") or "")
        # Transient calendar inputs, read from this instance's species snapshot.
        # Rendering must respect edited harvest windows, as the Tasks tab does.
        for field in ("harvest_start", "harvest_end"):
            value = species.get(field)
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value)):
                params[field] = value
    species_name = (species_name or str(getattr(item, "plant_species", "") or "")).strip()
    if species_name:
        params[PARAM_SPECIES_NAME] = species_name
    sprite_species = getattr(item, "plant_species", None)
    if isinstance(sprite_species, str) and sprite_species:
        params[PARAM_SPRITE_SPECIES] = sprite_species  # raw: what the 2D sprite is resolved from
    category = getattr(item, "plant_category", None)
    if category is not None:
        params[PARAM_PLANT_CATEGORY] = category.name
    if is_container_type(object_type):
        params[PARAM_CONTAINER_MATERIAL] = container_material(metadata)
    if kind == "HOUSE" and not resolved:  # a drawn ridge belongs to the DRAWN outline
        ridge_id = metadata.get("ridge_item_id")
        if ridge_id:
            ridge = _ridge_param(frame, lookup.get(ridge_id))
            if ridge is not None:
                params[PARAM_RIDGE] = ridge
    stroke = getattr(item, "stroke_color", None)
    if stroke is None and shape == OUTLINE_POLYLINE:
        stroke = item.pen().color()  # the line's visible colour: a preset-less polyline
    height = effective_height_cm(object_type, metadata, at_date=at_date)
    if height is not None and height <= 0.0:
        height = None  # no height. One that is no usable number — 1e300, 1e-300 — is the Record's to refuse.
    if height is None and kind in ("TREE", "SHRUB", "PERENNIAL"):
        # Illustrative fallback for unknown height (#557): the plan keeps
        # height None (unknown stays unknown); the transient record carries
        # the estimate separately so the builder can render the plant form.
        try:
            from open_garden_planner.core.plant_height_estimate import (
                ESTIMATED_HEIGHT_PARAM,
                estimated_height_cm,
            )

            _cat = getattr(item, "plant_category", None)
            _est = estimated_height_cm(
                kind, _cat.name if _cat is not None else None
            )
            if _est is not None and _est > 0:
                params[ESTIMATED_HEIGHT_PARAM] = float(_est)
        except Exception:
            pass
    paint: Paint | None = None
    as_drawn: Ring = ()  # a polygon AS DRAWN, where the regions are not it (Record.outline)
    if kind not in _NEVER_ON_THE_GROUND:
        # what the canvas paints the item with (L1.5) — whatever its height: the ground
        # bake shows it while no builder makes a solid for it, and a height that comes
        # or goes stays a change of the geometry alone
        paint, pen_colour = _paint_of(item, shape, frame.paint_turn_deg)
        if pen_colour is not None:
            stroke = pen_colour
        params[PARAM_PAINT_ORIGIN] = (quantize_cm(frame.anchor_x), quantize_cm(frame.anchor_y))
        if height is None and shape == OUTLINE_POLYGON and (resolved or refused is not None):
            # footprints is not the drawn polygon — the ring ``_regions_of`` made
            as_drawn = made[0] if made else frame.local_ring(outline.points)
    if refused is not None and (paint is None or height is not None):
        raise refused  # a solid needs regions: left out and reported, as before
    pattern = getattr(item, "fill_pattern", None)
    parent = getattr(item, "parent_bed_id", None)
    base = item_base_cm(item, lookup, at_date) if parent is not None else 0.0
    holes = tuple(region_holes for _outer, region_holes in regions)
    return Record(
        item_id=item_id,
        kind=kind,
        shape=shape,
        footprints=tuple(outer for outer, _holes in regions),
        transform=frame.transform(quantize_cm(base)),
        material=_material(kind, _rgba(getattr(item, "fill_color", None)), _rgba(stroke),
                           pattern.name if pattern is not None else None, paint),
        height_cm=height,
        path=path,
        path_width_cm=width,
        params=Params(params),
        parent_id=str(parent) if parent is not None else None,
        name=str(getattr(item, "name", "") or ""),
        holes=holes if any(holes) else (),
        outline=as_drawn,
    )


@snapshot_generation()  # what a snapshot asks for stays remembered while the plan keeps asking
def snapshot_records(
    scene: QGraphicsScene,
    at_date: date | None = None,
    *,
    skipped: list[SkippedItem] | None = None,
) -> dict[str, Record]:
    """Every visible item with a footprint → one contract-v2 ``Record``.

    Returns a dict keyed by item id, insertion-ordered BOTTOM TO TOP (paint
    order). Runs on the GUI thread; the records are plain immutable data.

    ``skipped``: pass a list to learn what had to be left out because something
    is WRONG with it — one ``SkippedItem`` is appended per such item, in paint
    order (the list is not cleared first; without one the report goes to the log
    only). It stays empty on a healthy plan.

    Left out by design, silently: invisible items (as the retired Qt 3D collector
    does), items without an ``object_type``, items that cover no ground (text,
    groups, arcs, a polyline shorter than two points, a shape without an area),
    and ``ROOF_RIDGE`` items (a ridge reaches 3D as its HOUSE's ``ridge`` param).

    Left out because something is wrong, and REPORTED — in ``skipped`` every
    time, and in the log once per item and kind of failure: an item whose
    record could not be built
    (malformed metadata, geometry that is not finite — any exception is
    contained to that item), a second item carrying an id already taken (the
    lower one wins), an item whose outline cannot be turned into regions a
    builder can build, an item whose outline is too large (more than
    ``MAX_ITEM_VERTICES`` vertices, or more work than ``MAX_REGION_WORK`` — a
    polyline of 200,000 points is answered with one comparison, and the rest of
    the plan gets its records), and an item with a length beyond
    ``core.scene3d.MAX_LENGTH_CM`` — a height of 1e300 from a hand-edited plan
    is a finite number and an infinite float32; such an item gets no record
    rather than a solid nobody can draw. One bad item never blanks the view.

    What a record holds, and why (``core.scene3d.record``, §8.29.1):

    - geometry in the ITEM-LOCAL frame, centred on the outline's anchor
      (``ui.canvas.footprints.item_outline``), on the record grid; the pose
      (``transform``) from the item's ``sceneTransform()``. A circle's rotation
      is 0 by construction: its footprint does not turn. A scene transform that
      is not rigid (an item in a scaled group) is baked into the local geometry.
    - ``footprints`` are simple OUTER rings, counter-clockwise, and ``holes``
      what is cut out of them: a polyline's stroke is sorted into both (a closed
      fence is one outer and one hole), a polygon that crosses itself is
      resolved by the non-zero rule, the 2D shadow's rule for a footprint —
      and says so in ``params`` (``outline_resolved``). EVERY region of a record
      satisfies ``core.scene3d.is_buildable_region``: the default builder's own
      triangulation has cut it.
    - ``height_cm``: ``effective_height_cm(..., at_date)`` — the 2D shadow's
      resolver; None means decoration that casts no shadow.
    - ``transform.base_cm`` (L1.6): where the item STANDS — the soil of the bed
      or container it is linked to AND stands inside (``footprints.item_base_cm``,
      the rule the 2D shadow casters use: 2 cm under a bed's rim, at a
      container's height), 0.0 on the ground. It is part of the transform, so a
      bed that changes height re-poses its plants and rebuilds none of them.
      An item whose parent got NO record here — left out for any of the reasons
      above — stands on the ground: nothing stands on a solid the scene does
      not hold (``_ground_items_without_a_parent_record``).
    - ``at_date`` (US-E8) grows dated plants: canopy radius and height. Lifetime
      presence comes from the scene's combined layer/date visibility (US-F4),
      applied before this snapshot. The workspace passes the same
      ``SimClock.plan_date`` for growth; a snapshot does not move that clock or
      temporarily reveal plants hidden by the current plan date.
    """
    items: list[Any] = scene.items()  # top-first; garden items are duck-typed below
    lookup = ItemLookup(items)
    records: dict[str, Record] = {}
    for item in reversed(items):
        if not item.isVisible():
            continue
        object_type = getattr(item, "object_type", None)
        item_uuid = getattr(item, "item_id", None)
        if object_type is None or item_uuid is None:
            continue
        kind = str(getattr(object_type, "name", object_type))
        if kind in _NO_RECORD_KINDS:
            continue
        item_id = str(item_uuid)
        try:
            record = _record_of(item, object_type, item_id, at_date, lookup)
        except RecordRangeError as error:  # a length beyond what a plan can hold
            _report(SkippedItem(item_id, kind, SkipReason.OUT_OF_RANGE,
                                type(error).__name__, str(error)), skipped)
            continue
        except _UnbuildableOutline as error:
            reason = (SkipReason.OUTLINE_TOO_LARGE if isinstance(error, _OutlineTooLarge)
                      else SkipReason.OUTLINE_UNBUILDABLE)
            _report(SkippedItem(item_id, kind, reason, type(error).__name__, str(error)), skipped)
            continue
        except Exception as error:  # one bad item must not blank the view (docstring)
            _report(SkippedItem(item_id, kind, SkipReason.RECORD_FAILED,
                                type(error).__name__, str(error)), skipped, error)
            continue
        if record is None:
            continue
        if item_id in records:
            _report(SkippedItem(item_id, kind, SkipReason.DUPLICATE_ID), skipped)
            continue
        records[item_id] = record
    _ground_items_without_a_parent_record(records)
    return records


def _ground_items_without_a_parent_record(records: dict[str, Record]) -> None:
    """An item lifted onto a parent that got no record stands on the ground instead.

    ``item_base_cm`` answers where an item stands from the ITEMS: the link, the
    parent's height, the item's centre inside the parent's shape. Whether that
    parent is in the 3D scene at all is known only here, and only once every
    record is built (the walk is bottom to top; a parent may lie above its
    plant). A parent is left out when it is beyond the contract's range (a bed
    30 km wide), when its outline cannot be built, when its record failed — and
    then there is no solid for a plant to stand on: 38 cm up over nothing.

    Only ``base_cm`` changes; ``parent_id`` still says whose the item is. The 2D
    shadow casters are not this function's business: there the parent is a
    caster like any other, and its plants stand on it.
    """
    for item_id, record in records.items():  # values are replaced, no key is added
        if record.transform.base_cm != 0.0 and record.parent_id not in records:
            records[item_id] = replace(record, transform=replace(record.transform, base_cm=0.0))
