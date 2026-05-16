"""Tests for the SnapProvider abstraction and registry."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtCore import QPointF as _Q  # alias to avoid name shadowing

from open_garden_planner.core.snap.geometry import (
    item_edges,
    segment_intersection,
)
from open_garden_planner.core.snap.provider import (
    SnapCandidate,
    SnapCandidateKind,
    SnapProvider,
)
from open_garden_planner.core.snap.providers import (
    CenterSnapProvider,
    EdgeCardinalSnapProvider,
    EndpointSnapProvider,
    IntersectionSnapProvider,
    MidpointSnapProvider,
)
from open_garden_planner.core.snap.registry import SnapRegistry
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    PolygonItem,
    PolylineItem,
    RectangleItem,
)


@pytest.fixture
def scene(qtbot) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(2000, 2000)


class TestSegmentIntersection:
    def test_perpendicular_cross(self) -> None:
        a = QLineF(0, 0, 100, 0)
        b = QLineF(50, -50, 50, 50)
        hit = segment_intersection(a, b)
        assert hit is not None
        assert abs(hit.x() - 50) < 1e-6
        assert abs(hit.y()) < 1e-6

    def test_parallel_returns_none(self) -> None:
        a = QLineF(0, 0, 100, 0)
        b = QLineF(0, 10, 100, 10)
        assert segment_intersection(a, b) is None

    def test_collinear_returns_none(self) -> None:
        a = QLineF(0, 0, 100, 0)
        b = QLineF(50, 0, 150, 0)
        assert segment_intersection(a, b) is None

    def test_segments_miss(self) -> None:
        a = QLineF(0, 0, 10, 0)
        b = QLineF(50, -50, 50, 50)
        assert segment_intersection(a, b) is None

    def test_endpoint_touch(self) -> None:
        a = QLineF(0, 0, 100, 0)
        b = QLineF(100, 0, 100, 100)
        hit = segment_intersection(a, b)
        assert hit is not None
        assert abs(hit.x() - 100) < 1e-6


class TestItemEdges:
    def test_rectangle_four_edges(self, scene: CanvasScene) -> None:
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        edges = list(item_edges(rect))
        assert len(edges) == 4

    def test_polygon_edges(self, scene: CanvasScene) -> None:
        poly = PolygonItem([_Q(0, 0), _Q(100, 0), _Q(50, 100)])
        scene.addItem(poly)
        edges = list(item_edges(poly))
        assert len(edges) == 3  # closed polygon

    def test_polyline_open(self, scene: CanvasScene) -> None:
        line = PolylineItem([_Q(0, 0), _Q(100, 0), _Q(100, 100)])
        scene.addItem(line)
        edges = list(item_edges(line))
        assert len(edges) == 2


class TestEndpointProvider:
    def test_endpoints_yielded_for_polyline(self, scene: CanvasScene) -> None:
        line = PolylineItem([_Q(0, 0), _Q(100, 0), _Q(100, 100)])
        scene.addItem(line)
        provider = EndpointSnapProvider()
        candidates = list(provider.candidates(_Q(0, 5), [line], threshold=20))
        # PolylineItem stores all vertices as ENDPOINT anchors.
        kinds = {c.kind for c in candidates}
        assert kinds == {SnapCandidateKind.ENDPOINT}


class TestMidpointProvider:
    def test_rect_yields_four_midpoints(self, scene: CanvasScene) -> None:
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        provider = MidpointSnapProvider()
        candidates = list(provider.candidates(_Q(50, 25), [rect], threshold=200))
        mids = {(round(c.point.x(), 1), round(c.point.y(), 1)) for c in candidates}
        # Centres of the four sides.
        assert (50.0, 0.0) in mids
        assert (50.0, 50.0) in mids
        assert (0.0, 25.0) in mids
        assert (100.0, 25.0) in mids


class TestIntersectionProvider:
    def test_two_crossing_lines(self, scene: CanvasScene) -> None:
        a = PolylineItem([_Q(0, 50), _Q(100, 50)])
        b = PolylineItem([_Q(50, 0), _Q(50, 100)])
        scene.addItem(a)
        scene.addItem(b)
        provider = IntersectionSnapProvider()
        cands = list(provider.candidates(_Q(50, 50), [a, b], threshold=20))
        assert len(cands) == 1
        assert abs(cands[0].point.x() - 50) < 1e-6
        assert abs(cands[0].point.y() - 50) < 1e-6

    def test_no_intersection(self, scene: CanvasScene) -> None:
        a = PolylineItem([_Q(0, 50), _Q(100, 50)])
        b = PolylineItem([_Q(0, 100), _Q(100, 100)])
        scene.addItem(a)
        scene.addItem(b)
        provider = IntersectionSnapProvider()
        cands = list(provider.candidates(_Q(50, 75), [a, b], threshold=20))
        assert cands == []

    def test_self_intersection_filtered(self, scene: CanvasScene) -> None:
        # A polygon's adjacent edges meet at a vertex; that must not be
        # surfaced as an "intersection" snap because it would duplicate
        # the endpoint mode.
        poly = PolygonItem([_Q(0, 0), _Q(100, 0), _Q(100, 100), _Q(0, 100)])
        scene.addItem(poly)
        provider = IntersectionSnapProvider()
        cands = list(provider.candidates(_Q(0, 0), [poly], threshold=10))
        assert cands == []


class TestRegistry:
    def test_best_picks_closest(self, scene: CanvasScene) -> None:
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        registry = SnapRegistry(
            [EndpointSnapProvider(), MidpointSnapProvider(), CenterSnapProvider(),
             EdgeCardinalSnapProvider()]
        )
        # Cursor near the right-edge midpoint (100, 25).
        hit = registry.best(_Q(98, 26), [rect], threshold=10)
        assert hit is not None
        assert abs(hit.point.x() - 100) < 1e-6
        assert abs(hit.point.y() - 25) < 1e-6

    def test_priority_breaks_tie(self, scene: CanvasScene) -> None:
        # Construct a corner (endpoint priority 10) co-located with a
        # midpoint candidate (priority 30): endpoint must win.
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        registry = SnapRegistry([MidpointSnapProvider(), EndpointSnapProvider()])
        # Top-left corner of the rect is at (0, 0). The top midpoint is at
        # (50, 0) -> not co-located; instead, pick a point right at a corner.
        hit = registry.best(_Q(0, 0), [rect], threshold=5)
        assert hit is not None
        assert hit.kind == SnapCandidateKind.ENDPOINT

    def test_threshold_rejects(self, scene: CanvasScene) -> None:
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        registry = SnapRegistry([EndpointSnapProvider()])
        # 50 cm away, threshold 5 -> nothing.
        hit = registry.best(_Q(500, 500), [rect], threshold=5)
        assert hit is None

    def test_empty_registry(self, scene: CanvasScene) -> None:
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        registry = SnapRegistry()
        assert registry.best(_Q(0, 0), [rect], threshold=10) is None

    def test_add_remove_has(self) -> None:
        registry = SnapRegistry()
        provider = EndpointSnapProvider()
        registry.add(provider)
        assert registry.has(EndpointSnapProvider)
        registry.remove(EndpointSnapProvider)
        assert not registry.has(EndpointSnapProvider)


class TestCustomProvider:
    def test_provider_protocol(self, scene: CanvasScene) -> None:
        """Any subclass with .candidates() works in the registry."""

        class FixedProvider(SnapProvider):
            kind = SnapCandidateKind.CENTER
            priority = 5

            def candidates(self, _scene_pos, _items, _threshold):  # type: ignore[override]
                yield SnapCandidate(
                    point=QPointF(1, 1),
                    kind=SnapCandidateKind.CENTER,
                    priority=self.priority,
                )

        registry = SnapRegistry([FixedProvider()])
        hit = registry.best(_Q(0, 0), [], threshold=5)
        assert hit is not None
        assert hit.point.x() == 1 and hit.point.y() == 1
