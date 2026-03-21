"""Unit tests for square-foot grid overlay (US-11.3)."""

import pytest
from PyQt6.QtCore import QPointF, QRectF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def bed_polygon(qtbot) -> PolygonItem:  # noqa: ARG001
    """A 120×90 polygon bed."""
    vertices = [
        QPointF(0, 0),
        QPointF(120, 0),
        QPointF(120, 90),
        QPointF(0, 90),
    ]
    return PolygonItem(vertices, object_type=ObjectType.GARDEN_BED)


@pytest.fixture()
def bed_rect(qtbot) -> RectangleItem:  # noqa: ARG001
    """A 120×90 rectangle bed."""
    return RectangleItem(0, 0, 120, 90, object_type=ObjectType.GARDEN_BED)


@pytest.fixture()
def non_bed_polygon(qtbot) -> PolygonItem:  # noqa: ARG001
    """A polygon that is NOT a bed type."""
    vertices = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)]
    return PolygonItem(vertices, object_type=ObjectType.HOUSE)


# ── Default state ─────────────────────────────────────────────


class TestGridDefaults:
    """Grid properties default to sensible values."""

    def test_grid_disabled_by_default(self, bed_polygon: PolygonItem) -> None:
        assert bed_polygon.grid_enabled is False

    def test_default_spacing_30cm(self, bed_polygon: PolygonItem) -> None:
        assert bed_polygon.grid_spacing == 30.0

    def test_default_not_in_export(self, bed_polygon: PolygonItem) -> None:
        assert bed_polygon.grid_visible_in_export is False


# ── Property setters ──────────────────────────────────────────


class TestGridProperties:
    """Grid setters persist values in metadata."""

    def test_enable_grid(self, bed_polygon: PolygonItem) -> None:
        bed_polygon.grid_enabled = True
        assert bed_polygon.grid_enabled is True
        assert bed_polygon.metadata["grid_enabled"] is True

    def test_disable_grid(self, bed_polygon: PolygonItem) -> None:
        bed_polygon.grid_enabled = True
        bed_polygon.grid_enabled = False
        assert bed_polygon.grid_enabled is False
        assert bed_polygon.metadata["grid_enabled"] is False

    def test_change_spacing(self, bed_polygon: PolygonItem) -> None:
        bed_polygon.grid_spacing = 15.0
        assert bed_polygon.grid_spacing == 15.0
        assert bed_polygon.metadata["grid_spacing"] == 15.0

    def test_spacing_clamped_to_min(self, bed_polygon: PolygonItem) -> None:
        bed_polygon.grid_spacing = 0.0
        assert bed_polygon.grid_spacing >= 1.0

    def test_export_flag(self, bed_polygon: PolygonItem) -> None:
        bed_polygon.grid_visible_in_export = True
        assert bed_polygon.metadata["grid_visible_in_export"] is True


# ── Metadata persistence (round-trip) ────────────────────────


class TestGridMetadataRoundTrip:
    """Grid settings survive construction from metadata dict."""

    def test_polygon_from_metadata(self, qtbot) -> None:  # noqa: ARG002
        meta = {"grid_enabled": True, "grid_spacing": 15.0}
        vertices = [QPointF(0, 0), QPointF(60, 0), QPointF(60, 60), QPointF(0, 60)]
        item = PolygonItem(vertices, object_type=ObjectType.GARDEN_BED, metadata=meta)
        assert item.grid_enabled is True
        assert item.grid_spacing == 15.0

    def test_rectangle_from_metadata(self, qtbot) -> None:  # noqa: ARG002
        meta = {"grid_enabled": True, "grid_spacing": 40.0}
        item = RectangleItem(0, 0, 80, 80, object_type=ObjectType.RAISED_BED, metadata=meta)
        assert item.grid_enabled is True
        assert item.grid_spacing == 40.0


# ── Cell count ────────────────────────────────────────────────


class TestGridCellCount:
    """grid_cell_count() returns correct numbers."""

    def test_polygon_cell_count(self, bed_polygon: PolygonItem) -> None:
        bed_polygon.grid_spacing = 30.0
        # 120×90 = 10800 cm²; cell = 900 cm² → 12 cells
        assert bed_polygon.grid_cell_count() == 12

    def test_rectangle_cell_count(self, bed_rect: RectangleItem) -> None:
        bed_rect.grid_spacing = 30.0
        # 120/30 = 4 cols, 90/30 = 3 rows → 12
        assert bed_rect.grid_cell_count() == 12

    def test_polygon_cell_count_15cm(self, bed_polygon: PolygonItem) -> None:
        bed_polygon.grid_spacing = 15.0
        # 120×90 / 15² = 10800/225 = 48
        assert bed_polygon.grid_cell_count() == 48

    def test_zero_spacing_returns_zero(self, bed_polygon: PolygonItem) -> None:
        bed_polygon._grid_spacing = 0
        assert bed_polygon.grid_cell_count() == 0
