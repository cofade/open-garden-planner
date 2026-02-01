"""Plant API manager with fallback chain."""

import logging
from typing import Any

from open_garden_planner.models.plant_data import PlantSpeciesData

from .base import PlantAPIClient, PlantAPIError
from .perenual_client import PerenualClient
from .permapeople_client import PermapeopleClient
from .trefle_client import TrefleClient

logger = logging.getLogger(__name__)


class PlantAPIManager:
    """Manager for plant API clients with automatic fallback.

    Implements the fallback chain specified in the PRD:
    1. Trefle.io (primary) - Comprehensive botanical database, 400,000+ species
    2. Perenual (secondary) - Most reliable, active maintenance
    3. Permapeople (tertiary) - Community-driven
    4. Bundled database (offline fallback) - Not yet implemented
    5. User-defined entries (always available) - Not yet implemented

    The manager automatically tries each service in order until one succeeds.
    """

    def __init__(
        self,
        trefle_api_token: str | None = None,
        perenual_api_key: str | None = None,
        permapeople_key_id: str | None = None,
        permapeople_key_secret: str | None = None,
    ) -> None:
        """Initialize the plant API manager.

        Args:
            trefle_api_token: Optional Trefle API token
            perenual_api_key: Optional Perenual API key
            permapeople_key_id: Optional Permapeople key ID
            permapeople_key_secret: Optional Permapeople key secret
        """
        self._clients: list[PlantAPIClient] = []

        # Initialize clients in fallback order (Trefle first)
        try:
            trefle = TrefleClient(api_token=trefle_api_token)
            self._clients.append(trefle)
            logger.info("Trefle client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Trefle client: {e}")

        try:
            perenual = PerenualClient(api_key=perenual_api_key)
            self._clients.append(perenual)
            logger.info("Perenual client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Perenual client: {e}")

        try:
            permapeople = PermapeopleClient(
                key_id=permapeople_key_id,
                key_secret=permapeople_key_secret,
            )
            self._clients.append(permapeople)
            logger.info("Permapeople client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Permapeople client: {e}")

        # TODO: Add bundled database client when implemented

    def search(self, query: str, limit: int = 10) -> list[PlantSpeciesData]:
        """Search for plants across all available APIs with fallback.

        Tries each API in order until one succeeds. Returns results from
        the first successful API.

        Args:
            query: Search term (plant name or partial name)
            limit: Maximum number of results to return

        Returns:
            List of matching plant species data

        Raises:
            PlantAPIError: If all APIs fail
        """
        if not query or not query.strip():
            return []

        last_error: Exception | None = None

        for client in self._clients:
            try:
                logger.info(f"Trying {client.name} API for search: '{query}'")
                results = client.search(query, limit)

                if results:
                    logger.info(f"{client.name} returned {len(results)} results")
                    return results
                else:
                    logger.info(f"{client.name} returned no results")

            except PlantAPIError as e:
                logger.warning(f"{client.name} API failed: {e}")
                last_error = e
                continue
            except Exception as e:
                logger.error(f"Unexpected error with {client.name}: {e}")
                last_error = e
                continue

        # All APIs failed
        error_msg = "All plant APIs failed"
        if last_error:
            error_msg += f": {last_error}"
        raise PlantAPIError(error_msg)

    def get_by_id(self, plant_id: str, source: str) -> PlantSpeciesData:
        """Get detailed plant data by ID from a specific source.

        Args:
            plant_id: Unique identifier in the source's database
            source: Source name ("perenual", "permapeople", etc.)

        Returns:
            Complete plant species data

        Raises:
            PlantAPIError: If the API request fails or source not found
        """
        # Find the client for this source
        for client in self._clients:
            if client.name.lower() == source.lower():
                try:
                    return client.get_by_id(plant_id)
                except PlantAPIError as e:
                    raise PlantAPIError(f"Failed to get plant from {source}: {e}") from e

        raise PlantAPIError(f"No client available for source: {source}")

    def get_available_sources(self) -> list[str]:
        """Get list of currently available API sources.

        Returns:
            List of source names that are operational
        """
        available = []
        for client in self._clients:
            try:
                if client.is_available():
                    available.append(client.name)
            except Exception as e:
                logger.debug(f"Failed to check {client.name} availability: {e}")
                continue

        return available

    def check_status(self) -> dict[str, Any]:
        """Check status of all configured API clients.

        Returns:
            Dictionary mapping client names to their availability status
        """
        status = {}
        for client in self._clients:
            try:
                is_available = client.is_available()
                status[client.name] = {
                    "available": is_available,
                    "configured": True,
                }
            except Exception as e:
                status[client.name] = {
                    "available": False,
                    "configured": True,
                    "error": str(e),
                }

        return status
