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
from tests.large_plan import LARGE_PLAN_SIZE_CM, show_large_plan

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
    points on a label that is not painted. No point is on any label now.

    One shape query over the whole plan covers every point of it at once: Qt
    returns an item there only where the item's shape meets the area, through
    the same ``collidesWithPath`` that a point query uses for a label (an item
    that ignores the view's transform). Then a point query
    (``itemAt``) at the middle of every label that is not painted, where the
    review's third of the plan lay.

    Not point by point: a label ignores the view's transform, so Qt's index
    cannot place it, and every query walks all the objects and their labels in
    Python (5 to 6 ms each, #919). 4,335 sampled point queries took 33-76 s,
    and more than the 180 s hang guard under branch coverage (#918).
    """
    view, scene, items = show_large_plan(qtbot)
    painted = _painted(view, scene)
    labels = [item for item in scene.items() if isinstance(item, PlanLabelItem)]
    assert len(labels) == 853 and 0 < len(painted) < len(labels)

    plan = QRectF(0.0, 0.0, *LARGE_PLAN_SIZE_CM)
    found = scene.items(
        plan, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder,
        view.transform(),
    )
    found_ids = {id(item) for item in found}
    assert all(id(item) in found_ids for item in items), "the query must find the objects"
    takers = [item for item in found if isinstance(item, PlanLabelItem)]
    assert not takers, f"{len(takers)} labels take a click somewhere on the plan"

    hidden = [label for label in labels if id(label) not in painted]
    on_a_label = [
        label for label in hidden
        if isinstance(
            scene.itemAt(view.mapToScene(_label_box(view, label).center().toPoint()), view.transform()),
            PlanLabelItem,
        )
    ]
    assert not on_a_label, f"a press on {len(on_a_label)} of {len(hidden)} hidden labels hits the label"


def test_scene_query_on_large_plan_uses_bsp_index_not_full_walk(qtbot, monkeypatch) -> None:
    """§8.10.10 counting gate for #919: ``scene.itemAt`` uses Qt's BSP tree.

    With ``ItemIgnoresTransformations`` kept off C++ ``PlanLabelItem``, a
    point query on the 853-object plan calls ``CircleItem.boundingRect`` and
    ``PlanLabelItem.boundingRect`` only for local BSP candidates (<= 15 calls
    per query), instead of walking all 853 objects and labels on every move.
    """
    view, scene, _items = show_large_plan(qtbot)
    circle_calls = 0
    label_calls = 0
    real_circle_rect = CircleItem.boundingRect
    real_label_rect = PlanLabelItem.boundingRect

    def counted_circle_rect(self: CircleItem) -> QRectF:
        nonlocal circle_calls
        circle_calls += 1
        return real_circle_rect(self)

    def counted_label_rect(self: PlanLabelItem) -> QRectF:
        nonlocal label_calls
        label_calls += 1
        return real_label_rect(self)

    monkeypatch.setattr(CircleItem, "boundingRect", counted_circle_rect)
    monkeypatch.setattr(PlanLabelItem, "boundingRect", counted_label_rect)

    queries = 20
    view_tx = view.transform()
    for index in range(queries):
        pt = view.mapToScene(QPoint(200 + index * 50, 300 + (index % 5) * 40))
        scene.itemAt(pt, view_tx)

    assert circle_calls / queries <= 15, (
        f"scene.itemAt walked {circle_calls / queries:.1f} circles/query (expected <= 15)"
    )
    assert label_calls / queries <= 15, (
        f"scene.itemAt walked {label_calls / queries:.1f} labels/query (expected <= 15)"
    )


def test_plan_label_in_plain_scene_ignores_parent_and_view_transforms(qtbot) -> None:
    """In a plain ``QGraphicsScene`` (``paints_plan_labels`` False), a
    ``PlanLabelItem`` whose ``ItemIgnoresTransformations`` flag was set via
    ``setFlag`` or ``setFlags`` keeps its C++ flag clear for BSP indexing while
    still painting upright at constant pixel size under rotated parents and
    scaled views.
    """
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

    scene = QGraphicsScene(-500, -500, 1000, 1000)
    parent = QGraphicsRectItem(-50, -50, 100, 100)
    parent.setRotation(40.0)
    parent.setScale(2.0)
    scene.addItem(parent)

    label = PlanLabelItem("Lavender", parent)
    label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
    assert not (label.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    assert label._ignores_transformations

    label_flags = PlanLabelItem("Sage", parent)
    label_flags.setPos(0, 40)
    label_flags.setFlags(
        label_flags.flags() | QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    )
    assert not (label_flags.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    assert label_flags._ignores_transformations

    view = QGraphicsView(scene)
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.scale(0.35, -0.35)
    view.show()
    qtbot.waitExposed(view)

    # Device transform matches constant-screen-size upright mapping.
    dt = label.deviceTransform(view.viewportTransform())
    assert dt.m11() == pytest.approx(1.0)
    assert dt.m12() == pytest.approx(0.0)
    assert dt.m21() == pytest.approx(0.0)
    assert dt.m22() == pytest.approx(1.0)

    # Rendering through the plain-scene paint path paints pixels at the anchor.
    img = QImage(400, 300, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("white"))
    painter = QPainter(img)
    view.render(painter)
    painter.end()
    box = dt.mapRect(label.boundingRect()).toAlignedRect()
    ink = 0
    for y in range(max(0, box.top()), min(img.height(), box.bottom() + 1)):
        for x in range(max(0, box.left()), min(img.width(), box.right() + 1)):
            c = img.pixelColor(x, y)
            if c.red() + c.green() + c.blue() < 600:
                ink += 1
    assert ink > 10, "PlanLabelItem did not paint upright in a plain QGraphicsScene"
