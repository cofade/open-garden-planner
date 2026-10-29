"""Opt-in startup measurement on the real source or frozen entry point (A9).

The probe uses an isolated settings identity and exits after a painted event-loop
turn. It does not disable or substitute any construction or theme work.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_garden_planner.app.application import GardenPlannerApp


class StartupProbe:
    def __init__(self, path: Path, started: float) -> None:
        self.path = path
        self.started = started
        self.stages: dict[str, float] = {}

    def mark(self, name: str) -> None:
        self.stages[name] = (time.perf_counter() - self.started) * 1000

    def finish(self, window: GardenPlannerApp) -> None:
        from PyQt6.QtCore import QT_VERSION_STR
        from PyQt6.QtWidgets import QApplication

        from open_garden_planner.config.settings import create_qsettings

        viewport = window.canvas_view.viewport()
        if viewport is None:
            raise RuntimeError("startup canvas has no viewport")
        viewport.repaint()
        self.mark("painted_event_loop")
        visible = window.isVisible() and viewport.isVisible()
        report = {
            "frozen": bool(getattr(sys, "frozen", False)),
            "platform": platform.platform(), "processor": platform.processor(),
            "python": platform.python_version(), "qt": QT_VERSION_STR,
            "qt_platform": os.environ.get("QT_QPA_PLATFORM", "native"),
            "pid": os.getpid(), "usable_window": visible, "stages_ms": self.stages,
            "definition": "shown canvas, synchronous repaint, first event-loop callback",
            "cache": "filesystem cache uncontrolled; repeated fresh processes",
            "finished_perf_counter": time.perf_counter(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        window.close()
        store = create_qsettings()
        store.clear()
        store.sync()
        QApplication.exit(0 if visible else 1)


def start_probe(arguments: list[str], started: float) -> StartupProbe | None:
    if "--benchmark-startup" not in arguments:
        return None
    index = arguments.index("--benchmark-startup")
    if index + 1 >= len(arguments):
        raise ValueError("--benchmark-startup requires a JSON report path")
    from PyQt6.QtCore import QStandardPaths

    from open_garden_planner.config import settings

    # Redirect BEFORE QApplication/AppSettings/UiStateStore are constructed.
    settings.ORGANIZATION_NAME = "cofade_test"
    settings.APPLICATION_NAME = f"Open Garden Planner Startup Benchmark {os.getpid()}"
    QStandardPaths.setTestModeEnabled(True)
    return StartupProbe(Path(arguments[index + 1]), started)
