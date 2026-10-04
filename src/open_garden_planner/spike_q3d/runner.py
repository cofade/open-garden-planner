"""``--spike-q3d`` entry point: render a real ``.ogp`` through Qt Quick 3D (ADR-047, L0).

Usage (dev, Windows or Linux with a GPU or Mesa)::

    python -m open_garden_planner --spike-q3d [--plan FILE.ogp] [--out DIR]
        [--host view|widget] [--presets low,medium,high,ultra] [--shots all|name,...]
        [--size 1280x720] [--fps-seconds 3] [--iou] [--orient]
        [--frame-timeout-s 120] [--watchdog-s 0]

Frozen exe: ``OpenGardenPlanner.exe --spike-q3d --plan C:\\path\\plan.ogp --out C:\\shots``.
Writes one PNG per shot × preset plus ``metrics.json``; exit 0 on success.

The frozen exe is a GUI-subsystem process with no stdout, so ``print`` is a
no-op there: every phase is written to ``<out>/spike.log`` (flushed per line)
and ``metrics.json`` is rewritten after every phase, so a run that dies or
hangs still leaves evidence. ``--watchdog-s`` arms ``faulthandler`` to dump
every thread's stack into the log and exit non-zero (Windows evidence run v1
hung for 56 min with no output at all).

Spike strings are not translated (dev evidence tooling, the ADR-038 exemption).
"""

from __future__ import annotations

import argparse
import contextlib
import faulthandler
import json
import math
import os
import platform
import sys
import time
import traceback
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

# ONE meadow albedo for the baked plan ground AND the endless meadow model: the
# linear mean of resources/textures/grass.png (hue 104°). Night comes from the
# light and the exposure, never from a darker albedo (the L0 board's per-mood
# meadow colours made the plan glow as an island at night: 5.6× its surround).
MEADOW_ALBEDO = "#487f34"
# Fog = sky horizon × probe exposure × this factor, in LINEAR light. The skybox
# is drawn × probeExposure but the fog is not, so a fog of "horizon × 0.6" (the
# L0 review's value) still sat 20-26 luma over the sky row above the horizon;
# × probe × 0.8 measures −0.7 / −0.5 / +1.4 luma (golden hour, morning, walk; high).
FOG_OF_HORIZON = 0.8


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
    # height / the builder's own top, per built item: fit_height() forces every top
    # to the data, so only this shows how far a builder was off before the fit
    fit_scales: dict[str, float] = field(default_factory=dict)
    # the plan's frost-free season on the build date (fruit and flowers shown or not)
    in_season: bool = True

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
    p.add_argument("--frame-timeout-s", type=float, default=120.0,
                   help="give up waiting for presented frames after this long (counted)")
    p.add_argument("--watchdog-s", type=float, default=0.0,
                   help="dump all stacks to spike.log and exit 1 after this long (0 = off)")
    p.add_argument("--pick", action="store_true", help="criterion 7: 20 picks vs a CPU oracle")
    p.add_argument("--update-bench", action="store_true",
                   help="criterion 6: replace a 100k-vertex geometry, time it")
    p.add_argument("--cold", action="store_true",
                   help="criterion 5: disable the Qt, QML and Mesa shader/pipeline disk caches, "
                        "so open time includes every compile (a first launch)")
    p.add_argument("--second-window", action="store_true",
                   help="a second 3D window in the same process, same view (what L1.3 avoids)")
    p.add_argument("--coexist", action="store_true",
                   help="criterion 2 (M1): QWebEngineView + 3D in one process")
    p.add_argument("--pan-bench", action="store_true",
                   help="criterion 3 (M2): 2D pan cost with/without a QQuickWidget")
    p.add_argument("--qml-dir", type=Path, default=None,
                   help="load GardenSpike.qml and its shaders from this folder "
                        "(the render tier's broken-shader positive control)")
    p.add_argument("--soak-leak-mb", type=float, default=0.0, metavar="MB",
                   help="positive control for the soak's leak gate: keep MB of memory alive "
                        "per project reload, so the gate must fire")
    p.add_argument("--soak", type=int, default=0, metavar="N",
                   help="criterion 10: N show/hide cycles, a project reload every "
                        "fifth, then close while animating")
    args, unknown = p.parse_known_args(argv[1:])
    # A typo must not run a different experiment and still report "ok" (senior review).
    args.unknown = unknown
    return args


PRESETS = ("low", "medium", "high", "ultra")
# --cold: every disk cache a Quick 3D open can hit (all present in the 6.11 runtime;
# Mesa's is Linux-only). GPU drivers keep their own caches, which no flag reaches.
COLD_ENV = {"QT_DISABLE_SHADER_DISK_CACHE": "1", "QSG_RHI_DISABLE_DISK_CACHE": "1",
            "QT_QUICK3D_NO_SHADER_CACHE_LOAD": "1", "QML_DISABLE_DISK_CACHE": "1",
            "MESA_SHADER_CACHE_DISABLE": "true"}
_CACHE_MARKERS = ("q3dshadercache", "qtpipelinecache", "qmlcache", "qtshadercache",
                  "mesa_shader_cache")
SETTINGS_ORGANIZATION = "cofade-ogp-tooling"
SETTINGS_APPLICATION = "Open Garden Planner 3D spike"


def _isolate_settings() -> None:
    """Point every settings store at a throwaway key before anything builds one.

    Loading a plan records it in Recent Files; evidence runs on the owner's
    machine must never touch the user's own settings (the redirection
    ``tests/conftest.py`` performs for the test suite).
    """
    import open_garden_planner.app.settings as app_settings

    app_settings.ORGANIZATION_NAME = SETTINGS_ORGANIZATION
    app_settings.APPLICATION_NAME = SETTINGS_APPLICATION


def _cache_inventory() -> list[str]:
    """Names of the Qt cache entries present now (names only: the path holds the user name).

    Measured on llvmpipe: the app's cache folder holds ``q3dshadercache-*``,
    ``qtpipelinecache-*`` and ``qmlcache`` after a first launch; the scene graph's
    ``qtshadercache-*`` and Mesa's ``mesa_shader_cache`` sit one level up, in the
    generic cache (Windows run v8: the first three, ``llp64``).
    """
    from PyQt6.QtCore import QStandardPaths

    found: set[str] = set()
    for where in (QStandardPaths.StandardLocation.CacheLocation,
                  QStandardPaths.StandardLocation.GenericCacheLocation):
        root = Path(QStandardPaths.writableLocation(where))
        if root.is_dir():
            found.update(p.name for p in root.iterdir() if p.name.startswith(_CACHE_MARKERS))
    return sorted(found)


def _validate(args: argparse.Namespace, shot_names: set[str] | None) -> None:
    """Fail on a typo before any work; shots are checked once the plan's size is known."""
    if args.unknown:
        raise ValueError(f"unknown arguments: {' '.join(args.unknown)}")
    bad = [p for p in args.presets.split(",") if p not in PRESETS]
    if bad:
        raise ValueError(f"unknown presets {bad}; choose from {list(PRESETS)}")
    if shot_names is not None and args.shots != "all":
        missing = set(args.shots.split(",")) - shot_names
        if missing:
            raise ValueError(f"unknown shots {sorted(missing)}; choose from {sorted(shot_names)}")


class SpikeLog:
    """Timestamped, line-flushed progress log in the output directory.

    Mirrors to stdout only when there is one (a frozen GUI exe has none).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._t0 = time.perf_counter()
        self.file = path.open("w", encoding="utf-8", buffering=1)

    def __call__(self, phase: str, **fields: Any) -> None:
        detail = " ".join(f"{k}={v}" for k, v in fields.items())
        line = f"{time.perf_counter() - self._t0:9.2f}s [{phase}] {detail}".rstrip()
        self.file.write(line + "\n")
        self.file.flush()
        if sys.stdout is not None:
            print(line, flush=True)

    def close(self) -> None:
        self.file.close()


_QT_MESSAGES: Any = None  # the run's QtMessages, folded into every metrics write


def _write_metrics(out: Path, metrics: dict) -> None:
    if _QT_MESSAGES is not None:
        metrics["qt_messages"] = _QT_MESSAGES.report()
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")


# ── sun ──────────────────────────────────────────────────────────────────


# The key light by sun elevation (ogp-lush-cinematic §3): the noon rig at and above
# SUN_RAMP_HIGH_DEG, the golden rig at SUN_RAMP_LOW_DEG, a CONTINUOUS ramp between them
# (colour mixed in linear light), the low-sun rig below. The old 15°/6° steps gave the
# December noon sun (14.0°) a warmer colour than June's golden hour (15.2°).
SUN_NOON = ("#fff1dc", 1.9)
SUN_GOLDEN = ("#ffb878", 2.1)
SUN_LOW = ("#ff9655", 1.7)
SUN_RAMP_HIGH_DEG, SUN_RAMP_LOW_DEG = 30.0, 6.0


def _linear_to_hex(lin: np.ndarray) -> str:
    lin = np.clip(np.asarray(lin, np.float64), 0.0, 1.0)
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    return "#" + "".join(f"{round(float(c) * 255):02x}" for c in srgb)


def sun_light(elev: float) -> tuple[str, float]:
    """(colour, brightness) of the daytime key light at ``elev`` degrees."""
    from open_garden_planner.spike_q3d.meshes import srgb_to_linear

    if elev >= SUN_RAMP_HIGH_DEG:
        return SUN_NOON
    if elev < SUN_RAMP_LOW_DEG:
        return SUN_LOW
    t = (elev - SUN_RAMP_LOW_DEG) / (SUN_RAMP_HIGH_DEG - SUN_RAMP_LOW_DEG)
    lo, hi = (srgb_to_linear(c).astype(np.float64) for c in (SUN_GOLDEN[0], SUN_NOON[0]))
    return _linear_to_hex(lo + (hi - lo) * t), SUN_GOLDEN[1] + (SUN_NOON[1] - SUN_GOLDEN[1]) * t


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
    color, bright = sun_light(elev)
    return SunState(elev, az, (-d[0], -d[1], -d[2]), color, bright, False)


# ── plan → meshes ────────────────────────────────────────────────────────


def _frost_month_day(value: Any) -> tuple[int, int] | None:
    """A frost date as (month, day), or None when absent or not a valid ``"MM-DD"``.

    The format the plan stores and every reader parses (``task_generator._parse_frost``,
    ``models/succession.py``): month and day split on "-". Checked against a LEAP year,
    so "02-29" stays a valid date; a malformed value counts as no data.
    """
    if not isinstance(value, str):
        return None
    try:
        month, day = (int(part) for part in value.split("-"))
        date(2000, month, day)
    except (ValueError, TypeError):
        return None
    return month, day


def in_frost_free_season(location: dict[str, Any] | None, at: date) -> bool:
    """True when ``at`` lies in the plan's frost-free season — fruit and flowers are shown.

    The season is the plan's OWN data: ``location["frost_dates"]["last_spring_frost"]``
    ≤ the day ≤ ``["first_fall_frost"]`` (both ``"MM-DD"``, inclusive) — the keys the
    task generator and the succession model read. No frost dates means no seasonal
    claim (True); with only one date the window is open on the other side; a spring
    date after the fall date wraps the new year (a southern-hemisphere entry).
    """
    frost = location.get("frost_dates") if isinstance(location, dict) else None
    if not isinstance(frost, dict):  # absent, or malformed in a hand-edited file: no data
        frost = {}
    spring = _frost_month_day(frost.get("last_spring_frost"))
    fall = _frost_month_day(frost.get("first_fall_frost"))
    day = (at.month, at.day)
    if spring is not None and fall is not None and spring > fall:
        return day >= spring or day <= fall
    return (spring is None or day >= spring) and (fall is None or day <= fall)


def _scene_points(item: Any, pts: list) -> list[tuple[float, float]]:
    return [(item.mapToScene(p).x(), item.mapToScene(p).y()) for p in pts]


def build_models(scene: Any, at: date, grass_density: float, with_grass: bool,
                 make_model: Any = None, location: dict[str, Any] | None = None):
    """Walk the live CanvasScene and emit one or two engine models per item.

    ``make_model(item_id, mesh, kind, casts)`` builds the engine object; the
    default creates ``SpikeModel``s (Qt Quick 3D). ``scripts/bench_view3d.py``
    passes a plain-data factory to time the CPU side without any engine.

    Truth rules (``ogp-lush-cinematic`` §1): every height comes from the SAME
    resolver the 2D shadow overlay uses (``effective_height_cm(at_date=at)``);
    a built item's meshes are fitted together so their top IS that height
    (``meshes.fit_height``); an item the resolver gives no height is drawn as
    decoration and casts NO shadow — exactly as in 2D, where it casts none.
    ``location`` is the plan's (``ProjectManager.location``): its frost dates
    decide whether fruit and flowers are in season on ``at``
    (``in_frost_free_season``); without them every accent stays.
    """
    from open_garden_planner.core.object_height import effective_height_cm
    from open_garden_planner.spike_q3d import meshes as M
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.sun_shadow_controller import (
        _item_footprints,
        _plant_canopy_radius_cm,
    )

    stats = BuildStats(in_season=in_frost_free_season(location, at))
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

    def emit_built(item_id: str, parts: list[tuple[M.MeshData, str, bool]],
                   height: float | None) -> None:
        """A non-plant item: ONE z-scale for all its meshes, so their union's top IS ``height``."""
        parts = [p for p in parts if p[0].vertex_count]
        if not parts:
            return
        if height:
            top = max(float(mesh.positions[:, 2].max()) for mesh, _k, _c in parts)
            stats.fit_scales[item_id] = height / top if top > 0 else float("inf")
            parts = [(M.fit_height(mesh, height, top=top), k, c) for mesh, k, c in parts]
        for mesh, kind, casts in parts:
            emit(item_id, mesh, kind, casts and bool(height))

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
        parts: list[tuple[M.MeshData, str, bool]] = []
        if name in PLANT_TYPES and isinstance(item, CircleItem):
            center = item.mapToScene(item.center)
            radius = _plant_canopy_radius_cm(item, at) or item.radius
            height = h if h else max(radius * 1.2, 20.0)  # no resolved height: decoration
            species = (item.metadata.get("plant_species") or {}).get("common_name") or \
                getattr(item, "plant_species", "") or ""
            base = 0.0
            parent = by_id.get(str(item.parent_bed_id)) if item.parent_bed_id else None
            if parent is not None and parent.object_type.name in SOIL_PARENTS:
                base = effective_height_cm(parent.object_type, parent.metadata, at_date=at) or 0.0
                base -= 2.0  # soil sits just below the rim
            mesh = M.plant_mesh(species, M.item_seed(iid), height, 2.0 * radius, name,
                                in_season=stats.in_season)
            emit(iid, M.translated(mesh, center.x(), center.y(), base), "foliage", h is not None)
            stats.add("plants", (time.perf_counter() - t0) * 1000.0)
            continue
        if name == "HOUSE":
            ridge_id = item.metadata.get("ridge_item_id")
            ridge = by_id.get(str(ridge_id)) if ridge_id else None
            if ridge is not None and isinstance(ridge, PolylineItem) and len(ridge.points) >= 2:
                pts = _scene_points(ridge, ridge.points)
                parts.append((M.gable_house(fp, (pts[0], pts[-1]), h or 450.0), "vc", True))
            else:
                parts.append((M.prism(fp, h or 450.0, 0.0, "#efe4cf", "#9c8e7e"), "vc", True))
        elif name == "ROOF_RIDGE":
            continue
        elif name in ("GARAGE_SHED", "TOOL_SHED"):
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            if max(xs) - min(xs) >= max(ys) - min(ys):
                ridge = ((min(xs), (min(ys) + max(ys)) / 2), (max(xs), (min(ys) + max(ys)) / 2))
            else:
                ridge = (((min(xs) + max(xs)) / 2, min(ys)), ((min(xs) + max(xs)) / 2, max(ys)))
            # roof: the 2D shingle texture's mid tone (was a blue-grey #55606a)
            parts.append((M.gable_house(fp, ridge, h or 250.0, wall="#9c7a54", roof="#78695a",
                                        pitch_deg=25.0, overhang=20.0), "vc", True))
        elif name == "GREENHOUSE":
            frame, glass = M.greenhouse(fp, h or 220.0)
            parts += [(frame, "vc", True), (glass, "glass", False)]
        elif name == "PERGOLA":
            parts.append((M.pergola(fp, h or 250.0), "vc", True))
        elif name == "TRELLIS":
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            long_y = (max(ys) - min(ys)) > (max(xs) - min(xs))
            length = max(max(ys) - min(ys), max(xs) - min(xs))
            ang = 90.0 if long_y else 0.0
            pieces = [M.box(cx, cy, 0, length, 4, 6, "#a77b52", ang)]
            hh = h or 180.0
            for k in range(int(length // 30) + 1):
                off = -length / 2 + k * 30
                px, py = (cx, cy + off) if long_y else (cx + off, cy)
                pieces.append(M.box(px, py, 0, 3, 3, hh, "#b48a5f"))
            for z in np.arange(25, hh, 30):
                pieces.append(M.box(cx, cy, float(z), length, 2, 2.5, "#b48a5f", ang))
            parts.append((M.MeshData.concat(pieces), "vc", True))
        elif name in ("RAISED_BED", "CONTAINER", "WALL_PLANTER"):
            parts.append((M.raised_bed(fp, h or 40.0), "vc", True))
        elif name == "CONTAINER_ROUND" and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            parts.append((M.round_thing(c.x(), c.y(), item.radius, h or 30.0, "#c46a3c", "#4a3222"),
                          "vc", True))
        elif name in ("HEDGE_POLYGON", "HEDGE_SECTION"):
            parts.append((M.hedge(fp, h or 150.0, M.item_seed(iid)), "foliage", True))
        elif name == "FENCE" and isinstance(item, PolylineItem):
            parts.append((M.polyline_posts_and_pickets(_scene_points(item, item.points),
                                                       h or 120.0), "vc", True))
        elif name == "WALL" and isinstance(item, PolylineItem):
            parts.append((M.stone_wall(_scene_points(item, item.points), h or 200.0), "vc", True))
        elif name == "POND_POOL":
            parts.append((M.water_surface(fp, 2.0), "water", False))
        elif name == "TABLE_RECTANGULAR":
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            parts.append((M.table((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                                  max(xs) - min(xs), max(ys) - min(ys), h or 75.0), "vc", True))
        elif name == "CHAIR":
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            facing = 0.0
            if tables:
                tc = tables[0].mapToScene(tables[0].rect().center())
                facing = math.degrees(math.atan2(tc.y() - cy, tc.x() - cx))
            parts.append((M.chair(cx, cy, facing, h or 85.0), "vc", True))
        elif name == "BENCH":
            xs, ys = [p[0] for p in fp], [p[1] for p in fp]
            parts.append((M.bench((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                                  max(xs) - min(xs), max(ys) - min(ys), h or 85.0), "vc", True))
        elif name == "TRAMPOLINE" and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            parts.append((M.trampoline(c.x(), c.y(), item.radius, h or 90.0), "vc", True))
        elif name in ("RAIN_BARREL",) and isinstance(item, CircleItem):
            # no 2D height (not in DEFAULT_HEIGHTS_CM): decoration, casts nothing
            c = item.mapToScene(item.center)
            parts.append((M.round_thing(c.x(), c.y(), item.radius, h or 100.0, "#2f5a3a",
                                        "#22313a"), "vc", True))
        elif name == "BIRD_BATH" and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            parts.append((M.bird_bath(c.x(), c.y(), item.radius, h or 90.0), "vc", True))
        elif name == "BBQ_GRILL" and isinstance(item, CircleItem):
            c = item.mapToScene(item.center)
            parts.append((M.bbq_grill(c.x(), c.y(), item.radius, h or 90.0), "vc", True))
        elif name == "FIRE_PIT" and isinstance(item, CircleItem):
            # no 2D height (not in DEFAULT_HEIGHTS_CM): decoration, casts nothing
            c = item.mapToScene(item.center)
            parts.append((M.round_thing(c.x(), c.y(), item.radius, h or 28.0, "#8d8478",
                                        "#2b2622"), "vc", True))
        elif name in GROUND_TYPES:
            pass  # baked into the ground texture
        elif h:
            fill = getattr(item, "fill_color", None)
            color = fill.name() if fill is not None else "#9e9e94"
            parts.append((M.prism(fp, h, 0.0, color), "vc", True))
        emit_built(iid, parts, h)
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
    shadows = scene.shadows_enabled
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    try:
        scene.set_labels_visible(False)
        scene.set_shadows_enabled(False)
        painter = QPainter(img)
        try:
            render_scene_region(scene, painter, QRectF(0, 0, w, h), QRectF(0, 0, width, height),
                                y_flip=True)
        finally:
            painter.end()
    finally:  # the scene is handed on to the 3D build: leave it as it was found
        for item in hidden:
            item.setVisible(True)
        scene.set_labels_visible(labels)
        scene.set_shadows_enabled(shadows)
    # scene.render() always paints the beige canvas background (drawBackground);
    # in 3D the empty plan reads as meadow, so swap that exact colour for grass
    # green (the production bake paints records directly and never sees it).
    from PyQt6.QtGui import QColor

    rgba = img.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = rgba.bits()
    ptr.setsize(rgba.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(rgba.height(), rgba.bytesPerLine() // 4, 4)
    canvas = QColor(scene.CANVAS_COLOR)
    meadow = QColor(MEADOW_ALBEDO)  # the same albedo as the endless meadow model
    mask = ((arr[..., 0] == canvas.red()) & (arr[..., 1] == canvas.green())
            & (arr[..., 2] == canvas.blue())) | (arr[..., 3] == 0)
    arr[mask] = [meadow.red(), meadow.green(), meadow.blue(), 255]
    return rgba.copy()


def _measure(args: argparse.Namespace, renderer: Any, scene: Any, ground: Any, width: float,
             height: float, out: Path, log: SpikeLog, metrics: dict[str, Any],
             reload: Any = None) -> None:
    """The L0.2 measurement flags, in an order where none disturbs the next."""
    from open_garden_planner.spike_q3d import measure

    steps: list[tuple[str, bool, Any]] = [
        ("pick", args.pick, lambda: measure.pick_probe(renderer, width, height)),
        ("update_bench", args.update_bench, lambda: measure.update_bench(renderer)),
        ("second_window", args.second_window,
         lambda: measure.second_window(renderer, ground, width, height, log)),
        ("coexist", args.coexist, lambda: measure.coexist_probe(renderer, log)),
        ("pan_bench", args.pan_bench,
         lambda: measure.pan_bench(scene, renderer, ground, width, height, log)),
        ("soak", args.soak > 0,  # last: it ends by animating
         lambda: measure.soak(renderer, args.soak, reload=reload,
                              deliberate_leak_mb=args.soak_leak_mb)),
    ]
    for name, wanted, run in steps:
        if not wanted:
            continue
        log(f"{name}_start")
        metrics[name] = run()
        log(f"{name}_done", result=json.dumps(metrics[name], default=str)[:400])
        _write_metrics(out, metrics)


# ── shots ────────────────────────────────────────────────────────────────


def scale_linear(hex_color: str, factor: float) -> str:
    """``#rrggbb`` scaled by ``factor`` in LINEAR light, back to ``#rrggbb``."""
    from open_garden_planner.spike_q3d.meshes import srgb_to_linear

    return _linear_to_hex(srgb_to_linear(hex_color).astype(np.float64) * factor)


def look_for(sun: Any) -> dict[str, Any]:
    """Sky/fog/exposure per sun height — golden hour warms the horizon, noon stays crisp.

    The direct sun must dominate the sky probe or shadows wash out (the first
    spike renders read flat because the IBL out-shone the light). The fog is
    DERIVED from the sky horizon as the skybox draws it (× probe exposure,
    ``FOG_OF_HORIZON``) so the meadow melts into the sky without a band; the
    ground albedo is not part of the look at all (``MEADOW_ALBEDO``) — a mood
    is light, never paint.
    """
    look: dict[str, Any]
    if sun.night:
        look = {"skyTop": "#070d22", "skyHorizon": "#1b2747", "sunDiscColor": "#9fb2e0",
                "exposure": 2.4, "probe": 0.35}
    elif sun.elevation < 8:
        look = {"skyTop": "#4a6fb0", "skyHorizon": "#f2b47c", "sunDiscColor": "#ffb070",
                "exposure": 1.25, "probe": 0.42}
    elif sun.elevation < 20:
        look = {"skyTop": "#4f7fc8", "skyHorizon": "#f4d2a6", "sunDiscColor": "#ffd09a",
                "exposure": 1.15, "probe": 0.5}
    else:
        # exposure 0.85 (was 0.92): noon_low clipped a channel on 4.6 % of the frame, the
        # sun-lit roof at R 254; now 0.26 %, the lawn still luma 158 / saturation 0.64
        look = {"skyTop": "#3f78c9", "skyHorizon": "#cfe2f2", "sunDiscColor": "#fff0d8",
                "exposure": 0.85, "probe": 0.55}
    look["fogColor"] = scale_linear(look["skyHorizon"], look["probe"] * FOG_OF_HORIZON)
    return look


class ModelsByDate:
    """The plan's engine models as they stand on a date — built once per date, shown on demand.

    The 2D shadow overlay recomputes its casters at the simulation DATE
    (``SunShadowController.recompute_now``: growth-projected heights and
    canopies, keyed on the UTC date), so a 3D shot must show the plan on its
    own sun date too: the L0 board built every model for 21 June, and its
    December shot showed June plants (29 of 99 bench items differ).
    """

    def __init__(self, build: Any) -> None:
        self._build = build  # date -> (models, BuildStats)
        self.sets: dict[date, tuple[list[Any], BuildStats, float]] = {}
        self.active_date: date | None = None

    def get(self, at: date) -> list[Any]:
        if at not in self.sets:
            t0 = time.perf_counter()
            models, stats = self._build(at)
            self.sets[at] = (models, stats, (time.perf_counter() - t0) * 1000.0)
        return self.sets[at][0]

    def activate(self, renderer: Any, at: date) -> bool:
        """Show the models of ``at``; True when the renderer's models changed."""
        if at == self.active_date:
            return False
        renderer.set_models(self.get(at))
        self.active_date = at
        return True

    def report(self) -> dict[str, dict[str, Any]]:
        return {at.isoformat(): {"items": s.items, "models": s.models, "triangles": s.triangles,
                                 "in_season": s.in_season, "build_ms": round(ms, 1)}
                for at, (_m, s, ms) in sorted(self.sets.items())}


def shoot_board(renderer: Any, shots: list[Shot], presets: list[str], models: ModelsByDate,
                sun_for: Any, out: Path, log: Any, metrics: dict[str, Any],
                fps_seconds: float = 0.0) -> list[dict[str, Any]]:
    """Render every shot at every preset; each shot shows the plan on its own sun date.

    ``sun_for(when_utc)`` returns the ``SunState``. The look is applied
    BEFORE the sun, so the fresh sky texture a sun change builds is born with
    this shot's colours (the light probe is pre-filtered once per texture).
    """
    rows: list[dict[str, Any]] = []
    metrics["shots"] = rows
    for preset in presets:
        renderer.set_preset(preset)
        for shot in shots:
            at = shot.when_utc.date()  # the 2D overlay's rule: sim_dt_utc.date()
            if models.activate(renderer, at):
                log("models_for_date", date=at.isoformat(), models=len(renderer.models),
                    in_season=models.sets[at][1].in_season)
            sun = sun_for(shot.when_utc)
            renderer.set_look(look_for(sun))
            renderer.set_sun(sun)
            renderer.set_camera(shot.eye, shot.target, shot.fov)
            t0 = time.perf_counter()
            renderer.wait_frames(6, label=f"{shot.name}_{preset}")
            t_grab = time.perf_counter()
            img = renderer.grab(label=f"{shot.name}_{preset}")
            grab_ms = round((time.perf_counter() - t_grab) * 1000, 1)
            path = out / f"{shot.name}_{preset}.png"
            img.save(str(path))
            rows.append({"shot": shot.name, "preset": preset, "file": path.name,
                         "sun_elev": round(sun.elevation, 2), "sun_az": round(sun.azimuth, 2),
                         "sun_date": at.isoformat(),
                         "build_date": models.active_date.isoformat() if models.active_date else None,
                         "settle_ms": round((time.perf_counter() - t0) * 1000, 1),
                         "grab_ms": grab_ms})
            log("shot", name=shot.name, preset=preset, settle_ms=rows[-1]["settle_ms"],
                build_date=rows[-1]["build_date"])
            if fps_seconds > 0 and shot is shots[0]:
                # right after the first shot, on exactly its frame: camera, sun, look
                # and date all belong to it (it used to mix shot 0's camera with
                # the last shot's sun — a frame on no board, senior review)
                fps = round(renderer.measure_fps(fps_seconds), 2)
                metrics.setdefault("fps", {})[preset] = fps
                log("fps", preset=preset, shot=shot.name, fps=fps)
            _write_metrics(out, metrics)
    return rows


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


QT_ERRORS_EXIT = 4  # not 3: the MSVC CRT's abort() also exits with 3 on Windows
_CRASH_LOG: Any = None  # faulthandler's own handle on spike.log, open until the process ends


def _early_error(message: str) -> None:
    """Before spike.log exists there is no log; a windowed exe has no stderr either."""
    if sys.stderr is not None:
        print(f"--spike-q3d: {message}", file=sys.stderr)
    with contextlib.suppress(OSError):
        Path("spike-q3d-error.txt").write_text(message + "\n", encoding="utf-8")


def run_spike_cli(argv: list[str]) -> int:
    """Run the spike; never let a failure go unrecorded (see the module docstring)."""
    global _QT_MESSAGES, _CRASH_LOG
    _isolate_settings()
    try:  # argparse writes to stderr, which a windowed exe does not have
        args = _parse(argv)
        out: Path = args.out
        out.mkdir(parents=True, exist_ok=True)
        log = SpikeLog(out / "spike.log")
    except SystemExit as exc:
        if not exc.code:
            return 0  # --help
        _early_error(f"invalid arguments (exit {exc.code})")
        return 2
    except Exception as exc:  # noqa: BLE001 - nowhere else to report it
        _early_error(f"{type(exc).__name__}: {exc}")
        return 2
    if args.cold:  # before the application exists: Qt reads these on first use
        os.environ.update(COLD_ENV)
    # Every Qt message into the log and metrics.json: a shader that fails to
    # compile only ever printed to stderr, and the frozen exe has none.
    from open_garden_planner.spike_q3d.qt_messages import QtMessages, install, uninstall

    _QT_MESSAGES = QtMessages(log)
    install(_QT_MESSAGES)
    # faulthandler gets its own append handle that is never closed: a crash in the
    # teardown after the run (criterion 10's failure mode) still leaves its stack.
    _CRASH_LOG = (out / "spike.log").open("a", encoding="utf-8")
    faulthandler.enable(file=_CRASH_LOG, all_threads=True)
    if args.watchdog_s > 0:
        faulthandler.dump_traceback_later(args.watchdog_s, exit=True, file=_CRASH_LOG)
    metrics: dict[str, Any] = {"status": "running"}
    code = 0
    try:
        _run(args, out, log, metrics)
        if _QT_MESSAGES.errors:  # the frame on screen is not the frame the QML describes
            metrics["status"] = "qt_errors"
            code = QT_ERRORS_EXIT
            log("qt_errors", n=len(_QT_MESSAGES.errors), first=_QT_MESSAGES.errors[0][:200])
        else:
            metrics["status"] = "ok"
    except Exception as exc:  # evidence tooling: record it, never swallow it silently
        metrics["status"] = "error"
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        log("error", error=metrics["error"])
        log.file.write(traceback.format_exc())
        code = 2
    finally:
        if args.watchdog_s > 0:
            faulthandler.cancel_dump_traceback_later()
        _write_metrics(out, metrics)
        log("done", status=metrics["status"], total_s=metrics.get("total_s"),
            wait_timeouts=metrics.get("wait_timeouts"))
        # Detach the recorder BEFORE the log closes: a Qt message after close()
        # wrote to a closed file inside the handler, which PyQt turns into qFatal.
        uninstall()
        log.close()
    return code


def _run(args: argparse.Namespace, out: Path, log: SpikeLog, metrics: dict[str, Any]) -> None:
    from PyQt6.QtWidgets import QApplication

    t_start = time.perf_counter()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.spike_q3d.quick import SpikeRenderer
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    w_px, h_px = (int(v) for v in args.size.lower().split("x"))
    metrics.update({
        "platform": platform.platform(), "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)), "plan": str(args.plan),
        "host": args.host, "size": [w_px, h_px],
        "env": {k: os.environ.get(k) for k in ("QSG_RHI_BACKEND", "QT_QPA_PLATFORM",
                                                "QSG_RHI_PREFER_SOFTWARE_RENDERER",
                                                "QSG_RENDER_LOOP")},
    })
    from PyQt6.QtCore import QT_VERSION_STR

    metrics["qt"] = QT_VERSION_STR
    log("start", qt=QT_VERSION_STR, frozen=metrics["frozen"], size=args.size,
        presets=args.presets, shots=args.shots, platform=metrics["platform"])
    _validate(args, None)
    # Criterion 5 needs to know what it measured: a first launch (no caches, or
    # --cold) or a warm one. Names only — the cache path holds the user name.
    metrics["shader_caches"] = {
        "cold": bool(args.cold),
        "disabled_by_env": sorted(k for k in COLD_ENV if os.environ.get(k)),
        "found_before_run": _cache_inventory(),
    }
    log("caches", **metrics["shader_caches"])

    scene = CanvasScene()
    pm = ProjectManager()
    t0 = time.perf_counter()
    pm.load(scene, args.plan)
    metrics["load_plan_ms"] = (time.perf_counter() - t0) * 1000
    log("plan_loaded", ms=round(metrics["load_plan_ms"], 1), items=len(scene.items()))
    loc = pm.location or {"latitude": 52.52, "longitude": 13.405}
    lat, lon = float(loc["latitude"]), float(loc["longitude"])
    width, height = scene.width_cm, scene.height_cm

    # Open time starts here: the project is loaded and the user asks for 3D. It
    # ends on the first finished readback (senior review: QML load and the scene
    # build are part of what the user waits through).
    t_open0 = t0 = time.perf_counter()
    ground = bake_ground(scene, width, height)
    metrics["ground_bake_ms"] = (time.perf_counter() - t0) * 1000
    log("ground_baked", ms=round(metrics["ground_bake_ms"], 1), px=f"{ground.width()}x{ground.height()}")

    shots = default_shots(width, height)
    _validate(args, {s.name for s in shots})
    if args.shots != "all":
        wanted = set(args.shots.split(","))
        shots = [s for s in shots if s.name in wanted]
    presets = args.presets.split(",")
    first_when = shots[0].when_utc if shots else datetime.now(UTC)

    models_by_date = ModelsByDate(
        lambda at: build_models(scene, at, args.grass_density, not args.no_grass,
                                location=pm.location))
    t0 = time.perf_counter()
    models = models_by_date.get(first_when.date())
    stats = models_by_date.sets[first_when.date()][1]
    metrics["build_models_ms"] = (time.perf_counter() - t0) * 1000
    metrics["build"] = {"date": first_when.date().isoformat(), "items": stats.items,
                        "models": stats.models, "triangles": stats.triangles,
                        "in_season": stats.in_season,
                        "by_kind_ms": {k: round(v, 1) for k, v in stats.build_ms.items()}}
    log("models_built", ms=round(metrics["build_models_ms"], 1), models=stats.models,
        triangles=stats.triangles, date=first_when.date().isoformat(), in_season=stats.in_season)
    _write_metrics(out, metrics)

    if args.qml_dir is not None:  # every renderer of this run loads from there
        from open_garden_planner.spike_q3d import quick

        quick.QML_DIR = args.qml_dir.resolve()
        metrics["qml_dir"] = str(quick.QML_DIR)
    renderer = SpikeRenderer(args.host, (w_px, h_px), frame_timeout_s=args.frame_timeout_s,
                             log=log)
    log("qml_loaded", ms=round(renderer.qml_load_ms, 1), host=args.host)
    renderer.root.setProperty("allowSsgi", bool(args.ssgi))
    renderer.root.setProperty("allowSsr", not args.no_ssr)
    renderer.set_meadow_albedo(MEADOW_ALBEDO)
    from open_garden_planner.spike_q3d.meshes import WATER_ALBEDO

    renderer.set_water_albedo(WATER_ALBEDO)
    metrics["qml_load_ms"] = renderer.qml_load_ms
    t0 = time.perf_counter()
    models_by_date.activate(renderer, first_when.date())
    renderer.set_ground(ground, 0, 0, width, height)
    metrics["scene_apply_ms"] = (time.perf_counter() - t0) * 1000
    metrics["geometry_upload_ms_total"] = sum(m.geometry.upload_ms for m in models)

    def sun_for(when_utc: datetime) -> Any:
        return sun_state(lat, lon, when_utc)

    renderer.set_preset(presets[0])
    first_sun = sun_for(first_when)
    renderer.set_look(look_for(first_sun))
    renderer.set_sun(first_sun)
    if shots:
        renderer.set_camera(shots[0].eye, shots[0].target, shots[0].fov)
    renderer.show()
    log("shown", exposed=renderer.is_exposed())
    renderer.wait_frames(2, timeout_s=max(args.frame_timeout_s, 300.0), label="first_frame")
    metrics["first_frame_ms"] = renderer.first_frame_ms
    # ``frameSwapped`` marks submission; on a software rasteriser the real cost lands
    # in the next readback (Windows v3: 2 s "first frame", then a 68 s grab). Open
    # time is judged on show -> first finished readback (senior review).
    renderer.grab(label="first_ready")
    metrics["first_ready_ms"] = round((time.perf_counter() - (renderer.shown_at or t_start))
                                      * 1000.0, 1)
    metrics["open_ms"] = round((time.perf_counter() - t_open0) * 1000.0, 1)
    metrics["open_breakdown_ms"] = {
        "ground_bake": round(metrics["ground_bake_ms"], 1),
        "build_models": round(metrics["build_models_ms"], 1),
        "qml_load": round(metrics["qml_load_ms"], 1),
        "scene_apply": round(metrics["scene_apply_ms"], 1),
        "show_to_first_ready": metrics["first_ready_ms"]}
    metrics["graphics_api"] = renderer.graphics_api()
    log("first_frame", ms=round(metrics["first_frame_ms"] or -1.0, 1),
        ready_ms=metrics["first_ready_ms"], open_ms=metrics["open_ms"],
        api=metrics["graphics_api"])
    _write_metrics(out, metrics)
    shoot_board(renderer, shots, presets, models_by_date, sun_for, out, log, metrics,
                args.fps_seconds)
    metrics["builds"] = models_by_date.report()
    _write_metrics(out, metrics)
    if args.iou:
        from open_garden_planner.spike_q3d.probes import shadow_iou_probe

        by_preset: dict[str, Any] = {}
        for preset in presets:
            log("iou_start", preset=preset)
            by_preset[preset] = shadow_iou_probe(renderer, out, preset=preset)
            log("iou_done", preset=preset,
                **{k: v["iou"] for k, v in by_preset[preset]["results"].items()})
        primary = "high" if "high" in by_preset else presets[0]
        # ``shadow_iou`` keeps its shape (one preset's results) for existing readers
        metrics["shadow_iou"] = by_preset[primary]
        metrics["shadow_iou_by_preset"] = by_preset
        _write_metrics(out, metrics)
    if args.orient:
        from open_garden_planner.spike_q3d.probes import orientation_probe

        log("orient_start")
        metrics["orientation"] = orientation_probe(renderer, out, ground, width, height)
        log("orient_done", ground_ok=metrics["orientation"]["ground_texture_ok"],
            sky_ok=metrics["orientation"]["sky_ok"])
        _write_metrics(out, metrics)
    def reload_project() -> list[Any]:
        """File → Open again: the plan from disk into a new scene, a fresh ground
        bake and freshly built models (criterion 10's project reloads)."""
        fresh = CanvasScene()
        fresh_pm = ProjectManager()
        fresh_pm.load(fresh, args.plan)
        renderer.set_ground(bake_ground(fresh, fresh.width_cm, fresh.height_cm), 0, 0,
                            fresh.width_cm, fresh.height_cm)
        models, _stats = build_models(fresh, models_by_date.active_date or first_when.date(),
                                      args.grass_density, not args.no_grass,
                                      location=fresh_pm.location)
        return models

    _measure(args, renderer, scene, ground, width, height, out, log, metrics,
             reload=reload_project)
    metrics["wait_timeouts"] = renderer.wait_timeouts
    if args.soak > 0:  # last: it closes the window and ends the event loop
        from open_garden_planner.spike_q3d import measure

        metrics["soak"].update(measure.close_while_animating(renderer, app, log))
        metrics["wait_timeouts"] = renderer.wait_timeouts  # incl. the animate-then-close wait
        _write_metrics(out, metrics)
    metrics["total_s"] = round(time.perf_counter() - t_start, 2)
    if sys.stdout is not None:
        print(json.dumps({k: metrics[k] for k in ("graphics_api", "open_ms", "build", "fps")
                          if k in metrics}, default=str), flush=True)
    del app
