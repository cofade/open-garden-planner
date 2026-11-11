"""#663: plan north is drawing metadata, and every solar consumer follows it."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.commands import CommandManager, SetPlanNorthCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plan_north import (
    DEFAULT_NORTH_ANGLE_DEG,
    normalize_north_angle,
    north_direction,
)
from open_garden_planner.core.project import FILE_VERSION, ProjectData, ProjectManager
from open_garden_planner.core.shade_aggregation import daylight_samples
from open_garden_planner.core.shadow_geometry import shadow_direction_scene
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.core.solar import scene_azimuth, solar_position
from open_garden_planner.services.pdf_report_service import _draw_north_arrow
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "open_garden_planner.services.example_library.user_templates_dir", lambda: tmp_path
    )
    win = GardenPlannerApp()
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    qtbot.addWidget(win)
    return win


class TestNorthAngleValue:
    def test_zero_points_up_and_positive_turns_clockwise(self) -> None:
        assert north_direction(0) == pytest.approx((0.0, 1.0))
        assert north_direction(90) == pytest.approx((1.0, 0.0), abs=1e-12)
        x, y = north_direction(135)
        assert x == pytest.approx(0.70710678, abs=1e-6)
        assert y == pytest.approx(-0.70710678, abs=1e-6)

    def test_normalisation_wraps_and_rejects_non_numbers(self) -> None:
        assert normalize_north_angle(360) == 0.0
        assert normalize_north_angle(-45) == 315.0
        for bad in (True, "45", None, float("nan"), float("inf")):
            with pytest.raises(ValueError):
                normalize_north_angle(bad)


class TestNorthInTheSolarFrame:
    def test_scene_azimuth_adds_the_plan_bearing(self) -> None:
        # North at 45° (up-right): a sun due east (compass 90) lies down-right
        # in the scene (135) — opposite the shadow direction.
        assert scene_azimuth(90, 45) == pytest.approx(135.0)
        dx, dy = shadow_direction_scene(scene_azimuth(90, 45))
        assert dx == pytest.approx(-0.70710678, abs=1e-6)
        assert dy == pytest.approx(0.70710678, abs=1e-6)

    @pytest.mark.parametrize("north", [0.0, 45.0, 135.0, 270.0])
    def test_every_daylight_sample_turns_with_the_plan(self, north: float) -> None:
        day = date(2026, 6, 21)
        plain = daylight_samples(52.52, 13.40, day)
        turned = daylight_samples(52.52, 13.40, day, north_angle_deg=north)
        assert len(plain) == len(turned) > 0
        for before, after in zip(plain, turned, strict=True):
            assert after.azimuth_deg == pytest.approx(
                (before.azimuth_deg + north) % 360.0
            )
            assert after.elevation_deg == pytest.approx(before.elevation_deg)

    def test_the_3d_sun_uses_the_scene_frame(self) -> None:
        from open_garden_planner.ui.view3d.sync_controller import Scene3DController

        clock = SimClock()
        clock.set_datetime(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        location = {"latitude": 52.52, "longitude": 13.40}
        raw = solar_position(52.52, 13.40, clock.utc)

        class Dummy:
            _clock = clock
            _location = staticmethod(lambda: location)
            _north = staticmethod(lambda: 90.0)

        sun = Scene3DController._sun(Dummy())
        assert sun.elevation_deg == pytest.approx(raw.elevation_deg)
        assert sun.azimuth_deg == pytest.approx(raw.azimuth_deg)
        assert sun.scene_azimuth_deg == pytest.approx((raw.azimuth_deg + 90.0) % 360.0)

    def test_a_turned_plan_does_not_turn_the_living_look_or_the_reported_compass(
        self, qtbot
    ) -> None:
        from open_garden_planner.core.scene3d.look import look_for
        from open_garden_planner.core.scene3d.sink import SunState
        from open_garden_planner.core.scene3d.weather import dew_amount, is_morning

        compass = SunState(8.0, 120.0)
        turned = SunState(8.0, 120.0, 90.0)
        # The living look reads the COMPASS bearing: a plan rotation is not a
        # different time of day, and the published azimuth stays compass.
        assert is_morning(turned) is is_morning(compass) is True
        assert dew_amount(turned) == pytest.approx(dew_amount(compass))
        assert dew_amount(turned) > 0.0
        assert look_for(turned, "medium").sky.sun_azimuth_deg == pytest.approx(
            look_for(compass, "medium").sky.sun_azimuth_deg + 90.0
        )

    def test_the_pdf_north_arrow_turns_with_the_plan(self, qtbot) -> None:
        def centroid(angle: float) -> tuple[float, float]:
            image = QImage(120, 120, QImage.Format.Format_RGB32)
            image.fill(QColor("white"))
            painter = QPainter(image)
            try:
                _draw_north_arrow(painter, 60, 60, 40, angle)
            finally:
                painter.end()
            xs: list[float] = []
            ys: list[float] = []
            for y in range(image.height()):
                for x in range(image.width()):
                    if QColor(image.pixel(x, y)).lightness() < 120:
                        xs.append(float(x))
                        ys.append(float(y))
            assert xs
            return sum(xs) / len(xs), sum(ys) / len(ys)

        up_x, up_y = centroid(0.0)
        assert up_x == pytest.approx(60.0, abs=2.0)
        assert up_y < 55.0
        right_x, right_y = centroid(135.0)
        assert right_x > 65.0
        assert right_y > 50.0


class TestNorthInThePlan:
    def test_the_2d_shadow_overlay_turns_with_the_plan(self, qtbot) -> None:
        from open_garden_planner.core.object_height import METADATA_KEY
        from open_garden_planner.ui.canvas.sun_shadow_controller import SunShadowController

        def shadow_centroid(north: float) -> tuple[float, float]:
            scene = CanvasScene(width_cm=500, height_cm=500)
            caster = RectangleItem(
                200, 200, 40, 40, object_type=ObjectType.GENERIC_RECTANGLE
            )
            caster.metadata[METADATA_KEY] = 300.0
            scene.addItem(caster)
            controller = SunShadowController(
                scene,
                lambda: {"latitude": 52.52, "longitude": 13.40},
                north_provider=lambda: north,
            )
            controller.set_sim_datetime(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
            controller.set_enabled(True)
            polygons = controller.drape_polygons()
            controller.set_enabled(False)
            assert polygons
            points = [point for polygon in polygons for point in polygon]
            return (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )

        # A north-up plan has a south sun at noon: the shadow lies north of
        # the caster. With north at 90° (to the right), the same sun lies
        # south-west in the scene and the shadow turns east/south.
        up_x, up_y = shadow_centroid(0.0)
        assert up_y > 220.0
        turned_x, turned_y = shadow_centroid(90.0)
        assert turned_x > 220.0
        assert turned_y < 220.0

    def test_the_3d_sun_path_and_compass_turn_with_the_plan(self, qtbot) -> None:
        from open_garden_planner.core.scene3d.sun_path import (
            compass_mesh,
            day_arc,
        )

        plain = day_arc(52.52, 13.40, date(2026, 6, 21), UTC, "today")
        turned = day_arc(
            52.52, 13.40, date(2026, 6, 21), UTC, "today", north_angle_deg=90
        )
        assert plain.segments and turned.segments
        before = plain.segments[0][0]
        after = turned.segments[0][0]
        assert after.azimuth_deg == pytest.approx((before.azimuth_deg + 90.0) % 360.0)

        up = compass_mesh((0.0, 0.0), 1000.0)
        right = compass_mesh((0.0, 0.0), 1000.0, north_angle_deg=90.0)
        assert max(point[1] for point in up.positions) > 1050.0
        assert max(point[0] for point in right.positions) > 1050.0

    def test_a_heatmap_for_the_old_north_is_refused(self, qtbot) -> None:
        import numpy as np

        from open_garden_planner.core.object_height import METADATA_KEY
        from open_garden_planner.core.shade_aggregation import (
            HeatmapGrid,
            SunExposureResult,
        )
        from open_garden_planner.ui.canvas.sun_exposure_snapshot import (
            collect_exposure_snapshot,
        )
        from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController

        scene = CanvasScene(width_cm=200, height_cm=200)
        caster = RectangleItem(
            80, 80, 40, 40, object_type=ObjectType.GENERIC_RECTANGLE
        )
        caster.metadata[METADATA_KEY] = 100.0
        scene.addItem(caster)
        north = [0.0]
        location = {"latitude": 52.52, "longitude": 13.40}
        day = date(2026, 6, 21)
        controller = SunHeatmapController(
            scene, lambda: location, north_provider=lambda: north[0]
        )
        grid = HeatmapGrid.for_rect(0.0, 0.0, 200.0, 200.0, 10.0)
        controller.snapshot = collect_exposure_snapshot(scene, location, day, 0.0)
        controller._computed_day = day
        controller._grid = grid
        controller._result_wanted = True
        controller._document_generation = 0
        # The plan turns while the worker is still running: its result belongs
        # to the old frame and must not become the shown map.
        north[0] = 90.0
        controller._on_success(
            SunExposureResult(
                np.zeros((grid.rows, grid.cols), dtype=np.float32), (), (), None, None
            )
        )
        assert controller.exposure_reason == "stale"
        assert controller.result() is None

    def test_old_plans_load_at_zero_and_the_file_version_does_not_move(
        self, qtbot, tmp_path: Path
    ) -> None:
        scene = CanvasScene(width_cm=500, height_cm=500)
        pm = ProjectManager()
        assert pm.north_angle_deg == DEFAULT_NORTH_ANGLE_DEG
        pm.set_north_angle(45)
        target = tmp_path / "north.ogp"
        pm.save(scene, target)
        raw = json.loads(target.read_text(encoding="utf-8"))
        assert raw["north_angle_deg"] == 45.0
        assert raw["version"] == FILE_VERSION

        reopened = CanvasScene(width_cm=500, height_cm=500)
        again = ProjectManager()
        again.load(reopened, target)
        assert again.north_angle_deg == 45.0

        old = json.loads(target.read_text(encoding="utf-8"))
        old.pop("north_angle_deg")
        old_path = tmp_path / "old.ogp"
        old_path.write_text(json.dumps(old), encoding="utf-8")
        old_scene = CanvasScene(width_cm=500, height_cm=500)
        old_pm = ProjectManager()
        old_pm.load(old_scene, old_path)
        assert old_pm.north_angle_deg == 0.0

    def test_an_invalid_file_value_is_ignored_and_the_plan_still_opens(self) -> None:
        data = ProjectData.from_dict({"north_angle_deg": "sideways"})
        assert data.north_angle_deg == 0.0

    def test_setting_north_is_one_undo_step_and_keeps_every_object(self, qtbot, tmp_path) -> None:
        scene = CanvasScene(width_cm=500, height_cm=500)
        item = RectangleItem(100, 100, 80, 60, object_type=ObjectType.RAISED_BED, name="Bed")
        scene.addItem(item)
        pm = ProjectManager()
        manager = CommandManager()
        before = json.dumps(pm.snapshot_dict(scene)["objects"], sort_keys=True)
        manager.execute(SetPlanNorthCommand(pm, 45))
        assert pm.north_angle_deg == 45.0
        assert len(manager._undo_stack) == 1
        assert json.dumps(pm.snapshot_dict(scene)["objects"], sort_keys=True) == before
        manager.undo()
        assert pm.north_angle_deg == 0.0
        manager.redo()
        assert pm.north_angle_deg == 45.0

    def test_an_invalid_set_refuses_without_mutation(self) -> None:
        pm = ProjectManager()
        pm.set_north_angle(30)
        for bad in (True, "45", float("nan")):
            with pytest.raises(ValueError):
                pm.set_north_angle(bad)
            assert pm.north_angle_deg == 30.0


class TestNorthInTheApp:
    def test_the_dialog_command_reaches_the_canvas_and_undo_brings_it_back(self, window) -> None:
        window._project_manager.set_north_angle(0)
        window.canvas_view.command_manager.execute(
            SetPlanNorthCommand(window._project_manager, 135)
        )
        assert window.canvas_view.north_angle_deg() == pytest.approx(135.0)
        window.canvas_view.command_manager.undo()
        assert window.canvas_view.north_angle_deg() == pytest.approx(0.0)

    def test_save_and_reopen_keep_the_angle(self, window, tmp_path: Path) -> None:
        window._project_manager.set_north_angle(45)
        target = tmp_path / "north-app.ogp"
        window._save_to_file(target)
        window._load_project_file(str(target))
        assert window._project_manager.north_angle_deg == pytest.approx(45.0)
        assert window.canvas_view.north_angle_deg() == pytest.approx(45.0)

    def test_a_north_change_clears_the_days_heatmap(self, window) -> None:
        window._project_manager.set_location({"latitude": 52.52, "longitude": 13.40})
        window._sun_heatmap.snapshot = object()  # a computed day would be here
        window._project_manager.set_north_angle(90)
        assert window._sun_heatmap.snapshot is None
