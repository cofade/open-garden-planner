"""The production builders of the 3D scene (Phase 17 L1.6, L1.7, L4; #385, #388; ADR-059
addenda, ADR-065).

``Record -> tuple[MeshPart, ...]`` functions, one module per family, each with a
module-level ``register(registry)``. Qt-free: standard library, numpy and
Qt-free ``core`` siblings (the AST scan in ``tests/unit/test_scene3d_contract.py``
covers this package).

=================  ==========================================================
``buildings``      HOUSE, GARAGE_SHED, TOOL_SHED: walls, a roof in the style
                   the item asks for (gable, hip, shed, flat — L4.1) and a
                   heuristic facade (``facade``)
``lines``          FENCE and WALL: the one dispatch from a polyline's kind and
                   style to its solid; the geometry is in ``fences`` (picket,
                   metal, chain link, hedge fence, plain panel) and ``walls``
``beds``           RAISED_BED, CONTAINER, WALL_PLANTER, CONTAINER_ROUND, and a
                   GARDEN_BED that was given a height
``hedges``         HEDGE_SECTION, HEDGE_POLYGON
``furniture``      tables, chair, bench, parasol, lounger, grill, fire pit,
                   planter pot, picnic table (L4.4)
``play``           sandbox, trampoline, hot tub, swing, hammock (L4.4)
``utility``        compost bin, cold frame, rain barrel, water tap,
                   wheelbarrow, bird bath (L4.4)
``structures``     PERGOLA, TRELLIS, GREENHOUSE (L4.3)
``surfaces``       PATH, TERRACE_PATIO, DRIVEWAY, POND_POOL, LAWN: relief on
                   the painted ground — ``ground_detail`` parts (L4.2, L4.5)
``plants``         TREE, SHRUB, PERENNIAL (``plant_art.PLANT_KINDS``): one
                   silhouette per sprite archetype, from the 2D recipe tables
                   (L1.7 — its own rules, gates and tests)
=================  ==========================================================

Four families, no kind in two: the BUILT WORLD (L1.6: ``register``,
``BUILT_WORLD_KINDS``, ``triangle_budget``), the OBJECTS (L4: ``register_objects``,
``OBJECT_KINDS``), the SURFACES (L4: ``register_surfaces``, ``SURFACE_KINDS``) and
the plants. ``production_registry()`` holds all four. Every other kind keeps
``build.default_builder`` — a prism up to its height, or nothing for an item
without one (an in-ground bed, a generic shape, a ridge line).

Shared: ``primitives`` (boxes, sweep, plank, lathe, tubes), ``kit`` (an object's
box, bevelled and turned parts), ``palette`` (the mirrored 2D colours),
``common`` (the top is the height; no height, the nominal one), ``roofs``.

The wiring (L1.3) calls ``production_registry()`` once and hands the result to
``SceneSync``.
"""

from __future__ import annotations

from typing import Final

from ..build import BuilderRegistry
from ..record import Record
from . import (
    beds,
    buildings,
    furniture,
    hedges,
    lines,
    plants,
    play,
    structures,
    surfaces,
    utility,
)
from .common import nominal_height_cm

__all__ = [
    "BUILT_WORLD_KINDS", "OBJECT_KINDS", "OBJECT_TRIANGLE_BUDGET", "SURFACE_KINDS",
    "production_registry", "register", "register_objects", "register_surfaces", "triangle_budget",
]

#: The kinds the built world registers a builder for (pinned by a test).
BUILT_WORLD_KINDS: frozenset[str] = frozenset({
    "HOUSE", "GARAGE_SHED", "TOOL_SHED",
    "FENCE", "WALL",
    "RAISED_BED", "CONTAINER", "WALL_PLANTER", "CONTAINER_ROUND", "GARDEN_BED",
    "HEDGE_SECTION", "HEDGE_POLYGON",
})
#: The L4 objects (#388): every furniture and infrastructure sprite of the 2D
#: roster that the built world does not already build, and the three structures.
OBJECT_KINDS: frozenset[str] = frozenset(
    {*furniture.KINDS, *play.KINDS, *utility.KINDS, *structures.KINDS})
#: The L4 surfaces: relief on the painted ground.
SURFACE_KINDS: frozenset[str] = frozenset(surfaces.KINDS)
#: The most triangles one L4 object may have (a 2.5 m slatted compost bin, the
#: largest of the matrix, makes 3,632).
OBJECT_TRIANGLE_BUDGET: Final = 4_000


def register(registry: BuilderRegistry) -> None:
    """Register every built-world builder (L1.6's five families)."""
    buildings.register(registry)
    lines.register(registry)
    beds.register(registry)
    hedges.register(registry)


def register_objects(registry: BuilderRegistry) -> None:
    """Register every L4 object builder (#388): furniture, play, utility, structures."""
    furniture.register(registry)
    play.register(registry)
    utility.register(registry)
    structures.register(registry)


def register_surfaces(registry: BuilderRegistry) -> None:
    """Register the L4 surface builders (#388)."""
    surfaces.register(registry)


def triangle_budget(record: Record) -> int | None:
    """The most triangles the built world may make for ``record`` — its family's
    stated budget (``buildings`` / ``lines`` / ``hedges`` / ``beds``
    ``.triangle_budget``), ``OBJECT_TRIANGLE_BUDGET`` for an L4 object — or None
    for a kind neither builds. A budget is a ceiling the tests hold every builder
    to, not a count."""
    kind = record.kind
    if kind in ("HOUSE", "GARAGE_SHED", "TOOL_SHED"):
        return buildings.triangle_budget(record)
    if kind in ("FENCE", "WALL"):
        return lines.triangle_budget(record)
    if kind in ("HEDGE_SECTION", "HEDGE_POLYGON"):
        return hedges.triangle_budget(record)
    if kind in BUILT_WORLD_KINDS:
        height = record.height_cm if record.height_cm is not None else nominal_height_cm(kind)
        return beds.triangle_budget(record, height or 0.0)
    if kind in OBJECT_KINDS:
        return OBJECT_TRIANGLE_BUDGET
    return None


def production_registry() -> BuilderRegistry:
    """A fresh registry holding every production builder: the built world
    (``register``), the L4 objects and surfaces (``register_objects``,
    ``register_surfaces``) and the plants (``plants.register``, L1.7). Every other
    kind falls to the registry's default, the plain prism."""
    registry = BuilderRegistry()
    register(registry)
    register_objects(registry)
    register_surfaces(registry)
    plants.register(registry)
    return registry
