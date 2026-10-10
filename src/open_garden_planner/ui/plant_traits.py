"""Single property write path for selected-plant species trait snapshots."""

from copy import deepcopy
from functools import partial
from typing import Any

from open_garden_planner.core.commands import ChangePropertyCommand


def apply_trait(item: Any, value: Any, *, field: str) -> None:
    species = item.metadata.get("plant_species")
    if isinstance(species, dict):
        species[field] = deepcopy(value)
        item.update()


def change_trait(item: Any, field: str, value: Any) -> bool:
    """One gesture, one command, no mutation of the machine-wide library."""
    species = item.metadata.get("plant_species")
    if not isinstance(species, dict):
        return False
    old = species.get(field, "unknown" if field == "permaculture_layer" else [])
    if old == value:
        return False
    scene = item.scene()
    views = scene.views() if scene is not None else []
    if not views:
        return False
    views[0].command_manager.execute(ChangePropertyCommand(
        item, field, deepcopy(old), deepcopy(value), apply_func=partial(apply_trait, field=field)))
    return True
