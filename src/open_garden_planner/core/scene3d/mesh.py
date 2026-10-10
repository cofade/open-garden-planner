"""Indexed triangle meshes for the 3D pipeline — plain numpy (Phase 17 L1.1).

A ``Mesh`` is what a builder returns and an engine sink uploads. Frame:
SCENE-frame AXES (x = East, y = North, z = up, centimetres) about the ITEM-LOCAL
origin — the record's ``Transform`` poses it, the engine adapter maps it to the
engine frame once (``frame.scene_to_engine_points``). A mesh therefore never
contains an item's scene position, which is what lets a move re-pose a Model
instead of rebuilding it.

Vertex attributes (the L0 spike's layout, ``ogp-3d-renderer`` §3):

=========  =======  ========  ==============================================
positions  float32  (n, 3)    centimetres
normals    float32  (n, 3)    unit length
colors     float32  (n, 4)    LINEAR RGBA (never sRGB — ``color.srgb_to_linear``)
uvs        float32  (n, 2)    builder-defined (the spike: u = wind weight, v = phase)
indices    uint32   (m, 3)    one row per triangle, counter-clockwise from outside
=========  =======  ========  ==============================================

Port map from ``spike_q3d/meshes.py::MeshData`` (L1.6 / L1.7 port builders with a
rename): ``MeshData`` → ``Mesh``; ``uv`` → ``uvs``; flat ``indices`` (M,) →
``(m, 3)``, and ``Mesh.from_arrays`` accepts either; ``MeshData.concat`` →
``Mesh.merge``; ``meshes.translated(mesh, x, y, z)`` → ``mesh.translated(x, y,
z)``; ``meshes.normal_vs_winding`` → ``normal_vs_winding`` (same instrument);
``MeshData.empty`` / ``bounds`` / ``vertex_count`` / ``triangle_count`` keep
their names. New: ``validate()``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

#: Material kinds a part can ask the sink for — the L0 spike's set
#: (``GardenSpike.qml``; pinned against it by a drift-guard test until L1.10).
#: ``vc`` = plain vertex colour.
MATERIAL_KINDS: Final[frozenset[str]] = frozenset(
    {"vc", "roof", "foliage", "grass", "glass", "water"}
)
#: Kinds shaded with bent (spherized) normals by design — exempt from the
#: "a flat face stores its winding normal" rule (``ogp-lush-cinematic`` §2).
BENT_NORMAL_KINDS: Final[frozenset[str]] = frozenset({"foliage", "grass"})

#: A flat face's stored normal must agree with its winding normal to this dot.
FLAT_NORMAL_MIN_DOT: Final = 0.99
#: ``|normal| - 1`` may be at most this (float32 normalisation is ~1e-7).
UNIT_NORMAL_TOLERANCE: Final = 1e-3

_SPEC: Final[tuple[tuple[str, type, int], ...]] = (
    ("positions", np.float32, 3),
    ("normals", np.float32, 3),
    ("colors", np.float32, 4),
    ("uvs", np.float32, 2),
)


class MeshError(ValueError):
    """A mesh that must not reach the engine; the message names the defect."""


def _f32(values: ArrayLike, width: int) -> NDArray[np.float32]:
    array = np.array(values, dtype=np.float32).reshape(-1, width)  # always a private copy
    array.setflags(write=False)
    return array


def _u32(values: ArrayLike) -> NDArray[np.uint32]:
    array = np.array(values, dtype=np.uint32).reshape(-1, 3)
    array.setflags(write=False)
    return array


@dataclass(frozen=True, eq=False)
class Mesh:
    """Indexed triangle mesh in the item-local frame (module docstring)."""

    positions: NDArray[np.float32]
    normals: NDArray[np.float32]
    colors: NDArray[np.float32]
    uvs: NDArray[np.float32]
    indices: NDArray[np.uint32]

    @staticmethod
    def from_arrays(
        positions: ArrayLike, normals: ArrayLike, colors: ArrayLike, uvs: ArrayLike,
        indices: ArrayLike,
    ) -> Mesh:
        """Build a mesh from anything array-like: dtypes are coerced, attributes
        reshaped to (n, k), indices (flat or (m, 3)) to (m, 3), all read-only.
        Shapes that do not fit raise ``ValueError`` here; content is judged by
        ``validate()``."""
        return Mesh(_f32(positions, 3), _f32(normals, 3), _f32(colors, 4), _f32(uvs, 2),
                    _u32(indices))

    @staticmethod
    def empty() -> Mesh:
        return _EMPTY

    @staticmethod
    def merge(meshes: Sequence[Mesh]) -> Mesh:
        """Concatenate meshes into one (static batching); empty ones are skipped."""
        parts = [m for m in meshes if m.vertex_count]
        if not parts:
            return _EMPTY
        if len(parts) == 1:
            return parts[0]
        offsets = np.cumsum([0] + [m.vertex_count for m in parts[:-1]])
        return Mesh.from_arrays(
            np.concatenate([m.positions for m in parts]),
            np.concatenate([m.normals for m in parts]),
            np.concatenate([m.colors for m in parts]),
            np.concatenate([m.uvs for m in parts]),
            np.concatenate([m.indices.astype(np.int64) + int(o)
                            for m, o in zip(parts, offsets, strict=True)]),
        )

    @property
    def vertex_count(self) -> int:
        return int(len(self.positions))

    @property
    def triangle_count(self) -> int:
        return int(len(self.indices))

    def bounds(self) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        """``(min xyz, max xyz)`` of the vertices."""
        if not self.vertex_count:
            raise MeshError("an empty mesh has no bounds")
        return self.positions.min(axis=0), self.positions.max(axis=0)

    def translated(self, dx: float, dy: float, dz: float) -> Mesh:
        """A copy moved WITHIN the item-local frame (a part of an item — never the
        item's scene position: that is the record's transform)."""
        offset = np.array([dx, dy, dz], dtype=np.float32)
        return Mesh.from_arrays(self.positions + offset, self.normals, self.colors, self.uvs,
                                self.indices)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mesh):
            return NotImplemented
        return self is other or all(
            np.array_equal(getattr(self, name), getattr(other, name))
            for name in ("positions", "normals", "colors", "uvs", "indices")
        )

    def validate(self, *, check_winding: bool = True) -> None:
        """Raise ``MeshError`` naming the first defect; return None for a sound mesh.

        Checked, in this order: dtypes; shapes (attributes (n, k) with one n,
        indices (m, 3)); finite values; index bounds; unit normals; and — unless
        ``check_winding`` is False (bent-normal foliage and grass) — that every
        FLAT face (three identical vertex normals) stores its winding normal to
        ``FLAT_NORMAL_MIN_DOT``: a face wound to look one way and lit from
        another is how L0 lit the wrong roof slope. Degenerate (zero-area)
        triangles have no winding normal and are skipped.
        """
        count = len(self.positions)
        for name, dtype, width in _SPEC:
            array = getattr(self, name)
            if array.dtype != dtype:
                raise MeshError(f"{name} must be {np.dtype(dtype).name}, got {array.dtype.name}")
            if array.shape != (count, width):
                raise MeshError(
                    f"{name} must have shape {(count, width)} (one row per vertex), got {array.shape}"
                )
        if self.indices.dtype != np.uint32:
            raise MeshError(f"indices must be uint32, got {self.indices.dtype.name}")
        if self.indices.ndim != 2 or self.indices.shape[1] != 3:
            raise MeshError(f"indices must have shape (m, 3), got {self.indices.shape}")
        for name, _dtype, _width in _SPEC:
            if not np.isfinite(getattr(self, name)).all():
                raise MeshError(f"non-finite values in {name}")
        if len(self.indices) and int(self.indices.max()) >= count:
            raise MeshError(f"index {int(self.indices.max())} out of bounds for {count} vertices")
        if count:
            lengths = np.linalg.norm(self.normals.astype(np.float64), axis=1)
            worst = int(np.abs(lengths - 1.0).argmax())
            if abs(float(lengths[worst]) - 1.0) > UNIT_NORMAL_TOLERANCE:
                raise MeshError(
                    f"normals must be unit length: vertex {worst} has length {float(lengths[worst])!r}"
                )
        if check_winding and len(self.indices):
            dots, flat = normal_vs_winding(self)
            if flat.any() and float(dots[flat].min()) < FLAT_NORMAL_MIN_DOT:
                worst = int(np.flatnonzero(flat)[dots[flat].argmin()])
                raise MeshError(
                    f"flat face (non-degenerate triangle {worst}) stores a normal that is not its "
                    f"winding normal: dot {float(dots[worst])!r} < {FLAT_NORMAL_MIN_DOT}"
                )


_EMPTY: Final = Mesh.from_arrays(
    np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 4)), np.zeros((0, 2)), np.zeros((0, 3))
)


def normal_vs_winding(mesh: Mesh) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
    """Per non-degenerate triangle: (stored normal · winding normal, is-flat mask).

    The flat-normal gate's instrument, ported from the spike. A triangle is
    *flat-shaded* when its three stored vertex normals are identical — how every
    flat builder emits faces; its stored normal must then equal the winding
    normal (dot ≥ 0.99). Smooth triangles (interpolated normals) report the dot
    of their mean normal.
    """
    tri = mesh.indices.reshape(-1, 3)
    p = mesh.positions.astype(np.float64)
    cross = np.cross(p[tri[:, 1]] - p[tri[:, 0]], p[tri[:, 2]] - p[tri[:, 0]])
    area2 = np.linalg.norm(cross, axis=1)
    keep = area2 > 1e-6
    winding = cross[keep] / area2[keep, None]
    n = mesh.normals.astype(np.float64)[tri[keep]]  # (T, 3 vertices, 3)
    flat = np.abs(n - n[:, :1]).max(axis=(1, 2)) < 1e-6
    stored = n.mean(axis=1)
    stored /= np.maximum(np.linalg.norm(stored, axis=1, keepdims=True), 1e-12)
    return (stored * winding).sum(axis=1), flat


@dataclass(frozen=True)
class MeshPart:
    """One mesh of an item plus how the sink shows it.

    ``material_kind``: one of ``MATERIAL_KINDS``. ``casts_shadow``: False for
    glass, water and for decoration without a resolved height (it casts none in
    2D either). ``tinted``: the sink multiplies the vertex colours with the
    item's ``Material.tint_linear()`` — the builder leaves them neutral (white,
    or a shading weight), so a recolour reaches the engine as
    ``update_material`` and never rebuilds this mesh. ``name`` labels the part
    ("walls", "roof") for logs and tests.
    """

    mesh: Mesh
    material_kind: str = "vc"
    casts_shadow: bool = True
    tinted: bool = False
    name: str = ""

    def __post_init__(self) -> None:
        if self.material_kind not in MATERIAL_KINDS:
            raise ValueError(
                f"unknown material_kind {self.material_kind!r}; expected one of {sorted(MATERIAL_KINDS)}"
            )

    def validate(self) -> None:
        """``Mesh.validate`` with the winding rule this part's kind is held to."""
        self.mesh.validate(check_winding=self.material_kind not in BENT_NORMAL_KINDS)
