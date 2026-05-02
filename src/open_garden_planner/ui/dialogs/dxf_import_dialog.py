"""DXF import dialog with layer selection and scale factor."""

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class DxfImportDialog(QDialog):
    """Dialog for configuring DXF import options.

    Allows the user to choose a scale factor and which DXF layers to import.
    """

    def __init__(
        self,
        file_path: Path | str,
        parent: object = None,
    ) -> None:
        super().__init__(parent)
        self._file_path = Path(file_path)
        self._layer_checkboxes: dict[str, QCheckBox] = {}
        self._scale_spin: QDoubleSpinBox

        self.setWindowTitle(self.tr("Import DXF"))
        self.setModal(True)
        self.setMinimumWidth(420)

        self._setup_ui()
        # Defer layer parsing so the dialog (with its "Loading layers…"
        # placeholder) is painted before ezdxf.readfile() blocks the UI thread.
        QTimer.singleShot(0, self._load_layers)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # File info
        file_label = QLabel(self.tr("File: {name}").format(name=self._file_path.name))
        file_label.setProperty("secondary", True)
        layout.addWidget(file_label)

        # Scale factor
        scale_group = QGroupBox(self.tr("Scale Factor"))
        scale_form = QFormLayout(scale_group)

        self._scale_spin = QDoubleSpinBox()
        self._scale_spin.setRange(0.001, 10000.0)
        self._scale_spin.setValue(1.0)
        self._scale_spin.setDecimals(3)
        self._scale_spin.setToolTip(
            self.tr("Multiply DXF coordinates by this factor to get centimeters.\n"
                    "Use 0.1 for DXF in mm, 100 for DXF in metres.")
        )
        scale_form.addRow(self.tr("Scale (DXF units → cm):"), self._scale_spin)
        layout.addWidget(scale_group)

        # Layer selection
        self._layers_group = QGroupBox(self.tr("Layers to Import"))
        layers_outer = QVBoxLayout(self._layers_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._layers_widget = QWidget()
        self._layers_layout = QVBoxLayout(self._layers_widget)
        self._layers_layout.setContentsMargins(4, 4, 4, 4)

        self._loading_label = QLabel(self.tr("Loading layers…"))
        self._loading_label.setProperty("secondary", True)
        self._layers_layout.addWidget(self._loading_label)

        scroll.setWidget(self._layers_widget)
        layers_outer.addWidget(scroll)

        layout.addWidget(self._layers_group)

        # Info label
        self._info_label = QLabel("")
        self._info_label.setProperty("secondary", True)
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_layers(self) -> None:
        from open_garden_planner.services.dxf_service import DxfImportService

        try:
            layers = DxfImportService.get_dxf_layers(self._file_path)
        except Exception as exc:
            self._loading_label.setText(self.tr("Failed to read DXF: {error}").format(error=exc))
            return

        # Remove loading label
        self._loading_label.setParent(None)  # type: ignore[arg-type]

        if not layers:
            placeholder = QLabel(self.tr("No layers found — all entities will be imported."))
            placeholder.setProperty("secondary", True)
            self._layers_layout.addWidget(placeholder)
            self._info_label.setText("")
            return

        for name in layers:
            cb = QCheckBox(name)
            cb.setChecked(True)
            self._layer_checkboxes[name] = cb
            self._layers_layout.addWidget(cb)

        self._info_label.setText(
            self.tr("{n} layer(s) found.").format(n=len(layers))
        )

    @property
    def scale_factor(self) -> float:
        """Scale factor to apply to DXF coordinates."""
        return self._scale_spin.value()

    @property
    def selected_layers(self) -> list[str] | None:
        """Checked layer names, or None if no layer checkboxes (import all)."""
        if not self._layer_checkboxes:
            return None
        return [name for name, cb in self._layer_checkboxes.items() if cb.isChecked()]
