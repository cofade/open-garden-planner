"""The director's cut on the real engine (Phase 17 L6, #390, ADR-072) — render tier.

Opt-in (``OGP_RENDER3D=1``; it opens windows on the desktop). The default tier pins every
decision around a picture (``test_directors_cut.py``); here the ENGINE answers what the
design rests on:

- **a capture IS the view**: same pixels at the view's size, the right size whatever the
  window's size and scale, and the same picture the view shows from that camera;
- **nothing jumps**: the view reads back identically afterwards, its camera untouched;
- **every photo setting off is the view again**, pixel for pixel, and a grade's table does
  not turn the darkest leaves red (Qt's lookup, ``Garden.qml``);
- **a tour's video has its frames**, a time-lapse follows and restores the clock, and the
  agent's picture refuses cleanly and leaves everything as it was.

    OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest -n 0 tests/integration/test_directors_cut_render.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.integration.quick3d_render_support import (
    REPO,
    keep_artifacts,
    render_env,
    render_tier,
)

pytestmark = render_tier

DRIVER = REPO / "tests" / "integration" / "view3d_capture_driver.py"
TIMEOUT_S = 840
#: How far a capture may lie from the view, levels: it is the same render. 0 was measured
#: on Direct3D 11, GPU and WARP.
SAME = 1
#: A grade's identity table against the view: rounding through a 16-level table, measured
#: at mean 0.13, p99 1, at most 5.
TABLE_MEAN, TABLE_MAX = 0.5, 8
#: The largest luma step between neighbouring frames of the two-week clock-change tour.
#: Measured on the dev box: 1.53 after the tour held UTC; 18.07 at the change before it
#: (the owner read 24 in the year video, #732). Every other step stays below 2.
DST_STEP_BOUND = 4.0
#: #733, the family garden at sunset: a 4K picture's horizon band against 1080p's, in
#: luma. Measured -0.41 mean / -0.53 worst 40-row bucket with the capture's AO radius
#: scaled; -1.75 / -2.82 without it. The band's sky control stays within 0.5.
PICTURE_BAND_DELTA = 1.0
PICTURE_BUCKET_DELTA = 1.6
PICTURE_SKY_DELTA = 0.5
#: #743: how far the preview's blur may lie from a 4K save's, seen at the preview's size, in
#: gradient ratio (the share of a 60 px tile's detail the blur keeps; mean over the tiles, and
#: the middle third of the picture). Qt's half-resolution blur measured 0.394 / 0.366 apart
#: (preview 0.527, save 0.917); the picture-relative blur of ADR-072's addendum is the gate.
BLUR_PARITY_MEAN = 0.06
BLUR_PARITY_MIDDLE = 0.06
#: The slider (#743, 3D review): from 0.05 to 1.0 the share of 60 px tiles that lost a fifth
#: of their detail rises by at least this, and the tile under the focus keeps 0.9 of its own.
SLIDER_SOFT_RISE = 0.20
SLIDER_FOCUS_KEPT = 0.9
#: The blur bench (#743): levels the in-focus bar's colour may add to the blurred wall beside it
#: (measured 0.0; Qt's blur 7-8 at 4K), how far a preview's measure may lie from a 4K save's as a
#: share of the save's (measured 10 % and 20 %; Qt's 260 %), and the near bar's rim at 360 px and
#: at 4K (measured 20 and 4; 47 at 360 px with full-weight silhouettes, PF-E3D-27).
BENCH_FRINGE = 1.0
BENCH_SHARE_TOLERANCE = 0.30
BENCH_RIM = (26.0, 8.0)


def drive(tmp_path: Path, scenario: str, **env: str) -> dict[str, Any]:
    out = tmp_path / scenario
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(DRIVER), "--out", str(out), "--scenario", scenario, "--limit-s", "780"],
        env=render_env(out, **env), capture_output=True, text=True, timeout=TIMEOUT_S, cwd=REPO)
    keep_artifacts(out, proc)
    result_path = out / "result.json"
    assert result_path.is_file(), f"exit {proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    result: dict[str, Any] = json.loads(result_path.read_text(encoding="utf-8"))
    assert "failed" not in result, result.get("trace", result.get("failed"))
    assert proc.returncode == 0
    result["out"] = str(out)
    return result


@pytest.fixture(scope="module")
def host_answers(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return drive(tmp_path_factory.mktemp("capture"), "host")


def test_a_capture_at_the_views_size_is_the_view(host_answers: dict[str, Any]) -> None:
    assert host_answers["capture_vs_view"]["max"] <= SAME
    assert host_answers["taken_size"] == host_answers["size"]
    assert host_answers["format"] == "Format_RGBX8888", "an opaque picture"


def test_the_window_is_behind_and_renders_all_the_same(host_answers: dict[str, Any]) -> None:
    """``scripts/quiet_windows``: no focus taken, under the other windows, and every other test
    in this file reads its frames from that very window."""
    behind = host_answers["behind"]
    if behind["checked"]:
        assert behind["no_activation"] and behind["exposed"]
        assert not behind["foreground"]


def test_every_size_comes_out_exact_and_shows_something(host_answers: dict[str, Any]) -> None:
    for name, row in host_answers["sizes"].items():
        width, height = (int(side) for side in name.split("x"))
        assert row["got"] == [width, height], name
        assert not row["flat"], name


#: #734: a still picture's shadow map fitted to the casters against the view's locked fit, on
#: the bench plan at 38° (medium, 640 x 360). Measured on the RTX 4070: 6.0 % of the pixels
#: more than 8 levels apart, mean 1.32 - every one along a shadow's edge or in a canopy's
#: self-shadow. Below the floor the fit did nothing; above the ceiling it changed more than
#: shadow edges.
FITTED_CHANGED_SHARE = (0.01, 0.15)
FITTED_MEAN = 3.0


def test_a_still_pictures_fitted_shadows_change_only_its_own_frame(host_answers: dict[str, Any]) -> None:
    """#734: ``capture(fitted_shadows=True)`` - what a photo, an agent's picture and a held
    camera's frame ask for - sharpens the shadow map for that frame and puts the view's fit
    back: the view grabbed after it is the view to the level. The default capture stays the
    view (``test_a_capture_at_the_views_size_is_the_view``; the self-test checks the same)."""
    fitted = host_answers["fitted"]
    low, high = FITTED_CHANGED_SHARE
    assert low <= fitted["changed_share"] <= high, fitted
    assert fitted["mean"] <= FITTED_MEAN, fitted
    assert fitted["view_after"]["max"] <= SAME, fitted
    assert fitted["flag_after"] is False, fitted


def test_another_camera_moves_nothing_on_screen(host_answers: dict[str, Any]) -> None:
    assert host_answers["other_vs_view"]["mean"] > 5.0, "the picture really is from elsewhere"
    assert host_answers["view_after_capture"]["max"] <= SAME
    assert host_answers["camera_kept"]
    assert host_answers["capture_off_after"], "the capture view rests again"


def test_a_capture_from_a_camera_is_what_the_view_shows_from_there(host_answers: dict[str, Any]) -> None:
    assert host_answers["other_vs_view_moved"]["max"] <= SAME


def test_photo_settings_develop_the_picture_and_off_is_the_view_again(host_answers: dict[str, Any]) -> None:
    for name, row in host_answers["photo"].items():
        assert row["mean"] > 1.0, f"{name} changed nothing"
    assert host_answers["no_photo_again"]["max"] <= SAME
    assert host_answers["photo_override"]["max"] <= SAME, "an agent's picture is undeveloped"
    assert host_answers["photo_kept"], "and the owner's settings stay"


def test_a_saved_photo_has_the_blur_its_preview_shows(host_answers: dict[str, Any]) -> None:
    """#743: Qt's blur was about 2 px at any picture size, so a 4K save was much sharper than the
    pane that previewed it (0.53 against 0.92 of the detail kept). The blur is a share of the
    picture's height: the save, shrunk to the preview's size, keeps what the preview keeps."""
    parity = host_answers["blur"]["parity"]
    assert parity["tiles"] >= 20, parity
    assert parity["preview_mean"] < 0.85, f"blur 0.8 really blurs: {parity}"
    assert parity["mean_abs_difference"] <= BLUR_PARITY_MEAN, parity
    assert abs(parity["preview_middle"] - parity["save_middle"]) <= BLUR_PARITY_MIDDLE, parity


def test_the_blur_slider_moves_the_picture_and_keeps_the_focus_sharp(
        host_answers: dict[str, Any]) -> None:
    """The 3D review of #729: the only pin was ``mean > 1.0``, which passed while the owner saw
    no difference between a high and a low blur."""
    slider = host_answers["blur"]["slider"]
    faint, strong = slider["0.05"], slider["1.0"]
    assert strong["soft_share"] - faint["soft_share"] >= SLIDER_SOFT_RISE, slider
    for row in (faint, strong):
        assert row["focus_ratio"] >= SLIDER_FOCUS_KEPT, slider


def test_the_blur_bleeds_no_sharp_colour_and_softens_a_near_edge(tmp_path: Path) -> None:
    """#743 on a bench with known answers (``photoblur_bench.qml``, the product's PhotoBlur.qml).
    Qt's blur, measured on the same bench: a 7-8 level fringe of the in-focus bar on the blurred
    wall at 4K, a thin far line 3.6 times wider (as a share of the picture) at 360 px than at 4K,
    and the near bar's edge 1 px wide at 4K. PF-E3D-27: the bar's rim read 47 levels at 360 px
    while a multisampled edge pixel had full weight."""
    result = drive(tmp_path, "blur_bench")
    small, large = result["360"], result["2160"]
    for size in (small, large):
        blurred, sharp = size["blurred"], size["sharp"]
        assert blurred["fringe"] <= BENCH_FRINGE, size
        assert blurred["line_humps"] == 1, f"one smooth hump, no copies: {size}"
        assert blurred["line_width_share"] > 1.6 * sharp["line_width_share"], size
        assert blurred["near_edge_share"] >= 2.5 * sharp["near_edge_share"], f"a soft near edge: {size}"
    shares = [(small["blurred"][key], large["blurred"][key]) for key in ("line_width_share", "near_edge_share")]
    for preview, save in shares:
        assert abs(preview - save) <= BENCH_SHARE_TOLERANCE * save, shares
    assert small["blurred"]["near_rim"] <= BENCH_RIM[0] and large["blurred"]["near_rim"] <= BENCH_RIM[1], result


def test_no_blur_with_a_focus_is_the_view_to_the_level(host_answers: dict[str, Any]) -> None:
    """Blur 0 draws no blur effect at all: the frame is the view's, not a level apart."""
    assert host_answers["blur"]["zero"]["max"] == 0, host_answers["blur"]["zero"]


def test_the_engine_reported_nothing(host_answers: dict[str, Any]) -> None:
    health = host_answers["health"]
    assert health["ok"] and not health["warnings"] and health["error"] is None


def test_a_grades_table_is_the_view_through_it_and_turns_nothing_red(tmp_path: Path) -> None:
    result = drive(tmp_path, "grades")
    identity = result["identity"]
    assert identity["mean"] <= TABLE_MEAN and identity["max"] <= TABLE_MAX, identity
    assert result["dark_pixels"] > 100, "the frame has dark leaves to judge"
    assert result["dark_red_rise"] <= TABLE_MAX, "R 0 became 57 before Garden.qml's fix"
    grades = result["grades"]
    plain = grades["none"]["means"]
    assert grades["none"]["max"] == 0
    assert grades["golden"]["means"][2] < plain[2] and grades["golden"]["means"][0] > plain[0]
    assert grades["cool"]["means"][2] > plain[2] and grades["cool"]["means"][0] < plain[0]
    mono = grades["mono"]["means"]
    assert max(mono) - min(mono) < 1.0
    assert result["after"]["max"] <= SAME, "and the view comes back"


def test_blur_on_the_ultra_preset_draws_and_does_not_take_the_render_thread_down(tmp_path: Path) -> None:
    """Ultra's reflections + glow + occlusion with depth of field in one chain crashed d3d11.dll
    at an owner's first focus click (#390's manual test): no result file, a dead process. With
    the app's own blur in Qt's place the chain still crashes (#744: with glow, ANY two effects
    ahead of Qt's scene effect - 3 of 3 on Ultra with reflections kept), so reflections still
    stand down while the blur is drawn, and come back with it."""
    result = drive(tmp_path, "ultra_blur")
    rows = result["rows"]
    assert result["reflections_without_blur"], "Ultra draws reflections"
    assert rows["0.0"]["reflections_drawn"], "and has them back when the blur is off"
    for blur in ("0.3", "1.0"):
        assert rows[blur]["blur_drawn"], blur
        assert not rows[blur]["reflections_drawn"], f"PF-E3D-21: reflections under blur {blur}"
        assert rows[blur]["capture_vs_sharp"]["mean"] > 0.05, f"blur {blur} changed nothing: {rows[blur]}"
    assert rows["1.0"]["capture_vs_sharp"]["mean"] > rows["0.3"]["capture_vs_sharp"]["mean"]
    assert not rows["0.0"]["blur_drawn"]
    assert rows["0.0"]["capture_vs_sharp"]["max"] <= SAME, "no blur is the sharp view again"
    for blur, row in rows.items():
        assert row["agent_vs_sharp"]["max"] <= SAME, f"an agent's picture is the plain view ({blur})"
    assert result["after"]["max"] <= SAME


def test_a_tour_writes_every_frame_and_leaves_the_view_where_it_was(tmp_path: Path) -> None:
    from PyQt6 import QtMultimedia  # noqa: F401 - the tier needs the module to read a video back

    result = drive(tmp_path, "tour")
    tour = result["result"]
    assert tour["ok"], tour
    assert tour["frames"] == result["expected_frames"] and tour["unsettled"] == 0
    assert result["blocker_while_recording"] == "recording"
    assert not result["part_left"]
    video = result["video"]
    assert video["duration_ms"] == 2000 and video["size"] == [1280, 720], video
    assert video["frames"] == result["expected_frames"], video
    assert result["camera_kept"] and result["clock_kept"]


def test_a_tours_frames_show_the_plants_as_the_view_would_from_there(tmp_path: Path) -> None:
    """The view's camera used to decide a tour's leaves: 17 levels (mean) on this close camera."""
    result = drive(tmp_path, "detail")
    assert result["tour"]["ok"] and result["tour"]["unsettled"] == 0, result["tour"]
    assert result["finer_than_the_view"] > 0, "the flight really passes closer than the view"
    assert result["frame_has_the_flights_detail"]
    assert result["pending_at_first_frame"] == 0, "the first frame waited for them"
    assert result["fine_vs_coarse"]["mean"] > 1.0, "and it can be seen"
    assert result["after_it_the_camera_decides"]


@pytest.fixture(scope="module")
def timelapse_runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The day, the year and the clock-change tours from ONE driver run."""
    return drive(tmp_path_factory.mktemp("timelapse"), "timelapse")["runs"]


def test_a_time_lapse_follows_the_clock_and_puts_it_back(
        timelapse_runs: dict[str, Any]) -> None:
    runs = timelapse_runs
    day, year = runs["day"], runs["year"]
    assert day["ok"] and year["ok"], runs
    assert day["files"] == year["files"] == 24
    assert day["first_moment"] == ["2026-06-21", "08:00"] and day["last_moment"] == ["2026-06-21", "20:00"]
    assert year["first_moment"][0] == "2026-03-01" and year["last_moment"][0] == "2026-10-31"
    assert day["unsettled"] == year["unsettled"] == 0
    assert day["clock_back"] and year["clock_back"]


def test_a_year_time_lapse_does_not_jump_at_the_clock_change(
        timelapse_runs: dict[str, Any]) -> None:
    """A wall time held across a DST change moves the sun by an hour: the owner saw a
    24-level step between neighbouring frames of the year video (#732). The tour holds
    UTC instead, so the sun moves evenly and the local clock shifts by the DST offset."""
    dst = timelapse_runs["dst"]
    assert dst["ok"] and dst["files"] == 24, dst
    assert dst["first_moment"][0] == "2026-10-18" and dst["last_moment"][0] == "2026-11-01"
    assert len(set(dst["utc_times"])) == 1, dst["utc_times"]
    steps = dst["luma_steps"]
    assert max(steps) <= DST_STEP_BOUND, dst
    assert dst["clock_back"]


def test_a_4k_picture_keeps_the_low_suns_horizon_band_within_1080ps_look(
        tmp_path: Path) -> None:
    """#733: the review read the horizon band about 9 levels darker at 4K and blamed Qt's
    pixel-sized glow. Measured on this shot, the glow changes nothing; the difference is
    screen-space ambient occlusion, whose scene-unit radius covers more pixels at a bigger
    picture. A capture scales that radius by its height: the band read -1.75 / -2.82 (mean
    / worst bucket) before and -0.41 / -0.53 after, at the family garden's sunset."""
    result = drive(tmp_path, "picture")
    assert result["sizes"] == {"1080": [1920, 1080], "2160": [3840, 2160]}
    assert abs(result["band_delta"]) <= PICTURE_BAND_DELTA, result
    assert abs(result["worst_bucket"]) <= PICTURE_BUCKET_DELTA, result
    assert abs(result["sky_delta"]) <= PICTURE_SKY_DELTA, result
    assert result["ao_scale_at_2160"] == 0.5, "the radius is halved for twice the height"
    assert result["ao_scale_after_4k"] == 1.0, "and the view's own look is back"


def test_the_agents_picture_refuses_cleanly_and_changes_nothing(tmp_path: Path) -> None:
    result = drive(tmp_path, "agent")
    assert result["while_warming"]["refused"] == "warming_up"
    assert result["while_warming"]["ms"] < 100.0, "at once, not after a timeout"
    assert result["in_plan_mode"]["refused"] == "not_open"
    own, other = result["own"], result["other"]
    assert own["image_width_px"] == 640 and other["image_width_px"] == 1024
    assert other["eye"] == [1000.0, -900.0, 700.0] and other["fov_deg"] == 40.0
    assert own["plan_date"] == other["plan_date"] == "2026-06-21"
    assert own["time_of_day"] == "15:00" and own["sun_elevation_deg"] > 0.0
    for kept in ("camera_kept", "clock_kept", "undo_kept", "dirty_kept"):
        assert result[kept], kept
    assert result["back_in_3d"] == 640, "and it works again when the view is back"
