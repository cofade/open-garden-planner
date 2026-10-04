"""End-to-end render of the Qt Quick 3D spike — the first test that renders a 3D frame.

Opt-in (render tier "B" of the plan): needs a real RHI context, which the
default ``QT_QPA_PLATFORM=offscreen`` CI job cannot create (the offscreen QPA
falls back to the *software* scene graph, which has no 3D). Run it with::

    OGP_RENDER3D=1 xvfb-run -a -s "-screen 0 1920x1080x24" \\
        venv/bin/python -m pytest tests/integration/test_spike_q3d_render.py

The spike runs in a subprocess with ``QT_QPA_PLATFORM=xcb`` +
``QSG_RHI_BACKEND=opengl`` (Mesa llvmpipe in a container, the real GPU on a dev
box) and the assertions are about MEANING, never pixel-exact goldens: the
shadow map agrees with the analytic 2D shadow (ADR-047 criterion 8), the ground
texture is north-up, the sky's sun disc sits at the solar azimuth.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("OGP_RENDER3D") != "1" or not os.environ.get("DISPLAY"),
        reason="render tier (Linux/X11 only): set OGP_RENDER3D=1 and run under xvfb-run",
    ),
    # each module fixture is a full render subprocess (~1.5-3 min on llvmpipe): the
    # global 180 s per-test timeout would abort the setup the first test pays for
    pytest.mark.timeout(1200),
]

PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
QML_SOURCE = REPO / "src" / "open_garden_planner" / "spike_q3d" / "qml"


def _render_env(config_home: Path, **extra: str) -> dict[str, str]:
    """xcb + OpenGL, and a private settings home so a run can be checked for
    writes to the user's store (loading a plan records Recent Files)."""
    env = dict(os.environ, QT_QPA_PLATFORM="xcb", QSG_RHI_BACKEND="opengl",
               XDG_CONFIG_HOME=str(config_home), **extra)
    env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"  # Chromium refuses root with a sandbox
    return env


def _spike(out: Path, env: dict[str, str], *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — fixed argv, our own module
        [sys.executable, "-m", "open_garden_planner", "--spike-q3d", "--plan", str(PLAN),
         "--out", str(out), *flags],
        env=env, capture_output=True, text=True, timeout=1100, cwd=REPO,
    )


@pytest.fixture(scope="module")
def spike_metrics(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path]:
    out = tmp_path_factory.mktemp("spike_q3d")
    config_home = tmp_path_factory.mktemp("config_home")
    proc = _spike(out, _render_env(config_home), "--presets", "medium",
                  "--shots", "noon,december_noon", "--size", "640x360", "--fps-seconds", "0",
                  "--iou", "--orient")
    assert proc.returncode == 0, proc.stderr[-2000:]
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    metrics["_config_home"] = str(config_home)
    return metrics, out


def test_the_users_settings_store_is_never_written(spike_metrics: tuple[dict, Path]) -> None:
    """Loading a plan records Recent Files; the spike must write a throwaway store."""
    from open_garden_planner.spike_q3d.runner import SETTINGS_ORGANIZATION

    config_home = Path(spike_metrics[0]["_config_home"])
    assert not (config_home / "cofade").exists(), sorted(p.name for p in config_home.iterdir())
    assert (config_home / SETTINGS_ORGANIZATION).is_dir()


def test_renders_a_real_frame(spike_metrics: tuple[dict, Path]) -> None:
    metrics, out = spike_metrics
    assert metrics["graphics_api"] in ("OpenGL", "Direct3D11", "Vulkan", "Metal", "Direct3D12")
    from PyQt6.QtGui import QImage

    img = QImage(str(out / "noon_medium.png"))
    assert not img.isNull()
    values = {img.pixel(x, y) for x in range(0, img.width(), 37) for y in range(0, img.height(), 29)}
    assert len(values) > 200  # a real scene, not a cleared framebuffer


def test_shadow_map_agrees_with_the_analytic_shadow(spike_metrics: tuple[dict, Path]) -> None:
    metrics, _ = spike_metrics
    for elev, row in metrics["shadow_iou"]["results"].items():
        assert row["iou"] >= 0.85, (elev, row)


def test_ground_is_north_up_and_sky_sun_follows_the_azimuth(spike_metrics: tuple[dict, Path]) -> None:
    """The sky is checked OFF-centre (the disc 25 degrees left and right of the view
    axis), where a wrong field of view or bearing mapping shows."""
    metrics, _ = spike_metrics
    orient = metrics["orientation"]
    assert orient["ground_texture_ok"], orient["ground_texture_ncc"]
    assert orient["sky_ok"], orient["sky_sun_disc"]
    assert orient["sky_max_abs_error_deg"] < 3.0, orient["sky_sun_disc"]


def test_each_shot_shows_the_plan_on_its_sun_date(spike_metrics: tuple[dict, Path]) -> None:
    """The 2D overlay resolves casters at the sim date; the L0 board built June for every shot.

    This pins the bookkeeping end to end: the expected dates come from the shot
    list, one build per date, and the two builds differ. It cannot see what was
    on screen (``build_date`` is recorded next to the grab from the same date);
    that the models on screen carry their date is proven with a fake renderer in
    ``tests/unit/test_spike_q3d_board.py``.
    """
    from open_garden_planner.spike_q3d.runner import default_shots

    metrics, _ = spike_metrics
    expected = {s.name: s.when_utc.date().isoformat() for s in default_shots(2400.0, 1600.0)}
    rows = metrics["shots"]
    assert {r["shot"] for r in rows} == {"noon", "december_noon"}
    for row in rows:
        assert row["build_date"] == expected[row["shot"]], row
    builds = metrics["builds"]
    assert set(builds) == {expected["noon"], expected["december_noon"]}
    assert builds[expected["noon"]]["triangles"] != builds[expected["december_noon"]]["triangles"]


@pytest.fixture(scope="module")
def measured(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, int]:
    """The L0.2 measurement flags in one run (ADR-047 criteria 2, 3, 5, 6, 7, 10)."""
    out = tmp_path_factory.mktemp("spike_q3d_measure")
    proc = _spike(out, _render_env(tmp_path_factory.mktemp("config_home")),
                  "--presets", "low", "--shots", "golden_hour", "--size", "640x360",
                  "--fps-seconds", "0", "--watchdog-s", "1000", "--iou", "--pick",
                  "--update-bench", "--second-window", "--coexist", "--pan-bench", "--soak", "50")
    log = (out / "spike.log").read_text(encoding="utf-8") if (out / "spike.log").exists() else ""
    assert (out / "metrics.json").exists(), proc.stderr[-2000:] + log[-2000:]
    return json.loads((out / "metrics.json").read_text(encoding="utf-8")), proc.returncode


def test_measurement_run_closes_cleanly_while_really_animating(measured: tuple[dict, int]) -> None:
    """Criterion 10, measured: the first version asserted a literal True while the
    wind animation never ticked (senior review)."""
    metrics, code = measured
    assert code == 0, metrics.get("error")
    assert metrics["status"] == "ok"
    assert metrics["wait_timeouts"] == 0
    soak = metrics["soak"]
    assert soak["animation_advanced"] is True, soak
    assert soak["frames_while_animating"] >= 8, soak
    assert soak["wind_time_after"] > soak["wind_time_before"], soak
    assert soak["event_loop_exit_code"] == 0, soak  # informational; the witness is `code`
    assert metrics["qt_messages"]["errors"] == [], metrics["qt_messages"]


def test_soak_reloads_the_project_from_disk_without_a_leak(measured: tuple[dict, int]) -> None:
    """Criterion 10: 50 show/hide cycles and 10 project reloads (the plan read into a
    new scene, every model, geometry and the ground built new while the engine runs).

    An append-only keep-alive list for ground textures grew RSS ~30 MB per reload,
    linearly; holding only the shown texture lets it settle. A total-growth bound
    cannot tell those apart (the allocator steps up early either way), the slope
    over the second half can.
    """
    soak = measured[0]["soak"]
    assert soak["cycles"] == 50
    assert soak["project_reloads"] == 10, soak
    assert soak["models_per_reload_ok"] is True, soak
    assert soak["rss_tail_slope_mb_per_reload"] is not None, soak
    assert soak["rss_tail_slope_mb_per_reload"] < 10.0, soak["rss_after_refill_mb"]


def test_low_preset_shadow_map_agrees_with_the_analytic_shadow(measured: tuple[dict, int]) -> None:
    """Every preset has its own shadow quality; the L0 board only measured "high"."""
    rows = measured[0]["shadow_iou_by_preset"]["low"]["results"]
    for elev, row in rows.items():
        assert row["iou"] >= 0.85, (elev, row)


def test_every_pick_names_the_item_the_cpu_oracle_expects(measured: tuple[dict, int]) -> None:
    """Runs after --iou, which swaps the scene's models out and back in.

    Without the re-upload in SpikeRenderer.set_models, models that return
    after removal render nothing and pick nothing (0/20, first seen in the
    Windows evidence run v3 and reproduced on OpenGL).
    """
    pick = measured[0]["pick"]
    assert pick["n"] == 20, pick
    assert pick["hits"] == 20, pick["misses"]
    assert pick["hits_after_reattach"] == 20, pick
    assert pick["reattach_frame_diff"] < 1.0, pick  # pixels come back too, not only picks


def test_adversarial_picks_defeat_a_bounding_box_picker(measured: tuple[dict, int]) -> None:
    """Points inside a tall item's box but off its mesh: the easy targets alone let a
    bounding-box picker score 18/20; these it must get right too. The click pixels
    are checked against our own projection, not only the engine's."""
    pick = measured[0]["pick"]
    assert pick["adversarial_n"] >= 5, pick
    assert pick["adversarial_hits"] == pick["adversarial_n"], pick["adversarial_misses"]
    assert pick["max_projection_err_px"] < 1.0, pick
    assert pick["max_xy_err_cm"] < 3.0, pick


def test_webengine_and_quick3d_both_draw_in_one_process(measured: tuple[dict, int]) -> None:
    co = measured[0]["coexist"]
    assert co["web_loaded"] is True, co
    assert co["web_ok"], co        # the page colour, before AND after the 3D frame
    # the 3D frame equals the same view rendered before WebEngine started, and that
    # view has structure — "mean luma > 20" also passed an empty frame
    assert co["frame3d_ok"], co


def test_timing_measurements_are_recorded(measured: tuple[dict, int]) -> None:
    """Thresholds are hardware criteria (owner GPU); here: measured, not invented."""
    metrics = measured[0]
    assert metrics["update_bench"]["vertices"] >= 100_000
    assert metrics["update_bench"]["set_mesh_ms"]["median"] > 0
    # open time ends on a finished readback, not on submission (senior review)
    assert metrics["first_ready_ms"] >= metrics["first_frame_ms"] > 0
    second = metrics["second_window"]
    assert second["first_ready_ms"] >= second["first_frame_ms"] > 0
    # criterion 5 (senior review): open time runs from the user's request to the first
    # finished readback, so it holds the QML load and the scene build
    breakdown = metrics["open_breakdown_ms"]
    assert metrics["open_ms"] >= sum(breakdown.values()) - 50.0, breakdown
    assert metrics["shader_caches"]["cold"] is False
    assert metrics["pan_bench"]["ratio_median"] is not None


@pytest.fixture(scope="module")
def scaled(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """A stock 150 % display: the probes once built their pixel grid from the
    logical size — ``--iou`` crashed and ``--orient`` reported a mirrored ground."""
    out = tmp_path_factory.mktemp("spike_q3d_scaled")
    proc = _spike(out, _render_env(tmp_path_factory.mktemp("config_home"), QT_SCALE_FACTOR="1.5"),
                  "--presets", "low", "--shots", "noon", "--size", "640x360", "--fps-seconds", "0",
                  "--iou", "--orient", "--pick")
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads((out / "metrics.json").read_text(encoding="utf-8"))


def test_probes_hold_at_150_percent_display_scale(scaled: dict) -> None:
    assert scaled["shadow_iou"]["device_pixel_ratio"] == 1.5
    for elev, row in scaled["shadow_iou"]["results"].items():
        assert row["iou"] >= 0.85, (elev, row)
    assert scaled["orientation"]["ground_texture_ok"], scaled["orientation"]["ground_texture_ncc"]
    assert scaled["orientation"]["sky_ok"], scaled["orientation"]["sky_sun_disc"]
    assert scaled["pick"]["hits"] == scaled["pick"]["n"] == 20, scaled["pick"]


def test_a_mistyped_flag_fails_instead_of_running_another_experiment(
        tmp_path: Path) -> None:
    proc = _spike(tmp_path, _render_env(tmp_path / "config_home"), "--presets", "lowww")
    assert proc.returncode == 2
    metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["status"] == "error"
    assert "lowww" in metrics["error"]


def test_a_shader_that_does_not_compile_fails_the_run(tmp_path: Path) -> None:
    """Positive control for the Qt message recorder. A broken custom shader used to
    leave ``status: ok`` and exit 0 while the pond silently changed colour; the
    compile error only reached stderr, which the frozen exe does not have."""
    qml = tmp_path / "qml"
    shutil.copytree(QML_SOURCE, qml)
    frag = qml / "water.frag"
    text = frag.read_text(encoding="utf-8")
    assert "qt_sampleGlossy(" in text  # the call this control breaks
    frag.write_text(text.replace("qt_sampleGlossy(", "qt_sampleGlossyBroken("), encoding="utf-8")
    out = tmp_path / "out"
    proc = _spike(out, _render_env(tmp_path / "config_home"), "--qml-dir", str(qml),
                  "--presets", "low", "--shots", "golden_hour", "--size", "320x180",
                  "--fps-seconds", "0")
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert proc.returncode == 3, metrics.get("error")
    assert metrics["status"] == "qt_errors"
    assert any("qt_sampleGlossyBroken" in e for e in metrics["qt_messages"]["errors"]), (
        metrics["qt_messages"])


def test_open_time_knows_a_first_launch_from_a_warm_one(tmp_path: Path) -> None:
    """Criterion 5 asks for cold AND warm open times, so a run must say which it was
    (senior review: every container "cold" run after the first one ran on warm caches).
    A fresh cache home makes the first launch cold; the second finds what it wrote;
    ``--cold`` turns every disk cache off and writes none."""
    from open_garden_planner.spike_q3d.runner import COLD_ENV

    cache = tmp_path / "cache"

    def run(name: str, *extra: str) -> dict:
        out = tmp_path / name
        env = _render_env(tmp_path / "config_home", XDG_CACHE_HOME=str(cache / name.split("-")[0]))
        proc = _spike(out, env, "--presets", "low", "--shots", "golden_hour", "--size", "320x180",
                      "--fps-seconds", "0", *extra)
        assert proc.returncode == 0, proc.stderr[-2000:]
        return json.loads((out / "metrics.json").read_text(encoding="utf-8"))

    first, second = run("a-first"), run("a-second")
    assert first["shader_caches"]["found_before_run"] == []
    assert any(n.startswith("q3dshadercache") for n in second["shader_caches"]["found_before_run"])
    cold = run("b-cold", "--cold")
    assert cold["shader_caches"]["cold"] is True
    assert cold["shader_caches"]["disabled_by_env"] == sorted(COLD_ENV)
    assert not any((cache / "b").rglob("q3dshadercache*"))  # cold writes no cache either
    for metrics in (first, second, cold):
        assert metrics["open_ms"] >= metrics["first_ready_ms"] + metrics["qml_load_ms"]
