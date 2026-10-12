"""Camera placements as plain data, and the top-down projection (L1.2). Engine-free.

A *shot* says where the camera is for one frame, in SCENE coordinates
(x = East, y = North, z = up, centimetres). ``Quick3DHost.set_shot`` maps it to
the engine frame; nothing else does.

``TopDownShot`` is the truth view: an orthographic camera looking straight down
with north at the top of the image, so a scene point lands on a pixel that
plain arithmetic predicts — ``top_down_pixel``, our own projection, independent
of the engine's. The render tier compares the two; a mirrored or swapped
mapping cannot pass.

The orbit camera and its input handling are L1.3 (``core/scene3d/camera.py``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _finite(values: tuple[float, ...]) -> bool:
    return all(math.isfinite(v) for v in values)


@dataclass(frozen=True, slots=True)
class PerspectiveShot:
    """A perspective camera at ``eye`` looking at ``target`` (scene E, N, up)."""

    eye: tuple[float, float, float]
    target: tuple[float, float, float]
    fov_deg: float = 40.0  # vertical field of view; the spike's default

    def __post_init__(self) -> None:
        if len(self.eye) != 3 or len(self.target) != 3 or not _finite((*self.eye, *self.target)):
            raise ValueError(f"PerspectiveShot needs finite (E, N, up) points, got {self!r}")
        if tuple(self.eye) == tuple(self.target):
            raise ValueError("PerspectiveShot: the eye and the target are the same point")
        if not math.isfinite(self.fov_deg) or not 0.0 < self.fov_deg < 180.0:
            raise ValueError(f"PerspectiveShot.fov_deg must be inside (0, 180), got {self.fov_deg!r}")


@dataclass(frozen=True, slots=True)
class TopDownShot:
    """An orthographic camera straight above ``center`` (scene E, N), north up.

    ``px_per_cm``: LOGICAL pixels per centimetre. A grabbed image is in device
    pixels — multiply with its ``devicePixelRatio`` (``top_down_pixel`` does).
    """

    center: tuple[float, float]
    px_per_cm: float

    def __post_init__(self) -> None:
        if len(self.center) != 2 or not _finite(tuple(self.center)):
            raise ValueError(f"TopDownShot.center must be a finite (E, N) point, got {self.center!r}")
        if not math.isfinite(self.px_per_cm) or self.px_per_cm <= 0.0:
            raise ValueError(f"TopDownShot.px_per_cm must be positive, got {self.px_per_cm!r}")


Shot = PerspectiveShot | TopDownShot


def top_down_pixel(east_cm: float, north_cm: float, shot: TopDownShot,
                   image_size: tuple[int, int],
                   device_pixel_ratio: float = 1.0) -> tuple[float, float]:
    """Where a top-down shot puts scene point (east, north) in an image of
    ``image_size`` (width, height, DEVICE pixels): east to the right, north UP.

    Continuous coordinates: pixel ``(i, j)`` covers ``[i, i + 1) x [j, j + 1)``.
    """
    width, height = image_size
    scale = shot.px_per_cm * device_pixel_ratio
    return (width / 2.0 + (east_cm - shot.center[0]) * scale,
            height / 2.0 - (north_cm - shot.center[1]) * scale)

