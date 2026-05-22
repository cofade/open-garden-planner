"""``PaperSpaceView``: a QGraphicsView for browsing a paper-space scene.

Provides wheel-zoom + middle-mouse pan, mirroring the model-space
``CanvasView`` controls. Y-up is applied here so the page draws with
its top edge up the way print-shop tools display it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QPainter, QWheelEvent
from PyQt6.QtWidgets import QGraphicsView

if TYPE_CHECKING:
    from open_garden_planner.ui.paper_space.paper_space_scene import (
        PaperSpaceScene,
    )


_MIN_ZOOM = 0.05
_MAX_ZOOM = 10.0


class PaperSpaceView(QGraphicsView):
    """Read/edit view for paper space."""

    def __init__(self, scene: PaperSpaceScene) -> None:
        super().__init__(scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setBackgroundBrush(self.palette().window())
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        # Fit the page on first show with a small initial zoom.
        # Y-up convention to match model-space canvas.
        self.scale(2.0, -2.0)
        self._is_panning = False
        self._pan_start = None

    # ── Zoom (wheel) ───────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        cur = self.transform().m11()
        if cur * factor < _MIN_ZOOM or cur * factor > _MAX_ZOOM:
            return
        self.scale(factor, factor)

    # ── Pan (middle mouse) ─────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning and self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            h = self.horizontalScrollBar()
            v = self.verticalScrollBar()
            h.setValue(h.value() - int(delta.x()))
            v.setValue(v.value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self._pan_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def fit_page(self) -> None:
        """Fit the page rect into the view with a small margin."""
        scene = self.scene()
        if scene is None or not hasattr(scene, "page_rect_cm"):
            return
        page = scene.page_rect_cm()  # type: ignore[attr-defined]
        margin = max(page.width(), page.height()) * 0.05
        target = page.adjusted(-margin, -margin, margin, margin)
        self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)
        # fitInView resets the transform with positive scale on both
        # axes; restore Y-up.
        t = self.transform()
        self.setTransform(t.scale(1.0, -1.0))
