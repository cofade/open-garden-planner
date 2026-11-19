"""The performance report keeps the evidence, so it must be right (#931).

A reporter with a bug is worse than none: it would print a plausible table that
nobody can check. These pin the arithmetic and the two output forms.
"""

from __future__ import annotations

import json
import time

import pytest

from tests.perf import perf_report


@pytest.fixture(autouse=True)
def _empty_report() -> None:
    perf_report.reset()
    yield
    perf_report.reset()


def test_begin_and_take_record_every_round_with_best_and_spread() -> None:
    started = time.perf_counter()
    measurement = perf_report.begin("fit-in-view", 16.7, 8)
    measurement.medians.extend([9.0, 10.0, 8.0])
    perf_report.take(measurement, started)

    assert measurement.best == 8.0
    assert measurement.worst == 10.0
    assert measurement.spread == pytest.approx(0.25)
    assert measurement.rounds_planned == 8
    assert perf_report.measurements() == [measurement]


def test_one_round_has_no_spread() -> None:
    """A single median must not report 0 % variation as if the host were calm."""
    measurement = perf_report.begin("one shot", 40.0, 1)
    measurement.medians.append(2.0)
    assert measurement.spread is None


def test_a_failing_budget_is_still_reported() -> None:
    """The whole point: a raised assertion must not lose the numbers."""
    with pytest.raises(RuntimeError), perf_report.measure("repaint", 16.7, 2) as measurement:
        measurement.medians.extend([20.0, 21.0])
        raise RuntimeError("budget failed")

    assert len(perf_report.measurements()) == 1
    assert perf_report.measurements()[0].medians == [20.0, 21.0]


def test_summary_names_every_median_and_the_verdict() -> None:
    slow = perf_report.begin("fit-in-view", 16.7, 8)
    slow.medians.extend([50.15, 50.02])
    fast = perf_report.begin("zoom step", 16.7, 8)
    fast.medians.append(4.6)

    text = "\n".join(perf_report.summary_lines())

    assert "fit-in-view: OVER" in text
    assert "50.15, 50.02" in text
    assert "zoom step: ok" in text
    assert "runner:" in text


def test_the_json_report_holds_the_runner_and_every_measurement(tmp_path) -> None:
    measurement = perf_report.begin("fit-in-view", 16.7, 8)
    measurement.medians.extend([9.0, 10.0])
    target = tmp_path / "perf.json"

    perf_report.write_report(str(target))

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["runner"]["cpu_count"] == perf_report.runner_conditions()["cpu_count"]
    assert payload["measurements"][0]["medians"] == [9.0, 10.0]
    assert payload["measurements"][0]["spread"] == pytest.approx(0.111, abs=0.001)


def test_runner_conditions_state_what_is_unknown_as_none() -> None:
    """No guessed load average: on Windows there is none."""
    conditions = perf_report.runner_conditions()
    assert "loadavg" in conditions
    assert conditions["affinity"] is None or isinstance(conditions["affinity"], int)
    assert conditions["ci"] in (True, False)
