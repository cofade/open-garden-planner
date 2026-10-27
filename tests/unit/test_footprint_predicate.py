"""``footprints.item_has_footprint`` must answer exactly what ``item_outline`` says (#628).

The Properties panel asks "can this item carry a height?" of every selected item on
every rebuild, and the honest answer is ``item_outline(item) is not None`` — but building
a 16 000-vertex polygon's outline to answer yes/no cost 8.9 ms. The fast predicate is a
class check, so this test is the drift guard: for EVERY item the app can place, the two
must agree, including the one clause that is not a class check (an ellipse with no area
has no outline) and the ones that must stay without one (text, callouts, groups, arcs,
beziers, journal pins).
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QPointF, QRectF

from open_garden_planner.ui.canvas.footprints import item_has_footprint, item_outline
from open_garden_planner.ui.canvas.items.arc_item import ArcItem
from open_garden_planner.ui.canvas.items.bezier_item import BezierItem
from open_garden_planner.ui.canvas.items.callout_item import CalloutItem
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.text_item import TextItem

#: Every kind of thing the app can place. Constructed inside the test: a
#: QGraphicsItem needs the QApplication the qtbot fixture brings.
KINDS = (
    "rectangle", "circle", "ellipse", "polygon", "polyline",
    "text", "group", "callout", "arc", "bezier", "journal pin",
)


def _item(kind: str) -> Any:
    if kind == "rectangle":
        return RectangleItem(0.0, 0.0, 100.0, 60.0)
    if kind == "circle":
        return CircleItem(50.0, 50.0, 20.0)
    if kind == "ellipse":
        return EllipseItem(0.0, 0.0, 100.0, 60.0)
    if kind == "polygon":
        return PolygonItem([QPointF(0.0, 0.0), QPointF(50.0, 0.0), QPointF(25.0, 40.0)])
    if kind == "polyline":
        return PolylineItem([QPointF(0.0, 0.0), QPointF(50.0, 30.0)])
    if kind == "text":
        return TextItem(10.0, 10.0, "note")
    if kind == "group":
        return GroupItem()
    if kind == "callout":
        return CalloutItem(QPointF(100.0, 100.0), QPointF(30.0, 30.0), "note")
    if kind == "arc":
        return ArcItem(QPointF(300.0, 220.0), 80.0, 20.0, 120.0)
    if kind == "bezier":
        return BezierItem(
            [QPointF(600.0, 120.0), QPointF(700.0, 260.0)],
            [QPointF(570.0, 160.0), QPointF(650.0, 210.0)],
            [QPointF(630.0, 90.0), QPointF(730.0, 280.0)],
        )
    if kind == "journal pin":
        return JournalPinItem(20.0, 20.0, "note-id")
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", KINDS)
def test_the_predicate_agrees_with_the_outline(kind: str, qtbot) -> None:
    item = _item(kind)
    assert item_has_footprint(item) is (item_outline(item) is not None), kind


def test_an_ellipse_without_an_area_has_no_footprint(qtbot) -> None:
    """The one non-class clause: a zero-size ellipse builds no outline, so no height."""
    flat = EllipseItem(0.0, 0.0, 0.0, 60.0)
    assert flat.rect() == QRectF(0.0, 0.0, 0.0, 60.0)
    assert item_outline(flat) is None
    assert item_has_footprint(flat) is False
