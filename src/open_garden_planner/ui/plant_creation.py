"""Build-only canonical plant constructor shared by drops and guild stamps."""

from copy import deepcopy
from datetime import date
from typing import Any

from PyQt6.QtCore import QPointF

from open_garden_planner.core.growth_model import stamp_default_planting_date
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.permaculture_commands import placement_layer
from open_garden_planner.core.plant_renderer import PlantCategory
from open_garden_planner.core.plant_sizing import species_drop_diameter_cm
from open_garden_planner.services.bundled_species_db import populate_item_species_metadata
from open_garden_planner.ui.canvas.items import CircleItem


def build_plant(scene: Any, position: QPointF, object_type: ObjectType, radius: float, *,
                species_name: str = "", plant_category: PlantCategory | None = None,
                species_dict: dict[str, Any] | None = None, auto_assign: bool = False) -> CircleItem:
    """No scene insertion or history mutation; creation commands handle parentage."""
    item = CircleItem(center_x=position.x(), center_y=position.y(), radius=radius, object_type=object_type)
    if species_name:
        item.plant_species = species_name
    if plant_category is not None:
        item.plant_category = plant_category
    if species_dict:
        item.metadata["plant_species"] = deepcopy(species_dict)
    elif species_name:
        populate_item_species_metadata(item, species_name)
    stamp_default_planting_date(item.metadata, getattr(scene, "plan_date", None) or date.today())
    layer = placement_layer(scene, item.metadata.get("plant_species", {}), auto_assign)
    if layer is not None:
        item.layer_id = layer.id
    return item


def build_species_plant(scene: Any, position: QPointF, species: dict[str, Any], *, auto_assign: bool = False) -> CircleItem:
    height = species.get("max_height_cm") or 0
    object_type = ObjectType.TREE if height >= 350 else ObjectType.SHRUB if height >= 100 else ObjectType.PERENNIAL
    category = {ObjectType.TREE: PlantCategory.ROUND_DECIDUOUS,
                ObjectType.SHRUB: PlantCategory.SPREADING_SHRUB,
                ObjectType.PERENNIAL: PlantCategory.FLOWERING_PERENNIAL}[object_type]
    diameter = species_drop_diameter_cm(species, object_type.name)
    return build_plant(scene, position, object_type, diameter / 2,
                       species_name=species.get("common_name") or species.get("scientific_name", ""),
                       plant_category=category, species_dict=species, auto_assign=auto_assign)
