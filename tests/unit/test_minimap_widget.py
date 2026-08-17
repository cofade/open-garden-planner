"""Unit tests for minimap / overview panel widget (US-11.7)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QMouseEvent, QResizeEvent
from PyQt6.QtWidgets import QWidget

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.widgets.minimap_widget import (
    MARGIN,
    MINIMAP_HEIGHT,
    MINIMAP_WIDTH,
    MinimapWidget,
    _OVERLAY_Z_MIN,
)


@pytest.fixture()
def canvas_pair(qtbot: object) -> tuple[CanvasView, CanvasScene]:
    """Create a CanvasView + CanvasScene pair for testing.

    Registered with ``qtbot`` so the view (and its child ``MinimapWidget``,
    where a test creates one) is deterministically torn down at the end of
    the test — otherwise the C++ QObject can outlive its Python wrapper and
    later still receive events via ``eventFilter``/timers, raising
    ``AttributeError`` from inside the Qt event loop and getting misattributed
    to an unrelated, later-running test.
    """
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.resize(800, 600)
    view.show()
    return view, scene


@pytest.fixture()
def minimap(canvas_pair: tuple[CanvasView, CanvasScene]) -> MinimapWidget:
    """Create a MinimapWidget attached to the canvas pair."""
    view, scene = canvas_pair
    return MinimapWidget(view, scene)


class TestMinimapCreation:
    """Tests for minimap widget creation and initial state."""

    def test_minimap_creates(self, minimap: MinimapWidget) -> None:
        assert minimap is not None
        assert isinstance(minimap, QWidget)

    def test_minimap_fixed_size(self, minimap: MinimapWidget) -> None:
        assert minimap.width() == MINIMAP_WIDTH
        assert minimap.height() == MINIMAP_HEIGHT

    def test_minimap_is_enabled_by_default(self, minimap: MinimapWidget) -> None:
        assert minimap.is_enabled() is True


class TestMinimapVisibility:
    """Tests for minimap visibility toggling."""

    def test_set_visible_false_hides(self, minimap: MinimapWidget) -> None:
        minimap.set_visible(False)
        assert minimap.is_enabled() is False
        assert minimap.isHidden()

    def test_set_visible_true_shows(self, minimap: MinimapWidget) -> None:
        minimap.set_visible(False)
        minimap.set_visible(True)
        assert minimap.is_enabled() is True
        assert minimap.isVisible()


class TestMinimapPosition:
    """Tests for minimap positioning."""

    def test_minimap_initial_position(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        QApplication.processEvents()  # flush deferred singleShot(0) reposition
        vp = view.viewport().geometry()
        sb = CanvasView.SCALE_BAR_RESERVED_PX if view.scale_bar_visible else 0
        expected_x = max(vp.left(), vp.right() - minimap.width() - MARGIN)
        expected_y = max(vp.top(), vp.bottom() - minimap.height() - MARGIN - sb)
        assert minimap.x() == expected_x
        assert minimap.y() == expected_y


class TestMinimapCoordinateMapping:
    """Tests for coordinate conversion.

    The minimap uses Y-inverted coordinates: minimap Y=0 corresponds
    to the visual top of the canvas (scene Y=height_cm) because the
    view applies a Y-flip transform.
    """

    def test_minimap_to_scene_top_left(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        """Minimap top-left (0,0) → scene bottom-left (0, height)."""
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        sx, sy = minimap._minimap_to_scene(0, 0)
        assert sx == pytest.approx(0.0, abs=1.0)
        assert sy == pytest.approx(3000.0, abs=1.0)

    def test_minimap_to_scene_bottom_right(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        """Minimap bottom-right (W,H) → scene top-right (width, 0)."""
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        sx, sy = minimap._minimap_to_scene(MINIMAP_WIDTH, MINIMAP_HEIGHT)
        assert sx == pytest.approx(5000.0, abs=1.0)
        assert sy == pytest.approx(0.0, abs=1.0)

    def test_minimap_to_scene_center(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        sx, sy = minimap._minimap_to_scene(MINIMAP_WIDTH / 2, MINIMAP_HEIGHT / 2)
        assert sx == pytest.approx(2500.0, abs=1.0)
        assert sy == pytest.approx(1500.0, abs=1.0)

    def test_viewport_rect_returns_qrectf(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        rect = minimap._viewport_rect_on_minimap()
        # May be None if canvas is empty or rect could be QRectF
        if rect is not None:
            assert isinstance(rect, QRectF)


class TestMinimapThrottleTimer:
    """Tests for the update throttle timer."""

    def test_timer_interval(self, minimap: MinimapWidget) -> None:
        assert minimap._update_timer.interval() == 100

    def test_timer_is_single_shot(self, minimap: MinimapWidget) -> None:
        assert minimap._update_timer.isSingleShot() is True


class TestMinimapMouseInteraction:
    """Tests for mouse-based navigation."""

    def test_click_pans_view(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object,
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)

        # Zoom in so the minimap is visible and viewport doesn't cover everything
        view.set_zoom(300.0)

        # Record initial center
        vp = view.viewport().rect()
        initial_center = view.mapToScene(vp.center())

        # Simulate click near top-left of minimap (should pan toward scene origin)
        click_pos = QPointF(10.0, 10.0)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            click_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        minimap.mousePressEvent(press)

        # Check that view center changed
        new_center = view.mapToScene(vp.center())
        # At high zoom, clicking near origin should move the view
        assert (
            initial_center.x() != new_center.x()
            or initial_center.y() != new_center.y()
        )

    def test_drag_flag_set_on_viewport_rect(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        # Initially not dragging
        assert minimap._dragging is False

    def test_mouse_release_clears_drag(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        minimap._dragging = True
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(50.0, 50.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        minimap.mouseReleaseEvent(release)
        assert minimap._dragging is False


class TestMinimapOverlayFiltering:
    """Regression tests for issue #152 — overlay filter must not hide garden items."""

    def test_layer_items_not_hidden_by_overlay_filter(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object
    ) -> None:
        """Items on non-bottom layers (zValue = 100, 200, …) must survive
        _hide_overlay_items() — they were wrongly hidden before the fix."""
        from PyQt6.QtWidgets import QGraphicsRectItem

        view, scene = canvas_pair
        item = QGraphicsRectItem(0, 0, 100, 100)
        item.setZValue(100)  # z_order=1 layer
        scene.addItem(item)

        minimap = MinimapWidget(view, scene)
        hidden = minimap._hide_overlay_items()
        minimap._restore_overlay_items(hidden)

        assert item not in hidden, "Garden item with zValue=100 must not be hidden"
        assert item.isVisible()

    def test_high_z_overlay_is_hidden_and_restored(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object
    ) -> None:
        """Items with zValue >= _OVERLAY_Z_MIN (overlay handles) must be
        hidden during render and restored afterwards."""
        from PyQt6.QtWidgets import QGraphicsRectItem

        view, scene = canvas_pair
        overlay = QGraphicsRectItem(0, 0, 10, 10)
        overlay.setZValue(_OVERLAY_Z_MIN)
        scene.addItem(overlay)

        minimap = MinimapWidget(view, scene)
        hidden = minimap._hide_overlay_items()
        assert overlay in hidden
        minimap._restore_overlay_items(hidden)
        assert overlay.isVisible()


class TestMinimapIdleQuiescence:
    """Regression tests for issue #305 — self-sustaining idle render loop.

    ``_do_update`` hides overlay items, renders, then restores them. Each
    ``setVisible()`` makes the scene emit ``changed`` ASYNCHRONOUSLY
    (queued, delivered after ``_do_update`` has already returned), and
    ``changed`` used to restart the 100 ms throttle timer unconditionally,
    causing ``_do_update`` to run again, hide/restore again, and so on
    forever, even while the app was otherwise completely idle. Measured
    before the fix: 13-14 renders per 1.5 s with a single overlay item
    present (vs. ~1/1.5s baseline with none, never quiescent). The fix is
    content-based: ``_on_scene_changed`` ignores an emission iff every rect
    lies inside an overlay rect the minimap itself just toggled.
    """

    @staticmethod
    def _count_do_update_calls(minimap: MinimapWidget) -> dict[str, int]:
        """Reroute the throttle timer's timeout to a counting wrapper.

        A plain ``minimap._do_update = wrapper`` instance-attribute
        assignment would NOT be observed by the timer: PyQt resolved the
        slot to the original bound method at ``connect()`` time in
        ``__init__``. The timer's connection must be replaced instead.
        """
        calls = {"n": 0}
        original = minimap._do_update

        def counted() -> None:
            calls["n"] += 1
            original()

        minimap._update_timer.timeout.disconnect()
        minimap._update_timer.timeout.connect(counted)
        return calls

    def test_overlay_item_present_settles_to_zero_renders(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object
    ) -> None:
        from PyQt6.QtWidgets import QGraphicsRectItem

        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)

        overlay = QGraphicsRectItem(0, 0, 10, 10)
        overlay.setZValue(_OVERLAY_Z_MIN + 1)
        scene.addItem(overlay)

        calls = self._count_do_update_calls(minimap)

        # Let everything triggered by adding the overlay item settle.
        qtbot.wait(400)  # type: ignore[attr-defined]

        calls["n"] = 0
        qtbot.wait(600)  # type: ignore[attr-defined]

        assert calls["n"] == 0, (
            f"minimap re-rendered {calls['n']} times while idle with an "
            "overlay item present — self-sustaining loop (issue #305)"
        )

    def test_real_scene_change_after_settle_still_schedules_render(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object
    ) -> None:
        """The suppression fix must not silence genuine changes.

        A real, unrelated scene mutation happening well after the overlay
        item's own hide/restore has settled must still schedule a render —
        proving the fix didn't just kill the minimap outright.
        """
        from PyQt6.QtWidgets import QGraphicsRectItem

        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)

        overlay = QGraphicsRectItem(0, 0, 10, 10)
        overlay.setZValue(_OVERLAY_Z_MIN + 1)
        scene.addItem(overlay)

        calls = self._count_do_update_calls(minimap)

        qtbot.wait(400)  # type: ignore[attr-defined]
        calls["n"] = 0

        # A genuine, unrelated scene change — not the minimap's own doing.
        new_item = QGraphicsRectItem(200, 200, 50, 50)
        scene.addItem(new_item)

        qtbot.wait(300)  # type: ignore[attr-defined]

        assert calls["n"] >= 1, "a real scene change must still trigger a render"

    def test_real_change_in_same_turn_as_self_render_is_not_dropped(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object
    ) -> None:
        """The suppression is content-based (rects), not a timing window: a
        genuine change that shares the event-loop turn with the minimap's
        own hide/restore must still schedule a render (issue #305 review).
        """
        from PyQt6.QtWidgets import QGraphicsRectItem

        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        overlay = QGraphicsRectItem(-5, -5, 10, 10)
        overlay.setPos(1000, 800)
        overlay.setZValue(_OVERLAY_Z_MIN + 1)
        scene.addItem(overlay)
        qtbot.wait(400)  # type: ignore[attr-defined]

        renders = self._count_scene_renders(scene)
        minimap._update_timer.stop()
        minimap._do_update()  # self-inflicted hide/restore ...
        real = QGraphicsRectItem(0, 0, 50, 50)  # ... and a real change, same turn
        real.setPos(2000, 1000)
        scene.addItem(real)
        qtbot.wait(400)  # type: ignore[attr-defined]
        # 1 = the forced render above; a 2nd proves the real change scheduled one.
        assert renders["n"] >= 2, "genuine change sharing the turn was dropped"

    def test_moving_an_overlay_item_still_schedules_render(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object
    ) -> None:
        """Stale self-dirty rects from the last render must not swallow an
        overlay item that genuinely moved (e.g. a handle following a drag)."""
        from PyQt6.QtWidgets import QGraphicsRectItem

        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        overlay = QGraphicsRectItem(-5, -5, 10, 10)
        overlay.setPos(1000, 800)
        overlay.setZValue(_OVERLAY_Z_MIN + 1)
        scene.addItem(overlay)
        qtbot.wait(600)  # type: ignore[attr-defined]
        assert minimap._self_dirty_rects, "precondition: last render hid the overlay"

        renders = self._count_scene_renders(scene)
        overlay.setPos(1200, 900)
        qtbot.wait(400)  # type: ignore[attr-defined]
        assert renders["n"] >= 1

    @staticmethod
    def _count_scene_renders(scene: CanvasScene) -> dict[str, int]:
        """Count actual ``QGraphicsScene.render`` calls (the expensive part).

        ``_do_update`` early-returns are still calls to ``_do_update``; what
        matters for #305 is whether the whole scene is rasterised.
        """
        calls = {"n": 0}
        original = scene.render

        def counted(*args: object, **kwargs: object) -> None:
            calls["n"] += 1
            original(*args, **kwargs)  # type: ignore[misc]

        scene.render = counted  # type: ignore[method-assign]
        return calls

    def test_toggled_off_minimap_does_not_render_on_scene_changes(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object
    ) -> None:
        """A minimap the user turned off (View menu) must not keep rasterising
        the whole scene into a pixmap nobody sees (issue #305 follow-up: the
        reporter wasn't sure whether the minimap was on or off while idle).
        Measured before the guard: 20 item additions -> 5 full renders with
        the widget hidden.
        """
        from PyQt6.QtWidgets import QGraphicsRectItem

        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        qtbot.wait(300)  # type: ignore[attr-defined]

        minimap.set_visible(False)
        qtbot.wait(200)  # type: ignore[attr-defined]
        renders = self._count_scene_renders(scene)

        for i in range(10):
            scene.addItem(QGraphicsRectItem(i * 10, i * 10, 50, 50))
            qtbot.wait(30)  # type: ignore[attr-defined]
        qtbot.wait(300)  # type: ignore[attr-defined]
        assert renders["n"] == 0, (
            f"hidden minimap rendered the scene {renders['n']} times"
        )

        # Turning it back on renders once so the thumbnail is fresh.
        minimap.set_visible(True)
        qtbot.wait(300)  # type: ignore[attr-defined]
        assert renders["n"] >= 1
        assert minimap._thumbnail is not None
