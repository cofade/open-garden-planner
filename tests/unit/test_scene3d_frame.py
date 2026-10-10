"""Frames of the 3D pipeline (Phase 17 L1.1, #385): scene ↔ engine, local ↔ scene.

Qt-free. Two mappings, each defined exactly once in ``core/scene3d/frame.py``:

- SCENE (E, N, up) → ENGINE (x = E, y = up, z = −N): determinant +1, so triangle
  winding survives and nothing is mirrored (``ogp-lush-cinematic`` §1 "North").
- ITEM-LOCAL → SCENE: ``scene = T + R(θ)·local``, θ counter-clockwise seen from
  above with north up. ``LocalFrame`` derives T, θ and the local coordinates
  from an item's affine scene transform; the test against real Qt items is
  ``tests/integration/test_scene3d_snapshot.py`` (gate G4).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from open_garden_planner.core.scene3d import Transform, to_engine_frame
from open_garden_planner.core.scene3d import frame as F

ANGLES = [0.0, 17.0, 90.0, 180.0, 213.5, 270.0, 359.5]


def _affine(angle_deg: float, dx: float = 0.0, dy: float = 0.0,
            sx: float = 1.0, sy: float = 1.0) -> tuple[float, float, float, float, float, float]:
    """Qt's affine for ``rotate(angle)`` after ``scale(sx, sy)``, plus a translation:
    x' = m11·x + m21·y + dx, y' = m12·x + m22·y + dy."""
    c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    return (c * sx, s * sx, -s * sy, c * sy, dx, dy)


def _map(m: tuple[float, ...], x: float, y: float) -> tuple[float, float]:
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


# ── scene ↔ engine ────────────────────────────────────────────────────────────


class TestSceneToEngine:
    def test_axes(self) -> None:
        east, north, up = np.eye(3)
        np.testing.assert_array_equal(F.scene_to_engine_vectors(east), [1.0, 0.0, 0.0])
        np.testing.assert_array_equal(F.scene_to_engine_vectors(north), [0.0, 0.0, -1.0])
        np.testing.assert_array_equal(F.scene_to_engine_vectors(up), [0.0, 1.0, 0.0])

    def test_determinant_is_plus_one(self) -> None:
        """A proper rotation, not a reflection: nothing is mirrored."""
        assert np.linalg.det(F.SCENE_TO_ENGINE) == pytest.approx(1.0, abs=1e-15)
        np.testing.assert_array_equal(F.SCENE_TO_ENGINE @ F.SCENE_TO_ENGINE.T, np.eye(3))
        np.testing.assert_array_equal(F.ENGINE_TO_SCENE, F.SCENE_TO_ENGINE.T)

    def test_the_constant_cannot_be_edited_in_place(self) -> None:
        with pytest.raises(ValueError):
            F.SCENE_TO_ENGINE[0, 0] = -1.0

    def test_matrix_and_function_agree(self) -> None:
        rng = np.random.default_rng(385)
        points = rng.uniform(-5000.0, 5000.0, size=(64, 3))
        np.testing.assert_array_equal(F.scene_to_engine_points(points), points @ F.SCENE_TO_ENGINE.T)

    def test_winding_survives(self) -> None:
        """The cross product of a mapped triangle is the mapped cross product — a
        face that points up in the scene points up in the engine."""
        rng = np.random.default_rng(1)
        tri = rng.uniform(-100.0, 100.0, size=(50, 3, 3))
        normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        mapped = F.scene_to_engine_points(tri)
        mapped_normal = np.cross(mapped[:, 1] - mapped[:, 0], mapped[:, 2] - mapped[:, 0])
        np.testing.assert_allclose(mapped_normal, F.scene_to_engine_vectors(normal), atol=1e-9)
        up_facing = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])  # CCW seen from above
        engine = F.scene_to_engine_points(up_facing)
        assert np.cross(engine[1] - engine[0], engine[2] - engine[0])[1] > 0.0  # +y is up

    def test_round_trip_is_exact(self) -> None:
        rng = np.random.default_rng(7)
        points = rng.uniform(-1e5, 1e5, size=(40, 3))
        np.testing.assert_array_equal(F.engine_to_scene_points(F.scene_to_engine_points(points)), points)
        np.testing.assert_array_equal(F.engine_to_scene_vectors(F.scene_to_engine_vectors(points)), points)

    def test_dtype_and_shape_are_kept(self) -> None:
        f32 = np.arange(12, dtype=np.float32).reshape(4, 3)
        out = F.scene_to_engine_points(f32)
        assert out.dtype == np.float32 and out.shape == (4, 3)
        assert F.scene_to_engine_vectors(np.zeros((0, 3), np.float32)).shape == (0, 3)
        assert F.scene_to_engine_points([1.0, 2.0, 3.0]).tolist() == [1.0, 3.0, -2.0]

    def test_input_is_not_modified(self) -> None:
        points = np.array([[1.0, 2.0, 3.0]])
        F.scene_to_engine_points(points)
        assert points.tolist() == [[1.0, 2.0, 3.0]]

    def test_a_non_xyz_array_is_refused(self) -> None:
        with pytest.raises(ValueError, match="last axis"):
            F.scene_to_engine_points(np.zeros((4, 2)))

    def test_legacy_scalar_mapping_agrees(self) -> None:
        """Drift guard: the Qt 3D adapter's scalar ``to_engine_frame`` and the numpy
        mapping are ONE rule until L1.10 deletes the former."""
        rng = np.random.default_rng(3)
        for e, n, u in rng.uniform(-900.0, 900.0, size=(25, 3)):
            assert tuple(F.scene_to_engine_points([e, n, u])) == to_engine_frame(e, n, u)


# ── item-local → scene ────────────────────────────────────────────────────────


class TestPose:
    def test_rotation_is_counter_clockwise_seen_from_above(self) -> None:
        """θ = +90°: local +x (east of the anchor) goes to scene +y (north)."""
        t = Transform(0.0, 0.0, 90.0)
        x, y = F.pose_point(t, 1.0, 0.0)
        assert (x, y) == pytest.approx((0.0, 1.0), abs=1e-15)

    @pytest.mark.parametrize("angle", ANGLES)
    def test_pose_point_is_t_plus_r_local(self, angle: float) -> None:
        t = Transform(1234.5, -678.25, angle, 40.0)
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        x, y = F.pose_point(t, 30.0, -12.5)
        assert x == pytest.approx(1234.5 + c * 30.0 - s * -12.5, abs=1e-9)
        assert y == pytest.approx(-678.25 + s * 30.0 + c * -12.5, abs=1e-9)

    def test_quarter_turns_are_exact(self) -> None:
        """No cos(90°) = 6e-17 dust: a quarter turn maps integers to integers."""
        ring = ((10.0, 0.0), (0.0, 20.0))
        assert F.pose_ring(Transform(0.0, 0.0, 90.0), ring) == [(0.0, 10.0), (-20.0, 0.0)]
        assert F.pose_ring(Transform(0.0, 0.0, 180.0), ring) == [(-10.0, 0.0), (0.0, -20.0)]
        assert F.pose_ring(Transform(0.0, 0.0, 270.0), ring) == [(0.0, -10.0), (20.0, 0.0)]
        assert F.pose_ring(Transform(5.0, 6.0, 0.0), ring) == [(15.0, 6.0), (5.0, 26.0)]

    @pytest.mark.parametrize("angle", ANGLES)
    def test_pose_points_matches_pose_point_and_lifts_by_the_base(self, angle: float) -> None:
        t = Transform(100.0, 200.0, angle, 38.0)
        local = np.array([[30.0, -12.5, 0.0], [0.0, 0.0, 250.0], [-7.0, 9.0, 3.0]], np.float32)
        scene = F.pose_points(t, local)
        assert scene.dtype == np.float64 and scene.shape == (3, 3)
        for row, (lx, ly, lz) in zip(scene, local.tolist(), strict=True):
            x, y = F.pose_point(t, lx, ly)
            assert row == pytest.approx([x, y, lz + 38.0], abs=1e-9)

    @pytest.mark.parametrize("angle", ANGLES)
    def test_engine_pose_is_the_same_map_in_the_engine_frame(self, angle: float) -> None:
        """What L1.2 sets on a Model: position = (E, base, −N), a turn of +θ about
        the engine's +Y. Mapping a local point to the engine frame and then posing
        it there equals posing it in the scene and mapping the result."""
        t = Transform(310.0, -45.5, angle, 12.0)
        pose = F.engine_pose(t)
        assert pose.position == (310.0, 12.0, 45.5)
        assert pose.yaw_deg == angle
        rng = np.random.default_rng(11)
        local = rng.uniform(-300.0, 300.0, size=(20, 3))
        expected = F.scene_to_engine_points(F.pose_points(t, local))
        yaw = math.radians(pose.yaw_deg)
        c, s = math.cos(yaw), math.sin(yaw)
        rotate_y = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])  # right-handed about +Y
        actual = F.scene_to_engine_points(local) @ rotate_y.T + np.array(pose.position)
        np.testing.assert_allclose(actual, expected, atol=1e-9)
        np.testing.assert_allclose(F.engine_model_matrix(t)[:3, :3], rotate_y, atol=1e-12)
        np.testing.assert_array_equal(F.engine_model_matrix(t)[:3, 3], pose.position)
        np.testing.assert_array_equal(F.engine_model_matrix(t)[3], [0.0, 0.0, 0.0, 1.0])


# ── LocalFrame: an affine scene transform → transform + local coordinates ─────


class TestLocalFrame:
    @pytest.mark.parametrize("angle", ANGLES)
    @pytest.mark.parametrize("offset", [(0.0, 0.0), (137.25, -42.5)])
    def test_rigid_transform_round_trips(self, angle: float, offset: tuple[float, float]) -> None:
        m = _affine(angle, *offset)
        anchor = (220.3, 115.95)
        frame = F.local_frame(*m, *anchor)
        assert frame.rigid
        transform = frame.transform()
        assert transform.rotation_deg == pytest.approx(angle, abs=1e-9)
        ax, ay = _map(m, *anchor)
        assert (transform.east_cm, transform.north_cm) == pytest.approx((ax, ay), abs=1e-7)
        for point in [(100.3, 50.7), (340.3, 181.2), anchor]:
            local = frame.local_from_item(*point)
            assert F.pose_point(transform, *local) == pytest.approx(_map(m, *point), abs=1e-6)
            assert frame.local_from_scene(*_map(m, *point)) == pytest.approx(local, abs=1e-6)

    def test_local_coordinates_are_relative_to_the_anchor_and_quantised(self) -> None:
        frame = F.local_frame(*_affine(0.0, 500.0, 600.0), 220.3, 115.95)
        assert frame.local_from_item(100.3, 50.7) == (-120.0, -65.25)  # not -120.00000000000001
        assert frame.local_ring([(100.3, 50.7), (340.3, 181.2)]) == ((-120.0, -65.25), (120.0, 65.25))

    def test_moving_an_item_changes_no_local_coordinate(self) -> None:
        here = F.local_frame(*_affine(17.0, 0.0, 0.0), 10.0, 20.0)
        there = F.local_frame(*_affine(17.0, 912.345, -77.7), 10.0, 20.0)
        points = [(3.3, 4.4), (-50.0, 90.1)]
        assert here.local_ring(points) == there.local_ring(points)
        assert here.transform().rotation_deg == there.transform().rotation_deg

    def test_rotating_an_item_changes_no_local_coordinate(self) -> None:
        points = [(3.3, 4.4), (-50.0, 90.1)]
        rings = {F.local_frame(*_affine(a), 10.0, 20.0).local_ring(points) for a in ANGLES}
        assert len(rings) == 1

    @pytest.mark.parametrize(
        ("label", "matrix"),
        [("scale", _affine(0.0, 5.0, 6.0, sx=2.0, sy=2.0)),
         ("mirror", _affine(0.0, 5.0, 6.0, sx=-1.0, sy=1.0)),
         ("stretch + turn", _affine(30.0, 5.0, 6.0, sx=1.5, sy=0.75)),
         ("shear", (1.0, 0.0, 0.4, 1.0, 5.0, 6.0))],
    )
    def test_a_non_rigid_transform_is_baked_into_the_local_geometry(
        self, label: str, matrix: tuple[float, ...]
    ) -> None:
        """The rule: scale, mirror or shear cannot live in a rigid ``Transform``,
        so the WHOLE linear part goes into the local coordinates and the rotation
        is 0. ``scene = T + local`` still holds exactly."""
        frame = F.local_frame(*matrix, 10.0, 20.0)
        assert not frame.rigid, label
        transform = frame.transform()
        assert transform.rotation_deg == 0.0
        for point in [(0.0, 0.0), (110.0, 20.0), (10.0, 320.0)]:
            local = frame.local_from_item(*point)
            assert F.pose_point(transform, *local) == pytest.approx(_map(matrix, *point), abs=1e-6)
            assert frame.local_from_scene(*_map(matrix, *point)) == pytest.approx(local, abs=1e-6)

    def test_a_mirror_is_not_mistaken_for_a_rotation(self) -> None:
        """det = −1 with orthonormal columns: the tolerance test must look at the
        determinant's sign, not only at the column lengths."""
        frame = F.local_frame(1.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0)
        assert not frame.rigid
        assert frame.local_from_item(3.0, 4.0) == (3.0, -4.0)

    def test_an_unrotatable_shape_keeps_rotation_zero(self) -> None:
        """A circle's footprint does not turn with its item (``item_footprints``
        polygonises it in the scene frame), so its record never carries a rotation."""
        frame = F.local_frame(*_affine(213.5, 40.0, 50.0), 7.0, 8.0, rotatable=False)
        transform = frame.transform(base_cm=3.0)
        assert transform.rotation_deg == 0.0 and transform.base_cm == 3.0
        assert (transform.east_cm, transform.north_cm) == pytest.approx(
            _map(_affine(213.5, 40.0, 50.0), 7.0, 8.0), abs=1e-7)

    def test_float_dust_in_qt_s_matrix_is_still_rigid(self) -> None:
        c, s = math.cos(math.radians(17.0)), math.sin(math.radians(17.0))
        frame = F.local_frame(c + 3e-16, s, -s - 2e-16, c, 0.0, 0.0, 0.0, 0.0)
        assert frame.rigid

    def test_noise_far_below_the_quantum_gives_the_same_record_values(self) -> None:
        a = F.local_frame(*_affine(0.0, 1000.3, 2000.7), 77.7, 33.3)
        b = F.local_frame(*_affine(0.0, 1000.3 + 2e-13, 2000.7 - 2e-13), 77.7, 33.3)
        assert a.transform() == b.transform()
