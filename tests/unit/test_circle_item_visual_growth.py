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
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QStyleOptionGraphicsItem

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.circle_item import CircleItem

SPECIES_MATURE = {"max_spread_cm": 600.0}


def _tree(qtbot, radius: float = 300.0) -> CircleItem:
    item = CircleItem(500.0, 500.0, radius, object_type=ObjectType.TREE)
    item.metadata["plant_species"] = dict(SPECIES_MATURE)
    return item


def _paint_alone(item: CircleItem, size: int = 800):
    """Render item.paint() to a QImage in isolation (no scene/view, so no
    Y-flip/zoom to account for) and return (image, scale, boundingRect) so
    callers can map item-local coordinates to image pixels.
    """
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    bounding = item.boundingRect()
    scale = size / max(bounding.width(), bounding.height()) * 0.9
    painter.translate(size / 2, size / 2)
    painter.scale(scale, scale)
    painter.translate(-bounding.center().x(), -bounding.center().y())
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    return image, scale, bounding


def _alpha_at(image: QImage, scale: float, bounding, local_x: float, local_y: float, size: int = 800) -> int:
    px = int(size / 2 + scale * (local_x - bounding.center().x()))
    py = int(size / 2 + scale * (local_y - bounding.center().y()))
    return image.pixelColor(px, py).alpha()


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


class TestDropShadowTracksTheIcon:
    """Render-based regression pin (#298 senior review): a first cut of this
    fix left the decorative drop-shadow keyed to the full mature rect() while
    the icon shrank, so a young plant rendered as a large grey disc with a
    tiny sprite inside it. Every other test in this file asserts against
    private helpers, which stayed green through that regression -- this test
    renders actual pixels so it cannot make the same mistake.
    """

    def test_shrunk_icon_leaves_no_shadow_at_the_mature_footprints_edge(self, qtbot) -> None:
        item = _tree(qtbot, radius=100.0)  # rect width 200
        item.metadata["plant_instance"] = {
            "planting_date": date.today().isoformat(),
            "current_spread_cm": 20.0,  # icon radius ~10, far smaller than 100
        }
        item._shadows_enabled = True

        image, scale, bounding = _paint_alone(item)
        rect = item.rect()

        # A point near the edge of the MATURE footprint -- reachable by the
        # pre-fix shadow (drawn at rect()), unreachable by either the shrunk
        # icon or a shadow correctly sized to match it.
        edge_alpha = _alpha_at(image, scale, bounding, rect.center().x() + 90, rect.center().y())

        assert edge_alpha == 0

    def test_mature_icon_still_casts_its_shadow(self, qtbot) -> None:
        """Positive control: the drop-shadow isn't just gone everywhere --
        a plant with no growth data (icon == full footprint) still shows one
        near its edge, same as before this fix.
        """
        item = _tree(qtbot, radius=100.0)
        item._shadows_enabled = True

        image, scale, bounding = _paint_alone(item)
        rect = item.rect()

        edge_alpha = _alpha_at(image, scale, bounding, rect.center().x() + 90, rect.center().y())

        assert edge_alpha > 0


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
