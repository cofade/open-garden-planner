"""The ground bake's half of the 3D render tier (Phase 17 L1.5, #385) — not a test module.

``quick3d_render_driver.py`` with the ground's scenarios added: the same process
rules (a real QPA, no Python Qt message handler, ``result.json`` after every
scenario, a watchdog), the same division of labour — this file only DOES engine
things (bake, upload, grab, count), and ``test_scene3d_ground_render.py`` JUDGES
the frames with a projection of its own::

    python tests/integration/ground_bake_render_driver.py --out <dir> --scenarios ground_plan,…

The scene definitions below are plain, engine-free functions both halves import.
Every frame is taken with ``host.grab()`` — a FINISHED frame; nothing here waits
for a swap signal. The keep-alive soak takes NONE in its measured loop: a live
view does not grab, and a ``grab()`` on a window that presents nothing is what
grows a Direct3D 11 process (PF-L3D-04, the grab() paragraph of archive/07-l1-5-ground-bake.md — the soak's ``_grab`` twin is the
control that shows it).
"""

from __future__ import annotations

import hashlib
import statistics
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":  # run as a script: make this checkout's code importable
    for entry in (str(REPO / "src"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

from open_garden_planner.core.scene3d import (  # noqa: E402
    BuilderRegistry,
    GroundSpec,
    GroundTile,
    Material,
    Paint,
    Params,
    Record,
    SceneSync,
    SunState,
    Transform,
)
from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot, TopDownShot  # noqa: E402
from tests.integration import quick3d_render_driver as base  # noqa: E402

# ── scene definitions (engine-free; the tests import them) ───────────────────

HIGH_SUN = SunState(elevation_deg=60.0, azimuth_deg=180.0)
PLAN_VIEW = (640, 400)                  # the real plan's frames
SEAM_VIEW = (480, 360)

#: A plan of 1100 x 700 cm: 3 x 2 tiles at 1 px/cm, with tile borders at east 512
#: and 1024 and at north 512.
SEAM_PLAN = GroundSpec(width_cm=1100.0, depth_cm=700.0)
BORDERS_EAST = (512.0, 1024.0)
BORDER_NORTH = 512.0
LAWN = (90, 160, 70, 255)
BAND = (40, 90, 40, 255)
#: the whole plan, a little minified (a mip level below the tiles' own)
SEAM_TOP = TopDownShot(center=(550.0, 350.0), px_per_cm=0.4)
#: 120 x 90 cm around the point where four tiles meet, each texel four pixels wide
SEAM_ZOOM = TopDownShot(center=(512.0, 512.0), px_per_cm=4.0)
#: … and around the second border, where the last column is a 76-px tile
SEAM_ZOOM_EAST = TopDownShot(center=(1024.0, 300.0), px_per_cm=4.0)
#: low over the lawn, looking along the border at east 512: minification by distance
SEAM_OBLIQUE = PerspectiveShot(eye=(380.0, 40.0, 70.0), target=(512.0, 520.0, 0.0))
SEAM_SHOTS = {"top": SEAM_TOP, "zoom": SEAM_ZOOM, "zoom_east": SEAM_ZOOM_EAST,
              "oblique": SEAM_OBLIQUE}

KEEPALIVE_PLAN = GroundSpec(width_cm=2048.0, depth_cm=2048.0)   # 16 tiles, 16 MB of RGBA8
KEEPALIVE_CYCLES = 20
KEEPALIVE_TOP = TopDownShot(center=(1024.0, 1024.0), px_per_cm=0.1)


#: Two tiles side by side, and the colours they are re-textured with (hand-made tiles:
#: the bake is not what this scenario is about).
RETEXTURE_TOP = TopDownShot(center=(512.0, 256.0), px_per_cm=0.25)
RETEXTURE_VIEW = (320, 240)
TILE_COLOURS = {"red": (200, 30, 30), "green": (30, 200, 30), "blue": (30, 30, 200),
                "pink": (220, 90, 200), "grey": (120, 120, 120)}
#: name → the grounds shown one after another WITHOUT a frame between them ("frame": one
#: is rendered there, and the replaced textures are let go as after a presented frame),
#: starting from (red, grey) and a frame. The last pair is what must be seen.
RETEXTURE_SEQUENCES: dict[str, tuple[Any, ...]] = {
    "one tile, twice": (("green", "grey"), ("blue", "grey")),
    "one tile, five times": (("green", "grey"), ("blue", "grey"), ("pink", "grey"), ("green", "grey"),
                             ("blue", "grey")),
    "two tiles in turn": (("green", "grey"), ("green", "blue"), ("pink", "blue")),
    "a frame between": (("green", "grey"), "frame", ("blue", "grey")),
    "the other tile after a frame": (("green", "grey"), "frame", ("green", "blue"), "frame",
                                     ("pink", "blue")),
}


def retexture_ground(first: str, second: str) -> GroundSpec:
    def tile(column: int, name: str) -> GroundTile:
        return GroundTile(column, 0, column * 512.0, 0.0, 512.0, 512.0, 64, 64,
                          bytes((*TILE_COLOURS[name], 255)) * (64 * 64))

    return GroundSpec(1024.0, 512.0, tiles=(tile(0, first), tile(1, second)))


def surface(item_id: str, east0: float, north0: float, east1: float, north1: float,
            rgba: tuple[int, int, int, int]) -> Record:
    """A flat rectangle of one colour, no outline: a record the bake paints."""
    half_w, half_d = (east1 - east0) / 2.0, (north1 - north0) / 2.0
    ring = ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))
    return Record(item_id=item_id, kind="LAWN", shape="rectangle", footprints=(ring,),
                  transform=Transform(east_cm=(east0 + east1) / 2.0, north_cm=(north0 + north1) / 2.0),
                  material=Material("LAWN", fill_rgba=rgba, paint=Paint(stroke_style="NoPen")),
                  params=Params({"seed": item_id}))


def uniform_records() -> dict[str, Record]:
    """G7: one lawn of one colour over the whole plan (and a little beyond)."""
    return {"lawn": surface("lawn", -20.0, -20.0, 1120.0, 720.0, LAWN)}


def banded_records() -> dict[str, Record]:
    """The lawn, and darker bands that STRADDLE every tile border: across a border
    the ground is one colour, while the tile's OPPOSITE edge has the other one. A
    texture that repeats instead of clamping blends that opposite edge into the
    border — a line the uniform lawn cannot show."""
    return {**uniform_records(),
            "band_east": surface("band_east", 384.0, -20.0, 640.0, 720.0, BAND),
            "band_far": surface("band_far", 896.0, -20.0, 1120.0, 720.0, BAND),
            "band_north": surface("band_north", -20.0, 384.0, 1120.0, 640.0, BAND)}


def keepalive_records(cycle: int) -> dict[str, Record]:
    """One lawn over the whole plan in a colour of its cycle: every tile re-bakes."""
    shade = 60 + (cycle * 7) % 120
    return {"lawn": surface("lawn", -20.0, -20.0, 2068.0, 2068.0, (shade, 200 - shade, 70, 255))}


def plan_top(ground: GroundSpec) -> TopDownShot:
    """The whole plan in a ``PLAN_VIEW`` frame, north up."""
    scale = min(PLAN_VIEW[0] / ground.width_cm, PLAN_VIEW[1] / ground.depth_cm) * 0.95
    return TopDownShot(center=(ground.width_cm / 2.0, ground.depth_cm / 2.0), px_per_cm=scale)


#: How many of the last cycles gate G6 reads (the first ones are the allocator settling).
TAIL_CYCLES = 10


def tail_growth(curve: list[float], cycles: int = TAIL_CYCLES) -> float:
    """MB per cycle at the end of a memory curve: the MEDIAN of the growth of each of
    the last ``cycles`` cycles (``curve[i] - curve[i - 1]``) — Ruling R41.

    A leak adds memory EVERY cycle, so most steps are the leak and the median is
    its size; a one-off step (an allocator taking one more block — measured on WARP:
    +20.6 MB once at cycle 15 of a flat curve) is one step of ten, and the median
    does not see it. The statistic before (Theil-Sen over the second half: the
    median of all pairwise slopes) read that one step as +2.80 MB a cycle — over a
    bound of 2.0 — because a step in the middle of the window tilts most pairs."""
    if len(curve) < cycles + 1:
        raise ValueError(f"a curve of {len(curve)} readings has no {cycles} cycles to judge")
    steps = [curve[index] - curve[index - 1] for index in range(len(curve) - cycles, len(curve))]
    return float(statistics.median(steps))


# ── the engine side ──────────────────────────────────────────────────────────

_WIN_QUERY: Any = None


def process_mb() -> float:
    """The memory a leak shows up in, in MiB: private bytes on Windows (the working
    set is trimmed and regrown by the OS), resident set size elsewhere. Neither sees
    dedicated GPU memory."""
    global _WIN_QUERY
    if sys.platform != "win32":
        import os

        with open("/proc/self/statm", encoding="ascii") as handle:
            return int(handle.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    import ctypes
    from ctypes import wintypes

    if _WIN_QUERY is None:  # declared once: a new ctypes type per call would itself grow the process
        class _Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                        ("PrivateUsage", ctypes.c_size_t)]

        windll = ctypes.windll  # type: ignore[attr-defined]
        windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        query = windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        _WIN_QUERY = (_Counters, query, windll.kernel32.GetCurrentProcess)
    struct, query, current = _WIN_QUERY
    counters = struct()
    counters.cb = ctypes.sizeof(struct)
    if not query(current(), ctypes.byref(counters), counters.cb):
        raise RuntimeError("GetProcessMemoryInfo failed: the leak gate has no instrument")
    return float(counters.PrivateUsage) / 2**20


def _tile_uploads() -> int:
    from open_garden_planner.ui.view3d.quick3d.ground_tiles import TileTexture

    return int(TileTexture.uploads)


def _textures_alive() -> int:
    """Tile texture objects that exist on the C++ side (asked of sip, ``textures_alive``)."""
    from open_garden_planner.ui.view3d.quick3d.ground_tiles import textures_alive

    return textures_alive()


def _without_relief(registry: BuilderRegistry) -> BuilderRegistry:
    """``registry`` with the L4 surfaces' relief taken off, in place (#388): stones,
    planks, kerbs, water and blades are ground-detail parts STANDING on the painted
    ground, and the gates of the ground alone judge the bake's tiles under them."""
    from open_garden_planner.core.scene3d.builders import SURFACE_KINDS

    registry.register_many(SURFACE_KINDS, lambda _record: (), replace=True)
    return registry


class _Rig:
    """The product's wiring on a shown host: SceneSync → GroundBaker + Quick3DSink."""

    def __init__(self, host: Any, registry: BuilderRegistry | None = None, *, baked: bool = True,
                 budget_s: float | None = None) -> None:
        from open_garden_planner.ui.view3d.ground_bake import GroundBaker
        from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

        self.host = host
        # no time budget unless a scenario asks for one: a frame is judged after ONE apply
        self.baker = GroundBaker(budget_s=budget_s) if baked else None
        self.sink = Quick3DSink(host)
        self.sync = SceneSync(self.sink, registry, ground_baker=self.baker)
        self.bake_ms: list[float] = []
        if self.baker is not None:
            real = self.baker.bake

            def timed(*args: Any) -> Any:
                started = time.perf_counter()
                try:
                    return real(*args)
                finally:
                    self.bake_ms.append((time.perf_counter() - started) * 1000.0)

            self.baker.bake = timed  # type: ignore[method-assign]

    def facts(self) -> dict[str, Any]:
        """What the engine holds for the ground, read back from the scene."""
        rows = self.host.ground.readback()
        grid = self.baker.grid if self.baker is not None else None
        return {
            "tiles_in_scene": len(rows), "tiles_visible": sum(1 for row in rows if row["visible"]),
            "tiles_textured": sum(1 for row in rows if row["textured"]),
            "ground_tiled": bool(self.host.scene_property("groundTiled")),
            "textures_held": self.host.ground.textures_held(),
            "grid": None if grid is None else {
                "px_per_cm": grid.px_per_cm, "columns": grid.columns, "rows": grid.rows,
                "width_px": grid.width_px, "height_px": grid.height_px},
            "painted": 0 if self.baker is None else len(self.baker.painted_ids()),
            "capped": 0 if self.baker is None else len(self.baker.capped),
            "bake_failures": 0 if self.baker is None else len(self.baker.failures),
            "ground_failure": self.sync.ground_failure,
            "state_equals_expected": self.sink.state() == self.sync.expected_state(),
        }

    def digest(self) -> str:
        """One hash over every tile's pixels, in grid order."""
        assert self.baker is not None
        sha = hashlib.sha256()
        for tile in self.baker.tiles():
            sha.update(tile.pixels)
        return sha.hexdigest()


def _flat_item(scene: Any, painted: set[str]) -> Any:
    """The largest painted item of the plan that is no longer than 3 m."""
    best: tuple[float, str, Any] | None = None
    for item in scene.items():
        item_id = str(getattr(item, "item_id", ""))
        if item_id not in painted:
            continue
        rect = item.sceneBoundingRect()
        if max(rect.width(), rect.height()) > 300.0:
            continue
        key = (rect.width() * rect.height(), item_id, item)
        if best is None or key[:2] > best[:2]:
            best = key
    if best is None:
        raise RuntimeError("the plan has no painted item of up to 3 m to move")
    return best[2]


def scenario_ground_plan(ctx: base.Context) -> dict[str, Any]:
    """§8.10 on a real renderer, and gate G2's engine half: bench_small.ogp → snapshot →
    SceneSync → GroundBaker + Quick3DSink → frames; one small edit and its undo."""
    from PyQt6.QtCore import QPointF

    from open_garden_planner.core.commands import MoveItemsCommand
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    scene, view, _manager = base._load_bench()
    commands = view.command_manager
    at = date(2026, 6, 21)
    ground = GroundSpec(float(scene.width_cm), float(scene.height_cm))
    top = plan_top(ground)
    overview = PerspectiveShot(eye=(ground.width_cm / 2.0, -1400.0, 1500.0),
                               target=(ground.width_cm / 2.0, ground.depth_cm / 2.0, 0.0))
    host = ctx.shown_host(PLAN_VIEW)
    out: dict[str, Any] = {"plan": base.PLAN.name, "ground": [ground.width_cm, ground.depth_cm],
                           "top": {"center": list(top.center), "px_per_cm": top.px_per_cm}}
    try:
        rig = _Rig(host, production_registry())
        records = snapshot_records(scene, at)
        uploads = _tile_uploads()
        started = time.perf_counter()
        rig.sync.apply(records, sun=HIGH_SUN, ground=ground)
        applied = time.perf_counter()
        host.set_shot(overview)
        frame = ctx.save("ground_plan_overview", host.grab("ground_plan_overview"))
        shown = time.perf_counter()
        out["open"] = {"frame": frame, "records": len(records), "uploads": _tile_uploads() - uploads,
                       "bake_ms": round(rig.bake_ms[-1], 2),
                       "apply_ms": round((applied - started) * 1000.0, 2),
                       "to_finished_frame_ms": round((shown - started) * 1000.0, 2),
                       "parts": len(host.engine_parts()), **rig.facts()}
        host.set_shot(top)
        out["open"]["top"] = ctx.save("ground_plan_top", host.grab("ground_plan_top"))
        first_digest = rig.digest()

        # one small edit, twenty times: an item of up to 3 m moved there and back
        item = _flat_item(scene, set(rig.baker.painted_ids()))  # type: ignore[union-attr]
        item_id = str(item.item_id)
        before = records[item_id].transform
        steps: list[dict[str, Any]] = []
        for index in range(20):
            delta = QPointF(40.0, -30.0) if index % 2 == 0 else QPointF(-40.0, 30.0)
            commands.execute(MoveItemsCommand([item], delta))
            uploads = _tile_uploads()
            t0 = time.perf_counter()
            records = snapshot_records(scene, at)
            t1 = time.perf_counter()
            changes = rig.sync.apply(records)
            t2 = time.perf_counter()
            image = host.grab("ground_plan_edit")
            t3 = time.perf_counter()
            steps.append({
                "transform": len(changes.transform), "uploads": _tile_uploads() - uploads,
                "repainted": len(rig.baker.last_repainted),  # type: ignore[union-attr]
                "changed": len(rig.baker.last_changed),  # type: ignore[union-attr]
                "textures_held": host.ground.textures_held(),
                "snapshot_ms": (t1 - t0) * 1000.0, "bake_ms": rig.bake_ms[-1],
                "apply_ms": (t2 - t1) * 1000.0, "grab_ms": (t3 - t2) * 1000.0})
            if index == 0:
                after = records[item_id].transform
                out["moved"] = {"id": item_id, "kind": records[item_id].kind,
                                "from": [before.east_cm, before.north_cm],
                                "to": [after.east_cm, after.north_cm],
                                "frame": ctx.save("ground_plan_moved", image)}
        out["edits"] = {
            "steps": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}
                      for row in steps],
            "median_bake_ms": round(statistics.median(row["bake_ms"] for row in steps), 3),
            "median_apply_ms": round(statistics.median(row["apply_ms"] for row in steps), 3),
            "median_grab_ms": round(statistics.median(row["grab_ms"] for row in steps), 3),
            **rig.facts()}
        # twenty moves there and back: the ground is the first one again, bit for bit
        out["after_edits_digest_equals_first"] = rig.digest() == first_digest
        out["back"] = ctx.save("ground_plan_back", host.grab("ground_plan_back"))

        # G2: the ground alone — the painted records, no solid above them and none of
        # their relief (L4, #388) — seen from straight above, next to the bake itself
        painted = set(rig.baker.painted_ids())  # type: ignore[union-attr]
        uploads = _tile_uploads()
        _without_relief(rig.sync.registry)
        rig.sync.apply({key: record for key, record in records.items() if key in painted})
        out["ground_only"] = {
            "frame": ctx.save("ground_only_top", host.grab("ground_only_top")),
            "bake": ctx.save("ground_only_bake", rig.baker.image()),  # type: ignore[union-attr]
            "uploads": _tile_uploads() - uploads, "parts": len(host.engine_parts()),
            "digest_equals_first": rig.digest() == first_digest, **rig.facts()}
        rig.sync.reset()
        out["cleared"] = {"tiles_in_scene": len(host.ground.readback()),
                          "textures_held": host.ground.textures_held(),
                          "ground_tiled": bool(host.scene_property("groundTiled")),
                          "ground_visible": bool(host.scene_property("groundVisible"))}

        # THE TIME BUDGET on a real engine: a baker that paints ONE tile a pass. The
        # ground arrives over several transactions — each uploads the tile it painted —
        # and ends as the ground of the one unbudgeted bake above, bit for bit.
        slow = _Rig(host, production_registry(), budget_s=0.0)
        uploads = _tile_uploads()
        slow.sync.apply(records, sun=HIGH_SUN, ground=ground)
        first_pass = {"pending": slow.baker.pending,  # type: ignore[union-attr]
                      "uploads": _tile_uploads() - uploads,
                      "frame": ctx.save("ground_plan_first_pass", host.grab("ground_plan_first_pass")),
                      **slow.facts()}
        pending: list[int] = [slow.baker.pending]  # type: ignore[union-attr]
        per_pass: list[int] = []
        held: list[int] = []
        while slow.sync.ground_pending:
            before = _tile_uploads()
            slow.sync.continue_ground()
            per_pass.append(_tile_uploads() - before)
            pending.append(slow.baker.pending)  # type: ignore[union-attr]
            held.append(host.ground.textures_held())
        out["budgeted"] = {
            "first_pass": first_pass, "passes": 1 + len(per_pass), "pending": pending,
            "uploads_per_pass": per_pass, "textures_held_max": max(held, default=0),
            "uploads": _tile_uploads() - uploads, "digest_equals_first": slow.digest() == first_digest,
            "frame": ctx.save("ground_plan_budgeted", host.grab("ground_plan_budgeted")),
            **slow.facts()}
        slow.sync.reset()
        health = host.health()
        out["health"] = {"ok": health.ok, "qml_warnings": list(health.qml_warnings),
                         "scene_graph_error": health.scene_graph_error}
        out["graphics_api"] = host.graphics_api()
        return out
    finally:
        host.close()
        base._pump()


def _offscreen(ctx: base.Context, name: str, records: dict[str, Record], **kwargs: Any
               ) -> dict[str, Any]:
    """One frame through ``render_records`` — a never-shown view — and what it reports."""
    from open_garden_planner.ui.view3d.quick3d.offscreen import render_records

    frame = render_records(records, qml_dir=ctx.qml_dir, log=ctx.log, graphics_info=True,
                           size=PLAN_VIEW, **kwargs)
    info = ctx.save(name, frame.image)
    info.update({"open_ms": round(frame.open_ms, 1), "graphics_api": frame.graphics_api,
                 "adapter": frame.adapter, "items": frame.items, "parts": frame.parts,
                 "build_failures": dict(frame.build_failures), "qt": dict(frame.qt),
                 "ground_tiles": frame.ground_tiles, "ground_failure": frame.ground_failure})
    return info


def scenario_ground_offscreen(ctx: base.Context) -> dict[str, Any]:
    """The §8.10 twin through the OFFSCREEN path: bench_small.ogp → snapshot →
    ``render_records`` with a ground baker — one hidden view, one image. The whole
    plan; the ground alone from straight above, next to its bake; and the same
    without a baker (the control: bare plan ground)."""
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.ui.view3d.ground_bake import GroundBaker
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    scene, _view, _manager = base._load_bench()
    records = snapshot_records(scene, date(2026, 6, 21))
    ground = GroundSpec(float(scene.width_cm), float(scene.height_cm))
    top = plan_top(ground)
    overview = PerspectiveShot(eye=(ground.width_cm / 2.0, -1400.0, 1500.0),
                               target=(ground.width_cm / 2.0, ground.depth_cm / 2.0, 0.0))
    common: dict[str, Any] = {"sun": HIGH_SUN, "ground": ground, "registry": production_registry()}
    baker = GroundBaker()
    whole = _offscreen(ctx, "ground_offscreen_overview", records, shot=overview,
                       ground_baker=baker, **common)
    painted = {key: record for key, record in records.items() if key in set(baker.painted_ids())}
    alone = GroundBaker()
    flat = {**common, "registry": _without_relief(production_registry())}  # L4: no relief
    only = _offscreen(ctx, "ground_offscreen_top", painted, shot=top, ground_baker=alone, **flat)
    return {"ground": [ground.width_cm, ground.depth_cm],
            "top": {"center": list(top.center), "px_per_cm": top.px_per_cm},
            "records": len(records), "painted": len(painted), "whole": whole, "only": only,
            "bake": ctx.save("ground_offscreen_bake", alone.image()),
            "bare": _offscreen(ctx, "ground_offscreen_bare", painted, shot=top, **flat)}


def _seam_frames(ctx: base.Context, host: Any, name: str) -> dict[str, Any]:
    frames: dict[str, Any] = {}
    for key, shot in SEAM_SHOTS.items():
        host.set_shot(shot)
        frames[key] = ctx.save(f"{name}_{key}", host.grab(f"{name}_{key}"))
    return frames


def _seams(ctx: base.Context, prefix: str) -> dict[str, Any]:
    host = ctx.shown_host(SEAM_VIEW)
    out: dict[str, Any] = {}
    try:
        # the bare plan rectangle first: a sync WITHOUT a baker (L1.2's ground)
        bare = _Rig(host, baked=False)
        bare.sync.apply({}, sun=HIGH_SUN, ground=SEAM_PLAN)
        host.set_shot(SEAM_TOP)
        out["bare_rectangle"] = {"frame": ctx.save(f"{prefix}_bare_rectangle",
                                                   host.grab(f"{prefix}_bare_rectangle")),
                                 **bare.facts()}
        bare.sync.reset()
        rig = _Rig(host)
        rig.sync.apply({}, sun=HIGH_SUN, ground=SEAM_PLAN)
        out["bare_tiles"] = {"frame": ctx.save(f"{prefix}_bare_tiles", host.grab(f"{prefix}_bare_tiles")),
                             **rig.facts()}
        for name, records in (("uniform", uniform_records()), ("banded", banded_records())):
            rig.sync.apply(records)
            out[name] = {"frames": _seam_frames(ctx, host, f"{prefix}_{name}"),
                         "bake": ctx.save(f"{prefix}_{name}_bake", rig.baker.image()),  # type: ignore[union-attr]
                         **rig.facts()}
        return out
    finally:
        host.close()
        base._pump()


def scenario_ground_seams(ctx: base.Context) -> dict[str, Any]:
    """G7: a uniform lawn, and a lawn with bands, across every tile border — from above,
    magnified, and low along a border."""
    return _seams(ctx, "seams")


def scenario_ground_seams_gap(ctx: base.Context) -> dict[str, Any]:
    """G7's positive control: the same lawns with the quads laid 1 cm SHORT of their
    tiles on every side — a 2 cm line of meadow between them, which the gate must see."""
    from open_garden_planner.ui.view3d.quick3d import ground_tiles

    kept = ground_tiles.SEAM_OVERLAP_CM
    ground_tiles.SEAM_OVERLAP_CM = -1.0  # type: ignore[misc]
    try:
        return _seams(ctx, "gap")
    finally:
        ground_tiles.SEAM_OVERLAP_CM = kept  # type: ignore[misc]


def scenario_ground_retexture(ctx: base.Context) -> dict[str, Any]:
    """Re-textured tiles keep their picture — whichever tile was re-textured after them,
    and after the replaced textures were let go. (A ``Texture`` element pointed at a
    second texture is drawn white once the first one is destroyed: PF-L3D-04.)"""
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    def show(sink: Any, first: str, second: str) -> None:
        sink.begin()
        sink.set_sun(HIGH_SUN)
        sink.set_ground(retexture_ground(first, second))
        sink.commit()

    out: dict[str, Any] = {"reference": {}, "sequences": {}}
    for name in TILE_COLOURS:  # what each colour looks like in a frame: a fresh host, one ground
        host = ctx.shown_host(RETEXTURE_VIEW)
        try:
            host.set_shot(RETEXTURE_TOP)
            show(Quick3DSink(host), name, name)
            out["reference"][name] = ctx.save(f"retexture_reference_{name}", host.grab(f"reference_{name}"))
        finally:
            host.close()
            base._pump()
    for index, (name, steps) in enumerate(RETEXTURE_SEQUENCES.items()):
        host = ctx.shown_host(RETEXTURE_VIEW)
        try:
            host.set_shot(RETEXTURE_TOP)
            sink = Quick3DSink(host)
            uploads, alive = _tile_uploads(), _textures_alive()
            show(sink, "red", "grey")
            host.grab(f"retexture_{index}_start")
            host.ground.frame_presented()  # what a window that presents does after a frame
            for step in steps:
                if step == "frame":
                    host.grab(f"retexture_{index}_between")
                    host.ground.frame_presented()
                else:
                    show(sink, *step)
            after = ctx.save(f"retexture_{index}_after", host.grab(f"retexture_{index}_after"))
            host.ground.frame_presented()  # the replaced textures go …
            again = ctx.save(f"retexture_{index}_again", host.grab(f"retexture_{index}_again"))
            out["sequences"][name] = {
                "after": after, "again": again, "want": list(steps[-1]),
                "uploads": _tile_uploads() - uploads, "tiles_in_scene": len(host.ground.readback()),
                "textures_held": host.ground.textures_held(),
                "alive": _textures_alive() - alive}
        finally:
            host.close()
            base._pump()
    return out


def _keepalive(ctx: base.Context, name: str, *, leak: bool = False, grab: bool = False
               ) -> dict[str, Any]:
    """Twenty full re-bakes of a 16-tile ground in one shown host. The measured loop
    takes NO frame unless ``grab`` — a live view does not grab: a window that
    presents renders the new tiles on its own while the loop pumps events, and one
    that does not renders nothing. Nor does it ask the QML scene anything: what a
    cycle is judged by are counters on this side. ``grab=True`` is the control of
    PF-L3D-04, the grab() paragraph of archive/07-l1-5-ground-bake.md: a ``grab()`` after every re-bake."""
    host = ctx.shown_host((320, 240))
    try:
        kept: list[Any] = []
        if leak:
            # THE control: the L0 spike's append-only keep-alive list — a replaced
            # texture is never let go
            host.ground._retire = kept.append  # noqa: SLF001
        rig = _Rig(host)
        host.set_shot(KEEPALIVE_TOP)
        curve: list[float] = []
        held: list[int] = []
        alive: list[int] = []
        uploads: list[int] = []
        tiles: list[int] = []
        alive_before, presented_before = _textures_alive(), host.frames_presented
        for cycle in range(KEEPALIVE_CYCLES):
            before = _tile_uploads()
            rig.sync.apply(keepalive_records(cycle), sun=HIGH_SUN, ground=KEEPALIVE_PLAN)
            if grab:
                host.grab(f"{name}_{cycle}")  # a frame that is rendered and not presented
            base._pump(20)  # a presenting window shows the tiles; what was destroyed is deleted
            curve.append(round(process_mb(), 2))
            held.append(host.ground.textures_held() + len(kept))
            alive.append(_textures_alive() - alive_before)
            uploads.append(_tile_uploads() - before)
            # the engine side's own books — NOT ``readback()``: that is a call into the
            # QML scene, and nothing but the re-bake itself belongs in the measured loop
            # (the scene is read back once, after it: ``facts()`` below)
            tiles.append(len(host.ground.keys()))
        presented = host.frames_presented - presented_before
        image = host.grab(f"{name}_last")  # AFTER the measured loop: what the soak ended on
        out = {**rig.facts(), "cycles": KEEPALIVE_CYCLES, "curve_mb": curve,
               "held_per_cycle": held, "alive_per_cycle": alive, "uploads_per_cycle": uploads,
               "tiles_per_cycle": tiles, "leak": leak, "grab": grab,
               "frames_presented": presented,
               "graphics_api": host.graphics_api(),
               "last_frame": ctx.save(f"{name}_last", image),
               "bytes_per_generation": sum(len(tile.pixels) for tile in rig.baker.tiles()),  # type: ignore[union-attr]
               "metric": "private_bytes" if sys.platform == "win32" else "rss"}
        rig.sync.reset()
        kept.clear()
        base._pump(20)
        out["alive_after_clear"] = _textures_alive() - alive_before
        out["mb_after_clear"] = round(process_mb(), 2)
        return out
    finally:
        host.close()
        base._pump()


def scenario_ground_keepalive(ctx: base.Context) -> dict[str, Any]:
    """G6: twenty full re-bakes of a 16-tile ground in one shown host — the memory
    curve, the textures held and the uploads of every cycle. No frame is grabbed
    in the loop."""
    return _keepalive(ctx, "keepalive")


def scenario_ground_keepalive_leak(ctx: base.Context) -> dict[str, Any]:
    """G6's positive control: the same twenty re-bakes with replaced textures kept
    forever — the gate's instrument must see it, on the machine it judges."""
    return _keepalive(ctx, "keepalive_leak", leak=True)


def scenario_ground_keepalive_grab(ctx: base.Context) -> dict[str, Any]:
    """The control of PF-L3D-04, the grab() paragraph of archive/07-l1-5-ground-bake.md: the same twenty re-bakes with a ``grab()`` after each.
    On Direct3D 11 with a hardware adapter, in a window that presents nothing, every
    grabbed frame leaves what it uploaded committed — the rule "no repeated grab on
    a host that is not presenting" exists because of this curve."""
    return _keepalive(ctx, "keepalive_grab", grab=True)


#: The orbit sweep of ``scenario_ground_visible``: bearings round the plan, eye heights
#: and the distance as shares of the plan's diagonal (the board's cameras lie in it).
VISIBLE_BEARINGS = tuple(float(bearing) for bearing in range(0, 360, 30))
VISIBLE_HEIGHTS = (0.12, 0.22, 0.40)
VISIBLE_DISTANCE = 0.95
VISIBLE_KEY = "#ff00ff"  # the meadow, keyed: a colour no plan surface has
VISIBLE_PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_built.ogp"
#: … and the workspace's own camera on the three bench plans (3D review of #388, round
#: 2: the meadow came through the plan from the default framing a few wheel notches out,
#: a view the orbit sweep never took): ``camera.frame_pose`` of the plan, turned by each
#: yaw, and its distance times each factor — 0, 2 and 4 notches of the wheel
#: (``orbit_input.WHEEL_ZOOM_PER_NOTCH`` 0.85) and the two factors that failed in review.
VISIBLE_PLANS = (("bench_small", 2400.0, 1600.0), ("bench_built", 2600.0, 1800.0),
                 ("bench_large", 5000.0, 3000.0))
VISIBLE_YAWS = tuple(float(yaw) for yaw in range(0, 360, 45))
VISIBLE_FACTORS = (1.0, 0.85 ** -2, 0.85 ** -4, 1.5, 1.63)


def scenario_ground_visible(ctx: base.Context) -> dict[str, Any]:
    """The endless meadow never shows through the plan (3D review of #388: one quad 1 cm,
    then 5 cm, under the plan overwrote it from 14 of 36 orbit cameras, then from 13 of
    120 default-framing views — the pond, the terraces and the paths were gone). The
    meadow is drawn in a key colour; the test projects the plan into each frame and
    counts that colour there. The orbit sweep on bench_built, then the workspace's own
    camera on the three bench plans."""
    import dataclasses
    import math

    from open_garden_planner.core import ProjectManager
    from open_garden_planner.core.scene3d import camera
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    host = ctx.shown_host(PLAN_VIEW)
    try:
        rig = _Rig(host, production_registry())
        views: list[dict[str, Any]] = []
        textured: dict[str, list[int]] = {}

        def show(name: str, width: float, depth: float) -> tuple[GroundSpec, list[Any]]:
            scene = CanvasScene(width_cm=width, height_cm=depth)
            ProjectManager().load(scene, REPO / "tests" / "fixtures" / "plans" / f"{name}.ogp")
            ground = GroundSpec(float(scene.width_cm), float(scene.height_cm))
            records = snapshot_records(scene, date(2026, 6, 21))
            rig.sync.apply(records, sun=HIGH_SUN, ground=ground)
            host.set_look(dataclasses.replace(host.look, meadow_albedo=VISIBLE_KEY))
            facts = rig.facts()
            textured[name] = [facts["tiles_textured"], facts["tiles_in_scene"]]
            return ground, list(records.values())

        def grab(name: str, plan: str, ground: GroundSpec, shot: PerspectiveShot) -> None:
            host.set_shot(shot)
            views.append({"plan": plan, "ground": [ground.width_cm, ground.depth_cm],
                          "eye": list(shot.eye), "target": list(shot.target), "fov": shot.fov_deg,
                          **ctx.save(name, host.grab(name))})

        ground, _records = show("bench_built", 2600.0, 1800.0)
        cx, cy = ground.width_cm / 2.0, ground.depth_cm / 2.0
        diag = math.hypot(ground.width_cm, ground.depth_cm)
        for height in VISIBLE_HEIGHTS:
            for bearing in VISIBLE_BEARINGS:
                turn = math.radians(bearing)
                eye = (cx + VISIBLE_DISTANCE * diag * math.sin(turn),
                       cy - VISIBLE_DISTANCE * diag * math.cos(turn), height * diag)
                grab(f"visible_{int(bearing):03d}_{int(height * 100):02d}", "bench_built", ground,
                     PerspectiveShot(eye=eye, target=(cx, cy, 60.0), fov_deg=44.0))
        for plan, width, depth in VISIBLE_PLANS:
            ground, records = show(plan, width, depth)
            top = max((r.transform.base_cm + r.height_cm for r in records if r.height_cm is not None),
                      default=0.0)
            framed = camera.frame_pose(camera.Bounds.of_plan(ground.width_cm, ground.depth_cm, top),
                                       PLAN_VIEW[0] / PLAN_VIEW[1])
            for yaw in VISIBLE_YAWS:
                for factor in VISIBLE_FACTORS:
                    pose = camera.CameraPose(framed.target, framed.distance_cm * factor,
                                             framed.yaw_deg + yaw, framed.pitch_deg)
                    grab(f"framed_{plan}_{int(yaw):03d}_x{factor:.2f}", plan, ground,
                         PerspectiveShot(eye=pose.eye, target=pose.target_scene, fov_deg=camera.FOV_DEG))
        return {"view": list(PLAN_VIEW), "views": views, "textured": textured,
                "meadow_loads": host.meadow_loads}
    finally:
        host.close()
        base._pump()


base.SCENARIOS.update({
    "ground_offscreen": scenario_ground_offscreen,
    "ground_plan": scenario_ground_plan,
    "ground_visible": scenario_ground_visible,
    "ground_retexture": scenario_ground_retexture,
    "ground_seams": scenario_ground_seams,
    "ground_seams_gap": scenario_ground_seams_gap,
    "ground_keepalive": scenario_ground_keepalive,
    "ground_keepalive_leak": scenario_ground_keepalive_leak,
    "ground_keepalive_grab": scenario_ground_keepalive_grab,
})


if __name__ == "__main__":
    sys.exit(base.main(sys.argv[1:]))
