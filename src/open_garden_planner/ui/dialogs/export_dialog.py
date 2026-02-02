"""Export dialog for configuring PNG export options."""

from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from open_garden_planner.services.export_service import ExportService


class ExportPngDialog(QDialog):
    """Dialog for configuring PNG export settings.

    Allows the user to select DPI (resolution) for the exported image
    and shows a preview of the output dimensions.
    """

    def __init__(
        self,
        canvas_width_cm: float,
        canvas_height_cm: float,
        parent: object = None,
    ) -> None:
        """Initialize the Export PNG dialog.

        Args:
            canvas_width_cm: Canvas width in centimeters
            canvas_height_cm: Canvas height in centimeters
            parent: Parent widget
        """
        super().__init__(parent)

        self._canvas_width_cm = canvas_width_cm
        self._canvas_height_cm = canvas_height_cm
        self._selected_dpi = ExportService.DPI_PRINT  # Default to 150 DPI

        self.setWindowTitle("Export as PNG")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._setup_ui()
        self._update_preview()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Resolution group
        resolution_group = QGroupBox("Resolution (DPI)")
        resolution_layout = QVBoxLayout(resolution_group)

        self._dpi_button_group = QButtonGroup(self)

        # 72 DPI option
        self._dpi_72_radio = QRadioButton("72 DPI (Screen)")
        self._dpi_72_radio.setToolTip("Best for on-screen viewing, smallest file size")
        self._dpi_button_group.addButton(self._dpi_72_radio, ExportService.DPI_SCREEN)
        resolution_layout.addWidget(self._dpi_72_radio)

        # 150 DPI option (default)
        self._dpi_150_radio = QRadioButton("150 DPI (Standard Print)")
        self._dpi_150_radio.setToolTip("Good balance of quality and file size")
        self._dpi_150_radio.setChecked(True)
        self._dpi_button_group.addButton(self._dpi_150_radio, ExportService.DPI_PRINT)
        resolution_layout.addWidget(self._dpi_150_radio)

        # 300 DPI option
        self._dpi_300_radio = QRadioButton("300 DPI (High Quality)")
        self._dpi_300_radio.setToolTip("Best for high-quality printing, largest file size")
        self._dpi_button_group.addButton(self._dpi_300_radio, ExportService.DPI_HIGH)
        resolution_layout.addWidget(self._dpi_300_radio)

        # Connect signal for preview updates
        self._dpi_button_group.idClicked.connect(self._on_dpi_changed)

        layout.addWidget(resolution_group)

        # Preview group
        preview_group = QGroupBox("Output Preview")
        preview_layout = QVBoxLayout(preview_group)

        # Canvas size info
        canvas_info = QLabel(
            f"Canvas size: {self._canvas_width_cm / 100:.1f} × "
            f"{self._canvas_height_cm / 100:.1f} m"
        )
        canvas_info.setStyleSheet("color: gray;")
        preview_layout.addWidget(canvas_info)

        # Output dimensions
        self._dimensions_label = QLabel()
        preview_layout.addWidget(self._dimensions_label)

        # Estimated file size
        self._filesize_label = QLabel()
        self._filesize_label.setStyleSheet("color: gray;")
        preview_layout.addWidget(self._filesize_label)

        layout.addWidget(preview_group)

        # Add spacing
        layout.addSpacing(10)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_dpi_changed(self, dpi: int) -> None:
        """Handle DPI selection change.

        Args:
            dpi: Selected DPI value
        """
        self._selected_dpi = dpi
        self._update_preview()

    def _update_preview(self) -> None:
        """Update the preview labels with current settings."""
        width_px, height_px = ExportService.calculate_image_size(
            self._canvas_width_cm,
            self._canvas_height_cm,
            self._selected_dpi,
        )

        self._dimensions_label.setText(
            f"<b>Image size: {width_px:,} × {height_px:,} pixels</b>"
        )

        estimated_mb = ExportService.estimate_file_size_mb(width_px, height_px)
        if estimated_mb < 1:
            size_text = f"Estimated file size: ~{estimated_mb * 1024:.0f} KB"
        else:
            size_text = f"Estimated file size: ~{estimated_mb:.1f} MB"
        self._filesize_label.setText(size_text)

    @property
    def selected_dpi(self) -> int:
        """Get the selected DPI value."""
        return self._selected_dpi
