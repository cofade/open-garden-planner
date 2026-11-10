"""A label of the plan takes no click (review of #793, P1-1).

An object's name, its area, a bed's succession badge and the hours on the sun
map are painted by the scene after every item, and only where they have room
(``ui.canvas.plan_labels``). The items behind them stayed hit-testable with
their full rectangle, painted or not: on a plan of 853 named plants at fit a
third of the canvas was the rectangle of a label nobody could see, and a press
there neither selected anything nor started a box selection.

A label is writing on the plan, not a body: what lies under it takes the
click. These tests drive the real ``CanvasView`` with real mouse events.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem
from open_garden_planner.ui.canvas.items.garden_item import SuccessionBadgeItem
from open_garden_planner.ui.canvas.items.halo_text import PlanLabelItem
from open_garden_planner.ui.canvas.sun_heatmap import SunMapLabelItem
from tests.large_plan import show_large_plan

LEFT = Qt.MouseButton.LeftButton
NO_MODIFIER = Qt.KeyboardModifier.NoModifier


@pytest.fixture()
def canvas(qtbot):
    scene = CanvasScene(5000, 3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1000, 700)
    view.show()
    qtbot.waitExposed(view)
    view.set_snap_enabled(False)
    view.fit_in_view()
    QApplication.processEvents()
    return view, scene


def _settle(view: CanvasView) -> None:
    QApplication.processEvents()
    view.viewport().repaint()
    QApplication.processEvents()


def _label_box(view: CanvasView, label) -> QRectF:
    """Where ``label`` lies on the viewport (painted or not)."""
    world = view.viewportTransform()
    return label.deviceTransform(world).mapRect(label.boundingRect())


def _painted(view: CanvasView, scene: CanvasScene) -> set[int]:
    return {id(label) for label, _device, _box in scene.plan_labels_shown(view.viewportTransform())}


def _drag(view: CanvasView, start: QPoint, end: QPoint) -> None:
    viewport = view.viewport()
    QTest.mousePress(viewport, LEFT, NO_MODIFIER, start)
    QTest.mouseMove(viewport, QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2))
    QTest.mouseMove(viewport, end)
    QTest.mouseRelease(viewport, LEFT, NO_MODIFIER, end)
    QApplication.processEvents()


def test_a_press_on_a_left_out_label_starts_a_box_selection(canvas) -> None:
    """A plant too small on screen for its name: the name is not painted, and
    a press where it would lie is a press on the bare plan."""
    view, scene = canvas
    plant = CircleItem(2500, 1500, 20, object_type=ObjectType.PERENNIAL, name="Lavender 'Hidcote'")
    scene.addItem(plant)
    plant.initialize_label()
    _settle(view)
    label = plant._label_item
    assert id(label) not in _painted(view, scene), "the label is painted: the test needs it left out"
    box = _label_box(view, label)
    body = plant.deviceTransform(view.viewportTransform()).mapRect(plant.rect())
    start = QPoint(int(box.left()) + 4, int(box.top()) + 2)
    assert not body.contains(QPointF(start)) and box.contains(QPointF(start))

    # Left to right around the plant: an enclosing box selects it.
    _drag(view, start, QPoint(int(body.right()) + 12, int(body.bottom()) + 12))
    assert plant.isSelected()


def test_a_press_on_a_painted_label_beside_its_object_starts_a_box_selection(canvas) -> None:
    """The name of a slim bed reaches past the bed. That part of a painted
    label lay over bare plan and swallowed the press as well."""
    view, scene = canvas
    bed = RectangleItem(2450, 1200, 100, 600, object_type=ObjectType.RAISED_BED,
                        name="Raised bed by the south fence")
    scene.addItem(bed)
    bed.initialize_label()
    _settle(view)
    label = bed._label_item
    assert id(label) in _painted(view, scene)
    box = _label_box(view, label)
    body = bed.deviceTransform(view.viewportTransform()).mapRect(bed.rect())
    start = QPoint(int(box.right()) - 3, int(box.center().y()))
    assert not body.contains(QPointF(start)), "the label does not reach past the bed"

    # Right to left into the bed: a crossing box selects it.
    _drag(view, start, QPoint(int(body.center().x()), int(body.center().y()) + 20))
    assert bed.isSelected()


def test_a_press_on_a_painted_label_over_its_object_selects_the_object(canvas) -> None:
    """As before: a label over its object's body lets the object take the click."""
    view, scene = canvas
    bed = RectangleItem(2000, 1000, 1000, 800, object_type=ObjectType.RAISED_BED, name="Herbs")
    scene.addItem(bed)
    bed.initialize_label()
    _settle(view)
    label = bed._label_item
    assert id(label) in _painted(view, scene)
    centre = _label_box(view, label).center().toPoint()

    QTest.mouseClick(view.viewport(), LEFT, NO_MODIFIER, centre)
    QApplication.processEvents()
    assert bed.isSelected()


def test_what_qt_delivers_at_a_label_is_its_object(canvas) -> None:
    """A double click, a context menu and a tooltip go to the topmost item Qt
    finds under the cursor. Over a label that is the object, never the label."""
    view, scene = canvas
    bed = RectangleItem(2000, 1000, 1000, 800, object_type=ObjectType.RAISED_BED, name="Herbs")
    scene.addItem(bed)
    bed.initialize_label()
    bed.area_label_visible = True
    _settle(view)
    for label in (bed._label_item, bed._area_label_item):
        assert label is not None and id(label) in _painted(view, scene)
        under = view.items(_label_box(view, label).center().toPoint())
        assert under and under[0] is bed
        assert not any(isinstance(item, PlanLabelItem) for item in under)


def test_a_double_click_on_a_label_edits_the_name(canvas) -> None:
    view, scene = canvas
    bed = RectangleItem(2000, 1000, 1000, 800, object_type=ObjectType.RAISED_BED, name="Herbs")
    scene.addItem(bed)
    bed.initialize_label()
    _settle(view)
    centre = _label_box(view, bed._label_item).center().toPoint()

    QTest.mouseDClick(view.viewport(), LEFT, NO_MODIFIER, centre)
    QApplication.processEvents()
    editor = bed._edit_label_item
    assert editor is not None and editor.isVisible()


def test_a_press_on_an_hour_of_the_sun_map_starts_a_box_selection(canvas) -> None:
    """The hours on the map's contours are labels of no object: nothing lies
    under them but the plan."""
    view, scene = canvas
    hour = SunMapLabelItem("6 h")
    hour.setPos(1000.0, 1700.0)                    # up and to the left of the plant
    scene.addItem(hour)
    plant = CircleItem(1300, 1500, 60, object_type=ObjectType.PERENNIAL)
    scene.addItem(plant)
    _settle(view)
    assert id(hour) in _painted(view, scene)
    start = _label_box(view, hour).center().toPoint()
    body = plant.deviceTransform(view.viewportTransform()).mapRect(plant.rect())

    _drag(view, start + QPoint(0, -30), QPoint(int(body.right()) + 12, int(body.bottom()) + 12))
    assert plant.isSelected(), "the box does not select: the test's own drag is wrong"
    scene.clearSelection()
    _drag(view, start, QPoint(int(body.right()) + 12, int(body.bottom()) + 12))
    assert plant.isSelected()


def test_a_press_on_a_left_out_succession_badge_starts_a_box_selection(canvas) -> None:
    """A bed too small on screen for its badge: the badge is not painted and
    reaches past the bed."""
    view, scene = canvas
    bed = RectangleItem(2500, 1500, 60, 40, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    bed.set_succession_indicator([("Radish", True), ("Winter purslane", False)])
    _settle(view)
    badge = bed._succession_badge_item
    assert isinstance(badge, SuccessionBadgeItem) and badge.isVisible()
    world = view.viewportTransform()
    assert not scene_shows_badge(scene, world, badge), "the badge is painted: the test needs it left out"
    box = badge.deviceTransform(world).mapRect(badge.boundingRect())
    body = bed.deviceTransform(world).mapRect(bed.rect())
    start = QPoint(int(box.right()) - 3, int(box.top()) + 3)
    assert not body.contains(QPointF(start)) and box.contains(QPointF(start))

    # Right to left across the bed: a crossing box selects it.
    _drag(view, start, QPoint(int(body.left()) + 2, int(body.bottom()) - 2))
    assert bed.isSelected()


def scene_shows_badge(scene: CanvasScene, world, badge: SuccessionBadgeItem) -> bool:
    from open_garden_planner.ui.canvas.plan_labels import succession_badges_shown

    return any(item is badge for item, _device, _box in succession_badges_shown(scene, world))


def test_no_point_of_a_large_plan_is_a_label_nobody_can_see(qtbot) -> None:
    """The review's measurement: 853 named plants at fit, 35 % of the plan's
    points on a label that is not painted. No point is on any label now."""
    view, scene, _items = show_large_plan(qtbot)
    painted = _painted(view, scene)
    labels = [item for item in scene.items() if isinstance(item, PlanLabelItem)]
    assert len(labels) == 853 and 0 < len(painted) < len(labels)

    top_left = view.mapFromScene(QPointF(0.0, 3000.0))
    bottom_right = view.mapFromScene(QPointF(5000.0, 0.0))
    on_a_label = sampled = 0
    for x in range(top_left.x() + 3, bottom_right.x() - 3, 17):
        for y in range(top_left.y() + 3, bottom_right.y() - 3, 17):
            sampled += 1
            hit = scene.itemAt(view.mapToScene(QPoint(x, y)), view.transform())
            on_a_label += isinstance(hit, PlanLabelItem)
    assert sampled > 3000
    assert on_a_label == 0, f"{on_a_label} of {sampled} sampled points are on a label"
