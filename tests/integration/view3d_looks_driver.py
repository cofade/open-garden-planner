"""The engine-side half of the LOOKS' render tier (Phase 17 L1.4, #385) — not a test module.

``test_view3d_looks_render.py`` starts this file with a real window system for what
needs a SHOWN host — a window Qt presents, a render loop on a thread of its own:

    python tests/integration/view3d_looks_driver.py --out <dir> --scenario <name> [--arg k=v …]

(Everything that one never-shown frame can answer — the board's shots, the shadow
IoU, north-up, the sky's azimuth, how fog meets sky — is ``scripts/render_beauty_board.py``,
which the same tests run.)

The driver only DOES engine things and writes raw answers to ``result.json`` and
frames as PNGs; the tests judge. Like the engine story's driver it installs no Qt
message handler (it shows windows: ``qt_messages.py``): Qt prints to stderr in the
pattern the caller set, and the judge classifies.

Scenarios:

``sky_sequence``  the sun moves A -> B -> C, a sky is built for each, a frame is read
                  after each — and one more after the old Textures and their data
                  objects are gone. The sky must still be the sky (the rule the
                  ground bake found: a Texture loses its data when a data object it
                  held EARLIER is destroyed).
``wind``          the wind's clock on the real render loop: at rest, running,
                  stopped (frozen where it is), at rest again — with the frames.
``controller``    the product's ``LookController`` on a real host through a scripted
                  day: sky builds counted in the ENGINE, the light's direction read
                  from the scene. ``software=1``: the compatibility mode (no sky, no
                  wind).
``wind_soak``     the product's default steady state — the plan shown, the wind
                  running — for ``minutes``: committed memory every 5 s, NO readback in
                  the loop; the slope per minute over the second half.
``sky_soak``      N sun changes with a sky each, committed memory after every one,
                  NO readback inside the loop (a readback renders a frame that is
                  never presented: ADR-065). ``frames=withheld``: nothing is drawn
                  for the length of the loop. ``leak=1``: the positive control — a
                  scene file whose ``buildSky`` never destroys the old Texture.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import ctypes
import gc
import json
import math
import os
import platform
import shutil
import statistics
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":  # run as a script: make this checkout's code importable
    for entry in (str(REPO / "src"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

from open_garden_planner.core.scene3d import GroundSpec, SceneSync, SunState  # noqa: E402
from open_garden_planner.core.scene3d.look import NEUTRAL_DAY, look_for  # noqa: E402

VIEW = (640, 360)
PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
#: The sky view of ``sky_sequence``: ONE camera, looking south-south-west and pitched up
#: 14° (the board's sky view), and three suns 12° up — 25° left of it, 15° and 30° right.
#: One camera, so that the three frames are three different pictures and the sun's
#: disc is off-centre in each.
SKY_ELEVATION, SKY_PITCH, SKY_FOV = 12.0, 14.0, 70.0
SEQUENCE_VIEW_AZIMUTH = 185.0
SEQUENCE_AZIMUTHS = (160.0, 200.0, 215.0)
#: The scripted day of ``controller``: (elevation, azimuth) — moves below the sky's
#: threshold, noticeable ones, dusk, a night that goes on, dawn.
DAY = ((35.0, 120.0), (35.2, 120.3), (35.4, 120.6), (48.0, 150.0), (48.3, 150.2), (60.0, 180.0),
       (30.0, 250.0), (6.0, 290.0), (0.6, 300.0), (0.4, 300.2), (-12.0, 330.0), (-20.0, 10.0),
       (0.7, 55.0), (20.0, 80.0))
#: The soak's gate: the second-half slope of committed memory per sun change. Registered
#: at 2.0 before the first run, when a sky was 32 MB (the first run read -0.4 presenting,
#: 0.0 with frames withheld, and 32.2 for the leak control); since round 3 a sky is 8 MB
#: (1024 x 512 float texels), so the bound is 1.0 — an eighth of one leaked sky — and
#: the control must exceed 4.0.
SOAK_BOUND_MB = 1.0
SOAK_CONTROL_MB = 4.0
#: The wind soak's gate (review, fix round 1: no soak measured the default steady state,
#: the wind running while shown): committed memory per MINUTE over the second half
#: (Theil-Sen), registered at 2.0 before the first run — a frame of a running wind
#: allocates nothing it keeps; 2 MB a minute would be 120 MB an hour.
WIND_SOAK_BOUND_MB_PER_MIN = 2.0


def sky_camera() -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    bearing = math.radians(SEQUENCE_VIEW_AZIMUTH)
    return ((0.0, 0.0, 160.0), (math.sin(bearing) * 1000.0, math.cos(bearing) * 1000.0,
                                160.0 + 1000.0 * math.tan(math.radians(SKY_PITCH))))


def instruments() -> dict[str, Any]:
    """The workspace gate's own memory instruments — ``private_mb`` (committed memory),
    ``theil_sen`` and ``gpu_dedicated_mb`` (DXGI) — taken from ITS file by name, so that
    there is one definition of each. (That module cannot be imported outside the
    gate: its first import is the gate's hook.)"""
    source = Path(__file__).with_name("workspace_gate_measure.py").read_text(encoding="utf-8")
    wanted = {"private_mb", "theil_sen", "gpu_dedicated_mb"}
    body = [node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert {node.name for node in body} == wanted, "the gate's instruments were renamed"
    namespace: dict[str, Any] = {"ctypes": ctypes, "os": os, "sys": sys, "statistics": statistics,
                                 "Any": Any}
    exec(compile(ast.Module(body=body, type_ignores=[]), "workspace_gate_measure.py", "exec"),  # noqa: S102
         namespace)
    return namespace


class Context:
    def __init__(self, out: Path, log: Any, arguments: dict[str, str]) -> None:
        self.out, self.log, self.arguments = out, log, arguments

    def flag(self, name: str) -> bool:
        return self.arguments.get(name, "0") not in ("0", "", "false")

    def save(self, name: str, image: Any) -> str:
        path = self.out / f"{name}.png"
        if not image.save(str(path)):
            raise RuntimeError(f"could not write {path}")
        return path.name

    def host(self, *, software: bool = False, qml_dir: Path | None = None,
             size: tuple[int, int] = VIEW) -> Any:
        from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

        made = Quick3DHost(size, qml_dir=qml_dir, log=self.log, prefer_software=software)
        made.show()
        if not made.wait_ready(20.0):
            state = made.state.value
            made.close()
            raise RuntimeError(f"the shown host did not become live (state {state})")
        return made


def pump(ms: float = 30.0) -> None:
    from PyQt6.QtCore import QCoreApplication, QEvent

    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        QCoreApplication.processEvents()
        time.sleep(0.001)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def _health(host: Any) -> dict[str, Any]:
    health = host.health()
    return {"ok": health.ok, "frames_presented": health.frames_presented,
            "qml_warnings": list(health.qml_warnings),
            "scene_graph_error": health.scene_graph_error,
            "slots_off_gui_thread": host.slot_calls_off_the_gui_thread}


def _light_travel(host: Any) -> list[float] | None:
    from PyQt6.QtGui import QVector3D

    if not host.scene_property("sunUp"):
        return None
    shines = host.scene_property("sunRotation").rotatedVector(QVector3D(0.0, 0.0, -1.0))
    return [shines.x(), shines.y(), shines.z()]


# ── scenarios ────────────────────────────────────────────────────────────────


def scenario_sky_sequence(ctx: Context) -> dict[str, Any]:
    from PyQt6 import sip

    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    host = ctx.host()
    try:
        sync = SceneSync(Quick3DSink(host))
        steps: list[dict[str, Any]] = []
        textures: list[tuple[Any, Any]] = []
        eye, target = sky_camera()
        host.set_camera(eye, target, SKY_FOV)
        for name, azimuth in zip("ABC", SEQUENCE_AZIMUTHS, strict=True):
            sun = SunState(SKY_ELEVATION, azimuth)
            look = look_for(sun, "low")
            sync.set_sun(sun)
            host.set_look(look)
            host.set_sky(look.sky)
            texture = host.scene_property("skyTextureObject")
            textures.append((texture, texture.property("textureData")))
            file = ctx.save(f"sky_{name}", host.grab(f"sky_{name}"))
            steps.append({"name": name, "azimuth": azimuth, "file": file,
                          "build_ms": round(host.last_sky_build_ms, 1),
                          "sky_builds": host.sky_builds,
                          "engine_builds": int(host.scene_property("skyBuilds")),
                          "alive": [not sip.isdeleted(t) for t, _d in textures]})
        pump(300)       # the old Textures and their data objects are deleted now
        gc.collect()
        after = ctx.save("sky_C_after_delete", host.grab("sky_C_after_delete"))
        pump(200)
        later = ctx.save("sky_C_later", host.grab("sky_C_later"))
        return {"steps": steps, "after_delete": after, "later": later,
                "textures_alive": [not sip.isdeleted(t) for t, _d in textures],
                "data_alive": [not sip.isdeleted(d) for _t, d in textures],
                "sky_built": bool(host.scene_property("skyBuilt")),
                "view": {"elevation": SKY_ELEVATION, "azimuth": SEQUENCE_VIEW_AZIMUTH,
                         "pitch": SKY_PITCH, "fov": SKY_FOV},
                "health": _health(host), "graphics_api": host.graphics_api()}
    finally:
        host.close()
        pump()


def scenario_wind(ctx: Context) -> dict[str, Any]:
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from tests.integration import quick3d_render_driver as engine

    host = ctx.host(size=engine.VIEW)
    try:
        sync = SceneSync(Quick3DSink(host), engine.rest_registry())
        sync.apply(engine.rest_records(), sun=engine.HIGH_SUN, ground=engine.GROUND)
        host.set_look(replace(NEUTRAL_DAY, wind_strength=engine.REST_WIND))
        host.set_shot(engine.TOP)
        out: dict[str, Any] = {"wind_strength": engine.REST_WIND, "frames": {}, "clock": {}}

        def frame(name: str) -> None:
            out["frames"][name] = ctx.save(f"wind_{name}", host.grab(f"wind_{name}"))
            out["clock"][name] = float(host.scene_property("windTime"))

        frame("0_rest")
        host.set_wind_running(True)
        pump(2600)                      # past the two seconds the shaders ease the sway in over
        frame("1_running")
        host.set_wind_running(False)
        frozen = float(host.scene_property("windTime"))
        pump(500)
        out["frozen_moved_by"] = float(host.scene_property("windTime")) - frozen
        frame("2_stopped")
        frame("3_stopped_again")
        host.rest_wind()
        frame("4_rest_again")
        # what the ENGINE does with a clock that runs while the window is hidden — the
        # reason the policy stops it, instead of trusting "hidden" to do so
        host.set_wind_running(True)
        pump(100)
        host.hide()
        pump(100)
        before = float(host.scene_property("windTime"))
        pump(600)
        out["hidden_and_running_moved_by"] = float(host.scene_property("windTime")) - before
        host.rest_wind()
        out["health"] = _health(host)
        return out
    finally:
        host.close()
        pump()


def scenario_controller(ctx: Context) -> dict[str, Any]:
    from open_garden_planner.ui.view3d.look_controller import SKY_SETTLE_MS, LookController
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    software = ctx.flag("software")
    host = ctx.host(software=software)
    try:
        sync = SceneSync(Quick3DSink(host))
        sync.set_ground(GroundSpec(2400.0, 1600.0))
        look = LookController(host, software=software, quality="high")
        look.set_showing(True)
        host.set_camera((1200.0, -1500.0, 700.0), (1200.0, 800.0, 100.0), 46.0)
        steps: list[dict[str, Any]] = []
        for elevation, azimuth in DAY:
            sun = SunState(elevation, azimuth)
            sync.set_sun(sun)
            look.set_sun(sync.sun)
            pump(SKY_SETTLE_MS + 200)
            steps.append({"sun": [elevation, azimuth], "night": bool(look.look and look.look.night),
                          "light_travel": _light_travel(host), "sky_builds": host.sky_builds,
                          "controller_rebuilds": look.sky_rebuilds,
                          "sky_built": bool(host.scene_property("skyBuilt")),
                          "exposure": float(host.scene_property("exposure"))})
        last = ctx.save("controller_last", host.grab("controller_last"))
        running = bool(host.scene_property("windRunning"))
        moving_from = float(host.scene_property("windTime"))
        pump(400)
        moved_shown = float(host.scene_property("windTime")) - moving_from
        look.set_showing(False)         # the pane was hidden: the policy stops the clock
        stopped_at = float(host.scene_property("windTime"))
        pump(500)
        moved_hidden = float(host.scene_property("windTime")) - stopped_at
        look.set_showing(True)
        look.set_reduced_motion(True)
        at_rest = float(host.scene_property("windTime"))
        look.shutdown()
        return {"software": software, "steps": steps, "last": last, "look_calls": look.look_calls,
                "wind": {"running_while_shown": running, "moved_while_shown": moved_shown,
                         "moved_while_hidden": moved_hidden, "after_reduced_motion": at_rest},
                "frames_taken_by_the_controller": 0, "health": _health(host),
                "graphics_api": host.graphics_api()}
    finally:
        host.close()
        pump()


def _leaking_copy(target: Path) -> Path:
    """The positive control's scene file: ``buildSky`` never destroys the old Texture."""
    from open_garden_planner.ui.view3d.quick3d.host import QML_DIR

    shutil.copytree(QML_DIR, target)
    scene = target / "Garden.qml"
    text = scene.read_text(encoding="utf-8")
    old = "        if (old)\n            old.destroy()              // ... and only then the old pair goes (deferred)\n"
    assert old in text, "the control no longer finds buildSky's destroy in Garden.qml"
    scene.write_text(text.replace(old, ""), encoding="utf-8")
    return target


def scenario_sky_soak(ctx: Context) -> dict[str, Any]:
    from PyQt6.QtCore import QEvent, QObject

    from open_garden_planner.core import ProjectManager
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    tools = instruments()
    private_mb, theil_sen, gpu_mb = tools["private_mb"], tools["theil_sen"], tools["gpu_dedicated_mb"]
    changes = int(ctx.arguments.get("changes", "20"))
    withheld = ctx.arguments.get("frames", "presented") == "withheld"
    leak = ctx.flag("leak")
    qml_dir = _leaking_copy(ctx.out / "qml_leak") if leak else None

    class NoPaint(QObject):
        eaten = 0

        def eventFilter(self, _watched: Any, event: Any) -> bool:  # noqa: N802 - Qt's name
            if event.type() in (QEvent.Type.Expose, QEvent.Type.UpdateRequest, QEvent.Type.Paint):
                NoPaint.eaten += 1
                return True
            return False

    from datetime import date

    scene = CanvasScene()
    ProjectManager().load(scene, PLAN)
    records = snapshot_records(scene, date(2026, 6, 21))
    host = ctx.host(qml_dir=qml_dir)
    try:
        sync = SceneSync(Quick3DSink(host), production_registry())
        first_sun = SunState(30.0, 100.0)
        sync.apply(records, sun=first_sun, ground=GroundSpec(float(scene.width_cm), float(scene.height_cm)))
        host.set_camera((2700.0, -700.0, 600.0), (1100.0, 900.0, 160.0), 46.0)

        def show(sun: SunState) -> None:
            look = look_for(sun, "high")
            sync.set_sun(sun)
            host.set_look(look)
            host.set_sky(look.sky)

        def present(timeout_s: float = 3.0) -> bool:
            wanted = host.health().frames_presented + 1
            host._view.update()  # noqa: SLF001 - an ordinary frame of the render loop, not a readback
            end = time.perf_counter() + timeout_s
            while time.perf_counter() < end and host.health().frames_presented < wanted:
                pump(5)
            return bool(host.health().frames_presented >= wanted)

        suns = [SunState(30.0 + 2.0 * (k % 5), 100.0 + 7.0 * k) for k in range(1, changes + 1)]
        for sun in (first_sun, *suns[:3], first_sun):   # warm up: shaders, the first probes
            show(sun)
            present()
        pump(200)
        before = ctx.save("soak_before", host.grab("soak_before"))   # the ONE frame before …
        present()
        present()
        pump(300)
        blocker: Any = None
        if withheld:
            blocker = NoPaint()
            host._view.installEventFilter(blocker)  # noqa: SLF001
            pump(100)
        gc.collect()
        start_mb, gpu_before = round(private_mb(), 2), gpu_mb()
        frames_at_start, builds_at_start = host.health().frames_presented, host.sky_builds
        releases_at_start = host.cache_releases
        curve: list[float] = []
        gpu_curve: list[float | None] = []
        for sun in suns:
            show(sun)
            if not withheld:
                present(2.0)
                present(2.0)
            pump(40)
            gc.collect()
            curve.append(round(private_mb(), 2))
            gpu = gpu_mb()
            gpu_curve.append(gpu.get("process_dedicated_mb") if gpu.get("available") else None)
        in_the_loop = {"frames_presented": host.health().frames_presented - frames_at_start,
                       "frames_read_back": 0, "sky_builds": host.sky_builds - builds_at_start,
                       "cache_releases": host.cache_releases - releases_at_start,
                       "paint_events_eaten": NoPaint.eaten}
        if blocker is not None:
            host._view.removeEventFilter(blocker)  # noqa: SLF001
        show(first_sun)                                              # … and the ONE after:
        presented_again = present(10.0)                              # the same sun, the same sky
        pump(200)
        after = ctx.save("soak_after", host.grab("soak_after"))
        present()
        pump(300)
        gc.collect()
        half = curve[len(curve) // 2:]
        gpu_values = [value for value in gpu_curve if value is not None]
        return {
            "changes": changes, "frames": "withheld" if withheld else "presented", "leak": leak,
            "start_mb": start_mb, "curve_mb": curve, "end_mb": round(private_mb(), 2),
            "slope_second_half_mb_per_change": round(theil_sen(half), 3),
            "slope_all_mb_per_change": round(theil_sen(curve), 3),
            "growth_mb": round(curve[-1] - start_mb, 2),
            "gpu_before": gpu_before, "gpu_after": gpu_mb(), "gpu_curve_mb": gpu_curve,
            "gpu_slope_second_half_mb_per_change": (
                round(theil_sen(gpu_values[len(gpu_values) // 2:]), 3) if len(gpu_values) > 3 else None),
            "in_the_loop": in_the_loop, "presented_again": presented_again,
            "before": before, "after": after, "parts": host.part_count(),
            "bound_mb": SOAK_BOUND_MB, "control_mb": SOAK_CONTROL_MB, "health": _health(host),
            "graphics_api": host.graphics_api()}
    finally:
        host.close()
        pump()


def scenario_wind_soak(ctx: Context) -> dict[str, Any]:
    from datetime import date

    from open_garden_planner.core import ProjectManager
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    tools = instruments()
    private_mb, theil_sen, gpu_mb = tools["private_mb"], tools["theil_sen"], tools["gpu_dedicated_mb"]
    minutes = float(ctx.arguments.get("minutes", "2"))
    scene = CanvasScene()
    ProjectManager().load(scene, PLAN)
    records = snapshot_records(scene, date(2026, 6, 21))
    host = ctx.host()
    try:
        sync = SceneSync(Quick3DSink(host), production_registry())
        sun = SunState(30.0, 200.0)
        sync.apply(records, sun=sun, ground=GroundSpec(float(scene.width_cm), float(scene.height_cm)))
        host.set_camera((2700.0, -700.0, 600.0), (1100.0, 900.0, 160.0), 46.0)
        look = look_for(sun, "high")
        host.set_look(look)
        host.set_sky(look.sky)
        host.set_wind_running(True)              # the default steady state: shown, wind on
        pump(5000)                                # warm up: shaders, the probe, the first frames
        gc.collect()
        frames_at_start, clock_at_start = host.health().frames_presented, float(
            host.scene_property("windTime"))
        start_mb = round(private_mb(), 2)
        curve: list[float] = []
        gpu_curve: list[float | None] = []
        seconds = int(minutes * 60.0)
        js_gc = ctx.flag("jsgc")                  # a diagnosis: the QML engine's collector too
        for _ in range(seconds // 5):
            pump(5000)                            # frames flow; nothing is read back
            gc.collect()
            if js_gc:
                host._view.engine().collectGarbage()  # noqa: SLF001 - a diagnostic arm
                pump(50)
            curve.append(round(private_mb(), 2))
            gpu = gpu_mb()
            gpu_curve.append(gpu.get("process_dedicated_mb") if gpu.get("available") else None)
        frames = host.health().frames_presented - frames_at_start
        clock_moved = float(host.scene_property("windTime")) - clock_at_start
        host.rest_wind()
        half = curve[len(curve) // 2:]
        gpu_values = [value for value in gpu_curve if value is not None]
        per_sample = theil_sen(half)
        return {
            "minutes": minutes, "js_gc": js_gc, "start_mb": start_mb, "curve_mb": curve,
            "slope_second_half_mb_per_min": round(per_sample * 12.0, 3),
            "gpu_curve_mb": gpu_curve,
            "gpu_slope_second_half_mb_per_min": (
                round(theil_sen(gpu_values[len(gpu_values) // 2:]) * 12.0, 3)
                if len(gpu_values) > 3 else None),
            "in_the_loop": {"frames_presented": frames, "frames_read_back": 0,
                            "wind_clock_moved_s": round(clock_moved, 2),
                            "sky_builds": host.sky_builds - 1},
            "bound_mb_per_min": WIND_SOAK_BOUND_MB_PER_MIN, "health": _health(host),
            "graphics_api": host.graphics_api()}
    finally:
        host.close()
        pump()


SCENARIOS: dict[str, Callable[[Context], dict[str, Any]]] = {
    "sky_sequence": scenario_sky_sequence,
    "wind": scenario_wind,
    "controller": scenario_controller,
    "sky_soak": scenario_sky_soak,
    "wind_soak": scenario_wind_soak,
}


def _isolate(out: Path) -> None:
    """Run by hand — not through the tests' ``isolated_env`` — this file still must not
    touch the developer's data or settings (``quick3d_render_driver.py`` says why)."""
    from tests.integration.quick3d_render_support import ISOLATED_MARK, private_dirs

    if os.environ.get(ISOLATED_MARK) != "1":
        os.environ.update(private_dirs(out / "private"))
    import open_garden_planner.app.settings as app_settings

    app_settings.ORGANIZATION_NAME = "cofade_test"
    app_settings.APPLICATION_NAME = f"Open Garden Planner Looks Tier {os.getpid()}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    parser.add_argument("--arg", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--watchdog-s", type=float, default=600.0)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    _isolate(args.out)

    from PyQt6.QtCore import QT_VERSION_STR

    from open_garden_planner.ui.view3d.quick3d import offscreen

    log = offscreen.RenderLog(args.out / "render.log")
    arguments = dict(item.split("=", 1) for item in args.arg)
    result: dict[str, Any] = {"status": "running", "scenario": args.scenario, "arguments": arguments,
                              "platform": platform.platform(), "qt": QT_VERSION_STR}

    def write() -> None:
        (args.out / "result.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")

    code = 0
    started = time.perf_counter()
    try:
        with offscreen.watchdog(args.watchdog_s, log, what=f"the looks driver ({args.scenario})",
                                supervised=True):
            offscreen.ensure_application()
            log("scenario", name=args.scenario, **arguments)
            print(f"OGPQT|scenario|{args.scenario}", file=sys.stderr, flush=True)
            result["data"] = SCENARIOS[args.scenario](Context(args.out, log, arguments))
            print("OGPQT|scenario|", file=sys.stderr, flush=True)
        result["status"] = "ok"
    except Exception as error:  # noqa: BLE001 - a driver: record it, never lose it
        result["status"] = "error"
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()
        log("error", error=result["error"])
        code = 2
    finally:
        result["total_s"] = round(time.perf_counter() - started, 2)
        write()
        log("done", status=result["status"], total_s=result["total_s"])
        log.close()
        with contextlib.suppress(Exception):
            import open_garden_planner.app.settings as app_settings

            app_settings.create_qsettings().clear()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
