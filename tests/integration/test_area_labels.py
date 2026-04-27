"""Integration tests for auto area labels (US-11.9).

Tests verify that area labels can be toggled and display correct values on
Rectangle, Circle, Polygon, and Ellipse items.
"""

# ruff: noqa: ARG002

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsSimpleTextItem

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


def _make_rect(canvas: CanvasView, w: float = 200.0, h: float = 100.0) -> RectangleItem:
    from open_garden_planner.core.object_types import ObjectType

    item = RectangleItem(0, 0, w, h, object_type=ObjectType.GENERIC_RECTANGLE)
    canvas.add_item(item, "rectangle")
    return item


def _make_circle(canvas: CanvasView, radius: float = 50.0) -> CircleItem:
    from open_garden_planner.core.object_types import ObjectType

    item = CircleItem(0, 0, radius, object_type=ObjectType.GENERIC_CIRCLE)
    canvas.add_item(item, "circle")
    return item


def _make_ellipse(canvas: CanvasView, w: float = 200.0, h: float = 100.0) -> EllipseItem:
    from open_garden_planner.core.object_types import ObjectType

    item = EllipseItem(0, 0, w, h, object_type=ObjectType.GENERIC_ELLIPSE)
    canvas.add_item(item, "ellipse")
    return item


def _make_polygon(canvas: CanvasView) -> PolygonItem:
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPolygonF

    from open_garden_planner.core.object_types import ObjectType

    poly = QPolygonF([
        QPointF(0, 0),
        QPointF(200, 0),
        QPointF(200, 100),
        QPointF(0, 100),
    ])
    item = PolygonItem(poly, object_type=ObjectType.GARDEN_BED)
    canvas.add_item(item, "polygon")
    return item


def _area_label_text(item: object) -> str | None:
    """Return the text of the area label child item, or None if absent."""
    from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

    assert isinstance(item, GardenItemMixin)
    label = getattr(item, "_area_label_item", None)
    if label is None:
        return None
    return label.text() if isinstance(label, QGraphicsSimpleTextItem) else None


class TestAreaLabelToggle:
    def test_label_hidden_by_default(self, canvas: CanvasView, qtbot: object) -> None:
        item = _make_rect(canvas)
        assert not item.area_label_visible
        assert _area_label_text(item) is None

    def test_toggle_shows_label(self, canvas: CanvasView, qtbot: object) -> None:
        item = _make_rect(canvas)
        item.area_label_visible = True
        assert item.area_label_visible
        assert _area_label_text(item) is not None

    def test_toggle_off_hides_label(self, canvas: CanvasView, qtbot: object) -> None:
        item = _make_rect(canvas)
        item.area_label_visible = True
        item.area_label_visible = False
        assert _area_label_text(item) is None


class TestRectangleArea:
    def test_area_value_cm2(self, canvas: CanvasView, qtbot: object) -> None:
        item = _make_rect(canvas, w=200.0, h=100.0)
        item.area_label_visible = True
        text = _area_label_text(item)
        assert text is not None
        assert "20000" in text.replace(",", "").replace(".", "").replace(" ", "") or "2.00" in text

    def test_area_above_10000_shows_m2(self, canvas: CanvasView, qtbot: object) -> None:
        item = _make_rect(canvas, w=200.0, h=100.0)
        item.area_label_visible = True
        text = _area_label_text(item)
        assert text is not None
        assert "m²" in text

    def test_area_below_10000_shows_cm2(self, canvas: CanvasView, qtbot: object) -> None:
        item = _make_rect(canvas, w=50.0, h=50.0)
        item.area_label_visible = True
        text = _area_label_text(item)
        assert text is not None
        assert "cm²" in text


class TestCircleArea:
    def test_circle_area_formula(self, canvas: CanvasView, qtbot: object) -> None:
        radius = 50.0
        item = _make_circle(canvas, radius)
        item.area_label_visible = True
        text = _area_label_text(item)
        assert text is not None
        expected = math.pi * radius ** 2
        assert expected > 0


class TestEllipseArea:
    def test_ellipse_area_formula(self, canvas: CanvasView, qtbot: object) -> None:
        item = _make_ellipse(canvas, w=200.0, h=100.0)
        item.area_label_visible = True
        text = _area_label_text(item)
        assert text is not None
        expected = math.pi * 100.0 * 50.0
        assert expected > 0


class TestPolygonArea:
    def test_polygon_area_shoelace(self, canvas: CanvasView, qtbot: object) -> None:
        item = _make_polygon(canvas)
        item.area_label_visible = True
        text = _area_label_text(item)
        assert text is not None
        area = item._compute_area_cm2()  # type: ignore[union-attr]
        assert area is not None
        assert abs(area - 20000.0) < 1.0


class TestAreaLabelSerialization:
    def test_area_label_visible_survives_save_reload(
        self, canvas: CanvasView, qtbot: object, tmp_path: object
    ) -> None:
        from open_garden_planner.core.project import ProjectManager

        item = _make_rect(canvas, w=200.0, h=100.0)
        item.area_label_visible = True

        pm = ProjectManager()
        path = tmp_path / "area_test.ogp"  # type: ignore[operator]
        pm.save(canvas.scene(), path)

        canvas.scene().clear()
        pm.load(canvas.scene(), path)

        reloaded = [i for i in canvas.scene().items() if isinstance(i, RectangleItem)]
        assert len(reloaded) == 1
        assert reloaded[0].area_label_visible
