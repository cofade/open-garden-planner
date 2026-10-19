"""The production builders of the 3D scene (Phase 17 L1.6 and L1.7, #385, ADR-059 addenda).

``Record -> tuple[MeshPart, ...]`` functions, one module per family, each with a
module-level ``register(registry)``. Qt-free: standard library, numpy and
Qt-free ``core`` siblings (the AST scan in ``tests/unit/test_scene3d_contract.py``
covers this package).

=================  ==========================================================
``buildings``      HOUSE (walls + gable roof from the live ridge), GARAGE_SHED,
                   TOOL_SHED (ridge from the local bounding box)
``lines``          FENCE and WALL: the one dispatch from a polyline's kind and
                   style to its solid; the geometry is in ``fences`` (picket,
                   metal, chain link, hedge fence, plain panel) and ``walls``
``beds``           RAISED_BED, CONTAINER, WALL_PLANTER, CONTAINER_ROUND, and a
                   GARDEN_BED that was given a height
``hedges``         HEDGE_SECTION, HEDGE_POLYGON
``plants``         TREE, SHRUB, PERENNIAL (``plant_art.PLANT_KINDS``): one
                   silhouette per sprite archetype, from the 2D recipe tables
                   (L1.7 — its own rules, gates and tests)
=================  ==========================================================

The first four are the BUILT WORLD (``register``, ``BUILT_WORLD_KINDS``,
``triangle_budget``); ``production_registry()`` holds them and the plants. No
kind belongs to both, and a test says so.

Every other kind keeps ``build.default_builder`` — a prism up to its height, or
nothing for an item without one: paths, lawns and in-ground beds are ground
(the ground bake paints them); furniture, glass, water and pergolas are L4.

Shared by all of them: ``primitives`` (boxes, sweep, plank, lathe, tubes),
``palette`` (the mirrored 2D colours), ``common`` (the top is the height; no
height, no shadow), ``roofs`` (the gable roof).

The wiring (L1.3) calls ``production_registry()`` once and hands the result to
``SceneSync``.
"""

from __future__ import annotations

from ..build import BuilderRegistry
from ..record import Record
from . import beds, buildings, hedges, lines, plants
from .common import nominal_height_cm

__all__ = ["BUILT_WORLD_KINDS", "production_registry", "register", "triangle_budget"]

#: The kinds the built world registers a builder for (pinned by a test).
BUILT_WORLD_KINDS: frozenset[str] = frozenset({
    "HOUSE", "GARAGE_SHED", "TOOL_SHED",
    "FENCE", "WALL",
    "RAISED_BED", "CONTAINER", "WALL_PLANTER", "CONTAINER_ROUND", "GARDEN_BED",
    "HEDGE_SECTION", "HEDGE_POLYGON",
})


def register(registry: BuilderRegistry) -> None:
    """Register every built-world builder (this story's five families)."""
    buildings.register(registry)
    lines.register(registry)
    beds.register(registry)
    hedges.register(registry)


def triangle_budget(record: Record) -> int | None:
    """The most triangles the built world may make for ``record`` — its family's
    stated budget (``buildings`` / ``lines`` / ``hedges`` / ``beds``
    ``.triangle_budget``) — or None for a kind the built world does not build.
    A budget is a ceiling the tests hold every builder to, not a count."""
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
    return None


def production_registry() -> BuilderRegistry:
    """A fresh registry holding every production builder: the built world
    (``register``) and the plants (``plants.register``, L1.7). Every other kind
    falls to the registry's default, the plain prism."""
    registry = BuilderRegistry()
    register(registry)
    plants.register(registry)
    return registry
