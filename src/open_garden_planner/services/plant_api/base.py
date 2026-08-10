"""Base interface for plant API clients."""

from abc import ABC, abstractmethod

from open_garden_planner.models.plant_data import PlantSpeciesData


class PlantAPIError(Exception):
    """Base exception for plant API errors."""

    pass


class PlantAPIClient(ABC):
    """Abstract base class for plant API clients.

    Defines the interface that all plant API clients must implement.
    This enables a consistent fallback chain across different providers.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the API service (e.g., "Perenual", "Permapeople").

        Returns:
            Service name
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def get_by_id(self, plant_id: str) -> PlantSpeciesData:
        """Get detailed plant data by API-specific ID.

        Contract depended on by callers that validate the response before
        trusting it (`PlantSearchDialog._enrich_selected_plant()`, #297): the
        returned record's `source_id` MUST equal the requested `plant_id`.
        Implementations that parse a nested sub-object (e.g. Trefle's
        `data.main_species`, which carries its own `id` distinct from the
        top-level `data.id`) must take `source_id` from whichever nested
        field actually identifies the requested record -- see
        `TrefleClient.get_by_id()` and `tests/unit/test_trefle_client.py`.

        Args:
            plant_id: Unique identifier in this API's database

        Returns:
            Complete plant species data, with `source_id == plant_id`

        Raises:
            PlantAPIError: If the API request fails or plant not found
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the API service is currently available.

        Returns:
            True if service can be reached, False otherwise

        Raises:
            PlantAPIError: Implementations may raise instead of returning
                False to distinguish a connectivity/server failure from a
                definitive rejection -- callers should be prepared for it.
        """
        pass
