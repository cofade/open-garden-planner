"""The builder seam: one record in, mesh parts out (Phase 17 L1.1, ADR-054).

A ``Builder`` is a PURE function of one ``Record``::

    Builder = Callable[[Record], tuple[MeshPart, ...]]

It returns meshes in the item-local frame (``mesh`` module) and may read ONLY
the record's geometry part — ``kind``, ``shape``, ``footprints``, ``path``,
``path_width_cm``, ``height_cm``, ``params`` (``record.GEOMETRY_FIELDS``). Not
the transform (the engine poses the Model), not the material (the sink tints),
not ``item_id`` / ``name`` / ``parent_id`` (take the seed from
``params["seed"]``). That rule is what makes the three signatures honest: the
pipeline calls a builder only when ``geometry_sig`` changed, so anything else a
builder read would go stale. ``verify_builder`` enforces it in tests.

``BuilderRegistry`` maps ``Record.kind`` to a builder; L1.6 (built world) and
L1.7 (plants) register theirs. Every other kind gets ``default_builder`` — the
honest v0: a prism of the footprint up to the resolved height, and nothing at
all for an item the plan gives no height (the ground bake, L1.5, paints flat
surfaces).
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable, Iterable, Sequence
from typing import Final, TypeAlias

import numpy as np

from .legacy import extrude_footprint
from .mesh import Mesh, MeshError, MeshPart
from .record import Material, Record, Ring, Transform

Builder: TypeAlias = Callable[[Record], tuple[MeshPart, ...]]

#: Truth gate "built heights" (``ogp-lush-cinematic`` §1): the top of a
#: shadow-casting item is its resolved height to this fraction. Plants are held
#: to 0.03 — L1.7 passes it to ``verify_builder``.
BUILT_HEIGHT_TOLERANCE: Final = 0.01


class BuilderContractError(Exception):
    """A builder broke the seam's contract (``verify_builder``)."""


def item_seed(item_id: str, salt: str = "") -> int:
    """Stable per-item seed, so no two plants are clones and none changes between
    runs. Ported from the spike (``meshes.item_seed``); feed it ``params["seed"]``."""
    digest = hashlib.md5(f"{item_id}:{salt}".encode(), usedforsecurity=False)
    return int(digest.hexdigest()[:12], 16)


def prism_mesh(footprints: Sequence[Ring], height_cm: float) -> Mesh:
    """Item-local prism(s) of ``footprints`` from z = 0 up to ``height_cm``.

    Neutral white vertex colours (a tinted part), flat normals, no bottom cap.
    Reuses the shipped triangulation and extrusion (``legacy.extrude_footprint``)
    — the 3D solid and the Qt 3D prism can never disagree. Rings with fewer than
    three vertices, and a non-positive height, give an empty mesh.
    """
    positions: list[float] = []
    normals: list[float] = []
    for ring in footprints:
        ring_positions, ring_normals = extrude_footprint(list(ring), height_cm, 0.0)
        positions.extend(ring_positions)
        normals.extend(ring_normals)
    if not positions:
        return Mesh.empty()
    count = len(positions) // 3
    return Mesh.from_arrays(
        positions,
        normals,
        np.ones((count, 4), np.float32),
        np.zeros((count, 2), np.float32),
        np.arange(count, dtype=np.uint32),
    )


def default_builder(record: Record) -> tuple[MeshPart, ...]:
    """The honest v0 for a kind without a builder of its own.

    With a height: ONE part — a prism of the local footprint whose top is exactly
    ``height_cm``, neutral and ``tinted`` (the sink colours it from the item's
    material, so a recolour is a material update). Without a height: no parts —
    the item is decoration, casts no shadow in 2D and has no solid in 3D.
    """
    if record.height_cm is None:
        return ()
    mesh = prism_mesh(record.footprints, record.height_cm)
    if not mesh.vertex_count:
        return ()
    return (MeshPart(mesh, "vc", casts_shadow=True, tinted=True, name="prism"),)


class BuilderRegistry:
    """``Record.kind`` → builder, with a default for every other kind.

    An instance, not a module global: the wiring (L1.3) creates one and hands it
    to each builder package's ``register(registry)`` — no import-order surprises.
    """

    def __init__(self, default: Builder = default_builder) -> None:
        self._default = default
        self._builders: dict[str, Builder] = {}

    def register(self, kind: str, builder: Builder, *, replace: bool = False) -> None:
        """Use ``builder`` for records of ``kind`` (an ObjectType name).

        Registering a kind twice is an error — two packages claiming one kind is
        a bug, not a preference — unless ``replace=True`` says it is meant.
        """
        if kind in self._builders and not replace:
            raise ValueError(f"a builder for kind {kind!r} is already registered")
        self._builders[kind] = builder

    def register_many(self, kinds: Iterable[str], builder: Builder, *,
                      replace: bool = False) -> None:
        for kind in kinds:
            self.register(kind, builder, replace=replace)

    def builder_for(self, kind: str) -> Builder:
        return self._builders.get(kind, self._default)

    def kinds(self) -> frozenset[str]:
        """The kinds with a builder of their own."""
        return frozenset(self._builders)

    def build(self, record: Record) -> tuple[MeshPart, ...]:
        """Run the builder of ``record.kind``. Exceptions propagate — ``SceneSync``
        is where a failing builder is contained."""
        return self.builder_for(record.kind)(record)


def checked_parts(parts: object) -> tuple[MeshPart, ...]:
    """``parts`` if it is a tuple of ``MeshPart``, else ``BuilderContractError``."""
    if not isinstance(parts, tuple) or not all(isinstance(p, MeshPart) for p in parts):
        raise BuilderContractError(
            f"a builder returns a tuple of MeshPart, got {type(parts).__name__}: {parts!r:.80}"
        )
    return parts


def _top_cm(parts: Sequence[MeshPart]) -> float | None:
    tops = [float(p.mesh.positions[:, 2].max()) for p in parts if p.mesh.vertex_count]
    return max(tops) if tops else None


def verify_builder(
    builder: Builder, record: Record, *, height_tolerance: float = BUILT_HEIGHT_TOLERANCE
) -> tuple[MeshPart, ...]:
    """Run ``builder`` on ``record`` and assert the seam's contract; return the parts.

    The test instrument for every builder (use it over each kind the builder
    handles and over the bench plans' records). Raises ``BuilderContractError``
    when the builder

    - does not return a tuple of ``MeshPart``;
    - is not deterministic (two calls differ);
    - reads the transform, the material or an unsigned field (``item_id``,
      ``name``, ``parent_id``): its output changed when only that changed;
    - emits a mesh ``MeshPart.validate`` rejects;
    - builds a shadow-casting item whose top is not its resolved height within
      ``height_tolerance`` (a fraction; truth gate "built heights").
    """
    parts = checked_parts(builder(record))
    if checked_parts(builder(record)) != parts:
        raise BuilderContractError("the builder is not deterministic: two calls on one record differ")
    variants: dict[str, Record] = {
        "transform": dataclasses.replace(record, transform=Transform(
            record.transform.east_cm + 137.25, record.transform.north_cm - 42.5,
            (record.transform.rotation_deg + 33.0) % 360.0, record.transform.base_cm + 7.0)),
        "material": dataclasses.replace(record, material=Material(
            record.material.key + "*", fill_rgba=(1, 2, 3, 255), stroke_rgba=(4, 5, 6, 255),
            pattern="VERIFY")),
        "item_id": dataclasses.replace(record, item_id=record.item_id + "-verify-builder"),
        "name": dataclasses.replace(record, name=record.name + " (verify builder)"),
        "parent_id": dataclasses.replace(
            record, parent_id=(record.parent_id or "") + "verify-builder-parent"),
    }
    for field, variant in variants.items():
        if checked_parts(builder(variant)) != parts:
            raise BuilderContractError(
                f"the builder's output depends on the record's {field}; a builder may read only "
                "the geometry part (kind, shape, footprints, path, path_width_cm, height_cm, params)"
            )
    for index, part in enumerate(parts):
        try:
            part.validate()
        except MeshError as error:
            raise BuilderContractError(f"part {index} ({part.name or part.material_kind}): {error}") from error
    top = _top_cm(parts)
    if record.height_cm is not None and top is not None:
        allowed = height_tolerance * record.height_cm
        if abs(top - record.height_cm) > allowed + 1e-4:
            raise BuilderContractError(
                f"the mesh top is {top:g} cm but the plan's resolved height is "
                f"{record.height_cm:g} cm (tolerance {height_tolerance:.0%}): truth before beauty"
            )
    return parts
