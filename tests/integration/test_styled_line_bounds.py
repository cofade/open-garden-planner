"""Uncached pixels independently constrain cached line bounds (#471)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QGraphicsItem, QStyleOptionGraphicsItem

from open_garden_planner.core.commands import CommandManager
from open_garden_planner.core.item_look import adopt_pen
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolylineItem
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel


def pixels(image: QImage) -> np.ndarray:
    bits = image.constBits()
    assert bits is not None
    return np.frombuffer(bits.asstring(image.sizeInBytes()), np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4)[:, :image.width(), :3].copy()


def contrast(image: np.ndarray, background: np.ndarray) -> np.ndarray:
    return np.max(np.abs(image.astype(int) - background.astype(int)), axis=2)


def raster_neighbours(mask: np.ndarray) -> np.ndarray:
    """Device-cache and direct antialiasing may differ by one device pixel."""
    padded = np.pad(mask, 1)
    height, width = mask.shape
    return np.logical_or.reduce([padded[y:y + height, x:x + width]
                                 for y in range(3) for x in range(3)])


def line(style: PathFenceStyle, width: float | None, shape: str = "straight") -> PolylineItem:
    points = [QPointF(150, 300), QPointF(650, 300)]
    if shape == "bend":
        points.append(QPointF(650, 500))
    elif shape == "hairpin":
        points = [QPointF(400, 300 + 200 * math.tan(math.radians(15))),
                  QPointF(650, 300), QPointF(400, 300 - 200 * math.tan(math.radians(15)))]
    item = PolylineItem(points, object_type=ObjectType.FENCE, path_fence_style=style)
    item.shadows_enabled = False
    item.label_visible = False
    pen = item.pen()
    pen.setColor(QColor("#606060"))
    if width is not None:
        pen.setWidthF(width)
    adopt_pen(item, pen)
    return item


@pytest.mark.parametrize("style", [s for s in PathFenceStyle if s is not PathFenceStyle.NONE])
@pytest.mark.parametrize("width", [None, 0.5, 30.0], ids=["preset", "narrow", "wide"])
@pytest.mark.parametrize("shape", ["straight", "bend", "hairpin"])
def test_uncached_pixels_fit_the_declared_bounds(
        qtbot: Any, style: PathFenceStyle, width: float | None, shape: str,
) -> None:
    item = line(style, width, shape)
    # Fixed independent region: never crop the oracle to the bounds being tested.
    image = QImage(900, 700, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    try:
        item.paint(painter, QStyleOptionGraphicsItem())
    finally:
        painter.end()
    rows, columns = np.nonzero(np.any(pixels(image) < 240, axis=2))
    assert len(rows) > 0
    painted = QRectF(float(columns.min()), float(rows.min()),
                     float(columns.max() - columns.min()), float(rows.max() - rows.min()))
    # One pixel for raster antialiasing, independent of the geometric reach.
    assert item.boundingRect().adjusted(-1, -1, 1, 1).contains(painted), (
        style.name, width, shape, painted, item.boundingRect())


@pytest.mark.parametrize("style", [PathFenceStyle.METAL_FENCE, PathFenceStyle.CHAIN_LINK])
@pytest.mark.parametrize("width", [None, 30.0], ids=["preset", "wide"])
@pytest.mark.parametrize("angle", [0.0, 45.0, 215.0])
@pytest.mark.parametrize("zoom", [0.25, 1.0, 2.0])
def test_real_canvas_cache_keeps_the_uncached_details(
        qtbot: Any, monkeypatch: Any, style: PathFenceStyle,
        width: float | None, angle: float, zoom: float,
) -> None:
    calls = []
    paint = PolylineItem.paint

    def counted(self: PolylineItem, *args: Any) -> None:
        calls.append(self.cacheMode())
        paint(self, *args)

    monkeypatch.setattr(PolylineItem, "paint", counted)
    scene = CanvasScene(width_cm=1500, height_cm=1500)
    item = line(style, width)
    scene.addItem(item)
    item.setTransformOriginPoint(QPointF(400, 300))
    item.setRotation(angle)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1300, 1100)
    view.set_grid_visible(False)
    view.show()
    view.set_zoom(zoom)
    view.centerOn(QPointF(400, 300))
    qtbot.wait(1)

    def rendered(mode: QGraphicsItem.CacheMode) -> np.ndarray:
        if item.cacheMode() != mode:
            item.setCacheMode(mode)
        view.viewport().update()
        qtbot.wait(1)
        image = QImage(view.viewport().size(), QImage.Format.Format_RGBA8888_Premultiplied)
        image.fill(QColor("white"))
        painter = QPainter(image)
        try:
            view.viewport().render(painter)
        finally:
            painter.end()
        return pixels(image)

    assert not item.isSelected()
    assert item.cacheMode() is QGraphicsItem.CacheMode.DeviceCoordinateCache
    cached = rendered(QGraphicsItem.CacheMode.DeviceCoordinateCache)
    first_paints = len(calls)
    assert first_paints > 0
    assert np.array_equal(cached, rendered(QGraphicsItem.CacheMode.DeviceCoordinateCache))
    if angle == 0:
        # Qt may regenerate a DeviceCoordinateCache under rotated transforms.
        # The unrotated control must actually reuse it, rather than only name it.
        assert len(calls) == first_paints, "the second view paint must reuse the real item cache"
    reference = rendered(QGraphicsItem.CacheMode.NoCache)
    assert len(calls) > first_paints
    item.setVisible(False)
    background = rendered(QGraphicsItem.CacheMode.NoCache)
    item.setVisible(True)
    expected = contrast(reference, background) > 8
    assert int(expected.sum()) > 0
    # Include faint subpixel metal rails at 25% zoom; exclude the empty scene,
    # including its dark outside-page area. Allow one pixel of raster alignment.
    missing = expected & ~raster_neighbours(contrast(cached, background) > 2)
    assert not missing.any(), (style.name, width, angle, zoom, int(missing.sum()))


def test_pen_and_preset_notify_before_the_bounds_change(qtbot: Any) -> None:
    class ObservedLine(PolylineItem):
        observations: list[tuple[float, PathFenceStyle]]

        def prepareGeometryChange(self) -> None:
            if hasattr(self, "observations"):
                self.observations.append((self.pen().widthF(), self.path_fence_style))
            super().prepareGeometryChange()

    item = ObservedLine([QPointF(100, 100), QPointF(500, 100)])
    item.observations = []
    previous = item.pen().widthF()
    pen = QPen(item.pen())
    pen.setWidthF(30)
    item.setPen(pen)
    assert (previous, PathFenceStyle.NONE) in item.observations
    item.observations.clear()
    item.path_fence_style = PathFenceStyle.METAL_FENCE
    assert (30, PathFenceStyle.NONE) in item.observations


@pytest.mark.parametrize("angle", [0.0, 45.0])
@pytest.mark.parametrize("zoom", [0.5, 1.0])
def test_cached_edits_history_and_move_match_an_uncached_frame(
        qtbot: Any, monkeypatch: Any, angle: float, zoom: float,
) -> None:
    """Change an already populated cache; an independently painted view is the oracle."""
    item = line(PathFenceStyle.METAL_FENCE, 2.0, "bend")
    item.setTransformOriginPoint(QPointF(400, 300))
    item.setRotation(angle)
    reference = line(PathFenceStyle.METAL_FENCE, 2.0, "bend")
    reference.setTransformOriginPoint(item.transformOriginPoint())
    reference.setRotation(angle)
    reference.setCacheMode(QGraphicsItem.CacheMode.NoCache)
    views = []
    # Keep both scenes alive and keep their viewport transforms fixed throughout.
    scenes = [CanvasScene(width_cm=1500, height_cm=1500) for _ in range(2)]
    for scene, subject in zip(scenes, (item, reference), strict=True):
        scene.addItem(subject)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        view.resize(1100, 1100)
        view.set_grid_visible(False)
        view.show()
        view.set_zoom(zoom)
        view.centerOn(QPointF(600, 550))
        views.append(view)
    manager = CommandManager()
    panel = PropertiesPanel(manager)
    qtbot.addWidget(panel)
    panel.set_selected_items([item])
    paints = []
    original_paint = PolylineItem.paint

    def counted(self: PolylineItem, *args: Any) -> None:
        if self is item:
            paints.append(self.cacheMode())
        original_paint(self, *args)

    monkeypatch.setattr(PolylineItem, "paint", counted)

    def frame(view: CanvasView) -> np.ndarray:
        qtbot.wait(1)
        return pixels(view.viewport().grab().toImage().convertToFormat(
            QImage.Format.Format_RGBA8888_Premultiplied))

    reference.setVisible(False)
    background = frame(views[1])
    reference.setVisible(True)

    def is_background(image: np.ndarray) -> np.ndarray:
        return contrast(image, background) <= 2

    def check() -> np.ndarray:
        assert not item.isSelected()
        assert item.cacheMode() is QGraphicsItem.CacheMode.DeviceCoordinateCache
        # The oracle never shares the device cache or history application path.
        reference.path_fence_style = item.path_fence_style
        adopt_pen(reference, QPen(item.pen()))
        reference.setPos(item.pos())
        cached, direct = (frame(view) for view in views)
        expected = contrast(direct, background) > 8
        actual = contrast(cached, background) > 8
        assert expected.any()
        assert not (expected & ~raster_neighbours(~is_background(cached))).any(), "missing detail"
        assert not (actual & ~raster_neighbours(~is_background(direct))).any(), "stale cached detail"
        return cached

    check()
    populated = len(paints)
    assert populated > 0
    check()
    if angle == 0:
        assert len(paints) == populated, "the initial cache must actually be reused"
    widths = [spin for spin in panel.findChildren(QDoubleSpinBox) if spin.suffix() == " px"]
    assert len(widths) == 1
    widths[0].setValue(20.0)
    check()
    manager.undo()
    check()
    manager.redo()
    check()
    presets = [combo for combo in panel.findChildren(QComboBox)
               if combo.findData(PathFenceStyle.CHAIN_LINK) >= 0]
    assert len(presets) == 1
    presets[0].setCurrentIndex(presets[0].findData(PathFenceStyle.CHAIN_LINK))
    check()
    manager.undo()
    check()
    manager.redo()
    old_frame = check()
    item.setPos(QPointF(0, 350))
    moved_frame = check()
    cleared = (contrast(old_frame, background) > 8) & is_background(frame(views[1]))
    assert cleared.any(), "the fixed old region must contain vacated line pixels"
    assert np.all(is_background(moved_frame)[cleared]), "the old location must clear"
