"""Issue #1005: one placement owner for a viewport-parented overlay."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRectF
from PyQt6.QtWidgets import QFrame

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.viewport_overlay import ViewportOverlay


def test_overlay_clamps_flips_and_keeps_a_hidden_widget_still(qtbot) -> None:
    scene = CanvasScene(width_cm=1000, height_cm=800)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(420, 320)
    view.show()
    qtbot.waitExposed(view)
    viewport = view.viewport()
    widget = QFrame(viewport)
    widget.resize(200, 100)
    anchor = [QRectF(10, 10, 10, 10)]
    overlay = ViewportOverlay(view, widget, lambda: anchor[0])
    widget.show()

    overlay.place()
    assert widget.pos() == QPoint(0, 32)

    # A widget past the right edge is clamped inside the viewport.
    anchor[0] = QRectF(viewport.width() + 50, 10, 4, 4)
    overlay.place()
    assert widget.pos().x() == viewport.width() - widget.width()
    assert widget.pos().y() == 26

    # No room below: the strip flips above the anchor.
    anchor[0] = QRectF(10, viewport.height() - 5, 4, 4)
    overlay.place()
    assert widget.pos().y() == viewport.height() - 5 - widget.height() - 12

    # A hidden widget and a draft that has gone keep their last position.
    widget.hide()
    widget.move(7, 9)
    anchor[0] = QRectF(10, 10, 10, 10)
    overlay.place()
    assert widget.pos() == QPoint(7, 9)

    widget.show()
    widget.move(11, 13)
    anchor[0] = None
    overlay.place()
    assert widget.pos() == QPoint(11, 13)
