"""The gallery picture of an example plan."""

from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.services.scene_rendering import render_scene_region

SIZE = (640, 360)


def thumbnail(scene, path, region=None):
    """The whole plan, letterboxed. A plan that is much taller than the picture is wide
    would be a sliver: its module names the ``region`` (x, y, width, height in cm, from the
    plan's south-west corner) that the picture shows instead."""
    width, height = SIZE
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#f2f0e8"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    x, y, region_width, region_height = region or (0.0, 0.0, scene.width_cm, scene.height_cm)
    scale = min(width / region_width, height / region_height)
    target = QRectF((width - region_width * scale) / 2, (height - region_height * scale) / 2,
                    region_width * scale, region_height * scale)
    source = QRectF(scene.canvas_rect.left() + x, scene.canvas_rect.top() + y,
                    region_width, region_height)
    render_scene_region(scene, painter, target, source)
    painter.end()
    assert image.save(str(path))
