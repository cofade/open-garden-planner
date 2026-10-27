"""Measurements start at rest and read the meshes actually admitted to the engine."""

from types import SimpleNamespace

import pytest

from tests.integration.workspace_render_state import workspace_settled


@pytest.mark.parametrize("pending,timer,moving,dirty,ground", [
    (1, False, False, False, False), (0, True, False, False, False),
    (0, False, True, False, False), (0, False, False, True, False),
    (0, False, False, False, True), (0, False, False, False, False),
])
def test_rest_includes_forge_admission_and_camera_lod(pending, timer, moving, dirty, ground):
    workspace = SimpleNamespace(
        controller=SimpleNamespace(dirty=dirty, ground_owed=ground),
        camera=SimpleNamespace(moving=moving),
        _forge_worker=SimpleNamespace(pending_count=pending),
        _forge_timer=SimpleNamespace(isActive=lambda: timer),
    )
    assert workspace_settled(workspace) is not any((pending, timer, moving, dirty, ground))


def test_memory_sample_waits_for_presented_frames_without_readback(monkeypatch):
    from tests.integration import ground_bake_render_driver as driver

    now = [0.0]
    host = SimpleNamespace(frames_presented=0)
    asked = []
    host._view = SimpleNamespace(update=lambda: asked.append(host.frames_presented))

    def pump(ms):
        now[0] += ms / 1000.0
        # A busy first presentation takes 40 ms, well beyond the old 20 ms pump.
        if now[0] >= (host.frames_presented + 1) * 0.04:
            host.frames_presented += 1

    monkeypatch.setattr(driver.time, "perf_counter", lambda: now[0])
    monkeypatch.setattr(driver.base, "_pump", pump)
    assert driver.present_releases(host) == 2
    assert asked == [0, 1]


def test_memory_sample_does_not_wait_forever_on_a_display_that_presents_nothing(monkeypatch):
    from tests.integration import ground_bake_render_driver as driver

    now = [0.0]
    host = SimpleNamespace(frames_presented=0, _view=SimpleNamespace(update=lambda: None))
    monkeypatch.setattr(driver.time, "perf_counter", lambda: now[0])
    monkeypatch.setattr(driver.base, "_pump", lambda ms: now.__setitem__(0, now[0] + ms / 1000.0))
    assert driver.present_releases(host) == 0
    assert 0.5 <= now[0] <= 0.51


def test_oracle_exports_the_held_forge_mesh_instead_of_rebuilding_v0(tmp_path):
    from open_garden_planner.core.plant_forge import forge_record
    from open_garden_planner.core.scene3d.builders import production_registry
    from tests.integration.view3d_selection_driver import ring_records
    from tests.integration.workspace_render_state import load_held_oracle, save_held_oracle

    records = ring_records()
    registry = production_registry()
    held = {key: registry.build(record) for key, record in records.items()}
    v0 = sum(part.mesh.triangle_count for part in held["plant"])
    held["plant"] = forge_record(records["plant"], lod=0, cache=None)
    expected = sum(part.mesh.triangle_count for part in held["plant"])
    assert expected != v0, "the fixture must distinguish the two generations"
    sink = SimpleNamespace(item_ids=lambda: tuple(held),
                           item=lambda key: SimpleNamespace(parts=held[key]))
    workspace = SimpleNamespace(controller=SimpleNamespace(sync=SimpleNamespace(records=records, sink=sink)))
    workspace.host = SimpleNamespace(engine_parts=lambda: [
        SimpleNamespace(item_id=key, part_index=index, visible=True,
                        has_geometry=True, fade=1.0, drawn=1.0)
        for key, parts in held.items() for index, _part in enumerate(parts)])
    path = tmp_path / "oracle.npz"
    counts = save_held_oracle(workspace, path)
    scene = load_held_oracle(path)
    assert counts["plant"] == expected
    index = scene.item_ids.index("plant")
    assert int((scene.item == index).sum()) == expected


@pytest.mark.parametrize("accent", ["flowers", "fruits"])
def test_hidden_shadow_casting_seasonal_parts_are_excluded_without_changing_slots(tmp_path, accent):
    from dataclasses import replace

    from open_garden_planner.core.scene3d.builders import production_registry
    from tests.integration.view3d_selection_driver import ring_records
    from tests.integration.workspace_render_state import load_held_oracle, save_held_oracle

    record = ring_records()["plant"]
    visible = production_registry().build(record)[0]
    hidden = replace(visible, name=accent, casts_shadow=True)
    parts = (hidden, visible)
    sync = SimpleNamespace(records={"plant": record}, sink=SimpleNamespace(
        item_ids=lambda: ("plant",), item=lambda _key: SimpleNamespace(parts=parts)))
    host = SimpleNamespace(engine_parts=lambda: [
        SimpleNamespace(item_id="plant", part_index=index, visible=index == 1,
                        has_geometry=True, fade=1.0, drawn=1.0)
        for index in range(2)])
    path = tmp_path / "oracle.npz"
    save_held_oracle(SimpleNamespace(controller=SimpleNamespace(sync=sync), host=host), path)
    oracle = load_held_oracle(path)
    assert oracle.triangle_count == visible.mesh.triangle_count
    assert set(oracle.part) == {1}
    assert hidden.casts_shadow and not hidden.ground_detail, "the sink's part must remain untouched"


@pytest.mark.parametrize("eye,expected", [((0.2, 0.2, 10.0), "front"), ((0.2, 0.2, -10.0), "back")])
def test_qt611_selection_uses_front_faces_but_general_oracle_keeps_both(eye, expected):
    import numpy as np

    from open_garden_planner.core.scene3d.pick_oracle import PickScene, Ray, cast_all
    from tests.integration.workspace_render_state import front_facing_oracle

    scene = PickScene(("front", "back"), np.zeros((2, 3)),
                      np.array([[1., 0., 0.], [0., 1., 0.]]),
                      np.array([[0., 1., 0.], [1., 0., 0.]]),
                      np.array([0, 1]), np.array([0, 1]))
    ray = Ray(eye, (0., 0., -1. if eye[2] > 0 else 1.))
    assert {hit.item_id for hit in cast_all(scene, ray)} == {"front", "back"}
    selected = front_facing_oracle(scene, eye)
    assert [hit.item_id for hit in cast_all(selected, ray)] == [expected]
    assert scene.triangle_count == 2


def test_workspace_render_entry_restores_a_minimized_window(qtbot, monkeypatch):
    import ast
    from pathlib import Path

    from PyQt6.QtWidgets import QWidget

    # The hook's import installs an app-start rebinder. Execute its actual entry
    # function alone so this unit test cannot install that global child-process hook.
    source = Path(__file__).parents[1] / "integration/workspace_gate_hook.py"
    node = next(node for node in ast.parse(source.read_text(encoding="utf-8")).body
                if isinstance(node, ast.FunctionDef) and node.name == "_enter")
    namespace = {"Any": object, "_still_look": lambda: None}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)

    window = QWidget()
    qtbot.addWidget(window)
    window.showMinimized()
    assert window.isMinimized()
    entered = []
    action = SimpleNamespace(trigger=lambda: entered.append(not window.isMinimized()))
    window._workspace = SimpleNamespace(mode_actions=lambda: (action, action, action), look=None)
    namespace["_enter"](window, "split")
    assert entered == [True]


def test_workspace_soak_pump_delivers_deferred_deletion(qtbot):
    import ast
    import time
    from pathlib import Path

    from PyQt6 import sip
    from PyQt6.QtCore import QObject

    source = Path(__file__).parents[1] / "integration/workspace_gate_measure.py"
    node = next(node for node in ast.parse(source.read_text(encoding="utf-8")).body
                if isinstance(node, ast.FunctionDef) and node.name == "_pump")
    namespace = {"time": time}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    retired = QObject()
    retired.deleteLater()
    assert not sip.isdeleted(retired)
    namespace["_pump"](2)
    assert sip.isdeleted(retired), "a synchronous soak must emulate the outer loop's deferred deletes"
