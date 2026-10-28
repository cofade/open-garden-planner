"""The engine-side half of the selection / walk render tier (Phase 17 L1.8) — not a test module.

Started by ``test_view3d_selection_render.py`` with a real QPA (the test process is
``offscreen``, where nothing 3D is drawn)::

    python tests/integration/view3d_selection_driver.py --out <dir> --scenarios ring,pick,…

The division of labour is the engine story's (``quick3d_render_driver.py``, whose
context, log and isolation this file reuses): the driver only DOES — it drives the
real ``Quick3DHost`` / the real ``Workspace``, saves frames and writes raw engine
answers to ``result.json``; the tests JUDGE, with a camera model, a projection and a
ray caster of their own (``core/scene3d/pick_oracle.py``). The scene definitions
below are plain engine-free functions both halves import.

Exit codes: 0 ok · 1 watchdog · 2 an exception · 4 a render that failed on a Qt error.
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
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":  # run as a script: make this checkout's code importable
    for entry in (str(REPO / "src"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

from open_garden_planner.core.scene3d import (  # noqa: E402
    GroundSpec,
    Material,
    Params,
    Record,
    SceneSync,
    SunState,
    Transform,
)
from open_garden_planner.core.scene3d.builders import production_registry  # noqa: E402
from open_garden_planner.core.scene3d.camera import Bounds, CameraPose, frame_pose  # noqa: E402
from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot, TopDownShot  # noqa: E402
from tests.integration.quick3d_render_driver import (  # noqa: E402
    OPEN_TIMEOUT_S,
    QT_ERRORS_EXIT,
    Context,
    _clear_settings,
    _isolate_app_data,
    _isolate_settings,
    _pump,
)
from tests.integration.workspace_render_state import (  # noqa: E402
    save_held_oracle,
    workspace_settled,
)

PLANS = REPO / "tests" / "fixtures" / "plans"
JUNE = date(2026, 6, 21)
HIGH_SUN = SunState(elevation_deg=60.0, azimuth_deg=180.0)

# ── scene definitions (engine-free; the tests import them) ───────────────────

RING_VIEW = (640, 480)                                  # logical pixels
RING_TOP = TopDownShot(center=(0.0, 0.0), px_per_cm=0.5)   # 1280 x 960 cm, north up
RING_GROUND = GroundSpec(width_cm=3000.0, depth_cm=3000.0)
RED, YELLOW, GREY, BROWN = (200, 40, 30, 255), (230, 200, 40, 255), (170, 170, 170, 255), (130, 90, 50, 255)
GREEN = (60, 140, 50, 255)


def rect(width: float, depth: float) -> tuple[tuple[float, float], ...]:
    half_w, half_d = width / 2.0, depth / 2.0
    return ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))


def circle(radius: float, corners: int = 24) -> tuple[tuple[float, float], ...]:
    return tuple((round(radius * math.cos(2 * math.pi * k / corners), 7),
                  round(radius * math.sin(2 * math.pi * k / corners), 7)) for k in range(corners))


def record(item_id: str, kind: str, east: float, north: float, ring, *, height: float | None,
           colour=GREY, rotation: float = 0.0, base: float = 0.0, holes: tuple = (),
           shape: str = "polygon", params: Mapping[str, Any] | None = None,
           parent: str | None = None, path=(), width: float | None = None) -> Record:
    return Record(
        item_id=item_id, kind=kind, shape=shape, footprints=(ring,), holes=holes,
        transform=Transform(east, north, rotation, base),
        material=Material(kind, fill_rgba=colour, stroke_rgba=colour), height_cm=height,
        path=path, path_width_cm=width, params=Params({"seed": item_id, **(params or {})}),
        parent_id=parent)


BED_HEIGHT, BED_SOIL = 40.0, 38.0


def ring_records() -> dict[str, Record]:
    """Gate G4's four: a turned rectangle, a polygon with a hole, a circle, and a plant
    standing on a raised bed (at the bed's soil height) — plus one item that is never
    selected. No kind here is drawn blue: what is blue in a frame is the ring."""
    hole = tuple(reversed(rect(140.0, 90.0)))
    return {
        "box": record("box", "GARAGE_SHED", -420.0, 280.0, rect(220.0, 140.0), height=120.0,
                      colour=RED, rotation=25.0, shape="rectangle"),
        "yard": record("yard", "COMPOST_BIN", 330.0, 290.0, rect(260.0, 200.0), height=60.0,
                       colour=YELLOW, holes=((hole,),)),
        "disc": record("disc", "RAIN_BARREL", -380.0, -260.0, circle(110.0), height=90.0,
                       colour=GREY, shape="circle", params={"radius_cm": 110.0}),
        "bed": record("bed", "RAISED_BED", 300.0, -250.0, rect(360.0, 200.0), height=BED_HEIGHT,
                      colour=BROWN, shape="rectangle"),
        "plant": record("plant", "PERENNIAL", 360.0, -230.0, circle(45.0), height=70.0,
                        colour=GREEN, shape="circle", base=BED_SOIL, parent="bed",
                        params={"radius_cm": 45.0, "plant_category": "PERENNIAL"}),
        "other": record("other", "TOOL_SHED", -40.0, 20.0, rect(120.0, 120.0), height=100.0,
                        colour=RED, shape="rectangle"),
    }


RING_SELECTED = ("box", "yard", "disc", "plant")
#: The perspective look at the plant on its bed: from the south-west, 35 degrees down.
RING_PERSPECTIVE = PerspectiveShot(eye=(-150.0, -820.0, 480.0), target=(340.0, -240.0, 40.0))

WALL_LENGTH, WALL_STROKE = 500.0, 5.0


def wall_record(item_id: str = "wall", east: float = 0.0, north: float = 0.0,
                length: float = WALL_LENGTH, height: float = 180.0,
                rotation: float = 0.0) -> Record:
    """A WALL as the snapshot gives it: a centre line, a stroke of 5 cm — and the
    built world makes 30 cm of masonry of it (``builders/walls.py``)."""
    half = length / 2.0
    return record(item_id, "WALL", east, north, rect(length, WALL_STROKE), height=height,
                  colour=GREY, shape="polyline", path=((-half, 0.0), (half, 0.0)),
                  width=WALL_STROKE, rotation=rotation)


# ── picking (gate G1) ────────────────────────────────────────────────────────

PICK_VIEW = (960, 600)
PICK_PLANS = {"bench_small": "bench_small.ogp", "edge_cases": "scene3d_edge_cases.ogp"}
#: Screen points tried per plan, in seeded order (the judge takes the first twenty
#: that are no edge case of rasterisation, plus the named ones).
PICK_CANDIDATES = 400
PICK_SEED = 385_108


def pick_camera(width_cm: float, depth_cm: float, top_cm: float) -> PerspectiveShot:
    """The orbit camera's own framing of the plan (``core.scene3d.camera.frame_pose``),
    tilted low enough that the upper part of the view is sky."""
    pose = frame_pose(Bounds.of_plan(width_cm, depth_cm, top_cm), PICK_VIEW[0] / PICK_VIEW[1],
                      pitch_deg=16.0)
    closer = CameraPose(pose.target, pose.distance_cm * 0.8, pose.yaw_deg, pose.pitch_deg)
    return PerspectiveShot(eye=closer.eye, target=closer.target_scene)


def seeded_points(count: int = PICK_CANDIDATES, seed: int = PICK_SEED,
                  view: tuple[int, int] = PICK_VIEW) -> list[tuple[float, float]]:
    """``count`` view positions, uniform over the view, from a fixed seed."""
    import random

    rng = random.Random(seed)
    return [(round(rng.uniform(4.0, view[0] - 4.0), 2), round(rng.uniform(4.0, view[1] - 4.0), 2))
            for _ in range(count)]


def load_plan(name: str) -> tuple[Any, Any, Any]:
    """A fixture plan in a real scene + a view (its undo stack) + the manager."""
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

    scene = CanvasScene()
    manager = ProjectManager()
    manager.load(scene, PLANS / PICK_PLANS[name])
    view = CanvasView(scene)
    view.set_snap_enabled(False)
    return scene, view, manager


def plan_records(scene: Any) -> dict[str, Record]:
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    return snapshot_records(scene, JUNE)


def plan_top(records: Mapping[str, Record]) -> float:
    return max((r.transform.base_cm + r.height_cm for r in records.values()
                if r.height_cm is not None), default=0.0)


# ── standing against a wall: the near plane ──────────────────────────────────

LOOK_VIEW = (640, 480)
LOOK_PLAN = (2000.0, 2000.0)
MAGENTA = (235, 30, 200, 255)
LOOK_NORTH_WALL, LOOK_EAST_WALL = 1200.0, 1300.0        # the two walls' centre lines
LOOK_YAWS = tuple(float(yaw) for yaw in range(0, 360, 15))
LOOK_PITCHES = (-35.0, 0.0, 35.0)
LOOK_EYES = (165.0, 110.0)


def look_records() -> dict[str, Record]:
    """An inside corner of two walls 180 cm high and, behind each of them, a magenta
    block 140 cm high. From anywhere inside the corner every line of sight to a block
    crosses its wall within the wall's length and below its top (the eye is at most
    165 cm, the block 140 cm): nothing magenta can be in a frame taken there unless
    the camera looks THROUGH masonry."""
    return {
        "north_wall": wall_record("north_wall", 900.0, LOOK_NORTH_WALL, length=800.0),
        "east_wall": wall_record("east_wall", LOOK_EAST_WALL, 800.0, length=800.0, rotation=90.0),
        "behind_north": record("behind_north", "GARAGE_SHED", 900.0, 1360.0, rect(400.0, 120.0),
                               height=140.0, colour=MAGENTA, shape="rectangle"),
        "behind_east": record("behind_east", "GARAGE_SHED", 1460.0, 800.0, rect(120.0, 400.0),
                              height=140.0, colour=MAGENTA, shape="rectangle"),
    }


# ── the real workspace on the real engine (gates G2 and G7, one row each) ────

WORKSPACE_WINDOW = (1400, 820)
WORKSPACE_CLICKS = 80
WORKSPACE_SEED = 385_208
WALK_HOLD_MS = 700


# ── the engine side ──────────────────────────────────────────────────────────


def _sink(host: Any) -> Any:
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink

    return Quick3DSink(host)


def _ring_counters(host: Any) -> dict[str, Any]:
    from open_garden_planner.ui.view3d.quick3d.geometry import BufferGeometry, ReloadableGeometry

    return {"ring_loads": host.ring_loads, "reloadable_loads": int(ReloadableGeometry.loads),
            "ring_geometries": int(ReloadableGeometry.created),
            "model_uploads": int(BufferGeometry.uploads), "parts": host.part_count(),
            "engine_parts": len(host.engine_parts()),
            "ring_visible": bool(host.scene_property("selectionVisible"))}


def scenario_ring(ctx: Context) -> dict[str, Any]:
    """Gate G4: the ring where the footprint is — top-down (the truth view), then one
    perspective look at the plant on its bed; and what a selection change costs the
    engine in objects (the counters around every step)."""
    host = ctx.shown_host(RING_VIEW)
    out: dict[str, Any] = {"steps": []}
    try:
        sink = _sink(host)
        sync = SceneSync(sink, production_registry())
        records = ring_records()
        sync.apply(records, sun=HIGH_SUN, ground=RING_GROUND)
        host.set_shot(RING_TOP)

        def step(name: str, ids: tuple[str, ...]) -> None:
            before = _ring_counters(host)
            sent = sync.set_selection(ids)
            row = ctx.save(f"ring_{name}", host.grab(f"ring_{name}"))
            row.update({"name": name, "ids": list(ids), "sent": sent, "before": before,
                        "after": _ring_counters(host), "sink_ring_uploads": sink.ring_uploads,
                        "sink_geometry_uploads": sink.geometry_uploads})
            out["steps"].append(row)
            _pump(10)

        step("none", ())
        step("all", RING_SELECTED)
        for item_id in RING_SELECTED:
            step(item_id, (item_id,))
        step("cleared", ())
        # twenty more changes: what steady use creates and destroys
        before = _ring_counters(host)
        for index in range(20):
            sync.set_selection(RING_SELECTED[: 1 + index % 4])
            host.grab("ring_steady")
        out["steady"] = {"before": before, "after": _ring_counters(host)}
        # a selected item that moves takes its ring along, in the move's transaction
        sync.set_selection(("box",))
        moved = {**records, "box": record("box", "GARAGE_SHED", -300.0, 150.0, rect(220.0, 140.0),
                                         height=120.0, colour=RED, rotation=70.0,
                                         shape="rectangle")}
        before = _ring_counters(host)
        sync.apply(moved)
        row = ctx.save("ring_moved", host.grab("ring_moved"))
        row.update({"before": before, "after": _ring_counters(host)})
        out["moved"] = row
        sync.apply(records)
        # the perspective look at the plant on the bed
        sync.set_selection(("plant",))
        host.set_shot(RING_PERSPECTIVE)
        out["perspective"] = ctx.save("ring_perspective", host.grab("ring_perspective"))
        sync.set_selection(())
        out["perspective_none"] = ctx.save("ring_perspective_none",
                                           host.grab("ring_perspective_none"))
        out["view_size"] = list(host.view_size())
        out["state_equals_expected"] = sink.state() == sync.expected_state()
        return out
    finally:
        host.close()
        _pump()


def scenario_ring_depth(ctx: Context) -> dict[str, Any]:
    """Why the ring is drawn in front (``ringDepthScale``): a wall is built 30 cm thick
    on a 5 cm stroke, so a depth-tested ring along the stroke lies INSIDE the masonry.
    The same frame twice, from above: the shipped scale, and 1.0 (depth-tested)."""
    host = ctx.shown_host(RING_VIEW)
    out: dict[str, Any] = {}
    try:
        sync = SceneSync(_sink(host), production_registry())
        sync.apply({"wall": wall_record()}, sun=HIGH_SUN, ground=RING_GROUND)
        sync.set_selection(("wall",))
        host.set_shot(RING_TOP)
        out["shipped_scale"] = float(host.scene_property("ringDepthScale"))
        out["graphics_api"] = host.graphics_api()
        out["in_front"] = ctx.save("ring_depth_in_front", host.grab("ring_depth_in_front"))
        host._root.setProperty("ringDepthScale", 1.0)  # noqa: SLF001 - the control of this probe
        out["depth_tested"] = ctx.save("ring_depth_tested", host.grab("ring_depth_tested"))
        return out
    finally:
        host.close()
        _pump()


def scenario_pick(ctx: Context) -> dict[str, Any]:
    """Gate G1: the engine's answer at every seeded view position (and at the judge's
    named ones), for both plans, from the orbit camera's own framing."""
    out: dict[str, Any] = {}
    for name in PICK_PLANS:
        scene, _view, _manager = load_plan(name)
        records = plan_records(scene)
        shot = pick_camera(float(scene.width_cm), float(scene.height_cm), plan_top(records))
        host = ctx.shown_host(PICK_VIEW)
        try:
            sink = _sink(host)
            sync = SceneSync(sink, production_registry())
            sync.apply(records, sun=HIGH_SUN,
                       ground=GroundSpec(float(scene.width_cm), float(scene.height_cm)))
            host.set_shot(shot)
            frame = ctx.save(f"pick_{name}", host.grab(f"pick_{name}"))
            points = seeded_points() + named_points(name, records, shot)
            hits = []
            started = time.perf_counter()
            for x, y in points:
                hit = host.pick(x, y)
                hits.append(None if hit is None else {
                    "id": hit.item_id, "part": hit.part_index, "point": list(hit.point),
                    "behind": [later.item_id for later in hit.behind]})
            out[name] = {
                "frame": frame, "points": [list(p) for p in points], "hits": hits,
                "ms_per_pick": round((time.perf_counter() - started) * 1000.0 / len(points), 4),
                "view_size": list(host.view_size()), "records": len(records),
                "models": host.part_count(), "build_failures": sorted(sync.failures),
                "shot": {"eye": list(shot.eye), "target": list(shot.target), "fov": shot.fov_deg},
            }
        finally:
            host.close()
            _pump()
    return out


def named_points(name: str, records: Mapping[str, Record],
                 shot: PerspectiveShot) -> list[tuple[float, float]]:
    """The view positions gate G1 names — computed by the JUDGE's own projection, here
    only so that the engine is asked at them too (``pick_targets`` in the test module
    recomputes them and checks they are the same)."""
    from tests.integration.view3d_selection_support import named_pick_points

    return [point for _label, point in named_pick_points(name, records, shot)]


def scenario_lookthrough(ctx: Context) -> dict[str, Any]:
    """Standing against a wall does not look through it. The walk core itself takes
    the walker there — north until the wall stops it, then into the inside corner of
    two — and from both places it looks all round, up and down, at two eye heights.
    The driver counts magenta pixels per frame (the judge's mask) and keeps the level
    adult frames every 45 degrees, every frame with magenta in it, and two controls:
    the block seen from above, and an eye put INSIDE the near distance of the wall."""
    from open_garden_planner.core.scene3d import walk
    from tests.integration.view3d_selection_support import builder_parts, image_rgb, marker_mask

    records = look_records()
    world = walk.build_world(records, *LOOK_PLAN, parts_of=builder_parts)
    state = walk.start_state(world, (900.0, 900.0), 0.0)
    assert state is not None
    for _ in range(1200):                                   # ten seconds to the north
        state = walk.advance(state, walk.WalkCommand(forward=1.0), walk.TICK_S, world)
    at_wall = state.shown
    for _ in range(1200):                                   # ten more, to the north-east
        state = walk.advance(state, walk.WalkCommand(forward=1.0, strafe=1.0), walk.TICK_S, world)
    in_corner = state.shown
    host = ctx.shown_host(LOOK_VIEW)
    out: dict[str, Any] = {"at_wall": list(at_wall), "in_corner": list(in_corner), "looks": [],
                           "segments": len(world.segments)}
    try:
        sync = SceneSync(_sink(host), production_registry())
        sync.apply(records, sun=HIGH_SUN, ground=GroundSpec(*LOOK_PLAN))
        out["view_size"] = list(host.view_size())

        def look(name: str, spot: tuple[float, float], eye_cm: float, yaw: float, pitch: float,
                 *, keep: bool = False) -> dict[str, Any]:
            pose = walk.WalkState(spot[0], spot[1], yaw, pitch, 0.0, (spot[0], spot[1]))
            host.set_camera(walk.eye_scene(pose, eye_cm), walk.look_target_scene(pose, eye_cm),
                            walk.WALK_FOV_DEG)
            image = host.grab(name)
            row: dict[str, Any] = {"name": name, "at": [spot[0], spot[1]], "eye_cm": eye_cm,
                                   "yaw": yaw, "pitch": pitch,
                                   "magenta": int(marker_mask(image_rgb(image)).sum())}
            if keep or row["magenta"]:
                row.update(ctx.save(name, image))
            return row

        for place, spot in (("wall", at_wall), ("corner", in_corner)):
            for eye_cm in LOOK_EYES:
                for pitch in LOOK_PITCHES:
                    for yaw in LOOK_YAWS:
                        keep = eye_cm == LOOK_EYES[0] and pitch == 0.0 and yaw % 45.0 == 0.0
                        out["looks"].append(look(
                            f"look_{place}_{eye_cm:.0f}_{pitch:+.0f}_{yaw:03.0f}", spot, eye_cm,
                            yaw, pitch, keep=keep))
        # control 1: the block IS magenta in a frame — seen from its own side of the wall
        host.set_camera((900.0, 1800.0, 165.0), (900.0, 1360.0, 70.0), walk.WALK_FOV_DEG)
        image = host.grab("look_control_above")
        out["control_above"] = {**ctx.save("look_control_above", image),
                                "magenta": int(marker_mask(image_rgb(image)).sum())}
        # control 2: an eye 2 cm in front of the masonry — nearer than the near plane
        body_face = LOOK_NORTH_WALL - 15.0
        out["control_too_close"] = look("look_control_too_close", (900.0, body_face - 2.0), 100.0,
                                        0.0, 0.0, keep=True)
        return out
    finally:
        host.close()
        _pump()


def _spin(turns: int = 20) -> None:
    from PyQt6.QtCore import QCoreApplication

    for _ in range(turns):
        QCoreApplication.processEvents()


def _spin_until(condition: Callable[[], bool], timeout_s: float = 10.0) -> bool:
    from PyQt6.QtCore import QCoreApplication

    end = time.perf_counter() + timeout_s
    while time.perf_counter() < end:
        if condition():
            return True
        QCoreApplication.processEvents()
    return bool(condition())


def _camera_facts(host: Any) -> dict[str, Any]:
    """The camera the ENGINE holds (root properties of ``Garden.qml``, engine frame)."""
    def vector(name: str) -> list[float]:
        value = host.scene_property(name)
        return [round(float(value.x()), 4), round(float(value.y()), 4), round(float(value.z()), 4)]

    return {"pos": vector("camPos"), "target": vector("camTarget"),
            "fov": float(host.scene_property("camFov")),
            "top_down": bool(host.scene_property("topDown"))}


def scenario_workspace(ctx: Context) -> dict[str, Any]:
    """The real ``Workspace`` around a real canvas with ``bench_small.ogp``, on the real
    engine (its own factory — nothing replaced). One row each of gates G2 and G7:

    - real mouse clicks in the 3D window (``QTest.mouseClick`` on the ``QQuickView``)
      at seeded positions → what the CANVAS has selected after each; Ctrl and Shift;
    - the ring of a clicked item, in a frame (and the same frame with nothing selected);
    - selection → the pass that hands the real engine its ring: timed with NO readback
      in the loop (one frame is taken after it);
    - walk mode with real key events: enter, hold W, look with a drag, leave — the
      engine's camera before and after, and the frames; then hide and show while walking.
    """
    import random
    from datetime import datetime
    from datetime import time as clock_time

    from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QGraphicsItem, QVBoxLayout, QWidget

    from open_garden_planner.core.scene3d.camera import FOV_DEG
    from open_garden_planner.core.sim_clock import SimClock
    from open_garden_planner.ui.canvas.items.group_item import GroupItem
    from open_garden_planner.ui.view3d.init_guard import Init3DGuard
    from open_garden_planner.ui.view3d.quick3d.geometry import BufferGeometry, ReloadableGeometry
    from open_garden_planner.ui.view3d.workspace import Workspace, WorkspaceMode

    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    plain, ctrl, shift = (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ControlModifier,
                          Qt.KeyboardModifier.ShiftModifier)
    scene, view, _manager = load_plan("bench_small")
    commands = view.command_manager
    window = QWidget()
    window.resize(*WORKSPACE_WINDOW)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    guard_dir = ctx.out / "guard"
    guard_dir.mkdir(exist_ok=True)
    workspace = Workspace(view, guard=Init3DGuard(guard_dir, is_running=lambda _pid: False))
    workspace.connect_plan(scene, SimClock(datetime.combine(JUNE, clock_time(12, 0))),
                           lambda: None, commands, None)
    layout.addWidget(workspace)
    from PyQt6.QtCore import Qt
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    window.setWindowFlags(window.windowFlags() | Qt.WindowType.WindowDoesNotAcceptFocus)
    window.move(-20000, -20000)
    window.show()
    _pump(200)
    out: dict[str, Any] = {}

    def selected() -> list[str]:
        return sorted(str(item.item_id) for item in scene.selectedItems())

    try:
        scene.clearSelection()
        workspace.set_mode(WorkspaceMode.SPLIT)
        if not _spin_until(lambda: workspace.host is not None and workspace.controller is not None, 30.0):
            raise RuntimeError(f"the workspace did not start its engine: {workspace.view3d_state}")
        host, controller = workspace.host, workspace.controller
        assert host is not None and controller is not None
        # A paused nonzero shader clock still displaces leaves. The CPU ray oracle
        # judges admitted mesh positions, so these still-picture tests require rest.
        workspace._look.set_reduced_motion(True)
        host.rest_wind()
        if not host.wait_ready(OPEN_TIMEOUT_S):
            raise RuntimeError(f"the workspace's host is not live: {host.state.value}")
        _spin_until(lambda: controller.apply_count >= 1 and not controller.dirty, 30.0)
        _spin_until(lambda: not workspace.camera.moving, 10.0)
        assert _spin_until(lambda: workspace_settled(workspace), 60.0), "forge/LOD did not settle"
        quick_view = host._view  # noqa: SLF001 - the native window a user clicks in
        records = dict(controller.sync.records)
        pose = workspace.camera.pose
        width, height = host.view_size()
        on_canvas = [item for item in scene.items() if str(getattr(item, "item_id", "")) in records]
        out.update({
            "view_size": [width, height], "records": len(records), "models": host.part_count(),
            "shot": {"eye": list(pose.eye), "target": list(pose.target_scene), "fov": FOV_DEG},
            "camera": _camera_facts(host), "build_failures": sorted(controller.sync.failures),
            "plan_facts": {
                "groups": sum(isinstance(item, GroupItem) for item in scene.items()),
                "locked_layers": sum(bool(layer.locked) for layer in scene.layers),
                "hidden_layers": sum(not layer.visible for layer in scene.layers),
                "not_selectable": sum(
                    not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    for item in on_canvas)},
        })
        out["held_triangles"] = save_held_oracle(workspace, ctx.out / "workspace_oracle.npz")
        out["oracle_file"] = "workspace_oracle.npz"

        def click(x: int, y: int, modifiers: Any = plain) -> list[str]:
            QTest.mouseClick(quick_view, left, modifiers, QPoint(x, y))
            _spin(5)
            return selected()

        # ── G2: seeded clicks ────────────────────────────────────────────────
        # (in the middle of the view, where the framed plan is: a click on the lawn
        # around it proves little — the judge still gets some of those)
        rng = random.Random(WORKSPACE_SEED)
        clicks = []
        for _ in range(WORKSPACE_CLICKS):
            x = rng.randrange(int(0.10 * width), int(0.90 * width))
            y = rng.randrange(int(0.25 * height), int(0.78 * height))
            clicks.append({"at": [x, y], "selected": click(x, y), "view": list(host.view_size())})
        out["clicks"] = clicks
        def steady(x: int, y: int) -> bool:
            """The ENGINE names one item two pixels all round (x, y): a place to click
            twice — not on a silhouette edge."""
            names = set()
            for dx, dy in ((0, 0), (2, 0), (-2, 0), (0, 2), (0, -2), (2, 2), (-2, -2), (2, -2), (-2, 2)):
                hit = host.pick(float(x + dx), float(y + dy))
                names.add(hit.item_id if hit is not None else None)
            return len(names) == 1

        singles: dict[str, list[int]] = {}
        for row in clicks:
            if len(row["selected"]) == 1 and steady(*row["at"]):
                singles.setdefault(row["selected"][0], row["at"])
        nothing = next((row["at"] for row in clicks if not row["selected"]), None)
        (id_a, at_a), (id_b, at_b) = list(singles.items())[:2]
        steps = [{"name": "plain_a", "at": at_a, "selected": click(*at_a)},
                 {"name": "ctrl_b", "at": at_b, "selected": click(*at_b, ctrl)},
                 {"name": "ctrl_b_again", "at": at_b, "selected": click(*at_b, ctrl)},
                 {"name": "shift_b", "at": at_b, "selected": click(*at_b, shift)},
                 {"name": "plain_a_again", "at": at_a, "selected": click(*at_a)}]
        out["modifiers"] = {"a": id_a, "b": id_b, "steps": steps}

        # ── the ring of the clicked item, on screen ──────────────────────────
        _spin_until(lambda: controller.sync.selection.ids == (id_a,), 5.0)
        _pump(60)
        out["ring"] = {"id": id_a, "sent": list(controller.sync.selection.ids),
                       "selected": ctx.save("ws_selected", host.grab("ws_selected"))}
        if nothing is not None:
            out["ring"]["after_a_click_on_nothing"] = click(*nothing)
        scene.clearSelection()
        _spin_until(lambda: controller.sync.selection.ids == (), 5.0)
        _pump(60)
        out["ring"]["cleared"] = ctx.save("ws_cleared", host.grab("ws_cleared"))

        # ── the card in the desktop's own font: does the fullest one fit its place? ──
        card = workspace.info_card
        assert card is not None
        slot = card.parentWidget()
        sizes = [list(host.view_size())]
        fullest: dict[str, Any] = {}
        for item in sorted(on_canvas, key=lambda item: str(item.item_id)):
            record_ = records[str(item.item_id)]
            if record_.kind not in ("TREE", "SHRUB", "PERENNIAL"):
                continue
            scene.clearSelection()
            item.setSelected(True)
            _spin(10)
            body = card._body  # noqa: SLF001 - the paragraph's own geometry
            facts = {"id": str(item.item_id), "rows": len(card.rows()), "text": card.text(),
                     "needed_px": body.heightForWidth(body.width()), "has_px": body.height(),
                     "line_px": body.fontMetrics().lineSpacing(), "width_px": body.width(),
                     "slot_px": slot.height(), "visible": card.isVisible()}
            if facts["rows"] > fullest.get("rows", 0) or (
                    facts["rows"] == fullest.get("rows") and facts["needed_px"] > fullest["needed_px"]):
                fullest = facts
        sizes.append(list(host.view_size()))
        scene.clearSelection()
        _spin_until(lambda: controller.sync.selection.ids == (), 5.0)
        sizes.append(list(host.view_size()))
        out["card"] = {"fullest": fullest, "view_sizes": sizes, "font": card.font().family(),
                       "hint": slot.hint()}

        # ── selection → the engine has its ring: NO readback in this loop ────
        targets = sorted(on_canvas, key=lambda item: str(item.item_id))
        rng.shuffle(targets)
        armed: dict[str, Any] = {}

        passes: list[dict[str, Any]] = []   # of the change being timed: read only on a miss

        def on_pass(report: Any) -> None:
            changes = report.changes
            passes.append({
                "at_ms": round((time.perf_counter() - armed.get("started", 0.0)) * 1000.0, 2),
                "snapshot": bool(report.snapshot), "sent": list(controller.sync.selection.ids),
                "wished": sorted(controller.sync.selected_ids), "canvas": selected(),
                "ring_loads": host.ring_loads,
                "diff": [len(changes.added), len(changes.removed), len(changes.geometry),
                         len(changes.transform)]})
            if "wanted" in armed and "done" not in armed and (
                    controller.sync.selection.ids == armed["wanted"]):
                armed["done"] = time.perf_counter()

        controller.applied.connect(on_pass)
        before = {"ring_loads": host.ring_loads, "ring_geometries": int(ReloadableGeometry.created),
                  "model_uploads": int(BufferGeometry.uploads), "parts": host.part_count(),
                  "frames": host.health().frames_presented}
        latencies: list[float] = []
        misses = 0
        missed: list[dict[str, Any]] = []
        for index in range(120):
            target = targets[index % len(targets)]
            scene.clearSelection()
            _spin(20)
            cleared = list(passes)
            passes.clear()
            armed.clear()
            armed["wanted"] = (str(target.item_id),)
            loads = host.ring_loads
            started = armed["started"] = time.perf_counter()
            target.setSelected(True)
            _spin_until(lambda: "done" in armed, 2.0)
            if "done" in armed:
                latencies.append((armed["done"] - started) * 1000.0)
            else:
                misses += 1
                missed.append({
                    "index": index, "id": str(target.item_id),
                    "kind": records[str(target.item_id)].kind,
                    "is_selected": bool(target.isSelected()), "canvas": selected(),
                    "wished": sorted(controller.sync.selected_ids),
                    "sent": list(controller.sync.selection.ids), "dirty": bool(controller.dirty),
                    "selection_dirty": bool(controller._selection_dirty),  # noqa: SLF001
                    "last_error": str(getattr(controller, "last_error", None)),
                    "host": host.state.value, "loads_before": loads, "loads_now": host.ring_loads,
                    "visible": bool(target.isVisible()), "enabled": bool(target.isEnabled()),
                    "passes": list(passes), "passes_of_the_clear": cleared})
        controller.applied.disconnect(on_pass)
        armed.clear()
        ordered = sorted(latencies)
        out["timing"] = {
            "n": len(latencies), "misses": misses, "missed": missed,
            "ms": [round(value, 3) for value in latencies],
            "median_ms": round(statistics.median(latencies), 3),
            "p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 3),
            "max_ms": round(ordered[-1], 3), "before": before,
            "after": {"ring_loads": host.ring_loads,
                      "ring_geometries": int(ReloadableGeometry.created),
                      "model_uploads": int(BufferGeometry.uploads), "parts": host.part_count(),
                      "frames": host.health().frames_presented},
            "last": list(controller.sync.selection.ids),
        }
        _pump(60)
        out["timing"]["frame_after"] = ctx.save("ws_after_timing", host.grab("ws_after_timing"))

        # ── G7: walk mode with real key events ───────────────────────────────
        scene.clearSelection()
        _spin_until(lambda: controller.sync.selection.ids == (), 5.0)
        _pump(80)
        assert _spin_until(lambda: workspace_settled(workspace), 60.0)
        orbit = workspace.camera.pose

        def books() -> dict[str, Any]:
            return {"undo": len(commands._undo_stack), "can_undo": bool(commands.can_undo),  # noqa: SLF001
                    "can_redo": bool(commands.can_redo)}

        def mouse(kind: QEvent.Type, x: float, y: float, button: Any, buttons: Any) -> None:
            QCoreApplication.sendEvent(quick_view, QMouseEvent(
                kind, QPointF(x, y), QPointF(x, y), button, buttons, plain))

        walk_out: dict[str, Any] = {"before": {
            "camera": _camera_facts(host), "books": books(),
            "frame": ctx.save("ws_orbit_before", host.grab("ws_orbit_before"))}}
        workspace.walk_action.trigger()
        _pump(80)
        walker = workspace.walk
        assert walker is not None and walker.state is not None
        walk_out["entered"] = {
            "walking": workspace.walking, "shown": list(walker.state.shown),
            "yaw": walker.state.yaw_deg, "eye_cm": walker.eye_height_cm,
            "orbit_target": list(orbit.target), "orbit_yaw": orbit.yaw_deg,
            "camera": _camera_facts(host),
            "frame": ctx.save("ws_walk_entered", host.grab("ws_walk_entered"))}
        started = time.perf_counter()
        QTest.keyPress(quick_view, Qt.Key.Key_W)
        _pump(WALK_HOLD_MS)
        moving = walker.moving
        QTest.keyRelease(quick_view, Qt.Key.Key_W)
        held = time.perf_counter() - started
        _pump(60)
        walk_out["walked"] = {
            "shown": list(walker.state.shown), "held_s": round(held, 4), "moving_while_held": moving,
            "moving_after": walker.moving, "camera": _camera_facts(host),
            "frame": ctx.save("ws_walk_walked", host.grab("ws_walk_walked"))}
        mouse(QEvent.Type.MouseButtonPress, 300.0, 200.0, left, left)
        mouse(QEvent.Type.MouseMove, 360.0, 200.0, none, left)
        mouse(QEvent.Type.MouseButtonRelease, 360.0, 200.0, left, none)
        _pump(60)
        walk_out["looked"] = {"yaw": walker.state.yaw_deg, "shown": list(walker.state.shown),
                              "selected": selected(), "camera": _camera_facts(host)}
        QTest.keyClick(quick_view, Qt.Key.Key_Escape)
        assert _spin_until(lambda: workspace_settled(workspace), 60.0)
        _pump(100)
        walk_out["left"] = {
            "walking": workspace.walking, "action_checked": workspace.walk_action.isChecked(),
            "pose_is_the_orbit_pose": workspace.camera.pose is orbit,
            "camera": _camera_facts(host), "books": books(),
            "frame": ctx.save("ws_orbit_after", host.grab("ws_orbit_after"))}
        # hide and show while walking keeps the walker
        workspace.walk_action.trigger()
        _pump(80)
        QTest.keyPress(quick_view, Qt.Key.Key_W)
        _pump(200)
        QTest.keyRelease(quick_view, Qt.Key.Key_W)
        _pump(40)
        there = list(walker.state.shown) if walker.state is not None else None
        workspace.set_mode(WorkspaceMode.PLAN)
        _pump(200)
        hidden = {"walking": workspace.walking, "moving": walker.moving,
                  "shown": list(walker.state.shown) if walker.state is not None else None}
        workspace.set_mode(WorkspaceMode.SPLIT)
        _pump(300)
        again = workspace.host
        assert again is not None
        if not again.wait_ready(OPEN_TIMEOUT_S):
            raise RuntimeError(f"the host shown again is not live: {again.state.value}")
        _pump(100)
        walk_out["hide_show"] = {
            "there": there, "hidden": hidden, "same_host": again is host,
            "shown_again": {"walking": workspace.walking,
                            "shown": list(walker.state.shown) if walker.state is not None else None,
                            "camera": _camera_facts(again)}}
        workspace.set_walking(False)
        _pump(60)
        walk_out["hide_show"]["left"] = {"walking": workspace.walking,
                                         "pose_is_the_orbit_pose": workspace.camera.pose is orbit,
                                         "camera": _camera_facts(again), "books": books()}
        out["walk"] = walk_out
        health = again.health()
        out["health"] = {"ok": health.ok, "frames_presented": health.frames_presented}
        return out
    finally:
        workspace.shutdown()
        window.close()
        window.deleteLater()
        _pump(150)


#: The keys walked in the full main window, each held for this long (real time).
APP_WALK_KEYS = ("W", "S", "A", "D", "Up", "Down", "Left", "Right")
APP_WALK_HOLD_MS = 300


def scenario_app_walk(_ctx: Context) -> dict[str, Any]:
    """Review 1, P0 / P1-2 on the real engine IN THE FULL MAIN WINDOW (``GardenPlannerApp``,
    the workspace switched on, its own engine): enter walk mode with the Walk action —
    the 3D view must take the keyboard — then press every walker's key, S included, into
    whichever window has the keyboard (``QTest`` on ``QGuiApplication.focusWindow()``:
    Qt's own path, ``ShortcutOverride`` and the main window's shortcuts included) and
    record how far the walker went, Snap to Grid and the plan's tool; then Escape — walk
    mode ends and the keyboard goes back to the plan."""
    import urllib.request

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QMessageBox

    import open_garden_planner.app.settings as app_settings

    # the app as a user starts it, minus what would block or reach out (as the workspace
    # gate hook and tests/conftest.py do): the settings store is this driver's own
    # (``_isolate_settings``), the welcome dialog (a modal exec) is silenced, the Agent
    # API server stays off, and every network request is "offline" at once
    store = app_settings.create_qsettings()
    store.setValue(app_settings.AppSettings.KEY_SHOW_WELCOME, False)
    store.setValue(app_settings.AppSettings.KEY_AGENT_API_ENABLED, False)
    store.sync()

    def offline(*_arguments: Any, **_options: Any) -> Any:
        raise OSError("the selection driver runs without a network")

    urllib.request.urlopen = offline  # type: ignore[assignment]
    QMessageBox.question = lambda *_a, **_k: QMessageBox.StandardButton.Discard  # type: ignore[method-assign]
    QMessageBox.information = lambda *_a, **_k: QMessageBox.StandardButton.Ok  # type: ignore[method-assign]
    QMessageBox.warning = lambda *_a, **_k: QMessageBox.StandardButton.Ok  # type: ignore[method-assign]
    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.ui.view3d.workspace import WorkspaceMode

    GardenPlannerApp._show_welcome_dialog = lambda _self: None  # type: ignore[method-assign]

    window = GardenPlannerApp()
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    window.setWindowFlags(window.windowFlags() | Qt.WindowType.WindowDoesNotAcceptFocus)
    # Use the desktop's work area; a fixed 1500x900 exceeds a scaled 1280x720 screen.
    window.showMaximized()
    _pump(300)
    out: dict[str, Any] = {}
    try:
        workspace = window._workspace  # noqa: SLF001 - the main window's workspace
        canvas = window.canvas_view
        workspace.set_mode(WorkspaceMode.SPLIT)
        if not _spin_until(lambda: workspace.host is not None and workspace.controller is not None, 30.0):
            raise RuntimeError(f"the workspace did not start its engine: {workspace.view3d_state}")
        host, controller = workspace.host, workspace.controller
        assert host is not None and controller is not None
        if not host.wait_ready(OPEN_TIMEOUT_S):
            raise RuntimeError(f"the workspace's host is not live: {host.state.value}")
        _spin_until(lambda: controller.apply_count >= 1 and not controller.dirty, 30.0)
        quick_view = host._view  # noqa: SLF001 - the native window a user types into
        canvas.setFocus()
        _pump(200)
        before = QApplication.focusWidget()
        out["before"] = {"focus_widget": type(before).__name__ if before is not None else None,
                         "focus_window_is_view": QGuiApplication.focusWindow() is quick_view}
        window_shortcuts = sorted({action.shortcut().toString() for action in window.findChildren(type(window.snap_action))
                                   if action.shortcut().count() == 1})
        out["window_shortcuts"] = window_shortcuts
        snap, tool = window.snap_action.isChecked(), canvas.tool_manager.active_tool_type
        workspace.walk_action.trigger()
        _pump(300)
        walk = workspace.walk
        assert walk is not None and walk.state is not None
        out["entered"] = {"walking": workspace.walking,
                          "focus_window_is_view": QGuiApplication.focusWindow() is quick_view}
        keys = []
        for name in APP_WALK_KEYS:
            key = getattr(Qt.Key, f"Key_{name}")
            here = walk.state.shown
            target = QGuiApplication.focusWindow()
            QTest.keyPress(target, key)
            _pump(APP_WALK_HOLD_MS)
            QTest.keyRelease(QGuiApplication.focusWindow(), key)
            _pump(60)
            there = walk.state.shown
            keys.append({"key": name, "to_the_view": target is quick_view,
                         "moved_cm": math.hypot(there[0] - here[0], there[1] - here[1]),
                         "snap": window.snap_action.isChecked(),
                         "tool": str(canvas.tool_manager.active_tool_type)})
        out["keys"] = keys
        out["snap_before"], out["tool_before"] = snap, str(tool)
        QTest.keyClick(QGuiApplication.focusWindow(), Qt.Key.Key_Escape)
        _pump(300)
        after = QApplication.focusWidget()
        out["left"] = {"walking": workspace.walking,
                       "focus_widget_is_canvas": after is canvas,
                       "focus_window_is_view": QGuiApplication.focusWindow() is quick_view,
                       "tool": str(canvas.tool_manager.active_tool_type),
                       "snap": window.snap_action.isChecked()}
        return out
    finally:
        window._project_manager.mark_clean()  # noqa: SLF001 - close without the save prompt
        window.close()
        window.deleteLater()
        _pump(300)


SCENARIOS: dict[str, Callable[[Context], dict[str, Any]]] = {
    "ring": scenario_ring,
    "ring_depth": scenario_ring_depth,
    "pick": scenario_pick,
    "lookthrough": scenario_lookthrough,
    "workspace": scenario_workspace,
    "app_walk": scenario_app_walk,
}


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
    from open_garden_planner.ui.view3d.quick3d import offscreen

    log = offscreen.RenderLog(args.out / "render.log")
    result: dict[str, Any] = {
        "status": "running", "platform": platform.platform(), "python": sys.version.split()[0],
        "qt": QT_VERSION_STR,
        "env": {key: os.environ.get(key) for key in (
            "QT_QPA_PLATFORM", "QSG_RHI_BACKEND", "QSG_RHI_PREFER_SOFTWARE_RENDERER", "APPDATA")},
        "scenarios": {},
    }

    def write() -> None:
        (args.out / "result.json").write_text(json.dumps(result, indent=1, default=str),
                                              encoding="utf-8")

    code = 0
    try:
        with offscreen.watchdog(args.watchdog_s, log, what="the selection driver", supervised=True):
            offscreen.ensure_application()
            context = Context(args.out, log, args.qml_dir.resolve() if args.qml_dir else None)
            log("start", scenarios=args.scenarios, qt=QT_VERSION_STR, platform=result["platform"])
            for name in wanted:
                log("scenario", name=name)
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
        log("error", error=result["error"])
        code = QT_ERRORS_EXIT if type(error).__name__ == "RenderError" else 2
    finally:
        result["total_s"] = round(time.perf_counter() - started, 2)
        write()
        log("done", status=result["status"], total_s=result["total_s"])
        log.close()
        with contextlib.suppress(Exception):
            _clear_settings()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
