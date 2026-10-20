"""One exposure-readiness boundary for GUI and agent visual exports."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from concurrent.futures import Future, TimeoutError
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar, cast

from PyQt6.QtCore import QObject, Qt, QThread, QTimer
from PyQt6.QtWidgets import QProgressDialog, QWidget

from open_garden_planner.ui.canvas.sun_exposure_snapshot import ExposureSnapshot
from open_garden_planner.ui.live_sun_map import LiveSunMap

T = TypeVar("T")


@dataclass(frozen=True)
class _ExportRequest:
    ready: Future[ExposureSnapshot | None]
    generation: int
    revision: int
    wall: datetime


class SunExportGate(QObject):
    def __init__(self, live: LiveSunMap, toolbar: Any, parent: QWidget) -> None:
        super().__init__(parent)
        self.live, self.toolbar = live, toolbar
        self.timeout_s = 30.0
        self._leases = 0
        self._resume = False

    def _begin(self) -> _ExportRequest:
        if self._leases == 0:
            self._resume = self.toolbar.animation_active
            self.toolbar.stop_animation()
        self._leases += 1
        try:
            return _ExportRequest(self.live.ensure_current(), getattr(self.live.scene, "_document_generation", 0),
                                  self.live.scene.plan_revision, self.live.clock.wall)
        except Exception:
            self._end()
            raise

    def _end(self) -> None:
        self._leases -= 1
        if self._leases == 0 and self._resume and not self.live._closed:
            self.toolbar.set_animation_active(True)

    def _render(self, request: _ExportRequest, action: Callable[[], T]) -> T:
        if (request.generation != getattr(self.live.scene, "_document_generation", 0)
                or request.revision != self.live.scene.plan_revision
                or request.wall != self.live.clock.wall):
            raise RuntimeError(self.tr("The garden changed during export. Please retry."))
        self.live.validate_export(request.ready.result())
        return action()

    def run_gui(self, action: Callable[[], T]) -> T:
        request = self._begin()
        future = request.ready
        try:
            if not future.done():
                parent = self.parent()
                progress = QProgressDialog(self.tr("Updating Hours of Sun for export…"), self.tr("Cancel"),
                                           0, 0, parent if isinstance(parent, QWidget) else None)
                progress.setWindowModality(Qt.WindowModality.ApplicationModal)
                progress.setMinimumDuration(0)
                poll = QTimer(progress)
                poll.setInterval(20)
                def check() -> None:
                    if future.done():
                        progress.accept()
                poll.timeout.connect(check)
                deadline = QTimer(progress)
                deadline.setSingleShot(True)
                def expired() -> None:
                    if not future.done():
                        future.set_exception(TimeoutError(self.tr("Sun-map calculation timed out. Please retry.")))
                    progress.accept()
                deadline.timeout.connect(expired)
                poll.start()
                deadline.start(round(self.timeout_s * 1000))
                progress.exec()
                poll.stop()
                deadline.stop()
                progress.deleteLater()
                if not future.done():
                    future.cancel()
                    raise RuntimeError(self.tr("Export canceled."))
            return self._render(request, action)
        finally:
            self._end()

    def run_worker(self, bridge: Any, action: Callable[[], T]) -> T:
        if QThread.currentThread() is self.thread():
            return self.run_gui(action)
        request = bridge.run_on_main(self._begin)
        future = request.ready
        try:
            try:
                future.result(timeout=self.timeout_s)
            except TimeoutError as error:
                raise TimeoutError(self.tr("Sun-map calculation timed out. Please retry.")) from error
            return cast(T, bridge.run_on_main(lambda: self._render(request, action)))
        finally:
            future.cancel()
            with contextlib.suppress(RuntimeError):
                bridge.run_on_main(self._end)
