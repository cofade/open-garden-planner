"""Centrally built plant membership actions and one-step transfers."""

import contextlib
from typing import Any
from uuid import UUID

from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout

from open_garden_planner.core.guild_commands import (
    GuildMembershipCommand,
    guild_members,
    remove_membership,
)
from open_garden_planner.core.object_types import is_plant_type
from open_garden_planner.models.plant_data import PlantFunction
from open_garden_planner.ui.widgets.trait_filters import trait_label


def add_to_guild(item: Any, view: Any) -> None:
    scene = item.scene()
    generation = getattr(scene, "_document_generation", 0)
    if scene is None:
        return
    centres = [plant for plant in scene.items() if isinstance(getattr(plant, "metadata", {}).get("guild"), dict)
               and plant.metadata["guild"].get("role") == "centre" and plant is not item]
    dialog = QDialog(view)
    dialog.setWindowTitle(QCoreApplication.translate("GuildActions", "Add to guild…"))
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    guild_combo, role_combo = QComboBox(), QComboBox()
    for centre in centres:
        guild_combo.addItem(centre.metadata["guild"].get("name", ""), centre.metadata["guild"].get("guild_id"))
    for function in PlantFunction:
        role_combo.addItem(trait_label(function.value), function.value)
    form.addRow(QCoreApplication.translate("GuildActions", "Guild:"), guild_combo)
    form.addRow(QCoreApplication.translate("GuildActions", "Intended role:"), role_combo)
    layout.addLayout(form)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
    if ok is not None:
        ok.setEnabled(bool(centres))
    layout.addWidget(buttons)
    if not dialog.exec() or generation != getattr(scene, "_document_generation", 0) or item.scene() is not scene:
        return
    gid = guild_combo.currentData()
    if not guild_members(scene, gid):
        return
    new = {"guild_id": gid, "role": role_combo.currentData()}
    if item.metadata.get("guild") == new:
        return
    old = item.metadata.get("guild")
    changes: list[tuple[Any, dict[str, Any] | None]] = []
    if isinstance(old, dict) and old.get("role") == "centre":
        changes = [(member, None) for member in guild_members(scene, old.get("guild_id", "")) if member is not item]
    changes.append((item, new))
    view.command_manager.execute(GuildMembershipCommand(changes))


def build_guild_actions(menu: Any, item: Any) -> None:
    """One builder shared by plant context menus, separate from bed actions."""
    if not is_plant_type(item.object_type) or item.scene() is None or not item.scene().views():
        return
    view = item.scene().views()[0]
    menu.addSeparator()
    add = menu.addAction(QCoreApplication.translate("GuildActions", "Add to guild…"))
    identity = item.item_id
    scene = item.scene()
    generation = getattr(scene, "_document_generation", 0)
    def defer_add() -> None:
        timer = QTimer(view)
        timer.setSingleShot(True)
        def navigate() -> None:
            try:
                if generation != getattr(scene, "_document_generation", 0):
                    return
                current = scene.find_item_by_id(UUID(str(identity)))
                if current is not None:
                    add_to_guild(current, view)
            except RuntimeError:
                pass
            finally:
                with contextlib.suppress(RuntimeError):
                    timer.deleteLater()
        timer.timeout.connect(navigate)
        timer.start(0)
    add.triggered.connect(defer_add)
    remove = menu.addAction(QCoreApplication.translate("GuildActions", "Remove from guild"))
    remove.setEnabled(item.metadata.get("guild") is not None)
    remove.triggered.connect(lambda: view.command_manager.execute(remove_membership(item.scene(), item)))
