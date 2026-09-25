"""Tests for the quadtree spatial index."""

from __future__ import annotations

import statistics
import time

import pytest
from PyQt6.QtCore import QRectF

from open_garden_planner.core.snap.spatial_index import QuadTree, build_from_items
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import RectangleItem


@pytest.fixture
def scene(qtbot) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(20000, 20000)


def test_empty_query() -> None:
    tree = QuadTree(QRectF(0, 0, 1000, 1000))
    assert tree.query(QRectF(0, 0, 100, 100)) == []


def test_inserted_item_is_found(scene: CanvasScene) -> None:
    rect = RectangleItem(100, 100, 50, 50)
    scene.addItem(rect)
    tree = QuadTree(QRectF(0, 0, 1000, 1000))
    tree.insert(rect.sceneBoundingRect(), rect)
    assert tree.query(QRectF(90, 90, 70, 70)) == [rect]


def test_query_outside_returns_empty(scene: CanvasScene) -> None:
    rect = RectangleItem(100, 100, 50, 50)
    scene.addItem(rect)
    tree = QuadTree(QRectF(0, 0, 1000, 1000))
    tree.insert(rect.sceneBoundingRect(), rect)
    assert tree.query(QRectF(500, 500, 50, 50)) == []


def test_subdivision_handles_many_items(scene: CanvasScene) -> None:
    items = []
    for i in range(40):
        item = RectangleItem(i * 30, i * 30, 20, 20)
        scene.addItem(item)
        items.append(item)
    tree = build_from_items(items)
    # Query a small region containing item index ~5.
    hits = tree.query(QRectF(140, 140, 40, 40))
    # Should only return the items that overlap the query window.
    assert len(hits) >= 1
    assert len(hits) <= 4


def test_overlap_detection(scene: CanvasScene) -> None:
    a = RectangleItem(0, 0, 100, 100)
    b = RectangleItem(50, 50, 100, 100)
    scene.addItem(a)
    scene.addItem(b)
    tree = build_from_items([a, b])
    hits = tree.query(QRectF(70, 70, 10, 10))
    assert set(hits) == {a, b}


def test_no_duplicates_when_item_spans_children(scene: CanvasScene) -> None:
    rect = RectangleItem(0, 0, 1000, 1000)
    scene.addItem(rect)
    tree = build_from_items([rect], scene_bounds=QRectF(0, 0, 1000, 1000))
    hits = tree.query(QRectF(400, 400, 200, 200))
    assert hits == [rect]


def test_perf_thousand_items(scene: CanvasScene) -> None:
    """1000 items build under a median 200ms and query under a median 1ms.

    CI runners are shared and a single wall-clock sample previously produced a
    false failure at 284ms.  The robust statistic absorbs an isolated scheduler
    spike while still failing for a consistently slower quadtree build.  The
    end-to-end snap budget of 16ms in ``test_point_snapper.py`` remains the
    user-facing gate; this test protects the pre-filter rebuild itself.
    """
    items: list[RectangleItem] = []
    for i in range(1000):
        x = (i % 50) * 30
        y = (i // 50) * 30
        item = RectangleItem(x, y, 20, 20)
        scene.addItem(item)
        items.append(item)

    # Warm the code path once so import/allocation costs do not dominate the
    # distribution.  The measured samples all use the same Qt item set.
    build_from_items(items)
    build_samples: list[float] = []
    tree = None
    for _ in range(5):
        t0 = time.perf_counter()
        tree = build_from_items(items)
        build_samples.append((time.perf_counter() - t0) * 1000)
    assert tree is not None
    build_median_ms = statistics.median(build_samples)
    assert build_median_ms < 200, (
        "build samples (ms)="
        f"{[round(sample, 3) for sample in build_samples]}, "
        f"median={build_median_ms:.3f}ms"
    )

    query_samples: list[float] = []
    query_rect = QRectF(150, 150, 30, 30)
    for _ in range(5):
        t0 = time.perf_counter()
        for _ in range(100):
            tree.query(query_rect)
        query_samples.append((time.perf_counter() - t0) * 1000 / 100)
    query_median_ms = statistics.median(query_samples)
    assert query_median_ms < 1.0, (
        "query samples (ms/query)="
        f"{[round(sample, 6) for sample in query_samples]}, "
        f"median={query_median_ms:.6f}ms"
    )
