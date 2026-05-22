"""Unit tests for BezierItem (Phase 13 Package B — US-B1)."""

from __future__ import annotations

import uuid

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.ui.canvas.items import BezierItem


def _approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


@pytest.fixture()
def simple_bezier(qtbot: object) -> BezierItem:  # noqa: ARG001
    """Two-anchor curve: corner anchors at (0, 0) and (100, 0).

    Zero-length handles render as a straight-line cubic segment.
    """
    return BezierItem(
        anchors=[QPointF(0, 0), QPointF(100, 0)],
        handles_in=[QPointF(0, 0), QPointF(100, 0)],
        handles_out=[QPointF(0, 0), QPointF(100, 0)],
    )


@pytest.fixture()
def smooth_bezier(qtbot: object) -> BezierItem:  # noqa: ARG001
    """Three-anchor smooth S-curve through (0,0), (100,50), (200,0)."""
    return BezierItem(
        anchors=[QPointF(0, 0), QPointF(100, 50), QPointF(200, 0)],
        handles_in=[QPointF(0, 0), QPointF(50, 60), QPointF(200, 0)],
        handles_out=[QPointF(0, 0), QPointF(150, 40), QPointF(200, 0)],
    )


class TestBezierItemConstruction:
    def test_anchor_and_segment_counts(self, smooth_bezier: BezierItem) -> None:
        assert smooth_bezier.anchor_count == 3
        assert smooth_bezier.segment_count == 2

    def test_item_id_is_uuid(self, simple_bezier: BezierItem) -> None:
        assert isinstance(simple_bezier.item_id, uuid.UUID)

    def test_rejects_single_anchor(self, qtbot: object) -> None:  # noqa: ARG002
        with pytest.raises(ValueError, match="at least"):
            BezierItem(
                anchors=[QPointF(0, 0)],
                handles_in=[QPointF(0, 0)],
                handles_out=[QPointF(0, 0)],
            )

    def test_rejects_mismatched_handle_lengths(self, qtbot: object) -> None:  # noqa: ARG002
        with pytest.raises(ValueError, match="one entry per anchor"):
            BezierItem(
                anchors=[QPointF(0, 0), QPointF(1, 1)],
                handles_in=[QPointF(0, 0)],  # only 1, should be 2
                handles_out=[QPointF(0, 0), QPointF(1, 1)],
            )


class TestBezierItemAccessors:
    def test_anchors_returns_copy(self, smooth_bezier: BezierItem) -> None:
        """Mutating the returned list must not affect internal state."""
        copy = smooth_bezier.anchors
        copy.append(QPointF(999, 999))
        assert smooth_bezier.anchor_count == 3

    def test_start_and_end_points_in_scene_coords(
        self, smooth_bezier: BezierItem
    ) -> None:
        smooth_bezier.setPos(10, 20)
        s = smooth_bezier.start_point()
        e = smooth_bezier.end_point()
        assert _approx(s.x(), 10) and _approx(s.y(), 20)
        assert _approx(e.x(), 210) and _approx(e.y(), 20)


class TestBezierItemPath:
    def test_path_has_segment_count_curves(
        self, smooth_bezier: BezierItem
    ) -> None:
        """A multi-segment cubic Bezier produces a QPainterPath that
        contains one moveTo plus N-1 cubicTo elements (= 3N-2 elements
        total: each cubicTo emits 3 path elements).
        """
        path = smooth_bezier.path()
        # 1 moveTo + 2 cubic segments × 3 elements per cubic = 7
        assert path.elementCount() == 7
        # First element is a moveTo at the first anchor.
        e0 = path.elementAt(0)
        assert _approx(e0.x, 0) and _approx(e0.y, 0)

    def test_bounding_rect_includes_path_extent(
        self, smooth_bezier: BezierItem
    ) -> None:
        rect = smooth_bezier.boundingRect()
        # Path passes through y = 50; rect must include it.
        assert rect.contains(QPointF(100, 50))


class TestBezierItemScene:
    def test_can_be_added_and_removed(self, simple_bezier: BezierItem) -> None:
        scene = QGraphicsScene()
        scene.addItem(simple_bezier)
        assert simple_bezier.scene() is scene
        scene.removeItem(simple_bezier)
        assert simple_bezier.scene() is None

    def test_is_selectable_and_movable(self, simple_bezier: BezierItem) -> None:
        from PyQt6.QtWidgets import QGraphicsItem
        flags = simple_bezier.flags()
        assert flags & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        assert flags & QGraphicsItem.GraphicsItemFlag.ItemIsMovable


class TestBezierItemSerialization:
    def test_to_dict_includes_all_arrays(self, smooth_bezier: BezierItem) -> None:
        d = smooth_bezier.to_dict()
        assert d["type"] == "bezier"
        assert len(d["anchors"]) == 3
        assert len(d["handles_in"]) == 3
        assert len(d["handles_out"]) == 3
        assert "item_id" in d

    def test_roundtrip_preserves_anchors_and_handles(
        self, smooth_bezier: BezierItem
    ) -> None:
        d = smooth_bezier.to_dict()
        clone = BezierItem.from_dict(d)
        assert clone.anchor_count == smooth_bezier.anchor_count
        for a, b in zip(clone.anchors, smooth_bezier.anchors, strict=True):
            assert _approx(a.x(), b.x()) and _approx(a.y(), b.y())
        for a, b in zip(clone.handles_in, smooth_bezier.handles_in, strict=True):
            assert _approx(a.x(), b.x()) and _approx(a.y(), b.y())
        for a, b in zip(clone.handles_out, smooth_bezier.handles_out, strict=True):
            assert _approx(a.x(), b.x()) and _approx(a.y(), b.y())

    def test_roundtrip_preserves_item_id(self, simple_bezier: BezierItem) -> None:
        clone = BezierItem.from_dict(simple_bezier.to_dict())
        assert clone.item_id == simple_bezier.item_id

    def test_roundtrip_preserves_stroke(self, qtbot: object) -> None:  # noqa: ARG002
        from PyQt6.QtGui import QColor
        item = BezierItem(
            anchors=[QPointF(0, 0), QPointF(10, 0)],
            handles_in=[QPointF(0, 0), QPointF(10, 0)],
            handles_out=[QPointF(0, 0), QPointF(10, 0)],
        )
        item.stroke_color = QColor(0, 128, 255)
        item.stroke_width = 2.25
        clone = BezierItem.from_dict(item.to_dict())
        assert clone.stroke_color.blue() == 255
        assert _approx(clone.stroke_width, 2.25)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
