"""Find & Replace panel — floating tool window for searching and bulk-editing canvas items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class FindReplacePanel(QWidget):
    """Floating panel for finding canvas items by name/type/layer/species and bulk-editing them."""

    def __init__(self, canvas_view: CanvasView, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self._canvas_view = canvas_view
        self._matched_items: list = []
        self._setup_ui()
        self.setVisible(False)
        self.setWindowTitle(self.tr("Find & Replace"))
        self.resize(320, 420)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # --- Search criteria ---
        layout.addWidget(QLabel(self.tr("Name contains:")))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(self.tr("(any)"))
        layout.addWidget(self._name_edit)

        layout.addWidget(QLabel(self.tr("Type:")))
        self._type_combo = QComboBox()
        layout.addWidget(self._type_combo)

        layout.addWidget(QLabel(self.tr("Layer:")))
        self._layer_combo = QComboBox()
        layout.addWidget(self._layer_combo)

        layout.addWidget(QLabel(self.tr("Species contains:")))
        self._species_edit = QLineEdit()
        self._species_edit.setPlaceholderText(self.tr("(any)"))
        layout.addWidget(self._species_edit)

        btn_row = QHBoxLayout()
        self._search_btn = QPushButton(self.tr("Search"))
        self._search_btn.clicked.connect(self._on_search)
        btn_row.addWidget(self._search_btn)
        self._select_all_btn = QPushButton(self.tr("Select All Matching"))
        self._select_all_btn.clicked.connect(self._on_select_all)
        btn_row.addWidget(self._select_all_btn)
        layout.addLayout(btn_row)

        # --- Results ---
        self._results_list = QListWidget()
        self._results_list.setMaximumHeight(160)
        self._results_list.itemClicked.connect(self._on_result_clicked)
        layout.addWidget(self._results_list)

        # --- Bulk actions ---
        layer_row = QHBoxLayout()
        layer_row.addWidget(QLabel(self.tr("Bulk change layer:")))
        self._target_layer_combo = QComboBox()
        layer_row.addWidget(self._target_layer_combo, 1)
        apply_layer_btn = QPushButton(self.tr("Apply"))
        apply_layer_btn.clicked.connect(self._on_apply_layer)
        layer_row.addWidget(apply_layer_btn)
        layout.addLayout(layer_row)

        species_row = QHBoxLayout()
        species_row.addWidget(QLabel(self.tr("Replace species:")))
        self._replace_species_edit = QLineEdit()
        species_row.addWidget(self._replace_species_edit, 1)
        apply_species_btn = QPushButton(self.tr("Apply"))
        apply_species_btn.clicked.connect(self._on_replace_species)
        species_row.addWidget(apply_species_btn)
        layout.addLayout(species_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_combos(self) -> None:
        """Repopulate type and layer combos from the current scene."""
        scene = self._canvas_view.scene()
        if scene is None:
            return

        # Collect unique type display names from scene items
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        type_names: list[str] = []
        for item in scene.items():
            if isinstance(item, GardenItemMixin):
                ot = getattr(item, "object_type", None)
                if ot is not None:
                    name = getattr(ot, "name", str(ot))
                    if name not in type_names:
                        type_names.append(name)
        type_names.sort()

        current_type = self._type_combo.currentText()
        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        self._type_combo.addItem(self.tr("All Types"), userData=None)
        for name in type_names:
            self._type_combo.addItem(name, userData=name)
        idx = self._type_combo.findText(current_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._type_combo.blockSignals(False)

        # Layers
        layers = getattr(scene, "layers", None)
        layers_list = layers() if callable(layers) else (layers or [])

        current_layer = self._layer_combo.currentText()
        current_target = self._target_layer_combo.currentText()
        for combo in (self._layer_combo, self._target_layer_combo):
            combo.blockSignals(True)
            combo.clear()
        self._layer_combo.addItem(self.tr("All Layers"), userData=None)
        for layer in layers_list:
            self._layer_combo.addItem(layer.name, userData=layer.id)
            self._target_layer_combo.addItem(layer.name, userData=layer.id)
        idx = self._layer_combo.findText(current_layer)
        if idx >= 0:
            self._layer_combo.setCurrentIndex(idx)
        idx = self._target_layer_combo.findText(current_target)
        if idx >= 0:
            self._target_layer_combo.setCurrentIndex(idx)
        for combo in (self._layer_combo, self._target_layer_combo):
            combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search(self) -> list:
        """Return all GardenItemMixin items matching the current criteria."""
        scene = self._canvas_view.scene()
        if scene is None:
            return []

        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        name_filter = self._name_edit.text().strip().lower()
        type_filter = self._type_combo.currentData()
        layer_filter = self._layer_combo.currentData()
        species_filter = self._species_edit.text().strip().lower()

        results = []
        for item in scene.items():
            if not isinstance(item, GardenItemMixin):
                continue

            if name_filter:
                item_name = (getattr(item, "name", None) or "").lower()
                if name_filter not in item_name:
                    continue

            if type_filter is not None:
                ot = getattr(item, "object_type", None)
                ot_name = getattr(ot, "name", str(ot)) if ot is not None else ""
                if ot_name != type_filter:
                    continue

            if layer_filter is not None and getattr(item, "layer_id", None) != layer_filter:
                continue

            if species_filter:
                meta = getattr(item, "metadata", {}) or {}
                species_data = meta.get("plant_species") if isinstance(meta, dict) else None
                species_name = ""
                if isinstance(species_data, dict):
                    species_name = (species_data.get("common_name") or "").lower()
                elif isinstance(species_data, str):
                    species_name = species_data.lower()
                if species_filter not in species_name:
                    continue

            results.append(item)
        return results

    def _highlight(self, items: list) -> None:
        scene = self._canvas_view.scene()
        if scene is None:
            return
        scene.clearSelection()
        for item in items:
            item.setSelected(True)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        self._matched_items = self._search()
        self._results_list.clear()
        for item in self._matched_items:
            item_name = getattr(item, "name", None) or self.tr("(unnamed)")
            ot = getattr(item, "object_type", None)
            type_str = getattr(ot, "name", str(ot)) if ot is not None else "?"
            list_item = QListWidgetItem(f"{item_name}  [{type_str}]")
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self._results_list.addItem(list_item)
        self._highlight(self._matched_items)

    def _on_select_all(self) -> None:
        self._matched_items = self._search()
        self._highlight(self._matched_items)

    def _on_result_clicked(self, list_item: QListWidgetItem) -> None:
        item = list_item.data(Qt.ItemDataRole.UserRole)
        if item is None:
            return
        scene = self._canvas_view.scene()
        if scene:
            scene.clearSelection()
            item.setSelected(True)
        self._canvas_view.ensureVisible(item)

    def _on_apply_layer(self) -> None:
        target_layer_id = self._target_layer_combo.currentData()
        if target_layer_id is None or not self._matched_items:
            return
        from open_garden_planner.core.commands import MoveToLayerCommand

        scene = self._canvas_view.scene()
        if scene is None:
            return
        target_layer = scene.get_layer_by_id(target_layer_id)
        layer_name = target_layer.name if target_layer else str(target_layer_id)
        items = [i for i in self._matched_items if hasattr(i, "layer_id")]
        if not items:
            return
        cmd = MoveToLayerCommand(items, target_layer_id, scene, layer_name)
        cmd_mgr = getattr(scene, "_command_manager", None)
        if cmd_mgr:
            cmd_mgr.execute(cmd)
        else:
            cmd.execute()

    def _on_replace_species(self) -> None:
        new_species = self._replace_species_edit.text().strip()
        if not new_species or not self._matched_items:
            return
        for item in self._matched_items:
            meta = getattr(item, "metadata", None)
            if not isinstance(meta, dict):
                continue
            species_data = meta.get("plant_species")
            if isinstance(species_data, dict):
                species_data["common_name"] = new_species
                item.update()
            elif species_data is not None:
                meta["plant_species"] = {"common_name": new_species}
                item.update()
