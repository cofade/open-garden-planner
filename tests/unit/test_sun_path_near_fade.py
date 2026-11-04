from __future__ import annotations

import math
from datetime import UTC, date

from open_garden_planner.core.scene3d.sun_path import (
    ARC_KINDS,
    SunPoint,
    compass_mesh,
    day_arc,
    hour_marks,
    key_days,
    sun_path_mesh,
)


def arc_alpha(
    vertex_xz: tuple[float, float],
    dome_center_xz: tuple[float, float],
    camera_xz: tuple[float, float],
) -> float:
    """The camera-relative near-half arc fade function matching overlay.vert (#578)."""
    to_vertex = (vertex_xz[0] - dome_center_xz[0], vertex_xz[1] - dome_center_xz[1])
    to_camera = (camera_xz[0] - dome_center_xz[0], camera_xz[1] - dome_center_xz[1])
    len_cam = math.hypot(*to_camera)
    len_vert = math.hypot(*to_vertex)
    if len_cam <= 1.0 or len_vert <= 1.0:
        return 1.0
    cos_theta = (to_vertex[0] * to_camera[0] + to_vertex[1] * to_camera[1]) / (len_vert * len_cam)
    if cos_theta <= 0.0:
        return 1.0
    return 1.0 * (1.0 - cos_theta) + 0.25 * cos_theta


class TestSunPathNearFade:
    def test_alpha_near_far_and_overhead(self) -> None:
        center = (500.0, 500.0)
        # Camera to the south (positive Y/Z in scene)
        camera = (500.0, 1500.0)

        # 1. Directly between camera and dome centre (near side): alpha is 0.25
        near_vert = (500.0, 800.0)
        assert math.isclose(arc_alpha(near_vert, center, camera), 0.25, abs_tol=1e-5)

        # 2. Opposite side (far side): alpha is 1.0
        far_vert = (500.0, 200.0)
        assert math.isclose(arc_alpha(far_vert, center, camera), 1.0, abs_tol=1e-5)

        # 3. Exactly orthogonal (meridian / equator boundary): alpha is 1.0
        side_vert = (800.0, 500.0)
        assert math.isclose(arc_alpha(side_vert, center, camera), 1.0, abs_tol=1e-5)

        # 4. Smooth intermediate angle (45 degrees near): between 0.25 and 1.0
        mid_vert = (500.0 + 300.0 * math.sqrt(0.5), 500.0 + 300.0 * math.sqrt(0.5))
        mid_alpha = arc_alpha(mid_vert, center, camera)
        assert 0.25 < mid_alpha < 1.0
        expected_mid = 1.0 * (1.0 - math.sqrt(0.5)) + 0.25 * math.sqrt(0.5)
        assert math.isclose(mid_alpha, expected_mid, abs_tol=1e-5)

        # 5. Camera directly overhead (within 1 cm of dome center): alpha remains 1.0
        overhead_cam = (500.0, 500.5)
        assert math.isclose(arc_alpha(near_vert, center, overhead_cam), 1.0, abs_tol=1e-5)

    def test_sun_path_mesh_marks_arcs_in_uv0(self) -> None:
        center = (500.0, 500.0)
        radius = 800.0
        lat, lon = 52.52, 13.405
        plan_date = date(2026, 6, 21)
        days = key_days(plan_date)
        arcs = tuple(day_arc(lat, lon, days[kind], UTC, kind) for kind in ARC_KINDS)
        marks = hour_marks(arcs[0], UTC)
        sun_pt = SunPoint(arcs[0].segments[0][0].utc, 45.0, 180.0)

        # Generate mesh with arcs, hour beads, and sun ball
        mesh = sun_path_mesh(arcs, center, radius, hour_marks=marks, sun=sun_pt)
        assert mesh.vertex_count > 0

        # Arc tube vertices must carry UV0.x == 1.0 and UV0.y == radius
        assert (mesh.uvs[:, 0] == 1.0).any()
        # Beads or sun ball vertices must carry UV0.x == 0.0
        assert (mesh.uvs[:, 0] == 0.0).any()

        # Compass rose vertices must carry UV0.x == 0.0 (never fade)
        compass = compass_mesh(center, radius)
        assert compass.vertex_count > 0
        assert (compass.uvs[:, 0] == 0.0).all()
