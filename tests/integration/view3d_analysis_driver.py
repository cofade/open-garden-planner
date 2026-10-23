"""Render-tier driver of Analyze in 3D (Phase 17 L2, #386): one child process, real engine.

Renders small top-down truth frames (``offscreen.render_records``: no tone curve, a
pixel is linear radiance) through the production host and writes what it measured
to ``<out>/result.json`` (and every frame as PNG). Run by
``test_view3d_analysis_render.py``; by hand::

    venv/Scripts/python.exe tests/integration/view3d_analysis_driver.py <out>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def main(out: Path) -> int:
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)
    from open_garden_planner.core.heatmap_render import build_sun_lut
    from open_garden_planner.core.scene3d import (
        GroundSpec,
        Material,
        Params,
        Record,
        SunState,
        Transform,
    )
    from open_garden_planner.core.scene3d.drape import shadow_drape, sun_hours_drape
    from open_garden_planner.core.scene3d.sun_path import compass_mesh
    from open_garden_planner.core.shade_aggregation import HeatmapGrid
    from open_garden_planner.ui.view3d.quick3d import selftest
    from open_garden_planner.ui.view3d.quick3d.offscreen import render_records
    from open_garden_planner.ui.view3d.quick3d.shots import TopDownShot, top_down_pixel

    out.mkdir(parents=True, exist_ok=True)
    size = (320, 240)
    width, depth = 800.0, 600.0
    shot = TopDownShot(center=(width / 2, depth / 2), px_per_cm=0.4)
    ground = GroundSpec(width, depth)
    sun = SunState(elevation_deg=60.0, azimuth_deg=180.0)
    result: dict[str, object] = {}

    def box(item_id: str, east: float, north: float, side: float, height: float, kind: str,
            tint: tuple[int, int, int, int] = (230, 20, 20, 255)) -> Record:
        half = side / 2.0
        return Record(item_id=item_id, kind="SELFTEST", shape="rectangle",
                      footprints=(((-half, -half), (half, -half), (half, half), (-half, half)),),
                      transform=Transform(east_cm=east, north_cm=north),
                      material=Material("SELFTEST", fill_rgba=tint), height_cm=height,
                      params=Params({"seed": item_id, "material_kind": kind}))

    def frame(name: str, records: dict, **options: object) -> np.ndarray:
        rendered = render_records(records, shot=shot, sun=sun, ground=ground, size=size,
                                  registry=selftest.registry(), **options)
        rendered.image.save(str(out / f"{name}.png"))
        result.setdefault("adapters", []).append(rendered.adapter or rendered.graphics_api)
        result.setdefault("qt_errors", 0)
        result["qt_errors"] = int(result["qt_errors"]) + int(rendered.qt.get("counts", {}).get("error", 0))
        result["ratio"] = rendered.device_pixel_ratio
        return rendered.rgba()[..., :3].astype(np.float64)

    def mean(rgb: np.ndarray, east: float, north: float, half: float) -> list[float]:
        ratio = float(result.get("ratio", 1.0))
        h, w = rgb.shape[:2]
        left, top = top_down_pixel(east - half, north + half, shot, (w, h), ratio)
        right, bottom = top_down_pixel(east + half, north - half, shot, (w, h), ratio)
        patch = rgb[int(np.ceil(top)):int(np.floor(bottom)), int(np.ceil(left)):int(np.floor(right))]
        return [float(v) for v in patch.reshape(-1, 3).mean(axis=0)]

    # ── the drapes ───────────────────────────────────────────────────────────
    bare = frame("bare", {})
    result["ground"] = mean(bare, 200.0, 300.0, 40.0)
    square = [(100.0, 250.0), (300.0, 250.0), (300.0, 350.0), (100.0, 350.0)]
    shadowed = frame("shadow_drape", {}, overlays={"drape": shadow_drape([square], width, depth)})
    result["shadow_drape"] = mean(shadowed, 200.0, 300.0, 30.0)
    grid = HeatmapGrid(0.0, 0.0, 50.0, cols=16, rows=12)
    minutes = np.zeros((12, 16))
    minutes[:6] = 900.0                       # row 0 = SOUTH: the south half in full sun
    hours = frame("sun_hours_drape", {}, overlays={"drape": sun_hours_drape(
        minutes, grid, 900.0, build_sun_lut())})
    result["sun_hours_north"] = mean(hours, 400.0, 500.0, 60.0)
    result["sun_hours_south"] = mean(hours, 400.0, 100.0, 60.0)

    # ── the lines: the compass's north arrow points up the north-up truth view ──
    lines = frame("compass", {}, overlays={"lines": compass_mesh((400.0, 300.0), 220.0)})
    red = (lines[..., 0] > 1.6 * lines[..., 1]) & (lines[..., 0] > 60)
    rows = np.nonzero(red)[0]
    result["north_arrow_rows"] = [int(rows.min()), int(rows.max())] if len(rows) else []
    result["frame_rows"] = int(lines.shape[0])

    # ── X-ray: a faded solid and a faded crown let the ground show through ──
    scene = {"wall": box("wall", 250.0, 300.0, 120.0, 200.0, "vc"),
             "crown": box("crown", 550.0, 300.0, 120.0, 200.0, "foliage")}
    solid = frame("xray_off", scene)
    faded = frame("xray_on", scene, faded={"wall", "crown"})
    for name, east in (("wall", 250.0), ("crown", 550.0)):
        result[f"{name}_solid"] = mean(solid, east, 300.0, 30.0)
        result[f"{name}_faded"] = mean(faded, east, 300.0, 30.0)

    # ── Cutaway: the roof goes, the walls stay ───────────────────────────────
    houses = {"roof": box("roof", 250.0, 300.0, 120.0, 150.0, "roof"),
              "walls": box("walls", 550.0, 300.0, 120.0, 150.0, "vc")}
    roofed = frame("roofs_on", houses)
    cut = frame("roofs_off", houses, roofs_hidden=True)
    for name, east in (("roof", 250.0), ("walls", 550.0)):
        result[f"{name}_shown"] = mean(roofed, east, 300.0, 30.0)
        result[f"{name}_cut"] = mean(cut, east, 300.0, 30.0)

    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
