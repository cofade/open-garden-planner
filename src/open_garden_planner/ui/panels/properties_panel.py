"""Properties panel for live editing of selected objects."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType, StrokeStyle, get_style
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)


class ColorButton(QPushButton):
    """A button that displays a color and opens a color picker when clicked."""

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        """Initialize the color button.

        Args:
            color: Initial color
            parent: Parent widget
        """
        super().__init__(parent)
        self._color = color
        self.setFixedHeight(30)
        self._update_style()
        self.clicked.connect(self._pick_color)

    @property
    def color(self) -> QColor:
        """Get the current color."""
        return self._color

    def set_color(self, color: QColor) -> None:
        """Set the button color.

        Args:
            color: New color
        """
        self._color = color
        self._update_style()

    def _update_style(self) -> None:
        """Update the button style to show the current color."""
        self.setStyleSheet(
            f"background-color: rgba({self._color.red()}, {self._color.green()}, "
            f"{self._color.blue()}, {self._color.alpha() / 255.0}); "
            f"border: 1px solid #888;"
        )

    def _pick_color(self) -> None:
        """Open color picker dialog."""
        dialog = QColorDialog()
        dialog.setCurrentColor(self._color)
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setWindowTitle("Choose Color")

        if dialog.exec():
            color = dialog.selectedColor()
            if color.isValid():
                self.set_color(color)


class PropertiesPanel(QWidget):
    """Panel for live editing of selected object properties.

    Shows properties of currently selected objects and allows immediate editing.
    Changes are applied in real-time to the canvas.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the properties panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._current_items: list[QGraphicsItem] = []
        self._updating = False  # Prevent feedback loops
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Scroll area for properties
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # Content widget
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)

        # Form layout for properties
        self._form_layout = QFormLayout()
        self._form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._content_layout.addLayout(self._form_layout)
        self._content_layout.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll)

        # Initially show "no selection" message
        self._show_no_selection()

    def _clear_form(self) -> None:
        """Clear all widgets from the form."""
        while self._form_layout.rowCount() > 0:
            self._form_layout.removeRow(0)

    def _show_no_selection(self) -> None:
        """Show message when nothing is selected."""
        self._clear_form()
        label = QLabel("No objects selected")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: gray; padding: 20px;")
        self._form_layout.addRow(label)

    def _show_multi_selection(self, count: int) -> None:
        """Show message for multiple selection.

        Args:
            count: Number of selected objects
        """
        self._clear_form()
        label = QLabel(f"{count} objects selected")
        label.setStyleSheet("font-weight: bold;")
        self._form_layout.addRow(label)

        # TODO: Show common properties for batch editing
        info = QLabel("Multi-selection editing\nnot yet implemented")
        info.setStyleSheet("color: gray; padding: 10px;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._form_layout.addRow(info)

    def set_selected_items(self, items: list[QGraphicsItem]) -> None:
        """Set the selected items to display properties for.

        Args:
            items: List of selected graphics items
        """
        self._current_items = items

        if not items:
            self._show_no_selection()
        elif len(items) > 1:
            self._show_multi_selection(len(items))
        else:
            self._show_single_item(items[0])

    def _show_single_item(self, item: QGraphicsItem) -> None:
        """Show properties for a single selected item.

        Args:
            item: The selected graphics item
        """
        self._clear_form()
        self._updating = True

        # Object Type (if applicable)
        if hasattr(item, 'object_type'):
            type_combo = QComboBox()
            self._populate_object_type_combo(type_combo, item)
            type_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'object_type', type_combo.currentData())
            )
            self._form_layout.addRow("Type:", type_combo)

        # Name/Label
        if hasattr(item, 'name'):
            name_edit = QLineEdit(item.name)
            name_edit.textChanged.connect(
                lambda text: self._on_property_changed(item, 'name', text)
            )
            self._form_layout.addRow("Name:", name_edit)

        # Layer
        if hasattr(item, 'layer_id'):
            layer_combo = QComboBox()
            self._populate_layer_combo(layer_combo, item)
            layer_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'layer_id', layer_combo.currentData())
            )
            self._form_layout.addRow("Layer:", layer_combo)

        # Geometry section
        self._add_geometry_properties(item)

        # Styling section
        self._add_styling_properties(item)

        # Plant-specific fields
        if hasattr(item, 'plant_type'):
            self._add_plant_properties(item)

        self._updating = False

    def _populate_object_type_combo(self, combo: QComboBox, item: QGraphicsItem) -> None:
        """Populate object type combobox.

        Args:
            combo: Combobox to populate
            item: Item to get valid types for
        """
        # Determine valid types based on item type
        if isinstance(item, (RectangleItem, PolygonItem, CircleItem)):
            valid_types = [
                ObjectType.GENERIC_RECTANGLE if isinstance(item, RectangleItem) else (
                    ObjectType.GENERIC_CIRCLE if isinstance(item, CircleItem) else ObjectType.GENERIC_POLYGON
                ),
                ObjectType.HOUSE,
                ObjectType.GARAGE_SHED,
                ObjectType.TERRACE_PATIO,
                ObjectType.DRIVEWAY,
                ObjectType.POND_POOL,
                ObjectType.GREENHOUSE,
            ]
        elif isinstance(item, PolylineItem):
            valid_types = [
                ObjectType.FENCE,
                ObjectType.WALL,
                ObjectType.PATH,
            ]
        else:
            valid_types = list(ObjectType)

        # Populate combo
        current_idx = 0
        for idx, obj_type in enumerate(valid_types):
            style = get_style(obj_type)
            combo.addItem(style.display_name, obj_type)
            if hasattr(item, 'object_type') and item.object_type == obj_type:
                current_idx = idx

        combo.setCurrentIndex(current_idx)

    def _populate_layer_combo(self, combo: QComboBox, item: QGraphicsItem) -> None:
        """Populate layer combobox.

        Args:
            combo: Combobox to populate
            item: Item to get current layer for
        """
        scene = item.scene()
        if scene and hasattr(scene, 'layers'):
            current_idx = 0
            for idx, layer in enumerate(scene.layers):
                combo.addItem(layer.name, layer.id)
                if hasattr(item, 'layer_id') and item.layer_id == layer.id:
                    current_idx = idx
            combo.setCurrentIndex(current_idx)

    def _add_geometry_properties(self, item: QGraphicsItem) -> None:
        """Add geometry property fields.

        Args:
            item: Item to show geometry for
        """
        # Position
        pos = item.pos()
        pos_label = QLabel(f"({pos.x():.1f}, {pos.y():.1f}) cm")
        self._form_layout.addRow("Position:", pos_label)

        # Type-specific geometry
        if isinstance(item, CircleItem):
            radius_label = QLabel(f"{item.radius * 2:.1f} cm")
            self._form_layout.addRow("Diameter:", radius_label)
        elif isinstance(item, RectangleItem):
            rect = item.rect()
            size_label = QLabel(f"{rect.width():.1f} × {rect.height():.1f} cm")
            self._form_layout.addRow("Size:", size_label)

    def _add_styling_properties(self, item: QGraphicsItem) -> None:
        """Add styling property fields.

        Args:
            item: Item to show styling for
        """
        if not isinstance(item, (RectangleItem, PolygonItem, CircleItem, PolylineItem)):
            return

        # Fill color (not for polylines)
        if not isinstance(item, PolylineItem):
            fill_color = item.fill_color if hasattr(item, 'fill_color') and item.fill_color else item.brush().color()
            fill_btn = ColorButton(fill_color)
            fill_btn.clicked.connect(
                lambda: self._on_color_changed(item, 'fill_color', fill_btn)
            )
            self._form_layout.addRow("Fill Color:", fill_btn)

            # Fill pattern
            pattern_combo = QComboBox()
            for pattern in FillPattern:
                pattern_combo.addItem(pattern.name.replace("_", " ").title(), pattern)

            current_pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
            for i in range(pattern_combo.count()):
                if pattern_combo.itemData(i) == current_pattern:
                    pattern_combo.setCurrentIndex(i)
                    break

            pattern_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'fill_pattern', pattern_combo.currentData())
            )
            self._form_layout.addRow("Fill Pattern:", pattern_combo)

        # Stroke color
        stroke_color = item.stroke_color if hasattr(item, 'stroke_color') and item.stroke_color else item.pen().color()
        stroke_btn = ColorButton(stroke_color)
        stroke_btn.clicked.connect(
            lambda: self._on_color_changed(item, 'stroke_color', stroke_btn)
        )
        self._form_layout.addRow("Stroke Color:", stroke_btn)

        # Stroke width
        width_spin = QDoubleSpinBox()
        width_spin.setRange(0.5, 20.0)
        width_spin.setSingleStep(0.5)
        width_spin.setDecimals(1)
        width_spin.setSuffix(" px")
        width_spin.setValue(
            item.stroke_width if hasattr(item, 'stroke_width') and item.stroke_width else item.pen().widthF()
        )
        width_spin.valueChanged.connect(
            lambda val: self._on_property_changed(item, 'stroke_width', val)
        )
        self._form_layout.addRow("Stroke Width:", width_spin)

        # Stroke style
        style_combo = QComboBox()
        for style in StrokeStyle:
            style_combo.addItem(style.name.replace("_", " ").title(), style)

        current_style = item.stroke_style if hasattr(item, 'stroke_style') else StrokeStyle.SOLID
        for i in range(style_combo.count()):
            if style_combo.itemData(i) == current_style:
                style_combo.setCurrentIndex(i)
                break

        style_combo.currentIndexChanged.connect(
            lambda: self._on_property_changed(item, 'stroke_style', style_combo.currentData())
        )
        self._form_layout.addRow("Stroke Style:", style_combo)

    def _add_plant_properties(self, item: QGraphicsItem) -> None:  # noqa: ARG002
        """Add plant-specific property fields.

        Args:
            item: Plant item to show properties for
        """
        # TODO: Add plant metadata fields when plant metadata is implemented
        # For now, just show a placeholder
        plant_label = QLabel("Plant metadata\ncoming in US-4.2")
        plant_label.setStyleSheet("color: gray; padding: 10px;")
        plant_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._form_layout.addRow(plant_label)

    def _on_property_changed(self, item: QGraphicsItem, property_name: str, value) -> None:
        """Handle property change.

        Args:
            item: Item being edited
            property_name: Name of the property
            value: New value
        """
        if self._updating:
            return

        # Apply the change to the item
        if property_name == 'object_type' and hasattr(item, 'object_type'):
            item.object_type = value
            # Apply default style for new type
            style = get_style(value)

            # Update stroke
            pen = QPen(style.stroke_color)
            pen.setWidthF(style.stroke_width)
            pen.setStyle(style.stroke_style.to_qt_pen_style())
            item.setPen(pen)

            # Update fill (not for polylines)
            if not isinstance(item, PolylineItem):
                if hasattr(item, 'fill_pattern'):
                    item.fill_pattern = style.fill_pattern
                if hasattr(item, 'fill_color'):
                    item.fill_color = style.fill_color
                brush = create_pattern_brush(style.fill_pattern, style.fill_color)
                item.setBrush(brush)

            # Store properties
            if hasattr(item, 'stroke_color'):
                item.stroke_color = style.stroke_color
            if hasattr(item, 'stroke_width'):
                item.stroke_width = style.stroke_width
            if hasattr(item, 'stroke_style'):
                item.stroke_style = style.stroke_style

            # Refresh the panel to show updated properties
            self.set_selected_items([item])

        elif property_name == 'name' and hasattr(item, 'name'):
            item.name = value
            # Update label if it exists
            if hasattr(item, '_update_label'):
                item._update_label()

        elif property_name == 'layer_id' and hasattr(item, 'layer_id'):
            item.layer_id = value
            # Update z-order based on new layer
            scene = item.scene()
            if scene and hasattr(scene, 'get_layer_by_id'):
                layer = scene.get_layer_by_id(value)
                if layer:
                    item.setZValue(layer.z_order * 100)

        elif property_name == 'fill_pattern':
            if hasattr(item, 'fill_pattern'):
                item.fill_pattern = value
            # Get current color
            color = item.fill_color if hasattr(item, 'fill_color') and item.fill_color else item.brush().color()
            brush = create_pattern_brush(value, color)
            item.setBrush(brush)

        elif property_name == 'stroke_width':
            if hasattr(item, 'stroke_width'):
                item.stroke_width = value
            pen = item.pen()
            pen.setWidthF(value)
            item.setPen(pen)

        elif property_name == 'stroke_style':
            if hasattr(item, 'stroke_style'):
                item.stroke_style = value
            pen = item.pen()
            pen.setStyle(value.to_qt_pen_style())
            item.setPen(pen)

        # Mark scene as modified
        scene = item.scene()
        if scene:
            scene.update()

    def _on_color_changed(self, item: QGraphicsItem, property_name: str, button: ColorButton) -> None:
        """Handle color button change.

        Args:
            item: Item being edited
            property_name: Name of the color property ('fill_color' or 'stroke_color')
            button: The color button that was changed
        """
        if self._updating:
            return

        color = button.color

        if property_name == 'fill_color':
            # Store the color
            if hasattr(item, 'fill_color'):
                item.fill_color = color
            # Apply to brush
            pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
            brush = create_pattern_brush(pattern, color)
            item.setBrush(brush)

        elif property_name == 'stroke_color':
            # Store the color
            if hasattr(item, 'stroke_color'):
                item.stroke_color = color
            # Apply to pen
            pen = item.pen()
            pen.setColor(color)
            item.setPen(pen)

        # Mark scene as modified
        scene = item.scene()
        if scene:
            scene.update()
