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
3. Plants with an assigned species — the embedded species dict's
   ``max_height_cm`` (the established linkage, cf.
   ``plant_sizing.sizing_for_item``).
4. A per-object-type default (``DEFAULT_HEIGHTS_CM`` below).
5. ``None`` — the object has no meaningful height and casts no shadow.

``object_height_cm`` is ADDITIVE item metadata: it round-trips through the
``.ogp`` serializer wholesale and old app versions ignore it (graceful
degrade) — NO FILE_VERSION bump (precedent: the ``container_*`` keys).

To stay Qt-free this module never imports ``core.object_types`` (which
pulls in Qt for its translated labels); object types are matched by
their enum ``name``. ``tests/unit/test_object_height.py`` pins the name
sets against the real enum so a rename cannot silently break the mapping.
"""

from __future__ import annotations

from typing import Any

from .container_model import container_height_cm

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
}

# Mirrors CONTAINER_TYPES in core/object_types.py (pinned by unit test).
_CONTAINER_TYPE_NAMES = frozenset({"CONTAINER", "CONTAINER_ROUND", "WALL_PLANTER"})

# Mirrors the circle-based plant types (pinned by unit test). Plants get a
# height from their species; a placeholder plant without species has no
# default height but the properties panel still offers the Height field.
_PLANT_TYPE_NAMES = frozenset({"TREE", "SHRUB", "PERENNIAL"})

# height_source() return values (stable identifiers, not user-visible text).
SOURCE_CUSTOM = "custom"
SOURCE_CONTAINER = "container"
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


def _species_height_cm(metadata: dict[str, Any] | None) -> float | None:
    if not metadata:
        return None
    species = metadata.get("plant_species")
    if not isinstance(species, dict):
        return None
    return _positive_number(species.get("max_height_cm"))


def effective_height_cm(
    object_type: Any, metadata: dict[str, Any] | None
) -> float | None:
    """Resolve the effective above-ground height in cm (see precedence above)."""
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
    species = _species_height_cm(metadata)
    if species is not None:
        return species
    return DEFAULT_HEIGHTS_CM.get(name)


def height_source(object_type: Any, metadata: dict[str, Any] | None) -> str:
    """Which precedence rule produced ``effective_height_cm``.

    Returns one of SOURCE_CUSTOM / SOURCE_CONTAINER / SOURCE_SPECIES /
    SOURCE_DEFAULT / SOURCE_NONE — drives the properties-panel tooltip.
    """
    if explicit_height_cm(metadata) is not None:
        return SOURCE_CUSTOM
    name = _type_name(object_type)
    if name in _CONTAINER_TYPE_NAMES:
        return SOURCE_CONTAINER
    if _species_height_cm(metadata) is not None:
        return SOURCE_SPECIES
    if name in DEFAULT_HEIGHTS_CM:
        return SOURCE_DEFAULT
    return SOURCE_NONE


def has_height_semantics(object_type: Any, metadata: dict[str, Any] | None) -> bool:
    """Should this object expose a Height field / participate in shadows?

    True for every type with a default, containers, plant types (even
    species-less placeholders, so the user can set a height by hand), and
    any object that already carries an explicit height.
    """
    name = _type_name(object_type)
    return (
        name in DEFAULT_HEIGHTS_CM
        or name in _CONTAINER_TYPE_NAMES
        or name in _PLANT_TYPE_NAMES
        or explicit_height_cm(metadata) is not None
    )
