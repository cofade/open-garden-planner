"""Array Along Path placement dialog."""

from PyQt6.QtWidgets import (
    QComboBox,
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


class ArrayAlongPathDialog(QDialog):
    """Dialog for creating an array of items along a polyline path.

    Allows specifying count or spacing, start/end offsets, and rotation mode
    to place copies of an item evenly along a path.
    """

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Array Along Path"))
        self.setModal(True)
        self.setMinimumWidth(380)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        group = QGroupBox(self.tr("Array Parameters"))
        form = QFormLayout(group)

        # Spacing mode
        self._mode_combo = QComboBox()
        self._mode_combo.addItem(self.tr("By count"))
        self._mode_combo.addItem(self.tr("By spacing"))
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow(self.tr("Mode:"), self._mode_combo)

        # Count
        self._count_spin = QSpinBox()
        self._count_spin.setRange(2, 100)
        self._count_spin.setValue(6)
        self._count_label = QLabel(self.tr("Count:"))
        form.addRow(self._count_label, self._count_spin)

        # Spacing
        spacing_layout = QHBoxLayout()
        self._spacing_spin = QDoubleSpinBox()
        self._spacing_spin.setRange(1.0, 10000.0)
        self._spacing_spin.setValue(50.0)
        self._spacing_spin.setDecimals(1)
        self._spacing_spin.setSuffix(" cm")
        self._spacing_spin.setMinimumWidth(120)
        spacing_layout.addWidget(self._spacing_spin)
        spacing_layout.addStretch()
        self._spacing_label = QLabel(self.tr("Spacing:"))
        form.addRow(self._spacing_label, spacing_layout)

        # Start offset
        start_layout = QHBoxLayout()
        self._start_offset_spin = QDoubleSpinBox()
        self._start_offset_spin.setRange(0.0, 99.0)
        self._start_offset_spin.setValue(0.0)
        self._start_offset_spin.setDecimals(1)
        self._start_offset_spin.setSuffix(" %")
        self._start_offset_spin.setMinimumWidth(100)
        start_layout.addWidget(self._start_offset_spin)
        start_layout.addStretch()
        form.addRow(self.tr("Start Offset:"), start_layout)

        # End offset
        end_layout = QHBoxLayout()
        self._end_offset_spin = QDoubleSpinBox()
        self._end_offset_spin.setRange(0.0, 99.0)
        self._end_offset_spin.setValue(0.0)
        self._end_offset_spin.setDecimals(1)
        self._end_offset_spin.setSuffix(" %")
        self._end_offset_spin.setMinimumWidth(100)
        end_layout.addWidget(self._end_offset_spin)
        end_layout.addStretch()
        form.addRow(self.tr("End Offset:"), end_layout)

        # Rotation mode
        self._rotation_combo = QComboBox()
        self._rotation_combo.addItem(self.tr("Fixed orientation"))
        self._rotation_combo.addItem(self.tr("Follow path tangent"))
        form.addRow(self.tr("Rotation:"), self._rotation_combo)

        layout.addWidget(group)
        layout.addSpacing(4)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Initial state: "By count" mode
        self._on_mode_changed(0)

    def _on_mode_changed(self, index: int) -> None:
        by_spacing = index == 1
        self._count_spin.setVisible(not by_spacing)
        self._count_label.setVisible(not by_spacing)
        self._spacing_spin.setVisible(by_spacing)
        self._spacing_label.setVisible(by_spacing)

    @property
    def count(self) -> int:
        return self._count_spin.value()

    @property
    def spacing_cm(self) -> float:
        return self._spacing_spin.value()

    @property
    def use_spacing_mode(self) -> bool:
        return self._mode_combo.currentIndex() == 1

    @property
    def start_offset_pct(self) -> float:
        return self._start_offset_spin.value()

    @property
    def end_offset_pct(self) -> float:
        return self._end_offset_spin.value()

    @property
    def follow_tangent(self) -> bool:
        return self._rotation_combo.currentIndex() == 1
