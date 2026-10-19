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

NOT box casters — exempt from the shadow gate by ADR-064's divergence table: closed
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
#: G8, the relaxed G2 of the software fallback (no sky: a flat fill lights the shadow).
MIN_IOU_SOFTWARE = 0.80
#: G3. Night's mean LUMINANCE (linear light) under a quarter of noon's, same shot and plan.
MAX_NIGHT_OVER_NOON = 0.25
#: G4. The spike's bound for the sky probe; measured here 0.03 degrees.
MAX_SKY_ERROR_DEG = 6.0
#: G5. The largest change of the row-mean luma across 0.15 degrees at the horizon, the
#: depth of a thin dark line there, the height of a thin bright one — at eye height, per
#: mood and preset, within 0.4 degrees of the horizon. Measured: step <= 3.5 at 640 x 360
#: (4.2 at 960 x 540), dip <= 1.9 (3.2), ridge <= 0.8 (1.0); on the software adapter,
#: where the plain sky IS the fog's colour, 0.15 / 0.03 / 0.02. The spike measured a
#: step of 3.6 at most, by day. Before L1.4's round 1 the night step was 10.5 (high)
#: and 21.2 (low).
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


@pytest.fixture(scope="module")
def board(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Path]:
    out = tmp_path_factory.mktemp("looks") / "board"
    return _ok_board(run_board(out, "--presets", ",".join(PRESETS), "--shots",
                               "noon,december_noon,night", "--iou", "--orient", "--horizon",
                               "--moods"), out), out


def test_the_production_board_runs_end_to_end_and_every_truth_row_is_green(board) -> None:
    """Gate G10. The production pipeline — snapshot, builders, sink, host, looks — from a
    plan on disk to PNGs and numbers, with nothing Qt objected to."""
    metrics, out = board
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
    assert metrics["orientation"]["ok"] is True, metrics["orientation"]
    assert metrics["orientation"]["ncc"]["identity"] > 0.6
    assert metrics["probe_restore_frame_diff"] == 0.0, "a probe left something behind"
    assert metrics["wind_time"] == 0.0


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
        # no mood contradicts its time of day: the lower the sun, the darker the frame
        order = [moods[name]["mean_luminance"] for name in ("noon", "golden_hour", "sunset", "night")]
        assert order == sorted(order, reverse=True), (preset, order)


def test_the_sky_draws_its_sun_at_the_solar_azimuth(board) -> None:
    """Gate G4. The disc is read 25 degrees off-centre, left and right, for a sun in
    the east, the south and the west."""
    metrics, _out = board
    sky = metrics["sky"]
    assert sky["ok"] is True and len(sky["views"]) == 6, sky
    assert sky["max_abs_error_deg"] < MAX_SKY_ERROR_DEG
    for view in sky["views"].values():
        assert view["found"] and abs(view["elevation_deg"] - 12.0) < 3.0, view


def test_fog_meets_the_sky_at_every_preset_and_in_every_mood(board) -> None:
    """Gate G5. At eye height, looking away from the sun and across it."""
    metrics, _out = board
    horizon = metrics["horizon"]
    worst = horizon["max"]
    assert worst["step"] <= MAX_HORIZON_STEP, horizon
    assert worst["dip"] <= MAX_HORIZON_DIP and worst["ridge"] <= MAX_HORIZON_RIDGE, horizon
    for preset in PRESETS:
        assert set(horizon[preset]) == {"noon", "golden_hour", "sunset", "night"}
        for mood in horizon[preset].values():
            assert mood["away"]["judged_rows"] >= 5 and mood["across"]["judged_rows"] >= 5


# ── speckle: the bound and its positive control ──────────────────────────────

#: Isolated dark pixels at 640 x 360, medium. The spike bounded its own board at 170
#: (38 / 42 clean, 737 / 700 with sharpening 0.08; noon / December noon). The PRODUCTION
#: scene measures 194 / 2 clean and 315 / 150 sharpened: its noon count is the far
#: picket fence — shaded pickets against the lit meadow behind them, 190 of the 194, the
#: same with and without sharpening and so not the look's — and its December frame has
#: almost none. The bounds are per shot, each a third above what was measured; the gate
#: for the LOOK is the December frame, where the control is 75 times the clean count.
MAX_SPECKLES = {"noon": 260, "december_noon": 30}
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
    return _ok_board(run_board(out, "--software", "--presets", "low,high", "--shots", "noon,night",
                               "--iou", "--orient", "--horizon", "--moods"), out), out


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
    measured = {(preset, elevation): block["results"][elevation]["iou"]
                for preset, block in metrics["shadow_iou"].items()
                for elevation in ("15deg", "35deg", "60deg")}
    assert len(measured) == 6 and min(measured.values()) >= MIN_IOU_SOFTWARE, measured
    assert metrics["orientation"]["ok"] is True
    for preset in ("low", "high"):
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
        travel = moon_travel_scene() if look.night else tuple(-c for c in sun.direction_scene)
        assert step["light_travel"] == pytest.approx(_engine(travel), abs=1e-5), step
        assert step["night"] is look.night
        assert step["exposure"] == pytest.approx(look.mood.exposure)
        if sky_is_stale(shown, look.sky):
            shown, expected_builds = look.sky, expected_builds + 1
        if software:
            assert step["sky_builds"] == 0 and step["sky_built"] is False, step
        else:
            assert step["sky_builds"] == step["controller_rebuilds"] == expected_builds, step
    assert expected_builds == 9, "the scripted day has nine noticeable moves"
    wind = data["wind"]
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


def test_the_soak_sees_a_sky_that_is_not_released(tmp_path: Path) -> None:
    """The positive control: a scene file whose ``buildSky`` never destroys the old
    Texture. The gate above must FAIL on it."""
    out = tmp_path / "control"
    data = _ok_scenario(run_scenario(out, "sky_soak", leak="1"), out)
    assert data["slope_second_half_mb_per_change"] >= SOAK_CONTROL_MB, data["curve_mb"]
    assert data["slope_second_half_mb_per_change"] > 4 * SOAK_BOUND_MB
    assert math.isclose(data["bound_mb"], SOAK_BOUND_MB)
