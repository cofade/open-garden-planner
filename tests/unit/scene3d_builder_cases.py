"""Records for the built-world builder tests (Phase 17 L1.6) — Qt-free, hand-made.

``CASES`` is the matrix gate G1 runs over: every registered kind, in several
sizes, with its local geometry turned by four angles (a builder never sees the
item's rotation — that is the transform's — but its sweeps, mitres and roof
planes must not care which way the local geometry happens to point), a closed
and a nearly closed polyline for every polyline style, and each of them with and
without a height.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import numpy as np

from open_garden_planner.core.scene3d import (
    Material,
    Mesh,
    MeshPart,
    Params,
    Record,
    Transform,
    ccw,
    group_rings,
)
from open_garden_planner.core.shadow_geometry import circle_footprint, polyline_footprint

Point = tuple[float, float]
ANGLES = (0.0, 17.0, 90.0, 213.5)


def turned(points: Sequence[Point], degrees: float) -> tuple[Point, ...]:
    """Plan points turned counter-clockwise about the origin."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return tuple((round(x * c - y * s, 7) + 0.0, round(x * s + y * c, 7) + 0.0) for x, y in points)


def rectangle(width: float, depth: float) -> tuple[Point, ...]:
    w, d = width / 2.0, depth / 2.0
    return ((-w, -d), (w, -d), (w, d), (-w, d))


L_SHAPE: tuple[Point, ...] = ((-450.0, -300.0), (450.0, -300.0), (450.0, 100.0), (0.0, 100.0),
                              (0.0, 300.0), (-450.0, 300.0))
#: The ridge ``core.roof_ridge`` gives that L: the long axis of its bounding box
#: through the box's centre, from wall to wall.
L_RIDGE: tuple[Point, Point] = ((-450.0, 0.0), (450.0, 0.0))
#: A U with its courtyard to the north; its ridge crosses the courtyard.
U_SHAPE: tuple[Point, ...] = ((-450.0, -300.0), (450.0, -300.0), (450.0, 300.0), (250.0, 300.0),
                              (250.0, -100.0), (-250.0, -100.0), (-250.0, 300.0), (-450.0, 300.0))
U_RIDGE: tuple[Point, Point] = ((-450.0, 0.0), (450.0, 0.0))
TRAPEZOID: tuple[Point, ...] = ((-400.0, -200.0), (400.0, -200.0), (250.0, 200.0), (-250.0, 200.0))
#: Acute corners (review round 1, P2-10): an isosceles triangle with a 30° apex (its
#: two base corners are 75°), and a right triangle with a 20° corner. A mitre at 30° is
#: 3.9 offsets long, at 20° it is 5.8 — both are bevelled.
ACUTE_TRIANGLE: tuple[Point, ...] = ((-200.0, -250.0), (200.0, -250.0), (0.0, 496.41))
#: ``core.roof_ridge`` for it: the long axis of its bounding box, wall to wall — it ends
#: IN the 30° apex.
ACUTE_RIDGE: tuple[Point, Point] = ((0.0, -250.0), (0.0, 496.41))
SLIVER_TRIANGLE: tuple[Point, ...] = ((-400.0, -100.0), (400.0, -100.0), (-400.0, 191.18))
SLIVER_RIDGE: tuple[Point, Point] = ((-400.0, 45.59), (0.0, 45.59))


def polygon_record(kind: str, ring: Sequence[Point], height: float | None, *,
                   shape: str = "polygon", params: dict | None = None,
                   item_id: str = "item-1") -> Record:
    """A polygon record as the snapshot makes it: ONE outer ring, counter-clockwise
    whichever way the polygon was drawn."""
    return Record(item_id, kind, shape, (ccw(tuple(ring)),), Transform(),
                  Material(kind, (200, 180, 140, 255)),
                  height_cm=height, params=Params({"seed": item_id, **(params or {})}))


def circle_record(kind: str, radius: float, height: float | None, *, params: dict | None = None,
                  item_id: str = "item-1") -> Record:
    ring = tuple((round(x, 7) + 0.0, round(y, 7) + 0.0) for x, y in circle_footprint(0.0, 0.0, radius))
    return Record(item_id, kind, "circle", (ring,), Transform(), Material(kind, (170, 110, 70, 255)),
                  height_cm=height,
                  params=Params({"seed": item_id, "radius_cm": radius, **(params or {})}))


def line_record(kind: str, path: Sequence[Point], height: float | None, *, width: float = 3.0,
                style: str | None = None, item_id: str = "item-1") -> Record:
    """A polyline record as the snapshot makes it (``snapshot._polyline_regions``): the
    centre line in ``path``, and its stroke sorted into OUTER rings (``footprints``) and
    the holes cut out of them (``holes``) — a closed line is one outer ring and one
    hole, the garden it encloses. A builder builds from ``path``; nothing may be built
    over the hole (``verify_builder`` checks it)."""
    line = tuple(path)
    regions = group_rings([tuple(ring) for ring in polyline_footprint(list(line), width)])
    holes = tuple(region_holes for _outer, region_holes in regions)
    params: dict = {"seed": item_id}
    if style is not None:
        params["path_style"] = style
    return Record(item_id, kind, "polyline", tuple(outer for outer, _holes in regions), Transform(),
                  Material(kind, None, (139, 69, 19, 255)), height_cm=height, path=line,
                  path_width_cm=width, params=Params(params),
                  holes=holes if any(holes) else ())


BENT_PATH: tuple[Point, ...] = ((-600.0, -200.0), (200.0, -200.0), (200.0, 300.0), (-100.0, 450.0))
STRAIGHT_PATH: tuple[Point, ...] = ((-250.0, 0.0), (250.0, 0.0))
LOOP: tuple[Point, ...] = ((-400.0, -300.0), (400.0, -300.0), (400.0, 300.0), (-400.0, 300.0))
CLOSED_PATH: tuple[Point, ...] = (*LOOP, LOOP[0])               # first point repeated: a loop
NEARLY_CLOSED_PATH: tuple[Point, ...] = (*LOOP, (-400.0, -295.0))  # a 5 cm gap
LONG_PATH: tuple[Point, ...] = ((-2500.0, 0.0), (2500.0, 0.0))  # 50 m of fence
#: A line that doubles back on itself: a turn of 174°. And a zigzag with a turn of 150°
#: followed by one of 135°.
HAIRPIN_PATH: tuple[Point, ...] = ((-300.0, 0.0), (300.0, 0.0), (-300.0, 60.0))
ZIGZAG_PATH: tuple[Point, ...] = ((-300.0, 0.0), (0.0, 0.0), (-259.81, 150.0), (40.19, 150.0),
                                  (-171.94, 362.13))
#: A closed loop with a 30° corner: the acute triangle's outline.
ACUTE_LOOP_PATH: tuple[Point, ...] = (*ACUTE_TRIANGLE, ACUTE_TRIANGLE[0])


def zigzag_path(leg_cm: float, turn_deg: float, legs: int = 4) -> tuple[Point, ...]:
    """A zigzag of equal legs turning left and right by ``turn_deg`` in turn, from the
    origin, on the snapshot's grid of thousandths."""
    points: list[Point] = [(0.0, 0.0)]
    heading, sign = 0.0, 1.0
    for _ in range(legs):
        points.append((round(points[-1][0] + leg_cm * math.cos(heading), 3),
                       round(points[-1][1] + leg_cm * math.sin(heading), 3)))
        heading += sign * math.radians(turn_deg)
        sign = -sign
    return tuple(points)


def square_loop(side_cm: float) -> tuple[Point, ...]:
    """A closed square loop about the origin (the first point repeated)."""
    half = side_cm / 2.0
    return ((-half, -half), (half, -half), (half, half), (-half, half), (-half, -half))
PATHS = {"straight": STRAIGHT_PATH, "bent": BENT_PATH, "closed": CLOSED_PATH,
         "nearly_closed": NEARLY_CLOSED_PATH, "hairpin": HAIRPIN_PATH, "zigzag": ZIGZAG_PATH,
         "acute_loop": ACUTE_LOOP_PATH}
#: None: no style (the plain line). The five fence styles. A PATH style on a fence and a
#: name no builder knows: both are built as the plain panel.
LINE_STYLES = (None, "WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK", "HEDGE_FENCE", "STONE_WALL",
               "GRAVEL_PATH", "BAMBOO_FENCE")


@dataclass(frozen=True)
class Case:
    """One record of the matrix; ``with_height`` is what the plan resolves for it."""

    name: str
    record: Record

    def __str__(self) -> str:
        return self.name


def _with_and_without(name: str, make, heights: Sequence[float]) -> Iterator[Case]:
    for height in (*heights, None):
        label = "no-height" if height is None else f"h{height:g}"
        yield Case(f"{name}/{label}", make(height))


def _cases() -> Iterator[Case]:
    # ── buildings ────────────────────────────────────────────────────────────
    for angle in ANGLES:
        house = turned(rectangle(900.0, 540.0), angle)
        ridge = turned(((-450.0, 0.0), (450.0, 0.0)), angle)
        yield from _with_and_without(
            f"HOUSE/rect@{angle:g}",
            lambda h, ring=house, r=ridge: polygon_record("HOUSE", ring, h, params={"ridge": r}),
            (450.0, 687.3))
        ell = turned(L_SHAPE, angle)
        ell_ridge = turned(L_RIDGE, angle)
        yield Case(f"HOUSE/L@{angle:g}/h450",
                   polygon_record("HOUSE", ell, 450.0, params={"ridge": ell_ridge}))
        shed = turned(rectangle(400.0, 300.0), angle)
        yield from _with_and_without(
            f"GARAGE_SHED/rect@{angle:g}", lambda h, ring=shed: polygon_record("GARAGE_SHED", ring, h),
            (250.0,))
    yield Case("HOUSE/U/h450", polygon_record("HOUSE", U_SHAPE, 450.0, params={"ridge": U_RIDGE}))
    yield Case("HOUSE/trapezoid/h450", polygon_record(
        "HOUSE", TRAPEZOID, 450.0, params={"ridge": ((-325.0, 0.0), (325.0, 0.0))}))
    yield Case("HOUSE/off-centre-ridge/h450", polygon_record(
        "HOUSE", rectangle(900.0, 540.0), 450.0, params={"ridge": ((-450.0, 120.0), (450.0, 120.0))}))
    yield Case("HOUSE/dragged-ridge/h450", polygon_record(
        "HOUSE", rectangle(900.0, 540.0), 450.0, params={"ridge": ((-450.0, -100.0), (450.0, 150.0))}))
    yield Case("HOUSE/low/h60", polygon_record(
        "HOUSE", rectangle(300.0, 200.0), 60.0, params={"ridge": ((-150.0, 0.0), (150.0, 0.0))}))
    yield from _with_and_without(  # no ridge: the plain block
        "HOUSE/no-ridge", lambda h: polygon_record("HOUSE", rectangle(900.0, 540.0), h,
                                                   shape="rectangle"), (450.0,))
    yield Case("HOUSE/degenerate-ridge/h450", polygon_record(
        "HOUSE", rectangle(900.0, 540.0), 450.0, params={"ridge": ((10.0, 0.0), (10.0, 0.0))}))
    yield from _with_and_without(
        "TOOL_SHED/deep", lambda h: polygon_record("TOOL_SHED", rectangle(150.0, 200.0), h,
                                                   shape="rectangle"), (250.0, 199.0))
    yield Case("GARAGE_SHED/L/h250", polygon_record("GARAGE_SHED", L_SHAPE, 250.0))
    for angle in ANGLES:  # acute corners: the eaves are bevelled, not spiked
        yield Case(f"HOUSE/acute-triangle@{angle:g}/h450", polygon_record(
            "HOUSE", turned(ACUTE_TRIANGLE, angle), 450.0, params={"ridge": turned(ACUTE_RIDGE, angle)}))
    yield Case("HOUSE/sliver-triangle/h450", polygon_record(
        "HOUSE", SLIVER_TRIANGLE, 450.0, params={"ridge": SLIVER_RIDGE}))
    yield Case("GARAGE_SHED/acute-triangle/h250", polygon_record("GARAGE_SHED", ACUTE_TRIANGLE, 250.0))
    yield Case("TOOL_SHED/sliver-triangle/h250", polygon_record("TOOL_SHED", SLIVER_TRIANGLE, 250.0))

    # ── fences and walls: every style x every path x heights ─────────────────
    for kind, heights in (("FENCE", (120.0, 37.5)), ("WALL", (200.0, 61.25))):
        for style in LINE_STYLES:
            for path_name, path in PATHS.items():
                width = {"HEDGE_FENCE": 8.0, "STONE_WALL": 5.0, "WALL": 4.0}.get(
                    style or kind, 3.0)
                yield from _with_and_without(
                    f"{kind}/{style or 'plain'}/{path_name}",
                    lambda h, k=kind, p=path, s=style, w=width: line_record(k, p, h, width=w, style=s),
                    heights)
    for angle in ANGLES[1:]:
        for style in ("WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK", "HEDGE_FENCE", "STONE_WALL"):
            yield Case(f"FENCE/{style}/bent@{angle:g}/h120",
                       line_record("FENCE", turned(BENT_PATH, angle), 120.0, style=style))
    for style in ("WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK", "STONE_WALL"):
        yield Case(f"FENCE/{style}/50m/h120", line_record("FENCE", LONG_PATH, 120.0, style=style))
    yield Case("FENCE/wide-stroke/h120", line_record("FENCE", BENT_PATH, 120.0, width=20.0))
    yield Case("WALL/wide-stroke/h200", line_record("WALL", BENT_PATH, 200.0, width=45.0))

    # ── beds and containers ──────────────────────────────────────────────────
    for angle in ANGLES:
        bed = turned(rectangle(300.0, 120.0), angle)
        yield from _with_and_without(
            f"RAISED_BED/300x120@{angle:g}",
            lambda h, ring=bed: polygon_record("RAISED_BED", ring, h, shape="rectangle"), (40.0, 90.0))
    yield Case("RAISED_BED/tiny/h40", polygon_record("RAISED_BED", rectangle(12.0, 8.0), 40.0))
    yield Case("RAISED_BED/rim-only/h1.5", polygon_record("RAISED_BED", rectangle(300.0, 120.0), 1.5))
    for material in ("terracotta", "plastic", "wood", "metal"):
        yield from _with_and_without(
            f"CONTAINER/{material}",
            lambda h, m=material: polygon_record("CONTAINER", rectangle(80.0, 40.0), h,
                                                 shape="rectangle",
                                                 params={"container_material": m}), (30.0, 55.5))
        yield from _with_and_without(
            f"CONTAINER_ROUND/{material}",
            lambda h, m=material: circle_record("CONTAINER_ROUND", 25.0, h,
                                                params={"container_material": m}), (30.0, 47.25))
    yield Case("CONTAINER_ROUND/large/h60", circle_record(
        "CONTAINER_ROUND", 90.0, 60.0, params={"container_material": "terracotta"}))
    yield Case("CONTAINER_ROUND/not-a-circle/h30", polygon_record(
        "CONTAINER_ROUND", rectangle(60.0, 60.0), 30.0, params={"container_material": "plastic"}))
    yield from _with_and_without(
        "WALL_PLANTER", lambda h: polygon_record("WALL_PLANTER", turned(rectangle(120.0, 25.0), 17.0), h,
                                                 shape="rectangle",
                                                 params={"container_material": "wood"}), (30.0,))
    yield Case("RAISED_BED/acute-triangle/h40", polygon_record("RAISED_BED", ACUTE_TRIANGLE, 40.0))
    yield Case("CONTAINER/sliver-triangle/h30", polygon_record(
        "CONTAINER", SLIVER_TRIANGLE, 30.0, params={"container_material": "wood"}))
    yield Case("CONTAINER/unknown-material/h30", polygon_record(
        "CONTAINER", rectangle(80.0, 40.0), 30.0, shape="rectangle",
        params={"container_material": "bamboo"}))
    yield Case("GARDEN_BED/raised-polygon/h25", polygon_record("GARDEN_BED", TRAPEZOID, 25.0))
    yield Case("GARDEN_BED/raised-circle/h25", circle_record("GARDEN_BED", 120.0, 25.0))
    yield Case("GARDEN_BED/in-ground/no-height", polygon_record("GARDEN_BED", TRAPEZOID, None))

    # ── hedges ───────────────────────────────────────────────────────────────
    for angle in ANGLES:
        yield from _with_and_without(
            f"HEDGE_SECTION/200x50@{angle:g}",
            lambda h, a=angle: polygon_record("HEDGE_SECTION", turned(rectangle(200.0, 50.0), a), h,
                                              shape="rectangle"), (150.0, 83.5))
    yield from _with_and_without(
        "HEDGE_POLYGON/L", lambda h: polygon_record("HEDGE_POLYGON", L_SHAPE, h), (150.0,))
    yield Case("HEDGE_POLYGON/low/h18", polygon_record("HEDGE_POLYGON", rectangle(400.0, 60.0), 18.0))
    yield Case("HEDGE_SECTION/sliver/h150", polygon_record("HEDGE_SECTION", rectangle(100.0, 10.0), 150.0))
    yield Case("HEDGE_POLYGON/acute-triangle/h150", polygon_record("HEDGE_POLYGON", ACUTE_TRIANGLE, 150.0))
    yield Case("HEDGE_POLYGON/sliver-triangle/h150", polygon_record("HEDGE_POLYGON", SLIVER_TRIANGLE, 150.0))


CASES: tuple[Case, ...] = tuple(_cases())


# ── measuring a built item ───────────────────────────────────────────────────


def positions(parts: Sequence[MeshPart]) -> np.ndarray:
    filled = [p.mesh.positions.astype(np.float64) for p in parts if p.mesh.vertex_count]
    return np.concatenate(filled) if filled else np.zeros((0, 3))


def triangle_count(parts: Sequence[MeshPart]) -> int:
    return sum(p.mesh.triangle_count for p in parts)


def distance_to_path(points: np.ndarray, path: Sequence[Point], *, closed: bool = False) -> np.ndarray:
    """Plan distance of each point (n, 2) to a polyline."""
    line = np.asarray(path, dtype=np.float64)
    starts = line if closed else line[:-1]
    ends = np.roll(line, -1, axis=0) if closed else line[1:]
    best = np.full(len(points), np.inf)
    for a, b in zip(starts, ends, strict=True):
        step = b - a
        length2 = float(step @ step)
        if length2 <= 1e-12:
            continue
        t = np.clip(((points - a) @ step) / length2, 0.0, 1.0)
        nearest = a + t[:, None] * step
        best = np.minimum(best, np.linalg.norm(points - nearest, axis=1))
    return best


def corner_reach(path: Sequence[Point], *, closed: bool = False, bevel_beyond: float) -> float:
    """How far past its lateral offset a swept section may reach at the path's corners, in
    offsets: ``1 / cos(half the turn)`` at a mitred joint — but a joint whose mitre would be
    longer than ``bevel_beyond`` is bevelled and stays at 1. From the angles alone."""
    line = np.asarray(path, dtype=np.float64)
    step = (np.roll(line, -1, axis=0) - line) if closed else np.diff(line, axis=0)
    heading = np.arctan2(step[:, 1], step[:, 0])
    turn = np.diff(np.concatenate([heading, heading[:1]])) if closed else np.diff(heading)
    turn = np.abs((turn + np.pi) % (2.0 * np.pi) - np.pi)
    reach = 1.0
    for angle in turn:
        cosine = math.cos(float(angle) / 2.0)
        mitre = 1.0 / cosine if cosine > 1e-9 else math.inf
        if mitre <= bevel_beyond * (1.0 + 1e-6):
            reach = max(reach, mitre)
    return reach


def path_length(path: Sequence[Point]) -> float:
    line = np.asarray(path, dtype=np.float64)
    return float(np.linalg.norm(np.diff(line, axis=0), axis=1).sum())


def plan_area(meshes: Sequence[Mesh]) -> float:
    """Area of the plan projection of meshes: the union of their triangles seen from above."""
    import pyclipper  # test-side only: the builders themselves may not import it

    scale = 1000.0
    clipper = pyclipper.Pyclipper()
    added = False
    for mesh in meshes:
        if not mesh.vertex_count:
            continue
        corners = mesh.positions.astype(np.float64)[mesh.indices][:, :, :2]
        for triangle in corners:
            path = [(round(float(x) * scale), round(float(y) * scale)) for x, y in triangle]
            if abs(pyclipper.Area(path)) < 1.0:
                continue  # a vertical face: no plan area
            if not pyclipper.Orientation(path):
                path.reverse()
            clipper.AddPath(path, pyclipper.PT_SUBJECT, True)
            added = True
    if not added:
        return 0.0
    union = clipper.Execute(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    return float(sum(pyclipper.Area(p) for p in union)) / (scale * scale)


def covers(meshes: Sequence[Mesh], x: float, y: float) -> bool:
    """True when some triangle of the meshes lies over the plan point."""
    p = np.array([x, y])

    def side(u: np.ndarray, v: np.ndarray) -> np.ndarray:
        return (v[:, 0] - u[:, 0]) * (p[1] - u[:, 1]) - (v[:, 1] - u[:, 1]) * (p[0] - u[:, 0])

    for mesh in meshes:
        if not mesh.vertex_count:
            continue
        t = mesh.positions.astype(np.float64)[mesh.indices][:, :, :2]
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        d1, d2, d3 = side(a, b), side(b, c), side(c, a)
        inside = ((d1 > 1e-9) & (d2 > 1e-9) & (d3 > 1e-9)) | ((d1 < -1e-9) & (d2 < -1e-9) & (d3 < -1e-9))
        if bool(inside.any()):
            return True
    return False


def outside_distance(points: np.ndarray, ring: Sequence[Point]) -> float:
    """How far the plan points (n, 2) reach OUTSIDE a polygon, at most (0.0 = all inside)."""
    polygon = np.asarray(ring, dtype=np.float64)
    following = np.roll(polygon, -1, axis=0)
    inside = np.zeros(len(points), dtype=bool)
    for (x1, y1), (x2, y2) in zip(polygon, following, strict=True):
        if y1 == y2:
            continue
        crosses = (y1 > points[:, 1]) != (y2 > points[:, 1])
        at = x1 + (points[:, 1] - y1) * (x2 - x1) / (y2 - y1)
        inside ^= crosses & (points[:, 0] < at)
    if inside.all():
        return 0.0
    return float(distance_to_path(points[~inside], ring, closed=True).max())
