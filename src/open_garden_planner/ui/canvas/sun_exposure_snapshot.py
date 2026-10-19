"""GUI-thread plain-data snapshots for heatmap acceptance and sparse receivers."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from open_garden_planner.core.guild_commands import guild_plant_bounds
from open_garden_planner.core.object_types import is_plant_type
from open_garden_planner.core.shade_aggregation import IdentifiedCaster, SunReceiver
from open_garden_planner.ui.canvas.footprints import ItemLookup, standing_parent
from open_garden_planner.ui.canvas.sun_shadow_controller import collect_identified_casters


@dataclass(frozen=True)
class ExposureSnapshot:
    generation: int
    day: date
    latitude: float | None
    longitude: float | None
    bounds: tuple[float, float, float, float]
    casters: tuple[IdentifiedCaster, ...]
    receivers: tuple[SunReceiver, ...]


def collect_exposure_snapshot(scene: Any, location: dict[str, Any] | None, day: date) -> ExposureSnapshot:
    rect = scene.sceneRect()
    width, height = getattr(scene, "width_cm", None), getattr(scene, "height_cm", None)
    bounds = ((0.0, 0.0, float(width), float(height)) if width is not None and height is not None
              else (rect.x(), rect.y(), rect.width(), rect.height()))
    receivers = []
    items = scene.items()
    lookup = ItemLookup(items)
    for item in items:
        if (not hasattr(item, "item_id") or not hasattr(item, "object_type")
                or not is_plant_type(item.object_type) or not item.isVisible()):
            continue
        centre = item.mapToScene(guild_plant_bounds(item).center())
        # A plant that stands in a soil parent's solid (the membership half of the
        # base rule — the rule the casters and the 3D records use) is not shaded by
        # that parent: the bed is under it. Without this every plant in a raised
        # bed reads 0 hours.
        parent = standing_parent(item, lookup, day)
        receivers.append(SunReceiver(str(item.item_id), centre.x(), centre.y(),
                                     str(parent.item_id) if parent is not None else None))
    return ExposureSnapshot(
        getattr(scene, "_document_generation", 0), day,
        (location or {}).get("latitude"), (location or {}).get("longitude"), bounds,
        tuple(sorted(collect_identified_casters(scene, day), key=lambda caster: caster.item_id)),
        tuple(sorted(receivers, key=lambda receiver: receiver.item_id)),
    )
