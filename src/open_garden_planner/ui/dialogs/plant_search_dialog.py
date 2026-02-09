"""Plant search dialog for finding species from online databases."""

import logging

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
        self.status_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.status_label)

        # Main content area
        content_layout = QHBoxLayout()

        # Left side: Search results list
        results_layout = QVBoxLayout()
        results_label = QLabel(self.tr("Results:"))
        results_label.setStyleSheet("font-weight: bold;")
        self.results_list = QListWidget()
        self.results_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        results_layout.addWidget(results_label)
        results_layout.addWidget(self.results_list)

        # Right side: Plant details
        details_layout = QVBoxLayout()
        details_label = QLabel(self.tr("Plant Details:"))
        details_label.setStyleSheet("font-weight: bold;")
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
            self.status_label.setStyleSheet("color: palette(mid);")

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
        self.status_label.setStyleSheet("color: blue;")
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
                self.status_label.setStyleSheet("color: green;")
            else:
                self.status_label.setText(self.tr("No results found"))
                self.status_label.setStyleSheet("color: orange;")

        except PlantAPIError as e:
            self.status_label.setText(self.tr("Search failed: {error}").format(error=str(e)))
            self.status_label.setStyleSheet("color: red;")
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
        html += f"<h3>{self.tr('Growing Requirements')}</h3><ul>"
        html += f"<li><b>{self.tr('Cycle:')}</b> {plant.cycle.value.replace('_', ' ').title()}</li>"
        html += f"<li><b>{self.tr('Sun:')}</b> {plant.sun_requirement.value.replace('_', ' ').title()}</li>"
        html += f"<li><b>{self.tr('Water:')}</b> {plant.water_needs.value.title()}</li>"

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
        html += "<hr><p style='color: palette(mid); font-size: small;'>"
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
        if self._selected_plant is None:
            QMessageBox.warning(
                self,
                self.tr("No Selection"),
                self.tr("Please select a plant from the search results."),
            )
            return

        self.accept()

    @property
    def selected_plant(self) -> PlantSpeciesData | None:
        """Get the selected plant species data.

        Returns:
            Selected plant data, or None if dialog was cancelled
        """
        return self._selected_plant
