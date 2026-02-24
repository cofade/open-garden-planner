"""Grid Array placement dialog."""

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


class GridArrayDialog(QDialog):
    """Dialog for creating a rectangular grid array of an object.

    Allows specifying rows, columns, row spacing, and column spacing
    to place copies in a 2-D grid at exact intervals.
    """

    def __init__(self, parent: object = None) -> None:
        """Initialize the Grid Array dialog."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Create Grid Array"))
        self.setModal(True)
        self.setMinimumWidth(360)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        group = QGroupBox(self.tr("Grid Parameters"))
        form = QFormLayout(group)

        # Rows
        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, 100)
        self._rows_spin.setValue(3)
        form.addRow(self.tr("Rows:"), self._rows_spin)

        # Columns
        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(1, 100)
        self._cols_spin.setValue(3)
        form.addRow(self.tr("Columns:"), self._cols_spin)

        # Row spacing
        row_spacing_layout = QHBoxLayout()
        self._row_spacing_spin = QDoubleSpinBox()
        self._row_spacing_spin.setRange(1.0, 100000.0)
        self._row_spacing_spin.setValue(100.0)
        self._row_spacing_spin.setDecimals(1)
        self._row_spacing_spin.setSuffix(" cm")
        self._row_spacing_spin.setMinimumWidth(120)
        row_spacing_layout.addWidget(self._row_spacing_spin)
        row_spacing_hint = QLabel(self.tr("(downward)"))
        row_spacing_hint.setStyleSheet("color: palette(mid);")
        row_spacing_layout.addWidget(row_spacing_hint)
        row_spacing_layout.addStretch()
        form.addRow(self.tr("Row spacing:"), row_spacing_layout)

        # Column spacing
        col_spacing_layout = QHBoxLayout()
        self._col_spacing_spin = QDoubleSpinBox()
        self._col_spacing_spin.setRange(1.0, 100000.0)
        self._col_spacing_spin.setValue(100.0)
        self._col_spacing_spin.setDecimals(1)
        self._col_spacing_spin.setSuffix(" cm")
        self._col_spacing_spin.setMinimumWidth(120)
        col_spacing_layout.addWidget(self._col_spacing_spin)
        col_spacing_hint = QLabel(self.tr("(rightward)"))
        col_spacing_hint.setStyleSheet("color: palette(mid);")
        col_spacing_layout.addWidget(col_spacing_hint)
        col_spacing_layout.addStretch()
        form.addRow(self.tr("Column spacing:"), col_spacing_layout)

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
    def rows(self) -> int:
        """Number of rows in the grid."""
        return self._rows_spin.value()

    @property
    def cols(self) -> int:
        """Number of columns in the grid."""
        return self._cols_spin.value()

    @property
    def row_spacing_cm(self) -> float:
        """Spacing between rows in centimeters (downward)."""
        return self._row_spacing_spin.value()

    @property
    def col_spacing_cm(self) -> float:
        """Spacing between columns in centimeters (rightward)."""
        return self._col_spacing_spin.value()

    @property
    def create_constraints(self) -> bool:
        """Whether to auto-create distance constraints between adjacent copies."""
        return self._constraints_check.isChecked()
