"""Integration tests for the 3D view (US-E6, #261).

The Qt-free math is pinned in ``tests/unit/test_scene3d.py``; this file
covers the collector on a REAL scene, the adapter's light instrumentation,
window lifecycle (no #230-style teardown crash), and the startup-cost pin
(Qt3D loads only when the user opens the 3D view).

Window/adapter tests are Windows-only: Qt3D needs a real RHI context that
the CI's offscreen Linux platform cannot provide; the Windows dev machine
(where every exe gate runs anyway) is the reference environment.
"""

from __future__ import annotations

import sys

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import FLAT_THICKNESS_CM
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import _item_footprints
from open_garden_planner.ui.view3d.snapshot import collect_scene3d_records

requires_windows_3d = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Qt3D window needs a real RHI context (Windows dev machine only)",
)


@pytest.fixture
def plan_scene(qtbot) -> CanvasScene:  # noqa: ARG001
    scene = CanvasScene(1000.0, 800.0)
    shed = RectangleItem(100, 100, 300, 200, object_type=ObjectType.TOOL_SHED)
    scene.addItem(shed)
    fence = PolylineItem(
        [QPointF(50, 50), QPointF(950, 50)], object_type=ObjectType.FENCE
    )
    scene.addItem(fence)
    tree = CircleItem(700, 500, 120, object_type=ObjectType.TREE)
    tree.metadata[METADATA_KEY] = 600.0
    scene.addItem(tree)
    lawn = RectangleItem(500, 100, 300, 250, object_type=ObjectType.LAWN)
    scene.addItem(lawn)
    return scene


class TestSnapshot:
    def test_records_cover_every_footprint_item(self, plan_scene) -> None:
        records = collect_scene3d_records(plan_scene)
        by_name = {r.name: r for r in records}
        assert len(records) == 4
        assert by_name["TOOL_SHED"].kind == "extruded"
        assert by_name["TOOL_SHED"].height_cm == 250.0  # type default
        assert by_name["FENCE"].height_cm == 120.0
        assert by_name["TREE"].height_cm == 600.0  # explicit metadata
        assert by_name["LAWN"].kind == "flat"  # no height → ground decal
        assert by_name["LAWN"].height_cm == FLAT_THICKNESS_CM

    def test_footprints_match_shadow_extraction(self, plan_scene) -> None:
        """3D solids and 2D shadows must come from the SAME footprints —
        the collector delegates to the US-E3 extraction, pin it."""
        fence = next(
            i for i in plan_scene.items() if isinstance(i, PolylineItem)
        )
        expected = _item_footprints(fence)
        records = [
            r for r in collect_scene3d_records(plan_scene) if r.name == "FENCE"
        ]
        assert len(records) == len(expected)
        assert [list(r.footprint) for r in records] == expected

    def test_hidden_items_are_skipped(self, plan_scene) -> None:
        for item in plan_scene.items():
            item.setVisible(False)
        assert collect_scene3d_records(plan_scene) == []


class TestStartupCost:
    def test_app_construction_does_not_import_qt3d(self, qtbot) -> None:
        """ADR-038: Qt3D loads only behind the 3D-view menu action —
        constructing the app must add no PyQt6.Qt3D* modules."""
        from open_garden_planner.app.application import GardenPlannerApp

        before = {m for m in sys.modules if m.startswith("PyQt6.Qt3D")}
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        after = {m for m in sys.modules if m.startswith("PyQt6.Qt3D")}
        assert after == before
        assert win._view3d_window is None


@requires_windows_3d
class TestAppWorkflow:
    """The §8.10-mandated end-to-end workflow (senior review P1): menu
    action → open → rebuilt → sun applied (with and without location) →
    sim-time forwarding → close → released. Pins the app-glue attribute
    contracts (ProjectManager.location dict, sim_datetime_utc,
    canvas_scene.width_cm) a rename would otherwise break silently."""

    def test_menu_open_sun_close_cycle(self, qtbot, monkeypatch) -> None:
        from datetime import UTC, datetime

        from open_garden_planner.app.application import GardenPlannerApp
        from open_garden_planner.ui.view3d.view3d_window import View3DWindow

        # Never actually show(): a SHOWN Qt3DWindow starts the RHI render
        # thread, which outlives this test (the window persists by design)
        # and segfaults later full-app tests. All glue below still runs;
        # real rendering is the frozen-exe/manual gate's job.
        monkeypatch.setattr(View3DWindow, "show", lambda self: None)
        monkeypatch.setattr(View3DWindow, "raise_", lambda self: None)
        monkeypatch.setattr(View3DWindow, "activateWindow", lambda self: None)

        win = GardenPlannerApp()
        qtbot.addWidget(win)
        item = RectangleItem(100, 100, 300, 200, object_type=ObjectType.TOOL_SHED)
        win.canvas_scene.addItem(item)

        win._view3d_action.trigger()
        window = win._view3d_window
        assert window is not None
        assert window.adapter.rebuild_count == 1
        # No project location → the documented default sun (50°, 180°).
        assert window.adapter.last_sun_scene is not None
        default_sun = window.adapter.last_sun_scene

        # Location set silently (avoids the weather-fetch thread) → the
        # location_changed forward is exercised via the slot directly.
        win._project_manager._location = {"latitude": 52.52, "longitude": 13.405}
        win._sun_controller.set_sim_datetime(
            datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
        )
        win._apply_sun_to_3d()
        berlin_noon_sun = window.adapter.last_sun_scene
        assert berlin_noon_sun != default_sun
        assert berlin_noon_sun[2] == pytest.approx(0.8598, abs=0.001)

        # Sim-time forwarding: the datetime slot must move the light.
        win._on_sun_sim_datetime(datetime(2026, 12, 21, 12, 0, tzinfo=UTC))
        assert window.adapter.last_sun_scene != berlin_noon_sun

        # Refresh through the window's own action wiring.
        window.refresh_requested.emit()
        assert window.adapter.rebuild_count == 2

        # Re-triggering the menu while the viewer is still OPEN refreshes and
        # raises the SAME window (live swapchain — no recreate).
        win._view3d_action.trigger()
        assert win._view3d_window is window
        assert window.adapter.rebuild_count == 3

        # Closing nulls the open reference (so 'is open' guards read true and
        # sun/refresh updates stop targeting it); the hidden window is retired
        # at the next open — a reused hidden→reshown Qt3DWindow renders white
        # (Qt3D never rebuilds its RHI swapchain), and deleteLater in
        # closeEvent would race the live render thread.
        window.close()
        assert win._view3d_window is None
        old_window = window
        win._view3d_action.trigger()  # reopen → fresh window, fresh snapshot
        assert win._view3d_window is not None
        assert win._view3d_window is not old_window
        assert win._view3d_window.adapter.rebuild_count == 1

        # Closing the MAIN window clears the 3D viewer so the app can actually
        # quit — a visible parentless Qt3DWindow would otherwise keep the
        # process alive under Qt's quitOnLastWindowClosed (senior-review P1).
        monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
        win.close()
        assert win._view3d_window is None
        assert win._view3d_window_retiring is None


@requires_windows_3d
class TestAdapter:
    def test_set_sun_day_vectors(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        # Berlin Jun-21 noon (the issue's gate): sun from SSW, high.
        adapter.set_sun(59.29, 203.74)
        sun_e, sun_n, sun_up = adapter.last_sun_scene
        assert sun_e == pytest.approx(-0.2056, abs=0.001)
        assert sun_n == pytest.approx(-0.4675, abs=0.001)
        assert sun_up == pytest.approx(0.8598, abs=0.001)
        # Engine light = negated sun, (E,N,up)→(E,up,−N): y must point DOWN.
        engine_x, engine_y, engine_z = adapter.last_light_engine
        assert engine_x == pytest.approx(0.2056, abs=0.001)
        assert engine_y == pytest.approx(-0.8598, abs=0.001)
        assert engine_z == pytest.approx(-0.4675, abs=0.001)

    def test_set_sun_night_fallback(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        adapter.set_sun(-8.0, 30.0)
        assert adapter.last_light_engine[1] < 0  # still lights from above

    def test_rebuild_counts_and_survives_repeat(self, qtbot, plan_scene) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        records = collect_scene3d_records(plan_scene)
        adapter.rebuild(records, 1000.0, 800.0)
        adapter.rebuild(records, 1000.0, 800.0)  # replace path — no crash
        assert adapter.rebuild_count == 2


@requires_windows_3d
class TestWalkthrough:
    """US-E7 (#262): walk is a camera MODE — orbit state round-trips."""

    def test_mode_toggle_round_trip_preserves_orbit_camera(
        self, qtbot, plan_scene
    ) -> None:  # noqa: ARG002
        from open_garden_planner.core.walk_camera import EYE_HEIGHT_CM
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        adapter.rebuild(collect_scene3d_records(plan_scene), 1000.0, 800.0)
        camera = adapter._view.camera()
        orbit_pos = (
            camera.position().x(), camera.position().y(), camera.position().z()
        )
        orbit_center = (
            camera.viewCenter().x(), camera.viewCenter().y(), camera.viewCenter().z()
        )

        orbit_up = (
            camera.upVector().x(), camera.upVector().y(), camera.upVector().z()
        )

        adapter.set_camera_mode("walk")
        assert adapter.camera_mode == "walk"
        assert camera.position().y() == pytest.approx(EYE_HEIGHT_CM)
        # Mutual exclusivity — exactly one controller drives the camera
        # (review P2 pin).
        assert not adapter._orbit_controller.isEnabled()
        assert adapter._walk_controller.isEnabled()

        adapter.set_camera_mode("orbit")
        assert adapter.camera_mode == "orbit"
        assert adapter._orbit_controller.isEnabled()
        assert not adapter._walk_controller.isEnabled()
        restored_up = (
            camera.upVector().x(), camera.upVector().y(), camera.upVector().z()
        )
        assert restored_up == pytest.approx(orbit_up)
        restored_pos = (
            camera.position().x(), camera.position().y(), camera.position().z()
        )
        restored_center = (
            camera.viewCenter().x(), camera.viewCenter().y(), camera.viewCenter().z()
        )
        assert restored_pos == pytest.approx(orbit_pos)
        assert restored_center == pytest.approx(orbit_center)

    def test_walk_camera_clamped_to_bounds_and_eye_height(
        self, qtbot, plan_scene
    ) -> None:  # noqa: ARG002
        from PyQt6.QtGui import QVector3D

        from open_garden_planner.core.walk_camera import (
            BOUNDS_MARGIN_CM,
            EYE_HEIGHT_CM,
        )
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        adapter.rebuild(collect_scene3d_records(plan_scene), 1000.0, 800.0)
        adapter.set_camera_mode("walk")
        camera = adapter._view.camera()
        # Simulate the controller flying far outside and off the ground.
        camera.setPosition(QVector3D(-50000.0, 9000.0, 50000.0))
        assert camera.position().x() == pytest.approx(-BOUNDS_MARGIN_CM)
        assert camera.position().y() == pytest.approx(EYE_HEIGHT_CM)
        # engine z = -north: far positive z = far south → clamped to -margin…
        assert camera.position().z() == pytest.approx(BOUNDS_MARGIN_CM)

    def test_escape_exits_walk_mode(self, qtbot, plan_scene) -> None:
        """Esc is delivered to the REAL focus target while walking — the
        embedded Qt3DWindow, not the QMainWindow (review P1): key events on
        a foreign QWindow don't bubble into the widget hierarchy, so the
        window installs an event filter on it; this test drives that path."""
        from PyQt6.QtCore import QCoreApplication, QEvent, Qt
        from PyQt6.QtGui import QKeyEvent

        from open_garden_planner.ui.view3d.view3d_window import View3DWindow

        window = View3DWindow()
        qtbot.addWidget(window)
        window.rebuild(collect_scene3d_records(plan_scene), 1000.0, 800.0)
        window._walk_action.setChecked(True)
        assert window.adapter.camera_mode == "walk"
        escape = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        QCoreApplication.sendEvent(window.adapter.window_handle(), escape)
        assert window.adapter.camera_mode == "orbit"
        assert not window._walk_action.isChecked()

    def test_pitch_clamp_enforced_on_live_camera(self, qtbot, plan_scene) -> None:
        """The ±89° rule is RUNTIME behavior, not a dead helper (review P1):
        pointing the walk camera past the zenith gets re-projected."""
        from PyQt6.QtGui import QVector3D

        from open_garden_planner.core.walk_camera import PITCH_LIMIT_DEG
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        adapter.rebuild(collect_scene3d_records(plan_scene), 1000.0, 800.0)
        adapter.set_camera_mode("walk")
        camera = adapter._view.camera()
        # Look almost straight up (≈ 89.9°): beyond the limit.
        camera.setViewCenter(
            camera.position() + QVector3D(0.0, 1000.0, -1.0)
        )
        look = camera.viewCenter() - camera.position()
        import math as _math

        pitch = _math.degrees(
            _math.atan2(look.y(), _math.hypot(look.x(), look.z()))
        )
        assert pitch <= PITCH_LIMIT_DEG + 0.01

    def test_rebuild_during_walk_reclamps(self, qtbot, plan_scene) -> None:
        """Refresh onto a smaller plan must not strand the walker outside
        the new bounds (review P2)."""
        from open_garden_planner.core.walk_camera import BOUNDS_MARGIN_CM
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        adapter.rebuild(collect_scene3d_records(plan_scene), 5000.0, 4000.0)
        adapter.set_camera_mode("walk")
        camera = adapter._view.camera()
        from PyQt6.QtGui import QVector3D

        camera.setPosition(QVector3D(4800.0, 165.0, -3800.0))
        adapter.rebuild(collect_scene3d_records(plan_scene), 1000.0, 800.0)
        assert camera.position().x() <= 1000.0 + BOUNDS_MARGIN_CM
        assert -camera.position().z() <= 800.0 + BOUNDS_MARGIN_CM

    def test_walk_movement_is_horizontal_and_wasd(
        self, qtbot, plan_scene
    ) -> None:  # noqa: ARG002
        """Movement stays at eye height even while looking UP (no vertical
        drift, no tilt), advances along the heading, and WASD works like the
        arrows — the three manual-test findings on the first cut."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QVector3D

        from open_garden_planner.core.walk_camera import EYE_HEIGHT_CM
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        adapter.rebuild(collect_scene3d_records(plan_scene), 1000.0, 800.0)
        adapter.set_camera_mode("walk")
        camera = adapter._view.camera()
        # Face north, look UP (pitched) — the old bug lifted the walker.
        camera.setPosition(QVector3D(500.0, EYE_HEIGHT_CM, -400.0))
        camera.setViewCenter(QVector3D(500.0, EYE_HEIGHT_CM + 50.0, -500.0))
        look_before = camera.viewCenter() - camera.position()

        adapter.walk_key_press(Qt.Key.Key_W)  # WASD, not only arrows
        adapter._walk_move_tick()
        adapter.walk_key_release(Qt.Key.Key_W)

        assert camera.position().y() == pytest.approx(EYE_HEIGHT_CM)
        assert -camera.position().z() > 400.0  # advanced north
        look_after = camera.viewCenter() - camera.position()
        assert look_after.x() == pytest.approx(look_before.x())
        assert look_after.y() == pytest.approx(look_before.y())
        assert look_after.z() == pytest.approx(look_before.z())

    def test_close_mid_walk_is_clean(self, qtbot, plan_scene) -> None:
        from open_garden_planner.ui.view3d.view3d_window import View3DWindow

        window = View3DWindow()
        qtbot.addWidget(window)
        window.rebuild(collect_scene3d_records(plan_scene), 1000.0, 800.0)
        window._walk_action.setChecked(True)
        window.close()  # must not crash (#230-class teardown)


@requires_windows_3d
class TestWindowLifecycle:
    def test_open_refresh_close_cleanly(self, qtbot, plan_scene) -> None:
        from open_garden_planner.ui.view3d.view3d_window import View3DWindow

        window = View3DWindow()
        qtbot.addWidget(window)
        refreshes: list[bool] = []
        window.refresh_requested.connect(lambda: refreshes.append(True))
        window.rebuild(collect_scene3d_records(plan_scene), 1000.0, 800.0)
        window.set_sun(59.29, 203.74)
        closed: list[bool] = []
        window.closed.connect(lambda: closed.append(True))
        window.close()
        assert closed
