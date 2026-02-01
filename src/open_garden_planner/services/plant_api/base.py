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

        Args:
            plant_id: Unique identifier in this API's database

        Returns:
            Complete plant species data

        Raises:
            PlantAPIError: If the API request fails or plant not found
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the API service is currently available.

        Returns:
            True if service can be reached, False otherwise
        """
        pass
