"""The measuring scenarios of the workspace gate — from source only (Phase 17 L1.3).

Not a test module. ``workspace_gate_hook.py`` looks a scenario up here when it is not
one of its own; each is a generator that runs INSIDE the real app on the GUI
thread (the hook's ``_Runner``) and reports through ``hook.step``. The numbers of
gates G2 (edit → finished readback), G3 (the camera rule on the real host), G7
(the memory soak), G8 (WebEngine beside the 3D host) and G11 (the 2D pan cost) are
measured here and judged in ``test_view3d_workspace_render.py``.

Measuring rules (ADR-048, ``ogp-3d-renderer`` §6 and §8):

- "A frame" is a FINISHED READBACK (``host.grab()`` on a live host), never
  ``frameSwapped``: with the display asleep a visible window presents one frame and
  no more, and a submitted frame is not a finished one.
- A readback is the measuring device of the LATENCY and PICTURE scenarios, and it
  costs memory of its own: the frame it renders is never presented, and what that
  frame holds stays until a presented frame ends. So the MEMORY soak takes no
  frame inside its measured loop (one before, one after), and the product takes
  none from the live view at all.
- 2D pan cost is measured with ``processEvents()`` — a synchronous ``repaint()``
  does not include the flush and composition.
- Memory is COMMITTED memory (private bytes on Windows): the working set is
  trimmed and regrown. Dedicated GPU memory is asked from DXGI for this process
  (``IDXGIAdapter3::QueryVideoMemoryInfo``) — private bytes do not see VRAM.
"""

from __future__ import annotations

import ctypes
import gc
import os
import statistics
import sys
import time
from collections.abc import Callable, Iterator
from datetime import date
from datetime import time as clock_time
from typing import Any

import workspace_gate_hook as hook  # the runner's module: already imported, first

step = hook.step
facts = hook.workspace_facts

#: How long a scenario waits for a frame of the window's size (the engine story's
#: ``OPEN_TIMEOUT_S``): the host's own default is one second, for one call in a GUI.
OPEN_WAIT_S = 10.0


# ── small tools ──────────────────────────────────────────────────────────────


def _pump(ms: float) -> None:
    from PyQt6.QtCore import QCoreApplication

    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        QCoreApplication.processEvents()
        time.sleep(0.001)


def _pump_until(condition: Callable[[], bool], timeout_s: float = 20.0) -> bool:
    from PyQt6.QtCore import QCoreApplication

    end = time.perf_counter() + timeout_s
    while time.perf_counter() < end:
        if condition():
            return True
        QCoreApplication.processEvents()
    return bool(condition())


def _percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    return ordered[min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))]


def _summary(values: list[float]) -> dict[str, float]:
    return {"n": len(values), "p50": round(statistics.median(values), 3),
            "p95": round(_percentile(values, 0.95), 3), "max": round(max(values), 3),
            "min": round(min(values), 3)}


def theil_sen(values: list[float]) -> float:
    """The median of all pairwise slopes (per step) — the leak gate's estimator."""
    slopes = [(values[j] - values[i]) / (j - i)
              for i in range(len(values)) for j in range(i + 1, len(values))]
    return statistics.median(slopes) if slopes else 0.0


def private_mb() -> float:
    """Committed memory of this process in MB (private bytes; RSS off Windows)."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                        ("PrivateUsage", ctypes.c_size_t)]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters),
                                               wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters),
                                          counters.cb):
            return float("nan")
        return counters.PrivateUsage / 1048576.0
    with open("/proc/self/statm", encoding="ascii") as handle:  # Linux: resident pages
        return int(handle.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1048576.0


def gpu_dedicated_mb() -> dict[str, Any]:
    """Dedicated GPU memory THIS PROCESS uses, per adapter, from DXGI:
    ``IDXGIAdapter3::QueryVideoMemoryInfo(node 0, DXGI_MEMORY_SEGMENT_GROUP_LOCAL)``
    → ``CurrentUsage``. ``{"available": False, "why": …}`` where DXGI 1.4 is not."""
    if sys.platform != "win32":
        return {"available": False, "why": "DXGI is Windows only"}
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                    ("d", ctypes.c_ubyte * 8)]

    def guid(a: int, b: int, c: int, *d: int) -> Guid:
        return Guid(a, b, c, (ctypes.c_ubyte * 8)(*d))

    class Desc1(ctypes.Structure):
        _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", wintypes.UINT),
                    ("DeviceId", wintypes.UINT), ("SubSysId", wintypes.UINT),
                    ("Revision", wintypes.UINT), ("DedicatedVideoMemory", ctypes.c_size_t),
                    ("DedicatedSystemMemory", ctypes.c_size_t),
                    ("SharedSystemMemory", ctypes.c_size_t), ("AdapterLuid", ctypes.c_int64),
                    ("Flags", wintypes.UINT)]

    class MemoryInfo(ctypes.Structure):
        _fields_ = [("Budget", ctypes.c_uint64), ("CurrentUsage", ctypes.c_uint64),
                    ("AvailableForReservation", ctypes.c_uint64),
                    ("CurrentReservation", ctypes.c_uint64)]

    factory_id = guid(0x770AAE78, 0xF26F, 0x4DBA, 0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87)
    adapter3_id = guid(0x645967A4, 0x1392, 0x4310, 0xA7, 0x98, 0x80, 0x53, 0xCE, 0x3E, 0x93, 0xFD)

    def method(pointer: ctypes.c_void_p, index: int, result: Any, *argtypes: Any) -> Any:
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *argtypes)(table[index])

    try:
        dxgi = ctypes.WinDLL("dxgi")
        factory = ctypes.c_void_p()
        dxgi.CreateDXGIFactory1.argtypes = [ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p)]
        dxgi.CreateDXGIFactory1.restype = ctypes.c_long
        if dxgi.CreateDXGIFactory1(ctypes.byref(factory_id), ctypes.byref(factory)) != 0:
            return {"available": False, "why": "CreateDXGIFactory1 failed"}
        adapters: list[dict[str, Any]] = []
        index = 0
        while True:
            adapter = ctypes.c_void_p()
            # IDXGIFactory1::EnumAdapters1 is slot 12 of its vtable
            if method(factory, 12, ctypes.c_long, wintypes.UINT,
                      ctypes.POINTER(ctypes.c_void_p))(factory, index, ctypes.byref(adapter)) != 0:
                break
            index += 1
            desc = Desc1()
            method(adapter, 10, ctypes.c_long, ctypes.POINTER(Desc1))(adapter, ctypes.byref(desc))
            adapter3 = ctypes.c_void_p()
            entry: dict[str, Any] = {"name": desc.Description, "software": bool(desc.Flags & 2),
                                     "dedicated_total_mb": desc.DedicatedVideoMemory / 1048576.0}
            if method(adapter, 0, ctypes.c_long, ctypes.POINTER(Guid),
                      ctypes.POINTER(ctypes.c_void_p))(
                          adapter, ctypes.byref(adapter3_id), ctypes.byref(adapter3)) == 0:
                info = MemoryInfo()
                # IDXGIAdapter3::QueryVideoMemoryInfo is slot 14; segment group 0 = local
                if method(adapter3, 14, ctypes.c_long, wintypes.UINT, wintypes.UINT,
                          ctypes.POINTER(MemoryInfo))(adapter3, 0, 0, ctypes.byref(info)) == 0:
                    entry["process_dedicated_mb"] = round(info.CurrentUsage / 1048576.0, 2)
                    entry["budget_mb"] = round(info.Budget / 1048576.0, 1)
                method(adapter3, 2, wintypes.ULONG)(adapter3)  # Release
            method(adapter, 2, wintypes.ULONG)(adapter)
            adapters.append(entry)
        method(factory, 2, wintypes.ULONG)(factory)
    except (OSError, AttributeError, ValueError) as error:
        return {"available": False, "why": f"{type(error).__name__}: {error}"}
    hardware = [a for a in adapters if not a["software"] and "process_dedicated_mb" in a]
    return {"available": bool(hardware), "adapters": adapters,
            "process_dedicated_mb": sum(a["process_dedicated_mb"] for a in hardware)}


def _enter_and_wait(window: Any, mode: str) -> Iterator[Any]:
    hook._enter(window, mode)
    yield hook._running(window)
    yield hook._settled(window)
    yield 300


def _live(window: Any) -> Any:
    """The engine host, with a frame of the window's size just taken (``wait_ready`` is
    called here — in a test's own loop — and nowhere in the product). ``OPEN_WAIT_S``:
    the first frame of a process can take longer than the host's default second; the
    wait costs nothing when nothing comes (False 0.5 s after the last sign)."""
    host = window._workspace.host
    assert host is not None, "no engine host"
    ready = host.wait_ready(OPEN_WAIT_S)
    assert ready, f"the host has no frame of its window's size: {host.state.value}"
    return host


def _grab(host: Any) -> tuple[float, Any]:
    """One finished readback; the time it took in ms. A host that is momentarily not
    answerable (a resize on its way) is waited for once."""
    from open_garden_planner.ui.view3d.quick3d.host import HostStateError

    started = time.perf_counter()
    try:
        image = host.grab()
    except HostStateError:
        host.wait_ready(OPEN_WAIT_S)
        image = host.grab()
    return (time.perf_counter() - started) * 1000.0, image


#: Two readbacks of the same plan and camera are "the same picture" when no channel of
#: any pixel differs by more than this (of 255). Since the L1.4 sky, the frame after a
#: soak is not always bit-identical to the one before it: measured on the RTX 4070,
#: 2026-10-19 (L1.5 review 3), rebuild_off soaks differed in 6 pixels of the sky band by
#: 1 in about half the runs, at the story's head as well. A tile left bare, a missing
#: Model or a different camera differs by far more (a bare tile against a lawn: > 30).
SAME_IMAGE_TOLERANCE = 2


def _image_difference(first: Any, last: Any) -> dict[str, Any]:
    """How two readbacks differ — for the report when they are not the same image: the
    pixels that differ, the largest channel difference, and the box they lie in."""
    import numpy as np
    from PyQt6.QtGui import QImage

    def pixels(image: Any) -> Any:
        rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
        data = rgba.constBits()
        data.setsize(rgba.sizeInBytes())
        rows = np.frombuffer(data, np.uint8).reshape(rgba.height(), rgba.bytesPerLine())
        return rows[:, :rgba.width() * 4].reshape(rgba.height(), rgba.width(), 4).astype(np.int16)

    if first is None or last is None or first.size() != last.size():
        return {"comparable": False}
    delta = np.abs(pixels(first) - pixels(last)).max(axis=2)
    rows, columns = np.nonzero(delta)
    if rows.size == 0:
        return {"comparable": True, "pixels": 0}
    return {"comparable": True, "pixels": int(rows.size), "largest": int(delta.max()),
            "over_8": int((delta > 8).sum()),
            "box": [int(columns.min()), int(rows.min()), int(columns.max()), int(rows.max())],
            "size": [first.width(), first.height()]}


def _editable(window: Any) -> dict[str, list[Any]]:
    """Items of the open plan the scripted edits use, by shape."""
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    found: dict[str, list[Any]] = {"rects": [], "circles": []}
    for item in window.canvas_scene.items():
        if getattr(item, "object_type", None) is None or not item.isVisible():
            continue
        if isinstance(item, RectangleItem):
            found["rects"].append(item)
        elif isinstance(item, CircleItem):
            found["circles"].append(item)
    found["rects"].sort(key=lambda item: str(item.item_id))
    found["circles"].sort(key=lambda item: str(item.item_id))
    return found


def _edits(window: Any, count: int) -> list[tuple[str, Callable[[], None]]]:
    """``count`` scripted edits through the app's own commands: moves, recolours, a
    resize, an add, a delete, undo and redo — in a fixed order."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor

    from open_garden_planner.core.commands import (
        ChangePropertyCommand,
        CreateItemCommand,
        DeleteItemsCommand,
        MoveItemsCommand,
        ResizeItemCommand,
    )
    from open_garden_planner.core.fill_patterns import create_pattern_brush
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.geometry_apply import (
        apply_rect_like_geometry,
        build_rect_resize,
    )
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    scene, commands = window.canvas_scene, window.canvas_view.command_manager
    items = _editable(window)
    rects, circles = items["rects"], items["circles"]
    assert rects and circles, "the plan has no rectangle or no circle to edit"
    layer = scene.active_layer.id
    added: list[Any] = []

    def move(index: int) -> Callable[[], None]:
        target = (rects + circles)[index % (len(rects) + len(circles))]
        delta = QPointF(7.0 if index % 2 == 0 else -7.0, 3.0 if index % 3 == 0 else -3.0)
        return lambda: commands.execute(MoveItemsCommand([target], delta))

    def recolour(index: int) -> Callable[[], None]:
        target = rects[index % len(rects)]
        colour = QColor(40 + (index * 37) % 200, 120, 60 + (index * 11) % 150)

        def apply() -> None:
            # the properties panel's fill-colour edit (``_on_color_changed``)
            def set_fill(item: Any, value: Any) -> None:
                item.fill_color = value
                item.setBrush(create_pattern_brush(item.fill_pattern, value))

            commands.execute(ChangePropertyCommand(
                target, "fill color", QColor(target.fill_color), colour, set_fill))

        return apply

    def resize(index: int) -> Callable[[], None]:
        target = rects[index % len(rects)]

        def apply() -> None:
            rect = target.rect()
            grow = 12.0 if index % 2 == 0 else -12.0
            old, new = build_rect_resize(target, rect.width() + grow, rect.height() + grow,
                                         keep_center=True)
            commands.execute(ResizeItemCommand(target, old, new, apply_rect_like_geometry))

        return apply

    def add(index: int) -> Callable[[], None]:
        def apply() -> None:
            item = CircleItem(900.0 + 40.0 * index, 700.0, 45.0, object_type=ObjectType.SHRUB,
                              layer_id=layer)
            added.append(item)
            commands.execute(CreateItemCommand(scene, item, "shrub"))

        return apply

    def delete() -> None:
        commands.execute(DeleteItemsCommand(scene, [added.pop()]))

    # Ten edits a round, every one of which changes the plan: … add, undo (the shrub
    # is gone), redo (it is back), delete. A redo with nothing to redo would be no
    # edit at all — the first version of this script had one, and "measured" 200 ms
    # for it: the time until some unrelated timer happened to repaint the scene.
    script: list[tuple[str, Callable[[], None]]] = []
    for index in range(count):
        kind = index % 10
        if kind == 3:
            script.append(("recolour", recolour(index)))
        elif kind == 5:
            script.append(("resize", resize(index)))
        elif kind == 6:
            script.append(("add", add(index)))
        elif kind == 7:
            script.append(("undo", commands.undo))
        elif kind == 8:
            script.append(("redo", commands.redo))
        elif kind == 9:
            script.append(("delete", delete))
        else:
            script.append(("move", move(index)))
    return script


# ── G2: edit → finished readback ─────────────────────────────────────────────


def scenario_edit_latency(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    """Gate G2. For each scripted edit: the clock starts before the app's command runs
    and stops when a readback of the 3D view that was taken AFTER the pipeline's
    pass has finished. The parts: ``edit`` (the command and every slot the app runs
    synchronously on it), ``wait`` (the event loop until the pass starts — the 2D
    side's own reaction to the edit is in here), ``snapshot``, ``apply`` (diff,
    builders, uploads), ``grab`` (render + readback; the readback is the measuring
    instrument's cost and grows with the pane's pixels)."""
    if args.get("width"):
        window.showNormal()
        window.resize(int(args["width"]), int(args.get("height", 900)))
        yield 300
    yield from _enter_and_wait(window, str(args.get("mode", "split")))
    workspace = window._workspace
    controller = workspace.controller
    if args.get("timer_ms"):
        # the alternative ADR-065 rejected, kept measurable: a pass scheduled with a
        # timer of this interval instead of the posted event
        controller._tick_ms = int(args["timer_ms"])
    host = _live(window)
    for _ in range(3):
        _grab(host)  # warm: the first grabs pay for the readback path
    # what the instrument itself costs at this pane size: a readback with nothing to do
    idle_grabs = [_grab(host)[0] for _ in range(20)]
    script = _edits(window, int(args.get("edits", 120)))
    rows: list[dict[str, Any]] = []
    misses = 0
    armed: dict[str, Any] = {}

    def on_pass(report: Any) -> None:
        # The readback is taken HERE — the moment the pass has committed, on the GUI
        # thread — so that the clock stops when a finished frame containing the edit
        # exists, not when the rest of the event-loop turn (the 2D side repainting
        # itself) is over as well.
        if not armed or "done" in armed:
            return
        armed["passed"] = time.perf_counter()
        armed["report"] = report
        try:
            armed["grab"] = host.grab() and 0.0
        except Exception as error:  # noqa: BLE001 - a host mid-resize: counted as a miss
            armed["error"] = f"{type(error).__name__}: {error}"
        armed["done"] = time.perf_counter()

    controller.applied.connect(on_pass)
    for kind, edit in script:
        armed.clear()
        armed["armed"] = True
        started = time.perf_counter()
        edit()
        edited = time.perf_counter()
        # the product's own path: scene.changed / stack_changed → the tick → a pass
        _pump_until(lambda: "done" in armed, 5.0)
        report = armed.get("report")
        if "done" not in armed or "error" in armed or report is None:
            misses += 1
            continue
        rows.append({"kind": kind, "total": (armed["done"] - started) * 1000.0,
                     "edit": (edited - started) * 1000.0,
                     "wait": (armed["passed"] - edited) * 1000.0 - report.total_ms,
                     "snapshot": report.snapshot_ms, "apply": report.apply_ms,
                     "grab": (armed["done"] - armed["passed"]) * 1000.0,
                     "sink_work": report.changes.touches_sink})
        armed.clear()
        _pump(20)  # let the 2D side finish its own reaction before the next edit
    controller.applied.disconnect(on_pass)
    kinds = sorted({row["kind"] for row in rows})
    size = host.view_size()
    step("edit_latency",
         records=len(controller.sync.records), edits=len(script), measured=len(rows),
         misses=misses, total_ms=_summary([row["total"] for row in rows]),
         edit_ms=_summary([row["edit"] for row in rows]),
         wait_ms=_summary([row["wait"] for row in rows]),
         snapshot_ms=_summary([row["snapshot"] for row in rows]),
         apply_ms=_summary([row["apply"] for row in rows]),
         grab_ms=_summary([row["grab"] for row in rows]),
         idle_grab_ms=_summary(idle_grabs),
         to_pass_done_ms=_summary([row["total"] - row["grab"] for row in rows]),
         by_kind={kind: _summary([row["total"] for row in rows if row["kind"] == kind])
                  for kind in kinds},
         edits_that_reached_the_engine=sum(bool(row["sink_work"]) for row in rows),
         pane_px=[round(size[0]), round(size[1])],
         window_px=[window.width(), window.height()], facts=facts(window))
    yield 100


# ── G3 (render twin): the camera rule on the real host ───────────────────────


def scenario_camera_rule(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent

    yield from _enter_and_wait(window, "split")
    workspace = window._workspace
    controller, camera = workspace.controller, workspace.camera
    host = _live(window)
    # the user looks around first — through the real input filter of the real window
    wheel = QWheelEvent(QPointF(60.0, 60.0), QPointF(60.0, 60.0), QPoint(0, 0), QPoint(0, 360),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    from PyQt6.QtCore import QCoreApplication

    QCoreApplication.sendEvent(host._view, wheel)
    moved = _pump_until(lambda: not camera.moving and camera.pose == camera.goal, 5.0)
    step("user_zoomed", settled=moved, distance=camera.pose.distance_cm,
         timer_active=workspace._camera_timer.isActive())
    pose = camera.pose
    version = int(host.scene_property("camVersion"))
    position = host.scene_property("camPos")
    start_position = (position.x(), position.y(), position.z())
    script = _edits(window, int(args.get("edits", 100)) - 2)
    script.append(("date", lambda: window._sim_clock.set_date(date(2027, 5, 1))))
    script.append(("time", lambda: window._sim_clock.set_time_of_day(clock_time(7, 40))))
    moved_by: list[str] = []
    for kind, edit in script:
        edit()
        _pump_until(lambda: not controller.dirty, 5.0)
        _pump(5)
        now = host.scene_property("camPos")
        same = (camera.pose is pose and camera.goal == pose
                and int(host.scene_property("camVersion")) == version
                and (now.x(), now.y(), now.z()) == start_position)
        if not same:
            moved_by.append(kind)
    step("edits_done", edits=len(script), kinds=sorted({kind for kind, _edit in script}),
         moved_by=moved_by, cam_version=int(host.scene_property("camVersion")),
         cam_version_before=version, applies=controller.apply_count)
    # a document change DOES frame — once
    window._new_project_document(width_cm=2400.0, height_cm=1200.0)
    _pump_until(lambda: not controller.dirty, 5.0)
    _pump(50)
    after = host.scene_property("camPos")
    step("document_changed", cam_version=int(host.scene_property("camVersion")),
         pose_changed=camera.pose != pose,
         cam_moved=(after.x(), after.y(), after.z()) != start_position,
         parts=host.part_count(), facts=facts(window))
    _ = QEvent  # (imported for the type of the event sent above)
    yield 100


# ── G7: the A/B memory soak in the production host ───────────────────────────


def scenario_soak(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    """``variant``: ``rebuild_off`` (a reload is a plain apply: the plan's ids are the
    same, so no Model is rebuilt), ``rebuild_on`` (every reload also tears the engine
    scene down and builds every Model and geometry again), ``control`` (rebuild on,
    plus 25 MB kept alive per reload — the gate must FAIL on it).

    ``frames``: ``presented`` (the default: the view draws and presents as a visible
    view does) or ``withheld`` (the engine story's no-paint device for the length of
    the measured loop: an event filter that eats the view's expose, update-request
    and paint events — the view is shown, exposed, on the screen, and NOTHING draws
    it: the display asleep, a session that does not present).

    ``grabs``: ``none`` (the default) or ``every``. THE MEASURED LOOP TAKES NO FRAME
    FROM THE HOST. A readback (``grab()``) renders a frame of its own that is never
    presented, and what such a frame holds stays until a presented frame ends: a
    soak that grabs every cycle measures the grab, not the pipeline. Nothing in the
    product takes a frame from the live view either. ONE frame is read before the
    loop and ONE after it — the picture must be the same. ``every`` is what this
    soak did before that was understood (one readback per reload): reported, never
    judged.

    ``release``: ``product`` (the default — the workspace's own release of the
    engine's cached graphics state, waited for after each reload, as a user who
    opens a plan and looks at it gives it time) or ``off`` (the workspace's two
    thresholds out of reach: what the same soak reads WITHOUT the release — the
    A of this A/B) or ``flood`` (the "at once" threshold at 1: every pass that
    destroyed a Model releases INSIDE the pass, the path an animated date takes —
    never waited for, never polled).

    ``ground``: ``on`` (the default — the product: the workspace's own ground bake) or
    ``off`` (the workspace gets no baker: a plain plan rectangle — Model churn alone).
    With the bake on, Qt Quick 3D 6.11's ``QSSGBufferManager::clear()`` leaks about
    half the same-size tile textures on every release (#532), so the soak REPORTS what
    the ground's textures hold (``ground_texture_mb``: tiles × width × height × 4 bytes
    × 4/3 for the mip chain — the tiles generate mipmaps, ``Garden.qml``); the gate
    derives its allowance for #532 from that number and the releases it counted."""
    from PyQt6.QtCore import QEvent, QObject

    from open_garden_planner.ui.view3d import workspace as workspace_module

    class NoPaint(QObject):
        eaten = 0

        def eventFilter(self, _watched: Any, event: Any) -> bool:  # noqa: N802 - Qt's name
            if event.type() in (QEvent.Type.Expose, QEvent.Type.UpdateRequest, QEvent.Type.Paint):
                NoPaint.eaten += 1
                return True
            return False

    variant = str(args.get("variant", "rebuild_on"))
    reloads = int(args.get("reloads", 20))
    release = str(args.get("release", "product"))
    frames_mode = str(args.get("frames", "presented"))
    grabs = str(args.get("grabs", "none"))
    ground = str(args.get("ground", "on"))
    assert ground in ("on", "off"), ground
    if ground == "off":
        from open_garden_planner.ui.view3d import ground_bake as ground_bake_module

        ground_bake_module.GroundBaker = lambda: None  # type: ignore[assignment,misc]
    assert frames_mode in ("presented", "withheld") and grabs in ("none", "every"), (frames_mode, grabs)
    if release == "off":
        workspace_module.RELEASE_AFTER_RETIRED = 10**9  # type: ignore[misc]
        workspace_module.RELEASE_NOW_RETIRED = 10**9  # type: ignore[misc]
    elif release == "flood":
        workspace_module.RELEASE_AFTER_RETIRED = 10**9  # type: ignore[misc]
        workspace_module.RELEASE_NOW_RETIRED = 1  # type: ignore[misc]
    plan = str(window._project_manager.current_file)  # the plan main() was started on
    yield from _enter_and_wait(window, "split")
    workspace = window._workspace
    controller = workspace.controller
    host = _live(window)

    def presented(count: int, timeout_s: float) -> bool:
        """Wait for frames the view presents BY ITSELF (a pass gave it something new)."""
        wanted = host.health().frames_presented + count
        return _pump_until(lambda: host.health().frames_presented >= wanted, timeout_s)

    def present(timeout_s: float = 5.0) -> bool:
        """Ask the view for a frame (a still scene presents none) and wait until it was
        PRESENTED — an ordinary frame of the render loop, not a readback."""
        wanted = host.health().frames_presented + 1
        host._view.update()
        return _pump_until(lambda: host.health().frames_presented >= wanted, timeout_s)

    def settled() -> bool:
        """No pass owed — and no GROUND pass either: the ground is painted to the end
        (a frame taken while tiles are pending shows them bare, and differs)."""
        return not controller.dirty and not controller.ground_owed

    # the ONE frame before the loop — and presented frames after it, so that what
    # the readback's own frame held is given back before anything is measured
    _pump_until(settled, 10.0)
    present()
    first = _grab(host)[1]
    present()
    present()
    _pump(200)
    parts_before = host.part_count()
    blocker: Any = None
    if frames_mode == "withheld":
        blocker = NoPaint()
        host._view.installEventFilter(blocker)
        _pump(100)
    kept: list[bytes] = []
    gpu_before = gpu_dedicated_mb()
    start_mb = round(private_mb(), 2)
    curve: list[float] = []
    gpu_curve: list[float | None] = []
    frames_per_reload: list[int] = []
    owed: list[int] = []
    grabbed = 0
    frames_at_start = host.health().frames_presented
    applies_at_start = controller.apply_count
    releases_before = host.cache_releases
    uploads_before = getattr(controller.sync.sink, "geometry_uploads", None)
    trace = bool(args.get("trace", False))  # where PYTHON-side memory grows, if it does
    traced: dict[str, Any] = {}
    if trace:
        import tracemalloc

        tracemalloc.start(8)
    for _index in range(reloads):
        if trace and _index in (reloads // 4, (3 * reloads) // 4):
            gc.collect()
            traced[str(_index)] = tracemalloc.take_snapshot()
        frames = host.health().frames_presented
        window._load_project_file(plan)
        _pump_until(settled, 30.0)
        if variant in ("rebuild_on", "control"):
            controller.reset()
            _pump_until(lambda: settled() and len(controller.sync.records) > 0, 30.0)
        if variant == "control":
            kept.append(b"\x01" * (25 * 1024 * 1024))
        releases_seen = host.cache_releases
        owed.append(workspace._retired)
        if grabs == "every":
            _grab(host)
            grabbed += 1
        if frames_mode == "presented":
            # two PRESENTED frames: the engine draws what the pass gave it, and what
            # the destroyed Models held is given back at the end of a presented frame
            presented(2, 2.0)
        _pump(30)
        if release == "product" and owed[-1] >= workspace_module.RELEASE_AFTER_RETIRED:
            # the workspace releases at its next health poll once the pipeline was
            # quiet: wait for exactly that, as a user who opened a plan and looks at
            # it gives it the time
            _pump_until(lambda seen=releases_seen: host.cache_releases > seen, 10.0)
            _pump(50)
        frames_per_reload.append(host.health().frames_presented - frames)
        gc.collect()
        curve.append(round(private_mb(), 2))
        gpu = gpu_dedicated_mb()
        gpu_curve.append(gpu.get("process_dedicated_mb") if gpu.get("available") else None)
    in_the_loop = {
        "frames_presented": host.health().frames_presented - frames_at_start,
        "frames_read_back": grabbed,
        "passes_applied": controller.apply_count - applies_at_start,
        "parts_at_the_end": host.part_count(),
        "paint_events_eaten": NoPaint.eaten,
    }
    # the ONE frame after the loop: the same plan, the same camera — the same picture
    if blocker is not None:
        host._view.removeEventFilter(blocker)
    _pump_until(lambda: settled() and host.part_count() == parts_before, 20.0)
    presented_again = present(10.0)
    last = _grab(host)[1]
    present()
    present()
    _pump(300)
    gc.collect()
    end_mb = round(private_mb(), 2)  # after the view presented again: what the loop left
    second_half = curve[len(curve) // 2:]
    gpu_values = [value for value in gpu_curve if value is not None]
    difference = (_image_difference(first, last) if first != last
                  else {"comparable": True, "pixels": 0, "largest": 0})
    # what the ground's tile textures hold (the plan is the same every reload, and so is
    # its ground): RGBA8, and the mip chain a third again
    ground_shown = controller.sync.ground
    tiles = ground_shown.tiles if ground_shown is not None else ()
    texture_bytes = sum(tile.width_px * tile.height_px * 4 for tile in tiles) * 4.0 / 3.0
    python_growth: dict[str, Any] = {}
    if trace and len(traced) == 2:
        import tracemalloc

        early, late = (traced[key] for key in sorted(traced, key=int))
        between = (3 * reloads) // 4 - reloads // 4
        stats = late.compare_to(early, "traceback")
        python_growth = {
            "reloads_between": between,
            "total_mb_per_reload": round(sum(s.size_diff for s in stats) / 1048576.0 / between, 3),
            "top": [{"mb_per_reload": round(s.size_diff / 1048576.0 / between, 3),
                     "count_per_reload": round(s.count_diff / between, 1),
                     "where": [f"{frame.filename.replace(os.sep, '/').rsplit('/', 3)[-1]}:"
                               f"{frame.lineno}" for frame in s.traceback][-6:]}
                    for s in stats[:8]],
        }
        tracemalloc.stop()
    step("soak", variant=variant, reloads=reloads, frames=frames_mode, grabs=grabs, release=release,
         ground=ground, ground_baker=controller.sync.ground_baker is not None,
         ground_tiles=len(tiles),
         ground_tile_px=sorted({(tile.width_px, tile.height_px) for tile in tiles}),
         ground_texture_mb=round(texture_bytes / 1048576.0, 3),
         start_mb=start_mb, curve_mb=curve, python_growth=python_growth,
         slope_second_half_mb_per_reload=round(theil_sen(second_half), 3),
         slope_all_mb_per_reload=round(theil_sen(curve), 3),
         growth_mb=round(curve[-1] - curve[0], 2),
         growth_from_start_mb=round(curve[-1] - start_mb, 2),
         after_the_last_frame_mb=end_mb,
         gpu_before=gpu_before, gpu_after=gpu_dedicated_mb(), gpu_curve_mb=gpu_curve,
         gpu_slope_second_half_mb_per_reload=(
             round(theil_sen(gpu_values[len(gpu_values) // 2:]), 3) if len(gpu_values) > 3 else None),
         geometry_uploads=(getattr(controller.sync.sink, "geometry_uploads", 0) - uploads_before
                           if uploads_before is not None else None),
         kept_mb=25 * len(kept), parts=parts_before, parts_after=host.part_count(),
         frames_presented_per_reload=frames_per_reload, in_the_loop=in_the_loop,
         retired_before_release_per_reload=owed,
         cache_releases=host.cache_releases - releases_before,
         presented_again=bool(presented_again),
         same_image_at_the_end=bool(first == last) or (
             bool(difference.get("comparable"))
             and int(difference.get("largest", 255)) <= SAME_IMAGE_TOLERANCE),
         identical_image_at_the_end=bool(first == last), image_difference=difference,
         facts=facts(window))
    yield 100


# ── G8: Qt WebEngine beside the 3D host ──────────────────────────────────────

_PAGE = ("<html><body style='margin:0;background:#1e90ff'>"
         "<div style='width:100%;height:100vh;background:#1e90ff'></div></body></html>")


def _web_colour(parent: Any) -> dict[str, Any]:
    """Open a ``QWebEngineView`` window on a page of one colour, let it load and
    paint, and read the colour back from its centre — the map picker's engine,
    without the network the picker's own page needs."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    view = QWebEngineView()
    view.setWindowFlag(Qt.WindowType.Tool, True)
    view.resize(320, 240)
    loaded: list[bool] = []
    view.loadFinished.connect(loaded.append)
    view.setHtml(_PAGE)
    view.show()
    finished = _pump_until(lambda: bool(loaded), 20.0)
    colour = ""
    for _attempt in range(40):
        _pump(100)
        image = view.grab().toImage()
        colour = image.pixelColor(image.width() // 2, image.height() // 2).name()
        if colour == "#1e90ff":
            break
    view.close()
    view.deleteLater()
    _pump(100)
    _ = parent
    return {"load_finished": finished, "loaded_ok": bool(loaded and loaded[0]), "centre": colour}


def scenario_coexist(window: Any, _args: dict[str, Any]) -> Iterator[Any]:
    before = _web_colour(window)
    step("web_before_3d", **before)
    yield from _enter_and_wait(window, "split")
    host = _live(window)
    _grab_ms, image = _grab(host)
    colours = {image.pixelColor(x, y).name() for x in range(0, image.width(), max(1, image.width() // 24))
               for y in range(0, image.height(), max(1, image.height() // 24))}
    after = _web_colour(window)
    host_after = _live(window)
    _grab_ms, image_after = _grab(host_after)
    step("web_after_3d", **after, distinct_3d_colours=len(colours),
         frame_px=[image_after.width(), image_after.height()], facts=facts(window))
    yield 100


# ── G11: the 2D pan cost beside the live 3D view ─────────────────────────────

_PAN_STEP_PX = 9
_PAN_TURN_AFTER = 20


def _pan_steps(window: Any, steps: int) -> list[float]:
    """``steps`` pan steps along ONE fixed path: from the middle of the scroll range,
    20 steps right, 20 left, and so on. Every block walks the same pixels — what a
    step costs depends on what it uncovers (3 ms over lawn, 30 ms over a dense bed),
    so blocks that walked different stretches of the plan compared the plan with
    itself (measured: ratios per round between 0.16 and 7.2)."""
    from PyQt6.QtCore import QCoreApplication

    canvas = window.canvas_view
    bar = canvas.horizontalScrollBar()
    reach = _PAN_STEP_PX * _PAN_TURN_AFTER
    middle = (bar.minimum() + bar.maximum()) // 2
    assert bar.minimum() <= middle <= middle + reach <= bar.maximum(), (
        f"nothing to pan: scroll range {bar.minimum()}..{bar.maximum()}")
    bar.setValue(middle)
    QCoreApplication.processEvents()
    times: list[float] = []
    for index in range(steps):
        target = bar.value() + (_PAN_STEP_PX if (index // _PAN_TURN_AFTER) % 2 == 0 else -_PAN_STEP_PX)
        started = time.perf_counter()
        bar.setValue(target)
        QCoreApplication.processEvents()
        times.append((time.perf_counter() - started) * 1000.0)
        assert bar.value() == target, "a pan step did not scroll"
    return times


def scenario_pan(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    """Gate G11. ``rounds`` times: ``steps`` pan steps in Split, then ``steps`` in Plan
    with the canvas at the SAME size (the window shrinks by the 3D pane's width).
    Short alternating blocks along the same path (``_pan_steps``), so that what else
    the machine is doing lands on both sides alike — two long blocks one after the
    other measured the machine's drift as much as the 3D view (1.10 to 1.28 for the
    same build on a busy box)."""
    steps = int(args.get("steps", 60))
    rounds = int(args.get("rounds", 6))
    window.showNormal()
    window.resize(int(args.get("width", 2200)), int(args.get("height", 1100)))
    yield 300
    yield from _enter_and_wait(window, "split")
    workspace, canvas = window._workspace, window.canvas_view
    _live(window)
    for _ in range(4):
        canvas.zoom_in()      # so that the plan is wider than the view: there is something to pan
    yield 300
    pane_width = workspace.pane.width() + workspace.splitter.handleWidth()
    split: list[float] = []
    plan: list[float] = []
    sizes: set[tuple[str, int, int]] = set()
    per_round: list[float] = []
    for _round in range(rounds):
        sizes.add(("split", canvas.width(), canvas.height()))
        _pan_steps(window, 15)     # warm
        in_split = _pan_steps(window, steps)
        hook._enter(window, "plan")
        window.resize(window.width() - pane_width, window.height())   # the canvas keeps its size
        yield 350
        sizes.add(("plan", canvas.width(), canvas.height()))
        _pan_steps(window, 15)
        in_plan = _pan_steps(window, steps)
        window.resize(window.width() + pane_width, window.height())
        hook._enter(window, "split")
        yield 350
        _live(window)
        split += in_split
        plan += in_plan
        per_round.append(round(statistics.median(in_split) / statistics.median(in_plan), 3))
    surface = window.windowHandle().surfaceType().name if window.windowHandle() else "?"
    step("pan", steps=steps, rounds=rounds, split_ms=_summary(split), plan_ms=_summary(plan),
         canvas_px=sorted(sizes), top_level_surface=surface,
         ratio=round(statistics.median(split) / statistics.median(plan), 3),
         # the same comparison where other processes disturb least: the fastest tenth
         ratio_of_p10=round(_percentile(split, 0.10) / _percentile(plan, 0.10), 3),
         ratio_per_round=per_round, facts=facts(window))
    yield 100


# ── shortcuts while the 3D window has the focus ──────────────────────────────


def scenario_shortcut_focus(window: Any, _args: dict[str, Any]) -> Iterator[Any]:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtTest import QTest

    from open_garden_planner.core.commands import MoveItemsCommand

    yield from _enter_and_wait(window, "3d")
    workspace = window._workspace
    host = _live(window)
    view = host._view
    window.activateWindow()
    view.requestActivate()
    yield 400
    focus = QGuiApplication.focusWindow()
    commands = window.canvas_view.command_manager
    item = (_editable(window)["rects"] or _editable(window)["circles"])[0]
    commands.execute(MoveItemsCommand([item], QPointF(11.0, 0.0)))
    depth = commands.undo_depth
    QTest.keyClick(view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    _pump(150)
    undone = commands.undo_depth == depth - 1
    distance = workspace.camera.goal.distance_cm
    QTest.keyClick(view, Qt.Key.Key_PageUp)
    _pump(50)
    zoomed = workspace.camera.goal.distance_cm < distance
    QTest.keyClick(view, Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)
    _pump(250)
    step("shortcuts", focus_is_the_3d_window=focus is view, undo_with_ctrl_z=undone,
         page_up_zooms=zoomed, mode_after_alt_1=workspace.mode.value, facts=facts(window))
    yield 100


SCENARIOS: dict[str, Callable[[Any, dict[str, Any]], Iterator[Any]]] = {
    "edit_latency": scenario_edit_latency,
    "camera_rule": scenario_camera_rule,
    "soak": scenario_soak,
    "coexist": scenario_coexist,
    "pan": scenario_pan,
    "shortcut_focus": scenario_shortcut_focus,
}
