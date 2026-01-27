"""Base mixin for garden canvas items."""

import uuid


class GardenItemMixin:
    """Mixin providing common functionality for garden items.

    Provides:
        - Unique identifier (UUID)
        - Future: name, metadata, serialization
    """

    def __init__(self) -> None:
        """Initialize the garden item mixin."""
        self._item_id = uuid.uuid4()

    @property
    def item_id(self) -> uuid.UUID:
        """Unique identifier for this item."""
        return self._item_id

    @property
    def item_id_str(self) -> str:
        """String representation of item ID."""
        return str(self._item_id)
