"""Built-in snap providers."""

from open_garden_planner.core.snap.providers.anchor import (
    CenterSnapProvider,
    EdgeCardinalSnapProvider,
    EndpointSnapProvider,
)
from open_garden_planner.core.snap.providers.intersection import (
    IntersectionSnapProvider,
)
from open_garden_planner.core.snap.providers.midpoint import MidpointSnapProvider
from open_garden_planner.core.snap.providers.nearest import NearestSnapProvider
from open_garden_planner.core.snap.providers.perpendicular import (
    PerpendicularSnapProvider,
)

__all__ = [
    "CenterSnapProvider",
    "EdgeCardinalSnapProvider",
    "EndpointSnapProvider",
    "IntersectionSnapProvider",
    "MidpointSnapProvider",
    "NearestSnapProvider",
    "PerpendicularSnapProvider",
]
