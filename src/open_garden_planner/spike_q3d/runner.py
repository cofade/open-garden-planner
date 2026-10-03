"""``--spike-q3d`` entry point: render a real ``.ogp`` through Qt Quick 3D (ADR-047, L0).

Usage (dev, Windows or Linux with a GPU or Mesa)::

    python -m open_garden_planner --spike-q3d [--plan FILE.ogp] [--out DIR]
        [--host view|widget] [--presets low,medium,high,ultra] [--shots all|name,...]
        [--size 1280x720] [--fps-seconds 3] [--iou] [--orient]

Frozen exe: ``OpenGardenPlanner.exe --spike-q3d --plan C:\\path\\plan.ogp --out C:\\shots``.
Writes one PNG per shot × preset plus ``metrics.json``; exit 0 on success.
Spike strings are not translated (dev evidence tooling, the ADR-038 exemption).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_PLAN = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "plans" / "bench_small.ogp"

GROUND_TYPES = {"LAWN", "TERRACE_PATIO", "DRIVEWAY", "POND_POOL", "GARDEN_BED", "PATH",
                "FIRE_PIT", "PARASOL", "COLD_FRAME", "WATER_TAP", "PLANTER_POT"}
PLANT_TYPES = {"TREE", "SHRUB", "PERENNIAL"}
SOIL_PARENTS = {"RAISED_BED", "CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"}


@dataclass
class Shot:
    name: str
    when_utc: datetime
    eye: tuple[float, float, float]
    target: tuple[float, float, float]
    fov: float = 40.0


@dataclass
class BuildStats:
    items: int = 0
    models: int = 0
    triangles: int = 0
    build_ms: dict[str, float] = field(default_factory=dict)

    def add(self, kind: str, ms: float) -> None:
        self.build_ms[kind] = self.build_ms.get(kind, 0.0) + ms


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="--spike-q3d", add_help=True)
    p.add_argument("--spike-q3d", action="store_true")
    p.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    p.add_argument("--out", type=Path, default=Path.cwd() / "spike_q3d_out")
    p.add_argument("--host", choices=["view", "widget"], default="view")
    p.add_argument("--presets", default="high")
    p.add_argument("--shots", default="all")
    p.add_argument("--size", default="1280x720")
    p.add_argument("--fps-seconds", type=float, default=3.0)
    p.add_argument("--iou", action="store_true", help="measure 3D vs analytic shadow IoU")
    p.add_argument("--orient", action="store_true", help="render orientation probes")
    p.add_argument("--no-grass", action="store_true")
    p.add_argument("--grass-density", type=float, default=110.0)
    p.add_argument("--ssgi", action="store_true",
                   help="ultra WITH SSGI (opt-in: renders black on Mesa llvmpipe)")
    p.add_argument("--no-ssr", action="store_true", help="ultra without SSR")
    args, _unknown = p.parse_known_args(argv[1:])
    return args


# ── sun ──────────────────────────────────────────────────────────────────


def sun_state(lat: float, lon: float, when_utc: datetime):
    from open_garden_planner.core.scene3d import sun_direction_scene
    from open_garden_planner.core.solar import solar_position
    from open_garden_planner.spike_q3d.quick import SunState

    pos = solar_position(lat, lon, when_utc)
    elev, az = pos.elevation_deg, pos.azimuth_deg
    if elev < 0.5:  # night: cool moonlight from high in the south
        d = sun_direction_scene(38.0, 165.0)
        return SunState(elev, az, (-d[0], -d[1], -d[2]), "#8ea4d6", 0.32, True)
    d = sun_direction_scene(elev, az)
    if elev >= 30:
        color, bright = "#fff1dc", 1.9
    elif elev >= 15:
        color, bright = "#ffdcaa", 2.0
    elif elev >= 6:
        color, bright = "#ffb878", 2.1
    else:
        color, bright = "#ff9655", 1.7
    return SunState(elev, az, (-d[0], -d[1], -d[2]), color, bright, False)


# ── plan → meshes ────────────────────────────────────────────────────────


def _scene_points(item: Any, pts: list) -> list[tuple[float, float]]:
    return [(item.mapToScene(p).x(), item.mapToScene(p).y()) for p in pts]


def build_models(scene: Any, at: date, grass_density: float, with_grass: bool,
                 make_model: Any = None):
    """Walk the live CanvasScene and emit one or two engine models per item.

    ``make_model(item_id, mesh, kind, casts)`` builds the engine object; the
    default creates ``SpikeModel``s (Qt Quick 3D). ``scripts/bench_view3d.py``
    passes a plain-data factory to time the CPU side without any engine.
    """
    from open_garden_planner.core.object_height import effective_height_cm
    from open_garden_planner.spike_q3d import meshes as M
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.sun_shadow_controller import (
        _item_footprints,
        _plant_canopy_radius_cm,
    )

    stats = BuildStats()
    models: list[Any] = []
    by_id = {str(i.item_id): i for i in scene.items() if hasattr(i, "item_id")}
    tables = [i for i in by_id.values() if getattr(i, "object_type", None)
              and i.object_type.name == "TABLE_RECTANGULAR"]

    if make_model is None:
        from open_garden_planner.spike_q3d.quick import NumpyGeometry, SpikeModel

        def make_model(item_id: str, mesh: M.MeshData, kind: str, casts: bool) -> Any:
            return SpikeModel(item_id, NumpyGeometry(mesh), kind, casts)

    def emit(item_id: str, mesh: M.MeshData, kind: str, casts: bool = True) -> None:
        if mesh.vertex_count == 0:
            return
        models.append(make_model(item_id, mesh, kind, casts))
        stats.models += 1
        stats.triangles += mesh.triangle_count

    lawn_polys: list[list[tuple[float, float]]] = []
    lawn_excludes: list[list[tuple[float, float]]] = []
    for item in by_id.values():
        ot = getattr(item, "object_type", None)
        if ot is None or not item.isVisible():
            continue
        name = ot.name
        iid = str(item.item_id)
        fps = _item_footprints(item, at)
        if not fps:
            continue
        fp = fps[0]
        h = effective_height_cm(ot, item.metadata, at_date=at)
        t0 = time.perf_counter()
        stats.items += 1
        kind_label = name
        if name == "LAWN":
            lawn_polys.append(fp)
        elif name in ("POND_POOL", "GARDEN_BED", "FIRE_PIT") or name in SOIL_PARENTS:
            lawn_excludes.append(fp)
        if name in PLANT_TYPES and isinstance(item, CircleItem):
            center = item.mapToScene(item.center)
            radius = _plant_canopy_radius_cm(item, at) or item.radius
            height = h if h else max(radius * 1.2, 20.0)
            species = (item.metadata.get("plant_species") or {}).get("common_name") or \
                getattr(item, "plant_species", "") or ""
            base = 0.0
            parent = by_id.get(str(item.parent_bed_id)) if item.parent_bed_id else None
            if parent is not None and parent.object_type.name in SOIL_PARENTS:
                base = effective_height_cm(parent.object_type, parent.metadata) or 0.0
                base -= 2.0  # soil sits just below the rim
            mesh = M.plant_mesh(species, M.item_seed(iid), height, 2.0 * radius, name)
            emit(iid, M.translated(mesh, center.x(), center.y(), base), "foliage")
            kind_label = "plants"
        elif name == "HOUSE":
            ridge_id = item.metadata.get("ridge_item_id")
            ridge = by_id.get(str(ridge_id)) if ridge_id else None
            if ridge is not None and isinstance(ridge, PolylineItem) and len(ridge.points) >= 2:
                pts = _scene_points(ridge, ridge.points)
                emit(iid, M.gable_house(fp, (pts[0], pts[-1]), h or 450.0), "vc")
            else:
                emit(iid, M.prism(fp, h or 450.0, 0.0, "#efe4cf", "#9c8e7e"), "vc")
        elif name == "ROOF_RIDGE":
            continue
        elif name in ("GARAGE_SHED", "TOOL_SHED"):
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            if max(xs) - min(xs) >= max(ys) - min(ys):
                ridge = ((min(xs), (min(ys) + max(ys)) / 2), (max(xs), (min(ys) + max(ys)) / 2))
            else:
                ridge = (((min(xs) + max(xs)) / 2, min(ys)), ((min(xs) + max(xs)) / 2, max(ys)))
            emit(iid, M.gable_house(fp, ridge, h or 250.0, wall="#9c7a54", roof="#55606a",
                                    pitch_deg=25.0, overhang=20.0), "vc")
        elif name == "GREENHOUSE":
            frame, glass = M.greenhouse(fp, h or 220.0)
            emit(iid, frame, "vc")
            emit(iid, glass, "glass", casts=False)
        elif name == "PERGOLA":
            emit(iid, M.pergola(fp, h or 250.0), "vc")
        elif name == "TRELLIS":
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            long_y = (max(ys) - min(ys)) > (max(xs) - min(xs))
            length = max(max(ys) - min(ys), max(xs) - min(xs))
            ang = 90.0 if long_y else 0.0
            parts = [M.box(cx, cy, 0, length, 4, 6, "#a77b52", ang)]
            hh = h or 180.0
            for k in range(int(length // 30) + 1):
                off = -length / 2 + k * 30
                px, py = (cx, cy + off) if long_y else (cx + off, cy)
                parts.append(M.box(px, py, 0, 3, 3, hh, "#b48a5f"))
            for z in np.arange(25, hh, 30):
                parts.append(M.box(cx, cy, float(z), length, 2, 2.5, "#b48a5f", ang))
            emit(iid, M.MeshData.concat(parts), "vc")
        elif name in ("RAISED_BED", "CONTAINER", "WALL_PLANTER"):
            emit(iid, M.raised_bed(fp, h or 40.0), "vc")
        elif name == "CONTAINER_ROUND" and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            emit(iid, M.round_thing(c.x(), c.y(), item.radius, h or 30.0, "#c46a3c", "#4a3222"), "vc")
        elif name in ("HEDGE_POLYGON", "HEDGE_SECTION"):
            emit(iid, M.hedge(fp, h or 150.0, M.item_seed(iid)), "foliage")
        elif name == "FENCE" and isinstance(item, PolylineItem):
            emit(iid, M.polyline_posts_and_pickets(_scene_points(item, item.points), h or 120.0), "vc")
        elif name == "WALL" and isinstance(item, PolylineItem):
            emit(iid, M.stone_wall(_scene_points(item, item.points), h or 200.0), "vc")
        elif name == "POND_POOL":
            emit(iid, M.water_surface(fp, 2.0), "water", casts=False)
        elif name == "TABLE_RECTANGULAR":
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            emit(iid, M.table((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                              max(xs) - min(xs), max(ys) - min(ys), h or 75.0), "vc")
        elif name == "CHAIR":
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            facing = 0.0
            if tables:
                tc = tables[0].mapToScene(tables[0].rect().center())
                facing = math.degrees(math.atan2(tc.y() - cy, tc.x() - cx))
            emit(iid, M.chair(cx, cy, facing), "vc")
        elif name == "BENCH":
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            emit(iid, M.bench((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                              max(xs) - min(xs), max(ys) - min(ys)), "vc")
        elif name == "TRAMPOLINE" and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            emit(iid, M.trampoline(c.x(), c.y(), item.radius), "vc")
        elif name in ("RAIN_BARREL",) and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            emit(iid, M.round_thing(c.x(), c.y(), item.radius, h or 100.0, "#2f5a3a", "#22313a"), "vc")
        elif name == "BIRD_BATH" and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            parts = [M.cylinder((c.x(), c.y(), 0), (c.x(), c.y(), 75), 8, 6, "#c9c1b2"),
                     M.round_thing(c.x(), c.y(), item.radius * 1.6, 12, "#d6cfc2", "#7fb3c8")]
            parts[1] = M.translated(parts[1], 0, 0, 75)
            emit(iid, M.MeshData.concat(parts), "vc")
        elif name == "BBQ_GRILL" and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            kettle = M.spheres(np.array([[c.x(), c.y(), 80.0]]), item.radius, "#2a2a2e", squash=0.8,
                               smooth=True)
            legs = M.tubes(np.array([[c.x() + 15, c.y(), 0], [c.x() - 8, c.y() + 13, 0],
                                     [c.x() - 8, c.y() - 13, 0]], np.float32),
                           np.array([[c.x(), c.y(), 70]] * 3, np.float32),
                           np.full(3, 1.5), np.full(3, 1.5), "#3b3b3b", 5)
            emit(iid, M.MeshData.concat([kettle, legs]), "vc")
        elif name == "FIRE_PIT" and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            emit(iid, M.round_thing(c.x(), c.y(), item.radius, 28, "#8d8478", "#2b2622"), "vc")
        elif name in GROUND_TYPES:
            pass  # baked into the ground texture
        elif h:
            fill = getattr(item, "fill_color", None)
            color = fill.name() if fill is not None else "#9e9e94"
            emit(iid, M.prism(fp, h, 0.0, color), "vc")
        stats.add(kind_label, (time.perf_counter() - t0) * 1000.0)
    if with_grass and lawn_polys:
        t0 = time.perf_counter()
        for k, poly in enumerate(lawn_polys):
            g = M.grass(poly, 1000 + k, grass_density, exclude=lawn_excludes)
            emit(f"lawn-grass-{k}", g, "grass", casts=False)
        stats.add("grass", (time.perf_counter() - t0) * 1000.0)
    return models, stats


def bake_ground(scene: Any, width: float, height: float):
    """Render only the flat plan surfaces top-down (north-up) into a QImage."""
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QImage, QPainter

    from open_garden_planner.services.scene_rendering import render_scene_region

    px_per_cm = min(1.0, 4096.0 / max(width, height))
    w, h = round(width * px_per_cm), round(height * px_per_cm)
    hidden = []
    for item in scene.items():
        ot = getattr(item, "object_type", None)
        if ot is None:
            continue
        if ot.name not in GROUND_TYPES and item.isVisible() and item.parentItem() is None:
            item.setVisible(False)
            hidden.append(item)
    labels = scene.labels_enabled if hasattr(scene, "labels_enabled") else True
    scene.set_labels_visible(False)
    scene.set_shadows_enabled(False)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    try:
        render_scene_region(scene, painter, QRectF(0, 0, w, h), QRectF(0, 0, width, height),
                            y_flip=True)
    finally:
        painter.end()
    for item in hidden:
        item.setVisible(True)
    scene.set_labels_visible(labels)
    # scene.render() always paints the beige canvas background (drawBackground);
    # in 3D the empty plan reads as meadow, so swap that exact colour for grass
    # green (the production bake paints records directly and never sees it).
    from PyQt6.QtGui import QColor

    rgba = img.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = rgba.bits()
    ptr.setsize(rgba.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(rgba.height(), rgba.bytesPerLine() // 4, 4)
    canvas = QColor(scene.CANVAS_COLOR)
    meadow = QColor("#6f9a48")
    mask = ((arr[..., 0] == canvas.red()) & (arr[..., 1] == canvas.green())
            & (arr[..., 2] == canvas.blue())) | (arr[..., 3] == 0)
    arr[mask] = [meadow.red(), meadow.green(), meadow.blue(), 255]
    return rgba.copy()


# ── shots ────────────────────────────────────────────────────────────────


def look_for(sun) -> dict:
    """Sky/fog/exposure per sun height — golden hour warms the horizon, noon stays crisp.

    The direct sun must dominate the sky probe or shadows wash out (the first
    spike renders read flat because the IBL out-shone the light).
    """
    if sun.night:
        return {"skyTop": "#070d22", "skyHorizon": "#1b2747", "groundHorizon": "#141b2e",
                "sunDiscColor": "#9fb2e0", "fogColor": "#161e33", "meadowColor": "#1c2b1f",
                "exposure": 2.4, "probe": 0.35}
    e = sun.elevation
    if e < 8:
        return {"skyTop": "#4a6fb0", "skyHorizon": "#f2b47c", "groundHorizon": "#c79a72",
                "sunDiscColor": "#ffb070", "fogColor": "#e9c3a0", "meadowColor": "#5a8237",
                "exposure": 1.25, "probe": 0.42}
    if e < 20:
        return {"skyTop": "#4f7fc8", "skyHorizon": "#f4d2a6", "groundHorizon": "#b9b48a",
                "sunDiscColor": "#ffd09a", "fogColor": "#e6d2b8", "meadowColor": "#5b853a",
                "exposure": 1.15, "probe": 0.5}
    return {"skyTop": "#3f78c9", "skyHorizon": "#cfe2f2", "groundHorizon": "#a3b894",
            "sunDiscColor": "#fff0d8", "fogColor": "#cfdbe6", "meadowColor": "#5d8a3c",
            "exposure": 0.92, "probe": 0.55}


def apply_look(renderer, sun) -> None:
    from PyQt6.QtGui import QColor

    look = look_for(sun)
    for key in ("skyTop", "skyHorizon", "groundHorizon", "sunDiscColor", "fogColor",
                "meadowColor"):
        renderer.root.setProperty(key, QColor(look[key]))
    renderer.set_exposure(look["exposure"], look["probe"])


def default_shots(width: float, height: float) -> list[Shot]:
    cx, cy = width / 2, height / 2
    diag = math.hypot(width, height)
    june = date(2026, 6, 21)
    dec = date(2026, 12, 21)

    def utc(d: date, hour: float) -> datetime:
        hh = int(hour)
        return datetime(d.year, d.month, d.day, hh, int((hour - hh) * 60), tzinfo=UTC)

    se = (cx + 0.62 * width, cy - 0.95 * height, 0.36 * diag)
    hero = (cx + 0.55 * width, cy - 0.78 * height, 0.17 * diag)
    sw = (cx - 0.62 * width, cy - 0.95 * height, 0.40 * diag)
    return [
        Shot("golden_hour", utc(june, 17.5), hero, (cx - 0.08 * width, cy + 0.1 * height, 160), 46),
        Shot("noon", utc(june, 11.0), sw, (cx + 0.04 * width, cy, 40), 42),
        Shot("morning", utc(june, 6.0), (cx - 0.85 * width, cy - 0.35 * height, 0.22 * diag),
             (cx + 0.1 * width, cy, 60), 44),
        Shot("december_noon", utc(dec, 11.0), se, (cx, cy, 40), 42),
        Shot("night", utc(june, 21.5), se, (cx, cy, 40), 42),
        Shot("walk", utc(june, 14.5), (cx - 0.21 * width, cy + 0.03 * height, 165),
             (cx + 0.35 * width, cy - 0.35 * height, 70), 62),
    ]


def run_spike_cli(argv: list[str]) -> int:
    args = _parse(argv)
    from PyQt6.QtWidgets import QApplication

    t_start = time.perf_counter()
    app = QApplication.instance() or QApplication(argv[:1])
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.spike_q3d.quick import SpikeRenderer
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    w_px, h_px = (int(v) for v in args.size.lower().split("x"))
    metrics: dict[str, Any] = {
        "platform": platform.platform(), "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)), "plan": str(args.plan),
        "host": args.host, "size": [w_px, h_px],
        "env": {k: os.environ.get(k) for k in ("QSG_RHI_BACKEND", "QT_QPA_PLATFORM",
                                                "QSG_RHI_PREFER_SOFTWARE_RENDERER")},
    }
    from PyQt6.QtCore import QT_VERSION_STR

    metrics["qt"] = QT_VERSION_STR

    scene = CanvasScene()
    pm = ProjectManager()
    t0 = time.perf_counter()
    pm.load(scene, args.plan)
    metrics["load_plan_ms"] = (time.perf_counter() - t0) * 1000
    loc = pm.location or {"latitude": 52.52, "longitude": 13.405}
    lat, lon = float(loc["latitude"]), float(loc["longitude"])
    width, height = scene.width_cm, scene.height_cm

    t0 = time.perf_counter()
    ground = bake_ground(scene, width, height)
    metrics["ground_bake_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    models, stats = build_models(scene, date(2026, 6, 21), args.grass_density, not args.no_grass)
    metrics["build_models_ms"] = (time.perf_counter() - t0) * 1000
    metrics["build"] = {"items": stats.items, "models": stats.models,
                        "triangles": stats.triangles,
                        "by_kind_ms": {k: round(v, 1) for k, v in stats.build_ms.items()}}

    renderer = SpikeRenderer(args.host, (w_px, h_px))
    renderer.root.setProperty("allowSsgi", bool(args.ssgi))
    renderer.root.setProperty("allowSsr", not args.no_ssr)
    metrics["qml_load_ms"] = renderer.qml_load_ms
    t0 = time.perf_counter()
    renderer.set_models(models)
    renderer.set_ground(ground, 0, 0, width, height)
    metrics["scene_apply_ms"] = (time.perf_counter() - t0) * 1000
    metrics["geometry_upload_ms_total"] = sum(m.geometry.upload_ms for m in models)

    shots = default_shots(width, height)
    if args.shots != "all":
        wanted = set(args.shots.split(","))
        shots = [s for s in shots if s.name in wanted]
    renderer.set_preset(args.presets.split(",")[0])
    renderer.set_sun(sun_state(lat, lon, shots[0].when_utc if shots else datetime.now(UTC)))
    if shots:
        renderer.set_camera(shots[0].eye, shots[0].target, shots[0].fov)
    renderer.show()
    renderer.wait_frames(2, timeout_s=300)
    metrics["first_frame_ms"] = renderer.first_frame_ms
    metrics["graphics_api"] = renderer.graphics_api()
    shot_rows = []
    for preset in args.presets.split(","):
        renderer.set_preset(preset)
        for shot in shots:
            sun = sun_state(lat, lon, shot.when_utc)
            renderer.set_sun(sun)
            apply_look(renderer, sun)
            renderer.set_camera(shot.eye, shot.target, shot.fov)
            t0 = time.perf_counter()
            renderer.wait_frames(6, timeout_s=300)
            img = renderer.grab()
            path = out / f"{shot.name}_{preset}.png"
            img.save(str(path))
            shot_rows.append({"shot": shot.name, "preset": preset, "file": path.name,
                              "sun_elev": round(sun.elevation, 2), "sun_az": round(sun.azimuth, 2),
                              "settle_ms": round((time.perf_counter() - t0) * 1000, 1)})
        if args.fps_seconds > 0 and shots:
            renderer.set_camera(shots[0].eye, shots[0].target, shots[0].fov)
            metrics.setdefault("fps", {})[preset] = round(renderer.measure_fps(args.fps_seconds), 2)
    metrics["shots"] = shot_rows
    if args.iou:
        from open_garden_planner.spike_q3d.probes import shadow_iou_probe

        metrics["shadow_iou"] = shadow_iou_probe(renderer, out)
    if args.orient:
        from open_garden_planner.spike_q3d.probes import orientation_probe

        metrics["orientation"] = orientation_probe(renderer, out, ground, width, height)
    metrics["total_s"] = round(time.perf_counter() - t_start, 2)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ("graphics_api", "first_frame_ms", "build", "fps")
                      if k in metrics}, default=str))
    del app
    return 0
