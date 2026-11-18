"""The gallery picture of an example plan."""

from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.services.scene_rendering import render_scene_region


def thumbnail(scene, path):
    image = QImage(640, 360, QImage.Format.Format_RGB32)
    image.fill(QColor("#f2f0e8"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = min(640 / scene.width_cm, 360 / scene.height_cm)
    target = QRectF((640 - scene.width_cm * scale) / 2,
                    (360 - scene.height_cm * scale) / 2,
                    scene.width_cm * scale, scene.height_cm * scale)
    render_scene_region(scene, painter, target, scene.canvas_rect)
    painter.end()
    assert image.save(str(path))
