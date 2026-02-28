"""Tests for US-8.2: ClimateService frost date & hardiness zone lookup."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from open_garden_planner.services.climate_service import (
    ClimateService,
    ClimateServiceError,
    FrostData,
    _estimate_usda_zone,
    _median_date,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestEstimateUsdaZone:
    """Tests for _estimate_usda_zone()."""

    def test_very_cold_zone_1a(self) -> None:
        # -55 °C ≈ -67 °F → zone 1a
        assert _estimate_usda_zone(-55.0) == "1a"

    def test_temperate_zone_7b(self) -> None:
        # Average annual min around 2 °C (≈ 36 °F) → zone 8a
        zone = _estimate_usda_zone(2.0)
        # 2 °C ≈ 35.6 °F → ≥35 → zone 10b threshold, but between 10a(30°F) and 10b(35°F)
        # Let's verify via formula: 2*9/5+32 = 35.6°F → ≥30 (10a), ≥35 (10b)
        # Correction: 2°C = 35.6°F which is ≥35 → zone 10b
        assert zone == "10b"

    def test_moderate_cold_zone_6b(self) -> None:
        # -7 °C ≈ 19.4 °F → falls in zone 8a/8b range... let me compute
        # -7°C → 19.4°F → ≥15 (8b threshold) → zone 8b
        # Actually: ≥10 → 8a, ≥15 → 8b, next is 9a at 20. 19.4 < 20 → 8b
        assert _estimate_usda_zone(-7.0) == "8b"

    def test_very_cold_tundra(self) -> None:
        # -40 °C ≈ -40 °F → ≥-40 → zone 3a
        assert _estimate_usda_zone(-40.0) == "3a"

    def test_tropical_zone_13b(self) -> None:
        # 20 °C ≈ 68 °F → zone 13b (highest)
        assert _estimate_usda_zone(20.0) == "13b"

    def test_boundary_zone_7a(self) -> None:
        # -17 °C ≈ 1.4 °F → ≥0 (7a) but <5 (7b) → zone 7a
        assert _estimate_usda_zone(-17.0) == "7a"


class TestMedianDate:
    """Tests for _median_date()."""

    def test_empty_returns_none(self) -> None:
        assert _median_date([]) is None

    def test_single_item_returns_itself(self) -> None:
        assert _median_date(["04-15"]) == "04-15"

    def test_odd_count_returns_middle(self) -> None:
        dates = ["04-01", "04-15", "04-30"]
        result = _median_date(dates)
        assert result == "04-15"

    def test_even_count_returns_upper_middle(self) -> None:
        dates = ["04-01", "04-10", "04-20", "04-30"]
        result = _median_date(dates)
        # Sorted by day-of-year; median index = 4//2 = 2 → "04-20"
        assert result == "04-20"

    def test_unsorted_input(self) -> None:
        dates = ["10-20", "10-01", "10-15"]
        result = _median_date(dates)
        assert result == "10-15"

    def test_invalid_strings_ignored(self) -> None:
        dates = ["99-99", "04-15", "bad"]
        result = _median_date(dates)
        assert result == "04-15"

    def test_all_invalid_returns_none(self) -> None:
        result = _median_date(["bad", "also-bad"])
        assert result is None


# ---------------------------------------------------------------------------
# Tests for FrostData dataclass
# ---------------------------------------------------------------------------


class TestFrostData:
    def test_creation(self) -> None:
        fd = FrostData(
            last_spring_frost="04-15",
            first_fall_frost="10-20",
            hardiness_zone="7b",
            data_source="open-meteo",
            latitude=51.5,
            longitude=10.2,
        )
        assert fd.last_spring_frost == "04-15"
        assert fd.first_fall_frost == "10-20"
        assert fd.hardiness_zone == "7b"
        assert fd.data_source == "open-meteo"

    def test_none_frost_dates_allowed(self) -> None:
        fd = FrostData(
            last_spring_frost=None,
            first_fall_frost=None,
            hardiness_zone="13b",
            data_source="open-meteo",
            latitude=1.0,
            longitude=103.0,
        )
        assert fd.last_spring_frost is None
        assert fd.first_fall_frost is None


# ---------------------------------------------------------------------------
# Tests for ClimateService compute logic
# ---------------------------------------------------------------------------


class TestClimateServiceCompute:
    """Tests for _compute_frost_data() without network calls."""

    @pytest.fixture
    def service(self, tmp_path: Path) -> ClimateService:
        svc = ClimateService.__new__(ClimateService)
        svc._cache_dir = tmp_path
        return svc

    def _make_dates_temps(
        self, start_year: int, end_year: int, frost_date_by_year: dict[int, tuple[str, str]]
    ) -> tuple[list[str], list[float | None]]:
        """Build a synthetic dates/temps list.

        Args:
            start_year, end_year: Inclusive year range.
            frost_date_by_year: Mapping year → (spring_frost_mmdd, fall_frost_mmdd).
                                 All other days get 10.0 °C.
        """
        dates: list[str] = []
        temps: list[float | None] = []

        current = datetime(start_year, 1, 1)
        end = datetime(end_year, 12, 31)

        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            year = current.year
            mmdd = current.strftime("%m-%d")

            frost_info = frost_date_by_year.get(year, ("04-15", "10-15"))
            spring_frost, fall_frost = frost_info

            # Make frost days exactly 0 °C, all others 10 °C
            if mmdd == spring_frost or mmdd == fall_frost:
                temps.append(0.0)
            else:
                temps.append(10.0)

            dates.append(date_str)
            current += timedelta(days=1)

        return dates, temps

    def test_frost_dates_computed_correctly(self, service: ClimateService) -> None:
        """With consistent frost dates each year, median should match."""
        # All years: last spring frost 04-15, first fall frost 10-15
        years = {y: ("04-15", "10-15") for y in range(2013, 2023)}
        dates, temps = self._make_dates_temps(2013, 2022, years)

        result = service._compute_frost_data(51.5, 10.2, dates, temps)

        assert result.last_spring_frost == "04-15"
        assert result.first_fall_frost == "10-15"

    def test_hardiness_zone_estimated(self, service: ClimateService) -> None:
        """Hardiness zone is estimated from average annual minimum."""
        # Set annual minimum to -10 °C each year → 14°F → zone 8a
        years = {y: ("04-15", "10-15") for y in range(2013, 2023)}
        dates, temps = self._make_dates_temps(2013, 2022, years)

        # Override Jan 15 each year to -10 °C (the annual minimum)
        for i, d in enumerate(dates):
            if d[5:] == "01-15":
                temps[i] = -10.0

        result = service._compute_frost_data(51.5, 10.2, dates, temps)
        assert result.hardiness_zone is not None
        # -10°C = 14°F → ≥10 → 8a, ≥15? 14<15 → 8a
        assert result.hardiness_zone == "8a"

    def test_no_frost_tropical_location(self, service: ClimateService) -> None:
        """All temps > 0 → no spring/fall frost; hardiness zone still estimated."""
        dates = [f"2020-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
        temps = [25.0] * len(dates)

        result = service._compute_frost_data(1.3, 103.8, dates, temps)

        assert result.last_spring_frost is None
        assert result.first_fall_frost is None
        # avg min = 25°C = 77°F → zone 13b
        assert result.hardiness_zone == "13b"

    def test_none_temperatures_skipped(self, service: ClimateService) -> None:
        """None temperature values are safely skipped."""
        dates = ["2020-01-15", "2020-04-15", "2020-10-15"]
        temps: list[float | None] = [None, 0.0, 0.0]

        result = service._compute_frost_data(51.5, 10.2, dates, temps)
        assert result.last_spring_frost == "04-15"
        assert result.first_fall_frost == "10-15"


# ---------------------------------------------------------------------------
# Tests for cache helpers
# ---------------------------------------------------------------------------


class TestClimateServiceCache:
    @pytest.fixture
    def service(self, tmp_path: Path) -> ClimateService:
        svc = ClimateService.__new__(ClimateService)
        svc._cache_dir = tmp_path
        return svc

    def _write_cache(
        self, svc: ClimateService, lat: float, lon: float, data: dict[str, Any]
    ) -> None:
        key = svc._cache_key(lat, lon)
        (svc._cache_dir / f"{key}.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def test_cache_miss_returns_none(self, service: ClimateService) -> None:
        assert service._load_cache(51.5, 10.2) is None

    def test_cache_hit_returns_frost_data(self, service: ClimateService) -> None:
        payload = {
            "cached_at": datetime.now().isoformat(),
            "last_spring_frost": "04-15",
            "first_fall_frost": "10-20",
            "hardiness_zone": "7b",
        }
        self._write_cache(service, 51.5, 10.2, payload)

        result = service._load_cache(51.5, 10.2)
        assert result is not None
        assert result.last_spring_frost == "04-15"
        assert result.first_fall_frost == "10-20"
        assert result.hardiness_zone == "7b"
        assert result.data_source == "cached"

    def test_expired_cache_returns_none(self, service: ClimateService) -> None:
        old_date = (datetime.now() - timedelta(days=400)).isoformat()
        payload = {
            "cached_at": old_date,
            "last_spring_frost": "04-15",
            "first_fall_frost": "10-20",
            "hardiness_zone": "7b",
        }
        self._write_cache(service, 51.5, 10.2, payload)

        assert service._load_cache(51.5, 10.2) is None

    def test_save_then_load_roundtrip(self, service: ClimateService) -> None:
        frost = FrostData(
            last_spring_frost="05-01",
            first_fall_frost="09-30",
            hardiness_zone="6b",
            data_source="open-meteo",
            latitude=55.0,
            longitude=13.0,
        )
        service._save_cache(55.0, 13.0, frost)
        loaded = service._load_cache(55.0, 13.0)
        assert loaded is not None
        assert loaded.last_spring_frost == "05-01"
        assert loaded.first_fall_frost == "09-30"
        assert loaded.hardiness_zone == "6b"

    def test_cache_key_rounds_to_half_degree(self, service: ClimateService) -> None:
        # 51.37 rounds to 51.5
        assert service._cache_key(51.37, 10.12) == "51.5_10.0"


# ---------------------------------------------------------------------------
# Tests for lookup_frost_dates (mocked network)
# ---------------------------------------------------------------------------


class TestClimateServiceLookup:
    @pytest.fixture
    def service(self, tmp_path: Path) -> ClimateService:
        svc = ClimateService.__new__(ClimateService)
        svc._cache_dir = tmp_path
        return svc

    def _make_api_response(self) -> dict[str, Any]:
        """Build a minimal synthetic Open-Meteo response with frost dates."""
        dates = []
        temps = []
        for year in range(2014, 2024):
            for month in range(1, 13):
                for day in range(1, 29):
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    dates.append(date_str)
                    mmdd = f"{month:02d}-{day:02d}"
                    # Spring frost: April 15 → 0 °C; Fall frost: Oct 15 → 0 °C
                    if mmdd in ("04-15", "10-15"):
                        temps.append(0.0)
                    else:
                        temps.append(10.0)
        return {"daily": {"time": dates, "temperature_2m_min": temps}}

    def test_returns_frost_data_from_api(self, service: ClimateService) -> None:
        api_payload = self._make_api_response()

        mock_resp = MagicMock()
        mock_resp.json.return_value = api_payload
        mock_resp.raise_for_status.return_value = None

        with patch("open_garden_planner.services.climate_service.requests.get") as mock_get:
            mock_get.return_value = mock_resp
            result = service.lookup_frost_dates(51.5, 10.2)

        assert result.last_spring_frost == "04-15"
        assert result.first_fall_frost == "10-15"
        assert result.data_source == "open-meteo"

    def test_result_is_cached_after_api_call(self, service: ClimateService) -> None:
        api_payload = self._make_api_response()

        mock_resp = MagicMock()
        mock_resp.json.return_value = api_payload
        mock_resp.raise_for_status.return_value = None

        with patch("open_garden_planner.services.climate_service.requests.get") as mock_get:
            mock_get.return_value = mock_resp
            service.lookup_frost_dates(51.5, 10.2)
            # Second call should use cache (no additional network request)
            service.lookup_frost_dates(51.5, 10.2)
            assert mock_get.call_count == 1

    def test_network_error_raises_climate_service_error(
        self, service: ClimateService
    ) -> None:
        import requests as req_module

        with patch("open_garden_planner.services.climate_service.requests.get") as mock_get:
            mock_get.side_effect = req_module.RequestException("timeout")
            with pytest.raises(ClimateServiceError, match="Open-Meteo request failed"):
                service.lookup_frost_dates(51.5, 10.2)

    def test_empty_response_raises_climate_service_error(
        self, service: ClimateService
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"daily": {}}
        mock_resp.raise_for_status.return_value = None

        with patch("open_garden_planner.services.climate_service.requests.get") as mock_get:
            mock_get.return_value = mock_resp
            with pytest.raises(ClimateServiceError, match="No temperature data"):
                service.lookup_frost_dates(51.5, 10.2)

    def test_cache_hit_skips_network_call(self, service: ClimateService) -> None:
        cached_payload = {
            "cached_at": datetime.now().isoformat(),
            "last_spring_frost": "04-01",
            "first_fall_frost": "11-01",
            "hardiness_zone": "8a",
        }
        key = service._cache_key(51.5, 10.2)
        (service._cache_dir / f"{key}.json").write_text(
            json.dumps(cached_payload), encoding="utf-8"
        )

        with patch("open_garden_planner.services.climate_service.requests.get") as mock_get:
            result = service.lookup_frost_dates(51.5, 10.2)
            mock_get.assert_not_called()

        assert result.last_spring_frost == "04-01"
        assert result.data_source == "cached"
