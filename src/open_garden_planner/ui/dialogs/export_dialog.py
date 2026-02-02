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

    Allows the user to select output size and DPI (resolution) for the exported image
    and shows a preview of the output dimensions and scale.
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
        self._selected_output_width_cm = ExportService.PAPER_A4_LANDSCAPE_WIDTH_CM

        self.setWindowTitle("Export as PNG")
        self.setModal(True)
        self.setMinimumWidth(450)

        self._setup_ui()
        self._update_preview()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Output size group
        size_group = QGroupBox("Output Size")
        size_layout = QVBoxLayout(size_group)

        self._size_button_group = QButtonGroup(self)

        # A4 landscape option (default)
        self._a4_radio = QRadioButton("A4 Landscape (29.7 cm wide)")
        self._a4_radio.setToolTip("Standard A4 paper in landscape orientation")
        self._a4_radio.setChecked(True)
        self._size_button_group.addButton(
            self._a4_radio, int(ExportService.PAPER_A4_LANDSCAPE_WIDTH_CM * 10)
        )
        size_layout.addWidget(self._a4_radio)

        # A3 landscape option
        self._a3_radio = QRadioButton("A3 Landscape (42.0 cm wide)")
        self._a3_radio.setToolTip("A3 paper in landscape orientation (larger)")
        self._size_button_group.addButton(
            self._a3_radio, int(ExportService.PAPER_A3_LANDSCAPE_WIDTH_CM * 10)
        )
        size_layout.addWidget(self._a3_radio)

        # Letter landscape option
        self._letter_radio = QRadioButton("Letter Landscape (27.9 cm wide)")
        self._letter_radio.setToolTip("US Letter paper in landscape orientation")
        self._size_button_group.addButton(
            self._letter_radio, int(ExportService.PAPER_LETTER_LANDSCAPE_WIDTH_CM * 10)
        )
        size_layout.addWidget(self._letter_radio)

        # Connect signal for preview updates
        self._size_button_group.idClicked.connect(self._on_size_changed)

        layout.addWidget(size_group)

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

        # Scale ratio
        self._scale_label = QLabel()
        self._scale_label.setStyleSheet("color: gray;")
        preview_layout.addWidget(self._scale_label)

        # Output dimensions
        self._dimensions_label = QLabel()
        preview_layout.addWidget(self._dimensions_label)

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

    def _on_size_changed(self, size_id: int) -> None:
        """Handle output size selection change.

        Args:
            size_id: Selected size ID (width * 10)
        """
        self._selected_output_width_cm = size_id / 10.0
        self._update_preview()

    def _on_dpi_changed(self, dpi: int) -> None:
        """Handle DPI selection change.

        Args:
            dpi: Selected DPI value
        """
        self._selected_dpi = dpi
        self._update_preview()

    def _update_preview(self) -> None:
        """Update the preview labels with current settings."""
        # Calculate scale
        scale_ratio = ExportService.calculate_scale(
            self._canvas_width_cm, self._selected_output_width_cm
        )
        scale_denominator = int(1 / scale_ratio)
        self._scale_label.setText(f"Scale: 1:{scale_denominator}")

        # Calculate image size
        width_px, height_px = ExportService.calculate_image_size(
            self._canvas_width_cm,
            self._canvas_height_cm,
            self._selected_output_width_cm,
            self._selected_dpi,
        )

        self._dimensions_label.setText(
            f"<b>Image size: {width_px:,} × {height_px:,} pixels</b>"
        )

    @property
    def selected_dpi(self) -> int:
        """Get the selected DPI value."""
        return self._selected_dpi

    @property
    def selected_output_width_cm(self) -> float:
        """Get the selected output width in centimeters."""
        return self._selected_output_width_cm
