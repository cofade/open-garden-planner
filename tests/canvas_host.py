"""A canvas below a header, and captures that preserve its backing-store offset."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
from pytestqt.qtbot import QtBot

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

HEADER_PX = 180


def embed_canvas(child: QWidget, qtbot: QtBot, *, size: tuple[int, int] = (700, 520)) -> QWidget:
    window = QWidget()
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    header = QWidget()
    header.setFixedHeight(HEADER_PX)
    layout.addWidget(header)
    layout.addWidget(child)
    child.setFixedSize(*size)
    qtbot.addWidget(window)
    window.resize(size[0], size[1] + HEADER_PX)
    window.show()
    qtbot.waitExposed(window)
    QApplication.processEvents()
    return window


def grab_viewport(view: "CanvasView") -> QImage:
    """Grab the window first: grabbing the viewport alone erases the offset."""
    viewport = view.viewport()
    window = view.window()
    image = window.grab().toImage()
    ratio = image.devicePixelRatioF()
    origin = viewport.mapTo(window, QPoint(0, 0))
    rect = QRect(round(origin.x() * ratio), round(origin.y() * ratio),
                 round(viewport.width() * ratio), round(viewport.height() * ratio))
    return image.copy(rect)
