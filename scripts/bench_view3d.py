"""CPU-side 3D pipeline benchmark on the committed bench plans (Phase 17, L0).

Prints JSON per plan: plan load time, the shipped Qt3D-era snapshot
(``collect_scene3d_records``), and the Qt Quick 3D spike's procedural mesh
build (items, models, triangles, per-kind milliseconds) — no GPU needed, so it
runs anywhere and makes CPU regressions visible in every 3D PR. GPU metrics
(first frame, fps per preset, graphics API) come from
``python -m open_garden_planner --spike-q3d`` (metrics.json).

Usage::

    venv/bin/python scripts/bench_view3d.py [--plans bench_small,bench_large] [--repeat 3]

Loading a plan records it in Recent Files, so ``main()`` points every settings
store at the spike's throwaway key before anything builds one (senior review:
each run used to push two of the user's real recent files out of the list).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))


def main(argv: list[str] | None = None) -> int:
    from open_garden_planner.spike_q3d.runner import _isolate_settings

    _isolate_settings()  # before any store exists — see the module docstring
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--plans", default="bench_small,bench_large")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args(argv)

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.spike_q3d.runner import build_models
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.view3d.snapshot import collect_scene3d_records

    at = date(2026, 6, 21)
    report: dict = {"python": sys.version.split()[0], "plans": {}}
    for name in args.plans.split(","):
        path = REPO / "tests" / "fixtures" / "plans" / f"{name}.ogp"
        scene = CanvasScene()
        t0 = time.perf_counter()
        ProjectManager().load(scene, path)
        load_ms = (time.perf_counter() - t0) * 1000
        snap, build, stats = [], [], None
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            records = collect_scene3d_records(scene, at_date=at)
            snap.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            _models, stats = build_models(scene, at, 110.0, True,
                                          make_model=lambda i, m, k, _c: (i, k, m.triangle_count))
            build.append((time.perf_counter() - t0) * 1000)
        report["plans"][name] = {
            "load_ms": round(load_ms, 1),
            "qt3d_snapshot_ms_median": round(statistics.median(snap), 1),
            "qt3d_records": len(records),
            "spike_build_ms_median": round(statistics.median(build), 1),
            "spike_items": stats.items, "spike_models": stats.models,
            "spike_triangles": stats.triangles,
            "spike_by_kind_ms": {k: round(v, 1) for k, v in sorted(stats.build_ms.items())},
        }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
