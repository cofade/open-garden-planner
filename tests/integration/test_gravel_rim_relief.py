"""The 3D gravel edging follows the actual round 2D rim (PR #645 owner pass).

The oracle is Qt's stroke, independent of the Qt-free relief builder. The
analytical shadow footprint remains the existing square-join, butt-end stroke.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainterPath, QPainterPathStroker

from open_garden_planner.core.scene3d.builders import production_registry, surfaces
from open_garden_planner.core.scene3d.record import MAX_LENGTH_CM
from tests.unit.scene3d_builder_cases import (
    BENT_PATH,
    CLOSED_PATH,
    HAIRPIN_PATH,
    ZIGZAG_PATH,
    line_record,
)


def stroke(points: tuple[tuple[float, float], ...], width: float) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    stroker = QPainterPathStroker()
    stroker.setWidth(width)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stroker.createStroke(path)


def top_triangles(points: tuple[tuple[float, float], ...], width: float) -> np.ndarray:
    record = line_record("PATH", points, None, width=width, style="GRAVEL_PATH")
    (part,) = production_registry().build(record)
    part.validate()
    mesh = part.mesh
    triangles = mesh.positions[mesh.indices.astype(np.int64)].astype(np.float64)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    return triangles[normals[:, 2] > 1e-6, :, :2]


def covers(triangles: np.ndarray, point: tuple[float, float]) -> bool:
    p = np.asarray(point)
    edges = np.roll(triangles, -1, axis=1) - triangles
    gaps = p - triangles
    crosses = edges[..., 0] * gaps[..., 1] - edges[..., 1] * gaps[..., 0]
    return bool(np.any(np.all(crosses >= -1e-5, axis=1) | np.all(crosses <= 1e-5, axis=1)))


@pytest.mark.parametrize("width", [40.0, 100.0, 200.0])
@pytest.mark.parametrize("reverse", [False, True])
def test_round_gravel_outer_corner_and_caps_have_relief(qtbot, width: float, reverse: bool) -> None:
    points = ((-500.0, 0.0), (0.0, 0.0), (0.0, 500.0))
    if reverse:
        points = points[::-1]
    edge = min(surfaces.GRAVEL_EDGE_CM, surfaces.GRAVEL_EDGE_SHARE * width)
    radius = width / 2 - edge / 2
    triangles = top_triangles(points, width)
    outer, inner = stroke(points, width), stroke(points, width - 2 * edge)
    probes = [(radius * math.cos(a), radius * math.sin(a))
              for a in np.linspace(-math.pi / 2, 0, 13)[1:-1]]
    probes += [(-500 - radius, 0), (0, 500 + radius)]
    for point in probes:
        assert outer.contains(QPointF(*point)) and not inner.contains(QPointF(*point))
        assert covers(triangles, point), f"painted round rim has no 3D edging at {point}"


@pytest.mark.parametrize("points", [
    ((-500., 0.), (0., 0.), (0., 500.)),
    ((-500., 0.), (0., 0.), (0., 0.), (0., 500.)),
    ((-500., 0.), (0., 0.), (-499., 20.)),
    ((-5., 0.), (0., 0.), (-4., 2.)),
    ((-200., -200.), (200., 200.), (-200., 200.), (200., -200.)),
    ((-200., -200.), (200., -200.), (200., 200.), (-200., 200.), (-200., -200.)),
    BENT_PATH, CLOSED_PATH, HAIRPIN_PATH, ZIGZAG_PATH,
])
def test_gravel_relief_never_cuts_across_the_inner_texture(qtbot, points) -> None:
    width = 100.0
    edge = min(surfaces.GRAVEL_EDGE_CM, surfaces.GRAVEL_EDGE_SHARE * width)
    triangles = top_triangles(points, width)
    probes = np.concatenate([triangles.reshape(-1, 2), triangles.mean(axis=1)])
    # Five hundredths of a centimetre covers the 0.01 cm arc approximation,
    # integer grid, float32 output and Qt's cubic approximation of a round join;
    # it does not cover the old 13 cm chord across the bend.
    outer = stroke(points, width + 0.1)
    inner = stroke(points, width - 2 * edge - 0.1)
    wrong = [tuple(point) for point in probes
             if not outer.contains(QPointF(*point)) or inner.contains(QPointF(*point))]
    assert not wrong, f"3D edging occupies painted gravel or lawn: {wrong[:5]}"


def test_an_unbounded_gravel_rim_keeps_only_the_painted_ground() -> None:
    # A many-bend trace could expand each corner into hundreds of arc vertices.
    # Reject that work before generating the outline, as other relief does.
    points = np.stack([np.arange(2000), np.arange(2000) % 2], axis=1).astype(float)
    assert surfaces._gravel_rim(points, 100.0, 2.5, 3.0) == []


def test_the_largest_admitted_width_is_refused_by_the_arc_budget() -> None:
    # Record validates stroke widths <=1e6 cm. At that largest admitted value
    # the acos argument differs from 1 by 2e-8 (step ~0.0004), so the preflight
    # remains numerically defined and rejects >15,000 cap vertices. Widths
    # large enough to round the argument to 1 cannot reach a builder.
    record = line_record("PATH", ((-500., 0.), (0., 0.), (0., 500.)), None,
                         width=MAX_LENGTH_CM, style="GRAVEL_PATH")
    assert production_registry().build(record) == ()
