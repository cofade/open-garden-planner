"""Tests for stroke style functionality."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from open_garden_planner.core.object_types import ObjectType, StrokeStyle, get_style
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem


class TestStrokeStyle:
    """Test the StrokeStyle enum."""

    def test_stroke_style_exists(self):
        """Test that StrokeStyle enum has expected values."""
        assert hasattr(StrokeStyle, "SOLID")
        assert hasattr(StrokeStyle, "DASHED")
        assert hasattr(StrokeStyle, "DOTTED")
        assert hasattr(StrokeStyle, "DASH_DOT")

    def test_to_qt_pen_style(self):
        """Test conversion to Qt pen style."""
        assert StrokeStyle.SOLID.to_qt_pen_style() == Qt.PenStyle.SolidLine
        assert StrokeStyle.DASHED.to_qt_pen_style() == Qt.PenStyle.DashLine
        assert StrokeStyle.DOTTED.to_qt_pen_style() == Qt.PenStyle.DotLine
        assert StrokeStyle.DASH_DOT.to_qt_pen_style() == Qt.PenStyle.DashDotLine


class TestObjectStyleWithStroke:
    """Test ObjectStyle includes stroke style."""

    def test_object_style_has_stroke_style(self):
        """Test that ObjectStyle has stroke_style field."""
        style = get_style(ObjectType.HOUSE)
        assert hasattr(style, "stroke_style")
        assert isinstance(style.stroke_style, StrokeStyle)

    def test_default_stroke_style_is_solid(self):
        """Test that default stroke style is SOLID."""
        for obj_type in ObjectType:
            style = get_style(obj_type)
            assert style.stroke_style == StrokeStyle.SOLID


class TestRectangleItemStroke:
    """Test RectangleItem stroke customization."""

    def test_default_stroke_style(self, qtbot):  # noqa: ARG002
        """Test rectangle has default solid stroke."""
        item = RectangleItem(0, 0, 100, 100)
        assert item.stroke_style == StrokeStyle.SOLID
        assert item.pen().style() == Qt.PenStyle.SolidLine

    def test_custom_stroke_style(self, qtbot):  # noqa: ARG002
        """Test rectangle can have custom stroke style."""
        item = RectangleItem(0, 0, 100, 100, stroke_style=StrokeStyle.DASHED)
        assert item.stroke_style == StrokeStyle.DASHED
        assert item.pen().style() == Qt.PenStyle.DashLine

    def test_stroke_color_customization(self, qtbot):  # noqa: ARG002
        """Test rectangle stroke color can be customized."""
        item = RectangleItem(0, 0, 100, 100)
        red = QColor(255, 0, 0)
        item.stroke_color = red
        item._setup_styling()  # Re-apply styling
        assert item.pen().color() == red

    def test_stroke_width_customization(self, qtbot):  # noqa: ARG002
        """Test rectangle stroke width can be customized."""
        item = RectangleItem(0, 0, 100, 100)
        item.stroke_width = 5.0
        item._setup_styling()  # Re-apply styling
        assert item.pen().widthF() == 5.0


class TestPolygonItemStroke:
    """Test PolygonItem stroke customization."""

    def test_default_stroke_style(self, qtbot):  # noqa: ARG002
        """Test polygon has default solid stroke."""
        from PyQt6.QtCore import QPointF

        points = [QPointF(0, 0), QPointF(100, 0), QPointF(50, 100)]
        item = PolygonItem(points)
        assert item.stroke_style == StrokeStyle.SOLID
        assert item.pen().style() == Qt.PenStyle.SolidLine

    def test_custom_stroke_style(self, qtbot):  # noqa: ARG002
        """Test polygon can have custom stroke style."""
        from PyQt6.QtCore import QPointF

        points = [QPointF(0, 0), QPointF(100, 0), QPointF(50, 100)]
        item = PolygonItem(points, stroke_style=StrokeStyle.DOTTED)
        assert item.stroke_style == StrokeStyle.DOTTED
        assert item.pen().style() == Qt.PenStyle.DotLine


class TestCircleItemStroke:
    """Test CircleItem stroke customization."""

    def test_default_stroke_style(self, qtbot):  # noqa: ARG002
        """Test circle has default solid stroke."""
        item = CircleItem(50, 50, 25)
        assert item.stroke_style == StrokeStyle.SOLID
        assert item.pen().style() == Qt.PenStyle.SolidLine

    def test_custom_stroke_style(self, qtbot):  # noqa: ARG002
        """Test circle can have custom stroke style."""
        item = CircleItem(50, 50, 25, stroke_style=StrokeStyle.DASH_DOT)
        assert item.stroke_style == StrokeStyle.DASH_DOT
        assert item.pen().style() == Qt.PenStyle.DashDotLine
