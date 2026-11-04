"""The walker on the two bench plans (Phase 17 L1.8, gate G5's long walk).

``bench_small.ogp`` and ``bench_large.ogp`` loaded into a real scene, their records
snapshotted and the walker's world built from them with the PRODUCTION builders —
picket fences, a 30 cm wall on a 5 cm stroke, hedges with their leaves, raised
beds, a house with its roof. A seeded random walk of 20,000 steps: after every one
of them the walker's circle touches no obstacle and lies inside the plan.

The judge is not the module's own index: ``Brute`` measures the distance from every
visited spot to EVERY obstacle segment (numpy, no grid) and decides "inside a
footprint" with a crossing count of its own over the records' posed rings.
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.scene3d import Record, pose_ring, walk
from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.core.scene3d.walk import (
    WALKER_RADIUS_CM,
    WalkCommand,
    WalkWorld,
    advance,
    build_world,
    start_state,
    turned,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.view3d.snapshot import snapshot_records

PLANS = Path(__file__).resolve().parents[1] / "fixtures" / "plans"
JUNE = date(2026, 6, 21)
R = WALKER_RADIUS_CM
STEPS = 20_000
TOL = 1e-6
REGISTRY = production_registry()


def load(name: str) -> tuple[dict[str, Record], float, float]:
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / name)
    return snapshot_records(scene, JUNE), float(scene.width_cm), float(scene.height_cm)


def parts_of(record: Record) -> Any:
    return REGISTRY.builder_for(record.kind)(record)


class Brute:
    """The independent judge: every segment for every spot, no index."""

    def __init__(self, world: WalkWorld, records: Mapping[str, Record]) -> None:
        self.world = world
        segments = world.segments.astype(np.float64)
        self.ax, self.ay = segments[:, 0], segments[:, 1]
        self.dx, self.dy = segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1]
        self.length2 = np.maximum(self.dx ** 2 + self.dy ** 2, 1e-30)
        self.min_x, self.max_x = segments[:, (0, 2)].min(axis=1), segments[:, (0, 2)].max(axis=1)
        self.min_y, self.max_y = segments[:, (1, 3)].min(axis=1), segments[:, (1, 3)].max(axis=1)
        #: per solid record and region: its rings (outer first), posed, as arrays
        self.regions: list[list[np.ndarray]] = []
        for record in records.values():
            if walk.is_solid(record):
                self.regions += [[np.array(pose_ring(record.transform, ring), float)
                                  for ring in (outer, *holes)] for outer, holes in record.regions]

    def clearance(self, points: np.ndarray, reach: float = 4.0 * R) -> np.ndarray:
        """For every row of ``points``: the distance to the nearest obstacle segment —
        exact up to ``reach``; ``inf`` where no segment is that near. (Points are
        judged in runs of 256; a run looks at every segment whose bounding box comes
        within ``reach`` of the run's own. No grid, no cells: a box test per run.)"""
        out = np.full(len(points), np.inf)
        for start in range(0, len(points), 256):
            run = points[start:start + 256]
            near = ((self.max_x >= run[:, 0].min() - reach) & (self.min_x <= run[:, 0].max() + reach)
                    & (self.max_y >= run[:, 1].min() - reach) & (self.min_y <= run[:, 1].max() + reach))
            if not near.any():
                continue
            ax, ay, dx, dy = self.ax[near], self.ay[near], self.dx[near], self.dy[near]
            px, py = run[:, 0, None], run[:, 1, None]
            along = np.clip(((px - ax) * dx + (py - ay) * dy) / self.length2[near], 0.0, 1.0)
            out[start:start + 256] = np.hypot(px - (ax + along * dx), py - (ay + along * dy)).min(axis=1)
        return out

    def inside(self, points: np.ndarray) -> np.ndarray:
        """For every row: inside the footprint (outer minus holes) of a solid record —
        an even-odd crossing count over all rings of a region."""
        x, y = points[:, 0], points[:, 1]
        hit = np.zeros(len(points), dtype=bool)
        for rings in self.regions:
            crossings = np.zeros(len(points), dtype=np.int64)
            for ring in rings:
                x1, y1 = ring[:, 0], ring[:, 1]
                x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
                for k in range(len(ring)):
                    if y1[k] == y2[k]:
                        continue
                    spans = (y1[k] > y) != (y2[k] > y)
                    at = (x2[k] - x1[k]) * (y - y1[k]) / (y2[k] - y1[k]) + x1[k]
                    crossings += spans & (x < at)
            hit |= crossings % 2 == 1
        return hit

    def free(self, points: np.ndarray) -> np.ndarray:
        world = self.world
        in_plan = ((points[:, 0] >= R - TOL) & (points[:, 0] <= world.width_cm - R + TOL)
                   & (points[:, 1] >= R - TOL) & (points[:, 1] <= world.depth_cm - R + TOL))
        return in_plan & (self.clearance(points) >= R - TOL) & ~self.inside(points)


@pytest.fixture(scope="module", params=["bench_small.ogp", "bench_large.ogp"])
def bench(request, qapp) -> dict[str, Any]:  # noqa: ARG001 - Qt for the scene
    records, width, depth = load(request.param)
    started = time.perf_counter()
    world = build_world(records, width, depth, parts_of=parts_of)
    return {"name": request.param, "records": records, "world": world,
            "build_ms": (time.perf_counter() - started) * 1000.0, "brute": Brute(world, records)}


def test_the_world_is_made_of_the_built_world_as_it_is_shown(bench) -> None:
    world, records = bench["world"], bench["records"]
    solids = {records[item_id].kind for item_id in world.solid_ids}
    assert solids and not solids & {"TREE", "SHRUB", "PERENNIAL"}, "plants are walked through in v0"
    assert solids <= walk.WALK_SOLID_KINDS
    footprint_only = build_world(records, world.width_cm, world.depth_cm)
    assert len(world.segments) > len(footprint_only.segments), "the shown meshes add to the footprints"
    assert world.solid_ids == footprint_only.solid_ids
    print(f"\n[walk world {bench['name']}] {len(records)} records, {len(world.solid_ids)} solid "
          f"({sorted(solids)}), {len(world.segments)} outline segments "
          f"({len(footprint_only.segments)} from footprints), grid {world.columns} x {world.rows} "
          f"of {world.cell_cm:.0f} cm, built in {bench['build_ms']:.0f} ms")
    assert bench["build_ms"] < 5000.0, "measured 116 ms and 257 ms"


def test_a_seeded_random_walk_of_20000_steps_never_leaves_free_ground(bench) -> None:
    """Gate G5: after EVERY step — where the walker is, and where it is shown — its
    circle touches no obstacle and lies inside the plan, by the brute-force judge.
    Measured: 841 m walked on the small plan and 945 m on the large one, 5,469 and
    3,664 of the 20,000 steps in contact with an obstacle."""
    world, brute = bench["world"], bench["brute"]
    rng = random.Random(385_108)
    state = start_state(world, (world.width_cm / 2.0, world.depth_cm / 2.0), 0.0)
    assert state is not None
    command = WalkCommand(forward=1.0)
    at = np.empty((STEPS + 1, 2))
    shown = np.empty((STEPS + 1, 2))
    at[0], shown[0] = (state.east, state.north), state.shown
    for step in range(1, STEPS + 1):
        if step % 29 == 1:
            command = WalkCommand(rng.choice((-1.0, 1.0, 1.0, 1.0, 1.0)),
                                  rng.choice((-1.0, 0.0, 0.0, 1.0)), rng.random() < 0.4)
            state = turned(state, rng.uniform(-150.0, 150.0), rng.uniform(-30.0, 30.0))
        state = advance(state, command, rng.choice((1 / 144, 1 / 60, 1 / 30, 0.05)), world)
        at[step], shown[step] = (state.east, state.north), state.shown
    for name, spots in (("is", at), ("is shown", shown)):
        free = brute.free(spots)
        bad = np.flatnonzero(~free)
        assert not len(bad), (f"{bench['name']}: after step {int(bad[0])} the walker {name} at "
                              f"{tuple(spots[bad[0]])}, {len(bad)} such steps")
    moved = np.hypot(*(shown[1:] - shown[:-1]).T)
    touching = int((brute.clearance(shown) < R + 0.05).sum())
    assert math.isinf(float(brute.clearance(np.array([[-1e7, -1e7]]))[0])), "far from everything"
    still = int((moved < 1e-9).sum())
    print(f"\n[random walk {bench['name']}] {STEPS} steps, {moved.sum() / 100.0:.0f} m walked, "
          f"{touching} steps in contact with an obstacle, {still} steps without movement")
    assert moved.sum() > 50_000.0, "it walked: more than half a kilometre"
    assert touching > 200, "and really along obstacles"
    assert still < STEPS * 0.25, "it was not trapped"
    # a push out of a corner can add a hair to a step (measured: 14.004 cm for 14.0): no leap
    assert float(moved.max()) <= 280.0 * 0.05 * 1.05, "no step is longer than its time allows"


def test_the_index_answers_as_the_brute_force_judge_does(bench) -> None:
    """The grid that finds the segments near the walker loses none: over 6,000 random
    spots ``walk.is_free`` and the judge agree, in the open and against the obstacles."""
    world, brute = bench["world"], bench["brute"]
    rng = np.random.default_rng(8)
    spots = np.stack([np.sort(rng.uniform(0.0, world.width_cm, 6000)),   # sorted: runs are slabs
                      rng.uniform(0.0, world.depth_cm, 6000)], axis=1)
    clearance = brute.clearance(spots)
    expected = brute.free(spots)
    judged = blocked = 0
    for (x, y), gap, free in zip(spots.tolist(), clearance.tolist(), expected.tolist(), strict=True):
        edge = min(x, y, world.width_cm - x, world.depth_cm - y)
        if abs(gap - R) < 1e-4 or abs(edge - R) < 1e-4:
            continue  # on the boundary of the decision: either answer is right
        assert walk.is_free(world, x, y) is free, (x, y, gap)
        judged += 1
        blocked += not free
    assert judged > 5500 and blocked > 100
