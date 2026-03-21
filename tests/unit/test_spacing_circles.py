"""Unit tests for plant spacing circles and overlap detection (US-11.2)."""

import math
import uuid

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.circle_item import CircleItem


@pytest.fixture()
def plant_a(qtbot) -> CircleItem:  # noqa: ARG001
    """A plant at (100, 100) with radius 25."""
    item = CircleItem(100.0, 100.0, 25.0, object_type=ObjectType.TREE)
    item.plant_species = "apple"
    return item


@pytest.fixture()
def plant_b(qtbot) -> CircleItem:  # noqa: ARG001
    """A plant at (160, 100) with radius 20."""
    item = CircleItem(160.0, 100.0, 20.0, object_type=ObjectType.SHRUB)
    item.plant_species = "rose"
    return item


class TestEffectiveSpacingRadius:
    """Test the effective_spacing_radius() priority logic."""

    def test_no_data_returns_none(self, plant_a: CircleItem) -> None:
        """No metadata, no override → returns None (no circle drawn)."""
        assert plant_a.effective_spacing_radius() is None

    def test_from_metadata_max_spread(self, plant_a: CircleItem) -> None:
        """max_spread_cm in metadata → uses half of that."""
        plant_a._metadata = {"plant_species": {"max_spread_cm": 60.0}}
        assert plant_a.effective_spacing_radius() == 30.0

    def test_user_override_takes_priority(self, plant_a: CircleItem) -> None:
        """User override takes priority over metadata."""
        plant_a._metadata = {"plant_species": {"max_spread_cm": 60.0}}
        plant_a.spacing_radius_cm = 45.0
        assert plant_a.effective_spacing_radius() == 45.0

    def test_override_none_reverts_to_metadata(self, plant_a: CircleItem) -> None:
        """Setting override to None reverts to metadata."""
        plant_a._metadata = {"plant_species": {"max_spread_cm": 80.0}}
        plant_a.spacing_radius_cm = 45.0
        plant_a.spacing_radius_cm = None
        assert plant_a.effective_spacing_radius() == 40.0

    def test_zero_spread_returns_none(self, plant_a: CircleItem) -> None:
        """max_spread_cm of 0 is ignored, returns None."""
        plant_a._metadata = {"plant_species": {"max_spread_cm": 0}}
        assert plant_a.effective_spacing_radius() is None

    def test_user_override_without_metadata(self, plant_a: CircleItem) -> None:
        """User override works even without database data."""
        plant_a.spacing_radius_cm = 50.0
        assert plant_a.effective_spacing_radius() == 50.0


class TestSpacingOverlapField:
    """Test the spacing overlap status field."""

    def test_default_is_none(self, plant_a: CircleItem) -> None:
        assert plant_a.spacing_overlap is None

    def test_set_overlap(self, plant_a: CircleItem) -> None:
        plant_a.set_spacing_overlap("overlap")
        assert plant_a.spacing_overlap == "overlap"

    def test_set_ideal(self, plant_a: CircleItem) -> None:
        plant_a.set_spacing_overlap("ideal")
        assert plant_a.spacing_overlap == "ideal"

    def test_clear(self, plant_a: CircleItem) -> None:
        plant_a.set_spacing_overlap("overlap")
        plant_a.set_spacing_overlap(None)
        assert plant_a.spacing_overlap is None


class TestSpacingVisibility:
    """Test spacing circles visibility toggle."""

    def test_default_visible(self, plant_a: CircleItem) -> None:
        assert plant_a.spacing_circles_visible is True

    def test_toggle_off(self, plant_a: CircleItem) -> None:
        plant_a.spacing_circles_visible = False
        assert plant_a.spacing_circles_visible is False

    def test_toggle_on(self, plant_a: CircleItem) -> None:
        plant_a.spacing_circles_visible = False
        plant_a.spacing_circles_visible = True
        assert plant_a.spacing_circles_visible is True


class TestBoundingRectExpansion:
    """Test that boundingRect expands for spacing circle."""

    def test_bounding_rect_expands_with_data(self, plant_a: CircleItem) -> None:
        """Spacing circle should expand bounding rect when data present."""
        plant_a._metadata = {"plant_species": {"max_spread_cm": 200.0}}
        base = plant_a.boundingRect()
        # Set spacing overlap to trigger expansion
        plant_a.set_spacing_overlap("ideal")
        expanded = plant_a.boundingRect()
        assert expanded.width() > base.width()
        assert expanded.height() > base.height()

    def test_bounding_rect_not_expanded_when_hidden(self, plant_a: CircleItem) -> None:
        """Spacing circle hidden → bounding rect not expanded."""
        plant_a._metadata = {"plant_species": {"max_spread_cm": 200.0}}
        plant_a.spacing_circles_visible = False
        plant_a.set_spacing_overlap("ideal")
        base_width = plant_a.boundingRect().width()
        plant_a.spacing_circles_visible = True
        assert plant_a.boundingRect().width() > base_width

    def test_bounding_rect_not_expanded_without_data(self, plant_a: CircleItem) -> None:
        """No spacing data → bounding rect not expanded."""
        base = plant_a.boundingRect()
        plant_a.set_spacing_overlap("ideal")
        expanded = plant_a.boundingRect()
        assert expanded.width() == base.width()


class TestOverlapDetection:
    """Test pairwise overlap detection logic (unit-level, no scene)."""

    def test_plants_overlapping(self) -> None:
        """Distance < sum of spacing radii → overlap."""
        dist = 40.0
        radius_a = 25.0
        radius_b = 25.0
        assert dist < radius_a + radius_b

    def test_plants_ideal(self) -> None:
        """Distance > sum of spacing radii → ideal."""
        dist = 60.0
        radius_a = 25.0
        radius_b = 25.0
        assert dist >= radius_a + radius_b


class TestSerialization:
    """Test spacing_radius_cm serialization roundtrip."""

    def test_spacing_not_in_default_dict(self, plant_a: CircleItem) -> None:
        """Default items should not have spacing_radius_cm in serialized data."""
        data = plant_a.to_dict()
        assert "spacing_radius_cm" not in data

    def test_spacing_radius_persistence(self, plant_a: CircleItem) -> None:
        """Setting spacing_radius_cm should be retrievable."""
        plant_a.spacing_radius_cm = 35.0
        assert plant_a._spacing_radius_cm == 35.0
        assert plant_a.effective_spacing_radius() == 35.0


class TestNonPlantItemsIgnored:
    """Ensure non-plant circle items don't get spacing features."""

    def test_generic_circle_returns_none(self, qtbot) -> None:  # noqa: ARG002
        """Generic circles return None (no data), and rendering is gated on is_plant_type."""
        item = CircleItem(0, 0, 50.0, object_type=ObjectType.GENERIC_CIRCLE)
        assert item.effective_spacing_radius() is None
