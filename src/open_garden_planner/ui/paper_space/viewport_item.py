"""Paper-space viewport: a rectangular "window" onto the model scene.

A ``ViewportItem`` is the bridge between the model-space ``CanvasScene``
(where the user draws) and a paper-space ``PaperSpaceScene`` (where the
user composes a print layout). The item paints a region of the model
scene into its own rectangle, scaled, with the usual overlay-hiding
applied.

The viewport caches its render as a ``QPixmap``; the cache is
invalidated when the source scene's ``changed`` signal fires or when
the viewport's source rect / scale / size is mutated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.services.scene_rendering import render_scene_region

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

# Cap render resolution so a huge viewport on a high-DPI display doesn't
# allocate a giant pixmap. The cache is regenerated only when the source
# scene changes, so a few hundred pixels per side is plenty for paper-
# space preview at typical print densities.
_MAX_PIXMAP_DIM = 2400  # px per side

# Coalesce rapid ``source_scene.changed`` bursts (a single drag emits
# many) into one cache rebuild. The trade-off: model edits show up in
# the paper-space view with a ~150 ms lag, which is invisible in normal
# tab-switching workflows.
_INVALIDATION_DEBOUNCE_MS = 150


class _InvalidationDebouncer(QObject):
    """Tiny QObject helper so the viewport can own a QTimer.

    ``QGraphicsRectItem`` doesn't inherit from ``QObject``, so it can't
    receive ``QTimer`` events directly. This wrapper exists purely to
    hold the debouncing timer and call back into the viewport when it
    fires.
    """

    def __init__(self, viewport: ViewportItem) -> None:
        super().__init__()
        self._viewport = viewport
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_INVALIDATION_DEBOUNCE_MS)
        self._timer.timeout.connect(self._fire)

    def schedule(self) -> None:
        # Restarts the timer if already running — coalesces bursts.
        self._timer.start()

    def cancel(self) -> None:
        self._timer.stop()

    def _fire(self) -> None:
        self._viewport.invalidate_cache()


class ViewportItem(QGraphicsRectItem):
    """Rectangular viewport that mirrors a region of the source scene.

    Coordinates:
        - The item's own rect (``self.rect()``) is the *paper-space*
          extent in cm. (0,0) at the top-left of the viewport in
          item-local coords.
        - ``source_rect`` is the region of the source scene visible
          through the viewport, in *scene* coords (cm).
        - ``scale_factor`` is the ratio paper-space-cm / model-space-cm.
          A 1:100 print → scale_factor = 0.01.
    """

    def __init__(
        self,
        source_scene: CanvasScene,
        source_rect: QRectF,
        paper_rect: QRectF,
    ) -> None:
        super().__init__(paper_rect)
        self._source_scene = source_scene
        self._source_rect = QRectF(source_rect)
        self._cached_pixmap: QPixmap | None = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        pen = QPen(QColor(80, 80, 80), 0.4)
        pen.setCosmetic(False)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(245, 245, 245)))

        # Watch the source scene for any change — items added, moved,
        # styled, etc. Each change schedules a debounced cache rebuild
        # so a drag burst (many ``changed`` signals per second) doesn't
        # collapse the cache on every signal. ``_signal_connected`` lets
        # ``cleanup()`` disconnect exactly once even if it's called
        # multiple times.
        self._debouncer = _InvalidationDebouncer(self)
        source_scene.changed.connect(self._on_source_changed)
        self._signal_connected = True

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def source_rect(self) -> QRectF:
        """Region of the source scene visible through the viewport."""
        return QRectF(self._source_rect)

    @source_rect.setter
    def source_rect(self, value: QRectF) -> None:
        self._source_rect = QRectF(value)
        self.invalidate_cache()

    @property
    def scale_factor(self) -> float:
        """Paper-cm per model-cm. Smaller scale → more model in less paper."""
        sw = self._source_rect.width()
        if sw <= 0:
            return 1.0
        return self.rect().width() / sw

    def set_paper_rect(self, rect: QRectF) -> None:
        """Move/resize the viewport within paper space."""
        self.setRect(rect)
        self.invalidate_cache()

    def set_scale(self, scale_factor: float) -> None:
        """Set paper-cm-per-model-cm by adjusting the source rect's size.

        The source rect's centre stays put. Use this to zoom the
        viewport's content without moving the viewport on the page.
        """
        if scale_factor <= 0:
            return
        new_w = self.rect().width() / scale_factor
        new_h = self.rect().height() / scale_factor
        cx = self._source_rect.x() + self._source_rect.width() / 2.0
        cy = self._source_rect.y() + self._source_rect.height() / 2.0
        self._source_rect = QRectF(
            cx - new_w / 2.0, cy - new_h / 2.0, new_w, new_h
        )
        self.invalidate_cache()

    # ── Cache management ───────────────────────────────────────────────

    def invalidate_cache(self) -> None:
        """Drop the cached pixmap so the next paint regenerates it."""
        self._cached_pixmap = None
        self.update()

    def _on_source_changed(self, _region: object = None) -> None:
        # Don't invalidate immediately — schedule a debounced rebuild
        # so a burst of ``scene.changed`` signals (e.g. mid-drag)
        # coalesces into one pixmap rebuild instead of N.
        self._debouncer.schedule()

    def cleanup(self) -> None:
        """Disconnect from the source scene's ``changed`` signal.

        Called by ``PaperSpaceScene.load_from_dict`` before clearing the
        scene so the slot doesn't fire on a half-destroyed item. Safe to
        call multiple times — the ``_signal_connected`` flag guards
        against the second disconnect raising.
        """
        import contextlib

        if self._signal_connected:
            # Already disconnected, or source scene was destroyed —
            # neither is a real failure here, so swallow.
            with contextlib.suppress(TypeError, RuntimeError):
                self._source_scene.changed.disconnect(self._on_source_changed)
            self._signal_connected = False
            self._debouncer.cancel()

    def _build_pixmap(self) -> QPixmap:
        """Render the source region into a fresh pixmap at the item's size."""
        r = self.rect()
        # Convert paper-cm to pixels: 1 cm at 96 px/in = 37.795 px. Bump
        # to 150 DPI equivalent (≈ 59 px/cm) for legibility.
        px_per_cm = 59.0
        target_w = int(max(1.0, r.width()) * px_per_cm)
        target_h = int(max(1.0, r.height()) * px_per_cm)
        # Cap so a giant viewport doesn't blow out memory.
        if target_w > _MAX_PIXMAP_DIM:
            shrink = _MAX_PIXMAP_DIM / target_w
            target_w = _MAX_PIXMAP_DIM
            target_h = max(1, int(target_h * shrink))
        if target_h > _MAX_PIXMAP_DIM:
            shrink = _MAX_PIXMAP_DIM / target_h
            target_h = _MAX_PIXMAP_DIM
            target_w = max(1, int(target_w * shrink))

        pixmap = QPixmap(target_w, target_h)
        pixmap.fill(QColor(255, 255, 255))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        try:
            render_scene_region(
                scene=self._source_scene,
                painter=painter,
                target_rect=QRectF(0, 0, target_w, target_h),
                source_rect=self._source_rect,
                hide_overlays=True,
                hide_construction=True,
                text_point_size=8,
            )
        finally:
            painter.end()
        return pixmap

    # ── Painting ───────────────────────────────────────────────────────

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        # Background frame.
        super().paint(painter, option, widget)

        if self._cached_pixmap is None or self._cached_pixmap.isNull():
            self._cached_pixmap = self._build_pixmap()

        painter.save()
        painter.drawPixmap(self.rect(), self._cached_pixmap, QRectF(self._cached_pixmap.rect()))
        painter.restore()

        # Re-paint the border on top so the pixmap's edges look clean.
        painter.save()
        pen = self.pen()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())
        painter.restore()

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict[str, float | str]:
        """Serialize the viewport for project save (paper_layouts entry)."""
        r = self.rect()
        pos = self.pos()
        sr = self._source_rect
        return {
            "type": "viewport",
            "paper_x": pos.x(),
            "paper_y": pos.y(),
            "paper_w": r.width(),
            "paper_h": r.height(),
            "source_x": sr.x(),
            "source_y": sr.y(),
            "source_w": sr.width(),
            "source_h": sr.height(),
        }

    @classmethod
    def from_dict(
        cls,
        source_scene: CanvasScene,
        data: dict[str, float | str],
    ) -> ViewportItem:
        item = cls(
            source_scene=source_scene,
            source_rect=QRectF(
                float(data["source_x"]),
                float(data["source_y"]),
                float(data["source_w"]),
                float(data["source_h"]),
            ),
            paper_rect=QRectF(
                0.0, 0.0, float(data["paper_w"]), float(data["paper_h"])
            ),
        )
        item.setPos(QPointF(float(data["paper_x"]), float(data["paper_y"])))
        return item

    # ── Mouse handling: resize via shift-drag corners ──────────────────

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        # Reserved for opening a viewport-properties dialog in a future
        # iteration; for the MVP a double-click just forwards to the
        # default selection behaviour.
        super().mouseDoubleClickEvent(event)
