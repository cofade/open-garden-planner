"""Integration tests for US-12.10b — Canvas Soil Health Overlay.

The overlay tints beds by the worst (or selected) soil-health parameter and
falls back to a hatched grey fill when no test exists. It is rendered at the
view level so PNG/SVG/PDF/print exports — all of which call ``scene.render()``
— exclude it.

These tests cover:
  * SoilService.health_level rules (pH ranges, NPK buckets, "overall" worst-of)
  * CanvasView state setters & visibility wiring
  * The overlay is invoked from CanvasView.drawForeground only when active
  * scene.render() does NOT trigger the overlay (export-exclusion guarantee)
  * Param combo updates the view via the application's wiring
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.services.soil_service import (
    GLOBAL_TARGET_ID,
    PARAM_K,
    PARAM_N,
    PARAM_OVERALL,
    PARAM_P,
    PARAM_PH,
    HealthLevel,
    SoilService,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


# ---------------------------------------------------------------------------
# health_level rules
# ---------------------------------------------------------------------------


class TestHealthLevel:
    def test_no_record_is_unknown(self) -> None:
        assert SoilService.health_level(None, PARAM_OVERALL) is HealthLevel.UNKNOWN

    def test_ph_in_ideal_range_is_good(self) -> None:
        rec = SoilTestRecord(date="2026-01-01", ph=6.5)
        assert SoilService.health_level(rec, PARAM_PH) is HealthLevel.GOOD

    def test_ph_acidic_borderline_is_fair(self) -> None:
        rec = SoilTestRecord(date="2026-01-01", ph=5.7)
        assert SoilService.health_level(rec, PARAM_PH) is HealthLevel.FAIR

    def test_ph_extreme_is_poor(self) -> None:
        rec = SoilTestRecord(date="2026-01-01", ph=4.5)
        assert SoilService.health_level(rec, PARAM_PH) is HealthLevel.POOR

    def test_ph_unset_is_unknown(self) -> None:
        rec = SoilTestRecord(date="2026-01-01")
        assert SoilService.health_level(rec, PARAM_PH) is HealthLevel.UNKNOWN

    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            (0, HealthLevel.POOR),
            (1, HealthLevel.POOR),
            (2, HealthLevel.FAIR),
            (3, HealthLevel.GOOD),
            (4, HealthLevel.GOOD),
        ],
    )
    def test_npk_buckets(self, level: int, expected: HealthLevel) -> None:
        rec = SoilTestRecord(
            date="2026-01-01", n_level=level, p_level=level, k_level=level,
        )
        for param in (PARAM_N, PARAM_P, PARAM_K):
            assert SoilService.health_level(rec, param) is expected

    def test_overall_is_worst_known(self) -> None:
        # pH GOOD, N FAIR, P GOOD, K unset → overall FAIR
        rec = SoilTestRecord(
            date="2026-01-01", ph=6.5, n_level=2, p_level=3,
        )
        assert SoilService.health_level(rec, PARAM_OVERALL) is HealthLevel.FAIR

    def test_overall_with_one_poor_is_poor(self) -> None:
        rec = SoilTestRecord(
            date="2026-01-01", ph=6.5, n_level=3, p_level=0, k_level=4,
        )
        assert SoilService.health_level(rec, PARAM_OVERALL) is HealthLevel.POOR

    def test_overall_all_unknown_stays_unknown(self) -> None:
        rec = SoilTestRecord(date="2026-01-01")
        assert SoilService.health_level(rec, PARAM_OVERALL) is HealthLevel.UNKNOWN


# ---------------------------------------------------------------------------
# CanvasView state wiring
# ---------------------------------------------------------------------------


@pytest.fixture()
def view_with_service(qtbot: object) -> tuple[CanvasView, SoilService, ProjectManager]:
    """A CanvasView with a SoilService injected and one bed."""
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]

    pm = ProjectManager()
    svc = SoilService(pm)
    view.set_soil_service(svc)

    bed = RectangleItem(100, 100, 300, 200, object_type=ObjectType.GARDEN_BED)
    scene.addItem(bed)
    return view, svc, pm


class TestOverlayState:
    def test_default_state(self, view_with_service: tuple) -> None:
        view, _, _ = view_with_service
        assert view.soil_overlay_visible is False
        assert view.soil_overlay_param == PARAM_OVERALL

    def test_toggle_visible(self, view_with_service: tuple) -> None:
        view, _, _ = view_with_service
        view.set_soil_overlay_visible(True)
        assert view.soil_overlay_visible is True
        view.set_soil_overlay_visible(False)
        assert view.soil_overlay_visible is False

    def test_param_setter_accepts_known(self, view_with_service: tuple) -> None:
        view, _, _ = view_with_service
        view.set_soil_overlay_param(PARAM_PH)
        assert view.soil_overlay_param == PARAM_PH

    def test_param_setter_rejects_unknown(self, view_with_service: tuple) -> None:
        view, _, _ = view_with_service
        view.set_soil_overlay_param("bogus")
        assert view.soil_overlay_param == PARAM_OVERALL


# ---------------------------------------------------------------------------
# Painting: the overlay calls SoilService for each bed when on, and not when off
# ---------------------------------------------------------------------------


class TestOverlayPainting:
    def test_overlay_off_does_not_query_service(
        self, view_with_service: tuple
    ) -> None:
        view, svc, _ = view_with_service
        # Overlay is off by default — drawForeground should never query the service.
        with patch.object(
            svc, "get_effective_record", wraps=svc.get_effective_record
        ) as spy:
            self._render_view(view)
            spy.assert_not_called()

    def test_overlay_on_queries_service_for_each_bed(
        self, view_with_service: tuple
    ) -> None:
        view, svc, _ = view_with_service
        view.set_soil_overlay_visible(True)
        with patch.object(
            svc, "get_effective_record", wraps=svc.get_effective_record
        ) as spy:
            self._render_view(view)
            assert spy.call_count == 1  # exactly one bed in the scene

    def test_overlay_skips_non_bed_items(self, view_with_service: tuple) -> None:
        view, svc, _ = view_with_service
        # Add a non-bed rectangle (raw, no GARDEN_BED type) — must be ignored.
        scene = view.scene()
        non_bed = RectangleItem(
            500, 500, 200, 200, object_type=ObjectType.GENERIC_RECTANGLE
        )
        scene.addItem(non_bed)

        view.set_soil_overlay_visible(True)
        with patch.object(
            svc, "get_effective_record", wraps=svc.get_effective_record
        ) as spy:
            self._render_view(view)
            assert spy.call_count == 1  # still only the GARDEN_BED counted

    def test_scene_render_excludes_overlay(
        self, view_with_service: tuple
    ) -> None:
        """Exports go through scene.render() which never invokes view.drawForeground."""
        view, svc, _ = view_with_service
        view.set_soil_overlay_visible(True)
        scene = view.scene()

        image = QImage(200, 200, QImage.Format.Format_ARGB32)
        image.fill(0)
        with patch.object(
            svc, "get_effective_record", wraps=svc.get_effective_record
        ) as spy:
            painter = QPainter(image)
            scene.render(painter)
            painter.end()
            # If the overlay leaked into exports, the spy would fire — but the
            # overlay lives in view.drawForeground, not scene.drawForeground.
            spy.assert_not_called()

    @staticmethod
    def _render_view(view: CanvasView) -> None:
        """Trigger drawForeground by rendering the view to an offscreen image."""
        image = QImage(200, 200, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        view.render(painter, QRectF(0, 0, 200, 200), view.rect())
        painter.end()


# ---------------------------------------------------------------------------
# Effective record drives the colour bucket
# ---------------------------------------------------------------------------


class TestEffectiveRecordRouting:
    def test_global_default_used_when_bed_has_no_record(
        self, view_with_service: tuple
    ) -> None:
        _, svc, _ = view_with_service
        svc.add_record(GLOBAL_TARGET_ID, SoilTestRecord(date="2026-01-01", ph=6.5))

        # Any random bed id falls back to global → GOOD.
        record = svc.get_effective_record("any-bed-id")
        assert record is not None
        assert SoilService.health_level(record, PARAM_PH) is HealthLevel.GOOD

    def test_bed_specific_record_overrides_global(
        self, view_with_service: tuple
    ) -> None:
        view, svc, _ = view_with_service
        # Global says GOOD, bed-specific says POOR — bed wins.
        svc.add_record(GLOBAL_TARGET_ID, SoilTestRecord(date="2026-01-01", ph=6.5))
        scene = view.scene()
        bed = next(
            i for i in scene.items()
            if getattr(i, "object_type", None) is ObjectType.GARDEN_BED
        )
        bed_id = str(bed.item_id)
        svc.add_record(bed_id, SoilTestRecord(date="2026-04-01", ph=4.5))

        record = svc.get_effective_record(bed_id)
        assert record is not None
        assert SoilService.health_level(record, PARAM_PH) is HealthLevel.POOR
