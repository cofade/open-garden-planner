"""The looks, the sky and the wind on the real engine (Phase 17 L1.4, #385) — render tier.

Opt-in (``OGP_RENDER3D=1``; it opens windows on the desktop). The default tier pins
every decision (``test_scene3d_look.py``, ``test_view3d_look_controller.py``,
``test_view3d_looks.py``); here the ENGINE is asked whether the frames say the same:

- the production Beauty Board (``scripts/render_beauty_board.py``) is run as a child on
  the GPU, on the software adapter (WARP — what the workspace's compatibility mode
  uses) and on the large bench plan, and its ``metrics.json`` is judged: gates G2
  (shadow IoU, perspective, the preset's cascades), G3 (night against noon), G4 (the
  sky's sun azimuth), G5 (fog meets sky; no speckle), G8 (no light probe on WARP),
  G10 (the board runs end to end);
- ``view3d_looks_driver.py`` shows a window for what needs one: the sky rebuilt three
  times and looked at again after the old textures are gone, the wind's clock on the
  real render loop (G7), the product's ``LookController`` on a real host (G4's count,
  G1's direction, G8), and the memory soak over twenty sun changes with its
  positive control (G4).

    # Windows (Git Bash) - one driver at a time; the one wall-clock bound is ``perf``
    OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest -n 0 -m "perf or not perf"
        tests/integration/test_view3d_looks_render.py      (one command line)

NOT box casters — exempt from the shadow gate by ADR-059's divergence table: closed
fences, and the built-world kinds listed there. The gate's caster is a solid box.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scripts import board_probes as probes
from scripts import render_beauty_board as beauty_board

from open_garden_planner.core.scene3d import SunState
from open_garden_planner.core.scene3d.look import (
    PRESET_SPECS,
    PRESETS,
    look_for,
    moon_travel_scene,
    sky_is_stale,
)
from tests.integration import view3d_looks_driver as driver
from tests.integration.quick3d_render_support import (
    QML_SOURCE,
    REPO,
    driver_messages,
    keep_artifacts,
    load_rgb,
    render_env,
    render_tier,
)

pytestmark = render_tier

BOARD = REPO / "scripts" / "render_beauty_board.py"
DRIVER = REPO / "tests" / "integration" / "view3d_looks_driver.py"
TIMEOUT_S = 840
#: The render tier's frame size: small enough for a software rasteriser.
SIZE = "640x360"

# ── the bounds, each with what was measured (RTX 4070 / WARP, 2026-10-12, 640 x 360) ──
#: G2. Issue #385: IoU >= 0.85 at 15 / 35 / 60 degrees. Measured, perspective with the
#: preset's cascades: 0.921-0.986 on the GPU (the lowest: low at 15 degrees, one cascade).
MIN_IOU = 0.85
#: G2 on WARP (no sky: a flat fill lights the shadow) holds the same bound at every preset;
#: measured 0.919-0.986 (640 x 360, 2026-10-12). G8 asked only for a relaxed G2 there.
#: G3. Night's mean LUMINANCE (linear light) under a quarter of noon's, same shot and plan.
MAX_NIGHT_OVER_NOON = 0.25
#: G4. The spike's bound for the sky probe; measured here 0.03 degrees.
MAX_SKY_ERROR_DEG = 6.0
#: G4's instrument (#717): the disc finder must place the disc within this of the solar
#: position at 6, 12, 30 and 60 degrees, on both skies (the white-plateau path).
MAX_DISC_ERROR_DEG = 0.25
#: 4 sun elevations x 3 azimuths x 2 offsets (#717).
SKY_VIEW_COUNT = 24
#: The set-sun probe's bound (#695): a sky row may not dip more than this under its rows.
MAX_SKY_DUSK_DIP = 10.0
#: G5. The largest change of the row-mean luma across 0.15 degrees at the horizon, the
#: depth of a thin dark line there, the height of a thin bright one — at eye height, per
#: mood and preset, within 0.4 degrees of the horizon. Measured: step <= 3.5 at 640 x 360
#: (4.2 at 960 x 540), dip <= 1.9 (3.2), ridge <= 0.8 (1.0); on the software adapter,
#: where the plain sky IS the fog's colour, 0.15 / 0.03 / 0.02. The spike measured a
#: step of 3.6 at most, by day. Before L1.4's round 1 the night step was 10.5 (high)
#: and 21.2 (low).
#: The CLEAR look's per-mood step, gated where the board reports it (#696: the low-preset
#: sunset read 3.13, above the 3.0 that only `--horizon`'s far rows used): 3.6, the same
#: re-derived bound as `HORIZON_STEP_BOUND` at 640 x 360 (#714; ADR-059's addendum).
#: The cloudy weathers keep the 6.0 above — this package measured the clear look's rows,
#: not theirs.
MAX_CLEAR_HORIZON_STEP = 3.6
MAX_HORIZON_STEP, MAX_HORIZON_DIP, MAX_HORIZON_RIDGE = 6.0, 4.5, 2.5
#: G4. Committed memory per sun change, second half of twenty (Theil-Sen) — the bound was
#: registered before the first run (the driver says how it moved with the sky's size).
SOAK_BOUND_MB, SOAK_CONTROL_MB = driver.SOAK_BOUND_MB, driver.SOAK_CONTROL_MB


def _run(command: list[str], out: Path, **env: str) -> subprocess.CompletedProcess[str]:
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        command, env=render_env(out, **env), capture_output=True, text=True, timeout=TIMEOUT_S,
        cwd=REPO)
    keep_artifacts(out, proc)
    return proc


def run_board(out: Path, *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    proc = _run([sys.executable, str(BOARD), "--out", str(out), "--size", SIZE,
                 "--watchdog-s", str(TIMEOUT_S - 60), *arguments], out)
    file = out / "metrics.json"
    return proc, (json.loads(file.read_text(encoding="utf-8")) if file.is_file() else {})


def run_scenario(out: Path, scenario: str, **arguments: str
                 ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    command = [sys.executable, str(DRIVER), "--out", str(out), "--scenario", scenario,
               "--watchdog-s", str(TIMEOUT_S - 60)]
    for key, value in arguments.items():
        command += ["--arg", f"{key}={value}"]
    # the children present by timer, so that no scenario depends on whether the
    # machine's display is awake (the workspace gate's rule, ogp-3d-renderer 13)
    proc = _run(command, out, QT_D3D_NO_VBLANK_THREAD="1")
    file = out / "result.json"
    result = json.loads(file.read_text(encoding="utf-8")) if file.is_file() else {}
    if result:
        result["qt_messages"] = driver_messages(proc.stderr)
    return proc, result


def _report(proc: subprocess.CompletedProcess[str], out: Path, log: str = "board.log") -> str:
    file = out / log
    tail = file.read_text(encoding="utf-8", errors="replace")[-2500:] if file.is_file() else "<no log>"
    return f"exit {proc.returncode}\n--- stderr ---\n{proc.stderr[-2000:]}\n--- {log} ---\n{tail}"


def _ok_board(run: tuple[subprocess.CompletedProcess[str], dict[str, Any]], out: Path) -> dict[str, Any]:
    proc, metrics = run
    assert proc.returncode == 0 and metrics.get("status") == "ok", _report(proc, out)
    return metrics


def _ok_scenario(run: tuple[subprocess.CompletedProcess[str], dict[str, Any]], out: Path
                 ) -> dict[str, Any]:
    proc, result = run
    assert proc.returncode == 0 and result.get("status") == "ok", _report(proc, out, "render.log")
    messages = result["qt_messages"]
    assert messages["errors"] == [] and messages["warnings"] == [], messages
    data: dict[str, Any] = result["data"]
    assert data["health"]["ok"] and data["health"]["slots_off_gui_thread"] == 0, data["health"]
    return data


# ── the board on the GPU ─────────────────────────────────────────────────────


#: The board of each sky model, run once per session (L7, #391: every board gate holds for
#: BOTH skies — the painted one of L1–L5 and the Qt 6.12 atmosphere — and the two are
#: compared with each other below).
_BOARDS: dict[str, tuple[dict[str, Any], Path]] = {}
SKY_MODELS = ("painted", "atmosphere")


def board_for(model: str, tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Path]:
    if model not in _BOARDS:
        out = tmp_path_factory.mktemp(f"looks-{model}") / "board"
        _BOARDS[model] = _ok_board(run_board(
            out, "--presets", ",".join(PRESETS), "--shots", "noon,december_noon,night", "--iou",
            "--orient", "--horizon", "--moods", "--dusk", "--fence", "--edge", "--sky", model),
            out), out
    return _BOARDS[model]


@pytest.fixture(scope="module", params=SKY_MODELS)
def board(request: pytest.FixtureRequest,
          tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Path]:
    return board_for(str(request.param), tmp_path_factory)


def test_the_production_board_runs_end_to_end_and_every_truth_row_is_green(board) -> None:
    """Gate G10. The production pipeline — snapshot, builders, sink, host, looks — from a
    plan on disk to PNGs and numbers, with nothing Qt objected to."""
    metrics, out = board
    assert metrics["sky_model"] in SKY_MODELS, "the board says which sky drew it"
    assert metrics["graphics"]["api"] in ("Direct3D11", "OpenGL", "Vulkan", "Metal", "Direct3D12")
    assert metrics["qt_messages"]["counts"]["error"] == 0, metrics["qt_messages"]
    assert metrics["qt_messages"]["counts"]["warning"] == 0, metrics["qt_messages"]
    rows = metrics["shots"]
    assert [(row["shot"], row["preset"]) for row in rows] == [
        (shot, preset) for preset in PRESETS for shot in ("noon", "december_noon", "night")]
    for row in rows:
        assert row["sun_date"] == row["build_date"], row    # the plan as it stands on that day
        assert row["build_failures"] == [] and row["parts"] > 80, row
        assert row["sky_builds"] == 1, "one sky per frame, built for that frame's sun"
        assert (out / row["file"]).is_file()
        assert 5.0 < row["mean_luma"] < 235.0, row          # neither black nor white
        assert row["clipped_pct"] < 2.0, row
    assert {row["sun_date"] for row in rows} == {"2026-06-21", "2026-12-21"}
    # the date row can fail: build_date is read back from the records rendered, and two
    # dates that grow the plants differently must give two different models
    digests = {day: block["digest"] for day, block in metrics["builds"].items()}
    assert digests["2026-06-21"] != digests["2026-12-21"], digests
    assert metrics["orientation"]["ok"] is True, metrics["orientation"]
    assert metrics["orientation"]["ncc"]["identity"] > 0.6
    assert metrics["probe_restore_frame_diff"] == 0.0, "a probe left something behind"
    assert metrics["wind_time"] == 0.0


def test_distant_horizon_rows_reach_the_real_fog_distances(board) -> None:
    metrics, _out = board
    from open_garden_planner.core.scene3d.camera import DEFAULT_PITCH_DEG

    for preset in PRESETS:
        rows = metrics["horizon"]["distance_rows"][preset]
        assert len(rows) == 8
        assert {row["distance_m"] for row in rows} == {67, 202, 403, 600}
        assert {row["pitch_deg"] for row in rows} == {15.0, DEFAULT_PITCH_DEG}
        # #714: the bound is the board's own, re-derived from this scene's rows (3.6);
        # the render tier does not carry a second copy of the number.
        assert all(row["ok"] for row in rows), rows
        assert max(row["step"] for row in rows) <= beauty_board.HORIZON_STEP_BOUND, rows


def test_the_analysis_board_finds_its_probe_pin_on_the_built_world(tmp_path) -> None:
    """#704: the built-world plan's noon camera is far enough that the product's
    52 cm pin read 38 magenta pixels, under the board's 50 px gate, so ``--analysis``
    raised before writing any sun-hours row. The pin is sized from that camera."""
    out = tmp_path / "analysis-built"
    metrics = _ok_board(run_board(out, "--plan", str(REPO / "tests/fixtures/plans/bench_built.ogp"),
                                  "--presets", "high", "--shots", "noon", "--analysis"), out)
    rows = [row for row in metrics["analysis"] if row["variant"] == "sunhours"]
    assert len(rows) == 1, metrics["analysis"]
    row = rows[0]
    assert row["pin_px"] >= 50, row
    assert row["pin_height_cm"] > 52.0, "the pin was not sized for this camera"
    assert (out / row["file"]).is_file()


def test_far_plan_preserves_shadows_and_has_no_ao_line(tmp_path) -> None:
    """#624: pixels at 2x/4x the 50x30 m bench framing, not QML text."""
    out = tmp_path / "far-plan"
    metrics = _ok_board(run_board(out, "--plan", str(REPO / "tests/fixtures/plans/bench_large.ogp"),
                                  "--presets", "high", "--shots=", "--far-plan"), out)
    rows = metrics["far_plan"]
    assert {row["framing_multiple"] for row in rows} == {2.0, 4.0}
    for row in rows:
        assert row["ground_samples"] > 1000 and row["shadowed_samples"] > 100, row
        assert row["shadow_delta_max"] > 8.0, row
        assert row["outer_rows"]["step"] <= 3.0, row


def test_lawn_blades_do_not_add_dark_stubble_to_the_same_high_look(tmp_path) -> None:
    """#604: isolate blades from High's own AO, cascades and ground lighting."""
    out = tmp_path / "lawn"
    _ok_board(run_board(out, "--presets", "low,high", "--shots", "walk"), out)
    hidden = tmp_path / "hidden-blades-qml"
    shutil.copytree(QML_SOURCE, hidden)
    scene = hidden / "Garden.qml"
    source = scene.read_text(encoding="utf-8")
    assert "root.lawnBlades" in source
    scene.write_text(source.replace("root.lawnBlades", "false"), encoding="utf-8")
    reference = tmp_path / "lawn-high-off"
    _ok_board(run_board(reference, "--presets", "high", "--shots", "walk",
                        "--qml-dir", str(hidden)), reference)
    low = load_rgb(out / "walk_low.png")
    on, off = load_rgb(out / "walk_high.png"), load_rgb(reference / "walk_high.png")
    height, width = low.shape[:2]
    # A fixed region of the documented walk shot: the lawn beyond the bench,
    # excluding the foreground herb bush. Low's sunlit green pixels define it;
    # both High frames are judged against the SAME mask, independent of their answer.
    mask = np.zeros((height, width), dtype=bool)
    mask[round(height * 350 / 540):round(height * 430 / 540),
         round(width * 550 / 960):round(width * 670 / 960)] = True
    low_luma = probes.luma(low)
    mask &= ((low_luma > 175.0) & (low_luma < 205.0)
             & (low[..., 1] > 1.6 * low[..., 0]) & (low[..., 1] > 1.7 * low[..., 2]))
    assert int(mask.sum()) > 150, "the instrument must see sunlit lawn"
    with_blades, without = probes.luma(on)[mask], probes.luma(off)[mask]
    mean_delta = float(with_blades.mean() - without.mean())
    dark_share_delta = float((with_blades < 150.0).mean() - (without < 150.0).mean())
    assert abs(mean_delta) <= 3.0, (mean_delta, dark_share_delta)
    assert dark_share_delta <= 0.03, (mean_delta, dark_share_delta)


def test_the_shadow_of_a_box_matches_the_2d_shadow_in_perspective_with_cascades(board) -> None:
    """Gate G2. The L0 number was orthographic and without cascades; this is the view
    people look at — the preset's own cascades, map, filter and bias — at every preset."""
    metrics, _out = board
    measured = {}
    for preset in PRESETS:
        block = metrics["shadow_iou"][preset]
        assert block["view"] == "perspective"
        for elevation in ("15deg", "35deg", "60deg"):
            result = block["results"][elevation]
            assert result["cascades"] == PRESET_SPECS[preset].shadow_cascades >= 1
            measured[(preset, elevation)] = result["iou"]
            assert result["analytic_cells"] > 500, result
    assert min(measured.values()) >= MIN_IOU, measured


def test_night_is_under_a_quarter_of_noons_luminance_on_the_same_shot(board) -> None:
    """Gate G3 (render half). One camera, one date; only the light differs."""
    metrics, _out = board
    for preset in PRESETS:
        moods = metrics["moods"][preset]
        ratio = moods["night_over_noon"]["luminance"]
        assert ratio < MAX_NIGHT_OVER_NOON, (preset, moods["night_over_noon"])
        assert moods["night"]["night"] is True and moods["noon"]["night"] is False
        # no mood contradicts its time of day: the lower the sun, the darker the GARDEN (the
        # rows below the horizon), on both skies
        names = ("noon", "golden_hour", "sunset", "night")
        ground = [moods[name]["ground_luminance"] for name in names]
        assert ground == sorted(ground, reverse=True), (preset, ground)
        if metrics["sky_model"] == "painted":
            # and the whole frame too. Not on the atmosphere (L7, #391, 3D review): its light
            # sits toward a low sun, so a frame FACING it reads sunset up to 1.9 % above
            # golden hour while the garden below darkens 23-25 %, as under the painted sky
            order = [moods[name]["mean_luminance"] for name in names]
            assert order == sorted(order, reverse=True), (preset, order)


def test_the_sky_draws_its_sun_at_the_solar_azimuth(board) -> None:
    """Gate G4. The disc is read 25 degrees off-centre, left and right, for a sun in
    the east, the south and the west."""
    metrics, _out = board
    sky = metrics["sky"]
    assert sky["ok"] is True and len(sky["views"]) == SKY_VIEW_COUNT, sky
    assert sky["max_abs_error_deg"] < MAX_SKY_ERROR_DEG
    assert sky["max_abs_elevation_error_deg"] < MAX_DISC_ERROR_DEG, sky
    for view in sky["views"].values():
        assert view["found"], view
        assert abs(view["elevation_deg"] - view["sun_elev"]) < MAX_DISC_ERROR_DEG, view


def test_fog_meets_the_sky_at_every_preset_and_in_every_mood(board) -> None:
    """Gate G5. At eye height, looking away from the sun and across it."""
    metrics, _out = board
    horizon = metrics["horizon"]
    worst = horizon["max"]
    assert worst["step"] <= MAX_HORIZON_STEP, horizon
    assert worst["dip"] <= MAX_HORIZON_DIP and worst["ridge"] <= MAX_HORIZON_RIDGE, horizon
    for preset in PRESETS:
        assert set(horizon[preset]) == {"noon", "golden_hour", "sunset", "night"}
        for mood_name, mood in horizon[preset].items():
            assert mood["away"]["judged_rows"] >= 5 and mood["across"]["judged_rows"] >= 5
            # #696: the per-mood step was ungated while the low-preset sunset read 3.13
            for label in ("away", "across"):
                assert mood[label]["step"] <= MAX_CLEAR_HORIZON_STEP, (
                    preset, mood_name, label, mood[label])


def test_dusk_fades_and_sunset_is_no_cliff(board) -> None:
    """Review P1 (the twilight ramp). The evening of the golden-hour shot from a 6° sun
    to a −7° one, one camera: the light never rises, and crossing sunset (0.6° -> 0.4°,
    where the sun's key light goes as the 2D shadows do) is no larger a step than the
    largest half degree of the day ramp before it. Before the ramp: 0.116 -> 0.034
    (low), 3.0 to 3.4 times the day ramp's largest step."""
    metrics, _out = board
    for preset in PRESETS:
        dusk = metrics["dusk"][preset]
        assert len(dusk["rows"]) == 16, dusk
        assert dusk["monotone"], (preset, dusk["rises"])
        assert dusk["sunset_step"] <= dusk["day_ramp_max_step"], (preset, dusk)
        night = [row for row in dusk["rows"] if row["target"] <= -6.0]
        assert all(row["night"] for row in night) and not any(
            row["night"] for row in dusk["rows"] if row["target"] > -5.9)
        # The sky-facing set-sun probe (#695): the meadow camera hid the sun behind the
        # poplar; a black disc in this window went unseen for three reviews.
        assert dusk["sky_dusk_ok"], (preset, dusk["sky_dusk"])
        assert len(dusk["sky_dusk"]) == 5, dusk["sky_dusk"]
        assert min(row["dip_luma"] for row in dusk["sky_dusk"]) >= -MAX_SKY_DUSK_DIP, dusk["sky_dusk"]


#: Review P1 (#529): the picket moiré at low. ``alias_error`` (``board_probes.
#: thin_geometry_moire``): the fence's mean luma error against the same view rendered at
#: twice the size and filtered down. Measured (960 x 540): FXAA at low 20.04, 2x MSAA
#: 11.96, 4x MSAA (low = medium's anti-aliasing) 7.17; medium 7.17, high 6.79, ultra 5.40.
#: Low may not alias more than medium by more than this.
MAX_LOW_OVER_MEDIUM_ALIAS = 1.5
#: And an absolute ceiling, because low and medium now share 4x MSAA: if both regressed
#: together the relative pin alone would pass (re-check). 2x MSAA measured 11.96 (960 x 540)
#: and 14.54 (640 x 360), 4x 6.22 / 8.10.
MAX_LOW_ALIAS = 11.0


def test_the_low_preset_does_not_alias_the_pickets(board) -> None:
    metrics, _out = board
    moire = metrics["fence_moire"]
    assert moire["fences"] >= 1
    low, medium = moire["low"]["alias_error"], moire["medium"]["alias_error"]
    assert low is not None and medium is not None, moire
    assert low <= medium + MAX_LOW_OVER_MEDIUM_ALIAS, moire
    assert low <= MAX_LOW_ALIAS, moire
    assert moire["low"]["dark_share"] <= moire["medium"]["dark_share"] + 0.02, moire


#: Review P2: the plan rectangle meets the meadow without a step (luma) on a plan with
#: nothing on it, in every view along its west and south edge (``plan_edge``). Measured
#: (960 x 540, low / high): the meadow's material on both, at most 0.21; the plan ground's
#: old material (roughness 0.92, specular 0.2) up to 4.65 — the positive control.
MAX_PLAN_EDGE_STEP = 1.0
#: 3D review of #388: a thin LINE on the edge, which the fitted step cannot see. With the
#: meadow 5 cm under the plan, ambient occlusion drew one of +-14 luma along every edge
#: (the step read 0.45); in the plan's plane, 0.09 (the reviewer's measurement).
MAX_PLAN_EDGE_LINE = 2.0


def test_the_plan_ground_meets_the_meadow_without_a_step(board) -> None:
    metrics, _out = board
    edge = metrics["plan_edge"]
    assert edge["max_abs_step"] <= MAX_PLAN_EDGE_STEP, edge
    assert edge["max_line"] <= MAX_PLAN_EDGE_LINE, edge
    for preset in PRESETS:
        for mood in ("golden_hour", "noon"):
            rows = edge[preset][mood]
            assert len(rows) == 4 and all(row["stations"] == 5 for row in rows.values()), rows


# ── L7 (#391): the atmosphere sky against the painted one ─────────────────────

#: The night is the painted night: the atmosphere's weight is 0 from the end of civil
#: twilight (``atmosphere_properties``). Measured 2026-11-03 (640 x 360, RTX 4070), the
#: night rows' mean luma: 53.61 / 53.60 at low, 51.32 / 51.31 at high.
MAX_NIGHT_LUMA_DIFFERENCE = 0.5
#: By day the atmosphere IS drawn: the sky probe's views (a 12° sun 25° off centre) differ
#: in their top third by 17.7 per channel (all three suns, same date).
MIN_DAY_SKY_DIFFERENCE = 5.0


def _night_and_sky(model: str, out: Path) -> tuple[dict[str, Any], Path]:
    """A small board of its own (the night shot, the sky probe): the comparison does not
    hang on the full board's distant-horizon rows (#714)."""
    return _ok_board(run_board(out, "--presets", ",".join(PRESETS), "--shots", "night",
                               "--orient", "--sky", model), out), out


def test_the_atmosphere_keeps_the_painted_night_and_draws_its_own_day(tmp_path: Path) -> None:
    painted, painted_out = _night_and_sky("painted", tmp_path / "painted")
    atmosphere, atmosphere_out = _night_and_sky("atmosphere", tmp_path / "atmosphere")
    for metrics in (painted, atmosphere):   # the sky's sun where the solar position puts it
        assert metrics["sky"]["ok"] and metrics["sky"]["max_abs_error_deg"] < MAX_SKY_ERROR_DEG
        for view in metrics["sky"]["views"].values():
            assert abs(view["elevation_deg"] - view["sun_elev"]) < MAX_DISC_ERROR_DEG, view
    assert (painted["sky_model"], atmosphere["sky_model"]) == ("painted", "atmosphere")
    nights = {model: {row["preset"]: row["mean_luma"] for row in metrics["shots"] if row["shot"] == "night"}
              for model, metrics in (("painted", painted), ("atmosphere", atmosphere))}
    for preset in PRESETS:
        assert abs(nights["painted"][preset] - nights["atmosphere"][preset]) <= MAX_NIGHT_LUMA_DIFFERENCE, nights
    view = "sky_12_180_-25.png"
    day_painted, day_atmosphere = load_rgb(painted_out / view), load_rgb(atmosphere_out / view)
    rows = day_painted.shape[0] // 3
    difference = float(np.abs(day_painted[:rows].astype(np.float64) - day_atmosphere[:rows]).mean())
    assert difference >= MIN_DAY_SKY_DIFFERENCE, difference


def test_the_horizon_hue_seam_is_reported(board) -> None:
    """Review P2: the luma rows cannot see a HUE seam (grey-blue sky over lime meadow);
    ``delta_e`` (CIE76) is reported for every mood — not gated (an owner question)."""
    metrics, _out = board
    for preset in PRESETS:
        for mood in metrics["horizon"][preset].values():
            assert mood["away"]["delta_e"] is not None and mood["across"]["delta_e"] is not None


# ── speckle: the bound and its positive control ──────────────────────────────

#: Isolated dark pixels at 640 x 360, medium. The spike bounded its own board at 170
#: (38 / 42 clean, 737 / 700 with sharpening 0.08; noon / December noon). The PRODUCTION
#: scene measures 194 / 2 clean and 315 / 150 sharpened: its noon count is the far
#: picket fence — shaded pickets against the lit meadow behind them, 190 of the 194, the
#: same with and without sharpening and so not the look's — and its December frame has
#: almost none. The bounds are per shot, each a third above what was measured; the gate
#: for the LOOK is the December frame, where the control is 75 times the clean count.
#: Re-measured 2026-10-26 (#388): the December frame reads 33 on master and 32 with L4 —
#: L3's forged crowns (#387) show their own shade through gaps between leaves, the tall
#: columnar tree most; none is a sharpening overshoot. A third above: 44. Noon reads
#: 162 on master and 191 with L4, inside its bound.
MAX_SPECKLES = {"noon": 260, "december_noon": 44}
MIN_CONTROL_EXTRA = 80


@pytest.fixture(scope="module")
def speckles(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, int]]:
    base = tmp_path_factory.mktemp("speckle")
    sharpened = base / "qml"
    shutil.copytree(QML_SOURCE, sharpened)
    scene = sharpened / "Garden.qml"
    text = scene.read_text(encoding="utf-8")
    assert "sharpnessAmount: 0.0" in text, "the control no longer finds the sharpening in Garden.qml"
    scene.write_text(text.replace("sharpnessAmount: 0.0", "sharpnessAmount: 0.08"), encoding="utf-8")
    out: dict[str, dict[str, int]] = {}
    for name, extra in (("clean", ()), ("sharpened", ("--qml-dir", str(sharpened)))):
        metrics = _ok_board(run_board(base / name, "--presets", "medium", "--shots",
                                      "noon,december_noon", *extra), base / name)
        out[name] = {row["shot"]: row["isolated_dark_px"] for row in metrics["shots"]}
    return out


def test_no_isolated_dark_pixel_speckle_and_the_gate_can_fire(speckles) -> None:
    """Gate G5. Sharpening at 0.08 overshot every thin lit edge into near-black dots;
    the scene file has none. The control — the same board with 0.08 — must show them."""
    clean, sharpened = speckles["clean"], speckles["sharpened"]
    assert set(clean) == set(MAX_SPECKLES)
    for shot, bound in MAX_SPECKLES.items():
        assert clean[shot] <= bound, (shot, clean)
        assert sharpened[shot] >= clean[shot] + MIN_CONTROL_EXTRA, (shot, clean, sharpened)
        assert sharpened[shot] > bound, f"{shot}: the control did not fire ({sharpened})"


# ── the software fallback (gate G8) ──────────────────────────────────────────


@pytest.fixture(scope="module")
def board_software(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Path]:
    out = tmp_path_factory.mktemp("looks") / "software"
    return _ok_board(run_board(out, "--software", "--presets", ",".join(PRESETS), "--shots",
                               "noon,night", "--iou", "--orient", "--horizon", "--moods"), out), out


def test_the_software_fallback_builds_no_light_probe_and_still_tells_the_truth(board_software) -> None:
    """Gate G8. No sky texture (count: 0 in every frame), a plain background and a flat
    fill — and the shadows are where the 2D geometry puts them, north is up, the fog
    meets the plain sky, night is night."""
    metrics, _out = board_software
    assert metrics["software"] is True and metrics["sky_light"] is False
    if sys.platform == "win32":
        assert "Basic Render" in str(metrics["graphics"]["adapter"]), metrics["graphics"]
    assert all(row["sky_builds"] == 0 for row in metrics["shots"]), "a light probe on WARP"
    assert metrics["sky"] == {"skipped": "no sky texture on a software adapter"}
    assert metrics["qt_messages"]["counts"]["error"] == 0
    measured = {}
    for preset, block in metrics["shadow_iou"].items():   # G2 on WARP: perspective, cascades
        assert block["view"] == "perspective"
        for elevation in ("15deg", "35deg", "60deg"):
            result = block["results"][elevation]
            assert result["cascades"] == PRESET_SPECS[preset].shadow_cascades >= 1
            measured[(preset, elevation)] = result["iou"]
    assert len(measured) == 12 and min(measured.values()) >= MIN_IOU, measured
    assert metrics["orientation"]["ok"] is True
    for preset in PRESETS:
        assert metrics["moods"][preset]["night_over_noon"]["luminance"] < MAX_NIGHT_OVER_NOON
    worst = metrics["horizon"]["max"]
    assert worst["step"] <= MAX_HORIZON_STEP and worst["dip"] <= MAX_HORIZON_DIP, metrics["horizon"]
    assert metrics["probe_restore_frame_diff"] == 0.0


def test_a_frame_on_the_software_adapter_builds_no_sky_step(board_software) -> None:
    """Gate G8, by structure: no frame of the fallback has a sky-build step at all."""
    metrics, _out = board_software
    assert all("sky_build" not in row["breakdown_ms"] for row in metrics["shots"])


@pytest.mark.perf   # a wall-clock bound (ADR-058): run with -m perf, or "perf or not perf"
def test_a_frame_on_the_software_adapter_costs_no_probe(board_software) -> None:
    """Gate G8, in time: a light probe on WARP costs seconds (9-13 s on this machine,
    40-85 s on a CI runner). A frame of the fallback must cost nothing like one."""
    metrics, _out = board_software
    slowest = max(row["open_ms"] for row in metrics["shots"])
    assert slowest < 6000.0, [(row["shot"], row["preset"], row["open_ms"]) for row in metrics["shots"]]


# ── the large bench plan (gate G10) ──────────────────────────────────────────


def test_the_board_runs_on_the_large_bench_plan(tmp_path: Path) -> None:
    out = tmp_path / "large"
    metrics = _ok_board(run_board(out, "--plan", str(REPO / "tests" / "fixtures" / "plans" /
                                                     "bench_large.ogp"),
                                  "--presets", "high", "--shots", "noon,golden_hour"), out)
    assert metrics["qt_messages"]["counts"]["error"] == 0
    for row in metrics["shots"]:
        assert row["build_failures"] == [] and row["parts"] > 300 and row["sky_builds"] == 1, row
        assert row["sun_date"] == row["build_date"]


# ── a shown window: the sky ──────────────────────────────────────────────────


def _sky_view(shape: tuple[int, ...]) -> probes.Pinhole:
    eye, target = driver.sky_camera()
    return probes.Pinhole(eye, target, driver.SKY_FOV, (shape[1], shape[0]))


def test_a_sky_rebuilt_three_times_is_still_the_sky_after_the_old_ones_are_gone(tmp_path: Path) -> None:
    """Gate G4, and the rule the ground bake found: a Texture loses its data when a data
    object it held EARLIER is destroyed. A -> B -> C with a frame after each, then a
    frame after the old Textures and their data are deleted: the same sky as before —
    its sun where the solar azimuth says, not black, not white."""
    out = tmp_path / "sequence"
    data = _ok_scenario(run_scenario(out, "sky_sequence"), out)
    assert [step["sky_builds"] for step in data["steps"]] == [1, 2, 3]
    assert [step["engine_builds"] for step in data["steps"]] == [1, 2, 3]
    assert data["textures_alive"] == [False, False, True], "the old Textures are destroyed"
    assert data["data_alive"] == [False, False, True], "… each TOGETHER with its own data object"
    frames = {}
    for step in data["steps"]:      # ONE camera: the disc must be where each sun stands
        rgb = load_rgb(out / step["file"])
        frames[step["name"]] = rgb
        found = probes.sun_disc(rgb, _sky_view(rgb.shape))
        assert found["found"], (step["name"], found)
        error = probes.bearing_error_deg(found["bearing_deg"], step["azimuth"])
        assert abs(error) < MAX_SKY_ERROR_DEG, (step["name"], found)
        assert abs(found["elevation_deg"] - driver.SKY_ELEVATION) < 3.0, (step["name"], found)
        assert 40.0 < float(probes.luma(rgb).mean()) < 235.0, step["name"]
    # three different skies were shown: A, B and C are not one frame
    assert float(np.abs(frames["A"] - frames["B"]).mean()) > 2.0
    assert float(np.abs(frames["B"] - frames["C"]).mean()) > 0.5
    for name in ("after_delete", "later"):
        rgb = load_rgb(out / data[name])
        assert float(np.abs(rgb - frames["C"]).mean()) < 0.5, f"{name}: the sky changed"
        found = probes.sun_disc(rgb, _sky_view(rgb.shape))
        assert found["found"] and abs(probes.bearing_error_deg(
            found["bearing_deg"], driver.SEQUENCE_AZIMUTHS[-1])) < MAX_SKY_ERROR_DEG


#: Mean absolute difference (0-255 per channel) below which two frames are the same sky;
#: the senior review of L7 measured 0.00 for a live host against a fresh one at the same
#: sun and model; two different skies of the sequence read 5.8 (painted, 160 against 215
#: degrees: 6.06) to 19.3 apart, a cloud deck against the clear sky 38.7.
SAME_SKY = 0.5
OTHER_SKY = 3.0


def test_the_atmosphere_on_a_live_host_is_the_fresh_hosts_sky(tmp_path: Path) -> None:
    """L7 (#391), senior review: the board renders a fresh host per frame and the
    self-test one frame, so the live paths were ungated — the sky-view table refilled
    in place for a new sun, a switch to the painted sky and back (PF-E3D-16 across it),
    the sky material re-attached after the top-down view, a cloud deck coming and going.
    Every frame of ONE host must be the fresh host's frame for that (sun, model, cloud),
    also after the old Textures were deleted."""
    out = tmp_path / "atmosphere"
    data = _ok_scenario(run_scenario(out, "atmosphere_sequence"), out)
    fresh = {key: load_rgb(out / row["file"]).astype(float) for key, row in data["fresh"].items()}
    for row in data["fresh"].values():   # a fresh host's own frame stays its frame
        before, after = load_rgb(out / row["file"]), load_rgb(out / row["after"])
        assert float(np.abs(before.astype(float) - after).mean()) < SAME_SKY, row["name"]

    def diff(rgb: Any, key: str) -> float:
        return float(np.abs(rgb - fresh[key]).mean())

    for row in data["steps"]:
        key = f"{row['model']}_{int(row['azimuth'])}" + ("_overcast" if row["name"].endswith("_overcast") else "")
        for frame in ("file", "after"):
            rgb = load_rgb(out / row[frame]).astype(float)
            assert diff(rgb, key) < SAME_SKY, (row["name"], frame, diff(rgb, key))
        assert row["atmosphere_built"] is (row["model"] == "atmosphere"), row
    # the references are told apart, so "the same sky" above is not a blind comparison
    assert diff(fresh["atmosphere_160"], "atmosphere_200") > OTHER_SKY
    assert diff(fresh["painted_160"], "painted_215") > OTHER_SKY
    assert diff(fresh["atmosphere_215"], "painted_215") > OTHER_SKY
    assert diff(fresh["atmosphere_200_overcast"], "atmosphere_200") > OTHER_SKY
    # the painted sky lights the garden under both (PF-E3D-17), so under the horizon the
    # two are one picture. Without this a lost probe passes above: the references lose it too
    rows = fresh["painted_215"].shape[0]
    horizon = rows / 2.0 * (1.0 + math.tan(math.radians(driver.SKY_PITCH))
                            / math.tan(math.radians(driver.SKY_FOV / 2.0)))
    ground = int(math.ceil(horizon)) + 1
    assert ground < rows, "the sequence's view must show ground"
    assert np.abs(fresh["atmosphere_215"][ground:] - fresh["painted_215"][ground:]).max() == 0.0, (
        "the garden is lit differently under the two skies")
    assert data["health"]["ok"], data["health"]


def _engine(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    east, north, up = vector
    return (east, up, -north)


@pytest.mark.parametrize("software", [False, True], ids=["gpu", "software"])
def test_the_look_controller_on_a_real_host_through_a_day(tmp_path: Path, software: bool) -> None:
    """Gates G1 and G4 on the engine, G8 for the software host: the light's direction is
    read from the scene the engine draws from, and sky textures are counted in the
    engine — one per noticeable move, none in compatibility mode."""
    out = tmp_path / "controller"
    data = _ok_scenario(run_scenario(out, "controller", software="1" if software else "0"), out)
    shown = None
    expected_builds = 0
    for step, (elevation, azimuth) in zip(data["steps"], driver.DAY, strict=True):
        sun = SunState(elevation, azimuth)
        look = look_for(sun, "high")
        travel = (moon_travel_scene() if look.moon_travel_scene is not None
                  else tuple(-c for c in sun.direction_scene))
        assert step["light_travel"] == pytest.approx(_engine(travel), abs=1e-5), step
        assert step["night"] is look.night
        assert step["exposure"] == pytest.approx(look.mood.exposure)
        if sky_is_stale(shown, look.sky):
            shown, expected_builds = look.sky, expected_builds + 1
        if software:
            assert step["sky_builds"] == 0 and step["sky_built"] is False, step
        else:
            assert step["sky_builds"] == step["controller_rebuilds"] == expected_builds, step
    # eight noticeable moves by day, sunset (0.6 -> 0.4: the disc goes), nightfall
    # (-12), dawn (0.7) and one more by day
    assert expected_builds == 10, "the scripted day has ten noticeable moves"
    wind = data["wind"]
    if software:   # review P0: no wind on a software adapter — it would render continuously
        assert wind["running_while_shown"] is False and wind["moved_while_shown"] == 0.0, wind
    else:
        assert wind["running_while_shown"] is True and wind["moved_while_shown"] > 0.1, wind
    assert wind["moved_while_hidden"] == 0.0, "hidden: the clock stands"
    assert wind["after_reduced_motion"] == 0.0, "reduced motion: the clock is AT REST"
    assert (out / data["last"]).is_file()


# ── a shown window: the wind (gate G7) ───────────────────────────────────────


def test_the_winds_clock_on_the_real_render_loop(tmp_path: Path) -> None:
    """Gate G7 (render half). At rest the frame is the mesh's; running, the foliage has
    moved; stopped, the clock stands where it is — and that is NOT rest; at rest again
    the frame is, to the pixel, the first one."""
    out = tmp_path / "wind"
    data = _ok_scenario(run_scenario(out, "wind"), out)
    clock, frames = data["clock"], {name: load_rgb(out / file) for name, file in data["frames"].items()}
    assert clock["0_rest"] == 0.0 and clock["4_rest_again"] == 0.0
    assert clock["1_running"] > 2.0, "past the two seconds the shaders ease the sway in over"
    assert clock["2_stopped"] == clock["3_stopped_again"] == clock["1_running"]
    assert data["frozen_moved_by"] == 0.0
    moved = float(np.abs(frames["1_running"] - frames["0_rest"]).mean())
    assert moved > 0.5, f"a wind of strength {data['wind_strength']} moved nothing ({moved})"
    assert np.array_equal(frames["2_stopped"], frames["3_stopped_again"]), "a stopped clock stands"
    assert float(np.abs(frames["2_stopped"] - frames["0_rest"]).mean()) > 0.5, "stopped is not rest"
    assert np.array_equal(frames["4_rest_again"], frames["0_rest"]), "at rest: rendered == mesh"
    # what the ENGINE does by itself with a hidden window whose clock runs: it goes on —
    # which is why the policy stops the clock, and does not trust "hidden" to
    assert data["hidden_and_running_moved_by"] > 0.2, data


# ── the memory of twenty sun changes (gate G4) ───────────────────────────────


@pytest.mark.parametrize("frames", ["presented", "withheld"])
def test_twenty_sun_changes_leave_no_sky_behind(tmp_path: Path, frames: str) -> None:
    """Gate G4. A sky per sun change — an 8 MB texture and a light probe — and the old
    one released: committed memory per change, second half of twenty, under the
    registered bound. No readback inside the loop; no release of the engine's
    caches either (``cache_releases`` 0): a retired sky needs none, presenting or not."""
    out = tmp_path / "soak"
    data = _ok_scenario(run_scenario(out, "sky_soak", frames=frames), out)
    loop = data["in_the_loop"]
    assert loop["sky_builds"] == 20 and loop["frames_read_back"] == 0 and loop["cache_releases"] == 0
    if frames == "withheld":
        assert loop["frames_presented"] == 0 and loop["paint_events_eaten"] > 0, loop
    else:
        assert loop["frames_presented"] >= 20, loop
    assert data["slope_second_half_mb_per_change"] <= SOAK_BOUND_MB, data["curve_mb"]
    gpu = data["gpu_slope_second_half_mb_per_change"]
    assert gpu is None or gpu <= SOAK_BOUND_MB, data["gpu_curve_mb"]
    assert data["presented_again"] is True
    before, after = load_rgb(out / data["before"]), load_rgb(out / data["after"])
    assert float(np.abs(before - after).mean()) < 0.5, "the same sun again is not the same picture"


@pytest.fixture(scope="module")
def wind_soak(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The product's default steady state — the plan shown, the wind running — had no
    soak (review): every workspace soak runs with reduced motion. Two minutes, committed
    memory every five seconds, no readback in the loop."""
    out = tmp_path_factory.mktemp("wind") / "wind_soak"
    return _ok_scenario(run_scenario(out, "wind_soak", minutes="2"), out)


def test_the_wind_soak_runs_the_default_steady_state(wind_soak) -> None:
    loop = wind_soak["in_the_loop"]
    assert loop["frames_read_back"] == 0 and loop["sky_builds"] == 0
    assert loop["wind_clock_moved_s"] > 60.0, "the wind ran"
    assert loop["frames_presented"] > 600, "the view presented frames all the while"
    gpu = wind_soak["gpu_slope_second_half_mb_per_min"]
    assert gpu is None or gpu <= driver.WIND_SOAK_BOUND_MB_PER_MIN, wind_soak["gpu_curve_mb"]


@pytest.mark.xfail(strict=False, reason=(
    "#534 (FU-L14-2): committed memory grows while the wind runs, intermittently - L1.4 "
    "2.6 MB/min over 2 min and 2.09 over 6; L1.9's six 4-5 min soaks 0.0-1.51 second-half; "
    "the final render tier of 2026-10-19 2.637. Neither strict nor an assertion is honest "
    "while a run can land on either side of the bound."))
def test_the_wind_running_for_two_minutes_leaves_nothing_behind(wind_soak) -> None:
    """FU-L14-2 (#534), at the bound registered before L1.4's first run. L1.4 measured 2.6
    MB/min over 2 min and 2.09 over 6 min and kept this a strict xfail. L1.9 re-measured on
    2026-10-19 (RTX 4070, timer-paced frames): six alternating 4-5 min soaks, three with
    L1.4's FrameAnimation and three with a C++ NumberAnimation driving the clock — 0.46 to
    2.03 MB/min from the first sample to the last, a second-half slope of 0.0 to 1.51; the
    two clocks inside each other's spread — and dropped the xfail. The final render tier the
    same day read 2.637: the growth is intermittent, not gone, so this is a non-strict xfail
    until #534 is fixed; then it becomes an assertion again. (§8.29.9; the product's
    vblank-paced path is still unmeasured.)"""
    assert wind_soak["slope_second_half_mb_per_min"] <= driver.WIND_SOAK_BOUND_MB_PER_MIN,         wind_soak["curve_mb"]


def test_the_soak_sees_a_sky_that_is_not_released(tmp_path: Path) -> None:
    """The positive control: a scene file whose ``buildSky`` never destroys the old
    Texture. The gate above must FAIL on it."""
    out = tmp_path / "control"
    data = _ok_scenario(run_scenario(out, "sky_soak", leak="1"), out)
    assert data["slope_second_half_mb_per_change"] >= SOAK_CONTROL_MB, data["curve_mb"]
    assert data["slope_second_half_mb_per_change"] > 4 * SOAK_BOUND_MB
    assert math.isclose(data["bound_mb"], SOAK_BOUND_MB)
