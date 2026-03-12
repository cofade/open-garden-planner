"""Crop rotation rule engine and recommendation service (US-10.6).

Analyses planting history for each bed/area and provides:
- Rotation status: good / suboptimal / violation
- Recommended plant families and nutrient demand levels
- Warnings when placing a plant that violates rotation rules
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from open_garden_planner.models.crop_rotation import (
    CropRotationHistory,
    PlantingRecord,
)


class RotationStatus(Enum):
    """Status of crop rotation compliance for a bed."""

    GOOD = "good"            # No family repeat, follows demand cycle
    SUBOPTIMAL = "suboptimal"  # Follows demand cycle but same family within window
    VIOLATION = "violation"    # Same family planted back-to-back or wrong demand order
    UNKNOWN = "unknown"        # No history available


# Ideal rotation order: heavy -> medium -> light -> fixer -> heavy ...
_DEMAND_ORDER = ("heavy", "medium", "light", "fixer")

# Minimum years to avoid repeating the same family
_FAMILY_COOLDOWN_YEARS = 3


@dataclass
class RotationRecommendation:
    """Recommendation for what to plant in a bed this season.

    Attributes:
        area_id: The bed/area UUID string.
        status: Overall rotation status.
        avoid_families: Families to avoid (planted too recently).
        suggested_demand: Ideal nutrient demand level for the next planting.
        reason: Human-readable explanation of the recommendation.
        last_records: Recent planting records for context.
    """

    area_id: str
    status: RotationStatus
    avoid_families: list[str]
    suggested_demand: str
    reason: str
    last_records: list[PlantingRecord]


class CropRotationService:
    """Service for crop rotation analysis and recommendations.

    Args:
        history: The crop rotation history to analyse.
        family_cooldown: Minimum years before replanting the same family.
    """

    def __init__(
        self,
        history: CropRotationHistory | None = None,
        family_cooldown: int = _FAMILY_COOLDOWN_YEARS,
    ) -> None:
        self._history = history or CropRotationHistory()
        self._family_cooldown = family_cooldown

    @property
    def history(self) -> CropRotationHistory:
        """The crop rotation history being analysed."""
        return self._history

    @history.setter
    def history(self, value: CropRotationHistory) -> None:
        """Replace the rotation history."""
        self._history = value

    def get_recommendation(self, area_id: str) -> RotationRecommendation:
        """Get a rotation recommendation for a specific bed/area.

        Args:
            area_id: UUID string of the bed/area.

        Returns:
            RotationRecommendation with status, avoids, and suggestions.
        """
        records = self._history.get_records_for_area(area_id)
        if not records:
            return RotationRecommendation(
                area_id=area_id,
                status=RotationStatus.UNKNOWN,
                avoid_families=[],
                suggested_demand="heavy",
                reason="No planting history — any crop is suitable.",
                last_records=[],
            )

        # Collect families from recent years
        recent_families = self._history.get_families_for_area(
            area_id, last_n_years=self._family_cooldown
        )
        avoid_families = list(dict.fromkeys(f for f in recent_families if f))

        # Determine suggested demand based on the most recent record
        last_demand = records[0].nutrient_demand if records else ""
        suggested_demand = self._next_demand(last_demand)

        # Evaluate status
        status, reason = self._evaluate_status(records, area_id)

        return RotationRecommendation(
            area_id=area_id,
            status=status,
            avoid_families=avoid_families,
            suggested_demand=suggested_demand,
            reason=reason,
            last_records=records[:5],  # Show last 5 records
        )

    def check_plant_placement(
        self,
        area_id: str,
        family: str,
        nutrient_demand: str,
    ) -> tuple[RotationStatus, str]:
        """Check if placing a specific plant in a bed is acceptable.

        Args:
            area_id: UUID string of the target bed/area.
            family: Botanical family of the plant to place.
            nutrient_demand: Nutrient demand level of the plant.

        Returns:
            Tuple of (status, reason_string).
        """
        records = self._history.get_records_for_area(area_id)
        if not records:
            return RotationStatus.GOOD, "No history — any crop is suitable."

        # Check family cooldown
        recent_families = self._history.get_families_for_area(
            area_id, last_n_years=self._family_cooldown
        )

        family_violation = family and family in recent_families
        last_demand = records[0].nutrient_demand if records else ""

        if family_violation and records[0].family == family:
            return (
                RotationStatus.VIOLATION,
                f"{family} was planted here recently — "
                f"avoid same family for {self._family_cooldown} years.",
            )

        if family_violation:
            # Same family within cooldown window but not back-to-back
            expected = self._next_demand(last_demand)
            if nutrient_demand != expected:
                return (
                    RotationStatus.SUBOPTIMAL,
                    f"{family} was planted here within the last "
                    f"{self._family_cooldown} years. "
                    f"Also, a '{expected}' feeder would be ideal after "
                    f"'{last_demand}'.",
                )
            return (
                RotationStatus.SUBOPTIMAL,
                f"{family} was planted here within the last "
                f"{self._family_cooldown} years.",
            )

        # Check demand sequence
        expected = self._next_demand(last_demand)
        if nutrient_demand and nutrient_demand != expected:
            return (
                RotationStatus.SUBOPTIMAL,
                f"A '{expected}' feeder would be ideal after "
                f"'{last_demand}'. Got '{nutrient_demand}'.",
            )

        return RotationStatus.GOOD, "Good rotation choice."

    def _evaluate_status(
        self,
        records: list[PlantingRecord],
        area_id: str,
    ) -> tuple[RotationStatus, str]:
        """Evaluate the overall rotation status for a bed.

        Returns:
            Tuple of (RotationStatus, reason_string).
        """
        if len(records) < 2:
            return (
                RotationStatus.GOOD,
                "Only one season recorded — rotation looks fine.",
            )

        # Check if the last two records have the same family
        if records[0].family and records[0].family == records[1].family:
            return (
                RotationStatus.VIOLATION,
                f"{records[0].family} planted in consecutive seasons — "
                f"rotate to a different family.",
            )

        # Check demand sequence
        if records[0].nutrient_demand and records[1].nutrient_demand:
            expected = self._next_demand(records[1].nutrient_demand)
            if records[0].nutrient_demand != expected:
                return (
                    RotationStatus.SUBOPTIMAL,
                    f"After '{records[1].nutrient_demand}' feeder, "
                    f"expected '{expected}' but got "
                    f"'{records[0].nutrient_demand}'.",
                )

        # Check if any family repeats within the cooldown window
        recent_families = self._history.get_families_for_area(
            area_id, last_n_years=self._family_cooldown
        )
        seen: set[str] = set()
        for fam in recent_families:
            if fam in seen:
                return (
                    RotationStatus.SUBOPTIMAL,
                    f"{fam} appears multiple times in the last "
                    f"{self._family_cooldown} years.",
                )
            seen.add(fam)

        return RotationStatus.GOOD, "Good rotation — diverse families and balanced demands."

    @staticmethod
    def _next_demand(current: str) -> str:
        """Return the ideal next nutrient demand level in the rotation cycle.

        Cycle: heavy -> medium -> light -> fixer -> heavy -> ...
        """
        try:
            idx = _DEMAND_ORDER.index(current)
            return _DEMAND_ORDER[(idx + 1) % len(_DEMAND_ORDER)]
        except ValueError:
            return "heavy"  # Default to heavy feeder if unknown
