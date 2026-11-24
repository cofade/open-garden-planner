"""One placement owner for a viewport-parented overlay (#1005, ADR-082).

The Plant Grid's control strip used to be moved by hand from the tool's zoom,
scroll and resize paths. That repeated the same clamping arithmetic in four
callbacks and made every new input path responsible for remembering it. This
class subscribes once to the view's geometry changes and places its widget
from a caller-supplied anchor rect instead; the tool only says *what* the
draft occupies, never *where* the strip goes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QObject, QRectF, QTimer
from PyQt6.QtWidgets import QWidget

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class _ViewportResizeWatcher(QObject):
    """Calls back when the viewport is resized.

    An ``AnchorViewCenter`` re-centre after a resize moves the scene through
    the view's alignment, not the scroll bars, so no scroll signal reports it.
    The viewport's Resize event also arrives *before* ``QGraphicsView`` has
    re-centred, so the callback runs one event-loop turn later. The timer is
    a child of this watcher, which is a child of the viewport: it dies with it.
    """

    def __init__(self, viewport: QWidget, callback: Callable[[], None]) -> None:
        super().__init__(viewport)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(callback)
        viewport.installEventFilter(self)

    def eventFilter(self, _watched: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.Resize:
            self._timer.start()
        return False


class ViewportOverlay(QObject):
    """Keep *widget* next to the scene rect *anchor* returns, in view pixels.

    The widget is parented to the viewport by the caller and shown/hidden by
    the tool. Placement is clamped to the viewport and flips above the anchor
    when there is no room below it. A paint never calls :meth:`place`: the
    callers are input and geometry changes only (ADR-082).
    """

    def __init__(
        self,
        view: CanvasView,
        widget: QWidget,
        anchor: Callable[[], QRectF | None],
        *,
        margin: int = 12,
    ) -> None:
        super().__init__(widget)
        self._view = view
        self._widget = widget
        self._anchor = anchor
        self._margin = margin
        viewport = view.viewport()
        assert viewport is not None
        self._resize_watcher = _ViewportResizeWatcher(viewport, self.place)
        view.zoom_changed.connect(self.place)
        for bar in (view.horizontalScrollBar(), view.verticalScrollBar()):
            if bar is not None:
                bar.valueChanged.connect(self.place)

    def place(self, *_args: object) -> None:
        """Move the widget from the current anchor; a hidden widget stays put."""
        widget = self._widget
        if not widget.isVisible():
            return
        viewport = self._view.viewport()
        if viewport is None:
            return
        anchor = self._anchor()
        if anchor is None:
            return
        x = round(anchor.right()) - widget.width()
        y = round(anchor.bottom()) + self._margin
        if y + widget.height() > viewport.height():
            y = round(anchor.top()) - widget.height() - self._margin
        widget.move(
            max(0, min(x, viewport.width() - widget.width())),
            max(0, min(y, viewport.height() - widget.height())),
        )
