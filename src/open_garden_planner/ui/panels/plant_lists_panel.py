"""Sidebar panel for Plant Lists and Favourites (US-G4, issue #320).

Allows users to manage plant collections (⭐ Favorites + custom palettes),
drag species onto the canvas, edit notes, import/export lists as JSON,
and update species snapshots from placed plants.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QDrag, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plant_renderer import render_plant_pixmap
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.models.plant_lists import (
    PlantListEntry,
    PlantListStore,
    get_plant_list_store,
)
from open_garden_planner.ui.theme import set_text_role, theme_color

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


class _DraggablePlantListWidget(QListWidget):
    """QListWidget supporting drag-to-canvas for plant list entries."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)

    def startDrag(self, supportedActions: Qt.DropAction) -> None:  # noqa: ARG002, N802
        item = self.currentItem()
        if not item:
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if not entry_id:
            return

        drag = QDrag(self)
        from PyQt6.QtCore import QMimeData  # noqa: PLC0415

        mime_data = QMimeData()
        mime_data.setText(f"plant_list:{entry_id}")
        drag.setMimeData(mime_data)

        icon = item.icon()
        if not icon.isNull():
            pixmap = icon.pixmap(32, 32)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(16, 16))

        drag.exec(Qt.DropAction.CopyAction)


class PlantListsPanel(QWidget):
    """Sidebar panel for browsing, managing, and dragging plant lists."""

    def __init__(
        self,
        store: PlantListStore | None = None,
        canvas_scene: CanvasScene | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store or get_plant_list_store()
        self._canvas_scene = canvas_scene
        self._current_list_id: str = PlantListStore.FAVORITES_ID

        self._setup_ui()
        self._store.changed.connect(self._on_store_changed)
        self._refresh_lists_dropdown()
        self._refresh_entries()

    def set_canvas_scene(self, scene: CanvasScene | None) -> None:
        """Update canvas scene reference."""
        self._canvas_scene = scene

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header / List Selector Row
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        self._list_combo = QComboBox()
        self._list_combo.currentIndexChanged.connect(self._on_list_selected)
        top_row.addWidget(self._list_combo, 1)

        self._menu_btn = QToolButton()
        self._menu_btn.setText("⋮")
        self._menu_btn.setToolTip(self.tr("List Actions"))
        self._menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._setup_list_menu()
        top_row.addWidget(self._menu_btn)

        layout.addLayout(top_row)

        # Description label
        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        set_text_role(self._desc_label, "hint")
        self._desc_label.setStyleSheet(
            f"color: {theme_color('text_secondary')}; font-size: 11px;"
        )
        layout.addWidget(self._desc_label)

        # Entries list
        self._entries_list = _DraggablePlantListWidget()
        self._entries_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._entries_list.customContextMenuRequested.connect(
            self._on_entry_context_menu
        )
        layout.addWidget(self._entries_list, 1)

        # Bottom action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self._add_selected_btn = QPushButton(
            self.tr("+ Add Selected from Plan")
        )
        self._add_selected_btn.setToolTip(
            self.tr("Add currently selected canvas plants to this list")
        )
        self._add_selected_btn.clicked.connect(self._on_add_selected_from_canvas)
        btn_layout.addWidget(self._add_selected_btn)

        layout.addLayout(btn_layout)

    def _setup_list_menu(self) -> None:
        menu = QMenu(self)

        act_new = QAction(self.tr("New List…"), self)
        act_new.triggered.connect(self._on_new_list)
        menu.addAction(act_new)

        self._act_rename = QAction(self.tr("Rename List…"), self)
        self._act_rename.triggered.connect(self._on_rename_list)
        menu.addAction(self._act_rename)

        self._act_delete = QAction(self.tr("Delete List"), self)
        self._act_delete.triggered.connect(self._on_delete_list)
        menu.addAction(self._act_delete)

        menu.addSeparator()

        act_export = QAction(self.tr("Export List to JSON…"), self)
        act_export.triggered.connect(self._on_export_list)
        menu.addAction(act_export)

        act_import = QAction(self.tr("Import List from JSON…"), self)
        act_import.triggered.connect(self._on_import_list)
        menu.addAction(act_import)

        self._menu_btn.setMenu(menu)

    # ── Refresh logic ─────────────────────────────────────────────────────────

    def _on_store_changed(self) -> None:
        """Handle store change event."""
        self._refresh_lists_dropdown()
        self._refresh_entries()

    def _refresh_lists_dropdown(self) -> None:
        """Populate the list combo box."""
        self._list_combo.blockSignals(True)
        self._list_combo.clear()

        all_lists = self._store.all_lists()
        select_index = 0
        for idx, pl in enumerate(all_lists):
            display_name = f"⭐ {pl.name}" if pl.id == PlantListStore.FAVORITES_ID else pl.name
            self._list_combo.addItem(display_name, pl.id)
            if pl.id == self._current_list_id:
                select_index = idx

        if all_lists:
            self._list_combo.setCurrentIndex(select_index)
            self._current_list_id = self._list_combo.currentData() or PlantListStore.FAVORITES_ID

        self._list_combo.blockSignals(False)
        self._update_actions_state()

    def _update_actions_state(self) -> None:
        """Enable/disable actions based on current list."""
        is_fav = self._current_list_id == PlantListStore.FAVORITES_ID
        self._act_rename.setEnabled(not is_fav)
        self._act_delete.setEnabled(not is_fav)

        curr_list = self._store.get_list(self._current_list_id)
        if curr_list and curr_list.description:
            self._desc_label.setText(curr_list.description)
            self._desc_label.show()
        else:
            self._desc_label.hide()

    def _create_thumbnail_for_species(self, species: PlantSpeciesData) -> QIcon:
        """Generate a thumbnail icon for a species."""
        name = species.common_name or species.scientific_name or ""
        pixmap = render_plant_pixmap(
            ObjectType.PERENNIAL, diameter=32, species=name
        )
        if pixmap and not pixmap.isNull():
            return QIcon(pixmap)

        # Fallback circle icon
        fallback = QPixmap(32, 32)
        fallback.fill(Qt.GlobalColor.transparent)
        from PyQt6.QtGui import QColor, QPainter  # noqa: PLC0415
        painter = QPainter(fallback)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#4CAF50"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.end()
        return QIcon(fallback)

    def _refresh_entries(self) -> None:
        """Populate the list entries widget."""
        self._entries_list.clear()
        curr_list = self._store.get_list(self._current_list_id)
        if not curr_list:
            return

        for entry in curr_list.entries:
            sp = entry.species
            common = sp.common_name or self.tr("Unknown Plant")
            scientific = sp.scientific_name

            title = f"{common} ({scientific})" if scientific and scientific != common else common
            display_text = f"{title}\n📝 {entry.note}" if entry.note else title

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            item.setIcon(self._create_thumbnail_for_species(sp))

            tooltip_parts = [title]
            if sp.data_source:
                tooltip_parts.append(self.tr("Source: {source}").format(source=sp.data_source.title()))
            if entry.note:
                tooltip_parts.append(self.tr("Note: {note}").format(note=entry.note))
            tooltip_parts.append(self.tr("Drag to place on canvas"))
            item.setToolTip("\n".join(tooltip_parts))

            self._entries_list.addItem(item)

    # ── List operations ───────────────────────────────────────────────────────

    def _on_list_selected(self, index: int) -> None:
        if index < 0:
            return
        list_id = self._list_combo.itemData(index)
        if list_id:
            self._current_list_id = list_id
            self._update_actions_state()
            self._refresh_entries()

    def _on_new_list(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            self.tr("New Plant List"),
            self.tr("List name:"),
        )
        if ok and name.strip():
            new_list = self._store.create_list(name.strip())
            self._current_list_id = new_list.id
            self._refresh_lists_dropdown()
            self._refresh_entries()

    def _on_rename_list(self) -> None:
        curr_list = self._store.get_list(self._current_list_id)
        if not curr_list or curr_list.id == PlantListStore.FAVORITES_ID:
            return

        name, ok = QInputDialog.getText(
            self,
            self.tr("Rename Plant List"),
            self.tr("New name:"),
            text=curr_list.name,
        )
        if ok and name.strip():
            self._store.rename_list(curr_list.id, name.strip())
            self._refresh_lists_dropdown()

    def _on_delete_list(self) -> None:
        curr_list = self._store.get_list(self._current_list_id)
        if not curr_list or curr_list.id == PlantListStore.FAVORITES_ID:
            return

        reply = QMessageBox.question(
            self,
            self.tr("Delete Plant List"),
            self.tr("Are you sure you want to delete '{name}'?").format(
                name=curr_list.name
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._store.delete_list(curr_list.id)
            self._current_list_id = PlantListStore.FAVORITES_ID
            self._refresh_lists_dropdown()
            self._refresh_entries()

    def _on_export_list(self) -> None:
        curr_list = self._store.get_list(self._current_list_id)
        if not curr_list:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export Plant List"),
            f"{curr_list.name.replace(' ', '_')}.json",
            self.tr("JSON Files (*.json)"),
        )
        if file_path:
            try:
                json_data = self._store.export_list_to_json(curr_list.id)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(json_data)
                QMessageBox.information(
                    self,
                    self.tr("Export Successful"),
                    self.tr("List exported to {path}").format(path=file_path),
                )
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(
                    self,
                    self.tr("Export Failed"),
                    self.tr("Could not export list: {error}").format(error=str(e)),
                )

    def _on_import_list(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import Plant List"),
            "",
            self.tr("JSON Files (*.json)"),
        )
        if file_path:
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                imported = self._store.import_list_from_json(content)
                self._current_list_id = imported.id
                self._refresh_lists_dropdown()
                self._refresh_entries()
                QMessageBox.information(
                    self,
                    self.tr("Import Successful"),
                    self.tr("Imported list '{name}' with {count} plants.").format(
                        name=imported.name, count=len(imported.entries)
                    ),
                )
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(
                    self,
                    self.tr("Import Failed"),
                    self.tr("Could not import list: {error}").format(error=str(e)),
                )

    # ── Entry Context Menu & Actions ──────────────────────────────────────────

    def _on_entry_context_menu(self, pos: QPoint) -> None:
        item = self._entries_list.itemAt(pos)
        if not item:
            return

        entry_id = item.data(Qt.ItemDataRole.UserRole)
        pl, entry = self._store.get_entry(entry_id)
        if not pl or not entry:
            return

        menu = QMenu(self)

        # Note action
        act_note = QAction(self.tr("Edit Note…"), self)
        act_note.triggered.connect(lambda: self._on_edit_entry_note(entry))
        menu.addAction(act_note)

        # Move to list submenu
        other_lists = [
            l_obj for l_obj in self._store.all_lists() if l_obj.id != pl.id
        ]
        if other_lists:
            move_menu = menu.addMenu(self.tr("Move to List"))
            for dest_list in other_lists:
                act_move = QAction(dest_list.name, self)
                dest_id = dest_list.id
                act_move.triggered.connect(
                    lambda _, d_id=dest_id: self._store.move_entry(
                        pl.id, d_id, entry.id
                    )
                )
                move_menu.addAction(act_move)

        # Update from plan action
        act_update = QAction(self.tr("Update from Plan"), self)
        canvas_plant = self._find_selected_canvas_plant_matching(entry.species_key)
        act_update.setEnabled(canvas_plant is not None)
        if canvas_plant:
            act_update.setToolTip(
                self.tr("Update stored snapshot from selected canvas plant")
            )
            act_update.triggered.connect(
                lambda: self._on_update_entry_from_plan(entry, canvas_plant)
            )
        else:
            act_update.setToolTip(
                self.tr("Select matching plant on canvas to update snapshot")
            )
        menu.addAction(act_update)

        menu.addSeparator()

        # Remove action
        act_remove = QAction(self.tr("Remove from List"), self)
        act_remove.triggered.connect(
            lambda: self._store.remove_entry(pl.id, entry.id)
        )
        menu.addAction(act_remove)

        menu.exec(self._entries_list.mapToGlobal(pos))

    def _on_edit_entry_note(self, entry: PlantListEntry) -> None:
        note, ok = QInputDialog.getText(
            self,
            self.tr("Edit Plant Note"),
            self.tr("Note for {name}:").format(
                name=entry.species.common_name or entry.species.scientific_name
            ),
            text=entry.note,
        )
        if ok:
            self._store.update_entry_note(self._current_list_id, entry.id, note)

    def _find_selected_canvas_plant_matching(
        self, target_species_key: str
    ) -> Any | None:
        """Find a selected canvas plant matching target_species_key."""
        if not self._canvas_scene:
            return None
        from open_garden_planner.models.plant_lists import _get_species_key

        for item in self._canvas_scene.selectedItems():
            meta = getattr(item, "metadata", None)
            if not isinstance(meta, dict):
                continue
            species_dict = meta.get("plant_species")
            if isinstance(species_dict, dict):
                sp_key = _get_species_key(species_dict)
                if sp_key == target_species_key:
                    return item
            elif getattr(item, "plant_species", None):
                sp_key = _get_species_key(item.plant_species)
                if sp_key == target_species_key:
                    return item
        return None

    def _on_update_entry_from_plan(
        self, entry: PlantListEntry, canvas_plant: Any
    ) -> None:
        """Update entry's species snapshot from canvas plant."""
        meta = getattr(canvas_plant, "metadata", {})
        species_dict = meta.get("plant_species")
        if isinstance(species_dict, dict):
            new_species = PlantSpeciesData.from_dict(species_dict)
        else:
            name = getattr(canvas_plant, "plant_species", "")
            new_species = PlantSpeciesData(
                scientific_name=name, common_name=name
            )

        self._store.update_entry_species(
            self._current_list_id, entry.id, new_species
        )
        QMessageBox.information(
            self,
            self.tr("Snapshot Updated"),
            self.tr("Species data updated from selected canvas plant."),
        )

    # ── Canvas selection integration ──────────────────────────────────────────

    def _on_add_selected_from_canvas(self) -> None:
        """Add any currently selected canvas plants to the current list."""
        if not self._canvas_scene:
            return
        selected = self._canvas_scene.selectedItems()
        added_count = 0

        for item in selected:
            meta = getattr(item, "metadata", None)
            species_obj: PlantSpeciesData | None = None
            if isinstance(meta, dict) and isinstance(meta.get("plant_species"), dict):
                with contextlib.suppress(Exception):
                    species_obj = PlantSpeciesData.from_dict(meta["plant_species"])

            if not species_obj:
                name = getattr(item, "plant_species", None)
                if name:
                    from open_garden_planner.services.bundled_species_db import lookup_species
                    rec = lookup_species(name)
                    if rec:
                        species_obj = PlantSpeciesData.from_dict(rec)
                    else:
                        species_obj = PlantSpeciesData(
                            scientific_name=name, common_name=name
                        )

            if species_obj:
                self._store.add_entry(self._current_list_id, species_obj)
                added_count += 1

        if added_count == 0:
            QMessageBox.information(
                self,
                self.tr("No Plants Selected"),
                self.tr("Please select one or more plants on the canvas first."),
            )
