"""Plant data models for storing botanical information from APIs."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class SunRequirement(Enum):
    """Sunlight requirements for plants."""

    FULL_SUN = "full_sun"
    PARTIAL_SUN = "partial_sun"
    PARTIAL_SHADE = "partial_shade"
    FULL_SHADE = "full_shade"
    UNKNOWN = "unknown"


class WaterNeeds(Enum):
    """Water requirements for plants."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class PlantCycle(Enum):
    """Plant life cycle."""

    ANNUAL = "annual"
    BIENNIAL = "biennial"
    PERENNIAL = "perennial"
    UNKNOWN = "unknown"


class GrowthRate(Enum):
    """Plant growth rate."""

    SLOW = "slow"
    MEDIUM = "medium"
    FAST = "fast"
    UNKNOWN = "unknown"


@dataclass
class PlantSpeciesData:
    """Botanical data for a plant species from external APIs.

    This model stores information fetched from plant databases like
    Perenual, Permapeople, or Trefle.io. It represents species-level
    data rather than individual plant instances.
    """

    # Core identification
    scientific_name: str
    common_name: str
    family: str = ""
    genus: str = ""

    # Growth characteristics
    cycle: PlantCycle = PlantCycle.UNKNOWN
    growth_rate: GrowthRate = GrowthRate.UNKNOWN

    # Size (in centimeters)
    min_height_cm: float | None = None
    max_height_cm: float | None = None
    min_spread_cm: float | None = None
    max_spread_cm: float | None = None

    # Environmental requirements
    sun_requirement: SunRequirement = SunRequirement.UNKNOWN
    water_needs: WaterNeeds = WaterNeeds.UNKNOWN
    hardiness_zone_min: int | None = None
    hardiness_zone_max: int | None = None

    # Soil preferences
    soil_type: str = ""  # e.g., "Light (sandy), medium, heavy (clay)"
    ph_min: float | None = None
    ph_max: float | None = None

    # Additional attributes
    edible: bool = False
    edible_parts: list[str] = field(default_factory=list)
    flowering: bool = False
    flower_color: str = ""
    foliage_color: str = ""
    foliage_texture: str = ""

    # Images
    image_url: str = ""
    thumbnail_url: str = ""

    # Source tracking
    data_source: str = ""  # e.g., "perenual", "permapeople", "trefle", "custom"
    source_id: str = ""  # ID in the source database
    description: str = ""

    # Extensible metadata for API-specific fields
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the plant data
        """
        return {
            "scientific_name": self.scientific_name,
            "common_name": self.common_name,
            "family": self.family,
            "genus": self.genus,
            "cycle": self.cycle.value,
            "growth_rate": self.growth_rate.value,
            "min_height_cm": self.min_height_cm,
            "max_height_cm": self.max_height_cm,
            "min_spread_cm": self.min_spread_cm,
            "max_spread_cm": self.max_spread_cm,
            "sun_requirement": self.sun_requirement.value,
            "water_needs": self.water_needs.value,
            "hardiness_zone_min": self.hardiness_zone_min,
            "hardiness_zone_max": self.hardiness_zone_max,
            "soil_type": self.soil_type,
            "ph_min": self.ph_min,
            "ph_max": self.ph_max,
            "edible": self.edible,
            "edible_parts": self.edible_parts,
            "flowering": self.flowering,
            "flower_color": self.flower_color,
            "foliage_color": self.foliage_color,
            "foliage_texture": self.foliage_texture,
            "image_url": self.image_url,
            "thumbnail_url": self.thumbnail_url,
            "data_source": self.data_source,
            "source_id": self.source_id,
            "description": self.description,
            "raw_data": self.raw_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlantSpeciesData":
        """Create from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            PlantSpeciesData instance
        """
        # Convert enum strings back to enums
        cycle = PlantCycle(data.get("cycle", "unknown"))
        growth_rate = GrowthRate(data.get("growth_rate", "unknown"))
        sun_requirement = SunRequirement(data.get("sun_requirement", "unknown"))
        water_needs = WaterNeeds(data.get("water_needs", "unknown"))

        return cls(
            scientific_name=data["scientific_name"],
            common_name=data["common_name"],
            family=data.get("family", ""),
            genus=data.get("genus", ""),
            cycle=cycle,
            growth_rate=growth_rate,
            min_height_cm=data.get("min_height_cm"),
            max_height_cm=data.get("max_height_cm"),
            min_spread_cm=data.get("min_spread_cm"),
            max_spread_cm=data.get("max_spread_cm"),
            sun_requirement=sun_requirement,
            water_needs=water_needs,
            hardiness_zone_min=data.get("hardiness_zone_min"),
            hardiness_zone_max=data.get("hardiness_zone_max"),
            soil_type=data.get("soil_type", ""),
            ph_min=data.get("ph_min"),
            ph_max=data.get("ph_max"),
            edible=data.get("edible", False),
            edible_parts=data.get("edible_parts", []),
            flowering=data.get("flowering", False),
            flower_color=data.get("flower_color", ""),
            foliage_color=data.get("foliage_color", ""),
            foliage_texture=data.get("foliage_texture", ""),
            image_url=data.get("image_url", ""),
            thumbnail_url=data.get("thumbnail_url", ""),
            data_source=data.get("data_source", ""),
            source_id=data.get("source_id", ""),
            description=data.get("description", ""),
            raw_data=data.get("raw_data", {}),
        )


@dataclass
class PlantInstance:
    """Individual plant instance in a garden.

    This represents a specific plant placed in the garden, with its own
    metadata separate from the species data. Links to PlantSpeciesData
    for botanical information.
    """

    # Instance-specific data
    variety_cultivar: str = ""  # e.g., "Honeycrisp" for apple
    planting_date: date | None = None
    current_diameter_cm: float | None = None
    current_height_cm: float | None = None
    notes: str = ""

    # Custom metadata (user-defined fields)
    custom_fields: dict[str, Any] = field(default_factory=dict)

    # Link to species data (optional - may be None for custom entries)
    species_data: PlantSpeciesData | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the plant instance
        """
        return {
            "variety_cultivar": self.variety_cultivar,
            "planting_date": self.planting_date.isoformat() if self.planting_date else None,
            "current_diameter_cm": self.current_diameter_cm,
            "current_height_cm": self.current_height_cm,
            "notes": self.notes,
            "custom_fields": self.custom_fields,
            "species_data": self.species_data.to_dict() if self.species_data else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlantInstance":
        """Create from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            PlantInstance instance
        """
        planting_date = None
        if data.get("planting_date"):
            planting_date = date.fromisoformat(data["planting_date"])

        species_data = None
        if data.get("species_data"):
            species_data = PlantSpeciesData.from_dict(data["species_data"])

        return cls(
            variety_cultivar=data.get("variety_cultivar", ""),
            planting_date=planting_date,
            current_diameter_cm=data.get("current_diameter_cm"),
            current_height_cm=data.get("current_height_cm"),
            notes=data.get("notes", ""),
            custom_fields=data.get("custom_fields", {}),
            species_data=species_data,
        )
