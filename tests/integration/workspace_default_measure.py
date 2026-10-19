"""The measuring scenarios of the default flip (Phase 17 L1.9) — from source only.

Not a test module. ``workspace_gate_hook.py`` looks a scenario up here when it is
neither one of its own nor one of ``workspace_gate_measure.py``'s; each runs INSIDE
the real app (the product's ``main()``, a throw-away settings store) on the GUI thread
and reports through ``hook.step``. Judged in ``test_view3d_default_render.py``.

- ``budget`` — the app's start with 3D never opened (time to the first turn of the
  event loop with the window built; what of the engine is imported: nothing), the
  first switch to 3D (to the first PRESENTED frame, and to the first finished
  readback), memory after the first frame and after 100 edits (committed memory
  and the process's dedicated GPU memory, medians of three readings — private bytes
  swing by 100 MB and more within a run, L1.8), and the pipeline's own cost per
  edit (the whole-plan snapshot and the apply, from the pass reports).
- ``date_playback`` — #531: an arrow key held in the date field (a step every
  33 ms) while 3D shows a plan with dated plants; committed and GPU memory every
  five seconds, how many regrowths the steps cost.

Measuring rules as in ``workspace_gate_measure.py``: a frame is a finished readback,
taken only where it is the measured thing, never inside a memory loop.
"""

from __future__ import annotations

import gc
import statistics
import sys
import time
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import workspace_gate_hook as hook  # the runner's module: already imported, first
import workspace_gate_measure as measure

step = hook.step
facts = hook.workspace_facts

#: Module prefixes that ARE the engine: none of them may be loaded before 3D is asked for.
ENGINE_PREFIXES = ("PyQt6.QtQuick", "PyQt6.QtQml", "PyQt6.QtQuickWidgets", "PyQt6.QtQuick3D",
                   "open_garden_planner.ui.view3d.quick3d")


def engine_modules() -> list[str]:
    return sorted(name for name in sys.modules if name.startswith(ENGINE_PREFIXES))


def _memory(readings: int = 3) -> dict[str, Any]:
    """Medians of ``readings`` readings 200 ms apart (private bytes swing — L1.8)."""
    private: list[float] = []
    gpu: list[float] = []
    for index in range(readings):
        if index:
            measure._pump(200)
        gc.collect()
        private.append(measure.private_mb())
        reading = measure.gpu_dedicated_mb()
        if reading.get("available"):
            gpu.append(float(reading["process_dedicated_mb"]))
    return {"private_mb": round(statistics.median(private), 1),
            "private_mb_readings": [round(value, 1) for value in private],
            "gpu_dedicated_mb": round(statistics.median(gpu), 1) if gpu else None}


def scenario_budget(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    """The budget rows of L1.9 (module docstring), one process, in order."""
    step("before_3d", engine=engine_modules(), modules=len(sys.modules),
         started_s=round(time.time() - hook._state["started"], 3), **facts(window))
    memory_before = _memory()
    workspace = window._workspace
    clicked = time.perf_counter()
    window._view3d_action.trigger()             # View -> "3D View": Split (L1.9)
    yield hook._running(window)
    first_frame_s = time.perf_counter() - clicked
    host = workspace.host
    ready = host.wait_ready(measure.OPEN_WAIT_S) if host is not None else False
    grab_ms, _image = measure._grab(host) if ready else (float("nan"), None)
    first_readback_s = time.perf_counter() - clicked
    yield hook._settled(window)
    yield 1500                                  # the first frames settle; the look builds its sky
    controller = workspace.controller
    step("opened", first_frame_s=round(first_frame_s, 3),
         first_readback_s=round(first_readback_s, 3), grab_ms=round(grab_ms, 1),
         memory_before_3d=memory_before, memory_after_open=_memory(),
         engine=len(engine_modules()), **facts(window))
    reports: list[Any] = []
    controller.applied.connect(reports.append)
    script = measure._edits(window, int(args.get("edits", 100)))
    for _kind, edit in script:
        edit()
        measure._pump_until(lambda: controller.idle, 5.0)
        measure._pump(10)
    yield hook._settled(window)
    yield 1000
    controller.applied.disconnect(reports.append)
    passes = [report for report in reports if report.snapshot]
    step("edited", edits=len(script), passes=len(passes),
         snapshot_ms=measure._summary([report.snapshot_ms for report in passes] or [0.0]),
         apply_ms=measure._summary([report.apply_ms for report in passes] or [0.0]),
         memory_after_edits=_memory(),
         cache_releases=getattr(host, "cache_releases", None), **facts(window))
    yield 100


def _add_dated_plants(window: Any, count: int) -> list[str]:
    """``count`` apple trees dropped from the gallery (the bundled species: a mature size
    to grow towards) and measured on their planting day — every date step regrows each of
    them (FR-SUN-08). Through the canvas's own ``dropEvent``, as the user drops them."""
    from PyQt6.QtCore import QMimeData, QPointF, Qt
    from PyQt6.QtGui import QDropEvent

    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    view = window.canvas_view
    ids: list[str] = []
    for index in range(count):
        at = QPointF(300.0 + 150.0 * (index % 10), 300.0 + 200.0 * (index // 10))
        before = {id(item) for item in view.scene().items()}
        mime = QMimeData()
        mime.setText("gallery:TREE:species=apple tree")
        view.dropEvent(QDropEvent(QPointF(view.mapFromScene(at)), Qt.DropAction.CopyAction, mime,
                                  Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        new = [item for item in view.scene().items()
               if isinstance(item, CircleItem) and id(item) not in before]
        assert len(new) == 1, f"the drop made {len(new)} plants"
        new[0].metadata["plant_instance"] = {"planting_date": "2024-04-01",
                                             "current_height_cm": 180.0,
                                             "current_spread_cm": 120.0}
        ids.append(str(new[0].item_id))
    view.scene().note_plan_changed()   # the metadata writes above go round every command
    return ids


def scenario_date_playback(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    """#531 — ``seconds`` of a held date key, a step every ``step_ms``; ``interval_ms``
    replaces the controller's ``DATE_REGROW_MIN_MS`` for the run (0 = the behaviour
    before L1.9: a regrowth on every step)."""
    from open_garden_planner.ui.view3d import sync_controller

    if "interval_ms" in args:
        sync_controller.DATE_REGROW_MIN_MS = int(args["interval_ms"])  # type: ignore[misc]
    hook._enter(window, str(args.get("mode", "split")))
    yield hook._running(window)
    yield hook._settled(window)
    ids = set(_add_dated_plants(window, int(args.get("plants", 20))))
    workspace = window._workspace
    controller = workspace.controller
    clock = window._sim_clock
    clock.set_date(date(2025, 1, 1))
    yield hook._settled(window)
    yield 3000                                  # warm: the first regrowths, the sky, a release
    regrown: list[int] = []

    def count(report: Any) -> None:
        regrown.append(len(ids.intersection(report.changes.geometry)))

    controller.applied.connect(count)
    seconds = float(args.get("seconds", 60))
    step_ms = int(args.get("step_ms", 33))
    start = _memory()
    curve: list[float] = []
    gpu_curve: list[float | None] = []
    day = date(2025, 1, 2)
    started = time.perf_counter()
    next_sample = started + 5.0
    steps = 0
    while time.perf_counter() - started < seconds:
        clock.set_date(day)
        day += timedelta(days=1)
        steps += 1
        measure._pump(step_ms)
        if time.perf_counter() >= next_sample:
            next_sample += 5.0
            curve.append(round(measure.private_mb(), 2))
            reading = measure.gpu_dedicated_mb()
            gpu_curve.append(reading.get("process_dedicated_mb") if reading.get("available")
                             else None)
    held_s = time.perf_counter() - started
    yield hook._settled(window)
    yield 2000
    controller.applied.disconnect(count)
    end = _memory()
    half = curve[len(curve) // 2:]
    gpu_values = [value for value in gpu_curve if value is not None]
    step("date_playback", interval_ms=sync_controller.DATE_REGROW_MIN_MS, plants=len(ids),
         steps=steps, held_s=round(held_s, 2),
         regrowth_passes=sum(1 for value in regrown if value),
         models_regrown=sum(regrown), deferrals=controller.date_deferrals,
         light_passes=controller.light_count, start=start, end=end,
         growth_mb=round(end["private_mb"] - start["private_mb"], 1),
         curve_mb=curve, gpu_curve_mb=gpu_curve,
         slope_mb_per_min=round(measure.theil_sen(curve) * 12.0, 2) if len(curve) > 2 else None,
         slope_second_half_mb_per_min=round(measure.theil_sen(half) * 12.0, 2)
         if len(half) > 2 else None,
         gpu_slope_mb_per_min=round(measure.theil_sen(gpu_values) * 12.0, 2)
         if len(gpu_values) > 2 else None,
         cache_releases=getattr(workspace.host, "cache_releases", None),
         shown_date=str(controller._pass_date), clock_date=str(clock.plan_date))
    yield 100


def _painted(image: Any) -> bool:
    """Whether a screen grab shows a drawn 3D frame and not an empty window."""
    if image is None or image.isNull() or image.width() < 8 or image.height() < 8:
        return False
    colours = {image.pixel(x, y) for x in range(0, image.width(), max(1, image.width() // 40))
               for y in range(0, image.height(), max(1, image.height() // 40))}
    return len(colours) > 12


def scenario_budget_old_view(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    """The RETIRED Qt 3D window's numbers, for the comparison in L1.9's budget table —
    reachable from no menu since L1.9 (its slot is called directly) and deleted with
    the window in L1.10. The old window has no readback of its own: its first frame
    is taken from the screen (``QScreen.grabWindow``) until it shows a drawn garden."""
    from PyQt6.QtGui import QGuiApplication

    step("before_3d", qt3d=sorted(name for name in sys.modules if name.startswith("PyQt6.Qt3D")),
         modules=len(sys.modules), started_s=round(time.time() - hook._state["started"], 3))
    memory_before = _memory()
    clicked = time.perf_counter()
    window._on_open_3d_view()
    opened_s = time.perf_counter() - clicked
    view = window._view3d_window
    container = view.centralWidget()
    found: dict[str, Any] = {}

    def drawn() -> bool:
        screen = QGuiApplication.primaryScreen()
        if not container.isVisible() or screen is None:
            return False
        image = screen.grabWindow(int(container.winId())).toImage()
        if _painted(image):
            found["at"] = time.perf_counter()
            return True
        return False

    yield drawn
    first_frame_s = found.get("at", float("nan")) - clicked
    yield 1500
    step("opened", opened_s=round(opened_s, 3), first_frame_s=round(first_frame_s, 3),
         memory_before_3d=memory_before, memory_after_open=_memory(),
         qt3d=len([name for name in sys.modules if name.startswith("PyQt6.Qt3D")]))
    script = measure._edits(window, int(args.get("edits", 100)))
    for _kind, edit in script:
        edit()
        measure._pump(10)
    yield 1000
    started = time.perf_counter()
    window._refresh_3d_view()            # the old window's only way to show the edits
    refresh_ms = (time.perf_counter() - started) * 1000.0
    yield 1500
    step("edited", edits=len(script), refresh_ms=round(refresh_ms, 1),
         memory_after_edits=_memory())
    yield 100


SCENARIOS = {
    "budget": scenario_budget,
    "date_playback": scenario_date_playback,
    "budget_old_view": scenario_budget_old_view,   # L1.9 only: L1.10 deletes the old window
}
