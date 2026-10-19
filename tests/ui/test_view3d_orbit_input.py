"""Mouse, wheel and keys → the orbit camera (Phase 17 L1.3, ADR-065).

``ui/view3d/orbit_input.OrbitInput`` is the event filter the workspace puts on the
engine's native window. Here it sits on a plain ``QObject`` and is sent real Qt
events — it needs no window and no GPU.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent

from open_garden_planner.core.scene3d.camera import FOV_DEG, CameraPose, OrbitCamera
from open_garden_planner.ui.view3d.orbit_input import (
    DRAG_ORBIT_DEG_PER_PX,
    DRAG_ZOOM_PER_PX,
    KEY_ORBIT_DEG,
    KEY_PAN_SHARE,
    KEY_ZOOM,
    WHEEL_ZOOM_PER_NOTCH,
    OrbitInput,
)

LEFT, RIGHT, MIDDLE = (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton,
                       Qt.MouseButton.MiddleButton)
NONE = Qt.MouseButton.NoButton
NO_MOD, ALT = Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.AltModifier
HEIGHT = 600.0
START = CameraPose((1000.0, 1000.0), 2000.0, 0.0, 45.0)


class Bench:
    """A camera, the filter, and a QObject that plays the 3D window."""

    def __init__(self) -> None:
        self.camera = OrbitCamera(START)
        self.window = QObject()
        self.filter = OrbitInput(self.camera, lambda: HEIGHT)
        self.window.installEventFilter(self.filter)
        self.moves = 0
        self.resets = 0
        self.filter.moved.connect(self._count_move)
        self.filter.reset_requested.connect(self._count_reset)

    def _count_move(self) -> None:
        self.moves += 1

    def _count_reset(self) -> None:
        self.resets += 1

    def mouse(self, kind: QEvent.Type, x: float, y: float, button: Qt.MouseButton,
              buttons: Qt.MouseButton) -> bool:
        event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), button, buttons, NO_MOD)
        return self.filter.eventFilter(self.window, event)

    def drag(self, buttons: Qt.MouseButton, dx: float, dy: float) -> None:
        first = LEFT if buttons & LEFT else (RIGHT if buttons & RIGHT else MIDDLE)
        assert self.mouse(QEvent.Type.MouseButtonPress, 100.0, 100.0, first, buttons) is True
        assert self.mouse(QEvent.Type.MouseMove, 100.0 + dx, 100.0 + dy, NONE, buttons) is True
        assert self.mouse(QEvent.Type.MouseButtonRelease, 100.0 + dx, 100.0 + dy, first, NONE) is True

    def key(self, key: Qt.Key, modifiers: Qt.KeyboardModifier = NO_MOD) -> bool:
        return self.filter.eventFilter(
            self.window, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))

    def wheel(self, angle_y: int) -> bool:
        event = QWheelEvent(QPointF(50.0, 50.0), QPointF(50.0, 50.0), QPoint(0, 0),
                            QPoint(0, angle_y), NONE, NO_MOD, Qt.ScrollPhase.NoScrollPhase, False)
        return self.filter.eventFilter(self.window, event)


@pytest.fixture()
def bench(qtbot) -> Bench:  # noqa: ARG001 - Qt init
    return Bench()


def test_a_right_drag_orbits(bench: Bench) -> None:
    bench.drag(RIGHT, 40.0, -20.0)
    assert bench.camera.goal.yaw_deg == pytest.approx(40.0 * DRAG_ORBIT_DEG_PER_PX)
    assert bench.camera.goal.pitch_deg == pytest.approx(45.0 - 20.0 * DRAG_ORBIT_DEG_PER_PX)
    assert bench.camera.goal.target == START.target and bench.moves == 1


@pytest.mark.parametrize("button", [LEFT, MIDDLE])
def test_a_left_or_middle_drag_pans_and_the_ground_follows_the_hand(bench: Bench,
                                                                    button: Qt.MouseButton) -> None:
    bench.drag(button, 60.0, 0.0)
    cm_per_px = 2.0 * 2000.0 * math.tan(math.radians(FOV_DEG) / 2.0) / HEIGHT
    east, north = bench.camera.goal.target
    assert east == pytest.approx(1000.0 - 60.0 * cm_per_px)   # looking north: right is east
    assert north == pytest.approx(1000.0)
    assert bench.camera.goal.distance_cm == 2000.0 and bench.camera.goal.yaw_deg == 0.0


def test_both_buttons_zoom_down_is_away(bench: Bench) -> None:
    bench.drag(LEFT | RIGHT, 0.0, 100.0)
    assert bench.camera.goal.distance_cm == pytest.approx(2000.0 * math.exp(100.0 * DRAG_ZOOM_PER_PX))


def test_the_wheel_zooms_up_is_closer(bench: Bench) -> None:
    assert bench.wheel(120) is True
    assert bench.camera.goal.distance_cm == pytest.approx(2000.0 * WHEEL_ZOOM_PER_NOTCH)
    assert bench.wheel(-240) is True
    assert bench.camera.goal.distance_cm == pytest.approx(2000.0 / WHEEL_ZOOM_PER_NOTCH)
    assert bench.wheel(0) is False, "a horizontal scroll is not ours"


@pytest.mark.parametrize(("key", "east", "north"), [
    (Qt.Key.Key_Right, 1.0, 0.0), (Qt.Key.Key_Left, -1.0, 0.0),
    (Qt.Key.Key_Up, 0.0, 1.0), (Qt.Key.Key_Down, 0.0, -1.0),
])
def test_the_arrow_keys_pan_by_a_tenth_of_the_view(bench: Bench, key: Qt.Key, east: float,
                                                   north: float) -> None:
    assert bench.key(key) is True
    step = KEY_PAN_SHARE * 2.0 * 2000.0 * math.tan(math.radians(FOV_DEG) / 2.0)
    assert bench.camera.goal.target == pytest.approx((1000.0 + east * step, 1000.0 + north * step))


def test_alt_arrows_orbit_and_the_page_keys_zoom(bench: Bench) -> None:
    assert bench.key(Qt.Key.Key_Right, ALT) is True
    assert bench.camera.goal.yaw_deg == KEY_ORBIT_DEG
    assert bench.key(Qt.Key.Key_Up, ALT) is True
    assert bench.camera.goal.pitch_deg == 45.0 + KEY_ORBIT_DEG
    assert bench.camera.goal.target == START.target
    assert bench.key(Qt.Key.Key_PageUp) is True
    assert bench.camera.goal.distance_cm == pytest.approx(2000.0 * KEY_ZOOM)
    assert bench.key(Qt.Key.Key_PageDown) is True
    assert bench.camera.goal.distance_cm == pytest.approx(2000.0)


def test_home_asks_for_the_view_to_be_reset(bench: Bench) -> None:
    assert bench.key(Qt.Key.Key_Home) is True
    assert bench.resets == 1 and bench.camera.goal == START


@pytest.mark.parametrize("key", [Qt.Key.Key_Escape, Qt.Key.Key_R, Qt.Key.Key_F7, Qt.Key.Key_Delete,
                                 Qt.Key.Key_Z])
def test_every_other_key_is_left_to_the_application(bench: Bench, key: Qt.Key) -> None:
    """Escape too: the Qt 3D controller frames the scene with it, and it is kept free
    for the walk mode's exit (L1.8). Shortcuts must keep working with the 3D view in
    focus, so the filter may not swallow what it does not use."""
    assert bench.key(key) is False
    assert bench.key(key, Qt.KeyboardModifier.ControlModifier) is False
    assert bench.camera.goal == START and bench.moves == 0


def test_a_mouse_that_only_hovers_moves_nothing(bench: Bench) -> None:
    assert bench.mouse(QEvent.Type.MouseMove, 300.0, 300.0, NONE, NONE) is False
    assert bench.camera.goal == START and bench.moves == 0


def test_a_drag_continues_from_where_the_mouse_was_last_seen(bench: Bench) -> None:
    bench.mouse(QEvent.Type.MouseButtonPress, 10.0, 10.0, RIGHT, RIGHT)
    for step in range(1, 11):
        bench.mouse(QEvent.Type.MouseMove, 10.0 + 5.0 * step, 10.0, NONE, RIGHT)
    assert bench.camera.goal.yaw_deg == pytest.approx(50.0 * DRAG_ORBIT_DEG_PER_PX)
    assert bench.moves == 10


def test_losing_focus_ends_a_drag_whose_release_never_arrives(bench: Bench) -> None:
    bench.mouse(QEvent.Type.MouseButtonPress, 10.0, 10.0, RIGHT, RIGHT)
    QCoreApplication.sendEvent(bench.window, QEvent(QEvent.Type.FocusOut))
    # the next move reports a button still down (as Qt does) from somewhere else entirely
    assert bench.mouse(QEvent.Type.MouseMove, 900.0, 900.0, NONE, RIGHT) is False
    assert bench.camera.goal == START


def test_a_gesture_that_changes_nothing_does_not_start_the_stepping(bench: Bench) -> None:
    bench.camera.orbit(0.0, 1000.0)   # already as steep as it gets
    bench.camera.snap()
    bench.mouse(QEvent.Type.MouseButtonPress, 10.0, 10.0, RIGHT, RIGHT)
    bench.mouse(QEvent.Type.MouseMove, 10.0, 60.0, NONE, RIGHT)   # steeper still
    assert bench.moves == 0 and bench.camera.moving is False


def test_the_filter_is_delivered_through_qts_own_event_path(bench: Bench) -> None:
    """Installed with ``installEventFilter`` and reached with ``sendEvent`` — the path
    the engine's window uses."""
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_PageUp, NO_MOD)
    assert QCoreApplication.sendEvent(bench.window, event) is True
    assert bench.camera.goal.distance_cm == pytest.approx(2000.0 * KEY_ZOOM)
