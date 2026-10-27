"""Rims do not paint beneath translucent path interiors (#617)."""

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QTransform

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.item_look import adopt_pen
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import path_style_paint
from open_garden_planner.ui.canvas.items.path_style_paint import PathStylePaint
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem


@pytest.mark.parametrize("style,pattern", [("gravel", FillPattern.GRAVEL), ("dirt", FillPattern.SOIL)])
@pytest.mark.parametrize("opacity,alpha", [(0.5, 255), (1.0, 128), (0.5, 128)])
@pytest.mark.parametrize("points", [
    [(20, 70), (300, 70)], [(20, 30), (180, 30), (180, 110)],
    [(20, 20), (300, 120), (300, 20), (20, 120)],
])
@pytest.mark.parametrize("transformed", [False, True])
def test_texture_middle_is_composited_once(qtbot, style, pattern, opacity, alpha, points, transformed):
    pen = QPen(QColor(160, 110, 70, alpha), 80.0)
    path = PathStylePaint([QPointF(*point) for point in points], pen)
    transform = QTransform().translate(30, 130).scale(0.75, -0.75).rotate(12) if transformed else QTransform()

    def render(texture_only):
        image = QImage(340, 140, QImage.Format.Format_RGBA8888)
        image.fill(QColor(70, 160, 90))
        painter = QPainter(image)
        painter.setWorldTransform(transform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(opacity)
        if texture_only:
            # Same coverage gives Qt the same transformed texture sampling phase.
            path._textured_stroke(painter, pattern, 75.0 if style == "gravel" else 80.0)
        else:
            getattr(path, f"_paint_{style}_path")(painter)
        painter.end()
        return np.frombuffer(image.constBits().asstring(image.sizeInBytes()), np.uint8).reshape(140, 340, 4).copy()

    actual, texture = render(False), render(True)
    mask = QImage(340, 140, QImage.Format.Format_RGBA8888)
    mask.fill(0)
    painter = QPainter(mask)
    painter.setWorldTransform(transform)
    painter.setPen(QPen(QColor("white"), 50.0, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawPath(path.path())
    painter.end()
    middle = np.frombuffer(mask.constBits().asstring(mask.sizeInBytes()), np.uint8).reshape(140, 340, 4)[..., 3] == 255
    delta = np.abs(actual[..., :3][middle].astype(int) - texture[..., :3][middle].astype(int))
    print(f"[617-RIM] {style} opacity={opacity} alpha={alpha} max_delta={delta.max()}")
    assert delta.max() <= 1


@pytest.mark.parametrize("style", [PathFenceStyle.GRAVEL_PATH, PathFenceStyle.DIRT_PATH])
def test_a_real_half_opacity_layer_has_no_underpaint(qtbot, monkeypatch, style):
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import QGraphicsItem

    scene = CanvasScene(340, 140)
    item = PolylineItem([QPointF(20, 70), QPointF(300, 70)],
                        object_type=ObjectType.PATH, path_fence_style=style)
    adopt_pen(item, QPen(QColor(160, 110, 70), 80))
    item.layer_id = scene.layers[0].id
    scene.addItem(item)
    item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
    scene.update_layer_opacity(item.layer_id, 0.5)
    assert item.opacity() == 0.5

    def render():
        image = QImage(340, 140, QImage.Format.Format_RGBA8888)
        image.fill(QColor("white"))
        painter = QPainter(image)
        scene.render(painter, QRectF(0, 0, 340, 140), QRectF(0, 0, 340, 140))
        painter.end()
        return np.frombuffer(image.constBits().asstring(image.sizeInBytes()), np.uint8).reshape(140, 340, 4).copy()

    actual = render()
    monkeypatch.setattr(PathStylePaint, "_paint_rim", lambda *_args: None)
    texture_only = render()
    assert np.array_equal(actual[50:90, 60:280], texture_only[50:90, 60:280])


def test_rim_mask_allocations_are_bounded_and_use_no_path_boolean(qtbot, monkeypatch):
    real_image = QImage
    allocations = []

    def image(width, height, image_format):
        allocations.append((width, height))
        return real_image(width, height, image_format)

    # Preserve the enum access used by the production allocator.
    image.Format = QImage.Format
    monkeypatch.setattr(path_style_paint, "QImage", image)
    from PyQt6.QtGui import QPainterPath

    def forbidden(*args):
        raise AssertionError("quadratic vector subtraction in the rim painter")

    monkeypatch.setattr(QPainterPath, "subtracted", forbidden)
    target = real_image(1400, 800, QImage.Format.Format_ARGB32_Premultiplied)
    target.fill(0)
    painter = QPainter(target)
    painter.setOpacity(0.5)
    path = PathStylePaint([QPointF(-10000, 400), QPointF(10000, 400)], QPen(QColor("brown"), 100))
    path._paint_gravel_path(painter)
    painter.end()
    assert len(allocations) == 3 and all(0 < w <= 512 and 0 < h <= 512 for w, h in allocations)
