"""Permapeople Plant API client implementation."""

import logging
import re
from typing import Any

import requests

from open_garden_planner.models.plant_data import (
    GrowthRate,
    PlantCycle,
    PlantSpeciesData,
    SunRequirement,
    WaterNeeds,
)

from .base import PlantAPIClient, PlantAPIError

logger = logging.getLogger(__name__)


_NUMBER_RE = re.compile(r"\d+\.?\d*")


def _extract_numbers(value: str) -> list[float]:
    """Extract numeric tokens from a string like "1.5-3.0m" or "6.2-6.8".

    Deliberately excludes a leading sign from the pattern -- Permapeople's
    range separator is a plain hyphen (and, on at least one live record, an
    en dash), and treating either as part of the following number would
    silently negate it.
    """
    return [float(match) for match in _NUMBER_RE.findall(value or "")]


def _meters_str_to_cm(value: str) -> float | None:
    """Parse a Permapeople Height/Width string (metres) into centimetres.

    Handles a bare value ("10.0"), a range ("1.5-3.0" or "15-32m", using the
    upper bound as the mature size), and an optional trailing unit suffix --
    all live-observed formats (#296).
    """
    numbers = _extract_numbers(value)
    return numbers[-1] * 100 if numbers else None


class PermapeopleClient(PlantAPIClient):
    """Client for the Permapeople Plant API.

    API Documentation: https://permapeople.org/knowledgebase/api-docs.html
    Free for non-commercial use, requires authentication headers.
    Licensed under CC BY-SA 4.0.
    """

    BASE_URL = "https://permapeople.org/api"
    KEY_ID_ENV_VAR = "PERMAPEOPLE_KEY_ID"
    KEY_SECRET_ENV_VAR = "PERMAPEOPLE_KEY_SECRET"

    def __init__(self, key_id: str | None = None, key_secret: str | None = None) -> None:
        """Initialize the Permapeople client.

        Args:
            key_id: Optional API key ID. If not provided, will look for
                   PERMAPEOPLE_KEY_ID environment variable.
            key_secret: Optional API key secret. If not provided, will look for
                       PERMAPEOPLE_KEY_SECRET environment variable.
        """
        import os

        self._key_id = key_id or os.environ.get(self.KEY_ID_ENV_VAR, "")
        self._key_secret = key_secret or os.environ.get(self.KEY_SECRET_ENV_VAR, "")
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "OpenGardenPlanner/1.0",
            "Content-Type": "application/json",
        })

        if self._key_id and self._key_secret:
            self._session.headers.update({
                "x-permapeople-key-id": self._key_id,
                "x-permapeople-key-secret": self._key_secret,
            })

    @property
    def name(self) -> str:
        """Name of the API service.

        Returns:
            Service name
        """
        return "Permapeople"

    def search(self, query: str, limit: int = 10) -> list[PlantSpeciesData]:
        """Search for plants by common or scientific name.

        Args:
            query: Search term (plant name or partial name)
            limit: Maximum number of results to return

        Returns:
            List of matching plant species data

        Raises:
            PlantAPIError: If the API request fails
        """
        if not self._key_id or not self._key_secret:
            raise PlantAPIError(f"{self.name} API credentials not configured")

        try:
            response = self._session.post(
                f"{self.BASE_URL}/search",
                json={"q": query},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            results: list[PlantSpeciesData] = []
            for item in data.get("plants", [])[:limit]:
                try:
                    plant_data = self._parse_species(item)
                    results.append(plant_data)
                except Exception as e:
                    logger.warning(f"Failed to parse Permapeople plant data: {e}")
                    continue

            return results

        except requests.RequestException as e:
            raise PlantAPIError(f"{self.name} API request failed: {e}") from e

    def get_by_id(self, plant_id: str) -> PlantSpeciesData:
        """Get detailed plant data by Permapeople ID.

        Args:
            plant_id: Unique identifier in Permapeople's database

        Returns:
            Complete plant species data

        Raises:
            PlantAPIError: If the API request fails or plant not found
        """
        if not self._key_id or not self._key_secret:
            raise PlantAPIError(f"{self.name} API credentials not configured")

        try:
            response = self._session.get(
                f"{self.BASE_URL}/plants/{plant_id}",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_species(data)

        except requests.RequestException as e:
            raise PlantAPIError(f"{self.name} API request failed: {e}") from e

    def is_available(self) -> bool:
        """Check if the Permapeople API is currently available.

        Returns:
            True if credentials are valid and the service responds, False if
            credentials are missing or explicitly rejected (401/403)

        Raises:
            PlantAPIError: If the request itself fails (timeout, DNS,
                connection reset, etc.) or the service returns any other
                non-2xx status (5xx, 429, ...) -- kept distinct from a
                definitive rejection so callers can tell "unreachable"/
                "broken" apart from "rejected" instead of reporting all
                three as a credentials problem
        """
        if not self._key_id or not self._key_secret:
            return False

        try:
            # per_page is a documented Permapeople parameter (default/max 100
            # -- permapeople.org/knowledgebase/api-docs.html). Bounding it to 1
            # keeps this a cheap connectivity probe: the unbounded default
            # page returns ~100 full records (~250KB) and reliably took 6s+ to
            # arrive, so a 5s timeout here silently misreported valid
            # credentials as failed (issue #294). Measured ~0.5-1.0s at
            # per_page=1, so the original timeout stays generous unchanged.
            response = self._session.get(
                f"{self.BASE_URL}/plants",
                params={"last_id": 0, "per_page": 1},
                timeout=5,
            )
        except requests.RequestException as e:
            # A genuine connectivity failure must not be reported to the user
            # as "check your credentials" (issue #294).
            raise PlantAPIError(f"connectivity check failed: {e}") from e

        if response.status_code == 200:
            return True
        if response.status_code in (401, 403):
            return False
        # Any other non-2xx (5xx, 429, ...) is a server-side problem, not a
        # credentials rejection -- must not collapse into the same False as
        # 401/403 or the "check your credentials" message reappears for an
        # outage (issue #294).
        raise PlantAPIError(f"unexpected HTTP {response.status_code} on connectivity check")

    def is_configured(self) -> bool:
        """True when both credentials are present. See `PlantAPIClient.is_configured()`."""
        return bool(self._key_id and self._key_secret)

    def _parse_species(self, data: dict[str, Any]) -> PlantSpeciesData:
        """Parse Permapeople API response into PlantSpeciesData.

        Args:
            data: Raw API response data

        Returns:
            Parsed plant species data
        """
        scientific_name = data.get("scientific_name") or "Unknown"
        common_name = data.get("name") or "Unknown"

        # Parse the flexible key-value data array. A present key with a JSON
        # null value (real Permapeople records have these) must not survive as
        # None -- every lookup below chains a .lower()/.split() off the
        # result, which crashed the whole record before this guard (#296).
        data_dict: dict[str, str] = {}
        for item in data.get("data") or []:
            if isinstance(item, dict):
                key = item.get("key", "")
                value = item.get("value")
                if key:
                    data_dict[key.lower()] = str(value) if value is not None else ""

        # Extract structured data from key-value pairs
        family = data_dict.get("family", "")
        genus = data_dict.get("genus", "")

        # Parse life cycle -- Permapeople's "Life cycle" key (e.g. "Perennial",
        # "Annual, Perennial") maps directly; a multi-value string keeps the
        # same annual > biennial > perennial precedence used elsewhere in this
        # file (#296). "Layer" (Trees/Shrubs/...) is a permaculture design
        # category, not a life cycle -- it was never the right field.
        life_cycle_str = data_dict.get("life cycle", "").lower()
        cycle = PlantCycle.UNKNOWN
        if "annual" in life_cycle_str:
            cycle = PlantCycle.ANNUAL
        elif "biennial" in life_cycle_str:
            cycle = PlantCycle.BIENNIAL
        elif "perennial" in life_cycle_str:
            cycle = PlantCycle.PERENNIAL

        # Parse sun requirements
        light_req = data_dict.get("light requirement", "").lower()
        sun_req = SunRequirement.UNKNOWN
        if "full sun" in light_req:
            sun_req = SunRequirement.FULL_SUN
        elif "partial sun" in light_req or "partial shade" in light_req:
            sun_req = SunRequirement.PARTIAL_SHADE
        elif "shade" in light_req:
            sun_req = SunRequirement.FULL_SHADE

        # Parse water requirements
        water_req = data_dict.get("water requirement", "").lower()
        water_needs = WaterNeeds.UNKNOWN
        if "dry" in water_req or "minimal" in water_req:
            water_needs = WaterNeeds.LOW
        elif "moist" in water_req or "moderate" in water_req:
            water_needs = WaterNeeds.MEDIUM
        elif "wet" in water_req or "frequent" in water_req:
            water_needs = WaterNeeds.HIGH

        # Parse hardiness zone
        hardiness_str = data_dict.get("usda hardiness zone", "")
        hardiness_min, hardiness_max = None, None
        if hardiness_str:
            # Format might be "3-9" or just "5"
            parts = hardiness_str.split("-")
            try:
                hardiness_min = int(parts[0].strip())
                hardiness_max = int(parts[1].strip()) if len(parts) > 1 else hardiness_min
            except ValueError:
                pass

        # Parse growth rate
        growth_str = data_dict.get("growth", "").lower()
        growth_rate = GrowthRate.UNKNOWN
        if "slow" in growth_str:
            growth_rate = GrowthRate.SLOW
        elif "medium" in growth_str or "moderate" in growth_str:
            growth_rate = GrowthRate.MEDIUM
        elif "fast" in growth_str or "rapid" in growth_str:
            growth_rate = GrowthRate.FAST

        # Parse mature size. Permapeople expresses Height/Width in metres
        # (live-observed: Apple 10.0/9, Tomato 2.0/1.00 -- #296); our model
        # stores centimetres.
        max_height_cm = _meters_str_to_cm(data_dict.get("height", ""))
        max_spread_cm = _meters_str_to_cm(data_dict.get("width", ""))

        # Parse soil pH range (e.g. "6.2-6.8"). A *single* value (e.g. "6.5")
        # is an optimum, not a hard min-and-max band -- treating it as both
        # collapsed the acceptable range to zero width and made
        # soil_service.get_mismatched_plants() (deliberately tight, +/-0.05)
        # fire a false mismatch for any real-world reading that wasn't that
        # exact value (live-observed: Permapeople's "Walking onion" record is
        # a single "6.5", #296 review). Only a genuine range gives both ends.
        ph_numbers = _extract_numbers(data_dict.get("soil ph", ""))
        ph_min = ph_numbers[0] if len(ph_numbers) > 1 else None
        ph_max = ph_numbers[-1] if len(ph_numbers) > 1 else None

        # Check if edible
        edible = data_dict.get("edible", "").lower() == "true"
        edible_parts_str = data_dict.get("edible parts", "")
        edible_parts = [part.strip() for part in edible_parts_str.split(",")] if edible_parts_str else []

        soil_type = data_dict.get("soil type", "")

        # Permapeople does provide photos -- top-level `images`, not in the
        # key-value `data` array (live-verified on every plant probed; the
        # old "doesn't provide images" assumption here was wrong, #296).
        images = data.get("images")
        image_url, thumbnail_url = "", ""
        if isinstance(images, dict):
            image_url = images.get("title") or images.get("thumb") or ""
            thumbnail_url = images.get("thumb") or images.get("title") or ""

        return PlantSpeciesData(
            scientific_name=scientific_name,
            common_name=common_name,
            family=family,
            genus=genus,
            cycle=cycle,
            growth_rate=growth_rate,
            sun_requirement=sun_req,
            water_needs=water_needs,
            max_height_cm=max_height_cm,
            max_spread_cm=max_spread_cm,
            hardiness_zone_min=hardiness_min,
            hardiness_zone_max=hardiness_max,
            soil_type=soil_type,
            ph_min=ph_min,
            ph_max=ph_max,
            edible=edible,
            edible_parts=edible_parts,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            data_source="permapeople",
            source_id=str(data.get("id") or ""),
            description=data.get("description") or "",
            raw_data=data,
        )
