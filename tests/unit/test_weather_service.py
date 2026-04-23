"""Unit tests for the weather forecast service (US-12.1)."""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from open_garden_planner.services.weather_service import (
    DayForecast,
    WeatherForecast,
    WeatherService,
    WeatherServiceError,
    _wmo_to_description,
    wmo_to_icon,
)

# ─── Sample Open-Meteo response ───────────────────────────────────────────────

SAMPLE_API_RESPONSE = {
    "latitude": 52.52,
    "longitude": 13.419998,
    "daily": {
        "time": ["2024-06-01", "2024-06-02", "2024-06-03"],
        "temperature_2m_max": [22.5, 24.0, 19.5],
        "temperature_2m_min": [12.0, 14.5, 10.0],
        "precipitation_sum": [0.0, 2.3, 5.5],
        "weathercode": [0, 1, 61],
    },
}


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def svc() -> WeatherService:
    return WeatherService()


@pytest.fixture()
def tmp_cache_dir(tmp_path: Path) -> Path:
    return tmp_path


# ─── WMO code mapping tests ───────────────────────────────────────────────────

class TestWmoMapping:
    def test_clear_sky(self) -> None:
        assert wmo_to_icon(0) == "☀"
        assert _wmo_to_description(0) == "Clear sky"

    def test_partly_cloudy(self) -> None:
        assert wmo_to_icon(2) == "⛅"
        assert _wmo_to_description(2) == "Partly cloudy"

    def test_rainy(self) -> None:
        assert wmo_to_icon(61) == "\U0001f327"
        assert _wmo_to_description(61) == "Rainy"

    def test_snowy(self) -> None:
        assert wmo_to_icon(71) == "\U0001f328"
        assert _wmo_to_description(71) == "Snowy"

    def test_thunderstorm(self) -> None:
        assert wmo_to_icon(95) == "⛈"
        assert _wmo_to_description(95) == "Thunderstorm"

    def test_unknown_code(self) -> None:
        assert wmo_to_icon(999) == "❓"
        assert _wmo_to_description(999) == "Unknown"


# ─── Response parsing tests ───────────────────────────────────────────────────

class TestParseResponse:
    def test_parse_sample_response(self, svc: WeatherService) -> None:
        result = svc._parse_response(SAMPLE_API_RESPONSE)
        assert len(result.days) == 3

        day0 = result.days[0]
        assert day0.date == "2024-06-01"
        assert day0.max_c == 22.5
        assert day0.min_c == 12.0
        assert day0.precipitation_mm == 0.0
        assert day0.weathercode == 0

    def test_parse_excludes_none_temperatures(self, svc: WeatherService) -> None:
        data = {
            "daily": {
                "time": ["2024-06-01"],
                "temperature_2m_max": [None],
                "temperature_2m_min": [None],
                "precipitation_sum": [None],
                "weathercode": [None],
            },
        }
        result = svc._parse_response(data)
        day = result.days[0]
        assert day.max_c == 0.0
        assert day.min_c == 0.0
        assert day.precipitation_mm == 0.0
        assert day.weathercode == 0

    def test_parse_sets_fetched_at(self, svc: WeatherService) -> None:
        result = svc._parse_response(SAMPLE_API_RESPONSE)
        assert result.fetched_at
        parsed = datetime.fromisoformat(result.fetched_at)
        assert parsed.tzinfo is not None


# ─── Cache tests ──────────────────────────────────────────────────────────────

class TestCache:
    def test_save_and_load_cache(self, svc: WeatherService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.weather_service.get_app_data_dir",
            lambda: tmp_path,
        )

        forecast = WeatherForecast(
            days=[
                DayForecast(date="2024-06-01", max_c=20.0, min_c=10.0, precipitation_mm=0.0, weathercode=0),
            ],
            fetched_at=datetime.now(UTC).isoformat(),
        )

        svc._save_cache(52.5, 13.4, forecast)
        loaded = svc._load_cache(52.5, 13.4)

        assert loaded is not None
        assert len(loaded.days) == 1
        assert loaded.days[0].max_c == 20.0

    def test_stale_cache_returns_none(self, svc: WeatherService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.weather_service.get_app_data_dir",
            lambda: tmp_path,
        )

        old_time = datetime.now(UTC) - timedelta(hours=4)
        forecast = WeatherForecast(
            days=[DayForecast(date="2024-06-01", max_c=20.0, min_c=10.0, precipitation_mm=0.0, weathercode=0)],
            fetched_at=old_time.isoformat(),
        )

        svc._save_cache(52.5, 13.4, forecast)
        loaded = svc._load_cache(52.5, 13.4)
        assert loaded is None

    def test_missing_cache_returns_none(self, svc: WeatherService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.weather_service.get_app_data_dir",
            lambda: tmp_path,
        )
        loaded = svc._load_cache(0.0, 0.0)
        assert loaded is None

    def test_corrupt_cache_returns_none(self, svc: WeatherService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.weather_service.get_app_data_dir",
            lambda: tmp_path,
        )
        cache_path = tmp_path / "weather_cache_0.0000_0.0000.json"
        cache_path.write_text("not json", encoding="utf-8")
        loaded = svc._load_cache(0.0, 0.0)
        assert loaded is None


# ─── API fetch tests ──────────────────────────────────────────────────────────

class TestFetchFromApi:
    def test_successful_fetch(self, svc: WeatherService) -> None:
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = json.dumps(SAMPLE_API_RESPONSE).encode()

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = svc._fetch_from_api(52.5, 13.4)

        assert len(result.days) == 3
        assert result.days[0].date == "2024-06-01"

    def test_network_error_raises(self, svc: WeatherService) -> None:
        with (patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network error")),
              pytest.raises(WeatherServiceError)):
            svc._fetch_from_api(52.5, 13.4)

    def test_invalid_json_raises(self, svc: WeatherService) -> None:
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"invalid json"

        with (patch("urllib.request.urlopen", return_value=mock_response),
              pytest.raises(WeatherServiceError)):
            svc._fetch_from_api(52.5, 13.4)


# ─── Integration: fetch_forecast ──────────────────────────────────────────────

class TestFetchForecast:
    def test_uses_cache_when_fresh(self, svc: WeatherService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.weather_service.get_app_data_dir",
            lambda: tmp_path,
        )

        cached = WeatherForecast(
            days=[DayForecast(date="2024-06-01", max_c=20.0, min_c=10.0, precipitation_mm=0.0, weathercode=0)],
            fetched_at=datetime.now(UTC).isoformat(),
        )
        svc._save_cache(52.5, 13.4, cached)

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = svc.fetch_forecast(52.5, 13.4)
            mock_urlopen.assert_not_called()

        assert result is not None
        assert result.days[0].max_c == 20.0

    def test_fetches_when_cache_stale(self, svc: WeatherService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.weather_service.get_app_data_dir",
            lambda: tmp_path,
        )

        old = datetime.now(UTC) - timedelta(hours=4)
        stale = WeatherForecast(
            days=[DayForecast(date="2024-06-01", max_c=10.0, min_c=5.0, precipitation_mm=0.0, weathercode=0)],
            fetched_at=old.isoformat(),
        )
        svc._save_cache(52.5, 13.4, stale)

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = json.dumps(SAMPLE_API_RESPONSE).encode()

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = svc.fetch_forecast(52.5, 13.4)

        assert result is not None
        assert result.days[0].max_c == 22.5

    def test_returns_none_on_complete_failure(self, svc: WeatherService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.weather_service.get_app_data_dir",
            lambda: tmp_path,
        )

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            result = svc.fetch_forecast(52.5, 13.4)

        assert result is None


# ─── Dataclass serialization ──────────────────────────────────────────────────

class TestSerialization:
    def test_weather_forecast_roundtrip(self) -> None:
        original = WeatherForecast(
            days=[
                DayForecast(date="2024-06-01", max_c=22.5, min_c=12.0, precipitation_mm=0.0, weathercode=0),
                DayForecast(date="2024-06-02", max_c=24.0, min_c=14.0, precipitation_mm=2.0, weathercode=1),
            ],
            fetched_at="2024-06-01T00:00:00+00:00",
        )
        data = original.to_dict()
        restored = WeatherForecast.from_dict(data)

        assert len(restored.days) == 2
        assert restored.days[1].max_c == 24.0
        assert restored.fetched_at == original.fetched_at
