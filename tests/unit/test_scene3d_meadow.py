"""The endless meadow's frame around the plan (#388, 3D review round 2): ``core/scene3d/meadow.py``.

The render tier holds the picture (``test_scene3d_ground_render.py::
test_the_meadow_never_shows_through_the_plan``); this file holds the mesh: it lies in the
plan's plane, faces up, covers the square less the plan's rectangle — and the strip
under the plan's edge — and no triangle is wider than a cell.
"""

from __future__ import annotations

import numpy as np
import pytest

from open_garden_planner.core.scene3d.meadow import (
    MEADOW_CELL_CM,
    MEADOW_HALF_CM,
    MEADOW_OVERLAP_CM,
    meadow_frame,
)

PLAN = (0.0, 0.0, 2600.0, 1800.0)


def _triangles(mesh) -> np.ndarray:  # noqa: ANN001 - a Mesh
    return mesh.positions[mesh.indices].astype(np.float64)  # (m, 3, 3)


def _areas(triangles: np.ndarray) -> np.ndarray:
    edges = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    return edges[:, 2] / 2.0   # signed: positive is counter-clockwise seen from above


@pytest.mark.parametrize("plan", [PLAN, (0.0, 0.0, 5000.0, 3000.0), (-250.0, 40.0, 780.0, 95.5),
                                  (0.0, 0.0, 10_000.0, 10_000.0), (0.0, 0.0, 30_000.0, 2_000.0)])
def test_the_frame_is_the_square_less_the_plan_in_the_plans_plane(plan: tuple[float, ...]) -> None:
    mesh = meadow_frame(plan)
    triangles = _triangles(mesh)
    east0, north0, east1, north1 = plan
    hole = (east0 + MEADOW_OVERLAP_CM, north0 + MEADOW_OVERLAP_CM,
            east1 - MEADOW_OVERLAP_CM, north1 - MEADOW_OVERLAP_CM)
    assert np.all(mesh.positions[:, 2] == 0.0), "in the plan's plane: no step at its edge"
    areas = _areas(triangles)
    assert np.all(areas > 0.0), "every face up"
    assert np.allclose(mesh.normals, [0.0, 0.0, 1.0])
    side = 2.0 * MEADOW_HALF_CM
    hole_area = (hole[2] - hole[0]) * (hole[3] - hole[1])
    assert areas.sum() == pytest.approx(side * side - hole_area, rel=1e-9)
    low, high = triangles[:, :, :2].min(axis=1), triangles[:, :, :2].max(axis=1)
    assert np.all((high - low) <= MEADOW_CELL_CM + 1e-6), "no triangle wider than a cell"
    # nothing lies on the plan, the strip under its edge excepted
    apart = ((high[:, 0] <= hole[0] + 1e-3) | (low[:, 0] >= hole[2] - 1e-3)
             | (high[:, 1] <= hole[1] + 1e-3) | (low[:, 1] >= hole[3] - 1e-3))  # float32 positions
    assert apart.all()
    centre = ((east0 + east1) / 2.0, (north0 + north1) / 2.0)
    assert low[:, 0].min() == pytest.approx(centre[0] - MEADOW_HALF_CM)
    assert high[:, 1].max() == pytest.approx(centre[1] + MEADOW_HALF_CM)


def test_the_frame_reaches_under_the_plans_edge_and_no_further() -> None:
    """The strip under the edge: the tiles' vertices along it are not the meadow's, and
    an edge shared without its vertices can leave pixels neither side covers. No
    further: the meadow wins the strip, and at 1 cm it took a visible centimetre of a
    surface painted to the edge (3D review of #388, round 3)."""
    assert MEADOW_OVERLAP_CM <= 0.1
    triangles = _triangles(meadow_frame(PLAN))
    half, past = MEADOW_OVERLAP_CM / 2.0, 3.0 * MEADOW_OVERLAP_CM
    for point in ((half, 900.0), (2600.0 - half, 900.0), (1300.0, half), (1300.0, 1800.0 - half),
                  (-50.0, -50.0), (2650.0, 1850.0)):
        assert _covered(triangles, point), point
    for point in ((past, 900.0), (1300.0, 900.0), (2600.0 - past, 1800.0 - past)):
        assert not _covered(triangles, point), point


@pytest.mark.parametrize("off", [-0.3, 0.3])
def test_a_cell_line_near_the_plans_edge_never_moves_the_meadows_edge(off: float) -> None:
    """A 100 m cell line within half a centimetre of a plan edge is dropped for the edge.
    Kept in the edge's place (whichever sorted first), a line just outside the plan
    would end the meadow there and open a gap between it and the plan (round 3)."""
    width = 2.0 * (MEADOW_CELL_CM + MEADOW_OVERLAP_CM + off)   # a cell line at x = overlap + off
    triangles = _triangles(meadow_frame((0.0, 0.0, width, 1800.0)))
    for east in (-0.05, MEADOW_OVERLAP_CM / 2.0):
        assert _covered(triangles, (east, 900.0)), (off, east)
    assert not _covered(triangles, (3.0 * MEADOW_OVERLAP_CM + max(off, 0.0) + 0.1, 900.0))


def _covered(triangles: np.ndarray, point: tuple[float, float]) -> bool:
    a, b, c = (triangles[:, k, :2] for k in range(3))
    p = np.asarray(point)

    def side(u: np.ndarray, v: np.ndarray) -> np.ndarray:
        return (v[:, 0] - u[:, 0]) * (p[1] - u[:, 1]) - (v[:, 1] - u[:, 1]) * (p[0] - u[:, 0])

    return bool(np.any((side(a, b) >= 0) & (side(b, c) >= 0) & (side(c, a) >= 0)))


@pytest.mark.parametrize("plan", [None, (0.0, 0.0, 0.15, 900.0), (0.0, 0.0, 0.2, 0.2)])
def test_no_plan_or_one_narrower_than_the_strip_leaves_no_hole(plan: tuple[float, ...] | None) -> None:
    triangles = _triangles(meadow_frame(plan))
    side = 2.0 * MEADOW_HALF_CM
    assert _areas(triangles).sum() == pytest.approx(side * side, rel=1e-12)
    if plan is None:
        assert triangles[:, :, :2].min() == pytest.approx(-MEADOW_HALF_CM)


@pytest.mark.parametrize("bad", [(0.0, 0.0, float("nan"), 10.0), (0.0, float("inf"), 5.0, 5.0)])
def test_a_plan_that_is_no_rectangle_of_numbers_is_refused(bad: tuple[float, ...]) -> None:
    with pytest.raises(ValueError, match="finite"):
        meadow_frame(bad)


def test_its_size_is_bounded() -> None:
    """43 lines each way at most (41 cell lines and the plan's two): the frame is built
    once per plan rectangle, and it is small."""
    mesh = meadow_frame(PLAN)
    assert mesh.vertex_count <= 43 * 43 and mesh.triangle_count <= 2 * 42 * 42
