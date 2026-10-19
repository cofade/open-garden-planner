"""Effective object height resolution for the Phase 14 sun/shade features
(US-E2, #257).

One source of truth for "how tall is this object above ground?" — consumed
by the 2D shadow overlay (US-E3), the hours-of-sun heatmap (US-E4) and the
3D extrusion (US-E6). Deliberately Qt-free (pattern: ``core/plant_sizing``,
``core/container_model``): it takes the object type and the item's
``metadata`` dict, never a QGraphicsItem, so it is unit-testable headless.

Height precedence (ADR-037):

1. ``metadata["object_height_cm"]`` — an explicit, user-set height.
2. Containers — ``container_height_cm`` (the soil *fill* height from
   ``core/container_model``). NOTE: the two keys are deliberately distinct
   and never aliased: a tall pot on legs can have ``object_height_cm`` 90
   with a fill height of 30; the fill height keeps driving soil volume.
3. Plants — in order:
   a. with a species, a planting date AND a measured current height, and
      when ``at_date`` is given — the DATE-PROJECTED height from
      ``core/growth_model`` (current → species max over years-to-maturity);
   b. else the measured ``current_height_cm`` (``plant_instance``) if set —
      the owner-chosen "current height anchors it" rule, so the field the
      user types drives the shadow directly. Applies even with NO species
      attached (an unknown/custom name is a supported state). NOTE this
      rule is metadata-driven, not type-driven: any object carrying a
      ``plant_instance`` height gets it. Only plant items are given that
      metadata today, so the distinction is currently inert;
   c. else, with a species, its mature ``max_height_cm`` (the established
      linkage, cf. ``plant_sizing.sizing_for_item``).
4. A per-object-type default (``DEFAULT_HEIGHTS_CM`` below).
5. ``None`` — the object has no meaningful height and casts no shadow.

Where an object STANDS is the second question this module answers (Phase 17
L1.6, ADR-037 addendum): ``standing_base_cm`` — the soil surface of a
soil-capable parent with a height, ``SOIL_DROP_CM`` below its rim, else the
ground. A height is always measured from there, so a 60 cm plant on the soil
of a 40 cm raised bed occupies 38–98 cm. One rule for the 2D shadow casters
and the 3D records.

``object_height_cm`` is ADDITIVE item metadata: it round-trips through the
``.ogp`` serializer wholesale and old app versions ignore it (graceful
degrade) — NO FILE_VERSION bump (precedent: the ``container_*`` keys).

To stay Qt-free this module never imports ``core.object_types`` (which
pulls in Qt for its translated labels); object types are matched by
their enum ``name``. ``tests/unit/test_object_height.py`` pins the name
sets against the real enum so a rename cannot silently break the mapping.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from .container_model import container_height_cm
from .growth_model import (
    current_height_from_metadata,
    effective_current_height_cm,
    grown_height_cm,
)

METADATA_KEY = "object_height_cm"

# Default above-ground heights (cm) per ObjectType name. Chosen as sensible
# central-European garden values; the owner confirms them at manual test
# (see #257). Types absent from this table (and not containers/plants)
# have no height semantics and cast no shadow.
DEFAULT_HEIGHTS_CM: dict[str, float] = {
    "FENCE": 120.0,
    "WALL": 200.0,
    "HEDGE_SECTION": 150.0,
    "HEDGE_POLYGON": 150.0,
    "HOUSE": 450.0,
    "GARAGE_SHED": 250.0,
    "TOOL_SHED": 250.0,
    "GREENHOUSE": 220.0,
    "TRELLIS": 180.0,
    "RAISED_BED": 40.0,
    "TABLE_RECTANGULAR": 75.0,
    "TABLE_ROUND": 75.0,
    "CHAIR": 85.0,
    "BENCH": 85.0,
    "LOUNGER": 80.0,
    "BBQ_GRILL": 90.0,
    "COMPOST_BIN": 100.0,
    # Package 3a roster (#308) — solid objects only. SWING / PERGOLA / HAMMOCK
    # deliberately have NO default: the shadow/3D model extrudes the FULL item
    # footprint as a solid prism (`ui/canvas/footprints.item_footprints`), and
    # a pergola or swing frame is mostly air (sprite ink 0.20-0.53) — a solid
    # 3x3 m block at 2.3 m would misstate a sun study. They still expose the
    # Height field (`_HEIGHT_FIELD_TYPES`) so a user can opt in explicitly.
    "SANDBOX": 30.0,
    "TRAMPOLINE": 90.0,
    "HOT_TUB": 90.0,
    "PICNIC_TABLE": 75.0,
    "WHEELBARROW": 60.0,
    "BIRD_BATH": 90.0,
}

# Mirrors CONTAINER_TYPES in core/object_types.py (pinned by unit test).
_CONTAINER_TYPE_NAMES = frozenset({"CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"})

# Mirrors the circle-based plant types (pinned by unit test). Plants get a
# height from their species; a placeholder plant without species has no
# default height but the properties panel still offers the Height field.
_PLANT_TYPE_NAMES = frozenset({"TREE", "SHRUB", "PERENNIAL"})

# Mirrors SOIL_CONTAINER_TYPES in core/object_types.py — the ``is_bed_type``
# predicate, "this type holds soil" (pinned by unit test). A plant stands on
# the soil of such a parent (``standing_base_cm``); a trellis holds none.
_SOIL_PARENT_TYPE_NAMES = frozenset(
    {"GARDEN_BED", "RAISED_BED", "CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"}
)

#: The soil of a BED lies this far below its rim. A modelling ASSUMPTION, not a
#: datum of the plan: a bed has a height (its rim) and nothing says how full it
#: is. ONE constant for the 3D bed meshes, the height a plant stands at and the
#: base of its 2D shadow caster (Phase 17 L1.6, ``ogp-lush-cinematic`` §1
#: "Base") — so it moves a raised plant's shadow by ``2 / tan α``: 7.5 cm at a
#: 15° sun, 1.2 cm at 60°. A CONTAINER has no drop: its height IS its soil fill
#: height (``soil_surface_cm``).
SOIL_DROP_CM = 2.0

#: No base is derived from a parent height beyond this — as none is from an
#: infinite one. That is all this bound says: a base is itself a length of a 3D
#: scene record (``transform.base_cm``), and one derived from a taller parent
#: would be out of the record's range, so the plant would lose its record over
#: its parent's nonsense height. The number is the scene contract's
#: ``core/scene3d/record.MAX_LENGTH_CM`` (10 km), mirrored — this module serves
#: the 2D app and does not import the 3D package — and pinned equal by a test.
#: It is NOT the rule "nothing stands on a parent the 3D scene does not hold":
#: whether a parent has a record is the snapshot's knowledge, and
#: ``ui/view3d/snapshot.snapshot_records`` settles that for every reason a parent
#: can be left out (a bed 30 km wide has an ordinary height). In 2D a bed taller
#: than this still casts while its plant casts from the ground — an oddity,
#: stated here, of plans no garden has.
MAX_PARENT_HEIGHT_CM = 1e6

# height_source() return values (stable identifiers, not user-visible text).
SOURCE_CUSTOM = "custom"
SOURCE_CONTAINER = "container"
SOURCE_CURRENT = "current"
SOURCE_SPECIES = "species"
SOURCE_DEFAULT = "default"
SOURCE_NONE = "none"


def _type_name(object_type: Any) -> str:
    """Enum member -> its name; plain strings pass through (test convenience)."""
    return getattr(object_type, "name", str(object_type))


def _positive_number(value: Any) -> float | None:
    """Coerce a metadata value to a positive float, else None.

    Mirrors ``container_model._positive_number``: rejects bools (which are
    ints in Python) and non-positive numbers.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number > 0 else None


def explicit_height_cm(metadata: dict[str, Any] | None) -> float | None:
    """The user-set ``object_height_cm`` metadata value, if valid."""
    if not metadata:
        return None
    return _positive_number(metadata.get(METADATA_KEY))


def _measured_height_cm(
    name: str, species_dict: Any, metadata: dict[str, Any] | None
) -> float | None:
    """The plant's measured (or spread-implied) current height, else None."""
    if name not in _PLANT_TYPE_NAMES:
        return None
    if isinstance(species_dict, dict):
        return effective_current_height_cm(species_dict, metadata)
    return current_height_from_metadata(metadata)


def _species_height_cm(metadata: dict[str, Any] | None) -> float | None:
    if not metadata:
        return None
    species = metadata.get("plant_species")
    if not isinstance(species, dict):
        return None
    return _positive_number(species.get("max_height_cm"))


def effective_height_cm(
    object_type: Any,
    metadata: dict[str, Any] | None,
    at_date: date | None = None,
) -> float | None:
    """Resolve the effective above-ground height in cm (see precedence above).

    ``at_date`` (US-E8): when given, a plant WITH a species, a planting
    date AND a measured current height resolves to its DATE-PROJECTED
    height via ``core/growth_model`` (linear current→max over
    years-to-maturity) — so shadows (US-E3/E4) and the 3D view (US-E6)
    automatically see the grown size. Independently of any date, a plant's
    measured ``current_height_cm`` (if set) drives the height ahead of the
    species mature max — the owner-chosen "current height anchors it" rule.
    An explicit ``object_height_cm`` override still wins; un-measured
    plants and non-plants keep the mature/default height as before.
    """
    explicit = explicit_height_cm(metadata)
    if explicit is not None:
        return explicit
    name = _type_name(object_type)
    if name in _CONTAINER_TYPE_NAMES:
        # KNOWN SIMPLIFICATION (flag for US-E3 shadows): without an explicit
        # override, the soil *fill* height stands in for the above-ground
        # height — a 30 cm-fill pot on 60 cm legs shadows as 30 cm until the
        # user sets one. There is no separate above-ground source to draw
        # from in this slice; revisit when shadow accuracy matters (#258).
        return container_height_cm(metadata if metadata else None)
    species_dict = (metadata or {}).get("plant_species")
    if isinstance(species_dict, dict) and at_date is not None:
        grown = grown_height_cm(species_dict, metadata, at_date, name)
        if grown is not None:
            return grown
    # Outside the SPECIES branch (a plant whose species lookup missed still
    # has a real measured height) but gated on the plant TYPE, so the rule
    # can never silently change height resolution for some future non-plant
    # that happens to acquire ``plant_instance`` metadata.
    current = _measured_height_cm(name, species_dict, metadata)
    if current is not None:
        return current
    if isinstance(species_dict, dict):
        mature = _positive_number(species_dict.get("max_height_cm"))
        if mature is not None:
            return mature
    return DEFAULT_HEIGHTS_CM.get(name)


def soil_surface_cm(object_type: Any, height_cm: float | None) -> float:
    """Height above ground of the soil in a soil parent of that type, ``height_cm``
    tall. 0.0 without a usable height: none at all (an in-ground bed), not
    positive, not finite, or beyond ``MAX_PARENT_HEIGHT_CM`` (no base is derived
    from a height beyond the bound).

    Two kinds of soil parent, because the plan says two different things:

    - a **container** (pot, box, wall planter): its resolved height IS its soil
      fill height (``effective_height_cm``: the fill stands in for the height),
      so the soil is AT that height. The plan's one soil datum is not moved for
      the look of a lip — and where the user overrode the height, the soil is at
      the top they gave, so a plant never stands inside the solid;
    - a **bed** (raised bed, an edged garden bed): the plan holds a rim height
      and no fill, so the soil is assumed ``SOIL_DROP_CM`` below the rim, never
      below the ground.

    The 3D bed builders put their soil here and plants stand here
    (``standing_base_cm``), so for the bed builders a plant is on its soil by
    construction. A bed whose outline is not one plain outline (several rings, a
    hole, or an outline the scene contract had to resolve) is built as a plain
    block up to its rim instead (``scene3d.builders.common.plain_block``); its
    plants stand ``SOIL_DROP_CM`` inside that block.
    """
    if (height_cm is None or not math.isfinite(height_cm) or height_cm <= 0.0
            or height_cm > MAX_PARENT_HEIGHT_CM):
        return 0.0
    if _type_name(object_type) in _CONTAINER_TYPE_NAMES:
        return height_cm
    return max(height_cm - SOIL_DROP_CM, 0.0)


def standing_base_cm(
    parent_type: Any,
    parent_metadata: dict[str, Any] | None,
    at_date: date | None = None,
) -> float:
    """How high above the ground an item stands, given the parent it grows in.

    The soil surface of a SOIL-capable parent (``is_bed_type``: beds, raised
    beds, containers, wall planters) that has a resolved height; 0.0 for every
    other parent — an in-ground bed (no height), a trellis (holds no soil), no
    parent at all. The item's own ``effective_height_cm`` is measured from
    there: it occupies ``[base, base + height]`` (Phase 17 L1.6; the caller
    resolves ``parent_bed_id``, see ``ui/canvas/footprints.item_base_cm``).
    """
    if parent_type is None or _type_name(parent_type) not in _SOIL_PARENT_TYPE_NAMES:
        return 0.0
    return soil_surface_cm(
        parent_type, effective_height_cm(parent_type, parent_metadata, at_date=at_date))


def is_solid_soil_parent(
    parent_type: Any,
    parent_metadata: dict[str, Any] | None,
    at_date: date | None = None,
) -> bool:
    """Is that parent a SOIL-capable solid: a bed, raised bed, container or wall
    planter (``is_bed_type``) with a resolved, positive, finite height?

    Such a parent is a shadow caster whose footprint covers the plants that grow
    in it. Whether they are LIFTED is another question — ``standing_base_cm``,
    0.0 where the soil is not above the ground (a 2 cm edging) — but a plant in
    it is in the parent's solid either way, and the per-plant sun estimate must
    not count that solid as shade (``ui/canvas/footprints.standing_parent``).
    False for an in-ground bed without a height, a trellis, no parent at all.
    """
    if parent_type is None or _type_name(parent_type) not in _SOIL_PARENT_TYPE_NAMES:
        return False
    height = effective_height_cm(parent_type, parent_metadata, at_date=at_date)
    return height is not None and math.isfinite(height) and height > 0.0


def height_source(object_type: Any, metadata: dict[str, Any] | None) -> str:
    """Which precedence rule produced ``effective_height_cm``.

    Returns one of SOURCE_CUSTOM / SOURCE_CONTAINER / SOURCE_CURRENT /
    SOURCE_SPECIES / SOURCE_DEFAULT / SOURCE_NONE — drives the
    properties-panel tooltip. Mirrors ``effective_height_cm``'s static
    (date-independent) precedence.
    """
    if explicit_height_cm(metadata) is not None:
        return SOURCE_CUSTOM
    name = _type_name(object_type)
    if name in _CONTAINER_TYPE_NAMES:
        return SOURCE_CONTAINER
    if (
        _measured_height_cm(name, (metadata or {}).get("plant_species"), metadata)
        is not None
    ):
        return SOURCE_CURRENT
    if _species_height_cm(metadata) is not None:
        return SOURCE_SPECIES
    if name in DEFAULT_HEIGHTS_CM:
        return SOURCE_DEFAULT
    return SOURCE_NONE


# Open structures (Package 3a, #308): no DEFAULT height — the shadow model
# extrudes a solid footprint and these are mostly air — but the Height field
# is offered so a user can opt a specific swing/pergola/hammock into the sun
# study by hand. Without a default or an explicit value they cast nothing.
_HEIGHT_FIELD_TYPES: frozenset[str] = frozenset({"SWING", "PERGOLA", "HAMMOCK"})


def has_height_semantics(object_type: Any, metadata: dict[str, Any] | None) -> bool:
    """Should this object expose a Height field / participate in shadows?

    True for every type with a default, containers, plant types (even
    species-less placeholders, so the user can set a height by hand), the
    open structures in `_HEIGHT_FIELD_TYPES` (field offered, no default), and
    any object that already carries an explicit height.
    """
    name = _type_name(object_type)
    return (
        name in DEFAULT_HEIGHTS_CM
        or name in _CONTAINER_TYPE_NAMES
        or name in _PLANT_TYPE_NAMES
        or name in _HEIGHT_FIELD_TYPES
        or explicit_height_cm(metadata) is not None
    )
