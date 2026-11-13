"""Keep the current Qt numeric policy at the display seam."""

import pytest

from open_garden_planner.core.i18n import set_current_language
from open_garden_planner.core.measurement_display import area_text, length_text
from open_garden_planner.core.unit_preference import get_unit_preference
from open_garden_planner.core.units import LengthStyle, UnitSystem
from open_garden_planner.ui.canvas.items.vertex_handles import _format_coordinate


@pytest.mark.parametrize(
    ("value", "expected"), [(45.25, "45.3 cm"), (112.5, "1.13 m"), (-45.25, "-45.3 cm")]
)
def test_metric_length_keeps_qt_rounding(qtbot, value, expected):
    assert length_text(value) == expected


@pytest.mark.parametrize(("value", "expected"), [(45.25, "45.3 cm²"), (11250, "1.13 m²")])
def test_metric_area_keeps_qt_rounding(qtbot, value, expected):
    assert area_text(value) == expected


def test_shopping_plant_summary_keeps_its_whole_number_rounding(qtbot):
    assert length_text(60.5, style=LengthStyle.PLANT_SIZE) == "60 cm"


def test_vertex_coordinates_follow_units_and_preserve_metric_pairs(qtbot):
    assert _format_coordinate(243.84, 121.92) == "(2.44, 1.22) m"
    assert _format_coordinate(45.25, 30.0) == "(45.3, 30.0) cm"
    get_unit_preference().set_system(UnitSystem.IMPERIAL)
    assert _format_coordinate(243.84, 121.92) == "(8' 0\", 4' 0\")"
    get_unit_preference().set_system(UnitSystem.METRIC)
    set_current_language("de")
    assert _format_coordinate(243.84, 121.92) == "(2,44; 1,22) m"
    assert length_text(112.5) == "1,13 m"
