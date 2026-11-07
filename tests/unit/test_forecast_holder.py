"""Unit tests for ForecastHolder (ADR-070 addendum, #693)."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

from open_garden_planner.services.forecast_holder import ForecastHolder
from open_garden_planner.services.weather_service import DayForecast, WeatherForecast


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
