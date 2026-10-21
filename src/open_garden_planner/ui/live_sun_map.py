"""User intent and latest-request scheduling around the single heatmap worker."""

from __future__ import annotations

import contextlib
from concurrent.futures import Future, InvalidStateError
from typing import Any

from PyQt6.QtCore import QObject, QTimer

from open_garden_planner.ui.canvas.sun_exposure_snapshot import (
    ExposureSnapshot,
    collect_exposure_snapshot,
)
from open_garden_planner.ui.sim_clock_subscription import connect_qobject


class LiveSunMap(QObject):
    """Retain a dated preview, but publish measurements only for current inputs."""

    def __init__(self, scene: Any, clock: Any, project: Any, heatmap: Any,
                 toolbar: Any, commands: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene, self.clock, self.project = scene, clock, project
        self.heatmap, self.toolbar = heatmap, toolbar
        self.enabled = False
        self._closed = False
        self._desired: ExposureSnapshot | None = None
        self._failed: ExposureSnapshot | None = None
        self._inputs_dirty = False
        self._status: tuple[Any, ...] | None = None
        self._waiters: list[Future[ExposureSnapshot | None]] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._start_latest)
        connect_qobject(clock.date_changed, self.schedule)
        scene.plan_changed.connect(self.schedule)
        scene.timeline_changed.connect(self.schedule)
        commands.stack_changed.connect(self.schedule)
        project.location_changed.connect(self.schedule)
        scene.document_replaced.connect(self.reset_document)
        heatmap.finished.connect(self._finished)
        heatmap.exposure_changed.connect(self._reflect)
        toolbar.heatmap_requested.connect(lambda: self.set_enabled(True))
        toolbar.heatmap_cleared.connect(lambda: self.set_enabled(False))

    def _snapshot(self) -> ExposureSnapshot:
        return collect_exposure_snapshot(self.scene, self.project.location, self.clock.plan_date)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self._failed = None
        self.toolbar.set_heatmap_active(enabled)
        if not enabled:
            self._timer.stop()
            self._desired = None
            self.heatmap.clear()
            self._fail_waiters(RuntimeError(self.tr("Hours of Sun was switched off during export.")))
        else:
            self.schedule()
        self._reflect()

    def schedule(self, *_args: Any) -> None:
        if self._closed or not self.enabled:
            return
        self._inputs_dirty = True
        self._failed = None
        shown = self.heatmap.displayed_snapshot
        # Spatial identity is O(1); collecting casters/receivers waits for debounce.
        rect = self.scene.sceneRect()
        width, height = getattr(self.scene, "width_cm", None), getattr(self.scene, "height_cm", None)
        bounds = ((0.0, 0.0, float(width), float(height)) if width is not None and height is not None
                  else (rect.x(), rect.y(), rect.width(), rect.height()))
        location = self.project.location or {}
        if shown is not None and (shown.generation, shown.latitude, shown.longitude, shown.bounds) != (
                getattr(self.scene, "_document_generation", 0), location.get("latitude"),
                location.get("longitude"), bounds):
            self.heatmap.clear()
        self.heatmap.suspend_measurements()
        if self.heatmap.snapshot is not None and self.heatmap.snapshot.day != self.clock.plan_date:
            self.heatmap.invalidate_exposure()
        self._timer.start()
        self._reflect()

    def _start_latest(self) -> None:
        if self._closed or not self.enabled:
            return
        self._desired = self._snapshot()
        self._inputs_dirty = False
        if self.heatmap.snapshot != self._desired:
            self.heatmap.invalidate_exposure()
        if self._desired.latitude is None or self._desired.longitude is None:
            self._failed = self._desired
            self._fail_waiters(RuntimeError(self.tr("Set a garden location before computing Hours of Sun.")))
        elif self.heatmap.displayed_snapshot == self._desired:
            self.heatmap.restore_displayed_measurements()
            self._resolve_waiters()
        elif not self.heatmap.result_pending and self._failed != self._desired:
            if not self.heatmap.run_for_day(self.clock.plan_date):
                self._failed = self._desired
                self._fail_waiters(RuntimeError(self.tr("Hours of Sun could not be computed.")))
        self._reflect()

    def _finished(self, success: bool) -> None:
        if self._closed or not self.enabled:
            return
        if self._inputs_dirty:
            if not self._timer.isActive():
                self._timer.start()
        elif success and self.is_current():
            self._resolve_waiters()
        elif self.heatmap.snapshot == self._desired and self.heatmap._result_wanted:
            self._failed = self._desired
            self._fail_waiters(RuntimeError(self.tr("Hours of Sun could not be computed.")))
        elif not self._timer.isActive():
            self._timer.start(0)  # the canceled worker has finally released ownership
        self._reflect()

    def is_current(self) -> bool:
        return (self.enabled and self.heatmap.exposure_reason == "ready"
                and not self._inputs_dirty and self.heatmap.displayed_snapshot == self._desired)

    def ensure_current(self) -> Future[ExposureSnapshot | None]:
        """Called on Qt; the returned Future can be waited on outside Qt."""
        future: Future[ExposureSnapshot | None] = Future()
        self._waiters = [waiter for waiter in self._waiters if not waiter.done()]
        if self._closed:
            future.set_exception(RuntimeError(self.tr("The garden is closing.")))
        elif not self.enabled:
            future.set_result(None)
        else:
            self._waiters.append(future)
            # Export is a trust boundary: verify even when no notification was emitted.
            self._timer.stop()
            self._start_latest()
            if self._failed == self._desired:
                self._fail_waiters(RuntimeError(self.tr("Hours of Sun could not be computed.")))
        return future

    def validate_export(self, snapshot: ExposureSnapshot | None) -> None:
        if snapshot is None:
            if self.enabled:
                raise RuntimeError(self.tr("Sun-map settings changed during export. Please retry."))
            return
        if not self.is_current() or snapshot != self.heatmap.displayed_snapshot or snapshot != self._snapshot():
            raise RuntimeError(self.tr("The garden changed during export. Please retry."))

    def _resolve_waiters(self) -> None:
        waiters, self._waiters = self._waiters, []
        for future in waiters:
            if not future.done():
                with contextlib.suppress(InvalidStateError):  # caller may cancel from its worker thread
                    future.set_result(self.heatmap.displayed_snapshot)

    def _fail_waiters(self, error: Exception) -> None:
        waiters, self._waiters = self._waiters, []
        for future in waiters:
            if not future.done():
                with contextlib.suppress(InvalidStateError):
                    future.set_exception(error)

    def _reflect(self) -> None:
        if self._closed:
            return
        with contextlib.suppress(RuntimeError):
            shown = self.heatmap.displayed_snapshot
            updating = self.enabled and not self.is_current() and self._failed is None
            unavailable = self.tr("Sun map unavailable") if self.enabled and self._failed is not None else ""
            status = (shown.day if shown else None, updating, unavailable)
            if status != self._status:
                self._status = status
                self.toolbar.set_heatmap_busy(updating)
                self.toolbar.set_map_status(*status)

    def reset_document(self) -> None:
        self._timer.stop()
        self._desired = self._failed = None
        self._inputs_dirty = False
        self.enabled = False
        self._fail_waiters(RuntimeError(self.tr("The garden document was replaced during export.")))
        self.heatmap.clear()
        self.toolbar.set_heatmap_active(False)
        self._reflect()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self._fail_waiters(RuntimeError(self.tr("The garden is closing.")))
