"""The gallery picture of an example plan."""

from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.services.scene_rendering import render_scene_region

SIZE = (640, 360)


def thumbnail(scene, path, region=None):
    """The whole plan, letterboxed. A plan that is much taller than the picture is wide
    would be a sliver: its module names a 16:9 ``region`` (x, y, width, height in cm, from
    the plan's south-west corner) that fills the picture instead."""
    width, height = SIZE
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#f2f0e8"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if region is None:
        scale = min(width / scene.width_cm, height / scene.height_cm)
        target = QRectF((width - scene.width_cm * scale) / 2, (height - scene.height_cm * scale) / 2,
                        scene.width_cm * scale, scene.height_cm * scale)
        source = scene.canvas_rect
    else:
        x, y, region_width, region_height = region
        assert abs(region_width / region_height - width / height) < 0.01, "a 16:9 region"
        target = QRectF(0, 0, width, height)
        # the scene's y grows downwards in Qt's own frame: measure from the plan's top
        source = QRectF(scene.canvas_rect.left() + x,
                        scene.canvas_rect.bottom() - y - region_height, region_width, region_height)
    render_scene_region(scene, painter, target, source)
    painter.end()
    assert image.save(str(path))
