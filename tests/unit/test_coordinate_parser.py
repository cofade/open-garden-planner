"""Unit tests for the coordinate input parser."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.coordinate_input.parser import (
    ParseError,
    parse,
    parse_alternative,
)


def _close(actual: QPointF, expected: QPointF, tol: float = 1e-6) -> bool:
    return abs(actual.x() - expected.x()) < tol and abs(actual.y() - expected.y()) < tol


class TestAbsoluteCartesian:
    def test_simple_pair(self) -> None:
        result = parse("200,300")
        assert result.kind == "absolute"
        assert _close(result.point, QPointF(200, -300))

    def test_whitespace_separator(self) -> None:
        result = parse("200 300")
        assert _close(result.point, QPointF(200, -300))

    def test_semicolon_separator(self) -> None:
        result = parse("200;300")
        assert _close(result.point, QPointF(200, -300))

    def test_dot_decimal_with_comma_separator(self) -> None:
        result = parse("200.5,300.25")
        assert _close(result.point, QPointF(200.5, -300.25))

    def test_locale_decimal_with_semicolon(self) -> None:
        result = parse("200,5;300,25")
        assert _close(result.point, QPointF(200.5, -300.25))

    def test_negative_values(self) -> None:
        result = parse("-150,-200")
        assert _close(result.point, QPointF(-150, 200))


class TestRelativeCartesian:
    def test_one_comma(self) -> None:
        last = QPointF(100, 100)
        result = parse("@500,0", last_point=last)
        assert result.kind == "relative"
        assert _close(result.point, QPointF(600, 100))
        assert result.raw_dx == 500
        assert result.raw_dy == 0

    def test_y_axis_flip(self) -> None:
        last = QPointF(0, 0)
        # User types dy=100 expecting "up"; scene Y goes down so we expect -100.
        result = parse("@0,100", last_point=last)
        assert _close(result.point, QPointF(0, -100))

    def test_dot_decimal(self) -> None:
        last = QPointF(0, 0)
        result = parse("@1.5,2.5", last_point=last)
        assert _close(result.point, QPointF(1.5, -2.5))

    def test_locale_decimal_with_semicolon(self) -> None:
        last = QPointF(0, 0)
        result = parse("@1,5;2,5", last_point=last)
        assert _close(result.point, QPointF(1.5, -2.5))

    def test_three_commas_locale(self) -> None:
        last = QPointF(0, 0)
        result = parse("@1,5,2,5", last_point=last)
        assert _close(result.point, QPointF(1.5, -2.5))

    def test_whitespace_separator(self) -> None:
        last = QPointF(10, 20)
        result = parse("@1,5 2,5", last_point=last)
        assert _close(result.point, QPointF(11.5, 17.5))

    def test_two_commas_prefers_locale(self) -> None:
        last = QPointF(0, 0)
        result = parse("@1,5,2", last_point=last)
        # 1.5, 2 -> point (1.5, -2)
        assert _close(result.point, QPointF(1.5, -2))

    def test_two_commas_alternative(self) -> None:
        last = QPointF(0, 0)
        alt = parse_alternative("@1,5,2", last_point=last)
        assert alt is not None
        # Alternative: dx=1, dy=5.2 -> point (1, -5.2)
        assert _close(alt.point, QPointF(1, -5.2))

    def test_relative_requires_last_point(self) -> None:
        with pytest.raises(ParseError, match="anchor"):
            parse("@1,2", last_point=None)


class TestPolar:
    def test_basic_polar(self) -> None:
        last = QPointF(0, 0)
        result = parse("@300<0", last_point=last)
        assert result.kind == "polar"
        assert _close(result.point, QPointF(300, 0))
        assert result.raw_distance == 300
        assert result.raw_angle_deg == 0

    def test_45_degrees(self) -> None:
        last = QPointF(0, 0)
        result = parse("@100<45", last_point=last)
        expected = QPointF(100 * math.cos(math.radians(45)), -100 * math.sin(math.radians(45)))
        assert _close(result.point, expected)

    def test_north_is_90(self) -> None:
        last = QPointF(0, 0)
        result = parse("@50<90", last_point=last)
        assert _close(result.point, QPointF(0, -50))

    def test_west_is_180(self) -> None:
        last = QPointF(10, 20)
        result = parse("@50<180", last_point=last)
        assert _close(result.point, QPointF(-40, 20))

    def test_negative_angle(self) -> None:
        last = QPointF(0, 0)
        result = parse("@100<-90", last_point=last)
        assert _close(result.point, QPointF(0, 100))

    def test_locale_decimal_in_polar(self) -> None:
        last = QPointF(0, 0)
        result = parse("@100<45,5", last_point=last)
        expected_rad = math.radians(45.5)
        assert _close(
            result.point,
            QPointF(100 * math.cos(expected_rad), -100 * math.sin(expected_rad)),
        )

    def test_polar_without_at_uses_last(self) -> None:
        last = QPointF(50, 0)
        result = parse("100<0", last_point=last)
        assert _close(result.point, QPointF(150, 0))

    def test_polar_two_angle_separators_invalid(self) -> None:
        with pytest.raises(ParseError):
            parse("@100<45<90", last_point=QPointF(0, 0))

    def test_polar_without_anchor_raises(self) -> None:
        """A silent fallback to origin would surprise the user; we raise instead."""
        with pytest.raises(ParseError, match="anchor"):
            parse("@100<45", last_point=None)
        with pytest.raises(ParseError, match="anchor"):
            parse("100<45", last_point=None)


class TestErrors:
    def test_empty(self) -> None:
        with pytest.raises(ParseError):
            parse("")

    def test_whitespace_only(self) -> None:
        with pytest.raises(ParseError):
            parse("   ")

    def test_lone_at(self) -> None:
        with pytest.raises(ParseError):
            parse("@", last_point=QPointF(0, 0))

    def test_single_value(self) -> None:
        with pytest.raises(ParseError):
            parse("100")

    def test_not_a_number(self) -> None:
        with pytest.raises(ParseError):
            parse("abc,123")

    def test_too_many_separators(self) -> None:
        with pytest.raises(ParseError):
            parse("1,2,3,4,5")

    def test_missing_polar_distance(self) -> None:
        with pytest.raises(ParseError):
            parse("@<90", last_point=QPointF(0, 0))

    def test_missing_polar_angle(self) -> None:
        with pytest.raises(ParseError):
            parse("@100<", last_point=QPointF(0, 0))


class TestAlternative:
    def test_unambiguous_returns_none(self) -> None:
        assert parse_alternative("@1,2", last_point=QPointF(0, 0)) is None
        assert parse_alternative("@1.5,2.5", last_point=QPointF(0, 0)) is None
        assert parse_alternative("@1,5;2,5", last_point=QPointF(0, 0)) is None
        assert parse_alternative("@1,5,2,5", last_point=QPointF(0, 0)) is None

    def test_polar_has_no_alternative(self) -> None:
        assert parse_alternative("@100<45", last_point=QPointF(0, 0)) is None
