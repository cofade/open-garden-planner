"""Which way a top-down object sprite faces — one rule for 2D and 3D (#776).

Every illustrated object is drawn for a NATURAL footprint: a wheelbarrow is
60 x 140 cm (portrait), a bench 180 x 60 cm (landscape), a table 150 x 100.
Drawn into a rectangle of the opposite proportions the picture was simply
stretched, so a wheelbarrow on a wide rectangle looked squashed and a lounger on
a short one looked flattened. Since #776 the picture TURNS instead: the sprite
is rendered at the swapped size and rotated a quarter turn, so its long axis
always follows the item's long axis.

The rule is deliberately conservative:

- a near-square natural art or a near-square target never turns (there is no
  long axis to follow);
- a turn happens only when the natural and target aspects are OPPOSITE
  (landscape vs portrait), never for two landscape or two portrait shapes —
  stretching along the same axis is what the sprite is for.

This module is Qt-free. It owns the natural sizes (``NATURAL_SIZE_CM``), which
``core.furniture_renderer`` turns into the renderer's default dimensions, and
the 3D kit (``core.scene3d.builders.kit.object_box``) reads the same function to
build the model in the un-turned frame and rotate it to the item.
"""

from __future__ import annotations

import math
from typing import Final

#: A natural footprint this close to square has no long axis to follow.
ASPECT_TOLERANCE: Final = 1.05

#: Each illustrated object's natural footprint in cm (width, height), keyed by
#: ObjectType name. These ARE the renderer's default dimensions and the sprite
#: viewBoxes (``tests/unit/test_object_sprite_conformance.py``); a parametric
#: picture (the pergola) states its default here too, although it never turns.
NATURAL_SIZE_CM: Final[dict[str, tuple[float, float]]] = {
    "TABLE_RECTANGULAR": (150.0, 100.0),
    "TABLE_ROUND": (100.0, 100.0),
    "CHAIR": (50.0, 50.0),
    "BENCH": (180.0, 60.0),
    "PARASOL": (300.0, 300.0),
    "LOUNGER": (70.0, 190.0),
    "BBQ_GRILL": (80.0, 80.0),  # circle-tool object → square footprint (#308)
    "FIRE_PIT": (100.0, 100.0),
    "PLANTER_POT": (50.0, 50.0),
    # Infrastructure
    "RAISED_BED": (120.0, 80.0),
    "COMPOST_BIN": (100.0, 100.0),
    "COLD_FRAME": (120.0, 60.0),
    "RAIN_BARREL": (60.0, 60.0),
    "WATER_TAP": (20.0, 20.0),
    "TOOL_SHED": (200.0, 150.0),
    # Package 3a roster (#308)
    "SANDBOX": (150.0, 150.0),
    "TRAMPOLINE": (300.0, 300.0),
    "HOT_TUB": (220.0, 220.0),
    "SWING": (200.0, 150.0),
    "PICNIC_TABLE": (180.0, 150.0),
    "HAMMOCK": (300.0, 120.0),
    "WHEELBARROW": (60.0, 140.0),
    "PERGOLA": (300.0, 300.0),
    "BIRD_BATH": (50.0, 50.0),
    # Garden lights (Phase 17 L5.4)
    "GARDEN_LIGHT": (40.0, 40.0),
}


def _finite_positive(*values: float) -> bool:
    return all(math.isfinite(value) and value > 0.0 for value in values)


def _landscape(width: float, height: float) -> bool:
    return width >= height * ASPECT_TOLERANCE


def _portrait(width: float, height: float) -> bool:
    return height >= width * ASPECT_TOLERANCE


def sprite_turn_deg(kind: str, width: float, height: float) -> float:
    """The quarter turn (0 or 90 degrees, clockwise) a sprite of ``kind`` needs
    to keep its natural long axis along the target's long axis (#776).

    ``width``/``height`` are the item's target footprint in cm (its rectangle,
    or the local bounding box of a polygon). 0 when the kind has no natural art,
    either shape is near-square, or both are the same aspect — the sprite is
    stretched, as before.
    """
    natural = NATURAL_SIZE_CM.get(kind)
    if natural is None or not _finite_positive(width, height):
        return 0.0
    natural_width, natural_height = natural
    if not _finite_positive(natural_width, natural_height):
        return 0.0
    if (_landscape(natural_width, natural_height) and _portrait(width, height)) or (
        _portrait(natural_width, natural_height) and _landscape(width, height)
    ):
        return 90.0
    return 0.0


__all__ = ["ASPECT_TOLERANCE", "NATURAL_SIZE_CM", "sprite_turn_deg"]
