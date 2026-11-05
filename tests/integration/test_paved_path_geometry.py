"""Tests for paved path ends/bends and 3D selection outline agreement (issue #726)."""

import math
from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.shadow_geometry import (
    polyline_bevel_footprint,
)
from open_garden_planner.ui.canvas.footprints import item_footprints
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem


def test_paved_path_shadow_uses_flat_cap_and_bevel_join(qtbot: object) -> None:
    """PolylineItem._paint_shadow for PAVED_PATH uses FlatCap and BevelJoin."""
    points = [QPointF(0.0, 0.0), QPointF(100.0, 0.0), QPointF(100.0, 100.0)]
    paved = PolylineItem(points, object_type=ObjectType.PATH, path_fence_style=PathFenceStyle.PAVED_PATH)
    assert paved._path_fence_style == PathFenceStyle.PAVED_PATH

    captured_pens = []
    mock_painter = MagicMock(spec=QPainter)
    def capture_set_pen(pen: QPen) -> None:
        captured_pens.append(QPen(pen))
    mock_painter.setPen.side_effect = capture_set_pen

    paved._paint_shadow(mock_painter)

    # The shadow pen for paved path must be FlatCap + BevelJoin
    assert len(captured_pens) >= 1
    shadow_pen = captured_pens[0]
    assert shadow_pen.capStyle() == Qt.PenCapStyle.FlatCap
    assert shadow_pen.joinStyle() == Qt.PenJoinStyle.BevelJoin


def test_gravel_path_shadow_keeps_round_cap_and_round_join(qtbot: object) -> None:
    """Gravel and other round path styles keep RoundCap and RoundJoin for drop shadows."""
    points = [QPointF(0.0, 0.0), QPointF(100.0, 0.0)]
    gravel = PolylineItem(points, object_type=ObjectType.PATH, path_fence_style=PathFenceStyle.GRAVEL_PATH)

    captured_pens = []
    mock_painter = MagicMock(spec=QPainter)
    def capture_set_pen(pen: QPen) -> None:
        captured_pens.append(QPen(pen))
    mock_painter.setPen.side_effect = capture_set_pen

    gravel._paint_shadow(mock_painter)

    assert len(captured_pens) >= 1
    shadow_pen = captured_pens[0]
    assert shadow_pen.capStyle() == Qt.PenCapStyle.RoundCap
    assert shadow_pen.joinStyle() == Qt.PenJoinStyle.RoundJoin


def test_paved_path_2d_paint_no_pixels_past_flat_end(qtbot: object) -> None:
    """2D painted paved path on a straight line has no painted pixels beyond the flat ends."""
    # Line from x=50 to x=150 at y=50, width=40. Ends are at x=50 and x=150.
    points = [QPointF(50.0, 50.0), QPointF(150.0, 50.0)]
    paved = PolylineItem(points, object_type=ObjectType.PATH, path_fence_style=PathFenceStyle.PAVED_PATH)
    pen = paved.pen()
    pen.setWidthF(40.0)
    paved.setPen(pen)

    img = QImage(200, 100, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(img)
    try:
        from open_garden_planner.ui.canvas.items.path_style_paint import PathStylePaint
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        paint = PathStylePaint([QPointF(50.0, 50.0), QPointF(150.0, 50.0)], paved.pen(), paved.path())
        paint.paint(painter, PathFenceStyle.PAVED_PATH)
    finally:
        painter.end()

    # Any pixel with x < 49 or x > 151 should be transparent (no rounded lobe extending past ends)
    for y in range(100):
        for x in range(0, 48):
            pixel = img.pixelColor(x, y)
            assert pixel.alpha() == 0, f"Unexpected pixel at ({x}, {y}) before start of paved path"
        for x in range(152, 200):
            pixel = img.pixelColor(x, y)
            assert pixel.alpha() == 0, f"Unexpected pixel at ({x}, {y}) past end of paved path"


def test_polyline_bevel_footprint_agrees_with_3d_kerb_mesh() -> None:
    """3D footprint for paved path agrees with _offset_line kerb chords at 90 deg and 45 deg."""
    pts_90 = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]
    width = 80.0
    footprint_90 = polyline_bevel_footprint(pts_90, width)
    assert len(footprint_90) == 1
    poly = footprint_90[0]

    # In 90 deg bend, outer bend bevel chord connects (100, -40) to (140, 0)
    # The footprint vertices must contain the bevel points
    poly_pts = set(poly)
    assert (100.0, -40.0) in poly_pts
    assert (140.0, 0.0) in poly_pts
    # And must NOT contain the squared-off clipper miter corner (which is at > 116, -40)
    for x, y in poly:
        if y == -40.0:
            assert x <= 100.001, f"Found vertex {x}, {y} past the bevel chord corner!"

    # In 45 deg bend:
    pts_45 = [(0.0, 0.0), (100.0, 0.0), (100.0 + 100.0 * math.cos(math.pi / 4), 100.0 * math.sin(math.pi / 4))]
    footprint_45 = polyline_bevel_footprint(pts_45, width)
    assert len(footprint_45) == 1
    # Check that item_footprints for a PAVED_PATH uses polyline_bevel_footprint
    paved_item = PolylineItem([QPointF(x, y) for x, y in pts_90], object_type=ObjectType.PATH, path_fence_style=PathFenceStyle.PAVED_PATH)
    p_pen = paved_item.pen()
    p_pen.setWidthF(width)
    paved_item.setPen(p_pen)
    fps = item_footprints(paved_item)
    assert len(fps) == 1
    assert set(fps[0]) == set(poly)
