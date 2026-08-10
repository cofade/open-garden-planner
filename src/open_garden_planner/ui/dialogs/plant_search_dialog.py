"""Plant search dialog for finding species from online databases."""

import logging
from dataclasses import replace

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services.plant_api import PlantAPIError, PlantAPIManager
from open_garden_planner.ui.theme import set_text_role, theme_color

logger = logging.getLogger(__name__)


class PlantSearchDialog(QDialog):
    """Dialog for searching plant species from online databases.

    Allows users to search for plants using the PlantAPIManager,
    which automatically tries multiple APIs with fallback.
    """

    def __init__(
        self,
        api_manager: PlantAPIManager,
        parent: object = None,
    ) -> None:
        """Initialize the plant search dialog.

        Args:
            api_manager: PlantAPIManager instance for searching
            parent: Parent widget
        """
        super().__init__(parent)

        self._api_manager = api_manager
        self._selected_plant: PlantSpeciesData | None = None
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._perform_search)

        self.setWindowTitle(self.tr("Search Plant Species"))
        self.setModal(True)
        self.setMinimumSize(700, 500)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Search input area
        search_layout = QHBoxLayout()
        search_label = QLabel(self.tr("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Enter plant common or scientific name..."))
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._perform_search)

        self.search_button = QPushButton(self.tr("Search"))
        self.search_button.clicked.connect(self._perform_search)

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        layout.addLayout(search_layout)

        # Status/info label
        self.status_label = QLabel(self.tr("Enter a plant name to search"))
        self.status_label.setStyleSheet(f"color: {theme_color('text_secondary')};")
        layout.addWidget(self.status_label)

        # Main content area
        content_layout = QHBoxLayout()

        # Left side: Search results list
        results_layout = QVBoxLayout()
        results_label = QLabel(self.tr("Results:"))
        set_text_role(results_label, "h2")
        self.results_list = QListWidget()
        self.results_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        results_layout.addWidget(results_label)
        results_layout.addWidget(self.results_list)

        # Right side: Plant details
        details_layout = QVBoxLayout()
        details_label = QLabel(self.tr("Plant Details:"))
        set_text_role(details_label, "h2")
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setPlaceholderText(self.tr("Select a plant to view details"))
        details_layout.addWidget(details_label)
        details_layout.addWidget(self.details_text)

        content_layout.addLayout(results_layout, 2)  # 40% width
        content_layout.addLayout(details_layout, 3)  # 60% width
        layout.addLayout(content_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)  # Disabled until a plant is selected

        # Focus on search input
        self.search_input.setFocus()

    def _on_search_text_changed(self, text: str) -> None:
        """Handle search text changes with debouncing.

        Args:
            text: New search text
        """
        # Debounce: wait 500ms after user stops typing before searching
        self._search_timer.stop()
        if text.strip():
            self._search_timer.start(500)
        else:
            self.results_list.clear()
            self.status_label.setText(self.tr("Enter a plant name to search"))
            self.status_label.setStyleSheet(f"color: {theme_color('text_secondary')};")

    def _perform_search(self) -> None:
        """Perform plant search using the API manager."""
        query = self.search_input.text().strip()
        if not query:
            return

        # Clear previous results
        self.results_list.clear()
        self.details_text.clear()
        self.ok_button.setEnabled(False)
        self._selected_plant = None

        # Show searching status
        self.status_label.setText(self.tr("Searching for '{query}'...").format(query=query))
        self.status_label.setStyleSheet(f"color: {theme_color('info')};")
        self.search_button.setEnabled(False)

        try:
            # Search using API manager (with automatic fallback)
            results = self._api_manager.search(query, limit=20)

            if results:
                # Populate results list
                for plant_data in results:
                    item = QListWidgetItem(
                        f"{plant_data.common_name} ({plant_data.scientific_name})"
                    )
                    item.setData(Qt.ItemDataRole.UserRole, plant_data)
                    self.results_list.addItem(item)

                self.status_label.setText(self.tr("Found {count} results").format(count=len(results)))
                self.status_label.setStyleSheet(f"color: {theme_color('success')};")
            else:
                self.status_label.setText(self.tr("No results found"))
                self.status_label.setStyleSheet(f"color: {theme_color('warning')};")

        except PlantAPIError as e:
            self.status_label.setText(self.tr("Search failed: {error}").format(error=str(e)))
            self.status_label.setStyleSheet(f"color: {theme_color('error')};")
            logger.error(f"Plant search failed: {e}")

            # Show error dialog
            QMessageBox.warning(
                self,
                self.tr("Search Failed"),
                self.tr("Failed to search plant database:\n{error}\n\n"
                "Please check your internet connection and API credentials.").format(error=str(e)),
            )

        finally:
            self.search_button.setEnabled(True)

    def _on_selection_changed(self) -> None:
        """Handle result selection change."""
        selected_items = self.results_list.selectedItems()
        if not selected_items:
            self.details_text.clear()
            self.ok_button.setEnabled(False)
            self._selected_plant = None
            return

        # Get plant data from selected item
        item = selected_items[0]
        plant_data: PlantSpeciesData = item.data(Qt.ItemDataRole.UserRole)
        self._selected_plant = plant_data
        self.ok_button.setEnabled(True)

        # Display plant details
        self._display_plant_details(plant_data)

    def _display_plant_details(self, plant: PlantSpeciesData) -> None:
        """Display detailed information about a plant.

        Args:
            plant: Plant species data to display
        """
        html = "<html><body style='font-family: sans-serif;'>"

        # Title
        html += f"<h2>{plant.common_name}</h2>"
        html += f"<p><i>{plant.scientific_name}</i></p>"

        if plant.description:
            html += f"<p>{plant.description}</p>"

        html += "<hr>"

        # Botanical info
        if plant.family or plant.genus:
            html += f"<h3>{self.tr('Botanical Classification')}</h3><ul>"
            if plant.family:
                html += f"<li><b>{self.tr('Family:')}</b> {plant.family}</li>"
            if plant.genus:
                html += f"<li><b>{self.tr('Genus:')}</b> {plant.genus}</li>"
            html += "</ul>"

        # Growing requirements
        _cycle_names = {
            "unknown": self.tr("Unknown"),
            "annual": self.tr("Annual"),
            "biennial": self.tr("Biennial"),
            "perennial": self.tr("Perennial"),
        }
        _sun_names = {
            "unknown": self.tr("Unknown"),
            "full_sun": self.tr("Full Sun"),
            "partial_sun": self.tr("Partial Sun"),
            "partial_shade": self.tr("Partial Shade"),
            "full_shade": self.tr("Full Shade"),
        }
        _water_names = {
            "unknown": self.tr("Unknown"),
            "low": self.tr("Low"),
            "medium": self.tr("Medium"),
            "high": self.tr("High"),
        }
        html += f"<h3>{self.tr('Growing Requirements')}</h3><ul>"
        html += f"<li><b>{self.tr('Cycle:')}</b> {_cycle_names.get(plant.cycle.value, plant.cycle.value)}</li>"
        html += f"<li><b>{self.tr('Sun:')}</b> {_sun_names.get(plant.sun_requirement.value, plant.sun_requirement.value)}</li>"
        html += f"<li><b>{self.tr('Water:')}</b> {_water_names.get(plant.water_needs.value, plant.water_needs.value)}</li>"

        if plant.hardiness_zone_min and plant.hardiness_zone_max:
            html += f"<li><b>{self.tr('Hardiness Zones:')}</b> {plant.hardiness_zone_min}-{plant.hardiness_zone_max}</li>"
        elif plant.hardiness_zone_min:
            html += f"<li><b>{self.tr('Hardiness Zone:')}</b> {plant.hardiness_zone_min}</li>"

        if plant.soil_type:
            html += f"<li><b>{self.tr('Soil:')}</b> {plant.soil_type}</li>"

        html += "</ul>"

        # Size info
        if plant.max_height_cm or plant.max_spread_cm:
            html += f"<h3>{self.tr('Size')}</h3><ul>"
            if plant.max_height_cm:
                height_m = plant.max_height_cm / 100
                html += f"<li><b>{self.tr('Max Height:')}</b> {height_m:.1f} m</li>"
            if plant.max_spread_cm:
                spread_m = plant.max_spread_cm / 100
                html += f"<li><b>{self.tr('Max Spread:')}</b> {spread_m:.1f} m</li>"
            html += "</ul>"

        # Additional attributes
        if plant.edible or plant.flowering or plant.flower_color:
            html += f"<h3>{self.tr('Attributes')}</h3><ul>"
            if plant.edible:
                html += f"<li><b>{self.tr('Edible:')}</b> {self.tr('Yes')}"
                if plant.edible_parts:
                    html += f" ({', '.join(plant.edible_parts)})"
                html += "</li>"
            if plant.flowering:
                html += f"<li><b>{self.tr('Flowering:')}</b> {self.tr('Yes')}"
                if plant.flower_color:
                    html += f" ({plant.flower_color})"
                html += "</li>"
            html += "</ul>"

        # Data source
        html += "<hr><p style='opacity: 0.6; font-size: small;'>"
        html += self.tr("Source: {source}").format(source=plant.data_source.title())
        if plant.source_id:
            html += f" (ID: {plant.source_id})"
        html += "</p>"

        html += "</body></html>"

        self.details_text.setHtml(html)

    def _on_result_double_clicked(self, _item: QListWidgetItem) -> None:
        """Handle double-click on a result (accept immediately).

        Args:
            _item: Clicked list item (unused)
        """
        self._on_accept()

    def _on_accept(self) -> None:
        """Handle OK button click."""
        # Stop the pending 500ms search-debounce timer FIRST. _enrich_selected_plant()
        # can open a modal QMessageBox on a failed fetch, and a modal spins its own
        # nested Qt event loop in which a still-pending timer WILL fire -- calling
        # _perform_search(), which nulls self._selected_plant and re-populates the
        # results list out from under this method, right before `accept()` commits
        # whatever selection is left. Same failure class as the #210 debounce/flush
        # incident (docs/11-risks-and-technical-debt/README.md §11.4): a pending
        # debounced action must be settled before anything destructive commits.
        self._search_timer.stop()

        if self._selected_plant is None:
            QMessageBox.warning(
                self,
                self.tr("No Selection"),
                self.tr("Please select a plant from the search results."),
            )
            return

        self._enrich_selected_plant()
        self.accept()

    def _enrich_selected_plant(self) -> None:
        """Fetch the full per-species detail record for the confirmed plant.

        Search results are sparse for most providers -- Trefle's
        `/plants/search` in particular carries only identity/taxonomy fields
        and omits `growth`/`specifications`/`foliage` entirely, so
        sun/water/pH/nutrient/foliage stay UNKNOWN on the search-result object
        no matter how correct `_parse_species()` is (issue #297). The richer
        data only exists behind `get_by_id()`. Runs once, on confirm rather
        than per browsed result, to keep this to one extra request instead of
        one per visible row (Trefle/Permapeople rate-limit concern raised in
        #297) -- and skipped for locally-stored custom plants, which have no
        online detail endpoint and are already complete.
        """
        plant = self._selected_plant
        if plant is None or plant.data_source == "custom" or not plant.source_id:
            return

        # setCursor (not a button disable) is the only user-visible feedback
        # this can give: get_by_id() is a synchronous, blocking call on the
        # GUI thread, so no Qt events -- including a repaint of a disabled
        # button -- are processed until it returns. The cursor still changes
        # immediately (an OS-level property, not something that needs a
        # paint event), matching the working precedent in
        # connect_ai_assistant_dialog.py / preferences_dialog.py.
        self.setCursor(Qt.CursorShape.WaitCursor)
        error: Exception | None = None
        try:
            detail = self._api_manager.get_by_id(plant.source_id, plant.data_source)
        except Exception as e:  # noqa: BLE001 -- external API trust boundary. Only
            # PlantAPIError is documented, but a 200 response with an unexpected
            # shape reaches _parse_species() uncaught here (unlike search(), which
            # already wraps per-item parsing in `except Exception` -- manager.py).
            # Losing the user's confirmed selection to an unhandled crash would be
            # worse than falling back to the sparse search result.
            detail = None
            error = e
        finally:
            self.unsetCursor()

        if error is not None or detail is None:
            logger.warning(
                f"Failed to fetch full details for {plant.common_name} "
                f"({plant.data_source}#{plant.source_id}), using search result as-is: {error}"
            )
            self._warn_enrichment_failed(plant)
            return

        # A "successful" response can still be empty, truncated, or describe a
        # different record than the one requested. Validate identity via
        # source_id (the contract PlantAPIClient.get_by_id() documents: the
        # returned record's source_id equals the id requested) before
        # replacing a known-good sparse result with it. Deliberately NOT also
        # rejecting an empty/"Unknown" common_name here: Trefle genuinely omits
        # common_name for many real (scientific-name-only) species, and
        # rejecting on that basis would throw away a fully-populated,
        # correctly-identified detail record for exactly the plants this fix
        # exists to help.
        if detail.source_id != plant.source_id:
            logger.warning(
                f"Detail fetch for {plant.common_name} ({plant.data_source}#{plant.source_id}) "
                "returned an unexpected or empty record, using search result as-is"
            )
            self._warn_enrichment_failed(plant)
            return

        self._selected_plant = self._merge_detail_into_search_result(plant, detail)

    @staticmethod
    def _merge_detail_into_search_result(
        plant: PlantSpeciesData, detail: PlantSpeciesData
    ) -> PlantSpeciesData:
        """Overlay `detail`'s enrichment fields onto `plant`, not the other way
        around -- a wholesale swap silently destroyed `common_name`/`family`/
        `genus`/`image_url` whenever the detail response validly omitted them
        (caught in senior review round 3, reproduced against this method's own
        null-common_name test fixture). The detail record and the search
        record are not guaranteed to be a superset/subset of each other, only
        to describe the same plant (already validated by the source_id check
        above) -- so identity fields keep the search result's value unless
        the detail response actually improves on it.
        """
        return replace(
            detail,
            common_name=(
                detail.common_name
                if detail.common_name not in ("", "Unknown")
                else plant.common_name
            ),
            scientific_name=(
                detail.scientific_name
                if detail.scientific_name not in ("", "Unknown")
                else plant.scientific_name
            ),
            family=detail.family or plant.family,
            genus=detail.genus or plant.genus,
            image_url=detail.image_url or plant.image_url,
            thumbnail_url=detail.thumbnail_url or plant.thumbnail_url,
        )

    def _warn_enrichment_failed(self, plant: PlantSpeciesData) -> None:
        """Tell the user their selection will use only the basic search data.

        A silent fallback would reproduce #297's exact symptom (sun/water/pH/
        foliage stuck at UNKNOWN) with no indication anything went wrong.
        """
        QMessageBox.warning(
            self,
            self.tr("Limited Plant Data"),
            self.tr(
                "Could not load full details for {name} from {source}. "
                "The plant will be added with basic information only "
                "(sun, water, pH, and foliage data may be missing)."
            ).format(name=plant.common_name, source=plant.data_source.title()),
        )

    @property
    def selected_plant(self) -> PlantSpeciesData | None:
        """Get the selected plant species data.

        Returns:
            Selected plant data, or None if dialog was cancelled
        """
        return self._selected_plant
