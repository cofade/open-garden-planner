"""Base mixin for garden canvas items."""

import uuid
from typing import Any

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QGraphicsTextItem

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType, StrokeStyle


class GardenItemMixin:
    """Mixin providing common functionality for garden items.

    Provides:
        - Unique identifier (UUID)
        - Object type classification
        - Name/label
        - Layer assignment
        - Extensible metadata
    """

    def __init__(
        self,
        object_type: ObjectType | None = None,
        name: str = "",
        metadata: dict[str, Any] | None = None,
        fill_pattern: FillPattern | None = None,
        fill_color: Any = None,  # QColor, but avoiding import
        stroke_color: Any = None,  # QColor, but avoiding import
        stroke_width: float | None = None,
        stroke_style: StrokeStyle | None = None,
        layer_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize the garden item mixin.

        Args:
            object_type: Type of property object (optional)
            name: Optional name/label for the object
            metadata: Optional metadata dictionary
            fill_pattern: Fill pattern (optional, defaults to pattern from object type)
            fill_color: Base fill color (optional, used with patterns)
            stroke_color: Stroke/outline color (optional)
            stroke_width: Stroke/outline width (optional)
            stroke_style: Stroke/outline style (optional)
            layer_id: Layer ID this item belongs to (optional)
        """
        self._item_id = uuid.uuid4()
        self._object_type = object_type
        self._name = name
        self._metadata = metadata or {}
        self._fill_pattern = fill_pattern
        self._fill_color = fill_color  # Store base color for serialization
        self._stroke_color = stroke_color
        self._stroke_width = stroke_width
        self._stroke_style = stroke_style
        self._layer_id = layer_id
        self._label_item: QGraphicsTextItem | None = None

    @property
    def item_id(self) -> uuid.UUID:
        """Unique identifier for this item."""
        return self._item_id

    @property
    def item_id_str(self) -> str:
        """String representation of item ID."""
        return str(self._item_id)

    @property
    def object_type(self) -> ObjectType | None:
        """Type of property object."""
        return self._object_type

    @object_type.setter
    def object_type(self, value: ObjectType | None) -> None:
        """Set the object type."""
        self._object_type = value

    @property
    def name(self) -> str:
        """Name/label of the object."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set the name/label."""
        self._name = value
        self._update_label()

    @property
    def metadata(self) -> dict[str, Any]:
        """Extensible metadata dictionary."""
        return self._metadata

    @property
    def fill_pattern(self) -> FillPattern | None:
        """Fill pattern for this item."""
        return self._fill_pattern

    @fill_pattern.setter
    def fill_pattern(self, value: FillPattern | None) -> None:
        """Set the fill pattern."""
        self._fill_pattern = value

    @property
    def fill_color(self) -> Any | None:  # QColor, but avoiding import
        """Base fill color for this item."""
        return self._fill_color

    @fill_color.setter
    def fill_color(self, value: Any) -> None:  # QColor, but avoiding import
        """Set the base fill color."""
        self._fill_color = value

    @property
    def stroke_color(self) -> Any | None:  # QColor, but avoiding import
        """Stroke/outline color for this item."""
        return self._stroke_color

    @stroke_color.setter
    def stroke_color(self, value: Any) -> None:  # QColor, but avoiding import
        """Set the stroke/outline color."""
        self._stroke_color = value

    @property
    def stroke_width(self) -> float | None:
        """Stroke/outline width for this item."""
        return self._stroke_width

    @stroke_width.setter
    def stroke_width(self, value: float) -> None:
        """Set the stroke/outline width."""
        self._stroke_width = value

    @property
    def stroke_style(self) -> StrokeStyle | None:
        """Stroke/outline style for this item."""
        return self._stroke_style

    @stroke_style.setter
    def stroke_style(self, value: StrokeStyle | None) -> None:
        """Set the stroke/outline style."""
        self._stroke_style = value

    @property
    def layer_id(self) -> uuid.UUID | None:
        """Layer ID this item belongs to."""
        return self._layer_id

    @layer_id.setter
    def layer_id(self, value: uuid.UUID | None) -> None:
        """Set the layer ID."""
        self._layer_id = value

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a metadata value.

        Args:
            key: Metadata key
            value: Metadata value
        """
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value.

        Args:
            key: Metadata key
            default: Default value if key not found

        Returns:
            Metadata value or default
        """
        return self._metadata.get(key, default)

    def _create_label(self) -> None:
        """Create the label text item if it doesn't exist."""
        if self._label_item is None:
            # Create label as a child item
            # TYPE_CHECKING guard to help type checker understand self has QGraphicsItem methods
            if not hasattr(self, 'boundingRect'):
                return

            self._label_item = QGraphicsTextItem(self._name, self)  # type: ignore[arg-type]

            # Configure label appearance
            font = QFont("Arial", 10)
            font.setBold(True)
            self._label_item.setFont(font)
            self._label_item.setDefaultTextColor(QColor(0, 0, 0))  # Black text

            # Add white background for readability
            self._label_item.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations)

            # Position the label
            self._position_label()

    def _update_label(self) -> None:
        """Update or create label based on current name."""
        if self._name:
            if self._label_item is None:
                self._create_label()
            else:
                self._label_item.setPlainText(self._name)
                self._position_label()
        else:
            # Remove label if name is empty
            if self._label_item is not None:
                self._label_item.setParentItem(None)
                if hasattr(self, 'scene') and callable(self.scene):  # type: ignore[attr-defined]
                    scene = self.scene()  # type: ignore[attr-defined]
                    if scene is not None:
                        scene.removeItem(self._label_item)
                self._label_item = None

    def _position_label(self) -> None:
        """Position the label at the center of the item's bounding rect."""
        if self._label_item is None:
            return

        # TYPE_CHECKING guard to help type checker
        if not hasattr(self, 'boundingRect'):
            return

        # Get the bounding rectangle
        bounds = self.boundingRect()  # type: ignore[attr-defined]

        # Position label at the center-bottom of the object
        label_rect = self._label_item.boundingRect()
        x = bounds.center().x() - label_rect.width() / 2
        y = bounds.center().y() - label_rect.height() / 2

        self._label_item.setPos(x, y)

    def initialize_label(self) -> None:
        """Initialize the label after the item is fully constructed.

        This should be called by subclasses after they complete their initialization.
        """
        if self._name:
            self._create_label()
