"""How long the 3D pipeline holds the GUI thread while it reads a huge plan (#452).

``snapshot_records`` used to run in one block: the first build of a plan cost the sum
of its items — measured 4.0 s, 5.4 s and 12.6 s for the three plans below, and 33 to
40 s for two hundred items at the per-item work bound (the issue's own numbers). It is
read in slices now (``snapshot_steps`` + ``CAPTURE_SLICE_MS``): the same records, one
item per step, between turns of the event loop.

What this measures is exactly that promise — the GUI HEARTBEAT. A 1 ms precise timer
runs on the main thread (the same thread the canvas, the paint and the tools live on)
while the controller reads the plan; each tick's arrival is stamped. The gaps between
ticks are how long the main thread was busy without answering: p95 and max, in ms.
The engine is NOT started (no Qt Quick 3D, no GPU): this is the pipeline's own GUI
work, which is what #452 was about. Engine startup is measured by the render tier, not
here.

Every fixture is built in memory from the issue's reproduction, so nothing is read
from or written to the owner's settings and data (``script_isolation``); it saves
nothing. From the repo root::

    venv/Scripts/python.exe scripts/measure_capture_heartbeat.py
    venv/Scripts/python.exe scripts/measure_capture_heartbeat.py --fixture fences-801

Prints one JSON line per fixture: the heartbeat percentiles, how many slices the read
took, its whole wall time, and the three numbers an unchanged plan then costs
(``second_pass_ms``: the read answered from the record layer's memories).
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # script_isolation, also under runpy
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")      # as CI's perf steps run

import script_isolation

TREE = Path(os.environ.get("OGP_MEASURE_TREE") or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0] = [str(TREE / "src"), str(TREE)]   # that tree's package, and its tests package

if __name__ == "__main__":
    script_isolation.isolate_profile()

from PyQt6.QtCore import QT_VERSION_STR, QEventLoop, QPointF, Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import open_garden_planner  # noqa: E402
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle  # noqa: E402
from open_garden_planner.core.scene3d import RecordingSink  # noqa: E402
from open_garden_planner.core.sim_clock import SimClock  # noqa: E402
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene  # noqa: E402
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem  # noqa: E402
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem  # noqa: E402
from open_garden_planner.ui.view3d.sync_controller import (  # noqa: E402
    CAPTURE_SLICE_MS,
    Scene3DController,
)

NOON = datetime.datetime(2026, 6, 21, 12, 0)
#: The issue's three reproduction plans, and the bound case: 200 items, each at the
#: per-item work bound. ``kind``: all polygons, or closed fences (a stroke to inflate).
FIXTURES: dict[str, tuple[str, int, int]] = {
    "polygons-1000": ("polygon", 160, 1_000),
    "polygons-100": ("polygon", 1_600, 100),
    "fences-801": ("fence", 110, 801),
    "bound-200": ("polygon", 200, 7_000),
}
#: What the issue measured for the same plans, in one block, before #452.
BASELINE_MS = {
    "polygons-1000": 4_000.0,
    "polygons-100": 5_400.0,
    "fences-801": 12_600.0,
    "bound-200": 35_000.0,
}


def _ring(cx: float, cy: float, radius: float, count: int) -> list[QPointF]:
    return [QPointF(cx + radius * math.cos(2.0 * math.pi * k / count),
                    cy + radius * math.sin(2.0 * math.pi * k / count))
            for k in range(count)]


def build(kind: str, count: int, vertices: int) -> CanvasScene:
    """The fixture, added to a canvas scene as the loader would leave it."""
    scene = CanvasScene()
    layer = scene.active_layer.id
    columns = max(1, int(math.ceil(math.sqrt(count))))
    for index in range(count):
        cx = 300.0 + (index % columns) * 900.0
        cy = 300.0 + (index // columns) * 900.0
        if kind == "fence":
            # a closed path: the last point is the first, so the stroke inflates to a
            # ring with a hole — the issue's "110 inflations, 110 cuts"
            points = _ring(cx, cy, 300.0, vertices - 1)
            points.append(points[0])
            scene.addItem(PolylineItem(points, object_type=ObjectType.FENCE,
                                       layer_id=layer,
                                       path_fence_style=PathFenceStyle.WOODEN_FENCE))
        else:
            scene.addItem(PolygonItem(_ring(cx, cy, 300.0, vertices),
                                      object_type=ObjectType.RAISED_BED,
                                      layer_id=layer))
    return scene


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def measure(name: str, kind: str, count: int, vertices: int, *, deadline_s: float) -> dict:
    scene = build(kind, count, vertices)
    clock = SimClock(NOON)
    sink = RecordingSink()
    controller = Scene3DController(scene, clock, lambda: None, sink)

    beats: list[float] = []
    heartbeat = QTimer()
    heartbeat.setTimerType(Qt.TimerType.PreciseTimer)
    heartbeat.setInterval(1)
    heartbeat.timeout.connect(lambda: beats.append(time.perf_counter()))

    loop = QEventLoop()
    applied: list[int] = []
    controller.applied.connect(
        lambda report: (applied.append(1), loop.quit()) if report.snapshot else None)
    QTimer.singleShot(int(deadline_s * 1000.0), loop.quit)

    heartbeat.start()
    started = time.perf_counter()
    controller.set_active(True)
    loop.exec()
    read_s = time.perf_counter() - started
    heartbeat.stop()

    gaps = [(later - earlier) * 1000.0 for earlier, later in zip(beats, beats[1:], strict=False)]
    if beats:
        # the TAIL matters as much as any gap: the last block (the lane's answer being
        # applied) is one nobody ticked through, and it is the one a user feels as a
        # frozen window ? a gap list that stops at the last beat would hide it
        gaps.append(read_s * 1000.0 - (beats[-1] - started) * 1000.0)
    slices = controller.capture_slices
    records = len(controller.sync.records)

    # … and what an unchanged plan costs afterwards: answered from memory
    second: list[float] = []
    for _ in range(3):
        controller.flush()
        start = time.perf_counter()
        controller.mark_dirty()
        controller.flush()
        second.append((time.perf_counter() - start) * 1000.0)

    controller.shutdown()
    scene.clear()
    return {
        "fixture": name,
        "items": count,
        "vertices": vertices,
        "capture_slice_ms": CAPTURE_SLICE_MS,
        "applied": len(applied),
        "prepared": controller.prepared_count,
        "records": records,
        "slices": slices,
        "read_s": round(read_s, 3),
        "baseline_block_ms": BASELINE_MS.get(name),
        "heartbeat_p50_ms": round(statistics.median(gaps), 2) if gaps else None,
        "heartbeat_p95_ms": round(_percentile(gaps, 0.95), 2) if gaps else None,
        "heartbeat_max_ms": round(max(gaps), 2) if gaps else None,
        "heartbeat_ticks": len(beats),
        "second_pass_ms": round(statistics.median(second), 2) if second else None,
        "python": sys.version.split()[0],
        "qt": QT_VERSION_STR,
        "version": open_garden_planner.__version__,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=sorted(FIXTURES), action="append",
                        help="only these fixtures (default: all)")
    parser.add_argument("--deadline", type=float, default=120.0,
                        help="give up on a fixture after this many seconds")
    options = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    names = options.fixture or sorted(FIXTURES)
    for name in names:
        kind, count, vertices = FIXTURES[name]
        print(json.dumps(measure(name, kind, count, vertices, deadline_s=options.deadline)),
              flush=True)
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
