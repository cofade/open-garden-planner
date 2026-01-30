"""Layer model for organizing objects."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass
class Layer:
    """Represents a layer for organizing objects.

    Attributes:
        id: Unique identifier for the layer
        name: Display name of the layer
        visible: Whether the layer is visible
        locked: Whether the layer is locked (prevents editing)
        opacity: Layer opacity (0.0 to 1.0)
        z_order: Stacking order (higher values appear on top)
    """

    id: UUID = field(default_factory=uuid4)
    name: str = "Layer"
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    z_order: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize layer to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "visible": self.visible,
            "locked": self.locked,
            "opacity": self.opacity,
            "z_order": self.z_order,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Layer":
        """Deserialize layer from dictionary."""
        return Layer(
            id=UUID(data["id"]),
            name=data["name"],
            visible=data.get("visible", True),
            locked=data.get("locked", False),
            opacity=data.get("opacity", 1.0),
            z_order=data.get("z_order", 0),
        )


def create_default_layers() -> list[Layer]:
    """Create the default set of layers for a new project."""
    return [Layer(name="Layer 1", z_order=0)]
