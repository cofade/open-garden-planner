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
from open_garden_planner.core.scene3d.polygon import (
    RegionTooLargeError,
    group_rings,
    point_in_ring,
)
from open_garden_planner.core.scene3d.record import BUILD_ONLY_PARAMS, Params
from open_garden_planner.core.shadow_geometry import polyline_round_outline
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


@pytest.mark.parametrize("size_cm", [0.1, 0.5, 1.0, 2.0, 3.0])
@pytest.mark.parametrize("height_cm", [0.1, 0.5, 1.0, 30.0])
def test_tiny_raised_ponds_are_valid_prisms(size_cm, height_cm) -> None:
    record = polygon_record("POND_POOL", rectangle(size_cm, size_cm), height_cm)
    parts = verify_builder(REGISTRY.builder_for("POND_POOL"), record, plan_margin_cm=10.0)
    assert parts
    assert max(float(part.mesh.positions[:, 2].max()) for part in parts) == pytest.approx(height_cm)


def test_moss_is_a_low_dense_cushion_and_sand_is_raked() -> None:
    """#960: the Japanese garden's moss and raked-sand court have looks of their own,
    moss gets MOSS_BLADES_PER_M2 through with_context, and hostile comb sand is capped."""
    lawn = polygon_record("LAWN", rectangle(400.0, 300.0), None,
                          params={"surface_pattern": "MOSS"})
    records = {lawn.item_id: lawn}
    with_context(records)
    # 12 m² at 1800/m² = 21,600 (clamped by MAX_BLADES), well above regular 220/m² (2,640)
    assert records[lawn.item_id].params["lawn_blades"] > int(surfaces.BLADES_PER_M2 * 12.0) * 3
    blades = REGISTRY.build(records[lawn.item_id])
    assert len(blades) == 1 and blades[0].name == surfaces.LAWN_BLADES
    assert float(blades[0].mesh.positions[:, 2].max()) <= surfaces.MOSS_BLADE_CM * 1.3 + 0.31

    zen = polygon_record("TERRACE_PATIO", rectangle(600.0, 420.0), None,
                         params={"surface_pattern": "SAND"})
    parts = REGISTRY.build(zen)
    ridges = [part for part in parts if part.name == "raked_sand"]
    assert ridges and ridges[0].ground_detail and ridges[0].casts_shadow is False
    assert float(ridges[0].mesh.positions[:, 2].max()) <= surfaces.RAKED_SAND_HEIGHT_CM + 1e-4
    assert len(ridges[0].mesh.positions) > 200

    # Hostile comb polygon: stays under MAX_RELIEF_VERTICES but exceeds MAX_RAKED_RIDGES.
    teeth = 60
    comb = [(0.0, 0.0), (teeth * 20.0, 0.0)]
    for i in range(teeth - 1, -1, -1):
        x = i * 20.0
        comb.extend([(x + 15.0, 1200.0), (x + 5.0, 1200.0), (x + 5.0, 20.0), (x, 20.0)])
    hostile = polygon_record("TERRACE_PATIO", tuple(comb), None, params={"surface_pattern": "SAND"})
    assert REGISTRY.build(hostile) == ()


def test_a_raked_court_does_not_draw_a_ridge_across_an_island_above_it() -> None:
    """#960 review round 2: the SAND court's cut-outs split the ridge rows, so no beam
    crosses a moss island painted above it (the board's tan bands)."""
    court = polygon_record("TERRACE_PATIO", rectangle(600.0, 420.0), None,
                           params={"surface_pattern": "SAND"}, item_id="court")
    island = dataclasses.replace(
        polygon_record("LAWN", rectangle(100.0, 100.0), None,
                       params={"surface_pattern": "MOSS"}, item_id="island"),
        material=Material("LAWN", (200, 180, 140, 255), paint=Paint()))
    records = {court.item_id: court, island.item_id: island}
    with_context(records)
    assert records[court.item_id].params.get("lawn_cutouts")
    beams = surfaces._raked_sand(records[court.item_id])
    assert beams
    for beam in beams:
        x0, x1 = float(beam.positions[:, 0].min()), float(beam.positions[:, 0].max())
        y0, y1 = float(beam.positions[:, 1].min()), float(beam.positions[:, 1].max())
        # The island is x/y in [-50, 50]; a beam may be beside it, never through it.
        assert not (y0 < 50.0 and y1 > -50.0 and x0 < 50.0 and x1 > -50.0), (
            x0, x1, y0, y1)


def test_a_stepping_stone_paths_painted_stone_is_cut_out_of_the_rake() -> None:
    """#998: the canvas paints a stepping stone centred on the path's end, so its
    picture reaches 0.4 widths (22 cm at 55 cm) beyond the footprint. The court's
    cut-out covers that painted stone, so no ridge is drawn across it."""
    width = 55.0
    court = polygon_record("TERRACE_PATIO", rectangle(600.0, 420.0), None,
                           params={"surface_pattern": "SAND"}, item_id="court")
    path = dataclasses.replace(
        line_record("PATH", ((0.0, 0.0), (250.0, 0.0)), None, width=width,
                    style="STEPPING_STONES", item_id="steps"),
        material=Material("PATH", (200, 180, 140, 255), paint=Paint()))
    records = {court.item_id: court, path.item_id: path}
    with_context(records)
    rings = records[court.item_id].params.get("lawn_cutouts", ())
    half_along = 0.4 * width   # a stone is 0.8 widths long, centred on the walk
    half_across = 0.3 * width  # and 0.6 widths across
    walked = surfaces.walk_path(np.asarray(path.path, dtype=float), width * 1.8)[0]
    # One cut-out per painted stone, not one corridor through the court.
    assert len(rings) == len(walked)
    assert any(point_in_ring(-half_along, 0.0, ring) for ring in rings), (
        "the cut-out stops at the path footprint, not at the painted stone")
    beams = surfaces._raked_sand(records[court.item_id])
    assert beams
    # The painted stone is a rounded rectangle (radius 2 cm): compare against its
    # straight-sided core, not the corner the ridge's own 2.4 cm width may graze.
    core_along, core_across = half_along - 2.0, half_across - 2.0
    for beam in beams:
        x0, x1 = float(beam.positions[:, 0].min()), float(beam.positions[:, 0].max())
        y0, y1 = float(beam.positions[:, 1].min()), float(beam.positions[:, 1].max())
        assert not (y0 < core_across and y1 > -core_across
                    and x0 < core_along and x1 > -core_along), (
            "a ridge crosses the painted stone", x0, x1, y0, y1)
    # And the rake still runs between two stones: the corridor is not cut out.
    assert any(x0 > 0.0 and x1 < 80.0 for x0, x1, *_ in (
        (float(beam.positions[:, 0].min()), float(beam.positions[:, 0].max()))
        for beam in beams)), "the whole stepping-stone corridor is cut out"


def test_batched_lawn_mask_matches_even_odd_at_edges_holes_and_self_crossings() -> None:
    rng = np.random.default_rng(607)
    points = np.concatenate([rng.uniform(-200, 200, (2000, 2)),
                             np.array([[0, 0], [100, 0], [0, 100], [100, 100]])])
    rings = [rectangle(200, 200), L_SHAPE,
             ((0, 0), (100, 100), (0, 100), (100, 0)),
             ((-100, -100), (100, -100), (100, 100), (-100, 100), (-100, -100),
              (-50, -50), (-50, 50), (50, 50), (50, -50), (-50, -50), (-100, -100))]
    for ring in rings:
        expected = []
        for x, y in points:
            inside = False
            for (x1, y1), (x2, y2) in zip(ring, (*ring[1:], ring[0]), strict=True):
                if (y1 > y) != (y2 > y) and x < x1 + (y-y1)*(x2-x1)/(y2-y1):
                    inside = not inside
            expected.append(inside)
        assert np.array_equal(surfaces._inside(points, np.array(ring)), expected)


def test_zero_lawn_share_never_synthesizes_a_sward(monkeypatch) -> None:
    def forbidden(*args):
        pytest.fail("Low/Medium must not synthesize lawn blades")

    monkeypatch.setattr(surfaces, "_sward", forbidden)
    record = polygon_record("LAWN", rectangle(2000.0, 2000.0), None, params={"lawn_blades": 0})
    assert REGISTRY.build(record) == ()


def test_long_lawn_ring_uses_the_same_even_odd_mask_as_a_dense_circle() -> None:
    theta = np.linspace(0.0, 2.0 * np.pi, 2048, endpoint=False)
    ring = np.stack([100.0 * np.cos(theta), 100.0 * np.sin(theta)], axis=1)
    points = np.random.default_rng(607).uniform(-110, 110, (2048, 2))
    radius = np.linalg.norm(points, axis=1)
    away_from_edge = np.abs(radius - 100.0) > 0.01
    assert np.array_equal(surfaces._inside(points[away_from_edge], ring), radius[away_from_edge] < 100.0)
PATH_STYLES = ["STEPPING_STONES", "WOODEN_BOARDWALK", "PAVED_PATH", "GRAVEL_PATH", "DIRT_PATH", None]


def test_the_surface_kinds() -> None:
    assert {"PATH", "TERRACE_PATIO", "DRIVEWAY", "POND_POOL", "LAWN",
            "GENERIC_POLYGON"} == SURFACE_KINDS


# ── paths ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("style", PATH_STYLES)
@pytest.mark.parametrize("path", [BENT_PATH, CLOSED_PATH, HAIRPIN_PATH, ZIGZAG_PATH],
                         ids=["bent", "closed", "hairpin", "zigzag"])
@pytest.mark.parametrize("width", [60.0, 100.0, 8.0])
def test_a_path_s_relief_is_ground_detail_on_its_footprint(style, path, width) -> None:
    record = line_record("PATH", path, None, width=width, style=style)
    # A stepping stone is centred on the 2D painter's walk, so an end stone stands
    # 0.4 widths beyond the stroke; every other relief stays within 10 cm (#998).
    margin = 0.5 * width + 1.0 if style == "STEPPING_STONES" else 10.0
    parts = verify_builder(REGISTRY.builder_for("PATH"), record, plan_margin_cm=margin)
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
    regions = record.regions
    if record.kind == "PATH" and record.params.get("path_style") == "GRAVEL_PATH":
        # The caster's nominal square/butt footprint is not the painted ground.
        # Round caps extend half a width beyond it. This analytical comparison
        # is independently pinned against Qt's stroke in test_gravel_rim_relief.
        regions = group_rings([tuple(ring) for ring in polyline_round_outline(
            record.path, record.path_width_cm,
            arc_tolerance_cm=surfaces.GRAVEL_ARC_TOLERANCE_CM)])
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
    for outer, holes in regions:
        here = surfaces._inside(points, np.asarray(outer, dtype=np.float64))
        for hole in holes:
            here &= ~surfaces._inside(points, np.asarray(hole, dtype=np.float64))
        inside |= here
    if inside.all():
        return 0.0
    rest = points[~inside]
    rings = [ring for outer, holes in regions for ring in (outer, *holes)]
    return float(np.min([distance_to_path(rest, ring, closed=True) for ring in rings], axis=0).max())


@pytest.mark.parametrize("style", PATH_STYLES[:4])
@pytest.mark.parametrize("path", [BENT_PATH, CLOSED_PATH, HAIRPIN_PATH, ZIGZAG_PATH],
                         ids=["bent", "closed", "hairpin", "zigzag"])
@pytest.mark.parametrize("width", [40.0, 90.0, 150.0])
def test_no_relief_vertex_lies_more_than_10_cm_past_the_path(style, path, width) -> None:
    record = line_record("PATH", path, None, width=width, style=style)
    # A stepping stone is centred on the painter's walk, so a corner of an end stone
    # is at most half a width (its half-diagonal) past the stroke (#998).
    allowed = 0.05 if style == "GRAVEL_PATH" else (
        0.5 * width + 1.0 if style == "STEPPING_STONES" else 10.0)
    assert reach_outside(record) <= allowed


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


def test_an_open_end_stone_is_where_the_2d_painter_draws_it() -> None:
    """#998: the 3D stone mirrors the painter's walk, including the first stone centred
    on an open end, half of it beyond the footprint (22 cm at 55 cm wide)."""
    record = line_record("PATH", ((-500.0, 0.0), (500.0, 0.0)), None, width=60.0,
                         style="STEPPING_STONES")
    (stones,) = REGISTRY.build(record)
    east = stones.mesh.positions[:, 0]
    assert float(east.min()) == pytest.approx(-500.0 - 0.4 * 60.0, abs=0.5)
    assert float(east.max()) <= 500.0 + 0.5


def test_every_stone_the_2d_painter_draws_on_a_tight_bend_is_built() -> None:
    one = line_record("PATH", ((0.0, 0.0), (100.0, 0.0)), None, width=100.0, style="STEPPING_STONES")
    per_stone = REGISTRY.build(one)[0].mesh.triangle_count
    record = line_record("PATH", HAIRPIN_PATH, None, width=100.0, style="STEPPING_STONES")
    walked = len(surfaces.walk_path(np.array(record.path), 180.0)[0])
    # The painted stone may stand beyond the stroke at an end or a bend; the cut-out
    # that keeps grass and rake off it is the same walk (context._cutout_rings).
    (stones,) = verify_builder(REGISTRY.builder_for("PATH"), record,
                               plan_margin_cm=0.5 * 100.0 + 1.0)
    assert stones.mesh.triangle_count == per_stone * walked


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
    parts = verify_builder(REGISTRY.builder_for("TERRACE_PATIO"), record, plan_margin_cm=0.5)
    assert parts and not any(part.ground_detail for part in parts)
    assert all(part.casts_shadow for part in parts)
    assert max(float(part.mesh.positions[:, 2].max()) for part in parts) == pytest.approx(45.0)


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
        assert names == ({"platform", "platform_sides"} if height is not None else {"kerb"})


@pytest.mark.parametrize("pattern", [None, "FLAGSTONE", "STONE"])
def test_a_raised_terrace_platform_shows_its_own_fill(pattern: str | None) -> None:
    """#628 follow-up: a terrace given a height keeps the fill the ground bake painted
    ("platform", ``fill_texture``) instead of turning into a flat slab; a raised DECK
    keeps its boards, which are geometry of their own."""
    params = {"surface_pattern": pattern} if pattern is not None else {}
    record = polygon_record("TERRACE_PATIO", rectangle(200.0, 120.0), 30.0, params=params)
    sides, cap = REGISTRY.build(record)
    assert cap.name == "platform" and cap.fill_texture and not cap.tinted
    # the canvas paints no texture down an edge: the sides are the item's tint (#627)
    assert sides.name == "platform_sides" and sides.tinted and not sides.fill_texture


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
    # a NON-zero anchor: the water's picture must sit in the canvas's phase, and with
    # (0, 0) a builder that dropped the origin would still compare equal
    record = dataclasses.replace(polygon_record("POND_POOL", rectangle(400.0, 300.0), 60.0),
                                 params=Params({"seed": "pond", "paint_origin": (137.0, -42.0)}))
    walls, water = verify_builder(REGISTRY.builder_for("POND_POOL"), record, plan_margin_cm=0.5)
    assert walls.casts_shadow and not walls.ground_detail
    assert float(walls.mesh.positions[:, 2].max()) == pytest.approx(60.0)
    assert 50.0 < float(water.mesh.positions[:, 2].max()) < 60.0
    # #627's manual pass: the water shows the plan's own water, not the flat fill
    # colour - the water shader samples the picture (uFill) and still lights it
    assert water.material_kind == "water" and water.fill_texture and not water.tinted
    # ... and it samples it with the plan's UVs: one texel would be a flat colour
    # (the render gate: luma std 17.25 with the plan UVs, 0.000 without - one texel)
    from open_garden_planner.core.scene3d import PATTERN_TILE_CM

    uvs = water.mesh.uvs
    assert np.ptp(uvs[:, 0]) > 0.5 and np.ptp(uvs[:, 1]) > 0.5
    expected = (water.mesh.positions[:, :2] + np.asarray([137.0, -42.0])) / PATTERN_TILE_CM
    assert np.allclose(uvs, expected)  # the cap's own rule, the anchor included


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


def test_a_lawn_the_user_gave_a_height_is_a_solid_that_still_grows_its_blades() -> None:
    """#627's manual pass: a raised lawn was a flat textured slab - its blades are
    what made the ground lawn read as grass. The solid is the default one (tinted
    sides, fill cap) and the sward rides its new top."""
    record = polygon_record("LAWN", rectangle(800.0, 600.0), 20.0)
    parts = REGISTRY.build(record)
    sides, cap, blades = parts
    assert (sides.name, cap.name, blades.name) == ("lawn_sides", "lawn", "lawn_blades")
    assert cap.fill_texture and sides.tinted and blades.fill_texture is False
    assert 20.0 <= float(blades.mesh.positions[:, 2].min()) < 21.0  # rooted on the new top
    assert float(blades.mesh.positions[:, 2].max()) > 20.0
    assert blades.ground_detail and not blades.casts_shadow


def test_a_lawn_s_blades_are_remembered_by_its_own_geometry() -> None:
    surfaces.clear_lawn_cache()
    REGISTRY.build(lawn())
    REGISTRY.build(lawn({"lawn_cutouts": (((-10.0, -10.0), (10.0, -10.0), (0.0, 10.0)),)}))
    info = surfaces.sward_cache_info()
    assert info["misses"] == 1 and info["hits"] == 1  # the cut-out re-masks the same sward
    assert 0 < info["bytes"] <= surfaces.SWARD_CACHE_BYTES
    surfaces.clear_lawn_cache()
    assert surfaces.sward_cache_info() == {"hits": 0, "misses": 0, "entries": 0, "bytes": 0}


# ── a flower meadow (#940): a lawn whose fill pattern is WILDFLOWER ──────────


def meadow(params=None, ring=None, height=None):
    return polygon_record("LAWN", ring if ring is not None else rectangle(800.0, 600.0), height,
                          params={"seed": "meadow", "surface_pattern": surfaces.MEADOW_PATTERN, **(params or {})})


def _heads(part) -> np.ndarray:  # noqa: ANN001 - a MeshPart
    """Each head's vertices: its polygon's corners, then its eye's."""
    return part.mesh.positions.astype(np.float64).reshape(-1, surfaces.HEAD_VERTICES, 3)


def _rims(heads: np.ndarray) -> np.ndarray:
    return heads[:, :surfaces.HEAD_PETALS]


def test_a_wildflower_lawn_is_a_meadow_of_taller_blades_and_flower_heads() -> None:
    blades, flowers = verify_builder(REGISTRY.builder_for("LAWN"), meadow(), plan_margin_cm=10.0)
    for part in (blades, flowers):  # the same name: the engine shows both from High, sways and lights both
        assert (part.material_kind, part.name) == ("grass", surfaces.LAWN_BLADES)
        assert part.ground_detail and not part.casts_shadow and not part.fill_texture
    assert blades.tinted and not flowers.tinted  # the heads carry their own colours
    # the plan's blade density, the same as a lawn's — one in MEADOW_FLOWER_EVERY a stem
    count = blades.mesh.triangle_count // 3
    assert 0.8 * 220.0 * 48.0 <= count <= 1.2 * 220.0 * 48.0
    heads = _heads(flowers)
    assert len(heads) == pytest.approx(count / surfaces.MEADOW_FLOWER_EVERY, rel=0.15)
    assert flowers.mesh.triangle_count == surfaces.HEAD_TRIANGLES * len(heads)
    # taller: a lawn's blades end below 10 cm, a meadow's stand about 24 cm, up to its top
    tips = blades.mesh.positions.astype(np.float64).reshape(-1, 5, 3)[:, 4, 2]
    lawn_top = max(float(part.mesh.positions[:, 2].max()) for part in REGISTRY.build(lawn()))
    assert lawn_top < 10.0 and 20.0 < float(np.median(tips)) < 28.0
    assert float(heads[:, :, 2].max()) <= surfaces.MEADOW_TOP_CM
    # the heads stand over the grass, each on the tip of a stem
    assert float(np.median(_rims(heads).mean(axis=1)[:, 2])) > float(np.percentile(tips, 75))
    stem_tips = blades.mesh.positions.astype(np.float64).reshape(-1, 5, 3)[:, 4]
    centres = _rims(heads).mean(axis=1)    # the rim's middle is the stem's tip
    gap = np.linalg.norm(centres[:, None, :] - stem_tips[None, :, :], axis=2).min(axis=1)
    assert float(gap.max()) < 0.01
    # every vertex of a head sways with its stem: one uv a head; and one normal a head,
    # one colour a triangle (a far head is a sliver: nothing to extrapolate across it)
    uvs = flowers.mesh.uvs.reshape(len(heads), -1, 2)
    assert np.all(uvs == uvs[:, :1])
    normals = flowers.mesh.normals.reshape(len(heads), -1, 3)
    assert np.all(normals == normals[:, :1])
    corners = flowers.mesh.colors[flowers.mesh.indices]
    assert np.all(corners == corners[:, :1])
    # the eye stands over the dome's apex, inside the rim
    eye, middle = heads[:, surfaces.HEAD_PETALS:], centres[:, None, :]
    assert np.all(eye.mean(axis=1)[:, 2] > centres[:, 2] + 0.1)
    reach = np.linalg.norm(eye - middle, axis=2).max(axis=1)
    assert np.all(reach < np.linalg.norm(_rims(heads) - middle, axis=2).min(axis=1))


@pytest.mark.parametrize("drift", [0.0, surfaces.MEADOW_DRIFT])
def test_a_meadow_s_flowers_are_the_2d_sprites_colours_in_their_shares(
        drift: float, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without drifts every kind takes its share; with them (the default) a kind grows
    in patches, so a 20 x 15 m sample strays from the shares, but every kind is there."""
    monkeypatch.setattr(surfaces, "MEADOW_DRIFT", drift)
    surfaces.clear_lawn_cache()
    (_blades, flowers) = REGISTRY.build(meadow(ring=rectangle(2000.0, 1500.0)))
    surfaces.clear_lawn_cache()
    petals, centres = surfaces.flower_colours()
    colours = flowers.mesh.colors.astype(np.float64).reshape(-1, surfaces.HEAD_VERTICES, 4)[:, :, :3]
    rim, middle = colours[:, 1], colours[:, -1]   # a corner's petal colour, the eye's centre colour

    def kind_of(colour, table):  # the entry whose colour this is, times the head's brightness
        ratio = colour[:, None, :] / table[None, :, :]
        spread = ratio.max(axis=2) - ratio.min(axis=2)
        return spread.argmin(axis=1), spread.min(axis=1), ratio.mean(axis=2)[np.arange(len(colour)), spread.argmin(axis=1)]

    kind, spread, bright = kind_of(rim, petals)
    assert float(spread.max()) < 1e-4
    assert bright.min() >= 0.9 - 1e-6 and bright.max() <= 1.05 + 1e-6
    assert np.allclose(middle, centres[kind] * bright[:, None], atol=1e-5)  # its centre, the same entry
    shares = np.bincount(kind, minlength=len(surfaces.MEADOW_FLOWERS)) / len(kind)
    wanted = np.asarray([share for _key, share, _radius in surfaces.MEADOW_FLOWERS])
    assert np.allclose(shares, wanted / wanted.sum(), atol=0.025 if drift == 0.0 else 0.06)
    assert shares.min() > 0.04
    from open_garden_planner.core.plant_art import FLOWERS
    from open_garden_planner.core.scene3d.color import srgb_to_linear

    assert np.allclose(petals, [srgb_to_linear(FLOWERS[key][0]) for key, _s, _r in surfaces.MEADOW_FLOWERS])


def test_a_cut_out_takes_a_meadow_s_flowers_with_their_stems() -> None:
    cut = ((-200.0, -150.0), (200.0, -150.0), (200.0, 150.0), (-200.0, 150.0))  # a quarter
    whole = _heads(REGISTRY.build(meadow())[1])
    blades, flowers = REGISTRY.build(meadow({"lawn_cutouts": (cut,)}))
    heads = _heads(flowers)

    def under(points, margin):   # a stem's tip (its rim's middle) is at most STEM_REACH_CM off its root
        return (np.abs(points[:, 0]) < 200.0 + margin) & (np.abs(points[:, 1]) < 150.0 + margin)

    reach = surfaces.STEM_REACH_CM + 0.01
    assert not under(_rims(heads).mean(axis=1), -reach).any()
    tips = _rims(whole).mean(axis=1)
    # every head whose stem is surely outside stays, every one surely inside goes
    assert int((~under(tips, reach)).sum()) <= len(heads) <= int((~under(tips, -reach)).sum())
    assert len(heads) < len(whole)
    assert blades.tinted and not flowers.tinted


def test_a_raised_meadow_s_flowers_ride_its_top() -> None:
    sides, cap, blades, flowers = REGISTRY.build(meadow(height=20.0))
    assert (sides.name, cap.name) == ("lawn_sides", "lawn")
    assert 20.0 <= float(blades.mesh.positions[:, 2].min()) < 21.0
    assert float(flowers.mesh.positions[:, 2].min()) > 20.0 + surfaces.MEADOW_BLADE_CM


def test_a_meadow_without_a_share_of_the_plan_s_blades_grows_nothing() -> None:
    assert REGISTRY.build(meadow({"lawn_blades": 0})) == ()
    blades, flowers = REGISTRY.build(meadow({"lawn_blades": 600}))
    assert blades.mesh.triangle_count // 3 == pytest.approx(600, rel=0.1)
    assert len(_heads(flowers)) == pytest.approx(600 / surfaces.MEADOW_FLOWER_EVERY, rel=0.35)


@pytest.mark.parametrize("pattern", [None, "GRASS", "SOLID", "CLAY", "wildflower"])
def test_only_wildflower_makes_a_meadow_and_a_lawn_stays_the_lawn_it_was(pattern) -> None:
    """Every other lawn builds exactly what it built before #940 — the plain blades,
    array for array."""
    params = {} if pattern is None else {"surface_pattern": pattern}
    built = REGISTRY.build(lawn({"seed": "same", **params}))
    plain = REGISTRY.build(lawn({"seed": "same"}))
    assert len(built) == len(plain) == 1 and built[0] == plain[0]
    assert not surfaces.is_meadow(lawn(params))


@pytest.mark.parametrize("kind", ["TERRACE_PATIO", "DRIVEWAY"])
def test_another_surface_with_the_wildflower_pattern_is_no_meadow(kind) -> None:
    def build(pattern):
        return REGISTRY.build(polygon_record(kind, rectangle(500.0, 400.0), None,
                                             params={"seed": "t", "surface_pattern": pattern}))

    assert build(surfaces.MEADOW_PATTERN) == build("STONE")
    assert not surfaces.is_meadow(polygon_record(kind, rectangle(500.0, 400.0), None,
                                                 params={"surface_pattern": surfaces.MEADOW_PATTERN}))


def test_the_sward_memory_keeps_a_meadow_apart_from_a_lawn() -> None:
    surfaces.clear_lawn_cache()
    plain = REGISTRY.build(lawn({"seed": "s"}))
    flowered = REGISTRY.build(meadow({"seed": "s"}))
    assert surfaces.sward_cache_info()["misses"] == 2  # the same outline, seed and share: two swards
    assert REGISTRY.build(lawn({"seed": "s"})) == plain and REGISTRY.build(meadow({"seed": "s"})) == flowered
    info = surfaces.sward_cache_info()
    assert (info["hits"], info["entries"]) == (2, 2)
    assert info["bytes"] > surfaces._sward((rectangle(800.0, 600.0),), (), "s", None).nbytes
    surfaces.clear_lawn_cache()


def test_a_meadow_s_triangles_are_the_lawn_s_and_its_heads_at_most() -> None:
    """The budget: the same blades as a lawn of the same share (the plan's
    ``MAX_PLAN_BLADES`` bounds them), and a head on at most one blade in
    ``MEADOW_FLOWER_EVERY / (1 + MEADOW_RICHNESS)`` — measured: +18 to +24 % on 15 x 10 m."""
    ring = rectangle(1500.0, 1000.0)
    (plain,) = REGISTRY.build(lawn({"seed": "budget"}, ring=ring))
    blades, flowers = REGISTRY.build(meadow({"seed": "budget"}, ring=ring))
    assert blades.mesh.triangle_count == plain.mesh.triangle_count
    most = surfaces.HEAD_TRIANGLES * (plain.mesh.triangle_count // 3) * (1.0 + surfaces.MEADOW_RICHNESS) \
        / surfaces.MEADOW_FLOWER_EVERY
    assert flowers.mesh.triangle_count <= most
    assert blades.mesh.triangle_count + flowers.mesh.triangle_count <= 1.3 * plain.mesh.triangle_count


def test_two_meadows_are_no_clones() -> None:
    first, second = (REGISTRY.build(meadow({"seed": seed})) for seed in ("one", "two"))
    for a, b in zip(first, second, strict=True):
        assert a.mesh.positions.shape != b.mesh.positions.shape or not np.array_equal(a.mesh.positions, b.mesh.positions)


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
    assert {"door_wall", "hedge_leaves", "lawn_cutouts", "lawn_blades", "roof_style",
            "roof_pitch_deg", "roof_overhang_cm", "surface_pattern"} == BUILD_ONLY_PARAMS
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
