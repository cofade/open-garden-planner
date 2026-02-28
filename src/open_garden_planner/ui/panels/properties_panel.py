"""Properties panel for live editing of selected objects."""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.commands import ChangePropertyCommand, CommandManager
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import (
    ObjectType,
    PathFenceStyle,
    StrokeStyle,
    get_style,
    get_translated_display_name,
    get_translated_path_fence_style_name,
)
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
        dialog.setWindowTitle(self.tr("Choose Color"))

        if dialog.exec():
            color = dialog.selectedColor()
            if color.isValid():
                self.set_color(color)


class PropertiesPanel(QWidget):
    """Panel for live editing of selected object properties.

    Shows properties of currently selected objects and allows immediate editing.
    Changes are applied in real-time to the canvas with undo support.
    """

    # Signal emitted when an object's type changes (for updating other panels)
    object_type_changed = pyqtSignal()

    def __init__(
        self,
        command_manager: CommandManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the properties panel.

        Args:
            command_manager: Optional command manager for undo support
            parent: Parent widget
        """
        super().__init__(parent)
        self._command_manager = command_manager
        self._current_items: list[QGraphicsItem] = []
        self._updating = False  # Prevent feedback loops
        self._setup_ui()

    def set_command_manager(self, command_manager: CommandManager) -> None:
        """Set the command manager for undo support.

        Args:
            command_manager: The command manager to use
        """
        self._command_manager = command_manager

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
        label = QLabel(self.tr("No objects selected"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("secondary", True)
        label.setStyleSheet("padding: 20px;")
        self._form_layout.addRow(label)

    def _show_multi_selection(self, count: int) -> None:
        """Show message for multiple selection.

        Args:
            count: Number of selected objects
        """
        self._clear_form()
        label = QLabel(self.tr("{count} objects selected").format(count=count))
        label.setStyleSheet("font-weight: bold;")
        self._form_layout.addRow(label)

        # TODO: Show common properties for batch editing
        info = QLabel(self.tr("Multi-selection editing\nnot yet implemented"))
        info.setProperty("secondary", True)
        info.setStyleSheet("padding: 10px;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._form_layout.addRow(info)

    def set_selected_items(self, items: list[QGraphicsItem]) -> None:
        """Set the selected items to display properties for.

        Args:
            items: List of selected graphics items
        """
        # Don't rebuild the form while the user is actively typing in a spin box.
        # This prevents the focused widget from being destroyed mid-input when
        # command_executed triggers _update_properties_panel.
        from PyQt6.QtWidgets import QApplication, QDoubleSpinBox
        fw = QApplication.focusWidget()
        if fw is not None and isinstance(fw, QDoubleSpinBox) and self.isAncestorOf(fw):
            return

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
            self._form_layout.addRow(self.tr("Type:"), type_combo)

        # Name/Label
        if hasattr(item, 'name'):
            name_edit = QLineEdit(item.name)
            name_edit.textChanged.connect(
                lambda text: self._on_property_changed(item, 'name', text)
            )
            self._form_layout.addRow(self.tr("Name:"), name_edit)

        # Show Label checkbox
        if hasattr(item, 'label_visible'):
            label_check = QCheckBox(self.tr("Show label on canvas"))
            label_check.setChecked(item.label_visible)
            label_check.toggled.connect(
                lambda checked: self._on_property_changed(item, 'label_visible', checked)
            )
            self._form_layout.addRow(self.tr("Label:"), label_check)

        # Layer
        if hasattr(item, 'layer_id'):
            layer_combo = QComboBox()
            self._populate_layer_combo(layer_combo, item)
            layer_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'layer_id', layer_combo.currentData())
            )
            self._form_layout.addRow(self.tr("Layer:"), layer_combo)

        # Geometry section
        self._add_geometry_properties(item)

        # Styling section
        self._add_styling_properties(item)

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
                ObjectType.GARDEN_BED,
                ObjectType.TREE,
                ObjectType.SHRUB,
                ObjectType.PERENNIAL,
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
            combo.addItem(get_translated_display_name(obj_type), obj_type)
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
        # Position (editable X, Y) - use top-left corner of bounding box in scene coords
        # This corresponds to visual bottom-left after Y-flip (CAD origin)
        bbox = item.boundingRect()

        # Get top-left in local coordinates and map to scene
        # In scene coords (Y-down), topLeft is the visual bottom-left after Y-flip
        top_left_local = bbox.topLeft()
        top_left_scene = item.mapToScene(top_left_local)

        # Scene topLeft Y directly corresponds to CAD bottom-left Y
        bottom_left_x = top_left_scene.x()
        bottom_left_y = top_left_scene.y()

        # Create horizontal layout for X and Y spin boxes
        pos_layout = QHBoxLayout()
        pos_layout.setSpacing(4)
        pos_layout.setContentsMargins(0, 0, 0, 0)

        # X coordinate
        x_label = QLabel("X:")
        x_spin = QDoubleSpinBox()
        x_spin.setRange(-100000.0, 100000.0)
        x_spin.setDecimals(1)
        x_spin.setSingleStep(10.0)
        x_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        x_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        x_spin.setValue(bottom_left_x)
        pos_layout.addWidget(x_label)
        pos_layout.addWidget(x_spin, 1)

        # Y coordinate
        y_label = QLabel("Y:")
        y_spin = QDoubleSpinBox()
        y_spin.setRange(-100000.0, 100000.0)
        y_spin.setDecimals(1)
        y_spin.setSingleStep(10.0)
        y_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        y_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        y_spin.setValue(bottom_left_y)
        pos_layout.addWidget(y_label)
        pos_layout.addWidget(y_spin, 1)

        # Connect after both spin boxes are created
        x_spin.valueChanged.connect(
            lambda _: self._on_position_changed(item, x_spin, y_spin)
        )
        y_spin.valueChanged.connect(
            lambda _: self._on_position_changed(item, x_spin, y_spin)
        )

        # Create a widget to hold the layout; Expanding so it fills the field column
        pos_widget = QWidget()
        pos_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        pos_widget.setLayout(pos_layout)
        self._form_layout.addRow(self.tr("Position:"), pos_widget)

        # Type-specific geometry (editable)
        if isinstance(item, CircleItem):
            diameter_spin = QDoubleSpinBox()
            diameter_spin.setRange(1.0, 100000.0)
            diameter_spin.setDecimals(1)
            diameter_spin.setSingleStep(10.0)
            diameter_spin.setSuffix(" cm")
            diameter_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            diameter_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
            diameter_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            diameter_spin.setValue(item.radius * 2)
            diameter_spin.valueChanged.connect(
                lambda val: self._on_dimension_changed(item, 'circle_diameter', val)
            )
            self._form_layout.addRow(self.tr("Diameter:"), diameter_spin)
        elif isinstance(item, RectangleItem):
            rect = item.rect()
            size_layout = QHBoxLayout()
            size_layout.setSpacing(4)
            size_layout.setContentsMargins(0, 0, 0, 0)

            w_label = QLabel("W:")
            w_spin = QDoubleSpinBox()
            w_spin.setRange(1.0, 100000.0)
            w_spin.setDecimals(1)
            w_spin.setSingleStep(10.0)
            w_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
            w_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            w_spin.setValue(rect.width())
            size_layout.addWidget(w_label)
            size_layout.addWidget(w_spin, 1)

            h_label = QLabel("H:")
            h_spin = QDoubleSpinBox()
            h_spin.setRange(1.0, 100000.0)
            h_spin.setDecimals(1)
            h_spin.setSingleStep(10.0)
            h_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
            h_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            h_spin.setValue(rect.height())
            size_layout.addWidget(h_label)
            size_layout.addWidget(h_spin, 1)

            w_spin.valueChanged.connect(
                lambda _: self._on_dimension_changed(item, 'rect_size', None, w_spin, h_spin)
            )
            h_spin.valueChanged.connect(
                lambda _: self._on_dimension_changed(item, 'rect_size', None, w_spin, h_spin)
            )

            size_widget = QWidget()
            size_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            size_widget.setLayout(size_layout)
            self._form_layout.addRow(self.tr("Size:"), size_widget)

    def _add_styling_properties(self, item: QGraphicsItem) -> None:
        """Add styling property fields.

        Args:
            item: Item to show styling for
        """
        if not isinstance(item, (RectangleItem, PolygonItem, CircleItem, PolylineItem)):
            return

        # Path/fence style preset (only for polylines)
        if isinstance(item, PolylineItem):
            style_combo = QComboBox()
            # Add "Paths" group
            style_combo.addItem(self.tr("── Paths ──"), None)
            idx = style_combo.count() - 1
            model = style_combo.model()
            if model:
                model.item(idx).setEnabled(False)
            for pfs in [
                PathFenceStyle.NONE,
                PathFenceStyle.GRAVEL_PATH,
                PathFenceStyle.STEPPING_STONES,
                PathFenceStyle.PAVED_PATH,
                PathFenceStyle.WOODEN_BOARDWALK,
                PathFenceStyle.DIRT_PATH,
            ]:
                style_combo.addItem(get_translated_path_fence_style_name(pfs), pfs)
            # Add "Fences" group
            style_combo.addItem(self.tr("── Fences ──"), None)
            idx = style_combo.count() - 1
            if model:
                model.item(idx).setEnabled(False)
            for pfs in [
                PathFenceStyle.WOODEN_FENCE,
                PathFenceStyle.METAL_FENCE,
                PathFenceStyle.CHAIN_LINK,
                PathFenceStyle.HEDGE_FENCE,
                PathFenceStyle.STONE_WALL,
            ]:
                style_combo.addItem(get_translated_path_fence_style_name(pfs), pfs)

            current_pfs = item.path_fence_style if hasattr(item, 'path_fence_style') else PathFenceStyle.NONE
            for i in range(style_combo.count()):
                if style_combo.itemData(i) == current_pfs:
                    style_combo.setCurrentIndex(i)
                    break

            style_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'path_fence_style', style_combo.currentData())
                if style_combo.currentData() is not None else None
            )
            self._form_layout.addRow(self.tr("Style:"), style_combo)

        # Fill color (not for polylines)
        if not isinstance(item, PolylineItem):
            fill_color = item.fill_color if hasattr(item, 'fill_color') and item.fill_color else item.brush().color()
            fill_btn = ColorButton(fill_color)
            fill_btn.clicked.connect(
                lambda: self._on_color_changed(item, 'fill_color', fill_btn)
            )
            self._form_layout.addRow(self.tr("Fill Color:"), fill_btn)

            # Fill pattern
            pattern_combo = QComboBox()
            _pattern_names = {
                FillPattern.SOLID: self.tr("Solid"),
                FillPattern.GRASS: self.tr("Grass"),
                FillPattern.GRAVEL: self.tr("Gravel"),
                FillPattern.CONCRETE: self.tr("Concrete"),
                FillPattern.WOOD: self.tr("Wood"),
                FillPattern.WATER: self.tr("Water"),
                FillPattern.SOIL: self.tr("Soil"),
                FillPattern.MULCH: self.tr("Mulch"),
                FillPattern.ROOF_TILES: self.tr("Roof Tiles"),
                FillPattern.SAND: self.tr("Sand"),
                FillPattern.STONE: self.tr("Stone"),
                FillPattern.GLASS: self.tr("Glass"),
            }
            for pattern in FillPattern:
                pattern_combo.addItem(_pattern_names.get(pattern, pattern.name), pattern)

            current_pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
            for i in range(pattern_combo.count()):
                if pattern_combo.itemData(i) == current_pattern:
                    pattern_combo.setCurrentIndex(i)
                    break

            pattern_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'fill_pattern', pattern_combo.currentData())
            )
            self._form_layout.addRow(self.tr("Fill Pattern:"), pattern_combo)

        # Stroke color
        stroke_color = item.stroke_color if hasattr(item, 'stroke_color') and item.stroke_color else item.pen().color()
        stroke_btn = ColorButton(stroke_color)
        stroke_btn.clicked.connect(
            lambda: self._on_color_changed(item, 'stroke_color', stroke_btn)
        )
        self._form_layout.addRow(self.tr("Stroke Color:"), stroke_btn)

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
        self._form_layout.addRow(self.tr("Stroke Width:"), width_spin)

        # Stroke style
        stroke_style_combo = QComboBox()
        _style_names = {
            StrokeStyle.SOLID: self.tr("Solid"),
            StrokeStyle.DASHED: self.tr("Dashed"),
            StrokeStyle.DOTTED: self.tr("Dotted"),
            StrokeStyle.DASH_DOT: self.tr("Dash Dot"),
        }
        for style in StrokeStyle:
            stroke_style_combo.addItem(_style_names.get(style, style.name), style)

        current_style = item.stroke_style if hasattr(item, 'stroke_style') else StrokeStyle.SOLID
        for i in range(stroke_style_combo.count()):
            if stroke_style_combo.itemData(i) == current_style:
                stroke_style_combo.setCurrentIndex(i)
                break

        stroke_style_combo.currentIndexChanged.connect(
            lambda: self._on_property_changed(item, 'stroke_style', stroke_style_combo.currentData())
        )
        self._form_layout.addRow(self.tr("Stroke Style:"), stroke_style_combo)

    def _capture_item_state(self, item: QGraphicsItem) -> dict:
        """Capture the current state of an item for undo purposes.

        Args:
            item: The item to capture state from

        Returns:
            Dictionary with all relevant property values
        """
        state = {}
        if hasattr(item, 'object_type'):
            state['object_type'] = item.object_type
        if hasattr(item, 'name'):
            state['name'] = item.name
        if hasattr(item, 'layer_id'):
            state['layer_id'] = item.layer_id
        if hasattr(item, 'fill_color'):
            state['fill_color'] = QColor(item.fill_color) if item.fill_color else None
        if hasattr(item, 'fill_pattern'):
            state['fill_pattern'] = item.fill_pattern
        if hasattr(item, 'stroke_color'):
            state['stroke_color'] = QColor(item.stroke_color) if item.stroke_color else None
        if hasattr(item, 'stroke_width'):
            state['stroke_width'] = item.stroke_width
        if hasattr(item, 'stroke_style'):
            state['stroke_style'] = item.stroke_style
        if hasattr(item, 'path_fence_style'):
            state['path_fence_style'] = item.path_fence_style
        return state

    def _apply_item_state(self, item: QGraphicsItem, state: dict) -> None:
        """Apply a captured state to an item.

        Args:
            item: The item to apply state to
            state: Dictionary with property values
        """
        if 'object_type' in state and hasattr(item, 'object_type'):
            item.object_type = state['object_type']

        if 'name' in state and hasattr(item, 'name'):
            item.name = state['name']
            if hasattr(item, '_update_label'):
                item._update_label()

        if 'layer_id' in state and hasattr(item, 'layer_id'):
            item.layer_id = state['layer_id']
            scene = item.scene()
            if scene and hasattr(scene, 'get_layer_by_id'):
                layer = scene.get_layer_by_id(state['layer_id'])
                if layer:
                    item.setZValue(layer.z_order * 100)

        if 'fill_color' in state and hasattr(item, 'fill_color'):
            item.fill_color = state['fill_color']
        if 'fill_pattern' in state and hasattr(item, 'fill_pattern'):
            item.fill_pattern = state['fill_pattern']
        if 'stroke_color' in state and hasattr(item, 'stroke_color'):
            item.stroke_color = state['stroke_color']
        if 'stroke_width' in state and hasattr(item, 'stroke_width'):
            item.stroke_width = state['stroke_width']
        if 'stroke_style' in state and hasattr(item, 'stroke_style'):
            item.stroke_style = state['stroke_style']
        if 'path_fence_style' in state and hasattr(item, 'path_fence_style'):
            item.path_fence_style = state['path_fence_style']
            if hasattr(item, 'apply_style_preset'):
                item.apply_style_preset()

        # Update visual appearance
        if not isinstance(item, PolylineItem):
            pattern = state.get('fill_pattern', FillPattern.SOLID)
            color = state.get('fill_color') or item.brush().color()
            brush = create_pattern_brush(pattern, color)
            item.setBrush(brush)

        stroke_color = state.get('stroke_color') or item.pen().color()
        stroke_width = state.get('stroke_width', item.pen().widthF())
        stroke_style = state.get('stroke_style', StrokeStyle.SOLID)
        pen = QPen(stroke_color)
        pen.setWidthF(stroke_width)
        pen.setStyle(stroke_style.to_qt_pen_style())
        item.setPen(pen)

        # Update scene
        scene = item.scene()
        if scene:
            scene.update()

    def _on_position_changed(
        self, item: QGraphicsItem, x_spin: QDoubleSpinBox, y_spin: QDoubleSpinBox
    ) -> None:
        """Handle position change with undo support and constraint solving.

        Args:
            item: Item being moved
            x_spin: X coordinate spin box
            y_spin: Y coordinate spin box
        """
        if self._updating:
            return

        from PyQt6.QtCore import QPointF

        from open_garden_planner.core.commands import AlignItemsCommand, MoveItemsCommand

        # Get new position from spin boxes
        # View transform already flips Y, so scene coords = CAD coords (no conversion)
        new_scene_x = x_spin.value()
        new_scene_y = y_spin.value()

        # Get current position (topLeft of bbox = CAD bottom-left)
        bbox = item.boundingRect()
        top_left_local = bbox.topLeft()
        old_top_left_scene = item.mapToScene(top_left_local)

        scene = item.scene()
        if not scene:
            return

        # Calculate delta in scene coordinates
        delta = QPointF(
            new_scene_x - old_top_left_scene.x(),
            new_scene_y - old_top_left_scene.y()
        )

        # Validate bounds - don't allow moving outside canvas area (0, 0, width, height in scene coords)
        canvas_rect = scene.canvas_rect  # QRectF(0, 0, width_cm, height_cm)
        # Calculate where corners would be after the move (in scene coordinates)
        top_left_after = item.mapToScene(bbox.topLeft()) + delta
        bottom_right_after = item.mapToScene(bbox.bottomRight()) + delta

        # Clamp to canvas bounds (not scene bounds with padding)
        if top_left_after.x() < canvas_rect.left():
            delta.setX(delta.x() + (canvas_rect.left() - top_left_after.x()))
        if top_left_after.y() < canvas_rect.top():
            delta.setY(delta.y() + (canvas_rect.top() - top_left_after.y()))
        if bottom_right_after.x() > canvas_rect.right():
            delta.setX(delta.x() - (bottom_right_after.x() - canvas_rect.right()))
        if bottom_right_after.y() > canvas_rect.bottom():
            delta.setY(delta.y() - (bottom_right_after.y() - canvas_rect.bottom()))

        # Skip if no movement
        if abs(delta.x()) < 0.01 and abs(delta.y()) < 0.01:
            return

        # Check if item is constrained
        scene = item.scene()
        if scene and hasattr(scene, 'constraint_graph'):
            from open_garden_planner.ui.canvas.items import GardenItemMixin

            graph = scene.constraint_graph
            if isinstance(item, GardenItemMixin) and graph.constraints:
                # Compute constraint propagation
                constrained_ids = set()
                for c in graph.constraints.values():
                    constrained_ids.add(c.anchor_a.item_id)
                    constrained_ids.add(c.anchor_b.item_id)

                if item.item_id in constrained_ids:
                    # Get canvas view to compute propagation
                    view = scene.views()[0] if scene.views() else None
                    if view and hasattr(view, '_compute_constraint_propagation'):
                        propagated_deltas = view._compute_constraint_propagation([item], delta)

                        if propagated_deltas:
                            # Combine dragged + propagated into per-item deltas
                            all_deltas = [(item, delta)]
                            all_deltas.extend(propagated_deltas)
                            command = AlignItemsCommand(
                                all_deltas, "Move item (constrained)"
                            )
                            if self._command_manager:
                                self._command_manager.execute(command)
                            return

        # No constraints or no propagation - simple move
        command = MoveItemsCommand([item], delta)
        if self._command_manager:
            self._command_manager.execute(command)

    def _on_dimension_changed(
        self,
        item: QGraphicsItem,
        dimension_type: str,
        value: float | None = None,
        width_spin: QDoubleSpinBox | None = None,
        height_spin: QDoubleSpinBox | None = None,
    ) -> None:
        """Handle dimension (width/height/diameter) change with undo support.

        Args:
            item: Item being resized
            dimension_type: 'circle_diameter' or 'rect_size'
            value: New diameter value (for circles)
            width_spin: Width spin box (for rectangles)
            height_spin: Height spin box (for rectangles)
        """
        if self._updating:
            return

        from PyQt6.QtCore import QPointF

        from open_garden_planner.core.commands import ResizeItemCommand

        if dimension_type == 'circle_diameter' and isinstance(item, CircleItem):
            new_diameter = value
            if new_diameter is None or new_diameter <= 0:
                return
            new_radius = new_diameter / 2.0

            old_rect = item.rect()
            old_pos = item.pos()
            old_radius = old_rect.width() / 2.0

            # Keep scene-space center fixed
            center_x = old_pos.x() + old_rect.x() + old_radius
            center_y = old_pos.y() + old_rect.y() + old_radius

            new_pos_x = center_x - new_radius
            new_pos_y = center_y - new_radius

            old_geometry = {
                'rect_x': old_rect.x(),
                'rect_y': old_rect.y(),
                'diameter': old_rect.width(),
                'center_x': old_rect.x() + old_radius,
                'center_y': old_rect.y() + old_radius,
                'radius': old_radius,
                'pos_x': old_pos.x(),
                'pos_y': old_pos.y(),
            }
            new_geometry = {
                'rect_x': 0.0,
                'rect_y': 0.0,
                'diameter': new_diameter,
                'center_x': new_radius,
                'center_y': new_radius,
                'radius': new_radius,
                'pos_x': new_pos_x,
                'pos_y': new_pos_y,
            }

            def apply_circle(itm: QGraphicsItem, geom: dict) -> None:
                if isinstance(itm, CircleItem):
                    itm.setRect(
                        geom['rect_x'], geom['rect_y'],
                        geom['diameter'], geom['diameter'],
                    )
                    itm._center = QPointF(geom['center_x'], geom['center_y'])
                    itm._radius = geom['radius']
                    itm.setPos(geom['pos_x'], geom['pos_y'])
                    itm.update_resize_handles()
                    itm._position_label()
                    itm._update_circle_annotations()

            apply_circle(item, new_geometry)

            if self._command_manager:
                cmd = ResizeItemCommand(item, old_geometry, new_geometry, apply_circle)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)
                self._command_manager.command_executed.emit(cmd.description)

        elif (
            dimension_type == 'rect_size'
            and isinstance(item, RectangleItem)
            and width_spin is not None
            and height_spin is not None
        ):
            new_width = width_spin.value()
            new_height = height_spin.value()
            if new_width <= 0 or new_height <= 0:
                return

            old_rect = item.rect()
            old_pos = item.pos()

            old_geometry = {
                'rect_x': old_rect.x(),
                'rect_y': old_rect.y(),
                'width': old_rect.width(),
                'height': old_rect.height(),
                'pos_x': old_pos.x(),
                'pos_y': old_pos.y(),
            }
            new_geometry = {
                'rect_x': old_rect.x(),
                'rect_y': old_rect.y(),
                'width': new_width,
                'height': new_height,
                'pos_x': old_pos.x(),
                'pos_y': old_pos.y(),
            }

            def apply_rect(itm: QGraphicsItem, geom: dict) -> None:
                if isinstance(itm, RectangleItem):
                    itm.setRect(
                        geom['rect_x'], geom['rect_y'],
                        geom['width'], geom['height'],
                    )
                    itm.setPos(geom['pos_x'], geom['pos_y'])
                    itm.update_resize_handles()
                    itm._position_label()

            apply_rect(item, new_geometry)

            if self._command_manager:
                cmd = ResizeItemCommand(item, old_geometry, new_geometry, apply_rect)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)
                self._command_manager.command_executed.emit(cmd.description)

        else:
            return

        # Update scene and run constraint solver
        scene = item.scene()
        if scene:
            scene.update()
            views = scene.views()
            if views and hasattr(views[0], 'apply_constraint_solver'):
                views[0].apply_constraint_solver()

    def _on_property_changed(self, item: QGraphicsItem, property_name: str, value) -> None:
        """Handle property change with undo support.

        Args:
            item: Item being edited
            property_name: Name of the property
            value: New value
        """
        if self._updating:
            return

        # Capture old state for undo
        old_state = self._capture_item_state(item)

        # Apply the change to the item
        if property_name == 'object_type' and hasattr(item, 'object_type'):
            # Object type change affects many properties
            style = get_style(value)
            new_state = {
                'object_type': value,
                'fill_color': style.fill_color,
                'fill_pattern': style.fill_pattern,
                'stroke_color': style.stroke_color,
                'stroke_width': style.stroke_width,
                'stroke_style': style.stroke_style,
            }
            self._apply_item_state(item, new_state)

            # Create undo command if we have a command manager
            if self._command_manager:
                def apply_func(itm, state):
                    self._apply_item_state(itm, state)
                cmd = ChangePropertyCommand(item, "type", old_state, new_state, apply_func)
                # Don't execute - already applied, just add to stack
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

            # Defer panel refresh to avoid destroying widgets while signal is processing
            QTimer.singleShot(0, lambda: self.set_selected_items([item]))

            # Notify other panels that the object type changed
            QTimer.singleShot(0, self.object_type_changed.emit)

        elif property_name == 'name' and hasattr(item, 'name'):
            old_name = item.name
            item.name = value
            if hasattr(item, '_update_label'):
                item._update_label()

            if self._command_manager:
                def apply_name(itm, val):
                    itm.name = val
                    if hasattr(itm, '_update_label'):
                        itm._update_label()
                cmd = ChangePropertyCommand(item, "name", old_name, value, apply_name)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

        elif property_name == 'label_visible' and hasattr(item, 'label_visible'):
            old_visible = item.label_visible
            item.label_visible = value

            if self._command_manager:
                def apply_label_visible(itm, val):
                    itm.label_visible = val
                cmd = ChangePropertyCommand(item, "label visibility", old_visible, value, apply_label_visible)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

        elif property_name == 'layer_id' and hasattr(item, 'layer_id'):
            old_layer = item.layer_id
            item.layer_id = value
            scene = item.scene()
            if scene and hasattr(scene, 'get_layer_by_id'):
                layer = scene.get_layer_by_id(value)
                if layer:
                    item.setZValue(layer.z_order * 100)

            if self._command_manager:
                def apply_layer(itm, val):
                    itm.layer_id = val
                    sc = itm.scene()
                    if sc and hasattr(sc, 'get_layer_by_id'):
                        lyr = sc.get_layer_by_id(val)
                        if lyr:
                            itm.setZValue(lyr.z_order * 100)
                cmd = ChangePropertyCommand(item, "layer", old_layer, value, apply_layer)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

        elif property_name == 'fill_pattern':
            old_pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
            if hasattr(item, 'fill_pattern'):
                item.fill_pattern = value
            color = item.fill_color if hasattr(item, 'fill_color') and item.fill_color else item.brush().color()
            brush = create_pattern_brush(value, color)
            item.setBrush(brush)

            if self._command_manager:
                def apply_pattern(itm, val):
                    if hasattr(itm, 'fill_pattern'):
                        itm.fill_pattern = val
                    c = itm.fill_color if hasattr(itm, 'fill_color') and itm.fill_color else itm.brush().color()
                    itm.setBrush(create_pattern_brush(val, c))
                cmd = ChangePropertyCommand(item, "fill pattern", old_pattern, value, apply_pattern)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

        elif property_name == 'stroke_width':
            old_width = item.stroke_width if hasattr(item, 'stroke_width') else item.pen().widthF()
            if hasattr(item, 'stroke_width'):
                item.stroke_width = value
            pen = item.pen()
            pen.setWidthF(value)
            item.setPen(pen)

            if self._command_manager:
                def apply_width(itm, val):
                    if hasattr(itm, 'stroke_width'):
                        itm.stroke_width = val
                    p = itm.pen()
                    p.setWidthF(val)
                    itm.setPen(p)
                cmd = ChangePropertyCommand(item, "stroke width", old_width, value, apply_width)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

        elif property_name == 'stroke_style':
            old_style = item.stroke_style if hasattr(item, 'stroke_style') else StrokeStyle.SOLID
            if hasattr(item, 'stroke_style'):
                item.stroke_style = value
            pen = item.pen()
            pen.setStyle(value.to_qt_pen_style())
            item.setPen(pen)

            if self._command_manager:
                def apply_stroke_style(itm, val):
                    if hasattr(itm, 'stroke_style'):
                        itm.stroke_style = val
                    p = itm.pen()
                    p.setStyle(val.to_qt_pen_style())
                    itm.setPen(p)
                cmd = ChangePropertyCommand(item, "stroke style", old_style, value, apply_stroke_style)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

        elif property_name == 'path_fence_style':
            old_pfs = item.path_fence_style if hasattr(item, 'path_fence_style') else PathFenceStyle.NONE
            if hasattr(item, 'path_fence_style'):
                item.path_fence_style = value
            if hasattr(item, 'apply_style_preset'):
                item.apply_style_preset()
            item.update()

            if self._command_manager:
                def apply_pfs(itm, val):
                    if hasattr(itm, 'path_fence_style'):
                        itm.path_fence_style = val
                    if hasattr(itm, 'apply_style_preset'):
                        itm.apply_style_preset()
                    itm.update()
                cmd = ChangePropertyCommand(item, "path/fence style", old_pfs, value, apply_pfs)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

        # Mark scene as modified
        scene = item.scene()
        if scene:
            scene.update()

    def _on_color_changed(self, item: QGraphicsItem, property_name: str, button: ColorButton) -> None:
        """Handle color button change with undo support.

        Args:
            item: Item being edited
            property_name: Name of the color property ('fill_color' or 'stroke_color')
            button: The color button that was changed
        """
        if self._updating:
            return

        color = button.color

        if property_name == 'fill_color':
            # Capture old value for undo
            old_color = QColor(item.fill_color) if hasattr(item, 'fill_color') and item.fill_color else item.brush().color()

            # Store the color
            if hasattr(item, 'fill_color'):
                item.fill_color = color
            # Apply to brush
            pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
            brush = create_pattern_brush(pattern, color)
            item.setBrush(brush)

            # Create undo command
            if self._command_manager:
                def apply_fill_color(itm, val):
                    if hasattr(itm, 'fill_color'):
                        itm.fill_color = val
                    p = itm.fill_pattern if hasattr(itm, 'fill_pattern') else FillPattern.SOLID
                    itm.setBrush(create_pattern_brush(p, val))
                cmd = ChangePropertyCommand(item, "fill color", old_color, color, apply_fill_color)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

        elif property_name == 'stroke_color':
            # Capture old value for undo
            old_color = QColor(item.stroke_color) if hasattr(item, 'stroke_color') and item.stroke_color else item.pen().color()

            # Store the color
            if hasattr(item, 'stroke_color'):
                item.stroke_color = color
            # Apply to pen
            pen = item.pen()
            pen.setColor(color)
            item.setPen(pen)

            # Create undo command
            if self._command_manager:
                def apply_stroke_color(itm, val):
                    if hasattr(itm, 'stroke_color'):
                        itm.stroke_color = val
                    p = itm.pen()
                    p.setColor(val)
                    itm.setPen(p)
                cmd = ChangePropertyCommand(item, "stroke color", old_color, color, apply_stroke_color)
                self._command_manager._undo_stack.append(cmd)
                self._command_manager._redo_stack.clear()
                self._command_manager.can_undo_changed.emit(True)
                self._command_manager.can_redo_changed.emit(False)

        # Mark scene as modified
        scene = item.scene()
        if scene:
            scene.update()
