import ast
from pathlib import Path

import pytest

from open_garden_planner.core.units import LengthStyle as S
from open_garden_planner.core.units import UnitSystem as U
from open_garden_planner.core.units import (
    cm_to_inches,
    default_bare_unit_cm,
    format_area,
    format_length,
    format_volume,
    grid_size_cm,
    imperial_step_inches,
    inches_to_cm,
    nice_distances,
    nudge_fine_cm,
    parse_length,
    parse_volume,
)

METRIC_CASES = [  # byte-identical to today's inline code
    (50.0, S.AUTO, "50.0 cm"),
    (99.9, S.AUTO, "99.9 cm"),
    (100.0, S.AUTO, "1.00 m"),
    (235.5, S.AUTO, "2.35 m"),
    (50.0, S.METRES, "0.50 m"),
    (25.0, S.CENTIMETRES, "25.0 cm"),
    (0.0, S.COORDINATE, "0.00 cm"),
    (1234.5, S.COORDINATE, "1234.50 cm"),
    (50, S.RULER, "50"),
    (100, S.RULER, "1m"),
    (250, S.RULER, "2.5m"),
    (0, S.RULER, "0"),
    (1, S.SCALE_BAR, "1 cm"),
    (250, S.SCALE_BAR, "2.5 m"),
    (100000, S.SCALE_BAR, "1 km"),
    (61.4, S.PLANT_SIZE, "61 cm"),
    (2.0, S.DEPTH, "2.0 cm"),
    (2, S.DEPTH, "2 cm"),
    (120000.0, S.FEET, "1200 m"),
]
IMPERIAL_CASES = [
    (0.0, S.AUTO, '0"'),
    (2.54, S.AUTO, '1"'),
    (1.5875, S.AUTO, '5/8"'),
    (19.05, S.AUTO, '7 1/2"'),
    (30.48, S.AUTO, "1' 0\""),
    (30.40, S.AUTO, "1' 0\""),
    (77.47, S.AUTO, "2' 6 1/2\""),
    (243.84, S.AUTO, "8' 0\""),
    (-77.47, S.AUTO, "-2' 6 1/2\""),
    (-0.05, S.AUTO, '0"'),
    (2.38125, S.AUTO, '1"'),
    (50.0, S.METRES, "1' 7 5/8\""),
    (60.0, S.PLANT_SIZE, "2' 0\""),
    (20.32, S.PLANT_SIZE, '8"'),
    (96.52, S.PLANT_SIZE, "3' 2\""),
    (0.635, S.DEPTH, '1/4"'),
    (3.81, S.DEPTH, '1 1/2"'),
    (35.56, S.DEPTH, '14"'),
    (0.0, S.RULER, "0"),
    (15.24, S.RULER, '6"'),
    (30.48, S.RULER, "1'"),
    (45.72, S.RULER, "1' 6\""),
    (15.24, S.SCALE_BAR, "6 in"),
    (762.0, S.SCALE_BAR, "25 ft"),
    (120000.0, S.FEET, "3937 ft"),
]


@pytest.mark.parametrize(("cm", "style", "expected"), METRIC_CASES)
def test_metric_output_is_unchanged(cm, style, expected):
    assert format_length(cm, U.METRIC, style) == expected


@pytest.mark.parametrize(("cm", "style", "expected"), IMPERIAL_CASES)
def test_imperial_output(cm, style, expected):
    assert format_length(cm, U.IMPERIAL, style) == expected


def test_default_system_is_metric():
    assert format_length(235.5) == "2.35 m" and format_area(500.0) == "500.0 cm²"


@pytest.mark.parametrize(
    ("cm2", "system", "expected"),
    [
        (500.0, U.METRIC, "500.0 cm²"),
        (9999.9, U.METRIC, "9999.9 cm²"),
        (10000.0, U.METRIC, "1.00 m²"),
        (23500.0, U.METRIC, "2.35 m²"),
        (929.0304, U.IMPERIAL, "1.00 ft²"),
        (64.516, U.IMPERIAL, "10.0 in²"),
        (92903.04, U.IMPERIAL, "100.00 ft²"),
    ],
)
def test_format_area(cm2, system, expected):
    assert format_area(cm2, system) == expected


@pytest.mark.parametrize(
    ("litres", "system", "expected"),
    [
        (12.0, U.METRIC, "12.0 L"),
        (0.946352946, U.IMPERIAL, "1.0 qt"),
        (3.785411784, U.IMPERIAL, "1.0 gal"),
        (18.92705892, U.IMPERIAL, "5.0 gal"),
    ],
)
def test_format_volume(litres, system, expected):
    assert format_volume(litres, system) == expected


def test_conversions_are_exact():
    assert inches_to_cm(12) == 30.48 and cm_to_inches(30.48) == 12.0


def test_module_imports_standard_library_only():  # AST scan, same pattern as tests/unit/test_sim_clock.py::test_module_is_qt_free
    tree = ast.parse(Path("src/open_garden_planner/core/units.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(("PyQt6", "open_garden_planner"))
        elif isinstance(node, ast.Import):
            assert not any(x.name.startswith(("PyQt6", "open_garden_planner")) for x in node.names)


@pytest.mark.parametrize(
    ("text", "system", "expected"),
    [
        ("12 in", U.IMPERIAL, 30.48),
        ('12"', U.IMPERIAL, 30.48),
        ("12", U.IMPERIAL, 30.48),
        ("8' 2 1/2\"", U.IMPERIAL, 250.19),
        ("8ft 2.5in", U.IMPERIAL, 250.19),
        ("8'2\"", U.IMPERIAL, 248.92),
        ('1/2"', U.IMPERIAL, 1.27),
        ("2 1/2", U.IMPERIAL, 6.35),
        ("-2' 6\"", U.IMPERIAL, -76.2),
        ("2,5 ft", U.IMPERIAL, 76.2),
        ("30 cm", U.IMPERIAL, 30.0),
        ("1.5m", U.IMPERIAL, 150.0),
        ("1200", U.METRIC, 1200.0),
        ("12 m", U.METRIC, 1200.0),
        ("12 in", U.METRIC, 30.48),
    ],
)
def test_parse_length(text, system, expected):
    assert parse_length(text, system) == pytest.approx(expected, abs=1e-9)


def test_parse_exact_inches():
    assert parse_length('12"', U.IMPERIAL) == 30.48  # exact, not approx


def test_bare_unit_override():
    assert parse_length("50", U.IMPERIAL, bare_unit_cm=30.48) == pytest.approx(1524.0)


@pytest.mark.parametrize(
    "text", ["", "  ", "abc", "1/0", "12 in 3 ft", "nan", "inf", "1e999", "5 furlongs", "''"]
)
def test_parse_rejects(text):
    with pytest.raises(ValueError):
        parse_length(text, U.IMPERIAL)


def test_round_trip_is_stable():
    cm = parse_length('12"', U.IMPERIAL)
    for _ in range(10):
        cm = parse_length(format_length(cm, U.IMPERIAL), U.IMPERIAL)
    assert cm == 30.48 and format_length(cm, U.IMPERIAL) == "1' 0\""


def test_negative_round_trip():
    assert parse_length(format_length(-77.47, U.IMPERIAL), U.IMPERIAL) == pytest.approx(-77.47)


@pytest.mark.parametrize(
    ("text", "system", "litres"),
    [
        ("2 gal", U.IMPERIAL, 7.570823568),
        ("3 qt", U.IMPERIAL, 2.839058838),
        ("5 L", U.IMPERIAL, 5.0),
        ("2", U.IMPERIAL, 7.570823568),
        ("2", U.METRIC, 2.0),
        ("500 ml", U.METRIC, 0.5),
    ],
)
def test_parse_volume(text, system, litres):
    assert parse_volume(text, system) == pytest.approx(litres)


@pytest.mark.parametrize(
    ("step_cm", "style", "inches"),
    [
        (10.0, S.AUTO, 4),
        (5.0, S.AUTO, 2),
        (1.0, S.AUTO, 0.5),
        (0.5, S.AUTO, 0.25),
        (100.0, S.AUTO, 12),
        (1.0, S.PLANT_SIZE, 1),
        (10.0, S.DEPTH, 0.125),
        (1.0, S.FEET, 12),
    ],
)
def test_imperial_step(step_cm, style, inches):
    assert imperial_step_inches(step_cm, style) == inches


def test_nice_distances():
    assert nice_distances(U.METRIC) == (
        1.0,
        2.0,
        5.0,
        10.0,
        20.0,
        50.0,
        100.0,
        200.0,
        500.0,
        1000.0,
        2000.0,
        5000.0,
        10000.0,
    )
    assert [format_length(d, U.IMPERIAL, S.SCALE_BAR) for d in nice_distances(U.IMPERIAL)] == [
        "1 in",
        "2 in",
        "3 in",
        "6 in",
        "1 ft",
        "2 ft",
        "5 ft",
        "10 ft",
        "25 ft",
        "50 ft",
        "100 ft",
        "250 ft",
        "500 ft",
    ]


def test_unit_dependent_constants():
    assert (grid_size_cm(U.METRIC), grid_size_cm(U.IMPERIAL)) == (50.0, 30.48)
    assert (nudge_fine_cm(U.METRIC), nudge_fine_cm(U.IMPERIAL)) == (1.0, 0.635)
    assert (default_bare_unit_cm(U.METRIC), default_bare_unit_cm(U.IMPERIAL)) == (1.0, 2.54)


@pytest.mark.parametrize("parser", [parse_length, parse_volume])
def test_overflowing_fraction_is_a_parse_error(parser):
    with pytest.raises(ValueError):
        parser("9" * 400 + "/1", U.IMPERIAL)
