"""The frames of the 3D pipeline — every conversion, each defined once (L1.1).

Three frames (ADR-054):

- ITEM-LOCAL: centimetres relative to an item's anchor; +z up from the item's
  own ground plane. Records and meshes live here.
- SCENE: x = East, y = North, z = up, centimetres (ADR-002 + height). The plan.
- ENGINE (Qt Quick 3D, Y-up, right-handed): x = East, y = up, z = −North.

Local → scene is the record's ``Transform``::

    scene_xy = (east_cm, north_cm) + R(rotation_deg) · local_xy
    scene_z  = base_cm + local_z

with ``R`` counter-clockwise seen from above with north up (+East → +North).
Scene → engine is ``SCENE_TO_ENGINE``: a proper rotation (determinant +1), so
triangle winding survives and nothing is mirrored. It is applied exactly ONCE,
by the engine adapter (``ui/view3d/quick3d/``, L1.2) — a second application
anywhere mirrors the garden (§8.20's rule, in 3D). ``engine_pose`` states how a
``Transform`` reads in the engine frame, so the adapter never re-derives it.

``LocalFrame`` goes the other way for the snapshot: from an item's affine scene
transform (Qt's ``sceneTransform()``, as six plain floats) to the transform and
the local coordinates of a record.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .record import LENGTH_DECIMALS, Point, Ring, Transform, quantize_cm, quantize_deg


def _frozen(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    matrix.setflags(write=False)
    return matrix


#: Scene (E, N, up) → engine (x = E, y = up, z = −N) as a matrix: ``engine = M · scene``.
SCENE_TO_ENGINE: Final[NDArray[np.float64]] = _frozen(
    np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
)
#: The inverse (= the transpose: the map is orthonormal).
ENGINE_TO_SCENE: Final[NDArray[np.float64]] = _frozen(SCENE_TO_ENGINE.T.copy())

#: An affine linear part counts as a pure rotation within this tolerance. Qt
#: builds an item's matrix from one cos/sin pair, so a rigid transform is exact
#: to a few ulp; anything a user could call a scale is many orders above it.
RIGID_TOLERANCE: Final = 1e-9


def _xyz(values: ArrayLike) -> NDArray[Any]:
    array = np.asarray(values)
    if array.shape[-1:] != (3,):
        raise ValueError(f"expected xyz on the last axis, got shape {array.shape}")
    return array


def scene_to_engine_points(points: ArrayLike) -> NDArray[Any]:
    """Scene positions (…, 3) → engine positions; dtype and shape are kept.

    Pure column selection — exact, no rounding. The same linear map as
    ``scene_to_engine_vectors`` (no translation: both frames share their
    origin); two names so a call site says which it means.
    """
    scene = _xyz(points)
    engine = np.empty_like(scene)
    engine[..., 0] = scene[..., 0]
    engine[..., 1] = scene[..., 2]
    engine[..., 2] = -scene[..., 1]
    return engine


def scene_to_engine_vectors(vectors: ArrayLike) -> NDArray[Any]:
    """Scene directions / normals (…, 3) → engine frame.

    The map is orthonormal, so normals transform like any vector (no
    inverse-transpose) and stay unit length.
    """
    return scene_to_engine_points(vectors)


def engine_to_scene_points(points: ArrayLike) -> NDArray[Any]:
    """Engine positions (…, 3) → scene positions (picking results, camera poses)."""
    engine = _xyz(points)
    scene = np.empty_like(engine)
    scene[..., 0] = engine[..., 0]
    scene[..., 1] = -engine[..., 2]
    scene[..., 2] = engine[..., 1]
    return scene


def engine_to_scene_vectors(vectors: ArrayLike) -> NDArray[Any]:
    """Engine directions (…, 3) → scene frame."""
    return engine_to_scene_points(vectors)


def cos_sin(rotation_deg: float) -> tuple[float, float]:
    """``(cos θ, sin θ)``, exact at quarter turns (no ``cos(90°) = 6e-17`` dust)."""
    turn = rotation_deg % 360.0
    if turn == 0.0:
        return (1.0, 0.0)
    if turn == 90.0:
        return (0.0, 1.0)
    if turn == 180.0:
        return (-1.0, 0.0)
    if turn == 270.0:
        return (0.0, -1.0)
    angle = math.radians(turn)
    return (math.cos(angle), math.sin(angle))


def pose_point(transform: Transform, x: float, y: float) -> Point:
    """One item-local ground point → scene: ``T + R(θ)·(x, y)``."""
    c, s = cos_sin(transform.rotation_deg)
    return (transform.east_cm + c * x - s * y, transform.north_cm + s * x + c * y)


def pose_ring(transform: Transform, ring: Iterable[Point]) -> list[Point]:
    """An item-local polygon → scene polygon (the 2D footprint of a posed record)."""
    c, s = cos_sin(transform.rotation_deg)
    east, north = transform.east_cm, transform.north_cm
    return [(east + c * x - s * y, north + s * x + c * y) for x, y in ring]


def pose_points(transform: Transform, points: ArrayLike) -> NDArray[np.float64]:
    """Item-local positions (…, 3) → scene positions, float64 (mesh vertices)."""
    local = _xyz(points).astype(np.float64)
    c, s = cos_sin(transform.rotation_deg)
    scene = np.empty_like(local)
    scene[..., 0] = transform.east_cm + c * local[..., 0] - s * local[..., 1]
    scene[..., 1] = transform.north_cm + s * local[..., 0] + c * local[..., 1]
    scene[..., 2] = transform.base_cm + local[..., 2]
    return scene


@dataclass(frozen=True, slots=True)
class EnginePose:
    """A ``Transform`` in the engine frame: what an engine Model is given.

    ``position``: (x, y, z) = (east_cm, base_cm, −north_cm). ``yaw_deg``: the
    right-handed turn about the engine's +Y (up) axis — numerically the record's
    ``rotation_deg``: a counter-clockwise turn seen from above is the same turn
    in both frames, because scene → engine is a rotation, not a reflection.
    """

    position: tuple[float, float, float]
    yaw_deg: float


def engine_pose(transform: Transform) -> EnginePose:
    """How the engine adapter poses the Model of a record (``EnginePose``)."""
    return EnginePose(
        position=(transform.east_cm, transform.base_cm, -transform.north_cm + 0.0),
        yaw_deg=transform.rotation_deg,
    )


def engine_model_matrix(transform: Transform) -> NDArray[np.float64]:
    """The 4×4 model matrix of a record in the engine frame.

    ``engine_position = M · [scene_to_engine(local), 1]`` — equal to mapping the
    posed scene position (pinned by ``test_scene3d_frame.py``).
    """
    pose = engine_pose(transform)
    c, s = cos_sin(pose.yaw_deg)
    matrix = np.identity(4)
    matrix[0, 0], matrix[0, 2] = c, s
    matrix[2, 0], matrix[2, 2] = -s, c
    matrix[:3, 3] = pose.position
    return matrix


@dataclass(frozen=True, slots=True)
class LocalFrame:
    """An item's affine scene transform, split into a rigid pose + local geometry.

    Built by ``local_frame`` from Qt's ``sceneTransform()`` (``x' = m11·x +
    m21·y + dx``, ``y' = m12·x + m22·y + dy``) and the anchor — the item-local
    point the record's frame is centred on.

    - RIGID (a pure rotation, the normal case): ``rotation_deg = atan2(m12,
      m11)``; a local coordinate is the item coordinate minus the anchor.
    - NOT rigid (scale, mirror, shear — an item in a scaled group): a rigid
      ``Transform`` cannot carry it, so the WHOLE linear part is baked into the
      local coordinates and the rotation is 0. ``scene = T + local`` still holds;
      the price is that rotating such an item rebuilds its geometry.
    - ``rotatable=False`` (circles): the rotation is 0 and local geometry is not
      derived from the matrix at all — a circle's footprint does not turn.

    Every value handed out is on the record grid (``quantize_cm``).
    """

    east_cm: float
    north_cm: float
    rotation_deg: float
    rigid: bool
    anchor_x: float
    anchor_y: float
    m11: float
    m12: float
    m21: float
    m22: float
    scene_x: float  # the anchor's scene position, NOT quantised (for local_from_scene)
    scene_y: float

    def transform(self, base_cm: float = 0.0) -> Transform:
        """The record transform of this frame."""
        return Transform(self.east_cm, self.north_cm, self.rotation_deg, base_cm)

    def local_from_item(self, x: float, y: float) -> Point:
        """An item-coordinate point → record-local coordinates."""
        u, v = x - self.anchor_x, y - self.anchor_y
        if self.rigid:
            return (quantize_cm(u), quantize_cm(v))
        return (quantize_cm(self.m11 * u + self.m21 * v), quantize_cm(self.m12 * u + self.m22 * v))

    def local_ring(self, points: Sequence[Point]) -> Ring:
        """Item-coordinate vertices → a record-local ring."""
        ax, ay = self.anchor_x, self.anchor_y
        if self.rigid:
            digits = LENGTH_DECIMALS  # quantize_cm, inlined: this is the snapshot's hot loop
            return tuple([(round(x - ax, digits) + 0.0, round(y - ay, digits) + 0.0)
                          for x, y in points])
        return tuple([self.local_from_item(x, y) for x, y in points])

    def local_from_scene(self, x: float, y: float) -> Point:
        """A SCENE point → record-local coordinates (another item's point, e.g. a
        HOUSE's ridge end read from its ridge item)."""
        u, v = x - self.scene_x, y - self.scene_y
        if not self.rigid or self.rotation_deg == 0.0:
            return (quantize_cm(u), quantize_cm(v))
        # R(θ)ᵀ · (u, v) with R's first column (m11, m12) = (cos θ, sin θ)
        return (quantize_cm(self.m11 * u + self.m12 * v), quantize_cm(-self.m12 * u + self.m11 * v))


def local_frame(
    m11: float, m12: float, m21: float, m22: float, dx: float, dy: float,
    anchor_x: float, anchor_y: float, *, rotatable: bool = True,
) -> LocalFrame:
    """Split an affine scene transform about ``anchor`` (see ``LocalFrame``)."""
    scene_x = m11 * anchor_x + m21 * anchor_y + dx
    scene_y = m12 * anchor_x + m22 * anchor_y + dy
    rigid = (
        abs(m11 - m22) <= RIGID_TOLERANCE
        and abs(m12 + m21) <= RIGID_TOLERANCE
        and abs(m11 * m11 + m12 * m12 - 1.0) <= RIGID_TOLERANCE
    )
    turn = math.degrees(math.atan2(m12, m11))
    rotation = quantize_deg(turn) if rigid and rotatable else 0.0
    return LocalFrame(
        east_cm=quantize_cm(scene_x), north_cm=quantize_cm(scene_y), rotation_deg=rotation,
        rigid=rigid, anchor_x=anchor_x, anchor_y=anchor_y,
        m11=m11, m12=m12, m21=m21, m22=m22, scene_x=scene_x, scene_y=scene_y,
    )
