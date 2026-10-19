"""Budgets of selection and walking in the 3D view (Phase 17 L1.8, gate G8).

Two numbers, each a median or a 95th percentile over many repetitions (another
pytest run may share the machine), with the conventions of
``tests/perf/test_scene3d_snapshot_budget.py`` — the ``perf`` marker, x3 on a CI
runner, a tripwire at x10 under a line tracer:

- **A walk step's collision resolve: median ≤ 0.5 ms on ``bench_large.ogp``** — one
  tick of the walker (``core/scene3d/walk.py``) in the world built from the plan's
  424 records with the production builders (32,548 outline segments). Measured on
  the dev box (Windows 11, Python 3.12.9, 2026-10-12, other suites running):
  0.021 to 0.029 ms median over all ticks of a seeded walk, 0.031 to 0.044 ms over
  the ticks an obstacle resolved (max 0.36 to 0.59 ms) — a tenth of the budget.
- **A selection change reaches the engine within the edit budget: p95 ≤ 50 ms on
  ``bench_small.ogp``** — from the canvas's ``setSelected`` to the pass that hands
  the engine the ring, in the real workspace (Split, the engine replaced by the
  recording sink: what is timed is everything BEFORE the engine — the canvas's own
  selection handling, the pass, the snapshot, the ring's mesh). Measured: 10.3 ms
  median, 14.9 ms p95, 37.7 ms max over 120 changes. The frame itself is the render tier's
  (``test_view3d_selection_render.py``).

What the second number no longer contains: until the workspace's plan revision the
canvas's repaint of a selected item was read as an edit — a whole-plan snapshot per
change (120 of 120, 2026-10-12). Since the revision a selection change is a ring-only
pass: no snapshot, asserted below (the repaints go to the quiet-time net, which finds
nothing — ``test_view3d_selection_workspace.py::test_a_canvas_selection_in_split_takes_no_snapshot``).
"""

from __future__ import annotations

import os
import random
import statistics
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QCoreApplication

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.core.scene3d.walk import (
    TICK_S,
    WALKER_RADIUS_CM,
    WalkCommand,
    advance,
    build_world,
    start_state,
    turned,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.view3d.snapshot import snapshot_records
from tests.integration.test_view3d_selection_workspace import SelectionBench
from tests.integration.test_view3d_workspace_widget import SPLIT
from tests.perf.test_scene3d_snapshot_budget import budget_factor, traced

PLANS = Path(__file__).resolve().parents[1] / "fixtures" / "plans"
JUNE = date(2026, 6, 21)
_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"

WALK_STEP_BUDGET_MS = 0.5
SELECTION_BUDGET_MS = 50.0


def factor() -> float:
    return budget_factor(is_traced=traced(), is_ci=_IS_CI)


@pytest.mark.perf
def test_a_walk_steps_collision_resolve_fits_its_budget_on_the_large_plan(qtbot) -> None:  # noqa: ARG001
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / "bench_large.ogp")
    records = snapshot_records(scene, JUNE)
    registry = production_registry()
    world = build_world(records, float(scene.width_cm), float(scene.height_cm),
                        parts_of=lambda record: registry.builder_for(record.kind)(record))
    assert len(records) == 424 and len(world.segments) > 20_000
    rng = random.Random(385)
    state = start_state(world, (world.width_cm / 2.0, world.depth_cm / 2.0), 0.0)
    assert state is not None
    command = WalkCommand(forward=1.0, run=True)
    every: list[float] = []
    blocked: list[float] = []
    for step in range(30_000):
        if step % 240 == 0:
            command = WalkCommand(rng.choice((-1.0, 1.0, 1.0)), rng.choice((-1.0, 0.0, 1.0)), True)
            state = turned(state, rng.uniform(-120.0, 120.0), 0.0)
        started = time.perf_counter()
        after = advance(state, command, TICK_S, world)          # exactly one tick
        took = (time.perf_counter() - started) * 1000.0
        every.append(took)
        expected = 280.0 * TICK_S
        walked = ((after.east - state.east) ** 2 + (after.north - state.north) ** 2) ** 0.5
        if walked < expected - 1e-6:                            # an obstacle or the edge resolved it
            blocked.append(took)
        state = after
    median, in_contact = statistics.median(every), statistics.median(blocked)
    print(f"\n[walk step] {len(every)} ticks on bench_large ({len(world.segments)} segments): "
          f"median {median:.4f} ms, p95 {sorted(every)[int(0.95 * len(every))]:.4f} ms; "
          f"{len(blocked)} ticks resolved against an obstacle: median {in_contact:.4f} ms, "
          f"max {max(blocked):.3f} ms")
    assert len(blocked) > 1000, "the walk met obstacles: free ticks alone would prove nothing"
    budget = WALK_STEP_BUDGET_MS * factor()
    assert median <= budget and in_contact <= budget
    assert WALKER_RADIUS_CM == 22.5


@pytest.mark.perf
def test_a_selection_change_reaches_the_engine_within_the_edit_budget(qtbot, tmp_path) -> None:
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / "bench_small.ogp")
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    bench = SelectionBench(view, qtbot, tmp_path)
    bench.open3d(SPLIT)
    controller = bench.workspace.controller
    records = controller.sync.records
    assert len(records) == 98
    items = [item for item in scene.items() if str(getattr(item, "item_id", "")) in records]
    rng = random.Random(8)
    rng.shuffle(items)
    applied: list[Any] = []
    controller.applied.connect(lambda report: applied.append((time.perf_counter(), report)))
    latencies: list[float] = []
    snapshots = 0
    for index in range(120):
        target = items[index % len(items)]
        wanted = (str(target.item_id),)
        scene.clearSelection()
        for _ in range(20):
            QCoreApplication.processEvents()
        applied.clear()
        started = time.perf_counter()
        target.setSelected(True)
        deadline = started + 2.0
        while bench.sink.selection.ids != wanted and time.perf_counter() < deadline:
            QCoreApplication.processEvents()
        assert bench.sink.selection.ids == wanted, "the ring reached the engine"
        told = next(at for at, _report in applied if at >= started)
        latencies.append((told - started) * 1000.0)
        snapshots += any(report.snapshot for _at, report in applied)
    ordered = sorted(latencies)
    p95 = ordered[int(0.95 * (len(ordered) - 1))]
    print(f"\n[selection to engine] {len(latencies)} changes on bench_small: median "
          f"{statistics.median(latencies):.2f} ms, p95 {p95:.2f} ms, max {ordered[-1]:.2f} ms; "
          f"{snapshots} of them rode a pass that took a snapshot")
    assert snapshots == 0, "a selection change reads nothing of the plan"
    assert p95 <= SELECTION_BUDGET_MS * factor()
