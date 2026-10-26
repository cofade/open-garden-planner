"""Illustrative heights for built objects the plan gives no height (Phase 17 L4, #388).

The 2D height resolver (``core/object_height``) deliberately gives some object
kinds NO height: a parasol, a fire pit, a rain barrel, a pergola. The 2D sun
study then casts no shadow for them, and until L4 the 3D view showed nothing but
their sprite painted flat on the ground. L4 builds every furniture and
infrastructure object in 3D, so those kinds need a height to be BUILT at.

This module is that one table — the object twin of ``core/plant_height_estimate``
(#557), under the same contract:

- The values are ILLUSTRATIVE, not measured. They are never written into the
  item's metadata or the saved plan; ``effective_height_cm`` keeps answering
  ``None`` for these kinds (unknown stays unknown), so the 2D shadow overlay
  and the hours-of-sun map are unchanged.
- The estimate lives only on the transient 3D record
  (``params["estimated_height_cm"]``, the key the plant estimate uses), and the
  3D info card labels it "(estimated)".
- Unlike an estimated PLANT (#557, an owner decision for plants), an estimated
  OBJECT is decoration in 3D and casts NO shadow: the built world's rule "no
  height, no shadow" (ADR-059 addendum L1.6, decision 3) — the 3D view must not
  shade the ground where the 2D sun study says the sun shines. A user who sets an
  explicit height gets a solid that casts, as for every other object.

Standard library only: imported by the snapshot (GUI side) and read by the
Qt-free builders.
"""

from __future__ import annotations

from typing import Final

from .plant_height_estimate import ESTIMATED_HEIGHT_PARAM

__all__ = ["ESTIMATED_HEIGHT_PARAM", "ESTIMATED_OBJECT_HEIGHTS_CM", "estimated_object_height_cm"]

#: Illustrative heights in cm per ObjectType name — only for kinds the 2D resolver
#: gives no height of their own (``object_height.DEFAULT_HEIGHTS_CM`` has no entry;
#: a drift test holds the two tables disjoint). Typical central-European garden
#: values: a market parasol's canopy top, a fire bowl's rim, a 200 l barrel, a
#: standpipe tap, an A-frame swing's top beam, a hammock stand's hooks, a pergola's
#: rafters, a cold frame's high back, a large planter's rim.
ESTIMATED_OBJECT_HEIGHTS_CM: Final[dict[str, float]] = {
    "PARASOL": 250.0,
    "FIRE_PIT": 30.0,
    "PLANTER_POT": 50.0,
    "COLD_FRAME": 45.0,
    "RAIN_BARREL": 100.0,
    "WATER_TAP": 80.0,
    "SWING": 220.0,
    "HAMMOCK": 110.0,
    "PERGOLA": 250.0,
}


def estimated_object_height_cm(kind: str) -> float | None:
    """The illustrative height of an object of ``kind`` (an ObjectType name) that the
    plan gives no height, or None for a kind this table does not cover."""
    return ESTIMATED_OBJECT_HEIGHTS_CM.get(kind)
