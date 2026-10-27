"""The engine-side half of the 3D render tier (Phase 17 L1.2, #385) — not a test module.

Why a separate process: 3D needs a real window system, and the test process is
``QT_QPA_PLATFORM=offscreen`` (the software scene graph renders no 3D). The
render tests (``test_quick3d_render.py``, ``test_quick3d_engine.py``) start THIS
file with a real QPA::

    python tests/integration/quick3d_render_driver.py --out <dir> --scenarios truth,edits,…

Division of labour — the reason the tier can be trusted:

- the driver only DOES engine things: it drives ``SceneSync`` → ``Quick3DSink`` →
  ``Quick3DHost``, saves every frame as a PNG and writes raw engine answers
  (picks, read-back Models, counters, timings) to ``result.json``;
- the tests JUDGE: they predict pixels with their own CPU projection and compare.

So the scene definitions below are plain, engine-free functions both halves
import, and nothing in this module asserts anything about a pixel.

Qt's MESSAGES are not recorded in here. A Python message handler beside a shown
window deadlocks against Qt's render thread (``qt_messages.py``), so this process
installs none of its own: Qt prints its messages to stderr in the pattern the
caller set (``quick3d_render_support.render_env``), a mark on stderr says which
scenario runs, and the judge classifies them. Only ``render_records`` — a
never-shown window, rendered on the calling thread — records its own frame's
messages, and reports them with the frame.

``result.json`` is rewritten after every scenario; ``render.log`` is flushed per
line; a watchdog dumps all stacks and exits 1 when the run takes too long.
Exit codes: 0 ok · 1 watchdog · 2 an exception · 4 a render that failed on a Qt
error (shader / QML).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import platform
import statistics
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":  # run as a script: make this checkout's code importable
    for entry in (str(REPO / "src"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

from open_garden_planner.core.scene3d import (  # noqa: E402
    BuilderRegistry,
    GroundSpec,
    Material,
    Mesh,
    MeshPart,
    Params,
    Record,
    RecordingSink,
    SceneSync,
    SunState,
    Transform,
    default_builder,
    engine_pose,
    pose_points,
    prism_mesh,
)
from open_garden_planner.ui.view3d.quick3d.materials import part_tint  # noqa: E402
from open_garden_planner.ui.view3d.quick3d.shots import (  # noqa: E402
    PerspectiveShot,
    TopDownShot,
    top_down_pixel,
)

PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
QT_ERRORS_EXIT = 4

# ── scene definitions (engine-free; the tests import them) ───────────────────

VIEW = (480, 360)                      # logical pixels of every probe frame
TOP = TopDownShot(center=(0.0, 0.0), px_per_cm=0.5)   # 960 x 720 cm, north up
GROUND = GroundSpec(width_cm=2000.0, depth_cm=2000.0)
RED = (230, 20, 20, 255)
BLUE = (20, 40, 230, 255)
YELLOW = (250, 220, 10, 255)
GREY = (200, 200, 200, 255)
HIGH_SUN = SunState(elevation_deg=60.0, azimuth_deg=180.0)


def rect_ring(width: float, depth: float) -> tuple[tuple[float, float], ...]:
    half_w, half_d = width / 2.0, depth / 2.0
    return ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))


def box(item_id: str, east: float, north: float, width: float, depth: float, height: float,
        colour: tuple[int, int, int, int], rotation: float = 0.0,
        ring: tuple[tuple[float, float], ...] | None = None) -> Record:
    """A record the default builder turns into a tinted prism."""
    footprint = ring if ring is not None else rect_ring(width, depth)
    return Record(
        item_id=item_id, kind="SHED", shape="polygon" if ring is not None else "rectangle",
        footprints=(footprint,),
        transform=Transform(east_cm=east, north_cm=north, rotation_deg=rotation),
        material=Material("SHED", fill_rgba=colour), height_cm=height,
        params=Params({"seed": item_id}),
    )


def truth_records() -> dict[str, Record]:
    """G5: a RED box EAST of the origin and a BLUE box NORTH of it."""
    return {"east": box("east", 250.0, 0.0, 80.0, 80.0, 60.0, RED),
            "north": box("north", 0.0, 200.0, 80.0, 80.0, 60.0, BLUE)}


BAR_ROTATIONS = (0.0, 17.0, 90.0, 213.5)


def bar_record(rotation: float) -> Record:
    """G5 / the open proof of L1.1: a NON-square box, turned."""
    return box("bar", -100.0, -80.0, 240.0, 60.0, 50.0, RED, rotation)


SUN_ELEVATION = 35.0
SUN_AZIMUTHS = (225.0, 135.0, 45.0)
CASTER_SIDE, CASTER_HEIGHT = 100.0, 200.0
# a camera on each face's own normal, looking at the face centre: that face is at the
# image centre by construction (any correct lookAt puts the target there)
FACE_NORMALS = {"south": (0.0, -1.0), "north": (0.0, 1.0), "east": (1.0, 0.0), "west": (-1.0, 0.0)}


def caster_record() -> Record:
    return box("caster", 0.0, 0.0, CASTER_SIDE, CASTER_SIDE, CASTER_HEIGHT, GREY)


def face_shot(face: str) -> PerspectiveShot:
    nx, ny = FACE_NORMALS[face]
    half, mid = CASTER_SIDE / 2.0, CASTER_HEIGHT / 2.0
    return PerspectiveShot(eye=(nx * 700.0, ny * 700.0, mid), target=(nx * half, ny * half, mid))


EDIT_A = box("a", -200.0, 100.0, 100.0, 100.0, 80.0, RED)
EDIT_B = box("b", 150.0, -100.0, 100.0, 100.0, 80.0, BLUE)
EDIT_A_MOVED = replace(EDIT_A, transform=Transform(east_cm=-250.0, north_cm=-150.0, rotation_deg=30.0))
EDIT_A_YELLOW = replace(EDIT_A_MOVED, material=Material("SHED", fill_rgba=YELLOW))
EDIT_A_WIDE = replace(EDIT_A_YELLOW, footprints=(rect_ring(240.0, 60.0),))

MATERIAL_KINDS_ORDER = ("vc", "roof", "foliage", "grass", "glass", "water")
SWATCH_TINT = (200, 60, 40, 255)
SWATCH_SUN = SunState(elevation_deg=30.0, azimuth_deg=200.0)


def swatch_builder(record: Record) -> tuple[MeshPart, ...]:
    """One tinted prism in the material kind the record asks for."""
    kind = str(record.params["material_kind"])
    assert record.height_cm is not None
    return (MeshPart(prism_mesh(record.footprints, record.height_cm), kind,
                     casts_shadow=kind not in ("glass", "water"), tinted=True, name=kind),)


def swatch_records() -> dict[str, Record]:
    """One 80 x 80 x 60 swatch per material kind, in a row along the east axis."""
    out: dict[str, Record] = {}
    for index, kind in enumerate(MATERIAL_KINDS_ORDER):
        out[kind] = Record(
            item_id=kind, kind="SWATCH", shape="rectangle", footprints=(rect_ring(80.0, 80.0),),
            transform=Transform(east_cm=-375.0 + 150.0 * index, north_cm=0.0),
            material=Material("SWATCH", fill_rgba=SWATCH_TINT), height_cm=60.0,
            params=Params({"seed": kind, "material_kind": kind}))
    return out


def swatch_registry() -> BuilderRegistry:
    registry = BuilderRegistry()
    registry.register("SWATCH", swatch_builder)
    return registry


#: The wind strength of the rest probe, in the shaders' units: 35 cm of sway for
#: foliage and 100 cm for grass if the shader moved a vertex at rest (40 x the look's).
REST_WIND = 100.0
REST_SIDE, REST_HEIGHT = 100.0, 60.0


def rest_builder(record: Record) -> tuple[MeshPart, ...]:
    """A prism whose EVERY vertex carries the full wind weight (uv.x = 1) and a
    quarter-turn phase (uv.y = 0.25) — the vertex a wind shader moves furthest."""
    kind = str(record.params["material_kind"])
    assert record.height_cm is not None
    mesh = prism_mesh(record.footprints, record.height_cm)
    uvs = np.tile(np.array([1.0, 0.25], dtype=np.float32), (mesh.vertex_count, 1))
    windy = Mesh.from_arrays(mesh.positions, mesh.normals, mesh.colors, uvs, mesh.indices)
    return (MeshPart(windy, kind, casts_shadow=True, tinted=True, name=kind),)


def rest_records() -> dict[str, Record]:
    """P2-11: a RED foliage box north of the origin and a BLUE grass box south of it,
    both on the east = 0 line (where the shaders' sway term is largest)."""
    out: dict[str, Record] = {}
    for kind, north, colour in (("foliage", 110.0, RED), ("grass", -110.0, BLUE)):
        out[kind] = Record(
            item_id=kind, kind="RESTPROBE", shape="rectangle",
            footprints=(rect_ring(REST_SIDE, REST_SIDE),),
            transform=Transform(east_cm=0.0, north_cm=north),
            material=Material("RESTPROBE", fill_rgba=colour), height_cm=REST_HEIGHT,
            params=Params({"seed": kind, "material_kind": kind}))
    return out


def rest_registry() -> BuilderRegistry:
    registry = BuilderRegistry()
    registry.register("RESTPROBE", rest_builder)
    return registry


L_RING = ((-90.0, -90.0), (90.0, -90.0), (90.0, -30.0), (-30.0, -30.0), (-30.0, 90.0), (-90.0, 90.0))
TRIANGLE_RING = ((-70.0, -50.0), (70.0, -50.0), (0.0, 70.0))


def pick_records() -> dict[str, Record]:
    """G8: ten items whose bounding boxes overlap and lie about their meshes — a post
    on a deck, turned bars, a concave L, a triangle, a pillar on a slab."""
    items = [
        box("low-deck", -250.0, 180.0, 300.0, 200.0, 20.0, GREY),
        box("tall-post", -300.0, 200.0, 40.0, 40.0, 300.0, RED),
        box("bar-30", 110.0, 230.0, 300.0, 40.0, 100.0, BLUE, rotation=30.0),
        box("bar-120", 320.0, -40.0, 260.0, 50.0, 60.0, YELLOW, rotation=120.0),
        box("l-shape", -60.0, -150.0, 0.0, 0.0, 150.0, RED, rotation=20.0, ring=L_RING),
        box("cube-low", -390.0, -250.0, 80.0, 80.0, 80.0, BLUE),
        box("cube-high", -310.0, -250.0, 80.0, 80.0, 200.0, YELLOW),
        box("slab", 170.0, -250.0, 200.0, 120.0, 10.0, GREY),
        box("pillar", 170.0, -250.0, 30.0, 30.0, 180.0, RED),
        box("tri", 370.0, 250.0, 0.0, 0.0, 90.0, BLUE, rotation=75.0, ring=TRIANGLE_RING),
    ]
    return {record.item_id: record for record in items}


def oracle_triangles(records: Mapping[str, Record]) -> dict[str, np.ndarray]:
    """Every item's triangles in the SCENE frame, (T, 3, 3) — CPU only: the default
    builder's mesh, posed by ``core.scene3d.pose_points``. No engine involved."""
    out: dict[str, np.ndarray] = {}
    for item_id, record in records.items():
        triangles = []
        for part in default_builder(record):
            scene = pose_points(record.transform, part.mesh.positions)
            triangles.append(scene[part.mesh.indices.astype(np.int64)])
        if triangles:
            out[item_id] = np.concatenate(triangles)
    return out


def cpu_topmost_hit(triangles: Mapping[str, np.ndarray], x: float, y: float
                    ) -> tuple[str | None, float]:
    """The item a vertical ray at scene (x, y) meets first from above, and the height
    it meets it at (ported from the L0 spike's pick oracle)."""
    best_id: str | None = None
    best_z = -math.inf
    point = np.array([x, y], np.float64)
    for item_id, tri in triangles.items():
        a, b, c = (tri[:, k, :] for k in range(3))
        v0, v1, v2 = c[:, :2] - a[:, :2], b[:, :2] - a[:, :2], point - a[:, :2]
        d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
        d02, d12 = (v0 * v2).sum(1), (v1 * v2).sum(1)
        den = d00 * d11 - d01 * d01
        ok = np.abs(den) > 1e-9
        den = np.where(ok, den, 1.0)
        u = (d11 * d02 - d01 * d12) / den
        v = (d00 * d12 - d01 * d02) / den
        inside = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
        if not inside.any():
            continue
        z = a[:, 2] + u * (c[:, 2] - a[:, 2]) + v * (b[:, 2] - a[:, 2])
        top = float(z[inside].max())
        if top > best_z:
            best_id, best_z = item_id, top
    return best_id, best_z


def robust_hit(triangles: Mapping[str, np.ndarray], x: float, y: float, margin: float = 3.0
               ) -> tuple[str | None, float] | None:
    """The oracle's answer if it is the same ``margin`` cm around the point (a target
    on an edge would test rasterisation, not picking), else None."""
    hit = cpu_topmost_hit(triangles, x, y)
    for dx, dy in ((margin, 0.0), (-margin, 0.0), (0.0, margin), (0.0, -margin),
                   (margin, margin), (-margin, -margin), (margin, -margin), (-margin, margin)):
        if cpu_topmost_hit(triangles, x + dx, y + dy)[0] != hit[0]:
            return None
    return hit


def pick_plan(records: Mapping[str, Record]) -> list[dict[str, Any]]:
    """The G8 click list, each with what the CPU oracle expects there.

    ``easy``: one point per item where it is the topmost thing. ``adversarial``:
    points INSIDE an item's bounding box where the oracle sees another item or
    bare ground (a picker that tests boxes fails these). ``empty``: bare ground.
    """
    triangles = oracle_triangles(records)
    plan: list[dict[str, Any]] = []
    fractions = np.linspace(0.08, 0.92, 15)
    for item_id, tri in triangles.items():
        flat = tri.reshape(-1, 3)
        low, high = flat.min(axis=0), flat.max(axis=0)
        easy = adversarial = None
        for fx in fractions:
            for fy in fractions:
                x = float(low[0] + fx * (high[0] - low[0]))
                y = float(low[1] + fy * (high[1] - low[1]))
                answer = robust_hit(triangles, x, y)
                if answer is None:
                    continue
                if answer[0] == item_id and easy is None:
                    easy = {"kind": "easy", "x": x, "y": y, "expected": item_id, "z": answer[1],
                            "in_box_of": item_id}
                if answer[0] != item_id and adversarial is None:
                    adversarial = {"kind": "adversarial", "x": x, "y": y, "expected": answer[0],
                                   "z": answer[1] if answer[0] is not None else 0.0,
                                   "in_box_of": item_id}
        plan.extend(entry for entry in (easy, adversarial) if entry is not None)
    for x, y in ((-440.0, 20.0), (-150.0, 20.0), (20.0, 60.0), (440.0, 120.0), (30.0, -330.0),
                 (-440.0, -330.0), (440.0, -330.0), (-30.0, 330.0), (250.0, 80.0), (-200.0, -40.0)):
        answer = robust_hit(triangles, x, y)
        if answer is not None and answer[0] is None:
            plan.append({"kind": "empty", "x": x, "y": y, "expected": None, "z": 0.0,
                         "in_box_of": None})
    return plan


# ── the engine side ──────────────────────────────────────────────────────────


class Context:
    """What every scenario gets: where to write, how to log, which QML to load."""

    def __init__(self, out: Path, log: Any, qml_dir: Path | None) -> None:
        self.out = out
        self.log = log
        self.qml_dir = qml_dir

    def save(self, name: str, image: Any) -> dict[str, Any]:
        path = self.out / f"{name}.png"
        if not image.save(str(path)):
            raise RuntimeError(f"could not write {path}")
        return {"file": path.name, "size": [image.width(), image.height()],
                "dpr": float(image.devicePixelRatio())}

    def offscreen(self, name: str, records: Mapping[str, Record], **kwargs: Any) -> dict[str, Any]:
        from open_garden_planner.ui.view3d.quick3d.offscreen import render_records

        kwargs.setdefault("size", VIEW)
        kwargs.setdefault("ground", GROUND)
        frame = render_records(records, qml_dir=self.qml_dir, log=self.log, graphics_info=True,
                               **kwargs)
        info = self.save(name, frame.image)
        info.update({"open_ms": round(frame.open_ms, 1),
                     "breakdown_ms": {k: round(v, 1) for k, v in frame.breakdown_ms.items()},
                     "graphics_api": frame.graphics_api, "adapter": frame.adapter,
                     "view_size": list(frame.view_size), "items": frame.items,
                     "parts": frame.parts, "build_failures": dict(frame.build_failures),
                     "qt": dict(frame.qt)})
        return info

    def shown_host(self, size: tuple[int, int] = VIEW) -> Any:
        from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

        host = Quick3DHost(size, qml_dir=self.qml_dir, log=self.log)
        host.show()
        require_ready(host, "a freshly shown host")
        return host


#: How long a driver waits for a host it has just shown. NOT the host's default (1 s, made
#: for the GUI thread): the first expose of a process creates the graphics device — 0.7 to
#: 1.0 s on the dev box, and a CI runner is slower. It costs nothing when nothing comes:
#: ``wait_ready()`` gives up 0.5 s after the last sign of progress, whatever its timeout.
OPEN_TIMEOUT_S = 10.0


def require_ready(host: Any, what: str) -> None:
    """``wait_ready()`` answers; a driver that drops the answer would go on to ask a
    host that is not live for frames (and get a HostStateError far from the cause)."""
    if not host.wait_ready(OPEN_TIMEOUT_S):
        state = host.state.value
        host.close()
        raise RuntimeError(f"{what} did not become live within the timeout "
                           f"(state {state}): no frame can be taken")


def _pump(ms: int = 30) -> None:
    from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    # destroyed Models go now, not at some later turn of the loop
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def _uploads() -> int:
    from open_garden_planner.ui.view3d.quick3d.geometry import BufferGeometry

    return int(BufferGeometry.uploads)


def _parts(host: Any) -> list[dict[str, Any]]:
    return [{"id": p.item_id, "part": p.part_index, "kind": p.kind, "position": list(p.position),
             "yaw": p.yaw_deg, "tint": list(p.tint_rgb), "casts": p.casts_shadow,
             "geometry": p.has_geometry, "visible": p.visible} for p in host.engine_parts()]


def _pick(host: Any, x: float, y: float) -> dict[str, Any]:
    """Click scene (x, y) in the top-down view — aimed with OUR projection — and
    report the hit plus where the ENGINE's projection puts the same point."""
    width, height = host.view_size()
    px, py = top_down_pixel(x, y, TOP, (round(width), round(height)))
    started = time.perf_counter()
    hit = host.pick(px, py)
    elapsed = (time.perf_counter() - started) * 1000.0
    engine_px = host.project(x, y, 0.0)
    return {"x": x, "y": y, "pixel": [px, py], "engine_pixel": list(engine_px),
            "hit": hit.item_id if hit is not None else None,
            "part": hit.part_index if hit is not None else None,
            "point": list(hit.point) if hit is not None else None, "ms": round(elapsed, 3)}


def scenario_truth(ctx: Context) -> dict[str, Any]:
    """G5: where things land in the top-down view (hidden, one host per frame)."""
    out: dict[str, Any] = {"boxes": ctx.offscreen("truth_boxes", truth_records(), shot=TOP,
                                                  sun=HIGH_SUN)}
    for rotation in BAR_ROTATIONS:
        key = f"bar_{rotation:g}"
        out[key] = ctx.offscreen(f"truth_{key}", {"bar": bar_record(rotation)}, shot=TOP,
                                 sun=HIGH_SUN)
    return out


FILL_SQUARE = ((-150.0, -150.0), (150.0, -150.0), (150.0, 150.0), (-150.0, 150.0))
FILL_RGBA = (110, 170, 70, 255)


def _fill_record(item_id: str, east: float, pattern: str) -> Record:
    """A 300 cm raised generic shape with a fill pattern — the kinds #628 made raisable."""
    return Record(item_id=item_id, kind="GENERIC_POLYGON", shape="polygon",
                  footprints=(FILL_SQUARE,), transform=Transform(east_cm=east),
                  material=Material("GENERIC_POLYGON", fill_rgba=FILL_RGBA, pattern=pattern),
                  height_cm=40.0, params=Params({"seed": item_id}))


def scenario_fill(ctx: Context) -> dict[str, Any]:
    """#628 follow-up: a raised object shows the fill the ground bake painted.

    Two 300 cm squares at 40 cm, one GRASS and one SOLID of the same colour: the
    patterned top must vary, the flat twin must not, and both must average the fill
    colour. A second frame fades the patterned one (X-ray): its screen door ghosts in
    the fill colour, not white. The lifetime is measured on a live, never-shown host —
    one picture per (pattern, colour), released with its last user.
    """
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost
    from open_garden_planner.ui.view3d.quick3d.patterns import PatternTexture, textures_alive

    shot = TopDownShot((0.0, 0.0), 0.5)
    records = {"grass": _fill_record("grass", -400.0, "GRASS"),
               "solid": _fill_record("solid", 400.0, "SOLID")}
    top = ctx.offscreen("fill_top", records, shot=shot, sun=SunState(60.0, 180.0),
                        size=(1000, 400), registry=BuilderRegistry())
    faded = ctx.offscreen("fill_faded", records, shot=shot, sun=SunState(60.0, 180.0),
                          size=(1000, 400), registry=BuilderRegistry(), faded=("grass",))

    host = Quick3DHost((320, 200), log=ctx.log)
    sink = Quick3DSink(host)
    part = MeshPart(prism_mesh([FILL_SQUARE], 40.0), "vc", fill_texture=True, name="prism")
    alive0, uploads0 = textures_alive(), PatternTexture.uploads
    lifetime: dict[str, int] = {}
    try:
        if not host.renders_3d():
            raise RuntimeError(f"the fill lifetime needs a 3D backend, got {host.graphics_api()}")
        sink.begin()
        sink.add("lawn", (part,), Transform(),
                 Material("LAWN", fill_rgba=FILL_RGBA, pattern="GRASS"))
        sink.commit()
        lifetime["alive_after_add"] = textures_alive() - alive0
        lifetime["uploads_after_add"] = PatternTexture.uploads - uploads0
        sink.begin()
        sink.update_material("lawn", Material("LAWN", fill_rgba=(120, 60, 30, 255),
                                               pattern="SOIL"))
        sink.commit()
        lifetime["alive_after_recolour"] = textures_alive() - alive0
        lifetime["uploads_after_recolour"] = PatternTexture.uploads - uploads0
        lifetime["geometry_uploads"] = sink.geometry_uploads
        sink.begin()
        sink.remove("lawn")
        sink.commit()
        lifetime["alive_after_remove"] = textures_alive() - alive0
    finally:
        sink.clear()
        host.close()
    return {"top": top, "faded": faded, "lifetime": lifetime}


def scenario_materials(ctx: Context) -> dict[str, Any]:
    """G9 (clean run): every material kind — every shader — rendered, top-down and in
    perspective, hidden. A shader that does not compile raises in ``render_records``."""
    records, registry = swatch_records(), swatch_registry()
    return {
        "top": ctx.offscreen("materials_top", records, shot=TOP, sun=SWATCH_SUN,
                             registry=registry),
        "perspective": ctx.offscreen(
            "materials_perspective", records, registry=registry, sun=SWATCH_SUN,
            shot=PerspectiveShot(eye=(-200.0, -800.0, 450.0), target=(0.0, 0.0, 30.0))),
    }


def scenario_shown_materials(ctx: Context) -> dict[str, Any]:
    """Every material kind — every shader — in a SHOWN window, the way the product will
    draw it: rendered on Qt's render thread, with no recorder in this process. What Qt
    says about it goes to stderr; what the host learned on the GUI thread is in
    ``health``."""
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    host = ctx.shown_host()
    try:
        sync = SceneSync(Quick3DSink(host), swatch_registry())
        sync.apply(swatch_records(), sun=SWATCH_SUN, ground=GROUND)
        host.set_shot(TOP)
        info = ctx.save("shown_materials_top", host.grab("shown_materials_top"))
        _pump(100)
        health = host.health()
        return {"top": info, "parts": len(host.engine_parts()), "graphics_api": host.graphics_api(),
                "health": {"ok": health.ok, "frames_presented": health.frames_presented,
                           "qml_warnings": list(health.qml_warnings),
                           "scene_graph_error": health.scene_graph_error,
                           "slots_off_gui_thread": host.slot_calls_off_the_gui_thread}}
    finally:
        host.close()
        _pump()


def scenario_sun(ctx: Context) -> dict[str, Any]:
    """G7: lit and shaded faces, and where the shadow falls, for three azimuths."""
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    host = ctx.shown_host()
    out: dict[str, Any] = {"azimuths": {}}
    try:
        sync = SceneSync(Quick3DSink(host))
        sync.apply({"caster": caster_record()})
        sync.set_ground(GROUND)
        width, height = host.view_size()
        for azimuth in SUN_AZIMUTHS:
            sync.set_sun(SunState(SUN_ELEVATION, azimuth))
            row: dict[str, Any] = {"faces": {}}
            host.set_shot(TOP)
            row["top"] = ctx.save(f"sun_{azimuth:g}_top", host.grab(f"sun_{azimuth:g}_top"))
            for face in FACE_NORMALS:
                host.set_shot(face_shot(face))
                info = ctx.save(f"sun_{azimuth:g}_{face}", host.grab(f"sun_{azimuth:g}_{face}"))
                hit = host.pick(width / 2.0, height / 2.0)
                info["centre_pick"] = None if hit is None else {
                    "id": hit.item_id, "point": list(hit.point)}
                row["faces"][face] = info
            out["azimuths"][f"{azimuth:g}"] = row
    finally:
        host.close()
        _pump()
    return out


def scenario_edits(ctx: Context) -> dict[str, Any]:
    """G6: move, recolour, replace, remove, re-add, clear, hide/show — one shown host."""
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    host = ctx.shown_host()
    steps: list[dict[str, Any]] = []
    try:
        sink = Quick3DSink(host)
        sync = SceneSync(sink, validate=True)
        host.set_shot(TOP)

        def step(name: str, records: dict[str, Record] | None, *, picks: tuple[str, ...] = (),
                 at: Mapping[str, tuple[float, float]] | None = None) -> None:
            before = _uploads()
            started = time.perf_counter()
            if records is not None:
                sync.apply(records)
            image = host.grab(f"edits_{name}")
            row = ctx.save(f"edits_{name}", image)
            row.update({"name": name, "edit_to_readback_ms": round(
                (time.perf_counter() - started) * 1000.0, 2),
                "uploads_delta": _uploads() - before, "sink_uploads": sink.geometry_uploads,
                "engine_parts": _parts(host), "build_count": sync.build_count, "picks": {}})
            for label in picks:
                x, y = (at or {})[label]
                row["picks"][label] = _pick(host, x, y)
            steps.append(row)
            _pump(10)

        sync.set_ground(GROUND)
        sync.set_sun(HIGH_SUN)
        first, moved = (EDIT_A.transform, EDIT_A_MOVED.transform)
        a0, a1 = (first.east_cm, first.north_cm), (moved.east_cm, moved.north_cm)
        b0 = (EDIT_B.transform.east_cm, EDIT_B.transform.north_cm)
        step("0_add", {"a": EDIT_A, "b": EDIT_B}, picks=("a", "b"), at={"a": a0, "b": b0})
        step("1_move", {"a": EDIT_A_MOVED, "b": EDIT_B}, picks=("a", "old"), at={"a": a1, "old": a0})
        step("2_recolour", {"a": EDIT_A_YELLOW, "b": EDIT_B})
        step("3_replace", {"a": EDIT_A_WIDE, "b": EDIT_B}, picks=("a",), at={"a": a1})
        step("4_remove", {"b": EDIT_B}, picks=("gone", "b"), at={"gone": a1, "b": b0})
        step("5_readd", {"a": EDIT_A_WIDE, "b": EDIT_B}, picks=("a", "b"), at={"a": a1, "b": b0})
        # SceneSync.reset(): it calls the sink's clear() — the engine holds nothing —
        # and the next apply sends everything again
        sync.reset()
        after_clear = ctx.save("edits_6a_cleared", host.grab("edits_6a_cleared"))
        after_clear["engine_parts"] = _parts(host)
        after_clear["sun_up"] = bool(host.scene_property("sunUp"))
        after_clear["ground_visible"] = bool(host.scene_property("groundVisible"))
        sync.set_ground(GROUND)
        sync.set_sun(HIGH_SUN)
        step("6_clear_readd", {"a": EDIT_A_WIDE, "b": EDIT_B}, picks=("a", "b"),
             at={"a": a1, "b": b0})
        steps[-1]["state_equals_expected"] = sink.state() == sync.expected_state()
        host.hide()
        _pump(50)
        started = time.perf_counter()
        host.show()
        require_ready(host, "the re-shown host")
        step("7_reentry", None, picks=("a",), at={"a": a1})
        reentry_ms = (time.perf_counter() - started) * 1000.0
        return {"steps": steps, "cleared": after_clear, "reentry_ms": round(reentry_ms, 1),
                "frames_presented": host.frames_presented}
    finally:
        host.close()
        _pump()


RECOVERY_BEFORE = {"a": EDIT_A, "b": EDIT_B}
RECOVERY_C = box("c", 250.0, 150.0, 120.0, 80.0, 60.0, YELLOW)
RECOVERY_D = box("d", -150.0, -220.0, 80.0, 120.0, 60.0, YELLOW, rotation=25.0)
RECOVERY_AFTER = {"a": EDIT_A_MOVED, "b": EDIT_B, "c": RECOVERY_C, "d": RECOVERY_D}


def _expected_parts(sync: SceneSync) -> list[dict[str, Any]]:
    """What the engine SHOULD hold, from ``sync.expected_state()`` — the reference a
    from-scratch apply gives an empty recording sink (rows like ``_parts``)."""
    rows = []
    for item_id, held in sync.expected_state().items.items():
        pose = engine_pose(held.transform)
        for index, part in enumerate(held.parts):
            if part.mesh.vertex_count:
                tint = part_tint(part, held.material)
                rows.append({"id": item_id, "part": index, "kind": part.material_kind,
                             "position": list(pose.position), "yaw": pose.yaw_deg,
                             "tint": list(tint[:3]), "casts": part.casts_shadow})
    return rows


def scenario_recovery(ctx: Context) -> dict[str, Any]:
    """The L1.1 recipe for a sink, on the REAL engine: one engine call fails in the
    middle of a transaction, ``sync.reset()``, ``sync.apply(...)`` — and what the
    engine holds is compared with ``sync.expected_state()``, and looked at."""
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.quick3d.host import EngineError

    host = ctx.shown_host()
    out: dict[str, Any] = {}
    try:
        sink = Quick3DSink(host)
        sync = SceneSync(sink, validate=True)
        host.set_shot(TOP)
        sync.apply(RECOVERY_BEFORE, sun=HIGH_SUN, ground=GROUND)
        out["before"] = ctx.save("recovery_0_before", host.grab("recovery_before"))
        out["before"]["state_equals_expected"] = sink.state() == sync.expected_state()

        # the engine refuses the SECOND Model of the next transaction: "c" is built,
        # "d" is not, "a" is not moved yet — a transaction applied half way
        real_create = host.create_part
        calls = {"n": 0}

        def refusing(spec: Any, pose: Any, tint: Any) -> object:
            calls["n"] += 1
            if calls["n"] == 2:
                raise EngineError("injected: the engine refused this Model")
            return real_create(spec, pose, tint)

        host.create_part = refusing  # type: ignore[method-assign]
        try:
            sync.apply(RECOVERY_AFTER)
            out["failure"] = "no error"
        except EngineError as error:
            out["failure"] = f"EngineError: {error}"
        finally:
            del host.create_part  # the engine works again
        out["poisoned"] = sync.poisoned
        out["transaction_left_open"] = sink.in_transaction
        try:
            sync.apply(RECOVERY_AFTER)
            out["apply_while_poisoned"] = "applied"
        except Exception as error:  # noqa: BLE001 - recorded, judged by the test
            out["apply_while_poisoned"] = type(error).__name__
        out["half_applied"] = ctx.save("recovery_1_half", host.grab("recovery_half"))
        out["half_applied"]["engine_parts"] = _parts(host)

        sync.reset()
        out["reset"] = {"poisoned": sync.poisoned, "transaction_open": sink.in_transaction,
                        "engine_parts": _parts(host), "sink_items": list(sink.item_ids()),
                        "sun_up": bool(host.scene_property("sunUp")),
                        "ground_visible": bool(host.scene_property("groundVisible"))}
        out["reset"].update(ctx.save("recovery_2_reset", host.grab("recovery_reset")))

        sync.apply(RECOVERY_AFTER, sun=HIGH_SUN, ground=GROUND)
        after = ctx.save("recovery_3_after", host.grab("recovery_after"))
        after.update({"state_equals_expected": sink.state() == sync.expected_state(),
                      "engine_parts": _parts(host), "expected_parts": _expected_parts(sync),
                      "picks": {name: _pick(host, r.transform.east_cm, r.transform.north_cm)
                                for name, r in RECOVERY_AFTER.items()}})
        out["after"] = after
        return out
    finally:
        host.close()
        _pump()


def scenario_pick(ctx: Context) -> dict[str, Any]:
    """G8: the click list of ``pick_plan`` against the engine, top-down."""
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    records = pick_records()
    host = ctx.shown_host()
    try:
        sync = SceneSync(Quick3DSink(host), validate=True)
        sync.apply(records)
        sync.set_ground(GROUND)
        sync.set_sun(HIGH_SUN)
        host.set_shot(TOP)
        frame = ctx.save("pick_scene", host.grab("pick_scene"))
        clicks = []
        for target in pick_plan(records):
            row = _pick(host, target["x"], target["y"])
            row.update(kind=target["kind"], in_box_of=target["in_box_of"])
            clicks.append(row)
        return {"frame": frame, "clicks": clicks, "view_size": list(host.view_size())}
    finally:
        host.close()
        _pump()


def scenario_states(ctx: Context) -> dict[str, Any]:
    """What the host refuses rather than answer wrongly (host.py's state rules)."""
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.quick3d.host import HostStateError, Quick3DHost

    out: dict[str, Any] = {}
    hidden = Quick3DHost(VIEW, qml_dir=ctx.qml_dir, log=ctx.log)
    try:
        sync = SceneSync(Quick3DSink(hidden))
        sync.apply({"a": EDIT_A})
        sync.set_sun(HIGH_SUN)
        hidden.set_shot(TOP)
        try:
            hidden.pick(10.0, 10.0)
            out["hidden_pick"] = "answered"
        except HostStateError as error:
            out["hidden_pick"] = f"HostStateError: {error}"
        out["state_new"] = hidden.state.value
        out["first_hidden_grab"] = ctx.save("states_hidden_first", hidden.grab("hidden_first"))
        out["state_after_offscreen_frame"] = hidden.state.value
        try:
            hidden.grab("hidden_second")
            out["second_hidden_grab"] = "answered"
        except HostStateError as error:
            out["second_hidden_grab"] = f"HostStateError: {error}"
        try:
            hidden.show()
            out["show_after_offscreen_frame"] = "shown"
        except HostStateError as error:
            out["show_after_offscreen_frame"] = f"HostStateError: {error}"
    finally:
        hidden.close()
        _pump()
    shown = ctx.shown_host()
    try:
        SceneSync(Quick3DSink(shown)).apply({"a": EDIT_A})
        shown.set_shot(TOP)
        shown.grab("states_shown")
        out["state_shown"] = shown.state.value
        shown.hide()
        _pump(50)
        out["state_hidden"] = shown.state.value
        try:
            shown.grab("states_hidden_after_show")
            out["grab_while_hidden"] = "answered"
        except HostStateError as error:
            out["grab_while_hidden"] = f"HostStateError: {error}"
        try:
            shown.pick(10.0, 10.0)
            out["pick_while_hidden"] = "answered"
        except HostStateError as error:
            out["pick_while_hidden"] = f"HostStateError: {error}"
    finally:
        shown.close()
        _pump()
    return out


def scenario_rest(ctx: Context) -> dict[str, Any]:
    """P2-11: with the wind at rest (the scene's clock at 0) a vertex is drawn where
    its mesh puts it — also one with the full wind weight, also in a strong wind."""
    from open_garden_planner.ui.view3d.quick3d.look import NEUTRAL_DAY

    windy = replace(NEUTRAL_DAY, wind_strength=REST_WIND)
    return {"wind_strength": REST_WIND,
            "top": ctx.offscreen("rest_top", rest_records(), shot=TOP, sun=HIGH_SUN,
                                 registry=rest_registry(), look=windy)}


def _load_bench() -> tuple[Any, Any, Any]:
    """bench_small.ogp in a real scene + a view (for its undo stack) + the manager."""
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

    scene = CanvasScene()
    manager = ProjectManager()
    manager.load(scene, PLAN)
    view = CanvasView(scene)
    view.set_snap_enabled(False)
    return scene, view, manager


def largest_solids(scene: Any, solid_ids: set[str]) -> tuple[Any, Any]:
    """The two canvas items with the largest footprint among those that have a Model."""
    def area(item: Any) -> float:
        rect = item.sceneBoundingRect()
        return float(rect.width() * rect.height())

    solids = [item for item in scene.items() if str(getattr(item, "item_id", "")) in solid_ids]
    solids.sort(key=lambda item: (-area(item), str(item.item_id)))
    return solids[0], solids[1]


def _recording_summary(sink: RecordingSink) -> dict[str, Any]:
    """What the engine SHOULD hold, from the recording sink: one row per drawable part."""
    rows = []
    for item_id, held in sink.state().items.items():
        pose = engine_pose(held.transform)
        for index, part in enumerate(held.parts):
            if not part.mesh.vertex_count:
                continue
            tint = part_tint(part, held.material)
            rows.append({"id": item_id, "part": index, "kind": part.material_kind,
                         "position": list(pose.position), "yaw": pose.yaw_deg,
                         "tint": list(tint[:3]), "casts": part.casts_shadow})
    return {"items": len(sink.state().items), "parts": rows}


def scenario_integration(ctx: Context) -> dict[str, Any]:
    """§8.10: a real plan → snapshot_records → SceneSync → Quick3DSink → frames, then a
    scripted edit session through the app's own commands; the engine's Models are
    read back after every step, next to what a RecordingSink was told."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor

    from open_garden_planner.core.commands import (
        ChangePropertyCommand,
        DeleteItemsCommand,
        MoveItemsCommand,
    )
    from open_garden_planner.core.fill_patterns import create_pattern_brush
    from open_garden_planner.core.solar import solar_position
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    started = time.perf_counter()
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    scene, view, manager = _load_bench()
    commands = view.command_manager
    at = date(2026, 6, 21)
    location = manager.location or {}
    position = solar_position(float(location["latitude"]), float(location["longitude"]),
                              datetime(2026, 6, 21, 11, 0, tzinfo=UTC))
    sun = SunState.from_solar_position(position)
    ground = GroundSpec(float(scene.width_cm), float(scene.height_cm))
    overview = PerspectiveShot(eye=(ground.width_cm / 2.0, -1400.0, 1500.0),
                               target=(ground.width_cm / 2.0, ground.depth_cm / 2.0, 0.0))
    top = TopDownShot(center=(ground.width_cm / 2.0, ground.depth_cm / 2.0),
                      px_per_cm=VIEW[0] / ground.width_cm * 0.9)

    opened = time.perf_counter()
    host = ctx.shown_host((640, 400))
    steps: list[dict[str, Any]] = []
    try:
        quick = Quick3DSink(host)
        recording = RecordingSink()
        syncs = (SceneSync(quick), SceneSync(recording))

        def tick(name: str, shot: Any = overview) -> dict[str, Any]:
            t0 = time.perf_counter()
            records = snapshot_records(scene, at)
            t1 = time.perf_counter()
            changes = [sync.apply(records) for sync in syncs][0]
            t2 = time.perf_counter()
            host.set_shot(shot)
            image = host.grab(f"integration_{name}")
            t3 = time.perf_counter()
            row = ctx.save(f"integration_{name}", image)
            row.update({
                "name": name, "records": len(records),
                "diff": {"added": len(changes.added), "removed": len(changes.removed),
                         "transform": len(changes.transform), "material": len(changes.material),
                         "geometry": len(changes.geometry)},
                "snapshot_ms": round((t1 - t0) * 1000.0, 2),
                "apply_ms": round((t2 - t1) * 1000.0, 2),
                "grab_ms": round((t3 - t2) * 1000.0, 2),
                "sink_state_equals_recording": quick.state() == recording.state(),
                "engine_parts": _parts(host), "expected": _recording_summary(recording),
                "uploads": _uploads(), "build_failures": len(syncs[0].failures),
            })
            steps.append(row)
            return row

        for sync in syncs:
            sync.set_ground(ground)
            sync.set_sun(sun)
        first = tick("0_open")
        open_ms = (time.perf_counter() - opened) * 1000.0
        tick("0_open_top", top)

        # the items of the session: the two largest solids (the house and its neighbour) —
        # big enough that an edit of them is visible from the overview camera
        target, victim = largest_solids(scene, {p["id"] for p in first["engine_parts"]})
        ids = {"moved": str(target.item_id), "deleted": str(victim.item_id)}

        commands.execute(MoveItemsCommand([target], QPointF(137.25, -42.5)))
        tick("1_move")

        def apply_colour(item: Any, value: QColor) -> None:
            item.fill_color = value
            item.setBrush(create_pattern_brush(item.fill_pattern, value))

        commands.execute(ChangePropertyCommand(target, "fill color", QColor(target.fill_color),
                                               QColor(250, 30, 200), apply_colour))
        tick("2_recolour")
        commands.execute(DeleteItemsCommand(scene, [victim]))
        tick("3_delete")
        commands.undo()
        tick("4_undo_delete")
        commands.undo()
        commands.undo()
        tick("5_undo_all")

        # edit-to-readback: 30 moves of one item (ADR-048 entries 5/6, moved here by ADR-059)
        loop: list[dict[str, float]] = []
        for index in range(30):
            delta = QPointF(3.0 if index % 2 == 0 else -3.0, 0.0)
            t0 = time.perf_counter()
            commands.execute(MoveItemsCommand([target], delta))
            records = snapshot_records(scene, at)
            t1 = time.perf_counter()
            for sync in syncs:
                sync.apply(records)
            t2 = time.perf_counter()
            host.grab("edit_loop")
            t3 = time.perf_counter()
            loop.append({"snapshot": (t1 - t0) * 1000.0, "apply": (t2 - t1) * 1000.0,
                         "grab": (t3 - t2) * 1000.0, "total": (t3 - t0) * 1000.0})
        totals = sorted(row["total"] for row in loop)
        return {
            "steps": steps, "ids": ids, "plan": PLAN.name,
            "sun": {"elevation": sun.elevation_deg, "azimuth": sun.azimuth_deg},
            "open_ms": round(open_ms, 1), "qml_load_ms": round(host.qml_load_ms, 1),
            "load_plan_ms": round((opened - started) * 1000.0, 1),
            "edit_to_readback_ms": {
                "n": len(totals), "median": round(statistics.median(totals), 2),
                "p95": round(totals[int(0.95 * (len(totals) - 1))], 2), "max": round(totals[-1], 2),
                "median_snapshot": round(statistics.median(r["snapshot"] for r in loop), 2),
                "median_apply": round(statistics.median(r["apply"] for r in loop), 2),
                "median_grab": round(statistics.median(r["grab"] for r in loop), 2)},
            "graphics_api": host.graphics_api(),
        }
    finally:
        host.close()
        _pump()


def scenario_embed(ctx: Context) -> dict[str, Any]:
    """G12: does a 3D container beside the 2D canvas put the main window on RHI
    composition? The top-level window's surface type says so directly; the 2D pan
    step (incl. flush — ``processEvents``, never ``repaint()``) is what it would cost."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QApplication, QMainWindow, QSplitter, QWidget

    from open_garden_planner.ui.canvas.canvas_view import CanvasView
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.quick3d.host import QML_DIR, Quick3DHost
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    scene, _view, _manager = _load_bench()
    records = snapshot_records(scene, date(2026, 6, 21))
    app = QApplication.instance()
    assert app is not None

    def run(mode: str, steps: int) -> dict[str, Any]:
        window = QMainWindow()
        splitter = QSplitter()
        canvas = CanvasView(scene)
        splitter.addWidget(canvas)
        host: Any = None
        control: Any = None
        if mode == "container":
            host = Quick3DHost((480, 540), qml_dir=ctx.qml_dir, log=ctx.log)
            sync = SceneSync(Quick3DSink(host))
            sync.apply(records)
            sync.set_ground(GroundSpec(float(scene.width_cm), float(scene.height_cm)))
            sync.set_sun(HIGH_SUN)
            host.set_shot(PerspectiveShot(eye=(1200.0, -1400.0, 1500.0), target=(1200.0, 800.0, 0.0)))
            splitter.addWidget(host.container())
        elif mode == "quickwidget":
            # POSITIVE CONTROL only — the host ADR-048 rejected. The engine package never
            # imports QtQuickWidgets; this test file does, to show the gate can fire.
            from PyQt6.QtQuickWidgets import QQuickWidget

            control = QQuickWidget()
            control.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            control.setSource(QUrl.fromLocalFile(str((ctx.qml_dir or QML_DIR) / "Garden.qml")))
            splitter.addWidget(control)
        else:
            splitter.addWidget(QWidget())
        window.setCentralWidget(splitter)
        window.resize(1200, 600)
        window.show()
        frame_ok = None
        if host is not None:
            host.show()
            require_ready(host, "the embedded host")
            frame = host.grab(f"embed_{mode}")
            frame_ok = ctx.save("embed_container", frame)
        _pump(300)
        canvas.fit_in_view()
        canvas.set_zoom(canvas.zoom_factor * 4.0)
        bar = canvas.horizontalScrollBar()
        low, high = bar.minimum(), bar.maximum()
        times = []
        for k in range(steps):
            t0 = time.perf_counter()
            bar.setValue(low + (high - low) * ((k * 7) % steps) // max(steps - 1, 1))
            canvas.viewport().update()
            app.processEvents()
            app.processEvents()
            times.append((time.perf_counter() - t0) * 1000.0)
        handle = window.windowHandle()
        surface = handle.surfaceType().name if handle is not None else "none"
        window.close()
        if host is not None:
            host.close()
        window.deleteLater()
        _pump(100)
        ordered = sorted(times)
        return {"mode": mode, "steps": steps, "surface": surface, "frame": frame_ok,
                "median_ms": round(statistics.median(times), 3),
                "p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 3),
                "max_ms": round(ordered[-1], 3)}

    rounds = [run("plain", 120), run("container", 120), run("plain", 120), run("container", 120)]
    plain = statistics.median(r["median_ms"] for r in rounds if r["mode"] == "plain")
    container = statistics.median(r["median_ms"] for r in rounds if r["mode"] == "container")
    control = run("quickwidget", 20)
    return {"rounds": rounds, "control": control, "plain_median_ms": round(plain, 3),
            "container_median_ms": round(container, 3),
            "ratio": round(container / plain, 3) if plain > 0 else None,
            "control_ratio": round(control["median_ms"] / plain, 3) if plain > 0 else None}


SCENARIOS: dict[str, Callable[[Context], dict[str, Any]]] = {
    "truth": scenario_truth,
    "materials": scenario_materials,
    "fill": scenario_fill,
    "sun": scenario_sun,
    "edits": scenario_edits,
    "pick": scenario_pick,
    "states": scenario_states,
    "rest": scenario_rest,
    "recovery": scenario_recovery,
    "shown_materials": scenario_shown_materials,
    "integration": scenario_integration,
    "embed": scenario_embed,
}


def _isolate_settings() -> None:
    """Loading a plan records Recent Files: never in the developer's own store (the
    redirection ``tests/conftest.py`` performs for the test process). Done HERE as
    well as by the start-up hook the tests hand every child (``quick3d_child_site``):
    this file is also run by hand, and must be safe by itself."""
    import open_garden_planner.app.settings as app_settings

    app_settings.ORGANIZATION_NAME = "cofade_test"
    app_settings.APPLICATION_NAME = f"Open Garden Planner Render Tier {os.getpid()}"


def _clear_settings() -> None:
    import open_garden_planner.app.settings as app_settings

    app_settings.create_qsettings().clear()


def _isolate_app_data(out: Path) -> None:
    """Run by hand — not through the tests' ``isolated_env`` — this file still must not
    touch the developer's data: loading a plan opens the app's data directory (the
    custom-plant library), and ``get_app_data_dir`` reads these variables on every
    call. Point them into the output directory.

    What this cannot move from inside a running process is the user PROFILE (Qt's
    QML and shader caches), nor macOS's data directory (it hangs on the home
    directory): to keep those out of your profile, start the driver the way the
    tests do (``quick3d_render_support.run_driver``)."""
    from tests.integration.quick3d_render_support import ISOLATED_MARK, private_dirs

    if os.environ.get(ISOLATED_MARK) != "1":
        os.environ.update(private_dirs(out / "private"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenarios", required=True)
    parser.add_argument("--qml-dir", type=Path, default=None)
    parser.add_argument("--watchdog-s", type=float, default=900.0)
    args = parser.parse_args(argv)
    wanted = args.scenarios.split(",")
    unknown = [name for name in wanted if name not in SCENARIOS]
    if unknown:
        parser.error(f"unknown scenarios {unknown}; choose from {sorted(SCENARIOS)}")
    args.out.mkdir(parents=True, exist_ok=True)
    _isolate_app_data(args.out)  # before anything of the app can ask where its data is
    _isolate_settings()          # before anything of the app can build a settings store

    from PyQt6.QtCore import QT_VERSION_STR

    started = time.perf_counter()
    import open_garden_planner.ui.view3d.quick3d.host  # noqa: F401 - timed: the engine import
    engine_import_ms = (time.perf_counter() - started) * 1000.0
    from open_garden_planner.ui.view3d.quick3d import offscreen

    log = offscreen.RenderLog(args.out / "render.log")
    result: dict[str, Any] = {
        "status": "running", "platform": platform.platform(), "python": sys.version.split()[0],
        "qt": QT_VERSION_STR, "engine_import_ms": round(engine_import_ms, 1),
        "qml_dir": str(args.qml_dir) if args.qml_dir else None,
        "env": {key: os.environ.get(key) for key in (
            "QT_QPA_PLATFORM", "QSG_RHI_BACKEND", "QSG_RHI_PREFER_SOFTWARE_RENDERER",
            "LIBGL_ALWAYS_SOFTWARE", "QSG_RENDER_LOOP", "QT_MESSAGE_PATTERN", "APPDATA",
            "XDG_DATA_HOME")},
        "scenarios": {},
    }

    def write() -> None:
        (args.out / "result.json").write_text(json.dumps(result, indent=1, default=str),
                                              encoding="utf-8")

    code = 0
    try:
        # supervised: this process shows windows, and a deadlock between Qt's render thread
        # and the GUI thread is exactly what the in-process watchdog cannot end on Windows
        with offscreen.watchdog(args.watchdog_s, log, what="the render driver", supervised=True):
            offscreen.ensure_application()
            context = Context(args.out, log, args.qml_dir.resolve() if args.qml_dir else None)
            log("start", scenarios=args.scenarios, qt=QT_VERSION_STR, platform=result["platform"])
            for name in wanted:
                log("scenario", name=name)
                # the judge reads Qt's messages from stderr: say which scenario they belong to
                print(f"OGPQT|scenario|{name}", file=sys.stderr, flush=True)
                t0 = time.perf_counter()
                data = SCENARIOS[name](context)
                data["seconds"] = round(time.perf_counter() - t0, 2)
                result["scenarios"][name] = data
                write()
            print("OGPQT|scenario|", file=sys.stderr, flush=True)
        result["status"] = "ok"
    except Exception as error:  # noqa: BLE001 - a driver: record it, never lose it
        result["status"] = "error"
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()
        # a render that failed on Qt's messages carries the recorder's report
        result["error_qt"] = dict(getattr(error, "qt", None) or {})
        log("error", error=result["error"])
        code = QT_ERRORS_EXIT if type(error).__name__ == "RenderError" else 2
    finally:
        result["total_s"] = round(time.perf_counter() - started, 2)
        write()
        log("done", status=result["status"], total_s=result["total_s"])
        log.close()
        with contextlib.suppress(Exception):  # a key that cannot be emptied fails no render
            _clear_settings()  # the test key of this process — also after a scenario that failed
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
