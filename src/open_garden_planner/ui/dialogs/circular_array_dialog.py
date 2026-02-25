"""Circular Array placement dialog."""

from PyQt6.QtWidgets import (
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


class CircularArrayDialog(QDialog):
    """Dialog for creating a circular array of an object.

    Allows specifying count, radius, start angle, and sweep angle to place
    N copies of an object equally spaced around a circle.
    """

    def __init__(self, parent: object = None) -> None:
        """Initialize the Circular Array dialog."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Create Circular Array"))
        self.setModal(True)
        self.setMinimumWidth(360)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        group = QGroupBox(self.tr("Array Parameters"))
        form = QFormLayout(group)

        # Count
        self._count_spin = QSpinBox()
        self._count_spin.setRange(2, 360)
        self._count_spin.setValue(6)
        form.addRow(self.tr("Count:"), self._count_spin)

        # Radius
        radius_layout = QHBoxLayout()
        self._radius_spin = QDoubleSpinBox()
        self._radius_spin.setRange(1.0, 100000.0)
        self._radius_spin.setValue(100.0)
        self._radius_spin.setDecimals(1)
        self._radius_spin.setSuffix(" cm")
        self._radius_spin.setMinimumWidth(120)
        radius_layout.addWidget(self._radius_spin)
        radius_layout.addStretch()
        form.addRow(self.tr("Radius:"), radius_layout)

        # Start angle
        start_layout = QHBoxLayout()
        self._start_angle_spin = QDoubleSpinBox()
        self._start_angle_spin.setRange(0.0, 359.9)
        self._start_angle_spin.setValue(0.0)
        self._start_angle_spin.setDecimals(1)
        self._start_angle_spin.setSuffix("°")
        self._start_angle_spin.setWrapping(True)
        self._start_angle_spin.setMinimumWidth(100)
        start_layout.addWidget(self._start_angle_spin)
        hint = QLabel(self.tr("(0° = right, 90° = down, 180° = left, 270° = up)"))
        hint.setStyleSheet("color: palette(mid);")
        start_layout.addWidget(hint)
        start_layout.addStretch()
        form.addRow(self.tr("Start Angle:"), start_layout)

        # Sweep angle
        sweep_layout = QHBoxLayout()
        self._sweep_angle_spin = QDoubleSpinBox()
        self._sweep_angle_spin.setRange(1.0, 360.0)
        self._sweep_angle_spin.setValue(360.0)
        self._sweep_angle_spin.setDecimals(1)
        self._sweep_angle_spin.setSuffix("°")
        self._sweep_angle_spin.setMinimumWidth(100)
        sweep_layout.addWidget(self._sweep_angle_spin)
        sweep_hint = QLabel(self.tr("(360° = full circle)"))
        sweep_hint.setStyleSheet("color: palette(mid);")
        sweep_layout.addWidget(sweep_hint)
        sweep_layout.addStretch()
        form.addRow(self.tr("Sweep Angle:"), sweep_layout)

        layout.addWidget(group)
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
    def radius_cm(self) -> float:
        """Radius of the circle in centimeters."""
        return self._radius_spin.value()

    @property
    def start_angle_deg(self) -> float:
        """Start angle in degrees (0° = right, 90° = down)."""
        return self._start_angle_spin.value()

    @property
    def sweep_angle_deg(self) -> float:
        """Total sweep angle in degrees."""
        return self._sweep_angle_spin.value()
