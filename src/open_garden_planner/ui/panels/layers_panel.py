"""Layers panel for managing layer visibility, locking, and order."""

from uuid import UUID

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.layer import Layer


class LayerListItem(QWidget):
    """Custom widget for a layer list item with visibility/lock controls."""

    visibility_changed = pyqtSignal(UUID, bool)
    lock_changed = pyqtSignal(UUID, bool)
    layer_selected = pyqtSignal(UUID)
    rename_requested = pyqtSignal(UUID)

    def __init__(self, layer: Layer, parent: QWidget | None = None) -> None:
        """Initialize the layer list item.

        Args:
            layer: The layer to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.layer = layer
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Visibility toggle button (eye icon)
        self.visibility_btn = QToolButton()
        self.visibility_btn.setCheckable(True)
        self.visibility_btn.setChecked(self.layer.visible)
        self.visibility_btn.setText("👁" if self.layer.visible else "🚫")
        self.visibility_btn.setToolTip("Toggle visibility")
        self.visibility_btn.setFixedSize(24, 24)
        self.visibility_btn.toggled.connect(self._on_visibility_toggled)
        layout.addWidget(self.visibility_btn)

        # Lock toggle button (lock icon)
        self.lock_btn = QToolButton()
        self.lock_btn.setCheckable(True)
        self.lock_btn.setChecked(self.layer.locked)
        self.lock_btn.setText("🔒" if self.layer.locked else "🔓")
        self.lock_btn.setToolTip("Toggle lock")
        self.lock_btn.setFixedSize(24, 24)
        self.lock_btn.toggled.connect(self._on_lock_toggled)
        layout.addWidget(self.lock_btn)

        # Layer name label
        self.name_label = QLabel(self.layer.name)
        self.name_label.setStyleSheet("padding-left: 4px;")
        self.name_label.mouseDoubleClickEvent = lambda _: self._start_editing()
        layout.addWidget(self.name_label, 1)

        # Layer name edit (hidden by default)
        self.name_edit = QLineEdit(self.layer.name)
        self.name_edit.setStyleSheet("padding-left: 4px;")
        self.name_edit.hide()
        self.name_edit.editingFinished.connect(self._finish_editing)
        self.name_edit.returnPressed.connect(self._finish_editing)
        layout.addWidget(self.name_edit, 1)

        # Update styling based on layer state
        self._update_styling()

    def _start_editing(self) -> None:
        """Start inline editing of layer name."""
        self.name_label.hide()
        self.name_edit.setText(self.layer.name)
        self.name_edit.show()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _finish_editing(self) -> None:
        """Finish inline editing of layer name."""
        new_name = self.name_edit.text().strip()
        if new_name and new_name != self.layer.name:
            self.layer.name = new_name
            self.name_label.setText(new_name)
            self.rename_requested.emit(self.layer.id)
        self.name_edit.hide()
        self.name_label.show()

    def contextMenuEvent(self, event):
        """Show context menu for layer operations."""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        rename_action = menu.addAction("Rename Layer")
        action = menu.exec(event.globalPos())
        if action == rename_action:
            self._start_editing()

    def _on_visibility_toggled(self, checked: bool) -> None:
        """Handle visibility toggle."""
        self.layer.visible = checked
        self.visibility_btn.setText("👁" if checked else "🚫")
        self.visibility_changed.emit(self.layer.id, checked)
        self._update_styling()

    def _on_lock_toggled(self, checked: bool) -> None:
        """Handle lock toggle."""
        self.layer.locked = checked
        self.lock_btn.setText("🔒" if checked else "🔓")
        self.lock_changed.emit(self.layer.id, checked)
        self._update_styling()

    def _update_styling(self) -> None:
        """Update visual styling based on layer state."""
        if not self.layer.visible:
            self.name_label.setStyleSheet("color: gray; padding-left: 4px;")
        else:
            self.name_label.setStyleSheet("padding-left: 4px;")

    def update_layer(self, layer: Layer) -> None:
        """Update the displayed layer.

        Args:
            layer: Updated layer data
        """
        self.layer = layer
        self.name_label.setText(layer.name)
        self.name_edit.setText(layer.name)
        self.visibility_btn.setChecked(layer.visible)
        self.visibility_btn.setText("👁" if layer.visible else "🚫")
        self.lock_btn.setChecked(layer.locked)
        self.lock_btn.setText("🔒" if layer.locked else "🔓")
        self._update_styling()


class LayersPanel(QWidget):
    """Panel for managing layers."""

    active_layer_changed = pyqtSignal(UUID)
    layer_visibility_changed = pyqtSignal(UUID, bool)
    layer_lock_changed = pyqtSignal(UUID, bool)
    layer_opacity_changed = pyqtSignal(UUID, float)
    layers_reordered = pyqtSignal(list)
    layer_renamed = pyqtSignal(UUID, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the layers panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._layers: list[Layer] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title
        title = QLabel("Layers")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # Layer list with limited height
        self.layer_list = QListWidget()
        self.layer_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.layer_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.layer_list.currentRowChanged.connect(self._on_layer_selected)
        self.layer_list.model().rowsMoved.connect(self._on_layers_reordered)
        # Set maximum height to show ~5 layers, then scroll
        self.layer_list.setMaximumHeight(165)
        layout.addWidget(self.layer_list)

        # Opacity slider
        opacity_layout = QHBoxLayout()
        opacity_label = QLabel("Opacity:")
        opacity_layout.addWidget(opacity_label)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setMinimum(0)
        self.opacity_slider.setMaximum(100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setToolTip("Layer opacity")
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)

        self.opacity_value_label = QLabel("100%")
        self.opacity_value_label.setFixedWidth(40)
        opacity_layout.addWidget(self.opacity_value_label)

        layout.addLayout(opacity_layout)

        # Add layer button
        add_btn = QPushButton("Add Layer")
        add_btn.clicked.connect(self._on_add_layer)
        layout.addWidget(add_btn)

        # Add spacer at the bottom to push everything to the top
        layout.addStretch()

    def set_layers(self, layers: list[Layer]) -> None:
        """Set the layers to display.

        Args:
            layers: List of layers
        """
        self._layers = layers
        self._refresh_list()

    def _refresh_list(self) -> None:
        """Refresh the layer list display."""
        current_row = self.layer_list.currentRow()
        self.layer_list.clear()

        for layer in self._layers:
            item = QListWidgetItem(self.layer_list)
            widget = LayerListItem(layer)
            widget.visibility_changed.connect(self.layer_visibility_changed.emit)
            widget.lock_changed.connect(self.layer_lock_changed.emit)
            widget.rename_requested.connect(self._on_rename_layer)

            item.setSizeHint(widget.sizeHint())
            self.layer_list.addItem(item)
            self.layer_list.setItemWidget(item, widget)

        # Restore selection
        if 0 <= current_row < len(self._layers):
            self.layer_list.setCurrentRow(current_row)
        elif self._layers:
            self.layer_list.setCurrentRow(0)

    def _on_layer_selected(self, row: int) -> None:
        """Handle layer selection.

        Args:
            row: Selected row index
        """
        if 0 <= row < len(self._layers):
            layer = self._layers[row]
            self.active_layer_changed.emit(layer.id)
            # Update opacity slider to show selected layer's opacity
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(int(layer.opacity * 100))
            self.opacity_value_label.setText(f"{int(layer.opacity * 100)}%")
            self.opacity_slider.blockSignals(False)

    def _on_opacity_changed(self, value: int) -> None:
        """Handle opacity slider change.

        Args:
            value: Slider value (0-100)
        """
        self.opacity_value_label.setText(f"{value}%")
        row = self.layer_list.currentRow()
        if 0 <= row < len(self._layers):
            layer = self._layers[row]
            opacity = value / 100.0
            self.layer_opacity_changed.emit(layer.id, opacity)

    def _on_layers_reordered(self) -> None:
        """Handle layer reordering via drag-and-drop."""
        # Rebuild layers list based on new order
        new_order = []
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            widget = self.layer_list.itemWidget(item)
            if isinstance(widget, LayerListItem):
                new_order.append(widget.layer)

        if new_order:
            self._layers = new_order
            self.layers_reordered.emit(new_order)

    def _on_add_layer(self) -> None:
        """Handle add layer button click."""
        # Create a new layer with a unique name
        layer_num = len(self._layers) + 1
        new_layer = Layer(name=f"Layer {layer_num}", z_order=len(self._layers))
        self._layers.append(new_layer)
        self._refresh_list()
        self.layers_reordered.emit(self._layers)

    def _on_rename_layer(self, layer_id: UUID) -> None:
        """Handle layer rename request (emitted from LayerListItem).

        Args:
            layer_id: ID of layer that was renamed
        """
        # Signal that the layer was renamed (for marking project dirty)
        for layer in self._layers:
            if layer.id == layer_id:
                self.layer_renamed.emit(layer_id, layer.name)
                break

    def update_layer(self, layer: Layer) -> None:
        """Update a specific layer in the list.

        Args:
            layer: Updated layer data
        """
        for i, existing_layer in enumerate(self._layers):
            if existing_layer.id == layer.id:
                self._layers[i] = layer
                item = self.layer_list.item(i)
                widget = self.layer_list.itemWidget(item)
                if isinstance(widget, LayerListItem):
                    widget.update_layer(layer)
                break
