"""The click of the 3D view: a press and a release that pick (Phase 17 L1.8, gate G2).

``OrbitInput`` — the event filter on the engine's window — decides what is a click
and what is a drag, and a click calls ``host.pick(x, y)``: once, on a user's own
action, never on a move. Here the filter sits on a plain ``QObject`` and gets real
Qt events; the host is a double that counts.

The two thresholds, stated: at most ``CLICK_SLOP_PX`` (4 logical pixels) between
press and release — at ANY moment of the gesture — and at most ``CLICK_MAX_S``
(0.4 s). Inside them the camera does not move; a drag that leaves the slop starts
with all of the way it has come.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.scene3d.camera import CameraPose, OrbitCamera
from open_garden_planner.ui.view3d.orbit_input import (
    CLICK_MAX_S,
    CLICK_SLOP_PX,
    DRAG_ORBIT_DEG_PER_PX,
    OrbitInput,
)
from open_garden_planner.ui.view3d.quick3d.lifecycle import HostStateError

LEFT, RIGHT, MIDDLE = (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton,
                       Qt.MouseButton.MiddleButton)
NONE = Qt.MouseButton.NoButton
PLAIN = Qt.KeyboardModifier.NoModifier
CTRL, SHIFT, ALT = (Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier,
                    Qt.KeyboardModifier.AltModifier)
START = CameraPose((1000.0, 1000.0), 2000.0, 0.0, 45.0)


class Host:
    """``Quick3DHost.pick`` as the click needs it: an answer, or a refusal."""

    def __init__(self) -> None:
        self.asked: list[tuple[float, float]] = []
        self.answer: Any = "the hit"
        self.error: BaseException | None = None

    def pick(self, x: float, y: float) -> Any:
        self.asked.append((x, y))
        if self.error is not None:
            raise self.error
        return self.answer


class Bench:
    def __init__(self) -> None:
        self.camera = OrbitCamera(START)
        self.window = QObject()
        self.filter = OrbitInput(self.camera, lambda: 600.0)
        self.window.installEventFilter(self.filter)
        self.host = Host()
        self.filter.watch(self.host)
        self.now = 100.0
        self.filter.clock = lambda: self.now
        self.picked: list[tuple[Any, Any]] = []
        self.filter.picked.connect(lambda hit, modifiers: self.picked.append((hit, modifiers)))

    def send(self, kind: QEvent.Type, x: float, y: float, button: Qt.MouseButton,
             buttons: Qt.MouseButton, modifiers: Qt.KeyboardModifier = PLAIN) -> bool:
        event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), button, buttons, modifiers)
        return self.filter.eventFilter(self.window, event)

    def press(self, x: float, y: float, button: Qt.MouseButton = LEFT,
              buttons: Qt.MouseButton | None = None) -> None:
        self.send(QEvent.Type.MouseButtonPress, x, y, button, buttons if buttons is not None else button)

    def move(self, x: float, y: float, buttons: Qt.MouseButton = LEFT) -> bool:
        return self.send(QEvent.Type.MouseMove, x, y, NONE, buttons)

    def release(self, x: float, y: float, button: Qt.MouseButton = LEFT,
                modifiers: Qt.KeyboardModifier = PLAIN, buttons: Qt.MouseButton = NONE) -> None:
        self.send(QEvent.Type.MouseButtonRelease, x, y, button, buttons, modifiers)

    def click(self, x: float, y: float, modifiers: Qt.KeyboardModifier = PLAIN) -> None:
        self.press(x, y)
        self.release(x, y, modifiers=modifiers)


@pytest.fixture()
def bench(qtbot) -> Bench:  # noqa: ARG001 - Qt init
    return Bench()


def test_the_thresholds_are_the_stated_ones() -> None:
    assert (CLICK_SLOP_PX, CLICK_MAX_S) == (4.0, 0.4)


def test_a_press_and_a_release_in_place_pick_once_at_that_position(bench: Bench) -> None:
    bench.click(320.5, 240.25)
    assert bench.host.asked == [(320.5, 240.25)]
    assert bench.picked == [("the hit", PLAIN)]
    assert bench.camera.goal == START and not bench.camera.moving, "a click moves no camera"


def test_a_click_on_nothing_says_so(bench: Bench) -> None:
    bench.host.answer = None
    bench.click(10.0, 10.0)
    assert bench.picked == [(None, PLAIN)], "the ground and the sky: a hit of None, still a click"


@pytest.mark.parametrize("modifiers", [PLAIN, CTRL, SHIFT, CTRL | SHIFT, ALT])
def test_the_click_carries_its_modifiers(bench: Bench, modifiers) -> None:
    """Fix round 1: Ctrl and Shift are not the same to the canvas (a Ctrl click on a
    locked item keeps the selection, a Shift click clears it), so the bridge is told
    which were held, not only "toggle" (``selection_bridge.apply_click``)."""
    bench.click(50.0, 60.0, modifiers)
    assert bench.picked == [("the hit", modifiers)]


def test_a_cancelled_press_is_no_click(bench: Bench) -> None:
    """Walk mode turns the view with a drag and keeps the moves to itself; once it has
    turned it says so (``cancel_click``) and the release picks nothing (fix round 1)."""
    bench.press(100.0, 100.0)
    bench.filter.cancel_click()
    bench.release(101.0, 100.0)
    assert bench.picked == [] and bench.host.asked == []
    bench.click(100.0, 100.0)
    assert len(bench.picked) == 1, "the next click is a click again"


@pytest.mark.parametrize("offset", [(0.0, 0.0), (3.0, 0.0), (0.0, -4.0), (2.8, 2.8)])
def test_a_release_within_the_slop_is_still_a_click(bench: Bench, offset) -> None:
    bench.press(100.0, 100.0)
    bench.release(100.0 + offset[0], 100.0 + offset[1])
    assert len(bench.picked) == 1 and bench.host.asked == [(100.0 + offset[0], 100.0 + offset[1])]


@pytest.mark.parametrize("offset", [(4.1, 0.0), (0.0, 5.0), (3.0, 3.0), (-40.0, 25.0)])
def test_a_release_beyond_the_slop_picks_nothing(bench: Bench, offset) -> None:
    bench.press(100.0, 100.0)
    bench.release(100.0 + offset[0], 100.0 + offset[1])
    assert bench.picked == [] and bench.host.asked == []


def test_a_drag_never_selects_also_when_it_returns_to_where_it_began(bench: Bench) -> None:
    """Gate G2: more than the threshold at ANY moment of the gesture is a drag."""
    bench.press(100.0, 100.0)
    assert bench.move(130.0, 100.0) is True
    assert bench.move(100.0, 100.0) is True       # back on the press point
    bench.release(100.0, 100.0)
    assert bench.picked == [] and bench.host.asked == []
    assert bench.camera.goal == START, "30 px there and 30 px back: where it was"


def test_inside_the_slop_the_camera_rests_and_beyond_it_the_whole_way_is_applied(bench: Bench) -> None:
    """A click's jitter does not pan the plan; a drag loses nothing to the dead zone."""
    moved: list[int] = []
    bench.filter.moved.connect(lambda: moved.append(1))
    bench.press(100.0, 100.0)
    for x in (101.0, 102.0, 103.0, 104.0):
        assert bench.move(x, 100.0) is True
    assert bench.camera.goal == START and moved == [], "still a click in the making"
    bench.move(106.0, 100.0)
    panned = bench.camera.goal.target[0]
    assert panned != 1000.0 and moved == [1]
    reference = OrbitCamera(START)
    reference.drag_pixels(6.0, 0.0, viewport_height_px=600.0)
    assert panned == pytest.approx(reference.goal.target[0]), "all six pixels, not two"
    bench.release(106.0, 100.0)
    assert bench.picked == []


def test_a_press_held_too_long_is_not_a_click(bench: Bench) -> None:
    bench.press(100.0, 100.0)
    bench.now += CLICK_MAX_S + 0.01
    bench.release(100.0, 100.0)
    assert bench.picked == []
    bench.press(100.0, 100.0)
    bench.now += CLICK_MAX_S - 0.01
    bench.release(100.0, 100.0)
    assert len(bench.picked) == 1


@pytest.mark.parametrize("button", [RIGHT, MIDDLE])
def test_only_the_left_button_clicks(bench: Bench, button) -> None:
    bench.press(100.0, 100.0, button)
    bench.release(100.0, 100.0, button)
    assert bench.picked == [] and bench.host.asked == []


def test_a_second_button_during_the_press_ends_the_click(bench: Bench) -> None:
    bench.press(100.0, 100.0)
    bench.press(100.0, 100.0, RIGHT, LEFT | RIGHT)        # both down: the zoom gesture
    bench.release(100.0, 100.0, RIGHT, buttons=LEFT)
    bench.release(100.0, 100.0, LEFT)
    assert bench.picked == []
    bench.press(100.0, 100.0, LEFT, LEFT | RIGHT)         # pressed while another was held
    bench.release(100.0, 100.0, LEFT, buttons=RIGHT)
    assert bench.picked == []


def test_a_right_drag_still_orbits_from_its_first_pixel(bench: Bench) -> None:
    """The dead zone is the left button's alone: nothing else can become a click."""
    bench.press(100.0, 100.0, RIGHT)
    bench.move(102.0, 100.0, RIGHT)
    assert bench.camera.goal.yaw_deg == pytest.approx(2.0 * DRAG_ORBIT_DEG_PER_PX)


def test_a_host_that_cannot_answer_means_not_now_and_nothing_else(
        bench: Bench, caplog: pytest.LogCaptureFixture) -> None:
    """Gate G2: ``HostStateError`` (mid-resize, collapsed, minimised) → no selection
    change, no message — not even a log line at a level the log file keeps."""
    bench.host.error = HostStateError("pick(): the render target has not caught up")
    with caplog.at_level(logging.INFO, logger="open_garden_planner"):
        bench.click(100.0, 100.0)
    assert bench.host.asked == [(100.0, 100.0)] and bench.picked == []
    assert caplog.records == []
    bench.host.error = None
    bench.click(100.0, 100.0)
    assert len(bench.picked) == 1, "the next click works"


def test_any_other_failure_of_the_pick_is_one_plain_log_line_and_no_crash(
        bench: Bench, caplog: pytest.LogCaptureFixture) -> None:
    bench.host.error = RuntimeError("the scene's pickAt() returned nothing\n2026 ERROR forged line")
    with caplog.at_level(logging.DEBUG, logger="open_garden_planner"):
        bench.click(100.0, 100.0)
    assert bench.picked == []
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1 and "\n" not in errors[0].getMessage()
    assert "could not be picked" in errors[0].getMessage()


def test_without_a_host_a_click_is_nothing(qtbot) -> None:  # noqa: ARG001
    plain = OrbitInput(OrbitCamera(START), lambda: 600.0)
    seen: list[Any] = []
    plain.picked.connect(lambda hit, toggle: seen.append((hit, toggle)))
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        buttons = LEFT if kind == QEvent.Type.MouseButtonPress else NONE
        plain.eventFilter(None, QMouseEvent(kind, QPointF(5, 5), QPointF(5, 5), LEFT, buttons, PLAIN))
    assert seen == []


def test_losing_the_focus_ends_a_click_in_the_making(bench: Bench) -> None:
    bench.press(100.0, 100.0)
    QCoreApplication.sendEvent(bench.window, QEvent(QEvent.Type.FocusOut))
    bench.release(100.0, 100.0)
    assert bench.picked == []


def test_a_move_a_wheel_and_a_key_never_pick(bench: Bench) -> None:
    """The memory rule: a frame is taken from the live view on a CLICK, once — never
    on a mouse move, a hover, a wheel turn or a key."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QKeyEvent, QWheelEvent

    bench.move(50.0, 50.0, NONE)                               # a hover
    bench.press(10.0, 10.0, RIGHT)
    for step in range(1, 30):
        bench.move(10.0 + step, 10.0, RIGHT)                   # a drag
    bench.release(39.0, 10.0, RIGHT)
    bench.filter.eventFilter(bench.window, QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120), NONE, PLAIN,
        Qt.ScrollPhase.NoScrollPhase, False))
    bench.filter.eventFilter(bench.window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Home, PLAIN))
    assert bench.host.asked == []
    for _ in range(3):
        bench.click(20.0, 20.0)
    assert len(bench.host.asked) == 3, "one pick per click, and none besides"
