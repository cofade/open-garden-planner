"""Surfaces, context and ground detail (Phase 17 L4.2 / L4.5, #388) — Qt-free.

- ``builders.surfaces``: relief on the painted ground — every part a
  ``ground_detail`` part (no shadow, never picked, the item still painted) —
  stones, planks, kerbs and edging per path style, kerbs and decks on a
  terrace or a driveway, a pond's water and coping, a lawn's blades; and what a
  surface the user gave a HEIGHT is (a raised deck, a raised pool, the prism).
- ``core/scene3d/context``: the params one record needs from the others (a
  building's door wall, a lawn's cut-outs and blade share).
- ``MeshPart.ground_detail`` through ``SceneSync`` (no solid), the pick oracle
  (not picked) and the record's ground comparison (no re-bake).
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from open_garden_planner.core.scene3d import (
    Material,
    Mesh,
    MeshPart,
    Paint,
    RecordingSink,
    SceneSync,
    Transform,
    default_builder,
    verify_builder,
)
from open_garden_planner.core.scene3d.build import BuilderRegistry
from open_garden_planner.core.scene3d.builders import (
    OBJECT_KINDS,
    SURFACE_KINDS,
    production_registry,
    surfaces,
)
from open_garden_planner.core.scene3d.context import (
    ENCLOSED_KINDS,
    GROUND_COVERING_KINDS,
    MAX_CUTOUTS,
    MAX_PLAN_BLADES,
    POND_CLEARANCE_CM,
    ROUND_PATH_STYLES,
    with_context,
)
from open_garden_planner.core.scene3d.pick_oracle import pick_scene
from open_garden_planner.core.scene3d.polygon import RegionTooLargeError
from open_garden_planner.core.scene3d.record import BUILD_ONLY_PARAMS, Params
from tests.unit.scene3d_builder_cases import (
    BENT_PATH,
    CLOSED_PATH,
    HAIRPIN_PATH,
    L_SHAPE,
    ZIGZAG_PATH,
    circle_record,
    distance_to_path,
    line_record,
    polygon_record,
    rectangle,
)

REGISTRY = production_registry()
PATH_STYLES = ["STEPPING_STONES", "WOODEN_BOARDWALK", "PAVED_PATH", "GRAVEL_PATH", "DIRT_PATH", None]


def test_the_surface_kinds() -> None:
    assert {"PATH", "TERRACE_PATIO", "DRIVEWAY", "POND_POOL", "LAWN"} == SURFACE_KINDS


# ── paths ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("style", PATH_STYLES)
@pytest.mark.parametrize("path", [BENT_PATH, CLOSED_PATH, HAIRPIN_PATH, ZIGZAG_PATH],
                         ids=["bent", "closed", "hairpin", "zigzag"])
@pytest.mark.parametrize("width", [60.0, 100.0, 8.0])
def test_a_path_s_relief_is_ground_detail_on_its_footprint(style, path, width) -> None:
    record = line_record("PATH", path, None, width=width, style=style)
    parts = verify_builder(REGISTRY.builder_for("PATH"), record, plan_margin_cm=10.0)
    assert all(part.ground_detail and not part.casts_shadow and part.tinted for part in parts)
    if style in (None, "DIRT_PATH") or width < surfaces.MIN_RELIEF_WIDTH_CM:
        assert parts == ()  # flat, or a 2D pattern rather than a path one walks on
    else:
        assert parts
        assert float(max(part.mesh.positions[:, 2].max() for part in parts)) <= surfaces.BOARD_TOP_CM


def reach_outside(record) -> float:
    """How far any relief of ``record`` lies outside its ground (the regions less
    their holes), in plan cm — per vertex and per triangle, which ``verify_builder``'s
    area check is not (3D review of #388: a boardwalk 15 cm, a gravel edging 18.6 cm
    past the path)."""
    parts = REGISTRY.build(record)
    if not parts:
        return 0.0
    samples = []
    for part in parts:  # every vertex, and every triangle's edge midpoints and centre: a
        # face may span a notch whose corners both lie on the outline
        corners = part.mesh.positions[:, :2].astype(np.float64)[part.mesh.indices.astype(np.int64)]
        samples += [corners.reshape(-1, 2), corners.mean(axis=1),
                    (corners + np.roll(corners, -1, axis=1)).reshape(-1, 2) / 2.0]
    points = np.concatenate(samples)
    inside = np.zeros(len(points), dtype=bool)
    for outer, holes in record.regions:
        here = surfaces._inside(points, np.asarray(outer, dtype=np.float64))
        for hole in holes:
            here &= ~surfaces._inside(points, np.asarray(hole, dtype=np.float64))
        inside |= here
    if inside.all():
        return 0.0
    rest = points[~inside]
    rings = [ring for outer, holes in record.regions for ring in (outer, *holes)]
    return float(np.min([distance_to_path(rest, ring, closed=True) for ring in rings], axis=0).max())


@pytest.mark.parametrize("style", PATH_STYLES[:4])
@pytest.mark.parametrize("path", [BENT_PATH, CLOSED_PATH, HAIRPIN_PATH, ZIGZAG_PATH],
                         ids=["bent", "closed", "hairpin", "zigzag"])
@pytest.mark.parametrize("width", [40.0, 90.0, 150.0])
def test_no_relief_vertex_lies_more_than_10_cm_past_the_path(style, path, width) -> None:
    record = line_record("PATH", path, None, width=width, style=style)
    assert reach_outside(record) <= 10.0


@pytest.mark.parametrize("kind,params", [("TERRACE_PATIO", {}), ("TERRACE_PATIO", {"surface_pattern": "DECKING"}),
                                         ("DRIVEWAY", {}), ("POND_POOL", {})])
@pytest.mark.parametrize("ring", [rectangle(400.0, 300.0), L_SHAPE], ids=["box", "L"])
def test_no_relief_vertex_lies_more_than_10_cm_past_a_surface(kind, params, ring) -> None:
    assert reach_outside(polygon_record(kind, ring, None, params=params)) <= 10.0


def test_the_stones_lie_where_the_2d_painter_draws_them() -> None:
    """``walk_path`` is ``PathStylePaint._walk_path``: a point every ``spacing`` along the
    line, each segment starting where the last one's spacing left off."""
    line = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0]])
    points, along = surfaces.walk_path(line, 40.0)
    assert np.allclose(points, [[0, 0], [40, 0], [80, 0], [100, 20]])
    assert np.allclose(along, [[1, 0], [1, 0], [1, 0], [0, 1]])
    one = line_record("PATH", ((0.0, 0.0), (50.0, 0.0)), None, width=60.0, style="STEPPING_STONES")
    per_stone = REGISTRY.build(one)[0].mesh.triangle_count
    record = line_record("PATH", ((-500.0, 0.0), (500.0, 0.0)), None, width=60.0, style="STEPPING_STONES")
    (stones,) = REGISTRY.build(record)
    walked = surfaces.walk_path(np.array(record.path), 108.0)[0]
    assert stones.mesh.triangle_count == per_stone * len(walked)  # every stone the 2D plan draws


def test_the_end_stone_is_slid_onto_the_path_not_dropped() -> None:
    """2D centres the first stone ON the path's end, half of it beyond; 3D slides it
    half a stone along the path, onto the footprint."""
    record = line_record("PATH", ((-500.0, 0.0), (500.0, 0.0)), None, width=60.0, style="STEPPING_STONES")
    (stones,) = REGISTRY.build(record)
    east = stones.mesh.positions[:, 0]
    assert float(east.min()) == pytest.approx(-500.0, abs=0.5)
    assert float(east.max()) <= 500.0 + 0.5


def test_a_stone_that_would_hang_off_a_tight_bend_is_slid_or_left_out() -> None:
    one = line_record("PATH", ((0.0, 0.0), (100.0, 0.0)), None, width=100.0, style="STEPPING_STONES")
    per_stone = REGISTRY.build(one)[0].mesh.triangle_count
    record = line_record("PATH", HAIRPIN_PATH, None, width=100.0, style="STEPPING_STONES")
    walked = len(surfaces.walk_path(np.array(record.path), 180.0)[0])
    (stones,) = verify_builder(REGISTRY.builder_for("PATH"), record, plan_margin_cm=10.0)
    assert 0 < stones.mesh.triangle_count <= per_stone * walked


def test_a_path_kilometres_long_gets_no_relief() -> None:
    record = line_record("PATH", ((-500_000.0, 0.0), (500_000.0, 0.0)), None, width=60.0,
                         style="STEPPING_STONES")
    assert REGISTRY.build(record) == ()


def test_a_path_the_user_gave_a_height_is_the_prism() -> None:
    record = line_record("PATH", BENT_PATH, 30.0, width=80.0, style="PAVED_PATH")
    assert REGISTRY.build(record) == default_builder(record)


# ── terraces, driveways, decks ───────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["TERRACE_PATIO", "DRIVEWAY"])
@pytest.mark.parametrize("pattern", ["DECKING", "WOOD", "FLAGSTONE", None])
@pytest.mark.parametrize("ring", [rectangle(400.0, 300.0), L_SHAPE], ids=["box", "L"])
def test_a_terrace_has_kerbs_or_deck_boards_inside_its_outline(kind, pattern, ring) -> None:
    params = {"surface_pattern": pattern} if pattern else {}
    record = polygon_record(kind, ring, None, params=params)
    (part,) = verify_builder(REGISTRY.builder_for(kind), record, plan_margin_cm=0.5)
    assert part.ground_detail and not part.casts_shadow and part.tinted
    assert part.name == ("deck" if pattern in surfaces.DECK_PATTERNS else "kerb")
    top = float(part.mesh.positions[:, 2].max())
    assert top == pytest.approx(surfaces.DECK_TOP_CM if part.name == "deck" else surfaces.KERB_CM)
    # on the ground, not above it (3D review of #388: the deck's boards were 1.25 cm off it)
    assert float(part.mesh.positions[:, 2].min()) == pytest.approx(0.0, abs=1e-3)


@pytest.mark.parametrize("pattern", ["DECKING", "STONE"])
def test_a_terrace_the_user_gave_a_height_is_a_solid_whose_top_is_it(pattern) -> None:
    record = polygon_record("TERRACE_PATIO", rectangle(400.0, 300.0), 45.0,
                            params={"surface_pattern": pattern})
    (part,) = verify_builder(REGISTRY.builder_for("TERRACE_PATIO"), record, plan_margin_cm=0.5)
    assert not part.ground_detail and part.casts_shadow
    assert float(part.mesh.positions[:, 2].max()) == pytest.approx(45.0)


def test_a_deck_s_boards_stay_inside_an_l() -> None:
    record = polygon_record("TERRACE_PATIO", L_SHAPE, None, params={"surface_pattern": "DECKING"})
    (deck,) = REGISTRY.build(record)
    points = deck.mesh.positions.astype(np.float64)
    inner_corner = (points[:, 0] > 5.0) & (points[:, 1] > 105.0)  # the L's missing quarter
    assert not inner_corner.any()


def comb(teeth: int, width: float = 4000.0, depth: float = 3000.0) -> list[tuple[float, float]]:
    """A 40 x 30 m outline with ``teeth`` teeth: every board row crosses every tooth."""
    points = [(0.0, 0.0), (width, 0.0), (width, 300.0)]
    step = width / teeth
    for k in range(teeth - 1, -1, -1):
        x0 = k * step
        points += [(x0 + 0.6 * step, 300.0), (x0 + 0.6 * step, depth),
                   (x0 + 0.2 * step, depth), (x0 + 0.2 * step, 300.0)]
    return [*points, (0.0, 300.0)]


@pytest.mark.parametrize("teeth", [5, 100, 2000])
@pytest.mark.parametrize("height", [None, 40.0])
def test_a_hostile_deck_is_bounded_by_construction(teeth: int, height: float | None) -> None:
    """Senior review of #388, P1: the boards were rows x runs and each run was found by
    a Python loop over every edge, per run — a 402-vertex comb built 446,364 triangles
    in 14 s, an 8,002-vertex one never finished. The runs are now found with numpy, and
    a deck that would need more than ``MAX_DECK_BOARDS`` boards gets none: a kerb on the
    ground, the plain solid when raised (which refuses what its own bound refuses)."""
    record = polygon_record("TERRACE_PATIO", comb(teeth), height, params={"surface_pattern": "DECKING"})
    try:
        parts = REGISTRY.build(record)
    except RegionTooLargeError:   # the raised plain solid's own bound: a contained build failure
        assert height is not None and teeth == 2000
        return
    triangles = sum(part.mesh.triangle_count for part in parts)
    assert triangles <= surfaces.MAX_DECK_BOARDS * 12 + 12 * surfaces.MAX_RELIEF_VERTICES
    names = {part.name for part in parts}
    if teeth == 100:   # 4 runs a row over 100 teeth: far beyond the cap
        assert names == ({"platform"} if height is not None else {"kerb"})


@pytest.mark.parametrize("width", [0.8, 20.0])
def test_a_deck_of_many_regions_scans_a_bounded_number_of_rows(
        width: float, monkeypatch: pytest.MonkeyPatch) -> None:
    """Senior review of #388, round 2: the board cap counted boards, not the rows
    scanned to find them — a self-crossing sawtooth resolved into 601 regions narrower
    than a board scanned 400 rows each and built nothing in 2.8 s. Rows are budgeted
    over ALL regions (``MAX_DECK_ROWS``), and a region narrower than 1 cm is skipped."""
    regions = tuple(((x, 0.0), (x + width, 0.0), (x + width, 3000.0), (x, 3000.0))
                    for x in np.arange(601) * (width + 5.0))
    record = dataclasses.replace(
        polygon_record("TERRACE_PATIO", regions[0], None, params={"surface_pattern": "DECKING"}),
        footprints=regions, holes=tuple(() for _ in regions))
    scans: list[float] = []
    real = surfaces._inside_at

    def counting(edges, at):  # noqa: ANN001, ANN202
        scans.append(at)
        return real(edges, at)

    monkeypatch.setattr(surfaces, "_inside_at", counting)
    parts = REGISTRY.build(record)
    assert len(scans) <= 3 * (surfaces.MAX_DECK_ROWS + 1)   # a row: its centre and two edges
    if width < 1.0:
        assert scans == [] and parts == ()   # no region can hold a board: none scanned
    else:
        assert {part.name for part in parts} == {"kerb"}   # beyond the budget: the kerb


@pytest.mark.parametrize("height", [None, 60.0])
def test_a_pond_of_many_small_regions_gets_no_sweep_along_all_of_them(height: float | None) -> None:
    """Security review of #388: the water's work bound holds per REGION, so a pond of
    many small regions passes it — and its coping, or a raised pool's walls, would be
    swept along all their vertices. Beyond ``MAX_RELIEF_VERTICES`` in all: the water
    alone (flat), the plain prism (raised)."""
    angle = np.linspace(0.0, 2.0 * np.pi, 16, endpoint=False)
    regions = tuple(tuple((float(x + 30.0 * np.cos(a)), float(30.0 * np.sin(a))) for a in angle)
                    for x in np.arange(300) * 80.0)
    assert sum(len(ring) for ring in regions) > surfaces.MAX_RELIEF_VERTICES
    record = dataclasses.replace(polygon_record("POND_POOL", regions[0], height),
                                 footprints=regions, holes=tuple(() for _ in regions))
    parts = REGISTRY.build(record)
    names = {part.name for part in parts}
    assert "coping" not in names and "walls" not in names, names
    triangles = sum(part.mesh.triangle_count for part in parts)
    assert triangles <= 64 * len(regions), triangles


@pytest.mark.parametrize("kind", ["TERRACE_PATIO", "DRIVEWAY"])
def test_an_outline_of_too_many_vertices_gets_no_relief(kind: str) -> None:
    """A kerb or a skirt is 12 triangles a vertex: beyond ``MAX_RELIEF_VERTICES`` the
    surface keeps its painted ground and no relief (an outline of 64,000 vertices built
    a kerb of 768,000 triangles). (A pond's water refuses such an outline first: its
    triangulation's own work bound.)"""
    count = surfaces.MAX_RELIEF_VERTICES + 4
    ring = [(2000.0 * np.cos(2 * np.pi * k / count), 2000.0 * np.sin(2 * np.pi * k / count))
            for k in range(count)]
    assert REGISTRY.build(polygon_record(kind, ring, None)) == ()
    small = ring[::2]   # half the vertices: under the cap, the relief is there
    assert REGISTRY.build(polygon_record(kind, small, None)) != ()


# ── ponds ────────────────────────────────────────────────────────────────────


def test_a_pond_is_water_inside_a_stone_coping() -> None:
    record = polygon_record("POND_POOL", rectangle(400.0, 300.0), None)
    water, coping = verify_builder(REGISTRY.builder_for("POND_POOL"), record, plan_margin_cm=10.0)
    assert (water.material_kind, water.name, water.tinted) == ("water", "water", True)
    assert coping.material_kind == "vc" and not coping.tinted
    assert all(part.ground_detail and not part.casts_shadow for part in (water, coping))
    assert float(water.mesh.positions[:, 2].max()) == pytest.approx(surfaces.WATER_CM)
    assert float(coping.mesh.positions[:, 2].max()) == pytest.approx(surfaces.COPING_UP_CM)


def test_a_round_pond_is_round_not_the_records_24_facets() -> None:
    record = circle_record("POND_POOL", 150.0, None)
    assert len(record.footprints[0]) < surfaces.ROUND_POND_SEGMENTS
    water, coping = verify_builder(REGISTRY.builder_for("POND_POOL"), record, plan_margin_cm=10.0)
    rim = coping.mesh.positions[np.isclose(coping.mesh.positions[:, 2], 0.0), :2]
    angles = np.unique(np.round(np.degrees(np.arctan2(rim[:, 1], rim[:, 0])), 3))
    assert len(angles) >= surfaces.ROUND_POND_SEGMENTS
    assert reach_outside(record) <= 10.0


def test_a_pond_the_user_gave_a_height_is_a_raised_pool() -> None:
    record = polygon_record("POND_POOL", rectangle(400.0, 300.0), 60.0)
    walls, water = verify_builder(REGISTRY.builder_for("POND_POOL"), record, plan_margin_cm=0.5)
    assert walls.casts_shadow and not walls.ground_detail
    assert float(walls.mesh.positions[:, 2].max()) == pytest.approx(60.0)
    assert 50.0 < float(water.mesh.positions[:, 2].max()) < 60.0


# ── lawns ────────────────────────────────────────────────────────────────────


def lawn(params=None, ring=None):
    return polygon_record("LAWN", ring if ring is not None else rectangle(800.0, 600.0), None,
                          params=params)


def blades_of(record) -> int:
    parts = REGISTRY.build(record)
    return sum(part.mesh.triangle_count for part in parts) // 3


def test_a_lawn_grows_blades_as_ground_detail() -> None:
    (blades,) = verify_builder(REGISTRY.builder_for("LAWN"), lawn(), plan_margin_cm=10.0)
    assert (blades.material_kind, blades.name) == ("grass", surfaces.LAWN_BLADES)
    assert blades.ground_detail and blades.tinted and not blades.casts_shadow
    assert 0.8 * 220.0 * 48.0 <= blades.mesh.triangle_count / 3 <= 1.2 * 220.0 * 48.0
    tips = blades.mesh.uvs[:, 0]
    assert np.round(np.unique(tips).astype(np.float64), 2).tolist() == [0.0, 0.45, 1.0]  # sway weight


def test_a_cutout_clears_the_blades_under_it_and_nothing_else() -> None:
    whole = blades_of(lawn())
    cut = ((-200.0, -150.0), (200.0, -150.0), (200.0, 150.0), (-200.0, 150.0))  # a quarter
    with_cut = blades_of(lawn({"lawn_cutouts": (cut,)}))
    assert with_cut == pytest.approx(0.75 * whole, rel=0.05)
    (part,) = REGISTRY.build(lawn({"lawn_cutouts": (cut,)}))
    roots = part.mesh.positions[::5, :2]
    assert not ((np.abs(roots[:, 0]) < 195.0) & (np.abs(roots[:, 1]) < 145.0)).any()


def test_the_plan_s_share_caps_a_lawn_s_blades() -> None:
    assert blades_of(lawn({"lawn_blades": 1000})) == pytest.approx(1000, rel=0.1)
    assert REGISTRY.build(lawn({"lawn_blades": 0})) == ()


@pytest.mark.parametrize("ring", [
    # a strip 10 km long and 20 cm wide, on the diagonal: 20 m2 of lawn in a 7 x 7 km box
    ((0.0, 0.0), (707_100.0, 707_100.0), (707_085.9, 707_114.1), (-14.1, 14.1)),
    # a strip 10 km long and 1 cm deep: a grid one row high
    ((0.0, 0.0), (1_000_000.0, 0.0), (1_000_000.0, 1.0), (0.0, 1.0)),
    # a round lawn of 16,000 edges, 2 km across: the point-in-ring work bounds the grid
    tuple((100_000.0 * np.cos(a), 100_000.0 * np.sin(a))
          for a in np.linspace(0.0, 2.0 * np.pi, 16_000, endpoint=False)),
], ids=["diagonal strip", "thin box", "many edges"])
def test_a_lawn_with_a_small_area_in_a_huge_box_grows_a_bounded_grid(
        ring, monkeypatch: pytest.MonkeyPatch) -> None:
    """Security review of #388: the roots' grid lies over the bounding box, so its
    size is bounded by construction (``MAX_SWARD_GRID``, ``MAX_SWARD_WORK``), not by
    the lawn's area."""
    surfaces.clear_lawn_cache()
    calls: list[int] = []
    real = np.meshgrid

    def counting(*arrays, **kwargs):
        calls.append(int(np.prod([len(a) for a in arrays])))
        return real(*arrays, **kwargs)

    monkeypatch.setattr(np, "meshgrid", counting)
    try:
        parts = REGISTRY.build(polygon_record("LAWN", ring, None))
    finally:
        surfaces.clear_lawn_cache()
    bound = min(surfaces.MAX_SWARD_GRID, surfaces.MAX_SWARD_WORK // len(ring))
    assert calls and max(calls) <= bound
    assert sum(part.mesh.triangle_count for part in parts) <= 3 * surfaces.MAX_BLADES


def test_a_lawn_the_user_gave_a_height_is_the_prism() -> None:
    record = polygon_record("LAWN", rectangle(800.0, 600.0), 20.0)
    assert REGISTRY.build(record) == default_builder(record)


def test_a_lawn_s_blades_are_remembered_by_its_own_geometry() -> None:
    surfaces.clear_lawn_cache()
    REGISTRY.build(lawn())
    REGISTRY.build(lawn({"lawn_cutouts": (((-10.0, -10.0), (10.0, -10.0), (0.0, 10.0)),)}))
    info = surfaces.sward_cache_info()
    assert info["misses"] == 1 and info["hits"] == 1  # the cut-out re-masks the same sward
    assert 0 < info["bytes"] <= surfaces.SWARD_CACHE_BYTES
    surfaces.clear_lawn_cache()
    assert surfaces.sward_cache_info() == {"hits": 0, "misses": 0, "entries": 0, "bytes": 0}


def test_the_sward_memory_is_capped_in_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    surfaces.clear_lawn_cache()
    one = surfaces._sward((rectangle(800.0, 600.0),), (), "a", None).nbytes
    monkeypatch.setattr(surfaces, "SWARD_CACHE_BYTES", int(2.5 * one))
    for seed in "bcdef":
        surfaces._sward((rectangle(800.0, 600.0),), (), seed, None)
    info = surfaces.sward_cache_info()
    assert info["entries"] == 2 and info["bytes"] <= 2.5 * one
    surfaces.clear_lawn_cache()


# ── the context pass ─────────────────────────────────────────────────────────


def painted(record):
    return dataclasses.replace(record, material=Material(record.kind, (90, 160, 70, 255), paint=Paint()))


def at(record, east: float, north: float, rotation: float = 0.0):
    return dataclasses.replace(record, transform=Transform(east, north, rotation))


def test_a_house_s_door_faces_the_nearest_path_and_a_garage_s_the_driveway() -> None:
    house = at(polygon_record("HOUSE", rectangle(900.0, 540.0), 450.0, item_id="house"), 0.0, 0.0)
    garage = at(polygon_record("GARAGE_SHED", rectangle(400.0, 300.0), 250.0, item_id="garage"),
                2000.0, 0.0)
    path = at(line_record("PATH", ((-200.0, 0.0), (200.0, 0.0)), None, width=80.0, item_id="path"),
              0.0, -800.0)  # south of both
    drive = at(polygon_record("DRIVEWAY", rectangle(300.0, 300.0), None, item_id="drive"), 2000.0, 900.0)
    records = {r.item_id: r for r in (house, garage, path, drive)}
    with_context(records)
    assert records["house"].params["door_wall"] == 0       # the south wall
    assert records["garage"].params["door_wall"] == 2      # the north wall: the driveway first


def test_a_turned_house_reads_the_path_in_its_own_frame() -> None:
    house = at(polygon_record("HOUSE", rectangle(900.0, 540.0), 450.0, item_id="house"), 0.0, 0.0, 90.0)
    path = at(line_record("PATH", ((-100.0, 0.0), (100.0, 0.0)), None, width=80.0, item_id="path"),
              0.0, -800.0)
    records = {r.item_id: r for r in (house, path)}
    with_context(records)
    # turned 90° counter-clockwise, the house's local +x faces the scene's north: the path in
    # the scene's south lies on its local -x side — wall 3 (walls 0..3: south, east, north, west)
    assert records["house"].params["door_wall"] == 3


def test_moving_a_house_along_its_path_keeps_its_door_param() -> None:
    path = at(line_record("PATH", ((-2000.0, 0.0), (2000.0, 0.0)), None, width=80.0, item_id="path"),
              0.0, -800.0)
    params = []
    for east in (0.0, 137.25, 500.0):
        house = at(polygon_record("HOUSE", rectangle(900.0, 540.0), 450.0, item_id="house"), east, 0.0)
        records = {r.item_id: r for r in (house, path)}
        with_context(records)
        params.append(records["house"].params)
    assert params[0] == params[1] == params[2]


def test_a_lawn_is_cut_by_flat_items_painted_above_it_and_by_enclosed_buildings() -> None:
    lawn_record = painted(at(polygon_record("LAWN", rectangle(2000.0, 2000.0), None, item_id="lawn"), 0.0, 0.0))
    under = painted(at(polygon_record("TERRACE_PATIO", rectangle(200.0, 200.0), None, item_id="under"),
                       -500.0, 0.0))
    above = painted(at(polygon_record("TERRACE_PATIO", rectangle(200.0, 200.0), None, item_id="above"),
                       500.0, 0.0))
    tree = painted(at(polygon_record("TREE", rectangle(100.0, 100.0), 400.0, item_id="tree"), 0.0, 500.0))
    table = painted(at(polygon_record("TABLE_RECTANGULAR", rectangle(150.0, 100.0), 75.0, item_id="table"),
                       0.0, -500.0))
    greenhouse = at(polygon_record("GREENHOUSE", rectangle(300.0, 200.0), 220.0, item_id="glass"), 0.0, 0.0)
    far = painted(at(polygon_record("TERRACE_PATIO", rectangle(200.0, 200.0), None, item_id="far"), 9000.0, 0.0))
    records = {r.item_id: r for r in (greenhouse, under, lawn_record, above, tree, table, far)}
    with_context(records)
    cutouts = records["lawn"].params["lawn_cutouts"]
    centres = sorted((round(float(np.mean([p[0] for p in ring]))), round(float(np.mean([p[1] for p in ring]))))
                     for ring in cutouts)
    assert centres == [(0, 0), (500, 0)]  # the terrace above and the greenhouse (drawn below it)
    assert {"HOUSE", "GARAGE_SHED", "TOOL_SHED", "GREENHOUSE"} == ENCLOSED_KINDS


def _blade_roots_cut(cutter) -> tuple[np.ndarray, np.ndarray]:  # noqa: ANN001 - a Record
    """A lawn under ``cutter``: the roots of its blades with and without the cut-out."""
    lawn_record = painted(at(polygon_record("LAWN", rectangle(2400.0, 2400.0), None, item_id="lawn"), 0.0, 0.0))
    records = {"lawn": lawn_record, cutter.item_id: painted(cutter)}
    with_context(records)
    cut = records["lawn"]
    whole = dataclasses.replace(cut, params=Params({k: v for k, v in cut.params.items() if k != "lawn_cutouts"}))
    return tuple(_roots(next(part for part in REGISTRY.build(record) if part.name == surfaces.LAWN_BLADES))
                 for record in (whole, cut))


def _roots(part) -> np.ndarray:  # noqa: ANN001 - a MeshPart
    """Where each blade stands: the middle of its vertices on the ground (5 a blade)."""
    blades = part.mesh.positions.astype(np.float64).reshape(-1, 5, 3)
    base = blades[:, :, 2] <= blades[:, :, 2].min(axis=1, keepdims=True) + 1e-6
    return np.stack([(blades[..., axis] * base).sum(axis=1) / base.sum(axis=1) for axis in (0, 1)], axis=1)


def test_no_blade_grows_through_a_pond_s_coping() -> None:
    """3D review of #388: blades rooted under the coping's 7 cm overhang grew through it."""
    pond = circle_record("POND_POOL", 300.0, None, item_id="pond")
    whole, cut = _blade_roots_cut(pond)
    reach = np.hypot(cut[:, 0], cut[:, 1])
    assert reach.min() >= 300.0 + POND_CLEARANCE_CM - 0.6  # the grown ring's arcs (0.5 cm)
    assert POND_CLEARANCE_CM == surfaces.COPING_OUT_CM + 2.0
    kept = np.hypot(whole[:, 0], whole[:, 1])
    assert ((kept > 300.0) & (kept < 300.0 + surfaces.COPING_OUT_CM)).sum() > 10  # there were some


@pytest.mark.parametrize("style", ["GRAVEL_PATH", "DIRT_PATH", "PAVED_PATH"])
def test_a_gravel_or_dirt_path_s_cutout_has_the_round_ends_the_canvas_paints(style) -> None:
    """3D review of #388: the canvas paints a gravel and a dirt path with round caps half
    a width past each end; the square-ended outline let blades grow there."""
    path = line_record("PATH", ((-500.0, 0.0), (500.0, 0.0)), None, width=80.0, style=style, item_id="p")
    _whole, cut = _blade_roots_cut(path)
    beyond_end = (cut[:, 0] > 505.0) & (cut[:, 0] < 535.0) & (np.abs(cut[:, 1]) < 10.0)
    assert bool(beyond_end.any()) is (style == "PAVED_PATH"), style  # a paved path ends square
    assert not ((np.abs(cut[:, 0]) < 500.0) & (np.abs(cut[:, 1]) < 40.0)).any()
    assert style in ROUND_PATH_STYLES or style == "PAVED_PATH"


def test_a_closed_gravel_loop_keeps_its_outline() -> None:
    """A loop's rounded stroke would be two rings, and a cut-out ring is filled: the
    garden inside the loop would lose its blades. A loop keeps its outline."""
    loop = line_record("PATH", CLOSED_PATH, None, width=80.0, style="GRAVEL_PATH", item_id="loop")
    _whole, cut = _blade_roots_cut(loop)
    inside = (np.abs(cut[:, 0]) < 300.0) & (np.abs(cut[:, 1]) < 200.0)
    assert inside.any(), "the blades inside the loop stay"


@pytest.mark.parametrize("kind,cuts", [("PERGOLA", False), ("PARASOL", False), ("HAMMOCK", False),
                                       ("SWING", False), ("WATER_TAP", False), ("PLANTER_POT", True),
                                       ("FIRE_PIT", True), ("COLD_FRAME", True)])
def test_an_object_cuts_the_lawn_only_where_it_covers_the_ground(kind, cuts) -> None:
    """Senior review of #388: an object that had no height was BUILT (at an illustrative
    height, its default since the owner's second pass) and so no longer painted, but
    its outline still cut the lawn — a pergola
    left 12 m² of bald lawn, a parasol 6 m². Only an object that covers its footprint
    at the ground cuts it, with a height or without one."""
    for height in (None, 30.0):   # round 2: a cold frame's soil is a few cm up, with a height too
        lawn_record = painted(at(polygon_record("LAWN", rectangle(2000.0, 2000.0), None, item_id="lawn"),
                                 0.0, 0.0))
        thing = painted(at(polygon_record(kind, rectangle(200.0, 200.0), height, item_id="thing"), 300.0, 0.0))
        records = {r.item_id: r for r in (thing, lawn_record)}   # drawn under the lawn, even
        with_context(records)
        assert ("lawn_cutouts" in records["lawn"].params) is cuts, height
    assert GROUND_COVERING_KINDS <= OBJECT_KINDS


def test_the_cutouts_are_in_the_lawn_s_own_frame() -> None:
    lawn_record = painted(at(polygon_record("LAWN", rectangle(2000.0, 2000.0), None, item_id="lawn"),
                             1000.0, 1000.0, 90.0))
    path = painted(at(polygon_record("TERRACE_PATIO", rectangle(100.0, 100.0), None, item_id="t"),
                      1500.0, 1000.0))  # 500 east of the lawn's centre
    records = {r.item_id: r for r in (lawn_record, path)}
    with_context(records)
    (ring,) = records["lawn"].params["lawn_cutouts"]
    centre = np.mean(np.asarray(ring), axis=0)
    assert np.allclose(centre, (0.0, -500.0), atol=1e-6)  # east of it is its local -y, turned 90°


def test_the_plan_s_blades_are_shared_and_none_is_wasted() -> None:
    big = painted(at(polygon_record("LAWN", rectangle(6000.0, 6000.0), None, item_id="big"), 0.0, 0.0))
    small = painted(at(polygon_record("LAWN", rectangle(600.0, 600.0), None, item_id="small"), 9000.0, 0.0))
    records = {r.item_id: r for r in (big, small)}
    with_context(records)
    a, b = records["big"].params["lawn_blades"], records["small"].params["lawn_blades"]
    assert a + b <= MAX_PLAN_BLADES and a == surfaces.MAX_BLADES  # the big lawn: capped
    assert b == int(220.0 * 36.0)  # the small one gets its own density from what the big one cannot use


def test_a_raised_lawn_takes_no_share_of_the_plan_s_blades() -> None:
    """A lawn with a height is the plain prism and grows no blades, yet it took a share:
    beside a raised 30 x 30 m lawn the real one got 30,000 blades, alone 36,000
    (senior review of #388, round 4)."""
    real = painted(at(polygon_record("LAWN", rectangle(3000.0, 3000.0), None, item_id="real"), 0.0, 0.0))
    raised = painted(at(polygon_record("LAWN", rectangle(3000.0, 3000.0), 50.0, item_id="raised"), 4000.0, 0.0))
    records = {r.item_id: r for r in (real, raised)}
    with_context(records)
    assert records["real"].params["lawn_blades"] == surfaces.MAX_BLADES
    assert "lawn_blades" not in records["raised"].params and "lawn_cutouts" not in records["raised"].params


def test_lawns_past_the_plan_budget_share_it_by_area() -> None:
    lawns = [painted(at(polygon_record("LAWN", rectangle(side, side), None, item_id=f"l{i}"), 10_000.0 * i, 0.0))
             for i, side in enumerate((1500.0, 1500.0, 3000.0))]
    records = {r.item_id: r for r in lawns}
    with_context(records)
    blades = [records[f"l{i}"].params["lawn_blades"] for i in range(3)]
    assert sum(blades) <= MAX_PLAN_BLADES and sum(blades) >= MAX_PLAN_BLADES - 3
    assert blades[0] == blades[1] and blades[2] == pytest.approx(min(surfaces.MAX_BLADES, 4 * blades[0]), abs=4)


def test_too_many_cutouts_keep_the_largest() -> None:
    lawn_record = painted(at(polygon_record("LAWN", rectangle(40000.0, 40000.0), None, item_id="lawn"), 0.0, 0.0))
    records = {"lawn": lawn_record}
    for index in range(MAX_CUTOUTS + 20):
        size = 50.0 + index
        records[f"t{index}"] = painted(at(polygon_record("TERRACE_PATIO", rectangle(size, size), None,
                                                         item_id=f"t{index}"), 300.0 * (index % 50), 300.0 * (index // 50)))
    with_context(records)
    kept = records["lawn"].params["lawn_cutouts"]
    assert len(kept) == MAX_CUTOUTS
    smallest_kept = min(abs(np.ptp(np.asarray(ring)[:, 0])) for ring in kept)
    assert smallest_kept >= 50.0 + 20 - 1e-6


def test_the_context_params_are_build_only() -> None:
    assert {"door_wall", "lawn_cutouts", "lawn_blades", "roof_style", "roof_pitch_deg",
            "roof_overhang_cm", "surface_pattern"} == BUILD_ONLY_PARAMS
    lawn_record = polygon_record("LAWN", rectangle(800.0, 600.0), None)
    cut = dataclasses.replace(lawn_record, params=lawn_record.params.merged({"lawn_cutouts": ()}))
    assert not lawn_record.same_geometry(cut) and lawn_record.same_ground_geometry(cut)
    moved = dataclasses.replace(lawn_record, footprints=(rectangle(801.0, 600.0),))
    assert not lawn_record.same_ground_geometry(dataclasses.replace(moved, params=cut.params))
    other = dataclasses.replace(lawn_record, params=lawn_record.params.merged({"seed": "x"}))
    assert not lawn_record.same_ground_geometry(other)
    assert isinstance(cut.params, Params)


# ── ground detail through the pipeline ───────────────────────────────────────


def test_a_ground_detail_part_casts_no_shadow_by_construction() -> None:
    mesh = Mesh.empty()
    with pytest.raises(ValueError, match="casts no shadow"):
        MeshPart(mesh, ground_detail=True)
    assert MeshPart(mesh, casts_shadow=False, ground_detail=True).ground_detail


def test_ground_detail_is_no_solid_and_is_never_picked() -> None:
    path = line_record("PATH", BENT_PATH, None, width=80.0, style="STEPPING_STONES", item_id="path")
    table = polygon_record("TABLE_RECTANGULAR", rectangle(150.0, 100.0), 75.0, item_id="table")
    sync = SceneSync(RecordingSink(), REGISTRY)
    sync.apply({"path": path, "table": table})
    assert sync.solid_ids == frozenset({"table"})  # the path is still painted on the ground
    assert sync.sink.item("path").parts  # … and its stones are in the engine
    scene = pick_scene({"path": path, "table": table}, REGISTRY.build)
    assert scene.item_ids == ("table",)


def test_an_item_with_a_solid_part_and_relief_is_a_solid() -> None:
    def mixed(record):
        relief = REGISTRY.build(line_record("PATH", BENT_PATH, None, width=80.0, style="PAVED_PATH"))
        return (*relief, *default_builder(dataclasses.replace(record, height_cm=50.0)))

    registry = BuilderRegistry()
    registry.register("PATH", mixed)
    sync = SceneSync(RecordingSink(), registry)
    record = line_record("PATH", BENT_PATH, None, width=80.0, style="PAVED_PATH", item_id="p")
    sync.apply({"p": record})
    assert sync.solid_ids == frozenset({"p"})
