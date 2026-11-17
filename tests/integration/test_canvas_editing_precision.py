"""Geometry and screen-space regressions for #840, #841 and #853."""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtTest import QTest

from open_garden_planner.core.alignment import AlignMode, align_items
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.snapping import ObjectSnapper
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem
from open_garden_planner.ui.canvas.items.resize_handle import HandlePosition


@pytest.fixture()
def shown_canvas(qtbot):
    scene = CanvasScene(3000, 2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    qtbot.waitExposed(view)
    view.set_snap_enabled(False)
    return view, scene


def _plant(scene, x=600):
    plant = CircleItem(x, 600, 50, object_type=ObjectType.TREE)
    plant.metadata["plant_species"] = {"max_spread_cm": 800}
    scene.addItem(plant)
    return plant


@pytest.mark.parametrize("angle", [0, 37, 215])
def test_snap_anchors_ignore_spacing_ring(shown_canvas, angle):
    _, scene = shown_canvas
    item = _plant(scene)
    item._apply_rotation(angle)
    before = ObjectSnapper._get_snap_values(item)
    scene.set_spacing_circles_visible(True)
    item.set_spacing_overlap("overlap")
    after = ObjectSnapper._get_snap_values(item)
    assert after == before


@pytest.mark.parametrize("mode", list(AlignMode))
def test_alignment_ignores_diagnostics(shown_canvas, mode):
    _, scene = shown_canvas
    plant = _plant(scene)
    other = RectangleItem(950, 900, 170, 110)
    scene.addItem(other)
    before = align_items([plant, other], mode)
    scene.set_spacing_circles_visible(True)
    plant.set_spacing_overlap("overlap")
    assert align_items([plant, other], mode) == before


def test_capacity_badge_is_inside_geometric_outline(shown_canvas, monkeypatch):
    _, scene = shown_canvas
    item = RectangleItem(100, 100, 60, 40, object_type=ObjectType.CONTAINER)
    scene.addItem(item)
    item.set_capacity_overrun(True)
    monkeypatch.setattr(item, "boundingRect", lambda: QRectF(-400, -400, 1200, 1200))
    painter = MagicMock()
    item._draw_capacity_badge(painter)
    points = painter.drawPolygon.call_args.args
    assert all(item.rect().contains(point) for point in points)


def test_multiselection_has_outlines_without_individual_handles(shown_canvas):
    view, scene = shown_canvas
    items = [RectangleItem(400, 400, 150, 100), _plant(scene, 1000)]
    scene.addItem(items[0])
    view.set_zoom(1)
    for item in items:
        item.setSelected(True)
    for item in items:
        assert not any(h.isVisible() for h in item._resize_handles)
        assert not item._rotation_handle.isVisible()
    items[1].setSelected(False)
    assert all(h.isVisible() for h in items[0]._resize_handles)
    assert items[0]._rotation_handle.isVisible()


def test_tiny_plant_handles_return_after_zoom(shown_canvas):
    view, scene = shown_canvas
    plant = _plant(scene)
    view.set_zoom(0.1)
    plant.setSelected(True)
    assert not any(h.isVisible() for h in plant._resize_handles)
    view.set_zoom(1)
    assert all(h.isVisible() for h in plant._resize_handles)


@pytest.mark.parametrize("angle", [0, 37, 215])
def test_rotation_handle_gap_stays_in_screen_pixels(shown_canvas, angle):
    view, scene = shown_canvas
    item = _plant(scene)
    item._apply_rotation(angle)
    view.set_zoom(0.5)
    item.setSelected(True)
    anchor = QPointF(item.rect().center().x(), item.rect().top())

    def gap():
        transform = view.viewportTransform()
        return (transform.map(item._rotation_handle.scenePos())
                - transform.map(item.mapToScene(anchor))).manhattanLength()

    before = gap()
    view.set_zoom(4)
    after = gap()
    assert after == pytest.approx(before, abs=1e-6)


@pytest.mark.parametrize("size", [(3000, 2000), (3000, 400), (400, 3000)])
@pytest.mark.parametrize("rulers", [True, False])
def test_fit_keeps_plan_inside_rulers(shown_canvas, size, rulers):
    view, scene = shown_canvas
    scene.resize_canvas(*size)
    view.set_guides_visible(rulers)
    view.fit_in_view()
    pixels = view.viewportTransform().mapRect(scene.canvas_rect)
    inset = 20 if rulers else 0
    safe = QRectF(view.viewport().rect()).adjusted(inset + 3, inset + 3, -3, -3)
    assert safe.contains(pixels)


def test_zoomed_handle_still_drags_and_undoes_once(shown_canvas):
    view, scene = shown_canvas
    item = RectangleItem(400, 400, 150, 100)
    scene.addItem(item)
    view.set_zoom(0.05)
    item.setSelected(True)
    view.set_zoom(1)
    view.centerOn(item.rect().center())
    before = QRectF(item.rect())
    handle = next(h for h in item._resize_handles
                  if h.handle_position is HandlePosition.BOTTOM_RIGHT)
    start = view.mapFromScene(handle.scenePos())
    end = start + QPointF(45, -30).toPoint()
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert item.rect() != before
    manager = scene.get_command_manager()
    assert len(manager._undo_stack) == 1
    manager.undo()
    assert item.rect() == before
