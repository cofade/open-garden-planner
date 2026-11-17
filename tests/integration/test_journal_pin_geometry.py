"""Measured device-space picking contract for the journal pin (#923)."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem


@pytest.mark.parametrize("scale", [1.0, 0.3, -0.3, 3.7, -3.7])
def test_item_at_finds_the_actual_device_sized_pin_head(qtbot, scale):
    scene = QGraphicsScene()
    pin = JournalPinItem(200, 200, "note")
    scene.addItem(pin)
    world = QTransform.fromScale(abs(scale), scale)
    world.translate(47, -93)
    device = pin.deviceTransform(world)
    point = world.inverted()[0].map(device.map(QPointF(0, -15)))
    assert pin.shape().contains(QPointF(0, -15))
    assert scene.itemAt(point, world) is pin
    if scale < 0 or scale > 1.0:
        # This is the old probe's contradictory result: an unscaled query
        # finds the pin at a point which is not its visible head under zoom/Y-flip.
        wrong = pin.mapToScene(QPointF(0, -15))
        assert pin in scene.items(wrong)
        assert scene.itemAt(wrong, world) is None


@pytest.mark.parametrize("zoom", [0.3, 1.0, 3.7])
def test_canvas_pin_query_agrees_with_the_visible_head(qtbot, zoom):
    scene = CanvasScene(2000, 1500)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1000, 800)
    view.show()
    qtbot.waitExposed(view)
    view.set_zoom(zoom)
    pin = JournalPinItem(500, 600, "note")
    scene.addItem(pin)
    view.centerOn(pin)
    world = view.viewportTransform()
    head = pin.deviceTransform(world).map(QPointF(0, -15))
    point = world.inverted()[0].map(head)
    assert scene.itemAt(point, world) is pin
    assert view._journal_pin_at(point) is pin
