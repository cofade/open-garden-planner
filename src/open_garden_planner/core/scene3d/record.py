"""Scene contract v2 — one plan item as plain, immutable data (Phase 17 L1.1).

A ``Record`` is everything the 3D pipeline knows about one canvas item, and
everything a builder may read (ADR-054). It is produced on the GUI thread by
``ui/view3d/snapshot.snapshot_records`` and contains no Qt object.

Geometry is ITEM-LOCAL: ``footprints`` / ``path`` are centimetres relative to
the item's own anchor (its centre), and ``transform`` places that frame in the
scene::

    scene = (east_cm, north_cm) + R(rotation_deg) · local        base_cm lifts it

``R`` turns counter-clockwise seen from above with north up (+East toward
+North) — the same sense as Qt's ``setRotation`` on the Y-up canvas, proven
against ``mapToScene`` in ``tests/integration/test_scene3d_snapshot.py``. So
moving or rotating an item changes its ``transform`` and nothing else, and the
engine re-poses a Model instead of rebuilding a mesh.

Three signatures say WHAT changed between two snapshots of the same item:

- ``geometry_sig`` — ``GEOMETRY_FIELDS``: anything that changes the mesh;
- ``transform_sig`` — the transform;
- ``material_sig`` — the material.

``UNSIGNED_FIELDS`` (the id, the display name, the parent link) are in none, and
selection and hover are not in the record at all. A signature is a Python
``hash``: equal values give equal signatures, but equal signatures do NOT prove
equal values (``hash(-1.0) == hash(-2.0)``), so ``same_geometry`` /
``same_transform`` / ``same_material`` confirm with the values. Signatures are
compared within one session only and between two snapshots of the SAME item;
they are not a content address across items (``params["seed"]`` is the item id).

Quantisation. Every length is snapped to 1e-7 cm (one nanometre) and every angle
to 1e-9 degrees when a record is built. An unchanged scene snapshots identically
without it — the computation is deterministic — but the SAME item reached along
another float path (undo is ``moveBy(-delta)``, a centre is ``x + w/2 - w/2``)
differs in the last bits; snapped, the two paths give one record. The quantum
cannot hide a real edit: it is far below anything the UI can express, and below
the float32 resolution of a vertex further than ~1 cm from its origin (the
engine receives float32). It stays below the 1e-6 cm bound to which
``transform ∘ local footprint`` must reproduce the 2D footprint.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Final, TypeAlias

from .color import Rgba, srgb8_to_linear

Point: TypeAlias = tuple[float, float]
Ring: TypeAlias = tuple[Point, ...]
ParamValue: TypeAlias = "str | int | float | bool | None | tuple[ParamValue, ...]"

#: Decimal places of a length in cm: 1e-7 cm = 1 nm (module docstring).
LENGTH_DECIMALS: Final = 7
#: Decimal places of an angle in degrees.
ANGLE_DECIMALS: Final = 9

#: The footprint shapes a record can have (``Record.shape``).
SHAPE_CIRCLE: Final = "circle"
SHAPE_ELLIPSE: Final = "ellipse"
SHAPE_RECTANGLE: Final = "rectangle"
SHAPE_POLYGON: Final = "polygon"
SHAPE_POLYLINE: Final = "polyline"
SHAPES: Final[tuple[str, ...]] = (
    SHAPE_CIRCLE, SHAPE_ELLIPSE, SHAPE_RECTANGLE, SHAPE_POLYGON, SHAPE_POLYLINE,
)

#: ``Record.params`` keys the snapshot writes (documented in §8.26.1).
PARAM_SEED: Final = "seed"  # str — the item id: the one seed source of a builder
PARAM_RADIUS_CM: Final = "radius_cm"  # float — circles: the footprint radius
PARAM_RIDGE: Final = "ridge"  # ((x, y), (x, y)) — a HOUSE's ridge ends, HOUSE-local
PARAM_SPECIES_KEY: Final = "species_key"  # str — canonical species key (ADR-016)
PARAM_SPECIES_NAME: Final = "species_name"  # str — common name (archetype lookup)
PARAM_PLANT_CATEGORY: Final = "plant_category"  # str — PlantCategory name
PARAM_PATH_STYLE: Final = "path_style"  # str — PathFenceStyle name, when not NONE
PARAM_CONTAINER_MATERIAL: Final = "container_material"  # str — container_model key

#: Tint of a part whose item has neither a fill nor a stroke colour (the legacy
#: collector's fallback, ``ui/view3d/snapshot._FALLBACK_COLOR``).
FALLBACK_RGBA: Final[Rgba] = (158, 158, 148, 255)


def quantize_cm(value: float) -> float:
    """Snap a length to the record grid; ``+ 0.0`` turns ``-0.0`` into ``0.0``."""
    return round(value, LENGTH_DECIMALS) + 0.0


def quantize_deg(value: float) -> float:
    """Snap an angle to the record grid, normalised to ``[0, 360)``."""
    angle = round(value % 360.0, ANGLE_DECIMALS)
    return 0.0 if angle >= 360.0 else angle + 0.0


@dataclass(frozen=True, slots=True)
class Transform:
    """Where an item's local frame sits in the scene — a rigid pose.

    ``east_cm`` / ``north_cm``: scene position of the local origin (the item's
    anchor). ``rotation_deg``: turn about the up axis, counter-clockwise seen
    from above with north up, in ``[0, 360)``. ``base_cm``: height of the local
    ground plane above the scene ground (0 in L1.1; L1.6 stands a plant on its
    parent bed's soil with it).
    """

    east_cm: float = 0.0
    north_cm: float = 0.0
    rotation_deg: float = 0.0
    base_cm: float = 0.0

    def __post_init__(self) -> None:
        if not (math.isfinite(self.east_cm) and math.isfinite(self.north_cm)
                and math.isfinite(self.rotation_deg) and math.isfinite(self.base_cm)):
            bad = [name for name in ("east_cm", "north_cm", "rotation_deg", "base_cm")
                   if not math.isfinite(getattr(self, name))]
            raise ValueError(f"Transform has non-finite {', '.join(bad)}: {self!r}")

    def with_base(self, base_cm: float) -> Transform:
        """The same pose standing on another ground height."""
        return replace(self, base_cm=base_cm)


def _check_rgba(name: str, value: object) -> None:
    if value is None:
        return
    if (not isinstance(value, tuple) or len(value) != 4
            or any(type(c) is not int or not 0 <= c <= 255 for c in value)):
        raise ValueError(f"Material.{name} must be four ints in 0..255 or None, got {value!r}")


@dataclass(frozen=True, slots=True)
class Material:
    """How an item is coloured in the plan — plain sRGB data, no engine material.

    ``key`` is the palette key a builder or sink looks colours up under: the
    item's ObjectType name. ``fill_rgba`` / ``stroke_rgba`` are the item's own
    8-bit sRGB colours (None when it has none — a polyline has no fill),
    ``pattern`` its fill-pattern name (``FillPattern`` member) when it has one.
    A change of any of them is a material change and never rebuilds a mesh —
    which is why a builder must not read this class (``build.verify_builder``).
    """

    key: str
    fill_rgba: Rgba | None = None
    stroke_rgba: Rgba | None = None
    pattern: str | None = None

    def __post_init__(self) -> None:
        _check_rgba("fill_rgba", self.fill_rgba)
        _check_rgba("stroke_rgba", self.stroke_rgba)

    @property
    def tint_rgba(self) -> Rgba:
        """The colour a ``MeshPart(tinted=True)`` is multiplied with, opaque.

        The fill colour; an item without one (a fence, a wall, a path) is seen
        in its stroke colour in 2D, so that is used; ``FALLBACK_RGBA`` otherwise.
        Alpha is forced to 255: a translucent 2D fill is still a solid body.
        """
        source = self.fill_rgba or self.stroke_rgba or FALLBACK_RGBA
        return (source[0], source[1], source[2], 255)

    def tint_linear(self) -> tuple[float, float, float, float]:
        """``tint_rgba`` in linear light — what the engine multiplies with."""
        return srgb8_to_linear(self.tint_rgba)


def _check_param_value(key: str, value: object) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"param {key!r} holds a non-finite float")
        return
    if isinstance(value, tuple):
        for element in value:
            _check_param_value(key, element)
        return
    raise TypeError(
        f"param {key!r}: {type(value).__name__} is not plain immutable data "
        "(str, int, float, bool, None or a tuple of those)"
    )


class Params(Mapping[str, ParamValue]):
    """The rest of what a builder needs: an immutable, hashable, SORTED mapping.

    Values are plain immutable data — ``str``, ``int``, ``float`` (finite),
    ``bool``, ``None`` or tuples of those — so a ``Params`` can be hashed,
    compared and sent across threads. Sorted by key, so two mappings with the
    same content are equal and hash alike whatever order they were built in.
    """

    __slots__ = ("_hash", "_items")
    _items: tuple[tuple[str, ParamValue], ...]
    _hash: int

    def __init__(
        self, values: Mapping[str, ParamValue] | Iterable[tuple[str, ParamValue]] = ()
    ) -> None:
        pairs = dict(values)
        for key, value in pairs.items():
            if not isinstance(key, str):
                raise TypeError(f"param keys are strings, got {type(key).__name__}")
            _check_param_value(key, value)
        items = tuple(sorted(pairs.items()))
        object.__setattr__(self, "_items", items)
        object.__setattr__(self, "_hash", hash(items))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Params is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Params is immutable")

    def __getitem__(self, key: str) -> ParamValue:
        for name, value in self._items:
            if name == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (name for name, _value in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Params):
            return self._items == other._items
        return NotImplemented

    def __repr__(self) -> str:
        return f"Params({dict(self._items)!r})"

    def __reduce__(self) -> tuple[type[Params], tuple[dict[str, ParamValue]]]:
        return (Params, (dict(self._items),))

    def merged(self, more: Mapping[str, ParamValue]) -> Params:
        """A new mapping with ``more`` laid over this one (L1.6 / L1.7 extend records)."""
        return Params({**dict(self._items), **more})


EMPTY_PARAMS: Final = Params()

#: Field groups of ``Record`` — pinned by a drift-guard test: every field is in
#: exactly one. A new field must be put into a signature or declared unsigned.
GEOMETRY_FIELDS: Final[tuple[str, ...]] = (
    "kind", "shape", "footprints", "path", "path_width_cm", "height_cm", "params",
)
TRANSFORM_FIELDS: Final[tuple[str, ...]] = ("transform",)
MATERIAL_FIELDS: Final[tuple[str, ...]] = ("material",)
UNSIGNED_FIELDS: Final[tuple[str, ...]] = ("item_id", "name", "parent_id")
SIGNATURE_FIELDS: Final[tuple[str, ...]] = ("geometry_sig", "transform_sig", "material_sig")


@dataclass(frozen=True, slots=True)
class Record:
    """One plan item, ready for a builder and an engine sink (module docstring).

    Geometry part (``GEOMETRY_FIELDS`` — all a builder may read):

    - ``kind``: the ObjectType name (``"HOUSE"``, ``"TREE"`` …) — picks the builder.
    - ``shape``: one of ``SHAPES`` — what the footprint was drawn as.
    - ``footprints``: the ground the item covers, item-local polygon(s) in cm.
      One ring for every shape but a polyline, whose stroke can come back as
      several (``core.shadow_geometry.polyline_footprint``).
    - ``path`` / ``path_width_cm``: a polyline's centre line (item-local) and
      stroke width — fences and walls are built from these, not from the strip.
      ``()`` / ``None`` for every other shape.
    - ``height_cm``: the resolved ``effective_height_cm(..., at_date)``, or None
      when the resolver gives none — then the item is decoration and casts no
      shadow, exactly as in 2D (``casts_shadow``).
    - ``params``: the rest (``PARAM_*`` keys).

    ``transform`` and ``material`` have a signature each. ``item_id``, ``name``
    (the display name) and ``parent_id`` (the plant's bed — resolved into
    ``transform.base_cm`` by the snapshot, never read by a builder) have none.
    """

    item_id: str
    kind: str
    shape: str
    footprints: tuple[Ring, ...]
    transform: Transform
    material: Material
    height_cm: float | None = None
    path: Ring = ()
    path_width_cm: float | None = None
    params: Params = EMPTY_PARAMS
    parent_id: str | None = None
    name: str = ""
    geometry_sig: int = field(init=False, compare=False, repr=False)
    transform_sig: int = field(init=False, compare=False, repr=False)
    material_sig: int = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.shape not in SHAPES:
            raise ValueError(f"unknown shape {self.shape!r}; expected one of {SHAPES}")
        object.__setattr__(self, "geometry_sig", hash((
            self.kind, self.shape, self.footprints, self.path, self.path_width_cm,
            self.height_cm, self.params,
        )))
        object.__setattr__(self, "transform_sig", hash(self.transform))
        object.__setattr__(self, "material_sig", hash(self.material))

    @property
    def base_cm(self) -> float:
        """Height of this item's ground plane (``transform.base_cm``)."""
        return self.transform.base_cm

    @property
    def casts_shadow(self) -> bool:
        """True when the plan gives the item a height — the 2D shadow rule."""
        return self.height_cm is not None

    def same_geometry(self, other: Record) -> bool:
        """Equal geometry part — the signature first, then the values (collisions)."""
        return (
            self.geometry_sig == other.geometry_sig
            and self.kind == other.kind
            and self.shape == other.shape
            and self.height_cm == other.height_cm
            and self.path_width_cm == other.path_width_cm
            and self.footprints == other.footprints
            and self.path == other.path
            and self.params == other.params
        )

    def same_transform(self, other: Record) -> bool:
        return self.transform_sig == other.transform_sig and self.transform == other.transform

    def same_material(self, other: Record) -> bool:
        return self.material_sig == other.material_sig and self.material == other.material
