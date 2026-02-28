"""New Project dialog for creating projects with specified dimensions."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)


class NewProjectDialog(QDialog):
    """Dialog for creating a new project with specified canvas dimensions.

    Allows the user to specify width and height in meters, which are
    converted to centimeters for internal use.
    """

    # Default canvas size in meters
    DEFAULT_WIDTH_M = 50.0
    DEFAULT_HEIGHT_M = 30.0

    # Limits in meters
    MIN_SIZE_M = 1.0
    MAX_SIZE_M = 1000.0

    def __init__(self, parent: object = None) -> None:
        """Initialize the New Project dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.setWindowTitle(self.tr("New Project"))
        self.setModal(True)
        self.setMinimumWidth(350)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Canvas dimensions group
        dimensions_group = QGroupBox(self.tr("Canvas Dimensions"))
        dimensions_layout = QFormLayout(dimensions_group)

        # Width input
        width_layout = QHBoxLayout()
        self.width_spinbox = QDoubleSpinBox()
        self.width_spinbox.setRange(self.MIN_SIZE_M, self.MAX_SIZE_M)
        self.width_spinbox.setValue(self.DEFAULT_WIDTH_M)
        self.width_spinbox.setDecimals(1)
        self.width_spinbox.setSuffix(" m")
        self.width_spinbox.setMinimumWidth(120)
        width_layout.addWidget(self.width_spinbox)
        width_layout.addStretch()
        dimensions_layout.addRow(self.tr("Width:"), width_layout)

        # Height input
        height_layout = QHBoxLayout()
        self.height_spinbox = QDoubleSpinBox()
        self.height_spinbox.setRange(self.MIN_SIZE_M, self.MAX_SIZE_M)
        self.height_spinbox.setValue(self.DEFAULT_HEIGHT_M)
        self.height_spinbox.setDecimals(1)
        self.height_spinbox.setSuffix(" m")
        self.height_spinbox.setMinimumWidth(120)
        height_layout.addWidget(self.height_spinbox)
        height_layout.addStretch()
        dimensions_layout.addRow(self.tr("Height:"), height_layout)

        layout.addWidget(dimensions_group)

        # Info label
        info_label = QLabel(
            self.tr("Tip: You can resize the canvas later from Edit > Canvas Size.")
        )
        info_label.setProperty("secondary", True)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        # Add some spacing
        layout.addSpacing(10)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    @property
    def width_cm(self) -> float:
        """Get the canvas width in centimeters."""
        return self.width_spinbox.value() * 100.0

    @property
    def height_cm(self) -> float:
        """Get the canvas height in centimeters."""
        return self.height_spinbox.value() * 100.0

    @property
    def width_m(self) -> float:
        """Get the canvas width in meters."""
        return self.width_spinbox.value()

    @property
    def height_m(self) -> float:
        """Get the canvas height in meters."""
        return self.height_spinbox.value()

    def set_dimensions_m(self, width_m: float, height_m: float) -> None:
        """Set the canvas dimensions in meters.

        Args:
            width_m: Width in meters
            height_m: Height in meters
        """
        self.width_spinbox.setValue(width_m)
        self.height_spinbox.setValue(height_m)

    def set_dimensions_cm(self, width_cm: float, height_cm: float) -> None:
        """Set the canvas dimensions in centimeters.

        Args:
            width_cm: Width in centimeters
            height_cm: Height in centimeters
        """
        self.width_spinbox.setValue(width_cm / 100.0)
        self.height_spinbox.setValue(height_cm / 100.0)
