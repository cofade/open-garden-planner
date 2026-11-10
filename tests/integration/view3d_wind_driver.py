"""The engine-side half of the WIND's render tier (#800) — not a test module.

``test_view3d_wind_render.py`` starts this file with a real window system: the family
garden on a SHOWN host with its forged plants and a sky, pictures through
``Quick3DHost.capture`` — the tour's path, whose wind clock is computed per frame
(``core.camera_path``: ``WIND_START_S + index / fps``), so a frame index is a picture.

    python tests/integration/view3d_wind_driver.py --out <dir> --scenario <name> [--arg k=v …]

The driver only DOES engine things and writes raw answers to ``result.json`` (and frames
as PNGs); the tests judge. It installs no Qt message handler (it shows windows).

Scenarios:

``sequence``  for a tree (the 9.5 m birch, about 11 m out), a shrub (the 1.7 m lilac,
              5 m) and a herb (a 60 cm basil, 3 m): the subject's own pixels (the frame
              against the subject drawn as an empty screen door), the frame at rest
              (clock 0), and ``seconds`` of frames at each of ``fps`` from the tour's
              wind start. Per frame the translation of the plant's upper part against
              the first frame (Lucas-Kanade on its own pixels) and the mean change of
              its pixels from the frame before; the same frame index twice. Argument
              ``qml``: a scene directory to load instead of the package's (the tests'
              copy whose sway is multiplied by 0).
``shadow``    the birch from above at a 35° sun in a wind ``gain`` x the look's: the
              ground beside the crown at two clock values — its shadow must move with it.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import platform
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":  # run as a script: make this checkout's code importable
    for entry in (str(REPO / "src"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    from scripts.quiet_windows import keep_windows_behind

    keep_windows_behind()  # run by hand: no start-up hook did this

PLAN = REPO / "src" / "open_garden_planner" / "resources" / "examples" / "family-garden.ogp"
DAY = date(2026, 6, 21)
#: The tour's wind start (``core.camera_path.WIND_START_S``): the sway is in full swing.
WIND_START_S = 10.0
#: The camera's sun: behind the camera, high enough to light the crowns from the front.
SUN = (40.0, 220.0)
#: subject: (item id prefix, distance cm, eye height cm, camera azimuth from the plant,
#: aim at this share of the plant's height, vertical field of view)
SUBJECTS: dict[str, tuple[str, float, float, float, float, float]] = {
    "tree": ("2d451f98", 1100.0, 250.0, 200.0, 0.62, 46.0),     # birch, 9.5 m
    "shrub": ("b79009a0", 500.0, 170.0, 110.0, 0.55, 40.0),     # lilac, 1.74 m
    "herb": ("77305f4c", 300.0, 160.0, 200.0, 0.5, 40.0),       # basil, 60 cm (raised bed)
}
#: The upper share of a plant's pixels the sway is read on (the top moves most).
TOP_SHARE = 0.45


class Context:
    def __init__(self, out: Path, log: Any, arguments: dict[str, str]) -> None:
        self.out, self.log, self.arguments = out, log, arguments

    def save(self, name: str, pixels: np.ndarray) -> str:
        from PyQt6.QtGui import QImage

        height, width = pixels.shape[:2]
        image = QImage(np.ascontiguousarray(pixels).data, width, height, 3 * width,
                       QImage.Format.Format_RGB888).copy()
        path = self.out / f"{name}.png"
        if not image.save(str(path)):
            raise RuntimeError(f"could not write {path}")
        return path.name


class Garden:
    """The family garden on a shown host, its plants forged, its sky built."""

    def __init__(self, ctx: Context, size: tuple[int, int], preset: str,
                 sun: tuple[float, float] = SUN, wind_gain: float = 1.0) -> None:
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

        self.size = size
        scene = CanvasScene()
        manager = ProjectManager()
        manager.load(scene, PLAN)
        rect = scene.sceneRect()
        latitude = float((manager.location or {}).get("latitude", 52.52))
        self.records = snapshot_records(scene, DAY)
        seasons = evaluate_phenology_for_records(tuple(self.records.values()), DAY,
                                                 latitude_deg=latitude)
        qml = ctx.arguments.get("qml")
        self.host = Quick3DHost((640, 360), log=ctx.log, **({"qml_dir": Path(qml)} if qml else {}))
        self.host.show()
        if not self.host.wait_ready(20.0):
            state = self.host.state.value
            self.host.close()
            raise RuntimeError(f"the shown host did not become live (state {state})")
        sink = Quick3DSink(self.host)
        sync = SceneSync(sink, production_registry())
        sun_state = SunState(*sun)
        sync.apply(self.records, sun=sun_state, ground=GroundSpec(float(rect.width()), float(rect.height())))
        self.host.set_plant_seasons(seasons)
        worker = ForgeWorker(sink, cache=ForgeCache(), season_sink=self.host.set_plant_seasons)
        worker.submit_snapshot(self.records.values(), plan_date=DAY, latitude_deg=latitude)
        worker.drain()
        worker.shutdown()
        look = look_for(sun_state, preset)
        if wind_gain != 1.0:
            look = replace(look, wind_strength=look.wind_strength * wind_gain)
        self.look = look
        self.host.set_look(look)
        if not self.host.is_software_adapter():
            self.host.set_sky(look.sky)

    def record(self, prefix: str) -> Any:
        return next(record for item_id, record in self.records.items() if item_id.startswith(prefix))

    def camera(self, subject: str) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
        prefix, distance, eye_height, azimuth, aim, fov = SUBJECTS[subject]
        record = self.record(prefix)
        t, height = record.transform, float(record.height_cm)
        a = math.radians(azimuth)
        eye = (t.east_cm + distance * math.sin(a), t.north_cm + distance * math.cos(a),
               t.base_cm + eye_height)
        return eye, (t.east_cm, t.north_cm, t.base_cm + aim * height), fov

    def capture(self, camera: Any, wind_s: float) -> np.ndarray:
        from open_garden_planner.ui.view3d.quick3d.offscreen import image_rgba
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        if self.host._camera_scene is None:  # noqa: SLF001 - a capture needs a camera to put back
            self.host.set_camera(*camera)
        image = self.host.capture(self.size, PerspectiveShot(*camera), wind_time_s=wind_s)
        return np.asarray(image_rgba(image)[..., :3])

    def mask(self, prefix: str, camera: Any) -> np.ndarray:
        """The subject's own pixels: the frame against the subject as an empty screen door
        (which keeps its shadow, so the mask holds the plant and nothing it casts)."""
        full = self.capture(camera, 0.0)
        self.host.set_faded_items({self.record(prefix).item_id}, 0.0)
        faded = self.capture(camera, 0.0)
        self.host.set_faded_items(set(), 1.0)
        return np.abs(full.astype(np.int16) - faded.astype(np.int16)).max(axis=2) > 10

    def close(self) -> None:
        self.host.close()


def luma(rgb: np.ndarray) -> np.ndarray:
    p = rgb.astype(np.float32)
    return np.asarray(0.299 * p[..., 0] + 0.587 * p[..., 1] + 0.114 * p[..., 2], dtype=np.float64)


def _box(a: np.ndarray) -> np.ndarray:
    pad = np.pad(a, 1, mode="edge")
    return sum(pad[dy:dy + a.shape[0], dx:dx + a.shape[1]] for dy in range(3) for dx in range(3)) / 9.0


def _bilinear(img: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    h, w = img.shape
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return ((1 - fx) * (1 - fy) * img[y0, x0] + fx * (1 - fy) * img[y0, x0 + 1]
            + (1 - fx) * fy * img[y0 + 1, x0] + fx * fy * img[y0 + 1, x0 + 1])


def translation(ref: np.ndarray, cur: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    """The (dx, dy) in px that maps ``ref`` onto ``cur`` over ``mask``: iterative
    Lucas-Kanade on lightly blurred luma — the dominant motion of those pixels."""
    a, b = _box(ref), _box(cur)
    gy, gx = np.gradient(a)
    ys, xs = np.nonzero(mask)
    gxm, gym = gx[ys, xs], gy[ys, xs]
    m = np.array([[np.sum(gxm * gxm), np.sum(gxm * gym)], [np.sum(gxm * gym), np.sum(gym * gym)]])
    inverse = np.linalg.inv(m)
    dx = dy = 0.0
    for _ in range(12):
        error = _bilinear(b, xs + dx, ys + dy) - a[ys, xs]
        step = inverse @ np.array([np.sum(gxm * error), np.sum(gym * error)])
        dx, dy = dx - float(step[0]), dy - float(step[1])
        if abs(step[0]) + abs(step[1]) < 1e-4:
            break
    return dx, dy


def scenario_sequence(ctx: Context) -> dict[str, Any]:
    width, height = (int(v) for v in ctx.arguments.get("size", "640x360").split("x"))
    seconds = float(ctx.arguments.get("seconds", "2"))
    rates = [int(v) for v in ctx.arguments.get("fps", "30,60").split(",")]
    subjects = ctx.arguments.get("subjects", "tree,herb").split(",")
    garden = Garden(ctx, (width, height), ctx.arguments.get("preset", "medium"))
    out: dict[str, Any] = {"size": [width, height], "seconds": seconds, "rates": rates,
                           "api": garden.host.graphics_api(), "software": garden.host.is_software_adapter()}
    try:
        for subject in subjects:
            camera = garden.camera(subject)
            prefix = SUBJECTS[subject][0]
            record = garden.record(prefix)
            mask = garden.mask(prefix, camera)
            ys = np.nonzero(mask)[0]
            top = mask.copy()
            top[int(ys.min() + TOP_SHARE * (ys.max() - ys.min())):, :] = False
            rest = garden.capture(camera, 0.0)
            row: dict[str, Any] = {
                "camera": camera, "height_cm": float(record.height_cm),
                "distance_cm": math.dist(camera[0], camera[1]), "fov_deg": camera[2],
                "mask_px": int(mask.sum()), "top_px": int(top.sum()),
                "rest": ctx.save(f"{subject}_rest", rest), "rest_digest": int(rest.astype(np.int64).sum()),
            }
            first = garden.capture(camera, WIND_START_S + 17 / 30.0)
            garden.capture(camera, WIND_START_S + 1.0)
            again = garden.capture(camera, WIND_START_S + 17 / 30.0)
            row["repeat_max_diff"] = int(np.abs(first.astype(np.int16) - again.astype(np.int16)).max())
            for fps in rates:
                # one frame at a time against the first and the one before (a sequence of
                # 1080p frames held at once would cost hundreds of MB on a shared machine)
                first_luma = previous = luma(garden.capture(camera, WIND_START_S))
                moves, change = [(0.0, 0.0)], []
                for index in range(1, int(round(seconds * fps)) + 1):
                    frame = luma(garden.capture(camera, WIND_START_S + index / fps))
                    moves.append(translation(first_luma, frame, top))
                    change.append(float(np.abs(frame - previous)[mask].mean()))
                    previous = frame
                row[f"fps{fps}"] = {"dx": [round(m[0], 4) for m in moves], "dy": [round(m[1], 4) for m in moves],
                                    "change": [round(c, 4) for c in change]}
            out[subject] = row
            ctx.log("sequence", subject=subject, mask=row["mask_px"], repeat=row["repeat_max_diff"])
    finally:
        garden.close()
    return out


def scenario_shadow(ctx: Context) -> dict[str, Any]:
    """The birch's shadow seen from above at a 35° sun in a wind ``gain`` x the look's:
    every plant's own pixels masked out (each drawn as an empty screen door, which keeps
    its shadow), the ground changes between two clock values only if the shadow pass sways
    the crowns as the colour pass does. Argument ``qml``: the tests' control copy whose
    shadow pass skips the sway."""
    from open_garden_planner.core.plant_art import PLANT_KINDS

    gain = float(ctx.arguments.get("gain", "20"))
    garden = Garden(ctx, (640, 360), ctx.arguments.get("preset", "medium"), sun=(35.0, 180.0),
                    wind_gain=gain)
    try:
        t = garden.record(SUBJECTS["tree"][0]).transform
        # the shadow of the birch's crown (3 - 9.5 m) at a 35° sun from the south falls
        # 4 - 14 m north of its trunk: the camera looks down on it from the south
        camera = ((t.east_cm, t.north_cm - 300.0, 1500.0), (t.east_cm, t.north_cm + 800.0, 0.0), 50.0)
        full = garden.capture(camera, 0.0)
        plants = {item_id for item_id, record in garden.records.items() if record.kind in PLANT_KINDS}
        garden.host.set_faded_items(plants, 0.0)
        empty = garden.capture(camera, 0.0)
        garden.host.set_faded_items(set(), 1.0)
        mask = np.abs(full.astype(np.int16) - empty.astype(np.int16)).max(axis=2) > 6
        grown = mask.copy()       # two pixels round every plant: its edge moves too
        for axis in (0, 1):
            for shift in (-2, -1, 1, 2):
                grown |= np.roll(mask, shift, axis=axis)
        frames = {wind: garden.capture(camera, wind) for wind in (11.0, 12.3)}
        out: dict[str, Any] = {"gain": gain, "plant_px": int(grown.sum()),
                               "rest": ctx.save("shadow_rest", full)}
        for wind, frame in frames.items():
            diff = np.abs(frame.astype(np.int16) - full.astype(np.int16)).max(axis=2)
            out[f"t{wind}"] = {"ground_changed_px": int(((diff > 12) & ~grown).sum()),
                               "plants_changed_px": int(((diff > 12) & grown).sum()),
                               "file": ctx.save(f"shadow_{wind}", frame)}
        return out
    finally:
        garden.close()


SCENARIOS: dict[str, Callable[[Context], dict[str, Any]]] = {
    "sequence": scenario_sequence,
    "shadow": scenario_shadow,
}


def _isolate(out: Path) -> None:
    """Run by hand — not through the tests' ``isolated_env`` — this file still must not
    touch the developer's data or settings (``quick3d_render_driver.py`` says why)."""
    from tests.integration.quick3d_render_support import ISOLATED_MARK, private_dirs

    if os.environ.get(ISOLATED_MARK) != "1":
        os.environ.update(private_dirs(out / "private"))
    import open_garden_planner.app.settings as app_settings

    app_settings.ORGANIZATION_NAME = "cofade_test"
    app_settings.APPLICATION_NAME = f"Open Garden Planner Wind Tier {os.getpid()}"


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
        with offscreen.watchdog(args.watchdog_s, log, what=f"the wind driver ({args.scenario})",
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
