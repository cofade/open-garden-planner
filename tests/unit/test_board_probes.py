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
from typing import Any

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


def test_the_ground_luminance_reads_only_below_the_horizon() -> None:
    """L7 (#391): the mood order is judged on the garden. A brighter SKY moves the frame's
    mean but not the ground's; a darker GROUND moves the ground's (the positive control)."""
    camera = P.Pinhole(eye=(0.0, 0.0, 160.0), target=(0.0, 1000.0, 300.0), fov_deg=60.0, size=SIZE)
    frame = _sky(camera, 180.0, 12.0)
    base = P.ground_luminance(frame, camera)
    brighter_sky = frame.copy()
    horizon = int(camera.horizon_row())
    brighter_sky[:horizon] = np.minimum(brighter_sky[:horizon] + 60.0, 255.0)
    assert P.ground_luminance(brighter_sky, camera) == base
    assert P.frame_stats(brighter_sky)["mean_luminance"] > P.frame_stats(frame)["mean_luminance"]
    darker_ground = frame.copy()
    darker_ground[horizon + 3:] *= 0.7
    assert P.ground_luminance(darker_ground, camera) < 0.75 * base


def test_a_low_suns_disc_beats_a_brighter_warm_horizon_band() -> None:
    """#717: the old "bright AND warm" score locked onto the horizon band at an 8 degree
    sun. A plateau of at least 20 white pixels is the disc's own signature; the band is
    deliberately brighter-scored than the disc here, so only the plateau can find it."""
    azimuth, elevation = 180.0, 8.0
    look = math.radians(azimuth)
    camera = P.Pinhole(
        eye=(0.0, 0.0, 160.0),
        target=(math.sin(look) * 1000.0, math.cos(look) * 1000.0,
                160.0 + 1000.0 * math.tan(math.radians(elevation))),
        fov_deg=70.0, size=SIZE)
    width, height = camera.size
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    rays = camera.rays(cols, rows)
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)
    frame = np.empty((height, width, 3))
    frame[:] = (120.0, 160.0, 215.0)
    frame[rays[..., 2] < 0.0] = (70.0, 110.0, 60.0)
    elevation_deg = np.degrees(np.arcsin(np.clip(rays[..., 2], -1.0, 1.0)))
    band = (elevation_deg > 0.2) & (elevation_deg < 1.2)
    frame[band] = (255.0, 200.0, 120.0)          # brighter-scored than the disc
    sun = np.asarray(sun_direction_scene(elevation, azimuth))
    angle = np.degrees(np.arccos(np.clip(rays @ sun, -1.0, 1.0)))
    disc = angle < 1.0
    frame[disc] = (255.0, 255.0, 255.0)
    assert int(disc.sum()) >= 20
    found = P.sun_disc(frame, camera)
    assert found["found"]
    assert abs(P.bearing_error_deg(found["bearing_deg"], azimuth)) < 0.25, found
    assert found["elevation_deg"] == pytest.approx(elevation, abs=0.25), found


def test_a_warm_clipped_disc_is_still_the_discs_own_plateau() -> None:
    """#716: the atmosphere's 6° disc core read (255, 255, 243) once the profile dimmed the
    sky round a low sun (master's (255, 255, 252) clipped blue too, from the brighter sky
    behind it). A warm core clips red and green first, so "every channel >= 250" found no
    plateau, and the warm fallback locked 0.49° low onto the haze band below. A clipped core
    is luma >= 250; the band (luma ~206) stays out."""
    azimuth, elevation = 180.0, 6.0
    look = math.radians(azimuth)
    camera = P.Pinhole(
        eye=(0.0, 0.0, 160.0),
        target=(math.sin(look) * 1000.0, math.cos(look) * 1000.0,
                160.0 + 1000.0 * math.tan(math.radians(elevation + 2.0))),
        fov_deg=70.0, size=SIZE)
    width, height = camera.size
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    rays = camera.rays(cols, rows)
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)
    frame = np.empty((height, width, 3))
    frame[:] = (120.0, 160.0, 215.0)
    frame[rays[..., 2] < 0.0] = (70.0, 110.0, 60.0)
    elevation_deg = np.degrees(np.arcsin(np.clip(rays[..., 2], -1.0, 1.0)))
    frame[(elevation_deg > 0.2) & (elevation_deg < 5.5)] = (255.0, 200.0, 120.0)
    sun = np.asarray(sun_direction_scene(elevation, azimuth))
    disc = np.degrees(np.arccos(np.clip(rays @ sun, -1.0, 1.0))) < 1.0
    frame[disc] = (255.0, 255.0, 243.0)
    assert int(disc.sum()) >= 20 and not np.all(frame[disc] >= 250.0)
    found = P.sun_disc(frame, camera)
    assert found["found"] and found.get("plateau_px", 0) >= 20, found
    assert abs(P.bearing_error_deg(found["bearing_deg"], azimuth)) < 0.25, found
    assert found["elevation_deg"] == pytest.approx(elevation, abs=0.25), found


def test_two_white_blobs_do_not_make_a_sun_between_them() -> None:
    """#717 review: the white path took the centroid of EVERY white pixel, so two
    clouds at 160° and 200° read as a sun at 180°. It takes the largest connected
    plateau instead; two equal blobs report one of them, never their midpoint."""
    azimuth, elevation = 180.0, 12.0
    look = math.radians(azimuth)
    camera = P.Pinhole(
        eye=(0.0, 0.0, 160.0),
        target=(math.sin(look) * 1000.0, math.cos(look) * 1000.0,
                160.0 + 1000.0 * math.tan(math.radians(elevation))),
        fov_deg=70.0, size=SIZE)
    width, height = camera.size
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    rays = camera.rays(cols, rows)
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)
    frame = np.empty((height, width, 3))
    frame[:] = (120.0, 160.0, 215.0)
    frame[rays[..., 2] < 0.0] = (70.0, 110.0, 60.0)
    for blob_bearing in (160.0, 200.0):
        blob = np.asarray(sun_direction_scene(elevation, blob_bearing))
        frame[np.degrees(np.arccos(np.clip(rays @ blob, -1.0, 1.0))) < 1.2] = 255.0
    found = P.sun_disc(frame, camera)
    assert found["found"]
    assert min(abs(P.bearing_error_deg(found["bearing_deg"], bearing))
               for bearing in (160.0, 200.0)) < 5.0, found
    assert abs(P.bearing_error_deg(found["bearing_deg"], 180.0)) > 10.0, found


def test_a_white_streak_does_not_hide_the_disc() -> None:
    """#717 review: a clipped white band is the largest component but not a disc. The
    finder takes the largest COMPACT component, so the band cannot hide the sun."""
    azimuth, elevation = 180.0, 12.0
    look = math.radians(azimuth)
    camera = P.Pinhole(
        eye=(0.0, 0.0, 160.0),
        target=(math.sin(look) * 1000.0, math.cos(look) * 1000.0,
                160.0 + 1000.0 * math.tan(math.radians(elevation))),
        fov_deg=70.0, size=SIZE)
    width, height = camera.size
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    rays = camera.rays(cols, rows)
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)
    frame = np.empty((height, width, 3))
    frame[:] = (120.0, 160.0, 215.0)
    frame[rays[..., 2] < 0.0] = (70.0, 110.0, 60.0)
    frame[10:470, 20:50] = 255.0                      # a clipped white band
    sun = np.asarray(sun_direction_scene(elevation, azimuth))
    disc = np.degrees(np.arccos(np.clip(rays @ sun, -1.0, 1.0))) < 1.2
    frame[disc] = 255.0
    assert int(disc.sum()) >= 20
    found = P.sun_disc(frame, camera)
    assert found["found"]
    assert abs(P.bearing_error_deg(found["bearing_deg"], azimuth)) < 5.0, found


def test_a_sky_without_an_away_band_is_not_measured() -> None:
    """#695 review: "no measurement" and "a clean sky" must not be the same value; the
    gate fails closed."""
    camera = P.Pinhole(eye=(0.0, 0.0, 160.0), target=(0.0, 1000.0, 400.0),
                       fov_deg=70.0, size=SIZE)
    result = P.sun_dip(_sky(camera, 180.0, 0.4), camera, 180.0, away_deg=(80.0, 90.0))
    assert result["measured"] is False


def test_a_black_set_sun_is_a_dip_and_a_sky_without_it_is_not() -> None:
    """#695: the board's dusk camera had the sun behind a poplar, so a black sun with a
    dark halo survived three reviews. A sky-only frame near the sun's bearing measures it;
    the same sky without the disc does not."""
    azimuth, elevation = 270.0, 0.4
    look = math.radians(azimuth)
    camera = P.Pinhole(
        eye=(0.0, 0.0, 160.0),
        target=(math.sin(look) * 1000.0, math.cos(look) * 1000.0,
                160.0 + 1000.0 * math.tan(math.radians(3.0))),
        fov_deg=70.0, size=SIZE)
    width, height = camera.size
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    rays = camera.rays(cols, rows)
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)
    sun = np.asarray(sun_direction_scene(elevation, azimuth))
    angle = np.degrees(np.arccos(np.clip(rays @ sun, -1.0, 1.0)))
    frame = np.empty((height, width, 3))
    frame[:] = (120.0, 160.0, 215.0)
    glow = np.clip(1.0 - angle / 6.0, 0.0, 1.0)[..., None]
    frame += glow * (np.array([255.0, 235.0, 190.0]) - frame)
    control = P.sun_dip(frame, camera, azimuth, sun_elevation_deg=elevation)
    assert control["dip_luma"] > -10.0, control          # a glow is not a dip
    assert control["measured"] is True, control
    # one stray dark pixel is not a black sun: the 2nd percentile ignores it
    speck = frame.copy()
    speck[135, 240] = 0.0
    stray = P.sun_dip(speck, camera, azimuth, sun_elevation_deg=elevation)
    assert stray["dip_luma"] > -10.0, stray
    black = frame.copy()
    black[angle < 1.0] = 0.0
    found = P.sun_dip(black, camera, azimuth, sun_elevation_deg=elevation)
    assert found["dip_luma"] < -50.0, found
    assert found["measured"] is True, found
    assert found["elevation_deg"] == pytest.approx(elevation, abs=1.0), found
    # a dark cumulus 6 degrees above the sun is weather, not a black sun
    sky_elevation = np.degrees(np.arcsin(np.clip(rays[..., 2], -1.0, 1.0)))
    cloudy = frame.copy()
    cloudy[(sky_elevation > 5.5) & (sky_elevation < 7.5)] = 20.0
    ignored = P.sun_dip(cloudy, camera, azimuth, sun_elevation_deg=elevation)
    assert ignored["dip_luma"] > -10.0, ignored


def _elevation_sky(camera: P.Pinhole, luma_of: Any) -> tuple[np.ndarray, np.ndarray]:
    """A grey frame whose value is a function of each pixel's WORLD elevation."""
    width, height = camera.size
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    rays = camera.rays(cols, rows)
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)
    elevation = np.degrees(np.arcsin(np.clip(rays[..., 2], -1.0, 1.0)))
    value = np.clip(luma_of(elevation), 0.0, 255.0)
    return np.repeat(value[..., None], 3, axis=2), elevation


def _band_camera(bearing: float = 120.0) -> P.Pinhole:
    look = math.radians(bearing)
    return P.Pinhole(eye=(0.0, 0.0, 160.0),
                     target=(math.sin(look) * 1000.0, math.cos(look) * 1000.0,
                             160.0 + 1000.0 * math.tan(math.radians(10.0))),
                     fov_deg=40.0, size=SIZE)


def test_the_sky_profile_bins_by_world_elevation_not_by_row() -> None:
    """#716/#719 (PF-L3D-19): a sky that only rises toward the horizon reads as rising in
    every band, and a band's value is the sky's AT that elevation — off-axis pixels of one
    row of a pitched camera sit higher, so a row mean would blur the bands together."""
    camera = _band_camera()
    frame, elevation = _elevation_sky(camera, lambda e: 200.0 - 4.0 * np.maximum(e, 0.0))
    profile = P.sky_profile(frame, camera, 120.0, half_width_deg=4.0)
    assert P.profile_at(profile, 3.0) == pytest.approx(188.0, abs=1.0)
    assert P.profile_at(profile, 10.0) == pytest.approx(160.0, abs=1.0)
    assert P.profile_at(profile, 40.0) is None, "outside the frame: not measured"
    assert P.profile_mean(profile, 6.0, 15.0, key="luma") == pytest.approx(158.0, abs=1.0)
    clean = P.horizon_inversion(profile)
    assert clean["measured"] is True and clean["inversion_luma"] == 0.0, clean
    # the image row through 25° in the middle spans several degrees across the frame:
    # its mean is not the sky at 25° (the profile's band is)
    row = int(np.argmin(np.abs(elevation[:, SIZE[0] // 2] - 25.0)))
    assert float(np.ptp(elevation[row])) > 2.0
    assert abs(float(frame[row, :, 0].mean()) - 100.0) > 2.0
    assert P.profile_at(P.sky_profile(frame, camera, 120.0, highest_deg=30.0), 25.0) == pytest.approx(
        100.0, abs=1.0)


def test_a_bright_band_above_the_horizon_is_an_inversion_and_a_deck_step_is_measured() -> None:
    """#716's symptom: the sky peaks at 4-5° and darkens toward 0.5°. #719's: a bright band
    under a darker deck — band (3°) minus deck (10°)."""
    camera = _band_camera()
    peaked, _ = _elevation_sky(camera, lambda e: np.where(e < 4.5, 190.0 + 8.0 * e, 226.0 - 2.0 * (e - 4.5)))
    found = P.horizon_inversion(P.sky_profile(peaked, camera, 120.0))
    assert found["inversion_luma"] == pytest.approx(32.0, abs=2.5), found
    assert found["above_deg"] == pytest.approx(4.5, abs=0.5) and found["at_deg"] == pytest.approx(0.5)
    deck, _ = _elevation_sky(camera, lambda e: np.where(e < 6.0, 180.0, 130.0))
    profile = P.sky_profile(deck, camera, 120.0)
    assert P.profile_at(profile, 3.0) - P.profile_at(profile, 10.0) == pytest.approx(50.0)
    # nothing measured is not a pass
    empty = P.horizon_inversion({"elevation_deg": [], "luma": [], "luminance": [], "count": []})
    assert empty["measured"] is False


def test_the_sky_profile_leaves_the_disc_out() -> None:
    """The sun's disc is not the sky's brightness: within the given radius of the sun its
    pixels are not counted, so a white core cannot pull two skies' means together."""
    camera = _band_camera(300.0)
    frame, _ = _elevation_sky(camera, lambda e: np.full_like(e, 120.0))
    cols, rows = np.meshgrid(np.arange(SIZE[0]) + 0.5, np.arange(SIZE[1]) + 0.5)
    rays = camera.rays(cols, rows)
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)
    sun = np.asarray(sun_direction_scene(8.0, 300.0))
    frame[np.degrees(np.arccos(np.clip(rays @ sun, -1.0, 1.0))) < 1.5] = 255.0
    with_disc = P.sky_profile(frame, camera, 300.0)
    without = P.sky_profile(frame, camera, 300.0, sun=(300.0, 8.0), sun_radius_deg=3.0)
    assert P.profile_mean(with_disc, 7.0, 9.0) > P.profile_mean(without, 7.0, 9.0)
    assert P.profile_mean(without, 7.0, 9.0) == pytest.approx(
        float(P.luminance(np.array([120.0] * 3))), rel=1e-4)


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


def _ground_frame(camera: P.Pinhole, step: float, gradient: float, line: float = 0.0,
                  line_cm: float = 4.0) -> np.ndarray:
    """A frame of flat ground whose luma rises ``gradient`` per cm eastwards everywhere
    (the sky's sheen changing with the angle) and jumps by ``step`` at the line east = 0
    (the plan to the east); ``line`` luma more on a strip ``line_cm`` wide on that line;
    the sky above."""
    cols, rows = camera.size
    xs, ys = np.meshgrid(np.arange(cols) + 0.5, np.arange(rows) + 0.5)
    rays = camera.rays(xs, ys)
    eye = np.asarray(camera.eye)
    down = rays[..., 2] < 0
    t = np.where(down, -eye[2] / np.where(down, rays[..., 2], -1.0), 0.0)
    east = eye[0] + t * rays[..., 0]
    level = (110.0 + gradient * east + np.where(east >= 0.0, step, 0.0)
             + np.where(np.abs(east) < line_cm / 2.0, line, 0.0))
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


def test_the_plan_edge_line_is_what_the_fits_cannot_see() -> None:
    """3D review of #388: ambient occlusion drew a +-14 luma line along every plan edge
    while the meadow lay 5 cm under the plan, and the fitted step read 0.45. ``line``
    reads it; a gradient, a clean step and the edge's own anti-aliasing do not."""
    camera = P.Pinhole(eye=(0.0, -700.0, 165.0), target=(0.0, 800.0, 0.0), fov_deg=40.0, size=SIZE)
    along = [500.0, 650.0, 800.0, 950.0, 1100.0]
    smooth = P.plan_edge_step(_ground_frame(camera, 0.0, 0.014), camera, axis="east", at=0.0,
                              along=along)
    assert smooth["line"] < 0.5, smooth
    stepped = P.plan_edge_step(_ground_frame(camera, -1.0, 0.014), camera, axis="east", at=0.0,
                               along=along)
    assert stepped["line"] <= 1.1, stepped
    for amplitude in (-14.0, 6.0):
        lined = P.plan_edge_step(_ground_frame(camera, 0.0, 0.014, line=amplitude), camera,
                                 axis="east", at=0.0, along=along)
        assert lined["line"] == pytest.approx(abs(amplitude), abs=1.0), lined
        assert abs(lined["step"]) < 1.0, "the fitted step does not see it"


# ── aliasing of thin repeated geometry ───────────────────────────────────────


def test_a_supersampled_reference_is_the_box_filter_in_linear_light() -> None:
    large = np.zeros((4, 4, 3))
    large[0::2, 0::2] = 255.0                    # one white sample in four
    down = P.downsample(large, 2)
    assert down.shape == (2, 2, 3)
    assert down[0, 0, 0] == pytest.approx(255.0 * (1.055 * 0.25 ** (1 / 2.4) - 0.055), abs=0.01)


def test_outer_row_step_sees_a_one_sided_cliff_without_cancelling_the_other_side() -> None:
    rgb = np.full((30, 100, 3), 100.0)
    assert P.outer_row_step(rgb)["step"] == 0.0
    rgb[15:, :18] += 20
    rgb[15:, -18:] -= 20
    result = P.outer_row_step(rgb)
    assert result["columns_per_side"] == 18
    assert result["step"] == result["left_step"] == result["right_step"] == 20.0
    rgb[:, 18:82] = 255.0
    assert P.outer_row_step(rgb)["step"] == 20.0, "central plan contents are outside the probe"


def test_outer_row_step_records_the_excluded_viewport_border() -> None:
    rgb = np.full((30, 100, 3), 100.0)
    rgb[-1] = 130.0
    result = P.outer_row_step(rgb)
    assert result["step"] == 0.0
    assert result["rows_excluded_each_edge"] == 2
    assert result["full_step"] == result["border_step"] == 30.0


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


# ── a long shadow's edge and the streaks in it (#734) ────────────────────────

#: An oblique camera over a shadow edge along ``north = EDGE_NORTH`` (the shadow north
#: of it), the edge's stations from about 8 m to 49 m deep — the board's ``--stairs``.
EDGE_CAMERA = P.Pinhole(eye=(1300.0, -900.0, 450.0), target=(-600.0, 300.0, 0.0), fov_deg=46.0,
                        size=(960, 540))
EDGE_NORTH = -130.0


def _ground(camera: P.Pinhole) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(east, north) of the ground under every pixel centre, and which pixels hit it."""
    width, height = camera.size
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    rays = camera.rays(cols, rows)
    eye = np.asarray(camera.eye)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(rays[..., 2] < -1e-9, -eye[2] / rays[..., 2], np.nan)
    return eye[0] + t * rays[..., 0], eye[1] + t * rays[..., 1], np.isfinite(t)


def _edge_frame(edge_north: np.ndarray | float, *, supersample: int = 2) -> np.ndarray:
    """The meadow with a shadow north of ``edge_north`` (a function of east, or a
    constant), anti-aliased by ``supersample`` x ``supersample`` sub-pixels."""
    width, height = EDGE_CAMERA.size
    big = P.Pinhole(EDGE_CAMERA.eye, EDGE_CAMERA.target, EDGE_CAMERA.fov_deg,
                    (width * supersample, height * supersample))
    east, north, ground = _ground(big)
    line = edge_north(east) if callable(edge_north) else edge_north
    frame = np.empty(east.shape + (3,))
    frame[:] = (150.0, 190.0, 230.0)
    frame[ground] = MEADOW
    frame[ground & (north > line)] = SHADE
    return frame.reshape(height, supersample, width, supersample, 3).mean(axis=(1, 3))


def _trace(frame: np.ndarray, line_north: float = EDGE_NORTH) -> dict:
    return P.shadow_edge_trace(frame, EDGE_CAMERA, (-4000.0, line_north), (1800.0, line_north),
                               (0.0, -1.0), half_width_cm=60.0)


def test_a_straight_shadow_edge_where_the_line_is_has_no_staircase() -> None:
    trace = _trace(_edge_frame(EDGE_NORTH))
    rows = [row for row in P.edge_staircase(trace) if "wobble_px" in row]
    assert {tuple(row["depth_m"]) for row in rows} >= {(0.0, 10.0), (10.0, 20.0), (20.0, 40.0)}
    for row in rows:
        assert abs(row["offset_cm"]) < 1.5, row
        # the instrument's floor on a 3x-supersampled frame: 0.28 px (0.56 cm) near
        assert row["wobble_px"] < 0.4 and row["jump_px"] < 0.45, row


def test_a_shadow_that_ends_short_reads_its_offset_and_still_no_staircase() -> None:
    """A constant offset is bias (or the caster's own shape), not steps: it is reported
    and detrended away. Negative: the shadow ends short of the line (positive: past it,
    toward the lit side)."""
    trace = _trace(_edge_frame(EDGE_NORTH + 15.0))
    for row in (row for row in P.edge_staircase(trace) if "wobble_px" in row):
        assert row["offset_cm"] == pytest.approx(-15.0, abs=1.5), row
        assert row["wobble_px"] < 0.4, row


def test_a_stepped_edge_is_measured_as_steps_of_its_own_size() -> None:
    """The positive control: a sawtooth staircase (20 cm deep, a riser every 50 cm along
    the edge, a ramp between) reads as about 20 cm of wobble, in pixels as the camera
    shows it — larger near, smaller far — and its risers are jumps. From 10 m out the
    steps are a few pixels deep and the pixels soften them: what is measured is what
    the screen shows (at 960 x 540: 14.7 cm at 10-20 m, less further out)."""
    def stepped(east: np.ndarray) -> np.ndarray:
        return EDGE_NORTH + 20.0 * (np.mod(east, 50.0) / 50.0)
    straight = P.edge_staircase(_trace(_edge_frame(EDGE_NORTH)))
    steps = P.edge_staircase(_trace(_edge_frame(stepped)))
    rows = [(flat, row) for flat, row in zip(straight, steps, strict=True)
            if "wobble_px" in row and row["depth_m"][1] <= 40.0]
    assert len(rows) == 3
    for flat, row in rows:
        if row["depth_m"][1] <= 10.0:
            assert row["wobble_cm"] == pytest.approx(18.0, abs=3.0), row  # p95 - p5 of a ramp
        assert row["wobble_cm"] > 8.0, row
        assert row["wobble_px"] > 3.0 * flat["wobble_px"] + 0.5, (flat, row)
        assert row["jump_px"] > flat["jump_px"] + 0.3, (flat, row)
    near, far = rows[0][1], rows[-1][1]
    assert near["wobble_px"] > far["wobble_px"], "the same steps look smaller further away"


def test_a_station_whose_line_leaves_the_frame_is_not_judged() -> None:
    trace = _trace(_edge_frame(EDGE_NORTH))
    assert trace["valid"].any() and not trace["valid"].all()
    kept = P.edge_staircase(trace, keep=np.zeros(len(trace["valid"]), dtype=bool))
    assert all("wobble_px" not in row and row["stations"] == 0 for row in kept)
    assert trace["valid"].any(), "the trace is the caller's: judging it leaves it as it was"


def _striped(lit_slits: np.ndarray | None) -> np.ndarray:
    """The meadow in a fence's shadow south of ``north = 0`` (to -500 cm), with slits of
    light 4 cm wide every 12 cm along east — every one of them (``lit_slits`` None) or
    those the mask lets through (indexed by slit)."""
    width, height = EDGE_CAMERA.size
    east, north, ground = _ground(P.Pinhole(EDGE_CAMERA.eye, EDGE_CAMERA.target,
                                            EDGE_CAMERA.fov_deg, (width * 2, height * 2)))
    frame = np.empty(east.shape + (3,))
    frame[:] = (150.0, 190.0, 230.0)
    frame[ground] = MEADOW
    band = ground & (north < 0.0) & (north > -500.0)
    slot = np.floor(np.nan_to_num(east) / 12.0).astype(np.int64)
    in_slit = np.mod(np.nan_to_num(east), 12.0) < 4.0
    if lit_slits is not None:
        in_slit &= lit_slits[np.mod(slot, len(lit_slits))]
    frame[band & ~in_slit] = SHADE
    return frame.reshape(height, 2, width, 2, 3).mean(axis=(1, 3))


def test_regular_picket_stripes_do_not_streak_and_aliased_slits_do() -> None:
    """True stripes repeat with the pickets and cancel in the one-pitch filter; slits
    of which a random few leak light (a shadow map's texels aliasing them) beat."""
    def streak(frame: np.ndarray) -> float:
        lit = P.shadow_streaks(frame, EDGE_CAMERA, (-300.0, 150.0), (1300.0, 150.0),
                               period_cm=12.0, lit_luma=0.0)["mean_luma"]
        out = P.shadow_streaks(frame, EDGE_CAMERA, (-300.0, -200.0), (1300.0, -200.0),
                               period_cm=12.0, lit_luma=float(lit))
        assert out["samples"] > 150, out
        return float(out["streak"])

    regular = streak(_striped(None))
    leaking = streak(_striped(np.random.default_rng(734).random(97) < 0.25))
    assert regular < 0.1, regular
    assert leaking > 0.25 and leaking > 3 * regular, (regular, leaking)


def test_an_edge_that_stays_put_while_the_camera_moves_does_not_swim_and_one_that_moves_does() -> None:
    """``edge_swim`` compares consecutive frames on one WORLD grid along the edge: a camera
    move changes where the stations are on screen, never where the edge is."""
    def framed(camera: P.Pinhole, edge: float) -> dict:
        width, height = camera.size
        big = P.Pinhole(camera.eye, camera.target, camera.fov_deg, (width * 2, height * 2))
        east, north, ground = _ground(big)
        frame = np.empty(east.shape + (3,))
        frame[:] = (150.0, 190.0, 230.0)
        frame[ground] = MEADOW
        frame[ground & (north > edge)] = SHADE
        rgb = frame.reshape(height, 2, width, 2, 3).mean(axis=(1, 3))
        return P.shadow_edge_trace(rgb, camera, (-4000.0, EDGE_NORTH), (1800.0, EDGE_NORTH),
                                   (0.0, -1.0), half_width_cm=60.0)

    moved = P.Pinhole((1330.0, -880.0, 450.0), EDGE_CAMERA.target, EDGE_CAMERA.fov_deg, EDGE_CAMERA.size)
    still = P.edge_swim([framed(EDGE_CAMERA, EDGE_NORTH), framed(moved, EDGE_NORTH)])
    crawled = P.edge_swim([framed(EDGE_CAMERA, EDGE_NORTH), framed(moved, EDGE_NORTH + 4.0)])
    judged = [(a, b) for a, b in zip(still, crawled, strict=True)
              if "swim_cm" in a and a["pairs"] >= 200]
    assert judged
    for a, b in judged:
        assert a["swim_cm"] < 1.5, a        # the instrument's floor: 1.0 cm at 960 x 540
        assert b["swim_cm"] == pytest.approx(4.0, abs=1.0), b
        assert b["swim_px"] > 2.0 * a["swim_px"], (a, b)
    assert P.edge_swim([framed(EDGE_CAMERA, EDGE_NORTH)]) == []


# ── the meadow (#798) ────────────────────────────────────────────────────────

#: A camera at a viewer's height south of a plan of 20 x 10 m (east 0..2000, north 0..1000),
#: looking north at its middle.
MEADOW_CAMERA = P.Pinhole(eye=(1000.0, -1500.0, 400.0), target=(1000.0, 500.0, 0.0), fov_deg=50.0,
                          size=(320, 180))
MEADOW_PLAN = (0.0, 0.0, 2000.0, 1000.0)


def test_a_felt_table_is_flat_and_green_and_grass_is_not() -> None:
    """The survey's instrument (#798): a flat green frame is all flat green; the same
    green with a texture of std 10 is not flat; a flat grey sky is flat but not green; a
    mask confines the count."""
    rng = np.random.default_rng(798)
    felt = np.zeros((90, 160, 3)) + MEADOW
    grass = felt + rng.normal(0.0, 10.0, felt.shape[:2])[..., None]
    sky = np.zeros_like(felt) + 170.0
    assert P.flat_share(felt) == {"flat_green": 1.0, "flat": 1.0, "local_std": 0.0, "pixels": 14400}
    textured = P.flat_share(grass)
    assert textured["flat_green"] < 0.01 and textured["local_std"] > 7.0, textured
    assert P.flat_share(sky)["flat"] == 1.0 and P.flat_share(sky)["flat_green"] == 0.0
    half = np.zeros(felt.shape[:2], dtype=bool)
    half[:, :80] = True
    mixed = np.where(half[..., None], felt, grass)
    assert P.flat_share(mixed, half)["flat_green"] > 0.9       # the window reaches 4 px over
    assert P.flat_share(mixed, ~half)["flat_green"] < 0.05
    assert P.flat_share(mixed, np.zeros_like(half))["pixels"] == 0


def test_the_local_spread_of_a_step_is_seen_only_near_it() -> None:
    values = np.zeros((40, 40))
    values[:, 20:] = 10.0
    spread = P.local_std(values, 9)
    assert spread[:, :15].max() == pytest.approx(0.0, abs=1e-9)
    assert spread[:, 25:].max() == pytest.approx(0.0, abs=1e-6)
    assert spread[20, 19] == pytest.approx(5.0, abs=0.6)       # half and half: std 5


def test_the_meadow_mask_sees_the_meadow_and_never_the_plan_or_what_lies_behind_it() -> None:
    east, north, distance = P.ground_hits(MEADOW_CAMERA)
    mask = P.meadow_mask(MEADOW_CAMERA, MEADOW_PLAN, margin_cm=100.0)
    with np.errstate(invalid="ignore"):
        on_plan = (east >= -100) & (east <= 2100) & (north >= -100) & (north <= 1100)
        behind = (north > 1100) & (east > 0) & (east < 2000)    # seen across the plan
    assert mask.any() and not (mask & on_plan).any() and not (mask & behind).any()
    assert not mask[:int(MEADOW_CAMERA.horizon_row())].any()   # no sky
    assert mask[-1, :].all()                                    # the meadow at the camera's feet
    assert np.nanmax(distance[mask]) < np.inf
    near = P.meadow_mask(MEADOW_CAMERA, MEADOW_PLAN, margin_cm=100.0, far_cm=1000.0)
    assert near.sum() < mask.sum() and not (near & (distance > 1000.0)).any()
    # the camera's foot inside the grown plan: every line of sight crosses it
    above = P.Pinhole((1000.0, 500.0, 2000.0), (1000.0, 2500.0, 0.0), 50.0, (320, 180))
    assert not P.meadow_mask(above, MEADOW_PLAN).any()


def test_a_still_or_smooth_move_does_not_flicker_and_aliasing_does() -> None:
    """``track_luma`` follows fixed ground points through camera moves; ``temporal_noise``
    tells a smooth change (a move) from a frame-to-frame one (crawl, shimmer)."""
    rng = np.random.default_rng(799)
    east, north, _distance = P.ground_hits(MEADOW_CAMERA)
    points = np.column_stack([np.linspace(400.0, 1600.0, 40), np.full(40, -600.0)])

    def frame(level: float, noise: float) -> np.ndarray:
        rgb = np.zeros(east.shape + (3,)) + level
        return rgb + rng.normal(0.0, noise, east.shape)[..., None] if noise else rgb

    cameras = [MEADOW_CAMERA] * 6
    still = P.temporal_noise(P.track_luma([frame(120.0, 0.0)] * 6, cameras, points))
    ramp = P.temporal_noise(P.track_luma([frame(120.0 + 2.0 * i, 0.0) for i in range(6)], cameras,
                                         points))
    shimmer = P.temporal_noise(P.track_luma([frame(120.0, 6.0) for _ in range(6)], cameras, points))
    assert still["zigzag_rms"] == 0.0 and still["step_mean"] == 0.0 and still["points"] == 40
    assert ramp["zigzag_rms"] == pytest.approx(0.0, abs=1e-9) and ramp["step_mean"] == 2.0
    assert shimmer["zigzag_rms"] > 1.5 and shimmer["step_mean"] > 1.5, shimmer
    # a point the camera cannot see is never counted
    hidden = P.track_luma([frame(120.0, 0.0)] * 3, cameras[:3], [(1000.0, -5000.0)])
    assert np.isnan(hidden).all() and P.temporal_noise(hidden)["points"] == 0
    assert P.temporal_noise(np.zeros((2, 4)))["zigzag_rms"] is None


def test_a_repeated_tile_correlates_at_its_period_and_noise_does_not() -> None:
    rng = np.random.default_rng(256)
    tile = rng.normal(0.0, 1.0, (32, 32))
    tiled = np.tile(tile, (6, 8))
    noise = rng.normal(0.0, 1.0, tiled.shape)
    repeated = P.repeat_correlation(tiled, 32.0)
    fresh = P.repeat_correlation(noise, 32.0)
    assert repeated["at_period"] > 0.99 and repeated["excess"] > 0.9, repeated
    assert abs(fresh["at_period"]) < 0.05 and abs(fresh["excess"]) < 0.08, fresh
    assert P.repeat_correlation(np.zeros((40, 40)), 8.0)["at_period"] == 0.0   # flat: nothing
