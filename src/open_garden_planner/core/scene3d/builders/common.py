"""What every built-world builder shares (Phase 17 L1.6).

The truth rules of the built world live here, once:

- **The top is the height.** A builder shapes its item for a height and its
  top is that height by construction. ``fit_parts`` is the safety net behind it
  (a z-scale about the ground, as the spike's ``fit_height``); a builder whose
  ``fit_scale`` is not 1 is a bug the tests catch, not a look the fit hides.
- **No height, no shadow.** An item the plan gives no height is built at its
  kind's nominal height as decoration and none of its parts casts a shadow —
  exactly as in 2D, where it casts none. A kind without a nominal height gets
  no solid at all.
- **One plain outline, or the plain block.** A shape function for a polygon,
  rectangle, ellipse or circle builds on ONE simple outline, as drawn. A record
  whose ground is anything else gets ``plain_block``: a prism of ALL its regions
  with their holes cut out. "Anything else" is three things: several outer
  rings; a ring with holes; and an outline the scene contract had to RESOLVE —
  a polygon drawn crossing or touching itself, flagged
  ``params["outline_resolved"]``. The flag counts even when the resolved ground
  is one ring without a hole: the ring count says nothing about how the item
  was drawn, a resolved ring can come within 0.002 cm of itself (no frame, inset
  or overhang is offset from that), and a roof would hang on a ridge drawn for
  another outline. Never a house, a bed or a hedge on ``footprints[0]`` alone.
  ``plain_block`` is also THE block every builder falls back to (a house without
  a usable ridge), so no fallback can drop a region or fill a hole.

``BuiltBuilder`` wraps a *shape function* ``(record, height_cm) -> parts`` into
the ``Builder`` the registry wants and applies the three rules.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Sequence
from typing import Final, TypeAlias

import numpy as np

from ...object_height import effective_height_cm
from ...object_height_estimate import ESTIMATED_HEIGHT_PARAM
from ..build import prism_mesh
from ..mesh import Mesh, MeshPart
from ..record import PARAM_OUTLINE_RESOLVED, SHAPE_POLYLINE, Record
from .primitives import F64, MIN_SEGMENT_CM, clean_path

ShapeFunction: TypeAlias = Callable[[Record, float], tuple[MeshPart, ...]]

#: A fit scale this close to 1 is float32 rounding of an exact construction,
#: and the mesh is left untouched.
FIT_IDENTITY: Final = 1e-6


def nominal_height_cm(kind: str) -> float | None:
    """The height an item of ``kind`` is drawn at when the plan gives it none:
    what the 2D height resolver itself answers for that kind without any data —
    the per-type default, a container's default fill height — or None when it
    has none. Asked, not mirrored: there is no table of kinds here."""
    return effective_height_cm(kind, None)


def estimated_height_of(record: Record) -> float | None:
    """The ILLUSTRATIVE height the snapshot put on ``record`` (``params
    ["estimated_height_cm"]``, L4 / #557), or None when there is no usable one. A
    geometry param: reading it is reading the record's geometry part."""
    value = record.params.get(ESTIMATED_HEIGHT_PARAM)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    height = float(value)
    return height if math.isfinite(height) and height > 0.0 else None


def centre_line(record: Record) -> tuple[F64, bool]:
    """A polyline record's centre line without repeated points, and whether it is
    a closed loop (its last point is its first — then the last point is dropped).

    What every line solid is built from. Never ``record.footprints``: those are
    the outline of the STROKE — for a fence round a garden one outer ring, with
    the garden as its hole in ``record.holes`` — the ground the 2D model treats
    as built on, not the shape of a fence.
    """
    line = clean_path(record.path) if len(record.path) >= 2 else np.zeros((0, 2))
    closed = len(line) > 3 and float(np.linalg.norm(line[0] - line[-1])) <= MIN_SEGMENT_CM
    return (line[:-1] if closed else line), closed


def has_one_plain_ring(record: Record) -> bool:
    """True when the record's ground is ONE plain outline — what every
    polygon-footprint shape function builds on: one outer ring, no hole, and not
    the resolved reading of an outline drawn crossing or touching itself
    (``params["outline_resolved"]``, set by the snapshot and by nothing else).

    False for several outer rings, for a ring with holes, and for ANY resolved
    outline — which can be one ring, several, or rings with holes: only the flag
    tells a resolved single ring from an ordinary polygon."""
    return (len(record.footprints) == 1 and not any(record.holes)
            and not record.params.get(PARAM_OUTLINE_RESOLVED))


def plain_block(record: Record, height_cm: float, *, name: str = "prism") -> tuple[MeshPart, ...]:
    """The honest solid of a record no shape function builds on — and of an item
    whose shape function has nothing to show (a house without a usable ridge):
    ALL of the record's regions, holes cut out, up to ``height_cm``, neutral and
    ``tinted``. The same mesh ``build.default_builder`` gives a record with that
    height. ``()`` for a record without ground; ``prism_mesh`` raises
    ``ValueError`` for a ring that is not simple (``SceneSync`` contains it)."""
    mesh = prism_mesh(record.footprints, height_cm, record.holes)
    if not mesh.vertex_count:
        return ()
    return (MeshPart(mesh, "vc", casts_shadow=True, tinted=True, name=name),)


def top_cm(parts: Sequence[MeshPart]) -> float | None:
    """The highest vertex of the union of ``parts`` (None when they hold none)."""
    tops = [float(part.mesh.positions[:, 2].max()) for part in parts if part.mesh.vertex_count]
    return max(tops) if tops else None


def fit_scale(parts: Sequence[MeshPart], height_cm: float) -> float:
    """``height_cm`` / the top of ``parts``: 1.0 when they were built to the height
    (and for no parts). The number gate G1 holds every builder to."""
    top = top_cm(parts)
    if top is None or top <= 0.0:
        return 1.0
    return height_cm / top


def _scaled_z(mesh: Mesh, scale: float) -> Mesh:
    positions = mesh.positions.astype(np.float64)
    positions[:, 2] *= scale
    normals = mesh.normals.astype(np.float64) / np.array([1.0, 1.0, scale])  # inverse transpose
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    return Mesh.from_arrays(positions, normals, mesh.colors, mesh.uvs, mesh.indices)


def fit_parts(parts: tuple[MeshPart, ...], height_cm: float) -> tuple[MeshPart, ...]:
    """``parts`` scaled in z about the ground, with ONE scale, so the top of their
    union is ``height_cm``. The identity for parts built to the height."""
    scale = fit_scale(parts, height_cm)
    if abs(scale - 1.0) <= FIT_IDENTITY:
        return parts
    return tuple(dataclasses.replace(part, mesh=_scaled_z(part.mesh, scale)) for part in parts)


class BuiltBuilder:
    """A ``Builder`` made of a shape function plus the two truth rules.

    ``shape(record, height_cm)`` returns the parts for a height; it reads only
    the record's geometry part. ``raw(record)`` gives its output before the fit
    (the tests measure ``fit_scale`` on it); calling the instance gives the parts
    the engine gets.
    """

    def __init__(self, shape: ShapeFunction, name: str) -> None:
        self._shape = shape
        self.name = name

    def __repr__(self) -> str:
        return f"<built-world builder {self.name}>"

    def height_for(self, record: Record) -> float | None:
        """The height the item is built at: the plan's, else the kind's nominal one,
        else the ILLUSTRATIVE one the snapshot put on the record for a kind the 2D
        resolver gives no height (L4: ``core/object_height_estimate``). Whichever it
        is, what is built casts its shadow in 3D (owner, L4 manual pass: a parasol
        shown 2.5 m tall shades the ground under it); the 2D sun study still sees no
        caster where the plan holds no height, as for an estimated plant (#557)."""
        if record.height_cm is not None:
            return record.height_cm
        nominal = nominal_height_cm(record.kind)
        if nominal is not None:
            return nominal
        return estimated_height_of(record)

    def uses_the_plain_block(self, record: Record) -> bool:
        """A polygon-footprint record whose ground is not one plain outline (several
        rings, a hole, or a resolved outline): the shape function cannot build on
        it honestly, ``plain_block`` of its regions can. Never a polyline: a line
        is built from its centre line, whatever its stroke's rings are."""
        return record.shape != SHAPE_POLYLINE and not has_one_plain_ring(record)

    def raw(self, record: Record) -> tuple[MeshPart, ...]:
        """The shape function's parts, unfitted (``()`` when there is no height at all)
        — or the plain block of all regions for a record that is not one plain ring."""
        height = self.height_for(record)
        if height is None:
            return ()
        if self.uses_the_plain_block(record):
            return plain_block(record, height)
        return tuple(part for part in self._shape(record, height) if part.mesh.vertex_count)

    def fit_scale(self, record: Record) -> float:
        """How far the shape function missed the height (1.0 = built to it)."""
        height = self.height_for(record)
        return 1.0 if height is None else fit_scale(self.raw(record), height)

    def __call__(self, record: Record) -> tuple[MeshPart, ...]:
        height = self.height_for(record)
        if height is None:
            return ()
        return fit_parts(self.raw(record), height)


def footprint_of(record: Record) -> tuple[tuple[float, float], ...]:
    """The item's ONE simple outline (item-local, counter-clockwise), or ``()`` for
    a record without ground. For a shape function that needs exactly one — a
    gable roof, a bed's frame, a pot, a hedge. Raises ``ValueError`` for a record
    whose ground is several rings, a ring with holes or a resolved outline: such
    a record is built by ``plain_block`` (``BuiltBuilder`` sees to it before any
    shape function runs), and taking ``footprints[0]`` for the whole would drop a
    region, fill a hole or dress up a ring that is not the drawn one. NEVER build
    a polyline from this either: its ``footprints`` are the outline of its
    STROKE — a line is built from ``record.path``."""
    if not record.footprints:
        return ()
    if not has_one_plain_ring(record):
        resolved = ", a resolved outline" if record.params.get(PARAM_OUTLINE_RESOLVED) else ""
        raise ValueError(
            f"{record.kind} item {record.item_id!r} is not one plain ring "
            f"({len(record.footprints)} outer rings, "
            f"{sum(len(group) for group in record.holes)} holes{resolved}): "
            "build it with plain_block, not on footprints[0]")
    return record.footprints[0]


def corner_count(record: Record) -> int:
    """Every vertex of the record's ground — all outer rings and all holes — for a
    triangle budget that holds whichever way the record is built."""
    return (sum(len(ring) for ring in record.footprints)
            + sum(len(hole) for group in record.holes for hole in group))
