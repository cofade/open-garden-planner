"""The temporary Windows evidence driver's verdict (ADR-048, L0) — delete with the driver.

The driver decides whether an evidence run is green. Its first version turned a
perfect 0.0 px projection error into a failure (``x or 99``) and would have
passed a run whose requested probe wrote nothing.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_DRIVER = Path(__file__).resolve().parents[2] / "scripts" / "spike_q3d_ci.py"


@pytest.fixture(scope="module")
def driver():
    spec = importlib.util.spec_from_file_location("spike_q3d_ci", _DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metrics(**overrides: object) -> dict:
    metrics = {
        "status": "ok",
        "wait_timeouts": 0,
        "first_frame_ms": 1000.0,
        "first_ready_ms": 1200.0,
        "qml_load_ms": 300.0,
        "open_ms": 2500.0,
        "open_breakdown_ms": {"ground_bake": 100.0, "build_models": 400.0, "qml_load": 300.0,
                              "scene_apply": 10.0, "look_and_sun": 490.0,
                              "show_to_first_ready": 1200.0},
        "shader_caches": {"cold": False, "disabled_by_env": [], "found_before_run": []},
        "qt_messages": {"counts": {"error": 0, "warning": 0, "info": 0}, "errors": [],
                        "warnings": []},
        "shadow_iou_by_preset": {"low": {"results": {"az135": {"iou": 0.96}}}},
        "pick": {"n": 20, "hits": 20, "hits_after_reattach": 20, "reattach_frame_diff": 0.0,
                 "adversarial_n": 10, "adversarial_hits": 10, "max_projection_err_px": 0.0,
                 "max_xy_err_cm": 0.0},
        "soak": {"animation_advanced": True, "cycles": 20, "project_reloads": 4,
                 "models_per_reload_ok": True, "leak_slope_mb_per_reload": 0.2},
        "probe_restore_frame_diff": 0.0,
    }
    metrics.update(overrides)
    return metrics


ARGS = ["--iou", "--pick", "--soak", "20"]


def test_a_perfect_run_passes(driver) -> None:
    assert driver._verdict(_metrics(), ARGS) == []


def test_a_zero_error_is_not_read_as_missing(driver) -> None:
    # the regression: (0.0 or 99) < 1.0 failed a perfect projection
    pick = dict(_metrics()["pick"], max_projection_err_px=0.0, reattach_frame_diff=0.0)
    assert driver._verdict(_metrics(pick=pick), ARGS) == []


def test_a_null_metric_fails_instead_of_raising(driver) -> None:
    pick = dict(_metrics()["pick"], max_projection_err_px=None, reattach_frame_diff=None)
    failures = driver._verdict(_metrics(pick=pick, first_ready_ms=None), ARGS)
    assert "click pixels match our own projection" in failures
    assert "frame unchanged after re-attach" in failures
    assert "open time measured to a finished readback" in failures


def test_a_requested_probe_that_wrote_nothing_fails(driver) -> None:
    metrics = _metrics()
    del metrics["pick"]
    assert driver._verdict(metrics, ARGS) == ["pick measured (its flag was given)"]
    assert driver._verdict(metrics, ["--iou"]) == []


@pytest.mark.parametrize("args", [["--soak", "20"], ["--soak=20"]])
def test_soak_is_required_in_both_flag_spellings(driver, args: list[str]) -> None:
    metrics = _metrics()
    del metrics["soak"]
    assert driver._verdict(metrics, args) == ["soak measured (its flag was given)"]
    assert driver._verdict(metrics, ["--soak", "0"]) == []


def test_a_low_iou_fails(driver) -> None:
    metrics = _metrics(shadow_iou_by_preset={"high": {"results": {"az135": {"iou": 0.84}}}})
    assert driver._verdict(metrics, ARGS) == ["shadow IoU high az135 >= 0.85"]


def test_a_leaking_reload_soak_fails_on_the_leak_gate_alone(driver) -> None:
    # exactly this list is what --expect-leak (the positive control) requires
    soak = dict(_metrics()["soak"], leak_slope_mb_per_reload=30.0)
    assert driver._verdict(_metrics(soak=soak), ARGS) == [driver.LEAK_CHECK]
    soak["leak_slope_mb_per_reload"] = None  # an unreadable value must not pass
    assert driver._verdict(_metrics(soak=soak), ARGS) == [driver.LEAK_CHECK]


def test_soak_counts_are_checked_against_the_flag(driver) -> None:
    soak = dict(_metrics()["soak"], cycles=10, project_reloads=2)
    assert driver._verdict(_metrics(soak=soak), ARGS) == [
        "soak ran 20 cycles", "soak reloaded the project 4 times"]


def test_a_qt_warning_or_error_fails_the_run(driver) -> None:
    warned = {"counts": {"error": 0, "warning": 1, "info": 0}, "errors": [], "warnings": ["x"]}
    assert driver._verdict(_metrics(qt_messages=warned), ARGS) == ["Qt reported no warning"]
    assert "Qt reported no shader/QML error" in driver._verdict(_metrics(qt_messages=None), ARGS)


@pytest.mark.parametrize("found, expect, ok", [
    ([], "none", True), ([], "found", False),
    (["q3dshadercache-x"], "found", True), (["q3dshadercache-x"], "none", False)])
def test_cold_and_warm_runs_are_checked(driver, found: list, expect: str, ok: bool) -> None:
    caches = {"cold": False, "disabled_by_env": [], "found_before_run": found}
    failures = driver._verdict(_metrics(shader_caches=caches), ARGS, expect)
    assert (failures == []) is ok, failures


def test_open_time_must_include_the_qml_load(driver) -> None:
    assert driver._verdict(_metrics(qml_load_ms=None), ARGS) == [
        "open time includes QML load and scene build"]  # missing is not zero


def test_open_time_must_be_fully_attributed(driver) -> None:
    # 3 s of open time in no bucket (the sky, senior review round 3) must fail
    assert driver._verdict(_metrics(open_ms=5500.0), ARGS) == [
        "open time is fully attributed (breakdown within 100 ms)"]
    # open_ms shorter than show->readback plus the QML load measured something else
    failures = driver._verdict(_metrics(open_ms=1300.0), ARGS)
    assert failures == ["open time includes QML load and scene build",
                        "open time is fully attributed (breakdown within 100 ms)"]
    assert "the run records which shader caches it found" in driver._verdict(
        _metrics(shader_caches=None), ARGS)


def test_frame_comparisons_are_checked(driver) -> None:
    metrics = _metrics(probe_restore_frame_diff=9.83,
                       second_window={"frame_diff_vs_first": 9.83})
    assert driver._verdict(metrics, ARGS) == [
        "the probes leave the view as they found it (< 1 luma)",
        "the second window renders the first window's view (< 1 luma)"]
    assert driver._verdict(_metrics(probe_restore_frame_diff=0.0,
                                    second_window={"frame_diff_vs_first": 0.0}), ARGS) == []


def test_the_leak_amount_flag_is_not_the_soak_flag(driver) -> None:
    assert driver._requested_sections(["--soak-leak-mb", "25"]) == []
    assert driver._requested_sections(["--soak", "100", "--soak-leak-mb", "25"]) == ["soak"]


def test_a_probed_run_without_the_restore_check_fails(driver) -> None:
    """Fail closed: once --iou or --orient ran, a missing restore metric is a failure,
    not a skipped check (senior review, pass 5)."""
    metrics = _metrics()
    del metrics["probe_restore_frame_diff"]
    assert driver._verdict(metrics, ARGS) == [
        "the probes leave the view as they found it (< 1 luma)"]
    assert driver._verdict(metrics, ["--pick", "--soak", "20"]) == []


def test_an_orient_only_run_requires_the_restore_check(driver) -> None:
    """The orientation probe restores the view too, not only the IoU probe."""
    metrics = _metrics(orientation={"ground_texture_ok": True})
    del metrics["probe_restore_frame_diff"]
    assert "the probes leave the view as they found it (< 1 luma)" in driver._verdict(
        metrics, ["--orient"])


def test_what_the_spike_ran_is_judged_not_only_the_argv(driver) -> None:
    """The spike records the flags it parsed (``metrics["args"]``): a probe that ran
    needs its section and the restore check even when the driver's argv scan misses
    it, as it missed "--ori" while the spike accepted abbreviations (pass 6)."""
    metrics = _metrics(args={"iou": True, "orient": False, "pick": False, "soak": 20})
    del metrics["probe_restore_frame_diff"]
    del metrics["soak"]
    failures = driver._verdict(metrics, [])
    assert "soak measured (its flag was given)" in failures
    assert "the probes leave the view as they found it (< 1 luma)" in failures
    assert driver._requested_sections([], {"pan_bench": True, "soak": True}) == ["pan_bench"]


def test_only_the_unfrozen_child_gets_this_checkouts_src(driver, monkeypatch) -> None:
    """The frozen bundle imports what it bundled; only ``python -m`` needs the pin
    (senior review, passes 6-7)."""
    monkeypatch.setenv("PYTHONPATH", "elsewhere")
    assert driver._child_env(frozen=True)["PYTHONPATH"] == "elsewhere"
    assert driver._child_env(frozen=False)["PYTHONPATH"].split(os.pathsep) == [
        str(driver.REPO / "src"), "elsewhere"]
