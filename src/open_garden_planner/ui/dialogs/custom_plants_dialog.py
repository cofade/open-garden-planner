"""Dialog for managing custom plant species."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services import get_plant_library


class CustomPlantsDialog(QDialog):
    """Dialog for viewing and managing custom plant species.

    Allows users to view, edit, and delete plants in their custom library.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the custom plants dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Manage Custom Plants")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        self._library = get_plant_library()
        self._selected_plant: PlantSpeciesData | None = None
        self._selected_plant_id: str | None = None

        self._setup_ui()
        self._load_plants()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("Custom Plant Library")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Plants you've created or customized are stored here. "
            "These are available across all your projects."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray;")
        layout.addWidget(desc)

        # Table for plant list
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Common Name", "Scientific Name", "Family", "Cycle", "ID"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        # Make columns resize properly
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        # Hide the ID column (we use it internally)
        self.table.setColumnHidden(4, True)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        # Create New button
        self.new_btn = QPushButton("Create New")
        self.new_btn.setToolTip("Create a new custom plant species")
        self.new_btn.clicked.connect(self._on_create_new)
        button_layout.addWidget(self.new_btn)

        button_layout.addStretch()

        # Delete button
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setToolTip("Delete the selected plant")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete)
        button_layout.addWidget(self.delete_btn)

        layout.addLayout(button_layout)

        # Info label
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.info_label)

        # Dialog buttons
        dialog_buttons = QHBoxLayout()
        dialog_buttons.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        dialog_buttons.addWidget(close_btn)

        layout.addLayout(dialog_buttons)

    def _load_plants(self) -> None:
        """Load plants from the library into the table."""
        self.table.setRowCount(0)
        plants = self._library.get_all_plants()

        for plant_id, plant in plants:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Common Name
            common_item = QTableWidgetItem(plant.common_name or "")
            self.table.setItem(row, 0, common_item)

            # Scientific Name
            sci_item = QTableWidgetItem(plant.scientific_name or "")
            sci_item.setData(Qt.ItemDataRole.FontRole, None)
            font = sci_item.font()
            font.setItalic(True)
            sci_item.setFont(font)
            self.table.setItem(row, 1, sci_item)

            # Family
            family_item = QTableWidgetItem(plant.family or "")
            self.table.setItem(row, 2, family_item)

            # Cycle
            cycle_text = plant.cycle.value.replace("_", " ").title()
            if cycle_text == "Unknown":
                cycle_text = ""
            cycle_item = QTableWidgetItem(cycle_text)
            self.table.setItem(row, 3, cycle_item)

            # ID (hidden column)
            id_item = QTableWidgetItem(plant_id)
            self.table.setItem(row, 4, id_item)

        # Update info label
        count = len(plants)
        if count == 0:
            self.info_label.setText("No custom plants yet. Click 'Create New' to add one.")
        else:
            self.info_label.setText(f"{count} custom plant{'s' if count != 1 else ''} in library")

    def _on_selection_changed(self) -> None:
        """Handle selection change in the table."""
        selected_rows = self.table.selectedItems()
        if selected_rows:
            row = self.table.currentRow()
            plant_id = self.table.item(row, 4).text()
            self._selected_plant_id = plant_id
            self._selected_plant = self._library.get_plant(plant_id)
            self.delete_btn.setEnabled(True)
        else:
            self._selected_plant = None
            self._selected_plant_id = None
            self.delete_btn.setEnabled(False)

    def _on_create_new(self) -> None:
        """Create a new custom plant."""
        # Create a new plant with default values
        new_plant = PlantSpeciesData(
            scientific_name="New Species",
            common_name="New Plant",
            data_source="custom",
        )

        # Add to library
        plant_id = self._library.add_plant(new_plant)

        # Reload table and select the new plant
        self._load_plants()

        # Find and select the new row
        for row in range(self.table.rowCount()):
            if self.table.item(row, 4).text() == plant_id:
                self.table.selectRow(row)
                break

        self.info_label.setText("New plant created. Edit it in the Plant Details panel.")

    def _on_delete(self) -> None:
        """Delete the selected plant."""
        if not self._selected_plant_id or not self._selected_plant:
            return

        # Confirm deletion
        result = QMessageBox.question(
            self,
            "Delete Plant",
            f"Are you sure you want to delete '{self._selected_plant.common_name}'?\n\n"
            "This will remove it from your custom library. "
            "Plants already placed in projects will keep their data.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            self._library.remove_plant(self._selected_plant_id)
            self._selected_plant = None
            self._selected_plant_id = None
            self._load_plants()

    @property
    def selected_plant(self) -> PlantSpeciesData | None:
        """Get the currently selected plant.

        Returns:
            The selected plant data, or None if no selection
        """
        return self._selected_plant

    @property
    def selected_plant_id(self) -> str | None:
        """Get the ID of the currently selected plant.

        Returns:
            The plant ID, or None if no selection
        """
        return self._selected_plant_id
