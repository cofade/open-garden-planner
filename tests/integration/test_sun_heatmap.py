"""Integration tests for the hours-of-sun heatmap (US-E4, #259).

Covers what the Qt-free unit suite cannot:
- the QImage rasterizer (route 1, ADR-037) against the point-in-polygon
  reference, including the 2-THREAD SMOKE TEST that licenses painting
  QImages off the GUI thread;
- the worker end to end on a real scene (a WALL polyline — pen-width
  footprint, default 200 cm height) reproducing the campaign toy case;
- the §8.19 pixel-band assertion through ``render_scene_region``;
- recompute-on-demand discipline, cancel/shutdown teardown safety, and
  the never-serialized guarantee.
"""

from __future__ import annotations

import threading
import time
from datetime import date

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.shade_aggregation import (
    HeatmapGrid,
    point_rasterizer_reference,
)
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_heatmap import (
    SunHeatmapController,
    SunHeatmapOverlayItem,
    rasterize_polygons_qimage,
)
from open_garden_planner.ui.widgets.sun_sim_toolbar import SunSimToolbar

BERLIN = {"latitude": 52.52, "longitude": 13.405}
WINTER = date(2026, 12, 21)
SUMMER = date(2026, 6, 21)

# Toy geometry: 40 m east–west WALL across a 40 m × 3 m canvas at y = 100;
# evaluation point 50 cm NORTH of the centerline at the canvas middle — far
# enough from the wall ends that it behaves as infinite for every azimuth
# that matters (|dx/dy| ≤ 40 ⇔ az ∈ (91.4°, 268.6°)).
WALL_Y = 100.0
POINT_NORTH = (2000.0, WALL_Y + 50.0)
POINT_SOUTH = (2000.0, 20.0)


@pytest.fixture
def wall_scene(qtbot) -> CanvasScene:  # noqa: ARG001
    scene = CanvasScene(4000.0, 300.0)
    wall = PolylineItem(
        [QPointF(0.0, WALL_Y), QPointF(4000.0, WALL_Y)],
        object_type=ObjectType.WALL,
    )
    scene.addItem(wall)
    return scene


def _run_and_wait(qtbot, controller: SunHeatmapController, day: date) -> None:
    with qtbot.waitSignal(controller.finished, timeout=60000) as blocker:
        assert controller.run_for_day(day)
    assert blocker.args == [True]


class TestQImageRasterizer:
    TRIANGLE = [[(35.0, 20.0), (370.0, 90.0), (150.0, 280.0)]]
    GRID = HeatmapGrid(x0_cm=0.0, y0_cm=0.0, cell_cm=10.0, cols=40, rows=30)

    def test_matches_point_reference(self, qtbot) -> None:  # noqa: ARG002
        qimage_mask = rasterize_polygons_qimage(self.TRIANGLE, self.GRID)
        reference = point_rasterizer_reference(self.TRIANGLE, self.GRID)
        mismatch = np.mean(qimage_mask != reference)
        # Differences only along polygon edges (pixel-fill vs cell-center
        # sampling) — a few boundary cells on a 1200-cell grid.
        assert mismatch < 0.03, f"mismatch fraction {mismatch:.3f}"

    def test_two_thread_smoke(self, qtbot) -> None:  # noqa: ARG002
        """The ADR-037 route-1 license: QImage painting is thread-safe off
        the GUI thread — two concurrent painter threads, identical output,
        no crash."""
        reference = rasterize_polygons_qimage(self.TRIANGLE, self.GRID)
        results: dict[int, list[np.ndarray]] = {0: [], 1: []}
        errors: list[BaseException] = []

        def paint_many(slot: int) -> None:
            try:
                for _ in range(40):
                    results[slot].append(
                        rasterize_polygons_qimage(self.TRIANGLE, self.GRID)
                    )
            except BaseException as exc:  # noqa: BLE001 — smoke test collects
                errors.append(exc)

        threads = [
            threading.Thread(target=paint_many, args=(slot,)) for slot in (0, 1)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not errors
        for slot in (0, 1):
            assert len(results[slot]) == 40
            for mask in results[slot]:
                assert np.array_equal(mask, reference)


class TestWorkerEndToEnd:
    def test_winter_toy_case_on_real_scene(self, qtbot, wall_scene) -> None:
        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        _run_and_wait(qtbot, controller, WINTER)

        assert controller.heatmap_visible()
        minutes, grid = controller.last_minutes, controller.last_grid
        assert minutes is not None and grid is not None
        north = minutes[grid.cell_at(*POINT_NORTH)]
        south = minutes[grid.cell_at(*POINT_SOUTH)]
        # North of the wall: zero direct sun on the winter solstice.
        assert north == 0.0
        # South of the wall: essentially the whole ~7.8 h winter day.
        assert south > 400.0

    def test_summer_toy_case_on_real_scene(self, qtbot, wall_scene) -> None:
        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        _run_and_wait(qtbot, controller, SUMMER)
        minutes, grid = controller.last_minutes, controller.last_grid
        north = minutes[grid.cell_at(*POINT_NORTH)]
        # The oracle's 540 min ± one sample; the real WALL item is 4 cm
        # thick (pen width), nudging the crossings by a few minutes.
        assert north == pytest.approx(540.0, abs=15.0)

    def test_gui_thread_stays_responsive(self, qtbot, wall_scene) -> None:
        """The compute runs off the GUI thread — a 150 ms timer must fire
        while the worker is still running (worker input is a snapshot,
        never live items)."""
        for i in range(60):  # widen the workload so the run outlives 150 ms
            item = RectangleItem(
                (i % 20) * 180.0, 120.0 + (i // 20) * 40.0, 30, 30,
                object_type=ObjectType.GENERIC_RECTANGLE,
            )
            item.metadata[METADATA_KEY] = 150.0
            wall_scene.addItem(item)
        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        fired_while_running: list[bool] = []
        QTimer.singleShot(
            50, lambda: fired_while_running.append(controller.is_running)
        )
        with qtbot.waitSignal(controller.finished, timeout=60000):
            # cell_cm=2 → 300 000 cells × ~67 samples — comfortably outlives
            # the 50 ms probe timer on any hardware (pyclipper+QImage are so
            # fast that the default grid finishes before any timer fires).
            assert controller.run_for_day(SUMMER, cell_cm=2.0)
        assert fired_while_running, "GUI event loop never turned during compute"
        assert fired_while_running[0] is True, (
            "the probe fired only after the worker finished — compute either "
            "blocked the GUI thread or ended before 50 ms"
        )

    def test_no_location_refuses(self, qtbot, wall_scene) -> None:  # noqa: ARG002
        controller = SunHeatmapController(wall_scene, lambda: None)
        assert controller.run_for_day(SUMMER) is False
        assert controller.run_count == 0

    def test_clear_mid_compute_drops_the_result(self, qtbot, wall_scene) -> None:
        """Senior-review P1: a date change / sim-off mid-compute calls
        clear() — the in-flight worker must be cancelled and its late result
        must NOT paint an orphaned overlay."""
        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        with qtbot.waitSignal(controller.finished, timeout=60000) as blocker:
            assert controller.run_for_day(SUMMER, cell_cm=2.0)
            controller.clear()
        assert blocker.args == [False]
        assert not controller.heatmap_visible()
        qtbot.wait(100)  # any stray queued success slot lands here
        assert not controller.heatmap_visible()
        controller.shutdown()

    def test_cancel_and_shutdown_mid_compute(self, qtbot, wall_scene) -> None:
        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        with qtbot.waitSignal(controller.finished, timeout=60000) as blocker:
            assert controller.run_for_day(SUMMER, cell_cm=2.0)
            controller.cancel()
        assert blocker.args == [False]
        assert not controller.heatmap_visible()
        controller.shutdown()  # idempotent, must not raise

    def test_recompute_on_demand_only(self, qtbot, wall_scene) -> None:
        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        _run_and_wait(qtbot, controller, WINTER)
        assert controller.run_count == 1
        # Scene edits do NOT retrigger the seconds-scale compute …
        item = RectangleItem(100, 30, 40, 40, object_type=ObjectType.TOOL_SHED)
        wall_scene.addItem(item)
        qtbot.wait(400)
        assert controller.run_count == 1
        # … and the (now potentially stale) overlay stays until asked anew —
        # recompute is a deliberate button press (the FR-SUN-05 contract).
        assert controller.heatmap_visible()


class TestPixelBand:
    def test_winter_ramp_tints_shade_darker(self, qtbot, wall_scene) -> None:
        """§8.19 formula, same discipline as US-E3's binding pixel test: the
        cool→warm ramp tints the shaded north point and renders it darker than
        the sunnier south point."""
        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        _run_and_wait(qtbot, controller, WINTER)

        region = QRectF(1900.0, 0.0, 200.0, 300.0)
        px_per_cm = 2.0

        def render() -> QImage:
            width = round(region.width() * px_per_cm)
            height = round(region.height() * px_per_cm)
            image = QImage(width, height, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            try:
                render_scene_region(
                    wall_scene,
                    painter,
                    QRectF(0, 0, width, height),
                    region,
                    y_flip=True,
                )
            finally:
                painter.end()
            return image

        with_heatmap = render()
        controller.clear()
        without_heatmap = render()

        def pixel(x_cm: float, y_cm: float) -> tuple[int, int]:
            px = round((x_cm - region.x()) * px_per_cm)
            py = round(with_heatmap.height() - (y_cm - region.y()) * px_per_cm)
            return px, py

        north_px = pixel(*POINT_NORTH)
        south_px = pixel(*POINT_SOUTH)

        def _lum(image: QImage, xy: tuple[int, int]) -> int:
            color = QColor(image.pixel(*xy))
            return color.red() + color.green() + color.blue()

        # Deep shade (north, 0 min) is tinted; and the cool→warm ramp renders
        # fewer sun-hours DARKER than more sun-hours (south, near full day).
        assert with_heatmap.pixel(*north_px) != without_heatmap.pixel(*north_px), (
            "deep shade must tint the point north of the wall"
        )
        assert _lum(with_heatmap, north_px) < _lum(with_heatmap, south_px), (
            "cool→warm ramp: fewer sun-hours must render darker than more"
        )


class TestNeverSerialized:
    def test_overlay_absent_from_saved_ogp(self, qtbot, wall_scene, tmp_path) -> None:
        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        _run_and_wait(qtbot, controller, WINTER)
        assert any(
            isinstance(i, SunHeatmapOverlayItem) for i in wall_scene.items()
        )
        manager = ProjectManager()
        file_path = tmp_path / "plan.ogp"
        manager.save(wall_scene, file_path)

        import json

        raw = json.loads(file_path.read_text(encoding="utf-8"))
        assert len(raw["objects"]) == 1  # just the wall

        wall_scene.clear()
        manager.load(wall_scene, file_path)
        assert not any(
            isinstance(i, SunHeatmapOverlayItem) for i in wall_scene.items()
        )

    def test_survives_scene_clear_then_rerun(self, qtbot, wall_scene) -> None:
        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        _run_and_wait(qtbot, controller, WINTER)
        wall_scene.clear()  # project load path — deletes the C++ overlay
        assert not controller.heatmap_visible()  # guarded, no RuntimeError
        wall = PolylineItem(
            [QPointF(0.0, WALL_Y), QPointF(4000.0, WALL_Y)],
            object_type=ObjectType.WALL,
        )
        wall_scene.addItem(wall)
        _run_and_wait(qtbot, controller, WINTER)
        assert controller.heatmap_visible()


class TestToolbarHeatmapControls:
    def test_button_emits_request_and_clear(self, qtbot) -> None:
        toolbar = SunSimToolbar()
        qtbot.addWidget(toolbar)
        requested: list[bool] = []
        cleared: list[bool] = []
        toolbar.heatmap_requested.connect(lambda: requested.append(True))
        toolbar.heatmap_cleared.connect(lambda: cleared.append(True))
        toolbar._heatmap_button.setChecked(True)
        assert requested and not cleared
        toolbar._heatmap_button.setChecked(False)
        assert cleared

    def test_busy_and_active_states(self, qtbot) -> None:
        toolbar = SunSimToolbar()
        qtbot.addWidget(toolbar)
        toolbar.set_heatmap_busy(True)
        assert not toolbar._heatmap_button.isEnabled()
        toolbar.set_heatmap_busy(False)
        assert toolbar._heatmap_button.isEnabled()
        toolbar.set_heatmap_active(True)
        assert toolbar._heatmap_button.isChecked()
        toolbar.set_heatmap_active(False)
        assert not toolbar._heatmap_button.isChecked()


class TestContours:
    def test_contours_built_and_cleared(self, qtbot, wall_scene) -> None:
        """Hourly lines + even-hour labels are created on success and fully
        removed on clear() (runtime-only, never serialized)."""
        from PyQt6.QtWidgets import QGraphicsSimpleTextItem

        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        _run_and_wait(qtbot, controller, SUMMER)
        assert controller._contour_items, "summer heatmap must draw hour contours"
        labels = [
            i
            for i in controller._contour_items
            if isinstance(i, QGraphicsSimpleTextItem)
        ]
        assert labels, "even-hour contours must be labeled"
        assert any("h" in label.text() for label in labels)

        controller.clear()
        assert controller._contour_items == []
        assert not any(
            isinstance(i, QGraphicsSimpleTextItem) for i in wall_scene.items()
        )

    def test_labels_respect_minimum_distance(self, qtbot, wall_scene) -> None:
        """Every hour label is >= _LABEL_MIN_DIST_CM from every other — no
        same-line pile-ups (the manual-test invariant; the per-component force
        that once bypassed it is gone)."""
        import math

        from PyQt6.QtWidgets import QGraphicsSimpleTextItem

        from open_garden_planner.ui.canvas.sun_heatmap import _LABEL_MIN_DIST_CM

        controller = SunHeatmapController(wall_scene, lambda: BERLIN)
        _run_and_wait(qtbot, controller, SUMMER)
        labels = [
            i
            for i in controller._contour_items
            if isinstance(i, QGraphicsSimpleTextItem)
        ]
        # halo + text share a position; dedup to one anchor per label.
        anchors = sorted(
            {(round(i.pos().x(), 3), round(i.pos().y(), 3)) for i in labels}
        )
        for a in range(len(anchors)):
            for b in range(a + 1, len(anchors)):
                dist = math.hypot(
                    anchors[a][0] - anchors[b][0], anchors[a][1] - anchors[b][1]
                )
                assert dist >= _LABEL_MIN_DIST_CM - 1e-6, (
                    f"two labels only {dist:.0f} cm apart"
                )


class TestAppGlue:
    def test_date_change_clears_heatmap_but_time_change_keeps_it(
        self, qtbot
    ) -> None:
        """The FR-SUN-05 stale rule lives in application._on_sun_sim_datetime:
        a TIME change keeps the (whole-day) map, a DATE change clears it."""
        from datetime import UTC, datetime

        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)
        heatmap = win._sun_heatmap
        heatmap._ensure_overlay().setVisible(True)
        heatmap._computed_day = SUMMER
        win._sun_toolbar.set_heatmap_active(True)

        win._on_sun_sim_datetime(datetime(2026, 6, 21, 15, 0, tzinfo=UTC))
        assert heatmap.heatmap_visible(), "time-of-day change must keep the map"

        win._on_sun_sim_datetime(datetime(2026, 6, 22, 15, 0, tzinfo=UTC))
        assert not heatmap.heatmap_visible(), "date change must clear the map"
        assert not win._sun_toolbar._heatmap_button.isChecked()


class TestPerf:
    def test_60k_cells_full_day_budget(self, qtbot) -> None:  # noqa: ARG002
        """The stated budget: 30 m × 20 m at 10 cm cells (60 000 cells),
        full summer day — < 2 s in the worker on dev hardware; asserted
        with CI slack (×3)."""
        scene = CanvasScene(3000.0, 2000.0)
        for i in range(10):
            item = RectangleItem(
                200.0 + i * 250.0, 800.0, 120, 60,
                object_type=ObjectType.TOOL_SHED,
            )
            scene.addItem(item)
        controller = SunHeatmapController(scene, lambda: BERLIN)
        start = time.perf_counter()
        with qtbot.waitSignal(controller.finished, timeout=30000):
            assert controller.run_for_day(SUMMER)
        elapsed = time.perf_counter() - start
        grid = controller.last_grid
        assert grid.cols * grid.rows == 60_000
        assert elapsed < 6.0, f"60k-cell full-day heatmap took {elapsed:.2f}s"
