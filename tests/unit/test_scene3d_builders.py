"""The built-world builders (Phase 17 L1.6, #385 — gates G1, G2, G5, G6). Qt-free.

Every builder is a pure function ``Record -> tuple[MeshPart, ...]`` in the
item-local frame. ``verify_builder`` holds each to the seam's contract
(deterministic; reads only the geometry part; every mesh validates; top = the
resolved height). This file adds what a planning tool needs on top:

G1  over the whole matrix (``scene3d_builder_cases.CASES``: every kind x sizes x
    turned local geometry x with / without a height): the top is the height to
    the float32, the base is the ground, the fit scale is 1, the triangle budget
    holds, flat faces store their winding normal, every solid casts — with or
    without a height of the plan's (owner, L4 manual pass) — and the solid stays
    on its footprint.
G2  the roof's ridge line IS the record's ridge, run on to the roof's edge; the
    slope that faces the sun is the lit one.
G5  every vertex colour is a ``palette`` entry — or pure white on a tinted part.
G6  the same record gives the same mesh; two hedges are never clones.
"""

from __future__ import annotations

import dataclasses
import functools
import logging
import math

import numpy as np
import pytest

from open_garden_planner.core.object_height import (
    METADATA_KEY,
    SOIL_DROP_CM,
    soil_surface_cm,
    standing_base_cm,
)
from open_garden_planner.core.plant_art import PLANT_KINDS
from open_garden_planner.core.scene3d import (
    BuilderContractError,
    BuilderRegistry,
    Material,
    Mesh,
    MeshPart,
    Params,
    Record,
    RecordingSink,
    SceneSync,
    SunState,
    Transform,
    default_builder,
    normal_vs_winding,
    plan_overreach,
    prism_mesh,
    verify_builder,
)
from open_garden_planner.core.scene3d.builders import (
    BUILT_WORLD_KINDS,
    OBJECT_KINDS,
    SURFACE_KINDS,
    beds,
    buildings,
    fences,
    hedges,
    lines,
    palette,
    plants,
    production_registry,
    register,
    walls,
)
from open_garden_planner.core.scene3d.builders import triangle_budget as triangle_budget_of
from open_garden_planner.core.scene3d.builders.common import BuiltBuilder, nominal_height_cm
from open_garden_planner.core.scene3d.builders.primitives import (
    BEVEL_BEYOND,
    MITER_LIMIT,
    ccw_ring,
    offset_ring,
)
from open_garden_planner.core.scene3d.builders.roofs import bounding_box_ridge, gable_roof
from open_garden_planner.core.scene3d.color import srgb8_to_linear
from tests.unit.scene3d_builder_cases import (
    ACUTE_LOOP_PATH,
    ACUTE_RIDGE,
    ACUTE_TRIANGLE,
    BENT_PATH,
    CASES,
    CLOSED_PATH,
    HAIRPIN_PATH,
    L_RIDGE,
    L_SHAPE,
    LOOP,
    NEARLY_CLOSED_PATH,
    SLIVER_RIDGE,
    SLIVER_TRIANGLE,
    TRAPEZOID,
    U_RIDGE,
    U_SHAPE,
    ZIGZAG_PATH,
    Case,
    circle_record,
    corner_reach,
    covers,
    distance_to_path,
    line_record,
    outside_distance,
    path_length,
    plan_area,
    polygon_record,
    positions,
    rectangle,
    square_loop,
    triangle_count,
    turned,
    zigzag_path,
)

REGISTRY = production_registry()
#: A HOUSE's walls on every route (``buildings._house_walls``), as vertex colours.
HOUSE_WALL_LINEAR = np.asarray(buildings.HOUSE_WALL.linear, dtype=np.float32)
HEIGHT_TOLERANCE_CM = 0.5  # gate G1; every builder is in fact exact to the float32
#: How far a hedge leaf's tip may pass the footprint's outline. Measured over the matrix:
#: 4.9 cm where the core is drawn in by 4 cm; 8.8 cm on a hedge too narrow to draw in
#: (10 cm wide), where leaves root on the outline itself — bounded by the leaf length.
LEAF_OVERSHOOT_CM = 6.0


def assert_the_block(part: MeshPart, block: Mesh, kind: str) -> None:
    """``part`` is the plain block ``block``: its shape, in the item's fill (``tinted``) —
    a HOUSE's in its sandstone, whatever the route (``buildings._house_walls``)."""
    assert np.array_equal(part.mesh.positions, block.positions)
    assert np.array_equal(part.mesh.indices, block.indices)
    house = kind == "HOUSE"
    assert part.tinted is not house
    assert np.allclose(part.mesh.colors, block.colors * (HOUSE_WALL_LINEAR if house else 1.0))


@functools.cache
def built(record: Record) -> tuple[MeshPart, ...]:
    """The production builder's parts for a record — cached: builders are pure, and
    the matrix asks for the same record from several tests."""
    return REGISTRY.build(record)


def builder_of(record: Record) -> BuiltBuilder:
    builder = REGISTRY.builder_for(record.kind)
    assert isinstance(builder, BuiltBuilder)
    return builder


def line_reach_cm(record: Record) -> float:
    """The furthest a FENCE's or WALL's vertex may lie from its centre line — stated
    per solid, from the builders' own sections and the path's angles:

    - a swept section (wall, plain panel, hedge core) reaches its half width times the
      sharpest MITRED corner's ``1 / cos(half the turn)``; a corner whose mitre would be
      longer than ``BEVEL_BEYOND`` half widths is bevelled and stays at the half width;
    - a post fence reaches the half diagonal of its square posts, whatever the corner;
    - a hedge's leaves are rooted within the block's half width and are a leaf long.
    """
    closed = record.path[0] == record.path[-1]
    corner = corner_reach(record.path[:-1] if closed else record.path, closed=closed,
                          bevel_beyond=BEVEL_BEYOND)
    assert 1.0 <= corner <= BEVEL_BEYOND * (1.0 + 1e-6)
    stroke = record.path_width_cm or 0.0
    solid = lines.solid_of(record)
    if solid == "STONE_WALL":
        return (walls.body_thickness_cm(record) / 2.0 + walls.COPING_OVERSAIL_CM) * corner
    if solid == fences.PLAIN:
        return fences.plain_width_cm(record) / 2.0 * corner
    if solid == "HEDGE_FENCE":
        half = max(stroke, fences.HEDGE_THICKNESS_CM) / 2.0 - hedges.CORE_INSET_CM
        return half * corner + hedges.LEAF_LENGTH_CM
    post = {"WOODEN_FENCE": fences.POST_CM, "METAL_FENCE": fences.METAL_POST_CM,
            "CHAIN_LINK": fences.CHAIN_POST_CM}[solid]
    return max(stroke, post) / 2.0 * math.sqrt(2.0)


def budget_of(record: Record) -> int:
    height = record.height_cm or nominal_height_cm(record.kind) or 0.0
    if record.kind in ("HOUSE", "GARAGE_SHED", "TOOL_SHED"):
        return buildings.triangle_budget(record)
    if record.kind in ("FENCE", "WALL"):
        return lines.triangle_budget(record)
    if record.kind in ("HEDGE_SECTION", "HEDGE_POLYGON"):
        return hedges.triangle_budget(record)
    return beds.triangle_budget(record, height)


# ── registration ─────────────────────────────────────────────────────────────


class TestRegistration:
    """``production_registry()`` holds four families and nothing else: the built world
    (this story's ``register``), the L4 objects and surfaces (#388:
    ``register_objects``, ``register_surfaces``) and the plants (the plant story's
    ``plants.register``, wired in at the merge of 5c44578)."""

    def test_exactly_the_built_world_kinds_and_the_plant_kinds(self) -> None:
        assert frozenset({
            "HOUSE", "GARAGE_SHED", "TOOL_SHED", "FENCE", "WALL", "RAISED_BED", "CONTAINER",
            "WALL_PLANTER", "CONTAINER_ROUND", "GARDEN_BED", "HEDGE_SECTION", "HEDGE_POLYGON",
        }) == BUILT_WORLD_KINDS
        assert frozenset({"TREE", "SHRUB", "PERENNIAL"}) == PLANT_KINDS
        assert len(OBJECT_KINDS) == 24 and len(SURFACE_KINDS) == 5
        families = (BUILT_WORLD_KINDS, OBJECT_KINDS, SURFACE_KINDS, PLANT_KINDS)
        for index, family in enumerate(families):                      # no kind belongs to two
            for other in families[index + 1:]:
                assert not family & other
        everything = BUILT_WORLD_KINDS | OBJECT_KINDS | SURFACE_KINDS | PLANT_KINDS
        assert REGISTRY.kinds() == everything                           # … and nothing else is registered
        assert len(REGISTRY.kinds()) == sum(len(family) for family in families) == 44

    def test_every_plant_kind_resolves_to_the_plant_builder(self) -> None:
        for kind in sorted(PLANT_KINDS):
            assert REGISTRY.builder_for(kind) is plants.build_plant, kind

    def test_every_built_world_kind_resolves_to_its_own_builder(self) -> None:
        expected = {
            "HOUSE": buildings.build_house, "GARAGE_SHED": buildings.build_shed,
            "TOOL_SHED": buildings.build_shed, "FENCE": lines.build_fence, "WALL": lines.build_wall,
            "RAISED_BED": beds.build_raised_bed, "CONTAINER": beds.build_container,
            "WALL_PLANTER": beds.build_container, "CONTAINER_ROUND": beds.build_round_container,
            "GARDEN_BED": beds.build_garden_bed,
            "HEDGE_SECTION": hedges.build_hedge, "HEDGE_POLYGON": hedges.build_hedge,
        }
        assert set(expected) == BUILT_WORLD_KINDS
        for kind, builder in expected.items():
            assert REGISTRY.builder_for(kind) is builder, kind
            assert isinstance(builder, BuiltBuilder), kind      # every one of them a BuiltBuilder …
            assert builder is not plants.build_plant, kind      # … and none the plants'

    def test_the_built_world_alone_is_the_built_world(self) -> None:
        """``register`` stays this story's: without the plants the plant kinds fall to
        the default prism, as every other kind does."""
        registry = BuilderRegistry()
        register(registry)
        assert registry.kinds() == BUILT_WORLD_KINDS
        for kind in sorted(PLANT_KINDS):
            assert registry.builder_for(kind) is default_builder

    def test_every_registered_kind_is_a_real_object_type(self) -> None:
        from open_garden_planner.core.object_types import ObjectType

        assert {member.name for member in ObjectType} >= REGISTRY.kinds()

    def test_every_other_kind_falls_to_the_default(self) -> None:
        """Over the whole ``ObjectType`` enum, not a sample of it: a kind is built by
        the built world, by the plant builder, or by the default prism."""
        from open_garden_planner.core.object_types import ObjectType

        others = ({member.name for member in ObjectType} - BUILT_WORLD_KINDS - PLANT_KINDS
                  - OBJECT_KINDS - SURFACE_KINDS)
        assert others == {"ROOF_RIDGE", "GENERIC_RECTANGLE", "GENERIC_POLYGON", "GENERIC_CIRCLE",
                          "GENERIC_ELLIPSE", "GENERIC_TEXT", "GENERIC_CALLOUT", "GARDEN_JOURNAL_PIN"}
        for kind in sorted(others) + ["NO_SUCH_KIND"]:
            assert REGISTRY.builder_for(kind) is default_builder, kind

    def test_a_fresh_registry_every_time_and_no_kind_is_registered_twice(self) -> None:
        assert production_registry() is not production_registry()
        registry = BuilderRegistry()
        register(registry)
        with pytest.raises(ValueError, match="already registered"):
            register(registry)             # the built world twice
        plants.register(registry)          # the plants once: fine …
        with pytest.raises(ValueError, match="already registered"):
            plants.register(registry)      # … twice: refused
        from open_garden_planner.core.scene3d.builders import register_objects, register_surfaces

        register_objects(registry)
        register_surfaces(registry)
        with pytest.raises(ValueError, match="already registered"):
            register_objects(registry)     # the objects twice: refused
        # the registry refuses a second claim on a kind, so production_registry() could not
        # have been built if two families shared one
        assert registry.kinds() == production_registry().kinds()
        assert production_registry().version == (len(BUILT_WORLD_KINDS) + len(OBJECT_KINDS)
                                                 + len(SURFACE_KINDS) + len(PLANT_KINDS))

    def test_the_matrix_covers_every_registered_kind(self) -> None:
        assert {case.record.kind for case in CASES} == BUILT_WORLD_KINDS
        assert len(CASES) >= 286  # round 0's matrix; acute corners and unknown styles came on top
        assert len({case.name for case in CASES}) == len(CASES)


# ── gate G1 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", CASES, ids=str)
class TestGateG1:
    def test_contract_height_base_fit_budget(self, case: Case) -> None:
        record = case.record
        builder = builder_of(record)
        # deterministic, geometry-only, valid, top = height to gate G1's 0.5 cm, and — the
        # plan view — nothing over a closed line's hole, nothing far outside the footprint
        parts = verify_builder(builder, record, height_tolerance_cm=HEIGHT_TOLERANCE_CM)
        height = record.height_cm if record.height_cm is not None else nominal_height_cm(record.kind)
        if height is None:
            assert parts == ()  # an in-ground bed: ground, no solid
            return
        assert parts, "a kind with a height has a solid"
        points = positions(parts)
        top, bottom = float(points[:, 2].max()), float(points[:, 2].min())
        assert abs(top - height) <= HEIGHT_TOLERANCE_CM
        assert top == float(np.float32(height))  # by construction, not by a fit
        assert bottom == 0.0  # it stands on its own ground: nothing floats, nothing sinks
        assert builder.fit_scale(record) == pytest.approx(1.0, abs=1e-6)
        assert triangle_count(parts) <= budget_of(record)
        assert all(part.mesh.vertex_count for part in parts)  # no empty part reaches the sink

    def test_every_solid_casts(self, case: Case) -> None:
        """Built at the plan's height or the kind's nominal one, a solid casts in 3D
        (owner, L4 manual pass; the 2D sun study keeps its own caster rule)."""
        assert {part.casts_shadow for part in built(case.record)} <= {True}

    def test_every_face_looks_the_way_its_normal_does(self, case: Case) -> None:
        for part in built(case.record):
            dots, flat = normal_vs_winding(part.mesh)
            if part.material_kind == "foliage":
                # exempt from the rule by design (bent normals) — but a trimmed leaf is
                # moved whole, so in fact every leaf still looks the way it faces
                assert float(dots.min()) >= 0.99
                continue
            if flat.any():
                assert float(dots[flat].min()) >= 0.99  # the L0 "wrong roof slope" rule
            if (~flat).any():
                assert float(dots[~flat].min()) > 0.4  # smooth faces (pots, wires) face out too

    def test_the_solid_stays_on_its_footprint(self, case: Case) -> None:
        record = case.record
        parts = built(record)
        if not parts:
            return
        plan = positions(parts)[:, :2]
        if record.shape == "polyline":
            closed = record.path[0] == record.path[-1]
            line = record.path[:-1] if closed else record.path
            away = float(distance_to_path(plan, line, closed=closed).max())
            assert away <= line_reach_cm(record) + 1e-3
            return
        ring = record.footprints[0]
        overhang = {"HOUSE": buildings.HOUSE_ROOF.overhang_cm,
                    "GARAGE_SHED": buildings.SHED_ROOF.overhang_cm,
                    "TOOL_SHED": buildings.SHED_ROOF.overhang_cm}.get(record.kind, 0.0)
        if record.kind == "HOUSE" and "ridge" not in record.params:
            overhang = buildings.FLAT_ROOF.overhang_cm  # L4.1: a house without a ridge: flat
        if len(parts) == 1 and record.kind in ("HOUSE", "GARAGE_SHED", "TOOL_SHED"):
            overhang = 0.0  # a plain block
        if overhang:  # a roof: inside the footprint grown by the overhang, on its edge somewhere
            eaves = offset_ring(ring, overhang)
            assert outside_distance(plan, [tuple(p) for p in eaves]) <= 1e-3
            assert outside_distance(plan, ring) == pytest.approx(outside_distance(eaves, ring), abs=1e-3)
            # the stated bound: a mitre up to BEVEL_BEYOND overhangs, a bevel beyond — no spike
            assert outside_distance(plan, ring) <= BEVEL_BEYOND * overhang + 1e-3
        elif record.kind.startswith("HEDGE"):
            # leaves are rooted on a core drawn in by 4 cm; a tip may pass the outline
            inset = len(hedges.core_ring(ring)) and not np.allclose(hedges.core_ring(ring), ccw_ring(ring))
            assert outside_distance(plan, ring) <= (LEAF_OVERSHOOT_CM if inset else hedges.LEAF_LENGTH_CM)
        else:
            assert outside_distance(plan, ring) <= 1e-3  # beds and blocks: exactly the footprint


class TestHeightIsExactForAwkwardNumbers:
    @pytest.mark.parametrize("height", [0.75, 3.0, 17.3, 40.0, 100.1, 333.333, 1234.5])
    @pytest.mark.parametrize("make", [
        lambda h: polygon_record("HOUSE", rectangle(900.0, 540.0), h,
                                 params={"ridge": ((-450.0, 0.0), (450.0, 0.0))}),
        lambda h: polygon_record("GARAGE_SHED", rectangle(400.0, 300.0), h),
        lambda h: line_record("FENCE", BENT_PATH, h, style="WOODEN_FENCE"),
        lambda h: line_record("FENCE", BENT_PATH, h, style="METAL_FENCE"),
        lambda h: line_record("FENCE", BENT_PATH, h, style="CHAIN_LINK"),
        lambda h: line_record("FENCE", BENT_PATH, h, style="HEDGE_FENCE"),
        lambda h: line_record("WALL", BENT_PATH, h),
        lambda h: polygon_record("RAISED_BED", rectangle(300.0, 120.0), h),
        lambda h: polygon_record("CONTAINER", rectangle(80.0, 40.0), h),
        lambda h: circle_record("CONTAINER_ROUND", 25.0, h, params={"container_material": "terracotta"}),
        lambda h: circle_record("CONTAINER_ROUND", 25.0, h),
        lambda h: polygon_record("GARDEN_BED", TRAPEZOID, h),
        lambda h: polygon_record("HEDGE_POLYGON", L_SHAPE, h),
    ], ids=["house", "shed", "picket", "metal", "chain", "hedge-fence", "wall", "raised-bed",
            "container", "pot", "tub", "garden-bed", "hedge"])
    def test_top_is_the_float32_of_the_height(self, make, height: float) -> None:
        record = make(height)
        parts = verify_builder(REGISTRY.builder_for(record.kind), record)
        points = positions(parts)
        assert float(points[:, 2].max()) == float(np.float32(height))
        assert float(points[:, 2].min()) == 0.0
        assert builder_of(record).fit_scale(record) == pytest.approx(1.0, abs=1e-6)


# ── buildings: gate G2 ───────────────────────────────────────────────────────


def ridge_line_in_mesh(parts: tuple[MeshPart, ...], height: float) -> np.ndarray:
    """The plan points of the mesh's top line — the ridge tile's apex."""
    roof = next(part for part in parts if part.name == "roof")
    points = roof.mesh.positions.astype(np.float64)
    top = points[points[:, 2] == np.float32(height)][:, :2]
    return np.unique(np.round(top, 4), axis=0)


def expected_ridge(ridge: tuple[tuple[float, float], tuple[float, float]],
                   beyond: tuple[float, float]) -> np.ndarray:
    start, end = np.asarray(ridge[0]), np.asarray(ridge[1])
    along = (end - start) / np.linalg.norm(end - start)
    return np.stack([start - beyond[0] * along, end + beyond[1] * along])


class TestRidgeIsTheRecordsRidge:
    """Gate G2, in the item-local frame (the real items, turned and moved, are in
    ``tests/integration/test_scene3d_built_world.py``)."""

    @pytest.mark.parametrize("angle", [0.0, 17.0, 90.0, 213.5])
    @pytest.mark.parametrize(("name", "ring", "ridge"), [
        ("rectangle", rectangle(900.0, 540.0), ((-450.0, 0.0), (450.0, 0.0))),
        ("off-centre", rectangle(900.0, 540.0), ((-450.0, 120.0), (450.0, 120.0))),
        ("L", L_SHAPE, L_RIDGE),
        ("short-axis", rectangle(900.0, 540.0), ((0.0, -270.0), (0.0, 270.0))),
    ])
    def test_a_ridge_that_meets_its_walls_squarely_runs_30_cm_on(
        self, name: str, ring, ridge, angle: float
    ) -> None:
        local_ridge = turned(ridge, angle)
        record = polygon_record("HOUSE", turned(ring, angle), 450.0,
                                params={"ridge": (local_ridge[0], local_ridge[1])})
        line = ridge_line_in_mesh(built(record), 450.0)
        expected = expected_ridge((local_ridge[0], local_ridge[1]), (30.0, 30.0))
        assert len(line) == 2, name
        for point in expected:
            assert float(np.linalg.norm(line - point, axis=1).min()) <= 0.1  # the gate: 1 mm
            assert float(np.linalg.norm(line - point, axis=1).min()) <= 2e-3  # measured: float32

    def test_a_ridge_that_meets_a_wall_at_an_angle_runs_overhang_over_cos_theta_on(self) -> None:
        """A dragged ridge: from the middle of the west wall to a point 250 cm up the
        east wall. The roof overhangs each wall by 30 cm measured SQUARE to it, so the
        ridge reaches the roof's edge 30 / cos θ beyond its end."""
        ridge = ((-450.0, -100.0), (450.0, 150.0))
        record = polygon_record("HOUSE", rectangle(900.0, 540.0), 450.0, params={"ridge": ridge})
        cos_theta = 900.0 / math.hypot(900.0, 250.0)  # the ridge against the walls' normal (±x)
        line = ridge_line_in_mesh(built(record), 450.0)
        expected = expected_ridge(ridge, (30.0 / cos_theta, 30.0 / cos_theta))
        assert 30.0 / cos_theta == pytest.approx(31.136, abs=1e-3)
        for point in expected:
            assert float(np.linalg.norm(line - point, axis=1).min()) <= 0.1
        assert np.allclose(sorted(line[:, 0]), [-480.0, 480.0], atol=1e-3)  # on the roof's edges

    def test_the_ridge_tile_does_not_bridge_a_courtyard(self) -> None:
        """A U-shaped house: its canonical ridge runs wall to wall THROUGH the
        courtyard. The roof is two planes through that line over both wings; the
        ridge tile exists only where there is roof — its outer ends are the record's
        ridge ends run on by the overhang, its inner ends the courtyard's eaves."""
        record = polygon_record("HOUSE", U_SHAPE, 450.0, params={"ridge": U_RIDGE})
        line = ridge_line_in_mesh(built(record), 450.0)
        assert np.allclose(line[:, 1], 0.0, atol=1e-3)  # every apex point is ON the ridge line
        assert np.allclose(sorted(line[:, 0]), [-480.0, -220.0, 220.0, 480.0], atol=2e-3)
        roof = next(part for part in built(record) if part.name == "roof").mesh
        assert not covers([roof], 0.0, 100.0) and covers([roof], 350.0, 100.0)  # open courtyard

    def test_a_trapezoid(self) -> None:
        """Slanted end walls (the ridge meets them at atan(150 / 400))."""
        ridge = ((-325.0, 0.0), (325.0, 0.0))
        record = polygon_record("HOUSE", TRAPEZOID, 450.0, params={"ridge": ridge})
        cos_theta = math.cos(math.atan2(150.0, 400.0))
        line = ridge_line_in_mesh(built(record), 450.0)
        for point in expected_ridge(ridge, (30.0 / cos_theta, 30.0 / cos_theta)):
            assert float(np.linalg.norm(line - point, axis=1).min()) <= 0.1

    def test_the_ridge_changes_the_mesh(self) -> None:
        ring = rectangle(900.0, 540.0)
        centred = polygon_record("HOUSE", ring, 450.0, params={"ridge": ((-450.0, 0.0), (450.0, 0.0))})
        dragged = polygon_record("HOUSE", ring, 450.0, params={"ridge": ((-450.0, 90.0), (450.0, 0.0))})
        assert not centred.same_geometry(dragged)
        assert built(centred) != built(dragged)
        assert ridge_line_in_mesh(built(dragged), 450.0)[:, 1].max() > 80.0

    def test_wall_tops_meet_the_roof_s_underside(self) -> None:
        """No gap between a wall and the slab above it: gable ends rise to the ridge,
        eaves stay low, and every wall top lies exactly ``slab`` under the tiles."""
        style = buildings.HOUSE_ROOF
        roof = gable_roof(rectangle(900.0, 540.0), ((-450.0, 0.0), (450.0, 0.0)), 450.0, style)
        assert roof is not None
        walls_points = roof.walls.positions.astype(np.float64)
        crease = 450.0 - style.cap_rise_cm
        expected = crease - style.slab_cm - roof.slope * np.abs(walls_points[:, 1])
        tops = walls_points[:, 2] > 0.0
        assert np.allclose(walls_points[tops, 2], expected[tops], atol=1e-3)
        assert float(walls_points[:, 2].max()) == pytest.approx(crease - style.slab_cm, abs=1e-3)
        assert roof.eave_cm == pytest.approx(crease - style.slab_cm - roof.slope * 270.0, abs=1e-9)
        assert roof.slope == pytest.approx(math.tan(math.radians(38.0)))  # eaves at 222 cm: no clamp

    def test_a_low_or_deep_building_keeps_its_eaves_up(self) -> None:
        style = buildings.HOUSE_ROOF
        deep = gable_roof(rectangle(900.0, 1000.0), ((-450.0, 0.0), (450.0, 0.0)), 450.0, style)
        assert deep is not None and deep.eave_cm == 220.0
        assert deep.slope < math.tan(math.radians(38.0))
        low = gable_roof(rectangle(300.0, 200.0), ((-150.0, 0.0), (150.0, 0.0)), 150.0, style)
        assert low is not None and low.eave_cm == pytest.approx(0.75 * (150.0 - 5.0 - 12.0))

    def test_the_slope_the_sun_faces_is_the_lit_one(self) -> None:
        """The L0 bug: each roof slab stored the OTHER slope's normal. Here the ridge
        runs east-west; the south slope must look south and catch a southern sun."""
        record = polygon_record("HOUSE", rectangle(900.0, 540.0), 450.0,
                                params={"ridge": ((-450.0, 0.0), (450.0, 0.0))})
        roof = next(part for part in built(record) if part.name == "roof")
        assert roof.material_kind == "roof"
        mesh = roof.mesh
        tile = np.asarray(palette.ROOF_TILE.linear, dtype=np.float32)
        is_tile = np.isclose(mesh.colors, tile, atol=1e-6).all(axis=1)
        points, normals = mesh.positions[is_tile], mesh.normals[is_tile].astype(np.float64)
        assert (normals[:, 2] > 0.5).all()  # tiles look up
        south, north = points[:, 1] < -1.0, points[:, 1] > 1.0
        assert south.any() and north.any()
        assert (normals[south, 1] < -0.3).all() and (normals[north, 1] > 0.3).all()
        noon = np.asarray(SunState(35.0, 180.0).direction_scene)  # the sun in the south
        lit, shaded = normals[south] @ noon, normals[north] @ noon
        assert float(lit.min()) > float(shaded.max()) + 0.5
        assert float(lit.min()) > 0.9  # 38° pitch against a 35° sun: almost square on
        evening = np.asarray(SunState(20.0, 0.0).direction_scene)  # … and from the north
        assert float((normals[north] @ evening).min()) > float((normals[south] @ evening).max())

    def test_underside_and_fascia(self) -> None:
        record = polygon_record("HOUSE", rectangle(900.0, 540.0), 450.0,
                                params={"ridge": ((-450.0, 0.0), (450.0, 0.0))})
        mesh = next(part for part in built(record) if part.name == "roof").mesh
        timber = np.isclose(mesh.colors, np.asarray(palette.TIMBER.linear, np.float32),
                            atol=1e-6).all(axis=1)
        normals = mesh.normals[timber]
        assert (normals[:, 2] < 0.1).all()  # the underside looks down, the fascia sideways
        assert (normals[:, 2] < -0.5).any() and (np.abs(normals[:, 2]) < 1e-6).any()
        outline = mesh.positions[:, :2]
        assert float(np.abs(outline[:, 0]).max()) == pytest.approx(480.0, abs=1e-3)  # 30 cm overhang
        assert float(np.abs(outline[:, 1]).max()) == pytest.approx(300.0, abs=1e-3)

    def test_a_house_without_a_usable_ridge_is_a_plain_block(self) -> None:
        """A ridge that is there but cannot carry a roof is the honest block. A house with
        NO ridge — no param, or one that is not two points — gets a flat roof (L4.1: the
        automatic style; ``TestRoofStyles``)."""
        ring = rectangle(900.0, 540.0)
        block = default_builder(polygon_record("HOUSE", ring, 450.0))
        for params in ({"ridge": ((10.0, 0.0), (10.0, 0.0))},
                       {"ridge": ((2000.0, 0.0), (2000.0, 500.0))}):  # a line that misses the house
            parts = built(polygon_record("HOUSE", ring, 450.0, params=params))
            assert len(parts) == 1 and parts[0].name == "walls"
            assert_the_block(parts[0], block[0].mesh, "HOUSE")  # in its sandstone, never its fill
        for params in ({}, {"ridge": "nonsense"}, {"ridge": ((0.0, 0.0),)},
                       {"ridge": ((0.0, True), (1.0, 2.0))}):
            parts = built(polygon_record("HOUSE", ring, 450.0, params=params))
            assert [part.name for part in parts] == ["walls", "roof", "facade"], params
        too_low = built(polygon_record("HOUSE", ring, 15.0,
                                       params={"ridge": ((-450.0, 0.0), (450.0, 0.0))}))
        assert [part.name for part in too_low] == ["walls"]  # no room for a slab: a block

    def test_buildings_have_their_walls_and_a_roof_of_their_own_material(self) -> None:
        """A shed's walls take the item's fill colour; a house's are sandstone: its 2D
        fill is its roof's colour (owner, L4 manual pass)."""
        for record, tinted in (
            (polygon_record("HOUSE", rectangle(900.0, 540.0), 450.0,
                            params={"ridge": ((-450.0, 0.0), (450.0, 0.0))}), False),
            (polygon_record("GARAGE_SHED", rectangle(400.0, 300.0), 250.0), True),
            (polygon_record("TOOL_SHED", rectangle(200.0, 150.0), 250.0), True),
        ):
            walls_part, roof_part, facade_part = built(record)
            assert (walls_part.name, walls_part.material_kind, walls_part.tinted) == ("walls", "vc", tinted)
            assert (roof_part.name, roof_part.material_kind, roof_part.tinted) == ("roof", "roof", False)
            assert (facade_part.name, facade_part.material_kind, facade_part.tinted) == (
                "facade", "vc", False)


class TestShedRidge:
    """The spike derived a shed's ridge from its bounding box in the SCENE frame;
    in the item-local frame it is the building's own long axis, and turns with it."""

    @pytest.mark.parametrize(("ring", "expected"), [
        (rectangle(400.0, 300.0), ((-200.0, 0.0), (200.0, 0.0))),
        (rectangle(150.0, 200.0), ((0.0, -100.0), (0.0, 100.0))),
        (rectangle(300.0, 300.0), ((-150.0, 0.0), (150.0, 0.0))),   # a square: along x
        (((0.0, 0.0), (400.0, 0.0), (400.0, 100.0), (100.0, 100.0), (100.0, 300.0), (0.0, 300.0)),
         ((0.0, 150.0), (400.0, 150.0))),
    ])
    def test_long_axis_of_the_local_bounding_box(self, ring, expected) -> None:
        assert bounding_box_ridge(ring) == expected
        assert bounding_box_ridge(ring[:2]) is None

    @pytest.mark.parametrize("angle", [17.0, 90.0, 213.5])
    def test_it_turns_with_a_footprint_drawn_at_an_angle(self, angle: float) -> None:
        """A shed drawn as a turned polygon: the ridge is parallel to its long walls,
        not to the axes of its frame (the plain bounding box would lay it askew)."""
        ring = turned(rectangle(400.0, 300.0), angle)
        start, end = bounding_box_ridge(ring)
        expected = sorted(turned(((-200.0, 0.0), (200.0, 0.0)), angle))
        assert np.allclose([start, end], expected, atol=1e-6)
        line = ridge_line_in_mesh(built(polygon_record("GARAGE_SHED", ring, 250.0)), 250.0)
        on_the_eaves = sorted(turned(((-220.0, 0.0), (220.0, 0.0)), angle))
        assert np.allclose(sorted(map(tuple, line)), on_the_eaves, atol=2e-3)

    def test_the_shed_s_ridge_tile_runs_along_it(self) -> None:
        record = polygon_record("GARAGE_SHED", rectangle(400.0, 300.0), 250.0)
        line = ridge_line_in_mesh(built(record), 250.0)
        overhang = buildings.SHED_ROOF.overhang_cm
        assert np.allclose(line, [[-200.0 - overhang, 0.0], [200.0 + overhang, 0.0]], atol=1e-3)
        deep = polygon_record("TOOL_SHED", rectangle(150.0, 200.0), 250.0)
        line = ridge_line_in_mesh(built(deep), 250.0)
        assert np.allclose(line, [[0.0, -100.0 - overhang], [0.0, 100.0 + overhang]], atol=1e-3)


# ── acute corners: bevelled, not spiked (review round 1, P2-10) ──────────────


class TestAcuteCorners:
    """A mitre at an interior angle φ is ``1 / sin(φ / 2)`` offsets long: 3.9 at 30°,
    5.8 at 20°. Round 0 only cut it at 4 offsets: a 116 cm eave spike on an
    acute-triangle house (30 cm overhang), a 76 cm spike of coping on a hairpin wall.
    A corner sharper than ``BEVEL_BEYOND`` (2 offsets, 60°) is cut flat, and the stated
    bound is: nothing further than ``BEVEL_BEYOND`` offsets outside the true outline —
    in fact one offset at every bevelled corner. For a swept LINE the bound assumes
    legs at least ``MITER_LIMIT`` offsets long
    (``test_legs_shorter_than_the_section_reach_up_to_the_inside_mitre``)."""

    @pytest.mark.parametrize(("ring", "ridge", "corner", "round_0_cm"), [
        (ACUTE_TRIANGLE, ACUTE_RIDGE, ACUTE_TRIANGLE[2], 115.9),     # 30°: 30 / sin 15°
        (SLIVER_TRIANGLE, SLIVER_RIDGE, SLIVER_TRIANGLE[1], 120.0),  # 20°: 172.8, cut at 4 x 30
    ], ids=["30-degree-apex", "20-degree-corner"])
    def test_an_acute_house_has_no_eave_spike(self, ring, ridge, corner, round_0_cm) -> None:
        overhang = buildings.HOUSE_ROOF.overhang_cm
        record = polygon_record("HOUSE", ring, 450.0, params={"ridge": ridge})
        parts = verify_builder(REGISTRY.builder_for("HOUSE"), record)
        assert [part.name for part in parts] == ["walls", "roof", "facade"]  # a real roof, not the block
        roof = positions([parts[1]])[:, :2]
        walls_plan = positions([parts[0]])[:, :2]
        assert outside_distance(walls_plan, ring) <= 1e-3  # the walls stand on the footprint
        beyond = outside_distance(roof, ring)
        assert beyond <= BEVEL_BEYOND * overhang + 1e-3 < round_0_cm
        # at the acute corner itself the roof ends ONE overhang out — the bevel's two points —
        # where round 0 put its tip `round_0_cm` out
        from_corner = np.linalg.norm(roof - np.asarray(corner), axis=1)
        overhanging = np.array([outside_distance(point[None, :], ring) > 1e-6 for point in roof])
        around = from_corner[overhanging & (from_corner < round_0_cm + 1.0)]
        assert float(around.max()) == pytest.approx(overhang, abs=1e-3)
        # every eave is still a full overhang out: the roof covers the footprint grown by it
        eaves = offset_ring(ring, overhang)
        assert len(eaves) == len(ring) + 1  # the acute corner became two points
        assert outside_distance(roof, [tuple(p) for p in eaves]) <= 1e-3
        following = np.roll(eaves, -1, axis=0)
        eaves_area = float((eaves[:, 0] * following[:, 1] - following[:, 0] * eaves[:, 1]).sum()) / 2.0
        assert plan_area([parts[1].mesh]) == pytest.approx(eaves_area, rel=1e-4)

    @pytest.mark.parametrize(("kind", "style", "half_cm", "round_0_cm"), [
        ("WALL", None, 19.0, 76.0),            # body 15 + coping 4; round 0: 4 x 19
        ("FENCE", "STONE_WALL", 19.0, 76.0),
        ("FENCE", "BAMBOO_FENCE", 1.5, 6.0),   # the plain panel: a 3 cm stroke
        ("FENCE", "HEDGE_FENCE", 16.0, 64.0),  # the hedge's core
    ], ids=["wall", "stone-wall-fence", "plain-panel", "hedge-fence-core"])
    @pytest.mark.parametrize("path", [HAIRPIN_PATH, ZIGZAG_PATH, ACUTE_LOOP_PATH],
                             ids=["hairpin-174", "zigzag-150", "loop-30"])
    def test_a_hairpin_line_has_no_spike(self, kind, style, half_cm, round_0_cm, path) -> None:
        record = line_record(kind, path, 120.0, style=style)
        parts = verify_builder(REGISTRY.builder_for(kind), record)
        closed = path[0] == path[-1]
        line = path[:-1] if closed else path
        solid = positions(parts) if style != "HEDGE_FENCE" else positions(parts)[:_core_vertices(parts)]
        away = float(distance_to_path(solid[:, :2], line, closed=closed).max())
        # the sharp bends are bevelled: one half width; the squarer ones mitred: up to two
        assert away <= half_cm * corner_reach(line, closed=closed, bevel_beyond=BEVEL_BEYOND) + 1e-3
        assert away <= BEVEL_BEYOND * half_cm + 1e-3 < round_0_cm
        if path is HAIRPIN_PATH:  # its one joint is bevelled: nothing past one half width
            assert away == pytest.approx(half_cm, abs=1e-3)

    @pytest.mark.parametrize(("kind", "style", "stroke", "half_cm", "turn_deg", "offsets"), [
        ("WALL", None, 4.0, 19.0, 150.0, 2.62),
        ("WALL", None, 4.0, 19.0, 165.0, 2.70),
        ("FENCE", "STONE_WALL", 5.0, 19.0, 150.0, 2.62),
        ("FENCE", "HEDGE_FENCE", 8.0, 16.0, 165.0, 2.46),
    ], ids=["wall-150", "wall-165", "stone-wall-fence-150", "hedge-fence-core-165"])
    def test_legs_shorter_than_the_section_reach_up_to_the_inside_mitre(
        self, kind: str, style: str | None, stroke: float, half_cm: float, turn_deg: float,
        offsets: float,
    ) -> None:
        """Review round 2, P2-5. "Nothing further than ``BEVEL_BEYOND`` offsets from the
        line" assumes legs at least as long as the inside mitre runs back along them —
        at most ``MITER_LIMIT`` offsets, 76 cm for a wall's 19 cm of coping. On the
        INSIDE of a sharp bend the two inner edges' true intersection is kept; with
        25 cm legs under a 38 cm section it lies beyond the leg's other end, so the
        nearest point of the line is further away than one offset. The real bound is
        the mitre's own length: ``MITER_LIMIT`` offsets. (A wall drawn with legs
        shorter than it is thick overlaps itself — the plan describes no such wall.)"""
        path = zigzag_path(25.0, turn_deg)
        record = line_record(kind, path, 120.0, width=stroke, style=style)
        parts = verify_builder(REGISTRY.builder_for(kind), record, height_tolerance_cm=0.5,
                               plan_margin_cm=MITER_LIMIT * half_cm)
        solid = positions(parts) if style != "HEDGE_FENCE" else positions(parts)[:_core_vertices(parts)]
        away = float(distance_to_path(solid[:, :2], path).max())
        assert away == pytest.approx(offsets * half_cm, abs=0.01 * half_cm)  # measured, pinned
        assert BEVEL_BEYOND * half_cm < away <= MITER_LIMIT * half_cm + 1e-3
        # the same zigzag with legs of MITER_LIMIT offsets is inside the stated bound again
        long_path = zigzag_path(MITER_LIMIT * half_cm, turn_deg)
        long_parts = REGISTRY.build(line_record(kind, long_path, 120.0, width=stroke, style=style))
        long_solid = (positions(long_parts) if style != "HEDGE_FENCE"
                      else positions(long_parts)[:_core_vertices(long_parts)])
        assert float(distance_to_path(long_solid[:, :2], long_path).max()) <= half_cm + 1e-3

    @pytest.mark.parametrize("ring", [ACUTE_TRIANGLE, SLIVER_TRIANGLE], ids=["30-degrees", "20-degrees"])
    def test_an_acute_bed_and_hedge_stay_on_their_footprint(self, ring) -> None:
        bed = verify_builder(REGISTRY.builder_for("RAISED_BED"), polygon_record("RAISED_BED", ring, 40.0))
        assert outside_distance(positions(bed)[:, :2], ring) <= 1e-3
        assert soil_level(bed) == 38.0
        hedge = verify_builder(REGISTRY.builder_for("HEDGE_POLYGON"),
                               polygon_record("HEDGE_POLYGON", ring, 150.0))
        assert outside_distance(positions(hedge)[:, :2], ring) <= hedges.LEAF_LENGTH_CM


def _core_vertices(parts: tuple[MeshPart, ...]) -> int:
    """A hedge is one mesh, core first: its leaves are quads with a wind weight in uv."""
    uvs = parts[0].mesh.uvs
    leaf = np.nonzero((uvs[:, 0] > 0.0) | (uvs[:, 1] > 0.0))[0]
    return int(leaf[0]) if len(leaf) else len(uvs)


# ── polylines: built from the centre line, never from the stroke polygon ─────


FENCE_STYLES = ["WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK", "HEDGE_FENCE", "STONE_WALL"]


class TestPolylinesAreBuiltFromTheCentreLine:
    def test_a_closed_line_s_record_is_an_outer_ring_and_a_hole(self) -> None:
        """What the contract hands a builder for a fence round a garden (L1.1's fix):
        ``footprints`` is the stroke's OUTER ring, the garden is its hole in ``holes``.
        The outer ring alone would lid the garden — so no builder may read it as the
        fence's shape — and the record's own region is the 3 cm line weight, not a
        fence. (Before the fix the hole ring sat in ``footprints`` as if it were a
        solid, and the default builder laid a slab over all 48 m².)"""
        record = line_record("FENCE", CLOSED_PATH, 120.0)
        assert len(record.footprints) == 1 and len(record.holes) == 1 and len(record.holes[0]) == 1
        lid = prism_mesh(record.footprints, 120.0)  # the trap: the outer ring taken for the shape
        assert covers([lid], 37.0, 11.0) and plan_area([lid]) == pytest.approx(803.0 * 603.0, rel=1e-3)
        strip = [part.mesh for part in default_builder(record)]  # the honest default: outer minus hole
        assert not covers(strip, 37.0, 11.0)
        assert plan_area(strip) == pytest.approx(record.plan_area_cm2, rel=1e-6)
        assert record.plan_area_cm2 == pytest.approx(path_length(CLOSED_PATH) * 3.0, rel=1e-3)

    @pytest.mark.parametrize("kind", ["FENCE", "WALL"])
    @pytest.mark.parametrize("style", [None, *("WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK",
                                               "HEDGE_FENCE", "STONE_WALL", "GRAVEL_PATH")])
    @pytest.mark.parametrize(("path", "stroke"), [
        (CLOSED_PATH, 3.0),          # the last point is the first
        (NEARLY_CLOSED_PATH, 10.0),  # a 5 cm gap that a 10 cm stroke bridges: its outline closes
        (ACUTE_LOOP_PATH, 3.0),      # a loop with a 30° corner
    ], ids=["closed", "nearly-closed-wide-stroke", "acute-loop"])
    def test_nothing_is_built_over_the_hole(self, kind: str, style: str | None, path,
                                            stroke: float) -> None:
        """The plan-view gate of ``verify_builder`` (L1.1's fix), on every line solid:
        of the hole a closed line encloses, at most half may lie under the solid.
        Measured here against tighter, stated bounds: a post fence and a plain panel
        stand on the stroke and cover next to none of it; a wall or a hedge is wider
        than the stroke and covers the strip along the hole's edge — never the garden."""
        record = line_record(kind, path, 120.0, width=stroke, style=style)
        parts = verify_builder(REGISTRY.builder_for(kind), record, height_tolerance_cm=0.5)
        assert record.holes != ()
        beyond_cm2, hole_cover = plan_overreach(parts, record.regions, 50.0)
        assert beyond_cm2 == 0.0  # nothing further than 50 cm from the line's stroke
        wide = lines.solid_of(record) in ("STONE_WALL", "HEDGE_FENCE")
        assert hole_cover <= (0.3 if wide else 0.03), hole_cover

    @pytest.mark.parametrize(("kind", "style", "stroke", "reach_cm"), [
        ("WALL", None, 4.0, 19.0),             # body 15 + coping 4 either side of the line
        ("FENCE", "STONE_WALL", 5.0, 19.0),
        ("FENCE", "HEDGE_FENCE", 8.0, 20.0),   # the hedge's 40 cm thickness
    ], ids=["wall", "stone-wall-fence", "hedge-fence"])
    def test_a_small_closed_loop_of_a_thick_line_needs_an_explicit_hole_limit(
        self, kind: str, style: str | None, stroke: float, reach_cm: float
    ) -> None:
        """Review round 2, P2-3. ``verify_builder`` refuses a solid that covers more
        than half of a hole. That default fits a fence round a garden — and NOT a wall
        round a square metre: the wall's section reaches 19 cm either side of its line
        where the stroke reaches 2, so of the 96 cm hole a 1 m loop encloses, the solid
        covers a 17 cm strip all round — 58 % of it. The solid is right (such a wall
        leaves a 62 cm opening); the bound is for large loops. So a small loop is
        verified with the limit stated here — the strip the section reaches into, never
        the middle.

        The gate also has a size floor: a hole narrower than ``HOLE_MIN_WIDTH_CM``
        (10 cm) is not judged at all. That is the other end of the range — a 12 cm loop,
        whose wall is one solid block over an 8 cm "hole", passes the default.

        This test pins three sides and no range: 12 cm passes, stroke + 12 cm and 1 m
        are refused, 1.5 m passes. Where the default refuses in between was measured
        once, for square loops at 1 cm steps of the side (ADR-059, decision 5): a WALL
        15 – 120 cm, a stone-wall fence 16 – 118 cm, a hedge fence 19 – 111 cm and
        again at 114 cm — the gate samples the hole on a coarse grid."""
        side = 100.0
        record = line_record(kind, square_loop(side), 120.0, width=stroke, style=style)
        assert len(record.holes) == 1 and len(record.holes[0]) == 1
        builder = REGISTRY.builder_for(kind)
        with pytest.raises(BuilderContractError, match="hole"):
            verify_builder(builder, record, height_tolerance_cm=0.5)  # the default: half a hole
        parts = verify_builder(builder, record, height_tolerance_cm=0.5, hole_cover_limit=0.65)
        beyond_cm2, cover = plan_overreach(parts, record.regions, 50.0)
        assert beyond_cm2 == 0.0
        # the strip of the hole within the section's reach of the line: 1 - (inner / hole)²
        strip = 1.0 - ((side - 2.0 * reach_cm) / (side - stroke)) ** 2
        assert 0.5 < cover <= strip + 0.02 < 0.65
        meshes = [part.mesh for part in parts]
        for x, y in ((0.0, 0.0), (15.0, -15.0), (-18.0, 18.0)):
            assert not covers(meshes, x, y)  # the middle of the loop is open sky
        # from 1.5 m on the same loop is inside the default bound
        large = line_record(kind, square_loop(150.0), 120.0, width=stroke, style=style)
        verify_builder(builder, large, height_tolerance_cm=0.5)
        assert plan_overreach(REGISTRY.build(large), large.regions, 50.0)[1] < 0.5
        # … and below the gate's size floor a hole is not judged: a 12 cm loop of a thick
        # line is one block, its 4 – 8 cm hole reads 0.0, and the default passes it
        from open_garden_planner.core.scene3d.build import HOLE_MIN_WIDTH_CM

        assert HOLE_MIN_WIDTH_CM == 10.0
        tiny = line_record(kind, square_loop(12.0), 120.0, width=stroke, style=style)
        assert len(tiny.holes) == 1 and len(tiny.holes[0]) == 1
        tiny_parts = verify_builder(builder, tiny, height_tolerance_cm=0.5)
        assert plan_overreach(tiny_parts, tiny.regions, 50.0)[1] == 0.0
        # the first loop whose hole IS judged (12 cm wide and more) is refused again
        judged = line_record(kind, square_loop(stroke + 12.0), 120.0, width=stroke, style=style)
        with pytest.raises(BuilderContractError, match="hole"):
            verify_builder(builder, judged, height_tolerance_cm=0.5)

    def test_a_gap_wider_than_the_stroke_leaves_no_hole_in_the_record(self) -> None:
        """A 5 cm gap in a 3 cm stroke: the outline does not close, the record has no
        hole — and the garden is open all the same, because the fence is built from
        the centre line (``test_a_loop_encloses_nothing`` probes it)."""
        record = line_record("FENCE", NEARLY_CLOSED_PATH, 120.0)
        assert record.holes == () and len(record.footprints) == 1
        assert record.plan_area_cm2 == pytest.approx(path_length(NEARLY_CLOSED_PATH) * 3.0, rel=2e-3)

    def test_the_gate_refuses_a_slab_over_the_garden(self) -> None:
        """… and it IS a gate: a builder that takes the outer ring for the fence's
        shape is refused, with the top at exactly the right height."""
        def slab(record: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(record.footprints, record.height_cm or 0.0), "vc", name="slab"),)

        record = line_record("FENCE", CLOSED_PATH, 120.0)
        with pytest.raises(BuilderContractError, match="hole"):
            verify_builder(slab, record, height_tolerance_cm=0.5)

    @pytest.mark.parametrize("kind", ["FENCE", "WALL"])
    @pytest.mark.parametrize("style", [None, *FENCE_STYLES])
    @pytest.mark.parametrize("path", [CLOSED_PATH, NEARLY_CLOSED_PATH], ids=["closed", "nearly-closed"])
    def test_a_loop_encloses_nothing(self, kind: str, style: str | None, path) -> None:
        record = line_record(kind, path, 120.0, style=style)
        meshes = [part.mesh for part in built(record)]
        assert meshes
        for x, y in ((37.0, 11.0), (310.0, 180.0), (-290.0, -210.0), (20.0, 250.0)):
            assert not covers(meshes, x, y)  # the garden inside the fence is open sky
        ring = LOOP
        length = path_length([*ring, ring[0]])
        area = plan_area(meshes)
        assert area < 0.3 * 800.0 * 600.0  # a strip along 28 m of line, not the enclosed 48 m²
        solid = style == "STONE_WALL" or (kind == "WALL" and style is None)
        if solid:  # a wall is a solid strip: plan area = centre-line length x coping width
            width = walls.body_thickness_cm(record) + 2.0 * walls.COPING_OVERSAIL_CM
            if path is CLOSED_PATH:
                assert area == pytest.approx(length * width, rel=1e-4)
            else:  # 5 cm short of closed: the two flat ends overlap the first corner
                assert area == pytest.approx(length * width, rel=0.02)

    @pytest.mark.parametrize("style", FENCE_STYLES)
    def test_a_closed_line_and_its_open_twin_differ_only_at_the_seam(self, style: str) -> None:
        closed = built(line_record("FENCE", CLOSED_PATH, 120.0, style=style))
        nearly = built(line_record("FENCE", NEARLY_CLOSED_PATH, 120.0, style=style))
        assert triangle_count(closed) > 0 and triangle_count(nearly) > 0
        assert float(positions(closed)[:, 2].max()) == float(positions(nearly)[:, 2].max()) == 120.0

    def test_a_wall_s_plan_area_is_length_times_width(self) -> None:
        record = line_record("WALL", BENT_PATH, 200.0, width=4.0)
        (wall,) = built(record)
        assert (wall.name, wall.tinted, wall.material_kind) == ("wall", True, "vc")
        width = 30.0 + 2.0 * walls.COPING_OVERSAIL_CM  # a 4 cm stroke: the nominal 30 cm body
        assert plan_area([wall.mesh]) == pytest.approx(path_length(BENT_PATH) * width, rel=1e-4)
        wide = line_record("WALL", BENT_PATH, 200.0, width=45.0)  # a stroke wider than a wall: obeyed
        assert plan_area([built(wide)[0].mesh]) == pytest.approx(
            path_length(BENT_PATH) * (45.0 + 8.0), rel=1e-4)

    def test_wall_profile(self) -> None:
        (wall,) = built(line_record("WALL", ((-250.0, 0.0), (250.0, 0.0)), 200.0, width=4.0))
        points = wall.mesh.positions.astype(np.float64)
        assert float(np.abs(points[:, 1]).max()) == pytest.approx(19.0, abs=1e-4)  # coping: 15 + 4
        body = points[points[:, 2] < 191.9]
        assert float(np.abs(body[:, 1]).max()) == pytest.approx(15.0, abs=1e-4)
        # its anatomy, read off the faces: along the line it looks six ways — out to each
        # side (body and coping), up each chamfer, up from the top, down from the two
        # soffits — and it has two flat ends; the face on the ground is left out
        normals = {tuple(float(v) + 0.0 for v in n)
                   for n in np.round(wall.mesh.normals.astype(np.float64), 4)}
        ends = {n for n in normals if abs(n[0]) > 0.5}
        assert ends == {(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)}
        assert normals - ends == {
            (0.0, 1.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.7071, 0.7071), (0.0, -0.7071, 0.7071),
            (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)}
        assert float(points[np.isclose(wall.mesh.normals[:, 2], -1.0)][:, 2].min()) == 192.0
        assert wall.mesh.triangle_count <= lines.triangle_budget(
            line_record("WALL", ((-250.0, 0.0), (250.0, 0.0)), 200.0, width=4.0))

    def test_the_style_picks_the_fence(self) -> None:
        signatures = {}
        for style in [None, *FENCE_STYLES]:
            parts = built(line_record("FENCE", BENT_PATH, 120.0, style=style))
            signatures[style] = (tuple(p.name for p in parts), triangle_count(parts))
            assert all(part.tinted for part in parts)  # a fence is seen in its own stroke colour
        assert signatures[None] == signatures["WOODEN_FENCE"]  # a FENCE without a style: the default
        assert len({signatures[s] for s in FENCE_STYLES}) == len(FENCE_STYLES)  # five different fences
        assert signatures["HEDGE_FENCE"][0] == ("hedge",)
        assert signatures["STONE_WALL"][0] == ("wall",)

    def test_which_solid_each_kind_and_style_is_built_as(self) -> None:
        """The dispatch table of ``lines.py``, row by row."""
        def solid(kind: str, style: object) -> str:
            record = line_record(kind, BENT_PATH, 120.0)
            if style is not None:
                record = dataclasses.replace(record, params=Params({"seed": "s", "path_style": style}))
            return lines.solid_of(record)

        assert solid("FENCE", None) == "WOODEN_FENCE" == fences.DEFAULT_FENCE_STYLE
        assert solid("WALL", None) == "STONE_WALL"
        for style in FENCE_STYLES:  # a fence style is that style whatever the kind
            assert solid("FENCE", style) == solid("WALL", style) == style
        for unknown in ("GRAVEL_PATH", "DIRT_PATH", "BAMBOO_FENCE", "", "wooden_fence", 7, 2.5, True):
            assert solid("FENCE", unknown) == solid("WALL", unknown) == fences.PLAIN

    @pytest.mark.parametrize("kind", ["FENCE", "WALL"])
    @pytest.mark.parametrize("style", ["GRAVEL_PATH", "BAMBOO_FENCE", 7])
    def test_a_style_no_builder_knows_is_a_plain_panel_never_a_picket_fence(
        self, kind: str, style: object
    ) -> None:
        """Review round 1, P2-5. A path style on a fence, or a fence style added to the
        2D table after the builders were written, used to become a picket fence without
        a word. It is built as what the plan itself holds: the line, as wide as it is
        drawn, up to its height — the solid the 2D shadow model casts for it."""
        record = dataclasses.replace(
            line_record(kind, BENT_PATH, 120.0, width=6.0),
            params=Params({"seed": "item-1", "path_style": style}))
        (panel,) = verify_builder(REGISTRY.builder_for(kind), record)
        assert (panel.name, panel.tinted, panel.material_kind, panel.casts_shadow) == (
            "fence", True, "vc", True)
        picket = built(line_record("FENCE", BENT_PATH, 120.0, width=6.0, style="WOODEN_FENCE"))
        assert panel.mesh.triangle_count < 0.05 * triangle_count(picket)  # no pickets, no posts
        points = panel.mesh.positions.astype(np.float64)
        assert float(points[:, 2].max()) == 120.0 and float(points[:, 2].min()) == 0.0
        # exactly the stroke strip: 6 cm wide along the whole line, mitred at the two corners
        assert plan_area([panel.mesh]) == pytest.approx(path_length(BENT_PATH) * 6.0, rel=1e-4)
        assert float(distance_to_path(points[:, :2], BENT_PATH).max()) <= 3.0 * math.sqrt(2.0) + 1e-3
        # every face is vertical or the flat top: a panel, nothing else
        up = np.abs(panel.mesh.normals.astype(np.float64)[:, 2])
        assert set(np.round(up, 4)) <= {0.0, 1.0}
        assert panel.mesh.triangle_count <= lines.triangle_budget(record)

    def test_an_unknown_style_is_reported_once_per_name(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review round 2, P2-10. The plain panel is the honest fallback — and until
        now a silent one at run time. ONE warning per style name, not one per build:
        every edit of a plan rebuilds the items it touches, and forty fences in one
        unknown style would otherwise write forty lines per edit to the app's log."""
        monkeypatch.setattr(lines, "_reported_styles", set())

        def styled(kind: str, style: object, seed: str) -> Record:
            return dataclasses.replace(line_record(kind, BENT_PATH, 120.0, item_id=seed),
                                       params=Params({"seed": seed, "path_style": style}))

        logger = logging.getLogger(lines.__name__)
        assert logger.propagate and logger.name.startswith("open_garden_planner.")  # the app's log
        with caplog.at_level(logging.DEBUG, logger=lines.__name__):
            for turn in range(3):
                assert REGISTRY.build(styled("FENCE", "GRAVEL_PATH", f"a{turn}")) != ()
                assert REGISTRY.build(styled("WALL", "GRAVEL_PATH", f"b{turn}")) != ()
                assert REGISTRY.build(styled("FENCE", "BAMBOO_FENCE", f"c{turn}")) != ()
                for known in FENCE_STYLES:  # a style with a solid: nothing to report
                    REGISTRY.build(styled("FENCE", known, f"d{turn}"))
                REGISTRY.build(line_record("FENCE", BENT_PATH, 120.0, item_id=f"e{turn}"))  # no style
                REGISTRY.build(line_record("WALL", BENT_PATH, 120.0, item_id=f"f{turn}"))
        reported = [record for record in caplog.records if record.name == lines.__name__]
        assert [record.levelno for record in reported] == [logging.WARNING, logging.WARNING]
        first, second = (record.getMessage() for record in reported)
        assert "'GRAVEL_PATH'" in first and "FENCE" in first and "a0" in first  # where it was met
        assert "'BAMBOO_FENCE'" in second and "c0" in second
        assert "plain panel" in first and "plain panel" in second
        # asking what a line WOULD be built as reports nothing: only a build does
        monkeypatch.setattr(lines, "_reported_styles", set())
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger=lines.__name__):
            assert lines.solid_of(styled("FENCE", "GRAVEL_PATH", "g")) == fences.PLAIN
            assert lines.triangle_budget(styled("FENCE", "GRAVEL_PATH", "g")) > 0
        assert [record for record in caplog.records if record.name == lines.__name__] == []

    def test_the_memory_of_reported_styles_is_bounded(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hand-edited plan can name any style. The memory of names is bounded — and
        so is the LOG: once it is full nothing new is logged for the rest of the session,
        and one line says so. (Review round 3, P2-5: the first version started over when
        full, so a plan with 65 unknown names wrote 65 lines on EVERY rebuild pass — the
        policy ``ui/view3d/snapshot.py`` rejects for its own log.)"""
        monkeypatch.setattr(lines, "_reported_styles", set())
        names = lines.REPORTED_STYLES_MAX + 10
        with caplog.at_level(logging.WARNING, logger=lines.__name__):
            for rebuild_pass in range(3):  # every edit rebuilds: the same plan, three times
                for index in range(names):
                    record = dataclasses.replace(
                        line_record("FENCE", BENT_PATH, 120.0),
                        params=Params({"seed": "s", "path_style": f"STYLE_{index}"}))
                    assert REGISTRY.build(record) != ()  # built all the same, as a plain panel
                    assert len(lines._reported_styles) <= lines.REPORTED_STYLES_MAX + 1
                reported = [record for record in caplog.records if record.name == lines.__name__]
                # the first 64 names once each, then ONE line that says no more follow
                assert len(reported) == lines.REPORTED_STYLES_MAX + 1, rebuild_pass
        messages = [record.getMessage() for record in reported]
        assert all(f"'STYLE_{index}'" in messages[index] for index in range(lines.REPORTED_STYLES_MAX))
        assert "further" in messages[-1] and str(lines.REPORTED_STYLES_MAX) in messages[-1]
        assert "STYLE_" not in messages[-1]
        # a name that WAS reported stays silent; a known style never spoke
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=lines.__name__):
            REGISTRY.build(dataclasses.replace(
                line_record("FENCE", BENT_PATH, 120.0),
                params=Params({"seed": "s", "path_style": "STYLE_0"})))
            REGISTRY.build(line_record("FENCE", BENT_PATH, 120.0, style="WOODEN_FENCE"))
        assert [record for record in caplog.records if record.name == lines.__name__] == []

    def test_the_fence_builders_never_guess_a_style(self) -> None:
        record = line_record("FENCE", BENT_PATH, 120.0)
        line = np.asarray(BENT_PATH, dtype=np.float64)
        with pytest.raises(ValueError, match="no fence is built in the style 'BAMBOO_FENCE'"):
            fences.fence_parts(record, line, False, 120.0, "BAMBOO_FENCE")
        with pytest.raises(ValueError, match="STONE_WALL"):  # the wall belongs to walls.py
            fences.fence_parts(record, line, False, 120.0, "STONE_WALL")

    def test_a_fence_style_on_a_wall_builds_that_fence(self) -> None:
        for style in ("WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK", "HEDGE_FENCE"):
            as_wall = built(line_record("WALL", BENT_PATH, 120.0, style=style))
            as_fence = built(line_record("FENCE", BENT_PATH, 120.0, style=style))
            assert [p.mesh for p in as_wall] == [p.mesh for p in as_fence]
        stone = built(line_record("WALL", BENT_PATH, 120.0, style="STONE_WALL"))
        assert stone == built(line_record("WALL", BENT_PATH, 120.0)) != ()
        as_fence = built(line_record("FENCE", BENT_PATH, 120.0, width=4.0, style="STONE_WALL"))
        assert [p.mesh for p in as_fence] == [p.mesh for p in built(
            line_record("WALL", BENT_PATH, 120.0, width=4.0))]  # one wall, whoever asks

    def test_picket_fence_anatomy(self) -> None:
        """Posts are the top; pickets stop 0.3 … 4 cm under them (the L0 fence)."""
        (fence,) = built(line_record("FENCE", ((0.0, 0.0), (400.0, 0.0)), 120.0, style="WOODEN_FENCE"))
        points = fence.mesh.positions.astype(np.float64)
        at_top = points[points[:, 2] == 120.0]
        assert set(np.round(at_top[:, 0] / 200.0).astype(int)) == {0, 1, 2}  # a post every 2 m
        assert float(np.abs(at_top[:, 1]).max()) <= 4.5  # 9 cm posts
        tops = np.unique(np.round(points[:, 2], 3))
        picket_tops = tops[(tops > 110.0) & (tops < 120.0)]
        assert picket_tops.min() >= 116.0 - 1e-3 and picket_tops.max() <= 119.7 + 1e-3
        assert len(picket_tops) > 5  # no two neighbours level
        # 33 pickets on 4 m at a 12 cm pitch, each centred in its pitch
        low = points[np.isclose(points[:, 2], 2.0, atol=1e-3)]  # where the pickets start
        assert len(np.unique(np.floor(low[:, 0] / fences.PICKET_PITCH_CM).astype(int))) == 33
        assert fence.mesh.triangle_count <= lines.triangle_budget(
            line_record("FENCE", ((0.0, 0.0), (400.0, 0.0)), 120.0, style="WOODEN_FENCE"))

    def test_a_shared_corner_has_one_post(self) -> None:
        (bent,) = built(line_record("FENCE", ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0)), 120.0))
        tops = bent.mesh.positions[bent.mesh.positions[:, 2] == 120.0][:, :2].astype(np.float64)
        centres = {(round(float(x) / 100.0), round(float(y) / 100.0)) for x, y in tops}
        assert centres == {(0, 0), (1, 0), (1, 1)}  # three posts, not four: the corner has one
        (loop,) = built(line_record("FENCE", CLOSED_PATH, 120.0))
        loop_tops = loop.mesh.positions[loop.mesh.positions[:, 2] == 120.0][:, :2].astype(np.float64)
        posts = {(round(float(x) / 100.0), round(float(y) / 100.0)) for x, y in loop_tops}
        # 4 corners + 3 along each 8 m side + 2 along each 6 m side: one every 2 m, none twice
        assert len(posts) == 4 + 3 + 2 + 3 + 2

    @pytest.mark.parametrize("style", ["WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK"])
    def test_fifty_metres_of_fence_do_not_explode(self, style: str) -> None:
        record = line_record("FENCE", ((-2500.0, 0.0), (2500.0, 0.0)), 120.0, style=style)
        count = triangle_count(built(record))
        assert count <= lines.triangle_budget(record)
        per_metre = count / 50.0
        assert per_metre <= {"WOODEN_FENCE": 105.0, "METAL_FENCE": 100.0, "CHAIN_LINK": 60.0}[style]
        double = line_record("FENCE", ((-5000.0, 0.0), (5000.0, 0.0)), 120.0, style=style)
        assert triangle_count(built(double)) <= 2 * count + 100  # linear in the length

    def test_a_stroke_wider_than_a_post_widens_the_posts(self) -> None:
        (fence,) = built(line_record("FENCE", ((0.0, 0.0), (400.0, 0.0)), 120.0, width=20.0))
        assert float(np.abs(fence.mesh.positions[:, 1]).max()) == pytest.approx(10.0, abs=1e-4)

    def test_degenerate_lines(self) -> None:
        assert built(line_record("FENCE", ((0.0, 0.0), (0.0, 0.0)), 120.0)) == ()
        empty = dataclasses.replace(line_record("FENCE", BENT_PATH, 120.0), path=())
        assert built(empty) == ()
        assert built(dataclasses.replace(line_record("WALL", BENT_PATH, 200.0), path=())) == ()


# ── beds: the soil rule ──────────────────────────────────────────────────────


def soil_level(parts: tuple[MeshPart, ...]) -> float:
    soil = np.asarray(palette.SOIL.linear, dtype=np.float32)
    for part in parts:
        mesh = part.mesh
        is_soil = np.isclose(mesh.colors, soil, atol=1e-6).all(axis=1)
        if is_soil.any():
            levels = np.unique(mesh.positions[is_soil][:, 2])
            assert len(levels) == 1
            assert (mesh.normals[is_soil][:, 2] > 0.999).all()  # a flat bed of soil, looking up
            return float(levels[0])
    raise AssertionError("no soil")


class TestSoilRule:
    @pytest.mark.parametrize("height", [10.0, 30.0, 40.0, 75.0, 120.5])
    @pytest.mark.parametrize("make", [
        lambda h: polygon_record("RAISED_BED", rectangle(300.0, 120.0), h),
        lambda h: polygon_record("CONTAINER", rectangle(80.0, 40.0), h),
        lambda h: polygon_record("WALL_PLANTER", rectangle(120.0, 25.0), h),
        lambda h: circle_record("CONTAINER_ROUND", 25.0, h),
        lambda h: circle_record("CONTAINER_ROUND", 25.0, h, params={"container_material": "terracotta"}),
        lambda h: polygon_record("GARDEN_BED", TRAPEZOID, h),
    ], ids=["raised-bed", "container", "wall-planter", "tub", "pot", "garden-bed"])
    def test_the_soil_is_where_plants_stand(self, make, height: float) -> None:
        """Truth gate "Base": the mesh's soil and the plant's base are ONE function —
        2 cm under the rim of a bed, AT the height of a container (its fill height)."""
        record = make(height)
        parts = built(record)
        assert soil_level(parts) == float(np.float32(soil_surface_cm(record.kind, height)))
        assert soil_level(parts) == float(np.float32(standing_base_cm(record.kind, {
            "object_height_cm": height})))  # what a plant in it is given as its base
        is_bed = record.kind in ("RAISED_BED", "GARDEN_BED")
        assert soil_level(parts) == float(np.float32(height - SOIL_DROP_CM if is_bed else height))
        assert float(positions(parts)[:, 2].max()) == float(np.float32(height))  # the rim

    def test_a_container_has_no_lip_and_no_crack_at_its_soil(self) -> None:
        """Soil flush with the top (review round 1, P2-7): the frame's top runs straight
        into it — no inner face left hanging above nothing, nothing above the soil."""
        for record in (polygon_record("CONTAINER", rectangle(80.0, 40.0), 30.0),
                       circle_record("CONTAINER_ROUND", 25.0, 30.0),
                       circle_record("CONTAINER_ROUND", 25.0, 30.0,
                                     params={"container_material": "terracotta"})):
            walls_part, soil_part = built(record)
            assert float(soil_part.mesh.positions[:, 2].min()) == 30.0 == float(
                walls_part.mesh.positions[:, 2].max())
            soil_plan = soil_part.mesh.positions.astype(np.float64)[:, :2]
            top = walls_part.mesh.positions.astype(np.float64)
            top = top[top[:, 2] == 30.0][:, :2]
            # the soil's outline is the inner edge of the frame's top: every soil corner
            # coincides with a top vertex of the walls
            for corner in soil_plan:
                assert float(np.linalg.norm(top - corner, axis=1).min()) < 1e-3
            # and no wall face looks inward over the soil
            if record.shape != "circle":
                normals = walls_part.mesh.normals.astype(np.float64)
                centres = walls_part.mesh.positions.astype(np.float64)[walls_part.mesh.indices].mean(axis=1)
                inward = (normals[walls_part.mesh.indices[:, 0]][:, :2] * -centres[:, :2]).sum(axis=1)
                vertical = np.abs(normals[walls_part.mesh.indices[:, 0]][:, 2]) < 0.5
                assert not (vertical & (inward > 1e-6)).any()

    def test_a_rim_lower_than_the_drop_has_no_soil_face(self) -> None:
        parts = built(polygon_record("RAISED_BED", rectangle(300.0, 120.0), 1.5))
        assert soil_surface_cm("RAISED_BED", 1.5) == 0.0
        with pytest.raises(AssertionError, match="no soil"):
            soil_level(parts)

    def test_raised_bed_is_planks_and_soil_inside_the_footprint(self) -> None:
        (bed,) = built(polygon_record("RAISED_BED", rectangle(300.0, 120.0), 40.0))
        assert (bed.name, bed.material_kind, bed.tinted) == ("bed", "vc", False)
        points = bed.mesh.positions.astype(np.float64)
        assert float(np.abs(points[:, 0]).max()) == 150.0 and float(np.abs(points[:, 1]).max()) == 60.0
        soil = np.isclose(bed.mesh.colors, np.asarray(palette.SOIL.linear, np.float32),
                          atol=1e-6).all(axis=1)
        inner = points[soil]
        assert float(np.abs(inner[:, 0]).max()) == 145.0 and float(np.abs(inner[:, 1]).max()) == 55.0
        assert beds.plank_rows(40.0) == 3 and beds.plank_rows(90.0) == 6 and beds.plank_rows(5.0) == 1
        groove = np.isclose(bed.mesh.colors, np.asarray(palette.PLANK_GROOVE.linear, np.float32),
                            atol=1e-6).all(axis=1)
        assert set(np.round(points[groove][:, 2], 2)) >= {12.53, 13.33, 14.13, 25.87, 26.67, 27.47}

    def test_containers_are_tinted_walls_and_baked_soil(self) -> None:
        for record in (polygon_record("CONTAINER", rectangle(80.0, 40.0), 30.0),
                       circle_record("CONTAINER_ROUND", 25.0, 30.0),
                       polygon_record("GARDEN_BED", TRAPEZOID, 25.0)):
            walls_part, soil_part = built(record)
            assert (walls_part.name, walls_part.tinted) == ("walls", True)
            assert (soil_part.name, soil_part.tinted, soil_part.material_kind) == ("soil", False, "vc")

    def test_a_round_container_s_rim_is_the_plans_footprint(self) -> None:
        from open_garden_planner.core.shadow_geometry import circle_footprint

        for material in ("terracotta", "plastic"):
            record = circle_record("CONTAINER_ROUND", 25.0, 30.0, params={"container_material": material})
            walls_part, _soil = built(record)
            points = walls_part.mesh.positions.astype(np.float64)
            radius = np.hypot(points[:, 0], points[:, 1])
            assert float(radius.max()) == pytest.approx(25.0, abs=1e-4)  # nothing outside the footprint
            rim = points[np.isclose(radius, 25.0, atol=1e-3)]
            for corner in circle_footprint(0.0, 0.0, 25.0):  # the 2D shadow's own 24 vertices
                assert np.isclose(rim[:, :2], corner, atol=1e-4).all(axis=1).any()
        pot = built(circle_record("CONTAINER_ROUND", 25.0, 30.0,
                                  params={"container_material": "terracotta"}))[0].mesh
        tub = built(circle_record("CONTAINER_ROUND", 25.0, 30.0))[0].mesh
        foot = lambda mesh: float(np.hypot(*mesh.positions[mesh.positions[:, 2] == 0.0][:, :2].T).max())  # noqa: E731
        assert foot(pot) == pytest.approx(18.0, abs=1e-4) and foot(tub) == pytest.approx(21.5, abs=1e-4)

    def test_the_material_shapes_the_container_and_never_colours_it(self) -> None:
        meshes = {}
        for material in ("terracotta", "plastic", "wood", "metal", "unobtainium", None):
            params = {} if material is None else {"container_material": material}
            walls_part, _soil = built(polygon_record("CONTAINER", rectangle(80.0, 40.0), 30.0,
                                                     params=params))
            assert np.all(walls_part.mesh.colors == 1.0)
            meshes[material] = walls_part.mesh
        assert meshes["unobtainium"] == meshes[None] == meshes["plastic"] == meshes["metal"]
        assert meshes["wood"] != meshes["plastic"] != meshes["terracotta"]

    def test_an_in_ground_bed_is_ground(self) -> None:
        assert built(polygon_record("GARDEN_BED", TRAPEZOID, None)) == ()
        assert nominal_height_cm("GARDEN_BED") is None


# ── hedges: gate G6 ──────────────────────────────────────────────────────────


def hedge_anatomy(record: Record) -> tuple[MeshPart, np.ndarray, np.ndarray]:
    """A hedge's one part, and which of its vertices are the core's and the leaves'.
    The core carries uv (0, 0) — it does not sway; every leaf has a wind weight > 0."""
    (part,) = built(record)
    is_leaf = (part.mesh.uvs != 0.0).any(axis=1)
    return part, ~is_leaf, is_leaf


class TestHedges:
    def test_one_foliage_part_core_and_leaves(self) -> None:
        part, core, leaves = hedge_anatomy(polygon_record("HEDGE_SECTION", rectangle(200.0, 50.0), 150.0))
        assert (part.name, part.material_kind, part.tinted) == ("hedge", "foliage", False)
        z = part.mesh.positions[:, 2]
        assert core.any() and leaves.any()
        assert float(z[core].max()) == 147.0  # the core ends under the trimmed top
        assert float(z[leaves].max()) == 150.0  # the trimmed top IS the height
        assert float(z[leaves].min()) >= 0.0 and float(z[core].min()) == 0.0  # no leaf in the ground
        dark = np.asarray(palette.HEDGE_CORE.linear, dtype=np.float32)
        assert np.allclose(part.mesh.colors[core], dark, atol=1e-6)
        assert not np.isclose(part.mesh.colors[leaves], dark, atol=1e-6).all(axis=1).any()

    def test_the_top_is_trimmed(self) -> None:
        """Leaves that reached above the height were pushed down onto it, whole:
        many tips lie ON the trim line, and every leaf still looks the way it faces."""
        part, _core, leaves = hedge_anatomy(polygon_record("HEDGE_SECTION", rectangle(200.0, 50.0), 150.0))
        z = part.mesh.positions[leaves][:, 2].reshape(-1, 4)
        assert int((z.max(axis=1) == 150.0).sum()) > 50
        dots, flat = normal_vs_winding(part.mesh)
        assert flat.all() and float(dots.min()) > 0.999

    def test_leaf_count_follows_the_shell_area(self) -> None:
        assert hedges.leaf_count(3000.0) == 200 and hedges.leaf_count(30000.0) == 1000
        assert hedges.leaf_count(1e9) == hedges.MAX_LEAVES == 6000
        _part, _core, small = hedge_anatomy(polygon_record("HEDGE_SECTION", rectangle(100.0, 40.0), 60.0))
        _part, _core, large = hedge_anatomy(polygon_record("HEDGE_SECTION", rectangle(300.0, 60.0), 150.0))
        ring = hedges.core_ring(rectangle(100.0, 40.0))
        expected = hedges.leaf_count(hedges.shell_area_cm2(hedges.ring_shell(ring, 60.0)))
        assert int(small.sum()) == 4 * expected  # four vertices a leaf
        assert int(large.sum()) > int(small.sum())

    def test_wind_weights(self) -> None:
        part, core, leaves = hedge_anatomy(polygon_record("HEDGE_SECTION", rectangle(200.0, 50.0), 150.0))
        uv = part.mesh.uvs
        assert float(uv.min()) >= 0.0 and float(uv.max()) <= 1.0
        assert np.all(uv[core] == 0.0)  # the core stands still
        assert float(uv[leaves][:, 0].max()) > 0.95 and float(uv[leaves][:, 0].min()) < 0.1
        assert len(np.unique(uv[leaves][:, 1])) > 100  # a phase per leaf

    def test_the_same_hedge_is_the_same_mesh(self) -> None:
        record = polygon_record("HEDGE_POLYGON", L_SHAPE, 150.0, item_id="hedge-a")
        (first,), (second,) = REGISTRY.build(record), REGISTRY.build(record)  # two real builds
        assert float(np.abs(first.mesh.positions - second.mesh.positions).max()) <= 1e-6
        assert float(np.abs(first.mesh.colors - second.mesh.colors).max()) <= 1e-6
        assert float(np.abs(first.mesh.uvs - second.mesh.uvs).max()) <= 1e-6
        assert np.array_equal(first.mesh.indices, second.mesh.indices)

    def test_two_hedges_are_never_clones(self) -> None:
        """Same footprint, same height, another item: another hedge."""
        one, core, leaves = hedge_anatomy(polygon_record("HEDGE_POLYGON", L_SHAPE, 150.0, item_id="hedge-a"))
        two, _core, _leaves = hedge_anatomy(polygon_record("HEDGE_POLYGON", L_SHAPE, 150.0, item_id="hedge-b"))
        a, b = one.mesh.positions.astype(np.float64), two.mesh.positions.astype(np.float64)
        assert a.shape == b.shape
        assert np.array_equal(a[core], b[core])  # the core is the footprint: identical
        moved = np.linalg.norm(a[leaves] - b[leaves], axis=1) > 1.0
        assert float(moved.mean()) > 0.95  # practically every leaf sits elsewhere
        fence_one = built(line_record("FENCE", BENT_PATH, 120.0, style="HEDGE_FENCE", item_id="f-1"))
        fence_two = built(line_record("FENCE", BENT_PATH, 120.0, style="HEDGE_FENCE", item_id="f-2"))
        assert fence_one[0].mesh != fence_two[0].mesh

    def test_the_seed_is_the_record_s_param_and_nothing_else(self) -> None:
        record = polygon_record("HEDGE_POLYGON", L_SHAPE, 150.0, item_id="hedge-a")
        renamed = dataclasses.replace(record, item_id="another-id", name="Yew")
        assert built(renamed) == built(record)  # the id is not read: params["seed"] is
        reseeded = dataclasses.replace(record, params=Params({"seed": "hedge-z"}))
        assert built(reseeded)[0].mesh != built(record)[0].mesh

    def test_a_hedge_fence_is_tinted_and_as_thick_as_a_hedge(self) -> None:
        record = line_record("FENCE", ((-250.0, 0.0), (250.0, 0.0)), 120.0, width=8.0, style="HEDGE_FENCE")
        part, core, leaves = hedge_anatomy(record)
        assert part.tinted and part.material_kind == "foliage" and part.name == "hedge"
        assert np.all(part.mesh.colors == 1.0)
        across = np.abs(part.mesh.positions[:, 1])
        assert float(across[core].max()) == pytest.approx(16.0, abs=1e-4)  # 40 / 2 − 4
        assert float(across[leaves].max()) < 20.0 + 6.0


# ── gate G5: colours ─────────────────────────────────────────────────────────


def _srgb8(linear: np.ndarray) -> np.ndarray:
    value = np.clip(linear.astype(np.float64), 0.0, 1.0)
    encoded = np.where(value <= 0.0031308, value * 12.92, 1.055 * value ** (1.0 / 2.4) - 0.055)
    return np.round(encoded * 255.0)


PALETTE_SRGB = np.asarray([entry.srgb for entry in palette.ALL], dtype=np.float64)


@pytest.mark.parametrize("case", CASES, ids=str)
def test_every_vertex_colour_is_a_2d_table_entry(case: Case) -> None:
    """Gate G5. A tinted part is pure white — the sink multiplies it with the item's
    own colour. Every other vertex colour maps back (linear → sRGB, ± 1/255) to an
    entry of ``builders/palette.py``, whose entries are pinned to their 2D sources
    by ``test_scene3d_builders_palette.py``. No stray literal."""
    for part in built(case.record):
        colors = part.mesh.colors
        assert np.all(colors[:, 3] == 1.0)
        if part.tinted:
            assert np.all(colors == 1.0), f"{part.name}: a tinted part carries no colour of its own"
            continue
        unique = np.unique(colors[:, :3], axis=0)
        srgb = _srgb8(unique)
        nearest = np.abs(srgb[:, None, :] - PALETTE_SRGB[None, :, :]).max(axis=2).min(axis=1)
        assert float(nearest.max()) <= 1.0, f"{part.name}: {srgb[nearest.argmax()]} is in no 2D table"


def test_which_colours_each_kind_uses() -> None:
    def used(record: Record) -> set[str]:
        names: set[str] = set()
        for part in built(record):
            if part.tinted:
                names.add("TINT")
                continue
            for entry in palette.ALL:
                target = np.asarray(srgb8_to_linear(entry.rgba8), dtype=np.float32)
                if np.isclose(part.mesh.colors, target, atol=1e-6).all(axis=1).any():
                    names.add(entry.name)
        return names

    house = polygon_record("HOUSE", rectangle(900.0, 540.0), 450.0,
                           params={"ridge": ((-450.0, 0.0), (450.0, 0.0))})
    facade = {"STEEL_LIGHT", "GLASS_OCC", "STONE_LIGHT", "STONE", "BRASS"}  # L4.1: windows, a door
    assert used(house) == {"SANDSTONE", "ROOF_TILE", "ROOF_TILE_CAP", "TIMBER"} | facade
    assert used(polygon_record("TOOL_SHED", rectangle(200.0, 150.0), 250.0)) == {
        "TINT", "SHINGLE", "SHINGLE_CAP", "TIMBER"} | facade
    assert used(polygon_record("RAISED_BED", rectangle(300.0, 120.0), 40.0)) == {
        "PLANK", "PLANK_GROOVE", "SOIL"}
    assert used(circle_record("CONTAINER_ROUND", 25.0, 30.0)) == {"TINT", "SOIL"}
    assert used(line_record("FENCE", BENT_PATH, 120.0)) == {"TINT"}
    assert used(line_record("WALL", BENT_PATH, 200.0)) == {"TINT"}
    assert used(polygon_record("HEDGE_POLYGON", L_SHAPE, 150.0)) == {
        "HEDGE_CORE", "HEDGE_LEAF_0", "HEDGE_LEAF_1", "HEDGE_LEAF_2", "HEDGE_LEAF_3"}


# ── through the pipeline ─────────────────────────────────────────────────────


def test_the_whole_matrix_through_scene_sync_and_a_recording_sink() -> None:
    records = {}
    for index, case in enumerate(CASES):
        records[f"item-{index}"] = dataclasses.replace(case.record, item_id=f"item-{index}")
    sink = RecordingSink()
    sync = SceneSync(sink, production_registry(), validate=True)
    sync.apply(records)
    assert sync.failures == {} and sync.build_count == len(records)
    assert sink.item_ids() == tuple(records)
    sink.clear_calls()
    assert sync.apply(records).is_empty and sink.calls == []  # nothing changed: nothing built
    assert sync.build_count == len(records)


# ── records whose ground is not one plain ring ──────────────────────────────


BOW_TIE_LOBES = (((-301.0, -200.0), (-1.0, 0.0), (-301.0, 200.0)),      # two triangles a hair apart:
                 ((301.0, 200.0), (1.0, 0.0), (301.0, -200.0)))          # a bow-tie, resolved
HOLED_OUTER = rectangle(400.0, 300.0)
HOLED_HOLE = tuple(reversed(rectangle(200.0, 100.0)))                     # clockwise
POLYGON_KINDS = ["HOUSE", "GARAGE_SHED", "TOOL_SHED", "RAISED_BED", "CONTAINER", "WALL_PLANTER",
                 "CONTAINER_ROUND", "GARDEN_BED", "HEDGE_SECTION", "HEDGE_POLYGON"]


def lobes_record(kind: str, height: float | None, **params: object) -> Record:
    """TWO regions: what the snapshot can hand a builder for a polygon drawn crossing
    itself (its lobes as separate outer rings)."""
    return Record("lobes", kind, "polygon", BOW_TIE_LOBES, Transform(),
                  Material(kind, (200, 180, 140, 255)), height_cm=height,
                  params=Params({"seed": "lobes", **params}))


def holed_record(kind: str, height: float | None, **params: object) -> Record:
    """ONE region WITH A HOLE: the other thing a self-crossing polygon can resolve to."""
    return Record("holed", kind, "polygon", (HOLED_OUTER,), Transform(),
                  Material(kind, (200, 180, 140, 255)), height_cm=height,
                  params=Params({"seed": "holed", **params}), holes=((HOLED_HOLE,),))


NOT_ONE_RING = {"two-regions": lobes_record, "a-hole": holed_record}


class TestGroundThatIsNotOnePlainRing:
    """A builder that needs ONE simple outline — a gable roof, a bed's frame, a pot, a
    hedge — checks that it has one. A record with several regions, or with a hole, is
    built as the plain block of ALL its regions with the holes cut out; never on
    ``footprints[0]`` alone. So is a record the scene contract flags as RESOLVED
    (``params["outline_resolved"]``: a polygon drawn crossing or touching itself) —
    even when it is one plain ring: the ring count cannot tell such a drawing from an
    ordinary polygon, the flag can."""

    @pytest.mark.parametrize("make", NOT_ONE_RING.values(), ids=NOT_ONE_RING.keys())
    @pytest.mark.parametrize("kind", POLYGON_KINDS)
    def test_it_is_the_plain_block_of_all_regions(self, kind: str, make) -> None:
        params = {"ridge": ((-300.0, 0.0), (300.0, 0.0))} if kind == "HOUSE" else {}
        record = make(kind, 150.0, **params)
        builder = builder_of(record)
        assert builder.uses_the_plain_block(record)
        parts = verify_builder(builder, record, height_tolerance_cm=0.5, plan_margin_cm=0.0,
                               hole_cover_limit=0.0)  # nothing outside, nothing over a hole
        assert [part.name for part in parts] == ["prism"]
        assert_the_block(parts[0], default_builder(record)[0].mesh, kind)  # the default prism
        assert plan_area([parts[0].mesh]) == pytest.approx(record.plan_area_cm2, rel=1e-6)
        assert float(positions(parts)[:, 2].max()) == 150.0 and builder.fit_scale(record) == 1.0
        assert parts[0].casts_shadow
        if record.holes:
            assert not covers([parts[0].mesh], 37.0, 11.0)   # the hole stays open
        else:
            assert covers([parts[0].mesh], -200.0, 11.0) and covers([parts[0].mesh], 200.0, 11.0)
            assert not covers([parts[0].mesh], 0.0, 150.0)   # between the lobes: nothing

    @pytest.mark.parametrize("make", NOT_ONE_RING.values(), ids=NOT_ONE_RING.keys())
    @pytest.mark.parametrize(("kind", "nominal"), [("HOUSE", 450.0), ("RAISED_BED", 40.0),
                                                   ("HEDGE_POLYGON", 150.0), ("CONTAINER", 30.0)])
    def test_without_a_height_it_is_built_like_any_other(self, kind: str, nominal: float,
                                                          make) -> None:
        """The plain block of a record without a height: the kind's nominal height,
        casting like every built object (owner, L4 manual pass) — and nothing for a
        kind without one."""
        record = make(kind, None)
        parts = built(record)
        assert [part.name for part in parts] == ["prism"] and parts[0].casts_shadow
        assert float(positions(parts)[:, 2].max()) == nominal
        assert plan_area([parts[0].mesh]) == pytest.approx(record.plan_area_cm2, rel=1e-6)
        assert built(make("GARDEN_BED", None)) == ()

    @pytest.mark.parametrize("make", NOT_ONE_RING.values(), ids=NOT_ONE_RING.keys())
    @pytest.mark.parametrize(("kind", "height", "soil"), [("RAISED_BED", 40.0, 38.0),
                                                          ("GARDEN_BED", 25.0, 23.0),
                                                          ("CONTAINER", 30.0, 30.0)])
    def test_a_bed_built_as_the_plain_block_has_its_top_at_the_rim(
        self, kind: str, height: float, soil: float, make
    ) -> None:
        """Review round 2, P2-11 — a stated limit, pinned. "A plant is on its soil by
        construction" holds for the BED BUILDERS. A bed whose outline is not one plain
        ring is the plain block: no frame, no soil mesh, its top at the rim — so a
        plant on it (base = the soil rule's 38) stands ``SOIL_DROP_CM`` INSIDE the
        block. A container's soil is at its height, so there the two agree."""
        record = make(kind, height)
        parts = built(record)
        assert [part.name for part in parts] == ["prism"]
        assert float(positions(parts)[:, 2].max()) == height
        with pytest.raises(AssertionError, match="no soil"):
            soil_level(parts)
        assert soil_surface_cm(kind, height) == soil == standing_base_cm(kind, {METADATA_KEY: height})
        assert height - soil == (0.0 if kind == "CONTAINER" else SOIL_DROP_CM)

    @pytest.mark.parametrize("make", NOT_ONE_RING.values(), ids=NOT_ONE_RING.keys())
    def test_footprint_of_refuses_to_take_one_ring_for_the_whole(self, make) -> None:
        from open_garden_planner.core.scene3d.builders.common import (
            corner_count,
            footprint_of,
            has_one_plain_ring,
        )

        record = make("RAISED_BED", 40.0)
        assert not has_one_plain_ring(record)
        with pytest.raises(ValueError, match="not one plain ring"):
            footprint_of(record)
        assert corner_count(record) == sum(len(r) for r in record.footprints) + sum(
            len(h) for group in record.holes for h in group)
        plain = polygon_record("RAISED_BED", rectangle(300.0, 120.0), 40.0)
        assert has_one_plain_ring(plain) and footprint_of(plain) == plain.footprints[0]
        for kind in POLYGON_KINDS:  # and every family's budget still answers
            assert triangle_budget_of(make(kind, 40.0)) > 0

    @pytest.mark.parametrize("make", NOT_ONE_RING.values(), ids=NOT_ONE_RING.keys())
    def test_the_buildings_own_fallback_builds_every_region(self, make) -> None:
        """The house's plain block — its fallback for no ridge, a ridge off the building,
        a house too low — is the same function: called on ground that is not one ring it
        still builds all of it (round 0 extruded ``footprints[:1]``)."""
        record = make("HOUSE", 300.0, ridge=((-300.0, 0.0), (300.0, 0.0)))
        for shape in (buildings._house, buildings._shed, buildings._block):
            (walls_part,) = shape(record, 300.0)
            assert walls_part.name == "walls" and walls_part.tinted
            assert plan_area([walls_part.mesh]) == pytest.approx(record.plan_area_cm2, rel=1e-6)
            if record.holes:
                assert not covers([walls_part.mesh], 37.0, 11.0)

    @pytest.mark.parametrize("kind", POLYGON_KINDS)
    def test_a_resolved_outline_is_the_plain_block_even_when_it_is_one_ring(self, kind: str) -> None:
        """The contract flags a polygon drawn crossing or touching itself
        (``params["outline_resolved"]``, merge of 9944012). Its regions may be ONE plain
        ring — the ring count says nothing — and until the flag existed such a HOUSE kept
        a gable roof (round 1's open point). The flag alone makes it the plain block of
        its regions, for every polygon kind: a resolved ring can come within 0.002 cm of
        itself, and no frame, inset or overhang is offset from such an outline. The
        builder does not rely on the snapshot having dropped the ridge."""
        from open_garden_planner.core.scene3d import PARAM_OUTLINE_RESOLVED
        from open_garden_planner.core.scene3d.builders.common import (
            footprint_of,
            has_one_plain_ring,
        )

        ring = rectangle(600.0, 400.0)
        params = {"ridge": ((-300.0, 0.0), (300.0, 0.0))} if kind == "HOUSE" else {}
        plain = polygon_record(kind, ring, 150.0, params=params)
        flagged = polygon_record(kind, ring, 150.0, params={**params, PARAM_OUTLINE_RESOLVED: True})
        assert PARAM_OUTLINE_RESOLVED == "outline_resolved"
        assert flagged.footprints == plain.footprints and flagged.holes == () == plain.holes
        builder = builder_of(flagged)
        assert has_one_plain_ring(plain) and not has_one_plain_ring(flagged)
        assert not builder.uses_the_plain_block(plain) and builder.uses_the_plain_block(flagged)
        with pytest.raises(ValueError, match="resolved"):
            footprint_of(flagged)
        parts = verify_builder(builder, flagged, height_tolerance_cm=0.5, plan_margin_cm=0.0,
                               hole_cover_limit=0.0)
        assert [part.name for part in parts] == ["prism"]
        assert_the_block(parts[0], default_builder(flagged)[0].mesh, kind)
        assert float(positions(parts)[:, 2].max()) == 150.0 and builder.fit_scale(flagged) == 1.0
        # … where the very same ring WITHOUT the flag is built as its kind
        as_its_kind = built(plain)
        assert as_its_kind and [part.name for part in as_its_kind] != ["prism"]
        assert parts[0].mesh.triangle_count < triangle_count(as_its_kind)
        # a flag that is present and false is not a flag
        unflagged = polygon_record(kind, ring, 150.0, params={**params, PARAM_OUTLINE_RESOLVED: False})
        assert not builder.uses_the_plain_block(unflagged)

    @pytest.mark.parametrize("shape", ["_house", "_shed"])
    def test_a_building_s_own_shape_function_hangs_no_roof_on_a_resolved_outline(
        self, shape: str
    ) -> None:
        """… and the buildings check again themselves: called directly on a resolved
        one-ring record WITH a usable ridge, they build the block, not walls and a roof."""
        ring = rectangle(900.0, 540.0)
        ridge = ((-450.0, 0.0), (450.0, 0.0))
        plain = polygon_record("HOUSE", ring, 450.0, params={"ridge": ridge})
        flagged = polygon_record("HOUSE", ring, 450.0,
                                 params={"ridge": ridge, "outline_resolved": True})
        function = getattr(buildings, shape)
        assert [part.name for part in function(plain, 450.0)] == ["walls", "roof", "facade"]
        (block,) = function(flagged, 450.0)
        assert block.name == "walls" and block.mesh == default_builder(flagged)[0].mesh

    @pytest.mark.parametrize(("name", "record"), [
        ("a ridge without length", polygon_record("HOUSE", L_SHAPE, 450.0,
                                                  params={"ridge": ((10.0, 0.0), (10.0, 0.0))})),
        ("a ridge whose line misses the building", polygon_record(
            "HOUSE", L_SHAPE, 450.0, params={"ridge": ((-450.0, 900.0), (450.0, 900.0))})),
        ("a house too low for a roof slab", polygon_record(
            "HOUSE", L_SHAPE, 12.0, params={"ridge": L_RIDGE})),
    ], ids=lambda value: value if isinstance(value, str) else "")
    def test_every_plain_block_of_a_house_is_the_whole_footprint(self, name: str, record: Record) -> None:
        (walls_part,) = verify_builder(builder_of(record), record, height_tolerance_cm=0.5,
                                       plan_margin_cm=0.0)
        assert (walls_part.name, walls_part.material_kind) == ("walls", "vc")
        assert plan_area([walls_part.mesh]) == pytest.approx(record.plan_area_cm2, rel=1e-6), name
        assert_the_block(walls_part, default_builder(record)[0].mesh, "HOUSE")  # concave L and all

    def test_one_plain_ring_is_what_every_matrix_record_is(self) -> None:
        for case in CASES:
            if case.record.shape != "polyline":
                assert not builder_of(case.record).uses_the_plain_block(case.record), case.name
        closed = line_record("FENCE", CLOSED_PATH, 120.0)  # a line with a hole is still a line
        assert not builder_of(closed).uses_the_plain_block(closed)


def test_no_builder_uses_numpy_s_default_bit_generator() -> None:
    """``np.random.default_rng`` picks whatever bit generator numpy currently prefers;
    a change there would reshuffle every seeded hedge. The builders name theirs."""
    import ast
    from pathlib import Path

    package = Path(hedges.__file__).parent
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert "default_rng" not in names, path.name
        assert "RandomState" not in names and "seed" not in {
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "random"}, path.name
    source = (package / "hedges.py").read_text(encoding="utf-8")
    assert "np.random.Generator(np.random.PCG64(seed))" in source
