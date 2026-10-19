"""Scene contract v2 — one plan item as plain, immutable data (Phase 17 L1.1).

A ``Record`` is everything the 3D pipeline knows about one canvas item, and
everything a builder may read (ADR-064). It is produced on the GUI thread by
``ui/view3d/snapshot.snapshot_records`` and contains no Qt object.

Geometry is ITEM-LOCAL: ``footprints`` / ``holes`` / ``path`` are centimetres
relative to the item's own anchor (its centre), and ``transform`` places that
frame in the scene::

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
without it — the computation is deterministic — but the SAME geometry reached
along another float path differs in its last bits, and that must not read as an
edit. Measured on real items (``tests/integration/test_scene3d_snapshot.py``):

- a HOUSE's ridge is another item whose points the app re-writes by ``+ delta``
  on every move; unsnapped, 689 of 1,000 moves changed the HOUSE's geometry, so
  "move → transform only" was false. Snapped: 0 of 20,000 (the dust had grown
  to 1.1e-10 cm by then — three orders below the grid);
- undo is ``moveBy(-delta)`` and ``(0.1 + 0.7) - 0.7 == 0.09999999999999998``;
  next to the scene origin that reaches the position;
- a rectangle corner is ``x - (x + w/2)`` = ``-150.00000000000003``.

The quantum cannot hide a real edit: it is far below anything the UI can
express, and below the float32 resolution of a vertex further than ~1 cm from
its origin (the engine receives float32). It also stays below the 1e-6 cm bound
to which ``transform ∘ local footprint`` must reproduce the 2D footprint
(measured worst case 1.5e-7 cm). When float dust does straddle a grid line the
cost is one redundant sink call — never a wrong frame.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Final, TypeAlias

from .color import Rgba, srgb8_to_linear
from .polygon import (
    Point as Point,  # re-exported: `from .record import Point, Ring` predates polygon.py
)
from .polygon import Region, ring_area, ring_keyed
from .polygon import Ring as Ring

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

#: ``Record.params`` keys the snapshot writes (documented in §8.32.1).
PARAM_SEED: Final = "seed"  # str — the item id: the one seed source of a builder
PARAM_RADIUS_CM: Final = "radius_cm"  # float — circles: the footprint radius
PARAM_RIDGE: Final = "ridge"  # ((x, y), (x, y)) — a HOUSE's ridge ends, HOUSE-local
PARAM_SPECIES_KEY: Final = "species_key"  # str — canonical species key (ADR-016)
PARAM_SPECIES_NAME: Final = "species_name"  # str — common name (labels; NOT the sprite key)
#: str — the plant item's OWN species string, raw (``item.plant_species``: not stripped,
#: not replaced by species data). It is what the 2D renderer resolves the item's sprite
#: from, so the plant builder resolves its recipe from it too (L1.7, ruling R14); absent
#: when the string is empty.
PARAM_SPRITE_SPECIES: Final = "sprite_species"
PARAM_PLANT_CATEGORY: Final = "plant_category"  # str — PlantCategory name
PARAM_PATH_STYLE: Final = "path_style"  # str — PathFenceStyle name, when not NONE
PARAM_CONTAINER_MATERIAL: Final = "container_material"  # str — container_model key
#: ``(x, y)`` — where the record's local origin lies in the ITEM's own coordinates
#: (L1.5): the frame the 2D canvas paints the item in. A fill texture is anchored
#: at the item's coordinate origin — not at its centre — and a furniture sprite is
#: aligned to whole centimetres there, so the ground bake paints in that frame:
#: an item point is ``paint_origin + local point``. It changes with the item's
#: geometry (a resize, a vertex edit) and never with a move or a turn. Absent for
#: a plant, which is never painted on the ground.
PARAM_PAINT_ORIGIN: Final = "paint_origin"
#: True — present ONLY when the drawn polygon could not be used as it was (it
#: crosses or touches itself) and ``footprints`` / ``holes`` are what the snapshot
#: resolved it into: not the drawn vertices, possibly several rings, and anything
#: that referred to the drawn outline (a HOUSE's ``ridge``) is left out.
PARAM_OUTLINE_RESOLVED: Final = "outline_resolved"

#: Tint of a part whose item has neither a fill nor a stroke colour (the legacy
#: collector's fallback, ``ui/view3d/snapshot._FALLBACK_COLOR``).
FALLBACK_RGBA: Final[Rgba] = (158, 158, 148, 255)


#: The largest length a record may hold, in cm: 10 km. A height, a stroke width,
#: a radius, a coordinate of the local geometry, a position, a float param —
#: nothing in a garden plan is taller, wider or farther from its origin. The
#: bound is decided HERE, once, for every consumer: a plan file edited by hand
#: can hold ``"object_height_cm": 1e300`` — a finite, positive float, which the
#: mesh's float32 turns into infinity — and no builder should have to know. At
#: the bound a float32 coordinate still resolves 0.06 cm.
MAX_LENGTH_CM: Final = 1e6
#: The smallest height a record may hold, in cm: ten micrometres. The same
#: hand-edited plan can hold ``1e-300`` — positive, finite, and ZERO in float32:
#: a solid without a height, with walls of no area, that validates. Below this a
#: height is no more a height than one above ``MAX_LENGTH_CM`` is.
MIN_HEIGHT_CM: Final = 1e-3
#: Keys of float params that are NOT lengths in cm. Every other float in
#: ``Params`` — also inside a tuple — is taken for one and held to
#: ``MAX_LENGTH_CM``: the two the snapshot writes are (``radius_cm``, ``ridge``),
#: and a builder turns what it reads into geometry. A later float param that is
#: a ratio, an angle or a count of days names its key HERE; it is then checked
#: for being finite and for nothing else. Empty today.
DIMENSIONLESS_PARAMS: Final[frozenset[str]] = frozenset()


class RecordRangeError(ValueError):
    """A length of a record lies beyond ``MAX_LENGTH_CM`` (or is infinite), or
    its height below ``MIN_HEIGHT_CM``."""


def _beyond(reach: float) -> str:
    return f"a coordinate of {reach!r} cm is beyond what a plan can hold (±{MAX_LENGTH_CM:g} cm)"


def _check_length(what: str, value: float) -> None:
    if not -MAX_LENGTH_CM <= value <= MAX_LENGTH_CM:
        raise RecordRangeError(
            f"{what} of {value!r} cm is beyond what a plan can hold (±{MAX_LENGTH_CM:g} cm)"
        )


@ring_keyed()
def _ring_facts(ring: Ring) -> tuple[float, float]:
    """``(signed area, largest absolute coordinate)`` of a ring — the two things a
    record checks on every ring of every snapshot, behind ONE lookup (a tuple's
    hash is recomputed on each lookup, and that is most of the cost). Remembered
    by the vertices held, not by the number of rings (``polygon.ring_keyed``)."""
    return ring_area(ring), max((max(abs(x), abs(y)) for x, y in ring), default=0.0)


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
        _check_length("a position east", self.east_cm)
        _check_length("a position north", self.north_cm)
        _check_length("a base height", self.base_cm)

    def with_base(self, base_cm: float) -> Transform:
        """The same pose standing on another ground height."""
        return replace(self, base_cm=base_cm)


def _check_rgba(name: str, value: object) -> None:
    if value is None:
        return
    if (not isinstance(value, tuple) or len(value) != 4
            or any(type(c) is not int or not 0 <= c <= 255 for c in value)):
        raise ValueError(f"Material.{name} must be four ints in 0..255 or None, got {value!r}")


#: The pen styles, caps and joins a ``Paint`` can name — Qt's enum member names,
#: as strings: this package imports no Qt, and the ground bake looks them up by name.
PEN_STYLES: Final[frozenset[str]] = frozenset({
    "NoPen", "SolidLine", "DashLine", "DotLine", "DashDotLine", "DashDotDotLine",
})
PEN_CAPS: Final[frozenset[str]] = frozenset({"FlatCap", "SquareCap", "RoundCap"})
PEN_JOINS: Final[frozenset[str]] = frozenset({"MiterJoin", "BevelJoin", "RoundJoin", "SvgMiterJoin"})


@dataclass(frozen=True, slots=True)
class Paint:
    """How the 2D canvas paints an item's SURFACE, beyond its two colours and its
    pattern — what the ground bake needs to paint a flat item exactly as the
    canvas does (Phase 17 L1.5). Plain data; part of the ``Material``, so a
    change of it re-bakes ground tiles and never rebuilds a mesh.

    The snapshot gives one to every record but a plant's (a plant is never
    painted on the ground). Whether a record IS painted is not said here: the
    ground shows it while the scene holds no solid for it.

    - ``stroke_width_cm``: the width of the pen the canvas strokes the item's
      OUTLINE with — a filled shape's. 0.0 for a polyline: its stroke is its
      geometry (``Record.path_width_cm``), and a wider line is a geometry
      change.
    - ``stroke_style``, ``stroke_cap``, ``stroke_join``: that pen's style, cap
      and join, by Qt's names (``PEN_STYLES`` …). Its colour is
      ``Material.stroke_rgba``.
    - ``opacity``: the item's effective opacity, its layer's included.
    - ``rotation_deg``: the turn of the item's own coordinates that the record's
      ``Transform`` does NOT carry — a CIRCLE's. A circle turned about its centre
      is the same footprint and the same solid (its transform stays unturned,
      its geometry too: no builder runs, nothing is posed anew), but what the
      canvas paints in the circle's coordinates turns with it: a fill texture, a
      dash pattern, a sprite. So that turn is a fact of the PAINT — a material
      change, which re-bakes ground tiles and never rebuilds a mesh. 0.0 for
      every other shape (their transform carries the turn).

    Where the canvas anchors a fill texture is not here either: that is the
    item's own coordinate origin, a fact of its GEOMETRY
    (``params["paint_origin"]``).
    """

    stroke_width_cm: float = 0.0
    stroke_style: str = "SolidLine"
    stroke_cap: str = "SquareCap"
    stroke_join: str = "BevelJoin"
    opacity: float = 1.0
    rotation_deg: float = 0.0

    def __post_init__(self) -> None:
        if self.stroke_style not in PEN_STYLES:
            raise ValueError(f"Paint.stroke_style {self.stroke_style!r} is not one of {sorted(PEN_STYLES)}")
        if self.stroke_cap not in PEN_CAPS:
            raise ValueError(f"Paint.stroke_cap {self.stroke_cap!r} is not one of {sorted(PEN_CAPS)}")
        if self.stroke_join not in PEN_JOINS:
            raise ValueError(f"Paint.stroke_join {self.stroke_join!r} is not one of {sorted(PEN_JOINS)}")
        if not (math.isfinite(self.stroke_width_cm) and self.stroke_width_cm >= 0.0):
            raise ValueError(f"Paint.stroke_width_cm is a finite length >= 0, got {self.stroke_width_cm!r}")
        _check_length("a stroke width", self.stroke_width_cm)
        if not 0.0 <= self.opacity <= 1.0:  # also False for a NaN
            raise ValueError(f"Paint.opacity lies in 0..1, got {self.opacity!r}")
        if not math.isfinite(self.rotation_deg):
            raise ValueError(f"Paint.rotation_deg must be finite, got {self.rotation_deg!r}")


@dataclass(frozen=True, slots=True)
class Material:
    """How an item is coloured in the plan — plain sRGB data, no engine material.

    ``key`` is the palette key a builder or sink looks colours up under: the
    item's ObjectType name. ``fill_rgba`` / ``stroke_rgba`` are the item's own
    8-bit sRGB colours (None when it has none — a polyline has no fill),
    ``pattern`` its fill-pattern name (``FillPattern`` member) when it has one.
    ``paint`` (L1.5) is the rest of how the canvas paints the item's surface —
    present on a record the ground bake can show, None on every other.
    A change of any of them is a material change and never rebuilds a mesh —
    which is why a builder must not read this class (``build.verify_builder``).
    """

    key: str
    fill_rgba: Rgba | None = None
    stroke_rgba: Rgba | None = None
    pattern: str | None = None
    paint: Paint | None = None

    def __post_init__(self) -> None:
        _check_rgba("fill_rgba", self.fill_rgba)
        _check_rgba("stroke_rgba", self.stroke_rgba)
        if self.paint is not None and not isinstance(self.paint, Paint):
            raise TypeError(f"Material.paint is a Paint or None, got {type(self.paint).__name__}")

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
        if key not in DIMENSIONLESS_PARAMS and not -MAX_LENGTH_CM <= value <= MAX_LENGTH_CM:
            raise RecordRangeError(
                f"param {key!r}: a value of {value!r} cm is beyond what a plan can hold "
                f"(±{MAX_LENGTH_CM:g} cm) — a float param is taken for a length in cm unless its "
                "key is listed in record.DIMENSIONLESS_PARAMS"
            )
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

    A FLOAT is taken for a length in centimetres and must lie within
    ``±MAX_LENGTH_CM`` (``RecordRangeError`` otherwise) — also inside a tuple,
    as a ridge's coordinates are. That is right for every float param there is
    (``radius_cm``, ``ridge``). A float that is not a length is exempted by
    naming its key in ``DIMENSIONLESS_PARAMS``; an ``int``, a ``str`` and a
    ``bool`` are never bounded.
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
    "kind", "shape", "footprints", "path", "path_width_cm", "height_cm", "params", "holes",
    "outline",
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
    - ``footprints``: the ground the item covers, as OUTER rings only — simple
      item-local polygons in cm, counter-clockwise seen from above (signed area
      > 0; a clockwise or area-less ring is refused). One ring for most items;
      possibly several for a polyline whose stroke falls apart and for a polygon
      that crosses itself, which the snapshot resolves (``params`` then says
      ``outline_resolved``; the ring COUNT says nothing — such a polygon may
      resolve into one ring, several, or rings with holes). The orientation is
      enforced here; that a region can be BUILT is the producer's duty (testing
      it means triangulating it): the snapshot keeps only regions for which
      ``polygon.is_buildable_region`` holds — simple rings, holes inside,
      a proven triangulation — and ``build.prism_mesh`` refuses any other.
    - ``holes``: what is cut out of them. ``holes[i]`` are the hole rings of
      ``footprints[i]`` — simple, CLOCKWISE (signed area < 0), inside that outer.
      ``()`` when no ring has a hole (the usual case); otherwise one entry per
      outer. A closed fence is the case that needs it: its stroke is one outer
      ring and one hole, and a builder that extrudes the hole as a solid turns
      3.6 m² of fence into an 80 m² slab. A polygon drawn crossing itself can
      enclose a pocket, so holes are not a stroke's alone. Iterate ``regions``
      to get both.
    - ``path`` / ``path_width_cm``: a polyline's centre line (item-local) and
      stroke width — fences and walls are built from these, not from the strip.
      ``()`` / ``None`` for every other shape.
    - ``height_cm``: the resolved ``effective_height_cm(..., at_date)`` — a
      positive finite number — or None when the resolver gives none: then the
      item is decoration and casts no shadow, exactly as in 2D (``casts_shadow``).
    - ``params``: the rest (``PARAM_*`` keys).
    - ``outline`` (L1.5): a POLYGON's vertices as they were DRAWN — in the drawn
      order, not turned, not resolved — when ``footprints`` is not that polygon:
      the outline crosses or touches itself (``outline_resolved``), or no
      regions could be made of it at all (then ``footprints`` is empty: nothing
      can be BUILT of this record, and a consumer that needs area finds none in
      ``regions``). ``()`` otherwise — ``footprints[0]`` then IS the drawn
      polygon. Only a record without a height carries one: it is what the
      ground bake fills (with the canvas's odd-even rule), never a builder's.

    ``transform`` and ``material`` have a signature each. ``item_id``, ``name``
    (the display name) and ``parent_id`` (the id of the bed a plant is LINKED to —
    the item's ``parent_bed_id``, carried as it is) have none. A builder never
    reads it.

    For a consumer: ``parent_id`` is a link, not a location. It may name NO record
    of the snapshot (a hidden parent, one beyond the contract's range, one whose
    outline cannot be built) — never index ``records[record.parent_id]`` unchecked
    — and a parented record may stand at ``transform.base_cm == 0.0``: its parent
    holds no soil or has no height, the item's centre is outside the parent's
    shape, or the parent got no record. Where an item stands is ``base_cm`` and
    nothing else (L1.6: ``ui/canvas/footprints.item_base_cm`` gives it, and
    ``snapshot_records`` grounds a record whose parent has none).
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
    holes: tuple[tuple[Ring, ...], ...] = ()
    outline: Ring = ()
    geometry_sig: int = field(init=False, compare=False, repr=False)
    transform_sig: int = field(init=False, compare=False, repr=False)
    material_sig: int = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.shape not in SHAPES:
            raise ValueError(f"unknown shape {self.shape!r}; expected one of {SHAPES}")
        if self.height_cm is not None:
            if not self.height_cm > 0.0:
                raise ValueError(
                    f"height_cm is a positive finite number or None, got {self.height_cm!r}"
                )
            _check_length("a height", self.height_cm)  # an infinite one too
            if self.height_cm < MIN_HEIGHT_CM:
                raise RecordRangeError(
                    f"a height of {self.height_cm!r} cm is below what a solid can have "
                    f"({MIN_HEIGHT_CM:g} cm)"
                )
        if self.path_width_cm is not None:
            if not math.isfinite(self.path_width_cm):
                raise ValueError(f"path_width_cm is finite or None, got {self.path_width_cm!r}")
            _check_length("a stroke width", self.path_width_cm)
        for ring in self.footprints:
            area, reach = _ring_facts(ring)
            if not reach <= MAX_LENGTH_CM:
                raise RecordRangeError(_beyond(reach))
            if not area > 0.0:
                raise ValueError(
                    "footprints holds OUTER rings: counter-clockwise with a positive area "
                    f"(got signed area {area!r} cm² for a ring of {len(ring)} vertices); "
                    "holes go into `holes`"
                )
        if self.path and not _ring_facts(self.path)[1] <= MAX_LENGTH_CM:
            raise RecordRangeError(_beyond(_ring_facts(self.path)[1]))
        if self.outline and not _ring_facts(self.outline)[1] <= MAX_LENGTH_CM:
            raise RecordRangeError(_beyond(_ring_facts(self.outline)[1]))
        if self.holes:
            if len(self.holes) != len(self.footprints):
                raise ValueError(
                    f"holes has {len(self.holes)} entries for {len(self.footprints)} footprints: "
                    "holes[i] are the holes of footprints[i]"
                )
            if not any(self.holes):
                object.__setattr__(self, "holes", ())  # one spelling of "no holes"
            for group in self.holes:
                for ring in group:
                    area, reach = _ring_facts(ring)
                    if not reach <= MAX_LENGTH_CM:
                        raise RecordRangeError(_beyond(reach))
                    if not area < 0.0:
                        raise ValueError(
                            "a hole ring is clockwise with a negative signed area "
                            f"(got {area!r} cm²)"
                        )
        object.__setattr__(self, "geometry_sig", hash((
            self.kind, self.shape, self.footprints, self.path, self.path_width_cm,
            self.height_cm, self.params, self.holes, self.outline,
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

    @property
    def regions(self) -> tuple[Region, ...]:
        """``(outer, holes)`` for every footprint ring — what a builder, the ground
        bake or a picker iterates instead of ``footprints`` alone."""
        if not self.holes:
            return tuple((outer, ()) for outer in self.footprints)
        return tuple(zip(self.footprints, self.holes, strict=True))

    @property
    def plan_area_cm2(self) -> float:
        """The ground the item covers, in cm²: the outers minus their holes."""
        return (sum(ring_area(ring) for ring in self.footprints)
                + sum(ring_area(ring) for group in self.holes for ring in group))

    def same_geometry(self, other: Record) -> bool:
        """Equal geometry part — the signature first, then the values (collisions)."""
        return (
            self.geometry_sig == other.geometry_sig
            and self.kind == other.kind
            and self.shape == other.shape
            and self.height_cm == other.height_cm
            and self.path_width_cm == other.path_width_cm
            and self.footprints == other.footprints
            and self.holes == other.holes
            and self.path == other.path
            and self.params == other.params
            and self.outline == other.outline
        )

    def same_transform(self, other: Record) -> bool:
        return self.transform_sig == other.transform_sig and self.transform == other.transform

    def same_material(self, other: Record) -> bool:
        return self.material_sig == other.material_sig and self.material == other.material
