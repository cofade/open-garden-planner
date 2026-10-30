"""Pinch-to-zoom and two-finger pan on the canvas (issue #321).

Qt's own ``QPinchGesture`` recognizer decides when a gesture starts — it needs a
second finger, so a single-finger tap or drag is never claimed by the gesture
path. The tests drive the real ``CanvasView.eventFilter`` with a synthetic
``QGestureEvent`` (PyQt6 exposes ``QPinchGesture`` and its setters); the gesture
centre is passed the way Qt reports it, in **global** coordinates, so the
viewport conversion is covered. A real touchscreen's *delivery* is still the
owner's manual test; it cannot be synthesised from a headless process.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QGestureEvent, QPinchGesture

from open_garden_planner.app.settings import get_settings
from open_garden_planner.ui.canvas.canvas_view import CanvasView


@pytest.fixture()
def view(qtbot: object) -> CanvasView:
    """A shown, 800 x 600 canvas at zoom 1, framed on the middle of its plan."""
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.resize(800, 600)
    view.show()
    view.set_zoom(1.0)
    view.centerOn(2500.0, 1500.0)
    QApplication.processEvents()
    return view


class _Pinch(QPinchGesture):
    """A pinch gesture whose state a test can set (QGesture.state is read-only)."""

    def __init__(self, state: Qt.GestureState, total: float, global_center: QPointF) -> None:
        super().__init__()
        self._state = state
        self.setTotalScaleFactor(total)
        self.setCenterPoint(global_center)

    def state(self) -> Qt.GestureState:
        return self._state


def _global(view: CanvasView, local: QPointF) -> QPointF:
    """The global position Qt's recognizer would report for a viewport point."""
    return QPointF(view.viewport().mapToGlobal(local.toPoint()))


def _send(view: CanvasView, state: Qt.GestureState, total: float, local: QPointF) -> bool:
    """Deliver one gesture event for a viewport-local centre; True when handled."""
    gesture = _Pinch(state, total, _global(view, local))
    return QApplication.sendEvent(view.viewport(), QGestureEvent([gesture]))


def _assert_point_stays(
    view: CanvasView, scene_point: QPointF, screen: QPointF, tolerance: float = 1.0
) -> None:
    """The scene point under the gesture centre is still within ``tolerance`` pixels."""
    now = view.mapFromScene(scene_point)
    assert abs(now.x() - screen.x()) <= tolerance
    assert abs(now.y() - screen.y()) <= tolerance


def test_a_pinch_at_the_view_centre_doubles_the_zoom_and_keeps_the_point(
    view: CanvasView, qtbot: object
) -> None:
    """Synthetic pinch scale 2.0 at the viewport centre (acceptance criterion 1)."""
    # The gesture centre is global, so the conversion is only proved off the origin.
    view.move(700, 300)
    QApplication.processEvents()
    anchor = QPointF(view.viewport().rect().center())
    before = view.mapToScene(anchor.toPoint())
    assert view.zoom_factor == pytest.approx(1.0)

    assert _send(view, Qt.GestureState.GestureStarted, 1.0, anchor) is True
    assert _send(view, Qt.GestureState.GestureUpdated, 2.0, anchor) is True

    assert view.zoom_factor == pytest.approx(2.0)
    _assert_point_stays(view, before, anchor)


def test_a_pinch_clamps_at_the_maximum_zoom(view: CanvasView) -> None:
    """A pinch beyond the maximum stops there; the anchor still holds."""
    view.set_zoom(view.max_zoom / 4.0)
    anchor = QPointF(view.viewport().rect().center())
    before = view.mapToScene(anchor.toPoint())

    assert _send(view, Qt.GestureState.GestureStarted, 1.0, anchor) is True
    assert _send(view, Qt.GestureState.GestureUpdated, 8.0, anchor) is True

    assert view.zoom_factor == pytest.approx(view.max_zoom)
    _assert_point_stays(view, before, anchor)


def test_a_pinch_below_the_minimum_stops_at_it(view: CanvasView) -> None:
    view.set_zoom(view.min_zoom * 4.0)
    anchor = QPointF(view.viewport().rect().center())
    assert _send(view, Qt.GestureState.GestureStarted, 8.0, anchor) is True
    assert _send(view, Qt.GestureState.GestureUpdated, 1.0, anchor) is True
    assert view.zoom_factor == pytest.approx(view.min_zoom)


def test_two_fingers_move_the_view_and_the_content_follows_them(view: CanvasView) -> None:
    """Two fingers dragged 60 px right take the plan with them; no zoom."""
    anchor = QPointF(view.viewport().rect().center())
    before = view.mapToScene(anchor.toPoint())
    zoom = view.zoom_factor

    assert _send(view, Qt.GestureState.GestureStarted, 1.0, anchor) is True
    assert _send(view, Qt.GestureState.GestureUpdated, 1.0, anchor + QPointF(60.0, 0.0)) is True

    assert view.zoom_factor == pytest.approx(zoom)  # a pure pan never zooms
    # the scene point that was under the centre is now 60 px to the right of it
    now = view.mapFromScene(before)
    assert now.x() == pytest.approx(anchor.x() + 60.0, abs=1.0)
    assert now.y() == pytest.approx(anchor.y(), abs=1.0)


def test_a_pinch_that_also_moves_keeps_the_point_under_the_new_centre(view: CanvasView) -> None:
    """Pan first, zoom second: the combined step must not drift by (1 - ratio)·delta."""
    anchor = QPointF(view.viewport().rect().center())
    moved = anchor + QPointF(70.0, 0.0)
    before = view.mapToScene(anchor.toPoint())

    assert _send(view, Qt.GestureState.GestureStarted, 1.0, anchor) is True
    assert _send(view, Qt.GestureState.GestureUpdated, 2.0, moved) is True

    assert view.zoom_factor == pytest.approx(2.0)
    # 2 px, not 1: the scrollbar's unit is a scene centimetre, so at zoom 2 its
    # integer steps land on two-pixel boundaries. A pure pinch holds to one pixel.
    _assert_point_stays(view, before, moved, tolerance=2.0)


def test_starting_a_pinch_releases_the_first_fingers_mouse_press(
    view: CanvasView, qtbot: object
) -> None:
    """Qt synthesises a press for the first finger before the second lands. A pinch
    that starts on an item must release it where it was pressed, not drag it."""
    anchor = QPointF(view.viewport().rect().center())
    releases: list[QPointF] = []

    class Watch(QObject):
        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            if event.type() == QEvent.Type.MouseButtonRelease:
                release = event
                releases.append(QPointF(release.position()))  # type: ignore[attr-defined]
            return False

    watcher = Watch()
    view.viewport().installEventFilter(watcher)
    try:
        QApplication.sendEvent(
            view.viewport(),
            _mouse(view, anchor.toPoint(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
        )
        assert view._touch_mouse_press is not None
        assert _send(view, Qt.GestureState.GestureStarted, 1.0, anchor) is True
        assert view._touch_mouse_press is None
        assert releases == [anchor]
    finally:
        view.viewport().removeEventFilter(watcher)


def test_a_pinch_puts_a_dragged_item_back_and_leaves_no_undo_step(view: CanvasView) -> None:
    """The outcome, not just the release: the first finger had already moved the item.

    The press is a normal item drag; the second finger starts the pinch mid-drag.
    The item must be back where the drag began, and the release must not push a
    move command (the user asked to zoom, not to move).
    """
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import PolygonItem

    item = PolygonItem(
        [QPointF(0.0, 0.0), QPointF(200.0, 0.0), QPointF(200.0, 200.0), QPointF(0.0, 200.0)],
        object_type=ObjectType.HOUSE,
    )
    view.scene().addItem(item)
    item.setPos(view.mapToScene(view.viewport().rect().center()))
    item.setSelected(True)
    start = item.pos()
    depth = len(view._command_manager._undo_stack)

    press = view.mapFromScene(item.sceneBoundingRect().center())
    QApplication.sendEvent(
        view.viewport(),
        _mouse(view, press, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
    )
    QApplication.sendEvent(
        view.viewport(),
        _mouse(view, press + QPoint(40, 25), Qt.MouseButton.NoButton,
               Qt.MouseButton.LeftButton),
    )
    moved = item.pos()
    assert moved != start, "the test's first finger really dragged the item"

    anchor = QPointF(view.viewport().rect().center())
    assert _send(view, Qt.GestureState.GestureStarted, 1.0, anchor) is True
    assert item.pos() == start, "the pinch put the dragged item back"
    assert len(view._command_manager._undo_stack) == depth, "no move step was committed"


def test_a_pinch_over_empty_canvas_keeps_the_selection(view: CanvasView) -> None:
    """The first finger's click on empty canvas clears the selection; a pinch restores it."""
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import PolygonItem

    item = PolygonItem(
        [QPointF(0.0, 0.0), QPointF(200.0, 0.0), QPointF(200.0, 200.0), QPointF(0.0, 200.0)],
        object_type=ObjectType.HOUSE,
    )
    view.scene().addItem(item)
    item.setPos(1200.0, 800.0)
    item.setSelected(True)
    empty_point = view.viewport().rect().center() + QPoint(200, 200)
    QApplication.sendEvent(
        view.viewport(),
        _mouse(view, empty_point, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
    )
    assert not item.isSelected(), "the press on empty canvas cleared the selection"

    anchor = QPointF(view.viewport().rect().center())
    assert _send(view, Qt.GestureState.GestureStarted, 1.0, anchor) is True
    assert item.isSelected(), "the pinch restored the selection it did not mean to clear"


def test_a_native_trackpad_pinch_zooms_at_its_position(view: CanvasView) -> None:
    """The trackpad path: `ZoomNativeGesture` maps `1 + value` onto `_zoom_at`."""
    from PyQt6.QtGui import QNativeGestureEvent, QPointingDevice

    anchor = QPointF(view.viewport().rect().center())
    before = view.mapToScene(anchor.toPoint())
    event = QNativeGestureEvent(
        Qt.NativeGestureType.ZoomNativeGesture,
        QPointingDevice.primaryPointingDevice(),
        2,
        anchor,
        anchor,
        QPointF(view.viewport().mapToGlobal(anchor.toPoint())),
        1.0,  # a doubling
        QPointF(0.0, 0.0),
    )
    assert QApplication.sendEvent(view.viewport(), event) is True
    assert view.zoom_factor == pytest.approx(2.0)
    _assert_point_stays(view, before, anchor)


def test_the_gesture_is_adopted_and_finished_cleanly(view: CanvasView) -> None:
    """Enabled mid-gesture: the first update adopts; a finish forgets the values."""
    anchor = QPointF(view.viewport().rect().center())
    view._pinch_scale = None
    view._pinch_center = None
    assert _send(view, Qt.GestureState.GestureUpdated, 3.0, anchor) is True
    assert view.zoom_factor == pytest.approx(1.0)  # adopted, not applied
    assert view._pinch_scale == pytest.approx(3.0)

    assert _send(view, Qt.GestureState.GestureFinished, 3.0, anchor) is True
    assert view._pinch_scale is None and view._pinch_center is None


def test_the_setting_off_ignores_gesture_events(view: CanvasView) -> None:
    """Off: the filter is gone and a gesture moves nothing."""
    view.set_touch_gestures_enabled(False)
    anchor = QPointF(view.viewport().rect().center())
    assert _send(view, Qt.GestureState.GestureStarted, 1.0, anchor) is False
    assert _send(view, Qt.GestureState.GestureUpdated, 2.0, anchor) is False
    assert view.zoom_factor == pytest.approx(1.0)

    view.set_touch_gestures_enabled(True)
    assert _send(view, Qt.GestureState.GestureStarted, 1.0, anchor) is True
    assert _send(view, Qt.GestureState.GestureUpdated, 2.0, anchor) is True
    assert view.zoom_factor == pytest.approx(2.0)


def test_the_preference_ships_on_and_round_trips() -> None:
    """The setting is a normal AppSettings boolean (default on, saved when changed)."""
    settings = get_settings()
    original = settings.touch_gestures_enabled
    try:
        assert original is True  # additive, so it ships on
        settings.touch_gestures_enabled = False
        assert get_settings().touch_gestures_enabled is False
        settings.touch_gestures_enabled = True
        assert get_settings().touch_gestures_enabled is True
    finally:
        settings.touch_gestures_enabled = original


def test_the_window_applies_the_preference_at_startup_and_from_the_dialog(
    qtbot: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wiring the view cannot prove: the window's startup and Preferences paths.

    A line that can be deleted while every other test still passes is how the
    3D look settings lost their live apply once; this is the window's own test.
    """
    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog

    settings = get_settings()
    original = settings.touch_gestures_enabled
    try:
        settings.touch_gestures_enabled = False
        settings.show_welcome_on_startup = False
        app = GardenPlannerApp()
        qtbot.addWidget(app)  # type: ignore[attr-defined]
        QApplication.processEvents()  # the QTimer.singleShot(0, ...) startup apply
        assert app.canvas_view._touch_gestures_enabled is False

        def accept_with_gestures(self: PreferencesDialog) -> int:
            self._touch_gestures_check.setChecked(True)
            self._save_and_accept()
            return int(QDialog.DialogCode.Accepted)

        monkeypatch.setattr(PreferencesDialog, "exec", accept_with_gestures)
        app._on_preferences()
        assert get_settings().touch_gestures_enabled is True
        assert app.canvas_view._touch_gestures_enabled is True
    finally:
        settings.touch_gestures_enabled = original


def test_a_middle_mouse_drag_still_pans(view: CanvasView) -> None:
    """The mouse pan the gesture helper was extracted from still works."""
    center = view.viewport().rect().center()
    before = view.mapToScene(center)
    QApplication.sendEvent(
        view.viewport(),
        _mouse(view, QPoint(center.x(), center.y()), Qt.MouseButton.MiddleButton,
               Qt.MouseButton.MiddleButton),
    )
    QApplication.sendEvent(
        view.viewport(),
        _mouse(view, QPoint(center.x() + 70, center.y()), Qt.MouseButton.NoButton,
               Qt.MouseButton.MiddleButton),
    )
    now = view.mapFromScene(before)
    assert now.x() == pytest.approx(center.x() + 70, abs=1.0)
    QApplication.sendEvent(
        view.viewport(),
        _mouse(view, QPoint(center.x() + 70, center.y()), Qt.MouseButton.MiddleButton,
               Qt.MouseButton.NoButton),
    )


def _mouse(view: CanvasView, position: QPoint, button: Qt.MouseButton,
           buttons: Qt.MouseButton):
    from PyQt6.QtGui import QMouseEvent

    kind = (QEvent.Type.MouseButtonPress if button != Qt.MouseButton.NoButton
            else QEvent.Type.MouseMove)
    return QMouseEvent(
        kind,
        QPointF(position),
        QPointF(view.viewport().mapToGlobal(position)),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
