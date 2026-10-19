"""Render the Beauty Board through the PRODUCTION 3D pipeline (Phase 17 L1.4, #385).

A dev tool for whoever builds or judges anything visible in 3D (``ogp-lush-cinematic``
§5) — not shipped behaviour. It loads a plan, and for every shot renders

    snapshot_records(scene, shot date) -> SceneSync(production_registry()) -> Quick3DSink
        -> Quick3DHost, lit by look_for(sun of that shot, preset)

into a PNG, and writes ``metrics.json`` with the numbers an artifact or a truth gate
is judged by. The sun of every shot is the plan's own (``core/solar`` at the plan's
location and the shot's instant); the models of every shot are built for the shot's
own date.

    venv/Scripts/python.exe scripts/render_beauty_board.py --out <dir> \
        --presets low,high --shots all --iou --orient --horizon --watchdog-s 1800

(Linux: ``QSG_RHI_BACKEND=opengl QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a
-s "-screen 0 1920x1080x24" venv/bin/python scripts/render_beauty_board.py …``.)

Shots (the L0 spike's dates, times and cameras, so that a board of today can be
laid beside an L0 board): ``golden_hour``, ``sunset`` (the 6° golden anchor),
``noon``, ``morning``, ``december_noon``, ``night``, ``walk``.

``metrics.json`` — per shot: sun elevation and azimuth, ``sun_date`` and
``build_date`` (they must be equal), ``isolated_dark_px``, ``clipped_pct``,
``mean_luma``, the frame's Qt message counts and its timings; per run, when asked:

``--iou``      the shadow of a box caster against the analytic 2D shadow at 15° / 35°
               / 60°, in a PERSPECTIVE view WITH the preset's cascades, per preset
``--orient``   is north up and nothing mirrored (a top-down frame against the
               records' own footprints), and does the sky draw its sun at the solar
               azimuth (the disc read 25° off-centre)
``--horizon``  how the fogged meadow meets the sky, per mood and preset
``--moods``    ONE camera and ONE date under the suns of noon, golden hour, sunset and
               night: how dark the night is against the noon of the same shot
``--dusk``     the evening of the golden-hour shot from a 6° sun to a −7° one, one camera:
               the light must fade (luminance never rises) and crossing sunset (0.6° →
               0.4°) is no larger a step than a half degree of the day ramp
``--fence``    the plan's fences alone against the same frame without them, at the noon
               camera, per preset: how the pickets alias (dark share, Laplacian)
``--edge``     an empty plan at golden hour and noon: the luma step where the plan
               rectangle meets the meadow (gate: within 1)
``--fps-seconds N``  frames a SHOWN view presents per second with the wind running,
               per preset — or, where nothing is presented (the display asleep), the
               cost of a finished readback, labelled as such

``--software`` renders on the graphics API's software adapter (WARP on Direct3D), the
workspace's compatibility mode: no sky texture and no light probe, a plain
background and a flat fill. ``--list`` prints the shots with their suns and renders
nothing.

HOW IT RENDERS. Every frame is a host of its own that is never shown
(``quick3d/offscreen.render_records``): nothing a probe does can leak into the next
frame (the spike's ``preserved_state`` lesson, by construction — and checked in
pixels: ``probe_restore_frame_diff`` is the first shot rendered again after the
probes), every frame's Qt messages are recorded, and a QML or shader error fails
the run. The wind is at rest in every frame: its clock is 0. Only ``--fps-seconds``
shows a window.

THE LOG is ``<out>/board.log``, flushed per line, and ``metrics.json`` is rewritten
after every phase; ``--watchdog-s`` dumps every thread's stack into the log and
ends the process (exit code 1). On a software rasteriser one frame can take a long
time: a slow board is not a hung board — read the log. Exit codes: 0 ok · 1
watchdog · 2 an error · 4 Qt reported a shader or QML error.

ISOLATED from the user's own stores (``scripts/script_isolation.py``): loading a plan
writes Recent Files, and outside pytest the settings are the user's.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parent.parent
for _entry in (str(REPO / "src"), str(Path(__file__).resolve().parent)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)   # this checkout's package; the probes beside this file

import script_isolation  # noqa: E402  (before the app is imported)

if __name__ == "__main__":
    script_isolation.isolate_profile()

import board_probes as probes  # noqa: E402  (numpy only)

from open_garden_planner.core.plain_text import log_text  # noqa: E402
from open_garden_planner.core.scene3d import (  # noqa: E402
    GroundSpec,
    Material,
    Params,
    Record,
    SunState,
    Transform,
    pose_ring,
)
from open_garden_planner.core.scene3d.look import (  # noqa: E402
    NEUTRAL_DAY,
    PRESETS,
    LookSpec,
    look_for,
)
from open_garden_planner.core.shadow_geometry import compute_scene_shadows  # noqa: E402
from open_garden_planner.core.solar import solar_position  # noqa: E402

DEFAULT_PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
QT_ERRORS_EXIT = 4
#: The sun a plan without a location gets in the app (FR-SUN-06) — and here.
NO_LOCATION_SUN = SunState(elevation_deg=50.0, azimuth_deg=180.0)


# ── the shots ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BoardShot:
    """One frame of the board: a moment (UTC) and a camera, scene frame (E, N, up)."""

    name: str
    when_utc: datetime
    eye: tuple[float, float, float]
    target: tuple[float, float, float]
    fov_deg: float


def default_shots(width: float, depth: float) -> list[BoardShot]:
    """The board's shots for a plan of ``width`` x ``depth`` cm — the L0 spike's
    (``spike_q3d/runner.default_shots``; pinned against it until the spike retires).
    Times are UTC; the sun is the plan's. ``sunset`` samples the golden anchor
    itself (5.9° on the bench plan); ``golden_hour`` (15.2°) and ``december_noon``
    (14.0°) lie between the golden and the noon rig."""
    cx, cy = width / 2, depth / 2
    diag = math.hypot(width, depth)
    june, december = date(2026, 6, 21), date(2026, 12, 21)

    def utc(day: date, hour: int, minute: int = 0) -> datetime:
        return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)

    south_east = (cx + 0.62 * width, cy - 0.95 * depth, 0.36 * diag)
    hero = (cx + 0.55 * width, cy - 0.78 * depth, 0.17 * diag)
    hero_target = (cx - 0.08 * width, cy + 0.1 * depth, 160.0)
    south_west = (cx - 0.62 * width, cy - 0.95 * depth, 0.40 * diag)
    return [
        BoardShot("golden_hour", utc(june, 17, 30), hero, hero_target, 46.0),
        BoardShot("sunset", utc(june, 18, 38), hero, hero_target, 46.0),
        BoardShot("noon", utc(june, 11), south_west, (cx + 0.04 * width, cy, 40.0), 42.0),
        BoardShot("morning", utc(june, 6), (cx - 0.85 * width, cy - 0.35 * depth, 0.22 * diag),
                  (cx + 0.1 * width, cy, 60.0), 44.0),
        BoardShot("december_noon", utc(december, 11), south_east, (cx, cy, 40.0), 42.0),
        BoardShot("night", utc(june, 21, 30), south_east, (cx, cy, 40.0), 42.0),
        BoardShot("walk", utc(june, 14, 30), (cx - 0.21 * width, cy + 0.03 * depth, 165.0),
                  (cx + 0.35 * width, cy - 0.35 * depth, 70.0), 62.0),
    ]


# ── the probes' own scenes (plain data) ──────────────────────────────────────

#: The box caster of the shadow gate: the spike's (100 x 100 x 200 cm), sun azimuth 225°.
CASTER_SIDE, CASTER_HEIGHT, IOU_AZIMUTH = 100.0, 200.0, 225.0
IOU_ELEVATIONS = (15.0, 35.0, 60.0)
#: A plan rectangle around the caster, large enough for the 15° shadow (7.5 m).
IOU_GROUND = GroundSpec(4000.0, 4000.0)
IOU_CENTRE = (1600.0, 1600.0)
CASTER_TINT = (208, 16, 16, 255)
#: The sky views of the azimuth probe: the sun 12° up, looked at 25° to its left and
#: right (a disc in the middle of the frame only proves the direction), pitched up 14°.
SKY_SUN_ELEVATION, SKY_PITCH_DEG, SKY_FOV_DEG = 12.0, 14.0, 70.0
SKY_OFFSETS_DEG = (-25.0, 25.0)
SKY_AZIMUTHS = (90.0, 180.0, 270.0)
SKY_MAX_ERROR_DEG = 6.0
#: The moods the horizon probe looks at, by the name of the shot whose sun it uses.
HORIZON_SHOTS = ("noon", "golden_hour", "sunset", "night")


def caster_footprint() -> list[tuple[float, float]]:
    half, (east, north) = CASTER_SIDE / 2.0, IOU_CENTRE
    return [(east - half, north - half), (east + half, north - half),
            (east + half, north + half), (east - half, north + half)]


def caster_record() -> Record:
    half = CASTER_SIDE / 2.0
    ring = ((-half, -half), (half, -half), (half, half), (-half, half))
    return Record(item_id="caster", kind="SHED", shape="rectangle", footprints=(ring,),
                  transform=Transform(east_cm=IOU_CENTRE[0], north_cm=IOU_CENTRE[1]),
                  material=Material("SHED", fill_rgba=CASTER_TINT), height_cm=CASTER_HEIGHT,
                  params=Params({"seed": "caster"}))


def iou_camera(elevation: float, size: tuple[int, int]) -> probes.Pinhole:
    """A camera that sees the caster and the whole of its shadow from the side: the
    shadow falls north-east, the camera stands south-east of its middle."""
    reach = CASTER_HEIGHT / math.tan(math.radians(elevation)) * math.sin(math.radians(45.0))
    middle = (IOU_CENTRE[0] + reach / 2.0, IOU_CENTRE[1] + reach / 2.0)
    span = max(reach * math.sqrt(2.0) + 2.0 * CASTER_SIDE, 500.0)
    back = span * 1.15
    return probes.Pinhole(eye=(middle[0] + back * 0.75, middle[1] - back * 0.75, back * 0.8),
                          target=(middle[0], middle[1], 0.0), fov_deg=40.0, size=size)


def plan_day(when_utc: datetime) -> date:
    """The plan's day of an instant: the LOCAL calendar day, as the app's sim clock
    reads it (ADR-053: ``tz=None`` = the system zone) — never the UTC date."""
    return when_utc.astimezone().date()


def records_digest(records: dict[str, Record]) -> str:
    """A short digest of (item id, height) over a snapshot: two plan dates that grow
    the plants differently give two digests — a board that rendered one date's
    models for another cannot hide behind equal date strings."""
    rows = sorted((item_id, None if record.height_cm is None else round(float(record.height_cm), 2))
                  for item_id, record in records.items())
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()[:16]


#: The dusk probe's sun elevations, high to low: the day ramp in half degrees down to
#: 0.6°, sunset's crossing to 0.4°, then civil twilight to past its end.
DUSK_ELEVATIONS = (6.0, 3.1, 2.6, 2.1, 1.6, 1.1, 0.6, 0.4, 0.0, -1.0, -2.0, -3.0, -4.0, -5.0,
                   -6.0, -7.0)
#: The edge probe's cameras stand on the edge's line this far from the middle of the
#: judged stretch, at eye height — the grazing view under which a sheen shows — and judge
#: a band this wide on each side of the edge, starting this far from it, this long.
EDGE_BACK_CM, EDGE_EYE_CM, EDGE_BAND_CM, EDGE_HALF_WIDTH_CM, EDGE_INSET_CM = (
    1500.0, 165.0, 200.0, 300.0, 20.0)


# ── the run ──────────────────────────────────────────────────────────────────


class Board:
    """One run: the plan, the engine, the output directory."""

    def __init__(self, args: argparse.Namespace, out: Path, log: Any, metrics: dict[str, Any]) -> None:
        self.args, self.out, self.log, self.metrics = args, out, log, metrics
        self.size = tuple(int(v) for v in str(args.size).lower().split("x"))
        self.software = bool(args.software)
        self.qt_counts: dict[str, int] = {}
        self.qt_errors: list[str] = []
        self.qt_warnings: list[str] = []
        self._records: dict[date, dict[str, Record]] = {}
        #: The day each snapshot was taken for, by the identity of the records it made:
        #: a row's ``build_date`` is read back from the records actually rendered.
        self._snapshot_day: dict[int, date] = {}
        self.scene: Any = None
        self.location: dict[str, Any] | None = None

    def write(self) -> None:
        self.metrics["qt_messages"] = {"counts": dict(self.qt_counts), "errors": self.qt_errors[:30],
                                       "warnings": self.qt_warnings[:30]}
        if not self.args.list:       # --list renders nothing and leaves nothing behind
            (self.out / "metrics.json").write_text(
                json.dumps(self.metrics, indent=2, default=str), encoding="utf-8")

    # ── the plan ─────────────────────────────────────────────────────────────

    def load(self) -> None:
        from open_garden_planner.core import ProjectManager
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        started = time.perf_counter()
        self.scene = CanvasScene()
        manager = ProjectManager()
        manager.load(self.scene, self.args.plan)
        location = manager.location if isinstance(manager.location, dict) else None
        if location is not None and (location.get("latitude") is None
                                     or location.get("longitude") is None):
            location = None
        self.location = location
        self.width, self.depth = float(self.scene.width_cm), float(self.scene.height_cm)
        self.metrics.update({
            "plan": log_text(self.args.plan.name), "plan_size_cm": [self.width, self.depth],
            "location": ({"latitude": float(location["latitude"]),
                          "longitude": float(location["longitude"])} if location else None),
            "load_plan_ms": round((time.perf_counter() - started) * 1000.0, 1)})
        self.log("plan_loaded", plan=log_text(self.args.plan.name), items=len(self.scene.items()),
                 ms=self.metrics["load_plan_ms"], location=bool(location))

    def sun_at(self, when_utc: datetime) -> SunState:
        """The plan's own sun at an instant — ``core/solar``; without a location the
        app's documented fallback (the same sun for every shot: said in ``metrics``)."""
        if self.location is None:
            return NO_LOCATION_SUN
        return SunState.from_solar_position(solar_position(
            float(self.location["latitude"]), float(self.location["longitude"]), when_utc))

    def records_for(self, at: date) -> dict[str, Record]:
        """The plan as it stands on ``at`` — snapshotted once per date."""
        if at not in self._records:
            from open_garden_planner.ui.view3d.snapshot import snapshot_records

            started = time.perf_counter()
            skipped: list[Any] = []
            self._records[at] = snapshot_records(self.scene, at, skipped=skipped)
            self._snapshot_day[id(self._records[at])] = at
            self.metrics.setdefault("builds", {})[at.isoformat()] = {
                "records": len(self._records[at]), "skipped": len(skipped),
                "snapshot_ms": round((time.perf_counter() - started) * 1000.0, 1),
                "digest": records_digest(self._records[at])}
            self.log("records", date=at.isoformat(), records=len(self._records[at]),
                     skipped=len(skipped))
        return self._records[at]

    def snapshot_day(self, records: dict[str, Record]) -> date:
        """The plan date the given records were snapshotted for."""
        return self._snapshot_day[id(records)]

    # ── one frame ────────────────────────────────────────────────────────────

    def frame(self, name: str, records: dict[str, Record], *, shot: Any, sun: SunState | None,
              look: LookSpec, ground: GroundSpec | None, registry: Any = None,
              sky: bool = True, size: tuple[int, int] | None = None) -> tuple[np.ndarray, Any, dict[str, Any]]:
        """Render one frame in a host of its own, save it, account for its Qt messages."""
        from open_garden_planner.ui.view3d.quick3d.offscreen import RenderError, render_records

        try:
            frame = render_records(
                records, shot=shot, sun=sun, ground=ground, size=size or self.size,
                registry=registry, look=look, qml_dir=self.args.qml_dir, log=self.log,
                graphics_info=True, sky_light=sky and not self.software,
                prefer_software=self.software)
        except RenderError as error:
            self._count(dict(error.qt))
            self.write()             # what Qt said is in metrics.json before the run ends
            raise
        self._count(dict(frame.qt))
        path = self.out / f"{name}.png"
        if not frame.image.save(str(path)):
            raise RuntimeError(f"could not write {path.name}")
        rgb = frame.rgba()[..., :3].astype(np.float64)
        info = {"file": path.name, "px": [frame.image.width(), frame.image.height()],
                "dpr": frame.device_pixel_ratio, "open_ms": round(frame.open_ms, 1),
                "breakdown_ms": {key: round(value, 1) for key, value in frame.breakdown_ms.items()},
                "items": frame.items, "parts": frame.parts,
                "build_failures": sorted(frame.build_failures), "sky_builds": frame.sky_builds,
                "qt": dict(frame.qt.get("counts", {}))}
        self.metrics.setdefault("graphics", {"api": frame.graphics_api, "adapter": frame.adapter})
        return rgb, frame, info

    def _count(self, report: dict[str, Any]) -> None:
        for name, count in dict(report.get("counts", {})).items():
            self.qt_counts[name] = self.qt_counts.get(name, 0) + int(count)
        self.qt_errors += [str(line) for line in report.get("errors", [])]
        self.qt_warnings += [str(line) for line in report.get("warnings", [])]

    def plan_ground(self) -> GroundSpec:
        # THE GROUND BAKE (L1.5) JOINS HERE. Until its baker is on this branch the board
        # shows the plan rectangle bare (one meadow albedo); with it, this is the one
        # line that hands the pipeline the baked surfaces — the lawn, the terrace, the
        # paths and the beds painted from the records.
        return GroundSpec(self.width, self.depth)

    # ── the shots ────────────────────────────────────────────────────────────

    def shoot(self, shots: list[BoardShot], presets: list[str]) -> None:
        from open_garden_planner.core.scene3d.builders import production_registry
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        registry = production_registry()
        rows: list[dict[str, Any]] = []
        self.metrics["shots"] = rows
        for preset in presets:
            for shot in shots:
                at = plan_day(shot.when_utc)         # the plan's LOCAL day (ADR-053)
                records = self.records_for(at)
                sun = self.sun_at(shot.when_utc)
                look = look_for(sun, preset)
                rgb, _frame, info = self.frame(
                    f"{shot.name}_{preset}", records, sun=sun, look=look, ground=self.plan_ground(),
                    registry=registry, shot=PerspectiveShot(shot.eye, shot.target, shot.fov_deg))
                row = {"shot": shot.name, "preset": preset, "sun_elev": round(sun.elevation_deg, 2),
                       "sun_az": round(sun.azimuth_deg, 2),
                       "sun_date": plan_day(shot.when_utc).isoformat(),
                       "build_date": self.snapshot_day(records).isoformat(), "night": look.night,
                       "exposure": round(look.mood.exposure, 3), "sun_color": look.mood.sun_color,
                       **info, **probes.frame_stats(rgb)}
                rows.append(row)
                self.log("shot", name=shot.name, preset=preset, ms=row["open_ms"],
                         luma=row["mean_luma"], dark_px=row["isolated_dark_px"],
                         clipped_pct=row["clipped_pct"], failures=len(row["build_failures"]))
                self.write()

    def mood_strip(self, shots: list[BoardShot], presets: list[str]) -> None:
        """ONE camera and ONE date through the day's moods (gate G3): the hero camera,
        the plan as it stands on the day of the ``noon`` shot, lit by the suns of the
        noon, golden-hour, sunset and night shots. Night against noon on the same
        shot and plan — and nothing but the light differs between the frames."""
        from open_garden_planner.core.scene3d.builders import production_registry
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        by_name = {shot.name: shot for shot in shots}
        camera = by_name["golden_hour"]
        at = plan_day(by_name["noon"].when_utc)
        records, registry = self.records_for(at), production_registry()
        out: dict[str, Any] = {}
        self.metrics["moods"] = out
        for preset in presets:
            rows: dict[str, Any] = {}
            for mood in HORIZON_SHOTS:
                when = by_name[mood].when_utc.replace(year=at.year, month=at.month, day=at.day)
                sun = self.sun_at(when)
                look = look_for(sun, preset)
                rgb, _frame, info = self.frame(
                    f"mood_{mood}_{preset}", records, sun=sun, look=look, ground=self.plan_ground(),
                    registry=registry, shot=PerspectiveShot(camera.eye, camera.target, camera.fov_deg))
                rows[mood] = {"sun_elev": round(sun.elevation_deg, 2), "night": look.night,
                              "file": info["file"], **probes.frame_stats(rgb)}
            noon, night = rows["noon"], rows["night"]
            rows["night_over_noon"] = {
                "luminance": round(night["mean_luminance"] / noon["mean_luminance"], 4),
                "luma": round(night["mean_luma"] / noon["mean_luma"], 4)}
            out[preset] = rows
            self.log("moods", preset=preset, **rows["night_over_noon"])
            self.write()

    # ── truth probes ─────────────────────────────────────────────────────────

    def shadow_iou(self, presets: list[str]) -> None:
        """Gate G2: perspective, the preset's own cascades, map, filter and bias."""
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        records = {"caster": caster_record()}
        footprint = caster_footprint()
        by_preset: dict[str, Any] = {}
        self.metrics["shadow_iou"] = by_preset
        for preset in presets:
            results: dict[str, Any] = {}
            for elevation in IOU_ELEVATIONS:
                sun = SunState(elevation, IOU_AZIMUTH)
                camera = iou_camera(elevation, self.size)
                name = f"iou_{int(elevation)}_{preset}"
                rgb, _frame, info = self.frame(
                    name, records, sun=sun, look=look_for(sun, preset), ground=IOU_GROUND,
                    shot=PerspectiveShot(camera.eye, camera.target, camera.fov_deg))
                reach = CASTER_HEIGHT / math.tan(math.radians(elevation))
                east, north = IOU_CENTRE
                result = probes.shadow_iou(
                    rgb, camera, footprint, CASTER_HEIGHT,
                    compute_scene_shadows([(footprint, CASTER_HEIGHT)], elevation, IOU_AZIMUTH),
                    region=(east - 200.0, north - 200.0, east + reach + 200.0, north + reach + 200.0),
                    lit_reference=(east - 190.0, north - 190.0, east - 90.0, north - 90.0))
                result.update(file=info["file"], cascades=look_for(sun, preset).shadow.cascades)
                results[f"{int(elevation)}deg"] = result
                self.log("iou", preset=preset, elevation=elevation, iou=result["iou"])
            by_preset[preset] = {"azimuth_deg": IOU_AZIMUTH, "view": "perspective",
                                 "caster_cm": [CASTER_SIDE, CASTER_SIDE, CASTER_HEIGHT],
                                 "results": results}
            self.write()

    def orientation(self, at: date) -> None:
        """North is up and nothing is mirrored: a top-down frame of the plan against the
        records' own footprints, projected with OUR arithmetic."""
        from open_garden_planner.core.scene3d.builders import production_registry
        from open_garden_planner.ui.view3d.quick3d.shots import TopDownShot, top_down_pixel

        records = self.records_for(at)
        width, height = self.size
        shot = TopDownShot(center=(self.width / 2.0, self.depth / 2.0),
                           px_per_cm=min(width / self.width, height / self.depth) * 0.9)
        high = SunState(80.0, 180.0)
        look = look_for(high, "high")
        plan, _frame, info = self.frame("orient_plan_topdown", records, shot=shot, sun=high, look=look,
                                        ground=self.plan_ground(), registry=production_registry(),
                                        sky=False)
        bare, _frame, _info = self.frame("orient_bare_topdown", {}, shot=shot, sun=high, look=look,
                                         ground=self.plan_ground(), sky=False)
        seen = np.abs(plan - bare).max(axis=2) > 12.0
        rows, cols = seen.shape
        ratio = cols / width
        xs, ys = np.meshgrid(np.arange(cols) + 0.5, np.arange(rows) + 0.5)
        predicted = np.zeros(seen.shape, dtype=bool)
        solids = 0
        for record in records.values():
            if record.height_cm is None:
                continue                     # a flat surface is the ground's (the bake's)
            solids += 1
            for ring in record.footprints:
                pixels = [top_down_pixel(east, north, shot, (cols, rows), ratio)
                          for east, north in pose_ring(record.transform, ring)]
                predicted |= probes.polygon_mask(xs, ys, pixels)
        result = probes.orientation_scores(seen, predicted)
        result.update(file=info["file"], solids=solids, seen_px=int(seen.sum()),
                      predicted_px=int(predicted.sum()))
        self.metrics["orientation"] = result
        self.log("orientation", ok=result["ok"], **result["ncc"])
        self.write()

    def sky_azimuth(self) -> None:
        """Gate G4: the sky draws its sun at the solar azimuth."""
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        if self.software:
            self.metrics["sky"] = {"skipped": "no sky texture on a software adapter"}
            return
        views: dict[str, Any] = {}
        errors: list[float | None] = []
        for azimuth in SKY_AZIMUTHS:
            sun = SunState(SKY_SUN_ELEVATION, azimuth)
            for offset in SKY_OFFSETS_DEG:
                bearing = math.radians(azimuth + offset)
                camera = probes.Pinhole(
                    eye=(0.0, 0.0, 160.0),
                    target=(math.sin(bearing) * 1000.0, math.cos(bearing) * 1000.0,
                            160.0 + 1000.0 * math.tan(math.radians(SKY_PITCH_DEG))),
                    fov_deg=SKY_FOV_DEG, size=self.size)
                name = f"sky_{int(azimuth)}_{offset:+.0f}"
                rgb, _frame, _info = self.frame(
                    name, {}, sun=sun, look=look_for(sun, "low"), ground=None,
                    shot=PerspectiveShot(camera.eye, camera.target, camera.fov_deg))
                found = probes.sun_disc(rgb, camera)
                if found["found"]:
                    found["error_deg"] = round(probes.bearing_error_deg(found["bearing_deg"], azimuth), 2)
                errors.append(found.get("error_deg"))
                views[name] = found
        known = [abs(error) for error in errors if error is not None]
        self.metrics["sky"] = {
            "views": views, "offsets_deg": list(SKY_OFFSETS_DEG),
            "max_abs_error_deg": round(max(known), 2) if known else None,
            "ok": len(known) == len(errors) and bool(known) and max(known) < SKY_MAX_ERROR_DEG}
        self.log("sky", ok=self.metrics["sky"]["ok"], max_error=self.metrics["sky"]["max_abs_error_deg"])
        self.write()

    def horizon(self, shots: list[BoardShot], presets: list[str]) -> None:
        """Gate G5: the fogged meadow meets the sky — per mood, per preset, looking away
        from the sun and across it (the sun itself is never in the bands)."""
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        by_name = {shot.name: shot for shot in shots}
        out: dict[str, Any] = {}
        self.metrics["horizon"] = out
        worst = {"step": 0.0, "dip": 0.0, "ridge": 0.0}
        for preset in presets:
            out[preset] = {}
            for mood in HORIZON_SHOTS:
                if mood not in by_name:
                    continue
                sun = self.sun_at(by_name[mood].when_utc)
                row: dict[str, Any] = {}
                for label, turn in (("away", 180.0), ("across", 90.0)):
                    bearing = math.radians(sun.azimuth_deg + turn)
                    camera = probes.Pinhole(
                        eye=(self.width / 2.0, self.depth / 2.0, 165.0),
                        target=(self.width / 2.0 + math.sin(bearing) * 1000.0,
                                self.depth / 2.0 + math.cos(bearing) * 1000.0, 165.0),
                        fov_deg=40.0, size=self.size)
                    rgb, _frame, info = self.frame(
                        f"horizon_{mood}_{label}_{preset}", {}, sun=sun, look=look_for(sun, preset),
                        ground=self.plan_ground(),
                        shot=PerspectiveShot(camera.eye, camera.target, camera.fov_deg))
                    row[label] = {**probes.horizon_step(rgb, camera), "file": info["file"]}
                    for key in worst:
                        worst[key] = max(worst[key], row[label][key])
                out[preset][mood] = row
                self.log("horizon", preset=preset, mood=mood,
                         **{f"{label}_{key}": row[label][key] for label in row for key in worst})
            self.write()
        out["max"] = {key: round(value, 2) for key, value in worst.items()}
        self.write()

    def dusk(self, shots: list[BoardShot], presets: list[str]) -> None:
        """Day into night on ONE camera and ONE date (the golden-hour shot's): the plan's
        own suns of that evening, found by elevation (``DUSK_ELEVATIONS``). The light
        must fade — the mean luminance never rises from 6° to −7° — and crossing sunset
        (0.6° → 0.4°, where the key light leaves as the 2D shadows do) is no larger a
        step than the largest half degree of the day ramp before it (6° … 0.6°)."""
        from open_garden_planner.core.scene3d.builders import production_registry
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        camera = {shot.name: shot for shot in shots}["golden_hour"]
        day = plan_day(camera.when_utc)
        records, registry = self.records_for(day), production_registry()
        found: dict[float, tuple[datetime, SunState]] = {}
        moment = camera.when_utc.replace(hour=15, minute=0)
        end = moment + timedelta(hours=8)
        while moment < end and len(found) < len(DUSK_ELEVATIONS):
            sun = self.sun_at(moment)
            for target in DUSK_ELEVATIONS:
                if target not in found and sun.elevation_deg <= target:
                    found[target] = (moment, sun)
            moment += timedelta(seconds=20)
        out: dict[str, Any] = {}
        self.metrics["dusk"] = out
        for preset in presets:
            rows = []
            for target in DUSK_ELEVATIONS:
                if target not in found:
                    continue
                moment, sun = found[target]
                look = look_for(sun, preset)
                rgb, _frame, info = self.frame(
                    f"dusk_{target:+.1f}_{preset}", records, sun=sun, look=look,
                    ground=self.plan_ground(), registry=registry,
                    shot=PerspectiveShot(camera.eye, camera.target, camera.fov_deg))
                rows.append({"target": target, "utc": moment.isoformat(),
                             "sun_elev": round(sun.elevation_deg, 3), "twilight": round(look.mood.twilight, 4),
                             "night": look.night, "exposure": round(look.mood.exposure, 4),
                             "key_brightness": round(look.mood.sun_brightness, 4),
                             "file": info["file"], **probes.frame_stats(rgb)})
            lums = [row["mean_luminance"] for row in rows]
            # a rise beyond the frames' own noise (two renders of one light differ by
            # up to 1e-5 in mean luminance: the night rows of the first measurement)
            rises = [round(after - before, 5) for before, after in zip(lums, lums[1:], strict=False)
                     if after > before * 1.002 + 1e-5]
            by_target = {row["target"]: row["mean_luminance"] for row in rows}
            day_ramp = [target for target in DUSK_ELEVATIONS if target >= 0.6]
            day_steps = [abs(by_target[a] - by_target[b])
                         for a, b in zip(day_ramp, day_ramp[1:], strict=False)
                         if a in by_target and b in by_target]
            crossing = (abs(by_target[0.6] - by_target[0.4])
                        if 0.6 in by_target and 0.4 in by_target else None)
            out[preset] = {"rows": rows, "rises": rises,
                           "monotone": not rises,
                           "day_ramp_max_step": round(max(day_steps), 5) if day_steps else None,
                           "sunset_step": None if crossing is None else round(crossing, 5)}
            self.log("dusk", preset=preset, monotone=not rises, sunset_step=out[preset]["sunset_step"],
                     day_ramp_max_step=out[preset]["day_ramp_max_step"])
            self.write()

    def fence_moire(self, shots: list[BoardShot], presets: list[str]) -> None:
        """How the plan's fences alias, per preset: the fences alone at the noon camera
        against the same frame without them (``probes.thin_geometry_moire``)."""
        from open_garden_planner.core.scene3d.builders import production_registry
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        camera = {shot.name: shot for shot in shots}["noon"]
        records = self.records_for(plan_day(camera.when_utc))
        fences = {key: record for key, record in records.items() if record.kind == "FENCE"}
        sun = self.sun_at(camera.when_utc)
        shot = PerspectiveShot(camera.eye, camera.target, camera.fov_deg)
        out: dict[str, Any] = {"fences": len(fences)}
        self.metrics["fence_moire"] = out
        if not fences:
            return
        registry = production_registry()
        for preset in presets:
            look = look_for(sun, preset)
            with_them, _frame, info = self.frame(f"fence_{preset}", fences, sun=sun, look=look,
                                                 ground=self.plan_ground(), registry=registry,
                                                 shot=shot)
            without, _frame, _info = self.frame(f"fence_empty_{preset}", {}, sun=sun, look=look,
                                                ground=self.plan_ground(), shot=shot)
            large, _frame, _info = self.frame(f"fence_2x_{preset}", fences, sun=sun, look=look,
                                              ground=self.plan_ground(), registry=registry, shot=shot,
                                              size=(2 * self.size[0], 2 * self.size[1]))
            reference = probes.downsample(large, 2) if large.shape[0] == 2 * with_them.shape[0] else None
            out[preset] = {**probes.thin_geometry_moire(with_them, without, reference),
                           "file": info["file"]}
            self.log("fence_moire", preset=preset, **{k: v for k, v in out[preset].items()
                                                      if k != "file"})
            self.write()

    def plan_edge(self, shots: list[BoardShot], presets: list[str]) -> None:
        """The plan rectangle against the meadow on a plan with nothing on it: the luma
        step across its west and its south edge at golden hour and at noon, per preset.

        Each edge is seen at eye height ALONG the edge, from both ends (the plan then
        lies left in one view and right in the other, the sun on the other side), and
        the step is measured AT the edge line (``probes.plan_edge_step``: both sides
        fitted, compared at the edge — a smooth gradient across the view is not a step).
        The gate's number is the largest step of any view (``max_abs_step``): a sheen
        that differs makes the plan darker looking one way and brighter looking the
        other (the old material: -4.1 and +4.3 along the south edge at golden hour),
        and a mean of the two would hide it."""
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        by_name = {shot.name: shot for shot in shots}
        mid_e, mid_n = self.width / 2.0, self.depth / 2.0
        back, half = EDGE_BACK_CM, EDGE_HALF_WIDTH_CM
        reach = (EDGE_INSET_CM, EDGE_INSET_CM + EDGE_BAND_CM)
        west_along = [mid_n + k * half / 2.0 for k in (-2, -1, 0, 1, 2)]
        south_along = [mid_e + k * half / 2.0 for k in (-2, -1, 0, 1, 2)]
        views = {   # name: (eye, target, axis of the edge line, stations along it)
            "west_looking_north": ((0.0, mid_n - back, EDGE_EYE_CM), (0.0, mid_n, 0.0),
                                   "east", west_along),
            "west_looking_south": ((0.0, mid_n + back, EDGE_EYE_CM), (0.0, mid_n, 0.0),
                                   "east", west_along),
            "south_looking_east": ((mid_e - back, 0.0, EDGE_EYE_CM), (mid_e, 0.0, 0.0),
                                   "north", south_along),
            "south_looking_west": ((mid_e + back, 0.0, EDGE_EYE_CM), (mid_e, 0.0, 0.0),
                                   "north", south_along),
        }
        out: dict[str, Any] = {}
        self.metrics["plan_edge"] = out
        worst = 0.0
        for preset in presets:
            out[preset] = {}
            for mood in ("golden_hour", "noon"):
                sun = self.sun_at(by_name[mood].when_utc)
                rows: dict[str, Any] = {}
                for name, (eye, target, axis, along) in views.items():
                    camera = probes.Pinhole(eye=eye, target=target, fov_deg=40.0, size=self.size)
                    rgb, _frame, info = self.frame(
                        f"edge_{mood}_{name}_{preset}", {}, sun=sun, look=look_for(sun, preset),
                        ground=self.plan_ground(),
                        shot=PerspectiveShot(camera.eye, camera.target, camera.fov_deg))
                    rows[name] = {**probes.plan_edge_step(rgb, camera, axis=axis, at=0.0,
                                                          along=along, reach=reach),
                                  "file": info["file"]}
                for row in rows.values():
                    worst = max(worst, abs(row["step"]) if row["step"] is not None else math.inf)
                out[preset][mood] = rows
                self.log("plan_edge", preset=preset, mood=mood,
                         **{name: row["step"] for name, row in rows.items()})
            self.write()
        out["max_abs_step"] = round(worst, 2)
        self.write()

    def restore_check(self, shot: BoardShot, preset: str) -> None:
        """The first shot again, after every probe: the same picture, to the pixel."""
        from PyQt6.QtGui import QImage

        from open_garden_planner.core.scene3d.builders import production_registry
        from open_garden_planner.ui.view3d.quick3d.offscreen import image_rgba
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        first = QImage(str(self.out / f"{shot.name}_{preset}.png"))
        sun = self.sun_at(shot.when_utc)
        again, _frame, _info = self.frame(
            "probes_restored", self.records_for(plan_day(shot.when_utc)), sun=sun,
            look=look_for(sun, preset), ground=self.plan_ground(), registry=production_registry(),
            shot=PerspectiveShot(shot.eye, shot.target, shot.fov_deg))
        before = image_rgba(first)[..., :3].astype(np.float64)
        same = before.shape == again.shape
        self.metrics["probe_restore_frame_diff"] = (
            round(float(np.abs(before - again).mean()), 4) if same else None)
        self.log("probes_restored", frame_diff=self.metrics["probe_restore_frame_diff"])
        self.write()

    # ── frame rate (a SHOWN window) ──────────────────────────────────────────

    def frame_rate(self, shot: BoardShot, presets: list[str], seconds: float) -> None:
        """Gate G9. Frames a shown view PRESENTS per second while the wind animates —
        counted by the host from Qt's own frame signal, never by reading frames back.
        Where nothing is presented (the display asleep) the cost of a finished
        readback is reported instead, and labelled as that."""
        from PyQt6.QtCore import QCoreApplication

        from open_garden_planner.core.scene3d import SceneSync
        from open_garden_planner.core.scene3d.builders import production_registry
        from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
        from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

        def pump(duration_s: float) -> None:
            end = time.perf_counter() + duration_s
            while time.perf_counter() < end:
                QCoreApplication.processEvents()
                time.sleep(0.001)

        def readback_cost(shot: BoardShot, count: int = 12) -> tuple[float, float]:
            """The median and the largest time of a finished readback of a NEW frame.
            A readback of an unchanged scene re-composites the last 3D frame (measured:
            ~6 ms on WARP where a frame takes 100-350 ms; the wind's clock does not advance
            across a readback), so the camera moves by 0.01 cm before each one — no
            picture is kept."""
            costs = []
            for index in range(count):
                east, north, up = shot.eye
                host.set_camera((east + 0.01 * (index % 2), north, up), shot.target, shot.fov_deg)
                t0 = time.perf_counter()
                host.grab("frame_cost")
                costs.append((time.perf_counter() - t0) * 1000.0)
            host.set_camera(shot.eye, shot.target, shot.fov_deg)
            return round(statistics.median(costs), 2), round(max(costs), 2)

        sun = self.sun_at(shot.when_utc)
        records = self.records_for(plan_day(shot.when_utc))
        host = Quick3DHost(self.size, qml_dir=self.args.qml_dir, log=self.log,
                           prefer_software=self.software)
        table: dict[str, Any] = {}
        self.metrics["frame_rate"] = {"shot": shot.name, "seconds": seconds, "size": list(self.size),
                                      "software": self.software, "presets": table}
        try:
            sync = SceneSync(Quick3DSink(host), production_registry())
            sync.apply(records, sun=sun, ground=self.plan_ground())
            host.set_camera(shot.eye, shot.target, shot.fov_deg)
            host.set_look(look_for(sun, presets[0]))
            if not self.software:
                host.set_sky(look_for(sun, presets[0]).sky)
            host.show()
            ready = host.wait_ready(30.0)
            for preset in presets:
                host.set_look(look_for(sun, preset))
                pump(0.5)                    # the preset's own shaders and targets
                host.set_wind_running(True)
                pump(0.3)
                frames, started = host.health().frames_presented, time.perf_counter()
                pump(seconds)
                presented = host.health().frames_presented - frames
                elapsed = time.perf_counter() - started
                row: dict[str, Any] = {
                    "frames_presented": presented,
                    "presented_fps": round(presented / elapsed, 2) if presented >= 2 else None}
                host.rest_wind()
                if ready:                    # a finished readback: what one frame COSTS
                    row["readback_ms_median"], row["readback_ms_max"] = readback_cost(shot)
                table[preset] = row
                self.log("frame_rate", preset=preset, **row)
                self.write()
            health = host.health()
            self.metrics["frame_rate"]["qml_warnings"] = list(health.qml_warnings)
            self.metrics["frame_rate"]["ready"] = bool(ready)
        finally:
            host.close()
            pump(0.1)
        self.write()


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="render_beauty_board.py", allow_abbrev=False,
                                     description="Render the 3D Beauty Board through the "
                                                 "production pipeline.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, default=Path.cwd() / "beauty_board_out")
    parser.add_argument("--presets", default="high")
    parser.add_argument("--shots", default="all")
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--iou", action="store_true", help="shadow IoU, perspective with cascades")
    parser.add_argument("--orient", action="store_true", help="north-up and the sky's sun azimuth")
    parser.add_argument("--horizon", action="store_true", help="how fog meets sky, per mood")
    parser.add_argument("--moods", action="store_true",
                        help="one camera and one date through noon, golden hour, sunset and night")
    parser.add_argument("--dusk", action="store_true",
                        help="the evening from 6 to -7 degrees on one camera: the light must fade")
    parser.add_argument("--fence", action="store_true",
                        help="the plan's fences alone at the noon camera: how they alias, per preset")
    parser.add_argument("--edge", action="store_true",
                        help="an empty plan: the step where the plan rectangle meets the meadow")
    parser.add_argument("--fps-seconds", type=float, default=0.0,
                        help="frames a SHOWN window presents per second, per preset (0 = off)")
    parser.add_argument("--software", action="store_true",
                        help="the software adapter (WARP): no sky texture, as compatibility mode")
    parser.add_argument("--qml-dir", type=Path, default=None,
                        help="load Garden.qml and its shaders from this folder (positive controls)")
    parser.add_argument("--watchdog-s", type=float, default=1800.0,
                        help="dump all stacks to board.log and exit 1 after this long (0 = off)")
    parser.add_argument("--list", action="store_true", help="print the shots and render nothing")
    return parser.parse_args(argv)   # a typo is an error, never another experiment


def _chosen(args: argparse.Namespace, shots: list[BoardShot]) -> tuple[list[BoardShot], list[str]]:
    presets = [name for name in str(args.presets).split(",") if name]
    bad = [name for name in presets if name not in PRESETS]
    if bad or not presets:
        raise ValueError(f"unknown presets {bad}; choose from {list(PRESETS)}")
    if args.shots != "all":
        wanted = [name for name in str(args.shots).split(",") if name]
        missing = sorted(set(wanted) - {shot.name for shot in shots})
        if missing:
            raise ValueError(f"unknown shots {missing}; choose from {[s.name for s in shots]}")
        shots = [shot for shot in shots if shot.name in wanted]
    return shots, presets


def run(args: argparse.Namespace, out: Path, log: Any, metrics: dict[str, Any]) -> Board:
    from PyQt6.QtCore import QT_VERSION_STR

    from open_garden_planner.ui.view3d.quick3d import offscreen

    started = time.perf_counter()
    offscreen.ensure_application()
    metrics.update({"platform": platform.platform(), "python": sys.version.split()[0],
                    "qt": QT_VERSION_STR, "size": str(args.size), "software": bool(args.software),
                    "sky_light": not args.software, "wind_time": 0.0})
    board = Board(args, out, log, metrics)
    log("start", qt=QT_VERSION_STR, size=args.size, presets=args.presets, shots=args.shots,
        software=bool(args.software))
    board.load()
    shots, presets = _chosen(args, default_shots(board.width, board.depth))
    metrics["presets"] = presets
    board.write()
    if args.list:
        for shot in shots:
            sun = board.sun_at(shot.when_utc)
            look = look_for(sun, presets[0])
            print(f"{shot.name:14s} {shot.when_utc.isoformat()}  sun {sun.elevation_deg:6.2f} / "
                  f"{sun.azimuth_deg:6.2f}  {'night' if look.night else 'day  '}  exposure "
                  f"{look.mood.exposure:.3f}  key {look.mood.sun_color}")
        return board
    board.shoot(shots, presets)
    if args.moods:
        board.mood_strip(default_shots(board.width, board.depth), presets)
    if args.iou:
        board.shadow_iou(presets)
    if args.orient:
        board.orientation(plan_day(shots[0].when_utc) if shots else date(2026, 6, 21))
        board.sky_azimuth()
    if args.horizon:
        board.horizon(default_shots(board.width, board.depth), presets)
    if args.dusk:
        board.dusk(default_shots(board.width, board.depth), presets)
    if args.fence:
        board.fence_moire(default_shots(board.width, board.depth), presets)
    if args.edge:
        board.plan_edge(default_shots(board.width, board.depth), presets)
    if shots and (args.iou or args.orient or args.horizon or args.dusk or args.fence or args.edge):
        board.restore_check(shots[0], presets[0])
    if args.fps_seconds > 0 and shots:
        board.frame_rate(shots[0], presets, float(args.fps_seconds))
    metrics["total_s"] = round(time.perf_counter() - started, 2)
    return board


def main(argv: list[str] | None = None) -> int:
    script_isolation.isolate()
    args = _parse(sys.argv[1:] if argv is None else argv)
    from open_garden_planner.ui.view3d.quick3d.offscreen import RenderError
    from open_garden_planner.ui.view3d.quick3d.runlog import RenderLog, watchdog

    out: Path = args.out
    if args.list:                    # prints the shots; no directory, no log, no metrics
        log = RenderLog(None, mirror=False)
        run(args, out, log, {"status": "list"})
        return 0
    out.mkdir(parents=True, exist_ok=True)
    log = RenderLog(out / "board.log")
    metrics: dict[str, Any] = {"status": "running",
                               "neutral_day": {"exposure": NEUTRAL_DAY.mood.exposure,
                                               "sun_color": NEUTRAL_DAY.mood.sun_color}}
    board: Board | None = None
    code = 0
    try:
        with watchdog(float(args.watchdog_s), log, what="the beauty board", supervised=True):
            board = run(args, out, log, metrics)
        metrics["status"] = "ok"
    except RenderError as error:   # a shader or QML error: the frames are not to be trusted
        metrics["status"] = "qt_errors"
        metrics["error"] = log_text(error)
        log("qt_errors", error=log_text(error))
        code = QT_ERRORS_EXIT
    except Exception as error:  # noqa: BLE001 - a tool: record it, never swallow it silently
        metrics["status"] = "error"
        metrics["error"] = f"{type(error).__name__}: {log_text(error)}"
        metrics["traceback"] = traceback.format_exc()
        log("error", error=metrics["error"])
        code = 2
    finally:
        if board is not None:
            board.write()
        else:
            (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str),
                                              encoding="utf-8")
        log("done", status=metrics["status"], total_s=metrics.get("total_s"))
        log.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
