"""Unit tests for the one look-copy rule (issues #470/#441).

`copy_visual_style` is duck-typed over shape items: it must copy the serialized
appearance attributes and the live pen/brush for a `GardenItemMixin` item, and
must not raise for an item that has none of them.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import QGraphicsRectItem

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.item_look import copy_visual_style
from open_garden_planner.core.object_types import ObjectType, StrokeStyle
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


def _styled_rectangle() -> RectangleItem:
    item = RectangleItem(0, 0, 100, 80, object_type=ObjectType.GARDEN_BED)
    item.fill_pattern = FillPattern.SOIL
    item.fill_color = QColor("#3366cc")
    item.stroke_color = QColor("#cc2222")
    item.stroke_width = 3.5
    item.stroke_style = StrokeStyle.DASHED
    item._setup_styling()
    return item


def test_copies_serialized_and_live_look(qtbot: object) -> None:  # noqa: ARG001
    source = _styled_rectangle()
    dest = RectangleItem(0, 0, 50, 40, object_type=ObjectType.GARDEN_BED)

    copy_visual_style(source, dest)

    assert dest.fill_pattern == source.fill_pattern
    assert dest.fill_color == source.fill_color
    assert dest.stroke_color == source.stroke_color
    assert dest.stroke_width == source.stroke_width
    assert dest.stroke_style == source.stroke_style
    assert dest.pen().color() == source.pen().color()
    assert dest.pen().widthF() == source.pen().widthF()
    assert dest.pen().style() == source.pen().style()


def test_copies_the_area_label_flag_when_set(qtbot: object) -> None:  # noqa: ARG001
    source = _styled_rectangle()
    source.area_label_visible = True
    dest = RectangleItem(0, 0, 50, 40, object_type=ObjectType.GARDEN_BED)
    assert dest.area_label_visible is False

    copy_visual_style(source, dest)

    assert dest.area_label_visible is True


def test_copies_between_different_shape_classes(qtbot: object) -> None:  # noqa: ARG001
    source = _styled_rectangle()
    dest = PolygonItem(
        vertices=[QPointF(0, 0), QPointF(10, 0), QPointF(10, 10)],
        object_type=ObjectType.LAWN,
    )

    copy_visual_style(source, dest)

    assert dest.fill_pattern == source.fill_pattern
    assert dest.pen().color() == source.pen().color()


def test_tolerates_plain_graphics_items(qtbot: object) -> None:  # noqa: ARG001
    """A plain QGraphicsItem has no look attributes; the helper must not raise."""
    source = QGraphicsRectItem(0, 0, 10, 10)
    source.setPen(QPen(QColor("#123456"), 2.0))
    source.setBrush(QBrush(QColor("#abcdef")))
    dest = QGraphicsRectItem(0, 0, 5, 5)

    copy_visual_style(source, dest)

    assert dest.pen().color() == source.pen().color()
    assert dest.brush().color() == source.brush().color()
