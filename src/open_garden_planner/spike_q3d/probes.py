"""Measurement probes for the Qt Quick 3D spike (ADR-048 criteria 8 + frame checks).

* ``shadow_iou_probe`` — top-down orthographic render of one box caster on a
  white ground, sun at 15°/35°/60°: the engine's shadow-map footprint vs the
  analytic ``core/shadow_geometry`` polygon, as IoU on the same pixel grid.
* ``orientation_probe`` — (a) ground texture: the 3D top-down render of the
  baked ground must correlate best with the north-up 2D bake *unflipped*;
  (b) sky: the procedural sky's sun disc must appear in the view that looks
  toward the solar azimuth.

Measure, don't eyeball: every result is a number written to metrics.json.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from open_garden_planner.core.scene3d import sun_direction_scene
from open_garden_planner.core.shadow_geometry import compute_scene_shadows
from open_garden_planner.spike_q3d import meshes as M


def _image_to_array(img: Any) -> np.ndarray:
    from PyQt6.QtGui import QImage

    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(bytes(ptr), np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
    return arr[:, : img.width(), :].astype(np.float32)


def _luma(arr: np.ndarray) -> np.ndarray:
    return 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]


# An isolated dark pixel: luma < 40 while the mean of its 8 neighbours is > 110 — a
# near-black dot on a lit surface. ExtendedSceneEnvironment's sharpening at 0.08
# overshot every thin lit/dark edge into them: teal-black slits in the picket fences,
# black stubble on lawns and crowns, 1,500-3,100 per daytime frame at 1280x720
# (3D reviewer pass 4's definition, in sRGB codes; its script was a scratch
# measurement, not committed).
SPECKLE_MAX_LUMA, SPECKLE_MIN_NEIGHBOURS = 40.0, 110.0


def isolated_dark_pixels(rgb: np.ndarray) -> int:
    """Pixels of an (h, w, 3+) sRGB frame darker than SPECKLE_MAX_LUMA in lit surroundings."""
    lum = _luma(np.asarray(rgb, np.float64))
    h, w = lum.shape
    pad = np.pad(lum, 1, mode="edge")
    neighbours = sum(pad[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                     for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)) / 8.0
    return int(((lum < SPECKLE_MAX_LUMA) & (neighbours > SPECKLE_MIN_NEIGHBOURS)).sum())


def frame_stats(img: Any) -> dict[str, Any]:
    """A board frame's numbers for its ``metrics.json`` row: isolated dark pixels, the
    share of pixels with a channel at 254 or more (clipped) and the mean luma."""
    rgb = _image_to_array(img)[..., :3].astype(np.float64)
    return {"isolated_dark_px": isolated_dark_pixels(rgb),
            "clipped_pct": round(float((rgb.max(axis=2) >= 254).mean()) * 100.0, 3),
            "mean_luma": round(float(_luma(rgb).mean()), 2)}


def _poly_mask(polys: list, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    mask = np.zeros(xs.shape, bool)
    for poly in polys:
        mask ^= M._point_in_polygon(xs, ys, poly)  # odd-even like the 2D overlay
    return mask


def _top_down_grid(width_px: int, height_px: int, px_per_cm: float) -> tuple[np.ndarray, np.ndarray]:
    """Scene (x, y) of every pixel centre of a top-down view centred on the origin.

    Built from the GRABBED image (device pixels): at a display scale of 1.5 the
    grab is 1.5x the logical size, and a grid built from the logical size made
    ``--iou`` crash and ``--orient`` report a mirrored ground (senior review).
    """
    cols = (np.arange(width_px) + 0.5 - width_px / 2) / px_per_cm
    rows = (height_px / 2 - (np.arange(height_px) + 0.5)) / px_per_cm
    return np.meshgrid(cols, rows)


def shadow_iou_probe(renderer: Any, out: Path, preset: str = "high") -> dict:
    """IoU of the engine's shadow footprint vs the analytic 2D shadow, at ``preset``.

    Each preset has its own shadow-map quality and filtering, so the gate is
    measured per preset (the L0 board only ever measured "high"). Everything it
    changes is restored (``SpikeRenderer.preserved_state``).
    """
    with renderer.preserved_state():
        return _shadow_iou(renderer, out, preset)


def _shadow_iou(renderer: Any, out: Path, preset: str) -> dict:
    from open_garden_planner.spike_q3d.quick import NumpyGeometry, SpikeModel, SunState

    side, height = 100.0, 200.0
    fp = [(-side / 2, -side / 2), (side / 2, -side / 2), (side / 2, side / 2), (-side / 2, side / 2)]
    caster = M.prism(fp, height, 0.0, "#d01010", "#ff0000")
    ground = M.ground_quad(-2000, -2000, 2000, 2000, 0.0)
    models = [SpikeModel("caster", NumpyGeometry(caster), "vc", True),
              SpikeModel("ground", NumpyGeometry(ground), "white", False)]
    renderer.set_models(models)
    renderer.root.setProperty("groundTexture", None)
    renderer.set_preset(preset)
    mag = 0.5  # logical px per cm: 1 px = 2 cm
    renderer.set_top_down((0.0, 0.0), mag)
    grid: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
    results = {}
    azimuth = 225.0
    for elev in (15.0, 35.0, 60.0):
        d = sun_direction_scene(elev, azimuth)
        renderer.set_sun(SunState(elev, azimuth, (-d[0], -d[1], -d[2]), "#ffffff", 1.6, False))
        renderer.set_exposure(1.0, 0.9)
        renderer.wait_frames(6, label=f"iou_{int(elev)}_{preset}")
        img = renderer.grab(label=f"iou_{int(elev)}_{preset}")
        img.save(str(out / f"iou_{int(elev)}_{preset}.png"))
        arr = _image_to_array(img)
        if grid is None:
            gx, gy = _top_down_grid(arr.shape[1], arr.shape[0], mag * img.devicePixelRatio())
            grid = (gx, gy, M._point_in_polygon(gx, gy, fp))
        xs, ys, footprint = grid
        lum = _luma(arr)
        red = (arr[..., 0] > 1.4 * arr[..., 1]) & (arr[..., 0] > 60)
        # lit ground reference: far from the caster on the sun side (SW quadrant)
        ref = lum[(xs < -300) & (ys < -300)]
        lit = float(np.median(ref)) if ref.size else float(lum.max())
        measured = (lum < 0.6 * lit) & ~red & ~footprint
        analytic = _poly_mask(compute_scene_shadows([(fp, height)], elev, azimuth), xs, ys)
        analytic &= ~footprint
        inter = np.logical_and(measured, analytic).sum()
        union = np.logical_or(measured, analytic).sum()
        iou = float(inter / union) if union else 0.0
        if measured.any():
            mx, my = float(xs[measured].mean()), float(ys[measured].mean())
            ax, ay = float(xs[analytic].mean()), float(ys[analytic].mean())
        else:
            mx = my = ax = ay = float("nan")
        results[f"{int(elev)}deg"] = {
            "iou": round(iou, 4), "measured_px": int(measured.sum()),
            "analytic_px": int(analytic.sum()), "lit_luma": round(lit, 1),
            "centroid_measured_cm": [round(mx, 1), round(my, 1)],
            "centroid_analytic_cm": [round(ax, 1), round(ay, 1)],
        }
    return {"preset": preset, "azimuth_deg": azimuth, "caster_cm": [side, side, height],
            "px_per_cm": mag, "device_pixel_ratio": img.devicePixelRatio(), "results": results}


# The sky check looks this far left and right of the sun: the disc then sits
# off-centre, where a wrong field-of-view or bearing mapping shows (a view aimed
# straight at the sun only proves the direction — senior review).
SKY_LOOK_OFFSETS_DEG = (-25.0, 25.0)
SKY_PITCH_DEG = 14.0  # the sky views look up this far, to put the 12-degree sun in frame


def pixel_bearing(px: float, py: float, width: float, height: float, yaw_deg: float,
                  pitch_deg: float, fov_v_deg: float) -> float:
    """Compass bearing of the world direction through image point (px, py).

    The inverse of a pinhole camera at compass ``yaw_deg`` pitched up by
    ``pitch_deg`` with vertical field of view ``fov_v_deg`` (x = E, y = N, z = up;
    image y grows downwards). The first version read the bearing off the x
    pixel alone, which is exact only for an unpitched camera: at 14 degrees of
    pitch it put ~0.6 degrees of its own error into every off-centre reading
    (senior review).
    """
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    tan_v = math.tan(math.radians(fov_v_deg) / 2)
    cam_x = (px - width / 2) / (width / 2) * tan_v * width / height  # right
    cam_y = (height / 2 - py) / (height / 2) * tan_v                  # up
    fwd = np.array([math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch),
                    math.sin(pitch)])
    right = np.array([math.cos(yaw), -math.sin(yaw), 0.0])
    up = np.cross(right, fwd)
    ray = cam_x * right + cam_y * up + fwd
    return math.degrees(math.atan2(ray[0], ray[1])) % 360.0


def orientation_probe(renderer: Any, out: Path, ground_img: Any, width: float,
                      height: float) -> dict:
    with renderer.preserved_state():
        return _orientation(renderer, out, ground_img, width, height)


def _orientation(renderer: Any, out: Path, ground_img: Any, width: float,
                 height: float) -> dict:
    from open_garden_planner.spike_q3d.quick import SunState

    report: dict[str, Any] = {}
    # (a) ground texture orientation: top-down render of the ground alone vs the bake
    renderer.set_models([])
    renderer.set_ground(ground_img, 0, 0, width, height)
    w, h = renderer.view_size()
    mag = min(w / width, h / height)
    renderer.set_top_down((width / 2, height / 2), mag)
    d = sun_direction_scene(70.0, 180.0)
    renderer.set_sun(SunState(70.0, 180.0, (-d[0], -d[1], -d[2]), "#ffffff", 1.4, False))
    renderer.wait_frames(6, label="orient_ground")
    img = renderer.grab(label="orient_ground")
    img.save(str(out / "orient_ground_topdown.png"))
    arr = _luma(_image_to_array(img))
    # crop the rendered plan rectangle — in DEVICE pixels (the grab's size)
    dpr = img.devicePixelRatio()
    gh, gw = arr.shape
    pw, ph = round(width * mag * dpr), round(height * mag * dpr)
    x0, y0 = (gw - pw) // 2, (gh - ph) // 2
    crop = arr[y0:y0 + ph, x0:x0 + pw]
    bake = _luma(_image_to_array(ground_img.scaled(pw, ph)))
    def ncc(a: np.ndarray, b: np.ndarray) -> float:
        a = a - a.mean()
        b = b - b.mean()
        den = math.sqrt(float((a * a).sum()) * float((b * b).sum())) or 1.0
        return float((a * b).sum() / den)
    variants = {"identity": bake, "flip_v": bake[::-1], "flip_h": bake[:, ::-1],
                "flip_both": bake[::-1, ::-1]}
    scores = {k: round(ncc(crop, v[: crop.shape[0], : crop.shape[1]]), 4) for k, v in variants.items()}
    report["ground_texture_ncc"] = scores
    report["ground_texture_ok"] = max(scores, key=scores.get) == "identity"
    # (b) sky sun disc orientation: find the sun glow, convert its pixel to a compass bearing
    renderer.set_ground(None, 0, 0, width, height)
    renderer.set_preset("low")  # the plainest post-processing. Fog is on at every preset
    # since creator round 2; the sun glow still reads above the haze (max error 0.79 deg
    # on D3D11 in Windows run v10)
    sky: dict[str, Any] = {}
    errs: list[float | None] = []
    fov_v = 70.0
    for sun_az in (90.0, 180.0, 270.0):
        d = sun_direction_scene(12.0, sun_az)
        renderer.set_sun(SunState(12.0, sun_az, (-d[0], -d[1], -d[2]), "#ffffff", 1.4, False))
        views = {}
        for offset in SKY_LOOK_OFFSETS_DEG:
            look_az = (sun_az + offset) % 360.0
            tx = math.sin(math.radians(look_az)) * 1000
            ty = math.cos(math.radians(look_az)) * 1000
            renderer.set_camera((0.0, 0.0, 160.0),
                                (tx, ty, 160.0 + 1000 * math.tan(math.radians(SKY_PITCH_DEG))),
                                fov_v)
            label = f"sky_{int(sun_az)}_look_{int(look_az)}"
            renderer.wait_frames(4, label=label)
            arr = _image_to_array(renderer.grab(label=label))
            lum = _luma(arr)
            band = int(lum.shape[0] * 0.55)
            score = lum[:band] + 0.8 * (arr[:band, :, 0] - arr[:band, :, 2])  # bright AND warm
            yx = np.unravel_index(np.argmax(score), score.shape)
            contrast = float(score[yx] - np.median(score))
            if contrast <= 40:
                views[f"{offset:+.0f}"] = {"measured_az": None}
                errs.append(None)
                continue
            measured = pixel_bearing(yx[1] + 0.5, yx[0] + 0.5, lum.shape[1], lum.shape[0],
                                     look_az, SKY_PITCH_DEG, fov_v)
            off = ((measured - look_az + 180) % 360) - 180
            err = ((measured - sun_az + 180) % 360) - 180
            errs.append(err)
            views[f"{offset:+.0f}"] = {"view_az": round(look_az, 1), "disc_offset_deg": round(off, 1),
                                       "measured_az": round(measured, 1),
                                       "error_deg": round(err, 2), "contrast": round(contrast, 1)}
        sky[f"sun_az_{int(sun_az)}"] = views
    report["sky_sun_disc"] = sky
    report["sky_look_offsets_deg"] = list(SKY_LOOK_OFFSETS_DEG)
    known = [abs(e) for e in errs if e is not None]
    report["sky_max_abs_error_deg"] = round(max(known), 2) if known else None
    report["sky_ok"] = bool(known) and len(known) == len(errs) and max(known) < 6.0
    return report
