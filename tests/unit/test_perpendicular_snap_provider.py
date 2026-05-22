"""Unit tests for PerpendicularSnapProvider (Phase 13 Package B — US-B5)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.snap.provider import SnapCandidateKind
from open_garden_planner.core.snap.providers import PerpendicularSnapProvider
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    CircleItem,
    PolylineItem,
    RectangleItem,
)


def _Q(x: float, y: float) -> QPointF:
    return QPointF(x, y)


def _approx(a: float, b: float, tol: float = 1e-4) -> bool:
    return abs(a - b) <= tol


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=5000, height_cm=3000)


@pytest.fixture()
def provider() -> PerpendicularSnapProvider:
    return PerpendicularSnapProvider()


class TestActivation:
    def test_without_reference_yields_nothing(
        self, scene: CanvasScene, provider: PerpendicularSnapProvider
    ) -> None:
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        # No reference_point → no candidates regardless of cursor position.
        candidates = list(provider.candidates(_Q(50, 30), [rect], threshold=20))
        assert candidates == []

    def test_priority_is_25(self, provider: PerpendicularSnapProvider) -> None:
        assert provider.priority == 25


class TestStraightEdge:
    def test_foot_within_segment(
        self, scene: CanvasScene, provider: PerpendicularSnapProvider
    ) -> None:
        """Reference at (50, -50) above the rect; top edge is y=0 from
        x=0 to x=100. Foot is (50, 0); cursor at (52, 2) is within
        threshold of the foot."""
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        candidates = list(
            provider.candidates(
                _Q(52, 2), [rect], threshold=20, reference_point=_Q(50, -50)
            )
        )
        feet = [c for c in candidates if c.kind == SnapCandidateKind.PERPENDICULAR]
        assert feet
        best = min(feet, key=lambda c: (c.point.x() - 52) ** 2 + (c.point.y() - 2) ** 2)
        assert _approx(best.point.x(), 50.0)
        assert _approx(best.point.y(), 0.0)

    def test_foot_outside_segment_skipped(
        self, scene: CanvasScene, provider: PerpendicularSnapProvider
    ) -> None:
        """Reference far past one end of an edge → perpendicular foot
        falls outside the segment → provider yields no candidate for
        that edge. (Other edges may still match.)"""
        poly = PolylineItem(points=[_Q(0, 0), _Q(100, 0)])  # single segment
        scene.addItem(poly)
        # Reference at (-200, 50). Perpendicular foot would be at (-200, 0)
        # which is outside [0, 100]. Provider must yield nothing.
        candidates = list(
            provider.candidates(
                _Q(-200, 0), [poly], threshold=20, reference_point=_Q(-200, 50)
            )
        )
        assert candidates == []

    def test_cursor_far_from_foot_is_filtered(
        self, scene: CanvasScene, provider: PerpendicularSnapProvider
    ) -> None:
        """Foot is correct geometrically but the cursor is beyond the
        threshold from it — no candidate."""
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        # Foot would be (50, 0); cursor at (50, 200) is way past threshold 20.
        # But the bounding-rect prefilter rejects this too — cursor is
        # outside rect+threshold envelope. Both paths produce []:
        candidates = list(
            provider.candidates(
                _Q(50, 200), [rect], threshold=20, reference_point=_Q(50, 50)
            )
        )
        assert candidates == []


class TestCircle:
    def test_radial_foot(
        self, scene: CanvasScene, provider: PerpendicularSnapProvider
    ) -> None:
        circle = CircleItem(0, 0, 100)
        scene.addItem(circle)
        # Reference at (200, 0); radial projection to circumference is (100, 0).
        # Cursor at (105, 3) within threshold.
        candidates = list(
            provider.candidates(
                _Q(105, 3), [circle], threshold=20, reference_point=_Q(200, 0)
            )
        )
        perp = [c for c in candidates if c.kind == SnapCandidateKind.PERPENDICULAR]
        assert perp
        assert _approx(perp[0].point.x(), 100.0)
        assert _approx(perp[0].point.y(), 0.0)


class TestArc:
    def test_radial_foot_in_sweep(
        self, scene: CanvasScene, provider: PerpendicularSnapProvider
    ) -> None:
        # Semicircle, center (0,0), r=100, sweep 0°..180°.
        arc = ArcItem(_Q(0, 0), 100, start_deg=0.0, span_deg=180.0)
        scene.addItem(arc)
        # Reference (0, 200): radial foot is (0, 100), inside the sweep.
        candidates = list(
            provider.candidates(
                _Q(0, 105), [arc], threshold=20, reference_point=_Q(0, 200)
            )
        )
        perp = [c for c in candidates if c.kind == SnapCandidateKind.PERPENDICULAR]
        assert perp
        assert _approx(perp[0].point.x(), 0.0)
        assert _approx(perp[0].point.y(), 100.0)

    def test_foot_outside_sweep_yields_nothing(
        self, scene: CanvasScene, provider: PerpendicularSnapProvider
    ) -> None:
        """Quarter-arc 0..90°; reference whose radial direction lies
        outside the sweep → no perpendicular candidate."""
        arc = ArcItem(_Q(0, 0), 100, start_deg=0.0, span_deg=90.0)
        scene.addItem(arc)
        # Reference at (-200, 0) → radial direction is 180°, outside [0..90].
        candidates = list(
            provider.candidates(
                _Q(-105, 0), [arc], threshold=20, reference_point=_Q(-200, 0)
            )
        )
        assert candidates == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
