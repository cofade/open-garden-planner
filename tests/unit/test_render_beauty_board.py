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
from open_garden_planner.core.shadow_geometry import compute_scene_shadows

#: What the L0 spike measured, frozen when L1.10 deleted it (its provenance field says how).
SPIKE = json.loads((Path(__file__).resolve().parents[1] / "data" / "l0_spike_reference.json")
                   .read_text(encoding="utf-8"))

SCRIPT = Path(board.__file__)


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
    assert spike["sky_pitch_deg"] == board.SKY_PITCH_DEG and board.SKY_MAX_ERROR_DEG == 6.0
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
    assert "THE GROUND BAKE (L1.5) JOINS HERE" in source, "the one line the bake's baker goes into"


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
