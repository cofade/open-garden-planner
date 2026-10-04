"""The Qt-free halves of the spike's L0.2 measurements (ADR-047 criteria 6, 7, 10).

The pick probe is only as good as its oracle: a wrong CPU "expected item" would
turn a broken engine pick into a pass. These tests pin the oracle on meshes
whose answer is known by construction.
"""

from __future__ import annotations

import math
import sys

import numpy as np
import pytest

from open_garden_planner.spike_q3d import measure
from open_garden_planner.spike_q3d import meshes as M


def _square(z: float, x0: float = 0.0, y0: float = 0.0, size: float = 100.0) -> M.MeshData:
    pos = np.array([[x0, y0, z], [x0 + size, y0, z], [x0 + size, y0 + size, z],
                    [x0, y0 + size, z]], np.float32)
    n = len(pos)
    return M.MeshData(pos, np.tile(np.float32([0, 0, 1]), (n, 1)),
                      np.ones((n, 4), np.float32), np.zeros((n, 2), np.float32),
                      np.array([0, 1, 2, 0, 2, 3], np.uint32))


def _tris(**meshes: M.MeshData) -> dict[str, np.ndarray]:
    return {name: measure._triangles(mesh) for name, mesh in meshes.items()}


def test_oracle_names_the_topmost_of_stacked_surfaces() -> None:
    tris = _tris(low=_square(10.0), high=_square(50.0, 25.0, 25.0, 50.0))
    assert measure.cpu_topmost_hit(tris, 50.0, 50.0) == ("high", pytest.approx(50.0))
    assert measure.cpu_topmost_hit(tris, 10.0, 10.0) == ("low", pytest.approx(10.0))


def test_oracle_reports_a_miss_as_none() -> None:
    hit, z = measure.cpu_topmost_hit(_tris(only=_square(10.0)), 500.0, 500.0)
    assert hit is None
    assert z == -math.inf


def test_oracle_counts_a_shared_edge_as_inside() -> None:
    # (50, 50) lies on the diagonal both triangles of the square share
    assert measure.cpu_topmost_hit(_tris(sq=_square(5.0)), 50.0, 50.0)[0] == "sq"


def test_top_target_is_on_the_top_face_of_a_box() -> None:
    box = M.prism([(0, 0), (80, 0), (80, 40), (0, 40)], 120.0, 0.0, "#808080", "#909090")
    x, y = measure._top_target(measure._triangles(box))
    assert 0.0 <= x <= 80.0
    assert 0.0 <= y <= 40.0
    assert measure.cpu_topmost_hit(_tris(box=box), x, y) == ("box", pytest.approx(120.0, abs=0.5))


def test_top_target_refuses_a_mesh_with_no_upward_face() -> None:
    pos = np.array([[0, 0, 0], [100, 0, 0], [100, 0, 100], [0, 0, 100]], np.float32)
    wall = M.MeshData(pos, np.tile(np.float32([0, -1, 0]), (4, 1)), np.ones((4, 4), np.float32),
                      np.zeros((4, 2), np.float32), np.array([0, 1, 2, 0, 2, 3], np.uint32))
    assert measure._top_target(measure._triangles(wall)) is None


def test_update_bench_grid_is_the_advertised_size() -> None:
    mesh = measure._grid_mesh(317, 0.0)
    assert mesh.vertex_count == 317 * 317 >= 100_000
    assert mesh.triangle_count == 2 * 316 * 316
    assert int(mesh.indices.max()) < mesh.vertex_count
    assert not np.isnan(mesh.positions).any()


def test_stats_are_order_free() -> None:
    assert measure._stats([5.0, 1.0, 3.0]) == {"median": 3.0, "p95": 5.0, "max": 5.0}
    assert measure._stats([]) == {}


@pytest.mark.skipif(not sys.platform.startswith(("linux", "win32")), reason="RSS probe platforms")
def test_rss_is_measured_where_supported() -> None:
    rss = measure.rss_mb()
    assert rss is not None
    assert rss > 1.0
