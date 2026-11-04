"""Tests for scripts/measure_test_suite_latency.py (#509).

The script exists so the suite's wall clock can be optimised from measurement. Its
dangerous failure mode is therefore not a crash but a **confident wrong number**:
every downstream decision (parallel execution, which files to fix, which subset to
run in the inner loop) is read off these tables. So these tests pin the arithmetic
against a hand-computable fixture, and pin the ways a report can mislead:

- a `setup`/`teardown` phase must not be charged to a test's own cost, or
  per-test latency inflates with pytest's own overhead;
- a node id must be attributed to the right layer, including Windows backslash
  paths and a root-level file that has no `tests/<layer>/` segment;
- a report with no duration lines must fail closed rather than render empty tables
  that read as "nothing is slow";
- all-zero durations must not divide by zero, and must not print "0.0%" as if it
  were a measurement;
- PowerShell 5.1's `>` redirection writes UTF-16LE, so both encodings must parse
  identically — otherwise the documented reproduce command silently yields nothing
  on the Windows dev box, which is the one platform this was measured on.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.measure_test_suite_latency import analyse, layer_of, main, read_report

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "measure_test_suite_latency.py"

# Hand-computable: 4 call lines totalling 30.0s across three layers, plus
# setup/teardown that must be reported but not charged to the tests.
FIXTURE = [
    "0.01s setup    tests/unit/test_a.py::test_one",
    "10.00s call    tests/unit/test_a.py::test_one",
    "0.02s teardown tests/unit/test_a.py::test_one",
    "0.01s setup    tests/unit/test_a.py::test_two",
    "20.00s call    tests/unit/test_a.py::test_two",
    "0.03s teardown tests/unit/test_a.py::test_two",
    "0.01s setup    tests/integration/test_b.py::TestC::test_three",
    "0.00s call    tests/integration/test_b.py::TestC::test_three",
    "0.05s teardown tests/integration/test_b.py::TestC::test_three",
    "0.01s setup    tests/unit/test_a.py::test_one",
]


def test_layer_attribution_handles_backslashes_and_root_files() -> None:
    assert layer_of("tests/unit/test_a.py::test_one") == "unit"
    assert layer_of("tests\\integration\\test_b.py::test") == "integration"
    # No layer segment at all: must not claim it belongs to "tests".
    assert layer_of("test_top_level.py::test_x") == "(root)"


def test_setup_and_teardown_are_reported_but_not_charged_to_tests() -> None:
    result = analyse(FIXTURE)
    assert result["parsed_tests"] == 3
    assert result["total_call_seconds"] == 30.0
    # 10 + 20 + 0.00 = 30.0s of call time; the 0.01/0.02/0.03/0.05 phases are
    # overhead and must not inflate it.
    slowest = result["slowest_tests"]  # type: ignore[index]
    assert slowest[0]["test"] == "tests/unit/test_a.py::test_two"
    assert slowest[0]["seconds"] == 20.0
    assert result["phase_seconds"] == {"call": 30.0, "setup": 0.04, "teardown": 0.1}


def test_a_call_only_report_does_not_raise_on_absent_phases() -> None:
    """A report with no `setup`/`teardown` line above the 5 ms floor must not raise.

    The phase summary indexed `phase_seconds[phase]` rather than reading it with a default,
    so a genuinely call-only report raised `KeyError: 'setup'` and exited 1. An earlier
    version of this docstring claimed that shape was reproduced from
    `test_gate_commands.py` and `test_perf_marker_guard.py`; six real inputs, including both
    CI artifacts, carry setup above the floor and do not reproduce it. The shape is real and
    is what this fixture builds; the file names were not.

    Every other test here is blind to it because the shared fixture always carries setup and
    teardown, and the two early-exit cases return before the summary is built.

    A phase that never appeared is absent, not zero: the report must not claim it was
    measured as 0.00s.
    """
    call_only = [
        "0.30s call    tests/unit/test_a.py::test_one",
        "0.20s call    tests/unit/test_a.py::test_two",
    ]
    result = analyse(call_only)
    assert result["total_call_seconds"] == 0.5
    assert result["parsed_tests"] == 2
    # Absent, not 0.0 - the distinction the KeyError was hiding.
    for phase in ("setup", "teardown"):
        assert result["phase_seconds"].get(phase) is None, (
            f"{phase} was reported as {result['phase_seconds'].get(phase)!r}, but no such "
            "line exists in the report"
        )


def test_layers_sum_to_the_measured_total() -> None:
    layers = analyse(FIXTURE)["layers"]  # type: ignore[index]
    assert layers["unit"]["tests"] == 2
    assert layers["unit"]["seconds"] == 30.0
    assert layers["integration"]["seconds"] == 0.0
    assert layers["integration"]["tests"] == 1
    assert sum(v["seconds"] for v in layers.values()) == result_total(FIXTURE)


def result_total(fixture: list[str]) -> float:
    return float(analyse(fixture)["total_call_seconds"])  # type: ignore[arg-type]


def test_concentration_and_projection_are_consistent_with_the_total() -> None:
    result = analyse(FIXTURE)
    assert result["concentration"]["slowest_1_test_seconds"] == 20.0  # type: ignore[index]
    # One test holds 20 of 30 seconds.
    assert result["concentration"]["slowest_10_share_percent"] == 100.0  # type: ignore[index]
    projected = result["projected_wall_clock_seconds"]  # type: ignore[index]
    assert projected["4"] == 7.5
    assert projected["8"] == 3.8


def test_a_report_without_durations_fails_closed() -> None:
    """No parsed lines must not render as "nothing is slow"."""
    junk = ["============================= test session starts =============", "1 passed"]
    result = analyse(junk)
    assert result["parsed_tests"] == 0
    assert "no duration lines parsed" in _render(result)


def test_all_zero_durations_do_not_divide_by_zero() -> None:
    zeros = ["0.00s call    tests/unit/test_a.py::test_one", "0.00s call    tests/unit/test_b.py::t"]
    result = analyse(zeros)
    assert result["parsed_tests"] == 2
    assert "layers" not in result, "must not publish share tables it cannot compute"
    assert _render(result)


def test_utf16_and_utf8_reports_parse_identically(tmp_path: Path) -> None:
    body = "\n".join(FIXTURE)
    ascii_report = tmp_path / "ascii.txt"
    ascii_report.write_text(body, encoding="utf-8")
    wide_report = tmp_path / "wide.txt"
    # Exactly what PowerShell 5.1's `>` redirection produces.
    wide_report.write_bytes(body.encode("utf-16"))

    assert analyse(read_report(ascii_report)) == analyse(read_report(wide_report))


def test_main_writes_json_and_returns_zero(tmp_path: Path, capsys: object) -> None:
    report = tmp_path / "d.txt"
    report.write_text("\n".join(FIXTURE), encoding="utf-8")
    out = tmp_path / "latency.json"
    code = main([str(report), "--json", str(out)])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["parsed_tests"] == 3
    assert payload["layers"]["unit"]["tests"] == 2


def test_main_reports_exit_2_when_there_is_nothing_to_summarise(tmp_path: Path) -> None:
    report = tmp_path / "empty.txt"
    report.write_text("nothing here", encoding="utf-8")
    assert main([str(report)]) == 2


def test_missing_report_is_an_error_not_a_traceback(tmp_path: Path) -> None:
    assert main([str(tmp_path / "nope.txt")]) == 2


def test_script_runs_as_a_subprocess_and_reports(tmp_path: Path) -> None:
    """The documented command in the docstring has to actually work."""
    report = tmp_path / "durations.txt"
    report.write_text("\n".join(FIXTURE), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(report)],
        capture_output=True, text=True, encoding="utf-8", timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "parsed 3 timed tests" in proc.stdout


def _render(result: object) -> str:
    from scripts.measure_test_suite_latency import render

    return render(result)  # type: ignore[arg-type]
