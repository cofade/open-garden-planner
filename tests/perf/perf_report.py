"""What a performance run measured, and on what machine (#931).

A timing budget that fails by 0.3 % is indistinguishable, in a CI log, from a
real regression that costs 0.3 % — the numbers that would tell them apart (every
round's median, the spread between them, and the conditions the runner was under)
were thrown away. ``_assert_repaint_budget`` kept only the *best* median, and
only if it failed.

Every NFR budget assertion in ``tests/perf/test_nfr_budgets.py`` that evaluates
rounds reports itself here instead. The summary is printed at the end of the session (``pytest_terminal_summary`` in
``tests/perf/conftest.py``) and written as JSON when ``OGP_PERF_REPORT`` names a
file, so a workflow can keep it beside the job log.

Nothing here changes a budget, a scenario or a test's selection (§8.10): it only
records what was measured.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path


def runner_conditions() -> dict[str, object]:
    """What the machine says about itself: the part that explains a slow round.

    ``loadavg`` and ``sched_getaffinity`` are both unavailable on Windows — an
    absent value is ``None``, never a guess.
    """
    conditions: dict[str, object] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "ci": os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true",
        "pid": os.getpid(),
    }
    try:
        conditions["affinity"] = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        conditions["affinity"] = None
    try:
        conditions["loadavg"] = list(os.getloadavg())
    except (AttributeError, OSError):
        conditions["loadavg"] = None
    return conditions


@dataclass
class Measurement:
    """One budgeted measurement: every round's median and what it was up against."""

    name: str
    budget_ms: float
    medians: list[float] = field(default_factory=list)
    rounds_planned: int = 0
    seconds: float = 0.0
    detail: dict[str, object] = field(default_factory=dict)

    @property
    def best(self) -> float | None:
        return min(self.medians) if self.medians else None

    @property
    def worst(self) -> float | None:
        return max(self.medians) if self.medians else None

    @property
    def spread(self) -> float | None:
        """``(worst - best) / best``: how much the same work varied on the host.

        A budget that fails while this is large is describing the host, not the
        code; one that fails while it is near zero is describing the code.
        Undefined for a single round: one number has no spread.
        """
        best = self.best
        worst = self.worst
        if best is None or worst is None or best <= 0.0 or len(self.medians) < 2:
            return None
        return (worst - best) / best

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "budget_ms": self.budget_ms,
            "medians": [round(value, 3) for value in self.medians],
            "rounds": len(self.medians),
            "rounds_planned": self.rounds_planned,
            "best_ms": None if self.best is None else round(self.best, 3),
            "worst_ms": None if self.worst is None else round(self.worst, 3),
            "spread": None if self.spread is None else round(self.spread, 3),
            "seconds": round(self.seconds, 3),
            "detail": self.detail,
        }


_MEASUREMENTS: list[Measurement] = []


def begin(name: str, budget_ms: float, rounds_planned: int) -> Measurement:
    """Start recording ``name``; it is reported even when the test raises."""
    measurement = Measurement(name, budget_ms, rounds_planned=rounds_planned)
    _MEASUREMENTS.append(measurement)
    return measurement


@contextmanager
def measure(name: str, budget_ms: float, rounds_planned: int) -> Iterator[Measurement]:
    """``begin`` and ``take`` around the block, so a failing budget is still reported."""
    measurement = begin(name, budget_ms, rounds_planned)
    started = time.perf_counter()
    try:
        yield measurement
    finally:
        take(measurement, started)


def take(measurement: Measurement, started: float) -> Measurement:
    """Stop the clock on ``measurement`` (its medians were appended as it ran)."""
    measurement.seconds = time.perf_counter() - started
    return measurement


def measurements() -> list[Measurement]:
    """Everything this session measured, in the order it ran."""
    return list(_MEASUREMENTS)


def reset() -> None:
    """Forget what was recorded (a test of this module, not a test run)."""
    _MEASUREMENTS.clear()


def summary_lines() -> list[str]:
    """The session's measurements as compact lines, best first for comparison."""
    if not _MEASUREMENTS:
        return []
    lines = ["", "Performance measurements (#931): every round, not only the best"]
    for measurement in _MEASUREMENTS:
        medians = ", ".join(f"{value:.2f}" for value in measurement.medians) or "-"
        spread = measurement.spread
        spread_text = "-" if spread is None else f"{spread * 100:.1f}%"
        if measurement.best is None:
            verdict = "-"  # interrupted before a round: not a pass
        else:
            verdict = "ok" if measurement.best <= measurement.budget_ms else "OVER"
        lines.append(
            f"  {measurement.name}: {verdict} best "
            f"{'-' if measurement.best is None else f'{measurement.best:.2f}'} ms, "
            f"budget {measurement.budget_ms:.2f} ms, "
            f"{len(measurement.medians)}/{measurement.rounds_planned} rounds, "
            f"spread {spread_text}, {measurement.seconds:.1f} s"
        )
        lines.append(f"      medians: {medians}")
        for key, value in measurement.detail.items():
            lines.append(f"      {key}: {value}")
    conditions = runner_conditions()
    lines.append(
        "  runner: "
        + ", ".join(
            f"{key}={conditions[key]}" for key in
            ("platform", "cpu_count", "affinity", "loadavg", "ci")
        )
    )
    return lines


def write_report(path: str) -> None:
    """Write the session's measurements as JSON to ``path``."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "runner": runner_conditions(),
        "measurements": [measurement.as_dict() for measurement in _MEASUREMENTS],
    }
    with target.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
