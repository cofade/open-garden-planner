"""Reproduce all five audit performance workloads without changing user settings.

Use --frozen dist/OpenGardenPlanner/OpenGardenPlanner.exe for the real artifact.
Timing data is reported with all samples, never treated as a universal CI limit.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))


import script_isolation  # noqa: E402

if __name__ == "__main__":
    script_isolation.isolate_profile()

# Match the product's required WebEngine-before-QApplication import order.
import open_garden_planner.main  # noqa: E402,F401


def summarize(samples: list[float]) -> dict[str, Any]:
    return {"samples_ms": samples, "median_ms": statistics.median(samples),
            "min_ms": min(samples), "max_ms": max(samples)}


def resident_bytes() -> int:
    """Current RSS, using the same native counter layout as the workspace gate."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        api = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        api.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.WorkingSetSize)
    if sys.platform.startswith("linux"):
        return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    raise RuntimeError("RSS measurement is supported on Windows and Linux")


def startup_runs(command: list[str], directory: Path, rounds: int) -> list[dict[str, Any]]:
    samples = []
    for index in range(rounds):
        report = directory / f"startup-{index}.json"
        started = time.perf_counter()
        subprocess.run([*command, "--benchmark-startup", str(report)],
                       check=True, timeout=90, cwd=ROOT)
        data = json.loads(report.read_text(encoding="utf-8"))
        data["launch_to_usable_ms"] = (data.pop("finished_perf_counter") - started) * 1000
        if not data["usable_window"]:
            raise RuntimeError("startup did not reach a painted usable window")
        samples.append(data)
    return samples


def measure(rounds: int, idle_seconds: float) -> dict[str, Any]:
    # Import order mirrors main: WebEngine is imported before QApplication exists.
    from PyQt6.QtCore import QT_VERSION_STR
    from PyQt6.QtGui import QImageReader
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.config.settings import get_settings
    from open_garden_planner.services.export_service import ExportService
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
    from open_garden_planner.ui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    settings = get_settings()
    settings.show_welcome_on_startup = False
    settings.agent_api_enabled = False
    apply_theme(app, settings.theme_mode)
    window = GardenPlannerApp()
    window.resize(1600, 1000)
    window.show()
    plan = ROOT / "tests/fixtures/plans/audit-2026-10-plan_500.ogp"
    loads, saves, exports = [], [], []
    dimensions = None
    with tempfile.TemporaryDirectory(prefix="ogp-perf-output-") as temporary:
        target = Path(temporary)
        for _ in range(rounds):
            started = time.perf_counter()
            window._load_project_file(str(plan))
            loads.append((time.perf_counter() - started) * 1000)
            QApplication.processEvents()
            started = time.perf_counter()
            window._project_manager.save(window.canvas_scene, target / "saved.ogp")
            saves.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            ExportService.export_to_png(window.canvas_scene, target / "a3.png",
                                        dpi=300, output_width_cm=42.0)
            exports.append((time.perf_counter() - started) * 1000)
            size = QImageReader(str(target / "a3.png")).size()
            dimensions = [size.width(), size.height()]
            QApplication.processEvents()
        window.canvas_view.fit_in_view()
        QTest.qWait(2000)
        frames = []
        for _ in range(15):
            started = time.perf_counter()
            window.canvas_view.viewport().repaint()
            frames.append((time.perf_counter() - started) * 1000)
        counts = {"scene_changed": 0, "minimap_renders": 0}
        def changed(_regions: Any) -> None:
            counts["scene_changed"] += 1
        window.canvas_scene.changed.connect(changed)
        original = window._minimap._do_update
        def update() -> None:
            counts["minimap_renders"] += 1
            original()
        window._minimap._update_timer.timeout.disconnect()
        window._minimap._update_timer.timeout.connect(update)
        rss_before = resident_bytes()
        QTest.qWait(int(idle_seconds * 1000))
        idle = {**counts, "seconds": idle_seconds, "rss_before_bytes": rss_before,
                "rss_after_bytes": resident_bytes()}
        # Same item workload, only batching differs. Rank/undo correctness is #450's gate.
        bulk = {}
        for count in [100, 500]:
            for batched in [False, True]:
                scene = CanvasScene()
                items = [RectangleItem(i * 2, 0, 1, 1) for i in range(count)]
                started = time.perf_counter()
                if batched:
                    with scene.suspend_z_refresh():
                        for item in items:
                            scene.addItem(item)
                else:
                    for item in items:
                        scene.addItem(item)
                bulk[f"{count}-{'batch' if batched else 'direct'}"] = (
                    time.perf_counter() - started) * 1000
                scene.clear()
        report = {
            "platform": platform.platform(), "processor": platform.processor(),
            "python": platform.python_version(), "qt": QT_VERSION_STR,
            "qt_platform": app.platformName(), "coverage": sys.gettrace() is not None,
            "plan": plan.relative_to(ROOT).as_posix(),
            "load": summarize(loads), "save": summarize(saves),
            "png_300dpi_width42cm": {**summarize(exports), "pixels": dimensions},
            "fit_repaint": summarize(frames), "idle": idle,
            "multi_add_ms": bulk, "pid": os.getpid(),
        }
    window._project_manager.mark_clean()
    window.close()
    return report


def main() -> int:
    script_isolation.isolate()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--idle-seconds", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1 or args.idle_seconds <= 0:
        parser.error("rounds and idle seconds must be positive")
    with tempfile.TemporaryDirectory(prefix="ogp-startup-reports-") as temporary:
        command = [str(args.frozen.resolve())] if args.frozen else [
            sys.executable, "-m", "open_garden_planner"]
        report = {"startup": startup_runs(command, Path(temporary), args.rounds),
                  "workloads": measure(args.rounds, args.idle_seconds)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote measured results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
