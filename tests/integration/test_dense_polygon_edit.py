"""Generated outlines keep a bounded editing overlay, not less geometry (#551)."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication, QGraphicsSceneMouseEvent

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem
from open_garden_planner.ui.canvas.items.resize_handle import (
    MAX_DENSE_VERTEX_HANDLES,
    _format_coordinate,
)


def _dense_polygon(count: int = 255) -> PolygonItem:
    """A tessellated circle: every vertex is real, none may be dropped."""
    points = [
        QPointF(
            200 + 150 * math.cos(2 * math.pi * index / count),
            200 + 150 * math.sin(2 * math.pi * index / count),
        )
        for index in range(count)
    ]
    return PolygonItem(points)


def _dense_polyline(count: int = 255, spacing: float = 20.0) -> PolylineItem:
    return PolylineItem([QPointF(index * spacing, 200) for index in range(count)])


@pytest.fixture
def view(qtbot) -> CanvasView:
    scene = CanvasScene(5000, 3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1100, 650)
    view.show()
    qtbot.waitExposed(view)
    return view


def _show(view: CanvasView, item, *, zoom: float, center: QPointF) -> None:
    view._zoom_factor = zoom
    view._apply_transform()
    view.centerOn(center)
    view.repaint()
    QApplication.processEvents()


def test_dense_polygon_overlay_is_bounded_and_keeps_the_outline(view) -> None:
    item = _dense_polygon()
    view.scene().addItem(item)
    original = item.polygon()
    _show(view, item, zoom=1.5, center=original.boundingRect().center())

    item.setSelected(True)
    item.enter_vertex_edit_mode()

    assert item.is_vertex_edit_mode
    assert not item._coord_labels and not item._edge_labels
    assert 0 < len(item._vertex_handles) <= MAX_DENSE_VERTEX_HANDLES
    assert len(item._midpoint_handles) < 10  # only edges genuinely long on screen
    assert len(item.childItems()) < 200
    assert item.polygon() == original
    assert all(handle.toolTip() for handle in item._vertex_handles)

    for zoom in (3.0, 0.8, 4.0):
        _show(view, item, zoom=zoom, center=QPointF(200, 200))
        assert len(item.childItems()) < 200
        assert item.polygon() == original

    item.setSelected(False)
    assert not item.is_vertex_edit_mode
    assert not item._vertex_handles and not item._midpoint_handles
    assert view.command_manager.undo_depth == 0


def test_sampled_handle_uses_its_original_index_and_undo(view) -> None:
    item = _dense_polygon()
    view.scene().addItem(item)
    _show(view, item, zoom=1.5, center=QPointF(200, 200))
    item.setSelected(True)
    item.enter_vertex_edit_mode()

    handle = next(
        handle
        for row, handle in enumerate(item._vertex_handles)
        if handle.vertex_index != row
    )
    index = handle.vertex_index
    before = item.polygon()
    old = before.at(index)
    new = old + QPointF(10, 5)
    item._move_vertex_to(index, new)
    item._on_vertex_move_end(index, old, new)

    assert handle.pos() == new
    assert handle.toolTip() == _format_coordinate(new.x(), new.y())
    assert all(
        item.polygon().at(i) == before.at(i)
        for i in range(before.count())
        if i != index
    )

    view.command_manager.undo()
    assert item.polygon() == before
    view.command_manager.redo()
    assert item.polygon().at(index) == new

    # Zooming into the outline reveals vertices the coarse sample hid.
    previous = {handle.vertex_index for handle in item._vertex_handles}
    _show(view, item, zoom=10.0, center=item.mapToScene(new))
    revealed = {handle.vertex_index for handle in item._vertex_handles}
    assert revealed - previous


def test_a_hundred_vertex_outline_is_sampled_not_piled_up(view) -> None:
    item = _dense_polygon(100)
    view.scene().addItem(item)
    _show(view, item, zoom=1.0, center=QPointF(200, 200))
    item.enter_vertex_edit_mode()

    assert 0 < len(item._vertex_handles) < 100
    assert len(item._vertex_handles) <= MAX_DENSE_VERTEX_HANDLES
    assert not item._coord_labels


def test_small_polygon_keeps_all_existing_annotations(view) -> None:
    item = PolygonItem([QPointF(0, 0), QPointF(100, 0), QPointF(50, 100)])
    view.scene().addItem(item)
    _show(view, item, zoom=1.0, center=QPointF(50, 50))
    item.enter_vertex_edit_mode()

    assert len(item._vertex_handles) == len(item._midpoint_handles) == 3
    assert len(item._coord_labels) == len(item._edge_labels) == 3


def test_dense_polyline_overlay_is_bounded(view) -> None:
    item = _dense_polyline()
    view.scene().addItem(item)
    _show(view, item, zoom=1.0, center=QPointF(2500, 200))
    item.enter_vertex_edit_mode()

    assert not item._coord_labels and not item._edge_labels
    assert 0 < len(item._vertex_handles) <= MAX_DENSE_VERTEX_HANDLES
    assert len(item.childItems()) < 300
    assert all(handle.toolTip() for handle in item._vertex_handles)


def test_visible_midpoint_with_both_endpoints_offscreen_is_insertable(view) -> None:
    item = _dense_polyline(spacing=200.0)
    view.scene().addItem(item)
    _show(view, item, zoom=10.0, center=QPointF(1100, 200))
    item.enter_vertex_edit_mode()

    handle = next(
        handle
        for handle in item._midpoint_handles
        if handle.pos() == QPointF(1100, 200)
    )
    index = handle.edge_index
    start = view.mapFromScene(item.mapToScene(item._points[index]))
    end = view.mapFromScene(item.mapToScene(item._points[index + 1]))
    assert not view.viewport().rect().contains(start)
    assert not view.viewport().rect().contains(end)

    event = MagicMock(spec=QGraphicsSceneMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    handle.mousePressEvent(event)

    assert len(item._points) == 256
    assert item._points[index + 1] == QPointF(1100, 200)
    view.command_manager.undo()
    assert len(item._points) == 255


def test_drag_handle_survives_a_refresh_and_undoes_once(view) -> None:
    item = _dense_polygon()
    view.scene().addItem(item)
    _show(view, item, zoom=1.5, center=QPointF(200, 200))
    item.setSelected(True)
    item.enter_vertex_edit_mode()

    handle = item._vertex_handles[3]
    before = item.polygon()
    handle._is_dragging = True
    try:
        item.refresh_vertex_edit_overlay()
        assert handle in item._vertex_handles
    finally:
        handle._is_dragging = False
    assert item.polygon() == before
