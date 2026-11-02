"""Rain, snow, leaves, butterflies, fireflies and the garden lights as data (Phase 17 L5,
#389, ADR-070): the budget, the buffers' layout, which plants have life, where the lamps
are."""

from __future__ import annotations

import dataclasses
import math
import re
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.phenology import PhenologyState
from open_garden_planner.core.scene3d import Material, Params, Record, Transform
from open_garden_planner.core.scene3d.builders import OBJECT_KINDS, production_registry
from open_garden_planner.core.scene3d.builders.lights import (
    STRING_POST_CM,
    build_garden_light,
    build_string_lights,
    lamp_light,
    lantern_bulb,
    string_bulbs,
    string_layout,
)
from open_garden_planner.core.scene3d.frame import pose_points, scene_to_engine_points
from open_garden_planner.core.scene3d.interleave import VERTEX_STRIDE
from open_garden_planner.core.scene3d.lights import (
    LAMP_SLOTS,
    LIGHT_KINDS,
    lamp_sources,
    nearest_lamps,
)
from open_garden_planner.core.scene3d.particles import (
    AMBIENT_KINDS,
    BULB_CODE,
    BUTTERFLY_CODE,
    FIREFLY_CODE,
    LEAF_CODE,
    MAX_BULBS,
    MAX_BUTTERFLIES,
    MAX_FIREFLIES,
    MAX_LEAVES,
    MAX_PARTICLES,
    PRECIP_COUNT,
    Emitter,
    ambient_buffers,
    ambient_emitters,
    ambient_particle_count,
    is_firefly_season,
    precipitation_buffers,
    precipitation_volume,
)
from open_garden_planner.core.string_lights import (
    BULB_SPACING_CM,
    MAX_BULBS_PER_STRING,
    POST_CLEAR_CM,
)
from tests.unit.scene3d_builder_cases import line_record

QML = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner" / "ui" / "view3d" / "quick3d" / "qml"


def _vertices(buffers) -> np.ndarray:
    return np.frombuffer(buffers.vertex_data, dtype="<f4").reshape(-1, VERTEX_STRIDE // 4)


def plant(item_id: str, kind: str = "TREE", *, radius: float = 150.0, height: float = 500.0,
          east: float = 0.0, north: float = 0.0, base: float = 0.0) -> Record:
    ring = tuple((radius * math.cos(a), radius * math.sin(a))
                 for a in (2.0 * math.pi * k / 16 for k in range(16)))
    return Record(item_id=item_id, kind=kind, shape="circle", footprints=(ring,),
                  transform=Transform(east_cm=east, north_cm=north, base_cm=base),
                  material=Material(kind, fill_rgba=(60, 120, 50, 255)), height_cm=height,
                  params=Params({"seed": item_id, "radius_cm": radius}))


def state(*, leaves: float = 1.0, autumn: float = 0.0, bloom: float = 0.0) -> PhenologyState:
    return PhenologyState(leaf_density=leaves, autumn_color=autumn, autumn_tint_linear=(1.0, 1.0, 1.0),
                          bloom=bloom, ripeness=0.0, snow=0.0, foliage_tint_linear=(1.0, 1.0, 1.0),
                          foliage_tint_rgba=(255, 255, 255, 255), accent_opacity=1.0,
                          accent_tint_linear=(1.0, 1.0, 1.0), accent_tint_rgba=(255, 255, 255, 255))


# ── the budget ───────────────────────────────────────────────────────────────


def test_every_particle_the_scene_can_draw_at_once_is_within_the_issues_5000() -> None:
    """Issue #389: <= 5k particles. One precipitation at a time, and every ambient cap."""
    assert PRECIP_COUNT + MAX_LEAVES + MAX_BUTTERFLIES + MAX_FIREFLIES + MAX_BULBS <= MAX_PARTICLES
    assert MAX_PARTICLES == 5_000


def test_a_crowded_plan_stays_within_the_caps() -> None:
    records = [plant(f"t{i:03d}", radius=80.0 + i, height=300.0, east=i * 300.0) for i in range(300)]
    seasons = {r.item_id: state(leaves=0.5, autumn=0.8, bloom=0.9) for r in records}
    emitters = ambient_emitters(records, seasons, date(2026, 7, 1), 52.0)
    for kind, cap in (("leaf", MAX_LEAVES), ("butterfly", MAX_BUTTERFLIES), ("firefly", MAX_FIREFLIES)):
        assert sum(e.count for e in emitters if e.kind == kind) <= cap, kind
    assert ambient_particle_count(emitters) <= MAX_LEAVES + MAX_BUTTERFLIES + MAX_FIREFLIES


def test_the_lights_bulbs_are_capped_too() -> None:
    strings = [string(f"s{i:03d}", length=4000.0, rotation=0.0, north=i * 100.0)
               for i in range(20)]
    sources = lamp_sources(strings)
    assert sum(len(s.bulb_points) for s in sources) == MAX_BULBS
    assert len(sources) == 20, "a string beyond the cap still lights; it does not glow"


# ── the precipitation's buffer ───────────────────────────────────────────────


def test_the_precipitation_buffer_is_quads_of_unit_seeds() -> None:
    buffers = precipitation_buffers()
    rows = _vertices(buffers)
    assert buffers.vertex_count == 4 * PRECIP_COUNT and buffers.index_count == 6 * PRECIP_COUNT
    assert rows.shape == (4 * PRECIP_COUNT, 12)
    assert (rows[:, 0:3] >= 0.0).all() and (rows[:, 0:3] < 1.0).all()
    assert set(np.unique(rows[:, 10]).tolist()) == {0.0, 1.0, 2.0, 3.0}
    quads = rows.reshape(PRECIP_COUNT, 4, 12)
    assert (quads[:, :, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]] == quads[:, :1, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]]).all(), \
        "a particle's four corners share everything but the corner"
    ranks = quads[:, 0, 9]
    assert ranks.min() >= 0.0 and ranks.max() < 1.0
    assert abs(float((ranks < 0.5).mean()) - 0.5) < 0.02, "a density draws that share"
    assert buffers == precipitation_buffers(), "seeded: the same buffer every time"
    assert buffers.bounds_max[0] >= 1.0e5, "the shader places the drops anywhere: never culled"


def test_the_volume_follows_the_cameras_target() -> None:
    near = precipitation_volume((0.0, -1000.0, 300.0), (0.0, 0.0, 0.0))
    far = precipitation_volume((0.0, -50_000.0, 30_000.0), (500.0, 700.0, 0.0))
    assert near.center_scene == (0.0, 0.0) and far.center_scene == (500.0, 700.0)
    assert 1_600.0 <= near.size_cm < far.size_cm <= 8_000.0
    assert 800.0 <= near.height_cm <= far.height_cm <= 2_500.0


# ── which plants have life ───────────────────────────────────────────────────


def test_leaves_fall_from_turned_trees_and_shrubs_that_are_dropping_them() -> None:
    records = [plant("oak"), plant("lilac", "SHRUB", radius=80.0, height=250.0),
               plant("aster", "PERENNIAL", radius=30.0, height=60.0), plant("bare"), plant("green")]
    seasons = {"oak": state(leaves=0.5, autumn=0.9), "lilac": state(leaves=0.7, autumn=0.5),
               "aster": state(leaves=0.5, autumn=0.9), "bare": state(leaves=0.0, autumn=1.0),
               "green": state(leaves=1.0, autumn=0.0)}
    leaves = [e for e in ambient_emitters(records, seasons, date(2026, 10, 20), 52.0) if e.kind == "leaf"]
    assert [e.item_id for e in leaves] == ["lilac", "oak"]
    oak = next(e for e in leaves if e.item_id == "oak")
    assert oak.top_cm == 500.0 and oak.base_cm == 0.0 and oak.radius_cm == 150.0
    assert oak.count > next(e for e in leaves if e.item_id == "lilac").count, "shared by crown size"


def test_butterflies_visit_flowers_within_reach() -> None:
    records = [plant("rose", "SHRUB", radius=60.0, height=150.0),
               plant("lime", radius=300.0, height=1500.0), plant("fern", "PERENNIAL", radius=30.0, height=40.0)]
    seasons = {"rose": state(bloom=0.9), "lime": state(bloom=1.0), "fern": state(bloom=0.1)}
    flies = [e for e in ambient_emitters(records, seasons, date(2026, 6, 21), 52.0) if e.kind == "butterfly"]
    assert [e.item_id for e in flies] == ["rose"], "not a tall tree's crown, not a fern"


@pytest.mark.parametrize(("month", "latitude", "season"), [
    (7, 52.0, True), (1, 52.0, False), (1, -33.9, True), (7, -33.9, False), (6, 0.0, True)])
def test_fireflies_belong_to_the_hemispheres_summer(month: int, latitude: float, season: bool) -> None:
    day = date(2026, month, 15)
    assert is_firefly_season(day, latitude) is season
    emitters = ambient_emitters([plant("oak")], {"oak": state()}, day, latitude)
    assert any(e.kind == "firefly" for e in emitters) is season


def test_a_plan_without_plants_has_no_life() -> None:
    assert ambient_emitters([], {}, date(2026, 7, 1), 52.0) == ()
    assert ambient_buffers(()).is_empty


def test_the_same_plan_and_date_give_the_same_life() -> None:
    records = [plant(f"p{i}", "SHRUB", radius=50.0, height=120.0, east=i * 200.0) for i in range(12)]
    seasons = {r.item_id: state(bloom=0.8) for r in reversed(records)}
    one = ambient_emitters(records, seasons, date(2026, 6, 1), 52.0)
    two = ambient_emitters(list(reversed(records)), seasons, date(2026, 6, 1), 52.0)
    assert one == two and ambient_buffers(one) == ambient_buffers(two)


# ── the ambient buffer ───────────────────────────────────────────────────────


def test_the_ambient_buffer_carries_kind_place_and_ground() -> None:
    emitters = (Emitter("leaf", "a", 100.0, 200.0, 400.0, 30.0, 150.0, 3),
                Emitter("butterfly", "b", -50.0, 0.0, 120.0, 0.0, 40.0, 2),
                Emitter("firefly", "c", 0.0, 0.0, 80.0, 0.0, 60.0, 4),
                Emitter("bulb", "d", 10.0, 20.0, 90.0, 90.0, 30.0, 1))
    buffers = ambient_buffers(emitters)
    rows = _vertices(buffers)
    assert buffers.vertex_count == 4 * 3 + 8 * 2 + 4 * 4 + 4
    assert buffers.index_count == 6 * (3 + 2 * 2 + 4 + 1)
    codes = rows[:, 9]
    assert {float(c) for c in codes} == {LEAF_CODE, BUTTERFLY_CODE, FIREFLY_CODE, BULB_CODE}
    assert sorted({int(c * 4) for c in codes}) == [0, 1, 2, 3], "ambient.vert reads int(a * 4)"
    leaf = rows[codes == np.float32(LEAF_CODE)]
    engine = scene_to_engine_points(np.array([[100.0, 200.0, 400.0]]))[0]
    assert np.allclose(leaf[:, 0:3], engine), "the frame mapping, once"
    assert np.allclose(leaf[:, 11], 30.0), "the soil's height rides along (engine y = up)"
    butterfly = rows[codes == np.float32(BUTTERFLY_CODE)]
    assert sorted(set(butterfly[:, 10].tolist())) == list(range(8)), "two wings: corners 0..7"
    lo, hi = np.array(buffers.bounds_min), np.array(buffers.bounds_max)
    assert (rows[:, 0:3] >= lo - 1e-3).all() and (rows[:, 0:3] <= hi + 1e-3).all()


def test_an_emitter_is_refused_for_what_it_cannot_be() -> None:
    with pytest.raises(ValueError):
        Emitter("bee", "a", 0.0, 0.0, 0.0, 0.0, 1.0, 1)
    with pytest.raises(ValueError):
        Emitter("leaf", "a", math.nan, 0.0, 0.0, 0.0, 1.0, 1)
    assert set(AMBIENT_KINDS) == {"leaf", "butterfly", "firefly", "bulb"}


# ── the garden lights ────────────────────────────────────────────────────────


def lantern(item_id: str = "lamp", *, east: float = 300.0, north: float = 400.0,
            rotation: float = 0.0, base: float = 0.0) -> Record:
    ring = tuple((20.0 * math.cos(a), 20.0 * math.sin(a)) for a in (2.0 * math.pi * k / 24 for k in range(24)))
    return Record(item_id=item_id, kind="GARDEN_LIGHT", shape="circle", footprints=(ring,),
                  transform=Transform(east_cm=east, north_cm=north, rotation_deg=rotation, base_cm=base),
                  material=Material("GARDEN_LIGHT", fill_rgba=(49, 53, 56, 255)), height_cm=110.0,
                  params=Params({"seed": item_id, "radius_cm": 20.0}))


def string(item_id: str = "string", *, length: float = 440.0, rotation: float = 30.0,
           north: float = 500.0, path: tuple[tuple[float, float], ...] | None = None) -> Record:
    """A string of lights as the line tool draws it (L5.4: a line since the owner's
    manual test) — by default straight, ``length`` long, about its middle."""
    half = length / 2.0
    line = path if path is not None else ((-half, 0.0), (half, 0.0))
    record = line_record("STRING_LIGHTS", line, 250.0, width=12.0, item_id=item_id)
    return dataclasses.replace(
        record, transform=Transform(east_cm=1000.0, north_cm=north, rotation_deg=rotation))


def test_the_light_kinds_are_registered_objects() -> None:
    assert set(LIGHT_KINDS) <= OBJECT_KINDS
    registry = production_registry()
    for record in (lantern(), string()):
        parts = registry.build(record) if hasattr(registry, "build") else registry.builder_for(record.kind)(record)
        assert parts, record.kind
        assert {part.name for part in parts} >= ({"bulb"} if record.kind == "GARDEN_LIGHT" else {"bulbs"})


def test_a_lantern_glows_where_its_bulb_is() -> None:
    """ONE canonical path: the glow and the light are posed from the builder's bulb."""
    record = lantern(rotation=40.0, base=35.0)
    (source,) = lamp_sources([record])
    local = lantern_bulb(record, 110.0)
    assert local is not None
    expected = pose_points(record.transform, np.array([local]))[0]
    assert np.allclose(source.bulb_points[0], expected)
    assert source.light[:2] == pytest.approx(tuple(expected[:2]))
    assert 35.0 < source.light[2] < 35.0 + 110.0, "the light hangs at the lantern, on its soil"
    bulb_part = next(part for part in build_garden_light(record) if part.name == "bulb")
    centre = bulb_part.mesh.positions.mean(axis=0)
    assert np.allclose(centre, local, atol=0.5), "the builder's bulb is where the glow is"


@pytest.mark.parametrize("kind", ["GARDEN_LIGHT", "STRING_LIGHTS"])
def test_the_point_light_stands_below_the_lamp(kind: str) -> None:
    """Inside the bulb the point light lit its ball from within — it drew dark (3D review
    of L5): it stands under the lantern's frame, and under a string's middle bulb."""
    record = lantern(rotation=40.0, base=35.0) if kind == "GARDEN_LIGHT" else string()
    height = 110.0 if kind == "GARDEN_LIGHT" else 250.0
    (source,) = lamp_sources([record])
    local = lamp_light(record, height)
    assert local is not None
    expected = pose_points(record.transform, np.array([local]))[0]
    assert source.light[:3] == pytest.approx(tuple(expected))
    parts = production_registry().builder_for(kind)(record)
    if kind == "GARDEN_LIGHT":
        bulb = next(part for part in parts if part.name == "bulb").mesh.positions
        assert local[2] < bulb[:, 2].min() - 10.0, "below the lantern"
        assert not any(part.material_kind == "glass" for part in parts), (
            "no pane: lit by its own lamp it drew a white box at night")
    else:
        bulbs = string_bulbs(record, height)
        assert bulbs is not None
        middle = bulbs[len(bulbs) // 2]
        mesh = next(part for part in parts if part.name == "bulbs").mesh.positions
        near = mesh[np.hypot(mesh[:, 0] - middle[0], mesh[:, 1] - middle[1]) < 4.0]
        assert len(near) and local[2] < near[:, 2].min(), "below the middle bulb"


@pytest.mark.parametrize("path", [
    ((0.0, 0.0), (200.0, 0.0), (400.0, 0.0)),                         # straight, 3 posts, 10 bulbs
    ((0.0, 0.0), (220.0, 0.0), (440.0, 0.0)),                         # straight, 3 posts, 11 bulbs
    tuple((200.0 * i, 0.0) for i in range(5)),                        # straight, 5 posts
    ((0.0, 0.0), (210.0, 40.0), (420.0, 0.0)),                        # a symmetric V, 11 bulbs
    ((0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0), (0.0, 0.0)),  # a closed square
], ids=["straight-3-even", "straight-3-odd", "straight-5", "v", "loop"])
def test_a_strings_point_light_stands_outside_every_post(path) -> None:
    """Senior review round 12: the bulbs' centroid put the light INSIDE the middle post
    of a straight string, and before ``POST_CLEAR_CM`` the middle bulb hung on the
    middle post of a symmetric one. Under the middle bulb, kept clear of the posts, the
    light is outside every post's box, and under a bulb."""
    from tests.unit.scene3d_builder_cases import line_record

    record = line_record("STRING_LIGHTS", path, 250.0, width=12.0)
    local = lamp_light(record, 250.0)
    lay = string_layout(record)
    assert local is not None and lay is not None
    half = STRING_POST_CM / 2.0
    for px, py in lay.posts:
        assert max(abs(local[0] - px), abs(local[1] - py)) > half + 2.0, (px, py, local)
    bulbs = string_bulbs(record, 250.0)
    assert bulbs is not None
    assert np.hypot(bulbs[:, 0] - local[0], bulbs[:, 1] - local[1]).min() < 1e-6, "under a bulb"


def test_a_strings_bulbs_hang_between_its_posts_and_sag() -> None:
    record = string(length=440.0, rotation=0.0)
    bulbs = string_bulbs(record, 250.0)
    assert bulbs is not None
    assert len(bulbs) == 11, "a bulb every 40 cm of 440 cm"
    gaps = np.diff(bulbs[:, 0])
    assert np.allclose(gaps, BULB_SPACING_CM), "a bulb every so often"
    assert (np.abs(bulbs[:, 0]) < 220.0).all() and np.allclose(bulbs[:, 1], 0.0)
    middle, end = bulbs[len(bulbs) // 2, 2], bulbs[0, 2]
    assert middle < end < 250.0, "a wire sags in the middle"
    parts = build_string_lights(record)
    bulb_meshes = next(part for part in parts if part.name == "bulbs").mesh
    assert bulb_meshes.positions[:, 2].max() < 250.0
    top = max(part.mesh.positions[:, 2].max() for part in parts)
    assert top == pytest.approx(250.0, abs=1e-6), "the height is the posts' tops"


# ── a string is a line (owner's manual test of L5) ───────────────────────────


def _posts_of(record: Record) -> list[tuple[float, float]]:
    """Where the builder stood a post: the centres of the clusters of the string's body
    vertices that reach its height (the wire hangs below the tops)."""
    body = next(part for part in build_string_lights(record) if part.name == "string lights")
    top = body.mesh.positions[body.mesh.positions[:, 2] > 249.0][:, :2]
    clusters: list[list[np.ndarray]] = []
    for point in top:
        for cluster in clusters:
            if float(np.hypot(*(point - cluster[0]))) < 3.0 * STRING_POST_CM:
                cluster.append(point)
                break
        else:
            clusters.append([point])
    return [(float(np.mean([p[0] for p in c])), float(np.mean([p[1] for p in c]))) for c in clusters]


BENT: tuple[tuple[float, float], ...] = ((0.0, 0.0), (300.0, 0.0), (300.0, 200.0), (600.0, 260.0))


def test_a_post_stands_at_every_point_of_the_line() -> None:
    """The owner: a string of lights "needs to be a 1D object like a fence or wall".
    Every point of the line is a post; the wire runs from post to post."""
    posts = _posts_of(string(path=BENT, rotation=0.0))
    assert len(posts) == len(BENT)
    for drawn in BENT:
        assert min(math.hypot(px - drawn[0], py - drawn[1]) for px, py in posts) < 0.5, drawn


def test_the_bulbs_are_spaced_along_the_wire_not_per_span() -> None:
    """A real string's bulbs sit evenly on its cable wherever the posts stand: 40 cm
    apart along the whole line — the layout the canvas draws too — each moved at most
    ``POST_CLEAR_CM`` off its place to keep clear of a post."""
    record = string(path=BENT, rotation=0.0)
    lay = string_layout(record)
    assert lay is not None and len(lay.posts) == 4 and len(lay.spans) == 3
    total = 300.0 + 200.0 + math.hypot(300.0, 60.0)
    assert len(lay.bulbs) == round(total / BULB_SPACING_CM)
    walked = [sum(lay.spans[i].length_cm for i in range(b.span)) + b.share * lay.spans[b.span].length_cm
              for b in lay.bulbs]
    step = total / len(lay.bulbs)
    even = [(k + 0.5) * step for k in range(len(lay.bulbs))]
    assert np.abs(np.array(walked) - np.array(even)).max() <= POST_CLEAR_CM + 1e-9
    bulbs = string_bulbs(record, 250.0)
    assert bulbs is not None
    assert np.allclose(bulbs[:, :2], np.array(lay.bulbs_xy()))
    assert (bulbs[:, 2] < 250.0 - 2.0).all(), "every bulb hangs under the wire"


def test_a_closed_string_has_no_second_post_where_it_closes() -> None:
    loop = ((0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 300.0), (0.0, 0.0))
    lay = string_layout(string(path=loop, rotation=0.0))
    assert lay is not None and len(lay.posts) == 4 and len(lay.spans) == 4
    assert len(_posts_of(string(path=loop, rotation=0.0))) == 4


def test_a_very_long_string_carries_at_most_max_bulbs() -> None:
    bulbs = string_bulbs(string(length=60_000.0, rotation=0.0), 250.0)
    assert bulbs is not None and len(bulbs) == MAX_BULBS_PER_STRING


@pytest.mark.parametrize("path", [
    ((10.0, 10.0), (10.0, 10.0), (10.4, 10.2)),                          # one post
    ((0.0, 0.0), (0.0, 0.0), (200.0, 0.0), (200.0, 0.0), (200.5, 0.0)),  # repeated points
], ids=["one post", "repeated points"])
def test_a_degenerate_line_builds_posts_and_no_stray_bulb(path) -> None:
    record = string(path=path, rotation=0.0)
    lay = string_layout(record)
    assert lay is not None
    parts = build_string_lights(record)
    assert parts and parts[0].name == "string lights"
    if not lay.spans:
        assert len(lay.posts) == 1 and not lay.bulbs
        assert all(part.name != "bulbs" for part in parts)
        assert lamp_sources([record]) == (), "no bulb, no light"
    else:
        assert len(lay.posts) == 2, "repeated points are one post"


def test_a_string_read_as_a_rectangle_is_the_line_along_its_long_side() -> None:
    """A hand-edited plan can still type a rectangle a string of lights: two posts at
    the ends of its long side, as it was built before it became a line."""
    ring = ((-220.0, -15.0), (220.0, -15.0), (220.0, 15.0), (-220.0, 15.0))
    record = Record(item_id="rect", kind="STRING_LIGHTS", shape="rectangle", footprints=(ring,),
                    transform=Transform(), height_cm=250.0, params=Params({"seed": "rect"}),
                    material=Material("STRING_LIGHTS", fill_rgba=(238, 225, 198, 255)))
    posts = _posts_of(record)
    assert len(posts) == 2
    assert all(abs(y) < 0.5 and abs(abs(x) - 215.0) < 0.5 for x, y in posts), posts


def test_the_nearest_lamps_light() -> None:
    sources = lamp_sources([lantern(f"l{i}", east=i * 1000.0, north=0.0) for i in range(10)])
    lit = nearest_lamps(sources, (4100.0, 0.0, 0.0))
    assert len(lit) == LAMP_SLOTS
    assert [s.item_id for s in lit][:3] == ["l4", "l5", "l3"]
    assert nearest_lamps((), (0.0, 0.0, 0.0)) == ()


def test_the_lamp_pool_is_the_scenes() -> None:
    """Drift guard: ``lights.LAMP_SLOTS`` is ``Garden.qml``'s ``lampSlots``."""
    scene = (QML / "Garden.qml").read_text(encoding="utf-8")
    match = re.search(r"readonly property int lampSlots:\s*(\d+)", scene)
    assert match and int(match.group(1)) == LAMP_SLOTS


@pytest.mark.parametrize("kind", ["STRING_LIGHTS", "GARDEN_LIGHT"])
def test_a_hostile_outline_has_no_bulb_and_breaks_nothing(kind: str) -> None:
    """A file can type any polygon a light: one drawn crossing itself (the snapshot's
    ``outline_resolved``), two rings, a ring with a hole. The builder builds those as the
    plain block; the bulbs follow the same rule — no light, and no exception that could
    reach the workspace's pass (security review of #389)."""
    from open_garden_planner.core.scene3d.record import PARAM_OUTLINE_RESOLVED

    square = ((0.0, 0.0), (400.0, 0.0), (400.0, 30.0), (0.0, 30.0))
    other = ((500.0, 0.0), (600.0, 0.0), (600.0, 30.0), (500.0, 30.0))
    hole = ((100.0, 10.0), (100.0, 20.0), (300.0, 20.0), (300.0, 10.0))
    material = Material(kind, fill_rgba=(238, 225, 198, 255))
    hostile = [
        Record(item_id="crossed", kind=kind, shape="polygon", footprints=(square,),
               transform=Transform(), material=material, height_cm=250.0,
               params=Params({"seed": "crossed", PARAM_OUTLINE_RESOLVED: True})),
        Record(item_id="two", kind=kind, shape="polygon", footprints=(square, other),
               transform=Transform(), material=material, height_cm=250.0,
               params=Params({"seed": "two"})),
        Record(item_id="holed", kind=kind, shape="polygon", footprints=(square,), holes=((hole,),),
               transform=Transform(), material=material, height_cm=250.0,
               params=Params({"seed": "holed"})),
    ]
    assert lamp_sources(hostile) == ()
    for record in hostile:
        assert lantern_bulb(record, 250.0) is None and string_bulbs(record, 250.0) is None
        assert lamp_light(record, 250.0) is None
        parts = production_registry().builder_for(kind)(record)
        assert parts and not any(part.name in ("bulb", "bulbs") for part in parts), record.item_id


def test_no_light_without_its_kind() -> None:
    assert lamp_sources([plant("oak")]) == ()
