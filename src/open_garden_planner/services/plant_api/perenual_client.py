"""Perenual Plant API client implementation."""

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


class PerenualClient(PlantAPIClient):
    """Client for the Perenual Plant API.

    API Documentation: https://perenual.com/docs/api
    Free tier: 10,000 requests/day, access to 10,000+ plant species
    """

    BASE_URL = "https://perenual.com/api"
    API_KEY_ENV_VAR = "PERENUAL_API_KEY"

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Perenual client.

        Args:
            api_key: Optional API key. If not provided, will look for
                    PERENUAL_API_KEY environment variable.
        """
        import os

        self._api_key = api_key or os.environ.get(self.API_KEY_ENV_VAR, "")
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "OpenGardenPlanner/1.0"})

    @property
    def name(self) -> str:
        """Name of the API service.

        Returns:
            Service name
        """
        return "Perenual"

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
        if not self._api_key:
            raise PlantAPIError(f"{self.name} API key not configured")

        try:
            response = self._session.get(
                f"{self.BASE_URL}/species-list",
                params={"key": self._api_key, "q": query, "page": 1},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            results: list[PlantSpeciesData] = []
            for item in data.get("data", [])[:limit]:
                try:
                    plant_data = self._parse_species(item)
                    results.append(plant_data)
                except Exception as e:
                    logger.warning(f"Failed to parse Perenual plant data: {e}")
                    continue

            return results

        except requests.RequestException as e:
            raise PlantAPIError(f"{self.name} API request failed: {e}") from e

    def get_by_id(self, plant_id: str) -> PlantSpeciesData:
        """Get detailed plant data by Perenual ID.

        Args:
            plant_id: Unique identifier in Perenual's database

        Returns:
            Complete plant species data

        Raises:
            PlantAPIError: If the API request fails or plant not found
        """
        if not self._api_key:
            raise PlantAPIError(f"{self.name} API key not configured")

        try:
            response = self._session.get(
                f"{self.BASE_URL}/species/details/{plant_id}",
                params={"key": self._api_key},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_species(data)

        except requests.RequestException as e:
            raise PlantAPIError(f"{self.name} API request failed: {e}") from e

    def is_available(self) -> bool:
        """Check if the Perenual API is currently available.

        Returns:
            True if service can be reached, False otherwise
        """
        if not self._api_key:
            return False

        try:
            response = self._session.get(
                f"{self.BASE_URL}/species-list",
                params={"key": self._api_key, "page": 1},
                timeout=5,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def _parse_species(self, data: dict[str, Any]) -> PlantSpeciesData:
        """Parse Perenual API response into PlantSpeciesData.

        Args:
            data: Raw API response data

        Returns:
            Parsed plant species data
        """
        # Extract basic info
        scientific_name = data.get("scientific_name", ["Unknown"])[0] if isinstance(data.get("scientific_name"), list) else data.get("scientific_name", "Unknown")
        common_name = data.get("common_name", "Unknown")

        # Parse cycle (annual, perennial, etc.)
        cycle_str = data.get("cycle", "").lower()
        cycle = PlantCycle.UNKNOWN
        if "annual" in cycle_str:
            cycle = PlantCycle.ANNUAL
        elif "biennial" in cycle_str:
            cycle = PlantCycle.BIENNIAL
        elif "perennial" in cycle_str:
            cycle = PlantCycle.PERENNIAL

        # Parse sun requirements
        sunlight_list = data.get("sunlight", [])
        sun_req = SunRequirement.UNKNOWN
        if sunlight_list:
            sunlight_str = " ".join(sunlight_list).lower()
            if "full sun" in sunlight_str or "full_sun" in sunlight_str:
                sun_req = SunRequirement.FULL_SUN
            elif "part shade" in sunlight_str or "partial" in sunlight_str:
                sun_req = SunRequirement.PARTIAL_SHADE

        # Parse watering needs
        watering = data.get("watering", "").lower()
        water_needs = WaterNeeds.UNKNOWN
        if "minimum" in watering or "low" in watering:
            water_needs = WaterNeeds.LOW
        elif "average" in watering or "moderate" in watering:
            water_needs = WaterNeeds.MEDIUM
        elif "frequent" in watering or "high" in watering:
            water_needs = WaterNeeds.HIGH

        # Extract images
        default_image = data.get("default_image", {})
        image_url = ""
        thumbnail_url = ""
        if isinstance(default_image, dict):
            image_url = default_image.get("original_url", "")
            thumbnail_url = default_image.get("thumbnail", "")

        # Size information would be extracted here
        # Perenual doesn't provide structured dimensions in free tier
        # Would need detailed endpoint or premium tier for accurate measurements

        return PlantSpeciesData(
            scientific_name=scientific_name,
            common_name=common_name,
            family="",  # Not in basic response
            genus="",  # Not in basic response
            cycle=cycle,
            growth_rate=GrowthRate.UNKNOWN,  # Not available in free tier
            sun_requirement=sun_req,
            water_needs=water_needs,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            data_source="perenual",
            source_id=str(data.get("id", "")),
            description=data.get("description", ""),
            flowering=data.get("flowering_season") is not None,
            raw_data=data,
        )
