"""Selection, picking and walking on the real renderer (Phase 17 L1.8 — the render tier).

Opt-in (``OGP_RENDER3D=1``): a driver process with a real window system
(``view3d_selection_driver.py``) drives the real engine; the tests here only JUDGE
what it saved, with a camera model, a projection and a ray caster of their own
(``view3d_selection_support.py``, ``core/scene3d/pick_oracle.py``) — never with the
engine's. Gates G1 (20/20 picks) and G4 (the ring is where the footprint is), and
the render rows of G2, G7 and G8.

Run it on the GPU and on WARP::

    OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_view3d_selection_render.py -s
    OGP_RENDER3D=1 QSG_RHI_PREFER_SOFTWARE_RENDERER=1 venv/Scripts/python.exe -m pytest <the same>

Measured on the dev box (RTX 4070, Direct3D 11) and on WARP, 2026-10-12 — the numbers
are next to each bound; ``-s`` prints them again.
"""

from __future__ import annotations

import colorsys
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from open_garden_planner.core.scene3d import point_in_ring, pose_ring, walk
from open_garden_planner.core.scene3d.builders import walls
from open_garden_planner.core.scene3d.camera import FOV_DEG
from open_garden_planner.core.scene3d.selection import (
    MITRE_LIMIT,
    RING_LIFT_CM,
    RING_WIDTH_PX,
    SELECTION_RGB,
)
from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot
from tests.integration import view3d_selection_driver as driver
from tests.integration.quick3d_render_support import (
    failure_report,
    load_rgb,
    render_env,
    render_tier,
)
from tests.integration.view3d_selection_support import (
    broken_qml_copy,
    builder_parts,
    distances_to,
    in_order,
    marker_mask,
    mask_pixels,
    named_pick_points,
    oracle_scene,
    outline_pixels,
    perspective_outline,
    ring_mask,
    robust_answer,
    robust_chain,
    run_selection_driver,
    top_down_outline,
)

pytestmark = render_tier

Run = tuple[dict[str, Any], Path]
SCENARIOS = "ring,ring_depth,pick,lookthrough,workspace,app_walk"
SOFTWARE_ADAPTERS = ("Basic Render", "llvmpipe", "SwiftShader", "softpipe")


def _software(run: Run) -> bool:
    adapter = run[0].get("adapter")
    return adapter is None or any(name in str(adapter) for name in SOFTWARE_ADAPTERS)


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Run:
    out = tmp_path_factory.mktemp("view3d_selection")
    proc, result = run_selection_driver(out, SCENARIOS)
    assert proc.returncode == 0 and result.get("status") == "ok", failure_report(proc, out)
    return result, out


def _frame(run: Run, info: dict[str, Any]) -> tuple[np.ndarray, float]:
    return load_rgb(run[1] / info["file"]), float(info["dpr"])


def test_the_run_drew_with_no_qt_error_and_names_its_device(run: Run) -> None:
    """The ring's shader is one more shipped shader: a compile error is only a Qt
    WARNING and the frame still renders — so the judge reads Qt's messages."""
    messages = run[0]["qt_messages"]
    assert messages["counts"]["error"] == 0, messages["errors"]
    assert messages["counts"]["warning"] == 0, messages["warnings"]
    assert run[0]["adapter"], "Qt named the graphics adapter"
    print(f"\n[adapter] {run[0]['adapter']}")


# ── gate G4: the ring is where the footprint is ──────────────────────────────

#: The band is RING_WIDTH_PX wide, outside the outline; a mitred square corner reaches
#: sqrt(2) widths; one pixel more for rasterisation and anti-aliasing.
RING_REACH_PX = RING_WIDTH_PX * 2 ** 0.5 + 1.0


def _ring_step(run: Run, name: str) -> tuple[np.ndarray, float, dict[str, Any]]:
    step = next(s for s in run[0]["scenarios"]["ring"]["steps"] if s["name"] == name)
    rgb, dpr = _frame(run, step)
    return rgb, dpr, step


def test_with_nothing_selected_there_is_no_ring(run: Run) -> None:
    for name in ("none", "cleared"):
        rgb, _dpr, step = _ring_step(run, name)
        assert int(ring_mask(rgb).sum()) == 0, name
        assert step["after"]["ring_visible"] is False


@pytest.mark.parametrize("item_id", driver.RING_SELECTED)
def test_the_ring_lies_on_the_footprint_outline_seen_from_above(run: Run, item_id: str) -> None:
    """Gate G4, per shape: a turned rectangle, a polygon with a hole (the hole has its
    own ring), a circle, a plant on a raised bed. Every ring pixel lies within
    ``RING_REACH_PX`` of OUR projection of the record's outline, on its outside; and
    the ring is complete — the whole outline has ring within a band's width."""
    rgb, dpr, _step = _ring_step(run, item_id)
    record = driver.ring_records()[item_id]
    size = (rgb.shape[1], rgb.shape[0])
    outline = outline_pixels(top_down_outline(record, driver.RING_TOP, size, dpr))
    ring = mask_pixels(ring_mask(rgb))
    assert len(ring) > 100, "there is a ring"
    off = distances_to(ring, outline)
    covered = distances_to(outline, ring)
    reach = RING_REACH_PX * dpr
    complete = float((covered <= (RING_WIDTH_PX + 1.0) * dpr).mean())
    # outside the solid: the centre of a ring pixel is not in the footprint (outer minus holes)
    inside = 0
    for x, y in ring:
        east = driver.RING_TOP.center[0] + (x - size[0] / 2.0) / (driver.RING_TOP.px_per_cm * dpr)
        north = driver.RING_TOP.center[1] - (y - size[1] / 2.0) / (driver.RING_TOP.px_per_cm * dpr)
        for outer, holes in record.regions:
            if point_in_ring(east, north, pose_ring(record.transform, outer)) and not any(
                    point_in_ring(east, north, pose_ring(record.transform, hole)) for hole in holes):
                inside += 1
    print(f"\n[ring {item_id}] pixels {len(ring)}, farthest from the outline {off.max():.2f} px "
          f"(bound {reach:.2f}), mean {off.mean():.2f}; outline covered {complete:.1%}; "
          f"pixel centres inside the footprint {inside / len(ring):.1%}")
    assert float(off.max()) <= reach
    assert complete >= 0.98
    assert inside / len(ring) <= 0.12, "the band lies OUTSIDE the footprint (edge pixels aside)"
    # … and it is a thin band, not a filled shape: about one band width per outline pixel
    perimeter = len(outline) * 0.5
    assert 0.6 * perimeter * RING_WIDTH_PX * dpr <= len(ring) <= 1.6 * perimeter * RING_WIDTH_PX * dpr


def test_every_selected_item_has_its_ring_in_one_frame_and_the_others_none(run: Run) -> None:
    rgb, dpr, step = _ring_step(run, "all")
    size = (rgb.shape[1], rgb.shape[0])
    records = driver.ring_records()
    ring = mask_pixels(ring_mask(rgb))
    selected = np.concatenate([outline_pixels(top_down_outline(records[i], driver.RING_TOP, size, dpr))
                               for i in driver.RING_SELECTED])
    assert float(distances_to(ring, selected).max()) <= RING_REACH_PX * dpr
    assert float((distances_to(selected, ring) <= (RING_WIDTH_PX + 1.0) * dpr).mean()) >= 0.98
    for item_id in ("other", "bed"):   # not selected: nothing blue along their outlines
        outline = outline_pixels(top_down_outline(records[item_id], driver.RING_TOP, size, dpr))
        near = distances_to(outline, ring) <= 2.0 * dpr
        # the plant's ring crosses nothing of the bed's outline; the shed is far from all
        assert float(near.mean()) <= 0.02, item_id
    assert step["ids"] == list(driver.RING_SELECTED) and step["sent"] is True


def test_the_ring_of_a_plant_on_a_bed_is_at_the_beds_soil_height(run: Run) -> None:
    """Gate G4, the height: in a perspective look the ring sits where OUR camera model
    puts the plant's outline at the soil's height (base + lift) — and NOT where it
    would be on the ground, 38 cm lower."""
    info = run[0]["scenarios"]["ring"]["perspective"]
    rgb, dpr = _frame(run, info)
    none, _ = _frame(run, run[0]["scenarios"]["ring"]["perspective_none"])
    assert int(ring_mask(none).sum()) == 0, "nothing else in that frame is ring-coloured"
    record = driver.ring_records()["plant"]
    view = tuple(run[0]["scenarios"]["ring"]["view_size"])
    ring = mask_pixels(ring_mask(rgb))
    assert len(ring) > 60
    soil = outline_pixels(perspective_outline(record, driver.RING_PERSPECTIVE, view,
                                              driver.BED_SOIL + RING_LIFT_CM, dpr))
    ground = outline_pixels(perspective_outline(record, driver.RING_PERSPECTIVE, view,
                                                RING_LIFT_CM, dpr))
    at_soil, at_ground = distances_to(ring, soil), distances_to(ring, ground)
    print(f"\n[ring height] pixels {len(ring)}; from the outline at soil height: mean "
          f"{at_soil.mean():.2f} px, max {at_soil.max():.2f}; from the outline on the ground: "
          f"mean {at_ground.mean():.2f} px")
    assert float(at_soil.max()) <= (RING_WIDTH_PX * MITRE_LIMIT + 1.0) * dpr
    assert float(at_soil.mean()) <= RING_WIDTH_PX * dpr
    assert float(at_ground.mean()) >= 4.0 * float(at_soil.mean()) and float(at_ground.mean()) > 8.0 * dpr
    # the ring is complete although the plant stands in the middle of it: it is drawn in front
    assert float((distances_to(soil, ring) <= (RING_WIDTH_PX + 1.5) * dpr).mean()) >= 0.97


def test_the_ring_is_the_canvas_selection_blue_on_screen(run: Run) -> None:
    """The colour a user sees (perspective view: exposure and the filmic curve applied)
    keeps the hue of the 2D selection colour; in the truth view it is that colour's
    linear value, as every pixel there is."""
    rgb, _dpr = _frame(run, run[0]["scenarios"]["ring"]["perspective"])
    seen = rgb[ring_mask(rgb)].astype(np.float64)
    core = seen[seen[:, 2] >= np.percentile(seen[:, 2], 50)].mean(axis=0)   # not the AA fringe
    hue = colorsys.rgb_to_hsv(*(core / 255.0))[0] * 360.0
    wanted = colorsys.rgb_to_hsv(*(np.array(SELECTION_RGB) / 255.0))[0] * 360.0
    print(f"\n[ring colour] on screen rgb({core[0]:.0f}, {core[1]:.0f}, {core[2]:.0f}), hue "
          f"{hue:.1f} deg; the canvas's {SELECTION_RGB}, hue {wanted:.1f} deg")
    assert abs(hue - wanted) <= 10.0
    assert core[2] > 150 and core[2] > core[0] + 80, "it reads as a saturated blue"


def test_a_selection_change_creates_and_destroys_no_engine_object(run: Run) -> None:
    """THE memory rule of the ring (ADR-060): one geometry, made with the first
    selection, re-loaded ever after; the Models and their buffers are not touched."""
    scenario = run[0]["scenarios"]["ring"]
    steps = scenario["steps"]
    first = steps[0]["before"]
    assert first["ring_geometries"] == 0 and first["ring_loads"] == 0
    for step in steps:
        for moment in ("before", "after"):
            assert step[moment]["parts"] == first["parts"] == step[moment]["engine_parts"], step["name"]
            assert step[moment]["model_uploads"] == first["model_uploads"], step["name"]
        loaded = step["after"]["ring_loads"] - step["before"]["ring_loads"]
        assert loaded == (1 if step["ids"] else 0), step["name"]
        assert step["after"]["ring_geometries"] == (1 if step["after"]["ring_loads"] else 0)
        assert step["sink_geometry_uploads"] == steps[0]["sink_geometry_uploads"]
    steady = scenario["steady"]
    assert steady["after"]["ring_loads"] - steady["before"]["ring_loads"] == 20
    assert steady["after"]["ring_geometries"] == steady["before"]["ring_geometries"] == 1
    assert steady["after"]["parts"] == steady["before"]["parts"] == steady["after"]["engine_parts"]
    assert steady["after"]["model_uploads"] == steady["before"]["model_uploads"]
    assert scenario["state_equals_expected"] is True


def test_the_ring_follows_a_moved_item_and_the_move_uploads_no_model_geometry(run: Run) -> None:
    info = run[0]["scenarios"]["ring"]["moved"]
    rgb, dpr = _frame(run, info)
    size = (rgb.shape[1], rgb.shape[0])
    moved = driver.record("box", "GARAGE_SHED", -300.0, 150.0, driver.rect(220.0, 140.0),
                          height=120.0, colour=driver.RED, rotation=70.0, shape="rectangle")
    ring = mask_pixels(ring_mask(rgb))
    here = outline_pixels(top_down_outline(moved, driver.RING_TOP, size, dpr))
    before = outline_pixels(top_down_outline(driver.ring_records()["box"], driver.RING_TOP, size, dpr))
    assert float(distances_to(ring, here).max()) <= RING_REACH_PX * dpr
    assert float((distances_to(before, ring) <= 2.0 * dpr).mean()) < 0.2, "not where the item was"
    assert info["after"]["model_uploads"] == info["before"]["model_uploads"]
    assert info["after"]["ring_loads"] == info["before"]["ring_loads"] + 1
    assert info["after"]["parts"] == info["before"]["parts"]


def test_a_depth_tested_ring_would_be_hidden_in_a_walls_own_masonry(run: Run) -> None:
    """WHY the ring is drawn in front (the control of that decision, measured): a wall
    is built 30 cm thick on a 5 cm stroke. Seen from above, the shipped ring shows the
    whole outline; the same ring depth-tested lies inside the wall and all but vanishes."""
    scenario = run[0]["scenarios"]["ring_depth"]
    record = driver.wall_record()
    counts = {}
    for name in ("in_front", "depth_tested"):
        rgb, dpr = _frame(run, scenario[name])
        size = (rgb.shape[1], rgb.shape[0])
        outline = outline_pixels(top_down_outline(record, driver.RING_TOP, size, dpr))
        ring = mask_pixels(ring_mask(rgb))
        counts[name] = (len(ring), float((distances_to(outline, ring) <= 4.0 * dpr).mean()))
    print(f"\n[ring depth] in front: {counts['in_front'][0]} px, outline covered "
          f"{counts['in_front'][1]:.1%}; depth-tested: {counts['depth_tested'][0]} px, "
          f"{counts['depth_tested'][1]:.1%}")
    assert scenario["shipped_scale"] == pytest.approx(0.01)
    assert counts["in_front"][1] >= 0.98
    assert counts["depth_tested"][1] <= 0.15 and counts["depth_tested"][0] < counts["in_front"][0] / 10


# ── gate G1: twenty of twenty picks ──────────────────────────────────────────

#: Of the twenty seeded positions at most this many may be "nothing" (the ground, the
#: sky): a list of twenty lawn clicks would prove nothing about picking.
NOTHING_QUOTA = 6


def _pick_case(run: Run, plan: str) -> dict[str, Any]:
    data = run[0]["scenarios"]["pick"][plan]
    scene, _view, _manager = driver.load_plan(plan)
    records = driver.plan_records(scene)
    shot = PerspectiveShot(tuple(data["shot"]["eye"]), tuple(data["shot"]["target"]),
                           float(data["shot"]["fov"]))
    view = (float(data["view_size"][0]), float(data["view_size"][1]))
    assert view == (float(driver.PICK_VIEW[0]), float(driver.PICK_VIEW[1])), "the window was clamped"
    assert shot == driver.pick_camera(float(scene.width_cm), float(scene.height_cm),
                                      driver.plan_top(records))
    assert data["build_failures"] == [] and data["records"] == len(records)
    engine = {tuple(point): (hit["id"] if hit else None)
              for point, hit in zip(data["points"], data["hits"], strict=True)}
    chains = {tuple(point): (in_order([hit["id"], *hit["behind"]]) if hit else ())
              for point, hit in zip(data["points"], data["hits"], strict=True)}
    return {"records": records, "shot": shot, "view": view, "engine": engine, "chains": chains,
            "oracle": oracle_scene(records), "data": data}


@pytest.fixture(scope="module")
def pick_cases(run: Run, qapp: Any) -> dict[str, dict[str, Any]]:  # noqa: ARG001 - Qt for the scene
    return {plan: _pick_case(run, plan) for plan in driver.PICK_PLANS}


@pytest.mark.parametrize("plan", list(driver.PICK_PLANS))
def test_twenty_of_twenty_picks_agree_with_the_cpu_oracle(pick_cases, plan: str) -> None:
    """Gate G1. Twenty seeded view positions per plan, taken in seeded order: the first
    twenty at which the oracle's answer does not hang on a silhouette edge, at most
    ``NOTHING_QUOTA`` of them on the ground or the sky. At each, the engine's
    ``pick`` names what the oracle's ray meets first in the records' own meshes."""
    case = pick_cases[plan]
    chosen: list[tuple[tuple[float, float], str | None]] = []
    nothing = 0
    for point in driver.seeded_points():
        answer, robust = robust_answer(case["oracle"], case["shot"], case["view"], *point)
        if not robust or (answer is None and nothing >= NOTHING_QUOTA):
            continue
        nothing += answer is None
        chosen.append((point, answer))
        if len(chosen) == 20:
            break
    assert len(chosen) == 20, "the seeded list holds twenty judgeable positions"
    agree = [point for point, answer in chosen if case["engine"][point] == answer]
    kinds = sorted({case["records"][answer].kind for _point, answer in chosen if answer})
    print(f"\n[pick {plan}] {len(agree)}/20; kinds hit: {kinds}; nothing: {nothing}")
    assert len(agree) == 20, [(point, answer, case["engine"][point]) for point, answer in chosen
                              if case["engine"][point] != answer]
    assert len(kinds) >= (5 if plan == "bench_small" else 2), "the twenty are not one item"


def test_the_named_positions_are_picked_as_the_oracle_says(pick_cases) -> None:
    """Gate G1's three named cases: a point on a plant standing on a raised bed, a
    point inside a polygon's hole (the ground, or what stands there — never the item
    around it), a point on the sky."""
    seen: dict[str, int] = {}
    for plan, case in pick_cases.items():
        named = named_pick_points(plan, case["records"], case["shot"], case["view"])
        for label, point in named:
            answer, robust = robust_answer(case["oracle"], case["shot"], case["view"], *point)
            assert robust, (plan, label)
            assert point in case["engine"], "the driver clicked where the judge points"
            assert case["engine"][point] == answer, (plan, label, point)
            seen[label] = seen.get(label, 0) + 1
            if label == "plant_on_bed":
                record = case["records"][answer]
                assert record.kind in ("TREE", "SHRUB", "PERENNIAL") and record.transform.base_cm > 0.0
            elif label == "sky":
                assert answer is None
            print(f"\n[pick {plan}] {label} at {point}: "
                  f"{case['records'][answer].kind if answer else 'nothing'}")
    assert seen.get("plant_on_bed", 0) >= 2 and seen.get("sky", 0) >= 2 and seen.get("hole", 0) >= 1


@pytest.mark.parametrize("plan", list(driver.PICK_PLANS))
def test_every_judgeable_seeded_position_agrees(pick_cases, plan: str) -> None:
    """Beyond the twenty: ALL 400 seeded positions of the plan. Off the silhouette
    edges the engine and the oracle agree everywhere (measured: 362 of 362 and 365 of
    365 on the GPU); ON an edge either answer is right, and both are items or nothing
    the neighbouring rays see."""
    case = pick_cases[plan]
    agree = disagree = edge = edge_agree = 0
    for point in driver.seeded_points():
        answer, robust = robust_answer(case["oracle"], case["shot"], case["view"], *point)
        got = case["engine"][point]
        if robust:
            agree += got == answer
            disagree += got != answer
        else:
            edge += 1
            edge_agree += got == answer
    print(f"\n[pick {plan}] off the edges {agree}/{agree + disagree} agree; on an edge "
          f"{edge_agree}/{edge}; {case['data']['ms_per_pick']} ms a pick; "
          f"{case['oracle'].triangle_count} triangles, {case['data']['models']} Models")
    assert disagree == 0 and agree >= 300
    assert case["data"]["ms_per_pick"] < 5.0


@pytest.mark.parametrize("plan", list(driver.PICK_PLANS))
def test_what_lies_behind_a_hit_is_in_the_oracles_order(pick_cases, plan: str) -> None:
    """``PickHit.behind`` is what a click that falls through a locked item meets next
    (``View3D.pickAll``). At every seeded position where the oracle's whole chain does
    not hang on a silhouette edge, the engine names the same items in the same order."""
    case = pick_cases[plan]
    agree = disagree = deep = 0
    wrong = []
    for point in driver.seeded_points():
        chain, robust = robust_chain(case["oracle"], case["shot"], case["view"], *point)
        if not robust:
            continue
        got = case["chains"][point]
        deep += len(chain) >= 2
        if got == chain:
            agree += 1
        else:
            disagree += 1
            wrong.append((point, chain, got))
    longest = max(len(chain) for chain in case["chains"].values())
    print(f"\n[pick chain {plan}] {agree}/{agree + disagree} whole chains agree; {deep} of them "
          f"two items or more deep; the longest engine chain: {longest} items")
    assert disagree == 0, wrong[:5]
    # measured on the GPU: 349 of 349 (34 of them two or more deep) and 362 of 362 (1)
    assert agree >= 300 and deep >= (25 if plan == "bench_small" else 1)


# ── standing against a wall: the near plane ──────────────────────────────────


def test_the_walk_core_stops_the_walker_a_radius_from_the_masonry(run: Run) -> None:
    """Where the look-through frames were taken: the walk core walked there itself."""
    look = run[0]["scenarios"]["lookthrough"]
    wall = driver.look_records()["north_wall"]
    masonry = walls.body_thickness_cm(wall) / 2.0 + walls.COPING_OVERSAIL_CM
    reach = masonry + walk.WALKER_RADIUS_CM
    assert masonry == 19.0 and (wall.path_width_cm or 0.0) == driver.WALL_STROKE == 5.0
    assert look["at_wall"] == pytest.approx([900.0, driver.LOOK_NORTH_WALL - reach], abs=0.01)
    assert look["in_corner"] == pytest.approx(
        [driver.LOOK_EAST_WALL - reach, driver.LOOK_NORTH_WALL - reach], abs=0.01)
    view = look["view_size"]
    corner = walk.near_plane_reach_cm(view[0] / view[1])
    print(f"\n[near plane] {walk.NEAR_PLANE_CM} cm; its farthest corner at {view[0]:.0f}x{view[1]:.0f} "
          f"and {walk.WALK_FOV_DEG} deg: {corner:.2f} cm from the eye; the walker's radius "
          f"{walk.WALKER_RADIUS_CM} cm")
    assert corner < walk.WALKER_RADIUS_CM


def test_standing_against_a_wall_never_looks_through_it(run: Run) -> None:
    """The brief's wall. Pressed against a 180 cm wall, and into the inside corner of
    two, the walker looks all round (every 15 degrees — at 75, 90 and 105 the wall is
    grazed), level, 35 degrees up and down, at the adult's and the child's eye height:
    in none of the 288 frames is a pixel of the magenta blocks behind the walls."""
    look = run[0]["scenarios"]["lookthrough"]
    rows = look["looks"]
    assert len(rows) == 2 * len(driver.LOOK_EYES) * len(driver.LOOK_PITCHES) * len(driver.LOOK_YAWS)
    seen = [(row["name"], row["magenta"]) for row in rows if row["magenta"]]
    assert seen == [], f"{len(seen)} frames look through the wall"
    kept = [row for row in rows if "file" in row]
    assert len(kept) == 16, "the level adult frames every 45 degrees, at both places"
    for row in kept:   # the driver counted with the judge's mask: count them again
        rgb = load_rgb(run[1] / row["file"])
        assert int(marker_mask(rgb).sum()) == 0
        assert rgb.std() > 1.0, "a frame of something (not one flat colour)"
    print(f"\n[look through] {len(rows)} frames, magenta pixels in none")


def test_the_look_through_test_can_fail(run: Run) -> None:
    """Its two controls. The blocks ARE magenta in a frame (seen from their own side
    of the wall), and an eye put 2 cm in front of the masonry — nearer than the near
    plane, where the collision radius never lets the walker be — DOES see them."""
    look = run[0]["scenarios"]["lookthrough"]
    above, close = look["control_above"], look["control_too_close"]
    for control in (above, close):
        assert int(marker_mask(load_rgb(run[1] / control["file"])).sum()) == control["magenta"]
    print(f"\n[look through] controls: the block in the open {above['magenta']} px; through the "
          f"wall from inside the near distance {close['magenta']} px")
    assert above["magenta"] > 2000
    assert close["magenta"] > 10_000


# ── the real workspace on the real engine: gates G2 and G7, one row each ─────


@pytest.fixture(scope="module")
def ws(run: Run, qapp: Any) -> dict[str, Any]:  # noqa: ARG001 - Qt for the scene
    data = run[0]["scenarios"]["workspace"]
    scene, _view, _manager = driver.load_plan("bench_small")
    records = driver.plan_records(scene)
    shot = PerspectiveShot(tuple(data["shot"]["eye"]), tuple(data["shot"]["target"]),
                           float(data["shot"]["fov"]))
    assert data["records"] == len(records) == data["models"] and data["build_failures"] == []
    return {"data": data, "records": records, "shot": shot, "oracle": oracle_scene(records),
            "view": (float(data["view_size"][0]), float(data["view_size"][1])),
            "size": (float(scene.width_cm), float(scene.height_cm))}


def test_a_real_click_in_the_3d_window_selects_on_the_canvas_what_the_ray_meets(ws) -> None:
    """Gate G2's render row. The real ``Workspace`` on the real engine, sixty seeded
    ``QTest.mouseClick`` s on the ``QQuickView``: after each, the CANVAS has selected
    exactly the item the oracle's ray meets first — or nothing where it meets none."""
    data = ws["data"]
    assert data["plan_facts"] == {"groups": 0, "locked_layers": 0, "hidden_layers": 0,
                                  "not_selectable": 0}, "the oracle's first hit IS the 2D rule here"
    assert data["shot"]["fov"] == FOV_DEG
    agree = wrong = edge = nothing = 0
    items: set[str] = set()
    mistakes = []
    for click in data["clicks"]:
        assert click["view"] == data["view_size"], "the view kept its size through every selection"
        x, y = click["at"]
        answer, robust = robust_answer(ws["oracle"], ws["shot"], ws["view"], float(x), float(y))
        if not robust:
            edge += 1
            continue
        expected = [answer] if answer is not None else []
        if click["selected"] == expected:
            agree += 1
            nothing += answer is None
            items.update(expected)
        else:
            wrong += 1
            mistakes.append((click["at"], expected, click["selected"]))
    kinds = sorted({ws["records"][item_id].kind for item_id in items})
    print(f"\n[3D click] {agree}/{agree + wrong} clicks select what the ray meets ({edge} on a "
          f"silhouette edge not judged); {len(items)} different items of kinds {kinds}; "
          f"{nothing} on nothing")
    assert wrong == 0, mistakes
    assert agree >= 45 and len(items) >= 10 and nothing >= 3 and len(kinds) >= 4


def test_ctrl_and_shift_toggle_and_a_plain_click_replaces_in_the_real_window(ws) -> None:
    """The sequence that FAILED on the real engine before the card had a place of
    constant height (select A; Ctrl+click B cleared the selection, because the view had
    been resized under the pointer)."""
    mods = ws["data"]["modifiers"]
    a, b = mods["a"], mods["b"]
    for item_id, step in ((a, mods["steps"][0]), (b, mods["steps"][1])):
        answer, robust = robust_answer(ws["oracle"], ws["shot"], ws["view"],
                                       float(step["at"][0]), float(step["at"][1]))
        assert (answer, robust) == (item_id, True)
    assert a != b
    assert [(step["name"], step["selected"]) for step in mods["steps"]] == [
        ("plain_a", [a]), ("ctrl_b", sorted([a, b])), ("ctrl_b_again", [a]),
        ("shift_b", sorted([a, b])), ("plain_a_again", [a])]


def _diff_ring(run: Run, with_ring: dict[str, Any], without: dict[str, Any]) -> tuple[np.ndarray, float]:
    """Pixels that are ring-coloured in one frame and not in the other (the plan has a
    pond: blue alone is not the ring)."""
    selected, dpr = _frame(run, with_ring)
    cleared, _ = _frame(run, without)
    assert selected.shape == cleared.shape
    return mask_pixels(ring_mask(selected) & ~ring_mask(cleared)), dpr


def test_the_ring_of_the_clicked_item_is_in_the_workspaces_frame(run: Run, ws) -> None:
    ring_info = ws["data"]["ring"]
    assert ring_info["sent"] == [ring_info["id"]]
    record = ws["records"][ring_info["id"]]
    ring, dpr = _diff_ring(run, ring_info["selected"], ring_info["cleared"])
    outline = outline_pixels(perspective_outline(
        record, ws["shot"], ws["view"], record.transform.base_cm + RING_LIFT_CM, dpr))
    off = distances_to(ring, outline)
    covered = float((distances_to(outline, ring) <= (RING_WIDTH_PX + 1.5) * dpr).mean())
    print(f"\n[workspace ring] {record.kind}: {len(ring)} ring pixels, farthest from OUR outline "
          f"{off.max():.2f} px (mean {off.mean():.2f}), outline covered {covered:.1%}")
    assert len(ring) > 150
    assert float(off.max()) <= (RING_WIDTH_PX * MITRE_LIMIT + 1.5) * dpr
    assert covered >= 0.95


def test_no_selection_and_no_walk_resizes_the_real_view(run: Run, ws) -> None:
    """Every frame of the scenario — nothing selected, an item, the fullest card, 120
    selection changes, walking, back in orbit — has ONE size."""
    data = ws["data"]
    walk_rows = data["walk"]
    frames = [data["ring"]["selected"], data["ring"]["cleared"], data["timing"]["frame_after"],
              walk_rows["before"]["frame"], walk_rows["entered"]["frame"],
              walk_rows["walked"]["frame"], walk_rows["left"]["frame"]]
    sizes = {tuple(frame["size"]) for frame in frames}
    assert len(sizes) == 1, sizes
    assert {tuple(size) for size in data["card"]["view_sizes"]} == {tuple(data["view_size"])}
    width, height = next(iter(sizes))
    assert (width, height) == (round(data["view_size"][0] * frames[0]["dpr"]),
                               round(data["view_size"][1] * frames[0]["dpr"]))


def test_the_fullest_card_fits_its_place_in_the_desktops_font(ws) -> None:
    """The slot has three lines of facts. In the font the desktop really uses, at the
    3D pane's width in Split mode of a 1400 px window, the card with the most facts
    of any plant in the plan needs no more."""
    card = ws["data"]["card"]
    fullest = card["fullest"]
    lines = fullest["needed_px"] / fullest["line_px"]
    print(f"\n[card] font {card['font']!r}: {fullest['rows']} facts need {lines:.1f} lines at "
          f"{fullest['width_px']} px; the place has {fullest['has_px'] / fullest['line_px']:.1f} "
          f"({fullest['slot_px']} px in all)\n{fullest['text']}")
    assert fullest["visible"] is True and fullest["rows"] >= 5
    assert fullest["needed_px"] <= fullest["has_px"]
    assert card["hint"] == "Click an object to see what the 3D view shows of it."


def test_a_selection_reaches_the_real_engine_within_the_edit_budget(run: Run, ws) -> None:
    """Gate G8 on the real engine, with NO readback in the measured loop: from the
    canvas's ``setSelected`` to the end of the pass that handed the engine its ring
    (the real upload included, which the default tier's recording sink has not).
    120 changes; one frame is taken AFTER the loop, and the ring is in it."""
    timing = ws["data"]["timing"]
    before, after = timing["before"], timing["after"]
    print(f"\n[selection to the real engine] {timing['n']} changes: median {timing['median_ms']} "
          f"ms, p95 {timing['p95_ms']} ms, max {timing['max_ms']} ms; "
          f"{after['frames'] - before['frames']} frames presented meanwhile")
    # A change that did not reach the engine within two seconds is a MISS. One was seen,
    # once (WARP, the first run of this test: 119 of 120, and 121 ring loads instead of
    # 120), and never again in 3,240 changes on WARP and 480 on the GPU; what it was is
    # not known. The driver records every pass of a missed change — that is this message.
    assert timing["n"] == 120 and timing["misses"] == 0, timing["missed"]
    assert timing["p95_ms"] <= 50.0 * (3.0 if _software(run) else 1.0)
    # what 120 selection changes created and destroyed in the engine: nothing
    assert after["ring_loads"] - before["ring_loads"] == 120
    # (a count of the whole driver process: each host before this one made its one)
    assert after["ring_geometries"] == before["ring_geometries"] >= 1
    assert after["model_uploads"] == before["model_uploads"] and after["parts"] == before["parts"]
    record = ws["records"][timing["last"][0]]
    ring, dpr = _diff_ring(run, timing["frame_after"], ws["data"]["ring"]["cleared"])
    outline = outline_pixels(perspective_outline(
        record, ws["shot"], ws["view"], record.transform.base_cm + RING_LIFT_CM, dpr))
    assert len(ring) > 20 and float(np.median(distances_to(ring, outline))) <= RING_WIDTH_PX * dpr


def _engine(point: tuple[float, float, float]) -> list[float]:
    """Scene (E, N, up) as the engine holds it: x = E, y = up, z = -N."""
    return [point[0], point[2], -point[1]]


def test_walk_mode_in_the_real_workspace_borrows_the_camera_and_gives_it_back(run: Run, ws) -> None:
    """Gate G7's render row: real key events on the ``QQuickView``. Enter → the engine's
    camera is at the walker's eye; hold W → it walks at walking pace, straight ahead;
    a drag looks round and selects nothing; Escape → the engine's camera is the orbit
    camera's again, to the last digit, and the frame is the frame from before."""
    rows = ws["data"]["walk"]
    before, entered, walked, looked, left = (rows[name] for name in (
        "before", "entered", "walked", "looked", "left"))
    world = walk.build_world(ws["records"], *ws["size"], parts_of=builder_parts)
    start = tuple(entered["shown"])
    assert entered["walking"] is True and walk.is_free(world, *start)
    assert start == tuple(entered["orbit_target"]) and entered["yaw"] == entered["orbit_yaw"], (
        "where the orbit camera looked, facing the way it looked")
    yaw = math.radians(entered["yaw"])
    ahead = (math.sin(yaw), math.cos(yaw))
    eye = (start[0], start[1], entered["eye_cm"])
    assert entered["eye_cm"] == walk.EYE_HEIGHTS_CM[0]
    assert entered["camera"]["pos"] == pytest.approx(_engine(eye), abs=1e-3)
    assert entered["camera"]["target"] == pytest.approx(_engine((
        eye[0] + walk.LOOK_DISTANCE_CM * ahead[0], eye[1] + walk.LOOK_DISTANCE_CM * ahead[1],
        eye[2])), abs=1e-3)
    assert entered["camera"]["fov"] == walk.WALK_FOV_DEG and before["camera"]["fov"] == FOV_DEG
    # W, held: at walking pace, straight ahead
    moved = (walked["shown"][0] - start[0], walked["shown"][1] - start[1])
    distance = math.hypot(*moved)
    pace = distance / walked["held_s"]
    print(f"\n[walk] W held {walked['held_s']:.3f} s: {distance:.1f} cm = {pace:.1f} cm/s "
          f"(walking pace {walk.WALK_SPEED_CM_S}); yaw {entered['yaw']:.1f} deg")
    assert walked["moving_while_held"] is True and walked["moving_after"] is False
    assert 0.85 * walk.WALK_SPEED_CM_S <= pace <= 1.03 * walk.WALK_SPEED_CM_S
    assert moved[0] * ahead[0] + moved[1] * ahead[1] == pytest.approx(distance, rel=1e-6)
    assert walk.is_free(world, *walked["shown"])
    assert walked["camera"]["pos"] == pytest.approx(
        _engine((walked["shown"][0], walked["shown"][1], entered["eye_cm"])), abs=1e-3)
    # the drag: 60 px to the right is 18 degrees to the right, and no selection
    assert looked["yaw"] == pytest.approx(entered["yaw"] + 18.0)
    assert looked["selected"] == [] and looked["shown"] == walked["shown"]
    # Escape
    assert left["walking"] is False and left["action_checked"] is False
    assert left["pose_is_the_orbit_pose"] is True
    assert left["camera"] == before["camera"], "the engine's camera, to the last digit"
    assert left["books"] == before["books"] == {"undo": 0, "can_undo": False, "can_redo": False}
    orbit, _ = _frame(run, before["frame"])
    back, _ = _frame(run, left["frame"])
    at_eye, _ = _frame(run, entered["frame"])
    further, _ = _frame(run, walked["frame"])
    same = float(np.abs(orbit - back).mean())
    print(f"[walk] frames: orbit before vs after {same:.3f} mean abs difference; orbit vs the "
          f"walker's view {np.abs(orbit - at_eye).mean():.1f}; before vs after the walk "
          f"{np.abs(at_eye - further).mean():.1f}")
    assert same <= 1.5, "the orbit view is back (a leaf may have moved)"
    assert float(np.abs(orbit - at_eye).mean()) > 10.0, "walking is another view"
    assert float(np.abs(at_eye - further).mean()) > 1.0, "the walk moved the picture"


def test_hiding_and_showing_the_real_view_keeps_the_walker(ws) -> None:
    rows = ws["data"]["walk"]
    row, before = rows["hide_show"], rows["before"]
    assert row["there"] is not None and row["same_host"] is True
    assert row["hidden"] == {"walking": True, "moving": False, "shown": row["there"]}
    again = row["shown_again"]
    assert again["walking"] is True and again["shown"] == row["there"]
    assert again["camera"]["pos"] == pytest.approx(
        _engine((row["there"][0], row["there"][1], walk.EYE_HEIGHTS_CM[0])), abs=1e-3)
    assert row["left"]["walking"] is False and row["left"]["pose_is_the_orbit_pose"] is True
    assert row["left"]["camera"] == before["camera"] and row["left"]["books"] == before["books"]
    assert ws["data"]["health"]["ok"] is True


# ── the ring on the OpenGL backend (clip z runs -1..1 there) ─────────────────


def _ring_depth_on_opengl(folder: Path, qml_dir: Path | None = None) -> dict[str, Any]:
    """The ``ring_depth`` scenario with ``QSG_RHI_BACKEND=opengl`` (on Linux that is the
    tier's backend anyway; on Windows the tier runs on Direct3D 11 and this is the
    one row that does not)."""
    out = folder / "opengl"
    proc, result = run_selection_driver(out, "ring_depth", qml_dir=qml_dir,
                                        env=render_env(folder, QSG_RHI_BACKEND="opengl"))
    if result.get("status") != "ok" and "opengl" in (proc.stderr + str(result.get("error"))).lower():
        pytest.skip(f"no OpenGL backend on this machine: {result.get('error')}")
    assert proc.returncode == 0 and result.get("status") == "ok", failure_report(proc, out)
    scenario = result["scenarios"]["ring_depth"]
    assert scenario["graphics_api"] == "OpenGL", scenario["graphics_api"]
    record = driver.wall_record()
    shares = {}
    for name in ("in_front", "depth_tested"):
        rgb = load_rgb(out / scenario[name]["file"])
        dpr = float(scenario[name]["dpr"])
        outline = outline_pixels(top_down_outline(record, driver.RING_TOP,
                                                  (rgb.shape[1], rgb.shape[0]), dpr))
        ring = mask_pixels(ring_mask(rgb))
        shares[name] = (len(ring), float((distances_to(outline, ring) <= 4.0 * dpr).mean()))
    return {"shares": shares, "qt": result["qt_messages"], "adapter": result.get("adapter")}


def test_in_the_full_main_window_every_walkers_key_walks_and_no_shortcut_fires(run: Run) -> None:
    """Review 1, P0 and P1-2 on the real engine in the real ``GardenPlannerApp``: the
    Walk action gives the 3D view the keyboard; each walker's key, pressed into the window
    that HAS the keyboard, moves the walker (S too — it was the main window's Snap to
    Grid); no shortcut fires (Snap to Grid unchanged) and the plan's tool is untouched;
    Escape leaves walk mode and the keyboard goes back to the plan."""
    data = run[0]["scenarios"]["app_walk"]
    assert data["before"]["focus_widget"] == "CanvasView" and not data["before"]["focus_window_is_view"]
    assert "S" in data["window_shortcuts"], "the main window still has its S shortcut"
    assert data["entered"] == {"walking": True, "focus_window_is_view": True}
    least = min(key["moved_cm"] for key in data["keys"])
    print(f"\n[app walk] {len(data['keys'])} keys into the focus window: each moved the walker "
          f"{least:.1f} cm or more in {driver.APP_WALK_HOLD_MS} ms; snap {data['snap_before']} -> "
          f"{data['left']['snap']}; tool {data['tool_before']} -> {data['left']['tool']}")
    for key in data["keys"]:
        assert key["to_the_view"], key
        assert key["moved_cm"] > 0.25 * walk.WALK_SPEED_CM_S * driver.APP_WALK_HOLD_MS / 1000.0, key
        assert key["snap"] is data["snap_before"] and key["tool"] == data["tool_before"], key
    assert data["left"]["walking"] is False and data["left"]["focus_widget_is_canvas"] is True
    assert data["left"]["tool"] == data["tool_before"] and data["left"]["snap"] is data["snap_before"]


def test_the_ring_is_in_front_on_the_opengl_backend_too(tmp_path: Path) -> None:
    """Found by this row: "in front" was first written as ``POSITION.z *= uDepthScale``,
    which is right where clip z runs 0..1. On OpenGL (-1..1) it moves the ring to the
    MIDDLE of the depth range — behind the ground of the orthographic truth view: 0 ring
    pixels in every top-down frame. The shader now pulls towards ``NEAR_CLIP_VALUE``."""
    seen = _ring_depth_on_opengl(tmp_path)
    shares = seen["shares"]
    print(f"\n[ring depth, OpenGL on {seen['adapter']}] in front: {shares['in_front'][0]} px, "
          f"outline covered {shares['in_front'][1]:.1%}; depth-tested: "
          f"{shares['depth_tested'][0]} px, {shares['depth_tested'][1]:.1%}")
    assert seen["qt"]["counts"]["error"] == 0, seen["qt"]["errors"]
    assert shares["in_front"][1] >= 0.98
    assert shares["depth_tested"][1] <= 0.15


def test_plainly_scaled_clip_z_hides_the_ring_on_opengl(tmp_path: Path) -> None:
    """Positive control of the row above: the shader as it was first written."""
    qml = broken_qml_copy(
        tmp_path, "ring.vert",
        "POSITION.z = mix(NEAR_CLIP_VALUE * POSITION.w, POSITION.z, uDepthScale);",
        "POSITION.z *= uDepthScale;")
    shares = _ring_depth_on_opengl(tmp_path, qml)["shares"]
    print(f"\n[ring depth, OpenGL, clip z plainly scaled] in front: {shares['in_front'][0]} px, "
          f"outline covered {shares['in_front'][1]:.1%}")
    assert shares["in_front"][1] <= 0.05, "the old shader's ring is behind the ground there"


# ── the ring's shader: the judge is not deaf ─────────────────────────────────


def test_a_broken_ring_shader_is_heard_by_the_judge(tmp_path: Path) -> None:
    """Positive control for ``test_the_run_drew_with_no_qt_error…``. A shader that does
    not compile is only a Qt message and the frame still renders (exit code 0): the
    judge reads the driver's stderr and must find the error there, in the scenario
    that selected something."""
    qml = broken_qml_copy(tmp_path, "ring.vert", "POSITION.z, uDepthScale);",
                          "POSITION.z, uDepthScaleMissing);")
    out = tmp_path / "out"
    proc, result = run_selection_driver(out, "ring_depth", qml_dir=qml, env=render_env(tmp_path))
    assert proc.returncode == 0 and result["status"] == "ok", failure_report(proc, out)
    heard = result["qt_messages"]
    assert heard["by_scenario"]["ring_depth"]["error"] >= 1, heard
    assert any("shader" in line.lower() for line in heard["errors"])
