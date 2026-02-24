"""Linear Array placement dialog."""

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


class LinearArrayDialog(QDialog):
    """Dialog for creating a linear array of an object.

    Allows specifying count, spacing, and direction to place N copies
    of an object along a line at exact intervals.
    """

    def __init__(self, parent: object = None) -> None:
        """Initialize the Linear Array dialog."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Create Linear Array"))
        self.setModal(True)
        self.setMinimumWidth(340)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        group = QGroupBox(self.tr("Array Parameters"))
        form = QFormLayout(group)

        # Count
        self._count_spin = QSpinBox()
        self._count_spin.setRange(2, 100)
        self._count_spin.setValue(3)
        form.addRow(self.tr("Count:"), self._count_spin)

        # Spacing
        spacing_layout = QHBoxLayout()
        self._spacing_spin = QDoubleSpinBox()
        self._spacing_spin.setRange(1.0, 100000.0)
        self._spacing_spin.setValue(100.0)
        self._spacing_spin.setDecimals(1)
        self._spacing_spin.setSuffix(" cm")
        self._spacing_spin.setMinimumWidth(120)
        spacing_layout.addWidget(self._spacing_spin)
        spacing_layout.addStretch()
        form.addRow(self.tr("Spacing:"), spacing_layout)

        # Direction angle
        dir_layout = QHBoxLayout()
        self._angle_spin = QDoubleSpinBox()
        self._angle_spin.setRange(0.0, 359.9)
        self._angle_spin.setValue(0.0)
        self._angle_spin.setDecimals(1)
        self._angle_spin.setSuffix("°")
        self._angle_spin.setWrapping(True)
        self._angle_spin.setMinimumWidth(100)
        dir_layout.addWidget(self._angle_spin)
        hint = QLabel(self.tr("(0° = right, 90° = down, 180° = left, 270° = up)"))
        hint.setStyleSheet("color: palette(mid);")
        dir_layout.addWidget(hint)
        dir_layout.addStretch()
        form.addRow(self.tr("Direction:"), dir_layout)

        layout.addWidget(group)

        # Optional distance constraints
        self._constraints_check = QCheckBox(
            self.tr("Auto-create distance constraints between copies")
        )
        layout.addWidget(self._constraints_check)

        layout.addSpacing(4)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    @property
    def count(self) -> int:
        """Total number of objects (including the original)."""
        return self._count_spin.value()

    @property
    def spacing_cm(self) -> float:
        """Spacing between copies in centimeters."""
        return self._spacing_spin.value()

    @property
    def angle_deg(self) -> float:
        """Direction angle in degrees (0° = right, 90° = down)."""
        return self._angle_spin.value()

    @property
    def create_constraints(self) -> bool:
        """Whether to auto-create distance constraints between copies."""
        return self._constraints_check.isChecked()
