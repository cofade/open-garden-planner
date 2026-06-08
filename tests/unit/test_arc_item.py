"""Unit tests for ArcItem (Phase 13 Package B — US-B2)."""

from __future__ import annotations

import math
import uuid

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.cad_geometry import (
    arc_from_three_points,
    arc_to_painter_path,
)
from open_garden_planner.ui.canvas.items import ArcItem


def _approx(a: float, b: float, tol: float = 1e-4) -> bool:
    return abs(a - b) <= tol


@pytest.fixture()
def basic_arc(qtbot: object) -> ArcItem:  # noqa: ARG001
    """A standard semicircle arc: center (0, 0), radius 100, from 0° to 180°."""
    return ArcItem(
        center=QPointF(0, 0),
        radius=100.0,
        start_deg=0.0,
        span_deg=180.0,
    )


class TestArcItemConstruction:
    def test_basic_properties(self, basic_arc: ArcItem) -> None:
        assert basic_arc.radius == 100.0
        assert basic_arc.start_deg == 0.0
        assert basic_arc.span_deg == 180.0
        assert isinstance(basic_arc.item_id, uuid.UUID)

    def test_rejects_zero_radius(self, qtbot: object) -> None:  # noqa: ARG002
        with pytest.raises(ValueError, match="radius"):
            ArcItem(center=QPointF(0, 0), radius=0.0, start_deg=0, span_deg=90)

    def test_rejects_negative_radius(self, qtbot: object) -> None:  # noqa: ARG002
        with pytest.raises(ValueError, match="radius"):
            ArcItem(center=QPointF(0, 0), radius=-5.0, start_deg=0, span_deg=90)


class TestArcItemDerivedPoints:
    def test_start_point_at_zero_degrees(self, basic_arc: ArcItem) -> None:
        """Semicircle at 0° start: start point is at (radius, 0)."""
        p = basic_arc.start_point()
        assert _approx(p.x(), 100.0)
        assert _approx(p.y(), 0.0)

    def test_end_point_at_180_degrees(self, basic_arc: ArcItem) -> None:
        """Semicircle of span 180°: end point is at (-radius, 0)."""
        p = basic_arc.end_point()
        assert _approx(p.x(), -100.0)
        assert _approx(p.y(), 0.0)

    def test_midpoint_at_90_degrees(self, basic_arc: ArcItem) -> None:
        """Semicircle midpoint at 90°: (0, radius)."""
        p = basic_arc.midpoint()
        assert _approx(p.x(), 0.0)
        assert _approx(p.y(), 100.0)

    def test_center_in_scene_coordinates(self, basic_arc: ArcItem) -> None:
        """Center is reported in scene coordinates regardless of item position."""
        basic_arc.setPos(50, 30)  # Shift the item.
        c = basic_arc.center
        assert _approx(c.x(), 50.0)
        assert _approx(c.y(), 30.0)


class TestArcItemSerialization:
    def test_to_dict_includes_geometry(self, basic_arc: ArcItem) -> None:
        d = basic_arc.to_dict()
        assert d["type"] == "arc"
        assert _approx(d["center_x"], 0.0)
        assert _approx(d["center_y"], 0.0)
        assert _approx(d["radius"], 100.0)
        assert _approx(d["start_deg"], 0.0)
        assert _approx(d["span_deg"], 180.0)
        assert "item_id" in d

    def test_roundtrip_preserves_geometry(self, basic_arc: ArcItem) -> None:
        """Save → load preserves center, radius, angles, and item_id."""
        d = basic_arc.to_dict()
        clone = ArcItem.from_dict(d)
        assert clone.radius == basic_arc.radius
        assert clone.start_deg == basic_arc.start_deg
        assert clone.span_deg == basic_arc.span_deg
        assert clone.item_id == basic_arc.item_id

    def test_roundtrip_preserves_stroke(self, qtbot: object) -> None:  # noqa: ARG002
        """Stroke color and width survive the roundtrip."""
        from PyQt6.QtGui import QColor

        arc = ArcItem(QPointF(10, 20), 50, 45, 90)
        arc.stroke_color = QColor(255, 0, 0)
        arc.stroke_width = 3.5
        clone = ArcItem.from_dict(arc.to_dict())
        assert clone.stroke_color.red() == 255
        assert _approx(clone.stroke_width, 3.5)

    def test_negative_span_roundtrip(self, qtbot: object) -> None:  # noqa: ARG002
        """A CW arc (negative span) preserves its sign through roundtrip."""
        arc = ArcItem(QPointF(0, 0), 50, 90, -135)
        clone = ArcItem.from_dict(arc.to_dict())
        assert _approx(clone.span_deg, -135.0)


class TestArcItemScene:
    def test_can_be_added_and_removed(self, basic_arc: ArcItem) -> None:
        scene = QGraphicsScene()
        scene.addItem(basic_arc)
        assert basic_arc.scene() is scene
        scene.removeItem(basic_arc)
        assert basic_arc.scene() is None

    def test_is_selectable_and_movable(self, basic_arc: ArcItem) -> None:
        from PyQt6.QtWidgets import QGraphicsItem
        flags = basic_arc.flags()
        assert flags & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        assert flags & QGraphicsItem.GraphicsItemFlag.ItemIsMovable

    def test_bounding_rect_contains_arc(self, basic_arc: ArcItem) -> None:
        """The bounding rect must enclose every point along the arc.

        For a CCW semicircle from 0° to 180° centered at the origin, the
        arc spans x ∈ [-r, r] and y ∈ [0, r].  Pen-width inflation is
        allowed but the rect must contain the geometric extents.
        """
        rect = basic_arc.boundingRect()
        # Allow some slack for pen-width inflation in either direction.
        assert rect.left() <= -100.0 + 0.5
        assert rect.right() >= 100.0 - 0.5
        # Y direction: arc sits in y >= 0 in math convention.
        # Qt's arcMoveTo/arcTo use the same convention (CCW from +X).
        # The geometric extents are y ∈ [0, 100], but the bounding rect
        # of QPainterPath may include the full circle's projection.
        # We only assert the rect contains the midpoint (0, 100).
        mid = basic_arc.midpoint()
        assert rect.contains(mid)


class TestArcAnchorPoints:
    def test_arc_anchors_include_center_and_endpoints(
        self, basic_arc: ArcItem
    ) -> None:
        from open_garden_planner.core.measure_snapper import (
            AnchorType,
            get_anchor_points,
        )

        scene = QGraphicsScene()
        scene.addItem(basic_arc)
        anchors = get_anchor_points(basic_arc)
        types = [a.anchor_type for a in anchors]
        assert AnchorType.CENTER in types
        assert types.count(AnchorType.ENDPOINT) == 2


class TestArcRenderedEndpointPrecision:
    """Issue #195: the *rendered* path must terminate exactly on p1 / p3.

    The analytic geometry was always exact; Qt's ``arcMoveTo``/``arcTo`` drifted
    the rendered endpoint by up to a few mm on shallow, large-radius arcs. The
    cubic-Bézier builder (:func:`arc_to_painter_path`) pins the endpoints.
    """

    @pytest.mark.parametrize(
        "p1,p2,p3",
        [
            (QPointF(0, 0), QPointF(50, 20), QPointF(100, 0)),  # gentle
            (QPointF(0, 0), QPointF(-30, 60), QPointF(20, 90)),  # big sweep
            (QPointF(0, 0), QPointF(50, 1), QPointF(100, 0)),  # near-collinear (the bug)
            (QPointF(0, 0), QPointF(40, -15), QPointF(85, -2)),  # clockwise
        ],
    )
    def test_rendered_endpoints_match_clicks(
        self, qtbot: object, p1: QPointF, p2: QPointF, p3: QPointF
    ) -> None:
        result = arc_from_three_points(p1, p2, p3)
        assert result is not None
        center, radius, start_deg, span_deg = result
        arc = ArcItem(
            center=center, radius=radius, start_deg=start_deg, span_deg=span_deg
        )
        path = arc.path()
        first = path.elementAt(0)
        last = path.elementAt(path.elementCount() - 1)
        assert math.hypot(first.x - p1.x(), first.y - p1.y()) < 1e-3
        assert math.hypot(last.x - p3.x(), last.y - p3.y()) < 1e-3

    def test_arc_to_painter_path_endpoints_on_circle(self, qtbot: object) -> None:
        center = QPointF(10, -5)
        radius = 250.0
        path = arc_to_painter_path(center, radius, 30.0, 200.0)
        first = path.elementAt(0)
        last = path.elementAt(path.elementCount() - 1)
        for el in (first, last):
            r = math.hypot(el.x - center.x(), el.y - center.y())
            assert _approx(r, radius, tol=1e-6)

    def test_empty_span_is_single_moveto(self, qtbot: object) -> None:
        path = arc_to_painter_path(QPointF(0, 0), 100.0, 0.0, 0.0)
        assert path.elementCount() == 1


class TestArcThroughPoint:
    """Issue #193: the arc stores a through-point so reshape handles round-trip."""

    def test_default_through_is_angular_midpoint(self, qtbot: object) -> None:
        arc = ArcItem(QPointF(0, 0), 100.0, 0.0, 180.0)
        mid = arc.midpoint()
        assert _approx(arc._through.x(), mid.x())
        assert _approx(arc._through.y(), mid.y())

    def test_through_roundtrips_through_serialization(self, qtbot: object) -> None:
        c, r, sd, sp = arc_from_three_points(
            QPointF(0, 0), QPointF(50, 20), QPointF(100, 0)
        )
        arc = ArcItem(center=c, radius=r, start_deg=sd, span_deg=sp, through=QPointF(50, 20))
        d = arc.to_dict()
        assert "through_x" in d and "through_y" in d
        clone = ArcItem.from_dict(d)
        assert _approx(clone._through.x(), 50.0)
        assert _approx(clone._through.y(), 20.0)

    def test_legacy_file_without_through_derives_midpoint(self, qtbot: object) -> None:
        arc = ArcItem(QPointF(0, 0), 100.0, 0.0, 90.0)
        d = arc.to_dict()
        del d["through_x"]
        del d["through_y"]
        clone = ArcItem.from_dict(d)
        mid = clone._angular_midpoint_local()
        assert _approx(clone._through.x(), mid.x())
        assert _approx(clone._through.y(), mid.y())


class TestArcReshape:
    """Issue #193: dragging a control point recomputes the 3-point arc."""

    def _arc(self) -> ArcItem:
        c, r, sd, sp = arc_from_three_points(
            QPointF(0, 0), QPointF(50, 20), QPointF(100, 0)
        )
        return ArcItem(center=c, radius=r, start_deg=sd, span_deg=sp, through=QPointF(50, 20))

    def test_drag_through_keeps_endpoints(self, qtbot: object) -> None:
        arc = self._arc()
        s0, e0 = arc._start_local(), arc._end_local()
        arc._move_control("arc_through", 0, QPointF(50, 45), False)
        assert math.hypot(arc._start_local().x() - s0.x(), arc._start_local().y() - s0.y()) < 1e-4
        assert math.hypot(arc._end_local().x() - e0.x(), arc._end_local().y() - e0.y()) < 1e-4
        assert math.hypot(arc._through.x() - 50, arc._through.y() - 45) < 1e-9

    def test_drag_start_keeps_end(self, qtbot: object) -> None:
        arc = self._arc()
        e0 = arc._end_local()
        arc._move_control("arc_start", 0, QPointF(-10, 0), False)
        assert math.hypot(arc._start_local().x() - (-10), arc._start_local().y() - 0) < 1e-4
        assert math.hypot(arc._end_local().x() - e0.x(), arc._end_local().y() - e0.y()) < 1e-4

    def test_collinear_drag_is_rejected(self, qtbot: object) -> None:
        arc = self._arc()
        snap = arc._capture_geometry()
        # Drag the through-point onto the start→end chord → no unique circle.
        arc._move_control("arc_through", 0, QPointF(50, 0), False)
        assert arc._capture_geometry() == snap

    def test_capture_restore_roundtrip(self, qtbot: object) -> None:
        arc = self._arc()
        snap = arc._capture_geometry()
        arc._move_control("arc_end", 0, QPointF(110, 30), False)
        assert arc._capture_geometry() != snap
        arc._restore_geometry(snap)
        assert arc._capture_geometry() == snap


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
