"""Permapeople Plant API client implementation."""

import logging
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
            True if service can be reached, False otherwise
        """
        if not self._key_id or not self._key_secret:
            return False

        try:
            # Try to list plants with a limit of 1
            response = self._session.get(
                f"{self.BASE_URL}/plants",
                params={"last_id": 0},
                timeout=5,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def _parse_species(self, data: dict[str, Any]) -> PlantSpeciesData:
        """Parse Permapeople API response into PlantSpeciesData.

        Args:
            data: Raw API response data

        Returns:
            Parsed plant species data
        """
        scientific_name = data.get("scientific_name", "Unknown")
        common_name = data.get("name", "Unknown")

        # Parse the flexible key-value data array
        data_dict: dict[str, str] = {}
        for item in data.get("data", []):
            if isinstance(item, dict):
                key = item.get("key", "")
                value = item.get("value", "")
                if key:
                    data_dict[key.lower()] = value

        # Extract structured data from key-value pairs
        family = data_dict.get("family", "")

        # Parse cycle
        cycle = PlantCycle.UNKNOWN
        # Permapeople uses "Layer" field which might indicate plant type

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

        # Check if edible
        edible = data_dict.get("edible", "").lower() == "true"
        edible_parts_str = data_dict.get("edible parts", "")
        edible_parts = [part.strip() for part in edible_parts_str.split(",")] if edible_parts_str else []

        soil_type = data_dict.get("soil type", "")

        return PlantSpeciesData(
            scientific_name=scientific_name,
            common_name=common_name,
            family=family,
            genus="",  # Not always provided
            cycle=cycle,
            growth_rate=growth_rate,
            sun_requirement=sun_req,
            water_needs=water_needs,
            hardiness_zone_min=hardiness_min,
            hardiness_zone_max=hardiness_max,
            soil_type=soil_type,
            edible=edible,
            edible_parts=edible_parts,
            image_url="",  # Permapeople doesn't provide images in API
            thumbnail_url="",
            data_source="permapeople",
            source_id=str(data.get("id", "")),
            description=data.get("description", ""),
            raw_data=data,
        )
