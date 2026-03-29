"""Minimap / overview panel widget for quick navigation.

Displays a scaled-down thumbnail of the entire garden plan with a
viewport rectangle showing the current visible area. Supports
click-to-pan and drag-to-navigate.

The widget is parented to the QGraphicsView (the scroll area, NOT its
viewport) so that panning/scrolling the scene does not move the overlay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import QGraphicsItem, QWidget

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

# Widget dimensions
MINIMAP_WIDTH = 240
MINIMAP_HEIGHT = 160
MARGIN = 12

# Visual style
_BG_COLOR = QColor(40, 40, 40, 215)
_BORDER_COLOR = QColor(100, 100, 100, 180)
_VIEWPORT_STROKE = QColor(50, 100, 255, 180)
_VIEWPORT_FILL = QColor(50, 100, 255, 30)
_VIEWPORT_STROKE_WIDTH = 2.0

# Throttle interval (ms) — max ~10 fps
_UPDATE_INTERVAL_MS = 100


class MinimapWidget(QWidget):
    """Semi-transparent minimap overlay for canvas navigation.

    Parented to the QGraphicsView itself (not its viewport) so that
    scrolling/panning does not move the overlay.
    """

    def __init__(
        self,
        canvas_view: CanvasView,
        canvas_scene: CanvasScene,
        parent: QWidget | None = None,
    ) -> None:
        # Parent to the QGraphicsView (scroll area) — NOT the viewport.
        # Viewport children scroll with scene content; view children stay put.
        super().__init__(parent or canvas_view)
        self._canvas_view = canvas_view
        self._canvas_scene = canvas_scene
        self._thumbnail: QPixmap | None = None
        # Content area within the minimap after aspect-ratio letterboxing.
        # Stored in displayed (post-Y-flip) coordinates.
        self._render_rect = QRectF(0, 0, MINIMAP_WIDTH, MINIMAP_HEIGHT)
        self._dragging = False
        self._drag_offset_x = 0.0
        self._drag_offset_y = 0.0
        self._enabled = True

        # Size is updated in _do_update() to match canvas aspect ratio
        self.resize(MINIMAP_WIDTH, MINIMAP_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # Throttle timer
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(_UPDATE_INTERVAL_MS)
        self._update_timer.timeout.connect(self._do_update)

        # Connect signals for viewport changes
        canvas_view.zoom_changed.connect(self._schedule_update)
        canvas_view.horizontalScrollBar().valueChanged.connect(self._schedule_update)
        canvas_view.verticalScrollBar().valueChanged.connect(self._schedule_update)
        canvas_scene.changed.connect(self._schedule_update)

        # Install event filter on the *view* (not viewport) to catch resize
        canvas_view.installEventFilter(self)

        # Defer initial position until after the window is fully laid out
        QTimer.singleShot(0, self._reposition)
        self._schedule_update()
        self.raise_()
        self.show()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_visible(self, visible: bool) -> None:
        """Toggle minimap visibility."""
        self._enabled = visible
        if visible:
            self._schedule_update()
            self.show()
            self.raise_()
        else:
            self.hide()

    def is_enabled(self) -> bool:
        """Return whether the minimap is logically enabled."""
        return self._enabled

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------

    def _reposition(self) -> None:
        """Move widget to bottom-right corner of the viewport.

        Clears the scale bar which is drawn at the bottom-right of the
        viewport. Uses viewport().geometry() to stay above the scrollbar.
        """
        from open_garden_planner.ui.canvas.canvas_view import CanvasView

        vp = self._canvas_view.viewport().geometry()
        sb = CanvasView.SCALE_BAR_RESERVED_PX if self._canvas_view.scale_bar_visible else 0
        x = vp.right() - self.width() - MARGIN
        y = vp.bottom() - self.height() - MARGIN - sb
        self.move(max(vp.left(), x), max(vp.top(), y))
        self.raise_()

    def eventFilter(self, obj: object, event: QEvent) -> bool:  # noqa: N802
        """Reposition minimap when the view is resized."""
        if obj is self._canvas_view and event.type() == QEvent.Type.Resize:
            self._reposition()
            self._schedule_update()
        return False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _schedule_update(self, *_args: object) -> None:
        """Schedule a throttled thumbnail re-render."""
        if not self._update_timer.isActive():
            self._update_timer.start()

    def _do_update(self) -> None:
        """Render the scene into a thumbnail pixmap.

        Resizes the widget to match the canvas aspect ratio (within the max
        minimap dimensions) so there are no gray letterbox bars.

        Screen-space overlay items (measure/constraint labels, dimension
        handles) are hidden during rendering so only garden plan content shows.

        The scene uses Y-down coordinates; the view applies a Y-flip so that
        Y increases upward. We flip the thumbnail vertically to match.
        """
        canvas_rect = self._canvas_scene.canvas_rect
        if canvas_rect.isEmpty():
            return

        # Resize widget to match canvas aspect ratio (no letterboxing)
        canvas_aspect = canvas_rect.width() / canvas_rect.height()
        if canvas_aspect > MINIMAP_WIDTH / MINIMAP_HEIGHT:
            w, h = MINIMAP_WIDTH, max(1, int(MINIMAP_WIDTH / canvas_aspect))
        else:
            h, w = MINIMAP_HEIGHT, max(1, int(MINIMAP_HEIGHT * canvas_aspect))
        if self.width() != w or self.height() != h:
            self.setFixedSize(w, h)
            self._reposition()

        # _render_rect always fills the full widget (no offset)
        self._render_rect = QRectF(0, 0, w, h)

        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.GlobalColor.transparent)

        hidden = self._hide_overlay_items()
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._canvas_scene.render(painter, QRectF(0, 0, w, h), canvas_rect)
        painter.end()
        self._restore_overlay_items(hidden)

        # Flip vertically to match the view's Y-flip transform
        self._thumbnail = pixmap.transformed(QTransform().scale(1, -1))
        self._check_auto_hide()
        self.update()

    def _hide_overlay_items(self) -> list[QGraphicsItem]:
        """Hide screen-space and tool-overlay items before thumbnail render.

        Returns the list of items that were hidden (for later restore).
        """
        hidden: list[QGraphicsItem] = []
        ignore_flag = QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        for item in self._canvas_scene.items():
            if item.isVisible() and (
                bool(item.flags() & ignore_flag) or item.zValue() >= 100
            ):
                item.setVisible(False)
                hidden.append(item)
        return hidden

    def _restore_overlay_items(self, hidden: list[QGraphicsItem]) -> None:
        """Restore items that were hidden before thumbnail render."""
        for item in hidden:
            item.setVisible(True)

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        """Draw the minimap thumbnail, border, and viewport rectangle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.setPen(QPen(_BORDER_COLOR, 1.0))
        painter.setBrush(QBrush(_BG_COLOR))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        # Thumbnail
        if self._thumbnail is not None:
            painter.drawPixmap(0, 0, self._thumbnail)

        # Viewport rectangle
        vp_rect = self._viewport_rect_on_minimap()
        if vp_rect is not None:
            painter.setPen(QPen(_VIEWPORT_STROKE, _VIEWPORT_STROKE_WIDTH))
            painter.setBrush(QBrush(_VIEWPORT_FILL))
            painter.drawRect(vp_rect)

        painter.end()

    # ------------------------------------------------------------------
    # Coordinate mapping
    # ------------------------------------------------------------------

    def _viewport_rect_on_minimap(self) -> QRectF | None:
        """Map the current visible viewport area to minimap coordinates."""
        canvas_rect = self._canvas_scene.canvas_rect
        if canvas_rect.isEmpty():
            return None

        view = self._canvas_view
        vp = view.viewport().rect()

        # Get visible scene rect (handling Y-flip swap)
        tl = view.mapToScene(vp.topLeft())
        br = view.mapToScene(vp.bottomRight())
        min_x = min(tl.x(), br.x())
        max_x = max(tl.x(), br.x())
        min_y = min(tl.y(), br.y())
        max_y = max(tl.y(), br.y())

        rr = self._render_rect
        sx = rr.width() / canvas_rect.width()
        sy = rr.height() / canvas_rect.height()

        # X maps directly within render rect
        rx = rr.x() + (min_x - canvas_rect.x()) * sx
        rw = (max_x - min_x) * sx

        # Y is inverted within render rect: rr.top() = scene max_y visually
        ry = rr.y() + (canvas_rect.height() - (max_y - canvas_rect.y())) * sy
        rh = (max_y - min_y) * sy

        # Clamp to render rect bounds
        rx = max(rr.x(), min(rx, rr.right()))
        ry = max(rr.y(), min(ry, rr.bottom()))
        rw = min(rw, rr.right() - rx)
        rh = min(rh, rr.bottom() - ry)

        return QRectF(rx, ry, rw, rh)

    def _minimap_to_scene(self, x: float, y: float) -> tuple[float, float]:
        """Convert minimap pixel coordinates to scene coordinates."""
        canvas_rect = self._canvas_scene.canvas_rect
        rr = self._render_rect
        sx = canvas_rect.x() + ((x - rr.x()) / rr.width()) * canvas_rect.width()
        # Invert Y within render rect: rr.top() → scene max Y
        sy = canvas_rect.y() + canvas_rect.height() * (1.0 - (y - rr.y()) / rr.height())
        return sx, sy

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Click to pan or start dragging the viewport rectangle."""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position()
        vp_rect = self._viewport_rect_on_minimap()

        if vp_rect is not None and vp_rect.contains(pos):
            # Start dragging the viewport rectangle
            self._dragging = True
            self._drag_offset_x = pos.x() - vp_rect.center().x()
            self._drag_offset_y = pos.y() - vp_rect.center().y()
        else:
            # Click-to-pan: center view on clicked point
            sx, sy = self._minimap_to_scene(pos.x(), pos.y())
            self._canvas_view.centerOn(QPointF(sx, sy))

        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Drag the viewport rectangle to navigate."""
        if self._dragging:
            pos = event.position()
            cx = pos.x() - self._drag_offset_x
            cy = pos.y() - self._drag_offset_y
            sx, sy = self._minimap_to_scene(cx, cy)
            self._canvas_view.centerOn(QPointF(sx, sy))
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """End viewport rectangle drag."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()

    # ------------------------------------------------------------------
    # Auto-hide
    # ------------------------------------------------------------------

    def _check_auto_hide(self) -> None:
        """Hide minimap when entire plan fits in view."""
        if not self._enabled:
            return

        canvas_rect = self._canvas_scene.canvas_rect
        if canvas_rect.isEmpty():
            self.hide()
            return

        view = self._canvas_view
        vp = view.viewport().rect()
        tl = view.mapToScene(vp.topLeft())
        br = view.mapToScene(vp.bottomRight())
        min_x = min(tl.x(), br.x())
        max_x = max(tl.x(), br.x())
        min_y = min(tl.y(), br.y())
        max_y = max(tl.y(), br.y())
        visible = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

        if visible.contains(canvas_rect):
            self.hide()
        else:
            self.show()
