"""The builder seam: one record in, mesh parts out (Phase 17 L1.1, ADR-059).

A ``Builder`` is a PURE function of one ``Record``::

    Builder = Callable[[Record], tuple[MeshPart, ...]]

It returns meshes in the item-local frame (``mesh`` module) and may read ONLY
the record's geometry part — ``kind``, ``shape``, ``footprints``, ``holes``,
``path``, ``path_width_cm``, ``height_cm``, ``params``
(``record.GEOMETRY_FIELDS``). Not the transform (the engine poses the Model),
not the material (the sink tints), not ``item_id`` / ``name`` / ``parent_id``
(take the seed from ``params["seed"]``). That rule is what makes the three
signatures honest: the pipeline calls a builder only when ``geometry_sig``
changed, so anything else a builder read would go stale. ``verify_builder``
enforces it in tests.

``BuilderRegistry`` maps ``Record.kind`` to a builder; L1.6 (built world) and
L1.7 (plants) register theirs. Every other kind gets ``default_builder`` — the
honest v0: a prism of the footprint (outer rings minus their holes) up to the
resolved height, and nothing at all for an item the plan gives no height (the
ground bake, L1.5, paints flat surfaces).
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Final, TypeAlias

import numpy as np
from numpy.typing import NDArray

from .mesh import Mesh, MeshError, MeshPart
from .polygon import Region, ccw, cut_region, cw, is_flat_ring
from .record import PARAM_PAINT_ORIGIN, PATTERN_TILE_CM, Material, Record, Ring, Transform

Builder: TypeAlias = Callable[[Record], tuple[MeshPart, ...]]

#: Truth gate "built heights" (``ogp-lush-cinematic`` §1): the top of a
#: shadow-casting item is its resolved height to this fraction. Plants are held
#: to 0.03 — L1.7 passes it to ``verify_builder``.
BUILT_HEIGHT_TOLERANCE: Final = 0.01
# ``verify_builder``'s plan-view check bounds EXCESS only — geometry where the
# plan has none. It never asks a mesh to cover its footprint: a flower, a grass
# tuft, the posts and pickets of a fence fill a fraction of theirs and are right.
#: Its default reach: a top surface may lie this far outside the footprint
#: (eaves, a post wider than its fence line, a canopy a few percent over its
#: circle). Pass 0.0 for a builder that must stay inside, None to switch it off.
PLAN_MARGIN_CM: Final = 50.0
#: The share of the footprint's area that may lie beyond that reach.
PLAN_AREA_TOLERANCE: Final = 0.01
#: A hole of the footprint may be covered from above by at most this share:
#: eaves over a courtyard cover its rim, a builder that extruded the hole ring as
#: a solid covers all of it.
HOLE_COVER_LIMIT: Final = 0.5
#: … unless the hole is narrower than this: one into which no circle of this
#: diameter fits is not judged at all — the 2 cm sliver between two parallel runs
#: of a stroke is covered by any honest panel a little wider than the stroke.
#: A hole of this width and more is judged whole, rim included.
HOLE_MIN_WIDTH_CM: Final = 10.0


class BuilderContractError(Exception):
    """A builder broke the seam's contract (``verify_builder``)."""


def item_seed(item_id: str, salt: str = "") -> int:
    """Stable per-item seed, so no two plants are clones and none changes between
    runs. Ported from the spike (``meshes.item_seed``); feed it ``params["seed"]``."""
    digest = hashlib.md5(f"{item_id}:{salt}".encode(), usedforsecurity=False)
    return int(digest.hexdigest()[:12], 16)


def _walls(ring: Ring, height_cm: float, positions: list[float], normals: list[float],
           uvs: list[float]) -> None:
    """Two triangles per edge with the flat normal on the RIGHT of the direction
    of travel: outward for a counter-clockwise outer ring, into the hole - away
    from the solid - for a clockwise hole ring.

    Its UVs are written (the mesh contract) but never read: these are the TINTED
    sides of a raised surface - ``walls_mesh`` is the one caller - and a fill
    surface's picture lives on its cap (``cap_mesh``), with plan UVs. ``u`` counts
    the distance along the ring, ``v`` the height, both / ``PATTERN_TILE_CM``."""
    n = len(ring)
    travelled = ring[0][0] if n else 0.0
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        edge = math.hypot(x2 - x1, y2 - y1)
        if edge <= 1e-9:
            continue
        nx, ny = (y2 - y1) / edge, -(x2 - x1) / edge
        u1, u2 = travelled / PATTERN_TILE_CM, (travelled + edge) / PATTERN_TILE_CM
        v0, v1 = 0.0, height_cm / PATTERN_TILE_CM
        for px, py, pz, u, v in (
            (x1, y1, 0.0, u1, v0), (x2, y2, 0.0, u2, v0), (x2, y2, height_cm, u2, v1),
            (x1, y1, 0.0, u1, v0), (x2, y2, height_cm, u2, v1), (x1, y1, height_cm, u1, v1),
        ):
            positions.extend((px, py, pz))
            normals.extend((nx, ny, 0.0))
            uvs.extend((u, v))
        travelled += edge


#: A mesh is float32: a coordinate of size m is stored to about m · 2⁻²⁴, so the
#: doubled area of a triangle moves by up to ~2.4e-7 · m · (its two edges) on the
#: way into the mesh. A cap triangle smaller than this many times that product
#: is nothing at the engine's precision — it could come out wound downwards — and
#: is left out. At m = 300 cm and edges of 40 cm that is a doubled area of
#: 0.012 cm²: a sliver 0.0003 cm high.
_FLOAT32_SLIVER: Final = 5e-7


_FLOAT32_MAX: Final = float(np.finfo(np.float32).max)  # 3.4e38


def _as_ring(points: Sequence[Sequence[float]]) -> Ring:
    """Any sequence of ``(x, y)`` pairs as an immutable ring of plain floats — what
    the cached polygon functions need (a list of lists or numpy rows is not hashable).
    A coordinate that is not finite in float32 raises ``MeshError``: before any
    arithmetic on it, and so that no mesh is made of it."""
    ring = tuple((float(x), float(y)) for x, y in points)
    for x, y in ring:
        if not (-_FLOAT32_MAX <= x <= _FLOAT32_MAX and -_FLOAT32_MAX <= y <= _FLOAT32_MAX):
            raise MeshError(f"a footprint coordinate ({x!r}, {y!r}) is not finite in float32")
    return ring


def prism_mesh(
    footprints: Sequence[Ring], height_cm: float, holes: Sequence[Sequence[Ring]] = (),
    *, uv_origin: tuple[float, float] = (0.0, 0.0),
) -> Mesh:
    """Item-local prism(s) from z = 0 up to ``height_cm``: one solid per region.

    ``footprints`` are the outer rings; ``holes[i]`` (when given) the rings cut
    out of ``footprints[i]`` — pass ``record.footprints, height, record.holes``.
    Each region gets walls around its outer ring, walls around every hole facing
    into the hole, and a cap that covers the outer MINUS the holes. Neutral white
    vertex colours (a tinted part), flat normals, no bottom cap.

    ``uv_origin``: the item's ``params["paint_origin"]`` — its anchor in ITEM
    coordinates, which the record's footprint is centred on. The canvas paints the
    item at ``anchor + position`` and phases the fill from that scene point, so the
    CAP samples ``(x + ox) / PATTERN_TILE_CM`` (``cap_mesh``). The walls' own UVs
    are not the fill's: a raised surface's sides are tinted (``walls_mesh``). (0, 0)
    for a caller with no record.

    A hole-free ring of fewer than ``polygon.ARRAY_EAR_CLIP_FROM`` (256) vertices
    produces exactly the vertices of the Qt 3D view's ``extrude_footprint`` (same
    ear clipper, ``polygon.triangulate_polygon``), so the two views cannot
    disagree — less the cap triangles that are nothing at the mesh's float32
    precision (``_FLOAT32_SLIVER``); a larger ring gets the same cap cut into
    other triangles. A flat ring (fewer than three corners, or all
    of them on one line) and a height that is not positive — or is zero once
    it is float32 (1e-46 cm) — give no geometry. A ring that
    is not a simple polygon (a bow-tie) raises ``ValueError``: no cap of it would
    be the plan's shape, and an honest "no solid" beats a wrong one. So does any
    region ``polygon.cut_region`` cannot cut and prove — the same function
    ``polygon.is_buildable_region`` asks, so a region for which that predicate
    holds is always built.

    A ring is any sequence of ``(x, y)`` pairs — tuples, lists, numpy rows.

    A height or a coordinate that is not finite in the mesh's float32 raises
    ``MeshError`` before anything is computed from it: no such number is ever
    emitted. A record cannot hold one (``record.MAX_LENGTH_CM``); a hand-made
    call can.
    """
    if len(holes) and len(holes) != len(footprints):
        raise ValueError(f"{len(holes)} hole groups for {len(footprints)} footprint rings")
    if height_cm <= 0:
        return Mesh.empty()
    if not height_cm <= _FLOAT32_MAX:  # an infinity, a NaN, 1e300
        raise MeshError(f"a height of {height_cm!r} cm is not finite in float32")
    if float(np.float32(height_cm)) == 0.0:  # 1e-46, 1e-300: zero in the mesh — as good as none
        return Mesh.empty()
    # ONE implementation of each half: ``walls_mesh`` and ``cap_mesh`` are the raised
    # surface's two Models, and a solid is their union — the hole rules and the
    # float32 sliver rule cannot drift between the one-part and two-part routes.
    walls = walls_mesh(footprints, height_cm, holes)
    cap = cap_mesh(footprints, height_cm, holes, uv_origin=uv_origin)
    if not walls.vertex_count and not cap.vertex_count:
        return Mesh.empty()
    return Mesh.merge([mesh for mesh in (walls, cap) if mesh.vertex_count])


def _cap_into(
    vertices: Sequence[Sequence[float]], triangles: Sequence[Sequence[int]], height_cm: float,
    uv_origin: tuple[float, float],
    positions: list[float], normals: list[float], uvs: list[float],
) -> None:
    """Append one region's cap triangles (``cut_region``'s output) to the arrays.

    The one place the cap's float32 sliver rule lives: ``prism_mesh`` and
    ``cap_mesh`` (a raised surface's fill top) must not disagree about a cap.
    """
    for triangle in triangles:
        (ax, ay), (bx, by), (cx, cy) = (vertices[vertex] for vertex in triangle)
        reach = max(abs(ax), abs(ay), abs(bx), abs(by), abs(cx), abs(cy))
        edges = abs(bx - ax) + abs(by - ay) + abs(cx - ax) + abs(cy - ay)
        if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) <= _FLOAT32_SLIVER * reach * edges:
            continue  # nothing at float32 precision (see _FLOAT32_SLIVER)
        for x, y in ((ax, ay), (bx, by), (cx, cy)):
            positions.extend((x, y, height_cm))
            normals.extend((0.0, 0.0, 1.0))
            uvs.extend(((x + uv_origin[0]) / PATTERN_TILE_CM,
                        (y + uv_origin[1]) / PATTERN_TILE_CM))  # the canvas's phase


def _regions(
    footprints: Sequence[Ring], holes: Sequence[Sequence[Ring]],
) -> Iterator[tuple[Ring, tuple[Ring, ...], tuple[tuple[float, float], ...],
                    tuple[tuple[int, int, int], ...]]]:
    """Every buildable region of a record's ground: ``(outer, inner, vertices,
    triangles)``, rings wound, holes cut by ``cut_region`` - THE one place the
    outline rule is applied, shared by ``walls_mesh`` and ``cap_mesh`` (and so by
    ``prism_mesh``). A ring that is flat (fewer than three corners, or all on one
    line) covers no ground and is skipped; a ring that crosses itself raises
    ``ValueError`` (``cut_region``), so no half a solid is ever built."""
    for index, raw in enumerate(footprints):
        ring = _as_ring(raw)
        if is_flat_ring(ring):
            continue
        outer = ccw(ring)
        inner = tuple(cw(_as_ring(hole)) for hole in (holes[index] if len(holes) else ()))
        vertices, triangles = cut_region(outer, inner)  # raises: no wrong cap, ever
        yield outer, inner, vertices, triangles


def walls_mesh(
    footprints: Sequence[Ring], height_cm: float, holes: Sequence[Sequence[Ring]] = (),
) -> Mesh:
    """Only the SIDES of ``prism_mesh``: the outline's walls and every hole's.

    A raised flat surface (a lawn, a bed, a generic shape) shows its fill on the
    TOP and its tint on the sides — the canvas paints no texture down an item's
    edge, and one fill-textured prism smeared the picture there (#627's manual
    pass). Its UVs are written (the mesh contract, ``_walls``) but never sampled: the
    part is never a ``fill_texture`` part, so the sink binds no picture to it.
    """
    positions: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    for outer, inner, _vertices, _triangles in _regions(footprints, holes):
        _walls(outer, height_cm, positions, normals, uvs)
        for hole in inner:
            _walls(hole, height_cm, positions, normals, uvs)
    if not positions:
        return Mesh.empty()
    count = len(positions) // 3
    return Mesh.from_arrays(
        positions, normals, np.ones((count, 4), np.float32), uvs,
        np.arange(count, dtype=np.uint32),
    )


def cap_mesh(
    footprints: Sequence[Ring], height_cm: float, holes: Sequence[Sequence[Ring]] = (),
    *, uv_origin: tuple[float, float] = (0.0, 0.0),
) -> Mesh:
    """Only the TOP of ``prism_mesh``: every region's cap, holes cut out, with the
    item's fill UVs (``(position + paint_origin) / PATTERN_TILE_CM``)."""
    positions: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    for _outer, _inner, vertices, triangles in _regions(footprints, holes):
        _cap_into(vertices, triangles, height_cm, uv_origin, positions, normals, uvs)
    if not positions:
        return Mesh.empty()
    count = len(positions) // 3
    return Mesh.from_arrays(
        positions, normals, np.ones((count, 4), np.float32), uvs,
        np.arange(count, dtype=np.uint32),
    )


def uv_origin_of(record: Record) -> tuple[float, float]:
    """The item's fill-texture anchor in its own coordinates — ``(0, 0)`` when the
    record carries none (a hand-made record, a kind never painted on the ground).

    ``params["paint_origin"]`` is written by the snapshot for every item the ground
    bake paints: it is the record's anchor (a rectangle's centre, a circle's centre)
    in item coordinates. The record's footprint is CENTRED on it, so the canvas's
    item coordinate is ``position + paint_origin`` — the phase a fill texture needs.
    """
    origin = record.params.get(PARAM_PAINT_ORIGIN)
    if isinstance(origin, tuple) and len(origin) == 2:
        first, second = origin
        if isinstance(first, float) and isinstance(second, float):
            return (first, second)
    return (0.0, 0.0)


def raised_surface(
    record: Record, height_cm: float, *, name: str = "platform", casts_shadow: bool = True,
) -> tuple[MeshPart, ...]:
    """A raised FLAT surface: tinted walls and a fill-textured cap.

    The canvas paints a flat item's fill on its TOP and strokes its outline; it
    has no textured edge. One fill-textured prism wrapped the picture down the
    walls (a lawn's grass smeared the full height of the side, a bed's soil ran
    down its frame — #627's manual pass), so the walls carry the item's tint and
    only the cap shows the fill. Both parts come from one region list, so the
    sides and the top cannot disagree about a hole or a ring.

    ``()`` for a record without ground; a ring that is not a simple polygon
    raises ``ValueError`` (``SceneSync`` then shows the item without a solid).
    """
    walls = walls_mesh(record.footprints, height_cm, record.holes)
    cap = cap_mesh(record.footprints, height_cm, record.holes, uv_origin=uv_origin_of(record))
    parts: list[MeshPart] = []
    if walls.vertex_count:
        parts.append(MeshPart(walls, "vc", casts_shadow=casts_shadow, tinted=True,
                              name=f"{name}_sides"))
    if cap.vertex_count:
        parts.append(MeshPart(cap, "vc", casts_shadow=casts_shadow, fill_texture=True,
                              name=name))
    return tuple(parts)


def default_builder(record: Record) -> tuple[MeshPart, ...]:
    """The honest v0 for a kind without a builder of its own.

    With a height: a prism of the local footprint, holes cut out, whose top is
    exactly ``height_cm`` — its SIDES tinted and its CAP showing the item's own
    FILL (``fill_texture``: the fill pattern textured by the fill colour, or that
    colour alone for SOLID), so a lawn, path, generic shape or bed the user gave
    a height keeps the look it had while the ground bake painted it (#628
    follow-up) without smearing that picture down its edges (#627's manual pass).
    Without a height: no parts — the item casts no shadow in 2D and has no solid
    in 3D. Raises ``ValueError`` for a ring that is not a simple polygon
    (``prism_mesh``); ``SceneSync`` then shows the item without a solid and
    reports it.
    """
    if record.height_cm is None:
        return ()
    return raised_surface(record, record.height_cm, name="prism")


class BuilderRegistry:
    """``Record.kind`` → builder, with a default for every other kind.

    An instance, not a module global: the wiring (L1.3) creates one and hands it
    to each builder package's ``register(registry)`` — no import-order surprises.
    A ``SceneSync`` notices a builder registered or replaced after it has built:
    its next ``apply`` rebuilds the items that builder now owns.

    The contract ``SceneSync`` relies on: ``builder_for(kind)`` returns the SAME
    object for the same kind until a ``register`` changes it (items are matched to
    the builder that built them by identity), and every change bumps ``version``.
    A subclass that hands out a fresh callable per call, or swaps builders behind
    ``register``'s back, breaks the first half or the second: ``SceneSync`` looks
    for items to rebuild only when ``version`` moved, so the first costs nothing
    worse than one full rebuild at the next registration, and the second goes
    unnoticed until then.
    """

    def __init__(self, default: Builder = default_builder) -> None:
        self._default = default
        self._builders: dict[str, Builder] = {}
        self._version = 0

    @property
    def version(self) -> int:
        """How many registrations this registry has seen — it moves whenever the
        answer of ``builder_for`` may have changed."""
        return self._version

    def register(self, kind: str, builder: Builder, *, replace: bool = False) -> None:
        """Use ``builder`` for records of ``kind`` (an ObjectType name).

        Registering a kind twice is an error — two packages claiming one kind is
        a bug, not a preference — unless ``replace=True`` says it is meant.
        """
        if kind in self._builders and not replace:
            raise ValueError(f"a builder for kind {kind!r} is already registered")
        self._builders[kind] = builder
        self._version += 1

    def register_many(self, kinds: Iterable[str], builder: Builder, *,
                      replace: bool = False) -> None:
        for kind in kinds:
            self.register(kind, builder, replace=replace)

    def builder_for(self, kind: str) -> Builder:
        """The builder of ``kind`` — the same object on every call until a
        ``register`` changes it (class docstring)."""
        return self._builders.get(kind, self._default)

    def kinds(self) -> frozenset[str]:
        """The kinds with a builder of their own."""
        return frozenset(self._builders)

    def build(self, record: Record) -> tuple[MeshPart, ...]:
        """Run the builder of ``record.kind``. Exceptions propagate — ``SceneSync``
        is where a failing builder is contained."""
        return self.builder_for(record.kind)(record)


def checked_parts(parts: object) -> tuple[MeshPart, ...]:
    """``parts`` if it is a tuple of ``MeshPart``, else ``BuilderContractError``."""
    if not isinstance(parts, tuple) or not all(isinstance(p, MeshPart) for p in parts):
        raise BuilderContractError(
            f"a builder returns a tuple of MeshPart, got {type(parts).__name__}: {parts!r:.80}"
        )
    return parts


def _top_cm(parts: Sequence[MeshPart]) -> float | None:
    """The solid's top — relief (``ground_detail``: a raised lawn's blades, up to
    9.4 cm above the requested height) is not it: every registered kind's solid
    measures exactly its height (swept over 44 kinds and h = 1..200 cm)."""
    tops = [float(p.mesh.positions[:, 2].max()) for p in parts
            if p.mesh.vertex_count and not p.ground_detail]
    return max(tops) if tops else None


# ── the plan-view check ───────────────────────────────────────────────────────

Triangles2D: TypeAlias = tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]


def _top_triangles(parts: Sequence[MeshPart]) -> tuple[Triangles2D, NDArray[np.float64]]:
    """The plan view of every upward-facing triangle: its corners (t, 2) each, and
    its plan area. A triangle faces up when it is wound counter-clockwise seen
    from above."""
    corners: list[list[NDArray[np.float64]]] = [[], [], []]
    areas: list[NDArray[np.float64]] = []
    for part in parts:
        mesh = part.mesh
        if not len(mesh.indices):
            continue
        p = mesh.positions.astype(np.float64)
        a, b, c = (p[mesh.indices[:, k]][:, :2] for k in range(3))
        twice = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
        up = twice > 1e-9
        for store, corner in zip(corners, (a, b, c), strict=True):
            store.append(corner[up])
        areas.append(twice[up] / 2.0)
    if not areas:
        empty = np.zeros((0, 2))
        return (empty, empty, empty), np.zeros(0)
    return ((np.concatenate(corners[0]), np.concatenate(corners[1]), np.concatenate(corners[2])),
            np.concatenate(areas))


def _inside(points: NDArray[np.float64], ring: Ring) -> NDArray[np.bool_]:
    """Even-odd point-in-ring for many points at once."""
    x, y = points[:, 0], points[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    xj, yj = ring[-1]
    for xi, yi in ring:
        if yi != yj:
            crosses = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
            inside ^= crosses
        xj, yj = xi, yi
    return inside


def _distance_to_rings(points: NDArray[np.float64], rings: Iterable[Ring]) -> NDArray[np.float64]:
    """Distance from each point to the nearest edge of any ring."""
    best = np.full(len(points), np.inf)
    for ring in rings:
        ax, ay = ring[-1]
        for bx, by in ring:
            dx, dy = bx - ax, by - ay
            length2 = dx * dx + dy * dy
            if length2 > 0.0:
                t = np.clip(((points[:, 0] - ax) * dx + (points[:, 1] - ay) * dy) / length2, 0.0, 1.0)
                best = np.minimum(best, np.hypot(points[:, 0] - (ax + t * dx),
                                                 points[:, 1] - (ay + t * dy)))
            ax, ay = bx, by
    return best


def _hole_cover(triangles: Triangles2D, hole: Ring, regions: Sequence[Region] = ()) -> float:
    """The share of a hole that upward-facing triangles cover, from a 24 x 24
    lattice of points INSIDE the hole — so a slab of two huge triangles over a
    small hole is seen as surely as a cap of many small ones. A hole narrower
    than ``HOLE_MIN_WIDTH_CM`` — no lattice point lies half that far from its
    edge — reads 0.0: a sliver is not judged.

    Only the OPEN part of the hole is judged: a point that one of ``regions``
    covers is ground the plan builds on — an island standing in the hole is a
    region of its own, and the solid on it is not "building over the hole"."""
    xs = [x for x, _y in hole]
    ys = [y for _x, y in hole]
    steps = (np.arange(24) + 0.5) / 24.0
    gx, gy = np.meshgrid(min(xs) + steps * (max(xs) - min(xs)), min(ys) + steps * (max(ys) - min(ys)))
    lattice = np.column_stack([gx.ravel(), gy.ravel()])
    lattice = lattice[_inside(lattice, hole)]
    if len(lattice) and 2.0 * float(_distance_to_rings(lattice, (hole,)).max()) < HOLE_MIN_WIDTH_CM:
        return 0.0
    for outer, inner in regions:  # leave out what an island covers
        if not len(lattice):
            break
        on_it = _inside(lattice, outer)
        for other in inner:
            on_it &= ~_inside(lattice, other)
        lattice = lattice[~on_it]
    a, b, c = triangles
    if not len(lattice) or not len(a):
        return 0.0
    near = ((np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0]) >= min(xs))
            & (np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0]) <= max(xs))
            & (np.maximum(np.maximum(a[:, 1], b[:, 1]), c[:, 1]) >= min(ys))
            & (np.minimum(np.minimum(a[:, 1], b[:, 1]), c[:, 1]) <= max(ys)))
    a, b, c = a[near], b[near], c[near]
    covered = np.zeros(len(lattice), dtype=bool)
    px, py = lattice[:, 0][:, None], lattice[:, 1][:, None]
    for start in range(0, len(a), 2048):  # points x triangles, a slab of triangles at a time
        ta, tb, tc = (corner[start:start + 2048] for corner in (a, b, c))
        d1 = (tb[:, 0] - ta[:, 0]) * (py - ta[:, 1]) - (tb[:, 1] - ta[:, 1]) * (px - ta[:, 0])
        d2 = (tc[:, 0] - tb[:, 0]) * (py - tb[:, 1]) - (tc[:, 1] - tb[:, 1]) * (px - tb[:, 0])
        d3 = (ta[:, 0] - tc[:, 0]) * (py - tc[:, 1]) - (ta[:, 1] - tc[:, 1]) * (px - tc[:, 0])
        covered |= ((d1 >= 0) & (d2 >= 0) & (d3 >= 0)).any(axis=1)
    return float(covered.mean())


def plan_overreach(
    parts: Sequence[MeshPart], regions: Sequence[Region], margin_cm: float
) -> tuple[float, float]:
    """How far a solid's top strays from its footprint, seen from above.

    Returns ``(beyond_cm2, hole_cover)``:

    - ``beyond_cm2`` — upward-facing area lying more than ``margin_cm`` outside
      the footprint (outer rings minus holes). Estimated at four points per
      triangle (its centroid and the points halfway to each corner), overlapping
      layers counted each time: a net for gross errors, not a rasteriser.
    - ``hole_cover`` — the largest share, 0 … 1, of any hole that
      upward-facing triangles cover, measured on a lattice of points inside the
      hole (0.0 without holes; a hole narrower than ``HOLE_MIN_WIDTH_CM`` is
      not judged and counts as 0.0). Regions can NEST — an island inside a
      hole is a region of its own — and what an island covers is not counted
      as the hole.
    """
    triangles, areas = _top_triangles(parts)
    a, b, c = triangles
    if not len(areas) or not regions:
        return 0.0, 0.0
    hole_cover = max(
        (_hole_cover(triangles, hole, regions) for _outer, holes in regions for hole in holes),
        default=0.0,
    )
    centre = (a + b + c) / 3.0
    points = np.concatenate([centre, (centre + a) / 2.0, (centre + b) / 2.0, (centre + c) / 2.0])
    weights = np.tile(areas / 4.0, 4)
    covered = np.zeros(len(points), dtype=bool)
    for outer, holes in regions:
        in_hole = np.zeros(len(points), dtype=bool)
        for hole in holes:
            in_hole |= _inside(points, hole)
        covered |= _inside(points, outer) & ~in_hole
    outside = ~covered
    if not outside.any():
        return 0.0, hole_cover
    rings = [ring for outer, holes in regions for ring in (outer, *holes)]
    far = _distance_to_rings(points[outside], rings) > margin_cm
    return float(weights[outside][far].sum()), hole_cover


def verify_builder(
    builder: Builder,
    record: Record,
    *,
    height_tolerance: float = BUILT_HEIGHT_TOLERANCE,
    height_tolerance_cm: float | None = None,
    plan_margin_cm: float | None = PLAN_MARGIN_CM,
    hole_cover_limit: float | None = HOLE_COVER_LIMIT,
) -> tuple[MeshPart, ...]:
    """Run ``builder`` on ``record`` and assert the seam's contract; return the parts.

    The test instrument for every builder (use it over each kind the builder
    handles and over the bench plans' records). Raises ``BuilderContractError``
    when the builder

    - does not return a tuple of ``MeshPart``;
    - is not deterministic (two calls differ);
    - reads the transform, the material or an unsigned field (``item_id``,
      ``name``, ``parent_id``): its output changed when only that changed;
    - emits a mesh ``MeshPart.validate`` rejects;
    - builds a shadow-casting item whose top is not its resolved height: within
      ``height_tolerance`` (a fraction of the height; truth gate "built
      heights"), or — when ``height_tolerance_cm`` is given — within that many
      centimetres instead (issue #385's L1.6 gate is ±0.5 cm absolute);
    - builds where the plan has NOTHING, seen from above — two upper bounds on
      excess, each with its own keyword:

      * ``plan_margin_cm`` (default ``PLAN_MARGIN_CM``): at most
        ``PLAN_AREA_TOLERANCE`` of the footprint's area (and at least 1 cm²)
        may be upward-facing surface lying further than this outside the
        footprint (the outer rings minus their holes). ``0.0`` holds a builder
        to its footprint, a larger value allows wider eaves, ``None`` switches
        this bound off.
      * ``hole_cover_limit`` (default ``HOLE_COVER_LIMIT``): at most this share
        of any HOLE of the footprint may be covered from above (a closed fence
        extruded with its inside filled covers all of it). ``None`` switches
        this bound off. A hole narrower than ``HOLE_MIN_WIDTH_CM`` (10 cm:
        no circle of that diameter fits into it) is not judged at all; every
        other hole is judged whole.

      Neither bound asks for coverage: a mesh that fills a fraction of its
      footprint — a flower, a tuft, pickets inside a fence's stroke — passes.
    """
    parts = checked_parts(builder(record))
    if checked_parts(builder(record)) != parts:
        raise BuilderContractError("the builder is not deterministic: two calls on one record differ")
    variants: dict[str, Record] = {
        "transform": dataclasses.replace(record, transform=Transform(
            record.transform.east_cm + 137.25, record.transform.north_cm - 42.5,
            (record.transform.rotation_deg + 33.0) % 360.0, record.transform.base_cm + 7.0)),
        "material": dataclasses.replace(record, material=Material(
            record.material.key + "*", fill_rgba=(1, 2, 3, 255), stroke_rgba=(4, 5, 6, 255),
            pattern="VERIFY")),
        "item_id": dataclasses.replace(record, item_id=record.item_id + "-verify-builder"),
        "name": dataclasses.replace(record, name=record.name + " (verify builder)"),
        "parent_id": dataclasses.replace(
            record, parent_id=(record.parent_id or "") + "verify-builder-parent"),
    }
    for field, variant in variants.items():
        if checked_parts(builder(variant)) != parts:
            raise BuilderContractError(
                f"the builder's output depends on the record's {field}; a builder may read only "
                "the geometry part (kind, shape, footprints, holes, path, path_width_cm, "
                "height_cm, params)"
            )
    for index, part in enumerate(parts):
        try:
            part.validate()
        except MeshError as error:
            raise BuilderContractError(f"part {index} ({part.name or part.material_kind}): {error}") from error
    top = _top_cm(parts)
    if record.height_cm is not None and top is None and parts:
        raise BuilderContractError(
            "every part is ground_detail: relief is not a solid, and a record with a height "
            "needs one whose top is that height - the gate cannot be opted out of with a flag "
            "on the data it measures"
        )
    if record.height_cm is not None and top is not None:
        if height_tolerance_cm is not None:
            allowed, rule = height_tolerance_cm, f"±{height_tolerance_cm:g} cm"
        else:
            allowed, rule = height_tolerance * record.height_cm, f"{height_tolerance:.0%}"
        if abs(top - record.height_cm) > allowed + 1e-4:
            raise BuilderContractError(
                f"the mesh top is {top:g} cm but the plan's resolved height is "
                f"{record.height_cm:g} cm (tolerance {rule}): truth before beauty"
            )
    if (plan_margin_cm is not None or hole_cover_limit is not None) and parts and record.footprints:
        beyond, hole_cover = plan_overreach(parts, record.regions, plan_margin_cm or 0.0)
        plan_area = record.plan_area_cm2
        if hole_cover_limit is not None and hole_cover > hole_cover_limit:
            raise BuilderContractError(
                f"the solid covers {hole_cover:.0%} of a hole of the footprint: holes are not "
                "built over (iterate record.regions, or pass record.holes to prism_mesh)"
            )
        if plan_margin_cm is not None and beyond > max(PLAN_AREA_TOLERANCE * plan_area, 1.0):
            raise BuilderContractError(
                f"{beyond:,.0f} cm² of top surface lie more than {plan_margin_cm:g} cm outside a "
                f"footprint of {plan_area:,.0f} cm²: the solid stands where the plan has nothing"
            )
    return parts
