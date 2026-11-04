"""The object builders' kit: an object's box, bevelled parts, round parts (Phase 17 L4).

What the L4 object builders (``furniture``, ``play``, ``utility``,
``structures``) share, on top of ``primitives``:

- **The object box.** A furniture sprite is drawn STRETCHED into its item's
  rectangle (``RectangleItem.paint``), its top edge along the rectangle's +y side
  (the canvas flips the pixmap back upright). So an object is built in the
  item-local frame of that rectangle: ``ObjectBox`` is the footprint's local
  bounding box, and sprite x / y map to local x / y. A footprint that is not that
  box (a polygon typed as a bench, a rectangle turned inside a scaled group) is
  not an object box: ``object_box`` returns None and the builder shows the
  honest block (``common.plain_block``). A circle's box is its radius.
- **Bevelled parts.** ``slab`` (an upright box, chamfered), ``beam`` (a box
  between any two points — a leg, a rafter, a slanted slat), ``board`` (a
  horizontal plank with chamfered long edges). Every face stores its winding
  normal (``primitives.flat_mesh``).
- **Round parts.** ``turned`` (a ``lathe`` about a vertical axis anywhere),
  ``ball`` (a smooth UV sphere, squashed with correct normals) and ``rod`` (thin
  tubes).
- **Turning.** ``turned_mesh`` turns a finished mesh about a horizontal axis (a
  wheel lies on its side) — positions and normals alike.

Heights are given, never derived, so a builder can put its top EXACTLY at the
item's height (``common``: the top is the height). Qt-free: numpy only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import ArrayLike

from ..build import item_seed
from ..mesh import Mesh
from ..record import PARAM_RADIUS_CM, PARAM_SEED, SHAPE_CIRCLE, Record
from .common import footprint_of
from .primitives import (
    F64,
    bevelled_boxes,
    boxes,
    flat_mesh,
    lathe,
    plank,
    quad_triangles,
    signed_area,
    tubes,
)

#: A footprint whose area is at least this share of its local bounding box is that
#: box (a rectangle item's ring IS its box). A circle is judged by its shape and its
#: radius, never by this.
BOX_AREA_SHARE: Final = 0.97
#: The most copies of one repeated element an object makes — staves, slats, bays,
#: lattice bars, boards. A plan item may be kilometres long (``record.MAX_LENGTH_CM``):
#: beyond this the elements are spaced wider, so every builder is bounded by
#: construction, whatever the plan holds.
MAX_REPEATS: Final = 240
#: Segments of a turned part: the 2D circle footprint's 24 (a rim of radius r IS
#: the plan's 24-gon, ``primitives.lathe``).
ROUND_SEGMENTS: Final = 24
#: Below 3 cm a rim, joint or inset has no room: retain the data as a plain prism.
MIN_DETAIL_DIMENSION_CM: Final = 3.0

Color = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class ObjectBox:
    """Where an object stands in its item-local frame: the centre and the half
    extents of its footprint's local bounding box (cm). ``round``: the footprint is
    a circle of radius ``half_w`` (= ``half_d``)."""

    cx: float
    cy: float
    half_w: float
    half_d: float
    round: bool = False

    @property
    def width(self) -> float:
        return 2.0 * self.half_w

    @property
    def depth(self) -> float:
        return 2.0 * self.half_d

    @property
    def radius(self) -> float:
        """The circle's radius; for a box, the half of its shorter side."""
        return min(self.half_w, self.half_d)

    def sprite(self, u: float, v: float, view_w: float, view_h: float) -> tuple[float, float]:
        """Where a point of the 2D sprite (``u`` right, ``v`` DOWN, in a viewBox of
        ``view_w`` × ``view_h``) lies in the object's frame — the sprite is stretched
        into the box, its top edge on the box's +y side."""
        return ((u / view_w - 0.5) * self.width, (0.5 - v / view_h) * self.depth)


def object_box(record: Record) -> ObjectBox | None:
    """The object's box (module docstring), or None for a footprint that is not one:
    no ground, no usable radius, or a polygon that does not fill its bounding box.
    ``record`` is one plain ring (``BuiltBuilder`` sees to that first)."""
    if record.height_cm is not None and record.height_cm < MIN_DETAIL_DIMENSION_CM:
        return None  # sub-3 cm parts have no room for the nominal rims and joints
    ring = np.asarray(footprint_of(record), dtype=np.float64).reshape(-1, 2)
    if len(ring) < 3:
        return None
    if record.shape == SHAPE_CIRCLE:
        radius = record.params.get(PARAM_RADIUS_CM)
        if isinstance(radius, bool) or not isinstance(radius, int | float) \
                or not radius >= MIN_DETAIL_DIMENSION_CM / 2.0:
            return None
        return ObjectBox(0.0, 0.0, float(radius), float(radius), round=True)
    low, high = ring.min(axis=0), ring.max(axis=0)
    size = high - low
    if not (size >= MIN_DETAIL_DIMENSION_CM).all():
        return None
    if abs(signed_area(ring)) < BOX_AREA_SHARE * float(size[0] * size[1]):
        return None
    centre = (low + high) / 2.0
    return ObjectBox(float(centre[0]), float(centre[1]), float(size[0]) / 2.0, float(size[1]) / 2.0)


def seed_of(record: Record, salt: str) -> int:
    """A stable random seed for ``record``'s jitter: its ``params["seed"]`` (the item
    id — a geometry param, so a builder may read it), salted per use."""
    return item_seed(str(record.params.get(PARAM_SEED, "")), salt)


def placed(meshes: Sequence[Mesh], box: ObjectBox) -> Mesh:
    """``meshes`` built about the object's own centre, merged and moved onto the box."""
    merged = Mesh.merge(list(meshes))
    if not merged.vertex_count or (box.cx == 0.0 and box.cy == 0.0):
        return merged
    return merged.translated(box.cx, box.cy, 0.0)


# ── boxes and boards ─────────────────────────────────────────────────────────


def slab(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, color: Color,
         bevel: float = 0.0) -> Mesh:
    """An upright box from (x0, y0, z0) to (x1, y1, z1); its vertical edges and top
    chamfered by ``bevel`` (limited by ``bevelled_boxes``). Its top is exactly z1."""
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        return Mesh.empty()
    centre = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    size = (x1 - x0, y1 - y0)
    if bevel <= 0.0:
        return boxes([centre], size, z0, z1, 0.0, color)
    return bevelled_boxes([centre], size, z0, z1, bevel, 0.0, color)


def slabs(rects: ArrayLike, z0: ArrayLike, z1: ArrayLike, color: Color, bevel: float = 0.0,
          angles_deg: ArrayLike = 0.0) -> Mesh:
    """Many upright boxes at once: ``rects`` (n, 4) as (cx, cy, size_x, size_y)."""
    rect = np.asarray(rects, dtype=np.float64).reshape(-1, 4)
    if not len(rect):
        return Mesh.empty()
    if bevel <= 0.0:
        return boxes(rect[:, :2], rect[:, 2:], z0, z1, angles_deg, color)
    return bevelled_boxes(rect[:, :2], rect[:, 2:], z0, z1, bevel, angles_deg, color)


def board(start: ArrayLike, end: ArrayLike, width: float, z0: float, z1: float, color: Color,
          bevel: float = 0.5) -> Mesh:
    """A horizontal plank from plan point ``start`` to ``end`` (``primitives.plank``)."""
    return plank(start, end, width, z0, z1, bevel, color)


def beam(p0: ArrayLike, p1: ArrayLike, width: float, thickness: float, color: Color,
         across: ArrayLike = (0.0, 0.0, 1.0)) -> Mesh:
    """A box from 3D point ``p0`` to ``p1``: ``width`` along ``across`` (made square to
    the beam's axis), ``thickness`` along the third axis. A leg, a slanted slat, an
    A-frame's rafter. Closed: two end caps and four sides, 12 triangles.

    An end that stands on the ground (z >= 0) never reaches under it: a slanted
    beam's end cap tips one corner below its axis, and a splayed leg dipped 0.4-1.4 cm
    into the ground (3D review of #388) — that end is raised by its dip."""
    a = np.asarray(p0, dtype=np.float64).copy()
    b = np.asarray(p1, dtype=np.float64).copy()
    for _ in range(3):
        corners = _beam_corners(a, b, width, thickness, across)
        if corners is None:
            return Mesh.empty()
        dips = [-float((end + corners)[:, 2].min()) if end[2] >= -1e-9 else 0.0 for end in (a, b)]
        if max(dips) <= 1e-6:
            break
        a[2] += max(dips[0], 0.0)
        b[2] += max(dips[1], 0.0)
    return _beam_mesh(a, b, width, thickness, color, across)


def _beam_corners(a: F64, b: F64, width: float, thickness: float, across: ArrayLike) -> F64 | None:
    """The four corners of ``beam``'s section about its axis, or None for no beam."""
    axis = b - a
    length = float(np.linalg.norm(axis))
    if length < 1e-6 or width <= 0.0 or thickness <= 0.0:
        return None
    axis = axis / length
    wide = np.asarray(across, dtype=np.float64)
    wide = wide - axis * float(wide @ axis)
    if float(np.linalg.norm(wide)) < 1e-6:
        helper = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        wide = helper - axis * float(helper @ axis)
    wide /= float(np.linalg.norm(wide))
    thick = np.cross(axis, wide)
    hw, ht = width / 2.0, thickness / 2.0
    return np.array([-wide * hw - thick * ht, wide * hw - thick * ht,
                     wide * hw + thick * ht, -wide * hw + thick * ht])


def _beam_mesh(a: F64, b: F64, width: float, thickness: float, color: Color,
               across: ArrayLike) -> Mesh:
    corners = _beam_corners(a, b, width, thickness, across)
    if corners is None:
        return Mesh.empty()
    axis = (b - a) / float(np.linalg.norm(b - a))
    low, high = a + corners, b + corners
    sides = np.stack([low, np.roll(low, -1, axis=0), np.roll(high, -1, axis=0), high], axis=1)
    centre = (a + b) / 2.0
    side_out = (sides.mean(axis=1) - centre)
    side_out -= np.outer(side_out @ axis, axis)
    ends = np.stack([low[::-1], high])
    triangles = np.concatenate([quad_triangles(sides), quad_triangles(ends)])
    outward = np.concatenate([np.repeat(side_out, 2, axis=0),
                              np.repeat(np.stack([-axis, axis]), 2, axis=0)])
    return flat_mesh(triangles, color, outward=outward)


def beam_under(top: ArrayLike, bottom: ArrayLike, width: float, thickness: float, color: Color,
               ceiling: float, across: ArrayLike = (0.0, 0.0, 1.0)) -> Mesh:
    """``beam`` from ``top`` down to ``bottom`` whose highest corner is at most
    ``ceiling``: a slanted beam's end corners stand above its axis, so the top end
    is lowered by what they overshoot (a leg under a beam, a rafter under a ridge)."""
    upper = np.asarray(top, dtype=np.float64).copy()
    mesh = beam(upper, bottom, width, thickness, color, across)
    for _ in range(4):
        if not mesh.vertex_count:
            return mesh
        excess = float(mesh.positions[:, 2].max()) - ceiling
        if excess <= 1e-6:
            return mesh
        upper[2] -= excess
        mesh = beam(upper, bottom, width, thickness, color, across)
    return mesh


# ── round parts ──────────────────────────────────────────────────────────────


def turned(profile: ArrayLike, color: ArrayLike, cx: float = 0.0, cy: float = 0.0,
           segments: int = ROUND_SEGMENTS) -> Mesh:
    """A surface of revolution about the vertical axis through (cx, cy):
    ``primitives.lathe`` (its profile convention: the outside on the RIGHT of travel —
    up the outer wall, over the rim, down the inner wall; start on the axis for a
    closed bottom)."""
    mesh = lathe(profile, color, segments)
    return mesh.translated(cx, cy, 0.0) if (cx or cy) and mesh.vertex_count else mesh


def cylinder(cx: float, cy: float, radius: float, z0: float, z1: float, color: Color, *,
             top_radius: float | None = None, segments: int = ROUND_SEGMENTS,
             bottom: bool = False) -> Mesh:
    """A solid upright cylinder (a frustum with ``top_radius``) with a lid — and a
    floor with ``bottom``. Its top is exactly ``z1``."""
    upper = radius if top_radius is None else top_radius
    if z1 <= z0 or radius <= 0.0 or upper < 0.0:
        return Mesh.empty()
    profile = ([(0.0, z0)] if bottom else []) + [(radius, z0), (upper, z1), (0.0, z1)]
    return turned(profile, color, cx, cy, segments)


def ball(cx: float, cy: float, cz: float, radius: float, color: Color, *, squash: float = 1.0,
         rings: int = 8, segments: int = 16) -> Mesh:
    """A smooth sphere of ``radius`` about (cx, cy, cz), scaled by ``squash`` in z; its
    normals are the inverse transpose of that squash (the spike once lit a squashed
    kettle as a round ball). Its top is exactly ``cz + radius * squash``."""
    theta = np.linspace(0.0, math.pi, rings + 1)
    phi = np.arange(segments) * (2.0 * math.pi / segments)
    st, ct = np.sin(theta)[:, None], np.cos(theta)[:, None]
    unit = np.stack([st * np.cos(phi)[None, :], st * np.sin(phi)[None, :],
                     np.broadcast_to(ct, (rings + 1, segments))], axis=-1).reshape(-1, 3)
    positions = unit * np.array([radius, radius, radius * squash]) + np.array([cx, cy, cz])
    normals = unit / np.array([1.0, 1.0, squash])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    j = np.arange(segments)
    following = (j + 1) % segments
    rows = np.arange(rings)[:, None] * segments
    a, b = rows + j[None, :], rows + following[None, :]
    c, d = a + segments, b + segments
    # counter-clockwise seen from outside: a (upper), c (lower), d, b
    index = np.concatenate([np.stack([a, c, d], axis=-1), np.stack([a, d, b], axis=-1)],
                           axis=1).reshape(-1, 3)
    colors = np.broadcast_to(np.asarray(color, dtype=np.float64), (len(positions), 4))
    return Mesh.from_arrays(positions, normals, colors, np.zeros((len(positions), 2)), index)


def rod(starts: ArrayLike, ends: ArrayLike, radius: float, color: Color, sides: int = 6) -> Mesh:
    """Thin round bars (legs, ropes, rails) from ``starts[i]`` to ``ends[i]``. An end
    that stands on the ground (z >= 0) never reaches under it: a slanted bar's end
    disc dips ``radius · |horizontal part of its axis|`` below its centre (a splayed
    grill leg 1.2 cm, 3D review of #388), and that end is raised by it."""
    start = np.asarray(starts, dtype=np.float64).reshape(-1, 3).copy()
    if not len(start):
        return Mesh.empty()
    end = np.asarray(ends, dtype=np.float64).reshape(-1, 3).copy()
    axis = end - start
    length = np.linalg.norm(axis, axis=1)
    level = np.where(length > 1e-9, np.linalg.norm(axis[:, :2], axis=1) / np.maximum(length, 1e-9), 0.0)
    dip = radius * level
    for point in (start, end):
        grounded = point[:, 2] >= -1e-9
        point[grounded, 2] = np.maximum(point[grounded, 2], dip[grounded])
    return tubes(start, end, radius, radius, color, sides)


# ── turning a finished part ──────────────────────────────────────────────────


def turned_mesh(mesh: Mesh, axis: str, degrees: float, about: ArrayLike = (0.0, 0.0, 0.0)) -> Mesh:
    """``mesh`` turned by ``degrees`` (right-handed) about the ``axis`` (``"x"``, ``"y"``
    or ``"z"``) through the point ``about`` — positions and normals."""
    if not mesh.vertex_count:
        return mesh
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    matrix = {
        "x": np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]),
        "y": np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]),
        "z": np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]),
    }[axis]
    pivot = np.asarray(about, dtype=np.float64)
    positions = (mesh.positions.astype(np.float64) - pivot) @ matrix.T + pivot
    normals = mesh.normals.astype(np.float64) @ matrix.T
    return Mesh.from_arrays(positions, normals, mesh.colors, mesh.uvs, mesh.indices)


def unit_circle(count: int, start_deg: float = 0.0) -> F64:
    """``count`` unit directions round the circle, counter-clockwise from ``start_deg``."""
    angle = np.radians(start_deg) + np.arange(count) * (2.0 * math.pi / count)
    circle: F64 = np.stack([np.cos(angle), np.sin(angle)], axis=1)
    return circle
