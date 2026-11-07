"""App-level forecast holder keyed by place (ADR-070 addendum, #693).

The weather forecast is application-level data keyed by GPS coordinates (lat, lon).
Previously it was owned by WeatherWidget on the Planting Calendar tab (often hidden),
causing redundant fetch threads and calendar dashboard rebuilds on every 3D pick of
Today's Weather, as well as race conditions when documents were replaced (PF-LIF-12).

ForecastHolder decouples forecast data ownership:
- Coordinates and generation counter track validity.
- document_replaced invalidates the held forecast and cancels in-flight workers.
- location_changed updates coordinates without fetching; subscribers (3D view when
  Today's Weather is active, or Planting Calendar on refresh) ask on demand.
- Repeat asks are coalesced through a zero-timer.
- Results whose coordinates or generation do not match current state are dropped.
- A 3D pick (forecast_wanted) with a fresh held forecast re-emits synchronously
  without spawning a background thread or rebuilding the hidden dashboard.
- Subscribers (3D view, Planting Calendar, Tasks tab) subscribe to its signals.
"""

from __future__ import annotations

import datetime

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from open_garden_planner.services.weather_service import WeatherForecast
from open_garden_planner.ui.widgets import weather_widget


class ForecastHolder(QObject):
    """Application-owned weather forecast holder keyed by coordinates."""

    forecast_ready = pyqtSignal(object)  # WeatherForecast
    forecast_failed = pyqtSignal(str)
    forecast_cleared = pyqtSignal()
    forecast_days_ready = pyqtSignal(object, object)  # (place, tuple_of_days)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lat: float | None = None
        self._lon: float | None = None
        self._forecast: WeatherForecast | None = None
        self._fetched_at: datetime.datetime | None = None
        self._generation: int = 0
        self._worker: weather_widget._WeatherFetchWorker | None = None

        self._coalesce_timer = QTimer(self)
        self._coalesce_timer.setSingleShot(True)
        self._coalesce_timer.setInterval(0)
        self._coalesce_timer.timeout.connect(self._on_coalesce_timeout)

    def place(self) -> tuple[float, float] | None:
        """The GPS coordinates currently held, or None."""
        if self._lat is None or self._lon is None:
            return None
        return (self._lat, self._lon)

    def forecast(self) -> WeatherForecast | None:
        """The currently held forecast, or None."""
        return self._forecast

    def is_fresh(self) -> bool:
        """Whether a forecast is held for the current coordinates."""
        if self._lat is None or self._lon is None or self._forecast is None:
            return False
        if self._fetched_at is not None:
            now = datetime.datetime.now()
            if (now - self._fetched_at).total_seconds() > 3 * 3600:
                return False
        return True

    def set_location(self, lat: float | None, lon: float | None) -> None:
        """Update coordinates. If changed, cancel any in-flight worker, clear old forecast,
        and notify subscribers."""
        if (lat, lon) == (self._lat, self._lon):
            return

        self._coalesce_timer.stop()
        self.shutdown(0)
        self._generation += 1
        self._forecast = None
        self._fetched_at = None
        self._lat = lat
        self._lon = lon

        self.forecast_cleared.emit()
        self.forecast_days_ready.emit(None, ())

    def invalidate(self) -> None:
        """Called on document replacement (File > New, File > Open, Revert).
        Forgets place and forecast, cancels workers, stops timers."""
        self._coalesce_timer.stop()
        self.shutdown(0)
        self._generation += 1
        self._forecast = None
        self._fetched_at = None
        self._lat = None
        self._lon = None

        self.forecast_cleared.emit()
        self.forecast_days_ready.emit(None, ())

    def request_forecast(self, force: bool = False) -> None:
        """Request a forecast for the current location.
        If a fresh forecast is already held and force is False, re-emits synchronously
        without starting a background thread.
        Otherwise, schedules a coalesced fetch (or starts immediately if forced)."""
        if self._lat is None or self._lon is None:
            self.forecast_cleared.emit()
            self.forecast_days_ready.emit(None, ())
            return

        if not force and self.is_fresh() and self._forecast is not None:
            days = tuple((day.date, int(day.weathercode)) for day in self._forecast.days)
            self.forecast_days_ready.emit(self.place(), days)
            return

        if force:
            self._start_fetch()
        else:
            self._coalesce_timer.start()

    def _on_coalesce_timeout(self) -> None:
        self._start_fetch()

    def _start_fetch(self) -> None:
        if self._lat is None or self._lon is None:
            return

        # Skip if worker already in flight for this exact location
        if (
            self._worker is not None
            and self._worker.isRunning()
            and self._worker._lat == self._lat
            and self._worker._lon == self._lon
        ):
            return

        if self._worker is not None:
            old = self._worker
            self._worker = None
            old.shutdown(100)

        gen = self._generation
        lat, lon = self._lat, self._lon
        worker = weather_widget._WeatherFetchWorker(lat, lon)
        self._worker = worker
        # UNDECORATED callables to respect PF-LIF-12 disconnect semantics
        worker.success.connect(lambda f: self._on_worker_success(f, gen, lat, lon))
        worker.error.connect(lambda msg: self._on_worker_failed(msg, gen, lat, lon))
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def _on_worker_success(
        self, forecast: WeatherForecast, gen: int, lat: float, lon: float
    ) -> None:
        if gen != self._generation or (lat, lon) != (self._lat, self._lon):
            # Drop result: generation or coordinates changed while worker was running
            return

        self._forecast = forecast
        self._fetched_at = datetime.datetime.now()
        days = tuple((day.date, int(day.weathercode)) for day in forecast.days)
        self.forecast_ready.emit(forecast)
        self.forecast_days_ready.emit(self.place(), days)

    def _on_worker_failed(
        self, message: str, gen: int, lat: float, lon: float
    ) -> None:
        if gen != self._generation or (lat, lon) != (self._lat, self._lon):
            return

        self._forecast = None
        self._fetched_at = None
        self.forecast_failed.emit(message)
        self.forecast_days_ready.emit(self.place(), ())

    def _on_worker_finished(self) -> None:
        if self.sender() is self._worker:
            self._worker = None

    def shutdown(self, timeout_ms: int = 100) -> None:
        """Cancel and detach/join running worker before teardown."""
        self._coalesce_timer.stop()
        worker = self._worker
        if worker is not None:
            self._worker = None
            worker.shutdown(timeout_ms)
