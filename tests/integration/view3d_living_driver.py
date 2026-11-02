"""The engine-side half of the LIVING GARDEN's render tier (Phase 17 L5, #389) — not a
test module.

``test_living_garden_render.py`` starts this file with a real window system for what
needs a SHOWN host:

    python tests/integration/view3d_living_driver.py --out <dir> --scenario <name> [--arg k=v …]

The driver only DOES engine things and writes raw answers to ``result.json`` (and
frames as PNGs); the tests judge. It installs no Qt message handler (it shows windows:
``qt_messages.py``).

Scenarios:

``idle``        issue #389's gate: with reduced motion the idle frame counter stays at
                0. The product's ``LookController`` on a shown host, raining, the
                garden's life on: the presented frames over a quiet stretch — with
                reduced motion, and (the positive control) without it.
``frame_cost``  issue #389's gate: the particles cost at most 15 % of a frame at
                Medium — the cost of a finished frame, read back, interleaved round by
                round (``scenario_frame_cost`` says why), the look without the living
                garden against clear, rain and snow with the garden's life.
``stills``      a frame of each weather on the plan (the reviewer's look, in a window).
``reload``      the ambient buffer loaded AGAIN into the same live host — a bulb's glow
                at one place, then nothing, then a glow at another place — each frame
                read back. ADR-069 withdrew an in-place reload that drew a replaced
                geometry as nothing; the product reloads this buffer on every date step
                and every light edit (senior review of L5).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import statistics
import sys
import time
import traceback
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":  # run as a script: make this checkout's code importable
    for entry in (str(REPO / "src"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

VIEW = (1280, 720)
PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
#: The quiet stretch of ``idle``, seconds, and how long a block of ``frame_cost`` runs.
QUIET_S = 2.5
BLOCK_S = 3.0
WARM_S = 1.0
#: June noon in Berlin: butterflies by day, the plan in leaf.
DAY = date(2026, 6, 21)


class Context:
    def __init__(self, out: Path, log: Any, arguments: dict[str, str]) -> None:
        self.out, self.log, self.arguments = out, log, arguments

    def save(self, name: str, image: Any) -> str:
        path = self.out / f"{name}.png"
        if not image.save(str(path)):
            raise RuntimeError(f"could not write {path}")
        return path.name


def pump(ms: float) -> None:
    from PyQt6.QtCore import QCoreApplication

    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        QCoreApplication.processEvents()
        time.sleep(0.001)


def _plan() -> tuple[dict[str, Any], Any, float]:
    """The bench plan's records on ``DAY``, their phenology and the plan's latitude."""
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.core.phenology import evaluate_phenology_for_records
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    scene = CanvasScene()
    manager = ProjectManager()
    manager.load(scene, PLAN)
    latitude = float((manager.location or {}).get("latitude", 52.52))
    records = snapshot_records(scene, DAY)
    seasons = evaluate_phenology_for_records(tuple(records.values()), DAY, latitude_deg=latitude)
    return records, seasons, latitude


def _host(ctx: Context, size: tuple[int, int] = VIEW) -> Any:
    from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

    made = Quick3DHost(size, log=ctx.log)
    made.show()
    if not made.wait_ready(20.0):
        state = made.state.value
        made.close()
        raise RuntimeError(f"the shown host did not become live (state {state})")
    return made


def _scene(host: Any, records: dict[str, Any], seasons: Any, latitude: float) -> tuple[Any, Any]:
    """The plan on the host, its life loaded; the camera on the board's hero shot."""
    from open_garden_planner.core.scene3d import GroundSpec, SceneSync, SunState
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.core.scene3d.particles import ambient_buffers, ambient_emitters
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    sync = SceneSync(Quick3DSink(host), production_registry())
    sun = SunState(60.9, 176.1)
    sync.apply(records, sun=sun, ground=GroundSpec(2400.0, 1600.0))
    host.set_plant_seasons(seasons)
    host.set_ambient(ambient_buffers(ambient_emitters(records.values(), seasons, DAY, latitude)))
    host.set_camera((2520.0, -448.0, 490.0), (1008.0, 960.0, 160.0), 46.0)   # the board's hero
    return sync, sun


def _health(host: Any) -> dict[str, Any]:
    health = host.health()
    return {"ok": health.ok, "frames_presented": health.frames_presented,
            "qml_warnings": list(health.qml_warnings), "scene_graph_error": health.scene_graph_error}


# ── scenarios ────────────────────────────────────────────────────────────────


def _settle(host: Any, before: int, quiet_s: float = 1.0, longest_s: float = 30.0) -> float | None:
    """Wait until the first build has been PRESENTED — a frame after ``before`` — and
    the view has then presented no frame for ``quiet_s``; say after how long. None: it
    never went quiet (an animated view, the positive control).

    "No frame for a while" alone is not "settled": the scene's update requests come at
    once, but on the bench plan their first frame — the plan's pipelines, the sky's
    light probe filtered — was presented about three seconds later, and a quiet stretch
    measured before it counted the first picture as idle frames (measured under the
    render tier's environment: requests at 1.8 s, both frames at 4.8-5.0 s)."""
    start = time.perf_counter()
    last_frames, last_change = host.health().frames_presented, start
    while time.perf_counter() - start < longest_s:
        pump(50)
        frames = host.health().frames_presented
        now = time.perf_counter()
        if frames != last_frames:
            last_frames, last_change = frames, now
        elif frames > before and now - last_change >= quiet_s:
            return round(now - start, 2)
    return None


def scenario_idle(ctx: Context) -> dict[str, Any]:
    """Reduced motion: raining, life on, the product's controller — no frame while idle."""
    from open_garden_planner.core.scene3d import SunState
    from open_garden_planner.ui.view3d.look_controller import LookController

    records, seasons, latitude = _plan()
    out: dict[str, Any] = {}
    for reduced in (True, False):
        host = _host(ctx, (640, 360))
        try:
            _scene(host, records, seasons, latitude)
            look = LookController(host, software=False, quality="medium", reduced_motion=reduced)
            look.set_weather("rain")
            look.set_sun(SunState(40.0, 200.0))
            before_build = host.health().frames_presented
            look.set_showing(True)
            settled_after = _settle(host, before_build)   # the plan, the sky, its probe: shown
            before = host.health().frames_presented
            clock_before = float(host.scene_property("windTime"))
            pump(QUIET_S * 1000.0)
            after = host.health().frames_presented
            out["reduced" if reduced else "animated"] = {
                "frames_during_quiet": after - before, "quiet_s": QUIET_S,
                "wind_time": [clock_before, float(host.scene_property("windTime"))],
                "precip_kind": int(host.scene_property("precipKind")),
                "precip_loads": host.precipitation_loads, "ambient_visible":
                    bool(host.scene_property("ambientVisible")),
                "animating": look.animating, "settled_after_s": settled_after,
                "health": _health(host)}
            look.shutdown()
        finally:
            host.close()
            pump(100)
    return out


def _fps(host: Any, seconds: float) -> float:
    pump(WARM_S * 1000.0)
    start, frames = time.perf_counter(), host.health().frames_presented
    pump(seconds * 1000.0)
    return (host.health().frames_presented - frames) / (time.perf_counter() - start)


def scenario_frame_cost(ctx: Context) -> dict[str, Any]:
    """What the particles cost a frame at Medium (issue #389: at most 15 %).

    THE INSTRUMENT: the cost of a finished frame, read back (``grab()`` renders the
    current state and reads it back, synchronously) — interleaved: in every round
    each look renders once, so a machine whose clocks drift moves every look alike
    (blocks of seconds drifted 24 % on the dev box). The baseline is the look WITHOUT
    the living garden (``look.CLEAR_STILL``); against it: clear with the garden's life,
    rain and snow (3,600 particles) with it. A readback adds its own time to every
    sample alike, so the share is a lower bound of the GPU's — and the presented
    frame rate is reported too (display-paced on most machines: ~60)."""
    from dataclasses import replace

    from open_garden_planner.core.scene3d.look import CLEAR_STILL
    from open_garden_planner.core.scene3d.weather import living_look

    rounds = int(ctx.arguments.get("rounds", "40"))
    records, seasons, latitude = _plan()
    host = _host(ctx)
    try:
        _sync, sun = _scene(host, records, seasons, latitude)
        clear = living_look(sun, "medium", "clear")
        looks = {"still": replace(clear, atmosphere=CLEAR_STILL), "clear": clear,
                 "rain": living_look(sun, "medium", "rain"),
                 "snow": living_look(sun, "medium", "snow")}
        for _warm in range(3):                       # every pipeline compiled, every buffer loaded
            for look in looks.values():
                host.set_look(look)
                host.grab("warm")
        samples: dict[str, list[float]] = {name: [] for name in looks}
        for _round in range(rounds):
            for name, look in looks.items():
                host.set_look(look)
                started = time.perf_counter()
                host.grab(name)
                samples[name].append((time.perf_counter() - started) * 1000.0)
        median = {name: statistics.median(values) for name, values in samples.items()}
        cost = {name: median[name] / median["still"] - 1.0 for name in ("clear", "rain", "snow")}
        presented = {}
        host.set_wind_running(True)
        for name in ("still", "rain"):
            host.set_look(looks[name])
            presented[name] = _fps(host, BLOCK_S)
        host.set_wind_running(False)
        host.set_look(looks["rain"])
        frame = ctx.save("cost_rain", host.grab("cost_rain"))
        return {"readback_ms": median, "cost": cost, "rounds": rounds,
                "readback_spread_ms": {name: [min(v), max(v)] for name, v in samples.items()},
                "presented_fps": presented, "frame": frame, "size": list(VIEW),
                "precipitation_loads": host.precipitation_loads,
                "graphics_api": host.graphics_api(), "software": host.is_software_adapter(),
                "health": _health(host)}
    finally:
        host.close()
        pump(100)


def scenario_stills(ctx: Context) -> dict[str, Any]:
    from open_garden_planner.core.scene3d.weather import living_look

    records, seasons, latitude = _plan()
    host = _host(ctx)
    try:
        _sync, sun = _scene(host, records, seasons, latitude)
        files = {}
        for weather in ("clear", "overcast", "rain", "snow"):
            host.set_look(living_look(sun, "medium", weather))
            files[weather] = ctx.save(f"still_{weather}", host.grab(weather))
        return {"files": files, "health": _health(host)}
    finally:
        host.close()
        pump(100)


#: The two glows of ``reload``, scene cm (east, north, up): over open lawn in the hero
#: camera's view (its target itself lies behind the poplar).
RELOAD_AT: tuple[tuple[float, float, float], ...] = ((1300.0, 500.0, 140.0), (2000.0, 800.0, 140.0))


def _warm(image: Any) -> dict[str, Any]:
    """How many pixels of a frame are a bulb's warm glow, and where their middle is (the
    self-test's own measure: red and green bright, blue well below green)."""
    import numpy as np
    from PyQt6.QtGui import QImage

    frame = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = frame.width(), frame.height()
    data = np.frombuffer(frame.constBits().asstring(frame.sizeInBytes()), dtype=np.uint8)
    rgb = data.reshape(height, frame.bytesPerLine() // 4, 4)[:, :width, :3].astype(np.int32)
    warm = (rgb[..., 0] >= 170) & (rgb[..., 1] >= 110) & (rgb[..., 2] + 30 < rgb[..., 1])
    ys, xs = np.nonzero(warm)
    return {"pixels": int(warm.sum()),
            "middle": [round(float(xs.mean()), 1), round(float(ys.mean()), 1)] if len(xs) else None}


def scenario_reload(ctx: Context) -> dict[str, Any]:
    """The ambient buffer reloaded into the same live host: A; while shown, at B (the
    product's common path: a date step, a lamp moved); nothing; B again after nothing."""
    from open_garden_planner.core.scene3d import SunState
    from open_garden_planner.core.scene3d.particles import Emitter, ambient_buffers
    from open_garden_planner.core.scene3d.weather import living_look

    records, seasons, latitude = _plan()
    host = _host(ctx)
    try:
        _scene(host, records, seasons, latitude)
        night = SunState(-14.0, 320.0)
        host.set_look(living_look(night, "medium", "clear"))
        host.set_lamps([])                        # the glows alone: no pool of light
        frames: dict[str, Any] = {}
        loads = [("a", RELOAD_AT[0]), ("a2", RELOAD_AT[1]), ("none", None), ("b", RELOAD_AT[1])]
        for name, at in loads:
            emitters = () if at is None else (Emitter("bulb", name, at[0], at[1], at[2], at[2], 60.0, 1),)
            host.set_ambient(ambient_buffers(emitters))
            image = host.grab(f"reload_{name}")
            frames[name] = {**_warm(image), "file": ctx.save(f"reload_{name}", image)}
        return {"frames": frames, "ambient_loads": host.ambient_loads, "health": _health(host)}
    finally:
        host.close()
        pump(100)


SCENARIOS: dict[str, Callable[[Context], dict[str, Any]]] = {
    "idle": scenario_idle,
    "frame_cost": scenario_frame_cost,
    "stills": scenario_stills,
    "reload": scenario_reload,
}


def _isolate(out: Path) -> None:
    """Run by hand — not through the tests' ``isolated_env`` — this file still must not
    touch the developer's data or settings (``quick3d_render_driver.py`` says why)."""
    from tests.integration.quick3d_render_support import ISOLATED_MARK, private_dirs

    if os.environ.get(ISOLATED_MARK) != "1":
        os.environ.update(private_dirs(out / "private"))
    import open_garden_planner.app.settings as app_settings

    app_settings.ORGANIZATION_NAME = "cofade_test"
    app_settings.APPLICATION_NAME = f"Open Garden Planner Living Tier {os.getpid()}"


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
        with offscreen.watchdog(args.watchdog_s, log, what=f"the living driver ({args.scenario})",
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
