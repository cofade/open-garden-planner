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


def test_stats_are_order_free_and_give_no_fake_p95() -> None:
    # below 20 samples a "p95" is just the max (senior review), so none is reported
    assert measure._stats([5.0, 1.0, 3.0]) == {"n": 3, "median": 3.0, "max": 5.0}
    assert measure._stats([]) == {}
    twenty = measure._stats([float(v) for v in range(1, 21)])
    assert twenty["p95"] == 19.0
    assert twenty["max"] == 20.0


def test_oracle_merges_every_model_of_an_item() -> None:
    class _Geo:
        def __init__(self, mesh: M.MeshData) -> None:
            self.mesh = mesh

    class _Model:
        def __init__(self, item_id: str, mesh: M.MeshData) -> None:
            self.itemId = item_id
            self.geometry = _Geo(mesh)

    frame, glass = _square(10.0), _square(30.0, 200.0, 0.0)
    merged = measure._oracle_meshes([_Model("gh", frame), _Model("gh", glass)])
    assert len(merged["gh"]) == 4  # both models' triangles, not the last one only
    assert measure.cpu_topmost_hit(merged, 250.0, 50.0)[0] == "gh"


def test_adversarial_targets_defeat_a_bounding_box_picker() -> None:
    """A thin tall mast on a wide low deck: inside the mast's box but off the mast,
    a correct picker must name the deck — a bounding-box picker names the mast."""
    deck = _square(20.0, 0.0, 0.0, 400.0)
    mast = M.prism([(180, 180), (220, 180), (220, 220), (180, 220)], 300.0, 0.0,
                   "#808080", "#909090")
    # the mast's box is its own footprint here, so widen it with a far-off sliver
    sliver = _square(300.0, 390.0, 390.0, 2.0)
    tall = M.MeshData.concat([mast, sliver])
    tris = _tris(deck=deck, mast=tall)
    targets = measure.adversarial_targets(tris, k=5)
    owners = {owner for *_rest, owner in targets}
    assert "mast" in owners, "no point inside the mast's box but off the mast"
    for x, y, expected, owner in targets:
        assert expected != owner  # a bounding-box picker would answer `owner` here
        assert measure.cpu_topmost_hit(tris, x, y)[0] == expected


def test_top_down_pixel_is_our_own_projection() -> None:
    assert measure.top_down_pixel(100.0, 50.0, (100.0, 50.0), 0.5, (640, 360)) == (320.0, 180.0)
    # east is right, north is UP (smaller row index)
    x, y = measure.top_down_pixel(120.0, 70.0, (100.0, 50.0), 0.5, (640, 360))
    assert (x, y) == (330.0, 170.0)


@pytest.mark.skipif(not sys.platform.startswith(("linux", "win32")), reason="RSS probe platforms")
def test_rss_is_measured_where_supported() -> None:
    rss = measure.rss_mb()
    assert rss is not None
    assert rss > 1.0


class _FakeRenderer:
    """Records what the soak does to a renderer; no engine involved."""

    def __init__(self, models: list[str]) -> None:
        self.models = list(models)
        self.calls: list[str] = []

    def hide(self) -> None:
        self.calls.append("hide")

    def show(self) -> None:
        self.calls.append("show")

    def wait_frames(self, n: int, label: str = "") -> None:
        self.calls.append(f"wait:{label}")

    def set_models(self, models: list[str]) -> None:
        self.models = list(models)
        self.calls.append(f"set:{len(models)}")


def test_soak_reloads_the_project_every_fifth_cycle(qtbot) -> None:
    renderer = _FakeRenderer(["a", "b", "c"])
    builds: list[int] = []

    def reload() -> list[str]:
        builds.append(len(builds))
        return [f"fresh{len(builds)}-{k}" for k in range(3)]

    result = measure.soak(renderer, 10, reload=reload)
    assert result["project_reloads"] == 2 == len(builds)
    assert result["models_per_reload_ok"] is True
    # the scene is emptied before each reload and refilled with the NEW models
    assert renderer.calls.count("set:0") == 2
    assert renderer.models == ["fresh2-0", "fresh2-1", "fresh2-2"]


def test_soak_flags_a_reload_that_lost_models(qtbot) -> None:
    renderer = _FakeRenderer(["a", "b", "c"])
    result = measure.soak(renderer, 5, reload=lambda: ["only-one"])
    assert result["project_reloads"] == 1
    assert result["models_per_reload_ok"] is False


def test_soak_without_reload_refills_the_same_models(qtbot) -> None:
    renderer = _FakeRenderer(["a", "b"])
    result = measure.soak(renderer, 5)
    assert "project_reloads" not in result
    assert renderer.models == ["a", "b"]


def test_rss_tail_slope_tells_a_leak_from_a_settling_allocator() -> None:
    leak = [771.0 + 30.0 * k for k in range(10)]
    settled = [771.0, 804.6, 799.4, 864.0, 864.1, 888.8, 888.9, 887.2, 887.2, 882.4]
    assert measure.rss_tail_slope(leak) == pytest.approx(30.0)
    assert measure.rss_tail_slope(settled) < 2.0  # measured, after the fix
    assert measure.rss_tail_slope([700.0, 710.0, 720.0, 730.0]) is None  # tail too short
    assert measure.rss_tail_slope([1.0, 2.0, 3.0, 4.0, None, 6.0]) is None  # unreadable
