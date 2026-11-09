"""The production Beauty Board's own data and arithmetic (Phase 17 L1.4, #385).

``scripts/render_beauty_board.py`` renders nothing in the default tier (no GPU); what
can be checked without one is what it would render: the shot list (the L0 spike's,
so that a board of today can be laid beside an L0 board), the probes' cameras (do
they see what they measure?), and that a mistyped argument is an error and never
another experiment. The frames themselves are judged by
``tests/integration/test_view3d_looks_render.py``.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pytest
from scripts import render_beauty_board as board

from open_garden_planner.core.scene3d import pose_ring
from open_garden_planner.core.scene3d.look import fog_depth_cm
from open_garden_planner.core.shadow_geometry import compute_scene_shadows

#: What the L0 spike measured, frozen when L1.10 deleted it (its provenance field says how).
SPIKE = json.loads((Path(__file__).resolve().parents[1] / "data" / "l0_spike_reference.json")
                   .read_text(encoding="utf-8"))

SCRIPT = Path(board.__file__)


def test_distant_horizon_cameras_exercise_the_fog_distance_and_low_pitch() -> None:
    from open_garden_planner.core.scene3d.camera import DEFAULT_PITCH_DEG

    cameras = board.distant_horizon_cameras(5000.0, 3000.0, (960, 540), 225.0)
    assert len(cameras) == 8
    assert {pitch for _distance, pitch, _camera in cameras} == {15.0, DEFAULT_PITCH_DEG}
    assert {distance for distance, _pitch, _camera in cameras} == {67, 202, 403, 600}
    for distance, pitch, camera in cameras:
        assert math.dist(camera.eye, camera.target) == pytest.approx(distance * 100.0)
        assert math.degrees(math.asin(camera.eye[2] / (distance * 100.0))) == pytest.approx(pitch)
    assert fog_depth_cm(600 * 100.0)[0] > fog_depth_cm(67 * 100.0)[0]


@pytest.mark.parametrize(("label", "turn"), board.SKY_BAND_DIRECTIONS)
def test_the_sky_band_cameras_see_every_band_they_judge(label: str, turn: float) -> None:
    """#716/#719: the sky-band frames must hold the meadow (−6…−3°), the haze band (3°),
    the deck (10°), the low band (6–15°) and the top of the inversion range (20°) in the
    probe's own window round the bearing — at the render tier's size."""
    from scripts import board_probes as probes

    size = (640, 360)
    bearing = (board.SKY_BAND_AZIMUTH + turn) % 360.0
    camera = board.sky_band_camera(bearing, size)
    flat = np.full((size[1], size[0], 3), 128.0)
    profile = probes.sky_profile(flat, camera, bearing, lowest_deg=-10.0, highest_deg=30.0)
    for elevation in (-6.0, -3.0, board.SKY_BAND_INVERSION_RANGE[0], board.SKY_BAND_HAZE_DEG,
                      board.SKY_BAND_LOW[0], board.SKY_BAND_DECK_DEG, board.SKY_BAND_LOW[1],
                      board.SKY_BAND_INVERSION_RANGE[1]):
        assert probes.profile_at(profile, elevation) == 128.0, (label, elevation)
    assert min(profile["count"]) >= 20
    args = board._parse(["--sky-bands", "--sky", "atmosphere"])
    assert args.sky_bands is True and args.sky == "atmosphere"


@pytest.mark.parametrize("size", [(2400.0, 1600.0), (5000.0, 4000.0), (800.0, 3000.0)])
def test_the_shots_are_the_spikes(size: tuple[float, float]) -> None:
    """Same dates, times and cameras as the L0 board (frozen when L1.10 deleted the
    spike): before / after is like for like only while this holds."""
    ours, theirs = board.default_shots(*size), SPIKE["shots"][f"{size[0]:g}x{size[1]:g}"]
    assert [shot.name for shot in ours] == [
        "golden_hour", "sunset", "noon", "morning", "december_noon", "night", "walk"]
    assert len(ours) == len(theirs)
    for mine, spike in zip(ours, theirs, strict=True):
        assert (mine.name, mine.when_utc.isoformat(), mine.fov_deg) == (
            spike["name"], spike["when_utc"], spike["fov"])
        assert mine.eye == pytest.approx(spike["eye"]) and mine.target == pytest.approx(
            spike["target"])


def test_the_probes_scene_is_the_spikes_caster() -> None:
    """The L0 probes' caster and sky look, frozen when L1.10 deleted the spike."""
    spike = SPIKE["probes"]
    assert spike["caster_in_source"] is True
    caster = spike["caster"]
    assert (board.CASTER_SIDE, board.CASTER_HEIGHT, board.IOU_AZIMUTH) == (
        caster["side"], caster["height"], caster["azimuth"]) == (100.0, 200.0, 225.0)
    assert list(board.IOU_ELEVATIONS) == caster["elevations"] == [15.0, 35.0, 60.0]
    assert list(board.SKY_OFFSETS_DEG) == spike["sky_look_offsets_deg"]
    # the spike's 14° camera was 2° above its 12° sun; the probe now pitches every sun
    # by the same offset (#717)
    assert spike["sky_pitch_deg"] == 12.0 + board.SKY_PITCH_OFFSET_DEG
    assert board.SKY_MAX_ERROR_DEG == 6.0
    record = board.caster_record()
    ring = pose_ring(record.transform, record.footprints[0])
    assert sorted(ring) == sorted(board.caster_footprint()) and record.height_cm == 200.0


@pytest.mark.parametrize("size", [(640, 360), (960, 540), (1280, 720)])
@pytest.mark.parametrize("elevation", board.IOU_ELEVATIONS)
def test_the_shadow_camera_sees_the_caster_and_the_whole_shadow(
        elevation: float, size: tuple[int, int]) -> None:
    """A gate that measures a shadow cut off by the frame's edge measures the edge."""
    camera = board.iou_camera(elevation, size)
    footprint = board.caster_footprint()
    points = [(x, y, 0.0) for polygon in compute_scene_shadows(
        [(footprint, board.CASTER_HEIGHT)], elevation, board.IOU_AZIMUTH) for x, y in polygon]
    points += [(x, y, z) for x, y in footprint for z in (0.0, board.CASTER_HEIGHT)]
    px, py, front = camera.project(points)
    margin = 0.04 * size[1]
    assert front.all()
    assert px.min() > margin and px.max() < size[0] - margin, (px.min(), px.max())
    assert py.min() > margin and py.max() < size[1] - margin, (py.min(), py.max())
    # … from the side: the caster does not stand between the camera and its shadow
    reach = board.CASTER_HEIGHT / math.tan(math.radians(elevation))
    assert reach > 100.0 and camera.eye[2] > 0.5 * reach
    # … and at about two centimetres of ground per pixel or better where the frame is large
    spread = float(np.hypot(px.max() - px.min(), py.max() - py.min()))
    assert spread > 0.35 * size[1], "the shadow is a speck in the frame"
    ground = board.IOU_GROUND
    assert min(x for x, _y, _z in points) > 0.0 and max(x for x, _y, _z in points) < ground.width_cm
    assert min(y for _x, y, _z in points) > 0.0 and max(y for _x, y, _z in points) < ground.depth_cm
    # … and near enough that its shadow map is the spike's: a perspective camera's map
    # reaches as far as the fog begins once that is further (Garden.qml, ADR-065)
    (shadow_far,) = SPIKE["qml"]["environment"]["shadowMapFar"]
    assert fog_depth_cm(math.dist(camera.eye, camera.target))[0] <= shadow_far


def test_a_distant_camera_gets_a_pin_that_shows_in_the_gate() -> None:
    """#704: the noon camera's 52 cm pin read 38 px on bench_built, under the board's
    50 px gate. The pin is sized from the camera at the point the whole-pin search
    chooses, so the gate holds without moving the measurement off the ground."""
    from open_garden_planner.core.scene3d.sun_path import dome_radius

    width, depth, size = 2600.0, 1800.0, (1280, 720)
    shot = next(shot for shot in board.default_shots(width, depth) if shot.name == "noon")
    world = type("World", (), {"pick": object()})()
    radius = dome_radius(width, depth)
    point, height = board._open_ground(world, shot, {}, lambda *_args: False, size, radius)
    camera = board.probes.Pinhole(shot.eye, shot.target, shot.fov_deg, size)
    assert height > 0.03 * radius, "the dome share was too short for this camera"
    assert board._pin_projected_px(camera, point, height) >= board.PROBE_PIN_MIN_PX - 1e-6


def test_a_pin_whose_ball_is_hidden_is_not_the_probe_point() -> None:
    """#704's other half: the old search only checked the first 30 cm, so a point under
    a canopy could win. The candidate seen without blocking is blocked at its top and
    a different, clear point is chosen."""
    from open_garden_planner.core.scene3d.sun_path import dome_radius

    width, depth, size = 2600.0, 1800.0, (1280, 720)
    shot = next(shot for shot in board.default_shots(width, depth) if shot.name == "noon")
    world = type("World", (), {"pick": object()})()
    radius = dome_radius(width, depth)
    point, height = board._open_ground(world, shot, {}, lambda *_args: False, size, radius)

    def canopy(_pick: object, _eye: tuple[float, float, float],
               target: tuple[float, float, float]) -> bool:
        return (round(target[0], 6) == round(point[0], 6)
                and round(target[1], 6) == round(point[1], 6)
                and target[2] > 100.0)      # only the ball is under the canopy

    other, other_height = board._open_ground(world, shot, {}, canopy, size, radius)
    assert other != point, "the hidden pin was chosen again"
    camera = board.probes.Pinhole(shot.eye, shot.target, shot.fov_deg, size)
    assert board._pin_projected_px(camera, other, other_height) >= board.PROBE_PIN_MIN_PX - 1e-6


def test_a_mistyped_argument_is_an_error_not_another_experiment(capsys) -> None:
    for argv in (["--iuo"], ["--preset", "high"], ["--ori"], ["--shots"]):
        with pytest.raises(SystemExit) as stop:
            board._parse(argv)
        assert stop.value.code == 2, argv
    capsys.readouterr()
    args = board._parse(["--presets", "low,high", "--shots", "noon,walk", "--iou"])
    shots, presets = board._chosen(args, board.default_shots(2400.0, 1600.0))
    assert [shot.name for shot in shots] == ["noon", "walk"] and presets == ["low", "high"]
    for bad in (["--presets", "hi"], ["--presets", ""], ["--shots", "dusk"], ["--presets", "auto"]):
        with pytest.raises(ValueError, match="unknown"):
            board._chosen(board._parse(bad), board.default_shots(2400.0, 1600.0))


def test_the_defaults_are_the_bench_plan_at_high() -> None:
    args = board._parse([])
    assert args.plan == board.DEFAULT_PLAN and args.plan.name == "bench_small.ogp"
    assert args.plan.is_file()
    assert (args.presets, args.shots, args.size) == ("high", "all", "1280x720")
    assert args.watchdog_s == 1800.0 and not (args.iou or args.orient or args.horizon or args.software)


def test_every_frame_goes_through_the_production_pipeline_and_no_shown_host() -> None:
    """Read from the source: frames come from ``render_records`` (a never-shown host per
    frame, Qt's messages recorded), the plan's items from ``snapshot_records`` and
    ``production_registry``; the one shown host is the frame-rate phase's; and the wind
    never runs while a frame is taken."""
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert "render_records" in calls and "snapshot_records" in calls
    assert calls.count("production_registry") >= 3
    assert calls.count("Quick3DHost") == 1, "one shown host: the frame-rate phase"
    methods = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    shown = ast.unparse(methods["frame_rate"])
    assert "Quick3DHost(" in shown and "set_wind_running(True)" in shown and "rest_wind()" in shown
    for name in ("shoot", "mood_strip", "shadow_iou", "orientation", "sky_azimuth", "horizon",
                 "restore_check"):
        body = ast.unparse(methods[name])
        assert "self.frame(" in body and "Quick3DHost" not in body and "wind" not in body, name
    # every frame that shows the plan paints its ground with the product's baker (#586);
    # the probes whose oracles are the records' own footprints stay bare
    assert "ground_baker=GroundBaker(budget_s=None) if baked else None" in ast.unparse(methods["frame"])
    for name in ("shoot", "mood_strip", "horizon", "restore_check"):
        assert "baked=True" in ast.unparse(methods[name]), name
    for name in ("shadow_iou", "orientation", "sky_azimuth"):
        assert "baked=True" not in ast.unparse(methods[name]), name


def test_plan_derived_text_is_logged_through_the_plain_text_helper() -> None:
    """A plan's file name is text somebody else chose (security add-on, §8.11)."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "log_text(self.args.plan.name)" in source
    assert "plan=str(" not in source and 'f"{self.args.plan' not in source


def test_a_shots_day_is_the_plans_local_day_not_the_utc_date() -> None:
    """Review P2: the board took the UTC date where ADR-053 says the plan's LOCAL day
    (the sim clock's ``tz=None``: the system zone)."""
    from datetime import UTC, datetime

    late = datetime(2026, 6, 21, 23, 30, tzinfo=UTC)
    assert board.plan_day(late) == late.astimezone().date()


def test_the_date_row_can_fail(qtbot, tmp_path: Path) -> None:  # noqa: ARG001 - Qt must be up
    """Review P2: ``sun_date`` and ``build_date`` were the same variable written twice.
    Now ``build_date`` is read back from the records actually rendered, and every
    snapshot carries a digest of its (item, height): the board's two dates grow the
    bench plan's plants differently, so a board that rendered June's models for
    December could not hide behind equal date strings."""
    import argparse
    from datetime import date

    args = argparse.Namespace(plan=board.DEFAULT_PLAN, size="320x180", software=False,
                              qml_dir=None, list=True)
    run = board.Board(args, tmp_path, lambda *_a, **_k: None, {})
    run.load()
    june, december = run.records_for(date(2026, 6, 21)), run.records_for(date(2026, 12, 21))
    assert run.snapshot_day(june) == date(2026, 6, 21)
    assert run.snapshot_day(december) == date(2026, 12, 21)
    assert run.records_for(date(2026, 6, 21)) is june, "one snapshot per date"
    digests = {day: block["digest"] for day, block in run.metrics["builds"].items()}
    assert digests["2026-06-21"] != digests["2026-12-21"]
    assert board.records_digest(june) == digests["2026-06-21"]
    with pytest.raises(KeyError):
        run.snapshot_day(dict(june))                  # records nobody snapshotted
