"""Measurement probes for the Qt Quick 3D spike (ADR-047 criteria 8 + frame checks).

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


def _poly_mask(polys: list, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    mask = np.zeros(xs.shape, bool)
    for poly in polys:
        mask ^= M._point_in_polygon(xs, ys, poly)  # odd-even like the 2D overlay
    return mask


def shadow_iou_probe(renderer: Any, out: Path) -> dict:
    from open_garden_planner.spike_q3d.quick import NumpyGeometry, SpikeModel, SunState

    saved_models = renderer.models
    side, height = 100.0, 200.0
    fp = [(-side / 2, -side / 2), (side / 2, -side / 2), (side / 2, side / 2), (-side / 2, side / 2)]
    caster = M.prism(fp, height, 0.0, "#d01010", "#ff0000")
    ground = M.ground_quad(-2000, -2000, 2000, 2000, 0.0)
    models = [SpikeModel("caster", NumpyGeometry(caster), "vc", True),
              SpikeModel("ground", NumpyGeometry(ground), "white", False)]
    renderer.set_models(models)
    renderer.root.setProperty("groundTexture", None)
    renderer.set_preset("high")
    w, h = renderer.size
    mag = 0.5  # 1 px = 2 cm
    renderer.set_top_down((0.0, 0.0), mag)
    cols = (np.arange(w) + 0.5 - w / 2) / mag
    rows = (h / 2 - (np.arange(h) + 0.5)) / mag
    xs, ys = np.meshgrid(cols, rows)
    footprint = M._point_in_polygon(xs, ys, fp)
    results = {}
    azimuth = 225.0
    for elev in (15.0, 35.0, 60.0):
        d = sun_direction_scene(elev, azimuth)
        renderer.set_sun(SunState(elev, azimuth, (-d[0], -d[1], -d[2]), "#ffffff", 1.6, False))
        renderer.set_exposure(1.0, 0.9)
        renderer.wait_frames(6, label=f"iou_{int(elev)}")
        img = renderer.grab(label=f"iou_{int(elev)}")
        img.save(str(out / f"iou_{int(elev)}.png"))
        arr = _image_to_array(img)
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
        # direction check: centroid of the measured shadow must point away from the sun
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
    renderer.set_models(saved_models)
    return {"azimuth_deg": azimuth, "caster_cm": [side, side, height], "px_per_cm": mag,
            "results": results}


def orientation_probe(renderer: Any, out: Path, ground_img: Any, width: float,
                      height: float) -> dict:
    from open_garden_planner.spike_q3d.quick import SunState

    saved_models = renderer.models
    report: dict[str, Any] = {}
    # (a) ground texture orientation: top-down render of the ground alone vs the bake
    renderer.set_models([])
    renderer.set_ground(ground_img, 0, 0, width, height)
    w, h = renderer.size
    mag = min(w / width, h / height)
    renderer.set_top_down((width / 2, height / 2), mag)
    d = sun_direction_scene(70.0, 180.0)
    renderer.set_sun(SunState(70.0, 180.0, (-d[0], -d[1], -d[2]), "#ffffff", 1.4, False))
    renderer.wait_frames(6, label="orient_ground")
    img = renderer.grab(label="orient_ground")
    img.save(str(out / "orient_ground_topdown.png"))
    arr = _luma(_image_to_array(img))
    # crop the rendered plan rectangle
    pw, ph = round(width * mag), round(height * mag)
    x0, y0 = (w - pw) // 2, (h - ph) // 2
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
    renderer.set_preset("low")  # no fog: the horizon haze must not out-shine the sun glow
    sky = {}
    fov_v = 70.0
    for sun_az in (90.0, 180.0, 270.0):
        d = sun_direction_scene(12.0, sun_az)
        renderer.set_sun(SunState(12.0, sun_az, (-d[0], -d[1], -d[2]), "#ffffff", 1.4, False))
        found = None
        for look_az in (0.0, 90.0, 180.0, 270.0):
            tx = math.sin(math.radians(look_az)) * 1000
            ty = math.cos(math.radians(look_az)) * 1000
            renderer.set_camera((0.0, 0.0, 160.0),
                                (tx, ty, 160.0 + 1000 * math.tan(math.radians(14))), fov_v)
            renderer.wait_frames(4, label=f"sky_{int(sun_az)}_look_{int(look_az)}")
            shot = renderer.grab(label=f"sky_{int(sun_az)}_look_{int(look_az)}")
            arr = _image_to_array(shot)
            lum = _luma(arr)
            top = lum[: int(lum.shape[0] * 0.55)]
            warm = arr[: int(lum.shape[0] * 0.55), :, 0] - arr[: int(lum.shape[0] * 0.55), :, 2]
            score = top + 0.8 * warm  # the disc is the brightest AND warmest sky spot
            yx = np.unravel_index(np.argmax(score), score.shape)
            contrast = float(score[yx] - np.median(score))
            if contrast > 40 and (found is None or contrast > found[2]):
                w_img = lum.shape[1]
                h_img = lum.shape[0]
                fov_h = 2 * math.degrees(math.atan(math.tan(math.radians(fov_v / 2)) * w_img / h_img))
                off = math.degrees(math.atan((yx[1] - w_img / 2) / (w_img / 2)
                                             * math.tan(math.radians(fov_h / 2))))
                found = (look_az, (look_az + off) % 360.0, contrast)
        if found is None:
            sky[f"sun_az_{int(sun_az)}"] = {"measured_az": None}
            continue
        err = ((found[1] - sun_az + 180) % 360) - 180
        sky[f"sun_az_{int(sun_az)}"] = {"view_az": found[0], "measured_az": round(found[1], 1),
                                        "error_deg": round(err, 1), "contrast": round(found[2], 1)}
    report["sky_sun_disc"] = sky
    errs = [v.get("error_deg") for v in sky.values()]
    report["sky_ok"] = all(e is not None and abs(e) < 6.0 for e in errs)
    renderer.set_preset("high")
    renderer.set_models(saved_models)
    renderer.set_ground(ground_img, 0, 0, width, height)
    return report
