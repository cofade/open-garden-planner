"""Base mixin for garden canvas items."""

import uuid
from typing import Any

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType, StrokeStyle


class GardenItemMixin:
    """Mixin providing common functionality for garden items.

    Provides:
        - Unique identifier (UUID)
        - Object type classification
        - Name/label
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
