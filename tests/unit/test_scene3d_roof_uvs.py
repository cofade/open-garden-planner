"""A roof's tiles (#801): the uvs every roof style writes on its tile faces.

The roof shader (``built_detail.vert``, mode 1) lays the canvas's own roof picture by
these uvs, in centimetres, one picture per ``SURFACES["roof_tile"].detail.tile_cm`` (256,
the canvas's ruler). A gable's are the 2D brush's frame exactly — the test computes that
frame the way ``ui/canvas/items/roof_paint.paint_roof_with_ridge`` does, with Qt's own
``QTransform`` — so the roof seen from above is the plan's picture, tile for tile and
mirrored across the ridge as the canvas mirrors it. A hip's faces and a shed's plane run
along their own eave and down their own slope.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform

from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.core.scene3d.builders.buildings import HOUSE_ROOF, SHED_ROOF
from open_garden_planner.core.scene3d.builders.palette import (
    ROOF_TILE,
    ROOF_TILE_CAP,
    SHINGLE,
    SHINGLE_CAP,
)
from open_garden_planner.core.scene3d.builders.roofs import gable_roof, hip_roof, shed_roof
from open_garden_planner.core.scene3d.mesh import Mesh, surface_pieces
from tests.unit.scene3d_builder_cases import polygon_record, rectangle, turned

REGISTRY = production_registry()


def _tile_faces(mesh: Mesh, *colours: tuple[float, float, float, float]) -> np.ndarray:
    """The triangles (t, 3) of ``mesh`` whose first vertex has one of ``colours``."""
    first = mesh.colors[mesh.indices[:, 0]]
    keep = np.zeros(len(first), dtype=bool)
    for colour in colours:
        keep |= np.isclose(first, np.asarray(colour, dtype=np.float32), atol=1e-6).all(axis=1)
    return mesh.indices[keep]


def _brush_uv(point: tuple[float, float], start: np.ndarray, end: np.ndarray) -> tuple[float, float]:
    """What the canvas's roof brush samples at an item point (roof_paint.py): the
    texture point ``T^-1 . p`` of ``translate(mid) . rotate(angle)`` on the left half
    (the side the ridge's left-perpendicular points into) and of the same with
    ``scale(1, -1)`` on the right half."""
    mid = (start + end) / 2.0
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    left = np.array([-(end - start)[1], (end - start)[0]])
    transform = QTransform()
    transform.translate(float(mid[0]), float(mid[1]))
    transform.rotate(angle)
    if float((np.asarray(point) - start) @ left) < 0.0:
        transform.scale(1.0, -1.0)
    inverse, ok = transform.inverted()
    assert ok
    sampled = inverse.map(QPointF(*point))
    return sampled.x(), sampled.y()


RIDGES = {
    "along x": ((-300.0, 0.0), (300.0, 0.0)),
    "off-centre": ((-300.0, 60.0), (300.0, 60.0)),
    "turned 30": tuple(turned(((-300.0, 0.0), (300.0, 0.0)), 30.0)),
}


@pytest.mark.parametrize("ridge_name", sorted(RIDGES))
def test_a_gable_s_tiles_are_the_canvas_s_tiles_on_both_halves(ridge_name: str) -> None:
    """Size, direction and phase: every tile vertex's uv is the 2D brush's texture
    point (cm) - the mirrored half included."""
    ridge = RIDGES[ridge_name]
    footprint = turned(rectangle(600.0, 400.0), 30.0) if ridge_name == "turned 30" else rectangle(600.0, 400.0)
    built = gable_roof(footprint, ridge, 450.0, HOUSE_ROOF)
    assert built is not None
    mesh = built.roof
    tiles = _tile_faces(mesh, ROOF_TILE.linear, ROOF_TILE_CAP.linear)
    start, end = np.asarray(ridge[0]), np.asarray(ridge[1])
    sides = set()
    for vertex in np.unique(tiles):
        point = (float(mesh.positions[vertex, 0]), float(mesh.positions[vertex, 1]))
        expected = _brush_uv(point, start, end)
        assert mesh.uvs[vertex] == pytest.approx(expected, abs=1e-2), (ridge_name, point)
        left = np.array([-(end - start)[1], (end - start)[0]])
        sides.add(float((np.asarray(point) - start) @ left) > 1e-3)
    assert sides == {True, False}, "both halves were checked"


def test_a_gable_s_tiles_meet_at_the_ridge_and_lap_down_both_slopes() -> None:
    built = gable_roof(rectangle(600.0, 400.0), RIDGES["along x"], 450.0, HOUSE_ROOF)
    assert built is not None
    mesh = built.roof
    tiles = _tile_faces(mesh, ROOF_TILE.linear)
    on_ridge = [v for v in np.unique(tiles) if abs(float(mesh.positions[v, 1])) < 1e-3]
    assert on_ridge
    for vertex in on_ridge:   # continuous across the ridge: v = 0 on both slopes, u the same
        assert float(mesh.uvs[vertex, 1]) == pytest.approx(0.0, abs=1e-3)
        assert float(mesh.uvs[vertex, 0]) == pytest.approx(float(mesh.positions[vertex, 0]), abs=1e-3)
    for triangle in tiles:   # v grows down the slope: away from the ridge, and the height falls
        p, uv = mesh.positions[triangle].astype(np.float64), mesh.uvs[triangle].astype(np.float64)
        gradient = _plane_gradient(p[:, :2], uv[:, 1])
        away = np.array([0.0, float(np.sign(p[:, 1].mean()))])
        assert float(gradient @ away) == pytest.approx(1.0)
        z_per_v = _plane_gradient(uv, p[:, 2])
        assert float(z_per_v[1]) < 0.0
        u_gradient = _plane_gradient(p[:, :2], uv[:, 0])   # u: one cm per cm, along the ridge
        assert u_gradient == pytest.approx([1.0, 0.0], abs=1e-6)


def _plane_gradient(points: np.ndarray, values: np.ndarray) -> np.ndarray:
    """The gradient of a linear function over a triangle's three 2D points."""
    a = np.column_stack([points, np.ones(3)])
    coefficients = np.linalg.solve(a, values)
    gradient: np.ndarray = coefficients[:2]
    return gradient


@pytest.mark.parametrize("footprint", [rectangle(800.0, 500.0), rectangle(500.0, 500.0),
                                       turned(rectangle(700.0, 400.0), 17.0)],
                         ids=["rectangle", "square", "turned"])
def test_each_hip_face_runs_along_its_own_eave_and_down_its_own_slope(footprint) -> None:
    built = hip_roof(footprint, 450.0, HOUSE_ROOF)
    assert built is not None
    mesh = built.roof
    tiles = _tile_faces(mesh, ROOF_TILE.linear)
    normals = np.round(mesh.normals[tiles[:, 0]].astype(np.float64), 4)
    faces = {tuple(n) for n in normals}
    assert len(faces) == 4
    top = float(mesh.positions[:, 2].max())
    for normal in faces:
        group = tiles[(normals == np.asarray(normal)).all(axis=1)]
        downslope = np.asarray(normal[:2]) / np.linalg.norm(normal[:2])
        for triangle in group:
            p, uv = mesh.positions[triangle].astype(np.float64), mesh.uvs[triangle].astype(np.float64)
            v_gradient = _plane_gradient(p[:, :2], uv[:, 1])
            u_gradient = _plane_gradient(p[:, :2], uv[:, 0])
            # (float32 positions and a normal rounded to 1e-4: the tolerances)
            assert v_gradient == pytest.approx(downslope, abs=1e-4)          # down this face
            assert float(u_gradient @ downslope) == pytest.approx(0.0, abs=1e-4)   # along its eave
            assert float(np.linalg.norm(u_gradient)) == pytest.approx(1.0, abs=1e-4)   # in cm
        # v = 0 at the face's top: the apex or ridge, where the slab tops out
        highest = group.reshape(-1)[np.argmax(mesh.positions[group.reshape(-1), 2])]
        assert float(mesh.positions[highest, 2]) == pytest.approx(top, abs=1e-3)
        assert float(mesh.uvs[highest, 1]) == pytest.approx(0.0, abs=1e-2)


def test_a_shed_roof_s_tiles_fall_from_its_high_edge() -> None:
    built = shed_roof(rectangle(400.0, 300.0), 300.0, SHED_ROOF)
    assert built is not None
    mesh = built.roof
    tiles = _tile_faces(mesh, SHINGLE.linear)
    assert len(tiles)
    for triangle in tiles:
        p, uv = mesh.positions[triangle].astype(np.float64), mesh.uvs[triangle].astype(np.float64)
        assert _plane_gradient(p[:, :2], uv[:, 1]) == pytest.approx([0.0, -1.0], abs=1e-6)  # high: +y
        assert _plane_gradient(p[:, :2], uv[:, 0]) == pytest.approx([1.0, 0.0], abs=1e-6)
    highest = np.unique(tiles)[np.argmax(mesh.positions[np.unique(tiles), 2])]
    assert float(mesh.uvs[highest, 1]) == pytest.approx(0.0, abs=1e-2)


def test_every_pitched_style_s_tiles_reach_the_engine_with_their_uvs() -> None:
    """Through the production builder: the roof part's tile run carries non-zero uvs
    (a picture laid by all-zero uvs samples ONE texel - a flat slab), its timber run
    none, and the faces still store their winding normals (the faces gate)."""
    ridge = {"ridge": ((-300.0, 0.0), (300.0, 0.0))}
    for style in ("gable", "hip", "shed"):
        for kind in ("HOUSE", "TOOL_SHED"):
            params = {"roof_style": style, **(ridge if kind == "HOUSE" else {})}
            parts = REGISTRY.build(polygon_record(kind, rectangle(600.0, 400.0), 450.0, params=params))
            roof = next(p for p in parts if p.name == "roof")
            roof.validate()
            pieces = {piece.surface: piece for piece in surface_pieces(roof)}
            tile = pieces["roof_tile" if kind == "HOUSE" else "shingle"]
            assert float(np.ptp(tile.mesh.uvs[:, 0])) > 300.0 and float(np.ptp(tile.mesh.uvs[:, 1])) > 100.0
            assert not pieces["wood"].mesh.uvs.any()


def test_shingles_and_tiles_of_a_flat_roof_carry_no_uvs() -> None:
    """A flat roof is a concrete slab: no tile surface, no uvs."""
    parts = REGISTRY.build(polygon_record("HOUSE", rectangle(600.0, 400.0), 300.0))
    roof = next(p for p in parts if p.name == "roof")
    assert {piece.surface for piece in surface_pieces(roof)} <= {"concrete", "stone"}
    assert not roof.mesh.uvs.any()


def test_shingle_colours_are_the_shed_style_s() -> None:
    assert (SHED_ROOF.tile, SHED_ROOF.cap) == (SHINGLE, SHINGLE_CAP)
