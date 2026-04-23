"""Integration tests for the weather forecast widget (US-12.1).

Tests cover:
- Empty state when no location is set
- Rendering a forecast into the 7-day strip
- Expandable table show/hide
- Offline cache age display
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from open_garden_planner.services.weather_service import DayForecast, WeatherForecast
from open_garden_planner.ui.widgets.weather_widget import WeatherWidget


def _make_forecast(days: int = 16) -> WeatherForecast:
    """Create a dummy forecast with the requested number of days."""
    base_date = datetime(2024, 6, 1, tzinfo=UTC)
    forecast_days = []
    for i in range(days):
        d = base_date + timedelta(days=i)
        forecast_days.append(
            DayForecast(
                date=d.strftime("%Y-%m-%d"),
                max_c=20.0 + (i % 5),
                min_c=10.0 + (i % 3),
                precipitation_mm=float(i % 3),
                weathercode=i % 100,
            )
        )
    return WeatherForecast(
        days=forecast_days,
        fetched_at=datetime.now(UTC).isoformat(),
    )


class TestWeatherWidgetEmptyState:
    def test_no_location_shows_empty_label(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(None, None)

        # Empty label should be visible; strip/table hidden
        assert widget._empty_lbl.isVisible()
        assert not widget._strip.isVisible()
        assert not widget._table.isVisible()

    def test_empty_label_text(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(None, None)

        assert "Set a location" in widget._empty_lbl.text()


class TestWeatherWidgetForecast:
    def test_set_location_then_inject_forecast_renders_strip(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(52.5, 13.4)
        forecast = _make_forecast(days=7)
        widget._on_fetch_success(forecast)

        # Strip should be visible with 7 cells
        assert widget._strip.isVisible()
        assert widget._day_cells[0].isVisible()
        assert widget._day_cells[6].isVisible()

    def test_day_cell_shows_correct_data(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(52.5, 13.4)
        forecast = _make_forecast(days=1)
        widget._on_fetch_success(forecast)

        cell = widget._day_cells[0]
        day_text = cell._day_lbl.text()
        # 2024-06-01 is a Saturday
        assert "Sat" in day_text
        assert cell._temp_lbl.text() == "20° / 10°"

    def test_expandable_table_hidden_by_default(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(52.5, 13.4)
        forecast = _make_forecast(days=16)
        widget._on_fetch_success(forecast)

        assert not widget._table.isVisible()
        assert widget._expand_btn.text() == "▾"

    def test_expand_button_shows_table(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(52.5, 13.4)
        forecast = _make_forecast(days=16)
        widget._on_fetch_success(forecast)

        # Simulate expand button click
        widget._on_expand_clicked()

        assert widget._table.isVisible()
        assert widget._expand_btn.text() == "▴"
        assert widget._table.rowCount() == 16

    def test_table_contains_correct_headers(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(52.5, 13.4)
        forecast = _make_forecast(days=3)
        widget._on_fetch_success(forecast)
        widget._on_expand_clicked()

        headers = [widget._table.horizontalHeaderItem(i).text() for i in range(5)]
        assert "Date" in headers
        assert "Weather" in headers
        assert "Max °C" in headers
        assert "Min °C" in headers
        assert "Rain mm" in headers


class TestWeatherWidgetOffline:
    def test_cache_age_label_shown_for_old_data(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(52.5, 13.4)

        # Create a forecast fetched 2 hours ago
        old_time = datetime.now(UTC) - timedelta(hours=2)
        forecast = WeatherForecast(
            days=[DayForecast(date="2024-06-01", max_c=20.0, min_c=10.0, precipitation_mm=0.0, weathercode=0)],
            fetched_at=old_time.isoformat(),
        )
        widget._on_fetch_success(forecast)

        assert widget._age_lbl.isVisible()
        assert "2" in widget._age_lbl.text()
        assert "h ago" in widget._age_lbl.text()

    def test_cache_age_hidden_for_fresh_data(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(52.5, 13.4)
        forecast = _make_forecast(days=1)
        widget._on_fetch_success(forecast)

        # Fresh data (< 1 min) should hide age label
        assert not widget._age_lbl.isVisible()


class TestWeatherWidgetFetchTrigger:
    def test_refresh_starts_worker_when_location_set(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)

        with (patch.object(widget, "_show_loading"),
              patch("open_garden_planner.ui.widgets.weather_widget._WeatherFetchWorker") as MockWorker):
            instance = MagicMock()
            MockWorker.return_value = instance

            widget.set_location(52.5, 13.4)
            widget.refresh()

            MockWorker.assert_called_once_with(52.5, 13.4)
            instance.start.assert_called_once()

    def test_refresh_shows_empty_when_no_location(self, qtbot: object) -> None:
        widget = WeatherWidget()
        qtbot.addWidget(widget)
        widget.show()

        widget.set_location(None, None)
        widget.refresh()

        assert widget._empty_lbl.isVisible()
        assert not widget._strip.isVisible()
