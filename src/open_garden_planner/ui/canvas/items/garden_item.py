"""Base mixin for garden canvas items."""

import uuid
from typing import Any

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType


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
    ) -> None:
        """Initialize the garden item mixin.

        Args:
            object_type: Type of property object (optional)
            name: Optional name/label for the object
            metadata: Optional metadata dictionary
            fill_pattern: Fill pattern (optional, defaults to pattern from object type)
            fill_color: Base fill color (optional, used with patterns)
        """
        self._item_id = uuid.uuid4()
        self._object_type = object_type
        self._name = name
        self._metadata = metadata or {}
        self._fill_pattern = fill_pattern
        self._fill_color = fill_color  # Store base color for serialization

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
