"""Qt-free provider trait mapping and shared catalog filtering."""

import re
from typing import Any

from open_garden_planner.models.plant_data import PermacultureLayer, PlantFunction

PERMAPEOPLE_LAYERS = {
    "tall trees": PermacultureLayer.CANOPY,
    "trees": PermacultureLayer.SUB_CANOPY,
    "shrubs": PermacultureLayer.SHRUB,
    "herbs": PermacultureLayer.HERBACEOUS,
    "ground cover": PermacultureLayer.GROUND_COVER,
    "roots": PermacultureLayer.ROOT,
    "vines": PermacultureLayer.VINE,
}
PERMAPEOPLE_USES = {
    "nitrogen fixer": PlantFunction.NITROGEN_FIXER,
    "nitrogen fixation": PlantFunction.NITROGEN_FIXER,
    "dynamic accumulator": PlantFunction.DYNAMIC_ACCUMULATOR,
    "attracts insects": PlantFunction.POLLINATOR_ATTRACTOR,
    "pest deterrent": PlantFunction.PEST_DETERRENT,
    "ground cover": PlantFunction.GROUND_COVER,
    "mulch": PlantFunction.MULCH_MAKER,
    "windbreak": PlantFunction.WINDBREAK,
    "hedgerow": PlantFunction.HEDGEROW,
    "animal feed": PlantFunction.ANIMAL_FEED,
    "medicinal": PlantFunction.MEDICINAL,
    "dye": PlantFunction.DYE,
    "fiber": PlantFunction.FIBER,
    "fibre": PlantFunction.FIBER,
}


def tokens(value: Any) -> list[str]:
    """Match complete case/whitespace-normalized tokens, never substrings."""
    values = value if isinstance(value, list) else [value]
    return [" ".join(part.casefold().split()) for v in values if isinstance(v, str)
            for part in re.split(r"[,;]", v) if part.strip()]


def permapeople_traits(data: dict[str, Any]) -> tuple[PermacultureLayer, list[PlantFunction]]:
    """Extract known tokens; caller retains the complete original response."""
    layers: list[str] = []
    uses: list[str] = []
    for row in data.get("data") or []:
        if isinstance(row, dict):
            key = str(row.get("key") or "").strip().casefold()
            if key == "layer":
                layers.extend(tokens(row.get("value")))
            elif key == "uses":
                uses.extend(tokens(row.get("value")))
    layer = next((PERMAPEOPLE_LAYERS[v] for v in layers if v in PERMAPEOPLE_LAYERS),
                 PermacultureLayer.UNKNOWN)
    found = {PERMAPEOPLE_USES[v] for v in uses if v in PERMAPEOPLE_USES}
    return layer, [f for f in PlantFunction if f in found]


def matches_traits(record: dict[str, Any], text: str = "", *,
                   layers: set[str] | None = None, functions: set[str] | None = None) -> bool:
    """Text AND (any selected layer) AND (all selected functions)."""
    names = [record.get("scientific_name", ""), record.get("common_name", ""),
             record.get("common_name_de", ""), *(record.get("aliases") or [])]
    return (not text or any(text.casefold() in str(n).casefold() for n in names)) and (
        not layers or (record.get("permaculture_layer") or "unknown") in layers
    ) and (not functions or functions.issubset(set(record.get("functions") or [])))
