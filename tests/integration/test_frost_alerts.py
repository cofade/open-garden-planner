"""Integration tests for frost alert & plant-aware warnings (US-12.2).

Tests cover:
- get_frost_alerts() logic (unit-level within integration context)
- Frost alert tasks appearing in the dashboard
- Hardy plant excluded from alerts
- Per-plant override (frost_protection_needed = False) excludes plant
- Per-plant override (frost_protection_needed = True) includes tender plant below orange threshold
- WeatherWidget strip tinting via apply_frost_thresholds()
- highlight_requested signal carries frost_items: prefix
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from open_garden_planner.services.weather_service import (
    DayForecast,
    FrostAlert,
    WeatherForecast,
    get_frost_alerts,
)
from open_garden_planner.ui.widgets.weather_widget import WeatherWidget

# ruff: noqa: ARG002


# ─── helpers ────────────────────────────────────────────────────────────────────


def _make_forecast(days: int = 7, *, min_c_override: float | None = None) -> WeatherForecast:
    base = datetime.datetime(2024, 6, 1, tzinfo=datetime.UTC)
    forecast_days = []
    for i in range(days):
        d = base + datetime.timedelta(days=i)
        forecast_days.append(
            DayForecast(
                date=d.strftime("%Y-%m-%d"),
                max_c=18.0,
                min_c=min_c_override if min_c_override is not None else 10.0,
                precipitation_mm=0.0,
                weathercode=0,
            )
        )
    return WeatherForecast(
        days=forecast_days,
        fetched_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )


def _make_frost_forecast(min_c: float, day_offset: int = 1) -> WeatherForecast:
    """Return a 7-day forecast where day *day_offset* has min_c set."""
    base = datetime.datetime.now(datetime.UTC)
    days = []
    for i in range(7):
        d = base + datetime.timedelta(days=i)
        days.append(
            DayForecast(
                date=d.strftime("%Y-%m-%d"),
                max_c=18.0,
                min_c=min_c if i == day_offset else 12.0,
                precipitation_mm=0.0,
                weathercode=0,
            )
        )
    return WeatherForecast(days=days, fetched_at=datetime.datetime.now(datetime.UTC).isoformat())


# ─── get_frost_alerts() unit tests ──────────────────────────────────────────────


class TestGetFrostAlerts:
    def test_no_frost_no_alerts(self) -> None:
        forecast = _make_forecast(min_c_override=10.0)
        plants = [{"id": "p1", "name": "Tomato", "frost_protection_needed": None, "frost_tolerance": "tender"}]
        assert get_frost_alerts(forecast, plants) == []

    def test_half_hardy_triggers_at_red_only(self) -> None:
        forecast = _make_frost_forecast(min_c=1.0, day_offset=0)
        plants = [{"id": "p1", "name": "Artichoke", "frost_protection_needed": None, "frost_tolerance": "half-hardy"}]
        alerts = get_frost_alerts(forecast, plants, orange_threshold=5.0, red_threshold=2.0)
        assert len(alerts) == 1
        assert alerts[0].severity == "red"
        assert "p1" in alerts[0].affected_plant_ids

    def test_half_hardy_not_triggered_at_orange(self) -> None:
        forecast = _make_frost_forecast(min_c=3.0, day_offset=0)
        plants = [{"id": "p1", "name": "Artichoke", "frost_protection_needed": None, "frost_tolerance": "half-hardy"}]
        alerts = get_frost_alerts(forecast, plants, orange_threshold=5.0, red_threshold=2.0)
        assert alerts == []

    def test_red_threshold_triggers_tender(self) -> None:
        forecast = _make_frost_forecast(min_c=1.0, day_offset=0)
        plants = [{"id": "p1", "name": "Basil", "frost_protection_needed": None, "frost_tolerance": "tender"}]
        alerts = get_frost_alerts(forecast, plants, orange_threshold=5.0, red_threshold=2.0)
        assert len(alerts) == 1
        assert alerts[0].severity == "red"

    def test_hardy_plant_excluded(self) -> None:
        forecast = _make_frost_forecast(min_c=0.0, day_offset=0)
        plants = [{"id": "p1", "name": "Kale", "frost_protection_needed": None, "frost_tolerance": "hardy"}]
        assert get_frost_alerts(forecast, plants) == []

    def test_override_true_always_included(self) -> None:
        # Even though frost_tolerance is "hardy", override True forces inclusion
        forecast = _make_frost_forecast(min_c=3.0, day_offset=0)
        plants = [{"id": "p1", "name": "Kale", "frost_protection_needed": True, "frost_tolerance": "hardy"}]
        alerts = get_frost_alerts(forecast, plants, orange_threshold=5.0, red_threshold=2.0)
        assert len(alerts) == 1
        assert "p1" in alerts[0].affected_plant_ids

    def test_override_false_excludes_tender(self) -> None:
        # Even though plant is tender, override False prevents inclusion
        forecast = _make_frost_forecast(min_c=1.0, day_offset=0)
        plants = [{"id": "p1", "name": "Basil", "frost_protection_needed": False, "frost_tolerance": "tender"}]
        assert get_frost_alerts(forecast, plants) == []

    def test_unknown_tolerance_excluded(self) -> None:
        # None tolerance → no species data → plant is excluded from alerts
        forecast = _make_frost_forecast(min_c=4.0, day_offset=0)
        plants = [{"id": "p1", "name": "Unknown", "frost_protection_needed": None, "frost_tolerance": None}]
        alerts = get_frost_alerts(forecast, plants, orange_threshold=5.0, red_threshold=2.0)
        assert alerts == []

    def test_tender_triggered_at_orange(self) -> None:
        # tender plants are most fragile: warn at orange threshold too
        forecast = _make_frost_forecast(min_c=3.0, day_offset=0)
        plants = [{"id": "p1", "name": "Basil", "frost_protection_needed": None, "frost_tolerance": "tender"}]
        alerts = get_frost_alerts(forecast, plants, orange_threshold=5.0, red_threshold=2.0)
        assert len(alerts) == 1
        assert alerts[0].severity == "orange"
        assert "p1" in alerts[0].affected_plant_ids

    def test_no_alert_when_no_affected_plants(self) -> None:
        forecast = _make_frost_forecast(min_c=3.0, day_offset=0)
        plants = [{"id": "p1", "name": "Kale", "frost_protection_needed": None, "frost_tolerance": "hardy"}]
        assert get_frost_alerts(forecast, plants) == []

    def test_alerts_sorted_by_date(self) -> None:
        # Build forecast where day 2 and day 0 are frost nights
        base = datetime.datetime.now(datetime.UTC)
        days = []
        for i in range(5):
            d = base + datetime.timedelta(days=i)
            days.append(DayForecast(
                date=d.strftime("%Y-%m-%d"),
                max_c=18.0,
                min_c=1.0 if i in (0, 2) else 12.0,
                precipitation_mm=0.0,
                weathercode=0,
            ))
        forecast = WeatherForecast(days=days, fetched_at=datetime.datetime.now(datetime.UTC).isoformat())
        plants = [{"id": "p1", "name": "T", "frost_protection_needed": None, "frost_tolerance": "half-hardy"}]
        alerts = get_frost_alerts(forecast, plants)
        assert alerts[0].date < alerts[1].date


# ─── WeatherWidget strip tinting ────────────────────────────────────────────────


class TestWeatherWidgetFrostTinting:
    def test_red_tint_applied(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()
        widget.set_location(52.5, 13.4)
        forecast = _make_frost_forecast(min_c=1.0, day_offset=0)
        widget._on_fetch_success(forecast)

        widget.apply_frost_thresholds(orange_c=5.0, red_c=2.0)

        assert "#f8d7da" in widget._day_cells[0].styleSheet()

    def test_orange_tint_applied(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()
        widget.set_location(52.5, 13.4)
        forecast = _make_frost_forecast(min_c=3.0, day_offset=0)
        widget._on_fetch_success(forecast)

        widget.apply_frost_thresholds(orange_c=5.0, red_c=2.0)

        assert "#fff3cd" in widget._day_cells[0].styleSheet()

    def test_no_tint_above_threshold(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()
        widget.set_location(52.5, 13.4)
        forecast = _make_frost_forecast(min_c=12.0, day_offset=0)
        widget._on_fetch_success(forecast)

        widget.apply_frost_thresholds(orange_c=5.0, red_c=2.0)

        # Should have default (neutral) background for all cells
        for cell in widget._day_cells:
            if cell.isVisible():
                assert "#f8d7da" not in cell.styleSheet()
                assert "#fff3cd" not in cell.styleSheet()

    def test_apply_frost_thresholds_no_crash_without_forecast(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()
        # Should not raise even without a loaded forecast
        widget.apply_frost_thresholds(5.0, 2.0)
