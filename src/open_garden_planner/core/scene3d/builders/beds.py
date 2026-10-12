"""Beds and containers: a frame and the soil in it (Phase 17 L1.6).

``RAISED_BED`` (a plank box), ``CONTAINER`` / ``WALL_PLANTER`` (a box),
``CONTAINER_ROUND`` (a turned pot or tub) and a ``GARDEN_BED`` the user gave a
height (an edged bed). An in-ground ``GARDEN_BED`` — no height — has no solid:
it is ground, painted by the ground bake.

**The soil rule, once.** The soil surface is ``object_height.soil_surface_cm``
of the item's kind and height: ``SOIL_DROP_CM`` (2 cm) below the rim of a BED —
an assumption, the plan holds no fill for a bed — and AT the height of a
CONTAINER, whose height is its soil fill height. The same function gives the
height a plant stands at (``standing_base_cm``) and the base of its 2D shadow,
so for the bed builders of this module a plant is on the soil by construction:
never inside the box, never floating over it (truth gate "Base"). NOT for a bed
that is built as the plain block instead (``common.plain_block``: an outline
that is not one plain ring, e.g. a self-crossing drawing) — that block's top is
the rim, so its plants stand ``SOIL_DROP_CM`` inside it. A container has no lip
above its soil:
the plan does not hold one, and drawing one would lower the plan's own soil
level by 2 cm for the look of it.

**Footprint.** The frame's OUTER face is the footprint; a round container's rim
is the footprint's own 24-gon (``lathe``).

**Colour.** A raised bed is SVG-rendered in 2D: its sprite's oak and soil are
its colours, baked. A container, a wall planter and a garden bed are filled in
the item's own colour in 2D, so their walls are ``tinted``; their soil is baked.
``params["container_material"]`` (terracotta / plastic / wood / metal) shapes
the pot — a rolled rim, thin walls, planks — and never picks a colour: the 2D
canvas does not either.
"""

from __future__ import annotations

from typing import Final

import numpy as np

from ...container_model import (
    DEFAULT_MATERIAL,
    METAL,
    PLASTIC,
    TERRACOTTA,
    WOOD,
    container_material,
)
from ...object_height import soil_surface_cm
from ..build import BuilderRegistry
from ..mesh import Mesh, MeshPart
from ..record import PARAM_CONTAINER_MATERIAL, PARAM_RADIUS_CM, SHAPE_CIRCLE, Record
from . import palette
from .common import BuiltBuilder, corner_count, footprint_of
from .primitives import F64, ccw_ring, lathe, offset_ring, polygon_cap, signed_area, sweep

#: Plank rows are about this tall (a 15 cm board).
PLANK_ROW_CM: Final = 15.0
#: The V-groove between two plank rows: depth and half height (cm).
GROOVE_CM: Final = 0.8
#: Chamfer of a frame's top edges (cm).
CHAMFER_CM: Final = 0.6
#: Frame thickness by material (cm); a raised bed is planks. Keyed by the
#: container model's own material names — imported, not retyped; a test pins that
#: every material of ``container_model.MATERIALS`` has a thickness here.
PLANK_THICKNESS_CM: Final = 5.0
WALL_THICKNESS_CM: Final = {TERRACOTTA: 3.0, WOOD: 3.0, PLASTIC: 1.5, METAL: 1.5}
#: A frame is never thicker than this share of the footprint's shorter side.
MAX_THICKNESS_SHARE: Final = 0.2
#: Soil lower than this above the ground is the ground: no soil face.
MIN_SOIL_CM: Final = 0.5
LATHE_SEGMENTS: Final = 24  # the 2D circle footprint's own vertex count

Color = tuple[float, float, float, float]


def plank_rows(height_cm: float) -> int:
    """How many plank rows a frame of that height has (at least one)."""
    return max(1, round(height_cm / PLANK_ROW_CM))


def _chamfer(height_cm: float, thickness_cm: float) -> float:
    return max(0.0, min(CHAMFER_CM, thickness_cm / 3.0, height_cm / 4.0))


def _is_flush(soil_cm: float, height_cm: float, chamfer: float) -> bool:
    """The soil reaches the top of the frame (a container): no inner face, no lip."""
    return soil_cm >= height_cm - chamfer


def frame_profile(height_cm: float, thickness_cm: float, soil_cm: float, *, rows: int,
                  foot_inset_cm: float, face: Color, groove: Color
                  ) -> tuple[list[tuple[float, float]], list[Color]]:
    """A frame's cross-section for ``primitives.sweep`` round a counter-clockwise
    footprint: ``(lateral, z)`` with lateral = cm INTO the bed, as an open sheet
    from the inner face (just under the soil at ``soil_cm``) over the chamfered top
    and down the outer face to the ground — grooved between plank rows when
    ``rows > 1``, drawn in by ``foot_inset_cm`` at the ground for a tapered pot.
    Where the soil is flush with the top (a container) the top runs straight into
    it: no inner chamfer and no inner face. Returns the points and one colour per
    edge."""
    chamfer = _chamfer(height_cm, thickness_cm)
    if _is_flush(soil_cm, height_cm, chamfer):
        points = [(thickness_cm, height_cm), (chamfer, height_cm), (0.0, height_cm - chamfer)]
        colors = [face, face]
    else:
        inner_bottom = max(min(soil_cm - 1.0, height_cm - chamfer - 0.1), 0.0)
        points = [(thickness_cm, inner_bottom), (thickness_cm, height_cm - chamfer),
                  (thickness_cm - chamfer, height_cm), (chamfer, height_cm), (0.0, height_cm - chamfer)]
        colors = [face, face, face, face]
    depth = min(GROOVE_CM, thickness_cm / 3.0)
    half = min(GROOVE_CM, height_cm / (4.0 * rows))
    for joint in range(rows - 1, 0, -1):
        z = height_cm * joint / rows
        points += [(0.0, z + half), (depth, z), (0.0, z - half)]
        colors += [face, groove, groove]
    points.append((foot_inset_cm, 0.0))
    colors.append(face)
    return points, colors


def thickness_cm(ring: F64, nominal_cm: float) -> float:
    """The frame thickness: the nominal one, limited for a small footprint."""
    span = ring.max(axis=0) - ring.min(axis=0)
    return float(min(nominal_cm, MAX_THICKNESS_SHARE * float(span.min())))


def soil_mesh(ring: F64, thickness: float, soil_cm: float) -> Mesh:
    """The soil: the footprint drawn in by the frame, at the soil surface ``soil_cm``."""
    if soil_cm < MIN_SOIL_CM:
        return Mesh.empty()
    inner = offset_ring(ring, -thickness)
    if signed_area(inner) <= 0.0:
        return Mesh.empty()
    return polygon_cap(inner, soil_cm, palette.SOIL.linear)


def _frame(ring: F64, height_cm: float, thickness: float, soil_cm: float, *, rows: int,
           foot_inset_cm: float, face: Color, groove: Color) -> Mesh:
    profile, colors = frame_profile(height_cm, thickness, soil_cm, rows=rows,
                                    foot_inset_cm=foot_inset_cm, face=face, groove=groove)
    return sweep(profile, ring, colors, closed=True, profile_closed=False)


def _raised_bed(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    ring = ccw_ring(footprint_of(record))
    if len(ring) < 3:
        return ()
    thickness = thickness_cm(ring, PLANK_THICKNESS_CM)
    soil = soil_surface_cm(record.kind, height_cm)
    frame = _frame(ring, height_cm, thickness, soil, rows=plank_rows(height_cm), foot_inset_cm=0.0,
                   face=palette.PLANK.linear, groove=palette.PLANK_GROOVE.linear)
    bed = Mesh.merge([frame, soil_mesh(ring, thickness, soil)])
    return (MeshPart(bed, "vc", name="bed"),)


def _material(record: Record) -> str:
    """The container's material as the container model itself resolves it: an
    unknown or missing value is the model's default, never a guess made here."""
    return container_material({"container_material": record.params.get(PARAM_CONTAINER_MATERIAL)})


def _wall_thickness(material: str) -> float:
    return WALL_THICKNESS_CM.get(material, WALL_THICKNESS_CM[DEFAULT_MATERIAL])


def _box(record: Record, height_cm: float, material: str) -> tuple[MeshPart, ...]:
    ring = ccw_ring(footprint_of(record))
    if len(ring) < 3:
        return ()
    thickness = thickness_cm(ring, _wall_thickness(material))
    planked = material == WOOD
    foot = 0.0 if planked else min(0.5 * thickness, 0.06 * height_cm)
    soil = soil_surface_cm(record.kind, height_cm)  # a container: its height; an edged bed: 2 cm under
    walls = _frame(ring, height_cm, thickness, soil, rows=plank_rows(height_cm) if planked else 1,
                   foot_inset_cm=foot, face=palette.TINT, groove=palette.TINT)
    return (MeshPart(walls, "vc", tinted=True, name="walls"),
            MeshPart(soil_mesh(ring, thickness, soil), "vc", name="soil"))


def _container(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    return _box(record, height_cm, _material(record))


def _garden_bed(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A GARDEN_BED the user gave a height: an edged bed, same soil rule. (Without
    a height ``BuiltBuilder`` never calls this: the kind has no nominal height.)"""
    return _box(record, height_cm, WOOD)


def round_profile(radius_cm: float, height_cm: float, material: str, soil_cm: float
                  ) -> tuple[list[tuple[float, float]], float]:
    """A round container's ``lathe`` profile (radius, z) — up the outside, over the
    rim and in to the soil at ``soil_cm`` (down the inside to just under it, where
    the soil lies below the rim) — and its wall thickness. The rim is the widest
    point: exactly ``radius_cm``."""
    wall = min(_wall_thickness(material), MAX_THICKNESS_SHARE * radius_cm)
    chamfer = _chamfer(height_cm, wall)
    if _is_flush(soil_cm, height_cm, chamfer):
        inside = [(radius_cm - chamfer, height_cm), (radius_cm - wall, height_cm)]
    else:
        inner_bottom = max(0.0, min(soil_cm - 1.0, height_cm - chamfer - 0.1))
        inside = [(radius_cm - chamfer, height_cm), (radius_cm - wall + chamfer, height_cm),
                  (radius_cm - wall, height_cm - chamfer), (radius_cm - wall, inner_bottom)]
    if material == TERRACOTTA:  # a tapered pot with a rim band
        rim = min(0.18 * height_cm, 6.0)
        outside = [(0.72 * radius_cm, 0.0), (0.92 * radius_cm, height_cm - rim),
                   (radius_cm, height_cm - rim), (radius_cm, height_cm - chamfer)]
    else:  # a tub
        outside = [(0.86 * radius_cm, 0.0), (radius_cm, height_cm - chamfer)]
    return outside + inside, wall


def _round_container(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    radius = record.params.get(PARAM_RADIUS_CM)
    if record.shape != SHAPE_CIRCLE or isinstance(radius, bool) \
            or not isinstance(radius, int | float) or radius <= 0.0:
        return _container(record, height_cm)  # not a circle after all: a box on its footprint
    material = _material(record)
    soil = soil_surface_cm(record.kind, height_cm)
    profile, wall = round_profile(float(radius), height_cm, material, soil)
    walls = lathe(profile, palette.TINT, LATHE_SEGMENTS)
    soil_part = Mesh.empty()
    inner = float(radius) - wall
    if soil >= MIN_SOIL_CM and inner > 0.0:
        angle = np.arange(LATHE_SEGMENTS) * (2.0 * np.pi / LATHE_SEGMENTS)
        ring = np.stack([inner * np.cos(angle), inner * np.sin(angle)], axis=1)
        soil_part = polygon_cap(ring, soil, palette.SOIL.linear)
    return (MeshPart(walls, "vc", tinted=True, name="walls"), MeshPart(soil_part, "vc", name="soil"))


build_raised_bed: Final = BuiltBuilder(_raised_bed, "raised bed")
build_container: Final = BuiltBuilder(_container, "container")
build_round_container: Final = BuiltBuilder(_round_container, "round container")
build_garden_bed: Final = BuiltBuilder(_garden_bed, "garden bed")


def triangle_budget(record: Record, height_cm: float) -> int:
    """The most triangles a bed or container may have: per footprint corner two
    per profile edge (4 + 3 per plank row) plus the soil; 500 for a turned pot."""
    if record.kind == "CONTAINER_ROUND" and record.shape == SHAPE_CIRCLE:
        return 500
    corners = max(corner_count(record), 3)
    return (2 * (4 + 3 * plank_rows(height_cm)) + 1) * corners + 10


def register(registry: BuilderRegistry) -> None:
    registry.register("RAISED_BED", build_raised_bed)
    registry.register_many(("CONTAINER", "WALL_PLANTER"), build_container)
    registry.register("CONTAINER_ROUND", build_round_container)
    registry.register("GARDEN_BED", build_garden_bed)
