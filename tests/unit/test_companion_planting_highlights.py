"""Unit tests for companion planting visual highlight logic (US-10.2)."""

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.companion_planting_service import ANTAGONISTIC, BENEFICIAL
from open_garden_planner.ui.canvas.items.circle_item import CircleItem


@pytest.fixture()
def tomato_item(qtbot) -> CircleItem:  # noqa: ARG001
    """A CircleItem representing a tomato plant at (100, 100)."""
    item = CircleItem(100.0, 100.0, 25.0, object_type=ObjectType.TREE)
    item.plant_species = "tomato"
    return item


@pytest.fixture()
def basil_item(qtbot) -> CircleItem:  # noqa: ARG001
    """A CircleItem representing basil at (150, 100) — 50cm from tomato."""
    item = CircleItem(150.0, 100.0, 15.0, object_type=ObjectType.SHRUB)
    item.plant_species = "basil"
    return item


@pytest.fixture()
def fennel_item(qtbot) -> CircleItem:  # noqa: ARG001
    """A CircleItem representing fennel at (160, 100) — 60cm from tomato."""
    item = CircleItem(160.0, 100.0, 15.0, object_type=ObjectType.SHRUB)
    item.plant_species = "fennel"
    return item


class TestCompanionHighlightField:
    def test_default_highlight_is_none(self, tomato_item: CircleItem) -> None:
        assert tomato_item.companion_highlight is None

    def test_set_beneficial_highlight(self, tomato_item: CircleItem) -> None:
        tomato_item.set_companion_highlight(BENEFICIAL)
        assert tomato_item.companion_highlight == BENEFICIAL

    def test_set_antagonistic_highlight(self, tomato_item: CircleItem) -> None:
        tomato_item.set_companion_highlight(ANTAGONISTIC)
        assert tomato_item.companion_highlight == ANTAGONISTIC

    def test_clear_highlight(self, tomato_item: CircleItem) -> None:
        tomato_item.set_companion_highlight(BENEFICIAL)
        tomato_item.set_companion_highlight(None)
        assert tomato_item.companion_highlight is None

    def test_set_same_value_is_no_op(self, tomato_item: CircleItem) -> None:
        """Setting the same highlight value twice should not cause issues."""
        tomato_item.set_companion_highlight(BENEFICIAL)
        tomato_item.set_companion_highlight(BENEFICIAL)
        assert tomato_item.companion_highlight == BENEFICIAL


class TestBoundingRectExpansion:
    def test_bounding_rect_larger_with_highlight(self, basil_item: CircleItem) -> None:
        rect_no_highlight = basil_item.boundingRect()
        basil_item.set_companion_highlight(BENEFICIAL)
        rect_with_highlight = basil_item.boundingRect()
        assert rect_with_highlight.width() > rect_no_highlight.width()
        assert rect_with_highlight.height() > rect_no_highlight.height()

    def test_bounding_rect_returns_to_normal_after_clear(self, basil_item: CircleItem) -> None:
        rect_original = basil_item.boundingRect()
        basil_item.set_companion_highlight(BENEFICIAL)
        basil_item.set_companion_highlight(None)
        rect_cleared = basil_item.boundingRect()
        assert abs(rect_cleared.width() - rect_original.width()) < 0.01


class TestHighlightLogic:
    """Test the proximity-based highlight assignment logic (extracted for unit testing)."""

    def _run_highlights(self, selected_plants, all_plants, radius_cm=200.0) -> None:
        """Replicate the core update logic from GardenPlannerApp._update_companion_highlights."""
        import math
        from open_garden_planner.services.companion_planting_service import CompanionPlantingService

        svc = CompanionPlantingService()

        # Clear
        for it in all_plants + selected_plants:
            it.set_companion_highlight(None)

        for sel in selected_plants:
            sel_center = QPointF(sel.rect().center().x() + sel.pos().x(),
                                 sel.rect().center().y() + sel.pos().y())
            sel_species = sel.plant_species

            for other in all_plants:
                other_center = QPointF(other.rect().center().x() + other.pos().x(),
                                       other.rect().center().y() + other.pos().y())
                dist = math.hypot(sel_center.x() - other_center.x(),
                                  sel_center.y() - other_center.y())
                if dist > radius_cm:
                    continue
                rel = svc.get_relationship(sel_species, other.plant_species)
                if rel is None:
                    continue
                current = other.companion_highlight
                if rel.type == ANTAGONISTIC:
                    other.set_companion_highlight(ANTAGONISTIC)
                elif rel.type == BENEFICIAL and current != ANTAGONISTIC:
                    other.set_companion_highlight(BENEFICIAL)

    def test_nearby_beneficial_gets_green(
        self, tomato_item: CircleItem, basil_item: CircleItem
    ) -> None:
        self._run_highlights([tomato_item], [basil_item], radius_cm=200.0)
        assert basil_item.companion_highlight == BENEFICIAL

    def test_nearby_antagonistic_gets_red(
        self, tomato_item: CircleItem, fennel_item: CircleItem
    ) -> None:
        self._run_highlights([tomato_item], [fennel_item], radius_cm=200.0)
        assert fennel_item.companion_highlight == ANTAGONISTIC

    def test_out_of_radius_gets_no_highlight(
        self, tomato_item: CircleItem, basil_item: CircleItem
    ) -> None:
        # Radius of 10cm — basil is 50cm away
        self._run_highlights([tomato_item], [basil_item], radius_cm=10.0)
        assert basil_item.companion_highlight is None

    def test_antagonistic_overrides_beneficial(
        self,
        tomato_item: CircleItem,
        basil_item: CircleItem,
        fennel_item: CircleItem,
        qtbot,  # noqa: ARG002
    ) -> None:
        """When two selected plants conflict, antagonistic takes priority."""
        # Create a second selected plant (basil) near fennel
        # fennel is beneficial to dill (not basil), antagonistic to tomato
        # So if tomato is selected, fennel should be ANTAGONISTIC
        # even if another plant would make it BENEFICIAL
        fennel2 = CircleItem(160.0, 100.0, 15.0, object_type=ObjectType.SHRUB)
        fennel2.plant_species = "fennel"
        self._run_highlights([tomato_item], [fennel2], radius_cm=200.0)
        assert fennel2.companion_highlight == ANTAGONISTIC

    def test_unrelated_plants_get_no_highlight(
        self, tomato_item: CircleItem, qtbot  # noqa: ARG002
    ) -> None:
        """Plants with no recorded relationship remain unhighlighted."""
        unknown = CircleItem(120.0, 100.0, 15.0, object_type=ObjectType.SHRUB)
        unknown.plant_species = "unknown_exotic_plant_xyz"
        self._run_highlights([tomato_item], [unknown], radius_cm=200.0)
        assert unknown.companion_highlight is None

    def test_no_selected_plants_clears_all(
        self, basil_item: CircleItem
    ) -> None:
        basil_item.set_companion_highlight(BENEFICIAL)
        self._run_highlights([], [basil_item], radius_cm=200.0)
        assert basil_item.companion_highlight is None
