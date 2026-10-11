"""Companion panel guild section, consuming the shared computed snapshot."""

from dataclasses import asdict
from typing import Any
from uuid import UUID

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from open_garden_planner.services.guild_service import GuildStatus
from open_garden_planner.ui.panels.diagnostics_panel import ObjectNavigator
from open_garden_planner.ui.plant_traits import species_display_name
from open_garden_planner.ui.widgets.trait_filters import trait_label


class GuildsPanel(ObjectNavigator):
    def __init__(self, scene: Any, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self._signature: Any = None
        self.statuses: list[GuildStatus] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel(self.tr("Guilds"))
        self.tree.itemClicked.connect(lambda row, _column: self.select_ids(row.data(0, Qt.ItemDataRole.UserRole) or []))
        layout.addWidget(self.tree)

    def set_statuses(self, statuses: list[GuildStatus]) -> None:
        names = {}
        for status in statuses:
            for identity in status.member_ids:
                item = self.scene.find_item_by_id(UUID(identity))
                names[identity] = getattr(item, "name", "") or species_display_name(item.metadata.get("plant_species") or {}) if item is not None else ""
        signature = ([asdict(s) for s in statuses], names)
        if signature == self._signature:
            return
        self._signature = signature
        self.statuses = statuses
        self.tree.clear()
        for status in statuses:
            coverage = self.tr("Complete") if not status.missing else self.tr("{count} missing roles").format(count=len(status.missing))
            root = QTreeWidgetItem([self.tr("{name} — {count} members — {coverage}").format(
                name=status.name, count=len(status.member_ids), coverage=coverage)])
            root.setData(0, Qt.ItemDataRole.UserRole, list(status.member_ids))
            self.tree.addTopLevelItem(root)
            for function, required in status.required.items():
                row = QTreeWidgetItem([self.tr("{function}: {present}/{required}").format(
                    function=trait_label(function), present=status.present.get(function, 0), required=required)])
                row.setData(0, Qt.ItemDataRole.UserRole, [status.centre_id])
                root.addChild(row)
            for identity in status.member_ids:
                row = QTreeWidgetItem([names[identity]])
                row.setData(0, Qt.ItemDataRole.UserRole, [identity])
                root.addChild(row)
