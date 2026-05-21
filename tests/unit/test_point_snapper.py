"""Tests for the PointSnapper end-to-end pipeline."""

from __future__ import annotations

import time

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.snap import PointSnapper, SnapRegistry
from open_garden_planner.core.snap.providers import (
    EndpointSnapProvider,
    IntersectionSnapProvider,
    MidpointSnapProvider,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    PolylineItem,
    RectangleItem,
)


@pytest.fixture
def scene(qtbot) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(2000, 2000)


def test_returns_none_when_scene_empty() -> None:
    snapper = PointSnapper(SnapRegistry([EndpointSnapProvider()]))
    assert snapper.snap(QPointF(0, 0), threshold=10) is None


def test_finds_endpoint(scene: CanvasScene) -> None:
    line = PolylineItem([QPointF(0, 0), QPointF(100, 0)])
    scene.addItem(line)
    snapper = PointSnapper(SnapRegistry([EndpointSnapProvider()]))
    snapper.update_scene([line])
    hit = snapper.snap(QPointF(3, 2), threshold=10)
    assert hit is not None
    assert abs(hit.point.x()) < 1e-6


def test_intersection_picked_over_midpoint_when_co_located(
    scene: CanvasScene,
) -> None:
    horiz = PolylineItem([QPointF(-100, 0), QPointF(100, 0)])
    vert = PolylineItem([QPointF(0, -100), QPointF(0, 100)])
    scene.addItem(horiz)
    scene.addItem(vert)
    snapper = PointSnapper(
        SnapRegistry([IntersectionSnapProvider(), MidpointSnapProvider()])
    )
    snapper.update_scene([horiz, vert])
    hit = snapper.snap(QPointF(2, 2), threshold=10)
    assert hit is not None
    from open_garden_planner.core.snap.provider import SnapCandidateKind

    assert hit.kind == SnapCandidateKind.INTERSECTION


def test_far_query_returns_none(scene: CanvasScene) -> None:
    rect = RectangleItem(0, 0, 50, 50)
    scene.addItem(rect)
    snapper = PointSnapper(SnapRegistry([EndpointSnapProvider()]))
    snapper.update_scene([rect])
    assert snapper.snap(QPointF(500, 500), threshold=10) is None


def test_perf_end_to_end(scene: CanvasScene) -> None:
    """1000 items: typical snap query must be < 16ms (60fps budget)."""
    items: list[RectangleItem] = []
    for i in range(1000):
        x = (i % 50) * 30
        y = (i // 50) * 30
        item = RectangleItem(x, y, 20, 20)
        scene.addItem(item)
        items.append(item)

    snapper = PointSnapper(
        SnapRegistry(
            [
                EndpointSnapProvider(),
                MidpointSnapProvider(),
                IntersectionSnapProvider(),
            ]
        )
    )
    snapper.update_scene(items)

    # Warm-up
    snapper.snap(QPointF(150, 150), threshold=15)

    t0 = time.perf_counter()
    for _ in range(50):
        snapper.snap(QPointF(150, 150), threshold=15)
    avg_ms = (time.perf_counter() - t0) * 1000 / 50
    assert avg_ms < 16.0, f"end-to-end snap avg {avg_ms:.2f}ms exceeds 16ms"
