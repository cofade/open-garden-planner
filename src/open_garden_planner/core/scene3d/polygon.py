"""Plane polygons for the 3D pipeline: orientation, nesting, triangulation (L1.1).

A footprint is a set of REGIONS. A region is one OUTER ring, counter-clockwise
seen from above (signed area > 0), and any number of HOLE rings inside it,
clockwise (signed area < 0). That is the orientation pyclipper emits and the one
``Record`` enforces: ``footprints`` holds the outers, ``holes[i]`` the holes of
``footprints[i]``. A closed fence is the case that makes the distinction
load-bearing — its stroke comes back as two rings, and extruding the inner one
as a solid turns a 3.6 m² fence into an 80 m² slab (senior review, fix round 1).

Plain Python on float pairs, except where a test is superlinear and runs on every
edit of a ring — the simplicity test of a large ring and the ring-conflict sweep
run on numpy. ``triangulate_polygon`` is the ear clipper the Qt 3D view of US-E6
used, moved here unchanged from the pre-L1.1 module that L1.10 deleted with that
view; it remains the test reference and the builders' fallback for small rings.
``triangulate_region`` cuts a region with holes, or a hole-free ring of
``ARRAY_EAR_CLIP_FROM`` vertices or more, with ONE native call (``mapbox-earcut``,
ADR-069); below that size it clips ears of the shared clipper, whose triangles the
golden meshes pin.

ONE predicate says whether a region may be handed to a builder:
``is_buildable_region`` — true exactly when ``cut_region``, the triangulation
the default builder itself uses, cuts it and the triangles add up to the
region's area. The snapshot asks it for every outline it turns into rings, so
"a record's regions can be built" is a checked fact, not a hope (fix round 2).

Two bounds hold for everything here, because the rings come out of a plan file
and a plan file can be written by anybody (security review of fix round 3):

- WORK. Whatever is superlinear — the simplicity test, the ring-conflict sweep,
  sorting rings into regions, a bridge, the native triangulation (worst case),
  counting the pairs of a path — is paid for in work units out of a
  ``WorkBudget`` BEFORE it runs, and refused (``RegionTooLargeError``) when the
  budget does not cover it. One region may cost ``MAX_REGION_WORK``; so may
  everything ONE item's outline needs, which ``ui.view3d.snapshot`` pays into one
  budget.
- MEMORY. What is remembered about rings (``ring_keyed``: ``ring_area``, the
  verdict and the cut of a region) is bounded by the VERTICES it holds, not by
  the number of answers, and a ring of more than ``MAX_ITEM_VERTICES`` vertices
  is never hashed and never a key.
"""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Final, Generic, NamedTuple, NoReturn, ParamSpec, TypeAlias, TypeVar

import mapbox_earcut
import numpy as np
from numpy.typing import NDArray

Point: TypeAlias = tuple[float, float]
Ring: TypeAlias = tuple[Point, ...]
Region: TypeAlias = tuple[Ring, tuple[Ring, ...]]
Triangle: TypeAlias = tuple[int, int, int]
_Floats: TypeAlias = "NDArray[np.float64] | float"


# ── what is remembered ────────────────────────────────────────────────────────

#: The most vertices ONE item's outline may have in the 3D pipeline: as it is
#: DRAWN (a polygon's ring, the points of a path) and as it is MADE (every ring
#: the clipper returns for it, together). The first is asked of the item before
#: one vertex is read, the second of the clipper's answer before one ring of it
#: is. Above what the work bound lets through (a plain outline of about 7,000
#: vertices with the native cut's pricing, fewer for a ring whose shape makes the
#: sweep pay; a straight path of about 6,600 points, whose pairs alone are the
#: bound), so it refuses only what could not be built anyway — it is what
#: makes the answer for 200,000 points ONE comparison, and what bounds a key.
MAX_ITEM_VERTICES: Final = 16_384
#: How many vertices of STALE answers ONE ``ring_keyed`` function holds at most,
#: keys and answers together — answers the plan no longer asks for: the ring an
#: outline had before its last edit. At 104 bytes a vertex (a tuple of two
#: floats, and its place in the ring) that is 27 MB. (Before fix round 3: 2,048
#: to 8,192 ANSWERS each, whatever their size — a traced outline of 4,000
#: vertices dragged for a minute was a gigabyte.) What the plan DOES ask for is
#: not counted against it and never dropped (``snapshot_generation``):
#: dropping it made every tick of an unchanged plan above the cap recompute
#: the plan (review of fix round 3).
#:
#: So what a LIVE plan holds has no cap: it is linear in the plan. Measured
#: (review of fix round 4): 130 bytes a vertex for an accepted polygon after
#: its record is gone — 400 polygons of 3,000 vertices 156 MB — and 112 bytes
#: a point for a REFUSED line, which has no record at all and whose key is
#: all that is kept: 20 lines of 16,384 points 37 MB. At most about 1.8 MB
#: for one item of ``MAX_ITEM_VERTICES``. An accepted outline's rings are its
#: record's own (the key too, when it was drawn counter-clockwise), so while
#: the records live this adds less than it counts. ``clear_ring_memories``
#: gives all of it back.
HELD_VERTICES: Final = 262_144
_ENTRY_VERTICES: Final = 8  # what an answer weighs beyond its rings: the entry itself

_generation = 0  # the snapshot being taken, or the last one that was
_snapshotting = False
_memories: weakref.WeakSet[RingKeyed[Any, Any]] = weakref.WeakSet()  # every ``ring_keyed`` function


@contextmanager
def snapshot_generation() -> Iterator[int]:
    """ONE snapshot of the plan (``ui.view3d.snapshot.snapshot_records`` runs in it).

    An answer a ``ring_keyed`` function is asked for INSIDE a snapshot is LIVE
    for that snapshot and the next: it is never dropped, however much is held —
    an unchanged plan is then answered from memory on every tick, whatever its
    size. An answer no snapshot has asked for since the one before the last is
    STALE, and so is one asked for outside any snapshot (a builder's own rings,
    a script's loop): only those are counted against ``HELD_VERTICES`` and
    dropped, least recently asked first — at the latest when the snapshot ends,
    also from a memory this snapshot did not ask (the plan's last fence is gone).

    The generation is the PROCESS's clock: nothing says whose snapshot it is.
    **One snapshotting scene per process is the supported case.** More are
    correct and recompute: two scenes snapshotted in turn still find their
    answers (the one before counts), three in turn find them stale — measured,
    every scene's 160 polygons cut again on every tick. A snapshot that raises
    half-way leaves the next ones correct. And a plan that is gone stays held
    until two more snapshots have run: ``clear_ring_memories`` (the workspace
    calls it through ``ui.view3d.snapshot.clear_outline_cache``) drops it at once.
    """
    global _generation, _snapshotting  # noqa: PLW0603 - the one clock of what is remembered
    _generation += 1
    outer, _snapshotting = _snapshotting, True
    try:
        yield _generation
    finally:
        _snapshotting = outer
        for memory in list(_memories):
            memory.settle()


def clear_ring_memories() -> None:
    """Forget every answer of every ``ring_keyed`` function — live and stale.
    What ``ui.view3d.snapshot.clear_outline_cache`` is made of; call that one."""
    for memory in list(_memories):
        memory.cache_clear()


_P = ParamSpec("_P")
_R = TypeVar("_R")


class CacheInfo(NamedTuple):
    """What a ``ring_keyed`` function holds (``cache_info()``)."""

    hits: int
    misses: int
    max_vertices: int
    vertices: int
    entries: int


class _Entry(Generic[_R]):
    __slots__ = ("answer", "asked", "generation", "weight")

    def __init__(self, answer: _R, weight: int, asked: int) -> None:
        self.answer, self.weight, self.asked = answer, weight, asked
        self.generation = -2  # the last snapshot that asked for it; -2: none has (stale from the start)


class RingKeyed(Generic[_P, _R]):
    """A function of rings with its answers remembered — what ``functools.lru_cache``
    does, bounded by the VERTICES held instead of the number of answers.

    An answer about a traced outline of 4,000 vertices is a thousand times an
    answer about a rectangle; a bound on entries is no bound on memory. What is
    bounded is the STALE answers (``snapshot_generation``): they are kept until
    their keys (``vertices(*args)``) and what ``holds(answer)`` says of the
    answers add up to ``max_vertices``; then the least recently asked of them
    go, down to three quarters. A LIVE answer — asked for by the snapshot being
    taken or the one before — is never dropped. A call about more than
    ``MAX_ITEM_VERTICES`` vertices is answered and NOT kept: such a ring is
    never hashed and never a key. Positional arguments only are remembered.
    Safe to call from several threads, like ``lru_cache``; an exception is not
    remembered.
    """

    def __init__(self, function: Callable[_P, _R], max_vertices: int,
                 vertices: Callable[..., int], holds: Callable[[Any], int] | None) -> None:
        self.__wrapped__ = function
        self.__name__ = function.__name__
        self.__doc__ = function.__doc__
        self._vertices, self._holds, self._max = vertices, holds, max_vertices
        self._entries: dict[tuple[Any, ...], _Entry[_R]] = {}
        self._held = self._asked = self._hits = self._misses = 0
        self._limit = max_vertices  # what is held is looked through for stale answers beyond this
        self._lock = threading.Lock()
        _memories.add(self)

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        if kwargs:
            return self.__wrapped__(*args, **kwargs)
        entry = self._entry(args)
        if entry is not None:
            return entry.answer
        answer = self.__wrapped__(*args, **kwargs)
        self.remember(args, answer)
        return answer

    def _size(self, args: tuple[Any, ...]) -> int | None:
        """The vertices these arguments hold — None when they are too many to be a key."""
        size = self._vertices(*args)
        return None if size > MAX_ITEM_VERTICES else size

    def _entry(self, args: tuple[Any, ...]) -> _Entry[_R] | None:
        if self._size(args) is None:
            return None  # never hashed
        with self._lock:
            self._asked += 1
            entry = self._entries.get(args)
            if entry is None:
                self._misses += 1
            else:
                entry.asked = self._asked
                self._hits += 1
                if _snapshotting:
                    entry.generation = _generation  # asked for by a snapshot: LIVE from now on
            return entry

    def settle(self) -> None:
        """Hold no more stale answers than the cap — asked of every memory when a
        snapshot ends (``snapshot_generation``). Nothing to do while all it holds
        fits the cap; beyond that one look through what it holds."""
        with self._lock:
            if self._held > self._max:
                self._forget()

    def known(self, *args: Any) -> _R | None:
        """The remembered answer to these arguments, or None. Nothing is computed."""
        entry = self._entry(args)
        return entry.answer if entry is not None else None

    def remember(self, args: tuple[Any, ...], answer: _R) -> None:
        """Keep ``answer`` as the answer to ``args`` — for a caller that worked it
        out on its own account (``pay_for_region``). Too large to be a key: not kept."""
        size = self._size(args)
        if size is None:
            return
        weight = _ENTRY_VERTICES + size + (self._holds(answer) if self._holds is not None else 0)
        with self._lock:
            if args not in self._entries:
                entry = self._entries[args] = _Entry(answer, weight, self._asked)
                if _snapshotting:
                    entry.generation = _generation
                self._held += weight
                if self._held > self._limit:
                    self._forget()

    def _forget(self) -> None:
        """(Under the lock.) When the STALE answers are more than the cap, drop the
        least recently asked of them until they take three quarters of it. A live
        answer is never among them — whatever is held. One look through all that
        is held; the next not before a quarter of the cap has come in again."""
        stale = [(key, entry) for key, entry in self._entries.items()
                 if entry.generation < _generation - 1]
        weight = sum(entry.weight for _key, entry in stale)
        if weight > self._max:
            for key, entry in sorted(stale, key=lambda item: item[1].asked):
                if weight <= self._max * 3 // 4:
                    break
                del self._entries[key]
                self._held -= entry.weight
                weight -= entry.weight
        self._limit = max(self._max, self._held + self._max // 4)

    def cache_clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._held = self._hits = self._misses = 0
            self._limit = self._max

    def cache_info(self) -> CacheInfo:
        return CacheInfo(self._hits, self._misses, self._max, self._held, len(self._entries))


def ring_keyed(max_vertices: int = HELD_VERTICES, *, vertices: Callable[..., int] = len,
               holds: Callable[[Any], int] | None = None,
               ) -> Callable[[Callable[_P, _R]], RingKeyed[_P, _R]]:
    """Decorator: remember a function of rings, bounded by vertices (``RingKeyed``).
    ``vertices(*args)`` says how many vertices a call's arguments hold (default:
    the length of its one ring), ``holds(answer)`` how many its answer does."""

    def remembered(function: Callable[_P, _R]) -> RingKeyed[_P, _R]:
        return RingKeyed(function, max_vertices, vertices, holds)

    return remembered


# ── area and orientation ──────────────────────────────────────────────────────


def _signed_area(polygon: Sequence[Sequence[float]]) -> float:
    total = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def signed_area(ring: Sequence[Sequence[float]]) -> float:
    """Shoelace area in cm²: positive for a counter-clockwise ring (seen from above,
    north up), negative for a clockwise one."""
    return _signed_area(ring)


@ring_keyed()
def ring_area(ring: Ring) -> float:
    """``signed_area`` of an immutable ring, remembered — a snapshot checks the
    orientation of every ring of every record, and most rings repeat."""
    return _signed_area(ring)


def ccw(ring: Ring) -> Ring:
    """``ring`` turning counter-clockwise (reversed when it turns clockwise)."""
    return ring if ring_area(ring) >= 0.0 else ring[::-1]


def cw(ring: Ring) -> Ring:
    """``ring`` turning clockwise — the orientation of a hole."""
    return ring if ring_area(ring) <= 0.0 else ring[::-1]


# ── predicates ────────────────────────────────────────────────────────────────


def _cross(o: Sequence[float], a: Sequence[float], b: Sequence[float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _point_in_triangle(
    p: Sequence[float], a: Sequence[float], b: Sequence[float], c: Sequence[float]
) -> bool:
    d1 = _cross(p, a, b)
    d2 = _cross(p, b, c)
    d3 = _cross(p, c, a)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def point_in_ring(x: float, y: float, ring: Sequence[Sequence[float]]) -> bool:
    """True when (x, y) lies inside ``ring`` (even-odd rule; a point exactly on the
    boundary may answer either way)."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_regions(x: float, y: float, regions: Sequence[Region]) -> bool:
    """True when (x, y) is covered: inside an outer ring and in none of its holes."""
    for outer, holes in regions:
        if point_in_ring(x, y, outer) and not any(point_in_ring(x, y, hole) for hole in holes):
            return True
    return False


def _on_segment(p: Sequence[float], a: Sequence[float], b: Sequence[float]) -> bool:
    return (min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def segments_touch(a: Sequence[float], b: Sequence[float],
                   c: Sequence[float], d: Sequence[float]) -> bool:
    """True when the closed segments a–b and c–d share at least one point."""
    d1 = _cross(c, d, a)
    d2 = _cross(c, d, b)
    d3 = _cross(a, b, c)
    d4 = _cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and d1 != 0 and d2 != 0 and ((d3 > 0) != (d4 > 0)) and d3 != 0 and d4 != 0:
        return True
    return ((d1 == 0 and _on_segment(a, c, d)) or (d2 == 0 and _on_segment(b, c, d))
            or (d3 == 0 and _on_segment(c, a, b)) or (d4 == 0 and _on_segment(d, a, b)))


#: By how much of the product of its two edges a corner must turn LEFT for
#: ``is_convex_ring`` to count it: far above what floats can get wrong (1e-16),
#: far below the corners of a real shape (a 24-gon turns by 0.26).
_CONVEX_TURN: Final = 1e-9
#: … and how much of the square of its reach the ring must cover, unless it is
#: small: the proof of a cut compares two sums of areas to 1e-9 (of 1 cm², or of
#: the area when that is more), and each sum is off by about 1e-13 of the largest
#: coordinate squared. A bed of 120 m by 2 µm is convex and fails that proof.
_CONVEX_BODY: Final = 1e-3


def is_convex_ring(ring: Sequence[Sequence[float]]) -> bool:
    """True when every corner of ``ring`` turns left by more than float noise, and
    the ring is not a sliver for its reach (its area, or 1 cm², is at least a
    thousandth of its farthest coordinate squared).

    For a ring that is convex BY CONSTRUCTION and winds once — a circle's, an
    ellipse's, a rectangle's footprint — that makes it a strictly convex polygon
    on the record grid as well, and such a ring is buildable WITHOUT being cut:
    it is simple, its ears are its corners, and their areas are its area beyond
    what floats can blur (so ``is_convex_ring(r)`` implies
    ``is_buildable_region(r)``; pinned over 2,000 shapes of every size and
    slenderness). Arithmetic on its corners where the predicate cuts a
    triangulation: the snapshot asks this first, because a date scrub gives every
    dated plant a new radius on every tick. It says nothing about a ring that is
    not convex by construction (a ring that winds twice turns left as well).
    False for a ring with a coordinate that is not a number, or not finite.
    """
    if len(ring) < 3:
        return False
    (x0, y0), (x1, y1) = ring[-2], ring[-1]
    twice = reach = 0.0
    for x2, y2 in ring:
        ax, ay, bx, by = x1 - x0, y1 - y0, x2 - x1, y2 - y1
        if not ax * by - ay * bx > _CONVEX_TURN * (abs(ax) + abs(ay)) * (abs(bx) + abs(by)):
            return False  # also for a coordinate that is no number: nothing is greater than NaN
        twice += x1 * y2 - x2 * y1
        reach = max(reach, x2 * x2 + y2 * y2)
        x0, y0, x1, y1 = x1, y1, x2, y2
    return max(1.0, twice / 2.0) >= _CONVEX_BODY * reach


def is_flat_ring(ring: Sequence[Sequence[float]]) -> bool:
    """True when ``ring`` covers no ground at all: fewer than three corners, or
    every corner on one line. (A bow-tie whose lobes cancel has a zero signed
    area too, but it is not flat — it is a polygon that crosses itself.)"""
    if len(ring) < 3:
        return True
    origin = ring[0]
    far = max(ring, key=lambda p: (p[0] - origin[0]) ** 2 + (p[1] - origin[1]) ** 2)
    return all(_cross(origin, far, p) == 0 for p in ring)


#: From this many vertices on the simplicity test runs on numpy. Below it the
#: plain loop is faster (a rectangle costs microseconds); above it the loop is
#: what an edit of a traced outline would wait for — measured on the dev box:
#: 500 vertices 72 ms in the loop, 1,000 vertices 262 ms.
SIMPLE_RING_NUMPY_FROM: Final = 32
_SIMPLE_RING_ROWS: Final = 512  # edges per block: bounds the rows x n temporaries


def _edges_touch_loop(ring: Ring) -> bool:
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        for j in range(i + 1, n):
            if (j + 1) % n == i or (i + 1) % n == j:
                continue  # a neighbour: they share a vertex by design
            if segments_touch(a, b, ring[j], ring[(j + 1) % n]):
                return True
    return False


def _edges_touch_numpy(ring: Ring, work: WorkBudget | None = None) -> bool:
    """``_edges_touch_loop`` on arrays: ``touching_pairs`` of the closed ring.

    In two steps. First the pairs of non-adjacent edges whose bounding boxes
    meet — two closed segments that share a point have boxes that do, so nothing
    is lost, and for an outline that leaves a few pairs per edge instead of n.
    Then, on those pairs only, the four cross products of ``segments_touch``,
    written in the same order of operations: the answer is the loop's, bit for
    bit (pinned by a test over random rings on both sides of the threshold).

    Paid for out of ``work`` (a budget of its own when none is given): the first
    step by the square of the edges, the second by the pairs it leaves — ALL of
    them before one is tested. For an outline those are few. For a ring
    scribbled across a plan they are half of all pairs, and testing them cost a
    hundred times what the square alone was priced at (3,500 vertices: half a
    second, three times the bound) until they were priced as well.
    """
    budget = work if work is not None else WorkBudget(
        f"the simplicity test of a ring of {len(ring)} vertices")
    return touching_pairs(ring, budget, closed=True)[1] > 0


def _touch(ax: _Floats, ay: _Floats, bx: _Floats, by: _Floats,
           cx: _Floats, cy: _Floats, dx: _Floats, dy: _Floats) -> NDArray[np.bool_]:
    """``segments_touch`` on arrays (they broadcast): the closed segments a–b and
    c–d share a point. The four cross products are written in the scalar
    version's order of operations, so the two never disagree."""
    d1 = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx)  # _cross(c, d, a)
    d2 = (dx - cx) * (by - cy) - (dy - cy) * (bx - cx)  # _cross(c, d, b)
    d3 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)  # _cross(a, b, c)
    d4 = (bx - ax) * (dy - ay) - (by - ay) * (dx - ax)  # _cross(a, b, d)
    crossing = (((d1 > 0) != (d2 > 0)) & (d1 != 0) & (d2 != 0)
                & ((d3 > 0) != (d4 > 0)) & (d3 != 0) & (d4 != 0))
    touching = (((d1 == 0) & _within(ax, ay, cx, cy, dx, dy))
                | ((d2 == 0) & _within(bx, by, cx, cy, dx, dy))
                | ((d3 == 0) & _within(cx, cy, ax, ay, bx, by))
                | ((d4 == 0) & _within(dx, dy, ax, ay, bx, by)))
    return np.asarray(crossing | touching)


def _within(px: _Floats, py: _Floats, sx: _Floats, sy: _Floats,
            ex: _Floats, ey: _Floats) -> NDArray[np.bool_]:
    """``_on_segment`` on arrays: p inside the bounding box of s–e."""
    return np.asarray((np.minimum(sx, ex) <= px) & (px <= np.maximum(sx, ex))
                      & (np.minimum(sy, ey) <= py) & (py <= np.maximum(sy, ey)))


def is_simple_ring(ring: Ring) -> bool:
    """True when ``ring`` is a simple polygon: at least three vertices, a non-zero
    area, and no two non-adjacent edges sharing a point (no bow-tie, no touching).

    Quadratic in the vertex count: from ``SIMPLE_RING_NUMPY_FROM`` vertices on it
    runs on arrays, and a ring whose test ALONE would cost more than
    ``MAX_REGION_WORK`` — about 7,000 vertices of an outline, far fewer of a
    ring scribbled across a plan — is refused with ``RegionTooLargeError``: a
    question is not answered at any price. Not remembered: the cut of a region
    is (``cut_region``), and that is where a ring out of a plan is asked.
    """
    return _is_simple(ring, WorkBudget(f"the simplicity test of a ring of {len(ring)} vertices"))


def _is_simple(ring: Ring, work: WorkBudget) -> bool:
    """``is_simple_ring``, paid for out of ``work``."""
    n = len(ring)
    if n < 3 or _signed_area(ring) == 0.0:
        return False
    if any(ring[i] == ring[(i + 1) % n] for i in range(n)):
        return False  # an edge without a length
    if n >= SIMPLE_RING_NUMPY_FROM:
        return not _edges_touch_numpy(ring, work)  # pays as it counts
    work.spend(_simplicity_work(n))
    return not _edges_touch_loop(ring)


# ── nesting ───────────────────────────────────────────────────────────────────


def _point_inside(ring: Ring) -> Point:
    """A point STRICTLY inside a simple ring (of either orientation).

    At the ring's lowest-leftmost corner — a convex one — the triangle with its
    two neighbours either holds no other vertex, and then its centroid is
    inside the ring, or it does, and then the midpoint between the corner and
    the vertex in it that is farthest from the neighbours' line is.
    """
    n = len(ring)
    at = min(range(n), key=lambda i: (ring[i][1], ring[i][0]))
    corner, before, after = ring[at], ring[at - 1], ring[(at + 1) % n]
    if _cross(before, corner, after) < 0:
        before, after = after, before  # the clockwise ring: read the corner the other way round
    best, reach = None, 0.0
    for point in ring:
        if point in (corner, before, after) or not _point_in_triangle(point, before, corner, after):
            continue
        height = abs(_cross(before, after, point))
        if best is None or height > reach:
            best, reach = point, height
    if best is None:
        return ((corner[0] + before[0] + after[0]) / 3.0, (corner[1] + before[1] + after[1]) / 3.0)
    return ((corner[0] + best[0]) / 2.0, (corner[1] + best[1]) / 2.0)


def _ring_holds(ring: Ring) -> Callable[[float, float], bool]:
    """``point_in_ring`` for ONE ring and many points: the same test — the same
    numbers in the same order of operations — on arrays when the ring is large.
    (A ladder of 180 cells asks its outer ring of 1,100 vertices 180 times.)"""
    if len(ring) < SIMPLE_RING_NUMPY_FROM:
        return lambda x, y: point_in_ring(x, y, ring)
    xi = np.asarray([x for x, _y in ring], dtype=np.float64)
    yi = np.asarray([y for _x, y in ring], dtype=np.float64)
    xj, yj = np.roll(xi, 1), np.roll(yi, 1)

    def holds(x: float, y: float) -> bool:
        at = np.flatnonzero((yi > y) != (yj > y))
        if not len(at):
            return False
        crossings = x < (xj[at] - xi[at]) * (y - yi[at]) / (yj[at] - yi[at]) + xi[at]
        return bool(np.count_nonzero(crossings) & 1)

    return holds


def group_rings(rings: Sequence[Ring], work: WorkBudget | None = None) -> tuple[Region, ...]:
    """Sort a flat list of rings — outers counter-clockwise, holes clockwise, as
    pyclipper returns them — into regions: each hole joins the smallest outer
    that contains it. Rings with fewer than three vertices or no area are dropped;
    a hole inside no outer raises ``ValueError`` (it is not a footprint).

    Ownership is decided by a point strictly INSIDE the hole and by size: the
    owner is the smallest outer ring that is larger than the hole and contains
    that point. (A vertex of the hole would not do — a hole may touch its outer
    ring, or an island inside it, exactly there, and a point on a boundary has
    no inside. Nor would containment alone: an island inside the hole contains
    points of it too, and is smaller than the hole.)

    Every hole asks every outer ring: holes x outers, and each question costs the
    outer ring's vertices. That product is paid into ``work`` (a budget of its
    own when none is given) BEFORE the first question — 2,000 small holes in
    2,000 small outer rings took 3.8 s here when nothing asked. Beyond the
    budget: ``RegionTooLargeError``.
    """
    outers: list[Ring] = []
    holes: list[Ring] = []
    areas: list[float] = []
    for ring in rings:
        if len(ring) < 3:
            continue
        area = ring_area(ring)
        if area > 0.0:
            outers.append(ring)
            areas.append(area)
        elif area < 0.0:
            holes.append(ring)
    owned: list[list[Ring]] = [[] for _ in outers]
    if holes:
        budget = work if work is not None else WorkBudget("sorting rings into regions")
        budget.spend(len(holes) * sum(_ask_work(len(outer)) for outer in outers)
                     + _INSIDE_VERTEX_UNITS * sum(len(hole) for hole in holes))
    holds = [_ring_holds(outer) for outer in outers] if holes else []
    for hole in holes:
        x, y = _point_inside(hole)
        size = -ring_area(hole)
        best = -1
        for index in range(len(outers)):
            if areas[index] > size and holds[index](x, y) and (
                best < 0 or areas[index] < areas[best]
            ):
                best = index
        if best < 0:
            raise ValueError("a hole ring lies inside no outer ring")
        owned[best].append(hole)
    return tuple((outer, tuple(mine)) for outer, mine in zip(outers, owned, strict=True))


def regions_area(regions: Sequence[Region]) -> float:
    """Covered area in cm²: the outers minus their holes."""
    return sum(ring_area(outer) + sum(ring_area(hole) for hole in holes)
               for outer, holes in regions)


# ── triangulation ─────────────────────────────────────────────────────────────


def triangulate_polygon(polygon: Sequence[Sequence[float]]) -> list[Triangle]:
    """Ear-clipping triangulation; returns index triples into ``polygon``.

    Handles convex and concave simple polygons; input winding is
    irrelevant (normalized to CCW internally, indices refer to the
    ORIGINAL order). Falls back to a fan for pathological inputs so the
    renderer always gets triangles rather than nothing.
    """
    n = len(polygon)
    if n < 3:
        return []
    indices = list(range(n))
    if _signed_area(polygon) < 0:
        indices.reverse()  # normalize to CCW traversal
    triangles: list[Triangle] = []
    guard = 0
    while len(indices) > 3 and guard < 10000:
        guard += 1
        ear_found = False
        m = len(indices)
        for i in range(m):
            prev_i, cur_i, next_i = (
                indices[(i - 1) % m],
                indices[i],
                indices[(i + 1) % m],
            )
            a, b, c = polygon[prev_i], polygon[cur_i], polygon[next_i]
            if _cross(a, b, c) <= 0:
                continue  # reflex or collinear — not an ear
            if any(
                _point_in_triangle(polygon[j], a, b, c)
                for j in indices
                if j not in (prev_i, cur_i, next_i)
            ):
                continue
            triangles.append((prev_i, cur_i, next_i))
            indices.pop(i)
            ear_found = True
            break
        if not ear_found:
            break  # numeric degeneracy — fan out the rest below
    if len(indices) == 3:
        triangles.append((indices[0], indices[1], indices[2]))
    elif len(indices) > 3:
        anchor = indices[0]
        for i in range(1, len(indices) - 1):
            triangles.append((anchor, indices[i], indices[i + 1]))
    return triangles


def _inside_corner(points: Sequence[Point], loop: Sequence[int], at: int, target: int) -> bool:
    """True when points[target] lies strictly inside the interior angle of the
    counter-clockwise ``loop`` at position ``at``."""
    n = len(loop)
    prev, here, nxt = points[loop[at - 1]], points[loop[at]], points[loop[(at + 1) % n]]
    t = points[target]
    left_of_in = _cross(prev, here, t) > 0
    left_of_out = _cross(here, nxt, t) > 0
    if _cross(prev, here, nxt) > 0:  # convex corner: inside both half-planes
        return left_of_in and left_of_out
    return left_of_in or left_of_out  # reflex corner: inside either


# ── what a cut may cost ───────────────────────────────────────────────────────

#: THE WORK BOUND — what cutting ONE region may cost, with holes or without, and
#: what everything ONE item's outline needs may cost together (the snapshot pays
#: the clipper, the sorting and every region's cut into one ``WorkBudget``: a
#: thousand regions that each fit are not a thousand bounds). What would cost
#: more is refused (``RegionTooLargeError``) instead of holding the GUI thread,
#: and the refusal comes FIRST: a step is paid for before it runs — before the
#: simplicity test, before a bridge, before an ear, before the clipper is asked.
#:
#: Work is counted, not timed, so the verdict is the same on every machine. A
#: unit is priced at about a nanosecond on the development box (the price list
#: below); the things a cut does each pay as they go:
#:
#: - the simplicity test of each ring — every pair of its edges, n²;
#: - a bridge per hole — one sort of the boundary, then a block of candidates at
#:   a time against EVERY edge, as many blocks as it takes to find a free one;
#: - the ear clipping — every corner looked at, and every vertex still in the
#:   loop each time one is tested.
#:
#: What fits, measured (``scripts/measure_region_work.py``, which prints the
#: tables in section 8.29.1). As ONE region: a plain traced outline of 3,557
#: vertices; a comb of 1,648; a spiral of 4,334. As a whole outline, clipper and
#: all: a closed fence along 1,321 traced points (933 when every segment lies
#: nearly level with every other); a straight fence of about 6,650 posts east–
#: west or north–south (4,514 at 30 degrees, where its outline keeps a vertex
#: per post); a ladder of 168 rungs or a mesh of 15 x 15 openings drawn as one
#: stroke; a drawn outline of 1,513 vertices that crosses itself; ONE ring with
#: holes bridged to its edge — 117 triangular ones in a slab, 88 square ones
#: in a row, 112 frames (146, 105 and 112 before the bridge search was
#: re-priced, #451). What a large plan needs is far inside it — a closed fence
#: along 400 traced points 16 % of the bound, a line of 2 km 0.02 %, a
#: rectangle 10,200 units.
#:
#: In TIME the bound is a measurement, not a promise. A unit of the reference (a
#: plain traced outline) took 0.35 to 1.15 ns on the development box when it was
#: quiet and 0.7 to 2.3 ns beside other test runs, and a unit CHARGED for
#: something else took 0.1 to 2.1 times that in every row of the script's tables.
#: The one family that stood at 3.6 to 8.1 — a ring whose holes TOUCH its outer
#: ring, whose bridge search (``_bridge_position``) was priced too low — was
#: re-priced for #451: the dearest row of the table then stood at 1.3 to 1.5, and the
#: family's own dearest refusal (110 such holes, 444 vertices) takes about 0.07 s
#: instead of 0.6 to 1.5 s. What it costs in capacity: a slab with 49 such holes
#: now fits (89 before), a row of 88 square holes (105) and a slab of 117
#: triangular ones (146). So one item costs at most 0.05 to 0.35 s of the
#: reference — measured up to 0.39 s beside other test runs for everything
#: else, up to 0.7 s where both factors meet. The script FAILS above 12 times:
#: a union asked for a tree stood at 14 to 76 and ran for seconds inside this
#: bound, twice.
MAX_REGION_WORK: Final = 150_000_000

# The price list, in work units. Fitted to measurements on the development box
# (the script above prints units against milliseconds for each kind of region).
_REGION_UNITS: Final = 3_000  # a region, whatever its size: what asking about it costs at least
_PAIR_UNITS: Final = 3  # every pair of the segments of one ring or path, on arrays: per n² …
_NEAR_PAIR_UNITS: Final = 350  # … and per pair whose boxes meet (those are tested one by one)
_SMALL_PAIR_UNITS: Final = 250  # … in the plain loop (rings below SIMPLE_RING_NUMPY_FROM)
_ASK_UNITS: Final = 12_000  # group_rings: one outer ring asked about one point, on arrays …
_ASK_VERTEX_UNITS: Final = 3  # … per vertex of that ring
_ASK_SMALL_VERTEX_UNITS: Final = 120  # … in the plain loop (rings below SIMPLE_RING_NUMPY_FROM)
_INSIDE_VERTEX_UNITS: Final = 700  # … and the point inside a hole: per vertex of the hole
_HOLE_UNITS: Final = 140_000  # a bridge: setting the search up, per hole …
_HOLE_VERTEX_UNITS: Final = 100  # … per boundary vertex (sorted by distance) …
_HOLE_EDGE_UNITS: Final = 60  # … and per edge of the boundary and the holes still waiting
#: A block of candidates, per edge it is tested against. 60 until #451, when the
#: touching-holes family showed what a block really costs: 600 makes the block
#: that finds nothing (the usual one for a hole touching the wall) pay for the
#: six candidates it tests against every edge. Measured by the script: that
#: family's cost to price fell from 3.6-8.1 to 0.8-1.5, and 110 such holes are
#: refused in 0.07 s instead of 0.6-1.5 s.
_BRIDGE_UNITS: Final = 600
_EAR_STEP_UNITS: Final = 300  # the ear clipper: per corner looked at
_EAR_TEST_UNITS: Final = 6_000  # per corner TESTED against the loop …
_EAR_VERTEX_UNITS: Final = 3  # … per vertex of the loop (which of them are near?) …
_EAR_NEAR_UNITS: Final = 400  # … and per vertex near, when they are few (one by one)
_EAR_MANY_UNITS: Final = 15_000  # … or, when they are many (arrays): this …
_EAR_MANY_NEAR_UNITS: Final = 40  # … and this per vertex near
_SHARED_CLIP_UNITS: Final = 200  # triangulate_polygon (small rings without holes): per n²
#: The native triangulation (``mapbox_earcut``, ISC; ADR-069) of a loop of n vertices costs
#: ``_EARCUT_VERTEX_UNITS * n + _EARCUT_SQUARE_UNITS * n²`` AT MOST. Linear for the usual
#: outline (a comb of 16,003 vertices 1.4 ms, a traced one 15 ms), quadratic for the worst
#: ring it has been measured on — a spiral of 16,000 vertices, 611 ms, 2.4 ns per n² — so it
#: is priced by that worst case: 3 units per n², and paid for BEFORE the native call.
_EARCUT_VERTEX_UNITS: Final = 2_000  # per vertex: the arrays in and out, the flat-corner filter
#: The joint edge test of a region's rings (``ring_conflict``): two sorts per edge …
_SWEEP_EDGE_UNITS: Final = 800
#: … and per candidate pair — two edges whose spans overlap on the axis it sweeps: counted, and
#: paid for, BEFORE the pairs are made (circle of 16,384 edges: 34,610 of them, 5.7 ms; a
#: spiral of 16,000: 2.8 M, 139 ms)
_SWEEP_CANDIDATE_UNITS: Final = 80
_SWEEP_BLOCK: Final = 1 << 20  # candidate pairs made at once: bounds the temporaries
_EARCUT_SQUARE_UNITS: Final = 3  # per vertex squared: the worst case measured

#: From this many vertices on, a ring WITHOUT holes is cut by the array ear clipper
#: as well. Below it ``triangulate_polygon`` — the clipper the Qt 3D view uses —
#: is faster and gives that view's triangles vertex for vertex; above it the plain
#: loop is what an edit of a traced outline waits for on every tick. Measured, same
#: machine, same load: 100 vertices 2.3 ms (loop) / 4.0 ms (arrays); 500: 76 / 25;
#: 1,000: 272 / 30.
ARRAY_EAR_CLIP_FROM: Final = 256
_BRIDGE_CANDIDATES: Final = 6  # boundary vertices tried per block, nearest first
_FEW_NEAR: Final = 16  # up to this many vertices near an ear are tested one by one


class RegionTooLargeError(ValueError):
    """Cutting a region would cost more than ``MAX_REGION_WORK``: it is refused
    for its SIZE, whatever its shape. (A ``ValueError``, like every other reason
    a region cannot be cut.)"""


def _too_large(what: str) -> str:
    return (f"{what} is beyond what is cut here (the work bound, MAX_REGION_WORK = "
            f"{MAX_REGION_WORK:,} units)")


def _refuse(what: str) -> NoReturn:
    raise RegionTooLargeError(_too_large(what))


class WorkBudget:
    """What is left to spend — on ONE region's cut, or on everything ONE item's
    outline needs. ``spend`` raises ``RegionTooLargeError`` the moment the bound
    is passed, so no more UNITS are spent than the bound: pay for a step BEFORE
    it runs wherever its price is known beforehand, and as it goes where it is
    not (the ears, the bridges). What a unit takes is measured, per step, by
    ``scripts/measure_region_work.py`` — a price that is too low is a step that
    runs longer than its units say (a union asked for a tree did, twice: 3.6 s
    and 5.3 s inside the budget, until the reviews of fix rounds 3 and 4)."""

    __slots__ = ("budget", "left", "what")

    def __init__(self, what: str = "an outline", budget: int | None = None) -> None:
        self.what = what
        self.budget = MAX_REGION_WORK if budget is None else budget
        self.left = self.budget

    @property
    def spent(self) -> int:
        return self.budget - self.left

    def spend(self, units: int) -> None:
        self.left -= units
        if self.left < 0:
            _refuse(self.what)

    def refuse(self) -> NoReturn:
        """Refuse outright: for a size that no budget covers (``MAX_ITEM_VERTICES``)."""
        _refuse(self.what)


def _simplicity_work(vertices: int) -> int:
    """What ``is_simple_ring`` costs for a ring of that many vertices AT LEAST: every
    pair of its edges once. (On arrays the pairs whose boxes meet cost more, and
    are paid for as they are counted — ``touching_pairs``.)"""
    pair = _PAIR_UNITS if vertices >= SIMPLE_RING_NUMPY_FROM else _SMALL_PAIR_UNITS
    return pair * vertices * vertices


def _ask_work(vertices: int) -> int:
    """What asking ONE outer ring of that many vertices about ONE point costs (``_ring_holds``)."""
    if vertices >= SIMPLE_RING_NUMPY_FROM:
        return _ASK_UNITS + _ASK_VERTEX_UNITS * vertices
    return _ASK_SMALL_VERTEX_UNITS * (vertices + 2)


def touching_pairs(points: Sequence[Sequence[float]], work: WorkBudget, *, closed: bool,
                   reach: float = 0.0) -> tuple[int, int]:
    """``(near, touching)`` among the pairs of NON-ADJACENT segments of a path —
    of a ring when ``closed``.

    ``touching``: the pairs that share a point — where a polygon crosses or
    touches itself, where a path crosses its own line. ``near``: the pairs whose
    bounding boxes meet once each is widened by ``reach``; every touching pair
    is among them. These two numbers are what the clipper's work on the path
    depends on, and they are counted BEFORE the clipper sees it: 800 points
    scribbled across a plan cross 73,000 times, and resolving them took ten
    seconds.

    The count itself is every pair once, on arrays, and is paid into ``work``
    before it runs; the near pairs are paid for — all of them — before the first
    is tested.
    """
    segments = len(points) if closed else len(points) - 1
    if segments < 3:
        return 0, 0
    work.spend(_PAIR_UNITS * segments * segments)
    xy = np.asarray(points, dtype=np.float64)
    first, second = xy[:segments], np.roll(xy, -1, axis=0)[:segments]
    low, high = np.minimum(first, second) - reach, np.maximum(first, second) + reach
    index = np.arange(segments)
    found: list[tuple[NDArray[np.intp], NDArray[np.intp]]] = []
    near_pairs = 0
    for start in range(0, segments, _SIMPLE_RING_ROWS):
        rows = slice(start, min(start + _SIMPLE_RING_ROWS, segments))
        later = slice(start, segments)
        row = index[rows, None]
        column = index[None, later]
        near = ((low[rows, None, 0] <= high[None, later, 0]) & (low[None, later, 0] <= high[rows, None, 0])
                & (low[rows, None, 1] <= high[None, later, 1]) & (low[None, later, 1] <= high[rows, None, 1])
                & (column > row + 1))
        if closed:
            near &= ~((row == 0) & (column == segments - 1))  # the ring's last segment meets its first
        i, j = np.nonzero(near)
        if not len(i):
            continue
        near_pairs += len(i)
        work.spend(_NEAR_PAIR_UNITS * len(i))
        found.append((i + start, j + start))
    # … and only now, with ALL of them paid for, is the first one tested: a path whose near
    # pairs alone are beyond the budget is refused on the count
    touching = 0
    for i, j in found:
        touching += int(np.count_nonzero(_touch(first[i, 0], first[i, 1], second[i, 0], second[i, 1],
                                                first[j, 0], first[j, 1], second[j, 0], second[j, 1])))
    return near_pairs, touching


def _hard_contact(ax: _Floats, ay: _Floats, bx: _Floats, by: _Floats,
                  cx: _Floats, cy: _Floats, dx: _Floats, dy: _Floats) -> NDArray[np.bool_]:
    """The segments a–b and c–d CROSS (each passes through the other's interior) or lie along
    each other for more than a point. What a touch that is no more than a point is not."""
    d1 = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx)
    d2 = (dx - cx) * (by - cy) - (dy - cy) * (bx - cx)
    d3 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    d4 = (bx - ax) * (dy - ay) - (by - ay) * (dx - ax)
    crossing = (((d1 > 0) != (d2 > 0)) & (d1 != 0) & (d2 != 0)
                & ((d3 > 0) != (d4 > 0)) & (d3 != 0) & (d4 != 0))
    along_x = (np.minimum(np.maximum(ax, bx), np.maximum(cx, dx))
               - np.maximum(np.minimum(ax, bx), np.minimum(cx, dx))) > 0
    along_y = (np.minimum(np.maximum(ay, by), np.maximum(cy, dy))
               - np.maximum(np.minimum(ay, by), np.minimum(cy, dy))) > 0
    return np.asarray(crossing | ((d1 == 0) & (d2 == 0) & (along_x | along_y)))


def _shared_corner(a: NDArray[np.float64], b: NDArray[np.float64], c: NDArray[np.float64],
                   d: NDArray[np.float64]) -> NDArray[np.bool_]:
    """Segments a–b and c–d have an END in common: the two rings meet corner to corner.
    (A hole that touches the outer ring with a corner on the middle of one of its edges is
    a pinch the cut handles; one that meets a corner of it is read apart by the snapshot.)"""
    def same(p: NDArray[np.float64], q: NDArray[np.float64]) -> NDArray[np.bool_]:
        return np.asarray((p[:, 0] == q[:, 0]) & (p[:, 1] == q[:, 1]))

    return same(a, c) | same(a, d) | same(b, c) | same(b, d)


def _contact_points(a: NDArray[np.float64], b: NDArray[np.float64], c: NDArray[np.float64],
                    d: NDArray[np.float64], tag: NDArray[np.intp]) -> NDArray[np.float64]:
    """Where segments a–b and c–d, which touch in no more than a point, touch: the end of one
    that lies on the other. Rows of ``(tag, x, y)``."""
    def on(p: NDArray[np.float64], s: NDArray[np.float64], e: NDArray[np.float64]) -> NDArray[np.bool_]:
        cross = (e[:, 0] - s[:, 0]) * (p[:, 1] - s[:, 1]) - (e[:, 1] - s[:, 1]) * (p[:, 0] - s[:, 0])
        return np.asarray((cross == 0) & _within(p[:, 0], p[:, 1], s[:, 0], s[:, 1], e[:, 0], e[:, 1]))

    point = np.where(on(a, c, d)[:, None], a, np.where(on(b, c, d)[:, None], b, np.where(
        on(c, a, b)[:, None], c, d)))
    return np.column_stack([tag.astype(np.float64), point])


def ring_conflict(rings: Sequence[Sequence[Sequence[float]]], work: WorkBudget) -> tuple[int, int] | None:
    """The first pair of rings of a region that cannot be cut together — ``(a, b)``,
    ``a <= b``, the smallest such pair, ring 0 being the outer one; ``(a, a)`` is a ring
    that crosses or touches ITSELF — or None. What conflicts:

    - a ring whose non-adjacent edges meet at all (it is not simple);
    - two holes whose edges meet at all (they overlap, or share a point);
    - a hole and the outer ring whose edges CROSS or run along each other. A hole
      that touches the outer ring in a point is not a conflict: it is a region with a
      pinch, and the cut handles it (``test_touching_is_not_refused_for_its_own_sake``).

    This one test stands in for the quadratic simplicity test per ring AND for the
    bridge search that used to find a hole on its outer ring.

    A sweep, not every pair. Both axes are sorted; on the one with fewer candidates
    an edge is paired with the edges that begin before it ends (counted with a
    binary search, and paid for before one pair is made), then those whose spans
    meet on the other axis are tested exactly (``_touch``, the same four cross
    products as ``segments_touch``). An outline has a few candidates per edge: a
    circle of 16,384 edges 34,610 against 134 million pairs. Every touching pair is
    among them — two segments that share a point have spans that meet on both axes.
    """
    sizes = [len(ring) for ring in rings]
    edges = sum(sizes)
    if edges < 3:
        return None
    work.spend(_SWEEP_EDGE_UNITS * edges)
    xy = [np.asarray(ring, dtype=np.float64).reshape(-1, 2) for ring in rings]
    first = np.concatenate(xy)
    second = np.concatenate([np.roll(points, -1, axis=0) for points in xy])
    ring_of = np.repeat(np.arange(len(sizes)), sizes)
    size_of = np.repeat(np.asarray(sizes), sizes)
    place = np.concatenate([np.arange(size) for size in sizes])
    low, high = np.minimum(first, second), np.maximum(first, second)
    best: tuple[int, int, NDArray[np.intp], NDArray[np.intp]] | None = None
    for axis in (0, 1):
        order = np.argsort(low[:, axis], kind="stable")
        ends = np.searchsorted(low[order, axis], high[order, axis], side="right")
        counts = ends - np.arange(1, edges + 1)
        total = int(counts.sum())
        if best is None or total < best[0]:
            best = (total, axis, order, counts)
    assert best is not None
    candidates, axis, order, counts = best
    work.spend(_SWEEP_CANDIDATE_UNITS * candidates)
    other = 1 - axis
    found: list[tuple[NDArray[np.intp], NDArray[np.intp]]] = []
    ahead = np.cumsum(counts)
    start = 0
    while start < edges:
        stop = max(start + 1, int(np.searchsorted(ahead, (ahead[start - 1] if start else 0) + _SWEEP_BLOCK,
                                                  side="right")))
        block = counts[start:stop]
        total = int(block.sum())
        if total:
            i = np.repeat(np.arange(start, stop), block)
            j = i + 1 + (np.arange(total) - np.repeat(np.cumsum(block) - block, block))
            p, q = order[i], order[j]
            gap = np.abs(place[p] - place[q])
            keep = ((low[p, other] <= high[q, other]) & (low[q, other] <= high[p, other])
                    & ~((ring_of[p] == ring_of[q]) & ((gap == 1) | (gap == size_of[p] - 1))))
            if keep.any():
                work.spend(_NEAR_PAIR_UNITS * int(np.count_nonzero(keep)))
                found.append((p[keep], q[keep]))
        start = stop
    # … and only now, with ALL of them paid for, is the first one tested
    meet: int | None = None
    pinches: list[NDArray[np.float64]] = []
    count = len(sizes)
    for p, q in found:
        touching = _touch(first[p, 0], first[p, 1], second[p, 0], second[p, 1],
                          first[q, 0], first[q, 1], second[q, 0], second[q, 1])
        if not touching.any():
            continue
        p, q = p[touching], q[touching]
        a, b = ring_of[p], ring_of[q]
        low_ring, high_ring = np.minimum(a, b), np.maximum(a, b)
        pinch = (low_ring == 0) & (high_ring != 0)  # a hole and the outer ring: a point is no conflict
        bad = ~pinch
        if pinch.any():
            bad |= pinch & (_hard_contact(first[p, 0], first[p, 1], second[p, 0], second[p, 1],
                                          first[q, 0], first[q, 1], second[q, 0], second[q, 1])
                            | _shared_corner(first[p], second[p], first[q], second[q]))
        if bad.any():
            key = int((low_ring[bad] * count + high_ring[bad]).min())
            meet = key if meet is None else min(meet, key)
        kept = pinch & ~bad
        if kept.any():
            pinches.append(_contact_points(first[p[kept]], second[p[kept]], first[q[kept]], second[q[kept]],
                                           high_ring[kept]))
    if pinches:
        # a hole that touches the outer ring in ONE point is a pinch the cut handles; in two it
        # splits the region in two, which is no region of one cut (the snapshot reads it apart)
        points = np.unique(np.concatenate(pinches), axis=0)
        holes_touching, touches = np.unique(points[:, 0], return_counts=True)
        if (touches > 1).any():
            key = int(holes_touching[touches > 1].min())  # (0, hole): the outer ring and that hole
            meet = key if meet is None else min(meet, key)
    if meet is None:
        return None
    return meet // count, meet % count


def stack_height(rings: Sequence[Sequence[Sequence[float]]], *, closed: bool, reach: float = 0.0,
                 flat: bool = True) -> int:
    """The most segments of ``rings`` — of paths when not ``closed`` — that ONE
    horizontal line crosses, each segment's height widened by ``reach``.

    What a sweep-line clipper pays per step: it carries every edge the line
    crosses. A zigzag of 4,000 points whose teeth stand side by side, crossing
    nothing, has a stack of 4,000 and took the clipper 1.6 s to inflate; lying on
    its side it has a stack of 2 and took 4 ms. Linear to compute (one sort).

    ``flat=False`` leaves out the segments WITHOUT a height — for a path the
    clipper inflates: the two sides of an exactly level segment are level edges,
    which the sweep walks along and does not carry. (Counted, a straight fence
    running east–west was charged its points squared for 7 ms of work, and fitted
    a fifth of the points the same fence fitted running north–south.)
    """
    lows, highs = [], []
    for ring in rings:
        if len(ring) < 2:
            continue
        y = np.asarray(ring, dtype=np.float64)[:, 1]
        following = np.roll(y, -1)
        if not closed:
            y, following = y[:-1], following[:-1]
        if not flat:
            y, following = y[y != following], following[y != following]
        lows.append(np.minimum(y, following))
        highs.append(np.maximum(y, following))
    if not sum(len(low) for low in lows):
        return 0
    low, high = np.sort(np.concatenate(lows) - reach), np.sort(np.concatenate(highs) + reach)
    # at the k-th lowest lower end: k + 1 segments have begun, and those whose upper end
    # lies below it have ended
    return int((np.arange(1, len(low) + 1) - np.searchsorted(high, low, side="left")).max())


def _earcut_work(vertices: int) -> int:
    """What the native triangulation of a loop of that many vertices is priced at."""
    return _EARCUT_VERTEX_UNITS * vertices + _EARCUT_SQUARE_UNITS * vertices * vertices


def _triangulation_floor(outer_vertices: int, hole_sizes: Sequence[int]) -> int:
    """The LEAST ``triangulate_region`` can cost for rings of these sizes. A ring
    without holes of fewer than ``ARRAY_EAR_CLIP_FROM`` vertices keeps the shared ear
    clipper (the Qt-free builders' own, whose triangles the golden meshes pin); every
    other region is ONE native call, paid for in full BEFORE it runs, from the sizes
    alone — so the floor is the price (``_earcut_work``): there is no cheaper case."""
    if not hole_sizes and outer_vertices < ARRAY_EAR_CLIP_FROM:
        return _SHARED_CLIP_UNITS * outer_vertices * outer_vertices
    return _earcut_work(outer_vertices + sum(hole_sizes))


def region_work(outer: Sequence[Sequence[float]], holes: Sequence[Sequence[Sequence[float]]] = ()) -> int:
    """The least ``cut_region`` can cost for this region, in work units — from
    the SIZES of its rings alone (their vertex counts; no coordinate is read), so
    it costs nothing to ask. A region with ``region_work(...) > MAX_REGION_WORK``
    is refused before any test runs; one below may still be refused while it is
    cut, when its shape makes the bridges or the ears cost more than the least."""
    sizes = [len(hole) for hole in holes]
    return (_REGION_UNITS + _SWEEP_EDGE_UNITS * (len(outer) + sum(sizes))
            + _triangulation_floor(len(outer), sizes))


def exceeds_work_bound(outer: Sequence[Sequence[float]],
                       holes: Sequence[Sequence[Sequence[float]]] = ()) -> bool:
    """True when rings of these SIZES are beyond ``MAX_REGION_WORK`` whatever
    their shape — ``region_work(...) > MAX_REGION_WORK``. Costs nothing to ask;
    ask it before doing anything to an outline that costs."""
    return region_work(outer, holes) > MAX_REGION_WORK


def _bridge_position(points: Sequence[Point], xy: NDArray[np.float64], loop: list[int],
                     hole_vertex: int, waiting_first: NDArray[np.intp],
                     waiting_second: NDArray[np.intp], work: WorkBudget) -> int:
    """The position in ``loop`` of the nearest boundary vertex that ``hole_vertex``
    can be bridged to: the segment between them touches no edge of the boundary
    or of a hole still to be merged (``waiting_first`` → ``waiting_second``, this
    hole's own edges among them), and leaves the boundary into its inside.

    Boundary vertices are tried nearest first, a block at a time, each block
    against every edge at once. Per hole that is one sort of the boundary plus,
    usually, one block: O(L log L + E) for a boundary of L vertices and E edges.
    A hole whose nearest boundary vertices are all hidden takes block after
    block — which is why each block is paid for (``work``).
    """
    index = np.asarray(loop, dtype=np.intp)
    first = np.concatenate([index, waiting_first])
    second = np.concatenate([np.roll(index, -1), waiting_second])
    work.spend(_HOLE_UNITS + _HOLE_VERTEX_UNITS * len(index) + _HOLE_EDGE_UNITS * len(first))
    cx, cy, dx, dy = xy[first, 0], xy[first, 1], xy[second, 0], xy[second, 1]
    hx, hy = float(xy[hole_vertex, 0]), float(xy[hole_vertex, 1])
    at_hole = (first == hole_vertex) | (second == hole_vertex)
    order = np.argsort(np.hypot(xy[index, 0] - hx, xy[index, 1] - hy), kind="stable")
    block = _BRIDGE_UNITS * len(first)
    for start in range(0, len(order), _BRIDGE_CANDIDATES):
        positions = [int(at) for at in order[start:start + _BRIDGE_CANDIDATES]
                     if _inside_corner(points, loop, int(at), hole_vertex)]
        if not positions:
            work.spend(_BRIDGE_CANDIDATES * _EAR_STEP_UNITS)
            continue
        work.spend(block)
        ends = index[positions]
        ax, ay = xy[ends, 0][:, None], xy[ends, 1][:, None]
        starts_here = first[None, :] == ends[:, None]
        at_end = starts_here | (second[None, :] == ends[:, None])
        # an edge that starts at an end of the bridge blocks it only when its far
        # end lies ON the bridge (they would overlap); every other edge when it
        # touches the bridge anywhere
        far = np.where(starts_here | (first == hole_vertex)[None, :], second[None, :], first[None, :])
        fx, fy = xy[far, 0], xy[far, 1]
        overlapping = (((hx - ax) * (fy - ay) - (hy - ay) * (fx - ax) == 0)
                       & _within(fx, fy, ax, ay, hx, hy))
        touching = _touch(ax, ay, hx, hy, cx[None, :], cy[None, :], dx[None, :], dy[None, :])
        blocked = np.where(at_end | at_hole[None, :], overlapping, touching).any(axis=1)
        free = np.flatnonzero(~blocked)
        if len(free):
            return positions[int(free[0])]
    raise ValueError("no bridge from a hole to its outer ring (rings touch or cross)")


#: Three vertices on one line have a cross product of zero — in exact arithmetic.
#: In floats it comes out as noise of either sign, about 4 · 2⁻⁵³ · (the largest
#: coordinate) · (the corner's two edges). A corner whose doubled area is below
#: this many times that product is FLAT: clipping it yields no triangle.
_FLAT_CORNER: Final = 4e-15


def _ear_clip(points: Sequence[Point], loop: Sequence[int], work: WorkBudget) -> list[Triangle]:
    """Clip ears of a counter-clockwise loop of indices into ``points``. The loop
    may visit a vertex twice (a bridge to a hole runs out and back): a second
    visit to an ear's own corner never blocks that ear.

    Each candidate corner is tested against every vertex still in the loop at
    once; after a clipped ear the search goes on at its neighbour. O(n) array
    passes for a well-behaved loop of n vertices, O(n²) at worst — a comb, whose
    every tooth has to wait for its neighbour — so every corner looked at and
    every test is paid for (``work``).

    An ear without an area — three vertices of different rings on one line, as
    along the edge of a diagonal stroke that other strokes cross — is clipped
    like any other and yields NO triangle (``_FLAT_CORNER``): it covers nothing,
    and rounded to the engine's float32 it would come out wound either way.
    """
    n = len(loop)
    xs = [points[i][0] for i in loop]
    ys = [points[i][1] for i in loop]
    x, y = np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)
    alive = np.ones(n, dtype=bool)
    before = [n - 1, *range(n - 1)]
    after = [*range(1, n), 0]
    triangles: list[Triangle] = []
    test = _EAR_TEST_UNITS + _EAR_VERTEX_UNITS * n
    remaining, at, misses = n, 0, 0
    while remaining > 3:
        a, c = before[at], after[at]
        ax, ay, bx, by, cx, cy = xs[a], ys[a], xs[at], ys[at], xs[c], ys[c]
        ear = False
        if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 0:  # a convex corner
            work.spend(test)
            # only a vertex inside the triangle's bounding box can be inside the triangle
            near = np.flatnonzero(alive & (x >= min(ax, bx, cx)) & (x <= max(ax, bx, cx))
                                  & (y >= min(ay, by, cy)) & (y <= max(ay, by, cy)))
            work.spend(_EAR_NEAR_UNITS * len(near) if len(near) <= _FEW_NEAR
                       else _EAR_MANY_UNITS + _EAR_MANY_NEAR_UNITS * len(near))
            if len(near) <= _FEW_NEAR:
                # the usual case — the ear's own corners and a neighbour or two: the
                # same test, written out (forty array calls on three numbers cost
                # more than the three numbers)
                ear = True
                for k in near.tolist():
                    qx, qy = xs[k], ys[k]
                    if (qx == ax and qy == ay) or (qx == bx and qy == by) or (qx == cx and qy == cy):
                        continue
                    e1 = (ax - qx) * (by - qy) - (ay - qy) * (bx - qx)
                    e2 = (bx - qx) * (cy - qy) - (by - qy) * (cx - qx)
                    e3 = (cx - qx) * (ay - qy) - (cy - qy) * (ax - qx)
                    if not ((e1 < 0 or e2 < 0 or e3 < 0) and (e1 > 0 or e2 > 0 or e3 > 0)):
                        ear = False
                        break
            else:
                px, py = x[near], y[near]
                d1 = (ax - px) * (by - py) - (ay - py) * (bx - px)  # _point_in_triangle, for each
                d2 = (bx - px) * (cy - py) - (by - py) * (cx - px)
                d3 = (cx - px) * (ay - py) - (cy - py) * (ax - px)
                inside = ~(((d1 < 0) | (d2 < 0) | (d3 < 0)) & ((d1 > 0) | (d2 > 0) | (d3 > 0)))
                corner = (((px == ax) & (py == ay)) | ((px == bx) & (py == by))
                          | ((px == cx) & (py == cy)))
                ear = not bool(np.any(inside & ~corner))
        else:
            work.spend(_EAR_STEP_UNITS)
        if ear:
            reach = max(abs(ax), abs(ay), abs(bx), abs(by), abs(cx), abs(cy))
            edges = abs(bx - ax) + abs(by - ay) + abs(cx - ax) + abs(cy - ay)
            if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > _FLAT_CORNER * reach * edges:
                triangles.append((loop[a], loop[at], loop[c]))
            alive[at] = False
            after[a], before[c] = c, a
            remaining -= 1
            at, misses = a, 0
            continue
        at = c
        misses += 1
        if misses > remaining:
            raise ValueError("the region cannot be triangulated (degenerate or self-touching rings)")
    b, c = after[at], after[after[at]]
    last = _cross(points[loop[at]], points[loop[b]], points[loop[c]])
    if last < 0:
        raise ValueError("the region cannot be triangulated (a clockwise remainder)")
    if last > 0:
        triangles.append((loop[at], loop[b], loop[c]))
    return triangles


def _described(outer: Sequence[object], holes: Sequence[Sequence[object]]) -> str:
    vertices = len(outer) + sum(len(hole) for hole in holes)
    return f"a region of {vertices} vertices with {len(holes)} holes"


def _triangulate(outer: Ring, holes: Sequence[Ring], work: WorkBudget) -> tuple[tuple[Point, ...], list[Triangle]]:
    """``triangulate_region``, paying into ``work``: ONE native call (``mapbox_earcut``).

    The rings are judged first (``ring_conflict``: simple, clear of each other,
    each hole inside the outer ring) — earcut is only asked about a region it can
    cut — and the native call is paid for before it runs (``_earcut_work``), from
    the sizes alone. The answer is not trusted for being an answer: flat triangles (three vertices on one line,
    which round to either winding in the engine's float32) are dropped here, and
    ``_cut`` proves what is left — every triangle faces up, the areas add up.
    """
    rings = (outer, *holes)
    for number, ring in enumerate(rings):
        n = len(ring)
        if n < 3 or any(ring[i] == ring[(i + 1) % n] for i in range(n)):
            raise ValueError(_not_simple(number, n))  # fewer than three corners, or an edge without a length
    met = ring_conflict(rings, work)
    if met is not None:
        a, b = met
        if a == b:
            raise ValueError(_not_simple(a, len(rings[a])))
        raise ValueError(f"two rings of a region ({len(rings[a])} and {len(rings[b])} vertices) "
                         "cross, overlap or touch each other")
    for hole in holes:  # each one inside the outer ring (it touches nothing: one point decides)
        if not _ring_holds(outer)(*_point_inside(hole)):
            raise ValueError(f"a hole ring of {len(hole)} vertices does not lie inside its outer ring")
    points: tuple[Point, ...] = tuple(outer) + tuple(p for hole in holes for p in hole)
    if not holes and len(outer) < ARRAY_EAR_CLIP_FROM:
        work.spend(_SHARED_CLIP_UNITS * len(outer) * len(outer))
        return points, triangulate_polygon(outer)
    work.spend(_earcut_work(len(points)))
    xy = np.asarray(points, dtype=np.float64)
    ends = np.cumsum([len(outer), *(len(hole) for hole in holes)]).astype(np.uint32)
    found = np.asarray(mapbox_earcut.triangulate_float64(xy, ends), dtype=np.int64).reshape(-1, 3)
    if not len(found):
        return points, []
    a, b, c = xy[found[:, 0]], xy[found[:, 1]], xy[found[:, 2]]
    doubled = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    reach = np.max(np.abs(np.stack([a, b, c])), axis=(0, 2))
    edges = (np.abs(b[:, 0] - a[:, 0]) + np.abs(b[:, 1] - a[:, 1])
             + np.abs(c[:, 0] - a[:, 0]) + np.abs(c[:, 1] - a[:, 1]))
    kept = found[doubled > _FLAT_CORNER * reach * edges]
    return points, [(int(i), int(j), int(k)) for i, j, k in kept.tolist()]


def _triangulate_reference(outer: Ring, holes: Sequence[Ring],
                           work: WorkBudget) -> tuple[tuple[Point, ...], list[Triangle]]:
    """The pure-Python triangulation ``_triangulate`` replaced (bridges and an
    ear clipper, priced per step). No production path calls it: it is the
    independent REFERENCE the tests hold the native answer against."""
    points: tuple[Point, ...] = tuple(outer) + tuple(p for hole in holes for p in hole)
    if not holes:
        if len(outer) >= ARRAY_EAR_CLIP_FROM and ring_area(outer) > 0.0:
            return points, _ear_clip(points, range(len(outer)), work)
        work.spend(_SHARED_CLIP_UNITS * len(outer) * len(outer))
        return points, triangulate_polygon(outer)
    xy = np.asarray(points, dtype=np.float64)
    loop = list(range(len(outer)))
    waiting: list[list[int]] = []
    start = len(outer)
    for hole in holes:
        waiting.append(list(range(start, start + len(hole))))
        start += len(hole)
    waiting.sort(key=lambda ring: max(points[i][0] for i in ring), reverse=True)
    rings = [np.asarray(ring, dtype=np.intp) for ring in waiting]
    first = np.concatenate(rings)  # the edges of every hole, in the order they are merged
    second = np.concatenate([np.roll(ring, -1) for ring in rings])
    begins = np.cumsum([0, *(len(ring) for ring in waiting)])
    for number, ring in enumerate(waiting):
        k = max(range(len(ring)), key=lambda j: points[ring[j]])  # its rightmost vertex
        at = _bridge_position(points, xy, loop, ring[k], first[begins[number]:],
                              second[begins[number]:], work)
        # out along the bridge, once around the hole, and back
        loop[at + 1:at + 1] = ring[k:] + ring[:k] + [ring[k], loop[at]]
    return points, _ear_clip(points, loop, work)


def triangulate_region(
    outer: Ring, holes: Sequence[Ring] = ()
) -> tuple[tuple[Point, ...], list[Triangle]]:
    """Triangulate one region: ``(vertices, triangles)``.

    ``vertices`` is ``outer`` followed by every hole, unchanged — the triangles
    index into it, are all counter-clockwise, and cover exactly the outer minus
    the holes (n + 2h − 2 of them for n vertices and h holes, fewer where three
    vertices lie on one line). ``outer`` must be a simple counter-clockwise ring and each hole a
    simple clockwise ring strictly inside it, none touching another; anything
    the algorithm cannot triangulate raises ``ValueError`` rather than returning
    a wrong cap. Use ``cut_region`` to get the result PROVEN (areas checked).

    Without holes this is ``triangulate_polygon`` (the ear clipper the Qt 3D view
    uses) — up to ``ARRAY_EAR_CLIP_FROM`` vertices; a larger ring is cut by the
    array ear clipper used for regions with holes: the same polygon, other
    triangles, a ninth of the time at 1,000 vertices. With holes, each one is first joined to the boundary by a *bridge* —
    a vertex-to-vertex segment that touches no edge — which turns the region
    into one ring that walks out to the hole, around it and back. Holes are
    taken rightmost first, each from its rightmost vertex: no hole still waiting
    can then stand between that vertex and the boundary to its right, so a
    bridge always exists.

    Its work is bounded like ``cut_region``'s (``MAX_REGION_WORK``): refused
    with ``RegionTooLargeError`` before it starts when the rings' sizes alone
    put it beyond the bound, and while it runs when the shape does.
    """
    what = _described(outer, holes)
    if _triangulation_floor(len(outer), [len(hole) for hole in holes]) > MAX_REGION_WORK:
        _refuse(what)
    return _triangulate(outer, holes, WorkBudget(what))


# ── the one predicate ─────────────────────────────────────────────────────────


_Cut: TypeAlias = tuple[tuple[Point, ...], tuple[Triangle, ...]]
_BUILDABLE, _UNBUILDABLE, _TOO_LARGE = 0, 1, 2
#: Up to this many vertices, and without holes, a region is looked up before it
#: is sized up (a rectangle is asked on every tick; ``_cut`` judges its size
#: anyway). Anything larger is sized up BEFORE it is hashed.
_SMALL_REGION: Final = 64


class _Examined(NamedTuple):
    """What cutting a region came to: the verdict, the work it took, the cut
    when there is one and the refusal's words when there is not."""

    verdict: int
    spent: int
    cut: _Cut | None
    why: str


def _region_vertices(outer: Ring, holes: tuple[Ring, ...]) -> int:
    return len(outer) + sum(len(hole) for hole in holes)


@ring_keyed(vertices=_region_vertices, holds=lambda examined: len(examined.cut[1]) if examined.cut else 0)
def _examined(outer: Ring, holes: tuple[Ring, ...]) -> _Examined:
    """``_cut``, remembered — refusals included: a region that cannot be built
    must not be tried again on every tick. ONE memory for the verdict, what it
    cost and the cut, so that the builder gets the cut the verdict made."""
    return _examination(outer, holes, WorkBudget(_described(outer, holes)))


def _examination(outer: Ring, holes: tuple[Ring, ...], work: WorkBudget) -> _Examined:
    try:
        cut = _cut(outer, holes, work)
    except RegionTooLargeError as error:
        return _Examined(_TOO_LARGE, work.spent, None, str(error))
    except ValueError as error:
        return _Examined(_UNBUILDABLE, work.spent, None, str(error))
    return _Examined(_BUILDABLE, work.spent, cut, "")


def _examine(outer: Ring, holes: tuple[Ring, ...]) -> _Examined:
    """``_examined`` — after the SIZE: a region whose rings alone put it beyond
    the bound is answered from their lengths, never hashed and never a key."""
    if (len(outer) > _SMALL_REGION or holes) and exceeds_work_bound(outer, holes):
        return _Examined(_TOO_LARGE, 0, None, _too_large(_described(outer, holes)))
    return _examined(outer, holes)


def cut_region(outer: Ring, holes: tuple[Ring, ...] = ()) -> _Cut:
    """``triangulate_region``, with the result PROVEN before it is handed out.

    Raises ``ValueError`` unless the outer ring is a simple counter-clockwise
    polygon, every hole a simple clockwise one, every triangle of the result
    faces up, and the triangles' areas add up to the region's (outer minus
    holes) — the two facts a wrong triangulation cannot both satisfy. This is
    what the default builder calls (``build.prism_mesh``); remembered, so asking
    whether a region can be built costs nothing again when it then is — and a
    refusal is remembered with its words.

    The size is judged FIRST: ``RegionTooLargeError`` (a ``ValueError``) when
    ``region_work`` is beyond ``MAX_REGION_WORK`` — raised before the simplicity
    test or anything else that costs — and when the cut itself, once started,
    would pass the bound.
    """
    examined = _examine(outer, holes)
    if examined.cut is None:
        raise (RegionTooLargeError if examined.verdict == _TOO_LARGE else ValueError)(examined.why)
    return examined.cut


def cut_work(outer: Ring, holes: tuple[Ring, ...] = ()) -> int:
    """What ``cut_region`` spends on this region, in work units — by cutting it
    (nothing is remembered). At least ``region_work(outer, holes)``; raises what
    ``cut_region`` raises. For measurements and tests: a count is the same on
    every machine, a duration is not."""
    work = WorkBudget(_described(outer, holes))
    _cut(outer, holes, work)
    return work.spent


def region_cost(outer: Ring, holes: tuple[Ring, ...] = ()) -> int:
    """What finding out about this region HAS cost, in work units — remembered
    with the verdict, and the same whether the region could be built or not
    (``region_work`` is the least a cut can cost, from the sizes alone; this is
    what it did cost). 0 for a region refused from its size alone."""
    return _examine(outer, holes).spent


def pay_for_region(outer: Ring, holes: tuple[Ring, ...], work: WorkBudget) -> bool:
    """``is_buildable_region``, paid out of ``work``: True when the region can be
    built, False when its SHAPE cannot. For a caller that judges several regions
    against ONE budget — a thousand regions that each fit the bound do not fit it
    together.

    The region is not hashed, let alone cut, unless the least it can cost
    (``region_work``) is still in ``work``; then it is cut out of what ``work``
    has LEFT, never out of a bound of its own, and what it cost is paid when it
    is known (a remembered region costs what it cost the first time: the total
    does not depend on what happens to be remembered). ``RegionTooLargeError``
    when ``work`` does not cover it, or when the region is beyond the bound by
    itself. A region refused only for what its caller had left is no fact about
    the region, and is not remembered.
    """
    if region_work(outer, holes) > work.left:
        work.refuse()
    examined = _examined.known(outer, holes)
    if examined is None:
        own = WorkBudget(_described(outer, holes), min(work.left, MAX_REGION_WORK))
        examined = _examination(outer, holes, own)
        if examined.verdict == _TOO_LARGE and own.budget < MAX_REGION_WORK:
            work.spend(own.spent)  # more than the caller had left — this raises
            work.refuse()
        _examined.remember((outer, holes), examined)
    work.spend(examined.spent)
    if examined.verdict == _TOO_LARGE:
        work.refuse()
    return examined.verdict == _BUILDABLE


def _not_simple(number: int, vertices: int) -> str:
    what = "a footprint" if number == 0 else "a hole"
    return f"{what} ring of {vertices} vertices is not a simple polygon (it crosses or touches itself)"


def _cut(outer: Ring, holes: tuple[Ring, ...], work: WorkBudget) -> _Cut:
    if exceeds_work_bound(outer, holes):
        _refuse(work.what)
    work.spend(_REGION_UNITS)
    for number, ring in enumerate((outer, *holes)):
        if not (ring_area(ring) > 0.0 if number == 0 else ring_area(ring) < 0.0):
            raise ValueError(_not_simple(number, len(ring)))  # the wrong way round, or no area
    vertices, triangles = _triangulate(outer, holes, work)
    doubled = [
        (vertices[b][0] - vertices[a][0]) * (vertices[c][1] - vertices[a][1])
        - (vertices[b][1] - vertices[a][1]) * (vertices[c][0] - vertices[a][0])
        for a, b, c in triangles
    ]
    expected = ring_area(outer) + sum(ring_area(hole) for hole in holes)
    slack = 1e-9 * max(1.0, abs(expected))
    if (doubled and min(doubled) < -slack) or abs(sum(doubled) / 2.0 - expected) > slack:
        raise ValueError(
            f"the cap of a footprint ring covers {sum(doubled) / 2.0!r} cm² "
            f"(smallest triangle {min(doubled, default=0.0) / 2.0!r}); its region is {expected!r} cm²"
        )
    return vertices, tuple(triangles)


def is_buildable_region(outer: Ring, holes: tuple[Ring, ...] = ()) -> bool:
    """THE predicate for "a builder can turn this region into a solid": true
    exactly when ``cut_region`` — the default builder's own triangulation — cuts
    it and proves the cut. The snapshot keeps only regions for which it holds.

    It implies what a builder of its own may rely on: the outer ring is a simple
    counter-clockwise polygon, the holes are simple, clockwise and inside it,
    and the triangulation exists. Remembered, false answers included.
    """
    return _examine(outer, holes).verdict == _BUILDABLE


def is_region_too_large(outer: Ring, holes: tuple[Ring, ...] = ()) -> bool:
    """True when ``cut_region`` refuses the region for its SIZE (the work bound)
    — as opposed to its shape. No other reading of the same outline will be
    smaller, so a caller that gets True stops there. Remembered with the verdict."""
    return _examine(outer, holes).verdict == _TOO_LARGE
