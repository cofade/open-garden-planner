"""Qt-free domain-intelligence functions for the Agent API (US-D3.1, issue #319).

These functions wrap the companion planting service and the compatible-set
finder to provide agent-ready domain tools. They are deliberately Qt-free
and operate on plain data, making them unit-testable without a GUI.

The actual service instance is injected by the provider callable in
``application.py``, so this module never constructs its own service.
"""

from __future__ import annotations

from open_garden_planner.agent_api.schema import (
    CompanionSuggestion,
    CompatibleSet,
    PlacementCheck,
)
from open_garden_planner.services.companion_planting_service import (
    ANTAGONISTIC,
    BENEFICIAL,
    CompanionPlantingService,
)
from open_garden_planner.services.companion_sets import (
    find_compatible_sets,
    suggest_companions,
)


def suggest_companions_for_agent(
    service: CompanionPlantingService,
    species_key: str,
    *,
    exclude_antagonists_of: list[str] | None = None,
) -> list[CompanionSuggestion]:
    """Suggest companion plants for a species, ranked by benefit.

    Args:
        service: The companion planting service.
        species_key: The species to find companions for.
        exclude_antagonists_of: Species keys whose antagonists should be
            excluded from suggestions.

    Returns:
        A list of CompanionSuggestion models, sorted by score descending.
    """
    raw = suggest_companions(
        service, species_key, exclude_antagonists_of=exclude_antagonists_of
    )
    return [CompanionSuggestion(**item) for item in raw]


def find_compatible_sets_for_agent(
    service: CompanionPlantingService,
    candidates: list[str],
    *,
    size: int = 3,
    must_include: list[str] | None = None,
) -> list[CompatibleSet]:
    """Find mutually compatible sets of plants among candidates.

    Args:
        service: The companion planting service.
        candidates: Species keys to consider.
        size: Target set size (2–5).
        must_include: Species keys that must be in every returned set.

    Returns:
        A list of CompatibleSet models, sorted by score descending.
    """
    raw = find_compatible_sets(
        service, candidates, size=size, must_include=must_include
    )
    return [CompatibleSet(**item) for item in raw]


def check_placement_for_agent(
    service: CompanionPlantingService,
    species_key: str,
    bed_id: str,
    *,
    bed_plants: list[str] | None = None,
    bed_exists: bool | None = None,
) -> PlacementCheck:
    """Check whether a species is well-placed in a bed.

    Reuses the existing companion relationship logic — never a second
    implementation.

    Args:
        service: The companion planting service.
        species_key: The species to check.
        bed_id: The bed to check against.
        bed_plants: Species keys of plants already in the bed. When omitted,
            the caller must supply ``bed_exists`` so an unknown bed is not
            silently reported as an empty one.
        bed_exists: Whether ``bed_id`` resolves to a real bed. ``None`` means
            the caller could not tell, which is reported as ``"unknown"`` —
            the honest answer, rather than ``"neutral"``, which reads as
            "I looked and there was nothing to find".

    Returns:
        A PlacementCheck model with the results.
    """
    bed_plants = bed_plants or []

    # Check for antagonists and companions in the bed
    antagonists_present: list[str] = []
    companions_present: list[str] = []

    for plant in bed_plants:
        rel = service.get_relationship(species_key, plant)
        if rel is not None:
            if rel.type == ANTAGONISTIC:
                antagonists_present.append(plant)
            elif rel.type == BENEFICIAL:
                companions_present.append(plant)

    # Spacing and soil checks are not implemented here — the full diagnostics
    # are available via get_diagnostics. None means "not checked", never a
    # misleading True.
    spacing_ok = None
    soil_ok = None

    # Determine overall status. An unresolvable bed must not be reported as a
    # clean "neutral": that is the same silent-negative failure as claiming a
    # spacing check passed (P1-5).
    if bed_exists is False:
        overall = "unknown_bed"
    elif antagonists_present:
        overall = "critical"
    elif companions_present:
        overall = "good"
    elif bed_exists is None and not bed_plants:
        overall = "unknown"
    else:
        overall = "neutral"

    return PlacementCheck(
        species_key=species_key,
        bed_id=bed_id,
        antagonists_present=antagonists_present,
        companions_present=companions_present,
        spacing_ok=spacing_ok,
        soil_ok=soil_ok,
        overall=overall,
    )
