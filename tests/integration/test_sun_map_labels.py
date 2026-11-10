"""The hours on the sun map's contours are in the open (#794).

They were scene items under every plant and object (z -448), each drawn twice
for a halo of its own: on the family-garden example 40 of the 64 were cut by
something standing on them, and the worst of the visible ones read at 3.2:1.
They are object labels now in every respect but their owner
(``sun_heatmap.SunMapLabelItem``): the one halo, painted after every item, and
left out where two labels would touch (§8.9.15). And they are placed where
their contour is in the open — off plants and objects, off the plan's edge.

Measured on pixels of a real map computed by the real worker. Nothing here
uses an API the change introduced, so every test states behaviour: it was
observed failing on the code before the change.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRect, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QGraphicsItem, QGraphicsSimpleTextItem

from open_garden_planner.core.legibility import MIN_TEXT_CONTRAST
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene, on_ground
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)
from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController
from tests.integration.test_canvas_legibility import _grab, _label_contrast

BERLIN = {"latitude": 52.52, "longitude": 13.405}
SUMMER = date(2026, 6, 21)

#: What stands on the ground: the drawn bodies that are no ground surface.
BODIES = (RectangleItem, CircleItem, EllipseItem, PolygonItem, PolylineItem)


def garden() -> CanvasScene:
    """A plan with a house, a tree, a row of shrubs and an open fence."""
    scene = CanvasScene(2400.0, 1600.0)
    scene.set_shadows_enabled(False)
    house = RectangleItem(300, 900, 800, 500, object_type=ObjectType.GENERIC_RECTANGLE)
    house.metadata[METADATA_KEY] = 600.0
    scene.addItem(house)
    tree = CircleItem(1500.0, 700.0, 220.0, object_type=ObjectType.TREE)
    tree.metadata[METADATA_KEY] = 700.0
    scene.addItem(tree)
    for index in range(6):
        shrub = CircleItem(500.0 + 190.0 * index, 400.0, 70.0, object_type=ObjectType.SHRUB)
        shrub.metadata[METADATA_KEY] = 150.0
        scene.addItem(shrub)
    fence = PolylineItem(
        [QPointF(120, 1480), QPointF(120, 120), QPointF(2280, 120), QPointF(2280, 1480)],
        object_type=ObjectType.FENCE,
    )
    fence.metadata[METADATA_KEY] = 150.0
    scene.addItem(fence)
    return scene


def hour_labels(controller: SunHeatmapController) -> list[QGraphicsSimpleTextItem]:
    """The hour labels of the map, each once (whatever a label is made of)."""
    seen: dict[tuple[float, float], QGraphicsSimpleTextItem] = {}
    for item in controller._contour_items:
        if isinstance(item, QGraphicsSimpleTextItem):
            key = (round(item.pos().x(), 3), round(item.pos().y(), 3))
            if key not in seen or item.zValue() > seen[key].zValue():
                seen[key] = item
    return list(seen.values())


def pixels(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :3].astype(np.int16).copy()


def export(scene: CanvasScene, width: int = 1200, text_point_size: int | None = 12) -> QImage:
    image = QImage(width, round(width * scene.height_cm / scene.width_cm), QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    render_scene_region(
        scene, painter, QRectF(image.rect()), scene.canvas_rect, text_point_size=text_point_size
    )
    painter.end()
    return image


def _bodies(scene: CanvasScene) -> list[QGraphicsItem]:
    return [item for item in scene.items() if isinstance(item, BODIES) and not on_ground(item)]


def _label_box(view: CanvasView, label: QGraphicsSimpleTextItem) -> QRect:
    world = view.viewportTransform()
    return label.deviceTransform(world).mapRect(label.boundingRect()).toAlignedRect()


@pytest.fixture
def mapped(qtbot):
    """The garden in a view at fit, with a finished map."""
    scene = garden()
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1150, 820)
    view.show()
    qtbot.waitExposed(view)
    view.fit_in_view()
    controller = SunHeatmapController(scene, lambda: BERLIN)
    with qtbot.waitSignal(controller.finished, timeout=120000) as blocker:
        assert controller.run_for_day(SUMMER)
    assert blocker.args == [True]
    QApplication.processEvents()
    yield view, scene, controller
    controller.shutdown()


def test_the_hour_labels_are_painted_above_plants_and_objects(mapped) -> None:
    """Each label's ink is there with every object standing as without them."""
    view, scene, controller = mapped
    labels = hour_labels(controller)
    assert len(labels) >= 6
    with_objects = pixels(_grab(view))
    for item in _bodies(scene):
        item.setOpacity(0.0)
    bare = pixels(_grab(view))
    for item in _bodies(scene):
        item.setOpacity(1.0)
    frame = QRect(0, 0, bare.shape[1], bare.shape[0])
    measured = 0
    for label in labels:
        box = _label_box(view, label).intersected(frame)
        ink_bare = bare[box.top(): box.bottom(), box.left(): box.right()].sum(axis=2) < 200
        if ink_bare.sum() < 12:
            continue                        # left out by the label pass: nothing to cover
        ink_now = with_objects[box.top(): box.bottom(), box.left(): box.right()].sum(axis=2) < 200
        assert (ink_now & ink_bare).sum() >= 0.97 * ink_bare.sum(), label.text()
        measured += 1
    assert measured >= 6


def test_the_hour_labels_read_on_the_map(mapped) -> None:
    view, _scene, controller = mapped
    with_labels = _grab(view)
    labels = hour_labels(controller)
    for item in controller._contour_items:
        if isinstance(item, QGraphicsSimpleTextItem):
            item.setVisible(False)
    without = _grab(view)
    ratios = []
    for label in labels:
        box = _label_box(view, label).adjusted(-2, -2, 2, 2)
        ratio = _label_contrast(with_labels, without, QColor(18, 22, 42), box)
        if ratio > 1.0:                     # a label that was painted
            ratios.append(ratio)
    assert len(ratios) >= 6
    assert min(ratios) >= MIN_TEXT_CONTRAST, min(ratios)


def test_no_hour_label_stands_on_a_plant_or_an_object(mapped) -> None:
    """At the zoom a plan is looked at as a whole (it fits the window), a label
    covers no object: it stands where its contour is in the open."""
    view, scene, controller = mapped
    labels = hour_labels(controller)
    assert len(labels) >= 6
    for label in labels:
        box = _label_box(view, label).adjusted(4, 4, -4, -4)      # the glyphs, not the halo's margin
        area = view.mapToScene(box).boundingRect()
        for item in scene.items(area):
            if isinstance(item, BODIES) and not on_ground(item):
                assert not item.mapToScene(item.grid_cover_path()).intersects(area), (
                    label.text(), item.object_type)


def test_no_hour_label_hangs_over_the_plans_edge(mapped) -> None:
    view, scene, controller = mapped
    plan = view.viewportTransform().mapRect(scene.canvas_rect)
    labels = hour_labels(controller)
    assert len(labels) >= 6
    for label in labels:
        assert plan.contains(QRectF(_label_box(view, label))), label.text()


def test_an_open_fence_covers_its_line_not_the_ground_it_encloses(mapped) -> None:
    """The fence runs round three sides of the garden. Its ``shape()`` is its
    stroke united with the path FILLED — the whole garden; what it covers is
    its stroke. Otherwise no label finds a free place, and the canvas grid is
    cut out of everything the fence encloses."""
    view, scene, controller = mapped
    (fence,) = [item for item in scene.items() if isinstance(item, PolylineItem)]
    middle = QPointF(1200.0, 800.0)
    assert fence.shape().contains(fence.mapFromScene(middle)), "this test needs Qt's filled shape"
    assert not fence.grid_cover_path().contains(fence.mapFromScene(middle))
    assert fence.grid_cover_path().contains(fence.mapFromScene(QPointF(120.0, 800.0)))

    # the grid lies on the open ground inside the fence
    for item in controller._contour_items:
        item.setVisible(False)              # the map's lines are not the grid's
    view.set_grid_visible(True)
    QApplication.processEvents()
    with_grid = pixels(_grab(view))
    view.set_grid_visible(False)
    QApplication.processEvents()
    without = pixels(_grab(view))
    centre = view.mapFromScene(QPointF(1880.0, 400.0))
    patch = (slice(centre.y() - 60, centre.y() + 60), slice(centre.x() - 60, centre.x() + 60))
    assert (np.abs(with_grid[patch] - without[patch]).sum(axis=2) > 6).sum() > 100


def test_hour_labels_do_not_touch_each_other_or_an_objects_name(mapped) -> None:
    """They are in the plan's label pass (§8.9.15): zoomed out, the ones with no
    room are left out, and an object's own name wins over an hour."""
    view, scene, controller = mapped
    house = next(item for item in scene.items() if isinstance(item, RectangleItem))
    house.name = "House"
    hours = {id(label) for label in hour_labels(controller)}
    for zoom in (0.12, 0.25, view.zoom_factor):
        view.set_zoom(zoom)
        view.centerOn(QPointF(1200.0, 800.0))
        QApplication.processEvents()
        shown = scene.plan_labels_shown(view.viewportTransform())
        boxes = [box for _label, _device, box in shown]
        for index, first in enumerate(boxes):
            for second in boxes[index + 1:]:
                assert not first.intersects(second), zoom
        assert "House" in [label.text() for label, _device, _box in shown]
        assert any(id(label) in hours for label, _device, _box in shown), zoom
    # zoomed far out fewer hours are shown than the map has
    view.set_zoom(0.12)
    QApplication.processEvents()
    far = [label for label, *_ in scene.plan_labels_shown(view.viewportTransform()) if id(label) in hours]
    assert 0 < len(far) < len(hours)


def test_the_hour_labels_go_into_a_picture_of_the_plan(mapped) -> None:
    _view, scene, controller = mapped
    with_labels = export(scene)
    for item in controller._contour_items:
        if isinstance(item, QGraphicsSimpleTextItem):
            item.setVisible(False)
    without = export(scene)
    changed = np.abs(pixels(with_labels) - pixels(without)).sum(axis=2) > 90
    assert changed.sum() > 300
    # a picture's labels have one halo and are not cut by an object either
    for item in _bodies(scene):
        item.setOpacity(0.0)
    for item in controller._contour_items:
        item.setVisible(True)
    bare = pixels(export(scene))
    ink_bare = (bare.sum(axis=2) < 200) & changed
    ink_now = (pixels(with_labels).sum(axis=2) < 200) & changed
    assert (ink_now & ink_bare).sum() >= 0.97 * ink_bare.sum()
