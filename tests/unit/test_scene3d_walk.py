"""The walker of the 3D view — its world, its collisions, its motion (Phase 17 L1.8, gate G5).

``core/scene3d/walk.py`` is Qt-free plain data and pure functions, so everything the
story promises about walking is judged here without a window: a 20 cm gap blocks, a
60 cm gate passes, a wall is slid along and never tunnelled, an inside corner does
not trap, the path does not depend on the frame rate.

The judge is NOT the module's own collision code: ``brute_clearance`` below measures
the distance from a point to every obstacle segment in plain Python, and
``brute_inside`` asks ``core.scene3d.point_in_regions`` — a walker the module calls
free must be free by those too.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

import numpy as np
import pytest

from open_garden_planner.core.scene3d import (
    Material,
    Mesh,
    MeshPart,
    Params,
    Record,
    Transform,
    point_in_regions,
    pose_ring,
    prism_mesh,
    walk,
)
from open_garden_planner.core.scene3d.walk import (
    EYE_HEIGHTS_CM,
    HEADROOM_CM,
    MAX_ADVANCE_S,
    PITCH_LIMIT_DEG,
    RUN_FACTOR,
    STEP_HEIGHT_CM,
    TICK_S,
    WALK_SOLID_KINDS,
    WALK_SPEED_CM_S,
    WALKER_RADIUS_CM,
    WalkCommand,
    WalkState,
    WalkWorld,
    advance,
    build_world,
    eye_scene,
    is_free,
    look_target_scene,
    nearest_free,
    start_state,
    turned,
)

R = WALKER_RADIUS_CM
FORWARD = WalkCommand(forward=1.0)
TOL = 1e-6


def rect(width: float, depth: float) -> tuple[tuple[float, float], ...]:
    half_w, half_d = width / 2.0, depth / 2.0
    return ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))


def solid(item_id: str, east: float, north: float, width: float, depth: float,
          height: float | None = 180.0, *, kind: str = "RAISED_BED", rotation: float = 0.0,
          base: float = 0.0, holes: tuple = ()) -> Record:
    return Record(
        item_id=item_id, kind=kind, shape="rectangle", footprints=(rect(width, depth),),
        transform=Transform(east, north, rotation, base), material=Material(kind),
        height_cm=height, params=Params({"seed": item_id}), holes=holes)


def world_of(*records: Record, width: float = 2000.0, depth: float = 2000.0, **kwargs) -> WalkWorld:
    return build_world({record.item_id: record for record in records}, width, depth, **kwargs)


# ── the independent judge ────────────────────────────────────────────────────


def brute_clearance(world: WalkWorld, x: float, y: float) -> float:
    """The distance from (x, y) to the nearest obstacle segment, in plain Python."""
    best = math.inf
    for ax, ay, bx, by in world.segments.tolist():
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0.0 else min(1.0, max(0.0, ((x - ax) * dx + (y - ay) * dy) / length2))
        best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return best


def brute_inside(records: Sequence[Record], x: float, y: float) -> bool:
    """Inside the posed footprint (outer minus holes) of any SOLID record."""
    for record in records:
        if not walk.is_solid(record):
            continue
        regions = [(tuple(pose_ring(record.transform, outer)),
                    tuple(tuple(pose_ring(record.transform, hole)) for hole in holes))
                   for outer, holes in record.regions]
        if point_in_regions(x, y, regions):
            return True
    return False


def brute_free(world: WalkWorld, records: Sequence[Record], x: float, y: float) -> bool:
    inside_plan = (R - TOL <= x <= world.width_cm - R + TOL
                   and R - TOL <= y <= world.depth_cm - R + TOL)
    return inside_plan and brute_clearance(world, x, y) >= R - TOL and not brute_inside(records, x, y)


def walk_for(world: WalkWorld, state: WalkState, command: WalkCommand, seconds: float,
             hz: float = 60.0) -> WalkState:
    for _ in range(round(seconds * hz)):
        state = advance(state, command, 1.0 / hz, world)
    return state


# ── the stated numbers ───────────────────────────────────────────────────────


def test_the_walker_is_the_stated_cylinder() -> None:
    assert WALKER_RADIUS_CM == 22.5, "shoulder width 45 cm"
    assert EYE_HEIGHTS_CM == (165.0, 150.0, 110.0)
    assert (WALK_SPEED_CM_S, RUN_FACTOR, STEP_HEIGHT_CM) == (140.0, 2.0, 25.0)
    # one tick never moves the walker further than its radius — not even running
    assert WALK_SPEED_CM_S * RUN_FACTOR * TICK_S < WALKER_RADIUS_CM / 5.0
    assert max(EYE_HEIGHTS_CM) + 10.0 <= HEADROOM_CM


def test_the_camera_cannot_reach_a_wall_the_walker_touches() -> None:
    """The near plane's farthest corner is closer to the eye than the walker's radius —
    for the walk's field of view and any pane up to 7 times as wide as high."""
    half_height = walk.NEAR_PLANE_CM * math.tan(math.radians(walk.WALK_FOV_DEG) / 2.0)
    for aspect in (0.5, 1.0, 16.0 / 9.0, 4.26, 7.0):
        corner = math.sqrt(walk.NEAR_PLANE_CM ** 2 + half_height ** 2 + (half_height * aspect) ** 2)
        assert corner < WALKER_RADIUS_CM, (aspect, corner)
    assert walk.near_plane_reach_cm(4.26) == pytest.approx(
        math.sqrt(25.0 + half_height ** 2 * (1.0 + 4.26 ** 2)))
    assert walk.near_plane_reach_cm(4.26) < 14.0


# ── what is an obstacle ──────────────────────────────────────────────────────


@pytest.mark.parametrize(("kind", "height", "base", "expected"), [
    ("RAISED_BED", 40.0, 0.0, True),
    ("RAISED_BED", 25.0, 0.0, False),      # a step: exactly the step height is walked over
    ("RAISED_BED", 25.1, 0.0, True),
    ("GARDEN_BED", 20.0, 0.0, False),      # an in-ground bed with a low edge is ground
    ("HOUSE", 600.0, 0.0, True),
    ("GREENHOUSE", 250.0, 0.0, True),      # named by the story; not in the built world's set
    ("GREENHOUSE", None, 0.0, False),      # the default builder gives it no solid then
    ("CONTAINER_ROUND", 10.0, 20.0, True),  # the TOP counts: base + height
    ("TREE", 800.0, 0.0, False),           # plants are not obstacles in v0 …
    ("SHRUB", 150.0, 0.0, False),
    ("PERENNIAL", 60.0, 0.0, False),
    ("HEDGE_SECTION", 150.0, 0.0, True),   # … hedges are: they are built world
    ("TABLE_RECTANGULAR", 75.0, 0.0, False),   # furniture is walked through in v0
    ("PERGOLA", 240.0, 0.0, False),
    ("LAWN", None, 0.0, False),
])
def test_which_records_are_solid(kind: str, height: float | None, base: float,
                                 expected: bool) -> None:
    record = solid("x", 500.0, 500.0, 100.0, 100.0, height, kind=kind, base=base)
    assert walk.is_solid(record) is expected


def test_a_built_item_without_a_height_is_solid_at_the_height_it_is_shown_at() -> None:
    """The built world draws an item the plan gives no height at its kind's nominal
    height. What is SHOWN blocks: a fence without a typed height is a fence."""
    from open_garden_planner.core.scene3d.builders.common import nominal_height_cm

    nominal = nominal_height_cm("FENCE")
    assert nominal is not None and nominal > STEP_HEIGHT_CM
    fence = solid("f", 500.0, 500.0, 400.0, 6.0, None, kind="FENCE")
    assert walk.solid_height_cm(fence) == nominal and walk.is_solid(fence)
    assert walk.solid_height_cm(solid("t", 0.0, 0.0, 10.0, 10.0, 90.0, kind="TREE")) is None


def test_the_solid_kinds_are_the_built_world_and_the_greenhouse() -> None:
    from open_garden_planner.core.scene3d.builders import BUILT_WORLD_KINDS

    assert BUILT_WORLD_KINDS | {"GREENHOUSE"} == WALK_SOLID_KINDS


def test_the_world_holds_the_posed_footprint_of_every_solid_and_nothing_else() -> None:
    box = solid("box", 600.0, 400.0, 200.0, 100.0, rotation=90.0)
    tree = solid("tree", 900.0, 900.0, 300.0, 300.0, 700.0, kind="TREE")
    lawn = solid("lawn", 1000.0, 1000.0, 800.0, 800.0, None, kind="LAWN")
    world = world_of(box, tree, lawn)
    assert world.solid_ids == ("box",)
    assert (world.width_cm, world.depth_cm) == (2000.0, 2000.0)
    # turned by 90 degrees: 100 wide (east), 200 deep (north)
    xs = sorted({round(float(v), 6) for v in world.segments[:, (0, 2)].ravel()})
    ys = sorted({round(float(v), 6) for v in world.segments[:, (1, 3)].ravel()})
    assert (xs[0], xs[-1], ys[0], ys[-1]) == (550.0, 650.0, 300.0, 500.0)
    assert not is_free(world, 600.0, 400.0), "inside the footprint"
    assert not is_free(world, 550.0 - R + 0.5, 400.0), "the circle reaches into it"
    assert is_free(world, 550.0 - R - 0.5, 400.0)
    assert is_free(world, 900.0, 900.0), "a tree is walked through in v0"


def test_a_courtyard_inside_a_closed_wall_is_free_ground() -> None:
    """Outer ring minus holes: the garden inside a closed fence is not solid."""
    hole = tuple(reversed(rect(300.0, 300.0)))     # clockwise
    ring_wall = Record(
        item_id="yard", kind="WALL", shape="polyline", footprints=(rect(360.0, 360.0),),
        holes=((hole,),), transform=Transform(1000.0, 1000.0), material=Material("WALL"),
        height_cm=200.0, params=Params({"seed": "yard"}))
    world = world_of(ring_wall)
    assert is_free(world, 1000.0, 1000.0), "the middle of the courtyard"
    assert not is_free(world, 1000.0 + 165.0, 1000.0), "in the wall"
    assert not is_free(world, 1000.0 + 150.0 - R + 1.0, 1000.0), "the circle touches the inside face"
    # … and there is no way in: walking east from the middle ends at the inner face
    state = start_state(world, (1000.0, 1000.0), 90.0)
    assert state is not None
    state = walk_for(world, state, FORWARD, 6.0)
    assert state.east == pytest.approx(1000.0 + 150.0 - R, abs=1e-3)


# ── the gaps (gate G5) ───────────────────────────────────────────────────────


def gate_world(gap_cm: float) -> tuple[WalkWorld, list[Record]]:
    """A wall right across the plan along north = 1000 — from edge to edge, so there is
    no way round it — with an opening of ``gap_cm`` centred on east = 1000."""
    half = gap_cm / 2.0
    length = 1000.0 - half
    left = solid("left", length / 2.0, 1000.0, length, 30.0)
    right = solid("right", 2000.0 - length / 2.0, 1000.0, length, 30.0)
    records = [left, right]
    return world_of(*records), records


@pytest.mark.parametrize(("gap", "passes"), [
    (20.0, False), (40.0, False), (44.5, False), (45.5, True), (60.0, True), (120.0, True)])
def test_a_gap_narrower_than_the_shoulders_blocks_and_a_garden_gate_passes(
        gap: float, passes: bool) -> None:
    world, records = gate_world(gap)
    state = start_state(world, (1000.0, 700.0), 0.0)        # south of the wall, facing north
    assert state is not None
    for _ in range(600):                                    # ten seconds at 60 Hz: 14 m of walking
        state = advance(state, FORWARD, 1.0 / 60.0, world)
        assert brute_free(world, records, state.east, state.north)
    if passes:
        assert state.north > 1000.0 + 15.0 + 300.0, "it is through, and well beyond"
    else:
        assert state.north <= 1000.0 - 15.0, "it never gets past the near face"


def test_a_twenty_centimetre_gap_blocks_from_every_direction_of_approach() -> None:
    world, records = gate_world(20.0)
    for yaw in (-40.0, -20.0, -5.0, 0.0, 5.0, 20.0, 40.0):
        for offset in (-60.0, -10.0, 0.0, 10.0, 60.0):
            state = start_state(world, (1000.0 + offset, 800.0), yaw)
            assert state is not None
            state = walk_for(world, state, WalkCommand(forward=1.0, run=True), 6.0)
            assert state.north < 1000.0, (yaw, offset, state)
            assert brute_free(world, records, state.east, state.north)


# ── sliding ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("angle", [10.0, 30.0, 45.0, 60.0, 80.0])
def test_walking_diagonally_into_a_long_wall_keeps_the_speed_along_it(angle: float) -> None:
    """Gate G5: at least 95 % of the tangential speed is kept (measured: all of it)."""
    wall = solid("wall", 1000.0, 1000.0, 1800.0, 30.0)
    world = world_of(wall)
    # facing north-east by ``angle`` off the wall's normal, starting in contact
    state = start_state(world, (300.0, 1000.0 - 15.0 - R), angle)
    assert state is not None
    seconds = 4.0
    after = walk_for(world, state, FORWARD, seconds)
    tangential = WALK_SPEED_CM_S * math.sin(math.radians(angle)) * seconds
    assert after.north == pytest.approx(1000.0 - 15.0 - R, abs=1e-3), "it stays on the face"
    assert after.east - state.east >= 0.95 * tangential
    assert after.east - state.east == pytest.approx(tangential, rel=1e-6)


def test_an_inside_corner_does_not_trap() -> None:
    """Pressed into a corner for two seconds, the walker leaves it at full speed along
    either wall."""
    south = solid("south", 1000.0, 500.0, 1000.0, 30.0)
    west = solid("west", 500.0, 1000.0, 30.0, 1000.0)
    world = world_of(south, west)
    corner = (500.0 + 15.0 + R, 500.0 + 15.0 + R)
    state = start_state(world, (700.0, 700.0), 225.0)       # facing south-west: into the corner
    assert state is not None
    state = walk_for(world, state, WalkCommand(forward=1.0, run=True), 2.0)
    assert (state.east, state.north) == pytest.approx(corner, abs=1e-3)
    for yaw, axis in ((0.0, "north"), (90.0, "east")):
        out = walk_for(world, turned(state, yaw - state.yaw_deg, 0.0), FORWARD, 1.0)
        assert getattr(out, axis) - getattr(state, axis) == pytest.approx(WALK_SPEED_CM_S, rel=1e-6)


def test_an_outside_corner_is_walked_around() -> None:
    block = solid("block", 1000.0, 1000.0, 200.0, 200.0)
    world = world_of(block)
    # along the south face, eastwards, pressing slightly into it: round the corner and on
    state = start_state(world, (850.0, 900.0 - R), 80.0)
    assert state is not None
    for _ in range(600):
        state = advance(state, FORWARD, 1.0 / 60.0, world)
        assert brute_free(world, [block], state.east, state.north)
    assert state.east > 1100.0 + R and state.north > 900.0, "it went round and kept going"


def test_no_tunnelling_through_a_thin_wall_at_any_speed_or_frame_time() -> None:
    """A wall 1 cm thick, the walker running, frames of up to the longest step the
    core accepts: the walker is never found on the other side."""
    thin = solid("thin", 1000.0, 1000.0, 1800.0, 1.0)
    world = world_of(thin)
    for dt in (1.0 / 240.0, 1.0 / 30.0, 0.1, MAX_ADVANCE_S, 5.0):
        state = start_state(world, (1000.0, 900.0), 0.0)
        assert state is not None
        for _ in range(200):
            state = advance(state, WalkCommand(forward=1.0, run=True), dt, world)
        assert state.north == pytest.approx(1000.0 - 0.5 - R, abs=1e-3), dt


def test_a_stalled_frame_does_not_teleport_the_walker() -> None:
    world = world_of()
    state = start_state(world, (1000.0, 1000.0), 0.0)
    assert state is not None
    after = advance(state, FORWARD, 30.0, world)
    assert after.north - state.north == pytest.approx(WALK_SPEED_CM_S * MAX_ADVANCE_S, abs=2.0)


# ── the plan's edge ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(("yaw", "east", "north"), [
    (0.0, 500.0, 800.0 - R), (90.0, 1200.0 - R, 400.0), (180.0, 500.0, R), (270.0, R, 400.0)])
def test_the_canvas_bounds_are_the_worlds_edge(yaw: float, east: float, north: float) -> None:
    world = world_of(width=1200.0, depth=800.0)
    state = start_state(world, (500.0, 400.0), yaw)
    assert state is not None
    state = walk_for(world, state, WalkCommand(forward=1.0, run=True), 10.0)
    assert (state.east, state.north) == pytest.approx((east, north), abs=1e-6)


def test_the_edge_is_slid_along_too() -> None:
    world = world_of(width=1200.0, depth=800.0)
    state = start_state(world, (300.0, 800.0 - R), 45.0)
    assert state is not None
    after = walk_for(world, state, FORWARD, 2.0)
    assert after.north == pytest.approx(800.0 - R)
    assert after.east - state.east == pytest.approx(WALK_SPEED_CM_S * math.sin(math.radians(45.0)) * 2.0)


# ── where a walk starts ──────────────────────────────────────────────────────


def test_a_walk_starts_where_asked_when_that_is_free() -> None:
    world = world_of(solid("box", 1500.0, 1500.0, 100.0, 100.0))
    state = start_state(world, (400.0, 300.0), 123.0)
    assert state is not None
    assert (state.east, state.north, state.yaw_deg, state.pitch_deg) == (400.0, 300.0, 123.0, 0.0)
    assert state.shown == (400.0, 300.0)


def test_a_start_inside_an_obstacle_moves_to_the_nearest_free_spot() -> None:
    house = solid("house", 1000.0, 1000.0, 800.0, 600.0, 600.0, kind="HOUSE")
    world = world_of(house)
    # 60 cm inside the south wall: the nearest free ground is just south of it
    spot = nearest_free(world, 1000.0, 760.0)
    assert spot is not None and brute_free(world, [house], *spot)
    assert spot[1] < 700.0 and abs(spot[0] - 1000.0) <= R
    assert math.hypot(spot[0] - 1000.0, spot[1] - 760.0) <= 60.0 + 2.0 * R + 1.0, "the nearest"
    state = start_state(world, (1000.0, 760.0), 0.0)
    assert state is not None and (state.east, state.north) == spot


def test_a_start_beyond_the_plan_is_brought_inside() -> None:
    world = world_of(width=1200.0, depth=800.0)
    state = start_state(world, (-900.0, 2000.0), 0.0)       # the orbit target may be panned out
    assert state is not None
    assert (state.east, state.north) == pytest.approx((R, 800.0 - R))


def test_a_plan_without_free_ground_gives_no_walk() -> None:
    slab = solid("slab", 100.0, 100.0, 400.0, 400.0)        # covers the whole 200 x 200 plan
    assert start_state(world_of(slab, width=200.0, depth=200.0), (100.0, 100.0), 0.0) is None
    assert start_state(world_of(width=40.0, depth=40.0), (20.0, 20.0), 0.0) is None, (
        "a plan narrower than the walker")


# ── looking ──────────────────────────────────────────────────────────────────


def test_turning_changes_the_view_and_never_the_position() -> None:
    world = world_of()
    state = start_state(world, (500.0, 500.0), 10.0)
    assert state is not None
    looked = turned(state, 30.0, 20.0)
    assert (looked.yaw_deg, looked.pitch_deg) == (40.0, 20.0)
    assert (looked.east, looked.north, looked.shown) == (state.east, state.north, state.shown)
    assert turned(looked, 0.0, 500.0).pitch_deg == PITCH_LIMIT_DEG
    assert turned(looked, 0.0, -500.0).pitch_deg == -PITCH_LIMIT_DEG
    assert turned(state, 725.0, 0.0).yaw_deg == pytest.approx(15.0), "yaw stays within one turn"


def test_the_eye_is_at_eye_height_and_looks_where_the_walker_looks() -> None:
    world = world_of()
    state = start_state(world, (500.0, 400.0), 90.0)          # facing east
    assert state is not None
    for height in EYE_HEIGHTS_CM:
        assert eye_scene(state, height) == (500.0, 400.0, height)
    target = look_target_scene(state, 165.0)
    assert target == pytest.approx((500.0 + walk.LOOK_DISTANCE_CM, 400.0, 165.0))
    up = look_target_scene(turned(state, 0.0, 30.0), 165.0)
    assert up[2] - 165.0 == pytest.approx(walk.LOOK_DISTANCE_CM * math.sin(math.radians(30.0)))


def test_the_pace_never_depends_on_where_the_walker_looks() -> None:
    """Movement is horizontal: looking up does not slow the walk or lift the walker."""
    world = world_of()
    level = start_state(world, (500.0, 500.0), 0.0)
    assert level is not None
    up = turned(level, 0.0, 70.0)
    assert walk_for(world, up, FORWARD, 1.0).north == walk_for(world, level, FORWARD, 1.0).north


@pytest.mark.parametrize(("command", "east", "north"), [
    (WalkCommand(forward=1.0), 0.0, 1.0), (WalkCommand(forward=-1.0), 0.0, -1.0),
    (WalkCommand(strafe=1.0), 1.0, 0.0), (WalkCommand(strafe=-1.0), -1.0, 0.0),
    (WalkCommand(forward=1.0, strafe=1.0), math.sqrt(0.5), math.sqrt(0.5)),
])
def test_forward_is_along_the_heading_and_a_diagonal_is_not_faster(
        command: WalkCommand, east: float, north: float) -> None:
    world = world_of()
    state = start_state(world, (1000.0, 1000.0), 0.0)
    assert state is not None
    after = walk_for(world, state, command, 2.0)
    assert (after.east - 1000.0, after.north - 1000.0) == pytest.approx(
        (east * WALK_SPEED_CM_S * 2.0, north * WALK_SPEED_CM_S * 2.0), abs=1e-6)
    run = walk_for(world, state, WalkCommand(command.forward, command.strafe, run=True), 2.0)
    assert math.hypot(run.east - 1000.0, run.north - 1000.0) == pytest.approx(
        WALK_SPEED_CM_S * RUN_FACTOR * 2.0)


def test_standing_still_costs_nothing_and_moves_nothing() -> None:
    world = world_of(solid("box", 1000.0, 1000.0, 100.0, 100.0))
    state = start_state(world, (500.0, 500.0), 0.0)
    assert state is not None
    assert advance(state, WalkCommand(), 0.5, world) == state
    assert advance(state, FORWARD, 0.0, world) == state
    assert advance(state, FORWARD, float("nan"), world) == state
    assert advance(state, FORWARD, -1.0, world) == state


# ── frame-rate independence (gate G5) ────────────────────────────────────────

#: (seconds, command, yaw change at the START of the stretch) — every stretch a multiple
#: of 1 / 6 s, the grid 30 Hz and 144 Hz frames share, so both runs are given THE SAME
#: inputs over the same times. It runs into a wall, slides, rounds a corner, squeezes
#: through a gate and presses into an inside corner.
SCRIPT = (
    (1.5, WalkCommand(forward=1.0), 0.0),
    (1.0, WalkCommand(forward=1.0, strafe=1.0), 0.0),
    (2.0, WalkCommand(forward=1.0, run=True), 55.0),
    (0.5, WalkCommand(strafe=-1.0), 0.0),
    (2.5, WalkCommand(forward=1.0), -140.0),
    (1.0, WalkCommand(), 0.0),
    (3.0, WalkCommand(forward=1.0, strafe=-1.0, run=True), 200.0),
    (2.0, WalkCommand(forward=-1.0), -35.0),
    (1.5, WalkCommand(forward=1.0, run=True), 90.0),
)


def obstacle_course() -> tuple[WalkWorld, list[Record]]:
    records = [
        solid("wall-a", 600.0, 900.0, 700.0, 30.0),
        solid("wall-b", 1300.0, 900.0, 580.0, 30.0),         # a 60 cm gate between a and b
        solid("block", 900.0, 500.0, 160.0, 160.0, rotation=30.0),
        solid("pillar", 400.0, 600.0, 40.0, 40.0),
        solid("long", 1500.0, 400.0, 30.0, 600.0),
        solid("bed", 700.0, 1300.0, 300.0, 120.0, rotation=-20.0),
    ]
    return world_of(*records, width=1800.0, depth=1600.0), records


def run_script(world: WalkWorld, hz: int) -> WalkState:
    state = start_state(world, (300.0, 300.0), 20.0)
    assert state is not None
    for seconds, command, yaw in SCRIPT:
        state = turned(state, yaw, 0.0)
        frames = seconds * hz
        assert frames == round(frames), "the script is on the grid both rates share"
        for _ in range(round(frames)):
            state = advance(state, command, 1.0 / hz, world)
    return state


def test_the_same_inputs_at_30_hz_and_144_hz_end_in_the_same_place() -> None:
    """Gate G5: within 2 cm (measured: the two end positions are equal to float noise —
    the walker advances in ticks of its own, not in frames)."""
    world, records = obstacle_course()
    slow, fast = run_script(world, 30), run_script(world, 144)
    apart = math.hypot(slow.shown[0] - fast.shown[0], slow.shown[1] - fast.shown[1])
    assert apart <= 2.0
    assert apart <= 1e-6, "in fact: the same ticks, so the same path"
    assert brute_free(world, records, *slow.shown)
    # the script DID meet the obstacles: a walk through empty ground proves nothing
    free_world = world_of(width=1800.0, depth=1600.0)
    unobstructed = run_script(free_world, 30)
    assert math.hypot(slow.east - unobstructed.east, slow.north - unobstructed.north) > 100.0


@pytest.mark.parametrize("hz", [24, 30, 60, 144, 240])
def test_what_is_shown_runs_ahead_of_the_last_tick_by_the_time_not_yet_ticked(hz: int) -> None:
    """Between two ticks the shown position is extrapolated (and resolved), so a view
    at 144 Hz does not judder with 120 ticks a second. In open ground it is exact."""
    world = world_of()
    state = start_state(world, (1000.0, 200.0), 0.0)
    assert state is not None
    for frame in range(1, 200):
        state = advance(state, FORWARD, 1.0 / hz, world)
        assert state.shown[1] - 200.0 == pytest.approx(WALK_SPEED_CM_S * frame / hz, abs=1e-6)
        assert 0.0 <= state.carry_s < TICK_S + 1e-9


# ── a long random walk (gate G5) ─────────────────────────────────────────────


def test_a_seeded_random_walk_never_leaves_free_ground() -> None:
    """20,000 steps over the obstacle course with random commands, turns and frame
    times: after every one of them the walker's circle touches no obstacle and lies
    inside the plan — judged by the brute-force judge, not by the module."""
    world, records = obstacle_course()
    rng = random.Random(385_108)
    state = start_state(world, (300.0, 300.0), 0.0)
    assert state is not None
    command = FORWARD
    touched = 0
    for step in range(20_000):
        if step % 23 == 0:
            command = WalkCommand(rng.choice((-1.0, 0.0, 1.0, 1.0, 1.0)),
                                  rng.choice((-1.0, 0.0, 0.0, 1.0)), rng.random() < 0.3)
            state = turned(state, rng.uniform(-120.0, 120.0), rng.uniform(-20.0, 20.0))
        state = advance(state, command, rng.choice((1 / 144, 1 / 60, 1 / 30, 0.05)), world)
        for x, y in ((state.east, state.north), state.shown):
            assert brute_free(world, records, x, y), (step, state)
        touched += brute_clearance(world, state.east, state.north) < R + 0.01
    assert touched > 500, "the walk really ran along obstacles"


# ── obstacles from what is SHOWN ─────────────────────────────────────────────


def overhang_parts(record: Record) -> tuple[MeshPart, ...]:
    """A builder whose solid is WIDER than the record's footprint — as a wall is built
    30 cm thick on a 5 cm stroke: a slab 20 cm beyond the footprint on every side,
    from the ground to 150 cm, and a canopy 100 cm beyond it at 300 cm (above the head)."""
    (x0, y0), (x1, y1) = record.footprints[0][0], record.footprints[0][2]
    body = prism_mesh((((x0 - 20, y0 - 20), (x1 + 20, y0 - 20), (x1 + 20, y1 + 20),
                        (x0 - 20, y1 + 20)),), 150.0)
    roof = prism_mesh((((x0 - 100, y0 - 100), (x1 + 100, y0 - 100), (x1 + 100, y1 + 100),
                        (x0 - 100, y1 + 100)),), 20.0).translated(0.0, 0.0, 300.0)
    kerb = prism_mesh((((x0 - 60, y0 - 60), (x1 + 60, y0 - 60), (x1 + 60, y1 + 60),
                        (x0 - 60, y1 + 60)),), 10.0)            # below the step height
    return (MeshPart(body), MeshPart(roof), MeshPart(kerb))


def test_the_walker_stops_at_what_is_shown_not_at_the_thinner_footprint() -> None:
    wall = solid("wall", 1000.0, 1000.0, 600.0, 4.0, 200.0, kind="WALL")
    bare = world_of(wall)
    shown = world_of(wall, parts_of=overhang_parts)
    start = (1000.0, 700.0)
    by_footprint = walk_for(bare, start_state(bare, start, 0.0), FORWARD, 5.0)
    by_solid = walk_for(shown, start_state(shown, start, 0.0), FORWARD, 5.0)
    assert by_footprint.north == pytest.approx(1000.0 - 2.0 - R, abs=1e-3)
    assert by_solid.north == pytest.approx(1000.0 - 2.0 - 20.0 - R, abs=1e-3), (
        "20 cm earlier: at the body's face")
    # the canopy above the head and the kerb below the step change nothing
    assert is_free(shown, 1000.0, 1000.0 - 2.0 - 20.0 - R - 0.01)


def test_a_turned_item_on_a_base_blocks_where_its_mesh_stands() -> None:
    """The mesh is item-local: it is posed by the record's transform, and its height
    band is taken above the WALKER's ground, so a low pot on a table-high base blocks."""
    pot = solid("pot", 800.0, 800.0, 200.0, 40.0, 10.0, kind="CONTAINER", rotation=90.0, base=30.0)
    world = world_of(pot, parts_of=lambda record: (MeshPart(prism_mesh(record.footprints, 10.0)),))
    assert walk.is_solid(pot)
    assert not is_free(world, 800.0, 800.0 + 100.0 + R - 1.0), "turned: it is 200 cm deep now"
    assert is_free(world, 800.0 + 20.0 + R + 1.0, 800.0)


def test_a_builder_that_fails_leaves_the_footprint_as_the_obstacle() -> None:
    def broken(_record: Record) -> tuple[MeshPart, ...]:
        raise ValueError("no mesh today")

    box = solid("box", 1000.0, 1000.0, 200.0, 200.0)
    world = world_of(box, parts_of=broken)
    assert world.solid_ids == ("box",) and not is_free(world, 1000.0, 1000.0)
    assert is_free(world, 1000.0, 900.0 - R - 0.01) and not is_free(world, 1000.0, 900.0 - R + 0.5)


def test_a_mesh_that_holds_nothing_in_the_walkers_height_adds_nothing() -> None:
    empty = world_of(solid("box", 1000.0, 1000.0, 100.0, 100.0), parts_of=lambda _r: (
        MeshPart(Mesh.empty()),))
    assert len(empty.segments) == 4


# ── plain data ───────────────────────────────────────────────────────────────


def test_the_world_is_plain_read_only_data() -> None:
    world, _records = obstacle_course()
    assert isinstance(world.segments, np.ndarray) and world.segments.shape[1] == 4
    assert world.segments.flags.writeable is False
    with pytest.raises(AttributeError):
        world.width_cm = 1.0  # type: ignore[misc]
    state = start_state(world, (300.0, 300.0), 0.0)
    assert state is not None
    with pytest.raises(AttributeError):
        state.east = 1.0  # type: ignore[misc]
    assert hash(WalkCommand(1.0, 0.0, True)) == hash(WalkCommand(1.0, 0.0, True))


def test_the_same_inputs_give_the_same_walk_twice() -> None:
    world, _records = obstacle_course()
    assert run_script(world, 60) == run_script(world, 60)
    assert run_script(obstacle_course()[0], 60) == run_script(world, 60), "a rebuilt world too"
