"""Pinch-to-zoom and two-finger pan on the canvas (issue #321).

The gesture state machine is fed touch positions directly: PyQt6 does not expose
``QTouchEvent.TouchPoint``, so a synthetic ``QTouchEvent`` cannot be built in a
test. Delivery (a real ``QTouchEvent`` reaching ``CanvasView.eventFilter``) is the
one step CI cannot prove; it is the manual test on a touch device. Everything
the gesture DOES — the anchored zoom, the clamp, the pan, and leaving a
single touch to the synthesised mouse path — is pinned here.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtWidgets import QApplication

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


def _fingers(center: QPointF, half_gap: float) -> list[QPointF]:
    return [center - QPointF(half_gap, 0.0), center + QPointF(half_gap, 0.0)]


def _moved(points: list[QPointF], delta: QPointF) -> list[QPointF]:
    return [point + delta for point in points]


def _assert_point_stays(view: CanvasView, scene_point: QPointF, screen: QPointF) -> None:
    """The scene point under the gesture centre is still within one pixel of it."""
    now = view.mapFromScene(scene_point)
    assert abs(now.x() - screen.x()) <= 1.0
    assert abs(now.y() - screen.y()) <= 1.0


def test_a_pinch_at_the_view_centre_doubles_the_zoom_and_keeps_the_point(view: CanvasView) -> None:
    """Synthetic pinch scale 2.0 at the viewport centre (acceptance criterion 1)."""
    anchor = QPointF(view.viewport().rect().center())
    before = view.mapToScene(anchor.toPoint())
    assert view.zoom_factor == pytest.approx(1.0)

    assert view._touch_started(_fingers(anchor, 40.0)) is True
    assert view._touch_moved(_fingers(anchor, 80.0)) is True

    assert view.zoom_factor == pytest.approx(2.0)
    _assert_point_stays(view, before, anchor)


def test_a_pinch_clamps_at_the_maximum_zoom(view: CanvasView) -> None:
    """A pinch beyond the maximum stops there; the anchor still holds."""
    view.set_zoom(view.max_zoom / 4.0)
    anchor = QPointF(view.viewport().rect().center())
    before = view.mapToScene(anchor.toPoint())

    assert view._touch_started(_fingers(anchor, 20.0)) is True
    assert view._touch_moved(_fingers(anchor, 160.0)) is True  # x8, past the clamp

    assert view.zoom_factor == pytest.approx(view.max_zoom)
    _assert_point_stays(view, before, anchor)


def test_a_pinch_below_the_minimum_stops_at_it(view: CanvasView) -> None:
    view.set_zoom(view.min_zoom * 4.0)
    anchor = QPointF(view.viewport().rect().center())
    assert view._touch_started(_fingers(anchor, 160.0)) is True
    assert view._touch_moved(_fingers(anchor, 20.0)) is True  # /8, below the floor
    assert view.zoom_factor == pytest.approx(view.min_zoom)


def test_two_fingers_move_the_view_and_the_content_follows_them(view: CanvasView) -> None:
    """Two fingers dragged 60 px right take the plan with them; no zoom."""
    anchor = QPointF(view.viewport().rect().center())
    before = view.mapToScene(anchor.toPoint())
    zoom = view.zoom_factor

    fingers = _fingers(anchor, 40.0)
    assert view._touch_started(fingers) is True
    assert view._touch_moved(_moved(fingers, QPointF(60.0, 0.0))) is True

    assert view.zoom_factor == pytest.approx(zoom)  # a pure pan never zooms
    # the scene point that was under the centre is now 60 px to the right of it
    now = view.mapFromScene(before)
    assert now.x() == pytest.approx(anchor.x() + 60.0, abs=1.0)
    assert now.y() == pytest.approx(anchor.y(), abs=1.0)


def test_the_pan_is_the_middle_mouse_pans_path(view: CanvasView) -> None:
    """The gesture and the mouse share one pan helper, so they cannot drift."""
    start = view.mapToScene(view.viewport().rect().center())
    view._pan_by(QPointF(55.0, -35.0))
    after_gesture = view.mapToScene(view.viewport().rect().center())

    view.set_zoom(1.0)
    view.centerOn(start)
    QApplication.processEvents()
    view._pan_by(QPointF(55.0, -35.0))
    again = view.mapToScene(view.viewport().rect().center())
    # centerOn snaps to whole scrollbar steps: the same call within a pixel
    assert again.x() == pytest.approx(after_gesture.x(), abs=1.5)
    assert again.y() == pytest.approx(after_gesture.y(), abs=1.5)


def test_one_finger_is_left_to_the_synthesised_mouse_path(view: CanvasView) -> None:
    """A tap or a one-finger drag is still a mouse event — the tools' path."""
    anchor = QPointF(view.viewport().rect().center())
    before = view.mapToScene(anchor.toPoint())
    assert view._touch_started([anchor]) is False
    assert view._touch_moved([anchor + QPointF(30.0, 0.0)]) is False
    assert view._touch_finished() is False
    assert view.zoom_factor == pytest.approx(1.0)
    assert view.mapToScene(anchor.toPoint()) == pytest.approx(before)


def test_the_setting_off_leaves_touch_events_to_qt(view: CanvasView) -> None:
    """Off: no touch acceptance, no gesture, and the canvas is as it was before #321."""
    assert view.viewport().testAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
    view.set_touch_gestures_enabled(False)
    assert not view.viewport().testAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)

    anchor = QPointF(view.viewport().rect().center())
    assert view._touch_started(_fingers(anchor, 40.0)) is False
    assert view._touch_moved(_fingers(anchor, 80.0)) is False
    assert view.zoom_factor == pytest.approx(1.0)

    view.set_touch_gestures_enabled(True)
    assert view.viewport().testAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
    assert view._touch_started(_fingers(anchor, 40.0)) is True
    assert view._touch_finished() is True  # the end of a gesture is consumed


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
    from PyQt6.QtCore import QEvent
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
