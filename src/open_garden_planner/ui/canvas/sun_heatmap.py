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
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from open_garden_planner.core.heatmap_render import (
    build_sun_lut,
    hour_levels,
    iso_segments,
    sun_fraction,
)
from open_garden_planner.core.shade_aggregation import (
    GRID_CELL_CM,
    SAMPLE_STEP_MINUTES,
    HeatmapGrid,
    compute_heatmap,
    daylight_samples,
)
from open_garden_planner.core.shadow_geometry import Polygon

from .sun_shadow_controller import collect_shadow_casters

#: Above the background image (−1000) and the shadow overlay (−500), below
#: every layer item (≥ 0). Contour lines and their hour labels sit just above
#: the fill, still behind user content.
_HEATMAP_Z = -450.0
_CONTOUR_Z = -449.0
_LABEL_Z = -448.0

# Dark cool ink for the topographic hour lines + a light halo for their labels.
_CONTOUR_COLOR = QColor(24, 30, 54, 205)
_LABEL_TEXT_COLOR = QColor(18, 22, 42)
_LABEL_HALO_COLOR = QColor(255, 255, 255, 220)

# Cool→warm sun ramp LUT (single source of truth, core/heatmap_render). ARGB32
# is B,G,R,A on little-endian, so keep a reordered copy for direct pixel packing.
_SUN_LUT_BGRA = build_sun_lut()[:, [2, 1, 0, 3]].copy()


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


def build_heatmap_image(
    sun_minutes: np.ndarray, daylight_minutes: float
) -> QImage:
    """Continuous cool→warm ARGB image, one pixel per grid cell (GUI thread).

    Each cell's sun-minutes are normalized against the day's daylight duration
    and mapped through the shared sun ramp LUT (single source of truth for the
    tints). The overlay draws this with SmoothTransformation, so the coarse grid
    renders as a smooth surface rather than hard blocks.
    """
    fraction = sun_fraction(sun_minutes, daylight_minutes)
    n = _SUN_LUT_BGRA.shape[0]
    idx = np.clip(np.round(fraction * (n - 1)).astype(np.intp), 0, n - 1)
    bgra = _SUN_LUT_BGRA[idx]  # (rows, cols, 4) uint8, B,G,R,A
    rows, cols = fraction.shape
    image = QImage(
        bgra.tobytes(), cols, rows, cols * 4, QImage.Format.Format_ARGB32
    )
    return image.copy()  # detach from the temporary buffer


class SunHeatmapOverlayItem(QGraphicsPixmapItem):
    """Marker subclass — runtime-only, never serialized (not in the
    ``project._serialize_item`` whitelist; pinned by test)."""

    def __init__(self) -> None:
        super().__init__()
        self.setZValue(_HEATMAP_Z)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)


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
        #: Runtime-only contour lines + hour labels (rebuilt on each success).
        self._contour_items: list[QGraphicsItem] = []
        #: Full daylight duration (min) of the last launched day — ramp scale.
        self._daylight_minutes: float = 0.0

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
        self._daylight_minutes = float(
            len(daylight_samples(latitude, longitude, day)) * SAMPLE_STEP_MINUTES
        )
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
        self._clear_contours()

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
        image = build_heatmap_image(minutes, self._daylight_minutes)
        overlay = self._ensure_overlay()
        overlay.setPixmap(QPixmap.fromImage(image))
        overlay.setScale(grid.cell_cm)
        overlay.setPos(grid.x0_cm, grid.y0_cm)
        overlay.setVisible(True)
        self._rebuild_contours(minutes, grid)
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

    # ── contour lines + hour labels ─────────────────────────

    def _grid_to_scene(
        self, point: tuple[float, float], grid: HeatmapGrid
    ) -> tuple[float, float]:
        """Grid (col, row) → scene cm, at the cell CENTRE (matches the raster)."""
        col, row = point
        return (
            grid.x0_cm + (col + 0.5) * grid.cell_cm,
            grid.y0_cm + (row + 0.5) * grid.cell_cm,
        )

    def _clear_contours(self) -> None:
        for item in self._contour_items:
            try:
                scene = item.scene()
            except RuntimeError:  # C++ object already deleted by scene.clear()
                continue
            if scene is not None:
                scene.removeItem(item)
        self._contour_items = []

    def _rebuild_contours(
        self, minutes: np.ndarray, grid: HeatmapGrid
    ) -> None:
        """Draw one topographic line per whole hour of sun; labels on even hours.

        Runtime-only ``QGraphicsPathItem`` / ``QGraphicsSimpleTextItem`` — not
        ``GardenItemMixin``, so ``project._serialize_item_core`` drops them, and
        their negative z keeps them behind user content.
        """
        self._clear_contours()
        max_minutes = float(minutes.max()) if minutes.size else 0.0
        for threshold in hour_levels(max_minutes):
            segments = iso_segments(minutes, threshold)
            if not segments:
                continue
            hour = threshold // 60
            even = hour % 2 == 0
            path = QPainterPath()
            for start, end in segments:
                sx, sy = self._grid_to_scene(start, grid)
                ex, ey = self._grid_to_scene(end, grid)
                path.moveTo(sx, sy)
                path.lineTo(ex, ey)
            line = QGraphicsPathItem(path)
            pen = QPen(_CONTOUR_COLOR)
            pen.setCosmetic(True)  # crisp, ~constant width at any zoom
            pen.setWidthF(1.6 if even else 0.7)
            line.setPen(pen)
            line.setZValue(_CONTOUR_Z)
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self._scene.addItem(line)
            self._contour_items.append(line)
            if even:
                label = self._make_hour_label(hour, segments, grid)
                self._scene.addItem(label)
                self._contour_items.append(label)

    def _make_hour_label(
        self,
        hour: int,
        segments: list[tuple[tuple[float, float], tuple[float, float]]],
        grid: HeatmapGrid,
    ) -> QGraphicsSimpleTextItem:
        """A zoom-stable '{n} h' label at a representative point on the contour.

        Reuses the dimension-line idiom: ``ItemIgnoresTransformations`` keeps the
        text a fixed on-screen size, with a light halo pen for legibility over
        the coloured map.
        """
        (ax, ay), (bx, by) = segments[len(segments) // 2]
        mid = ((ax + bx) / 2.0, (ay + by) / 2.0)
        sx, sy = self._grid_to_scene(mid, grid)
        label = QGraphicsSimpleTextItem(self.tr("{n} h").format(n=hour))
        label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        label.setFont(font)
        label.setBrush(QBrush(_LABEL_TEXT_COLOR))
        halo = QPen(_LABEL_HALO_COLOR)
        halo.setWidthF(1.5)
        label.setPen(halo)
        label.setZValue(_LABEL_Z)
        label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        label.setPos(sx, sy)
        return label
