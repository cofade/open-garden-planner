"""The L4 object builders (Phase 17 L4.3 / L4.4, #388) — Qt-free.

Issue #388's truth gate for every builder: "decoration ≤ footprint + 10 cm; top =
resolved height". Held here over a matrix of sizes and heights for all 24 kinds of
``OBJECT_KINDS`` (``verify_builder`` with a 10 cm plan margin, the top to 1 %),
plus what the gate does not see: each object stands the way its 2D sprite is
drawn (the sprite's top edge is the item's local +y), an object the plan gives no
height is decoration that casts no shadow, glass and water cast none, every
colour is a 2D table's, and a footprint kilometres wide still makes a bounded mesh.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from open_garden_planner.core.object_height import DEFAULT_HEIGHTS_CM, effective_height_cm
from open_garden_planner.core.object_height_estimate import (
    ESTIMATED_HEIGHT_PARAM,
    ESTIMATED_OBJECT_HEIGHTS_CM,
    estimated_object_height_cm,
)
from open_garden_planner.core.scene3d import BuilderContractError, Record, verify_builder
from open_garden_planner.core.scene3d.builders import (
    OBJECT_KINDS,
    OBJECT_TRIANGLE_BUDGET,
    furniture,
    palette,
    play,
    production_registry,
    structures,
    triangle_budget,
    utility,
)
from open_garden_planner.core.scene3d.builders.common import BuiltBuilder
from open_garden_planner.core.scene3d.builders.kit import MAX_REPEATS, object_box
from open_garden_planner.core.scene3d.color import srgb8_to_linear
from tests.unit.scene3d_builder_cases import circle_record, polygon_record, rectangle, turned

REGISTRY = production_registry()

#: The kinds drawn with the circle tool (their footprint is a circle).
ROUND: dict[str, list[float]] = {
    "TABLE_ROUND": [50.0, 30.0, 80.0], "PARASOL": [150.0, 60.0, 220.0], "BBQ_GRILL": [40.0, 25.0, 60.0],
    "FIRE_PIT": [50.0, 30.0, 90.0], "PLANTER_POT": [25.0, 12.0, 50.0], "TRAMPOLINE": [150.0, 90.0, 220.0],
    "RAIN_BARREL": [30.0, 20.0, 45.0], "WATER_TAP": [10.0, 6.0, 15.0], "BIRD_BATH": [25.0, 15.0, 40.0],
}
#: The rectangle kinds, each with its sprite's own size first.
BOXED: dict[str, list[tuple[float, float]]] = {
    "TABLE_RECTANGULAR": [(150, 100), (60, 60), (300, 90)], "CHAIR": [(50, 50), (40, 60), (80, 80)],
    "BENCH": [(180, 60), (120, 45), (300, 70)], "LOUNGER": [(70, 190), (60, 160), (90, 220)],
    "PICNIC_TABLE": [(180, 150), (120, 120), (240, 180)], "SANDBOX": [(150, 150), (100, 80), (300, 200)],
    "HOT_TUB": [(220, 220), (180, 200), (300, 240)], "SWING": [(200, 150), (150, 120), (300, 200)],
    "HAMMOCK": [(300, 120), (250, 100), (400, 150)], "COMPOST_BIN": [(100, 100), (80, 120), (300, 100)],
    "COLD_FRAME": [(120, 60), (100, 80), (200, 100)], "WHEELBARROW": [(60, 140), (50, 120), (80, 160)],
    "PERGOLA": [(300, 300), (400, 250), (150, 150)], "TRELLIS": [(200, 20), (30, 200), (300, 60)],
    "GREENHOUSE": [(300, 200), (200, 300), (500, 300)],
}
HEIGHTS: list[float | None] = [None, 30.0, 75.0, 250.0]


def record_of(kind: str, size: object, height: float | None, *, angle: float = 0.0) -> Record:
    """A record as the snapshot makes it — with the illustrative height of a kind the
    2D resolver gives none (the snapshot writes it whenever the plan gives none)."""
    estimate = estimated_object_height_cm(kind)
    params = {ESTIMATED_HEIGHT_PARAM: estimate} if estimate is not None and height is None else {}
    if kind in ROUND:
        return circle_record(kind, float(size), height, params=params)  # type: ignore[arg-type]
    w, d = size  # type: ignore[misc]
    return polygon_record(kind, turned(rectangle(w, d), angle) if angle else rectangle(w, d), height,
                          shape="rectangle", params=params)


def matrix() -> list[tuple[str, object, float | None]]:
    cases = []
    for kind, sizes in {**ROUND, **BOXED}.items():
        for size in sizes:
            for height in HEIGHTS:
                cases.append((kind, size, height))
    return cases


def test_the_matrix_is_every_object_kind() -> None:
    assert set(ROUND) | set(BOXED) == OBJECT_KINDS
    assert len(OBJECT_KINDS) == 24
    assert set(furniture.KINDS) | set(play.KINDS) | set(utility.KINDS) | set(structures.KINDS) == OBJECT_KINDS


@pytest.mark.parametrize(("kind", "size", "height"), matrix(),
                         ids=lambda v: str(v) if not isinstance(v, tuple) else "x".join(map(str, v)))
def test_the_truth_gate_of_issue_388(kind: str, size: object, height: float | None) -> None:
    """Deterministic, geometry-only, valid meshes, the top at the resolved (or
    illustrative) height to 1 %, nothing more than 10 cm beyond the footprint, built
    TO the height (no fit), within the object budget, and something built."""
    record = record_of(kind, size, height)
    builder = REGISTRY.builder_for(kind)
    assert isinstance(builder, BuiltBuilder)
    parts = verify_builder(builder, record, plan_margin_cm=10.0)
    assert parts, "every object kind is built at every size"
    assert builder.fit_scale(record) == pytest.approx(1.0, abs=1e-6)
    top = max(float(part.mesh.positions[:, 2].max()) for part in parts)
    assert top == pytest.approx(builder.height_for(record), rel=1e-4)
    triangles = sum(part.mesh.triangle_count for part in parts)
    assert triangles <= OBJECT_TRIANGLE_BUDGET == triangle_budget(record)


def test_the_gate_catches_a_builder_that_reaches_too_far() -> None:
    """Positive control: the same footprint with a mesh grown 20 cm past it fails."""
    record = record_of("TABLE_RECTANGULAR", (150.0, 100.0), 75.0)

    def grown(rec: Record) -> tuple:
        parts = REGISTRY.build(rec)
        part = parts[0]
        positions = part.mesh.positions.astype(np.float64)
        positions[:, :2] *= 1.3
        from open_garden_planner.core.scene3d import Mesh

        mesh = Mesh.from_arrays(positions, part.mesh.normals, part.mesh.colors, part.mesh.uvs, part.mesh.indices)
        return (dataclasses.replace(part, mesh=mesh),)

    with pytest.raises(BuilderContractError, match="outside a footprint"):
        verify_builder(grown, record, plan_margin_cm=10.0)


# ── heights: the plan's, else the resolver's, else the illustrative one ─────────


def test_every_object_kind_has_a_height_to_be_built_at() -> None:
    """A kind the 2D resolver gives no height has an illustrative one, and the two
    tables never both answer (``core/object_height_estimate``)."""
    assert not set(ESTIMATED_OBJECT_HEIGHTS_CM) & set(DEFAULT_HEIGHTS_CM)
    for kind in sorted(OBJECT_KINDS):
        has_default = effective_height_cm(kind, None) is not None
        assert has_default != (estimated_object_height_cm(kind) is not None), kind
    from open_garden_planner.core.object_types import ObjectType

    assert set(ESTIMATED_OBJECT_HEIGHTS_CM) <= {member.name for member in ObjectType}


@pytest.mark.parametrize("kind", sorted(ESTIMATED_OBJECT_HEIGHTS_CM))
def test_an_object_the_plan_gives_no_height_is_decoration(kind: str) -> None:
    """Built at its illustrative height, and NO part casts a shadow — the 2D sun study
    casts none for it either. Given a height, the same object casts."""
    sizes = ROUND.get(kind) or BOXED[kind]
    decoration = REGISTRY.build(record_of(kind, sizes[0], None))
    assert decoration and not any(part.casts_shadow for part in decoration)
    top = max(float(part.mesh.positions[:, 2].max()) for part in decoration)
    assert top == pytest.approx(ESTIMATED_OBJECT_HEIGHTS_CM[kind], rel=1e-4)
    real = REGISTRY.build(record_of(kind, sizes[0], 120.0))
    assert any(part.casts_shadow for part in real)


def test_without_an_estimate_a_height_less_object_is_not_built() -> None:
    """A hand-made record of a height-less kind WITHOUT the snapshot's estimate has no
    height to be built at: no parts (``BuiltBuilder``'s rule, unchanged)."""
    record = circle_record("PARASOL", 150.0, None)
    assert REGISTRY.build(record) == ()


# ── glass and water ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(("kind", "size", "material"), [
    ("GREENHOUSE", (300.0, 200.0), "glass"), ("COLD_FRAME", (120.0, 60.0), "glass"),
    ("HOT_TUB", (220.0, 220.0), "water"), ("BIRD_BATH", 25.0, "water"),
])
def test_glass_and_water_cast_no_shadow(kind: str, size: object, material: str) -> None:
    parts = REGISTRY.build(record_of(kind, size, 150.0))
    special = [part for part in parts if part.material_kind == material]
    assert special and not any(part.casts_shadow for part in special)
    assert any(part.casts_shadow for part in parts if part.material_kind == "vc")


def test_the_greenhouse_glass_is_the_items_colour() -> None:
    """The 2D greenhouse is a GLASS fill in the item's colour: the 3D glass is tinted."""
    (glass,) = [part for part in REGISTRY.build(record_of("GREENHOUSE", (300.0, 200.0), 220.0))
                if part.material_kind == "glass"]
    assert glass.tinted and np.all(glass.mesh.colors == 1.0)


# ── the sprite's side up ─────────────────────────────────────────────────────


def _mesh_points(kind: str, size: object, height: float = 120.0) -> np.ndarray:
    parts = REGISTRY.build(record_of(kind, size, height))
    return np.concatenate([part.mesh.positions.astype(np.float64) for part in parts])


def _highest(points: np.ndarray, share: float = 0.97) -> np.ndarray:
    top = points[:, 2].max()
    selected: np.ndarray = points[points[:, 2] >= share * top]
    return selected


@pytest.mark.parametrize(("kind", "size"), [("CHAIR", (50.0, 50.0)), ("BENCH", (180.0, 60.0)),
                                            ("LOUNGER", (70.0, 190.0))])
def test_a_seat_s_back_is_on_the_sprite_s_top_edge(kind: str, size: tuple[float, float]) -> None:
    """The chair's back, the bench's backrest and the lounger's head end are drawn at
    the top of their sprites — the item's local +y — so the highest part is there."""
    points = _mesh_points(kind, size, 85.0)
    assert float(_highest(points)[:, 1].mean()) > 0.25 * size[1]


def test_a_wheelbarrow_s_wheel_is_at_the_sprite_s_top_and_its_handles_at_the_bottom() -> None:
    points = _mesh_points("WHEELBARROW", (60.0, 140.0), 60.0)
    low = points[points[:, 2] < 5.0]  # what touches the ground: the tyre and the legs
    assert float(low[:, 1].max()) > 40.0  # the wheel, near the top edge
    handles = points[(points[:, 1] < -40.0)]
    assert len(handles) and float(handles[:, 2].max()) > 30.0  # the grips, up at the bottom end


@pytest.mark.parametrize(("kind", "size", "low_z"), [
    ("BBQ_GRILL", 40.0, 30.0), ("RAIN_BARREL", 30.0, 0.0), ("WATER_TAP", 10.0, 40.0),
])
def test_a_round_object_s_side_part_points_to_the_sprite_s_right(kind: str, size: float, low_z: float) -> None:
    """The grill's shelf, the barrel's tap and spout and the tap's spout are on the
    sprite's right — the item's +x: the mesh reaches further east than west there."""
    points = _mesh_points(kind, size, 90.0)
    band = points[points[:, 2] >= low_z]
    assert float(band[:, 0].max()) > -float(band[:, 0].min()) + 0.05 * size


def test_a_cold_frame_is_high_at_the_back() -> None:
    """Hinges at the sprite's top edge: the back (+y) is the high side of the lid."""
    points = _mesh_points("COLD_FRAME", (120.0, 60.0), 45.0)
    back = points[points[:, 1] > 25.0]
    front = points[points[:, 1] < -25.0]
    assert float(back[:, 2].max()) == pytest.approx(45.0, rel=1e-4)
    assert float(front[:, 2].max()) < 0.75 * 45.0


# ── colours ──────────────────────────────────────────────────────────────────


PALETTE_LINEAR = np.array([srgb8_to_linear(entry.rgba8)[:3] for entry in palette.ALL])


@pytest.mark.parametrize("kind", sorted(OBJECT_KINDS))
def test_every_colour_is_a_2d_table_entry_or_a_shade_of_the_item_s(kind: str) -> None:
    """Untinted parts take every vertex colour from the palette (the sprites'
    ``MATERIALS``); tinted parts carry a grey shading weight of at most 1 that the
    sink multiplies with the item's own colour."""
    sizes = ROUND.get(kind) or BOXED[kind]
    for part in REGISTRY.build(record_of(kind, sizes[0], 150.0)):
        colors = part.mesh.colors.astype(np.float64)
        assert np.all(colors[:, 3] == 1.0)
        if part.tinted:
            assert np.allclose(colors[:, 0], colors[:, 1]) and np.allclose(colors[:, 1], colors[:, 2])
            assert float(colors[:, :3].max()) <= 1.0 + 1e-6
            continue
        distance = np.abs(colors[:, None, :3] - PALETTE_LINEAR[None, :, :]).max(axis=2).min(axis=1)
        assert float(distance.max()) < 1e-5, f"{part.name}: a colour in no 2D table"


# ── footprints that are not a box, and plans kilometres wide ─────────────────


def test_a_polygon_that_is_not_its_box_is_the_plain_block() -> None:
    """A table typed onto an L-shaped polygon: the object box cannot be honest about
    it, the plain block of its footprint is."""
    from open_garden_planner.core.scene3d import default_builder
    from tests.unit.scene3d_builder_cases import L_SHAPE

    record = polygon_record("TABLE_RECTANGULAR", L_SHAPE, 75.0)
    assert object_box(record) is None
    (block,) = REGISTRY.build(record)
    assert block.mesh == default_builder(record)[0].mesh


@pytest.mark.parametrize("kind", sorted(OBJECT_KINDS))
def test_a_footprint_of_nine_kilometres_is_still_a_bounded_mesh(kind: str) -> None:
    """``MAX_REPEATS``: staves, slats, bays and lattice bars are spaced wider rather
    than made in their millions."""
    assert MAX_REPEATS == 240
    for size, height in ((900_000.0, 300.0), (300.0, 900_000.0)):
        record = (circle_record(kind, size / 2.0, height) if kind in ROUND
                  else polygon_record(kind, rectangle(size, size / 3.0), height, shape="rectangle"))
        triangles = sum(part.mesh.triangle_count for part in REGISTRY.build(record))
        assert triangles <= OBJECT_TRIANGLE_BUDGET, (kind, size, height, triangles)


def test_a_turned_object_is_its_turned_mesh() -> None:
    """The rotation is the transform's: a record whose LOCAL rectangle is turned is
    not a box any more (the snapshot never makes one — a rotated item's local frame
    is its own), and is shown as the block rather than a mis-fitted object."""
    record = record_of("BENCH", (180.0, 60.0), 85.0, angle=30.0)
    assert object_box(record) is None
    assert [part.name for part in REGISTRY.build(record)] == ["prism"]


def test_the_seeds_come_from_the_record_and_differ_between_items() -> None:
    """A fire pit's stone tones are seeded by its item id (``params["seed"]``)."""
    first = circle_record("FIRE_PIT", 50.0, 40.0, item_id="pit-1")
    second = circle_record("FIRE_PIT", 50.0, 40.0, item_id="pit-2")
    a = REGISTRY.build(first)[0].mesh.colors
    b = REGISTRY.build(second)[0].mesh.colors
    assert not np.array_equal(a, b)
    assert np.array_equal(a, REGISTRY.build(first)[0].mesh.colors)


def test_round_objects_stay_on_their_circle() -> None:
    """Measured, not assumed: every round object's widest reach from its centre is its
    radius plus at most 10 cm (the trampoline's pad, the parasol's valance)."""
    for kind, sizes in ROUND.items():
        for radius in sizes:
            points = _mesh_points(kind, radius, 150.0)
            reach = float(np.hypot(points[:, 0], points[:, 1]).max())
            assert reach <= radius + 10.0 + 1e-3, (kind, radius, reach)
    assert math.isfinite(reach)
