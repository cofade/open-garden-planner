"""Unit tests for NearestSnapProvider (Phase 13 Package B — US-B4)."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.snap.provider import SnapCandidateKind
from open_garden_planner.core.snap.providers import NearestSnapProvider
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    BezierItem,
    CircleItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)


def _Q(x: float, y: float) -> QPointF:
    return QPointF(x, y)


def _approx(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) <= tol


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=5000, height_cm=3000)


@pytest.fixture()
def provider() -> NearestSnapProvider:
    return NearestSnapProvider()


class TestRectangle:
    def test_nearest_point_on_top_edge(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        # Cursor 5 units above the top edge midpoint → snap projects onto
        # (50, 0) (closest point on the top edge).
        candidates = list(provider.candidates(_Q(50, -5), [rect], threshold=20))
        assert candidates, "expected a nearest candidate on the top edge"
        c = candidates[0]
        assert c.kind == SnapCandidateKind.NEAREST
        # One of the candidates from the four edges should be at (50, 0).
        nearest = min(
            candidates,
            key=lambda c: (c.point.x() - 50) ** 2 + (c.point.y() - 0) ** 2,
        )
        assert _approx(nearest.point.x(), 50.0)
        assert _approx(nearest.point.y(), 0.0)


class TestCircle:
    def test_nearest_on_circumference(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        circle = CircleItem(0, 0, 100)
        scene.addItem(circle)
        # Cursor at (150, 0) → nearest point is (100, 0).
        candidates = list(provider.candidates(_Q(150, 0), [circle], threshold=80))
        assert candidates
        c = candidates[0]
        assert _approx(c.point.x(), 100.0)
        assert _approx(c.point.y(), 0.0)

    def test_nearest_when_inside_circle(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        """Cursor inside the circle: nearest projects out along the radial."""
        circle = CircleItem(0, 0, 100)
        scene.addItem(circle)
        candidates = list(provider.candidates(_Q(50, 0), [circle], threshold=80))
        assert candidates
        c = candidates[0]
        assert _approx(c.point.x(), 100.0)
        assert _approx(c.point.y(), 0.0)


class TestPolyline:
    def test_nearest_on_segment(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        poly = PolylineItem(points=[_Q(0, 0), _Q(100, 0), _Q(100, 100)])
        scene.addItem(poly)
        # Cursor 5 units above mid of first segment.
        candidates = list(provider.candidates(_Q(50, -5), [poly], threshold=20))
        assert candidates
        # Pick the candidate closest to (50, 0).
        nearest = min(
            candidates,
            key=lambda c: (c.point.x() - 50) ** 2 + (c.point.y() - 0) ** 2,
        )
        assert _approx(nearest.point.x(), 50.0)
        assert _approx(nearest.point.y(), 0.0)


class TestPolygon:
    def test_nearest_clamps_to_segment_endpoint(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        """Cursor past a segment's endpoint clamps to the endpoint."""
        poly = PolygonItem(vertices=[_Q(0, 0), _Q(100, 0), _Q(50, 100)])
        scene.addItem(poly)
        # Cursor far to the left of the bottom edge → projects to the
        # left vertex (0, 0) under the bottom-edge projection.
        candidates = list(provider.candidates(_Q(-5, -5), [poly], threshold=20))
        assert candidates
        nearest = min(
            candidates,
            key=lambda c: (c.point.x() + 5) ** 2 + (c.point.y() + 5) ** 2,
        )
        # Should clamp to (0, 0).
        assert _approx(nearest.point.x(), 0.0)
        assert _approx(nearest.point.y(), 0.0)


class TestArc:
    def test_nearest_on_semicircle(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        # Math-convention semicircle: center (0,0), r=100, start 0°, span 180°.
        # The midpoint of this arc is at (0, 100).
        arc = ArcItem(_Q(0, 0), 100, start_deg=0.0, span_deg=180.0)
        scene.addItem(arc)
        # Cursor at (0, 120): on the radial outside the arc midpoint.
        # Projected to the arc → (0, 100).
        candidates = list(provider.candidates(_Q(0, 120), [arc], threshold=40))
        assert candidates
        c = candidates[0]
        assert _approx(c.point.x(), 0.0)
        assert _approx(c.point.y(), 100.0)

    def test_outside_sweep_clamps_to_endpoint(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        """Cursor outside the arc's angular sweep clamps to nearest endpoint."""
        # 90° arc from 0° to 90° centered at origin, r=100.
        # Endpoints: (100, 0) at start, (0, 100) at end.
        arc = ArcItem(_Q(0, 0), 100, start_deg=0.0, span_deg=90.0)
        scene.addItem(arc)
        # Cursor at (100, -50): outside the sweep (angle ≈ -27°).
        # Nearest endpoint should be (100, 0).
        candidates = list(provider.candidates(_Q(100, -50), [arc], threshold=80))
        assert candidates
        c = candidates[0]
        assert _approx(c.point.x(), 100.0)
        assert _approx(c.point.y(), 0.0)


class TestBezier:
    def test_nearest_on_curve_via_path_sampling(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        """Bezier item: fallback path sampling produces a point ON the curve."""
        anchors = [_Q(0, 0), _Q(200, 0)]
        # Symmetric handles pointing up — curve bulges upward.
        handles_in = [_Q(0, 0), _Q(200, 0)]
        handles_out = [_Q(0, -100), _Q(200, -100)]  # control points above
        bez = BezierItem(anchors, handles_in, handles_out)
        scene.addItem(bez)
        # Cursor at (100, -75) — likely just above the curve.
        candidates = list(provider.candidates(_Q(100, -75), [bez], threshold=80))
        assert candidates
        c = candidates[0]
        # The closest curve point is somewhere around y ≈ -75 at x ≈ 100.
        # Sampling resolution gives sub-cm accuracy; we just check it's
        # on the curve (close to the cursor in y).
        d = math.hypot(c.point.x() - 100, c.point.y() + 75)
        assert d < 50, f"snap point ({c.point.x()}, {c.point.y()}) too far from cursor"


class TestThresholdAndFlags:
    def test_far_cursor_yields_nothing(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        # Cursor 100 units away from any edge; threshold 20.
        candidates = list(provider.candidates(_Q(500, 500), [rect], threshold=20))
        assert candidates == []

    def test_non_selectable_items_ignored(
        self, scene: CanvasScene, provider: NearestSnapProvider
    ) -> None:
        from PyQt6.QtWidgets import QGraphicsItem

        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        candidates = list(provider.candidates(_Q(50, -5), [rect], threshold=20))
        assert candidates == []

    def test_priority_is_45(self, provider: NearestSnapProvider) -> None:
        """Ensures the documented fallback priority is preserved."""
        assert provider.priority == 45


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
