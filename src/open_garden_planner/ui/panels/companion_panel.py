"""Companion planting recommendation panel (US-10.3).

Shows good and bad companions for the currently selected plant, highlighting
those that are already nearby in the garden plan.  Clicking a companion entry
selects that plant on the canvas (if placed).
"""

import math

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services.companion_planting_service import (
    CompanionPlantingService,
    CompanionRelationship,
)
from open_garden_planner.ui.icons import get_icon, get_pixmap
from open_garden_planner.ui.theme import set_text_role, theme_color

_NEARBY_ROLE = Qt.ItemDataRole.UserRole + 1  # bool: row carries the nearby star


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
        self._current_item = item
        self._good_list.clear()
        self._bad_list.clear()

        if item is None:
            self._plant_label.setText(self.tr("No plant selected"))
            self._add_empty_placeholder(self._good_list)
            self._add_empty_placeholder(self._bad_list)
            self._update_provider_credit()
            return

        species = self._species_name(item)
        if not species:
            self._plant_label.setText(self.tr("Unknown plant"))
            self._add_empty_placeholder(self._good_list)
            self._add_empty_placeholder(self._bad_list)
            self._update_provider_credit()
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

        self._update_provider_credit()

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

        # === PROVIDER ACTIONS (US-G3, issue #318) ===
        actions_row = QHBoxLayout()
        actions_row.setSpacing(4)

        self._fetch_permapeople_btn = QPushButton(self.tr("Fetch from Permapeople"))
        self._fetch_permapeople_btn.setToolTip(
            self.tr("Fetch companion/antagonist data from Permapeople for this plant")
        )
        self._fetch_permapeople_btn.clicked.connect(self._on_fetch_permapeople)
        actions_row.addWidget(self._fetch_permapeople_btn)

        self._refresh_permapeople_btn = QPushButton(self.tr("Refresh"))
        self._refresh_permapeople_btn.setToolTip(
            self.tr("Refresh companion data from Permapeople (re-fetches and replaces cache)")
        )
        self._refresh_permapeople_btn.clicked.connect(self._on_refresh_permapeople)
        actions_row.addWidget(self._refresh_permapeople_btn)

        layout.addLayout(actions_row)

        # === COMPATIBLE SET ACTION (US-D3.1, issue #319) ===
        self._suggest_set_btn = QPushButton(self.tr("Suggest a compatible set…"))
        self._suggest_set_btn.setToolTip(
            self.tr("Find mutually compatible plant sets for this bed")
        )
        self._suggest_set_btn.clicked.connect(self._on_suggest_compatible_set)
        layout.addWidget(self._suggest_set_btn)

        good_header = QLabel(self.tr("Good Companions"))
        set_text_role(good_header, "h2", "success")
        layout.addWidget(good_header)

        self._good_list = QListWidget()
        self._good_list.setMaximumHeight(160)
        self._good_list.setAlternatingRowColors(True)
        self._good_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._good_list)

        bad_header = QLabel(self.tr("Bad Companions"))
        set_text_role(bad_header, "h2", "error")
        layout.addWidget(bad_header)

        self._bad_list = QListWidget()
        self._bad_list.setMaximumHeight(160)
        self._bad_list.setAlternatingRowColors(True)
        self._bad_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._bad_list)

        # === PROVIDER CREDIT LINE (US-G3, issue #318) ===
        self._provider_credit = QLabel()
        self._provider_credit.setWordWrap(True)
        set_text_role(self._provider_credit, "hint")
        self._provider_credit.setVisible(False)
        layout.addWidget(self._provider_credit)

        legend_row = QHBoxLayout()
        legend_row.setSpacing(4)
        self._legend_icon = QLabel()
        self._legend_icon.setFixedSize(16, 16)
        legend_row.addWidget(self._legend_icon)
        legend = QLabel(self.tr("= already nearby in plan  (click to select)"))
        set_text_role(legend, "hint")
        legend.setWordWrap(True)
        legend_row.addWidget(legend, 1)
        layout.addLayout(legend_row)
        self.refresh_theme_icons()

    def refresh_theme_icons(self) -> None:
        """Theme-switch hook: re-tint the legend star and every nearby-star
        row (baked icons do not follow the palette, #310)."""
        pixmap = get_pixmap("star", 14, color=theme_color("accent"))
        if pixmap is not None:
            self._legend_icon.setPixmap(pixmap)
        icon = get_icon("star", color=theme_color("accent"))
        if icon is None:
            return
        for lst in (self._good_list, self._bad_list):
            for i in range(lst.count()):
                row = lst.item(i)
                if row is not None and row.data(_NEARBY_ROLE):
                    row.setIcon(icon)

    def _add_list_entry(
        self,
        list_widget: QListWidget,
        rel: CompanionRelationship,
        nearby: bool,
        lang: str = "en",
    ) -> None:
        name = self._service.get_display_name(rel.plant_b, lang)
        reason = self._service.get_relationship_reason(rel, lang)
        source_label = self._get_source_label(rel)
        text = f"{name} [{source_label}]"
        if reason:
            text += f"\n    {reason}"

        entry = QListWidgetItem(text)
        entry.setData(_NEARBY_ROLE, bool(nearby))
        if nearby:  # star icon (was a "★ " text prefix, #310)
            icon = get_icon("star", color=theme_color("accent"))
            if icon is not None:
                entry.setIcon(icon)
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

    # ------------------------------------------------------------------
    # Provider actions (US-G3, issue #318)
    # ------------------------------------------------------------------

    def _on_fetch_permapeople(self) -> None:
        """Fetch companion data from Permapeople for the selected plant."""
        species = self._get_current_species_name()
        if not species:
            return
        self._fetch_permapeople_companions(species)

    def _on_refresh_permapeople(self) -> None:
        """Refresh companion data from Permapeople (re-fetch and replace cache)."""
        species = self._get_current_species_name()
        if not species:
            return
        self._fetch_permapeople_companions(species, force=True)

    def _get_current_species_name(self) -> str:
        """Return the scientific name of the currently selected plant, or empty."""
        if not hasattr(self, "_current_item") or self._current_item is None:
            return ""
        meta = getattr(self._current_item, "metadata", {}) or {}
        species_data = meta.get("plant_species") if isinstance(meta, dict) else None
        if isinstance(species_data, dict):
            return (
                species_data.get("scientific_name")
                or species_data.get("common_name")
                or ""
            )
        return ""

    def _fetch_permapeople_companions(self, species_name: str, force: bool = False) -> None:
        """Fetch companions from Permapeople for a species.

        Args:
            species_name: The plant's name.
            force: If True, re-fetch even if cached.
        """
        from open_garden_planner.services.companion_cache import get_cached_companions
        from open_garden_planner.services.plant_api.permapeople_client import (
            PermapeopleClient,
        )

        # Check cache first (unless force=True)
        if not force:
            cached = get_cached_companions(species_name)
            if cached is not None:
                self._service.add_provider_companions(species_name, cached)
                self._update_provider_credit()
                self.update_for_plant(self._current_item)
                return

        # Need to fetch from API
        try:
            client = PermapeopleClient()
            if not client.is_configured():
                self._provider_credit.setText(
                    self.tr("Permapeople credentials not configured — "
                        "set them in Preferences → Plant APIs")
                )
                self._provider_credit.setVisible(True)
                return

            # Search for the plant to get its ID
            results = client.search(species_name, limit=1)
            if not results:
                return
            plant_id = results[0].source_id
            if not plant_id:
                return

            companions = client.get_companions(plant_id)
            if companions:
                self._service.add_provider_companions(species_name, companions)
                self._update_provider_credit()
                self.update_for_plant(self._current_item)
        except Exception as exc:
            self._provider_credit.setText(
                self.tr("Failed to fetch companion data: {error}").format(error=str(exc))
            )
            self._provider_credit.setVisible(True)

    def _update_provider_credit(self) -> None:
        """Update the provider credit line based on loaded provider rules."""
        count = self._service.get_provider_companions_count()
        if count > 0:
            self._provider_credit.setText(
                self.tr("Companion data from Permapeople · CC BY-SA 4.0 "
                    "({count} relationships loaded)").format(count=count)
            )
            self._provider_credit.setVisible(True)
        else:
            self._provider_credit.setVisible(False)

    def _get_source_label(self, rel: CompanionRelationship) -> str:
        """Return the source label for a relationship (Bundled / Custom / Permapeople)."""
        source = self._service.get_relationship_source(rel)
        if source == "custom":
            return self.tr("Custom")
        if source == "permapeople":
            return self.tr("Permapeople")
        return self.tr("Bundled")

    # ------------------------------------------------------------------
    # Compatible set action (US-D3.1, issue #319)
    # ------------------------------------------------------------------

    def _on_suggest_compatible_set(self) -> None:
        """Show a dialog with compatible sets for the selected plant's bed."""
        from open_garden_planner.services.companion_sets import find_sets_for_bed

        if not hasattr(self, "_current_item") or self._current_item is None:
            return

        # Find the bed this plant is in
        bed_id = self._get_current_bed_id()
        if not bed_id:
            return

        # Get plants already in the bed
        bed_plants = self._get_bed_plants(bed_id)
        if not bed_plants:
            return

        # Rank sets by how much of the bed they satisfy, and report conflicts.
        # Deliberately NOT find_compatible_sets(must_include=bed_plants) — that
        # returns nothing unless the bed already IS a complete clique, which is
        # the very situation the user is trying to resolve (P0-2).
        result = find_sets_for_bed(self._service, bed_plants, size=3)

        dialog = CompatibleSetDialog(
            result["sets"],
            result["bed_plants"],
            result["conflicts"],
            result["uncovered"],
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.get_selected_set()
            if selected:
                self._highlight_members(selected)

    def _get_current_bed_id(self) -> str | None:
        """Return the bed ID of the currently selected plant, if any."""
        if not hasattr(self, "_current_item") or self._current_item is None:
            return None
        # parent_bed_id is a property on GardenItem (stored as _parent_bed_id UUID)
        bed_id = getattr(self._current_item, "parent_bed_id", None)
        if bed_id:
            return str(bed_id)
        return None

    def _get_bed_plants(self, bed_id: str) -> list[str]:
        """Return species keys of plants in the given bed.

        Returns ``[]`` for a bed with no plants. A scene that cannot be walked
        at all raises — an ``except Exception: pass`` here turned any failure
        into "bed is empty", which the caller cannot distinguish from a real
        empty bed, and the action then opened an empty dialog for the same
        reason it did before the parent_bed_id fix.
        """
        if self._canvas_scene is None:
            return []
        plants: list[str] = []
        for item in self._canvas_scene.items():
            if not hasattr(item, "plant_species"):
                continue
            # parent_bed_id is a property on GardenItem, not in metadata
            parent = getattr(item, "parent_bed_id", None)
            if parent and str(parent) == bed_id:
                sp = self._species_name(item)
                if sp:
                    plants.append(sp.lower())
        return plants

    def _highlight_members(self, members: list[str]) -> None:
        """Highlight the selected members on the canvas (if already placed).

        This is a GUI-only action — it does not insert new plants. The
        actual insertion would require a separate create-plants path.
        """
        for member in members:
            self.highlight_species_requested.emit(member)


class CompatibleSetDialog(QDialog):
    """Dialog showing compatible plant sets for a bed (US-D3.1).

    Sets are ranked by how many of the bed's CURRENT plants each one already
    satisfies, so the top row is the set that agrees with the most of what is
    already planted. ``conflicts`` carries only bed plants that are genuinely
    ANTAGONISTIC to another bed plant — absence from a set is not a clash, and
    is listed separately as ``uncovered`` with neutral wording, because calling
    it a conflict once told users a bundled-beneficial pair did not work
    together.
    """

    def __init__(
        self,
        sets: list[dict],
        existing_plants: list[str],
        conflicts: list[dict] | None = None,
        uncovered: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sets = sets
        self._existing_plants = existing_plants
        self._conflicts = conflicts or []
        self._uncovered = uncovered or []
        self._selected: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle(self.tr("Compatible Plant Sets"))
        layout = QVBoxLayout(self)

        if self._existing_plants:
            # Inline {named} fields, NOT Qt's positional %1. `.format()` on a
            # "%1" string is a SILENT no-op -- there is no {field} to fill, so
            # it returned the literal and the bed's plants were never shown at
            # all. The registered translations for these three strings are in
            # {named} form, so this is also the only variant present in the
            # .ts; a %1 literal matches neither the table nor the output,
            # which is why the i18n gate was structurally blind to it.
            label = QLabel(
                self.tr("Already in bed: {plants}").format(
                    plants=", ".join(self._existing_plants)
                )
            )
            set_text_role(label, "hint")
            layout.addWidget(label)

        bed_count = len(self._existing_plants)
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        for entry in self._sets:
            members_str = ", ".join(entry["members"])
            score = entry.get("score", 0.0)
            covers = entry.get("covers", [])
            if entry.get("covers_all") and bed_count:
                suffix = self.tr("keeps all {count} already planted").format(
                    count=bed_count
                )
            elif covers:
                suffix = self.tr("keeps {count} of {total} already planted").format(
                    count=len(covers), total=bed_count
                )
            else:
                suffix = self.tr("replaces what is planted")
            item = QListWidgetItem(
                self.tr("{members}  (score: {score:.1f}) — {note}").format(
                    members=members_str, score=score, note=suffix
                )
            )
            item.setData(Qt.ItemDataRole.UserRole, entry["members"])
            self._list.addItem(item)
        if self._sets:
            self._list.setCurrentRow(0)
        layout.addWidget(self._list)

        if not self._sets:
            label = QLabel(
                self.tr(
                    "No compatible set found among the plants already in this bed "
                    "and their companions."
                )
            )
            set_text_role(label, "hint")
            layout.addWidget(label)

        # Name genuine bed-internal clashes. A plant that merely fits no set of
        # this size is NOT a clash — saying so told users mint does not go with
        # cabbage when the bundled data says it does.
        for conflict in self._conflicts:
            text = self.tr("{plant} clashes with {others} already in this bed.").format(
                plant=conflict["species_key"],
                others=", ".join(conflict.get("antagonistic_to", [])),
            )
            label = QLabel(text)
            set_text_role(label, "h2", "warning")
            label.setWordWrap(True)
            layout.addWidget(label)

        for name in self._uncovered:
            if any(c["species_key"] == name for c in self._conflicts):
                continue
            label = QLabel(
                self.tr("{plant} is not part of any of these sets.").format(plant=name)
            )
            set_text_role(label, "hint")
            label.setWordWrap(True)
            layout.addWidget(label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        item = self._list.currentItem()
        if item:
            self._selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def get_selected_set(self) -> list[str]:
        """Return the selected set's member list."""
        return self._selected
