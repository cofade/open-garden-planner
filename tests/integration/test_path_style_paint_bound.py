"""A styled line costs what it shows, not its whole length (#450)."""

from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.path_style_paint import PathStylePaint
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem


def _long_gravel_path(*, length_cm: float = 1_900_000.0) -> PolylineItem:
    return PolylineItem(
        [QPointF(0, 0), QPointF(length_cm, 0)],
        object_type=ObjectType.PATH,
        path_fence_style=PathFenceStyle.GRAVEL_PATH,
    )


def test_a_19_km_line_is_clipped_to_the_live_viewport(qtbot) -> None:
    scene = CanvasScene(2_000_000, 2_000_000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    qtbot.waitExposed(view)
    item = _long_gravel_path()
    scene.addItem(item)
    view._zoom_factor = 1.0
    view._apply_transform()
    view.centerOn(QPointF(100, 0))
    qtbot.wait(10)

    option = QStyleOptionGraphicsItem()
    option.exposedRect = item.boundingRect()
    clip = item._canvas_paint_clip(option, view.viewport())
    assert clip is not None
    left, top, right, bottom = clip
    assert right - left < 10_000  # the item is 1 900 000 cm long
    assert bottom - top < 10_000


def test_an_export_keeps_full_detail(qtbot) -> None:
    scene = CanvasScene(2_000_000, 2_000_000)
    item = _long_gravel_path()
    scene.addItem(item)
    option = QStyleOptionGraphicsItem()
    option.exposedRect = item.boundingRect()
    item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
    assert item._canvas_paint_clip(option, None) is None


def test_painting_generates_a_bounded_number_of_elements(qtbot, monkeypatch) -> None:
    scene = CanvasScene(2_000_000, 2_000_000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    qtbot.waitExposed(view)
    item = _long_gravel_path()
    scene.addItem(item)
    view._zoom_factor = 1.0
    view._apply_transform()
    view.centerOn(QPointF(100, 0))
    qtbot.wait(10)

    yielded = []
    original = PathStylePaint._walk_indexed

    def counting(self, spacing):
        for element in original(self, spacing):
            yielded.append(element)
            yield element

    monkeypatch.setattr(PathStylePaint, "_walk_indexed", counting)
    option = QStyleOptionGraphicsItem()
    option.exposedRect = item.boundingRect()
    image = QImage(400, 300, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        item.paint(painter, option, view.viewport())
    finally:
        painter.end()

    # The whole line would be 475 001 elements at its preset spacing.
    assert 0 < len(yielded) < 5_000


def test_a_cached_paint_is_clipped_too(qtbot, monkeypatch) -> None:
    """Qt passes widget=None for a cached paint; the cache mode still marks it live."""
    scene = CanvasScene(2_000_000, 2_000_000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    qtbot.waitExposed(view)
    item = _long_gravel_path()
    scene.addItem(item)
    item.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
    view._zoom_factor = 1.0
    view._apply_transform()
    view.centerOn(QPointF(100, 0))
    qtbot.wait(10)

    yielded = []
    original = PathStylePaint._walk_indexed

    def counting(self, spacing):
        for element in original(self, spacing):
            yielded.append(element)
            yield element

    monkeypatch.setattr(PathStylePaint, "_walk_indexed", counting)
    option = QStyleOptionGraphicsItem()
    option.exposedRect = item.boundingRect()
    image = QImage(400, 300, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        item.paint(painter, option, None)
    finally:
        painter.end()

    assert 0 < len(yielded) < 5_000
