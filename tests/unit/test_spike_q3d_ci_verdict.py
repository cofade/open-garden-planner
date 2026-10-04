"""The temporary Windows evidence driver's verdict (ADR-047, L0) — delete with the driver.

The driver decides whether an evidence run is green. Its first version turned a
perfect 0.0 px projection error into a failure (``x or 99``) and would have
passed a run whose requested probe wrote nothing.
"""

from __future__ import annotations

import importlib.util
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
        "shader_caches": {"cold": False, "disabled_by_env": [], "found_before_run": []},
        "qt_messages": {"counts": {"error": 0, "warning": 0, "info": 0}, "errors": [],
                        "warnings": []},
        "shadow_iou_by_preset": {"low": {"results": {"az135": {"iou": 0.96}}}},
        "pick": {"n": 20, "hits": 20, "hits_after_reattach": 20, "reattach_frame_diff": 0.0,
                 "adversarial_n": 10, "adversarial_hits": 10, "max_projection_err_px": 0.0,
                 "max_xy_err_cm": 0.0},
        "soak": {"animation_advanced": True, "cycles": 20, "project_reloads": 4,
                 "models_per_reload_ok": True, "leak_slope_mb_per_reload": 0.2},
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
    # open_ms shorter than show->readback plus the QML load measured something else
    failures = driver._verdict(_metrics(open_ms=1300.0), ARGS)
    assert failures == ["open time includes QML load and scene build"]
    assert "the run records which shader caches it found" in driver._verdict(
        _metrics(shader_caches=None), ARGS)
