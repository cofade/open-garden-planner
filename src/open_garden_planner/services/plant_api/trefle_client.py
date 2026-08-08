"""Trefle Plant API client implementation."""

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


class TrefleClient(PlantAPIClient):
    """Client for the Trefle Plant API.

    API Documentation: https://docs.trefle.io/
    Comprehensive botanical database with 400,000+ species.
    """

    BASE_URL = "https://trefle.io/api/v1"
    API_TOKEN_ENV_VAR = "TREFLE_API_TOKEN"

    def __init__(self, api_token: str | None = None) -> None:
        """Initialize the Trefle client.

        Args:
            api_token: Optional API token. If not provided, will look for
                      TREFLE_API_TOKEN environment variable.
        """
        import os

        self._api_token = api_token or os.environ.get(self.API_TOKEN_ENV_VAR, "")
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "OpenGardenPlanner/1.0"})

    @property
    def name(self) -> str:
        """Name of the API service.

        Returns:
            Service name
        """
        return "Trefle"

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
        if not self._api_token:
            raise PlantAPIError(f"{self.name} API token not configured")

        try:
            response = self._session.get(
                f"{self.BASE_URL}/plants/search",
                params={"token": self._api_token, "q": query},
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
                    logger.warning(f"Failed to parse Trefle plant data: {e}")
                    continue

            return results

        except requests.RequestException as e:
            raise PlantAPIError(f"{self.name} API request failed: {e}") from e

    def get_by_id(self, plant_id: str) -> PlantSpeciesData:
        """Get detailed plant data by Trefle ID.

        Args:
            plant_id: Unique identifier in Trefle's database (slug or numeric ID)

        Returns:
            Complete plant species data

        Raises:
            PlantAPIError: If the API request fails or plant not found
        """
        if not self._api_token:
            raise PlantAPIError(f"{self.name} API token not configured")

        try:
            response = self._session.get(
                f"{self.BASE_URL}/plants/{plant_id}",
                params={"token": self._api_token},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            # The response has data.main_species for detailed species info
            plant_data = data.get("data", {})
            main_species = plant_data.get("main_species", plant_data)

            return self._parse_species(main_species)

        except requests.RequestException as e:
            raise PlantAPIError(f"{self.name} API request failed: {e}") from e

    def is_available(self) -> bool:
        """Check if the Trefle API is currently available.

        Returns:
            True if service can be reached, False otherwise
        """
        if not self._api_token:
            return False

        try:
            response = self._session.get(
                f"{self.BASE_URL}/kingdoms",
                params={"token": self._api_token},
                timeout=5,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def _parse_species(self, data: dict[str, Any]) -> PlantSpeciesData:
        """Parse Trefle API response into PlantSpeciesData.

        Args:
            data: Raw API response data

        Returns:
            Parsed plant species data
        """
        # Basic info
        scientific_name = data.get("scientific_name", "Unknown")
        common_name = data.get("common_name") or "Unknown"
        family = data.get("family", "")
        genus = data.get("genus", "")

        # Parse duration/cycle (annual, perennial, etc.)
        cycle = PlantCycle.UNKNOWN
        duration_list = data.get("duration", []) or []
        if duration_list:
            duration_str = " ".join(duration_list).lower()
            if "annual" in duration_str:
                cycle = PlantCycle.ANNUAL
            elif "biennial" in duration_str:
                cycle = PlantCycle.BIENNIAL
            elif "perennial" in duration_str:
                cycle = PlantCycle.PERENNIAL

        # Parse sun requirements from growth.light (0-10 scale)
        sun_req = SunRequirement.UNKNOWN
        growth = data.get("growth", {}) or {}
        light_level = growth.get("light")
        if light_level is not None:
            # Trefle uses 0-10 scale: 0=no light, 10=very intensive
            if light_level >= 8:
                sun_req = SunRequirement.FULL_SUN
            elif light_level >= 5:
                sun_req = SunRequirement.PARTIAL_SHADE
            elif light_level >= 0:
                sun_req = SunRequirement.FULL_SHADE

        # Parse water requirements from growth.atmospheric_humidity (0-10 scale)
        water_needs = WaterNeeds.UNKNOWN
        humidity_level = growth.get("atmospheric_humidity")
        if humidity_level is not None:
            # Trefle uses 0-10 scale for humidity
            if humidity_level >= 7:
                water_needs = WaterNeeds.HIGH
            elif humidity_level >= 4:
                water_needs = WaterNeeds.MEDIUM
            elif humidity_level >= 0:
                water_needs = WaterNeeds.LOW

        # Growth rate (not directly available in Trefle, would need to infer from days_to_harvest)
        growth_rate = GrowthRate.UNKNOWN
        days_to_harvest = growth.get("days_to_harvest")
        if days_to_harvest:
            # Rough estimation: <60 days = fast, 60-120 = medium, >120 = slow
            if days_to_harvest < 60:
                growth_rate = GrowthRate.FAST
            elif days_to_harvest < 120:
                growth_rate = GrowthRate.MEDIUM
            else:
                growth_rate = GrowthRate.SLOW

        # Height information
        specifications = data.get("specifications", {}) or {}
        max_height_data = specifications.get("maximum_height", {}) or {}
        max_height_cm = max_height_data.get("cm")

        # Soil pH range. Trefle docs (docs.trefle.io/docs/advanced/plants-fields):
        # "The minimum/maximum acceptable soil pH ... for the plant" -- a
        # direct 1:1 with ph_min/ph_max. Lives under `growth`, not
        # `specifications` (#296) -- verified against a live Carrot response
        # (growth.ph_minimum=6.5, growth.ph_maximum=7.0).
        ph_min = growth.get("ph_minimum")
        ph_max = growth.get("ph_maximum")

        # Nutrient demand from the 0-10 soil_nutriments scale, mirroring the
        # light/atmospheric_humidity 0-10-scale mapping above (#296). Trefle
        # docs: "Required quantity of nutriments in the soil, on a scale from
        # 0 (oligotrophic) to 10 (hypereutrophic)" -- this is the plant's
        # demand, not its tolerance, so higher really does mean "heavier".
        nutrient_demand = None
        soil_nutriments = growth.get("soil_nutriments")
        if soil_nutriments is not None:
            if soil_nutriments >= 7:
                nutrient_demand = "heavy"
            elif soil_nutriments >= 4:
                nutrient_demand = "medium"
            else:
                nutrient_demand = "light"
        # NOTE: Trefle's `specifications.nitrogen_fixation` looked like a
        # natural "fixer" override, but it's a documented *string* field with
        # an unspecified value domain, and it came back null on every one of
        # 46 live legume records sampled during review (#296) -- not mapped
        # here for lack of any real response to verify the shape against.

        # Foliage
        foliage = data.get("foliage", {}) or {}
        foliage_color_raw = foliage.get("color")
        foliage_color = ", ".join(foliage_color_raw) if isinstance(foliage_color_raw, list) else ""
        foliage_texture = foliage.get("texture") or ""

        # Edible information
        edible = data.get("edible") or False
        edible_part_list = data.get("edible_part", []) or []
        edible_parts = [part for part in edible_part_list if part]

        # Image URL
        image_url = data.get("image_url", "")

        # Flowering information
        flower = data.get("flower", {}) or {}
        flower_color = None
        flower_color_raw = flower.get("color")
        if isinstance(flower_color_raw, list) and flower_color_raw:
            flower_color = ", ".join(flower_color_raw)

        # Description from observations or growth description
        observations = data.get("observations", "")
        growth_desc = growth.get("description", "")
        description = observations or growth_desc

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
            ph_min=ph_min,
            ph_max=ph_max,
            nutrient_demand=nutrient_demand,
            image_url=image_url,
            thumbnail_url=image_url,  # Trefle doesn't provide separate thumbnails
            data_source="trefle",
            source_id=str(data.get("id") or ""),
            description=description,
            edible=edible,
            edible_parts=edible_parts,
            flowering=flower.get("conspicuous", False),
            flower_color=flower_color,
            foliage_color=foliage_color,
            foliage_texture=foliage_texture,
            raw_data=data,
        )
