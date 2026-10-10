"""Undoable food-forest preset and project assignment preference."""

from typing import Any, cast

from PyQt6.QtCore import QCoreApplication

from open_garden_planner.core.commands import Command
from open_garden_planner.models.layer import Layer
from open_garden_planner.models.plant_data import PermacultureLayer


class FoodForestLayersCommand(Command):
    def __init__(self, scene: Any, names: dict[str, str]) -> None:
        self.scene = scene
        self.active = scene.active_layer
        self.previous = list(scene.layers)
        self.previous_z = [layer.z_order for layer in self.previous]
        existing = {layer.permaculture_layer for layer in self.previous}
        self.added = [Layer(name=names[tag.value], permaculture_layer=tag.value)
                      for tag in PermacultureLayer if tag != PermacultureLayer.UNKNOWN
                      and tag.value not in existing]

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Create food-forest layer set")

    def execute(self) -> None:
        self.scene.reorder_layers(self.previous + self.added)
        self.scene.set_active_layer(self.active)

    def undo(self) -> None:
        self.scene.set_layers(list(self.previous))
        for layer, z in zip(self.previous, self.previous_z, strict=True):
            layer.z_order = z
        self.scene._update_items_z_order()
        self.scene.set_active_layer(self.active)


class AutoAssignPermacultureCommand(Command):
    def __init__(self, manager: Any, enabled: bool) -> None:
        self.manager = manager
        self.before = manager.auto_assign_permaculture_layers
        self.after = enabled

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Change food-forest auto-assignment")

    def execute(self) -> None:
        self.manager.auto_assign_permaculture_layers = self.after

    def undo(self) -> None:
        self.manager.auto_assign_permaculture_layers = self.before


def placement_layer(scene: Any, species: dict[str, Any], enabled: bool) -> Layer | None:
    """No implicit layers: fall back to the ordinary active layer."""
    if enabled:
        trait = species.get("permaculture_layer")
        for layer in scene.layers:
            if trait and trait != "unknown" and layer.permaculture_layer == trait and layer.visible and not layer.locked:
                return cast(Layer, layer)
    return cast(Layer | None, scene.active_layer)
