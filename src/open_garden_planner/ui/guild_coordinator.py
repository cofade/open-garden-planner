"""One teardown-safe, idempotent debounced guild/diagnostics coordinator."""

import contextlib
from copy import deepcopy
from typing import Any

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsSimpleTextItem

from open_garden_planner.core.guild_commands import guild_plant_bounds
from open_garden_planner.core.object_types import is_plant_type
from open_garden_planner.services.guild_service import (
    GuildStatus,
    compute_guilds,
    guild_diagnostics,
)
from open_garden_planner.ui.widgets.trait_filters import trait_label


class GuildCoordinator(QObject):
    def __init__(self, scene: Any, command_manager: Any, diagnostics_panel: Any, guilds_panel: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self.diagnostics_panel = diagnostics_panel
        self.guilds_panel = guilds_panel
        self.statuses: list[GuildStatus] = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        scene.changed.connect(self.schedule)
        command_manager.stack_changed.connect(self.schedule)
        scene.document_replaced.connect(self.reset)
        self.schedule()

    def reset(self) -> None:
        self.timer.stop()
        self.statuses = []
        self.guilds_panel.set_statuses([])

    def schedule(self, *_args: Any) -> None:
        with contextlib.suppress(RuntimeError):
            if not self.timer.isActive():
                self.timer.start(100)

    def refresh(self) -> None:
        with contextlib.suppress(RuntimeError):
            plants = [item for item in self.scene.items() if hasattr(item, "object_type")
                      and is_plant_type(item.object_type)]
            snapshots = [{"item_id": str(item.item_id), "guild": deepcopy(item.metadata.get("guild")),
                          "functions": deepcopy(item.metadata["plant_species"].get("functions", []))
                          if isinstance(item.metadata.get("plant_species"), dict) else []}
                         for item in plants if item.isVisible()]
            self.statuses, errors = compute_guilds(snapshots)
            diagnostics = guild_diagnostics(self.statuses) + errors
            # Agent object queries address top-level objects. Keep the physical
            # centre ID in details, but navigate to its enclosing group.
            roots = {}
            for plant in plants:
                root = plant
                while root.parentItem() is not None and hasattr(root.parentItem(), "item_id"):
                    root = root.parentItem()
                roots[str(plant.item_id)] = str(root.item_id)
            for diagnostic in diagnostics:
                diagnostic["item_ids"] = list(dict.fromkeys(roots.get(identity, identity)
                    for identity in diagnostic["item_ids"]))
            if getattr(self.scene, "_guild_diagnostics", []) != diagnostics:
                self.scene._guild_diagnostics = diagnostics
                self.scene.diagnostics_changed.emit()
            by_centre = {status.centre_id: status for status in self.statuses}
            for item in plants:
                status = by_centre.get(str(item.item_id))
                missing = status.missing if status is not None else {}
                badge = getattr(item, "_guild_badge", None)
                if not missing and badge is None:
                    continue
                # Saved/imported plants can use another GardenItem geometry.
                # ObjectType identifies a plant; it does not promise a circle.
                geometry = guild_plant_bounds(item)
                position = geometry.center()
                radius = getattr(item, "radius", min(geometry.width(), geometry.height()) / 2)
                signature = (missing, status.name if status is not None else "", radius,
                             position.x(), position.y())
                if getattr(item, "_guild_badge_signature", None) == signature:
                    continue
                item._guild_badge_signature = deepcopy(signature)
                if missing and badge is None:
                    badge = QGraphicsEllipseItem(-8, -8, 16, 16, item)
                    badge.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
                    badge.setBrush(QColor("#e3a234"))
                    badge.setPen(QPen(Qt.PenStyle.NoPen))
                    text = QGraphicsSimpleTextItem("!", badge)
                    text.setPos(-2, -8)
                    badge.setZValue(100)
                    item._guild_badge = badge
                if badge is not None:
                    badge.setPos(position.x(), position.y() - radius * 0.7)
                    badge.setVisible(bool(missing))
                    tooltip = self.tr("Missing guild roles: {roles}").format(
                        roles=", ".join(trait_label(function) for function in missing)) if missing else ""
                    badge.setToolTip(tooltip)
            self.guilds_panel.set_statuses(self.statuses)
