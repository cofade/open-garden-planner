"""Single source of truth for plant sizing precedence.

A plant's size is governed by three independent quantities that used to have
their precedence re-encoded in three places (``garden_item`` resolver,
``circle_item`` paint/boundingRect ring gate, and the species-assignment
helper). This module collapses that into one documented value object so the
rules live in exactly one file (issue #218).

The three quantities:

* **footprint** — the drawn circle radius (``CircleItem._radius``).
* **spacing override** — a user-set planting distance (``spacing_radius_cm``),
  or ``None`` for "use the database".
* **max_spread_cm** — the database value from ``metadata["plant_species"]``.

Precedence (unchanged behaviour, see ``PlantSizing.effective_spacing_radius_cm``):
the manual override wins; otherwise the database ``max_spread_cm / 2``; otherwise
there is no spacing data. The spacing ring is drawn only when the effective
spacing radius exceeds the drawn footprint (a ring that would sit inside the
footprint conveys nothing — the footprint already shows that size).

This module is intentionally Qt-free so the precedence can be unit-tested in
isolation.

US-E8 note — a fourth size input this module deliberately does NOT own: the
plant's measured ``plant_instance["current_spread_cm"]``, read by
``core/growth_model`` and the shadow/3D canopy. It does **not** affect the
spacing ring or the spacing-overlap diagnostic, which stay on the MATURE
``max_spread_cm`` — spacing is a planning-for-maturity rule, so shrinking it
to a sapling's current canopy would let the user plant too densely.

Update (issue #299): the drawn circle's own SVG icon is no longer part of
this module's "stays mature" guarantee either — ``CircleItem`` renders it at
the growth-model size when available (``_visual_plant_diameter_cm``), while
``rect()``/``radius`` (what THIS module reads) stay exactly as documented
above. One plant can therefore legitimately show FOUR different sizes at
once: the drawn circle's *geometry* (selection/snapping/spacing, still owned
by this module), a mature spacing ring (also this module), a
growth-sized icon (owned by ``CircleItem``, cosmetic only — never read by
anything in this module), and a growth-sized shadow canopy (owned by
``core/growth_model`` + the sun/shade views). The four are independent by
design; this module's job is only ever the first two.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol


def _positive_number(value: Any) -> float | None:
    """Coerce ``value`` to a positive float, or ``None`` if it is not one.

    The single home for "is this a usable size?" — guards every ``max_spread_cm``
    read so a missing/zero/non-numeric value degrades to "no data" instead of
    raising (``bool`` is rejected so ``True`` is never mistaken for ``1``).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


class _SizedPlant(Protocol):
    """The duck-typed surface ``sizing_for_item`` reads (a plant ``CircleItem``)."""

    @property
    def radius(self) -> float: ...
    @property
    def spacing_radius_cm(self) -> float | None: ...
    @property
    def metadata(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class PlantSizing:
    """Resolved view of a plant's three sizing quantities and their precedence."""

    footprint_radius_cm: float
    spacing_override_cm: float | None
    db_max_spread_cm: float | None

    @property
    def effective_spacing_radius_cm(self) -> float | None:
        """The planting-distance radius in cm, or ``None`` when no data exists.

        Precedence: user override > ``max_spread_cm / 2`` > ``None`` — identical
        to the historical ``GardenItemMixin.effective_spacing_radius()``.
        """
        if self.spacing_override_cm is not None:
            return self.spacing_override_cm
        db = _positive_number(self.db_max_spread_cm)
        return db / 2.0 if db is not None else None

    @property
    def spacing_source(self) -> str:
        """Where the effective spacing radius comes from: ``override``/``database``/``none``."""
        if self.spacing_override_cm is not None:
            return "override"
        if _positive_number(self.db_max_spread_cm) is not None:
            return "database"
        return "none"

    @property
    def spacing_ring_radius_cm(self) -> float | None:
        """Radius of the dashed spacing ring to draw, or ``None`` to hide it.

        The ring is drawn only when the effective spacing radius is known and
        strictly larger than the drawn footprint — a ring inside the footprint
        adds nothing (the footprint already conveys that size, #213). Returning
        the radius (not a bool) lets callers type-narrow in one step.
        """
        effective = self.effective_spacing_radius_cm
        if effective is not None and effective > self.footprint_radius_cm:
            return effective
        return None

    @property
    def shows_spacing_ring(self) -> bool:
        """Whether the dashed spacing ring should be drawn."""
        return self.spacing_ring_radius_cm is not None


def db_spacing_radius_cm(species_dict: dict[str, Any]) -> float | None:
    """Footprint/spacing radius the database implies for a species, or ``None``.

    Equals ``max_spread_cm / 2`` when ``max_spread_cm`` is a positive number,
    else ``None``. Used by the species-assignment helper to size the drawn
    footprint so its diameter equals ``max_spread_cm`` (#213).
    """
    db = _positive_number(species_dict.get("max_spread_cm"))
    return db / 2.0 if db is not None else None


#: The gallery's fallback diameter per object type when a plant has no species
#: spread (cm). One copy: every drop path asks ``species_drop_diameter_cm``.
GALLERY_DEFAULT_DIAMETER_CM: dict[str, float] = {
    "TREE": 200.0,
    "SHRUB": 100.0,
    "PERENNIAL": 60.0,
}


def species_drop_diameter_cm(
    species_dict: dict[str, Any] | None, object_type_name: str
) -> float:
    """Diameter a NEW plant is drawn at: the species spread, else the type default.

    One rule for every creation path that knows a species record - the gallery
    drop, the Plant Database drop (``build_species_plant``) and the Plant Lists
    drop (#596). ``db_spacing_radius_cm`` is the same positive-only
    ``max_spread_cm / 2`` used by species assignment, so the drawn footprint
    and the stamped metadata cannot disagree. An unknown/custom name keeps the
    gallery default; an EXISTING plant's geometry is never touched.
    """
    radius = (
        db_spacing_radius_cm(species_dict)
        if isinstance(species_dict, dict)
        else None
    )
    if radius is not None:
        return radius * 2.0
    return GALLERY_DEFAULT_DIAMETER_CM.get(object_type_name, 60.0)


#: The species layers whose crown stands OVER the planting below it (the values of
#: ``models.plant_data.PermacultureLayer``; this module stays import-free of it).
OVERSTOREY_LAYERS: frozenset[str] = frozenset({"canopy", "sub_canopy"})
#: The species layers that grow below a crown, among each other.
UNDERSTOREY_LAYERS: frozenset[str] = frozenset(
    {"shrub", "herbaceous", "ground_cover", "root", "vine"}
)

OVERSTOREY = "overstorey"
UNDERSTOREY = "understorey"


def spacing_storey(species_dict: dict[str, Any] | None, object_type_name: str) -> str:
    """The storey a plant's spacing is judged in: ``OVERSTOREY`` or ``UNDERSTOREY``.

    A spacing overlap says two plants will crowd each other when grown. A tree
    and what grows beneath its crown do not: a lawn, a shrub border, the
    strawberries of an apple guild share the tree's ground on purpose, and
    whether they get enough light there is the sun evaluation's question, not a
    planting-distance one. So spacing is compared within a storey only (#786;
    before, a food-forest guild reported every ground-cover plant under its
    tree as an overlap).

    The species' recorded ``permaculture_layer`` decides; a plant without one
    (a custom or pre-layer record) falls back to how it was drawn: a ``TREE``
    is overstorey, everything else understorey.
    """
    layer = species_dict.get("permaculture_layer") if isinstance(species_dict, dict) else None
    if layer in OVERSTOREY_LAYERS:
        return OVERSTOREY
    if layer in UNDERSTOREY_LAYERS:
        return UNDERSTOREY
    return OVERSTOREY if object_type_name == "TREE" else UNDERSTOREY


def spacing_storey_for_item(item: Any) -> str:
    """``spacing_storey`` of a plant item (its species record and object type)."""
    meta = getattr(item, "metadata", None) or {}
    object_type = getattr(item, "object_type", None)
    return spacing_storey(meta.get("plant_species"), getattr(object_type, "name", ""))


def spacings_conflict(
    distance_cm: float,
    radius_a_cm: float,
    radius_b_cm: float,
    storey_a: str,
    storey_b: str,
) -> bool:
    """Whether two plants are closer than their spacing allows.

    True when both stand in the same storey and their spacing circles
    intersect (``distance < radius_a + radius_b``). Touching circles are the
    intended distance, not a conflict.
    """
    return storey_a == storey_b and distance_cm < radius_a_cm + radius_b_cm


def spacing_conflict_arcs(
    center: tuple[float, float],
    radius_cm: float,
    neighbours: Iterable[tuple[float, float, float]],
) -> list[tuple[float, float]]:
    """The parts of a plant's spacing circle that lie inside a neighbour's.

    A spacing warning is drawn on the crowded spot, not all round the plant:
    of the plant's own circle only the arcs inside the circle of a neighbour
    it is too close to. Returns ``(start_deg, span_deg)`` pairs, angles in
    degrees counter-clockwise from +X in the coordinate system the inputs are
    given in, ``start`` in ``[0, 360)``, merged where they overlap and sorted.
    ``[(0.0, 360.0)]`` is the whole circle (a neighbour's circle holds it
    entirely); an empty list means no part of it lies inside a neighbour (the
    circles do not meet in the plane, or this circle holds the neighbour's).

    ``neighbours`` are ``(x, y, radius_cm)`` in the same coordinate system as
    ``center``.
    """
    cx, cy = center
    if radius_cm <= 0:
        return []
    spans: list[tuple[float, float]] = []
    for nx, ny, neighbour_radius in neighbours:
        distance = math.hypot(nx - cx, ny - cy)
        if distance + radius_cm <= neighbour_radius:
            return [(0.0, 360.0)]
        if distance <= 0 or distance >= radius_cm + neighbour_radius:
            continue
        cosine = (distance**2 + radius_cm**2 - neighbour_radius**2) / (
            2.0 * distance * radius_cm
        )
        if cosine >= 1.0:
            continue  # this circle holds the neighbour's: none of it is inside
        half = math.degrees(math.acos(max(-1.0, cosine)))
        toward = math.degrees(math.atan2(ny - cy, nx - cx))
        spans.append(((toward - half) % 360.0, 2.0 * half))
    if not spans:
        return []
    # Merge on the circle: unroll every span from the smallest start, join the
    # ones that touch, then join the last onto the first across 360 degrees.
    spans.sort()
    merged: list[list[float]] = [list(spans[0])]
    for start, span in spans[1:]:
        last = merged[-1]
        if start <= last[0] + last[1]:
            last[1] = max(last[1], start + span - last[0])
        else:
            merged.append([start, span])
    tail = merged[-1]
    while len(merged) > 1 and tail[0] + tail[1] >= merged[0][0] + 360.0:
        head = merged.pop(0)
        tail[1] = max(tail[1], head[0] + 360.0 + head[1] - tail[0])
    if any(span >= 360.0 for _start, span in merged):
        return [(0.0, 360.0)]
    return sorted((start, span) for start, span in merged)


def sizing_for_item(item: _SizedPlant) -> PlantSizing:
    """Build a :class:`PlantSizing` from a plant item's current state."""
    footprint = float(getattr(item, "radius", 0.0) or 0.0)
    override = getattr(item, "spacing_radius_cm", None)
    meta = getattr(item, "metadata", None) or {}
    species = meta.get("plant_species")
    db_max_spread = species.get("max_spread_cm") if isinstance(species, dict) else None
    return PlantSizing(
        footprint_radius_cm=footprint,
        spacing_override_cm=override,
        db_max_spread_cm=db_max_spread,
    )
