"""A real plan through the Qt Quick 3D engine, end to end (Phase 17 L1.2, #385 — §8.10).

``bench_small.ogp`` in a real scene → ``snapshot_records`` → ``SceneSync`` →
``Quick3DSink`` → the engine, then a scripted edit session through the app's own
commands (move, recolour, delete, undo). Two tiers, the same session:

- **Default tier** (``TestAgainstARecordingEngine``): the sink drives a
  list-backed ``EngineScene``. It proves everything up to the engine boundary —
  which Models the engine is asked for, with which pose, tint and bytes — on
  every machine, GPU or not.
- **Render tier** (``TestOnTheRealRenderer``, ``OGP_RENDER3D=1``): the same
  session on a real ``Quick3DHost``. After every step the Models are read back
  FROM THE QML SCENE and compared with what a ``RecordingSink`` was told, and
  the frames are checked for content. Plus gate G12: the host beside the 2D
  canvas does not move the main window onto RHI composition.

What only the render tier can show is that a Model appears on screen where it
should; ``test_quick3d_render.py`` pins that on small scenes.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import (
    ChangePropertyCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
)
from open_garden_planner.core.fill_patterns import create_pattern_brush
from open_garden_planner.core.scene3d import (
    RecordingSink,
    SceneSync,
    engine_buffers,
    engine_pose,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
from open_garden_planner.ui.view3d.snapshot import snapshot_records
from tests.integration.quick3d_render_driver import largest_solids
from tests.integration.quick3d_render_support import (
    failure_report,
    load_rgb,
    private_dirs,
    render_tier,
    run_driver,
)
from tests.unit.test_quick3d_adapter import FakeScene

PLAN = Path(__file__).resolve().parents[1] / "fixtures" / "plans" / "bench_small.ogp"
JUNE = date(2026, 6, 21)
SOFTWARE_ADAPTERS = ("basic render", "llvmpipe", "softpipe", "swiftshader", "lavapipe")


def _recolour(item: Any, colour: QColor) -> ChangePropertyCommand:
    """The properties panel's fill-colour edit."""
    def apply(target: Any, value: QColor) -> None:
        target.fill_color = value
        target.setBrush(create_pattern_brush(target.fill_pattern, value))

    return ChangePropertyCommand(item, "fill color", QColor(item.fill_color), colour, apply)


@pytest.fixture()
def private_app_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Loading a plan creates the app's per-user data directory (smart symbols, plant
    lists). This process must not create it in the developer's profile (review round
    2, P2-9): the variables it hangs on point into ``tmp_path`` for the test."""
    for name, target in private_dirs(tmp_path).items():
        monkeypatch.setenv(name, target)
    return tmp_path


class TestAgainstARecordingEngine:
    """The default-tier twin: the real pipeline up to the engine boundary."""

    def test_a_real_plan_and_an_edit_session(self, qtbot, private_app_data: Path) -> None:
        from open_garden_planner.services.plant_library import get_app_data_dir

        assert private_app_data in get_app_data_dir().parents, "the app's data directory is redirected"
        scene = CanvasScene()
        ProjectManager().load(scene, PLAN)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        commands = view.command_manager
        engine = FakeScene()
        quick = Quick3DSink(engine)
        pair: list[Any] = []

        def fresh_pipelines() -> None:
            recording = RecordingSink()
            pair[:] = [recording, SceneSync(quick, validate=True), SceneSync(recording, validate=True)]

        def tick() -> None:
            recording, *syncs = pair
            records = snapshot_records(scene, JUNE)
            for sync in syncs:
                sync.apply(records)
            assert quick.state() == recording.state()
            assert quick.state() == syncs[0].expected_state()  # incremental == full rebuild
            assert syncs[0].failures == {}
            expected = {}
            for item_id, held in recording.state().items.items():
                for index, part in enumerate(held.parts):
                    if part.mesh.vertex_count:
                        tint = held.material.tint_rgba if part.tinted else (255, 255, 255, 255)
                        expected[(item_id, index)] = (
                            part.material_kind, engine_pose(held.transform), tint,
                            part.casts_shadow, engine_buffers(part.mesh))
            held_by_engine = {
                (p.spec.item_id, p.spec.part_index):
                    (p.spec.kind, p.pose, p.tint, p.spec.casts_shadow, p.spec.buffers)
                for p in engine.parts}
            assert len(held_by_engine) == len(engine.parts), "two Models for one part"
            assert held_by_engine == expected

        fresh_pipelines()
        tick()
        # 98 records (a roof ridge has none: it is a param of its house), 11 of them flat
        assert len(quick.item_ids()) == 98 and len(engine.parts) == 87
        uploads = quick.geometry_uploads
        target, victim = largest_solids(scene, {p.spec.item_id for p in engine.parts})

        engine.calls.clear()
        commands.execute(MoveItemsCommand([target], QPointF(137.25, -42.5)))
        tick()
        # the house takes its roof ridge along (the app's own orchestration): poses only
        assert ("pose", str(target.item_id)) in engine.calls and engine.calls[-1] == ("frame",)
        assert {call[0] for call in engine.calls[:-1]} == {"pose"}

        engine.calls.clear()
        commands.execute(_recolour(target, QColor(250, 30, 200)))
        tick()
        assert engine.calls == [("tint", str(target.item_id)), ("frame",)]
        assert quick.geometry_uploads == uploads  # neither a move nor a recolour uploaded

        commands.execute(DeleteItemsCommand(scene, [victim]))
        tick()
        assert len(engine.parts) == 86
        commands.undo()
        tick()
        assert len(engine.parts) == 87 and quick.geometry_uploads == uploads + 1
        commands.undo()
        commands.undo()
        tick()

        quick.clear()  # a document change: the engine holds nothing …
        assert engine.parts == [] and engine.sun is None and engine.ground is None
        fresh_pipelines()
        tick()         # … and the same plan comes back complete
        assert len(engine.parts) == 87


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Path]:
    out = tmp_path_factory.mktemp("quick3d_engine")
    proc, result = run_driver(out, "integration,embed")
    assert proc.returncode == 0 and result.get("status") == "ok", failure_report(proc, out)
    return result, out


def _is_software(adapter: str | None) -> bool:
    """True for a software rasteriser the run NAMED. An unknown adapter is not one:
    a run that cannot say what it rendered on has no licence to skip a budget."""
    if not adapter:
        raise AssertionError(
            "the run did not name its graphics adapter (qt.rhi.general): a hardware budget "
            "can neither be asserted nor waived — fix the adapter readout, do not skip")
    return any(name in adapter.lower() for name in SOFTWARE_ADAPTERS)


def test_an_unknown_adapter_is_not_a_software_adapter() -> None:
    """Review P2-8: ``adapter is None`` used to count as software, so a run that lost the
    adapter line skipped both hardware budgets — green, with nothing measured."""
    assert _is_software("Microsoft Basic Render Driver") is True
    assert _is_software("llvmpipe (LLVM 15.0.7, 256 bits)") is True
    assert _is_software("NVIDIA GeForce RTX 4070") is False
    for unknown in (None, ""):
        with pytest.raises(AssertionError, match="did not name its graphics adapter"):
            _is_software(unknown)


def _key(part: dict[str, Any]) -> tuple[str, int]:
    return (part["id"], part["part"])


class TestOnTheRealRenderer:
    pytestmark = render_tier

    def test_the_engine_holds_exactly_what_the_recording_sink_would(
            self, run: tuple[dict[str, Any], Path]) -> None:
        """After EVERY step: the Models read back from the QML scene are the parts the
        ``RecordingSink`` was told about — same ids, part counts, kinds, poses, tints."""
        steps = run[0]["scenarios"]["integration"]["steps"]
        assert [step["name"] for step in steps] == [
            "0_open", "0_open_top", "1_move", "2_recolour", "3_delete", "4_undo_delete", "5_undo_all"]
        for step in steps:
            assert step["sink_state_equals_recording"], step["name"]
            assert step["build_failures"] == 0, step["name"]
            engine = {_key(part): part for part in step["engine_parts"]}
            expected = {_key(part): part for part in step["expected"]["parts"]}
            assert len(engine) == len(step["engine_parts"]), "two Models for one part"
            assert engine.keys() == expected.keys(), step["name"]
            for key, want in expected.items():
                got = engine[key]
                assert got["kind"] == want["kind"] and got["casts"] == want["casts"], (step["name"], key)
                assert got["geometry"] is True, (step["name"], key)
                assert got["tint"] == want["tint"], (step["name"], key)
                # QVector3D is float32: a plan coordinate of a few thousand cm is exact to ~1e-4
                assert got["position"] == pytest.approx(want["position"], abs=1e-2), (step["name"], key)
                assert got["yaw"] == pytest.approx(want["yaw"], abs=1e-3), (step["name"], key)
        first = steps[0]
        assert first["records"] == 98 and len(first["engine_parts"]) == 87

    def test_the_frame_shows_the_plan(self, run: tuple[dict[str, Any], Path]) -> None:
        result, out = run
        steps = {step["name"]: step for step in result["scenarios"]["integration"]["steps"]}
        perspective = load_rgb(out / steps["0_open"]["file"])
        assert len(np.unique(perspective.reshape(-1, 3), axis=0)) > 200  # a lit scene, not a clear
        top = load_rgb(out / steps["0_open_top"]["file"])
        bare = top[3:10, 3:10].reshape(-1, 3).mean(axis=0)     # a corner: meadow outside the plan
        assert bare[1] > 1.5 * bare[0] and bare[1] > 1.5 * bare[2]
        covered = (np.abs(top - bare).max(axis=2) > 25).mean()
        assert covered > 0.15, f"only {covered:.1%} of the top view is not bare ground"

    def test_the_edit_session_reaches_the_engine_as_minimal_changes(
            self, run: tuple[dict[str, Any], Path]) -> None:
        result, out = run
        integration = result["scenarios"]["integration"]
        steps = {step["name"]: step for step in integration["steps"]}
        moved, deleted = integration["ids"]["moved"], integration["ids"]["deleted"]

        def parts_of(step: str, item_id: str) -> list[dict[str, Any]]:
            return [part for part in steps[step]["engine_parts"] if part["id"] == item_id]

        # move: transforms only (the house takes its roof ridge along), no upload; the
        # Model is 137.25 cm further east and 42.5 cm further south
        move = steps["1_move"]["diff"]
        assert move["transform"] >= 1 and sum(move.values()) == move["transform"], move
        assert steps["1_move"]["uploads"] == steps["0_open_top"]["uploads"]
        before, after = parts_of("0_open", moved)[0], parts_of("1_move", moved)[0]
        delta = np.array(after["position"]) - np.array(before["position"])
        assert delta == pytest.approx([137.25, 0.0, 42.5], abs=1e-2)  # engine z = −north
        # recolour: one material, no upload, the tint is the new colour
        assert steps["2_recolour"]["diff"]["material"] == 1
        assert steps["2_recolour"]["uploads"] == steps["1_move"]["uploads"]
        assert all(part["tint"] == [250, 30, 200] for part in parts_of("2_recolour", moved))
        # delete and undo
        assert parts_of("3_delete", deleted) == [] and steps["3_delete"]["diff"]["removed"] == 1
        assert len(parts_of("4_undo_delete", deleted)) == len(parts_of("0_open", deleted)) >= 1
        assert steps["4_undo_delete"]["uploads"] == steps["3_delete"]["uploads"] + len(
            parts_of("0_open", deleted))
        # undo everything: the engine is where it started, and so is the picture
        assert sorted(steps["5_undo_all"]["engine_parts"], key=_key) == sorted(
            steps["0_open"]["engine_parts"], key=_key)
        first = load_rgb(out / steps["0_open"]["file"])
        last = load_rgb(out / steps["5_undo_all"]["file"])
        changed = load_rgb(out / steps["2_recolour"]["file"])
        assert float(np.abs(last - first).mean()) < 0.5
        assert float(np.abs(changed - first).mean()) > 0.05

    def test_an_edit_is_on_screen_within_the_frame_budget(
            self, run: tuple[dict[str, Any], Path]) -> None:
        """ADR-048 entries 5/6 (moved here by ADR-059): edit → snapshot → diff → engine →
        FINISHED READBACK. Measured on the dev box (RTX 4070, 98 records, 640 x 400):
        median 7.1 ms, p95 17.9 ms; WARP: median 23.2 ms. The bound is asserted on a
        hardware adapter only — a software rasteriser says nothing about a GPU."""
        result, _ = run
        timing = result["scenarios"]["integration"]["edit_to_readback_ms"]
        assert timing["n"] == 30
        if _is_software(result["adapter"]):
            pytest.skip(f"software rasteriser ({result['adapter']}): {timing}")
        assert timing["median"] <= 50.0, timing

    def test_the_host_beside_the_2d_canvas_keeps_the_window_off_rhi_composition(
            self, run: tuple[dict[str, Any], Path]) -> None:
        """G12 / ADR-048 criterion 3. Direct evidence: with the 3D container in the
        window the top-level surface stays a RASTER surface — and the control, a
        ``QQuickWidget`` in the same place, turns it into an RHI surface (measured
        on Windows: ``Direct3DSurface``)."""
        result, out = run
        embed = result["scenarios"]["embed"]
        for row in embed["rounds"]:
            assert row["surface"] == "RasterSurface", row
        assert embed["control"]["surface"] != "RasterSurface", embed["control"]
        frame = load_rgb(out / "embed_container.png")
        assert len(np.unique(frame.reshape(-1, 3), axis=0)) > 50  # the embedded view renders

    def test_the_2d_pan_step_costs_the_same_with_the_3d_container_visible(
            self, run: tuple[dict[str, Any], Path]) -> None:
        """G12 in milliseconds: median 2D pan step (incl. flush) with the container
        visible ≤ x1.3 of without. Measured on the dev box: 2.56 ms vs 2.63 ms (x0.97),
        WARP x0.92; the QQuickWidget control: x94–x99 there (monitor asleep — its
        presents wait for a display that is not refreshing)."""
        result, _ = run
        embed = result["scenarios"]["embed"]
        if _is_software(result["adapter"]):
            pytest.skip(f"software rasteriser ({result['adapter']}): ratio {embed['ratio']}")
        assert embed["ratio"] is not None and embed["ratio"] <= 1.3, embed
        assert embed["control_ratio"] > embed["ratio"], embed

    def test_the_plan_opens_in_a_reportable_time(self, run: tuple[dict[str, Any], Path]) -> None:
        """Not a budget (ADR-048 criterion 5 is judged on the owner's hardware in L1.3) — a
        tripwire that the numbers the report quotes exist and are sane: request → first
        finished readback of the 98-record plan, and the engine package's import."""
        result, _ = run
        integration = result["scenarios"]["integration"]
        assert 0.0 < integration["open_ms"] < 120_000.0, integration["open_ms"]
        assert 0.0 < result["engine_import_ms"] < 30_000.0
