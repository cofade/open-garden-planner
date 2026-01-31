"""Properties dialog for editing object attributes."""

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType, StrokeStyle, get_style
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    PolygonItem,
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
        self.setFixedSize(80, 30)
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
        # Use rgba() to show color with alpha
        self.setStyleSheet(
            f"background-color: rgba({self._color.red()}, {self._color.green()}, "
            f"{self._color.blue()}, {self._color.alpha() / 255.0}); "
            f"border: 1px solid #888;"
        )

    def _pick_color(self) -> None:
        """Open color picker dialog."""
        # Create color dialog as top-level window (no parent) to avoid inheriting
        # the colored background from this ColorButton
        dialog = QColorDialog()
        dialog.setCurrentColor(self._color)
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setWindowTitle("Choose Color")

        # Execute dialog
        if dialog.exec():
            color = dialog.selectedColor()
            if color.isValid():
                self.set_color(color)


class PropertiesDialog(QDialog):
    """Dialog for editing object properties."""

    def __init__(self, item: QGraphicsItem, parent: QWidget | None = None) -> None:
        """Initialize the properties dialog.

        Args:
            item: The graphics item to edit
            parent: Parent widget
        """
        super().__init__(parent)
        self._item = item
        self._fill_color_button: ColorButton | None = None
        self._stroke_color_button: ColorButton | None = None
        self._fill_pattern_combo: QComboBox | None = None
        self._stroke_width_spin: QDoubleSpinBox | None = None
        self._stroke_style_combo: QComboBox | None = None
        self._layer_combo: QComboBox | None = None

        self.setWindowTitle("Object Properties")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout()

        # Basic info section
        layout.addWidget(self._create_basic_info_section())

        # Appearance section
        layout.addWidget(self._create_appearance_section())

        # Metadata section (if available)
        if hasattr(self._item, 'metadata') and self._item.metadata:
            layout.addWidget(self._create_metadata_section())

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _create_basic_info_section(self) -> QGroupBox:
        """Create the basic information section."""
        group = QGroupBox("Basic Information")
        layout = QFormLayout()

        # Object type dropdown
        if hasattr(self._item, 'object_type'):
            self._object_type_combo = QComboBox()

            # Determine which object types are valid for this item
            if isinstance(self._item, (RectangleItem, PolygonItem, CircleItem)):
                # All filled shapes can be any structure type
                valid_types = [
                    ObjectType.GENERIC_RECTANGLE if isinstance(self._item, RectangleItem) else (
                        ObjectType.GENERIC_CIRCLE if isinstance(self._item, CircleItem) else ObjectType.GENERIC_POLYGON
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
            else:
                # Default to all types
                valid_types = list(ObjectType)

            # Populate combobox
            current_idx = 0
            for idx, obj_type in enumerate(valid_types):
                style = get_style(obj_type)
                self._object_type_combo.addItem(style.display_name, obj_type)
                if self._item.object_type == obj_type:
                    current_idx = idx

            self._object_type_combo.setCurrentIndex(current_idx)
            # Connect to update colors/patterns when object type changes
            self._object_type_combo.currentIndexChanged.connect(self._on_object_type_changed)
            layout.addRow("Type:", self._object_type_combo)

        # Name/label
        if hasattr(self._item, 'name'):
            self._name_edit = QLineEdit(self._item.name)
            layout.addRow("Name:", self._name_edit)

        # Layer selection
        if hasattr(self._item, 'layer_id'):
            self._layer_combo = QComboBox()

            # Get layers from scene
            scene = self._item.scene()
            if scene and hasattr(scene, 'layers'):
                current_idx = 0
                for idx, layer in enumerate(scene.layers):
                    self._layer_combo.addItem(layer.name, layer.id)
                    # Select current layer
                    if hasattr(self._item, 'layer_id') and self._item.layer_id == layer.id:
                        current_idx = idx

                self._layer_combo.setCurrentIndex(current_idx)
                layout.addRow("Layer:", self._layer_combo)

        group.setLayout(layout)
        return group

    def _create_appearance_section(self) -> QGroupBox:
        """Create the appearance customization section."""
        group = QGroupBox("Appearance")
        layout = QFormLayout()

        # Get current fill color
        current_fill = self._get_current_fill_color()

        # Fill color picker
        self._fill_color_button = ColorButton(current_fill)
        layout.addRow("Fill Color:", self._fill_color_button)

        # Fill pattern selector
        self._fill_pattern_combo = QComboBox()
        for pattern in FillPattern:
            # Format the pattern name for display (e.g., GRASS -> Grass)
            display_name = pattern.name.replace("_", " ").title()
            self._fill_pattern_combo.addItem(display_name, pattern)

        # Set current pattern (default to SOLID if can't determine)
        current_pattern = self._get_current_fill_pattern()
        for i in range(self._fill_pattern_combo.count()):
            if self._fill_pattern_combo.itemData(i) == current_pattern:
                self._fill_pattern_combo.setCurrentIndex(i)
                break

        layout.addRow("Fill Pattern:", self._fill_pattern_combo)

        # Stroke/outline controls
        current_stroke = self._get_current_stroke_color()
        self._stroke_color_button = ColorButton(current_stroke)
        layout.addRow("Stroke Color:", self._stroke_color_button)

        # Stroke width
        self._stroke_width_spin = QDoubleSpinBox()
        self._stroke_width_spin.setRange(0.5, 20.0)
        self._stroke_width_spin.setSingleStep(0.5)
        self._stroke_width_spin.setDecimals(1)
        self._stroke_width_spin.setSuffix(" px")
        self._stroke_width_spin.setValue(self._get_current_stroke_width())
        layout.addRow("Stroke Width:", self._stroke_width_spin)

        # Stroke style
        self._stroke_style_combo = QComboBox()
        for style in StrokeStyle:
            # Format the style name for display
            display_name = style.name.replace("_", " ").title()
            self._stroke_style_combo.addItem(display_name, style)

        # Set current stroke style
        current_stroke_style = self._get_current_stroke_style()
        for i in range(self._stroke_style_combo.count()):
            if self._stroke_style_combo.itemData(i) == current_stroke_style:
                self._stroke_style_combo.setCurrentIndex(i)
                break

        layout.addRow("Stroke Style:", self._stroke_style_combo)

        group.setLayout(layout)
        return group

    def _create_metadata_section(self) -> QGroupBox:
        """Create metadata section."""
        group = QGroupBox("Additional Information")
        layout = QFormLayout()

        if hasattr(self._item, 'metadata'):
            for key, value in self._item.metadata.items():
                layout.addRow(f"{key}:", QLabel(str(value)))

        group.setLayout(layout)
        return group

    def _get_current_fill_color(self) -> QColor:
        """Get the current fill color of the item."""
        # First check if item has a stored fill_color (important for patterned brushes)
        if hasattr(self._item, 'fill_color') and self._item.fill_color is not None:
            return self._item.fill_color
        # Otherwise get it from the brush
        if isinstance(self._item, (RectangleItem, PolygonItem, CircleItem)):
            return self._item.brush().color()
        return QColor(200, 200, 200)  # Default gray

    def _get_current_fill_pattern(self) -> FillPattern:
        """Get the current fill pattern of the item.

        Returns:
            Current fill pattern or SOLID as default
        """
        # First check if item has a stored fill_pattern
        if hasattr(self._item, 'fill_pattern') and self._item.fill_pattern is not None:
            return self._item.fill_pattern
        # Otherwise try to get pattern from object type style
        if hasattr(self._item, 'object_type') and self._item.object_type:
            style = get_style(self._item.object_type)
            return style.fill_pattern
        return FillPattern.SOLID

    def _get_current_stroke_color(self) -> QColor:
        """Get the current stroke color of the item."""
        # First check if item has a stored stroke_color
        if hasattr(self._item, 'stroke_color') and self._item.stroke_color is not None:
            return self._item.stroke_color
        # Otherwise get it from the pen
        if isinstance(self._item, (RectangleItem, PolygonItem, CircleItem)):
            return self._item.pen().color()
        return QColor(0, 0, 0)  # Default black

    def _get_current_stroke_width(self) -> float:
        """Get the current stroke width of the item."""
        # First check if item has a stored stroke_width
        if hasattr(self._item, 'stroke_width') and self._item.stroke_width is not None:
            return self._item.stroke_width
        # Otherwise get it from the pen
        if isinstance(self._item, (RectangleItem, PolygonItem, CircleItem)):
            return self._item.pen().widthF()
        return 2.0  # Default width

    def _get_current_stroke_style(self) -> StrokeStyle:
        """Get the current stroke style of the item.

        Returns:
            Current stroke style or SOLID as default
        """
        # First check if item has a stored stroke_style
        if hasattr(self._item, 'stroke_style') and self._item.stroke_style is not None:
            return self._item.stroke_style
        # Otherwise try to get style from object type
        if hasattr(self._item, 'object_type') and self._item.object_type:
            style = get_style(self._item.object_type)
            return style.stroke_style
        return StrokeStyle.SOLID

    def get_object_type(self) -> ObjectType | None:
        """Get the selected object type.

        Returns:
            Selected object type or None
        """
        if hasattr(self, '_object_type_combo'):
            return self._object_type_combo.currentData()
        return None

    def get_fill_color(self) -> QColor:
        """Get the selected fill color.

        Returns:
            Selected fill color
        """
        if self._fill_color_button:
            return self._fill_color_button.color
        return self._get_current_fill_color()

    def get_fill_pattern(self) -> FillPattern:
        """Get the selected fill pattern.

        Returns:
            Selected fill pattern
        """
        if self._fill_pattern_combo:
            return self._fill_pattern_combo.currentData()
        return FillPattern.SOLID

    def get_name(self) -> str:
        """Get the object name.

        Returns:
            Object name
        """
        if hasattr(self, '_name_edit'):
            return self._name_edit.text()
        return ""

    def get_layer_id(self):
        """Get the selected layer ID.

        Returns:
            Selected layer ID (UUID) or None
        """
        if self._layer_combo:
            return self._layer_combo.currentData()
        return None

    def get_stroke_color(self) -> QColor:
        """Get the selected stroke color.

        Returns:
            Selected stroke color
        """
        if self._stroke_color_button:
            return self._stroke_color_button.color
        return self._get_current_stroke_color()

    def get_stroke_width(self) -> float:
        """Get the selected stroke width.

        Returns:
            Selected stroke width
        """
        if self._stroke_width_spin:
            return self._stroke_width_spin.value()
        return self._get_current_stroke_width()

    def get_stroke_style(self) -> StrokeStyle:
        """Get the selected stroke style.

        Returns:
            Selected stroke style
        """
        if self._stroke_style_combo:
            return self._stroke_style_combo.currentData()
        return StrokeStyle.SOLID

    def _on_object_type_changed(self, _index: int) -> None:
        """Handle object type change - update color and pattern to new type's defaults.

        Args:
            _index: The new combo box index (unused, but required by Qt signal)
        """
        if not hasattr(self, '_object_type_combo'):
            return

        # Get the new object type
        new_type = self._object_type_combo.currentData()
        if not new_type:
            return

        # Get the style for the new type
        style = get_style(new_type)

        # Update the fill color button to show the new default color
        if self._fill_color_button:
            self._fill_color_button.set_color(style.fill_color)

        # Update the pattern selector to show the new default pattern
        if self._fill_pattern_combo:
            for i in range(self._fill_pattern_combo.count()):
                if self._fill_pattern_combo.itemData(i) == style.fill_pattern:
                    self._fill_pattern_combo.setCurrentIndex(i)
                    break

        # Update the stroke color button to show the new default color
        if self._stroke_color_button:
            self._stroke_color_button.set_color(style.stroke_color)

        # Update the stroke width
        if self._stroke_width_spin:
            self._stroke_width_spin.setValue(style.stroke_width)

        # Update the stroke style selector to show the new default style
        if self._stroke_style_combo:
            for i in range(self._stroke_style_combo.count()):
                if self._stroke_style_combo.itemData(i) == style.stroke_style:
                    self._stroke_style_combo.setCurrentIndex(i)
                    break
