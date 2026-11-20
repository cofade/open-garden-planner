"""Print (and optionally save) what the performance run measured (#931).

The budgets themselves are untouched (§8.10): this only makes the evidence
behind a pass or a failure visible. ``OGP_PERF_REPORT`` names a JSON file to
keep beside the job log.
"""

from __future__ import annotations

import os

from tests.perf import perf_report


def pytest_terminal_summary(terminalreporter) -> None:
    """Report every round's median, and the host conditions, at the end of a run."""
    for line in perf_report.summary_lines():
        terminalreporter.write_line(line)
    path = os.environ.get("OGP_PERF_REPORT")
    if path:
        perf_report.write_report(path)
        terminalreporter.write_line(f"  performance report written to {path}")
