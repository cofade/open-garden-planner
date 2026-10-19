"""Walk mode's keys, drags and clock (Phase 17 L1.8, ADR-065).

``ui/view3d/walk_mode.WalkMode`` is the thin layer between Qt's events and the
Qt-free walker (``core/scene3d/walk.py``, judged in ``tests/unit/test_scene3d_walk.py``).
Here it sits on a plain ``QObject`` and gets real key and mouse events; its clock
is held by the test, so a "second of walking" is exact.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent

from open_garden_planner.core.scene3d import Material, Params, Record, Transform
from open_garden_planner.core.scene3d.camera import CameraPose, OrbitCamera
from open_garden_planner.core.scene3d.walk import (
    EYE_HEIGHTS_CM,
    PITCH_LIMIT_DEG,
    RUN_FACTOR,
    WALK_FOV_DEG,
    WALK_SPEED_CM_S,
    WALKER_RADIUS_CM,
    build_world,
    is_free,
)
from open_garden_planner.ui.view3d.orbit_input import CLICK_SLOP_PX, OrbitInput
from open_garden_planner.ui.view3d.walk_mode import (
    LOOK_DEG_PER_PX,
    PASSED_ON_MODIFIERS,
    WALK_STEP_MS,
    WALKER_KEYS,
    WalkMode,
)

NONE, LEFT, RIGHT = Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton
PLAIN, SHIFT = Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier
CTRL, ALT, META = (Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.AltModifier,
                   Qt.KeyboardModifier.MetaModifier)
K = Qt.Key


def box(item_id: str, east: float, north: float, width: float, depth: float) -> Record:
    half_w, half_d = width / 2.0, depth / 2.0
    ring = ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))
    return Record(item_id=item_id, kind="RAISED_BED", shape="rectangle", footprints=(ring,),
                  transform=Transform(east, north), material=Material("RAISED_BED"),
                  height_cm=180.0, params=Params({"seed": item_id}))


def world_of(*records: Record, width: float = 2000.0, depth: float = 2000.0):
    return build_world({record.item_id: record for record in records}, width, depth)


class Bench:
    """The engine's window played by a QObject, both filters on it in the app's order."""

    def __init__(self) -> None:
        self.camera = OrbitCamera(CameraPose((1000.0, 1000.0), 2000.0, 30.0, 45.0))
        self.window = QObject()
        self.orbit = OrbitInput(self.camera, lambda: 600.0)
        self.walk = WalkMode()
        self.window.installEventFilter(self.orbit)
        self.window.installEventFilter(self.walk)     # installed LAST: it sees events first
        self.now = 50.0
        self.walk.clock = lambda: self.now
        self.changes = 0
        self.lefts = 0
        self.walk.changed.connect(self._changed)
        self.walk.left.connect(self._left)

    def _changed(self) -> None:
        self.changes += 1

    def _left(self) -> None:
        self.lefts += 1

    def enter(self, world: Any = None, at=(1000.0, 1000.0), yaw: float = 0.0) -> None:
        assert self.walk.enter(world if world is not None else world_of(), at, yaw) is True

    def key(self, key: Qt.Key, *, down: bool = True, modifiers=PLAIN, repeat: bool = False) -> bool:
        kind = QEvent.Type.KeyPress if down else QEvent.Type.KeyRelease
        return QCoreApplication.sendEvent(self.window, QKeyEvent(kind, key, modifiers, "", repeat))

    def override(self, key: Qt.Key, modifiers=PLAIN) -> tuple[bool, bool]:
        """Qt's ``ShortcutOverride`` for ``key``, as Qt sends it to the view's window
        before it looks for a shortcut: (filtered, accepted) — accepted means "no
        shortcut of the app fires"."""
        event = QKeyEvent(QEvent.Type.ShortcutOverride, key, modifiers)
        event.ignore()
        filtered = QCoreApplication.sendEvent(self.window, event)
        return filtered, event.isAccepted()

    def mouse(self, kind: QEvent.Type, x: float, y: float, button=NONE, buttons=NONE) -> bool:
        event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), button, buttons, PLAIN)
        return QCoreApplication.sendEvent(self.window, event)

    def tick(self, seconds: float) -> None:
        """Let ``seconds`` pass and fire the step timer's slot once."""
        self.now += seconds
        self.walk.step()   # what the timer calls

    @property
    def at(self) -> tuple[float, float]:
        state = self.walk.state
        assert state is not None
        return state.shown


@pytest.fixture()
def bench(qtbot) -> Bench:  # noqa: ARG001 - Qt init
    return Bench()


# ── inactive: it is not there ────────────────────────────────────────────────


def test_while_not_walking_every_event_goes_on_to_the_orbit_camera(bench: Bench) -> None:
    assert bench.walk.active is False
    assert bench.key(K.Key_W) is False and bench.key(K.Key_Escape) is False
    assert bench.key(K.Key_PageUp) is True, "the orbit filter's zoom"
    assert bench.camera.goal.distance_cm < 2000.0
    bench.mouse(QEvent.Type.MouseButtonPress, 10.0, 10.0, RIGHT, RIGHT)
    bench.mouse(QEvent.Type.MouseMove, 60.0, 10.0, NONE, RIGHT)
    assert bench.camera.goal.yaw_deg > 30.0, "the orbit drag"
    assert bench.changes == 0 and bench.walk.moving is False
    with pytest.raises(RuntimeError, match="not in walk mode"):
        bench.walk.camera()


# ── walking ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("key", "east", "north"), [
    (K.Key_W, 0.0, 1.0), (K.Key_Up, 0.0, 1.0), (K.Key_S, 0.0, -1.0), (K.Key_Down, 0.0, -1.0),
    (K.Key_D, 1.0, 0.0), (K.Key_Right, 1.0, 0.0), (K.Key_A, -1.0, 0.0), (K.Key_Left, -1.0, 0.0),
])
def test_wasd_and_the_arrow_keys_walk(bench: Bench, key: Qt.Key, east: float, north: float) -> None:
    bench.enter()
    assert bench.key(key) is True and bench.walk.moving is True
    bench.tick(1.0 / 4.0)
    bench.tick(1.0 / 4.0)
    assert bench.at == pytest.approx((1000.0 + east * WALK_SPEED_CM_S / 2.0,
                                      1000.0 + north * WALK_SPEED_CM_S / 2.0), abs=1e-6)
    assert bench.key(key, down=False) is True
    assert bench.walk.moving is False, "no key held: no timer, an idle view costs nothing"
    before = bench.at
    bench.tick(1.0)
    assert bench.at == before


def test_the_step_timer_runs_only_while_a_walking_key_is_held(bench: Bench) -> None:
    bench.enter()
    assert bench.walk._timer.interval() == WALK_STEP_MS  # noqa: SLF001
    assert bench.walk._timer.isActive() is False  # noqa: SLF001
    bench.key(K.Key_W)
    bench.key(K.Key_D)
    assert bench.walk._timer.isActive() is True  # noqa: SLF001
    bench.key(K.Key_W, down=False)
    assert bench.walk._timer.isActive() is True, "D is still held"  # noqa: SLF001
    bench.key(K.Key_D, down=False)
    assert bench.walk._timer.isActive() is False  # noqa: SLF001
    bench.key(K.Key_W)
    bench.key(K.Key_S)
    assert bench.walk._timer.isActive() is False, "ahead and back cancel: standing still"  # noqa: SLF001


def test_shift_runs(bench: Bench) -> None:
    bench.enter()
    bench.key(K.Key_Shift, modifiers=SHIFT)
    assert bench.walk.moving is False, "Shift alone walks nowhere"
    bench.key(K.Key_W, modifiers=SHIFT)
    bench.tick(0.25)
    assert bench.at[1] - 1000.0 == pytest.approx(WALK_SPEED_CM_S * RUN_FACTOR * 0.25, abs=1e-6)
    bench.key(K.Key_Shift, down=False)
    bench.tick(0.25)
    assert bench.at[1] - 1000.0 == pytest.approx(WALK_SPEED_CM_S * (RUN_FACTOR + 1.0) * 0.25, abs=1e-6)


def test_a_key_change_is_applied_after_the_time_before_it_was_walked(bench: Bench) -> None:
    """A fifth of a second ahead, then — WITHOUT a timer tick in between — the key
    changes: that time is walked ahead first. The pace does not depend on when the
    timer happens to fire."""
    bench.enter()
    bench.key(K.Key_W)
    bench.now += 0.2
    bench.key(K.Key_D)                      # no tick since the press
    assert bench.at == pytest.approx((1000.0, 1000.0 + WALK_SPEED_CM_S * 0.2), abs=1e-6)
    bench.now += 0.2
    bench.key(K.Key_W, down=False)
    diagonal = WALK_SPEED_CM_S * 0.2 / math.sqrt(2.0)
    assert bench.at == pytest.approx((1000.0 + diagonal, 1000.0 + WALK_SPEED_CM_S * 0.2 + diagonal),
                                     abs=1e-6)


def test_auto_repeat_changes_nothing(bench: Bench) -> None:
    bench.enter()
    bench.key(K.Key_W)
    for _ in range(20):
        assert bench.key(K.Key_W, repeat=True) is True
        assert bench.key(K.Key_W, down=False, repeat=True) is True   # X11 sends such pairs
    bench.tick(1.0 / 8.0)
    assert bench.at[1] - 1000.0 == pytest.approx(WALK_SPEED_CM_S / 8.0, abs=1e-6)
    assert bench.walk.moving is True


def test_a_wall_stops_the_walker_through_the_event_path_too(bench: Bench) -> None:
    wall = box("wall", 1000.0, 1300.0, 1900.0, 30.0)
    bench.enter(world_of(wall))
    bench.key(K.Key_W)
    for _ in range(100):
        bench.tick(0.1)
    assert bench.at[1] == pytest.approx(1300.0 - 15.0 - WALKER_RADIUS_CM, abs=1e-3)


# ── looking ──────────────────────────────────────────────────────────────────


def test_a_drag_looks_around_right_is_right_and_down_is_down(bench: Bench) -> None:
    bench.enter(yaw=10.0)
    assert bench.mouse(QEvent.Type.MouseButtonPress, 100.0, 100.0, LEFT, LEFT) is True, (
        "the press goes on to the orbit filter (a click still picks), which takes it")
    assert bench.mouse(QEvent.Type.MouseMove, 140.0, 80.0, NONE, LEFT) is True
    state = bench.walk.state
    assert state is not None
    assert state.yaw_deg == pytest.approx(10.0 + 40.0 * LOOK_DEG_PER_PX)
    assert state.pitch_deg == pytest.approx(20.0 * LOOK_DEG_PER_PX), "the mouse went UP: so does the view"
    assert state.shown == (1000.0, 1000.0), "looking never moves the walker"
    bench.mouse(QEvent.Type.MouseMove, 140.0, 5000.0, NONE, LEFT)
    assert bench.walk.state.pitch_deg == -PITCH_LIMIT_DEG  # type: ignore[union-attr]
    bench.mouse(QEvent.Type.MouseButtonRelease, 140.0, 5000.0, LEFT, NONE)
    assert bench.mouse(QEvent.Type.MouseMove, 300.0, 300.0, NONE, NONE) is False, "a hover"
    assert bench.walk.state.yaw_deg == pytest.approx(10.0 + 40.0 * LOOK_DEG_PER_PX)  # type: ignore[union-attr]


def test_a_left_drag_turns_only_once_it_leaves_the_click_slop_and_then_ends_the_click(
        bench: Bench) -> None:
    """Review 1, P2-4: walk mode keeps every move to itself, so the orbit filter never
    saw a flick and picked on the release — a look that turned the view AND selected.
    Now a left press that stays within ``CLICK_SLOP_PX`` turns nothing (it is still a
    click, as in orbit); a move past it turns by ALL of the way and says ``turned``,
    which the workspace hands to ``OrbitInput.cancel_click``."""
    turned: list[int] = []
    bench.walk.turned.connect(lambda: turned.append(1))
    bench.walk.turned.connect(bench.orbit.cancel_click)
    bench.enter(yaw=10.0)
    bench.mouse(QEvent.Type.MouseButtonPress, 100.0, 100.0, LEFT, LEFT)
    assert bench.mouse(QEvent.Type.MouseMove, 102.0, 101.0, NONE, LEFT) is True
    assert bench.mouse(QEvent.Type.MouseMove, 100.0, 100.0 + CLICK_SLOP_PX, NONE, LEFT) is True
    assert bench.walk.state.yaw_deg == 10.0 and turned == []  # type: ignore[union-attr]
    assert bench.orbit._press is not None, "still a click in the making"  # noqa: SLF001
    bench.mouse(QEvent.Type.MouseMove, 110.0, 100.0, NONE, LEFT)
    assert bench.walk.state.yaw_deg == pytest.approx(10.0 + 10.0 * LOOK_DEG_PER_PX)  # type: ignore[union-attr]
    assert turned == [1] and bench.orbit._press is None  # noqa: SLF001
    bench.mouse(QEvent.Type.MouseMove, 112.0, 100.0, NONE, LEFT)
    assert turned == [1], "said once per press"
    bench.mouse(QEvent.Type.MouseButtonRelease, 112.0, 100.0, LEFT, NONE)
    # a right drag can never be a click: it turns at once
    bench.mouse(QEvent.Type.MouseButtonPress, 100.0, 100.0, RIGHT, RIGHT)
    bench.mouse(QEvent.Type.MouseMove, 102.0, 100.0, NONE, RIGHT)
    assert bench.walk.state.yaw_deg == pytest.approx(10.0 + 14.0 * LOOK_DEG_PER_PX)  # type: ignore[union-attr]
    assert turned == [1]


def test_walking_never_touches_the_orbit_camera(bench: Bench) -> None:
    """Gate G7's root: every gesture that would move the orbit camera is taken or
    swallowed while walking, so leaving shows the pose the user had — exactly."""
    pose, goal = bench.camera.pose, bench.camera.goal
    bench.enter()
    bench.key(K.Key_W)
    bench.tick(0.3)
    for key in (K.Key_Up, K.Key_Left, K.Key_PageUp, K.Key_PageDown, K.Key_Home):
        bench.key(key)
        bench.key(key, down=False)
    bench.key(K.Key_Right, modifiers=Qt.KeyboardModifier.AltModifier)   # the orbit's Alt+arrow
    for buttons in (LEFT, RIGHT, LEFT | RIGHT, Qt.MouseButton.MiddleButton):
        bench.mouse(QEvent.Type.MouseButtonPress, 100.0, 100.0, LEFT, buttons)
        bench.mouse(QEvent.Type.MouseMove, 180.0, 160.0, NONE, buttons)
        bench.mouse(QEvent.Type.MouseButtonRelease, 180.0, 160.0, LEFT, NONE)
    wheel = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 240), NONE, PLAIN,
                        Qt.ScrollPhase.NoScrollPhase, False)
    assert QCoreApplication.sendEvent(bench.window, wheel) is True
    assert bench.camera.pose is pose and bench.camera.goal is goal and not bench.camera.moving


def test_keys_that_are_not_walk_keys_reach_the_application(bench: Bench) -> None:
    bench.enter()
    for key in (K.Key_Z, K.Key_Delete, K.Key_F7, K.Key_V, K.Key_Space):
        assert bench.key(key) is False, key
        assert bench.key(key, modifiers=Qt.KeyboardModifier.ControlModifier) is False


# ── the walker's keys belong to the walker (P0 of review 1) ─────────────────


def test_the_walkers_keys_are_stated_once() -> None:
    stated = {K.Key_W, K.Key_A, K.Key_S, K.Key_D, K.Key_Up, K.Key_Down, K.Key_Left, K.Key_Right,
              K.Key_Shift, K.Key_Escape}
    assert stated == WALKER_KEYS
    assert PASSED_ON_MODIFIERS == CTRL | ALT | META


@pytest.mark.parametrize("key", sorted(WALKER_KEYS, key=int))
def test_while_walking_a_walkers_key_is_claimed_before_any_shortcut(bench: Bench, key: Qt.Key) -> None:
    """Qt sends ``ShortcutOverride`` to the view's window BEFORE it looks for a
    shortcut; accepting it is what stops the main window's ``S`` (Snap to Grid) from
    firing (measured on the real main window, fix round 1). Shift still runs."""
    assert bench.override(key) == (False, False), "not walking: the app's shortcuts get it"
    bench.enter()
    assert bench.override(key) == (True, True)
    assert bench.override(key, SHIFT) == (True, True)
    for held in (CTRL, ALT, META, CTRL | SHIFT):
        assert bench.override(key, held) == (False, False), "a key with Ctrl or Alt is passed on"


@pytest.mark.parametrize("key", [K.Key_G, K.Key_Z, K.Key_Delete, K.Key_Space, K.Key_F7,
                                 K.Key_PageUp, K.Key_Home, K.Key_Q, K.Key_E])
def test_every_other_key_is_left_to_the_apps_shortcuts(bench: Bench, key: Qt.Key) -> None:
    bench.enter()
    assert bench.override(key) == (False, False)
    assert bench.override(key, CTRL) == (False, False)


def test_a_walkers_key_with_ctrl_or_alt_is_passed_on_and_does_not_walk(bench: Bench) -> None:
    bench.enter()
    for held in (CTRL, ALT):
        assert bench.key(K.Key_W, modifiers=held) is False, "Ctrl+W, Alt+W: the app's"
        assert bench.walk.moving is False
        assert bench.key(K.Key_Escape, modifiers=held) is False and bench.lefts == 0
        assert bench.key(K.Key_Up, modifiers=held) is True, (
            "an arrow is the orbit camera's too: swallowed, never walked, never orbited")
        assert bench.walk.moving is False
    assert bench.walk.state.shown == (1000.0, 1000.0)  # type: ignore[union-attr]


def test_a_held_key_released_with_ctrl_down_is_still_let_go(bench: Bench) -> None:
    """W held, then Ctrl pressed, then W released: the release carries Ctrl, and it is
    still the walker's — or W would be stuck down."""
    bench.enter()
    bench.key(K.Key_W)
    bench.tick(0.1)
    assert bench.key(K.Key_W, down=False, modifiers=CTRL) is True
    assert bench.walk.moving is False
    here = bench.at
    bench.tick(1.0)
    assert bench.at == here


def test_escape_asks_to_leave_and_is_not_passed_on(bench: Bench) -> None:
    bench.enter()
    assert bench.key(K.Key_Escape) is True and bench.lefts == 1
    assert bench.key(K.Key_Escape, repeat=True) is True and bench.lefts == 1
    assert bench.key(K.Key_Escape, down=False) is True
    assert bench.walk.active is True, "leaving is the workspace's to do (it restores the view)"


# ── entering, leaving, pausing ───────────────────────────────────────────────


def test_entering_starts_where_asked_and_says_so_once(bench: Bench) -> None:
    bench.enter(at=(400.0, 300.0), yaw=77.0)
    state = bench.walk.state
    assert state is not None and (state.east, state.north, state.yaw_deg) == (400.0, 300.0, 77.0)
    assert bench.changes == 1 and bench.walk.active
    eye, target, fov = bench.walk.camera()
    assert eye == (400.0, 300.0, EYE_HEIGHTS_CM[0]) and fov == WALK_FOV_DEG
    assert target[2] == pytest.approx(EYE_HEIGHTS_CM[0]), "looking level"


def test_entering_inside_a_solid_starts_on_the_nearest_free_ground(bench: Bench) -> None:
    house = box("house", 1000.0, 1000.0, 800.0, 600.0)
    world = world_of(house)
    assert bench.walk.enter(world, (1000.0, 760.0), 0.0) is True
    assert is_free(world, *bench.at) and bench.at[1] < 700.0


def test_no_free_ground_refuses_and_changes_nothing(bench: Bench) -> None:
    slab = box("slab", 100.0, 100.0, 400.0, 400.0)
    assert bench.walk.enter(world_of(slab, width=200.0, depth=200.0), (100.0, 100.0), 0.0) is False
    assert bench.walk.active is False and bench.changes == 0


def test_leaving_drops_the_walker_and_keeps_the_eye_height(bench: Bench) -> None:
    bench.walk.set_eye_height(EYE_HEIGHTS_CM[2])
    bench.enter()
    bench.key(K.Key_W)
    bench.walk.leave()
    assert bench.walk.active is False and bench.walk.state is None and bench.walk.world is None
    assert bench.walk.moving is False
    assert bench.key(K.Key_W) is False, "not walking: not its key any more"
    bench.enter()
    assert bench.walk.camera()[0][2] == EYE_HEIGHTS_CM[2]


@pytest.mark.parametrize("height", EYE_HEIGHTS_CM)
def test_the_eye_height_presets(bench: Bench, height: float) -> None:
    bench.enter()
    changes = bench.changes
    bench.walk.set_eye_height(height)
    eye, target, _fov = bench.walk.camera()
    assert eye[2] == height == target[2] and bench.walk.eye_height_cm == height
    assert bench.changes == changes + (height != EYE_HEIGHTS_CM[0])
    with pytest.raises(ValueError, match="one of"):
        bench.walk.set_eye_height(172.0)


def test_a_pause_lets_every_key_go_and_keeps_the_walker(bench: Bench) -> None:
    """The 3D pane was hidden while W was held: no key release will arrive. The walker
    stays where it is and does not run on when the pane comes back."""
    bench.enter()
    bench.key(K.Key_W, modifiers=SHIFT)
    bench.key(K.Key_Shift, modifiers=SHIFT)
    bench.tick(0.25)
    here = bench.at
    bench.walk.pause()
    assert bench.walk.moving is False and bench.walk.active is True
    bench.tick(5.0)
    assert bench.at == here
    bench.key(K.Key_D)
    assert bench.walk.moving is False, "paused: a key does not start the clock"
    bench.key(K.Key_D, down=False)
    bench.walk.resume()
    bench.tick(1.0)
    assert bench.at == here, "W was let go with the pause"
    bench.key(K.Key_W)
    bench.tick(0.25)
    assert bench.at[1] - here[1] == pytest.approx(WALK_SPEED_CM_S * 0.25, abs=1e-6), "and not running"


def test_losing_the_focus_lets_every_key_go(bench: Bench) -> None:
    bench.enter()
    bench.key(K.Key_W)
    bench.tick(0.1)
    QCoreApplication.sendEvent(bench.window, QEvent(QEvent.Type.FocusOut))
    assert bench.walk.moving is False
    here = bench.at
    bench.tick(1.0)
    assert bench.at == here


def test_a_world_that_changes_under_the_walker(bench: Bench) -> None:
    """An edit while walking: the same walker in the new world — moved off a solid
    that was put where it stands; out of walk mode when no ground is left."""
    bench.enter(at=(1000.0, 1000.0), yaw=40.0)
    bench.walk.set_world(world_of(box("far", 300.0, 300.0, 100.0, 100.0)))
    assert bench.at == (1000.0, 1000.0), "nothing near: it stays"
    onto = world_of(box("onto", 1000.0, 1000.0, 300.0, 300.0))
    bench.walk.set_world(onto)
    assert bench.walk.active and is_free(onto, *bench.at)
    assert math.hypot(bench.at[0] - 1000.0, bench.at[1] - 1000.0) <= 150.0 + 2.5 * WALKER_RADIUS_CM
    assert bench.walk.state.yaw_deg == 40.0  # type: ignore[union-attr]
    bench.walk.set_world(world_of(box("all", 1000.0, 1000.0, 4000.0, 4000.0)))
    assert bench.walk.active is False and bench.lefts == 1
    bench.walk.set_world(world_of())      # not walking: nothing happens
    assert bench.walk.active is False
