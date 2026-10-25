"""Generated outlines keep a bounded editing overlay, not less geometry (#551)."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QApplication, QGraphicsSceneMouseEvent

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem
from open_garden_planner.ui.canvas.items.resize_handle import (
    MAX_DENSE_VERTEX_HANDLES,
    _dense_sample_covers_view,
    _format_coordinate,
    _visible_viewport_rect,
)


def _dense_polygon(count: int = 255, radius: float = 150.0) -> PolygonItem:
    """A tessellated circle: every vertex is real, none may be dropped."""
    points = [
        QPointF(
            200 + radius * math.cos(2 * math.pi * index / count),
            200 + radius * math.sin(2 * math.pi * index / count),
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


def test_the_visible_rect_stays_in_viewport_pixels_at_any_dpr() -> None:
    """``deviceTransform`` does NOT apply the device-pixel ratio on Qt 6.11.

    It is ``sceneTransform * viewportTransform``, so the visible window must be
    the viewport rect unscaled. The first version of this helper multiplied by
    ``devicePixelRatioF()`` and sampled a whole viewport beyond the edge at
    200 % scaling (senior review of PR #585, round 5).
    """

    class FakeViewport:
        @staticmethod
        def rect():
            from PyQt6.QtCore import QRect

            return QRect(0, 0, 800, 600)

    class FakeView:
        @staticmethod
        def viewport():
            return FakeViewport()

        @staticmethod
        def devicePixelRatioF():
            return 2.0

    assert _visible_viewport_rect(FakeView(), 10.0).getRect() == (
        -10.0,
        -10.0,
        820.0,
        620.0,
    )


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


@pytest.mark.parametrize("kind", ["polygon", "polyline"])
def test_a_pan_inside_the_sampled_region_does_not_resample(view, monkeypatch, kind) -> None:
    """A scrollbar step must not walk every vertex of a dense outline (#594).

    #551 caps the overlay at 128 handles, but ``scrollContentsBy`` re-sampled the
    whole outline to decide which; the senior review of PR #585 measured ~100 ms
    per scrollbar step. The sample is reused while the viewport stays inside the
    scene region the sampler actually tested (the viewport grown by
    ``DENSE_HANDLE_SPACING_PX``), and re-taken when it leaves.
    """
    from open_garden_planner.ui.canvas.items import resize_handle

    if kind == "polygon":
        item = _dense_polygon(16_384, radius=600.0)
        centre = QPointF(200, 200)
    else:
        item = _dense_polyline(255)
        centre = QPointF(2500, 200)
    view.scene().addItem(item)
    _show(view, item, zoom=1.0, center=centre)
    item.setSelected(True)
    item.enter_vertex_edit_mode()
    before = {handle.vertex_index for handle in item._vertex_handles}

    calls: list[int] = []
    original = resize_handle._dense_overlay_indices

    def spy(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(resize_handle, "_dense_overlay_indices", spy)

    bar = view.horizontalScrollBar()
    start = bar.value()
    for step in range(1, 11):
        bar.setValue(start + step * 2)
        view.repaint()
        QApplication.processEvents()
    assert calls == [], "a small scroll re-sampled the dense outline"

    # A pan beyond the sampler's 24-px candidate margin re-samples, and the new
    # viewport gets handles for vertices the old sample never considered.
    bar.setValue(start + 100)
    view.repaint()
    QApplication.processEvents()
    assert calls, "a pan beyond the candidate margin did not re-sample"
    after = {handle.vertex_index for handle in item._vertex_handles}
    assert after != before
    newly = after - before
    assert newly, "the re-sample exposed no vertex the old sample had missed"
    viewport = view.viewport().rect()
    assert any(
        handle.vertex_index in newly
        and viewport.contains(view.mapFromScene(handle.scenePos()))
        for handle in item._vertex_handles
    )

    # A pan far outside the region re-samples too.
    calls.clear()
    view.centerOn(QPointF(3000, 2500))
    view.repaint()
    QApplication.processEvents()
    assert calls

    # Zoom always re-samples: the pixel spacing changed.
    calls.clear()
    _show(view, item, zoom=2.0, center=centre)
    assert calls


def test_a_polygon_resize_in_edit_mode_updates_its_handles(view) -> None:
    """Undo/redo of a polygon resize must not leave stale vertex handles (#594)."""
    from open_garden_planner.ui.canvas.items.polygon_item import polygon_resize_apply

    item = _dense_polygon(255)
    view.scene().addItem(item)
    _show(view, item, zoom=1.0, center=QPointF(200, 200))
    item.enter_vertex_edit_mode()
    polygon = item.polygon()
    vertices = [
        {
            "x": polygon.at(i).x() * 0.9 + 20.0,
            "y": polygon.at(i).y() * 0.9 + 20.0,
        }
        for i in range(polygon.count())
    ]
    polygon_resize_apply(item, {
        "vertices": vertices,
        "pos_x": item.pos().x(),
        "pos_y": item.pos().y(),
    })
    assert item.polygon().count() == len(vertices)
    assert all(
        handle.pos() == item.polygon().at(handle.vertex_index)
        for handle in item._vertex_handles
    )
    assert not _dense_sample_covers_view(item)


def test_a_transform_change_invalidates_the_dense_sample(view) -> None:
    """The pose key is the full scene transform, not only pos/rotation/scale (#594)."""
    item = _dense_polygon(255)
    view.scene().addItem(item)
    _show(view, item, zoom=1.0, center=QPointF(200, 200))
    item.enter_vertex_edit_mode()
    assert _dense_sample_covers_view(item)
    item.setTransform(QTransform().translate(5.0, 0.0))
    assert not _dense_sample_covers_view(item)


def test_a_parent_transform_invalidates_the_dense_sample(view) -> None:
    """The pose key includes the parent chain, not only the child's own pose (#594)."""
    from PyQt6.QtWidgets import QGraphicsItemGroup

    item = _dense_polygon(255)
    group = QGraphicsItemGroup()
    view.scene().addItem(group)
    group.addToGroup(item)
    _show(view, item, zoom=1.0, center=QPointF(200, 200))
    item.enter_vertex_edit_mode()
    assert _dense_sample_covers_view(item)
    group.setRotation(30.0)
    assert item.rotation() == 0.0 and item.scale() == 1.0
    assert not _dense_sample_covers_view(item)


def test_a_transform_origin_change_invalidates_the_dense_sample(view) -> None:
    """The pose key includes ``transformOriginPoint``, which moves a rotated item (#594)."""
    item = _dense_polygon(255)
    view.scene().addItem(item)
    item.setRotation(20.0)
    _show(view, item, zoom=1.0, center=QPointF(200, 200))
    item.enter_vertex_edit_mode()
    assert _dense_sample_covers_view(item)
    item.setTransformOriginPoint(QPointF(10.0, 10.0))
    assert not _dense_sample_covers_view(item)


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
