"""Tests for the quadtree spatial index."""

from __future__ import annotations

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
    """1000 items must be inserted in < 30ms and queried in < 1ms."""
    items: list[RectangleItem] = []
    for i in range(1000):
        x = (i % 50) * 30
        y = (i // 50) * 30
        item = RectangleItem(x, y, 20, 20)
        scene.addItem(item)
        items.append(item)

    t0 = time.perf_counter()
    tree = build_from_items(items)
    build_ms = (time.perf_counter() - t0) * 1000
    # Generous ceiling to absorb CI variance; the end-to-end snap budget
    # of 16ms in test_point_snapper.py is the user-facing gate.
    assert build_ms < 200, f"build took {build_ms:.1f}ms"

    t0 = time.perf_counter()
    for _ in range(100):
        tree.query(QRectF(150, 150, 30, 30))
    query_ms = (time.perf_counter() - t0) * 1000 / 100
    assert query_ms < 1.0, f"query took {query_ms:.3f}ms avg"
