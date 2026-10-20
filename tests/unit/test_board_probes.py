"""The Beauty Board's instruments on synthetic frames (Phase 17 L1.4, #385).

``scripts/board_probes.py`` turns pixels into the numbers the looks' gates are
judged by. Here every instrument measures a frame whose answer is KNOWN — painted
with the arithmetic below, not rendered — and each has a positive control: a frame
that is wrong in the way the instrument exists to catch.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
from scripts import board_probes as P

from open_garden_planner.core.scene3d import sun_direction_scene
from open_garden_planner.core.shadow_geometry import compute_scene_shadows

#: What the L0 spike measured, frozen when L1.10 deleted it (its provenance field says how).
SPIKE = json.loads((Path(__file__).resolve().parents[1] / "data" / "l0_spike_reference.json")
                   .read_text(encoding="utf-8"))

SIZE = (480, 270)
MEADOW = np.array([86.0, 150.0, 60.0])
SHADE = MEADOW * 0.45
FOOTPRINT = [(-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0)]
HEIGHT = 200.0


def test_the_module_needs_nothing_but_numpy() -> None:
    import ast
    from pathlib import Path

    tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
    imported = {node.module.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module}
    imported |= {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names}
    assert imported <= {"__future__", "math", "collections", "dataclasses", "typing", "numpy"}


# ── frame statistics ─────────────────────────────────────────────────────────


def test_frame_statistics_are_the_spikes() -> None:
    """The same numbers for the same frame as the L0 spike's probes gave (frozen when
    L1.10 deleted the spike)."""
    spike = SPIKE["probes"]
    frozen = spike["noise_rng7_90x160"]
    noise = np.random.default_rng(7).integers(0, 256, size=(90, 160, 3)).astype(np.float64)
    assert P.isolated_dark_pixels(noise) == frozen["isolated_dark_pixels"]
    assert (
        spike["speckle_max_luma"], spike["speckle_min_neighbours"]) == (P.SPECKLE_MAX_LUMA, P.SPECKLE_MIN_NEIGHBOURS)
    luma = P.luma(noise)
    assert float(luma.mean()) == pytest.approx(frozen["luma_mean"], abs=1e-9)
    assert np.allclose(luma[0], frozen["luma_first_row"], atol=1e-9)
    assert hashlib.sha256(np.round(luma, 9).tobytes()).hexdigest() == frozen["luma_sha256_9dp"]


def test_a_clean_frame_has_no_speckles_and_a_speckled_one_is_counted() -> None:
    frame = np.full((60, 80, 3), 170.0)
    assert P.frame_stats(frame) == {"isolated_dark_px": 0, "clipped_pct": 0.0, "mean_luma": 170.0,
                                    "mean_luminance": 0.40198}
    for row, col in ((10, 10), (20, 33), (41, 70)):
        frame[row, col] = 12.0                       # a near-black dot on a lit surface
    frame[30:36, 40:52] = 255.0                      # a clipped highlight
    stats = P.frame_stats(frame)
    assert stats["isolated_dark_px"] == 3
    assert stats["clipped_pct"] == pytest.approx(100.0 * 72 / 4800, abs=1e-3)
    frame[50:56, 5:25] = 12.0                        # a dark AREA is not 120 speckles:
    assert P.isolated_dark_pixels(frame) == 3 + 4    # only its four corners have lit surroundings


def test_luminance_is_linear_light_and_luma_is_not() -> None:
    """Gate G3 says LUMINANCE: a frame of code 128 has a fifth of the luminance of a
    white one and half its luma — the two must not be mixed up in a "quarter" gate."""
    white, grey = np.full((4, 4, 3), 255.0), np.full((4, 4, 3), 128.0)
    assert float(P.luminance(white).mean()) == pytest.approx(1.0)
    assert float(P.luminance(grey).mean()) == pytest.approx(0.2158, abs=1e-4)
    assert float(P.luma(grey).mean() / P.luma(white).mean()) == pytest.approx(0.502, abs=1e-3)
    assert float(P.luminance(np.array([[[255.0, 0.0, 0.0]]])).mean()) == pytest.approx(0.2126)


# ── the camera ───────────────────────────────────────────────────────────────

CAMERA = P.Pinhole(eye=(900.0, -700.0, 650.0), target=(250.0, 250.0, 0.0), fov_deg=40.0, size=SIZE)


def test_the_target_lands_in_the_middle_and_east_is_right_of_a_camera_that_looks_north() -> None:
    x, y, front = CAMERA.project([CAMERA.target])
    assert (x[0], y[0]) == pytest.approx((SIZE[0] / 2.0, SIZE[1] / 2.0)) and front[0]
    north = P.Pinhole(eye=(0.0, -1000.0, 200.0), target=(0.0, 0.0, 200.0), fov_deg=50.0, size=SIZE)
    x, y, _front = north.project([(100.0, 0.0, 200.0), (0.0, 0.0, 300.0), (0.0, -2000.0, 200.0)])
    assert x[0] > SIZE[0] / 2.0, "east is to the right"
    assert y[1] < SIZE[1] / 2.0, "up is up the image"
    assert not north.project([(0.0, -2000.0, 200.0)])[2][0], "a point behind the camera is not seen"


def test_projection_and_ray_are_inverse_of_each_other() -> None:
    points = np.array([(120.0, 300.0, 0.0), (-200.0, 80.0, 0.0), (400.0, 600.0, 150.0)])
    x, y, _front = CAMERA.project(points)
    for point, px, py in zip(points, x, y, strict=True):
        ray = CAMERA.rays(np.array(px), np.array(py))
        towards = point - np.asarray(CAMERA.eye)
        assert np.allclose(ray / np.linalg.norm(ray), towards / np.linalg.norm(towards), atol=1e-9)


def test_the_vertical_field_of_view_is_the_images_height() -> None:
    level = P.Pinhole(eye=(0.0, 0.0, 100.0), target=(0.0, 1000.0, 100.0), fov_deg=60.0, size=SIZE)
    assert level.elevation_deg(SIZE[0] / 2.0, 0.0) == pytest.approx(30.0)
    assert level.elevation_deg(SIZE[0] / 2.0, SIZE[1]) == pytest.approx(-30.0)
    assert level.horizon_row() == pytest.approx(SIZE[1] / 2.0)
    assert level.bearing_deg(SIZE[0] / 2.0, SIZE[1] / 2.0) == pytest.approx(0.0, abs=1e-9)
    east = P.Pinhole(eye=(0.0, 0.0, 100.0), target=(1000.0, 0.0, 100.0), fov_deg=60.0, size=SIZE)
    assert east.bearing_deg(SIZE[0] / 2.0, SIZE[1] / 2.0) == pytest.approx(90.0)
    down = P.Pinhole(eye=(0.0, 0.0, 500.0), target=(0.0, 1000.0, 0.0), fov_deg=60.0, size=SIZE)
    assert down.horizon_row() < SIZE[1] / 2.0, "a camera that looks down sees the horizon higher up"


def test_a_camera_for_a_larger_grab_is_the_same_camera() -> None:
    """A grab is in device pixels: at 150 % it is 1.5x the logical size."""
    bigger = CAMERA.scaled((720, 405))
    x, y, _front = CAMERA.project([(100.0, 200.0, 0.0)])
    bx, by, _front = bigger.project([(100.0, 200.0, 0.0)])
    assert (bx[0], by[0]) == pytest.approx((x[0] * 1.5, y[0] * 1.5))


def test_polygons_and_hulls() -> None:
    xs, ys = np.meshgrid(np.arange(-95.0, 100.0, 10.0), np.arange(-95.0, 100.0, 10.0))
    assert int(P.polygon_mask(xs, ys, FOOTPRINT).sum()) == 100
    ring = [(-90.0, -90.0), (90.0, -90.0), (90.0, 90.0), (-90.0, 90.0)]
    assert int(P.polygons_mask(xs, ys, [ring, FOOTPRINT]).sum()) == 18 * 18 - 100, "even-odd"
    hull = P.convex_hull([(0, 0), (4, 0), (4, 3), (0, 3), (2, 1), (1, 2), (4, 0)])
    assert sorted(hull) == [(0.0, 0.0), (0.0, 3.0), (4.0, 0.0), (4.0, 3.0)]


# ── gate G2's instrument ─────────────────────────────────────────────────────


def _painted(camera: P.Pinhole, shadow: list, *, shift: tuple[float, float] = (0.0, 0.0),
             with_box: bool = True) -> np.ndarray:
    """A frame painted with the camera's own arithmetic: meadow, the shadow polygons
    (moved by ``shift`` cm on the ground), the box in front of what it hides."""
    width, height = camera.size
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    rays = camera.rays(cols, rows)
    eye = np.asarray(camera.eye)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(rays[..., 2] < -1e-9, -eye[2] / rays[..., 2], np.nan)
    east, north = eye[0] + t * rays[..., 0], eye[1] + t * rays[..., 1]
    frame = np.empty((height, width, 3))
    frame[:] = (150.0, 190.0, 230.0)                 # sky where no ground is hit
    ground = np.isfinite(t)
    frame[ground] = MEADOW
    in_shadow = ground & P.polygons_mask(east - shift[0], north - shift[1], shadow)
    frame[in_shadow] = SHADE
    if with_box:
        frame[P.polygon_mask(cols, rows, P.box_silhouette(camera, FOOTPRINT, HEIGHT))] = (200.0, 30.0, 30.0)
    return frame


def _judge(frame: np.ndarray, shadow: list, **kwargs: float) -> dict:
    return P.shadow_iou(frame, CAMERA, FOOTPRINT, HEIGHT, shadow,
                        region=(-250.0, -250.0, 900.0, 900.0),
                        lit_reference=(-240.0, -240.0, -120.0, -120.0), **kwargs)


#: The frame size of the looks' render tier: the instrument's own floor depends on it.
#: A shadow painted exactly where the 2D geometry puts it scores 0.959-0.972 at 480x270
#: (3.5 cm of ground per pixel) and 0.980-0.987 at 960x540 — one pixel of boundary.
BOARD = P.Pinhole(CAMERA.eye, CAMERA.target, CAMERA.fov_deg, (960, 540))


@pytest.mark.parametrize("elevation", [15.0, 35.0, 60.0])
def test_a_shadow_painted_where_the_2d_geometry_puts_it_scores_one(elevation: float) -> None:
    shadow = compute_scene_shadows([(FOOTPRINT, HEIGHT)], elevation, 225.0)
    assert _judge(_painted(BOARD, shadow), shadow)["iou"] >= 0.975, "the instrument's floor"
    result = _judge(_painted(CAMERA, shadow), shadow)
    assert result["iou"] >= 0.95, result
    assert result["lit_luma"] == pytest.approx(float(P.luma(MEADOW)), abs=0.5)
    assert result["centroid_measured_cm"] == pytest.approx(result["centroid_analytic_cm"], abs=3.0)
    east, north, _up = sun_direction_scene(elevation, 225.0)
    assert result["centroid_analytic_cm"][0] > 0 and result["centroid_analytic_cm"][1] > 0, \
        "a sun in the south-west throws the shadow north-east"
    assert east < 0 and north < 0


@pytest.mark.parametrize(("shift", "at_most"), [((40.0, 0.0), 0.80), ((0.0, -60.0), 0.75),
                                                ((120.0, 120.0), 0.45)])
def test_a_shadow_in_the_wrong_place_scores_low(shift: tuple[float, float], at_most: float) -> None:
    """The positive control: the gate's 0.85 is out of reach for a shadow 40 cm off."""
    shadow = compute_scene_shadows([(FOOTPRINT, HEIGHT)], 35.0, 225.0)
    assert _judge(_painted(CAMERA, shadow, shift=shift), shadow)["iou"] < at_most


def test_a_shadow_for_another_azimuth_scores_low_and_no_shadow_scores_nothing() -> None:
    right = compute_scene_shadows([(FOOTPRINT, HEIGHT)], 35.0, 225.0)
    mirrored = compute_scene_shadows([(FOOTPRINT, HEIGHT)], 35.0, 135.0)
    assert _judge(_painted(CAMERA, mirrored), right)["iou"] < 0.2
    none = _judge(_painted(CAMERA, []), right)
    assert none["iou"] < 0.2


def test_ground_behind_the_caster_is_not_judged() -> None:
    """What the box hides cannot be measured: it is in neither mask — with the box
    painted and the instrument told about it, the IoU does not drop."""
    shadow = compute_scene_shadows([(FOOTPRINT, HEIGHT)], 35.0, 225.0)
    behind = P.Pinhole(eye=(-150.0, -1000.0, 700.0), target=(150.0, 150.0, 0.0), fov_deg=40.0,
                       size=(960, 540))
    frame = _painted(behind, shadow)
    result = P.shadow_iou(frame, behind, FOOTPRINT, HEIGHT, shadow,
                          region=(-250.0, -250.0, 700.0, 700.0),
                          lit_reference=(-240.0, 200.0, -120.0, 320.0))
    assert result["iou"] >= 0.97 and result["analytic_cells"] > 1000, result
    assert result["analytic_cells"] < int(P.polygons_mask(
        *np.meshgrid(np.arange(-249.0, 700.0, 2.0), np.arange(-249.0, 700.0, 2.0)), shadow).sum())


# ── gate G4's instrument ─────────────────────────────────────────────────────


def _sky(camera: P.Pinhole, sun_azimuth: float, sun_elevation: float) -> np.ndarray:
    width, height = camera.size
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    rays = camera.rays(cols, rows)
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)
    sun = np.asarray(sun_direction_scene(sun_elevation, sun_azimuth))
    angle = np.degrees(np.arccos(np.clip(rays @ sun, -1.0, 1.0)))
    frame = np.empty((height, width, 3))
    frame[:] = (120.0, 160.0, 215.0)
    frame[rays[..., 2] < 0.0] = (70.0, 110.0, 60.0)
    glow = np.clip(1.0 - angle / 6.0, 0.0, 1.0)[..., None]
    return frame + glow * (np.array([255.0, 235.0, 190.0]) - frame)


@pytest.mark.parametrize("sun_azimuth", [90.0, 180.0, 270.0, 301.5])
@pytest.mark.parametrize("offset", [-25.0, 25.0])
def test_the_disc_is_found_off_centre_at_its_bearing(sun_azimuth: float, offset: float) -> None:
    look = math.radians(sun_azimuth + offset)
    camera = P.Pinhole(eye=(0.0, 0.0, 160.0),
                       target=(math.sin(look) * 1000.0, math.cos(look) * 1000.0,
                               160.0 + 1000.0 * math.tan(math.radians(14.0))),
                       fov_deg=70.0, size=SIZE)
    found = P.sun_disc(_sky(camera, sun_azimuth, 12.0), camera)
    assert found["found"]
    assert abs(P.bearing_error_deg(found["bearing_deg"], sun_azimuth)) < 0.5, found
    assert found["elevation_deg"] == pytest.approx(12.0, abs=0.5)
    wrong = P.sun_disc(_sky(camera, sun_azimuth + 20.0, 12.0), camera)
    assert abs(P.bearing_error_deg(wrong["bearing_deg"], sun_azimuth)) > 15.0, "the control"


def test_a_sky_without_a_disc_is_not_a_measurement() -> None:
    camera = P.Pinhole(eye=(0.0, 0.0, 160.0), target=(0.0, 1000.0, 400.0), fov_deg=70.0, size=SIZE)
    assert P.sun_disc(_sky(camera, 180.0, 12.0), camera)["found"] is False
    assert P.bearing_error_deg(359.0, 1.0) == pytest.approx(-2.0)
    assert P.bearing_error_deg(2.0, 358.0) == pytest.approx(4.0)


# ── gate G5's instrument ─────────────────────────────────────────────────────


def _horizon(sky: float, ground: float, line: float | None = None) -> tuple[np.ndarray, P.Pinhole]:
    camera = P.Pinhole(eye=(0.0, 0.0, 165.0), target=(0.0, 1000.0, 165.0), fov_deg=40.0, size=SIZE)
    frame = np.empty((SIZE[1], SIZE[0], 3))
    horizon = int(round(camera.horizon_row()))
    frame[:horizon] = sky
    frame[horizon:] = ground
    if line is not None:
        frame[horizon - 1:horizon + 1] = line
    return frame, camera


def test_fog_that_meets_the_sky_has_no_step_and_a_cliff_is_measured() -> None:
    frame, camera = _horizon(140.0, 141.5)
    result = P.horizon_step(frame, camera)
    assert result["step"] == pytest.approx(1.5) and result["dip"] == result["ridge"] == 0.0
    assert (result["sky_luma"], result["ground_luma"]) == (140.0, 141.5)
    frame, camera = _horizon(200.0, 115.5)           # the meadow meets the sky in ONE row
    assert P.horizon_step(frame, camera)["step"] == pytest.approx(84.5)


def test_a_soft_transition_is_not_a_cliff() -> None:
    """The same 84.5 luma spread over the half degree below the horizon — what fog
    does — is a few luma per row."""
    frame, camera = _horizon(200.0, 200.0)
    horizon = int(round(camera.horizon_row()))
    rows = int(round(0.5 * P.horizon_step(frame, camera)["rows_per_degree"]))
    for index in range(rows):
        frame[horizon + index] = 200.0 - 84.5 * (index + 1) / rows
    frame[horizon + rows:] = 115.5
    result = P.horizon_step(frame, camera)
    assert result["step"] == pytest.approx(84.5 / rows, abs=0.01) and result["step"] < 30.0
    assert result["dip"] == result["ridge"] == 0.0


def test_a_thin_dark_line_at_the_horizon_is_a_dip_and_a_bright_one_a_ridge() -> None:
    frame, camera = _horizon(140.0, 140.0, line=130.0)
    result = P.horizon_step(frame, camera)
    assert result["dip"] == pytest.approx(10.0) and result["ridge"] == 0.0
    assert result["step"] == pytest.approx(10.0), "a line has two edges of its own height"
    frame, camera = _horizon(20.0, 60.0, line=85.0)  # a fog brighter than both: the night's
    result = P.horizon_step(frame, camera)
    assert result["ridge"] == pytest.approx(25.0) and result["dip"] == 0.0


def test_the_columns_keep_a_sun_out_of_the_horizon_bands() -> None:
    frame, camera = _horizon(140.0, 140.0)
    frame[:, :120] = 255.0
    assert P.horizon_step(frame, camera, columns=(0.3, 1.0))["step"] == pytest.approx(0.0)
    assert P.horizon_step(frame, camera)["sky_luma"] > 160.0


def test_a_horizon_outside_the_frame_judges_nothing() -> None:
    down = P.Pinhole(eye=(0.0, 0.0, 800.0), target=(0.0, 300.0, 0.0), fov_deg=30.0, size=SIZE)
    assert P.horizon_step(np.full((SIZE[1], SIZE[0], 3), 90.0), down)["judged_rows"] == 0


# ── north is up ──────────────────────────────────────────────────────────────


def test_the_orientation_of_a_top_down_frame() -> None:
    plan = np.zeros((60, 90))
    plan[5:20, 10:30] = 1.0          # something in the north-west …
    plan[40:55, 60:85] = 1.0         # … and something larger in the south-east
    plan[8:12, 70:80] = 1.0
    assert P.orientation_scores(plan, plan)["ok"] is True
    assert P.orientation_scores(plan, plan)["ncc"]["identity"] == pytest.approx(1.0)
    for name, wrong in (("flip_v", plan[::-1]), ("flip_h", plan[:, ::-1]),
                        ("flip_both", plan[::-1, ::-1])):
        result = P.orientation_scores(wrong, plan)
        assert result["ok"] is False and result["best"] == name
    assert P.ncc(np.ones((4, 4)), plan[:4, :4]) == 0.0, "a flat image correlates with nothing"


# ── the hue at the horizon (reported) ────────────────────────────────────────


def test_colour_difference_is_cie76() -> None:
    assert P.delta_e76((120.0, 120.0, 120.0), (120.0, 120.0, 120.0)) == 0.0
    white, black = P.srgb_to_lab((255.0, 255.0, 255.0)), P.srgb_to_lab((0.0, 0.0, 0.0))
    assert white == pytest.approx([100.0, 0.0, 0.0], abs=0.05)
    assert black == pytest.approx([0.0, 0.0, 0.0], abs=0.05)
    assert P.delta_e76((255.0, 255.0, 255.0), (0.0, 0.0, 0.0)) == pytest.approx(100.0, abs=0.1)


def test_the_horizon_reports_a_hue_seam_that_luma_cannot_see() -> None:
    """A grey-blue sky over a lime meadow of almost the same luma: the luma rows see a
    step of a few codes, the hue difference is large — the review's noon horizon."""
    frame, camera = _horizon(0.0, 0.0)
    horizon = int(round(camera.horizon_row()))
    frame[:horizon] = (150.0, 165.0, 185.0)
    frame[horizon:] = (150.0, 170.0, 60.0)
    result = P.horizon_step(frame, camera)
    assert result["step"] < 6.0 and result["delta_e"] > 40.0, result
    same, _camera = _horizon(140.0, 140.0)
    assert P.horizon_step(same, camera)["delta_e"] == pytest.approx(0.0, abs=1e-6)


# ── the plan rectangle meets the meadow ──────────────────────────────────────


def _ground_frame(camera: P.Pinhole, step: float, gradient: float) -> np.ndarray:
    """A frame of flat ground whose luma rises ``gradient`` per cm eastwards everywhere
    (the sky's sheen changing with the angle) and jumps by ``step`` at the line east = 0
    (the plan to the east); the sky above."""
    cols, rows = camera.size
    xs, ys = np.meshgrid(np.arange(cols) + 0.5, np.arange(rows) + 0.5)
    rays = camera.rays(xs, ys)
    eye = np.asarray(camera.eye)
    down = rays[..., 2] < 0
    t = np.where(down, -eye[2] / np.where(down, rays[..., 2], -1.0), 0.0)
    east = eye[0] + t * rays[..., 0]
    level = 110.0 + gradient * east + np.where(east >= 0.0, step, 0.0)
    frame = np.full((rows, cols, 3), 200.0)
    frame[down] = level[down][:, None]
    return frame


def test_the_plan_edge_step_is_the_jump_at_the_edge_not_the_gradient() -> None:
    camera = P.Pinhole(eye=(0.0, -700.0, 165.0), target=(0.0, 800.0, 0.0), fov_deg=40.0, size=SIZE)
    along = [500.0, 650.0, 800.0, 950.0, 1100.0]
    smooth = P.plan_edge_step(_ground_frame(camera, 0.0, 0.014), camera, axis="east", at=0.0,
                              along=along)
    assert smooth["stations"] == 5 and abs(smooth["step"]) < 0.3, smooth
    # two band means 2 m apart would have read the gradient as a step: +2.8 luma here
    darker = P.plan_edge_step(_ground_frame(camera, -6.0, 0.014), camera, axis="east", at=0.0,
                              along=along)
    assert darker["step"] == pytest.approx(-6.0, abs=0.4), "the positive control"
    behind = P.Pinhole(eye=(0.0, 3000.0, 165.0), target=(0.0, 5000.0, 0.0), fov_deg=40.0, size=SIZE)
    assert P.plan_edge_step(np.zeros((SIZE[1], SIZE[0], 3)), behind, axis="east", at=0.0,
                            along=along)["step"] is None, "ground behind the camera: no number"


# ── aliasing of thin repeated geometry ───────────────────────────────────────


def test_a_supersampled_reference_is_the_box_filter_in_linear_light() -> None:
    large = np.zeros((4, 4, 3))
    large[0::2, 0::2] = 255.0                    # one white sample in four
    down = P.downsample(large, 2)
    assert down.shape == (2, 2, 3)
    assert down[0, 0, 0] == pytest.approx(255.0 * (1.055 * 0.25 ** (1 / 2.4) - 0.055), abs=0.01)


def test_pickets_that_alias_are_measured_against_their_resolved_texture() -> None:
    """Thin dark/light stripes: resolved, they average to a mid grey; aliased, each
    pixel lands on a stripe and the frame is a hard pattern. The error against the
    supersampled reference is the measure; a frame equal to its reference scores 0."""
    rows, cols = 60, 80
    meadow = np.zeros((rows, cols, 3)) + MEADOW
    stripes = meadow.copy()
    stripes[20:40, ::2] = 30.0                   # aliased: dark pickets on every other column
    stripes[20:40, 1::2] = 200.0
    large = np.zeros((2 * rows, 2 * cols, 3)) + MEADOW
    large[40:80, ::2] = 30.0                     # the same pickets at twice the size …
    large[40:80, 1::2] = 200.0
    reference = P.downsample(large, 2)           # … filtered down: resolved, a mid grey
    aliased = P.thin_geometry_moire(stripes, meadow, reference)
    resolved = P.thin_geometry_moire(reference, meadow, reference)
    assert resolved["alias_error"] == 0.0
    assert aliased["alias_error"] > 40.0 and aliased["dark_share"] == pytest.approx(0.5)
    assert aliased["pixels"] == resolved["pixels"] == 20 * cols
    assert P.thin_geometry_moire(meadow, meadow) == {"pixels": 0, "dark_share": 0.0,
                                                     "laplacian": 0.0, "alias_error": None}
