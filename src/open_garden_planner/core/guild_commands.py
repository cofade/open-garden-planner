"""Guild creation and membership change without introducing Qt parentage."""

from copy import deepcopy
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import QCoreApplication, QPointF

from open_garden_planner.core.commands import Command, CreateItemsCommand
from open_garden_planner.core.object_types import is_plant_type
from open_garden_planner.core.plant_sizing import sizing_for_item
from open_garden_planner.models.guild import GuildTemplate, ring_positions


class GuildMembershipCommand(Command):
    def __init__(self, changes: list[tuple[Any, dict[str, Any] | None]]) -> None:
        self.changes = [(item, deepcopy(item.metadata.get("guild")), deepcopy(value)) for item, value in changes]

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Change guild membership")

    def _apply(self, after: bool) -> None:
        for item, old, new in self.changes:
            value = new if after else old
            if value is None:
                item.metadata.pop("guild", None)
            else:
                item.metadata["guild"] = deepcopy(value)
            item.update()

    def execute(self) -> None:
        self._apply(True)

    def undo(self) -> None:
        self._apply(False)


class InsertGuildCommand(Command):
    def __init__(self, scene: Any, items: list[Any], changes: list[tuple[Any, dict[str, Any] | None]]) -> None:
        self.items = items
        self.creation = CreateItemsCommand(scene, items)
        self.membership = GuildMembershipCommand(changes)

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Insert guild")

    def execute(self) -> None:
        try:
            self.creation.execute()
            self.membership.execute()
        except Exception:
            self.membership.undo()
            self.creation.undo()
            raise

    def undo(self) -> None:
        self.membership.undo()
        self.creation.undo()


def prepare_guild(scene: Any, template: GuildTemplate, catalog: dict[str, dict[str, Any]], name: str, position: QPointF,
                  *, selections: dict[str, str] | None = None, existing_centre: Any = None,
                  auto_assign: bool = False) -> InsertGuildCommand:
    """Resolve and preflight everything before executing any scene/history write."""
    from open_garden_planner.ui.plant_creation import build_species_plant

    GuildTemplate.from_dict(template.to_dict())
    if not name.strip():
        raise ValueError("A guild needs an instance name")
    selected = selections or {}
    centre_key = selected.get("centre", template.centre)
    if existing_centre is not None:
        if existing_centre.scene() is not scene or not is_plant_type(existing_centre.object_type):
            raise ValueError("Choose a plant in the current plan as centre")
        if existing_centre.metadata.get("guild") is not None:
            raise ValueError("Remove this plant from its current guild before using it as centre")
        centre = existing_centre
        species = centre.metadata.get("plant_species") or {}
        position = centre.mapToScene(centre.rect().center())
    else:
        if centre_key not in catalog:
            raise ValueError("Select a resolved centre species")
        species = catalog[centre_key]
        centre = build_species_plant(scene, position, species, auto_assign=auto_assign)
    if template.centre.startswith("function:"):
        if template.centre.removeprefix("function:") not in (species.get("functions") or []):
            raise ValueError("Centre species does not record the required function")
    elif species.get("scientific_name", "").casefold() != catalog.get(template.centre, {}).get("scientific_name", "").casefold():
        raise ValueError("Centre species does not match this template")
    radius = sizing_for_item(centre).effective_spacing_radius_cm
    positions = ring_positions(template, (position.x(), position.y()), radius)
    choices = {}
    for role in template.roles:
        key = selected.get(role.function, role.suggested_species[0] if role.suggested_species else "")
        if key not in catalog:
            raise ValueError("Unresolved suggested species: choose a replacement")
        if role.function not in (catalog[key].get("functions") or []):
            raise ValueError("Selected member species does not record its required function")
        choices[role.function] = catalog[key]
    gid = str(uuid4())
    items = [] if existing_centre is not None else [centre]
    changes: list[tuple[Any, dict[str, Any] | None]] = [(centre, {"guild_id": gid, "role": "centre", "name": name.strip(),
                         "template": template.to_dict()})]
    for function, x, y in positions:
        member = build_species_plant(scene, QPointF(x, y), choices[function], auto_assign=auto_assign)
        items.append(member)
        changes.append((member, {"guild_id": gid, "role": function}))
    for plant, _ in changes:
        layer = scene.get_layer_by_id(plant.layer_id) if plant.layer_id is not None else None
        if layer is None or layer.locked or not layer.visible:
            raise ValueError("Guild placement needs visible, unlocked target layers")
        footprint = plant.mapRectToScene(plant.rect())
        if not scene.canvas_rect.contains(footprint):
            raise ValueError("Guild layout extends outside the canvas; choose another position or radius")
    return InsertGuildCommand(scene, items, changes)


def guild_members(scene: Any, guild_id: str) -> list[Any]:
    return [item for item in scene.items() if isinstance(getattr(item, "metadata", None), dict)
            and isinstance(item.metadata.get("guild"), dict) and item.metadata["guild"].get("guild_id") == guild_id]


def remove_membership(scene: Any, item: Any) -> GuildMembershipCommand:
    guild = item.metadata.get("guild")
    members = guild_members(scene, guild.get("guild_id", "")) if isinstance(guild, dict) and guild.get("role") == "centre" else [item]
    return GuildMembershipCommand([(member, None) for member in members])
