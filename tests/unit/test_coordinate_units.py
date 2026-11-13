import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.coordinate_input.parser import ParseError, parse
from open_garden_planner.core.units import UnitSystem as U


@pytest.mark.parametrize(
    ("text", "system", "x", "y"),
    [
        ("96in, 120in", U.METRIC, 243.84, -304.8),
        ("8ft, 10ft", U.METRIC, 243.84, -304.8),
        ("100, 200", U.IMPERIAL, 254, -508),
        ("100, 200", U.METRIC, 100, -200),
        ("2m, 3m", U.METRIC, 200, -300),
    ],
)
def test_coordinate_unit_tokens(qtbot, text, system, x, y):
    result = parse(text, system=system)
    assert result.point.x() == pytest.approx(x)
    assert result.point.y() == pytest.approx(y)


def test_polar_angle_is_never_converted(qtbot):
    result = parse("@5ft<90", QPointF(), system=U.IMPERIAL)
    assert result.point.y() == pytest.approx(-152.4)
    with pytest.raises(ParseError):
        parse("@5ft<90ft", QPointF(), system=U.IMPERIAL)


def test_bad_unit_refused(qtbot):
    with pytest.raises(ParseError):
        parse("5 furlongs, 1")
