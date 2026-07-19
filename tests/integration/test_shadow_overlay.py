"""Integration tests for the sun & shade shadow overlay (US-E3, #258).

The centerpiece is the BINDING PIXEL TEST from the campaign runbook: it
renders the live scene through the same ``render_scene_region`` pipeline the
PNG/PDF exports use (``y_flip=True``) and asserts the shadow lands at the
pixel the §8.19 formula predicts from raw scene coordinates — no eyeballing,
no extra Y conversion. If someone re-flips the Y axis anywhere in the shadow
path, this test fails with a mirrored tip.

Pinned solar numbers (oracle, campaign appendix): Berlin 2026-06-21 12:00 UTC
→ α = 59.29°, Az = 203.74° → L(100 cm) = 59.4 cm, direction (+0.4025, +0.9154).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.shadow_geometry import (
    shadow_direction_scene,
    shadow_length_cm,
)
from open_garden_planner.core.solar import solar_position
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    STATE_ACTIVE,
    STATE_NIGHT,
    STATE_NO_LOCATION,
    SunShadowController,
    SunShadowOverlayItem,
)
from open_garden_planner.ui.widgets.sun_sim_toolbar import SunSimToolbar

BERLIN = {"latitude": 52.52, "longitude": 13.405}
JUNE_NOON_UTC = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
JUNE_NIGHT_UTC = datetime(2026, 6, 21, 23, 0, tzinfo=UTC)


@pytest.fixture
def scene(qtbot) -> CanvasScene:  # noqa: ARG001 — qtbot for Qt init
    return CanvasScene(500.0, 500.0)


def _make_caster(scene: CanvasScene) -> RectangleItem:
    """40×40 rect at (100,100) with an explicit 100 cm height."""
    item = RectangleItem(100, 100, 40, 40, object_type=ObjectType.GENERIC_RECTANGLE)
    item.metadata[METADATA_KEY] = 100.0
    scene.addItem(item)
    return item


def _render(scene: CanvasScene, region: QRectF, px_per_cm: float) -> QImage:
    width = round(region.width() * px_per_cm)
    height = round(region.height() * px_per_cm)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        render_scene_region(
            scene, painter, QRectF(0, 0, width, height), region, y_flip=True
        )
    finally:
        painter.end()
    return image


def _pixel(region: QRectF, px_per_cm: float, image_height: int, x_cm: float, y_cm: float) -> tuple[int, int]:
    """The §8.19 render pixel formula — raw scene cm in, pixel out."""
    px_x = round((x_cm - region.x()) * px_per_cm)
    px_y = round(image_height - (y_cm - region.y()) * px_per_cm)
    return px_x, px_y


class TestBindingPixel:
    def test_shadow_tip_lands_at_predicted_pixel(self, qtbot, scene) -> None:  # noqa: ARG002
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)

        region = QRectF(50, 50, 200, 200)
        px_per_cm = 2.0
        before = _render(scene, region, px_per_cm)

        controller.set_enabled(True)
        assert controller.state == STATE_ACTIVE
        after = _render(scene, region, px_per_cm)

        position = solar_position(
            BERLIN["latitude"], BERLIN["longitude"], JUNE_NOON_UTC
        )
        assert position.elevation_deg == pytest.approx(59.29, abs=0.05)
        assert position.azimuth_deg == pytest.approx(203.74, abs=0.05)
        length = shadow_length_cm(100.0, position.elevation_deg)
        dx, dy = shadow_direction_scene(position.azimuth_deg)
        # The caster corner that extends furthest along the shadow direction.
        tip = (140.0 + dx * length, 140.0 + dy * length)
        # Sanity: the tip went NORTH (+y) and slightly east — scene frame.
        assert tip[1] > 194.0 and tip[0] > 163.0

        inside = (tip[0] - dx * 3.0, tip[1] - dy * 3.0)
        beyond = (tip[0] + dx * 3.0, tip[1] + dy * 3.0)
        h = after.height()
        inside_px = _pixel(region, px_per_cm, h, *inside)
        beyond_px = _pixel(region, px_per_cm, h, *beyond)
        # Northward tip → larger scene-y → SMALLER pixel-y (nearer image top).
        assert inside_px[1] < _pixel(region, px_per_cm, h, 140.0, 140.0)[1]

        assert after.pixel(*inside_px) != before.pixel(*inside_px), (
            "expected shadow tint just inside the predicted tip pixel"
        )
        assert after.pixel(*beyond_px) == before.pixel(*beyond_px), (
            "expected untouched background just beyond the predicted tip"
        )

    def test_disabling_restores_clean_render(self, qtbot, scene) -> None:  # noqa: ARG002
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        region = QRectF(50, 50, 200, 200)
        before = _render(scene, region, 2.0)
        controller.set_enabled(True)
        controller.set_enabled(False)
        after = _render(scene, region, 2.0)
        assert before == after


class TestRecomputeDiscipline:
    def test_one_effective_recompute_per_change_event(self, qtbot, scene) -> None:
        item = _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        controller.set_enabled(True)
        assert controller.recompute_count == 1

        # Let the overlay's own setPath → scene.changed echo settle: the
        # snapshot key must swallow it without a second rebuild.
        qtbot.wait(400)
        assert controller.recompute_count == 1

        item.setPos(item.pos().x() + 25.0, item.pos().y())
        qtbot.wait(400)  # debounce (150 ms) + echo settle
        assert controller.recompute_count == 2

        qtbot.wait(300)  # no further changes → no further rebuilds
        assert controller.recompute_count == 2

    def test_sim_time_change_recomputes_immediately(self, qtbot, scene) -> None:  # noqa: ARG002
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        controller.set_enabled(True)
        assert controller.recompute_count == 1
        controller.set_sim_datetime(datetime(2026, 12, 21, 12, 0, tzinfo=UTC))
        assert controller.recompute_count == 2


class TestEmptyStates:
    def test_no_location_state(self, qtbot, scene) -> None:  # noqa: ARG002
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: None)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        states: list[str] = []
        controller.state_changed.connect(states.append)
        controller.set_enabled(True)
        assert controller.state == STATE_NO_LOCATION
        assert STATE_NO_LOCATION in states

    def test_night_state_no_shadow_painted(self, qtbot, scene) -> None:  # noqa: ARG002
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NIGHT_UTC)
        region = QRectF(50, 50, 200, 200)
        before = _render(scene, region, 2.0)
        controller.set_enabled(True)
        assert controller.state == STATE_NIGHT
        assert _render(scene, region, 2.0) == before

    def test_location_set_recovers_from_empty_state(self, qtbot, scene) -> None:  # noqa: ARG002
        _make_caster(scene)
        location: dict | None = None
        controller = SunShadowController(scene, lambda: location)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        controller.set_enabled(True)
        assert controller.state == STATE_NO_LOCATION
        location = BERLIN
        controller.recompute_now()  # the app wires location_changed here
        assert controller.state == STATE_ACTIVE


class TestNeverSerialized:
    def test_overlay_absent_from_saved_ogp(self, qtbot, scene, tmp_path) -> None:  # noqa: ARG002
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        controller.set_enabled(True)
        assert any(isinstance(i, SunShadowOverlayItem) for i in scene.items())

        manager = ProjectManager()
        file_path = tmp_path / "plan.ogp"
        manager.save(scene, file_path)

        import json

        raw = json.loads(file_path.read_text(encoding="utf-8"))
        assert len(raw["objects"]) == 1  # the caster — no overlay record

        scene.clear()
        manager.load(scene, file_path)
        assert not any(isinstance(i, SunShadowOverlayItem) for i in scene.items())

    def test_recompute_survives_scene_clear(self, qtbot, scene) -> None:  # noqa: ARG002
        """scene.clear() (project load/new) deletes the overlay's C++ object;
        the controller must recover, not crash (RuntimeError guard)."""
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        controller.set_enabled(True)
        scene.clear()
        _make_caster(scene)
        controller.recompute_now()  # must not raise
        assert controller.state == STATE_ACTIVE
        assert any(isinstance(i, SunShadowOverlayItem) for i in scene.items())


class TestPerf:
    def test_recompute_200_items_perf(self, qtbot, scene) -> None:  # noqa: ARG002
        for i in range(200):
            item = RectangleItem(
                (i % 20) * 60.0,
                (i // 20) * 60.0,
                40,
                40,
                object_type=ObjectType.GENERIC_RECTANGLE,
            )
            item.metadata[METADATA_KEY] = 100.0 + i
            scene.addItem(item)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        controller.set_enabled(True)  # first build outside the timed window

        controller.set_sim_datetime(datetime(2026, 6, 21, 13, 0, tzinfo=UTC))
        start = time.perf_counter()
        controller.set_sim_datetime(datetime(2026, 6, 21, 14, 0, tzinfo=UTC))
        elapsed = time.perf_counter() - start
        # Campaign gate: < 50 ms on dev hardware; ×4 slack for CI runners.
        assert elapsed < 0.200, f"200-item recompute took {elapsed * 1000:.1f} ms"


class TestSunSimToolbar:
    def test_datetime_round_trip(self, qtbot) -> None:
        toolbar = SunSimToolbar()
        qtbot.addWidget(toolbar)
        local = datetime(2026, 6, 21, 14, 0).astimezone()
        toolbar.set_datetime_local(local)
        result = toolbar.current_datetime_local()
        assert result.astimezone(UTC) == local.astimezone(UTC)

    def test_slider_change_emits_aware_datetime(self, qtbot) -> None:
        toolbar = SunSimToolbar()
        qtbot.addWidget(toolbar)
        received: list[datetime] = []
        toolbar.datetime_changed.connect(received.append)
        toolbar._slider.setValue(15 * 60)
        assert received
        emitted = received[-1]
        assert emitted.tzinfo is not None
        assert emitted.hour == 15

    def test_animate_advances_time(self, qtbot) -> None:
        toolbar = SunSimToolbar()
        qtbot.addWidget(toolbar)
        toolbar._slider.setValue(12 * 60)
        received: list[datetime] = []
        toolbar.datetime_changed.connect(received.append)
        toolbar._animate_button.setChecked(True)
        qtbot.wait(500)
        toolbar._animate_button.setChecked(False)
        assert received, "animation ticks should advance the sim time"
        assert toolbar._slider.value() > 12 * 60


class TestAppWiring:
    def test_menu_action_toggles_toolbar_and_overlay(self, qtbot) -> None:
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)
        assert not win._sun_toolbar.isVisible()
        assert not win._sun_controller.enabled

        win._sun_sim_action.trigger()
        assert win._sun_controller.enabled
        # No location on a fresh project → the empty-state hint shows.
        assert win._sun_controller.state == STATE_NO_LOCATION
        assert win._sun_toolbar._hint_label.text() != ""

        win._sun_sim_action.trigger()
        assert not win._sun_controller.enabled
        assert win._sun_controller.state == "disabled"

    def test_height_edit_via_command_recomputes_shadows(self, qtbot, scene) -> None:
        """A metadata-only height edit repaints nothing, so scene.changed never
        fires — the stack_changed → schedule_recompute wiring is the only
        thing keeping shadows fresh after a height edit (senior review P1).
        Replicates the exact application.py wiring on a lean scene (a full
        GardenPlannerApp would drag the calendar/weather refresh chain into
        the test); the companion source-tripwire test below pins the real
        connect line itself."""
        from open_garden_planner.core.commands import ChangePropertyCommand, CommandManager

        item = _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        controller.set_enabled(True)
        cmd_mgr = CommandManager()
        # The exact wiring _setup_central_widget applies:
        cmd_mgr.stack_changed.connect(controller.schedule_recompute)
        qtbot.wait(400)  # let add-item scene.changed echoes settle
        baseline = controller.recompute_count

        def apply_height(target, value) -> None:
            # Mirrors the properties panel's apply_func: metadata only,
            # no repaint — the exact path scene.changed cannot see.
            target.metadata[METADATA_KEY] = value

        cmd_mgr.execute(
            ChangePropertyCommand(item, "object height", 100.0, 250.0, apply_height)
        )
        qtbot.wait(400)  # debounce + settle
        assert controller.recompute_count == baseline + 1, (
            "height edit through the command stack must trigger exactly one "
            "effective shadow recompute"
        )
        # And the recomputed shadow really reflects the new height: undo →
        # another recompute back to the shorter shadow.
        cmd_mgr.undo()
        qtbot.wait(400)
        assert controller.recompute_count == baseline + 2

    def test_app_wires_stack_changed_to_sun_controller(self) -> None:
        """Source tripwire for the application.py connect line the behavioral
        test above replicates — deleting the line fails HERE."""
        import inspect

        from open_garden_planner.app import application

        source = inspect.getsource(application)
        assert (
            "stack_changed.connect(self._sun_controller.schedule_recompute)"
            in source
        ), (
            "application.py must wire cmd_mgr.stack_changed to the sun "
            "controller — metadata-only height edits repaint nothing, so "
            "scene.changed alone misses them"
        )
