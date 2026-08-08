"""Unit tests for CircleItem's growth-aware icon rendering (issue #298 follow-up).

The plant's SVG icon size is decoupled from the drawn footprint: the
footprint (``rect()``/``radius``) stays at the mature ``max_spread_cm`` for
spacing/overlap correctness (see ``core/plant_sizing.py``'s "three
legitimate sizes" note), while the ICON reflects the growth-model
current size when both a planting date and a measured current spread are
set -- matching the shadow, which already did this via US-E8.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.circle_item import CircleItem

SPECIES_MATURE = {"max_spread_cm": 600.0}


def _tree(qtbot, radius: float = 300.0) -> CircleItem:
    item = CircleItem(500.0, 500.0, radius, object_type=ObjectType.TREE)
    item.metadata["plant_species"] = dict(SPECIES_MATURE)
    return item


class TestVisualPlantDiameter:
    def test_no_species_falls_back_to_footprint(self, qtbot) -> None:
        item = CircleItem(500.0, 500.0, 300.0, object_type=ObjectType.TREE)
        assert item._visual_plant_diameter_cm(600.0) == 600.0

    def test_no_growth_data_falls_back_to_footprint(self, qtbot) -> None:
        item = _tree(qtbot)
        assert item._visual_plant_diameter_cm(600.0) == 600.0

    def test_freshly_planted_young_tree_renders_much_smaller_than_footprint(self, qtbot) -> None:
        item = _tree(qtbot)
        item.metadata["plant_instance"] = {
            "planting_date": date.today().isoformat(),
            "current_spread_cm": 50.0,
        }

        diameter = item._visual_plant_diameter_cm(600.0)

        assert diameter == pytest.approx(50.0, abs=1.0)
        assert diameter < 600.0

    def test_mature_tree_renders_at_footprint_size(self, qtbot) -> None:
        item = _tree(qtbot)
        item.metadata["plant_instance"] = {
            "planting_date": (date.today() - timedelta(days=365 * 30)).isoformat(),
            "current_spread_cm": 50.0,
        }

        diameter = item._visual_plant_diameter_cm(600.0)

        assert diameter == pytest.approx(600.0, abs=1.0)

    def test_oversized_current_measurement_exceeds_footprint(self, qtbot) -> None:
        """A current size recorded larger than the species max is returned
        as-is (already mature) -- see growth_model._grown_dimension.
        """
        item = _tree(qtbot)
        item.metadata["plant_instance"] = {
            "planting_date": date.today().isoformat(),
            "current_spread_cm": 900.0,
        }

        assert item._visual_plant_diameter_cm(600.0) == 900.0


class TestBoundingRectNeverShrinksBelowFootprint:
    def test_shrunk_visual_diameter_does_not_shrink_bounding_rect(self, qtbot) -> None:
        """The invariant is "never below the item's own geometry" (so hit-
        testing/selection of the mature footprint stays intact) -- NOT "stays
        equal to the mature-icon baseline". A much-smaller icon legitimately
        needs LESS overflow than a full-size one (it draws well within the
        footprint rect), so a strictly-smaller boundingRect here is correct,
        not a regression.
        """
        item = _tree(qtbot)
        baseline = item.boundingRect()
        footprint_width = item.rect().width()

        item.metadata["plant_instance"] = {
            "planting_date": date.today().isoformat(),
            "current_spread_cm": 10.0,
        }
        shrunk = item.boundingRect()

        assert shrunk.width() >= footprint_width
        assert shrunk.height() >= item.rect().height()
        assert shrunk.width() <= baseline.width()

    def test_oversized_current_measurement_grows_bounding_rect(self, qtbot) -> None:
        """Qt uses boundingRect() for the repaint/hit-test region -- an
        oversized pixmap that isn't reflected here would paint outside the
        advertised rect and risk leaving a ghost (see #218's own lesson).
        """
        item = _tree(qtbot)
        baseline = item.boundingRect()

        item.metadata["plant_instance"] = {
            "planting_date": date.today().isoformat(),
            "current_spread_cm": 900.0,
        }
        grown = item.boundingRect()

        assert grown.width() > baseline.width()


class TestFootprintUnaffected:
    def test_footprint_radius_is_unchanged_by_current_spread(self, qtbot) -> None:
        """The spacing footprint must stay at the mature size regardless of
        the visual icon's size -- overlap/companion-distance correctness
        (core/plant_sizing.py) must not regress.
        """
        item = _tree(qtbot, radius=300.0)

        item.metadata["plant_instance"] = {
            "planting_date": date.today().isoformat(),
            "current_spread_cm": 10.0,
        }

        assert item.radius == 300.0
        assert item.rect().width() == 600.0
