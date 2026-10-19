"""A CPU pick oracle: which item does a view ray meet first? (Phase 17 L1.8, ADR-065.)

Qt-free: standard library and numpy. The 3D view picks with the ENGINE
(``Quick3DHost.pick``); this module is the independent witness the tests hold it
to — the question "what is under this pixel?" answered from the records' own
meshes and a camera model of our own, with no engine in the loop. It is the
perspective sibling of the top-down oracle the engine story's render tier uses
(``tests/integration/quick3d_render_driver.py::cpu_topmost_hit``), and the two
are pinned against each other.

How it works:

- ``pick_scene(records, parts_of)`` builds every record's mesh parts with the
  caller's builder (``registry.builder_for(record.kind)`` — the meshes the engine
  is handed), poses them with the record's transform (``frame.pose_points``, the
  one local → scene rule) and keeps the triangles in the SCENE frame.
- ``perspective_ray`` / ``top_down_ray`` turn a view position (logical pixels,
  origin top left) into a ray, for the two cameras the host has: a perspective
  camera at ``eye`` looking at ``target`` with a VERTICAL field of view and no
  roll, and the orthographic truth view straight down with north up.
- ``cast`` returns the nearest triangle the ray meets — from either side: a
  picker has no back faces — or None for empty space (the ground and the sky are
  not items).

What it does not know: the wind (a foliage shader moves vertices only while the
scene's clock runs; at rest the drawn mesh IS the mesh — ``ogp-3d-renderer`` §2),
the near and far planes, and anything the engine holds that is not a record's
part (the ground, the selection ring — neither is pickable).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypeAlias

import numpy as np
from numpy.typing import NDArray

from .frame import pose_points
from .mesh import MeshPart
from .record import Record

Vector: TypeAlias = tuple[float, float, float]
PartsOf: TypeAlias = Callable[[Record], Sequence[MeshPart]]
_F64: TypeAlias = NDArray[np.float64]

#: A ray parallel to a triangle to this determinant misses it (the triangle's edges
#: are in cm, the direction is a unit vector: this is a sliver seen edge-on).
_PARALLEL: Final = 1e-12
#: Barycentric slack: a ray through a shared edge hits one of the two triangles.
_EDGE_SLACK: Final = 1e-9
#: A hit closer to the origin than this (cm) is the origin's own surface.
_MIN_DISTANCE_CM: Final = 1e-6
#: Where the orthographic truth camera hangs (``Garden.qml``: ``topCam``, y = 4000).
TOP_DOWN_CAMERA_HEIGHT_CM: Final = 4000.0


@dataclass(frozen=True, slots=True)
class Ray:
    """A half line in the scene frame (E, N, up; cm): ``origin + t * direction`` for
    ``t >= 0``. ``direction`` is a unit vector."""

    origin: Vector
    direction: Vector


@dataclass(frozen=True, slots=True)
class RayHit:
    """What a ray met first: the item, the index of its mesh part, the point (scene
    frame) and how far along the ray it lies (cm)."""

    item_id: str
    part_index: int
    point: Vector
    distance_cm: float


@dataclass(frozen=True, slots=True, eq=False)
class PickScene:
    """Every pickable triangle of a snapshot, posed: plain read-only arrays.

    ``corner`` is one corner of each triangle, ``edge1`` / ``edge2`` the two edges
    from it (``(n, 3)`` each, scene frame); ``item`` / ``part`` say whose triangle
    row it is (indices into ``item_ids``, and the part's index in its item).
    """

    item_ids: tuple[str, ...]
    corner: _F64
    edge1: _F64
    edge2: _F64
    item: NDArray[np.int64]
    part: NDArray[np.int64]

    @property
    def triangle_count(self) -> int:
        return int(len(self.corner))


def pick_scene(records: Mapping[str, Record], parts_of: PartsOf) -> PickScene:
    """The oracle's scene for ``records``: each record built by ``parts_of`` and
    posed by its own transform. A record without triangles (a flat item, a builder
    that returned nothing) is not in it — it cannot be picked."""
    ids: list[str] = []
    corners: list[_F64] = []
    firsts: list[_F64] = []
    seconds: list[_F64] = []
    items: list[NDArray[np.int64]] = []
    parts: list[NDArray[np.int64]] = []
    for item_id, record in records.items():
        index = len(ids)
        held = False
        for part_index, part in enumerate(parts_of(record)):
            mesh = part.mesh
            if not mesh.triangle_count:
                continue
            posed = pose_points(record.transform, mesh.positions)
            triangles = posed[mesh.indices.astype(np.int64)]
            corners.append(triangles[:, 0])
            firsts.append(triangles[:, 1] - triangles[:, 0])
            seconds.append(triangles[:, 2] - triangles[:, 0])
            items.append(np.full(len(triangles), index, np.int64))
            parts.append(np.full(len(triangles), part_index, np.int64))
            held = True
        if held:
            ids.append(item_id)
    if not corners:
        empty = np.zeros((0, 3))
        none = np.zeros(0, np.int64)
        return PickScene((), empty, empty, empty, none, none)
    arrays = (np.concatenate(corners), np.concatenate(firsts), np.concatenate(seconds),
              np.concatenate(items), np.concatenate(parts))
    for array in arrays:
        array.setflags(write=False)
    return PickScene(tuple(ids), *arrays)


def _unit(vector: Sequence[float]) -> Vector:
    length = math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)
    if not length > 0.0 or not math.isfinite(length):
        raise ValueError(f"not a direction: {tuple(vector)!r}")
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _cross(a: Sequence[float], b: Sequence[float]) -> Vector:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def camera_axes(eye: Sequence[float], target: Sequence[float]) -> tuple[Vector, Vector, Vector]:
    """``(forward, right, up)`` of a camera at ``eye`` looking at ``target`` with the
    scene's up as its up and no roll — unit vectors, scene frame. A camera looking
    straight up or down has no "right" and is refused."""
    forward = _unit((target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]))
    right = _unit(_cross(forward, (0.0, 0.0, 1.0)))
    return forward, right, _cross(right, forward)


def perspective_ray(eye: Sequence[float], target: Sequence[float], fov_deg: float,
                    view_size: tuple[float, float], x: float, y: float) -> Ray:
    """The ray through view position ``(x, y)`` (logical pixels, origin top left, y
    down) of a view ``view_size`` wide and high, for a perspective camera at
    ``eye`` looking at ``target`` with a VERTICAL field of view of ``fov_deg``."""
    width, height = view_size
    if not (width > 0.0 and height > 0.0):
        raise ValueError(f"a view has a positive size, got {view_size!r}")
    if not 0.0 < fov_deg < 180.0:
        raise ValueError(f"fov_deg must be inside (0, 180), got {fov_deg!r}")
    forward, right, up = camera_axes(eye, target)
    half = math.tan(math.radians(fov_deg) / 2.0)
    across = (2.0 * x / width - 1.0) * half * (width / height)
    upward = (1.0 - 2.0 * y / height) * half
    direction = _unit(tuple(forward[axis] + across * right[axis] + upward * up[axis]
                            for axis in range(3)))
    return Ray((float(eye[0]), float(eye[1]), float(eye[2])), direction)


def top_down_ray(center: Sequence[float], px_per_cm: float, view_size: tuple[float, float],
                 x: float, y: float) -> Ray:
    """The ray through view position ``(x, y)`` of the orthographic truth view:
    straight down, north up the image, east to the right, ``px_per_cm`` logical
    pixels per centimetre, centred on scene ``center`` (E, N)."""
    width, height = view_size
    if not px_per_cm > 0.0:
        raise ValueError(f"px_per_cm must be positive, got {px_per_cm!r}")
    east = center[0] + (x - width / 2.0) / px_per_cm
    north = center[1] - (y - height / 2.0) / px_per_cm
    return Ray((east, north, TOP_DOWN_CAMERA_HEIGHT_CM), (0.0, 0.0, -1.0))


def project(eye: Sequence[float], target: Sequence[float], fov_deg: float,
            view_size: tuple[float, float], point: Sequence[float]) -> tuple[float, float] | None:
    """Where the perspective camera of ``perspective_ray`` puts scene ``point`` in the
    view (logical pixels) — the inverse of the ray — or None for a point that is not
    in front of the camera."""
    forward, right, up = camera_axes(eye, target)
    offset = (point[0] - eye[0], point[1] - eye[1], point[2] - eye[2])
    depth = sum(offset[axis] * forward[axis] for axis in range(3))
    if not depth > 1e-9:
        return None
    width, height = view_size
    half = math.tan(math.radians(fov_deg) / 2.0)
    across = sum(offset[axis] * right[axis] for axis in range(3)) / depth
    upward = sum(offset[axis] * up[axis] for axis in range(3)) / depth
    return ((across / (half * width / height) + 1.0) * width / 2.0,
            (1.0 - upward / half) * height / 2.0)


def cast(scene: PickScene, ray: Ray) -> RayHit | None:
    """The first triangle of ``scene`` along ``ray`` (Möller–Trumbore over every
    triangle at once) — met from either side — or None when the ray meets none."""
    hits = _cast(scene, ray, every_item=False)
    return hits[0] if hits else None


def cast_all(scene: PickScene, ray: Ray) -> tuple[RayHit, ...]:
    """EVERY item ``ray`` meets, nearest first — one hit per item: where the ray first
    enters it. What a click that falls through a locked item meets next."""
    return _cast(scene, ray, every_item=True)


def _cast(scene: PickScene, ray: Ray, *, every_item: bool) -> tuple[RayHit, ...]:
    if not scene.triangle_count:
        return ()
    origin = np.array(ray.origin, np.float64)
    direction = np.array(ray.direction, np.float64)
    p = np.cross(direction, scene.edge2)
    det = np.einsum("ij,ij->i", scene.edge1, p)
    usable = np.abs(det) > _PARALLEL
    inverse = 1.0 / np.where(usable, det, 1.0)
    to_origin = origin - scene.corner
    u = np.einsum("ij,ij->i", to_origin, p) * inverse
    q = np.cross(to_origin, scene.edge1)
    v = (q @ direction) * inverse
    distance = np.einsum("ij,ij->i", scene.edge2, q) * inverse
    met = (usable & (u >= -_EDGE_SLACK) & (v >= -_EDGE_SLACK) & (u + v <= 1.0 + _EDGE_SLACK)
           & (distance > _MIN_DISTANCE_CM))
    if not met.any():
        return ()
    rows = np.flatnonzero(met)
    rows = rows[np.argsort(distance[rows], kind="stable")]
    hits: list[RayHit] = []
    seen: set[int] = set()
    for row in rows.tolist():
        item = int(scene.item[row])
        if item in seen:
            continue
        seen.add(item)
        reach = float(distance[row])
        point = origin + reach * direction
        hits.append(RayHit(scene.item_ids[item], int(scene.part[row]),
                           (float(point[0]), float(point[1]), float(point[2])), reach))
        if not every_item:
            break
    return tuple(hits)
