"""Real-engine seasonal values on the same forged Models and uploaded buffers."""

from __future__ import annotations

import datetime
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np


def _runner_identity(host) -> dict:
    """#598: what a callback median was measured on - CPU, cores, Python, Qt, graphics
    API (the adapter's name is in Qt's own log: the test adds ``driver_messages``)."""
    import os
    import platform

    from PyQt6.QtCore import QT_VERSION_STR

    try:
        api = host.graphics_api()
    except Exception as error:  # noqa: BLE001 - an identity field, never a failure
        api = f"unknown ({error})"
    return {"cpu": platform.processor() or platform.machine(), "logical_cpus": os.cpu_count(),
            "platform": platform.platform(), "python": platform.python_version(),
            "qt": QT_VERSION_STR, "graphics_api": str(api)}


def _pixels(image) -> np.ndarray:
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    return np.frombuffer(bits, np.uint8).copy()


def _regrow_in_place(host, sink, record, before: np.ndarray, out: Path) -> dict:
    """#531: a forged tree regrown IN PLACE (LOD0 -> LOD1: its Models take the new
    buffers) draws exactly what the same parts draw in fresh Models. ADR-069 withdrew an
    in-place path that drew a replaced part as nothing while it still picked."""
    from open_garden_planner.core.plant_forge import LOD1, forge_record

    parts = forge_record(record, lod=LOD1)
    reused, destroyed = sink.models_reused, sink.models_destroyed
    sink.begin()
    sink.replace_geometry(record.item_id, parts)
    sink.commit()
    counts = {"regrow_reused": sink.models_reused - reused,
              "regrow_destroyed": sink.models_destroyed - destroyed,
              "regrow_models": sink.part_count(record.item_id)}
    image = host.grab("forge-regrow-in-place")
    assert image.save(str(out / "regrow_in_place.png"))
    in_place = _pixels(image)
    held = sink.item(record.item_id)
    sink.begin()
    sink.remove(record.item_id)
    sink.add(record.item_id, parts, held.transform, held.material)
    sink.commit()
    image = host.grab("forge-regrow-fresh")
    assert image.save(str(out / "regrow_fresh.png"))
    fresh = _pixels(image)
    return {**counts,
            "regrow_fresh_diff_channels": int(np.count_nonzero(in_place != fresh)),
            "regrow_changed_channels": int(np.count_nonzero(in_place != before))}


def main(out: Path, *, slow_refresh: bool = False) -> int:
    from open_garden_planner.core.scene3d import GroundSpec, SunState
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.core.scene3d.sync import SceneSync
    from open_garden_planner.ui.view3d.forge_worker import ForgeWorker
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost
    from open_garden_planner.ui.view3d.quick3d.offscreen import ensure_application
    from open_garden_planner.ui.view3d.quick3d.shots import TopDownShot
    from tests.integration.test_plant_forge_workspace import tree

    _app = ensure_application()
    out.mkdir(parents=True, exist_ok=True)
    record = tree()
    host = Quick3DHost((400, 300))
    sink = Quick3DSink(host)
    worker = ForgeWorker(sink, season_sink=host.set_plant_seasons)
    result = {}
    try:
        SceneSync(sink, production_registry()).apply(
            {record.item_id: record}, ground=GroundSpec(800., 800.),
            sun=SunState(elevation_deg=45., azimuth_deg=225.),
        )
        worker.submit_snapshot([record], force_lod=0, plan_date=datetime.date(2026, 7, 15))
        assert worker.drain() == [record.item_id]
        host.set_shot(TopDownShot(center=(0., 0.), px_per_cm=0.8))
        host.show()
        assert host.wait_ready(10.)
        shapes = sink.geometry_uploads
        model_ids = {id(part.model) for part in host._parts}
        images = []
        for name, day in (("summer", datetime.date(2026, 7, 15)),
                          ("winter", datetime.date(2026, 1, 15)),
                          ("summer_again", datetime.date(2026, 7, 15))):
            states = worker.scrub_date(day)
            image = host.grab("forge-season")
            assert image.save(str(out / f"{name}.png"))
            bits = image.constBits()
            bits.setsize(image.sizeInBytes())
            images.append(np.frombuffer(bits, np.uint8).copy())
            result[name] = states[record.item_id].leaf_density
        result["changed_channels"] = int(np.count_nonzero(images[0] != images[1]))
        result["restored_equal"] = bool(np.array_equal(images[0], images[2]))
        result["uploads_unchanged"] = sink.geometry_uploads == shapes
        result["models_unchanged"] = {id(part.model) for part in host._parts} == model_ids
        result.update(_regrow_in_place(host, sink, record, images[2], out))
        # Measure the production workspace admission route, including support
        # dependencies: the old evaluator-only probe missed a 500 ms search.
        from types import SimpleNamespace

        from open_garden_planner.ui.view3d.workspace import Workspace
        from tests.integration.test_plant_forge_workspace import climber_scene

        climber, fence = climber_scene()
        from dataclasses import replace

        # Every plant is in view, rather than 300 canopies at the same pose.
        records = [replace(climber, item_id=f"vine-{i}", transform=replace(
            climber.transform, east_cm=(i % 20 - 9.5) * 230.,
            north_cm=(i // 20 - 7) * 230.,
        )) for i in range(300)]
        from open_garden_planner.core.plant_forge import LOD2, enrich_climber_record, forge_record

        supports = [replace(fence, item_id=f"fence-{i}",
                            transform=replace(fence.transform, north_cm=i * 20.)) for i in range(100)]
        parts = forge_record(enrich_climber_record(climber, supports), lod=LOD2)
        sink.begin()
        for rec in records:
            sink.add(rec.item_id, parts, rec.transform, rec.material)
        sink.commit()
        # #598: where the callback's time goes - per stage, per sample. The QML hop is
        # timed around the host's own call into the scene; the rest of the season sink
        # is the Python marshalling; the rest of the callback is the worker's states.
        stage = {"sink_ms": 0.0, "qml_ms": 0.0}
        host_call = host._call

        def timed_call(name, *args):
            if name != "setPlantSeasons":
                return host_call(name, *args)
            begun = time.perf_counter()
            try:
                return host_call(name, *args)
            finally:
                stage["qml_ms"] += (time.perf_counter() - begun) * 1000.

        host._call = timed_call

        def season_sink(states):
            begun = time.perf_counter()
            if slow_refresh:
                # Negative control inside the actual production uniform hop.
                time.sleep(0.020)
            host.set_plant_seasons(states)
            stage["sink_ms"] += (time.perf_counter() - begun) * 1000.

        timing_worker = ForgeWorker(season_sink=season_sink)
        scene_records = {r.item_id: r for r in (*records, *supports)}
        controller = SimpleNamespace(sync=SimpleNamespace(records=scene_records),
                                     pass_date=datetime.date(2026, 7, 15))
        workspace = SimpleNamespace(
            _forge_worker=timing_worker, _controller=controller,
            _location=lambda: {"latitude": 52., "frost_dates": {}},
            _camera_now=lambda: ((0., 0., 10000.), (0., 0., 0.), 45.),
            _pane_is_showing=lambda: False,
        )
        Workspace._refresh_forge(workspace)
        for rec in records:
            assert timing_worker.apply_completed(rec.item_id, rec.geometry_sig, LOD2, parts)
        host.set_shot(TopDownShot(center=(0., 0.), px_per_cm=0.055))
        assert host.wait_ready(10.)
        days = (datetime.date(2026, 4, 15), datetime.date(2026, 6, 15),
                datetime.date(2026, 10, 15))
        # Fixed warm-up and frame settlement are outside the measured callback.
        for day in days:
            controller.pass_date = day
            Workspace._refresh_forge(workspace)
            host.grab("forge-budget-warm")
        shapes_before = sink.geometry_uploads
        models_before = {id(part.model) for part in host._parts}
        durations = {day.isoformat(): [] for day in days}
        stages = {day.isoformat(): {"states_ms": [], "marshal_ms": [], "qml_ms": []}
                  for day in days}
        # Predeclared samples, interleaved so every call changes the date. No
        # adaptive retries: gate the worst per-date median, and retain all tails.
        for _ in range(15):
            for day in days:
                host.grab("forge-budget-settle")
                stage["sink_ms"] = stage["qml_ms"] = 0.0
                started = time.perf_counter()
                controller.pass_date = day
                Workspace._refresh_forge(workspace)
                total = (time.perf_counter() - started) * 1000.
                durations[day.isoformat()].append(total)
                split = stages[day.isoformat()]
                split["states_ms"].append(total - stage["sink_ms"])
                split["marshal_ms"].append(stage["sink_ms"] - stage["qml_ms"])
                split["qml_ms"].append(stage["qml_ms"])
        medians = {day: statistics.median(values) for day, values in durations.items()}
        raw = [value for values in durations.values() for value in values]
        result["scrub300_ms"] = max(medians.values())
        result["scrub300_medians_ms"] = medians
        result["scrub300_samples_ms"] = durations
        result["scrub300_stage_medians_ms"] = {
            day: {name: round(statistics.median(values), 4) for name, values in split.items()}
            for day, split in stages.items()}
        result["scrub300_runner"] = _runner_identity(host)
        result["scrub300_models"] = host.part_count()
        result["scrub300_p95_ms"] = float(np.percentile(raw, 95))
        result["scrub300_max_ms"] = max(raw)
        result["scrub300_plants"] = len(records)
        result["scrub300_supports"] = len(supports)
        result["slow_refresh"] = slow_refresh
        result["scrub300_no_geometry_work"] = timing_worker.pending_count == 0
        result["scrub300_buffers_unchanged"] = sink.geometry_uploads == shapes_before
        result["scrub300_models_unchanged"] = {id(part.model) for part in host._parts} == models_before
        (out / "result.json").write_text(json.dumps(result), encoding="utf-8")
        timing_worker.shutdown()
    finally:
        worker.shutdown()
        host.close()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.quiet_windows import keep_windows_behind

    keep_windows_behind()  # run by hand: no start-up hook did this
    raise SystemExit(main(Path(sys.argv[1]), slow_refresh="--slow-refresh" in sys.argv[2:]))
