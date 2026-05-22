"""Unit tests for TangentSnapProvider (Phase 13 Package B — US-B6)."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.snap.provider import SnapCandidateKind
from open_garden_planner.core.snap.providers import TangentSnapProvider
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import ArcItem, CircleItem


def _Q(x: float, y: float) -> QPointF:
    return QPointF(x, y)


def _approx(a: float, b: float, tol: float = 1e-4) -> bool:
    return abs(a - b) <= tol


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=5000, height_cm=3000)


@pytest.fixture()
def provider() -> TangentSnapProvider:
    return TangentSnapProvider()


class TestActivation:
    def test_without_reference_yields_nothing(
        self, scene: CanvasScene, provider: TangentSnapProvider
    ) -> None:
        circle = CircleItem(0, 0, 100)
        scene.addItem(circle)
        candidates = list(provider.candidates(_Q(0, 0), [circle], threshold=20))
        assert candidates == []

    def test_priority_is_26(self, provider: TangentSnapProvider) -> None:
        assert provider.priority == 26


class TestCircleTangents:
    def test_two_tangent_solutions_from_external_point(
        self, scene: CanvasScene, provider: TangentSnapProvider
    ) -> None:
        """From an external point, there are exactly two tangent points.

        Reference at (200, 0) onto a circle centred at the origin with
        radius 100. Distance d=200, so alpha = acos(100/200) = 60°. The
        two tangent points are at angles ±60° from the +X axis:
        (50, ±86.60).
        """
        circle = CircleItem(0, 0, 100)
        scene.addItem(circle)

        # Run the math on the *circle helper* with a wide threshold so
        # both tangents pass; then verify the two solutions match the
        # closed-form expectation.
        big = 1000.0
        candidates = list(
            provider.candidates(
                _Q(50, 0), [circle], threshold=big, reference_point=_Q(200, 0)
            )
        )
        pts = {(round(c.point.x(), 3), round(c.point.y(), 3)) for c in candidates}
        expected = math.sqrt(3) / 2 * 100  # 86.60254...
        assert (50.0, round(expected, 3)) in pts
        assert (50.0, -round(expected, 3)) in pts

    def test_cursor_picks_the_closer_tangent(
        self, scene: CanvasScene, provider: TangentSnapProvider
    ) -> None:
        """With threshold tight to the cursor, only the near-side tangent fires."""
        circle = CircleItem(0, 0, 100)
        scene.addItem(circle)
        expected_y = math.sqrt(3) / 2 * 100  # ≈86.60
        # Cursor near the +y tangent point (50, +86.60).
        candidates = list(
            provider.candidates(
                _Q(50, expected_y - 2),
                [circle],
                threshold=10,
                reference_point=_Q(200, 0),
            )
        )
        assert len(candidates) == 1
        c = candidates[0]
        assert c.kind == SnapCandidateKind.TANGENT
        assert _approx(c.point.x(), 50.0)
        assert _approx(c.point.y(), expected_y)

    def test_ref_inside_circle_yields_no_tangent(
        self, scene: CanvasScene, provider: TangentSnapProvider
    ) -> None:
        circle = CircleItem(0, 0, 100)
        scene.addItem(circle)
        candidates = list(
            provider.candidates(
                _Q(0, 0),
                [circle],
                threshold=1000,
                reference_point=_Q(20, 0),  # inside
            )
        )
        assert candidates == []

    def test_ref_at_center_yields_no_tangent(
        self, scene: CanvasScene, provider: TangentSnapProvider
    ) -> None:
        circle = CircleItem(0, 0, 100)
        scene.addItem(circle)
        candidates = list(
            provider.candidates(
                _Q(50, 50),
                [circle],
                threshold=1000,
                reference_point=_Q(0, 0),  # at centre
            )
        )
        assert candidates == []


class TestArcTangents:
    def test_only_in_sweep_tangent_emits(
        self, scene: CanvasScene, provider: TangentSnapProvider
    ) -> None:
        """Quarter arc from 0° to 90° on a circle of radius 100 centred
        at the origin. Reference (200, 0) has two tangent points on the
        full circle — only the one at (50, +86.60) falls within the
        0°..90° sweep. The other (50, -86.60) is filtered out.
        """
        # Full sweep 0..90, so only the upper tangent qualifies.
        arc = ArcItem(_Q(0, 0), 100, start_deg=0.0, span_deg=90.0)
        scene.addItem(arc)
        big = 1000.0
        candidates = list(
            provider.candidates(
                _Q(50, 0), [arc], threshold=big, reference_point=_Q(200, 0)
            )
        )
        assert len(candidates) == 1
        c = candidates[0]
        expected_y = math.sqrt(3) / 2 * 100
        assert _approx(c.point.x(), 50.0)
        assert _approx(c.point.y(), expected_y)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
