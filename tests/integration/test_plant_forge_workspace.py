"""Plant Forge's real scheduling seam: background synthesis, dates and camera."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from open_garden_planner.core.plant_forge import LOD0, LOD2, LOD2_TRIANGLE_BUDGET, ForgeCache
from open_garden_planner.core.scene3d import Material, Params, Record, RecordingSink, Transform
from open_garden_planner.ui.view3d import forge_worker as module
from open_garden_planner.ui.view3d.forge_worker import ForgeWorker


def tree(item_id: str = "oak") -> Record:
    return Record(
        item_id=item_id, kind="TREE", name="Oak", shape="circle",
        footprints=(((-100., -100.), (100., -100.), (100., 100.), (-100., 100.)),),
        transform=Transform(0., 0., 0., 0.), height_cm=400., material=Material("plant"),
        params=Params({"seed": item_id, "radius_cm": 100., "sprite_species": "Oak"}),
    )


def sink_for(record: Record) -> RecordingSink:
    sink = RecordingSink()
    sink.begin()
    sink.add(record.item_id, (), record.transform, record.material)
    sink.commit()
    return sink


def climber_scene():
    plant = replace(tree("jasmine"), kind="SHRUB", params=Params({
        "seed": "jasmine", "radius_cm": 100., "sprite_species": "Jasmine",
    }))
    fence = Record(item_id="fence", kind="FENCE", name="Fence", shape="polyline",
                   footprints=(), transform=Transform(),
                   path=((-200., 90.), (200., 90.)), path_width_cm=10.,
                   height_cm=200., material=Material("wood"))
    return plant, fence


def test_support_discovery_runs_on_the_background_thread(qtbot, monkeypatch):
    from open_garden_planner.core.plant_forge import climbers
    plant, fence = climber_scene()
    calls = []
    original = climbers.resolve_climber_support

    def observed(*args, **kwargs):
        calls.append(threading.get_ident())
        return original(*args, **kwargs)

    monkeypatch.setattr(climbers, "resolve_climber_support", observed)
    worker = ForgeWorker(sink_for(plant), cache=ForgeCache(), background=True)
    try:
        worker.submit_snapshot([plant, fence], force_lod=LOD2)
        assert calls == [], "support discovery held the GUI during snapshot admission"
        worker.step()
        qtbot.waitUntil(lambda: bool(worker.step()) or worker.pending_count == 0)
        assert calls and threading.get_ident() not in calls
    finally:
        worker.shutdown()


def test_date_only_snapshot_reuses_support_discovery(monkeypatch):
    from open_garden_planner.core.plant_forge import climbers
    plant, fence = climber_scene()
    worker = ForgeWorker(sink_for(plant), cache=ForgeCache())
    worker.submit_snapshot([plant, fence], force_lod=LOD2, plan_date=datetime.date(2026, 6, 21))
    worker.drain()

    def forbidden(*args, **kwargs):
        raise AssertionError("date-only snapshot repeated structural support discovery")

    monkeypatch.setattr(climbers, "resolve_climber_support", forbidden)
    worker.submit_snapshot([plant, fence], force_lod=LOD2, plan_date=datetime.date(2026, 10, 21))
    assert worker.pending_count == 0


def test_cached_support_keeps_new_height_and_seed(monkeypatch):
    from open_garden_planner.core.plant_forge import climbers
    plant, fence = climber_scene()
    resolutions, built = [], []
    resolve = climbers.resolve_climber_support

    def observed(*args, **kwargs):
        resolutions.append(True)
        return resolve(*args, **kwargs)

    def capture(record, **kwargs):
        built.append((record.height_cm, record.params["seed"], record.params["climber_support"]))
        return ()

    monkeypatch.setattr(climbers, "resolve_climber_support", observed)
    monkeypatch.setattr(module, "forge_record", capture)
    worker = ForgeWorker(sink_for(plant), cache=None)
    worker.submit_snapshot([plant, fence], force_lod=LOD2)
    worker.drain()
    changed = replace(plant, height_cm=500., params=Params(dict(plant.params, seed="new-seed")))
    worker.submit_snapshot([changed, fence], force_lod=LOD2)
    worker.drain()
    assert len(resolutions) == 1
    assert [(height, seed) for height, seed, _support in built] == [(400., "jasmine"), (500., "new-seed")]
    assert built[0][2] == built[1][2]


def test_a_support_move_rejects_an_inflight_result_with_unchanged_plant_geometry(qtbot, monkeypatch):
    plant, fence = climber_scene()
    sink = sink_for(plant)
    entered, release = threading.Event(), threading.Event()
    original = module.forge_record
    builds = []

    def held(record, **kwargs):
        builds.append(record.params["climber_support"])
        if len(builds) == 1:
            entered.set()
            assert release.wait(5)
        return original(record, **kwargs)

    monkeypatch.setattr(module, "forge_record", held)
    worker = ForgeWorker(sink, cache=ForgeCache(), background=True)
    try:
        worker.submit_snapshot([plant, fence], force_lod=LOD2)
        worker.step()
        qtbot.waitUntil(entered.is_set)
        moved = replace(fence, transform=Transform(0., -180.))
        worker.submit_snapshot([plant, moved], force_lod=LOD2)
        release.set()
        qtbot.waitUntil(lambda: worker._flight[2].done())
        assert worker.step() == []
        assert sink.item(plant.item_id).parts == ()
        qtbot.waitUntil(lambda: bool(worker.step()) or worker.pending_count == 0)
        assert len(builds) == 2 and builds[0] != builds[1]
        wood = next(p.mesh for p in sink.item(plant.item_id).parts if p.name == "wood")
        assert float(wood.positions[:, 1].mean()) < 0
    finally:
        release.set()
        worker.shutdown()


def test_background_forge_does_not_hold_the_gui_and_rejects_replaced_document(qtbot, monkeypatch):
    record = tree()
    sink = sink_for(record)
    entered, release = threading.Event(), threading.Event()
    original = module.forge_record

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "forge_record", held)
    worker = ForgeWorker(sink, cache=ForgeCache(), background=True)
    try:
        worker.submit_snapshot([record], force_lod=LOD2)
        assert worker.step() == []
        qtbot.waitUntil(entered.is_set)
        worker.clear()
        release.set()
        qtbot.waitUntil(lambda: worker.pending_count == 0 or bool(worker.step()))
        assert sink.item(record.item_id).parts == ()
    finally:
        release.set()
        worker.shutdown()


def test_season_only_scrub_updates_uniforms_without_rebuilding_or_uploading(monkeypatch):
    record = tree()
    sink = sink_for(record)
    states = []
    worker = ForgeWorker(sink, cache=ForgeCache(), season_sink=states.append)
    worker.submit_snapshot([record], force_lod=LOD2, plan_date=datetime.date(2026, 6, 21))
    assert worker.drain() == [record.item_id]
    parts = sink.item(record.item_id).parts

    def forbidden(*args, **kwargs):
        raise AssertionError("A season-only scrub must not synthesize geometry")

    monkeypatch.setattr(module, "forge_record", forbidden)
    worker.submit_snapshot([record], force_lod=LOD2, plan_date=datetime.date(2026, 1, 15))
    assert worker.pending_count == 0
    assert sink.item(record.item_id).parts is parts
    assert states[-1][record.item_id].leaf_density == 0


def test_v0_replacement_invalidates_applied_forge_and_camera_requeues_lod():
    record = tree()
    sink = sink_for(record)
    worker = ForgeWorker(sink, cache=ForgeCache())
    worker.submit_snapshot([record], force_lod=LOD0)
    worker.drain()
    assert sink.item(record.item_id).parts
    sink.begin()
    sink.replace_geometry(record.item_id, ())
    sink.commit()
    worker.invalidate([record.item_id])
    worker.submit_snapshot([record], force_lod=LOD0)
    assert worker.drain() == [record.item_id]
    worker.update_camera((0., 0., 10000.), force_lod=LOD2)
    assert worker.drain() == [record.item_id]
    assert sum(p.mesh.triangle_count for p in sink.item(record.item_id).parts) <= LOD2_TRIANGLE_BUDGET


def test_workspace_render_flags_use_the_production_worker(qtbot, monkeypatch, tmp_path):
    from open_garden_planner.core.commands import CreateItemCommand
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.view3d import workspace as workspace_module
    from open_garden_planner.ui.view3d.workspace import WorkspaceMode
    from tests.integration.test_view3d_workspace import build_app3d, first_pass

    window, engines = build_app3d(qtbot, monkeypatch, tmp_path)
    workspace = window._workspace
    # Replace the production factory with a recording engine at its documented seam.
    monkeypatch.setattr(workspace_module, "quick3d_engine", workspace.engine_factory)
    monkeypatch.setenv("OGP_RENDER3D", "1")
    monkeypatch.setenv("OGP_WORKSPACE_GATE_SCENARIO", "plant-forge")
    item = CircleItem(500., 500., 100., object_type=ObjectType.TREE,
                      metadata={"height_cm": 400.})
    item.plant_species = "Oak"
    window.canvas_view.command_manager.execute(CreateItemCommand(window.canvas_scene, item, "tree"))
    workspace.set_mode(WorkspaceMode.VIEW3D)
    first_pass(workspace, qtbot)
    worker = workspace._forge_worker
    assert worker is not None
    qtbot.waitUntil(lambda: worker.pending_count == 0, timeout=10000)
    assert {p.name for p in engines.sink.item(str(item.item_id)).parts} >= {"wood", "foliage"}
    workspace._apply_camera()
    assert worker._camera_forward is not None
    window.close()
    assert worker._closed


def test_live_regrowth_never_downgrades_forged_tree_to_v0_silhouette(qtbot, monkeypatch, tmp_path):
    """#995: stepping the plan date across the year on a growing forged tree updates seasonal
    uniforms on every date step and keeps a forged branch skeleton on every regrowth pass,
    never calling the v0 silhouette builder (which has only a branchless conical trunk)."""
    from open_garden_planner.core.commands import CreateItemCommand
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.core.scene3d.builders import plants as v0_plants
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.view3d import sync_controller
    from open_garden_planner.ui.view3d import workspace as workspace_module
    from open_garden_planner.ui.view3d.workspace import WorkspaceMode
    from tests.integration.test_view3d_workspace import build_app3d, first_pass
    from tests.integration.test_view3d_workspace_widget import wait_for_pipeline

    monkeypatch.setattr(sync_controller, "DATE_REGROW_MIN_MS", 0)
    window, engines = build_app3d(qtbot, monkeypatch, tmp_path)
    workspace = window._workspace
    monkeypatch.setattr(workspace_module, "quick3d_engine", workspace.engine_factory)

    window._sim_clock.set_date(datetime.date(2026, 1, 15))
    item = CircleItem(
        500.0,
        500.0,
        90.0,
        object_type=ObjectType.TREE,
        metadata={
            "plant_species": {
                "common_name": "Cherry Tree",
                "scientific_name": "Prunus avium",
                "max_height_cm": 450.0,
                "max_spread_cm": 360.0,
            },
            "plant_instance": {
                "planting_date": "2025-10-25",
                "current_height_cm": 220.0,
                "current_spread_cm": 180.0,
            },
        },
    )
    item.plant_species = "Cherry Tree"
    window.canvas_view.command_manager.execute(CreateItemCommand(window.canvas_scene, item, "tree"))
    workspace.set_mode(WorkspaceMode.VIEW3D)
    first_pass(workspace, qtbot)
    worker = workspace._forge_worker
    assert worker is not None
    qtbot.waitUntil(lambda: worker.pending_count == 0, timeout=10000)

    item_id = str(item.item_id)

    def sink_wood():  # the forge upgrade is a later event-loop turn than the first pass
        try:
            return next(p.mesh for p in engines.sink.item(item_id).parts if p.name == "wood")
        except (KeyError, StopIteration):
            return None

    qtbot.waitUntil(lambda: (wood := sink_wood()) is not None and wood.vertex_count > 100,
                    timeout=10000)
    forged_wood = sink_wood()
    assert forged_wood is not None and forged_wood.vertex_count > 100

    def forbid_v0_downgrade(_record):
        raise AssertionError("An already-forged growing tree was downgraded to a v0 silhouette")

    monkeypatch.setattr(v0_plants, "build_plant", forbid_v0_downgrade)

    # Step 1: small growth within the same 2 % bucket in winter (leaf_density == 0).
    window._sim_clock.set_date(datetime.date(2026, 1, 20))
    wait_for_pipeline(workspace, qtbot)
    assert worker.pending_count == 0
    winter_state = worker.phenology_state(item_id)
    assert winter_state is not None and winter_state.leaf_density == 0.0
    wood_jan = next(p.mesh for p in engines.sink.item(item_id).parts if p.name == "wood")
    assert wood_jan.vertex_count == forged_wood.vertex_count

    # Step 2: larger growth into a new 2 % bucket in spring bloom.
    window._sim_clock.set_date(datetime.date(2026, 4, 18))
    wait_for_pipeline(workspace, qtbot)
    wood_immediate = next(p.mesh for p in engines.sink.item(item_id).parts if p.name == "wood")
    assert wood_immediate.vertex_count >= 100
    qtbot.waitUntil(lambda: worker.pending_count == 0, timeout=10000)
    spring_state = worker.phenology_state(item_id)
    assert spring_state is not None and spring_state.bloom > 0.0
    window.close()


def test_toolbar_playback_holds_preset_defers_cache_release_and_skips_hidden_2d_shadows(
    qtbot, monkeypatch, tmp_path
):
    """#996: while toolbar Animate is active, AutoPreset is held, QQuickWindow cache releases
    are deferred, and in pure 3D mode (without the 2D shadow drape) 2D shadow polygon solves
    and heavy date diagnostics are deferred until playback stops or 2D is shown again."""
    from open_garden_planner.core.commands import CreateItemCommand
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.view3d import workspace as workspace_module
    from open_garden_planner.ui.view3d.workspace import WorkspaceMode
    from tests.integration.test_view3d_workspace import build_app3d, first_pass
    from tests.integration.test_view3d_workspace_widget import wait_for_pipeline

    window, engines = build_app3d(qtbot, monkeypatch, tmp_path)
    window._project_manager.set_location({"latitude": 52.52, "longitude": 13.405})
    window._sim_clock.set_time_of_day(datetime.time(12, 0))
    window._sun_controller.set_enabled(True)
    item = CircleItem(400.0, 400.0, 100.0, object_type=ObjectType.TREE, metadata={"height_cm": 300.0})
    window.canvas_view.command_manager.execute(CreateItemCommand(window.canvas_scene, item, "tree"))
    window._sun_controller.recompute_now()
    workspace = window._workspace
    workspace.set_mode(WorkspaceMode.VIEW3D)
    first_pass(workspace, qtbot)
    wait_for_pipeline(workspace, qtbot)

    look = workspace.look
    assert look is not None
    monkeypatch.setattr(workspace_module, "RELEASE_AFTER_RETIRED", 1)
    monkeypatch.setattr(workspace_module, "RELEASE_NOW_RETIRED", 2)

    shadow_solves_before = window._sun_controller.recompute_count
    window._sun_toolbar.set_animation_active(True)
    assert look._preset_held is True
    assert window.canvas_scene.is_animating_timeline is True

    # Even with retired above both thresholds, active playback must not trigger a 5 s cache release.
    workspace._retired = 10
    workspace._applied_at = 0.0
    workspace._poll_health()
    assert engines.host.releases == 0

    # Advancing the date in pure VIEW3D mode skips the 2D shadow polygon solve and defers date surfaces.
    window._sim_clock.set_date(datetime.date(2026, 5, 10))
    assert window._sun_controller.recompute_count == shadow_solves_before
    assert window._date_diagnostics_deferred is True

    # Stopping playback releases the preset hold, flushes deferred date diagnostics, and lets
    # the next health poll release retired engine caches.
    window._sun_toolbar.set_animation_active(False)
    assert look._preset_held is False
    assert window.canvas_scene.is_animating_timeline is False
    assert window._date_diagnostics_deferred is False
    workspace._poll_health()
    assert engines.host.releases == 1

    # Switching back to SPLIT immediately flushes the deferred 2D shadow solve.
    workspace.set_mode(WorkspaceMode.SPLIT)
    assert window._sun_controller.recompute_count > shadow_solves_before
    window.close()


def _run_forge_renderer(tmp_path, *, slow_refresh=False):
    from tests.integration.quick3d_render_support import (
        REPO,
        driver_messages,
        render_env,
        render_tier_skip_reason,
    )

    reason = render_tier_skip_reason()
    if reason:
        pytest.skip(reason)
    driver = Path(__file__).with_name("plant_forge_render_driver.py")
    arguments = [sys.executable, str(driver), str(tmp_path)]
    if slow_refresh:
        arguments.append("--slow-refresh")
    proc = subprocess.run(arguments,
                          cwd=REPO, env=render_env(tmp_path), capture_output=True,
                          text=True, timeout=90)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-3000:]
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    result["qt"] = driver_messages(proc.stderr)
    assert result["qt"]["counts"]["error"] == result["qt"]["counts"]["warning"] == 0, result["qt"]
    artifacts = os.environ.get("OGP_RENDER3D_ARTIFACTS")
    if artifacts:
        directory = Path(artifacts)
        directory.mkdir(parents=True, exist_ok=True)
        name = "plant-forge-budget-slow.json" if slow_refresh else "plant-forge-budget.json"
        (directory / name).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def test_real_engine_scrubs_the_same_forged_models(tmp_path):
    result = _run_forge_renderer(tmp_path)
    assert result["summer"] == result["summer_again"] == 1.
    assert result["winter"] == 0.
    assert result["changed_channels"] > 3000
    assert result["restored_equal"]
    assert result["uploads_unchanged"] and result["models_unchanged"]


def test_a_forged_tree_regrown_in_place_draws_what_a_fresh_build_draws(tmp_path):
    """#531 on the engine: LOD0 -> LOD1 keeps the tree's Models (their geometry objects
    take the new buffers) and the frame equals the frame of fresh Models with the same
    parts, channel for channel. ADR-069 withdrew an in-place path that drew nothing."""
    result = _run_forge_renderer(tmp_path)
    assert result["regrow_reused"] >= 2 and result["regrow_reused"] == result["regrow_models"]
    assert result["regrow_destroyed"] == 0, result
    assert result["regrow_changed_channels"] > 1000, "LOD1 must look different from LOD0"
    assert result["regrow_fresh_diff_channels"] == 0, result


def _run_far_renderer(tmp_path):
    from tests.integration.quick3d_render_support import (
        REPO,
        driver_messages,
        render_env,
        render_tier_skip_reason,
    )

    reason = render_tier_skip_reason()
    if reason:
        pytest.skip(reason)
    driver = Path(__file__).with_name("plant_forge_far_driver.py")
    proc = subprocess.run([sys.executable, str(driver), str(tmp_path)],
                          cwd=REPO, env=render_env(tmp_path), capture_output=True,
                          text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-3000:]
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    result["qt"] = driver_messages(proc.stderr)
    assert result["qt"]["counts"]["error"] == result["qt"]["counts"]["warning"] == 0, result["qt"]
    return result


def test_a_far_crop_and_a_dormant_bulb_render(tmp_path):
    """#948/#963 on the engine: a 4.2 m cherry at 45 m keeps a pink crop in bloom and a
    red one at ripeness (pixels the without-crop frame does not have); a tulip's April
    plant is gone by July, when only its 2.5 cm neck remains."""
    result = _run_far_renderer(tmp_path)
    assert result["cherry_bloom_crop_pixels"] >= 30, result
    assert result["cherry_fruit_crop_pixels"] >= 20, result
    assert result["cherry_bloom_crop_pixels"] <= result["cherry_bloom_changed_pixels"]
    assert result["cherry_fruit_crop_pixels"] <= result["cherry_fruit_changed_pixels"]
    assert result["tulip_april_leaf_density"] == 1.0 and result["tulip_april_bloom"] == 1.0
    assert result["tulip_july_leaf_density"] == 0.0 and result["tulip_july_bloom"] == 0.0
    assert result["tulip_april_pixels"] > 200, result
    assert result["tulip_july_pixels"] <= 0.05 * result["tulip_april_pixels"], result


#: The 16 ms budget of the 300-plant scrub callback (§8.29.11), on every adapter.
#: CI's software rasterisers measured 16.1-21.8 ms across runners and PR #596 gated
#: them at 25 ms instead; #598 made the callback itself cheaper (the season values
#: cross as one float64 buffer, the scene visits only the seasonal parts and writes
#: only what changed): worst date medians on the dev box fell from 13.2-13.8 to
#: 5.9-6.3 ms (RTX 4070) and from 14.0-15.3 to 6.8-7.6 ms (WARP), three runs each.
#: So CI is held to the documented 16 ms again. The 20 ms negative control stays
#: above it.
FRAME_BUDGET_MS = 16.0


@pytest.mark.perf
@pytest.mark.parametrize("slow_refresh", (False, True), ids=("production", "negative-control"))
def test_real_engine_scrubs_300_models_within_frame_budget(tmp_path, slow_refresh):
    budget = FRAME_BUDGET_MS
    result = _run_forge_renderer(tmp_path, slow_refresh=slow_refresh)
    assert result["scrub300_plants"] == 300 and result["scrub300_supports"] == 100
    assert len(result["scrub300_samples_ms"]) == 3
    assert all(len(values) == 15 for values in result["scrub300_samples_ms"].values())
    if slow_refresh:
        assert result["scrub300_ms"] > budget, "the gate missed a deterministic 20 ms uniform-hop delay"
        assert all(value >= 20. for values in result["scrub300_samples_ms"].values() for value in values)
    else:
        assert result["scrub300_ms"] <= budget, result
    assert result["scrub300_no_geometry_work"]
    assert result["scrub300_buffers_unchanged"] and result["scrub300_models_unchanged"]
