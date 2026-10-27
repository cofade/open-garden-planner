"""The endless meadow around the plan (Phase 17 L4, #388). Qt-free.

The meadow is a square ``2 × MEADOW_HALF_CM`` wide (4 km; its edge lies in full fog, the
midpoints of its edges inside the workspace's 3 km far plane) centred on the plan, IN the plan's plane, with the plan's rectangle cut out —
less ``MEADOW_OVERLAP_CM`` on each side — and cut into cells of at most
``MEADOW_CELL_CM``. Nothing of it lies under the plan.

Two earlier forms lost the depth test to the plan's ground tiles. Both were ONE quad of
two triangles under the whole plan (3D review of #388), first 1 cm under it, then 5 cm.
A triangle 2 km across interpolates its depth with more than 5 cm of error at 55-90 m.
So from the workspace's default framing, a few wheel notches out, the meadow drew over
up to 52 % of the plan: the pond, the terraces and the paths were gone. The same quad
cut into 100 m cells lost no view. The 5 cm step also drew an ambient-occlusion line
along every plan edge (±14 luma), and the shadows that crossed the edge jumped there.

The strip under the plan's edge (``MEADOW_OVERLAP_CM``, 1 mm): the tiles' vertices along
the edge are not the meadow's, and an edge shared without its vertices can leave pixels
that neither side covers. In that strip the meadow and the plan are coplanar, and the
meadow wins; at 1 cm it took a visible centimetre of a surface painted to the edge.
Without a plan the square has no hole.

``meadow_frame`` builds the mesh in the scene frame (E, N, up), at the scene origin, with
the faces up. The host loads it into ONE geometry of the scene's one meadow Model
(``Quick3DHost``), as it loads the selection ring.
"""

from __future__ import annotations

from typing import Final

import numpy as np

from .mesh import Mesh

#: Half the meadow's side, cm: 2 km, so its edge lies in full fog (look.FOG_FAR_MAX_CM).
MEADOW_HALF_CM: Final = 200_000.0
#: The largest cell, cm. A 4 km quad of two triangles drew over the plan from the
#: default framing; cells of 100 m drew over it from no view (3D review of #388).
MEADOW_CELL_CM: Final = 10_000.0
#: How far the meadow reaches under the plan's edge, cm (module docstring). At 1 cm the
#: meadow won the strip's equal depth test and took the outer centimetre of a surface
#: painted up to the edge (4 px at 0.5 m); 1 mm shows none,
#: and no crack either.
MEADOW_OVERLAP_CM: Final = 0.1
#: A cell line this close to one of the plan's edges is dropped for the edge, cm.
_MERGE_CM: Final = 0.5


def meadow_frame(plan: tuple[float, float, float, float] | None) -> Mesh:
    """The meadow around ``plan`` = (east0, north0, east1, north1), scene cm, or the whole
    square around the scene origin for None (or for a plan narrower than twice the
    overlap). Faces up, white vertex colour."""
    hole: tuple[float, float, float, float] | None = None
    centre = (0.0, 0.0)
    if plan is not None:
        east0, north0, east1, north1 = (float(value) for value in plan)
        if not all(np.isfinite((east0, north0, east1, north1))):
            raise ValueError(f"a plan rectangle of finite numbers, got {plan!r}")
        centre = ((east0 + east1) / 2.0, (north0 + north1) / 2.0)
        inner = (east0 + MEADOW_OVERLAP_CM, north0 + MEADOW_OVERLAP_CM,
                 east1 - MEADOW_OVERLAP_CM, north1 - MEADOW_OVERLAP_CM)
        if inner[2] > inner[0] and inner[3] > inner[1]:
            hole = inner
    xs = _lines(centre[0], None if hole is None else (hole[0], hole[2]))
    ys = _lines(centre[1], None if hole is None else (hole[1], hole[3]))
    grid_x, grid_y = np.meshgrid(xs, ys)  # (len(ys), len(xs)), row = y
    positions = np.column_stack([grid_x.ravel(), grid_y.ravel(), np.zeros(grid_x.size)])
    columns = len(xs)
    cell_i, cell_j = np.meshgrid(np.arange(columns - 1), np.arange(len(ys) - 1))
    i, j = cell_i.ravel(), cell_j.ravel()
    if hole is not None:
        middle_x = (xs[i] + xs[i + 1]) / 2.0
        middle_y = (ys[j] + ys[j + 1]) / 2.0
        outside = ~((middle_x > hole[0]) & (middle_x < hole[2])
                    & (middle_y > hole[1]) & (middle_y < hole[3]))
        i, j = i[outside], j[outside]
    a = j * columns + i
    # counter-clockwise seen from above: (a, a+1, a+columns) and (a+1, a+columns+1, a+columns)
    triangles = np.concatenate([np.column_stack([a, a + 1, a + columns]),
                                np.column_stack([a + 1, a + columns + 1, a + columns])])
    count = len(positions)
    return Mesh.from_arrays(positions, np.tile([0.0, 0.0, 1.0], (count, 1)),
                            np.ones((count, 4)), np.zeros((count, 2)), triangles)


def _lines(middle: float, hole: tuple[float, float] | None) -> np.ndarray:
    """The grid's lines along one axis: every ``MEADOW_CELL_CM`` across the square, and
    the hole's two edges. A cell line within ``_MERGE_CM`` of an edge goes, never the
    edge: a cell line kept in its place would move the meadow's edge off the plan's and
    open a gap there."""
    steps = round(2.0 * MEADOW_HALF_CM / MEADOW_CELL_CM)
    at = middle - MEADOW_HALF_CM + MEADOW_CELL_CM * np.arange(steps + 1)
    if hole is not None:
        edges = np.asarray(hole, dtype=np.float64)
        near = np.abs(at[:, None] - edges[None, :]).min(axis=1) <= _MERGE_CM
        at = np.concatenate([at[~near], edges])
    return np.asarray(np.sort(at), dtype=np.float64)


__all__ = ["MEADOW_CELL_CM", "MEADOW_HALF_CM", "MEADOW_OVERLAP_CM", "meadow_frame"]
