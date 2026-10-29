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
# (see #257). Every object kind that stands up has one; types absent from this
# table (and not containers/plants) are the ground surfaces, generic shapes and
# annotations: they have no height semantics and cast no shadow.
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
    # Package 3a roster (#308).
    "SANDBOX": 30.0,
    "TRAMPOLINE": 90.0,
    "HOT_TUB": 90.0,
    "PICNIC_TABLE": 75.0,
    "WHEELBARROW": 60.0,
    "BIRD_BATH": 90.0,
    # The kinds that had no height until L4's second owner pass (ADR-065): "Doesn't
    # make sense ... that a parasol doesn't have a height, while a trampoline has
    # it." The values the 3D view had shown them at: a market parasol's canopy top,
    # a fire bowl's rim, a large planter's rim, a cold frame's high back, a 200 l
    # barrel, a standpipe tap, an A-frame swing's top beam, a hammock stand's hooks,
    # a pergola's rafters. The 2D model extrudes the whole footprint as a solid
    # prism (`ui/canvas/footprints.item_footprints`), so an open frame — a swing,
    # a hammock, a pergola — shades its whole footprint in 2D, as a picket fence
    # casts a solid strip: accepted by the owner, ADR-042's #308 note superseded.
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

#: The garden's surfaces: with no height of their own they ARE the ground the 2D sun
#: study's shadows and hours of sun lie on (``lies_on_ground``). Generic shapes with
#: no height (zones, highlights) also lie on the ground (#589). Annotations stay above.
#: Every object that stands up has a default height and stands above.
GROUND_SURFACE_TYPE_NAMES = frozenset(
    {
        "LAWN",
        "PATH",
        "TERRACE_PATIO",
        "DRIVEWAY",
        "POND_POOL",
        "GARDEN_BED",
        "GENERIC_RECTANGLE",
        "GENERIC_POLYGON",
        "GENERIC_CIRCLE",
        "GENERIC_ELLIPSE",
    }
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
#: ``height_source_at`` only: the height was GROWN for the date (``growth_model``).
SOURCE_GROWN = "grown"


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


def resolve_height(
    object_type: Any,
    metadata: dict[str, Any] | None,
    at_date: date | None = None,
) -> tuple[float | None, str]:
    """The ONE precedence ladder: ``(effective height, source)`` (#581).

    explicit ``object_height_cm`` > container fill > date-projected growth >
    measured current height > species max height > per-type default > None.
    ``effective_height_cm`` returns the height, ``height_source`` and
    ``height_source_at`` the source; all three are projections of this tuple, so
    the ladder is changed in exactly one place.

    ``at_date`` (US-E8): a plant with a species, a planting date and a measured
    current height resolves to its date-projected height via
    ``core/growth_model`` (linear current→max over years-to-maturity), and its
    source is ``SOURCE_GROWN``. Without a date the growth branch is skipped.
    """
    explicit = explicit_height_cm(metadata)
    if explicit is not None:
        return explicit, SOURCE_CUSTOM
    name = _type_name(object_type)
    if name in _CONTAINER_TYPE_NAMES:
        # KNOWN SIMPLIFICATION (flag for US-E3 shadows): without an explicit
        # override, the soil *fill* height stands in for the above-ground
        # height — a 30 cm-fill pot on 60 cm legs shadows as 30 cm until the
        # user sets one. There is no separate above-ground source to draw
        # from in this slice; revisit when shadow accuracy matters (#258).
        return container_height_cm(metadata if metadata else None), SOURCE_CONTAINER
    species_dict = (metadata or {}).get("plant_species")
    if isinstance(species_dict, dict) and at_date is not None:
        grown = grown_height_cm(species_dict, metadata, at_date, name)
        if grown is not None:
            return grown, SOURCE_GROWN
    # Outside the SPECIES branch (a plant whose species lookup missed still
    # has a real measured height) but gated on the plant TYPE, so the rule
    # can never silently change height resolution for some future non-plant
    # that happens to acquire ``plant_instance`` metadata.
    current = _measured_height_cm(name, species_dict, metadata)
    if current is not None:
        return current, SOURCE_CURRENT
    if isinstance(species_dict, dict):
        mature = _positive_number(species_dict.get("max_height_cm"))
        if mature is not None:
            return mature, SOURCE_SPECIES
    default = DEFAULT_HEIGHTS_CM.get(name)
    return default, SOURCE_DEFAULT if default is not None else SOURCE_NONE


def effective_height_cm(
    object_type: Any,
    metadata: dict[str, Any] | None,
    at_date: date | None = None,
) -> float | None:
    """Resolve the effective above-ground height in cm (see precedence above).

    A projection of :func:`resolve_height` (#581). ``at_date`` (US-E8): when
    given, a plant WITH a species, a planting date AND a measured current height
    resolves to its DATE-PROJECTED height via ``core/growth_model`` (linear
    current→max over years-to-maturity) — so shadows (US-E3/E4) and the 3D view
    (US-E6) automatically see the grown size. Independently of any date, a
    plant's measured ``current_height_cm`` (if set) drives the height ahead of
    the species mature max — the owner-chosen "current height anchors it" rule.
    An explicit ``object_height_cm`` override still wins; un-measured plants and
    non-plants keep the mature/default height as before.
    """
    return resolve_height(object_type, metadata, at_date)[0]


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
    SOURCE_SPECIES / SOURCE_DEFAULT / SOURCE_NONE — drives the properties-panel
    tooltip. A projection of :func:`resolve_height`'s static (date-independent)
    precedence (#581).
    """
    return resolve_height(object_type, metadata)[1]


def height_source_at(object_type: Any, metadata: dict[str, Any] | None,
                     at_date: date | None) -> str:
    """``height_source`` for the height ``effective_height_cm(..., at_date)`` gives:
    the same precedence, with ``SOURCE_GROWN`` where that height is a plant's
    date-projected growth (Phase 17 L2.3, the 3D info card's "height with its
    source"). Without a date it IS ``height_source``. A projection of
    :func:`resolve_height` (#581)."""
    return resolve_height(object_type, metadata, at_date)[1]


def lies_on_ground(object_type: Any, metadata: dict[str, Any] | None) -> bool:
    """Is this object a surface of the ground — a lawn, a path, a terrace, a driveway,
    a pond or an in-ground bed (``GROUND_SURFACE_TYPE_NAMES``) with no height of its own?

    The 2D canvas draws such a surface UNDER the sun study's overlays, so a shadow and
    the hours-of-sun map lie on it as they lie on the ground (manual pass of PR #584;
    ``ui/canvas/canvas_scene.GROUND_Z_RANGE``). A height — only stored metadata can
    give these types one — makes it a solid that stands on the ground instead.
    """
    return (_type_name(object_type) in GROUND_SURFACE_TYPE_NAMES
            and effective_height_cm(object_type, metadata) is None)


def has_height_semantics(object_type: Any, metadata: dict[str, Any] | None) -> bool:
    """Does this object's TYPE carry a height of its own (a default, a container's
    fill, a plant's species or measurement, or an explicit value)?

    The type-level half of "can this object have a height" — a type that answers
    False (a generic shape, an in-ground bed, a lawn) can still be GIVEN one, and
    the Properties panel must offer the field for it (#628); that question is
    ``shows_height_field``.
    """
    name = _type_name(object_type)
    return (
        name in DEFAULT_HEIGHTS_CM
        or name in _CONTAINER_TYPE_NAMES
        or name in _PLANT_TYPE_NAMES
        or explicit_height_cm(metadata) is not None
    )


def shows_height_field(
    object_type: Any, metadata: dict[str, Any] | None, *, has_footprint: bool
) -> bool:
    """Should the Properties panel offer the Height field for this object (#628)?

    True for every item that HAS a footprint — a generic shape, an in-ground bed, a
    terrace, a pond, a lawn, a path, a driveway — and for every type with height
    semantics. The field is the only way to set an explicit ``object_height_cm``, so
    gating it on an explicit value having been set already (``has_height_semantics``
    for a type with no default) made it unreachable: a polygon could never become a
    solid, and an in-ground bed could never be mounded. "Auto" (0) is no height and
    keeps today's behaviour — a ground surface stays on the ground
    (``lies_on_ground`` yields the moment a height is set) and a generic shape simply
    casts nothing.
    """
    return has_footprint or has_height_semantics(object_type, metadata)
