"""Layers panel for managing layer visibility, locking, and order."""

from pathlib import Path
from uuid import UUID

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
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

_ICONS_DIR = Path(__file__).parent.parent.parent / "resources" / "icons" / "layers"

# Inline SVG sources for layer icons.
# Stroke colors chosen for good contrast on both light and dark backgrounds.
_EYE_OPEN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3d8b37" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>"""

_EYE_CLOSED_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#888888" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/>
  <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/>
  <line x1="1" y1="1" x2="23" y2="23"/>
</svg>"""

_LOCK_OPEN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3d8b37" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
  <path d="M7 11V7a5 5 0 019.9-1"/>
</svg>"""

_LOCK_CLOSED_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#D97706" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
  <path d="M7 11V7a5 5 0 0110 0v4"/>
</svg>"""


def _svg_to_icon(svg_data: str, size: int = 20) -> QIcon:
    """Render an inline SVG string to a QIcon.

    Args:
        svg_data: SVG markup string
        size: Icon pixel size

    Returns:
        QIcon rendered from the SVG
    """
    renderer = QSvgRenderer(svg_data.encode())
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class LayerListItem(QWidget):
    """Custom widget for a layer list item with visibility/lock controls."""

    visibility_changed = pyqtSignal(UUID, bool)
    lock_changed = pyqtSignal(UUID, bool)
    delete_requested = pyqtSignal(UUID)
    layer_selected = pyqtSignal(UUID)
    rename_requested = pyqtSignal(UUID, str)

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

        # Pre-render icons
        self._eye_open_icon = _svg_to_icon(_EYE_OPEN_SVG)
        self._eye_closed_icon = _svg_to_icon(_EYE_CLOSED_SVG)
        self._lock_open_icon = _svg_to_icon(_LOCK_OPEN_SVG)
        self._lock_closed_icon = _svg_to_icon(_LOCK_CLOSED_SVG)

        # Visibility toggle button
        self.visibility_btn = QToolButton()
        self.visibility_btn.setCheckable(True)
        self.visibility_btn.setChecked(self.layer.visible)
        self.visibility_btn.setIcon(
            self._eye_open_icon if self.layer.visible else self._eye_closed_icon
        )
        self.visibility_btn.setIconSize(QSize(16, 16))
        self.visibility_btn.setToolTip(self.tr("Toggle visibility"))
        self.visibility_btn.setFixedSize(24, 24)
        self.visibility_btn.toggled.connect(self._on_visibility_toggled)
        layout.addWidget(self.visibility_btn)

        # Lock toggle button
        self.lock_btn = QToolButton()
        self.lock_btn.setCheckable(True)
        self.lock_btn.setChecked(self.layer.locked)
        self.lock_btn.setIcon(
            self._lock_closed_icon if self.layer.locked else self._lock_open_icon
        )
        self.lock_btn.setIconSize(QSize(16, 16))
        self.lock_btn.setToolTip(self.tr("Toggle lock"))
        self.lock_btn.setFixedSize(24, 24)
        self.lock_btn.toggled.connect(self._on_lock_toggled)
        layout.addWidget(self.lock_btn)

        # Layer name label — use palette-safe color so it stays readable
        # when selected in both light and dark modes
        self.name_label = QLabel(self.layer.name)
        self.name_label.setStyleSheet(
            "padding-left: 4px;"
        )
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
        self.name_edit.hide()
        self.name_label.show()
        # Do NOT mutate self.layer here — the rename is applied by an undoable
        # RenameLayerCommand; the resulting layers_changed rebuild updates the
        # label. Emit last: the rebuild deletes this widget.
        if new_name and new_name != self.layer.name:
            self.rename_requested.emit(self.layer.id, new_name)

    def contextMenuEvent(self, event):
        """Show context menu for layer operations."""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        rename_action = menu.addAction(self.tr("Rename Layer"))
        delete_action = menu.addAction(self.tr("Delete Layer"))
        action = menu.exec(event.globalPos())
        if action == rename_action:
            self._start_editing()
        elif action == delete_action:
            self.delete_requested.emit(self.layer.id)

    def _on_visibility_toggled(self, checked: bool) -> None:
        """Handle visibility toggle.

        Emit-only: the change is applied by an undoable command whose
        layers_changed emission rebuilds this widget with the new state.
        """
        self.visibility_changed.emit(self.layer.id, checked)

    def _on_lock_toggled(self, checked: bool) -> None:
        """Handle lock toggle.

        Emit-only: the change is applied by an undoable command whose
        layers_changed emission rebuilds this widget with the new state.
        """
        self.lock_changed.emit(self.layer.id, checked)

    def _update_styling(self) -> None:
        """Update visual styling based on layer state."""
        # Use the secondary property for dimmed (hidden-layer) appearance so
        # the colour comes from the global CSS rule and stays readable in both
        # light and dark themes.
        is_hidden = not self.layer.visible
        self.name_label.setProperty("secondary", is_hidden)
        self.name_label.setStyleSheet("padding-left: 4px;")
        # Force a style re-evaluation after the dynamic property change.
        self.name_label.style().unpolish(self.name_label)
        self.name_label.style().polish(self.name_label)

    def update_layer(self, layer: Layer) -> None:
        """Update the displayed layer.

        Args:
            layer: Updated layer data
        """
        self.layer = layer
        self.name_label.setText(layer.name)
        self.name_edit.setText(layer.name)
        self.visibility_btn.setChecked(layer.visible)
        self.visibility_btn.setIcon(
            self._eye_open_icon if layer.visible else self._eye_closed_icon
        )
        self.lock_btn.setChecked(layer.locked)
        self.lock_btn.setIcon(
            self._lock_closed_icon if layer.locked else self._lock_open_icon
        )
        self._update_styling()


class LayersPanel(QWidget):
    """Panel for managing layers."""

    active_layer_changed = pyqtSignal(UUID)
    layer_visibility_changed = pyqtSignal(UUID, bool)
    layer_lock_changed = pyqtSignal(UUID, bool)
    # Live (non-undoable) opacity preview while the slider is being dragged.
    layer_opacity_changed = pyqtSignal(UUID, float)
    # Final opacity commit: (layer_id, old_opacity, new_opacity) — one per
    # slider drag (or per keyboard/groove-click change).
    layer_opacity_committed = pyqtSignal(UUID, float, float)
    layers_reordered = pyqtSignal(list)
    layer_renamed = pyqtSignal(UUID, str)
    layer_deleted = pyqtSignal(UUID)
    # Request to create a new layer with the given (unique) name.
    layer_add_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the layers panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._layers: list[Layer] = []
        # Opacity snapshot taken on sliderPressed so the whole drag coalesces
        # into a single undoable command on release.
        self._opacity_drag_origin: float | None = None
        self._opacity_drag_layer_id: UUID | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Layer list - height adjusts to content, scrolls at 5+ layers
        self.layer_list = QListWidget()
        self.layer_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.layer_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.layer_list.currentRowChanged.connect(self._on_layer_selected)
        self.layer_list.model().rowsMoved.connect(self._on_layers_reordered)
        # Height will be adjusted dynamically in _refresh_list
        layout.addWidget(self.layer_list)

        # Opacity slider
        opacity_layout = QHBoxLayout()
        opacity_label = QLabel(self.tr("Opacity:"))
        opacity_layout.addWidget(opacity_label)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setMinimum(0)
        self.opacity_slider.setMaximum(100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setToolTip(self.tr("Layer opacity"))
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_slider.sliderPressed.connect(self._on_opacity_drag_started)
        self.opacity_slider.sliderReleased.connect(self._on_opacity_drag_finished)
        opacity_layout.addWidget(self.opacity_slider)

        self.opacity_value_label = QLabel("100%")
        self.opacity_value_label.setFixedWidth(40)
        opacity_layout.addWidget(self.opacity_value_label)

        layout.addLayout(opacity_layout)

        # Add layer button
        add_btn = QPushButton(self.tr("Add Layer"))
        add_btn.clicked.connect(self._on_add_layer)
        layout.addWidget(add_btn)

        # Add spacer at the bottom to push everything to the top
        layout.addStretch()

    def set_layers(self, layers: list[Layer]) -> None:
        """Set the layers to display.

        Args:
            layers: List of layers
        """
        # Defensive copy: the scene hands over its LIVE list (see risk §11.4).
        # The panel must never mutate the scene's list structure — all
        # structural changes go through undoable commands.
        self._layers = list(layers)
        self._refresh_list()

    def _refresh_list(self) -> None:
        """Refresh the layer list display."""
        # Remember the selected layer by identity (not row index): the order can
        # change between refreshes — e.g. a new layer inserted at the top shifts
        # every existing row down by one (issue #201) — so a saved row index would
        # point at the wrong layer after the rebuild.
        selected_id = None
        current_item = self.layer_list.currentItem()
        if current_item is not None:
            current_widget = self.layer_list.itemWidget(current_item)
            if isinstance(current_widget, LayerListItem):
                selected_id = current_widget.layer.id

        self.layer_list.clear()

        for layer in self._layers:
            item = QListWidgetItem(self.layer_list)
            widget = LayerListItem(layer)
            widget.visibility_changed.connect(self.layer_visibility_changed.emit)
            widget.lock_changed.connect(self.layer_lock_changed.emit)
            widget.rename_requested.connect(self._on_rename_layer)
            widget.delete_requested.connect(self._on_delete_layer)

            hint = widget.sizeHint()
            hint.setHeight(max(hint.height(), 36))
            item.setSizeHint(hint)
            self.layer_list.addItem(item)
            self.layer_list.setItemWidget(item, widget)

        # Restore selection by layer id, falling back to the top layer.
        restored = False
        if selected_id is not None:
            for i, layer in enumerate(self._layers):
                if layer.id == selected_id:
                    self.layer_list.setCurrentRow(i)
                    restored = True
                    break
        if not restored and self._layers:
            self.layer_list.setCurrentRow(0)

        # Adjust height based on number of layers (max 5 visible, then scroll)
        self._adjust_list_height()

    def _adjust_list_height(self) -> None:
        """Adjust the list height based on number of layers."""
        # Height per item (24px icon + 4+4px margins + 4px padding)
        item_height = 36
        num_layers = len(self._layers)
        max_visible = 5

        if num_layers <= max_visible:
            # Show all layers without scrolling
            height = max(item_height, num_layers * item_height)
            self.layer_list.setFixedHeight(height)
        else:
            # Limit to max_visible layers, enable scrolling
            height = max_visible * item_height
            self.layer_list.setMaximumHeight(height)
            self.layer_list.setMinimumHeight(height)

    def refresh_layer_visibility(self, layer_id: UUID, visible: bool) -> None:
        """Update the visibility button for a layer without emitting layer_visibility_changed.

        Called when the scene auto-unhides a layer (e.g. when drawing on a hidden layer).
        """
        for i in range(self.layer_list.count()):
            widget = self.layer_list.itemWidget(self.layer_list.item(i))
            if isinstance(widget, LayerListItem) and widget.layer.id == layer_id:
                widget.visibility_btn.blockSignals(True)
                widget.visibility_btn.setChecked(visible)
                widget.visibility_btn.setIcon(
                    widget._eye_open_icon if visible else widget._eye_closed_icon
                )
                widget.visibility_btn.blockSignals(False)
                widget._update_styling()
                break

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

        While the slider is being dragged this emits the live (non-undoable)
        preview signal; the drag is committed as one undoable step on release
        (see _on_opacity_drag_finished). Keyboard / groove-click changes have
        no press/release pair, so they commit immediately.

        Args:
            value: Slider value (0-100)
        """
        self.opacity_value_label.setText(f"{value}%")
        row = self.layer_list.currentRow()
        if not (0 <= row < len(self._layers)):
            return
        layer = self._layers[row]
        opacity = value / 100.0
        if self.opacity_slider.isSliderDown():
            self.layer_opacity_changed.emit(layer.id, opacity)
        elif opacity != layer.opacity:
            # layer.opacity still holds the old value — the panel no longer
            # mutates it; the command does.
            self.layer_opacity_committed.emit(layer.id, layer.opacity, opacity)

    def _on_opacity_drag_started(self) -> None:
        """Snapshot the opacity at drag start for commit-on-release."""
        row = self.layer_list.currentRow()
        if 0 <= row < len(self._layers):
            layer = self._layers[row]
            self._opacity_drag_layer_id = layer.id
            self._opacity_drag_origin = layer.opacity

    def _on_opacity_drag_finished(self) -> None:
        """Commit the whole slider drag as a single undoable change."""
        if (
            self._opacity_drag_origin is not None
            and self._opacity_drag_layer_id is not None
        ):
            final = self.opacity_slider.value() / 100.0
            if final != self._opacity_drag_origin:
                self.layer_opacity_committed.emit(
                    self._opacity_drag_layer_id, self._opacity_drag_origin, final
                )
        self._opacity_drag_origin = None
        self._opacity_drag_layer_id = None

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
        """Handle add layer button click.

        Computes a unique name and emits layer_add_requested; the actual
        insertion (top of the order, highest z_order, activation — issue #201)
        is performed by an undoable AddLayerCommand, whose layers_changed /
        active_layer_changed emissions rebuild this list and select the new
        layer.
        """
        existing_names = {layer.name for layer in self._layers}
        layer_num = 1
        layer_base = self.tr("Layer")
        while f"{layer_base} {layer_num}" in existing_names:
            layer_num += 1
        self.layer_add_requested.emit(f"{layer_base} {layer_num}")

    def _on_rename_layer(self, layer_id: UUID, new_name: str) -> None:
        """Handle layer rename request (emitted from LayerListItem).

        Args:
            layer_id: ID of the layer to rename
            new_name: Requested new name (the layer still holds the old one)
        """
        self.layer_renamed.emit(layer_id, new_name)

    def _on_delete_layer(self, layer_id: UUID) -> None:
        """Handle layer delete request.

        Emit-only: the deletion is performed by an undoable command whose
        layers_changed emission rebuilds this list.

        Args:
            layer_id: ID of layer to delete
        """
        if len(self._layers) <= 1:
            return  # Must keep at least one layer
        self.layer_deleted.emit(layer_id)

    def select_layer(self, layer_id: UUID) -> None:
        """Select the given layer in the list without re-emitting activation.

        Called when the scene's active layer changes from outside the panel
        (e.g. undo/redo of layer commands), so the visible selection and the
        opacity slider follow the scene state.

        Args:
            layer_id: ID of the layer to select
        """
        for i, layer in enumerate(self._layers):
            if layer.id == layer_id:
                self.layer_list.blockSignals(True)
                self.layer_list.setCurrentRow(i)
                self.layer_list.blockSignals(False)
                self.opacity_slider.blockSignals(True)
                self.opacity_slider.setValue(int(layer.opacity * 100))
                self.opacity_slider.blockSignals(False)
                self.opacity_value_label.setText(f"{int(layer.opacity * 100)}%")
                return

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
