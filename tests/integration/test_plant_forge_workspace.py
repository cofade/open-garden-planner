"""Plant Forge's real scheduling seam: background synthesis, dates and camera."""

from __future__ import annotations

import datetime
import json
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


def _run_forge_renderer(tmp_path):
    from tests.integration.quick3d_render_support import REPO, render_env, render_tier_skip_reason

    reason = render_tier_skip_reason()
    if reason:
        pytest.skip(reason)
    driver = Path(__file__).with_name("plant_forge_render_driver.py")
    proc = subprocess.run([sys.executable, str(driver), str(tmp_path)],
                          cwd=REPO, env=render_env(tmp_path), capture_output=True,
                          text=True, timeout=90)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-3000:]
    return json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))


def test_real_engine_scrubs_the_same_forged_models(tmp_path):
    result = _run_forge_renderer(tmp_path)
    assert result["summer"] == result["summer_again"] == 1.
    assert result["winter"] == 0.
    assert result["changed_channels"] > 3000
    assert result["restored_equal"]
    assert result["uploads_unchanged"] and result["models_unchanged"]


@pytest.mark.perf
def test_real_engine_scrubs_300_models_within_16ms(tmp_path):
    result = _run_forge_renderer(tmp_path)
    assert result["scrub300_ms"] <= 16.0, result
    assert result["scrub300_no_geometry_work"]
    assert result["scrub300_buffers_unchanged"] and result["scrub300_models_unchanged"]
