"""Weather forecast service for US-12.1.

Fetches a 16-day forecast from Open-Meteo (free, no API key) using stdlib
urllib.  Results are cached on disk for 3 hours so offline launches still
show data.
"""

from __future__ import annotations

import json
import logging
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_garden_planner.services.plant_library import get_app_data_dir

logger = logging.getLogger(__name__)

_OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_REQUEST_TIMEOUT = 15
_CACHE_STALE_SECONDS = 10800  # 3 hours

# WMO Weather interpretation codes (Open-Meteo docs)
# Each tuple is (inclusive_start, inclusive_end) -> (description, emoji)
_WMO_CODE_MAP: dict[tuple[int, int], tuple[str, str]] = {
    (0, 0): ("Clear sky", "☀️"),       # ☀️ (VS-16 forces colour/emoji rendering)
    (1, 3): ("Partly cloudy", "⛅️"),   # ⛅️
    (45, 48): ("Foggy", "\U0001f32b"),            # 🌫
    (51, 67): ("Rainy", "\U0001f327"),            # 🌧
    (71, 77): ("Snowy", "\U0001f328"),            # 🌨
    (80, 82): ("Showers", "\U0001f326"),          # 🌦
    (85, 86): ("Snow showers", "\U0001f328"),     # 🌨
    (95, 95): ("Thunderstorm", "⛈️"),  # ⛈️
    (96, 99): ("Thunderstorm", "⛈️"),  # ⛈️
}


def _wmo_to_description(code: int) -> str:
    """Return a human-readable description for a WMO weather code."""
    for (lo, hi), (desc, _) in _WMO_CODE_MAP.items():
        if lo <= code <= hi:
            return desc
    return "Unknown"


def wmo_to_icon(code: int) -> str:
    """Return an emoji icon for a WMO weather code."""
    for (lo, hi), (_, icon) in _WMO_CODE_MAP.items():
        if lo <= code <= hi:
            return icon
    return "❓"  # ❓


@dataclass
class DayForecast:
    """One day of forecast data."""

    date: str           # ISO date "YYYY-MM-DD"
    max_c: float
    min_c: float
    precipitation_mm: float
    weathercode: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "max_c": self.max_c,
            "min_c": self.min_c,
            "precipitation_mm": self.precipitation_mm,
            "weathercode": self.weathercode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DayForecast:
        return cls(
            date=str(data["date"]),
            max_c=float(data["max_c"]),
            min_c=float(data["min_c"]),
            precipitation_mm=float(data.get("precipitation_mm", 0)),
            weathercode=int(data["weathercode"]),
        )


@dataclass
class WeatherForecast:
    """A complete forecast with metadata."""

    days: list[DayForecast]
    fetched_at: str  # ISO datetime with timezone

    def to_dict(self) -> dict[str, Any]:
        return {
            "days": [d.to_dict() for d in self.days],
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeatherForecast:
        return cls(
            days=[DayForecast.from_dict(d) for d in data.get("days", [])],
            fetched_at=str(data["fetched_at"]),
        )


@dataclass
class FrostAlert:
    """One day's frost alert with the plants at risk."""

    date: str               # ISO "YYYY-MM-DD"
    min_temp: float
    severity: str           # "orange" | "red"
    affected_plant_ids: list[str]


def get_frost_alerts(
    forecast: WeatherForecast,
    plants: list[dict],
    orange_threshold: float = 5.0,
    red_threshold: float = 2.0,
) -> list[FrostAlert]:
    """Return frost alerts for days that breach a threshold.

    Args:
        forecast: 16-day forecast to scan.
        plants: List of plant info dicts with keys:
            ``id`` (str), ``name`` (str),
            ``frost_protection_needed`` (bool | None),
            ``frost_tolerance`` (str | None — "tender", "half-hardy", "hardy").
        orange_threshold: min_c at or below which tender plants are at risk.
        red_threshold: min_c at or below which half-hardy plants are at risk.

    Returns:
        Alerts sorted by date, only for days with ≥1 affected plant.
    """
    alerts: list[FrostAlert] = []
    for day in forecast.days:
        if day.min_c > orange_threshold:
            continue
        severity = "red" if day.min_c <= red_threshold else "orange"
        affected: list[str] = []
        for p in plants:
            override = p.get("frost_protection_needed")
            if override is True:
                affected.append(p["id"])
                continue
            if override is False:
                continue
            # override is None → use DB default
            tolerance = p.get("frost_tolerance")
            if tolerance == "hardy":
                continue
            if tolerance is None:
                continue  # no species data — don't assume frost sensitivity
            if tolerance == "tender":
                affected.append(p["id"])  # most fragile: warn at orange and red
            elif tolerance == "half-hardy" and severity == "red":
                affected.append(p["id"])  # tolerates light frost; only hard-frost warning
        if affected:
            alerts.append(FrostAlert(
                date=day.date,
                min_temp=day.min_c,
                severity=severity,
                affected_plant_ids=affected,
            ))
    return alerts


class WeatherServiceError(Exception):
    """Raised when a weather forecast lookup fails."""


class WeatherService:
    """Fetch and cache 16-day weather forecasts from Open-Meteo."""

    def fetch_forecast(self, lat: float, lon: float) -> WeatherForecast | None:
        """Return a forecast, preferring cache if fresh.

        Loads a cached entry if it exists and is < 3 hours old. Otherwise
        queries the Open-Meteo API, saves the result, and returns it.

        Args:
            lat: Latitude (-90 to 90).
            lon: Longitude (-180 to 180).

        Returns:
            A populated WeatherForecast or None if the request failed and
            no valid cache exists.
        """
        cached = self._load_cache(lat, lon)
        if cached is not None:
            logger.info("Using cached weather data for (%.4f, %.4f)", lat, lon)
            return cached

        try:
            forecast = self._fetch_from_api(lat, lon)
        except WeatherServiceError:
            logger.debug("Weather fetch failed for (%.4f, %.4f)", lat, lon, exc_info=True)
            return None

        self._save_cache(lat, lon, forecast)
        return forecast

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_path(self, lat: float, lon: float) -> Path:
        return get_app_data_dir() / f"weather_cache_{lat:.4f}_{lon:.4f}.json"

    def _load_cache(self, lat: float, lon: float) -> WeatherForecast | None:
        path = self._cache_path(lat, lon)
        if not path.exists():
            return None
        try:
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(raw["fetched_at"])
            age_seconds = (datetime.now(UTC) - cached_at).total_seconds()
            if age_seconds > _CACHE_STALE_SECONDS:
                logger.debug("Weather cache stale (%.0f s old)", age_seconds)
                return None
            return WeatherForecast.from_dict(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load weather cache: %s", exc)
            return None

    def _save_cache(self, lat: float, lon: float, forecast: WeatherForecast) -> None:
        path = self._cache_path(lat, lon)
        try:
            path.write_text(json.dumps(forecast.to_dict(), indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save weather cache: %s", exc)

    # ------------------------------------------------------------------
    # API fetch
    # ------------------------------------------------------------------

    def _fetch_from_api(self, lat: float, lon: float) -> WeatherForecast:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
            "forecast_days": 16,
            "timezone": "auto",
        }
        query = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())
        url = f"{_OPEN_METEO_FORECAST_URL}?{query}"
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme != "https" or parsed_url.netloc != "api.open-meteo.com":
            raise WeatherServiceError("Unexpected weather API URL")

        # Enterprise-compatible SSL context: loads the OS certificate store so
        # corporate proxy CAs are trusted, and clears VERIFY_X509_STRICT (added
        # in Python 3.12) which rejects legacy CA certs whose Basic Constraints
        # extension is not marked as critical per RFC 5280.
        ssl_ctx = ssl.create_default_context()
        if sys.platform == "win32":
            ssl_ctx.load_default_certs(ssl.Purpose.SERVER_AUTH)
        ssl_ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0x20)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OpenGardenPlanner-WeatherService/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT, context=ssl_ctx) as resp:
                raw_bytes = resp.read()
                data: dict[str, Any] = json.loads(raw_bytes.decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            logger.debug("Weather fetch failed for (%.4f, %.4f)", lat, lon, exc_info=True)
            raise WeatherServiceError(f"Open-Meteo request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise WeatherServiceError(f"Invalid JSON from Open-Meteo: {exc}") from exc

        return self._parse_response(data)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> WeatherForecast:
        daily = data.get("daily", {})
        dates: list[str] = daily.get("time", [])
        max_temps: list[float | None] = daily.get("temperature_2m_max", [])
        min_temps: list[float | None] = daily.get("temperature_2m_min", [])
        precips: list[float | None] = daily.get("precipitation_sum", [])
        codes: list[int | None] = daily.get("weathercode", [])

        days: list[DayForecast] = []
        for i, date in enumerate(dates):
            days.append(
                DayForecast(
                    date=str(date),
                    max_c=float(max_temps[i]) if i < len(max_temps) and max_temps[i] is not None else 0.0,
                    min_c=float(min_temps[i]) if i < len(min_temps) and min_temps[i] is not None else 0.0,
                    precipitation_mm=float(precips[i]) if i < len(precips) and precips[i] is not None else 0.0,
                    weathercode=int(codes[i]) if i < len(codes) and codes[i] is not None else 0,
                )
            )

        return WeatherForecast(
            days=days,
            fetched_at=datetime.now(UTC).isoformat(),
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_weather_service: WeatherService | None = None


def get_weather_service() -> WeatherService:
    """Return the shared WeatherService singleton."""
    global _weather_service
    if _weather_service is None:
        _weather_service = WeatherService()
    return _weather_service
