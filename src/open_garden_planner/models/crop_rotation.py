"""Crop rotation data model for tracking planting history across years/seasons.

Supports recording which plants were grown in which beds/areas, enabling
rotation rule checking and recommendations (US-10.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Valid nutrient demand levels for rotation planning
NUTRIENT_DEMANDS = ("heavy", "medium", "light", "fixer")

# Valid seasons
SEASONS = ("spring", "summer", "fall", "winter")


@dataclass
class PlantingRecord:
    """A single planting event in a bed/area.

    Attributes:
        year: Calendar year of the planting.
        season: Season identifier (spring | summer | fall | winter).
        species_name: Scientific name of the planted species.
        common_name: Common name for display purposes.
        family: Botanical family (e.g. Solanaceae, Brassicaceae).
        nutrient_demand: Nutrient demand classification (heavy | medium | light | fixer).
        area_id: UUID string linking to a garden item (bed/area).
    """

    year: int
    season: str
    species_name: str
    common_name: str = ""
    family: str = ""
    nutrient_demand: str = ""
    area_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "year": self.year,
            "season": self.season,
            "species_name": self.species_name,
            "common_name": self.common_name,
            "family": self.family,
            "nutrient_demand": self.nutrient_demand,
            "area_id": self.area_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlantingRecord:
        """Deserialize from dictionary."""
        return cls(
            year=data["year"],
            season=data.get("season", "spring"),
            species_name=data.get("species_name", ""),
            common_name=data.get("common_name", ""),
            family=data.get("family", ""),
            nutrient_demand=data.get("nutrient_demand", ""),
            area_id=data.get("area_id", ""),
        )


@dataclass
class CropRotationHistory:
    """Collection of planting records for the entire garden.

    Attributes:
        records: All planting records across all areas and years.
    """

    records: list[PlantingRecord] = field(default_factory=list)

    def add_record(self, record: PlantingRecord) -> None:
        """Add a planting record."""
        self.records.append(record)

    def remove_record(self, record: PlantingRecord) -> None:
        """Remove a planting record."""
        self.records.remove(record)

    def get_records_for_area(self, area_id: str) -> list[PlantingRecord]:
        """Get all planting records for a specific area/bed.

        Args:
            area_id: The UUID of the garden item.

        Returns:
            List of records for that area, sorted by year descending then season.
        """
        season_order = {s: i for i, s in enumerate(SEASONS)}
        area_records = [r for r in self.records if r.area_id == area_id]
        area_records.sort(
            key=lambda r: (-r.year, season_order.get(r.season, 0))
        )
        return area_records

    def get_records_for_year(self, year: int) -> list[PlantingRecord]:
        """Get all planting records for a specific year.

        Args:
            year: The calendar year.

        Returns:
            List of records for that year.
        """
        return [r for r in self.records if r.year == year]

    def get_families_for_area(
        self, area_id: str, last_n_years: int = 3
    ) -> list[str]:
        """Get the botanical families planted in an area over the last N years.

        Args:
            area_id: The UUID of the garden item.
            last_n_years: How many years of history to consider.

        Returns:
            List of family names (may contain duplicates for repeat years).
        """
        area_records = self.get_records_for_area(area_id)
        if not area_records:
            return []

        # Determine the most recent year in the records for this area
        max_year = max(r.year for r in area_records)
        cutoff_year = max_year - last_n_years + 1

        return [
            r.family
            for r in area_records
            if r.year >= cutoff_year and r.family
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for project file storage."""
        return {
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CropRotationHistory:
        """Deserialize from dictionary."""
        records = [
            PlantingRecord.from_dict(r)
            for r in data.get("records", [])
        ]
        return cls(records=records)
