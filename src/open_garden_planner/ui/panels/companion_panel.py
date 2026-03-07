"""Companion planting recommendation panel (US-10.3).

Shows good and bad companions for the currently selected plant, highlighting
those that are already nearby in the garden plan.  Clicking a companion entry
selects that plant on the canvas (if placed).
"""

import math

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from open_garden_planner.services.companion_planting_service import (
    CompanionPlantingService,
    CompanionRelationship,
)


class CompanionPanel(QWidget):
    """Sidebar panel showing companion planting recommendations.

    Displays beneficial and antagonistic companions for the selected plant.
    Companions already present nearby in the plan are marked with a star and
    shown in bold.  Clicking any list entry emits ``highlight_species_requested``
    so the application can select the matching canvas items.

    Args:
        companion_service: Shared CompanionPlantingService instance.
        parent: Optional parent widget.
    """

    #: Emitted when the user clicks a companion entry; carries the species name.
    highlight_species_requested = pyqtSignal(str)

    def __init__(
        self,
        companion_service: CompanionPlantingService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = companion_service
        self._canvas_scene: object | None = None
        self._radius_cm: float = 200.0  # 2 m default, should match app radius
        self._setup_ui()
        self.update_for_plant(None)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_canvas_scene(self, scene: object) -> None:
        """Attach the canvas scene used to cross-reference placed plants."""
        self._canvas_scene = scene

    def set_radius_cm(self, radius_cm: float) -> None:
        """Set the proximity radius (in cm) used to detect nearby plants."""
        self._radius_cm = radius_cm

    def update_for_plant(self, item: object | None) -> None:
        """Rebuild the companion lists for *item* (a canvas plant item, or None)."""
        self._good_list.clear()
        self._bad_list.clear()

        if item is None:
            self._plant_label.setText(self.tr("No plant selected"))
            self._add_empty_placeholder(self._good_list)
            self._add_empty_placeholder(self._bad_list)
            return

        species = self._species_name(item)
        if not species:
            self._plant_label.setText(self.tr("Unknown plant"))
            self._add_empty_placeholder(self._good_list)
            self._add_empty_placeholder(self._bad_list)
            return

        lang = self._current_lang()
        display_name = self._service.get_display_name(species, lang)
        self._plant_label.setText(self.tr("Companions for: %1").replace("%1", display_name))

        beneficial, antagonistic = self._service.get_companions(species)
        nearby = self._nearby_species(item)

        for rel in sorted(beneficial, key=lambda r: self._service.get_display_name(r.plant_b, lang)):
            self._add_list_entry(self._good_list, rel, rel.plant_b.lower() in nearby, lang)

        for rel in sorted(antagonistic, key=lambda r: self._service.get_display_name(r.plant_b, lang)):
            self._add_list_entry(self._bad_list, rel, rel.plant_b.lower() in nearby, lang)

        if self._good_list.count() == 0:
            self._add_empty_placeholder(self._good_list)
        if self._bad_list.count() == 0:
            self._add_empty_placeholder(self._bad_list)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self._plant_label = QLabel(self.tr("No plant selected"))
        self._plant_label.setWordWrap(True)
        self._plant_label.setStyleSheet("font-style: italic;")
        layout.addWidget(self._plant_label)

        good_header = QLabel(self.tr("Good Companions"))
        good_header.setStyleSheet("font-weight: bold; color: #2e7d32;")
        layout.addWidget(good_header)

        self._good_list = QListWidget()
        self._good_list.setMaximumHeight(160)
        self._good_list.setAlternatingRowColors(True)
        self._good_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._good_list)

        bad_header = QLabel(self.tr("Bad Companions"))
        bad_header.setStyleSheet("font-weight: bold; color: #c62828;")
        layout.addWidget(bad_header)

        self._bad_list = QListWidget()
        self._bad_list.setMaximumHeight(160)
        self._bad_list.setAlternatingRowColors(True)
        self._bad_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._bad_list)

        legend = QLabel(self.tr("★ = already nearby in plan  (click to select)"))
        legend.setStyleSheet("font-size: 10px; color: gray;")
        legend.setWordWrap(True)
        layout.addWidget(legend)

    def _add_list_entry(
        self,
        list_widget: QListWidget,
        rel: CompanionRelationship,
        nearby: bool,
        lang: str = "en",
    ) -> None:
        prefix = "★ " if nearby else "  "
        name = self._service.get_display_name(rel.plant_b, lang)
        reason = self._service.get_relationship_reason(rel, lang)
        text = f"{prefix}{name}"
        if reason:
            text += f"\n    {reason}"

        entry = QListWidgetItem(text)
        entry.setData(Qt.ItemDataRole.UserRole, rel.plant_b)
        entry.setToolTip(reason or "")
        if nearby:
            font = entry.font()
            font.setBold(True)
            entry.setFont(font)
            entry.setToolTip(
                (reason + "\n\n" if reason else "") + self.tr("Click to select on canvas")
            )
        list_widget.addItem(entry)

    def _add_empty_placeholder(self, list_widget: QListWidget) -> None:
        placeholder = QListWidgetItem(self.tr("(none in database)"))
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        placeholder.setForeground(self.palette().placeholderText())
        list_widget.addItem(placeholder)

    def _nearby_species(self, selected_item: object) -> set[str]:
        """Return lowercase species names of plants within radius of *selected_item*."""
        if self._canvas_scene is None:
            return set()

        try:
            sel_center = selected_item.mapToScene(selected_item.rect().center())  # type: ignore[attr-defined]
        except Exception:
            return set()

        nearby: set[str] = set()
        for item in self._canvas_scene.items():  # type: ignore[attr-defined]
            if item is selected_item:
                continue
            if not hasattr(item, "plant_species"):
                continue
            try:
                other_center = item.mapToScene(item.rect().center())  # type: ignore[attr-defined]
                dist = math.hypot(
                    sel_center.x() - other_center.x(),
                    sel_center.y() - other_center.y(),
                )
                if dist <= self._radius_cm:
                    sp = self._species_name(item)
                    if sp:
                        nearby.add(sp.lower())
            except Exception:
                continue
        return nearby

    @staticmethod
    def _current_lang() -> str:
        """Return the current app language code (e.g. 'en', 'de')."""
        try:
            from open_garden_planner.app.settings import get_settings
            return get_settings().language
        except Exception:
            return "en"

    @staticmethod
    def _species_name(item: object) -> str:
        """Return the best species name for companion DB lookup."""
        meta = getattr(item, "metadata", {}) or {}
        species_data = meta.get("plant_species") if isinstance(meta, dict) else None
        if isinstance(species_data, dict):
            name = (
                species_data.get("common_name")
                or species_data.get("scientific_name")
                or ""
            )
            if name:
                return name
        return getattr(item, "plant_species", "") or ""

    def _on_item_clicked(self, entry: QListWidgetItem) -> None:
        species = entry.data(Qt.ItemDataRole.UserRole)
        if species:
            self.highlight_species_requested.emit(species)
