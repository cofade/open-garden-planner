"""Unit tests for ForecastHolder (ADR-070 addendum, #693)."""

from __future__ import annotations

import datetime
import threading
from unittest.mock import MagicMock

from PyQt6.QtCore import QThread, pyqtSignal

from open_garden_planner.services import forecast_holder
from open_garden_planner.services.forecast_holder import ForecastHolder
from open_garden_planner.services.weather_service import DayForecast, WeatherForecast


class _FakeFetchWorker(QThread):
    """A worker whose start() does nothing; the test emits its signals."""

    success = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, lat, lon, parent=None, *, generation=0):
        super().__init__(parent)
        self._lat = lat
        self._lon = lon
        self._generation = generation

    def start(self) -> None:
        pass

    def shutdown(self, timeout_ms: int = 100) -> None:
        pass


class _QueuedFetchWorker(_FakeFetchWorker):
    """A real thread that emits one result after the test releases it."""

    def __init__(self, lat, lon, parent=None, *, generation=0):
        super().__init__(lat, lon, parent, generation=generation)
        self._payload = None
        self._release = threading.Event()
        self.emitted = threading.Event()

    def start(self) -> None:
        QThread.start(self)

    def set_payload(self, payload) -> None:
        self._payload = payload

    def release(self) -> None:
        self._release.set()

    def run(self) -> None:
        self._release.wait(5)
        self.success.emit(self._payload)
        self.emitted.set()


def _make_forecast(days_count: int = 7) -> WeatherForecast:
    today = datetime.date.today()
    days = [
        DayForecast((today + datetime.timedelta(days=i)).isoformat(), 20.0, 10.0, 0.0, 0)
        for i in range(days_count)
    ]
    return WeatherForecast(days, datetime.datetime.now().isoformat())


def test_holder_initial_state(qtbot):
    holder = ForecastHolder()
    assert holder.place() is None
    assert holder.forecast() is None
    assert not holder.is_fresh()


def test_holder_set_location_and_invalidate(qtbot):
    holder = ForecastHolder()
    holder.set_location(52.5, 13.4)
    assert holder.place() == (52.5, 13.4)
    assert holder.forecast() is None
    assert not holder.is_fresh()

    # Invalidate drops location and forecast
    holder.invalidate()
    assert holder.place() is None
    assert holder.forecast() is None


def test_holder_fresh_forecast_reemits_without_worker(qtbot, monkeypatch):
    holder = ForecastHolder()
    holder.set_location(52.5, 13.4)

    # Simulate loaded forecast
    forecast = _make_forecast(3)
    holder._on_worker_success(forecast, holder._generation, 52.5, 13.4)
    assert holder.is_fresh()
    assert holder.forecast() is forecast

    # Spy on _start_fetch
    fetch_mock = MagicMock()
    monkeypatch.setattr(holder, "_start_fetch", fetch_mock)

    days_received = []
    holder.forecast_days_ready.connect(lambda place, days: days_received.append((place, days)))

    # request_forecast when fresh re-emits immediately without starting fetch
    holder.request_forecast(force=False)
    assert fetch_mock.call_count == 0
    assert len(days_received) == 1
    assert days_received[0][0] == (52.5, 13.4)
    assert len(days_received[0][1]) == 3


def test_holder_stale_worker_dropped_on_generation_or_place_mismatch(qtbot):
    holder = ForecastHolder()
    holder.set_location(52.5, 13.4)
    gen = holder._generation

    # Place changed / generation bumped
    holder.set_location(48.1, 11.6)
    assert holder._generation > gen

    # Result from old generation arrives late
    stale_forecast = _make_forecast(3)
    holder._on_worker_success(stale_forecast, gen, 52.5, 13.4)
    assert holder.forecast() is None, "stale result from old generation must be dropped"

    # Result from matching generation but mismatching coordinates arrives
    holder._on_worker_success(stale_forecast, holder._generation, 52.5, 13.4)
    assert holder.forecast() is None, "result with mismatching coordinates must be dropped"


def test_holder_shutdown_stops_timer_and_worker(qtbot):
    holder = ForecastHolder()
    holder.set_location(52.5, 13.4)
    holder._coalesce_timer.start(1000)
    assert holder._coalesce_timer.isActive()

    holder.shutdown(0)
    assert not holder._coalesce_timer.isActive()
    assert holder._worker is None


def test_a_worker_result_carries_the_request_values_not_the_holders(qtbot, monkeypatch):
    """A result is delivered through the bound slot, keyed to the request that
    produced it — not to the holder's current fields (#898)."""
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        ForecastHolder,
        "_safe_worker_success",
        lambda _self, *args: calls.append(args),
    )
    monkeypatch.setattr(forecast_holder, "WeatherFetchWorker", _FakeFetchWorker)
    holder = ForecastHolder()
    holder.set_location(52.5, 13.4)
    holder._start_fetch()
    worker = holder._worker
    assert worker is not None
    forecast = _make_forecast(3)

    # The holder moves on; the result must still carry the request it answers.
    holder._generation += 1
    holder._lat, holder._lon = 48.1, 11.6
    worker.success.emit(forecast)

    assert calls == [(forecast, 1, 52.5, 13.4)]


def test_a_worker_failure_carries_the_request_values_not_the_holders(qtbot, monkeypatch):
    """The error path carries the same request values as success (#898)."""
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        ForecastHolder,
        "_safe_worker_failed",
        lambda _self, *args: calls.append(args),
    )
    monkeypatch.setattr(forecast_holder, "WeatherFetchWorker", _FakeFetchWorker)
    holder = ForecastHolder()
    holder.set_location(52.5, 13.4)
    holder._start_fetch()
    worker = holder._worker
    assert worker is not None

    holder._generation += 1
    holder._lat, holder._lon = 48.1, 11.6
    worker.error.emit("boom")

    assert calls == [("boom", 1, 52.5, 13.4)]


def test_a_queued_worker_result_never_reaches_a_deleted_holder(qtbot, monkeypatch):
    """#898: a bound slot is dropped with its receiver. The old lambda outlived
    the deleted holder, and the queued result crashed the Linux CI worker inside
    pytest-qt's event processing. PyQt still resolves a Python method on the
    deleted wrapper, so the patched method records the delivery the fix prevents.
    """
    from PyQt6 import sip

    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        ForecastHolder,
        "_safe_worker_success",
        lambda _self, *args: calls.append(args),
    )
    monkeypatch.setattr(forecast_holder, "WeatherFetchWorker", _QueuedFetchWorker)
    holder = ForecastHolder()
    holder.set_location(52.5, 13.4)
    holder._start_fetch()
    worker = holder._worker
    assert worker is not None
    forecast = _make_forecast(3)
    worker.set_payload(forecast)
    # A control receiver proves the queued event was delivered at all.
    received: list[object] = []
    worker.success.connect(lambda payload: received.append(payload))

    sip.delete(holder)
    worker.release()
    assert worker.emitted.wait(5), "the fake worker never emitted"
    worker.wait(5000)
    qtbot.wait(50)  # deliver the queued result

    assert received == [forecast], "the queued event was never processed"
    assert calls == [], "a queued result must not be delivered to a deleted holder"
