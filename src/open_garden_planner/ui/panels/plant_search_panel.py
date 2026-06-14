"""Plant search panel for finding and filtering plants in the project."""

import contextlib
from uuid import UUID

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import PlantSpeciesData


class PlantListItem(QWidget):
    """Custom widget for a plant list item."""

    def __init__(
        self,
        item_id: UUID,
        name: str,
        species: str,
        plant_type: ObjectType,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the plant list item.

        Args:
            item_id: The UUID of the graphics item
            name: Display name of the plant
            species: Scientific name of the plant
            plant_type: The plant type (TREE, SHRUB, PERENNIAL)
            parent: Parent widget
        """
        super().__init__(parent)
        self.item_id = item_id
        # Hardening: let every press fall straight through to the QListWidget
        # viewport so the click always hit-tests to the row regardless of this
        # widget's child layout. The row needs no mouse interaction of its own;
        # selection is driven entirely by the list's itemClicked (issue #212).
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._setup_ui(name, species, plant_type)

    def _setup_ui(self, name: str, species: str, plant_type: ObjectType) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Top row: type icon and name
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        # Type icon/label
        type_icons = {
            ObjectType.TREE: "🌳",
            ObjectType.SHRUB: "🌿",
            ObjectType.PERENNIAL: "🌸",
        }
        type_label = QLabel(type_icons.get(plant_type, "🌱"))
        type_label.setFixedWidth(20)
        top_row.addWidget(type_label)

        # Plant name
        name_label = QLabel(name or "Unnamed")
        name_label.setStyleSheet("font-weight: bold;")
        top_row.addWidget(name_label, 1)

        layout.addLayout(top_row)

        # Bottom row: scientific name
        if species:
            species_label = QLabel(species)
            species_label.setProperty("secondary", True)
            species_label.setStyleSheet("font-style: italic; padding-left: 24px;")
            layout.addWidget(species_label)


class PlantSearchPanel(QWidget):
    """Panel for searching and filtering plants in the current project.

    Allows users to:
    - Search plants by common name, scientific name, or family
    - Filter by plant type (Tree, Shrub, Perennial)
    - Click on a plant to select and pan to it on the canvas
    """

    plant_selected = pyqtSignal(UUID)  # Emitted when a plant is clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the plant search panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        # (item_id, name, species, family, object_type). No live QGraphicsItem is
        # cached - selection resolves the item by id via the scene (see
        # _apply_selection), which keeps it reliable across undo/redo/delete (#212).
        self._all_plants: list[tuple[UUID, str, str, str, ObjectType]] = []
        # Signature of the rows currently rendered in the list. Lets
        # _update_results_display skip the destructive clear()+rebuild when the
        # visible set is unchanged, so the chatty (debounced) scene.changed refresh
        # no longer resets scroll position or tears down the row mid-click (#212).
        # `family` is deliberately excluded (it is never displayed) — any family
        # change that affects results also changes the visible membership, so the
        # id-set already differs; tracking it here would only force needless rebuilds.
        self._rendered_signature: tuple[tuple[UUID, str, str, ObjectType], ...] | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Search input
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Search plants..."))
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)

        layout.addLayout(search_layout)

        # Filter checkboxes
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        self.tree_checkbox = QCheckBox(self.tr("🌳 Trees"))
        self.tree_checkbox.setChecked(True)
        self.tree_checkbox.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.tree_checkbox)

        self.shrub_checkbox = QCheckBox(self.tr("🌿 Shrubs"))
        self.shrub_checkbox.setChecked(True)
        self.shrub_checkbox.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.shrub_checkbox)

        self.perennial_checkbox = QCheckBox(self.tr("🌸 Perennials"))
        self.perennial_checkbox.setChecked(True)
        self.perennial_checkbox.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.perennial_checkbox)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Results count label
        self.results_label = QLabel(self.tr("No plants in project"))
        self.results_label.setStyleSheet("color: palette(text);")
        layout.addWidget(self.results_label)

        # Results list
        self.results_list = QListWidget()
        self.results_list.setAlternatingRowColors(True)
        self.results_list.itemClicked.connect(self._on_item_clicked)
        self.results_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.results_list)

    def set_canvas_scene(self, scene) -> None:
        """Set the canvas scene to query plants from.

        Args:
            scene: The CanvasScene instance
        """
        self._scene = scene
        self.refresh_plant_list()

    def refresh_plant_list(self) -> None:
        """Refresh the list of plants from the canvas scene."""
        self._all_plants = []

        if not hasattr(self, "_scene") or self._scene is None:
            self._update_results_display()
            return

        # Query all items from the scene
        for item in self._scene.items():
            if not hasattr(item, "object_type"):
                continue

            object_type = item.object_type
            if object_type not in (ObjectType.TREE, ObjectType.SHRUB, ObjectType.PERENNIAL):
                continue

            # Get plant data
            item_id = getattr(item, "item_id", None)
            if item_id is None:
                continue

            # Get name from item or plant metadata
            name = getattr(item, "name", None) or ""
            species = ""
            family = ""

            if hasattr(item, "metadata") and item.metadata:
                species_data = item.metadata.get("plant_species")
                if species_data:
                    if isinstance(species_data, dict):
                        name = name or species_data.get("common_name", "")
                        species = species_data.get("scientific_name", "")
                        family = species_data.get("family", "")
                    elif isinstance(species_data, PlantSpeciesData):
                        name = name or species_data.common_name or ""
                        species = species_data.scientific_name or ""
                        family = species_data.family or ""

            # Store plant info: (id, name, species, family, type)
            self._all_plants.append((item_id, name, species, family, object_type))

        # Sort alphabetically by name (case-insensitive)
        self._all_plants.sort(key=lambda p: (p[1] or "").lower())

        self._update_results_display()

    def _on_search_changed(self, _text: str) -> None:
        """Handle search text changes."""
        self._update_results_display(from_user_input=True)

    def _on_filter_changed(self) -> None:
        """Handle filter checkbox changes."""
        self._update_results_display(from_user_input=True)

    def _visible_plants(self) -> list[tuple[UUID, str, str, ObjectType]]:
        """Return the (id, name, species, type) rows that pass search + filters."""
        search_text = self.search_input.text().lower().strip()

        enabled_types = set()
        if self.tree_checkbox.isChecked():
            enabled_types.add(ObjectType.TREE)
        if self.shrub_checkbox.isChecked():
            enabled_types.add(ObjectType.SHRUB)
        if self.perennial_checkbox.isChecked():
            enabled_types.add(ObjectType.PERENNIAL)

        visible: list[tuple[UUID, str, str, ObjectType]] = []
        for item_id, name, species, family, plant_type in self._all_plants:
            if plant_type not in enabled_types:
                continue
            if search_text and search_text not in f"{name} {species} {family}".lower():
                continue
            visible.append((item_id, name, species, plant_type))
        return visible

    def _update_results_display(self, *, from_user_input: bool = False) -> None:
        """Refresh the results list, rebuilding only when the visible set changed.

        The destructive ``clear()`` + recreate-every-row path discards scroll
        position and the current selection, and can tear down the row the user is
        mid-clicking. Because this is driven (debounced) by the very chatty
        ``QGraphicsScene.changed``, it fired on every repaint — including the
        spacing/companion visual churn that *selecting* a plant itself triggers.
        We now skip the rebuild entirely when the rows would be identical (#212).

        Args:
            from_user_input: True when the call comes from a search/filter edit
                (reset scroll to top); False for scene-driven refreshes (preserve
                the user's scroll position).
        """
        visible = self._visible_plants()
        signature = tuple(visible)

        # Nothing the list cares about changed → leave scroll + selection intact.
        if signature == self._rendered_signature:
            self._update_results_label(len(visible))
            return

        scrollbar = self.results_list.verticalScrollBar()
        prev_scroll = scrollbar.value()
        cur = self.results_list.currentItem()
        prev_selected_id = (
            cur.data(Qt.ItemDataRole.UserRole) if cur is not None else None
        )

        self.results_list.clear()
        for item_id, name, species, plant_type in visible:
            list_item = QListWidgetItem()
            widget = PlantListItem(item_id, name, species, plant_type)
            list_item.setSizeHint(widget.sizeHint())
            # Store only the stable item id, never a live QGraphicsItem reference:
            # the latter goes stale after undo/redo/delete and makes selection flaky
            # (issue #212). The live item is resolved at click time via
            # scene.find_item_by_id().
            list_item.setData(Qt.ItemDataRole.UserRole, item_id)

            self.results_list.addItem(list_item)
            self.results_list.setItemWidget(list_item, widget)
            if item_id == prev_selected_id:
                self.results_list.setCurrentItem(list_item)

        self._rendered_signature = signature

        # Preserve the scroll position across scene-driven rebuilds; jump back to
        # the top when the user just narrowed the results via search/filter.
        scrollbar.setValue(0 if from_user_input else min(prev_scroll, scrollbar.maximum()))

        self._update_results_label(len(visible))

    def _update_results_label(self, matching_count: int) -> None:
        """Update the results-count label for the given number of visible rows."""
        total = len(self._all_plants)
        if total == 0:
            self.results_label.setText(self.tr("No plants in project"))
        elif matching_count == total:
            self.results_label.setText(self.tr("{count} plant(s) in project").format(count=total))
        else:
            self.results_label.setText(
                self.tr("Showing {shown} of {total} plants").format(
                    shown=matching_count, total=total
                )
            )

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle single click on a plant item - select and reveal it."""
        item_id = item.data(Qt.ItemDataRole.UserRole)
        if item_id is not None:
            self._select_plant(item_id)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double click on a plant item - select and pan to it."""
        item_id = item.data(Qt.ItemDataRole.UserRole)
        if item_id is not None:
            self._select_and_pan_to_plant(item_id)

    def _select_plant(self, item_id: UUID) -> None:
        """Select the plant with *item_id* on the canvas and reveal it if off-screen.

        Args:
            item_id: The UUID of the graphics item to select
        """
        if not hasattr(self, "_scene") or self._scene is None:
            return
        # Defer the scene mutation so it runs after the QListWidget finishes its own
        # click processing (which itself triggers selectionChanged); selecting inline
        # can clear the panel mid-click. Mirrors _on_companion_highlight_species.
        QTimer.singleShot(0, lambda: self._apply_selection(item_id, pan=False))

    def _select_and_pan_to_plant(self, item_id: UUID) -> None:
        """Select the plant with *item_id* and center the view on it.

        Args:
            item_id: The UUID of the graphics item to select and pan to
        """
        if not hasattr(self, "_scene") or self._scene is None:
            return
        QTimer.singleShot(0, lambda: self._apply_selection(item_id, pan=True))

    def _apply_selection(self, item_id: UUID, *, pan: bool) -> None:
        """Resolve *item_id* against the live scene and select it.

        Looking the item up fresh (rather than trusting a stored QGraphicsItem
        reference) keeps selection reliable across undo/redo/delete (issue #212).

        Args:
            item_id: The UUID of the graphics item to select.
            pan: If True, center the view on the item; otherwise only scroll it
                into view when it is off-screen.
        """
        # The panel (or scene) may have been torn down between scheduling this
        # deferred call and it firing; touching deleted Qt C++ objects raises
        # RuntimeError. Swallow that race (same guard as the debounced refresh slot
        # in application._on_scene_changed_for_plant_search).
        with contextlib.suppress(RuntimeError):
            scene = getattr(self, "_scene", None)
            if scene is None:
                return

            graphics_item = scene.find_item_by_id(item_id)
            if graphics_item is None:
                # The item is gone (e.g. deleted/undone). Heal the list and bail.
                self.refresh_plant_list()
                return

            scene.clearSelection()
            graphics_item.setSelected(True)

            views = scene.views()
            if views:
                view = views[0]
                if pan:
                    view.centerOn(graphics_item.sceneBoundingRect().center())
                else:
                    # Scroll only when the plant is not already visible.
                    view.ensureVisible(graphics_item)

            self.plant_selected.emit(item_id)
