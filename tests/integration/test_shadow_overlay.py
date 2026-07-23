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
from datetime import UTC, date, datetime

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
        # Far enough past the tip to clear the soft outward penumbra (a few cm
        # halo, US-E3 soft-edge follow-up) so "beyond" is genuinely untouched.
        beyond = (tip[0] + dx * 15.0, tip[1] + dy * 15.0)
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


class TestCanvasClip:
    def test_shadow_clipped_to_canvas_bounds(self, qtbot, scene) -> None:  # noqa: ARG002
        # A tall caster near the north edge throws a shadow far past the top of
        # the canvas; the overlay must be cut off at the canvas boundary, not
        # spill onto the grey area outside the garden.
        item = RectangleItem(
            240, 450, 40, 40, object_type=ObjectType.GENERIC_RECTANGLE
        )
        item.metadata[METADATA_KEY] = 300.0  # ~178 cm shadow — well past y=500
        scene.addItem(item)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)

        # A band entirely OUTSIDE the canvas (scene-y > 500 = north of the top
        # edge) that the *unclipped* shadow would otherwise cover.
        outside = QRectF(240, 510, 120, 90)
        before = _render(scene, outside, 2.0)
        controller.set_enabled(True)
        assert controller.state == STATE_ACTIVE
        assert _render(scene, outside, 2.0) == before, (
            "shadow overlay must be clipped to the canvas — nothing outside it"
        )

    def test_soft_feather_extends_just_past_shadow(self, qtbot, scene) -> None:  # noqa: ARG002
        # The soft edge is an OUTWARD penumbra: it tints a few cm past the
        # geometric shadow tip (proving the feather is painted and points
        # outward), while well beyond it the background is untouched.
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        region = QRectF(50, 50, 200, 200)
        before = _render(scene, region, 2.0)
        controller.set_enabled(True)
        after = _render(scene, region, 2.0)

        position = solar_position(
            BERLIN["latitude"], BERLIN["longitude"], JUNE_NOON_UTC
        )
        length = shadow_length_cm(100.0, position.elevation_deg)
        dx, dy = shadow_direction_scene(position.azimuth_deg)
        tip = (140.0 + dx * length, 140.0 + dy * length)
        # ~5 cm past the tip is inside the widest feather stroke's ~7 cm reach;
        # 15 cm past is clear of it (matches the binding test's untouched point).
        penumbra = (tip[0] + dx * 5.0, tip[1] + dy * 5.0)
        far = (tip[0] + dx * 15.0, tip[1] + dy * 15.0)
        h = after.height()
        pen_px = _pixel(region, 2.0, h, *penumbra)
        far_px = _pixel(region, 2.0, h, *far)
        assert after.pixel(*pen_px) != before.pixel(*pen_px), (
            "soft feather should tint a few cm past the shadow tip"
        )
        assert after.pixel(*far_px) == before.pixel(*far_px), (
            "no tint well past the feather's reach"
        )


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

    def test_night_holds_no_churn(self, qtbot, scene) -> None:
        # The night full-canvas fill triggers the overlay's own scene.changed
        # echo; the night snapshot key must swallow it — no rebuild storm (the
        # exact invariant the night short-circuit exists to hold).
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NIGHT_UTC)
        controller.set_enabled(True)
        assert controller.state == STATE_NIGHT
        night_count = controller.recompute_count
        qtbot.wait(400)
        assert controller.recompute_count == night_count

    def test_canvas_resize_forces_rebuild(self, qtbot, scene) -> None:  # noqa: ARG002
        # A canvas resize (satellite picker) changes the clip bounds with the
        # sun and casters unchanged; canvas_key must break the snapshot guard,
        # else the overlay stays pinned to the stale canvas.
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        controller.set_enabled(True)
        count = controller.recompute_count
        scene.resize_canvas(800.0, 800.0)
        controller.recompute_now()
        assert controller.recompute_count == count + 1

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

    def test_night_shades_whole_canvas(self, qtbot, scene) -> None:  # noqa: ARG002
        # US-E3 follow-up: at night the shadows do NOT vanish — the entire
        # garden lies in shade. The overlay fills (and is clipped to) the
        # canvas, so an interior region renders darker than the bare scene.
        _make_caster(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NIGHT_UTC)
        region = QRectF(50, 50, 200, 200)
        before = _render(scene, region, 2.0)
        controller.set_enabled(True)
        assert controller.state == STATE_NIGHT
        assert _render(scene, region, 2.0) != before
        overlay = next(
            i for i in scene.items() if isinstance(i, SunShadowOverlayItem)
        )
        assert overlay.isVisible()
        assert overlay.path().boundingRect().width() == pytest.approx(
            scene.canvas_rect.width()
        )
        assert overlay.path().boundingRect().height() == pytest.approx(
            scene.canvas_rect.height()
        )

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


class TestGrowthCoupledShadows:
    """US-E8 (#263): the sim instant doubles as the growth timeline — a
    dated tree's shadow lengthens as the years scrub forward, while the
    STORED item geometry never changes (the #218/#219 scars)."""

    SPECIES = {
        "min_height_cm": 100.0,
        "max_height_cm": 500.0,
        "min_spread_cm": 50.0,
        "max_spread_cm": 400.0,
    }

    def _make_tree(self, scene):
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        tree = CircleItem(200, 200, 200, object_type=ObjectType.TREE)
        tree.metadata["plant_species"] = dict(self.SPECIES)
        # A MEASURED plant: the redesigned model interpolates from the
        # plant's own current size up to the species max, so growth only
        # engages when both a date and a current size are present.
        tree.metadata["plant_instance"] = {
            "planting_date": "2026-01-01",
            "current_height_cm": 100.0,
            "current_spread_cm": 50.0,
        }
        scene.addItem(tree)
        return tree

    def test_scrubbing_years_regrows_the_shadow(self, qtbot, scene) -> None:  # noqa: ARG002
        self._make_tree(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        controller.set_enabled(True)
        young = controller._overlay.path().boundingRect()
        count_young = controller.recompute_count

        # Same solar instant five years on (TREE matures over 10 y) — the
        # only change is growth, and it must trigger a real recompute.
        controller.set_sim_datetime(datetime(2031, 6, 21, 12, 0, tzinfo=UTC))
        grown = controller._overlay.path().boundingRect()
        assert controller.recompute_count == count_young + 1
        assert grown.width() * grown.height() > young.width() * young.height()

    def test_stored_geometry_untouched_by_scrubbing(
        self, qtbot, scene, tmp_path
    ) -> None:  # noqa: ARG002
        import json

        tree = self._make_tree(scene)
        radius_before = tree.radius
        manager = ProjectManager()
        first = tmp_path / "before.ogp"
        manager.save(scene, first)

        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        controller.set_enabled(True)
        controller.set_sim_datetime(datetime(2031, 6, 21, 12, 0, tzinfo=UTC))
        controller.set_sim_datetime(datetime(2027, 3, 1, 9, 0, tzinfo=UTC))

        assert tree.radius == radius_before
        second = tmp_path / "after.ogp"
        manager.save(scene, second)
        assert json.loads(first.read_text(encoding="utf-8"))["objects"] == (
            json.loads(second.read_text(encoding="utf-8"))["objects"]
        )

    def test_planting_date_round_trips(self, qtbot, scene, tmp_path) -> None:  # noqa: ARG002
        self._make_tree(scene)
        manager = ProjectManager()
        path = tmp_path / "tree.ogp"
        manager.save(scene, path)
        scene.clear()
        manager.load(scene, path)
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        loaded = next(i for i in scene.items() if isinstance(i, CircleItem))
        assert (
            loaded.metadata["plant_instance"]["planting_date"] == "2026-01-01"
        )

    def test_measured_current_height_drives_the_caster(self, qtbot, scene) -> None:  # noqa: ARG002
        """The owner's report: 'shadow scales only on max height, ignores
        current height'. The measured size must win — even with no date."""
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem
        from open_garden_planner.ui.canvas.sun_shadow_controller import (
            collect_shadow_casters,
        )

        # Drawn circle is deliberately 100 cm across while the species
        # matures at 400 — the gallery drop uses a fixed default size, so
        # "drawn == mature spread" (#213) does NOT hold on that path.
        tree = CircleItem(200, 200, 50, object_type=ObjectType.TREE)
        tree.metadata["plant_species"] = dict(self.SPECIES)
        tree.metadata["plant_instance"] = {
            "current_height_cm": 120.0,
            "current_spread_cm": 150.0,
        }
        scene.addItem(tree)

        casters = collect_shadow_casters(scene)  # no date at all
        assert casters, "the tree must still cast a shadow"
        footprint, height = casters[0]
        assert height == pytest.approx(120.0)  # NOT the 500 cm species max
        xs = [x for x, _ in footprint]
        # ABSOLUTE, like height: a typed 150 cm spread is a 150 cm canopy,
        # not a fraction of the 100 cm drawn circle.
        assert (max(xs) - min(xs)) == pytest.approx(150.0, abs=2.0)

    def test_canopy_grows_past_the_drawn_circle(self, qtbot, scene) -> None:  # noqa: ARG002
        """A placeholder-sized circle must not cap canopy growth.

        The earlier proportional model clamped the scale to ≤1, so a tree
        dropped at the default 200 cm could never shadow wider than that
        however large its species grows.
        """
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem
        from open_garden_planner.ui.canvas.sun_shadow_controller import (
            collect_shadow_casters,
        )

        tree = CircleItem(200, 200, 50, object_type=ObjectType.TREE)  # 100 cm drawn
        tree.metadata["plant_species"] = dict(self.SPECIES)  # matures at 400 cm
        tree.metadata["plant_instance"] = {
            "planting_date": "2026-01-01",
            "current_height_cm": 100.0,
            "current_spread_cm": 50.0,
        }
        scene.addItem(tree)

        footprint, _ = collect_shadow_casters(scene, at_date=date(2060, 1, 1))[0]
        xs = [x for x, _ in footprint]
        assert (max(xs) - min(xs)) == pytest.approx(400.0, abs=2.0)

    def test_unmeasured_plants_unchanged(self, qtbot, scene) -> None:  # noqa: ARG002
        """A dated but UN-measured plant keeps its mature size at every
        date — growth stays disengaged until a current height is typed."""
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem
        from open_garden_planner.ui.canvas.sun_shadow_controller import (
            collect_shadow_casters,
        )

        tree = CircleItem(200, 200, 200, object_type=ObjectType.TREE)
        tree.metadata["plant_species"] = dict(self.SPECIES)
        tree.metadata["plant_instance"] = {"planting_date": "2026-01-01"}
        scene.addItem(tree)

        for at in (date(2026, 1, 1), date(2040, 1, 1), None):
            _, height = collect_shadow_casters(scene, at_date=at)[0]
            assert height == pytest.approx(500.0)

    def test_undated_plants_unchanged(self, qtbot, scene) -> None:  # noqa: ARG002
        """No planting date → mature size at every sim date — behavior
        identical to pre-E8 (the compatibility contract)."""
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        tree = CircleItem(200, 200, 200, object_type=ObjectType.TREE)
        tree.metadata["plant_species"] = dict(self.SPECIES)
        scene.addItem(tree)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        controller.set_enabled(True)
        first = controller._overlay.path().boundingRect()
        controller.set_sim_datetime(datetime(2031, 6, 21, 12, 0, tzinfo=UTC))
        # The sun differs microscopically year-to-year (declination/EoT
        # drift), so a recompute may fire — but with no growth data the
        # shadow itself must be unchanged to sub-centimeter precision.
        second = controller._overlay.path().boundingRect()
        assert second.width() == pytest.approx(first.width(), abs=1.0)
        assert second.height() == pytest.approx(first.height(), abs=1.0)


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

        # Negative control: without the wiring, the same edit goes unseen —
        # proving the connection (not some hidden side channel) is what
        # keeps shadows fresh.
        cmd_mgr.stack_changed.disconnect(controller.schedule_recompute)
        cmd_mgr.redo()
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
