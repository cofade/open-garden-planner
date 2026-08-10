"""External services (file I/O, plant API, etc.)."""

from .autosave_service import AutoSaveManager
from .plant_api import (
    PlantAPIClient,
    PlantAPIError,
    PlantAPIManager,
    PlantDetailUnavailableError,
)
from .plant_library import PlantLibrary, get_plant_library

__all__ = [
    "AutoSaveManager",
    "PlantAPIClient",
    "PlantAPIError",
    "PlantAPIManager",
    "PlantDetailUnavailableError",
    "PlantLibrary",
    "get_plant_library",
]
