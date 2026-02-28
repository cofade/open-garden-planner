"""Climate service for frost date and hardiness zone lookup.

Uses the Open-Meteo ERA5 archive API (free, no API key required) to fetch
historical daily minimum temperatures and compute local frost dates and
USDA hardiness zones.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from PyQt6.QtCore import QStandardPaths

logger = logging.getLogger(__name__)

_OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# USDA hardiness zone lower bounds in °F and zone names (ascending order)
_USDA_ZONES: list[tuple[float, str]] = [
    (-60.0, "1a"), (-55.0, "1b"),
    (-50.0, "2a"), (-45.0, "2b"),
    (-40.0, "3a"), (-35.0, "3b"),
    (-30.0, "4a"), (-25.0, "4b"),
    (-20.0, "5a"), (-15.0, "5b"),
    (-10.0, "6a"), (-5.0, "6b"),
    (0.0, "7a"),   (5.0, "7b"),
    (10.0, "8a"),  (15.0, "8b"),
    (20.0, "9a"),  (25.0, "9b"),
    (30.0, "10a"), (35.0, "10b"),
    (40.0, "11a"), (45.0, "11b"),
    (50.0, "12a"), (55.0, "12b"),
    (60.0, "13a"), (65.0, "13b"),
]

_CACHE_EXPIRY_DAYS = 365


def _celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def _estimate_usda_zone(avg_annual_min_c: float) -> str:
    """Estimate USDA hardiness zone from average annual extreme minimum temperature.

    Args:
        avg_annual_min_c: Average annual extreme minimum temperature in °C.

    Returns:
        USDA zone string such as "7b".
    """
    min_f = _celsius_to_fahrenheit(avg_annual_min_c)
    zone = "1a"
    for threshold_f, zone_name in _USDA_ZONES:
        if min_f >= threshold_f:
            zone = zone_name
        else:
            break
    return zone


@dataclass
class FrostData:
    """Result of a frost date/hardiness zone lookup."""

    last_spring_frost: str | None  # "MM-DD", e.g. "04-15"
    first_fall_frost: str | None   # "MM-DD", e.g. "10-20"
    hardiness_zone: str | None     # e.g. "7b"
    data_source: str               # "open-meteo" | "cached"
    latitude: float
    longitude: float


class ClimateServiceError(Exception):
    """Raised when a frost date lookup fails."""


class ClimateService:
    """Service for looking up frost dates and hardiness zones from GPS coordinates.

    Uses the Open-Meteo ERA5 archive API (free, no API key) to fetch 10 years
    of daily minimum temperatures and compute typical frost dates and USDA zone.
    Results are cached on disk for one year to avoid repeated API calls.
    """

    def __init__(self) -> None:
        """Initialise the climate service and ensure the cache directory exists."""
        self._cache_dir = self._get_cache_dir()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup_frost_dates(self, lat: float, lon: float) -> FrostData:
        """Look up frost dates and hardiness zone for given coordinates.

        Checks the on-disk cache first; if no valid entry exists the
        Open-Meteo ERA5 archive is queried.

        Args:
            lat: Latitude in decimal degrees (−90 to 90).
            lon: Longitude in decimal degrees (−180 to 180).

        Returns:
            FrostData with computed frost dates and estimated hardiness zone.

        Raises:
            ClimateServiceError: If the lookup fails and no cache is available.
        """
        cached = self._load_cache(lat, lon)
        if cached is not None:
            logger.info("Using cached climate data for (%.4f, %.4f)", lat, lon)
            return cached

        data = self._fetch_from_open_meteo(lat, lon)
        self._save_cache(lat, lon, data)
        return data

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_cache_dir() -> Path:
        app_data = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation
        )
        cache_dir = Path(app_data) / "climate_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _cache_key(self, lat: float, lon: float) -> str:
        """Round coordinates to ~0.5° (~55 km) for cache key grouping."""
        return f"{round(lat * 2) / 2:.1f}_{round(lon * 2) / 2:.1f}"

    def _load_cache(self, lat: float, lon: float) -> FrostData | None:
        """Load cached frost data if it exists and has not expired."""
        cache_file = self._cache_dir / f"{self._cache_key(lat, lon)}.json"
        if not cache_file.exists():
            return None
        try:
            raw: dict[str, Any] = json.loads(cache_file.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(raw.get("cached_at", "2000-01-01"))
            age_days = (datetime.now() - cached_at).days
            if age_days > _CACHE_EXPIRY_DAYS:
                logger.debug("Climate cache expired for (%.4f, %.4f)", lat, lon)
                return None
            return FrostData(
                last_spring_frost=raw.get("last_spring_frost"),
                first_fall_frost=raw.get("first_fall_frost"),
                hardiness_zone=raw.get("hardiness_zone"),
                data_source="cached",
                latitude=lat,
                longitude=lon,
            )
        except Exception as exc:
            logger.warning("Failed to load climate cache: %s", exc)
            return None

    def _save_cache(self, lat: float, lon: float, data: FrostData) -> None:
        """Persist frost data to the on-disk cache."""
        cache_file = self._cache_dir / f"{self._cache_key(lat, lon)}.json"
        try:
            payload: dict[str, Any] = {
                "cached_at": datetime.now().isoformat(),
                "last_spring_frost": data.last_spring_frost,
                "first_fall_frost": data.first_fall_frost,
                "hardiness_zone": data.hardiness_zone,
            }
            cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save climate cache: %s", exc)

    # ------------------------------------------------------------------
    # API fetch
    # ------------------------------------------------------------------

    def _fetch_from_open_meteo(self, lat: float, lon: float) -> FrostData:
        """Query the Open-Meteo ERA5 archive for historical daily min temps.

        Fetches the last 10 complete calendar years and derives frost dates
        and an estimated USDA hardiness zone.

        Raises:
            ClimateServiceError: On network error or unexpected response format.
        """
        current_year = datetime.now().year
        end_year = current_year - 1
        start_year = end_year - 9  # 10 full years

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": f"{start_year}-01-01",
            "end_date": f"{end_year}-12-31",
            "daily": "temperature_2m_min",
            "timezone": "auto",
        }

        try:
            response = requests.get(
                _OPEN_METEO_ARCHIVE_URL, params=params, timeout=30
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ClimateServiceError(
                f"Open-Meteo request failed: {exc}"
            ) from exc

        try:
            raw = response.json()
        except ValueError as exc:
            raise ClimateServiceError(
                f"Invalid JSON from Open-Meteo: {exc}"
            ) from exc

        daily = raw.get("daily", {})
        dates: list[str] = daily.get("time", [])
        temps: list[float | None] = daily.get("temperature_2m_min", [])

        if not dates or not temps:
            raise ClimateServiceError(
                "No temperature data received from Open-Meteo"
            )

        return self._compute_frost_data(lat, lon, dates, temps)

    # ------------------------------------------------------------------
    # Computation helpers
    # ------------------------------------------------------------------

    def _compute_frost_data(
        self,
        lat: float,
        lon: float,
        dates: list[str],
        temps: list[float | None],
    ) -> FrostData:
        """Derive frost dates and hardiness zone from daily minimum temps.

        Args:
            lat, lon: Coordinates (passed through to FrostData).
            dates: ISO date strings ("YYYY-MM-DD") from API.
            temps: Corresponding daily minimum temperatures in °C (may contain None).

        Returns:
            FrostData populated with median spring/fall frost dates and zone.
        """
        from collections import defaultdict

        year_data: dict[int, list[tuple[str, float]]] = defaultdict(list)
        for date_str, temp in zip(dates, temps, strict=False):
            if temp is None:
                continue
            year = int(date_str[:4])
            year_data[year].append((date_str, temp))

        spring_frosts: list[str] = []   # last spring frost per year (MM-DD)
        fall_frosts: list[str] = []     # first fall frost per year (MM-DD)
        annual_min_temps: list[float] = []

        for day_data in year_data.values():
            year_temps = [t for _, t in day_data]
            if year_temps:
                annual_min_temps.append(min(year_temps))

            # Last spring frost: months 1–6, temp ≤ 0 °C
            spring_days = [
                (d, t)
                for d, t in day_data
                if 1 <= int(d[5:7]) <= 6 and t <= 0.0
            ]
            if spring_days:
                last_spring_date = max(spring_days, key=lambda x: x[0])
                spring_frosts.append(last_spring_date[0][5:])  # "MM-DD"

            # First fall frost: months 7–12, temp ≤ 0 °C
            fall_days = [
                (d, t)
                for d, t in day_data
                if 7 <= int(d[5:7]) <= 12 and t <= 0.0
            ]
            if fall_days:
                first_fall_date = min(fall_days, key=lambda x: x[0])
                fall_frosts.append(first_fall_date[0][5:])  # "MM-DD"

        hardiness_zone: str | None = None
        if annual_min_temps:
            avg_min = sum(annual_min_temps) / len(annual_min_temps)
            hardiness_zone = _estimate_usda_zone(avg_min)

        return FrostData(
            last_spring_frost=_median_date(spring_frosts),
            first_fall_frost=_median_date(fall_frosts),
            hardiness_zone=hardiness_zone,
            data_source="open-meteo",
            latitude=lat,
            longitude=lon,
        )


def _median_date(mmdd_list: list[str]) -> str | None:
    """Return the median MM-DD value from a list of "MM-DD" strings.

    Converts each value to a day-of-year using a fixed non-leap year (2001),
    takes the median day-of-year, then converts back to "MM-DD".

    Args:
        mmdd_list: List of date strings in "MM-DD" format.

    Returns:
        Median date as "MM-DD", or None if the list is empty.
    """
    if not mmdd_list:
        return None

    days_of_year: list[int] = []
    for mmdd in mmdd_list:
        try:
            dt = datetime.strptime(f"2001-{mmdd}", "%Y-%m-%d")
            days_of_year.append(dt.timetuple().tm_yday)
        except ValueError:
            continue

    if not days_of_year:
        return None

    days_of_year.sort()
    median_doy = days_of_year[len(days_of_year) // 2]
    result_dt = datetime(2001, 1, 1) + timedelta(days=median_doy - 1)
    return result_dt.strftime("%m-%d")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service_instance: ClimateService | None = None


def get_climate_service() -> ClimateService:
    """Return the shared ClimateService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ClimateService()
    return _service_instance
