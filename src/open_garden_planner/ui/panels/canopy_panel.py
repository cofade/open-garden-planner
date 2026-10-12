"""Read-only mature-canopy grouping in Plant Details; rows own UUIDs only."""

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from open_garden_planner.models.plant_data import PermacultureLayer
from open_garden_planner.services.sun_mismatch_service import CanopyPlant, SunEvaluation
from open_garden_planner.ui.panels.diagnostics_panel import ObjectNavigator
from open_garden_planner.ui.sun_exposure_text import exposure_hours_text, unavailable_message
from open_garden_planner.ui.widgets.trait_filters import trait_label


class CanopyPanel(ObjectNavigator):
    def __init__(self, scene: Any, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self._signature: Any = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        title = QLabel(self.tr("Under this canopy"))
        layout.addWidget(title)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("Plant / food-forest layer"), self.tr("Estimated direct sun")])
        self.tree.setMaximumHeight(260)
        self.tree.itemClicked.connect(lambda row, _column: self.select_ids(row.data(0, Qt.ItemDataRole.UserRole) or []))
        layout.addWidget(self.tree)
        self.hide()

    def set_members(self, selected_tree_id: str | None, members: list[CanopyPlant] | None,
                    evaluations: dict[str, SunEvaluation]) -> None:
        signature = (selected_tree_id, members, evaluations)
        if signature == self._signature:
            return
        self._signature = signature
        self.setVisible(selected_tree_id is not None)
        self.tree.clear()
        if selected_tree_id is None:
            return
        if members is None:
            self.hint.setText(self.tr("Mature canopy size unavailable"))
            return
        self.hint.setText(self.tr("Plant centres within the mature canopy; this does not identify the cause of shade."))
        groups = {}
        known = {layer.value for layer in PermacultureLayer}
        for plant in members:
            layer = plant.layer if plant.layer in known else "unknown"
            if layer not in groups:
                groups[layer] = QTreeWidgetItem([trait_label(layer)])
                self.tree.addTopLevelItem(groups[layer])
            evaluation = evaluations[plant.item_id]
            text = (exposure_hours_text(evaluation.hours, evaluation.reference_date) if evaluation.hours is not None
                    else unavailable_message(evaluation.reason or "absent"))
            row = QTreeWidgetItem([plant.name, text])
            row.setData(0, Qt.ItemDataRole.UserRole, [plant.item_id])
            groups[layer].addChild(row)
        self.tree.expandAll()
