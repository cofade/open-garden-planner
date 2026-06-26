"""Unit tests for the Qt-free smart-symbol model + generation (US-C4)."""

import pytest

from open_garden_planner.models.smart_symbol import (
    CircleSpec,
    LineSpec,
    PolygonSpec,
    RectSpec,
    SmartSymbolDefinition,
)


def _raised_bed() -> dict:
    return {
        "id": "raised_bed_rows",
        "version": 1,
        "name": "Raised Bed (rows)",
        "name_de": "Hochbeet (Reihen)",
        "category": "beds",
        "parameters": [
            {"name": "L", "type": "length", "label": "Length", "default": 200},
            {"name": "W", "type": "length", "label": "Width", "default": 100},
            {"name": "rows", "type": "number", "label": "Rows", "default": 4},
        ],
        "elements": [
            {"kind": "rect", "x": 0, "y": 0, "w": "L", "h": "W", "object_type": "RAISED_BED"},
            {
                "repeat": {"var": "i", "from": 1, "to": "rows - 1"},
                "element": {"kind": "line", "x1": 0, "y1": "W*i/rows", "x2": "L", "y2": "W*i/rows"},
            },
        ],
    }


class TestGenerate:
    def test_default_counts_and_values(self) -> None:
        d = SmartSymbolDefinition.from_dict(_raised_bed())
        specs = d.generate(d.param_defaults())
        assert len(specs) == 4  # 1 rect + 3 divider lines
        rects = [s for s in specs if isinstance(s, RectSpec)]
        lines = [s for s in specs if isinstance(s, LineSpec)]
        assert len(rects) == 1 and rects[0].w == 200 and rects[0].h == 100
        assert rects[0].object_type == "RAISED_BED"
        assert len(lines) == 3
        assert [round(line.y1, 1) for line in lines] == [25.0, 50.0, 75.0]

    def test_param_override_changes_repeat(self) -> None:
        d = SmartSymbolDefinition.from_dict(_raised_bed())
        specs = d.generate({"rows": 6})
        assert len([s for s in specs if isinstance(s, LineSpec)]) == 5

    def test_rows_one_yields_no_dividers(self) -> None:
        d = SmartSymbolDefinition.from_dict(_raised_bed())
        specs = d.generate({"rows": 1})
        assert len([s for s in specs if isinstance(s, LineSpec)]) == 0

    def test_polygon_and_circle_kinds(self) -> None:
        d = SmartSymbolDefinition.from_dict(
            {
                "id": "x", "version": 1, "name": "X", "category": "c",
                "parameters": [{"name": "r", "type": "length", "default": 10}],
                "elements": [
                    {"kind": "polygon", "points": [[0, 0], [10, 0], ["r", "r"]]},
                    {"kind": "circle", "cx": 0, "cy": 0, "r": "r"},
                ],
            }
        )
        specs = d.generate(d.param_defaults())
        poly = [s for s in specs if isinstance(s, PolygonSpec)][0]
        circ = [s for s in specs if isinstance(s, CircleSpec)][0]
        assert poly.points[2] == (10.0, 10.0)
        assert circ.r == 10.0

    def test_display_name_lang(self) -> None:
        d = SmartSymbolDefinition.from_dict(_raised_bed())
        assert d.display_name("de") == "Hochbeet (Reihen)"
        assert d.display_name("en") == "Raised Bed (rows)"


class TestValidation:
    def test_missing_id_raises(self) -> None:
        with pytest.raises(ValueError):
            SmartSymbolDefinition.from_dict({"version": 1, "elements": [{"kind": "rect"}]})

    def test_empty_elements_raises(self) -> None:
        with pytest.raises(ValueError):
            SmartSymbolDefinition.from_dict({"id": "x", "version": 1, "elements": []})

    def test_unknown_kind_raises_on_load(self) -> None:
        with pytest.raises(ValueError):
            SmartSymbolDefinition.from_dict(
                {"id": "x", "version": 1, "parameters": [],
                 "elements": [{"kind": "blob", "x": 0}]}
            )

    def test_bad_expression_raises_on_load(self) -> None:
        with pytest.raises(ValueError):
            SmartSymbolDefinition.from_dict(
                {"id": "x", "version": 1,
                 "parameters": [{"name": "L", "type": "length", "default": 1}],
                 "elements": [{"kind": "rect", "x": 0, "y": 0, "w": "L + missing", "h": 1}]}
            )

    def test_choice_param_requires_choices(self) -> None:
        with pytest.raises(ValueError):
            SmartSymbolDefinition.from_dict(
                {"id": "x", "version": 1,
                 "parameters": [{"name": "s", "type": "choice"}],
                 "elements": [{"kind": "rect", "x": 0, "y": 0, "w": 1, "h": 1}]}
            )

    def test_non_int_version_raises(self) -> None:
        with pytest.raises(ValueError):
            SmartSymbolDefinition.from_dict(
                {"id": "x", "version": "1",
                 "parameters": [], "elements": [{"kind": "rect", "x": 0, "y": 0, "w": 1, "h": 1}]}
            )


class TestUntrustedInputCaps:
    """User JSON is untrusted — runaway repeats / blowups must raise, not freeze."""

    def test_huge_repeat_rejected_at_load(self) -> None:
        with pytest.raises(ValueError):
            SmartSymbolDefinition.from_dict(
                {"id": "huge", "version": 1, "name": "H", "category": "c", "parameters": [],
                 "elements": [{"repeat": {"var": "i", "from": 0, "to": 100000},
                               "element": {"kind": "circle", "cx": "i", "cy": 0, "r": 1}}]}
            )

    def test_divide_by_zero_raises_arithmeticerror(self) -> None:
        d = SmartSymbolDefinition.from_dict(
            {"id": "dz", "version": 1, "name": "DZ", "category": "c",
             "parameters": [{"name": "n", "type": "number", "label": "N", "default": 2}],
             "elements": [{"kind": "line", "x1": 0, "y1": 0, "x2": "10 / n", "y2": 0}]}
        )
        with pytest.raises(ArithmeticError):
            d.generate({"n": 0})
