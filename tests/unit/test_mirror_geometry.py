"""Unit tests for mirror reflection helpers and the item builder (US-B4)."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsRectItem

from open_garden_planner.core.cad_geometry import (
    arc_from_three_points,
    reflect_angle_deg,
    reflect_point,
    snap_point_to_axis_step,
)
from open_garden_planner.core.mirror_geometry import build_mirrored_item
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    BezierItem,
    CircleItem,
    EllipseItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)


def _approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def _approx_pt(p: QPointF, x: float, y: float, tol: float = 1e-6) -> bool:
    return _approx(p.x(), x, tol) and _approx(p.y(), y, tol)


# Common axes
_VERTICAL = (QPointF(100, 0), QPointF(100, 50))  # x = 100
_HORIZONTAL = (QPointF(0, 40), QPointF(20, 40))  # y = 40
_DIAGONAL = (QPointF(0, 0), QPointF(10, 10))  # line y = x


class TestReflectPoint:
    def test_across_vertical_line(self) -> None:
        r = reflect_point(QPointF(30, 5), *_VERTICAL)
        assert _approx_pt(r, 170, 5)  # 2*100 - 30 = 170, y unchanged

    def test_across_horizontal_line(self) -> None:
        r = reflect_point(QPointF(7, 10), *_HORIZONTAL)
        assert _approx_pt(r, 7, 70)  # 2*40 - 10 = 70, x unchanged

    def test_across_diagonal_swaps_coordinates(self) -> None:
        r = reflect_point(QPointF(3, 8), *_DIAGONAL)
        assert _approx_pt(r, 8, 3)

    def test_point_on_axis_is_fixed(self) -> None:
        r = reflect_point(QPointF(100, 25), *_VERTICAL)
        assert _approx_pt(r, 100, 25)

    def test_degenerate_axis_returns_point(self) -> None:
        r = reflect_point(QPointF(5, 6), QPointF(1, 1), QPointF(1, 1))
        assert _approx_pt(r, 5, 6)


class TestReflectAngle:
    def test_vertical_axis(self) -> None:
        # φ = 90°, θ -> 180 - θ
        assert _approx(reflect_angle_deg(30.0, *_VERTICAL), 150.0)

    def test_horizontal_axis(self) -> None:
        # φ = 0°, θ -> -θ (mod 360)
        assert _approx(reflect_angle_deg(30.0, *_HORIZONTAL), 330.0)

    def test_result_is_normalised(self) -> None:
        v = reflect_angle_deg(200.0, *_HORIZONTAL)
        assert 0.0 <= v < 360.0


class TestSnapAxisStep:
    def test_snaps_near_horizontal(self) -> None:
        s = snap_point_to_axis_step(QPointF(0, 0), QPointF(10, 1))
        assert _approx(s.y(), 0.0, 1e-6)
        assert _approx(s.x(), math.hypot(10, 1), 1e-6)

    def test_snaps_near_45(self) -> None:
        s = snap_point_to_axis_step(QPointF(0, 0), QPointF(10, 10))
        assert _approx_pt(s, 10, 10, 1e-9)

    def test_zero_length_returns_target(self) -> None:
        s = snap_point_to_axis_step(QPointF(2, 2), QPointF(2, 2))
        assert _approx_pt(s, 2, 2)


@pytest.fixture()
def _qt(qtbot: object) -> object:  # noqa: ARG001 — ensures a QApplication exists
    return qtbot


class TestBuildMirroredPolyline:
    def test_vertices_reflected(self, _qt: object) -> None:
        pl = PolylineItem(points=[QPointF(10, 0), QPointF(30, 0), QPointF(30, 40)])
        clone = build_mirrored_item(pl, *_VERTICAL)
        assert isinstance(clone, PolylineItem)
        expected = [(190, 0), (170, 0), (170, 40)]
        for p, (x, y) in zip(clone.points, expected, strict=True):
            scene_pt = clone.mapToScene(p)
            assert _approx_pt(scene_pt, x, y)


class TestBuildMirroredPolygon:
    def test_vertices_reflected(self, _qt: object) -> None:
        poly = PolygonItem(
            vertices=[QPointF(0, 0), QPointF(40, 0), QPointF(40, 30)]
        )
        clone = build_mirrored_item(poly, *_VERTICAL)
        assert isinstance(clone, PolygonItem)
        got = {
            (round(clone.mapToScene(clone.polygon().at(i)).x(), 6),
             round(clone.mapToScene(clone.polygon().at(i)).y(), 6))
            for i in range(clone.polygon().count())
        }
        assert got == {(200.0, 0.0), (160.0, 0.0), (160.0, 30.0)}


class TestBuildMirroredCircle:
    def test_center_reflected_radius_kept(self, _qt: object) -> None:
        c = CircleItem(50, 50, 12)
        clone = build_mirrored_item(c, *_VERTICAL)
        assert isinstance(clone, CircleItem)
        assert _approx(clone.radius, 12)
        assert _approx_pt(clone.mapToScene(clone.center), 150, 50)


class TestBuildMirroredRectangle:
    def test_corners_match_reflected_set(self, _qt: object) -> None:
        rect = RectangleItem(10, 20, 40, 30)
        clone = build_mirrored_item(rect, *_VERTICAL)
        assert isinstance(clone, RectangleItem)
        r = rect.rect()
        corners = [
            QPointF(r.left(), r.top()), QPointF(r.right(), r.top()),
            QPointF(r.right(), r.bottom()), QPointF(r.left(), r.bottom()),
        ]
        expected = {
            (round(reflect_point(rect.mapToScene(c), *_VERTICAL).x(), 4),
             round(reflect_point(rect.mapToScene(c), *_VERTICAL).y(), 4))
            for c in corners
        }
        cr = clone.rect()
        clone_corners = [
            QPointF(cr.left(), cr.top()), QPointF(cr.right(), cr.top()),
            QPointF(cr.right(), cr.bottom()), QPointF(cr.left(), cr.bottom()),
        ]
        got = {
            (round(clone.mapToScene(c).x(), 4), round(clone.mapToScene(c).y(), 4))
            for c in clone_corners
        }
        assert got == expected

    def test_rotated_rectangle_flips_angle_and_centre(self, _qt: object) -> None:
        rect = RectangleItem(0, 0, 40, 20)  # centre (20, 10)
        rect._apply_rotation(30.0)
        clone = build_mirrored_item(rect, *_VERTICAL)
        assert isinstance(clone, RectangleItem)
        # φ = 90° (vertical axis) → reflected angle = 2·90 − 30 = 150.
        assert clone.rotation_angle == pytest.approx(150.0)
        # Centre reflects across x = 100: (20, 10) → (180, 10).
        assert _approx_pt(clone.mapToScene(clone.rect().center()), 180, 10, 1e-4)


class TestBuildMirroredEllipse:
    def test_center_reflected(self, _qt: object) -> None:
        e = EllipseItem(10, 10, 60, 20)  # center (40, 20)
        clone = build_mirrored_item(e, *_VERTICAL)
        assert isinstance(clone, EllipseItem)
        assert _approx_pt(clone.mapToScene(clone.rect().center()), 160, 20)


class TestBuildMirroredArc:
    def test_endpoints_reflected_and_stays_arc(self, _qt: object) -> None:
        result = arc_from_three_points(
            QPointF(0, 0), QPointF(50, 30), QPointF(100, 0)
        )
        assert result is not None
        center, radius, start_deg, span_deg = result
        arc = ArcItem(
            center=center, radius=radius, start_deg=start_deg, span_deg=span_deg,
            through=QPointF(50, 30),
        )
        clone = build_mirrored_item(arc, *_VERTICAL)
        assert isinstance(clone, ArcItem)
        # start/end of the original reflect onto the clone's start/end.
        exp_start = reflect_point(arc.start_point(), *_VERTICAL)
        exp_end = reflect_point(arc.end_point(), *_VERTICAL)
        assert _approx_pt(clone.start_point(), exp_start.x(), exp_start.y(), 1e-4)
        assert _approx_pt(clone.end_point(), exp_end.x(), exp_end.y(), 1e-4)


class TestBuildMirroredBezier:
    def test_all_points_reflected(self, _qt: object) -> None:
        bez = BezierItem(
            anchors=[QPointF(0, 0), QPointF(100, 50)],
            handles_in=[QPointF(0, 0), QPointF(70, 60)],
            handles_out=[QPointF(30, 20), QPointF(100, 50)],
        )
        clone = build_mirrored_item(bez, *_VERTICAL)
        assert isinstance(clone, BezierItem)
        for src, dst in zip(bez.anchors, clone.anchors, strict=True):
            exp = reflect_point(bez.mapToScene(src), *_VERTICAL)
            assert _approx_pt(clone.mapToScene(dst), exp.x(), exp.y())


class TestBuildMirroredUnsupported:
    def test_plain_item_returns_none(self, _qt: object) -> None:
        assert build_mirrored_item(QGraphicsRectItem(0, 0, 10, 10), *_VERTICAL) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
