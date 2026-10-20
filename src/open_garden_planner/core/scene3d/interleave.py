"""A ``Mesh`` as the bytes a renderer uploads — the last Qt-free step (L1.2, ADR-048).

The engine adapter (``ui/view3d/quick3d/``) hands Qt Quick 3D one interleaved
vertex buffer and one index buffer per mesh part. Building them is plain numpy,
so it lives here, where the default test run covers the layout byte for byte
(``tests/unit/test_scene3d_interleave.py``); the engine module only passes the
bytes on.

Vertex layout — the L0 spike's, measured on every backend it ran on
(``ogp-3d-renderer`` §3). Stride 48 bytes, little-endian::

    offset  0   position  float32 x 3   ENGINE frame (x = East, y = up, z = −North), cm
    offset 12   normal    float32 x 3   ENGINE frame, unit length
    offset 24   colour    float32 x 4   LINEAR RGBA, exactly the mesh's values
    offset 40   uv        float32 x 2   builder-defined (the spike: wind weight, phase)

Indices: little-endian uint32, three per triangle, in the mesh's order.

This is THE place a mesh crosses from the scene axes into the engine frame
(``frame.scene_to_engine_points``): a proper rotation, so the triangles stay
wound counter-clockwise seen from outside. The item's pose is not applied here —
the engine poses the Model (``frame.engine_pose``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from .frame import scene_to_engine_points, scene_to_engine_vectors
from .mesh import Mesh

#: Bytes per vertex.
VERTEX_STRIDE: Final = 48
#: Byte offset of each attribute inside a vertex.
POSITION_OFFSET: Final = 0
NORMAL_OFFSET: Final = 12
COLOR_OFFSET: Final = 24
UV_OFFSET: Final = 40

_FLOATS_PER_VERTEX: Final = VERTEX_STRIDE // 4
_ORIGIN: Final = (0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class EngineBuffers:
    """One mesh, ready to upload: interleaved vertices, indices, counts and bounds.

    ``bounds_min`` / ``bounds_max``: the axis-aligned box of the positions in the
    ENGINE frame (what the engine culls and picks with); both ``(0, 0, 0)`` for an
    empty mesh.
    """

    vertex_data: bytes
    index_data: bytes
    vertex_count: int
    index_count: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to draw (no vertices or no triangles)."""
        return self.vertex_count == 0 or self.index_count == 0


def engine_buffers(mesh: Mesh) -> EngineBuffers:
    """Interleave ``mesh`` (item-local frame, scene axes) for the engine.

    Positions and normals are mapped to the engine frame — once, here. Colours
    are copied as they are: they are linear already, and a transfer function
    applied at this point would be a second gamma.
    """
    count = mesh.vertex_count
    positions = scene_to_engine_points(mesh.positions)
    vertices = np.empty((count, _FLOATS_PER_VERTEX), dtype="<f4")
    vertices[:, 0:3] = positions
    vertices[:, 3:6] = scene_to_engine_vectors(mesh.normals)
    vertices[:, 6:10] = mesh.colors
    vertices[:, 10:12] = mesh.uvs
    indices = np.ascontiguousarray(mesh.indices, dtype="<u4").reshape(-1)
    if count:
        low, high = positions.min(axis=0), positions.max(axis=0)
        bounds_min = (float(low[0]), float(low[1]), float(low[2]))
        bounds_max = (float(high[0]), float(high[1]), float(high[2]))
    else:
        bounds_min = bounds_max = _ORIGIN
    return EngineBuffers(
        vertex_data=vertices.tobytes(),
        index_data=indices.tobytes(),
        vertex_count=count,
        index_count=int(indices.size),
        bounds_min=bounds_min,
        bounds_max=bounds_max,
    )
