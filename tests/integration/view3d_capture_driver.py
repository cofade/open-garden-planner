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
``picture``   The family garden at a low sun: a 4K picture against 1080p (the band, #733).
``grades``    Every grade against the view; the identity table against the view.
``tour``      The workspace's own recording: a drone orbit into an MP4, read back with Qt.
``detail``    A recording close to the plants: its frames have the flight's plant detail.
``timelapse`` A day and a stretch of the year: the clock is put back, frames follow it.
``daylapse``  A held-camera day lapse through dawn and dusk (#799): per frame the sky band.
``agent``     The MCP tool's provider on the real workspace: its refusals and its picture.
"""

from __future__ import annotations

import argparse
import json
import math
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
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":  # run as a script: make this checkout's code importable
    for entry in (str(REPO / "src"), str(REPO / "scripts"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    import script_isolation

    script_isolation.isolate_profile()  # with scripts/quiet_windows.keep_windows_behind

PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
#: The packaged example the L6 promotion shoots: larger, denser, and the shot the 4K look
#: was reported on (#733).
FAMILY_GARDEN = REPO / "src" / "open_garden_planner" / "resources" / "examples" / "family-garden.ogp"
DAY = date(2026, 6, 21)
VIEW = (640, 360)
HERO = ((2520.0, -448.0, 490.0), (1008.0, 960.0, 160.0), 46.0)
OTHER = ((1000.0, -900.0, 700.0), (1000.0, 800.0, 100.0), 40.0)
#: The board's sunset anchor on the bench plan (5.9°); a low sun shows the horizon band.
PHOTO_SUN = (5.9, 250.0)
#: The picture band #733 measures: the far meadow where the ground meets the sky, as a
#: share of the picture's height (the sky above it is the control). The garden below it
#: differs by up to 3 levels for a different reason (texture minification) and is not the
#: reported horizon band.
PICTURE_BAND = (0.36, 0.44)
PICTURE_SKY = 0.18
#: The blur's measuring tile (#743): 60 px of the picture it is measured in. A tile whose sharp
#: picture has less gradient than this (levels per pixel) is flat (sky, a lawn far off) and says
#: nothing about blur.
BLUR_TILE = 60
BLUR_FLAT = 1.0
#: The picture the slider is pinned in, and the save the preview is compared with (a whole
#: multiple of the view's own size, so that the save shrinks to the preview by area means).
SLIDER_PICTURE = (1280, 720)
SAVE_HEIGHT = 2160
#: Where the slider's focus is clicked in the view (logical px): the crown of the tree left of
#: the house, about 21 m out, a body that fills its tile. A click on the poplar's trunk in the
#: middle kept 0.67 of its tile at blur 1, rightly: the tile is mostly lawn metres behind it.
FOCUS_CLICK = (180.0, 150.0)


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


def luma_of(pixels: Any) -> Any:
    return (0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1]
            + 0.0722 * pixels[..., 2]).astype(np.float64)


def shrink(luma: Any, factor: int) -> Any:
    """Area means of ``factor`` x ``factor`` blocks: a big picture seen at a small size."""
    height, width = luma.shape[0] // factor, luma.shape[1] // factor
    return luma[:height * factor, :width * factor].reshape(height, factor, width, factor).mean(axis=(1, 3))


def gradient_tiles(luma: Any, tile: int) -> Any:
    """The mean absolute luma step to the right and downwards, per ``tile`` x ``tile`` block."""
    step = np.zeros_like(luma)
    step[:, :-1] += np.abs(np.diff(luma, axis=1))
    step[:-1, :] += np.abs(np.diff(luma, axis=0))
    rows, columns = luma.shape[0] // tile, luma.shape[1] // tile
    return step[:rows * tile, :columns * tile].reshape(rows, tile, columns, tile).mean(axis=(1, 3))


def gradient_ratios(blurred: Any, sharp: Any, tile: int = BLUR_TILE) -> Any:
    """Per tile: how much of the sharp picture's detail the blurred one keeps (1 = all of it).
    NaN where the sharp tile is flat."""
    kept, there = gradient_tiles(blurred, tile), gradient_tiles(sharp, tile)
    return np.where(there >= BLUR_FLAT, kept / np.maximum(there, 1e-9), np.nan)


def blur_answers(host: Any, size: tuple[int, int], out: Path) -> dict[str, Any]:
    """#743: what the blur does to a picture, measured in tiles of the picture's detail.

    - ``parity``: the preview's size and a save of ``SAVE_HEIGHT`` of one camera and one blur,
      the save shrunk to the preview's size by area means: the gradient ratio per tile of each
      against its own sharp picture. Qt's half-resolution blur gave 0.66 in the pane and 0.91 in a
      4K save at blur 0.8 (3D review of #729).
    - ``slider``: blur 0.05 and 1.0 with one focus, in ``SLIDER_PICTURE``: the share of tiles
      that lost a fifth of their detail, and the ratio of the tile under the focus.
    - ``zero``: blur 0 with a focus is the view, not a level apart.
    """
    from open_garden_planner.core.scene3d.photo import NO_PHOTO, PhotoSettings

    host.grab("before the click")   # the engine picks in the frame it drew last: the view's
    hit = host.pick(*FOCUS_CLICK)
    focus = hit.point if hit is not None else HERO[1]
    answers: dict[str, Any] = {"focus": [round(value, 1) for value in focus],
                               "focus_item": hit.item_id if hit is not None else None}
    host.set_photo(PhotoSettings(blur=0.0, focus_scene=focus))
    answers["zero"] = difference(rgb(host.capture(size, photo=NO_PHOTO, label="sharp")),
                                 rgb(host.capture(size, label="blur 0")))
    factor = max(1, round(SAVE_HEIGHT / size[1]))
    save = (size[0] * factor, size[1] * factor)
    sharp_small = luma_of(rgb(host.capture(size, photo=NO_PHOTO, label="sharp")))
    sharp_save = shrink(luma_of(rgb(host.capture(save, photo=NO_PHOTO, label="sharp save"))), factor)
    host.set_photo(PhotoSettings(blur=0.8, focus_scene=focus))
    preview = host.capture(size, label="preview")
    saved = host.capture(save, label="save")
    preview.save(str(out / "blur_preview.png"))
    saved.scaled(size[0], size[1]).save(str(out / "blur_save_shrunk.png"))
    small = gradient_ratios(luma_of(rgb(preview)), sharp_small)
    large = gradient_ratios(shrink(luma_of(rgb(saved)), factor), sharp_save)
    both = ~(np.isnan(small) | np.isnan(large))
    rows, columns = small.shape
    middle = np.zeros_like(both)
    middle[rows // 3:rows - rows // 3, columns // 3:columns - columns // 3] = True
    answers["parity"] = {
        "save": list(save), "tiles": int(both.sum()),
        "preview_mean": round(float(small[both].mean()), 3),
        "save_mean": round(float(large[both].mean()), 3),
        "mean_abs_difference": round(float(np.abs(small - large)[both].mean()), 3),
        "worst_tile": round(float(np.abs(small - large)[both].max()), 3),
        "preview_middle": round(float(small[both & middle].mean()), 3),
        "save_middle": round(float(large[both & middle].mean()), 3)}
    # the slider: one focus, a faint blur and the strongest
    sharp = luma_of(rgb(host.capture(SLIDER_PICTURE, photo=NO_PHOTO, label="slider sharp")))
    x, y = host.project(*focus)
    column = int(x * SLIDER_PICTURE[0] / VIEW[0]) // BLUR_TILE
    row = int(y * SLIDER_PICTURE[1] / VIEW[1]) // BLUR_TILE
    slider: dict[str, Any] = {"focus_tile": [row, column]}
    for blur in (0.05, 1.0):
        host.set_photo(PhotoSettings(blur=blur, focus_scene=focus))
        image = host.capture(SLIDER_PICTURE, label=f"slider {blur}")
        image.save(str(out / f"blur_{blur}.png"))
        ratios = gradient_ratios(luma_of(rgb(image)), sharp)
        valid = ~np.isnan(ratios)
        slider[str(blur)] = {"soft_share": round(float((ratios[valid] < 0.8).mean()), 3),
                             "focus_ratio": round(float(ratios[row, column]), 3),
                             "tiles": int(valid.sum())}
    answers["slider"] = slider
    host.set_photo(NO_PHOTO)
    return answers


def shown_host(out: Path, preset: str = "medium", *,
               plan: Path = PLAN, sun: tuple[float, float] = (38.0, 250.0)) -> tuple[Any, Any]:
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
    manager.load(scene, plan)
    rect = scene.sceneRect()
    width, depth = float(rect.width()), float(rect.height())
    cx, cy = width / 2.0, depth / 2.0
    diag = math.hypot(width, depth)
    records = snapshot_records(scene, DAY)
    seasons = evaluate_phenology_for_records(tuple(records.values()), DAY, latitude_deg=52.52)
    host = Quick3DHost(VIEW)
    host.show()
    if not host.wait_ready(20.0):
        raise RuntimeError(f"the shown host did not become live ({host.state.value})")
    sink = Quick3DSink(host)
    sync = SceneSync(sink, production_registry())
    state_of_the_sky = SunState(*sun)
    sync.apply(records, sun=state_of_the_sky, ground=GroundSpec(width, depth))
    host.set_plant_seasons(seasons)
    worker = ForgeWorker(sink, cache=ForgeCache(), season_sink=host.set_plant_seasons)
    worker.submit_snapshot(records.values(), plan_date=DAY, latitude_deg=52.52)
    worker.drain()
    worker.shutdown()
    look = look_for(state_of_the_sky, preset)
    host.set_look(look)
    if not host.is_software_adapter():
        host.set_sky(look.sky)
    # the board's hero framing of this plan (the bench plan's is HERO, exactly)
    if plan == PLAN:
        host.set_camera(*HERO)
    else:
        host.set_camera((cx + 0.55 * width, cy - 0.78 * depth, 0.17 * diag),
                        (cx - 0.08 * width, cy + 0.1 * depth, 160.0), 46.0)
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
        # #734: a still picture's shadow map fitted to the casters differs from the view only
        # where a shadow's edge is, and only in its own frame - the view after it is the view
        fitted_image = host.capture(size, label="fitted", fitted_shadows=True)
        fitted_image.save(str(out / "fitted.png"))
        fitted = rgb(fitted_image)
        fitted_delta = np.abs(fitted - view).max(axis=-1)
        result["fitted"] = {**difference(view, fitted),
                            "changed_share": round(float((fitted_delta > 8).mean()), 5),
                            "view_after": difference(view, rgb(host.grab("after fitted"))),
                            "flag_after": host.scene_property("fittedShadows")}
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
        result["blur"] = blur_answers(host, size, out)
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


def scenario_picture(out: Path) -> dict[str, Any]:
    """A 4K picture against 1080p of the shot the 4K look was reported on (#733): a low sun
    over the family garden. The ENGINE answers whether a bigger picture keeps 1080p's look."""
    from open_garden_planner.core.scene3d.look import ao_distance_scale

    host, _sync = shown_host(out, sun=PHOTO_SUN, plan=FAMILY_GARDEN)
    try:
        host.wait_ready(5.0)
        profiles: dict[str, Any] = {}
        sizes: dict[str, list[int]] = {}
        for label, size in (("1080", (1920, 1080)), ("2160", (3840, 2160))):
            image = host.capture(size, label=label)
            image.save(str(out / f"picture_{label}.png"))
            sizes[label] = [image.width(), image.height()]
            pixels = rgb(image)
            luma = 0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1] + 0.0722 * pixels[..., 2]
            profiles[label] = luma.mean(axis=1)
        full, small = profiles["2160"], profiles["1080"]
        index = np.linspace(0, len(full) - 1, len(small))
        delta = np.interp(index, np.arange(len(full)), full) - small
        low = round(len(small) * PICTURE_BAND[0])
        high = round(len(small) * PICTURE_BAND[1])
        buckets = [round(float(delta[row:row + 40].mean()), 3)
                   for row in range(low, max(low + 1, high - 39), 40)]
        return {
            "band": [low, high],
            "band_delta": round(float(delta[low:high].mean()), 3),
            "worst_bucket": max(buckets, key=abs),
            "sky_delta": round(float(delta[:round(len(small) * PICTURE_SKY)].mean()), 3),
            "ao_scale_at_2160": round(ao_distance_scale(2160.0), 3),
            "ao_scale_after_4k": host.scene_property("captureAoDistanceScale"),
            "sizes": sizes,
        }
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


def scenario_ultra_blur(out: Path) -> dict[str, Any]:
    """The Ultra preset draws screen-space reflections, a high-quality glow and ambient occlusion.
    With depth of field in the same effect chain Qt's render thread crashed in d3d11.dll
    (a read at address 0x16d in OMSetRenderTargets, #744) at the first focus click of an owner's manual test
    of #390. The picture is blurred in the shown window and in a capture, over and over, and
    the blur is really there."""
    from PyQt6.QtCore import QObject

    from open_garden_planner.core.scene3d.photo import NO_PHOTO, PhotoSettings

    host, _sync = shown_host(out, "ultra")
    try:
        host.wait_ready(5.0)
        ratio = host.device_pixel_ratio()
        size = (round(VIEW[0] * ratio), round(VIEW[1] * ratio))
        sharp = rgb(host.capture(size, label="sharp"))
        focus = HERO[1]   # what the hero camera looks at
        # the environment's own switch: Ultra's reflections, and whether they stand down (#744)
        environment = next(child for child in host._root.findChildren(QObject)
                           if "ExtendedSceneEnvironment" in child.metaObject().className())
        reflections = bool(environment.property("ssrEnabled"))
        rows: dict[str, Any] = {}
        for blur in (0.3, 1.0, 0.0, 1.0):
            host.set_photo(PhotoSettings(blur=blur, focus_scene=focus))
            pump(400)   # the shown window's own render thread draws with the effect chain
            host._view.grabWindow()   # the shown window's frame, with the chain
            made = rgb(host.capture(size, label=f"blur {blur}"))
            # an agent's picture takes NO_PHOTO: the chain flips to blur off and back, mid-session
            agent = rgb(host.capture(size, photo=NO_PHOTO, label=f"agent {blur}"))
            rows[str(blur)] = {"capture_vs_sharp": difference(sharp, made),
                               "agent_vs_sharp": difference(sharp, agent),
                               "blur_drawn": bool(host._root.property("depthOfFieldActive")),
                               "reflections_drawn": bool(environment.property("ssrEnabled"))}
        host.set_photo(PhotoSettings())
        pump(300)
        return {"rows": rows, "reflections_without_blur": reflections,
                "after": difference(sharp, rgb(host.capture(size, label="after")))}
    finally:
        host.close()
        pump(100)


BENCH = Path(__file__).with_name("photoblur_bench.qml")


def _bench_picture(size: tuple[int, int], blur_on: bool, out: Path) -> Any:
    """One picture of ``photoblur_bench.qml`` at ``size``, read as luma (a shown window, an
    explicit-size View3D, ``grabToImage`` driven by ``grabWindow``: the capture path's way)."""
    from PyQt6.QtCore import QCoreApplication, QSize
    from PyQt6.QtQuick import QQuickItem, QQuickView

    view = QQuickView()
    view.setResizeMode(QQuickView.ResizeMode.SizeViewToRootObject)
    view.setInitialProperties({"pictureWidth": size[0], "pictureHeight": size[1], "blurOn": blur_on})
    view.setSource(QUrl.fromLocalFile(str(BENCH)))
    if view.errors():
        raise RuntimeError("; ".join(error.toString() for error in view.errors()))
    view.show()
    try:
        if wait_until(lambda: view.isExposed() and view.isSceneGraphInitialized(), 20.0) is None:
            raise RuntimeError("the bench window never got a frame")
        pump(50)
        item = view.rootObject().findChild(QQuickItem, "bench")
        result = item.grabToImage(QSize(*size))
        view.grabWindow()
        QCoreApplication.sendPostedEvents(result, 0)
        image = result.image()
        image.save(str(out / f"bench_{size[1]}_{'blur' if blur_on else 'sharp'}.png"))
        return luma_of(rgb(image))
    finally:
        view.close()
        view.deleteLater()
        pump(50)


def _bench_answers(sharp: Any, blurred: Any) -> dict[str, Any]:
    """The bench's measures, positions given in a 2160 px picture and scaled to this one."""
    scale = sharp.shape[0] / 2160.0

    def at(value: float) -> int:
        return round(value * scale)

    rows = slice(at(950), at(1250))
    # in-focus white bar on the far wall: the wall's first pixels beside it, against the wall
    profile = sharp[rows].mean(axis=0)
    right = at(1400) + int(np.argmax(profile[at(1400):] < 100.0))
    left = at(1300) + int(np.argmax(profile[at(1300):] > 200.0)) - 1
    wall = float(blurred[rows, right + at(90):right + at(90) + 10].mean())
    fringe = max(float((blurred[rows, right:right + 3].mean(axis=0) - wall).max()),
                 float((blurred[rows, left - 2:left + 1].mean(axis=0) - wall).max()))
    # the thin line on the far wall: its width and its humps
    line = blurred[at(900):at(1000), at(2482):at(2782)].mean(axis=0)
    line = np.convolve(line, np.ones(3) / 3.0, mode="same")[2:-2]
    base = float(np.median(np.r_[line[:5], line[-5:]]))
    top = float(line.max()) - base
    above = np.where(line - base >= 0.5 * top)[0]
    humps = sum(1 for index in range(1, len(line) - 1)
                if line[index] > line[index - 1] and line[index] >= line[index + 1]
                and line[index] - base > 0.3 * top)
    # the near bar's right edge over the sharp panel: 10-90 % rise; and the bar's own rim
    edge = blurred[at(1485):at(1565), at(2180):at(2420)].mean(axis=0)
    low, high = float(edge.min()), float(edge.max())
    rise = int(np.argmax(edge > low + 0.9 * (high - low))) - int(np.argmax(edge > low + 0.1 * (high - low)))
    inner = blurred[at(1485):at(1565), at(2173):at(2261)].mean(axis=0)
    return {"fringe": round(fringe, 2), "line_width_share": round(float(above[-1] - above[0] + 1) / sharp.shape[0], 5),
            "line_humps": humps, "near_edge_share": round(rise / sharp.shape[0], 5),
            "near_rim": round(float(inner.max() - inner[len(inner) // 2]), 2)}


def scenario_blur_bench(out: Path) -> dict[str, Any]:
    """#743's three defects of Qt's blur on a bench with known answers, at a preview's size and
    at 4K: an in-focus colour reaching the blurred wall (fringe), a thin line drawn as copies,
    and a blurred near bar with a hard edge (or a light rim, PF-E3D-27). And the same measures
    in both sizes, as shares of the picture's height."""
    answers: dict[str, Any] = {}
    for size in ((640, 360), (3840, 2160)):
        sharp = _bench_picture(size, False, out)
        blurred = _bench_picture(size, True, out)
        answers[str(size[1])] = {"blurred": _bench_answers(sharp, blurred),
                                 "sharp": _bench_answers(sharp, sharp)}
    return answers


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


def main_window_on_plan(clock_zone: Any = None, plan: Path = PLAN) -> tuple[Any, Any]:
    """The app's real window on ``plan``, in 3D (the settings store is this process's).

    ``clock_zone`` builds the one SimClock through its public ``tz`` constructor instead of
    the system zone - a test seam, not a private attribute write."""
    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.ui.view3d.workspace import WorkspaceMode

    if clock_zone is not None:
        import open_garden_planner.core.sim_clock as sim_clock_module
        from open_garden_planner.core.sim_clock import SimClock

        # application.py imports SimClock INSIDE __init__, so patch the module it reads
        sim_clock_module.SimClock = lambda: SimClock(tz=clock_zone)  # type: ignore[assignment]

    # nobody clicks here: as in tests/conftest.py, no modal Welcome dialog over the plan, and no
    # Unsaved Changes on close (a dirty plan held a probe for ever, in front of the owner)
    GardenPlannerApp._show_welcome_dialog = lambda _self: None  # type: ignore[method-assign]
    GardenPlannerApp._confirm_discard_changes = lambda _self: True  # type: ignore[method-assign]
    window = GardenPlannerApp()
    if clock_zone is not None:
        assert window._sim_clock.tz is clock_zone, "the test clock zone did not reach the app"
    window.resize(1100, 700)
    window.show()
    window._project_manager.load(window.canvas_scene, plan)
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
        from open_garden_planner.core.mp4_stream import read_stream

        stream = read_stream(path)   # what the file states (#807)
        result["stream"] = {
            "codec": stream.codec, "profile": stream.sps.profile if stream.sps else None,
            "level": stream.sps.level if stream.sps else None, "samples": stream.samples,
            "deltas": sorted({delta for _count, delta in stream.durations}),
            "timescale": stream.timescale, "mbit_s": round(stream.bit_rate / 1e6, 2),
            "tagged": None if stream.tagged is None else [
                stream.tagged.primaries, stream.tagged.transfer, stream.tagged.matrix,
                stream.tagged.full_range]}
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


def scenario_detail(out: Path) -> dict[str, Any]:
    """A recording's frames show the plants the view would show from there, not the view's."""
    from open_garden_planner.core.camera_path import CameraKey, HeldCamera, TourSpec, path_eyes
    from open_garden_planner.core.plant_forge.lod import select_lod
    from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot
    from open_garden_planner.ui.view3d.video_writer import PngSequenceWriter

    window, workspace = main_window_on_plan()
    try:
        result: dict[str, Any] = {"settled_s": settled(workspace)}
        capture, host = workspace.capture, workspace.host
        worker, records = workspace._forge_worker, workspace._controller.sync.records
        key = CameraKey((2100.0, -300.0, 300.0), (1900.0, 300.0, 60.0), 40.0)
        shot = PerspectiveShot(key.eye, key.target, key.fov_deg)
        coarse = rgb(host.capture((1280, 720), shot, wind_time_s=10.0, label="coarse"))
        spec = TourSpec(HeldCamera(key), 1.0, 24)

        def lods() -> dict[str, int]:
            return {name: state[1] for name, state in worker._applied_state.items()}

        def wanted(eyes: Any) -> dict[str, int]:
            answer = {}
            for name in lods():
                place = records[name].transform
                centre = (place.east_cm, place.north_cm,
                          place.base_cm + float(records[name].height_cm or 0.0) * 0.5)
                answer[name] = select_lod(min(math.dist(centre, eye) for eye in eyes))
            return answer

        before = lods()
        seen: dict[str, Any] = {}
        take = capture._tour_frame

        def spy(frame: Any) -> Any:
            if not seen:
                seen["lods"] = lods()
                seen["pending"] = capture._forge_pending()
            return take(frame)

        capture._tour_frame = spy
        folder = out / "frames"
        folder.mkdir()
        outcome: list[Any] = []
        recorder = capture.start_tour(spec, (1280, 720), PngSequenceWriter(folder))
        recorder.finished.connect(outcome.append)
        result["done_s"] = wait_until(lambda: bool(outcome), 240.0)
        tour = outcome[0]
        result["tour"] = {"ok": tour.ok, "frames": tour.frames, "unsettled": tour.unsettled}
        expected = wanted(path_eyes(spec))
        result["finer_than_the_view"] = sum(1 for name, lod in expected.items() if lod < before[name])
        result["frame_has_the_flights_detail"] = seen["lods"] == expected
        result["pending_at_first_frame"] = seen["pending"]
        fine = rgb(QImage(str(folder / "frame_000001.png")))
        result["fine_vs_coarse"] = difference(fine, coarse)
        settled(workspace)
        result["after_it_the_camera_decides"] = lods() == before
        return result
    finally:
        workspace.shutdown()
        window.close()
        pump(100)


def scenario_timelapse(out: Path) -> dict[str, Any]:
    from open_garden_planner.core.camera_path import HeldCamera, TourSpec
    from open_garden_planner.ui.view3d.video_writer import PngSequenceWriter
    from tests.integration.quick3d_render_support import EU_DST, load_rgb, luma

    window, workspace = main_window_on_plan(EU_DST)
    try:
        result: dict[str, Any] = {"settled_s": settled(workspace)}
        # A DST zone without tzdata, so the clock-change rows behave the same on every
        # test machine. The wall reading is what the user sees; the sun is read from UTC.
        window._sim_clock.set_datetime(datetime(2026, 6, 21, 15, 0))
        settled(workspace)
        capture = workspace.capture
        clock_before = window._sim_clock.wall
        rows = {}
        for name, spec in (
                ("day", TourSpec(HeldCamera(capture.camera_key()), 1.0, 24,
                                 time_range=(day_time(8, 0), day_time(20, 0)))),
                ("year", TourSpec(HeldCamera(capture.camera_key()), 1.0, 24,
                                  date_range=(date(2026, 3, 1), date(2026, 10, 31)))),
                # Two weeks either side of the autumn clock change: the frame pair that
                # straddles it is the one the owner saw jump by 24 levels (#732).
                ("dst", TourSpec(HeldCamera(capture.camera_key()), 1.0, 24,
                                 date_range=(date(2026, 10, 18), date(2026, 11, 1))))):
            outcome: list[Any] = []
            seen: list[tuple[str, str]] = []
            utc_seen: list[str] = []
            clock = window._sim_clock
            folder = out / name
            before = committed_mb()
            recorder = capture.start_tour(spec, (640, 360), PngSequenceWriter(folder))

            def moment(*_arguments: Any, seen: list[tuple[str, str]] = seen,
                       utc_seen: list[str] = utc_seen, clock: Any = clock) -> None:
                seen.append((clock.plan_date.isoformat(), clock.time_of_day.isoformat("minutes")))
                utc_seen.append(clock.utc.time().isoformat(timespec="minutes"))

            recorder.progress.connect(moment)
            recorder.finished.connect(outcome.append)
            started = time.monotonic()
            wait_until(outcome.__len__, 300.0)
            tour = outcome[0] if outcome else None
            files = sorted(folder.glob("frame_*.png"))
            means = [round(float(luma(load_rgb(path)).mean()), 3) for path in files]
            steps = [round(abs(after - before), 3)
                     for before, after in zip(means, means[1:], strict=False)]
            rows[name] = {"ok": tour.ok if tour else None, "frames": tour.frames if tour else None,
                          "message": tour.message if tour else "no end",
                          "unsettled": tour.unsettled if tour else None,
                          "wall_s": round(time.monotonic() - started, 1),
                          "growth_mb": round(committed_mb() - before, 1),
                          "files": len(files),
                          "first_moment": seen[0] if seen else None,
                          "last_moment": seen[-1] if seen else None,
                          "utc_times": utc_seen,
                          "luma_steps": steps,
                          "clock_back": clock.wall == clock_before}
            settled(workspace)
        result["runs"] = rows
        return result
    finally:
        workspace.shutdown()
        window.close()
        pump(100)


#: #799: the day lapse's dawn and dusk, wall times of the family garden's day (Berlin, 21 June,
#: CEST): the sun from below -8° to above +8°. 42 frames over 2 h 40 min is 3.9 min of clock
#: a frame - the survey's 10 s, 30 fps lapse of 04:00-23:00 (3.8 min): 0.33-0.51° of
#: elevation a frame, 0.5-0.7° of great circle.
DAYLAPSE_WINDOWS = (("dawn", day_time(3, 20), day_time(6, 0)),
                    ("dusk", day_time(20, 10), day_time(22, 50)))
DAYLAPSE_SECONDS, DAYLAPSE_FPS = 1.75, 24
#: The bands of a frame the lapse statistics read (the survey's): the top 12 % of rows (the
#: horizon's fog under the default framing, which follows the SHOWN sky) and the whole frame.
SKY_BAND_SHARE = 0.12


def scenario_daylapse(out: Path) -> dict[str, Any]:
    """#799: a held-camera day lapse through dawn and dusk on the family garden's default
    framing, the workspace's own recording path. Raw answers per frame: the mean luma of the
    sky band and of the frame, the frame's sun, the sun the sky on screen draws, and the skies
    built (the test computes the zigzag)."""
    from open_garden_planner.core.camera_path import HeldCamera, TourSpec
    from open_garden_planner.ui.view3d.video_writer import PngSequenceWriter
    from tests.integration.quick3d_render_support import EU_DST, load_rgb, luma

    window, workspace = main_window_on_plan(EU_DST, plan=FAMILY_GARDEN)
    try:
        result: dict[str, Any] = {"settled_s": settled(workspace, 180.0)}
        capture, look = workspace.capture, workspace.look
        runs: dict[str, Any] = {}
        for name, start, end in DAYLAPSE_WINDOWS:
            settled(workspace, 120.0)
            spec = TourSpec(HeldCamera(capture.camera_key()), DAYLAPSE_SECONDS, DAYLAPSE_FPS,
                            time_range=(start, end))
            folder = out / name
            frames: list[dict[str, Any]] = []
            built = [look.sky_rebuilds]

            def note(*_arguments: Any, frames: list[dict[str, Any]] = frames,
                     built: list[int] = built) -> None:
                sun, shown = look._sun, look.sky
                frames.append({"elev": round(sun.elevation_deg, 4), "az": round(sun.azimuth_deg, 3),
                               "sky_elev": None if shown is None else round(shown.sun_elevation_deg, 4),
                               "sky_builds": look.sky_rebuilds - built[0]})
                built[0] = look.sky_rebuilds

            outcome: list[Any] = []
            recorder = capture.start_tour(spec, (640, 360), PngSequenceWriter(folder))
            recorder.progress.connect(note)
            recorder.finished.connect(outcome.append)
            started = time.monotonic()
            wait_until(outcome.__len__, 400.0)
            tour = outcome[0] if outcome else None
            files = sorted(folder.glob("frame_*.png"))
            for row, path in zip(frames, files, strict=False):
                values = luma(load_rgb(path))
                row["sky_luma"] = round(float(values[:max(1, round(values.shape[0] * SKY_BAND_SHARE))].mean()), 4)
                row["frame_luma"] = round(float(values.mean()), 4)
            runs[name] = {"ok": tour.ok if tour else None, "frames": tour.frames if tour else None,
                          "unsettled": tour.unsettled if tour else None,
                          "message": tour.message if tour else "no end",
                          "wall_s": round(time.monotonic() - started, 1), "files": len(files),
                          "rows": frames}
        result["runs"] = runs
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
    "detail": scenario_detail,
    "timelapse": scenario_timelapse, "daylapse": scenario_daylapse, "agent": scenario_agent,
    "soak": scenario_soak,
    "daysoak": scenario_daysoak, "ultra_blur": scenario_ultra_blur,
    "picture": scenario_picture, "blur_bench": scenario_blur_bench,
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
