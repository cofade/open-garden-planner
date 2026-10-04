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
        "shadow_iou_by_preset": {"low": {"results": {"az135": {"iou": 0.96}}}},
        "pick": {"n": 20, "hits": 20, "hits_after_reattach": 20, "reattach_frame_diff": 0.0,
                 "adversarial_n": 10, "adversarial_hits": 10, "max_projection_err_px": 0.0,
                 "max_xy_err_cm": 0.0},
        "soak": {"animation_advanced": True, "close_exit_code": 0},
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


def test_a_leaking_reload_soak_fails(driver) -> None:
    soak = {"animation_advanced": True, "close_exit_code": 0, "project_reloads": 10,
            "models_per_reload_ok": True, "rss_tail_slope_mb_per_reload": 30.0}
    assert driver._verdict(_metrics(soak=soak), ARGS) == [
        "no RSS growth trend over the project reloads (< 10 MB/reload)"]
    soak["rss_tail_slope_mb_per_reload"] = None  # unreadable RSS must not pass
    assert len(driver._verdict(_metrics(soak=soak), ARGS)) == 1
