"""The real window's half of the director's cut's render tier (Phase 17 L6, #390) — not a
test module.

``test_directors_cut_render.py`` starts this file with a real window system for what needs
a SHOWN host and the app's own workspace. It only DOES things and writes raw answers to
``result.json`` (frames and videos beside it); the tests judge. It isolates the app's
settings and installs no Qt message handler (it shows windows: ``qt_messages.py``).

    python tests/integration/view3d_capture_driver.py --out <dir> --scenario <name>

Scenarios:

``host``      A plan on a shown host. A capture at the view's size against the view; 4K; a
              camera of its own, and the view afterwards; photo settings, each off again.
``grades``    Every grade against the view; the identity table against the view.
``tour``      The workspace's own recording: a drone orbit into an MP4, read back with Qt.
``timelapse`` A day and a stretch of the year: the clock is put back, frames follow it.
``agent``     The MCP tool's provider on the real workspace: its refusals and its picture.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections.abc import Callable
from datetime import date, datetime
from datetime import time as day_time
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import QEventLoop, Qt, QTimer, QUrl
from PyQt6.QtWidgets import QApplication

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":  # run as a script: make this checkout's code importable
    for entry in (str(REPO / "src"), str(REPO / "scripts"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    import script_isolation

    script_isolation.isolate_profile()  # with scripts/quiet_windows.keep_windows_behind

PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
DAY = date(2026, 6, 21)
VIEW = (640, 360)
HERO = ((2520.0, -448.0, 490.0), (1008.0, 960.0, 160.0), 46.0)
OTHER = ((1000.0, -900.0, 700.0), (1000.0, 800.0, 100.0), 40.0)


def pump(ms: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(ms), loop.quit)
    loop.exec()


def wait_until(condition: Callable[[], Any], limit_s: float) -> float | None:
    started = time.monotonic()
    while time.monotonic() - started < limit_s:
        if condition():
            return time.monotonic() - started
        pump(10)
    return None


def rgb(image: Any) -> Any:
    from open_garden_planner.ui.view3d.quick3d.offscreen import image_rgba

    return image_rgba(image)[..., :3].astype(np.int32)


def difference(first: Any, second: Any) -> dict[str, float]:
    if first.shape != second.shape:
        return {"shape_differs": 1.0}
    delta = np.abs(first - second)
    return {"mean": round(float(delta.mean()), 3), "p99": float(np.percentile(delta, 99)),
            "max": int(delta.max())}


def shown_host(out: Path) -> tuple[Any, Any]:
    """The plan on a shown host of its own, with its forged plants and a sky."""
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.core.phenology import evaluate_phenology_for_records
    from open_garden_planner.core.plant_forge import ForgeCache
    from open_garden_planner.core.scene3d import GroundSpec, SceneSync, SunState
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.core.scene3d.look import look_for
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.view3d.forge_worker import ForgeWorker
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    scene = CanvasScene()
    manager = ProjectManager()
    manager.load(scene, PLAN)
    records = snapshot_records(scene, DAY)
    seasons = evaluate_phenology_for_records(tuple(records.values()), DAY, latitude_deg=52.52)
    host = Quick3DHost(VIEW)
    host.show()
    if not host.wait_ready(20.0):
        raise RuntimeError(f"the shown host did not become live ({host.state.value})")
    sink = Quick3DSink(host)
    sync = SceneSync(sink, production_registry())
    sun = SunState(38.0, 250.0)
    sync.apply(records, sun=sun, ground=GroundSpec(2400.0, 1600.0))
    host.set_plant_seasons(seasons)
    worker = ForgeWorker(sink, cache=ForgeCache(), season_sink=host.set_plant_seasons)
    worker.submit_snapshot(records.values(), plan_date=DAY, latitude_deg=52.52)
    worker.drain()
    worker.shutdown()
    look = look_for(sun, "medium")
    host.set_look(look)
    if not host.is_software_adapter():
        host.set_sky(look.sky)
    host.set_camera(*HERO)
    return host, sync


def window_behind(host: Any) -> dict[str, Any]:
    """Whether the shown view is out of the user's way (``scripts/quiet_windows``), asked of
    Windows itself. None on another platform, where the switch is off."""
    if sys.platform != "win32":
        return {"checked": False}
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32")
    user32.GetForegroundWindow.restype = wintypes.HWND
    view = host._view
    return {"checked": True, "foreground": bool(user32.GetForegroundWindow() == int(view.winId())),
            "no_activation": bool(view.property("_q_showWithoutActivating")),
            "exposed": bool(view.isExposed())}


def scenario_host(out: Path) -> dict[str, Any]:
    from open_garden_planner.core.scene3d.photo import NO_PHOTO, PhotoSettings
    from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

    host, _sync = shown_host(out)
    try:
        host.wait_ready(5.0)
        ratio = host.device_pixel_ratio()
        size = (round(VIEW[0] * ratio), round(VIEW[1] * ratio))
        view = rgb(host.grab("view"))
        taken = host.capture(size, label="same")
        taken.save(str(out / "same.png"))
        result: dict[str, Any] = {
            "behind": window_behind(host),
            "ratio": ratio, "size": size, "format": taken.format().name,
            "taken_size": [taken.width(), taken.height()],
            "capture_vs_view": difference(view, rgb(taken))}
        # the sizes a user can ask for, whatever the window's size and ratio
        sizes = {}
        for wanted in ((1280, 720), (1920, 1080), (3840, 2160), (1000, 1000), (1921, 1081)):
            started = time.perf_counter()
            image = host.capture(wanted, label=f"{wanted}")
            sizes[f"{wanted[0]}x{wanted[1]}"] = {
                "got": [image.width(), image.height()],
                "ms": round((time.perf_counter() - started) * 1000.0, 1),
                "flat": bool(float(rgb(image).std()) < 2.0)}
        result["sizes"] = sizes
        # another camera, for one picture: nothing about the view moves
        camera_before = (host.scene_property("camPos"), host.scene_property("camTarget"))
        other = host.capture(size, PerspectiveShot(*OTHER), label="other")
        other.save(str(out / "other.png"))
        after = rgb(host.grab("after"))
        result["other_vs_view"] = difference(view, rgb(other))
        result["view_after_capture"] = difference(view, after)
        result["camera_kept"] = bool(camera_before == (host.scene_property("camPos"),
                                                       host.scene_property("camTarget")))
        result["capture_off_after"] = host.scene_property("captureWanted") is False
        # the same camera set on the view: the capture of a shot IS the view from there
        host.set_camera(*OTHER)
        result["other_vs_view_moved"] = difference(rgb(host.grab("moved")), rgb(other))
        host.set_camera(*HERO)
        # a selection ring is not in a picture, and is back afterwards
        host.scene_property("selectionVisible")
        # photo settings: on in the picture, off again exactly
        rows: dict[str, Any] = {}
        for name, settings in (("exposure", PhotoSettings(exposure_ev=1.0)),
                               ("vignette", PhotoSettings(vignette=0.6)),
                               ("blur", PhotoSettings(blur=0.8, focus_scene=(1960.0, 260.0, 60.0)))):
            host.set_photo(settings)
            image = host.capture(size, label=name)
            image.save(str(out / f"photo_{name}.png"))
            rows[name] = difference(view, rgb(image))
            host.set_photo(NO_PHOTO)
        result["photo"] = rows
        result["no_photo_again"] = difference(view, rgb(host.capture(size, label="again")))
        # a picture developed differently leaves the view's own settings alone
        host.set_photo(PhotoSettings(exposure_ev=1.0))
        plain = rgb(host.capture(size, photo=NO_PHOTO, label="plain"))
        result["photo_override"] = difference(view, plain)
        result["photo_kept"] = host.photo.exposure_ev == 1.0
        host.set_photo(NO_PHOTO)
        # memory: 30 pictures of a moving camera, with the view presenting
        before = committed_mb()
        spent = []
        for index in range(30):
            started = time.perf_counter()
            host.capture((1920, 1080), PerspectiveShot(
                (1000.0 + 20.0 * index, -900.0, 700.0), (1000.0, 800.0, 100.0), 40.0), label="loop")
            spent.append((time.perf_counter() - started) * 1000.0)
            pump(1)
        pump(300)
        result["loop"] = {"median_ms": round(float(np.median(spent)), 1),
                          "growth_mb": round(committed_mb() - before, 1)}
        health = host.health()
        result["health"] = {"ok": health.ok, "warnings": list(health.qml_warnings),
                            "error": health.scene_graph_error}
        return result
    finally:
        host.close()
        pump(100)


def scenario_grades(out: Path) -> dict[str, Any]:
    from open_garden_planner.core.scene3d.photo import GRADES, NO_GRADE, PhotoSettings, lut_strip
    from open_garden_planner.ui.view3d.quick3d.patterns import PatternTexture

    host, _sync = shown_host(out)
    try:
        host.wait_ready(5.0)
        ratio = host.device_pixel_ratio()
        size = (round(VIEW[0] * ratio), round(VIEW[1] * ratio))
        view = rgb(host.capture(size, label="view"))
        # the identity table with the look's own adjustments: the view, through the table
        mood = host.look.mood
        identity = PatternTexture(*lut_strip(NO_GRADE, saturation=mood.saturation,
                                             contrast=mood.contrast))
        identity.setParent(host._root)
        host._call("showPhotoGrade", host._call("createPhotoGrade", identity))
        through = rgb(host.capture(size, label="identity"))
        host.set_photo(PhotoSettings())
        result: dict[str, Any] = {"identity": difference(view, through)}
        # … and the darkest leaves stay dark (R 0 once became 57: Garden.qml)
        dark = view.max(axis=2) < 60
        result["dark_pixels"] = int(dark.sum())
        result["dark_red_rise"] = int((through[..., 0] - view[..., 0])[dark].max()) if dark.any() else 0
        rows = {}
        for grade in GRADES:
            host.set_photo(PhotoSettings(grade=grade))
            image = host.capture(size, label=grade)
            image.save(str(out / f"grade_{grade}.png"))
            rows[grade] = {**difference(view, rgb(image)),
                           "means": [round(float(rgb(image)[..., c].mean()), 1) for c in range(3)]}
        host.set_photo(PhotoSettings())
        result["grades"] = rows
        result["after"] = difference(view, rgb(host.capture(size, label="after")))
        return result
    finally:
        host.close()
        pump(100)


def scenario_soak(out: Path) -> dict[str, Any]:
    """Memory over many pictures of a moving camera (a tour's shape), with the view presenting,
    in the same size and then in another: committed memory every 50 pictures."""
    from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

    host, _sync = shown_host(out)
    try:
        host.wait_ready(5.0)
        rows: dict[str, list[float]] = {}
        host.begin_captures()
        for size, count in (((1920, 1080), 300), ((3840, 2160), 100)):
            marks = [round(committed_mb(), 1)]
            for index in range(count):
                host.capture(size, PerspectiveShot(
                    (1000.0 + float(index % 100) * 10.0, -900.0, 700.0), (1000.0, 800.0, 100.0), 40.0),
                    wind_time_s=10.0 + index / 30.0, label="soak")
                pump(1)
                if (index + 1) % 50 == 0:
                    marks.append(round(committed_mb(), 1))
            rows[f"{size[0]}x{size[1]}"] = marks
        host.end_captures()
        idle = {"before": round(committed_mb(), 1)}
        host.request_frame()
        pump(2000)
        idle["after_2s"] = round(committed_mb(), 1)
        # single pictures: the capture view is made and destroyed for each
        view = rgb(host.grab("after"))
        idle["single_vs_view"] = difference(view, rgb(host.capture((640, 360), label="single")))
        single_ms = []
        marks = [round(committed_mb(), 1)]
        for index in range(60):
            started = time.perf_counter()
            host.capture((3840, 2160), label="single-4k")
            single_ms.append((time.perf_counter() - started) * 1000.0)
            pump(50)
            if (index + 1) % 20 == 0:
                pump(2000)
                marks.append(round(committed_mb(), 1))
        idle["single_4k_median_ms"] = round(float(np.median(single_ms)), 1)
        idle["single_4k_marks"] = marks
        return {"committed_mb": rows, "idle": idle, "frames_presented": host.health().frames_presented,
                "health": host.health().ok, "warnings": list(host.health().qml_warnings)}
    finally:
        host.close()
        pump(100)


def committed_mb() -> float:
    if sys.platform != "win32":
        with open("/proc/self/statm", encoding="ascii") as statm:
            return int(statm.read().split()[1]) * 4096 / 1e6
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "peak_ws", "ws", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile",
                "peak_pagefile", "private")]

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    kernel = ctypes.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.private / 1e6


def main_window_on_plan() -> tuple[Any, Any]:
    """The app's real window on the plan, in 3D (the settings store is this process's)."""
    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.ui.view3d.workspace import WorkspaceMode

    # nobody clicks here: as in tests/conftest.py, no modal Welcome dialog over the plan
    GardenPlannerApp._show_welcome_dialog = lambda _self: None  # type: ignore[method-assign]
    window = GardenPlannerApp()
    window.resize(1100, 700)
    window.show()
    window._project_manager.load(window.canvas_scene, PLAN)
    window._sim_clock.set_datetime(datetime(2026, 6, 21, 15, 0))
    workspace = window._workspace
    workspace.set_mode(WorkspaceMode.VIEW3D)
    return window, workspace


def settled(workspace: Any, limit_s: float = 60.0) -> float | None:
    capture = workspace.capture
    return wait_until(lambda: capture.capture_blocker() is None, limit_s)


def read_video(path: Path) -> dict[str, Any]:
    """Qt's own decoder on the file: what a player would get."""
    from PyQt6 import QtMultimedia as media

    player = media.QMediaPlayer()
    sink = media.QVideoSink()
    frames: list[Any] = []
    player.setVideoSink(sink)
    sink.videoFrameChanged.connect(lambda frame: frames.append(frame.toImage()) if frame.isValid() else None)
    player.setSource(QUrl.fromLocalFile(str(path)))
    player.play()
    wait_until(lambda: player.mediaStatus() == media.QMediaPlayer.MediaStatus.EndOfMedia
               or player.error() != media.QMediaPlayer.Error.NoError, 60.0)
    answer = {"duration_ms": player.duration(), "frames": len(frames),
              "error": player.errorString(), "bytes": path.stat().st_size if path.exists() else 0}
    if frames:
        answer["size"] = [frames[0].width(), frames[0].height()]
    player.stop()
    return {**answer, "first": frames[0] if frames else None, "last": frames[-1] if frames else None}


def scenario_tour(out: Path) -> dict[str, Any]:
    from open_garden_planner.core.camera_path import DroneOrbit, TourSpec, frame_count
    from open_garden_planner.ui.view3d.video_writer import Mp4Writer

    window, workspace = main_window_on_plan()
    try:
        result: dict[str, Any] = {"settled_s": settled(workspace)}
        capture = workspace.capture
        spec = TourSpec(DroneOrbit(capture.orbit_pose(), turns=1.0), 2.0, 30)
        path = out / "tour.mp4"
        camera_before = workspace.camera.pose
        clock_before = window._sim_clock.wall
        host = workspace.host
        view_before = rgb(host.grab("before"))
        outcome: list[Any] = []
        recorder = capture.start_tour(spec, (1280, 720), Mp4Writer(path, (1280, 720), spec.fps))
        recorder.finished.connect(outcome.append)
        started = time.monotonic()
        result["blocker_while_recording"] = capture.capture_blocker()
        result["done_s"] = wait_until(lambda: bool(outcome), 180.0)
        result["wall_s"] = round(time.monotonic() - started, 2)
        tour = outcome[0]
        result["result"] = {"ok": tour.ok, "frames": tour.frames, "message": tour.message,
                            "unsettled": tour.unsettled}
        result["expected_frames"] = frame_count(spec)
        result["part_left"] = (out / "tour.part.mp4").exists()
        read = read_video(path)
        first, last = read.pop("first"), read.pop("last")
        result["video"] = read
        if first is not None:
            first.save(str(out / "tour_first.png"))
            last.save(str(out / "tour_last.png"))
        result["camera_kept"] = workspace.camera.pose == camera_before
        result["clock_kept"] = window._sim_clock.wall == clock_before
        pump(300)
        result["view_after"] = difference(view_before, rgb(host.grab("after")))
        return result
    finally:
        workspace.shutdown()
        window.close()
        pump(100)


def scenario_timelapse(out: Path) -> dict[str, Any]:
    from open_garden_planner.core.camera_path import HeldCamera, TourSpec
    from open_garden_planner.ui.view3d.video_writer import PngSequenceWriter

    window, workspace = main_window_on_plan()
    try:
        result: dict[str, Any] = {"settled_s": settled(workspace)}
        capture = workspace.capture
        clock_before = window._sim_clock.wall
        rows = {}
        for name, spec in (
                ("day", TourSpec(HeldCamera(capture.camera_key()), 1.0, 24,
                                 time_range=(day_time(8, 0), day_time(20, 0)))),
                ("year", TourSpec(HeldCamera(capture.camera_key()), 1.0, 24,
                                  date_range=(date(2026, 3, 1), date(2026, 10, 31))))):
            outcome: list[Any] = []
            seen: list[tuple[str, str]] = []
            clock = window._sim_clock
            folder = out / name
            before = committed_mb()
            recorder = capture.start_tour(spec, (640, 360), PngSequenceWriter(folder))

            def moment(*_arguments: Any, seen: list[tuple[str, str]] = seen, clock: Any = clock) -> None:
                seen.append((clock.plan_date.isoformat(), clock.time_of_day.isoformat("minutes")))

            recorder.progress.connect(moment)
            recorder.finished.connect(outcome.append)
            started = time.monotonic()
            wait_until(outcome.__len__, 300.0)
            tour = outcome[0] if outcome else None
            rows[name] = {"ok": tour.ok if tour else None, "frames": tour.frames if tour else None,
                          "message": tour.message if tour else "no end",
                          "unsettled": tour.unsettled if tour else None,
                          "wall_s": round(time.monotonic() - started, 1),
                          "growth_mb": round(committed_mb() - before, 1),
                          "files": len(list(folder.glob("frame_*.png"))),
                          "first_moment": seen[0] if seen else None,
                          "last_moment": seen[-1] if seen else None,
                          "clock_back": clock.wall == clock_before}
            settled(workspace)
        result["runs"] = rows
        return result
    finally:
        workspace.shutdown()
        window.close()
        pump(100)


def scenario_daysoak(out: Path) -> dict[str, Any]:
    """Memory over a long time-lapse of a day and of a year (a sky per sun, plants per date):
    committed memory every 60 frames, and what is left a moment after each."""
    from open_garden_planner.core.camera_path import HeldCamera, TourSpec
    from open_garden_planner.ui.view3d.video_writer import NullWriter

    window, workspace = main_window_on_plan()
    try:
        result: dict[str, Any] = {"settled_s": settled(workspace)}
        capture = workspace.capture
        for name, spec in (
                ("day", TourSpec(HeldCamera(capture.camera_key()), 10.0, 24,
                                 time_range=(day_time(6, 0), day_time(21, 0)))),
                ("year", TourSpec(HeldCamera(capture.camera_key()), 10.0, 24,
                                  date_range=(date(2026, 3, 1), date(2026, 10, 31))))):
            outcome: list[Any] = []
            marks = [round(committed_mb(), 1)]

            def note(done: int, _total: int, _image: Any, marks: list[float] = marks) -> None:
                if done % 60 == 0:
                    marks.append(round(committed_mb(), 1))

            started = time.monotonic()
            recorder = capture.start_tour(spec, (1280, 720), NullWriter())
            recorder.progress.connect(note)
            recorder.finished.connect(outcome.append)
            wait_until(outcome.__len__, 700.0)
            pump(3000)
            result[name] = {"marks": marks, "after_3s": round(committed_mb(), 1),
                            "s_per_frame": round((time.monotonic() - started - 3.0) / 240.0, 2),
                            "ok": outcome[0].ok if outcome else None,
                            "unsettled": outcome[0].unsettled if outcome else None}
        return result
    finally:
        workspace.shutdown()
        window.close()
        pump(100)


def scenario_agent(out: Path) -> dict[str, Any]:
    from open_garden_planner.ui.view3d.workspace import WorkspaceMode
    from open_garden_planner.ui.view3d.workspace_capture import CaptureRefused

    window, workspace = main_window_on_plan()
    result: dict[str, Any] = {}

    def ask(*arguments: Any) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            answer = window._agent_render_3d(*arguments)
        except CaptureRefused as refused:
            return {"refused": refused.code, "text": str(refused),
                    "ms": round((time.perf_counter() - started) * 1000.0, 1)}
        return {"png_bytes": len(answer["png_bytes"]), **{k: v for k, v in answer.items() if k != "png_bytes"},
                "ms": round((time.perf_counter() - started) * 1000.0, 1)}

    try:
        result["while_warming"] = ask(None, (640, 360))
        result["settled_s"] = settled(workspace)
        host = workspace.host
        pump(200)
        before = rgb(host.grab("before"))
        camera_before, clock_before = workspace.camera.pose, window._sim_clock.wall
        undo_before = window.canvas_view.command_manager.can_undo
        dirty_before = window._project_manager.is_dirty
        own = window._agent_render_3d(None, (640, 360))
        (out / "agent_own.png").write_bytes(own["png_bytes"])
        other = window._agent_render_3d(
            ((1000.0, -900.0, 700.0), (1000.0, 800.0, 100.0), 40.0), (1024, 576))
        (out / "agent_other.png").write_bytes(other["png_bytes"])
        result["own"] = {k: v for k, v in own.items() if k != "png_bytes"}
        result["other"] = {k: v for k, v in other.items() if k != "png_bytes"}
        result["camera_kept"] = workspace.camera.pose == camera_before
        result["clock_kept"] = window._sim_clock.wall == clock_before
        result["undo_kept"] = window.canvas_view.command_manager.can_undo == undo_before
        result["dirty_kept"] = window._project_manager.is_dirty == dirty_before
        pump(200)
        result["view_after"] = difference(before, rgb(host.grab("after")))
        workspace.set_mode(WorkspaceMode.PLAN)
        pump(200)
        result["in_plan_mode"] = ask(None, (640, 360))
        workspace.set_mode(WorkspaceMode.VIEW3D)
        settled(workspace)
        back: list[Any] = []

        def came_back() -> bool:   # a host that was hidden comes back with its next frame
            back[:] = [ask(None, (640, 360))]
            return "image_width_px" in back[0]

        result["back_in_3d_s"] = wait_until(came_back, 10.0)
        result["back_in_3d"] = back[0].get("image_width_px") if back else None
        return result
    finally:
        workspace.shutdown()
        window.close()
        pump(100)


SCENARIOS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "host": scenario_host, "grades": scenario_grades, "tour": scenario_tour,
    "timelapse": scenario_timelapse, "agent": scenario_agent, "soak": scenario_soak,
    "daysoak": scenario_daysoak,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    parser.add_argument("--limit-s", default=400.0, type=float,
                        help="dump every thread's stack and exit after this long")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    script_isolation.isolate()
    import faulthandler

    faulthandler.dump_traceback_later(float(args.limit_s), exit=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    try:
        result = SCENARIOS[args.scenario](out)
        status = 0
    except Exception as error:  # noqa: BLE001 - the test reads the failure from the file
        result = {"failed": f"{type(error).__name__}: {error}", "trace": traceback.format_exc()}
        status = 1
    (out / "result.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
