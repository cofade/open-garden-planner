"""Hours-of-sun heatmap: QImage rasterizer, worker thread, overlay (US-E4).

ADR-037 route 1: each daylight sample's shadow polygons are painted into a
monochrome ``QImage`` at grid resolution and accumulated with numpy.
``QImage`` painting is documented thread-safe off the GUI thread (unlike
``QPixmap``) — pinned by the 2-thread smoke test in
``tests/integration/test_sun_heatmap.py`` before anything relies on it; the
worker touches ONLY ``QImage``.

Threading shape copies ``_WeatherFetchWorker`` (§8.20 / weather_widget):
a ``QThread`` subclass whose inputs are plain-data snapshots (never live
QGraphicsItems) and whose results arrive via signals on the GUI thread.
The heatmap is recompute-ON-DEMAND (a button), never wired to
``scene.changed`` — it costs seconds, not milliseconds.

Grid/row convention is ``core/shade_aggregation``'s: row 0 = SOUTH edge.
A ``QGraphicsPixmapItem`` placed at the grid origin draws row *r* at scene
y ``y0 + r·cell``; the view's Y-flip then renders larger scene-y (north)
higher on screen — no extra flip anywhere (§8.20), pinned by the §8.19
pixel-band integration test.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import numpy as np
from PyQt6.QtCore import QObject, QPointF, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap, QPolygonF
from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

from open_garden_planner.core.shade_aggregation import (
    GRID_CELL_CM,
    HeatmapGrid,
    band_grid,
    compute_heatmap,
)
from open_garden_planner.core.shadow_geometry import Polygon

from .sun_shadow_controller import collect_shadow_casters

# Band colors, index 0..3 (deep shade → full sun). Full sun is fully
# transparent — the garden shows through where the light is good.
BAND_COLORS: tuple[QColor, ...] = (
    QColor(40, 52, 84, 150),  # < 2 h — deep shade
    QColor(72, 92, 145, 110),  # 2–4 h — light shade
    QColor(205, 185, 95, 80),  # 4–6 h — partial sun
    QColor(0, 0, 0, 0),  # ≥ 6 h — full sun (transparent)
)

#: Above the background image (−1000) and the shadow overlay (−500),
#: below every layer item (≥ 0).
_HEATMAP_Z = -450.0

def legend_swatch_hexes() -> list[str]:
    """Opaque display hex per band — BAND_COLORS alpha-blended over the
    default canvas color, so the legend tracks the real overlay tints
    (band→legend is single-source; pinned by test). The blend base is the
    DEFAULT canvas color — a theme override shifts the on-canvas blend
    slightly, which a static legend approximation accepts."""
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    background = CanvasScene.CANVAS_COLOR
    hexes: list[str] = []
    for color in BAND_COLORS:
        alpha = color.alphaF()
        blended = QColor(
            round(color.red() * alpha + background.red() * (1 - alpha)),
            round(color.green() * alpha + background.green() * (1 - alpha)),
            round(color.blue() * alpha + background.blue() * (1 - alpha)),
        )
        hexes.append(blended.name())
    return hexes


def rasterize_polygons_qimage(
    polygons: list[Polygon], grid: HeatmapGrid
) -> np.ndarray:
    """Paint shadow polygons into a grid-resolution mask (True = shaded).

    Runs on the worker thread — QImage only. Odd-even fill matches the
    shadow overlay's rule (union holes stay sunny).
    """
    image = QImage(grid.cols, grid.rows, QImage.Format.Format_Grayscale8)
    image.fill(0)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        painter.scale(1.0 / grid.cell_cm, 1.0 / grid.cell_cm)
        painter.translate(-grid.x0_cm, -grid.y0_cm)
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        for polygon in polygons:
            path.addPolygon(QPolygonF([QPointF(x, y) for x, y in polygon]))
            path.closeSubpath()
        painter.drawPath(path)
    finally:
        painter.end()
    pointer = image.bits()
    pointer.setsize(image.sizeInBytes())
    raw = np.frombuffer(pointer, np.uint8).reshape(
        grid.rows, image.bytesPerLine()
    )[:, : grid.cols]
    return (raw > 127).copy()


def build_heatmap_image(sun_minutes: np.ndarray) -> QImage:
    """Band-colored ARGB image, one pixel per grid cell (GUI thread)."""
    bands = band_grid(sun_minutes)
    # Format_ARGB32 on little-endian is B,G,R,A per pixel.
    palette = np.array(
        [(c.blue(), c.green(), c.red(), c.alpha()) for c in BAND_COLORS],
        dtype=np.uint8,
    )
    rgba = palette[bands]
    rows, cols = bands.shape
    image = QImage(
        rgba.tobytes(), cols, rows, cols * 4, QImage.Format.Format_ARGB32
    )
    return image.copy()  # detach from the numpy buffer


class SunHeatmapOverlayItem(QGraphicsPixmapItem):
    """Marker subclass — runtime-only, never serialized (not in the
    ``project._serialize_item`` whitelist; pinned by test)."""

    def __init__(self) -> None:
        super().__init__()
        self.setZValue(_HEATMAP_Z)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setTransformationMode(Qt.TransformationMode.FastTransformation)


class HeatmapWorker(QThread):
    """Computes one day's heatmap off the GUI thread (plain-data inputs)."""

    progress = pyqtSignal(int, int)
    success = pyqtSignal(object)  # np.ndarray sun-minutes

    def __init__(
        self,
        casters: list[tuple[Polygon, float]],
        lat_deg: float,
        lon_deg: float,
        day: date,
        grid: HeatmapGrid,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._casters = casters
        self._lat = lat_deg
        self._lon = lon_deg
        self._day = day
        self._grid = grid
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # worker thread
        minutes = compute_heatmap(
            self._casters,
            self._lat,
            self._lon,
            self._day,
            self._grid,
            rasterize_polygons_qimage,
            progress=lambda done, total: self.progress.emit(done, total),
            should_cancel=lambda: self._cancelled,
        )
        if minutes is not None and not self._cancelled:
            self.success.emit(minutes)


# NOTE on the sampling window: ``daylight_samples`` walks the UTC civil day.
# Far from Greenwich that window is offset against the local day, but over
# any 24 h UTC window the sun still completes one full diurnal arc, so
# per-cell daily totals are preserved to within day-to-day declination
# drift — do NOT "fix" this into a local-day loop.


class SunHeatmapController(QObject):
    """Owns the heatmap worker + overlay. Recompute on demand only."""

    started = pyqtSignal()
    progress = pyqtSignal(int, int)
    #: bool = success (False: cancelled / no location)
    finished = pyqtSignal(bool)

    def __init__(
        self,
        scene: QGraphicsScene,
        location_provider: Callable[[], dict[str, Any] | None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene = scene
        self._location_provider = location_provider
        self._overlay: SunHeatmapOverlayItem | None = None
        self._worker: HeatmapWorker | None = None
        self._grid: HeatmapGrid | None = None
        self._computed_day: date | None = None
        #: Test instrument — number of worker launches.
        self.run_count = 0
        #: Last computed minutes grid (tests / future tooltips).
        self.last_minutes: np.ndarray | None = None
        #: Grid of the last launch (cell lookup for tests / tooltips).
        self.last_grid: HeatmapGrid | None = None

    # ── public API ─────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    @property
    def computed_day(self) -> date | None:
        return self._computed_day

    def heatmap_visible(self) -> bool:
        overlay = self._alive_overlay()
        return overlay is not None and overlay.isVisible()

    def run_for_day(self, day: date, cell_cm: float = GRID_CELL_CM) -> bool:
        """Snapshot the scene and launch the worker. False if it can't run
        (no location / already running — incl. a just-cancelled worker still
        winding down; the button re-enables on its ``finished``)."""
        if self.is_running:
            return False
        location = self._location_provider()
        latitude = location.get("latitude") if isinstance(location, dict) else None
        longitude = location.get("longitude") if isinstance(location, dict) else None
        if latitude is None or longitude is None:
            return False
        width = getattr(self._scene, "width_cm", None)
        height = getattr(self._scene, "height_cm", None)
        if width is None or height is None:  # plain QGraphicsScene fallback
            rect = self._scene.sceneRect()
            x0, y0, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        else:
            x0, y0, w, h = 0.0, 0.0, float(width), float(height)
        grid = HeatmapGrid.for_rect(x0, y0, w, h, cell_cm)
        # US-E8: heatmap sees the same date-projected plant sizes as the
        # shadow overlay — one growth timeline everywhere.
        casters = collect_shadow_casters(self._scene, at_date=day)
        worker = HeatmapWorker(casters, latitude, longitude, day, grid, self)
        worker.progress.connect(self.progress)
        worker.success.connect(self._on_success)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._grid = grid
        self.last_grid = grid
        self._computed_day = day
        self._success_seen = False
        self._result_wanted = True
        self.run_count += 1
        worker.start()
        self.started.emit()
        return True

    def clear(self) -> None:
        """Hide the overlay AND drop any in-flight compute.

        Cancelling matters: on a large canvas the compute takes seconds, and
        a date change / sim-off mid-compute must not let ``_on_success``
        paint an orphaned or stale-day map afterwards (senior-review P1).
        There is no result caching, so a cancelled compute buys nothing.
        """
        self._result_wanted = False
        self.cancel()
        overlay = self._alive_overlay()
        if overlay is not None:
            overlay.setVisible(False)

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Cancel + join the worker — call before teardown (a QThread
        destroyed while running aborts the process, the #230 class)."""
        worker = self._worker
        if worker is not None:
            worker.cancel()
            worker.wait(timeout_ms)

    # ── internals ──────────────────────────────────────────────

    def _on_success(self, minutes: np.ndarray) -> None:  # GUI thread
        grid = self._grid
        # A clear() may land between the worker's success emission and this
        # queued slot — the result is no longer wanted, don't paint it.
        if grid is None or not getattr(self, "_result_wanted", True):
            return
        self.last_minutes = minutes
        image = build_heatmap_image(minutes)
        overlay = self._ensure_overlay()
        overlay.setPixmap(QPixmap.fromImage(image))
        overlay.setScale(grid.cell_cm)
        overlay.setPos(grid.x0_cm, grid.y0_cm)
        overlay.setVisible(True)
        self._success_seen = True

    def _on_worker_finished(self) -> None:  # GUI thread
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self.finished.emit(bool(getattr(self, "_success_seen", False)))

    def _alive_overlay(self) -> SunHeatmapOverlayItem | None:
        overlay = self._overlay
        if overlay is None:
            return None
        try:
            if overlay.scene() is not self._scene:
                self._overlay = None
                return None
        except RuntimeError:  # C++ object deleted by scene.clear()
            self._overlay = None
            return None
        return overlay

    def _ensure_overlay(self) -> SunHeatmapOverlayItem:
        overlay = self._alive_overlay()
        if overlay is None:
            overlay = SunHeatmapOverlayItem()
            self._scene.addItem(overlay)
            self._overlay = overlay
        return overlay
