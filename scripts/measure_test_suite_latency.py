"""Aggregate a pytest `--durations` report into the tables that decide test-suite work (#509).

Run the suite once with durations recorded, then point this at the report:

    pytest tests/ -n 0 -o addopts="" --durations=0 --timeout=180 > durations.txt
    python scripts/measure_test_suite_latency.py durations.txt

**Both `-n 0` and `-o addopts=""` are load-bearing, not style preferences**, because this
script cannot detect which kind of report it was handed and will render either wrong one
as a baseline:

* Without `-n 0`, `addopts` supplies `-n auto --dist worksteal` (#509) and per-test call
  time *inflates* - the same suite reads 620.6 s of call time serially and about 1 700 s
  under `-n auto`.
* Without `-o addopts=""`, the same `addopts` also supplies `-m 'not perf'`, so the run
  deselects the entire 14-test `perf` layer and every total, share and concentration figure
  is computed over a suite that is missing a layer. (`-m ''` is the intuitive way to clear
  a marker filter and it fails: `argument -m: expected one argument`.)

A confident wrong baseline is the exact failure this script exists to prevent, so pointing
it at itself is the least it can do.

That is the step issue #509 called the missing first one: nothing in the repo
recorded *where* the wall clock went, so every optimisation was a guess about
which tests were slow. This script turns a recorded run into the questions that
actually decide the work:

1. which layer owns the time (unit / integration / ui / perf);
2. whether the time is uniform or concentrated in a few files -- this is the
   fork in the road: uniform time means parallel execution pays, concentrated
   time means the few files should be fixed or isolated and a new dependency
   is not the answer;
3. which files would make viable inner-loop subsets;
4. the Amdahl-style projection for `-n N`.

Pure text in, tables out. It never runs pytest itself -- keeping the parse
separate from the run is what makes it testable.

Note on encoding: PowerShell 5.1's `>` redirection writes UTF-16LE while pytest
itself writes UTF-8, so both are accepted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TypedDict

# "12.34s call    tests/unit/test_foo.py::test_bar"
# "0.50s setup   tests/unit/test_foo.py::test_bar"
# "1.20s teardown tests/unit/test_foo.py::test_bar"
DURATION_LINE = re.compile(
    r"^(?P<secs>\d+(?:\.\d+)?)s\s+(?P<phase>call|setup|teardown)\s+(?P<node>\S+)"
)
# setup/teardown are reported but are per-test framework overhead, not test cost.
CALL_ONLY = frozenset({"call"})
PHASES = ("call", "setup", "teardown")
WORKER_COUNTS = (2, 4, 6, 8, 12, 16)


class LayerStats(TypedDict):
    tests: int
    seconds: float
    share_percent: float
    mean_seconds: float


class FileCost(TypedDict):
    file: str
    seconds: float
    share_percent: float


class TestCost(TypedDict):
    test: str
    seconds: float


class LatencyAnalysis(TypedDict, total=False):
    parsed_tests: int
    total_call_seconds: float
    phase_seconds: dict[str, float]
    layers: dict[str, LayerStats]
    concentration: dict[str, float]
    slowest_files: list[FileCost]
    slowest_tests: list[TestCost]
    projected_wall_clock_seconds: dict[str, float]


def read_report(path: Path) -> list[str]:
    """Return the report's lines, tolerating either encoding pytest may meet."""
    blob = path.read_bytes()
    if blob[:2] in (b"\xff\xfe", b"\xfe\xff") or blob.count(b"\x00") > len(blob) // 4:
        text = blob.decode("utf-16", errors="replace")
    else:
        text = blob.decode("utf-8", errors="replace")
    return text.splitlines()


def layer_of(node: str) -> str:
    parts = node.replace("\\", "/").split("/")
    return parts[1] if len(parts) > 1 else "(root)"


def by_cost(costs: dict[str, float]) -> list[tuple[str, float]]:
    """`(name, seconds)` pairs, most expensive first."""
    return sorted(costs.items(), key=lambda kv: kv[1], reverse=True)


def analyse(lines: list[str]) -> LatencyAnalysis:
    """Reduce a duration report to the decision tables.

    Only `call` phases contribute to per-test and per-file cost; `setup` and
    `teardown` are accumulated separately because they are framework overhead
    proportional to the number of tests, which is a different lever entirely.
    """
    call_by_test: dict[str, float] = {}
    # Plain dicts, not Counter: typeshed types Counter's values as int, and
    # these accumulate fractional seconds.
    call_by_file: dict[str, float] = {}
    call_by_layer: dict[str, float] = {}
    layer_tests: dict[str, int] = {}
    phase_seconds: dict[str, float] = {}

    for raw in lines:
        match = DURATION_LINE.match(raw.strip())
        if match is None:
            continue
        seconds = float(match.group("secs"))
        phase = match.group("phase")
        node = match.group("node")
        phase_seconds[phase] = phase_seconds.get(phase, 0.0) + seconds
        if phase not in CALL_ONLY:
            continue
        call_by_test[node] = call_by_test.get(node, 0.0) + seconds
        file_node = node.split("::", 1)[0]
        call_by_file[file_node] = call_by_file.get(file_node, 0.0) + seconds
        layer = layer_of(node)
        call_by_layer[layer] = call_by_layer.get(layer, 0.0) + seconds
        layer_tests[layer] = layer_tests.get(layer, 0) + 1

    if not call_by_test:
        return {"parsed_tests": 0, "total_call_seconds": 0.0}

    ranked = sorted(call_by_test.values(), reverse=True)
    total = sum(ranked)
    if total <= 0.0:
        # Every timed call was 0.00s. Report the count and stop: the share
        # figures below are divisions by `total`, and "0.0%" for every layer
        # would read as a measurement rather than as an absence of one.
        return {"parsed_tests": len(call_by_test), "total_call_seconds": 0.0}
    median = ranked[len(ranked) // 2]
    file_costs = sorted(call_by_file.values(), reverse=True)
    top_decile = max(1, len(file_costs) // 10)

    def share(n: int) -> float:
        """Percent of measured call time held by the slowest `n` tests."""
        return round(sum(ranked[:n]) / total * 100, 1)

    return LatencyAnalysis(
        parsed_tests=len(call_by_test),
        total_call_seconds=round(total, 1),
        # `.get`, not `[phase]`: a report whose phases are all under the 5 ms floor has no
        # entry for them at all, and `[phase]` raised `KeyError: 'setup'` and exited 1.
        # To see it, write a report with only `call` lines - a three-line file is enough:
        # `0.03s call tests/unit/test_gate_commands.py::test_a`. A full `--durations=0` run
        # usually carries setup and teardown above the floor, so the shape is easy to miss;
        # `test_a_call_only_report_does_not_raise_on_absent_phases` pins it.
        phase_seconds={phase: round(value, 2)
                       for phase in PHASES
                       if (value := phase_seconds.get(phase))},
        layers={
            layer: LayerStats(
                tests=layer_tests[layer],
                seconds=round(seconds, 1),
                share_percent=round(seconds / total * 100, 1),
                mean_seconds=round(seconds / layer_tests[layer], 3),
            )
            for layer, seconds in by_cost(call_by_layer)
        },
        concentration={
            "slowest_1_test_seconds": round(ranked[0], 2),
            "slowest_10_share_percent": share(10),
            "slowest_50_share_percent": share(50),
            "slowest_200_share_percent": share(200),
            "top_decile_files_share_percent": round(
                sum(file_costs[:top_decile]) / total * 100, 1),
            "median_test_seconds": round(median, 3),
            "mean_over_median": round(total / len(ranked) / median, 1) if median else 0.0,
        },
        slowest_files=[
            FileCost(file=name, seconds=round(secs, 1),
                     share_percent=round(secs / total * 100, 1))
            for name, secs in by_cost(call_by_file)[:30]
        ],
        slowest_tests=[
            TestCost(test=node, seconds=round(secs, 2))
            for node, secs in sorted(call_by_test.items(), key=lambda kv: kv[1],
                                     reverse=True)[:20]
        ],
        projected_wall_clock_seconds={str(n): round(total / n, 1) for n in WORKER_COUNTS},
    )


def render(result: LatencyAnalysis) -> str:
    if not result.get("parsed_tests"):
        return "no duration lines parsed -- was the run made with --durations?\n"
    total = result.get("total_call_seconds", 0.0)
    out: list[str] = [
        f"parsed {result['parsed_tests']} timed tests, {total:.1f}s of call time\n",
        "== per layer ==",
        f"{'layer':<14}{'tests':>7}{'seconds':>11}{'share':>9}{'mean s':>9}",
    ]
    for layer, stats in result.get("layers", {}).items():
        out.append(f"{layer:<14}{stats['tests']:>7}{stats['seconds']:>9.1f}s"
                   f"{stats['share_percent']:>8.1f}%{stats['mean_seconds']:>9.3f}")

    out.append("\n== concentration ==")
    conc = result.get("concentration", {})
    rows = (
        ("slowest_1_test_seconds", "slowest 1 test", "s"),
        ("slowest_10_share_percent", "slowest 10 tests", "%"),
        ("slowest_50_share_percent", "slowest 50 tests", "%"),
        ("slowest_200_share_percent", "slowest 200 tests", "%"),
        ("top_decile_files_share_percent", "top decile of files", "%"),
    )
    for key, label, unit in rows:
        out.append(f"{label:<22}{conc.get(key, 0.0)}{unit} of measured call time")
    out.append(f"median test: {conc.get('median_test_seconds', 0.0)}s, "
               f"mean/median ratio: {conc.get('mean_over_median', 0.0)}x")

    out.append("\n== slowest 30 files ==")
    for entry in result.get("slowest_files", []):
        out.append(f"{entry['seconds']:>9.1f}s{entry['share_percent']:>7.1f}%  {entry['file']}")

    out.append("\n== slowest 10 individual tests ==")
    for slow in result.get("slowest_tests", [])[:10]:
        out.append(f"{slow['seconds']:>9.2f}s  {slow['test']}")

    out.append("\n== phase split (setup/teardown are per-test framework overhead) ==")
    for phase, secs in result.get("phase_seconds", {}).items():
        # Two decimals, not one: these are totals over thousands of tests, and a
        # real sub-0.05 s figure rounded to one place prints as "0.0s", which
        # reads as "no overhead" rather than as a negligible amount of it.
        out.append(f"{phase:<10}{secs:>9.2f}s")

    out.append("\n== projected wall clock at -n N (zero overhead, Amdahl-style) ==")
    for n, secs in result.get("projected_wall_clock_seconds", {}).items():
        out.append(f"-n {n:<3} -> {secs:>7.1f}s ({secs / 60:.1f} min)")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", type=Path, help="a pytest --durations report (text)")
    parser.add_argument("--json", type=Path, help="also write the analysis as JSON")
    args = parser.parse_args(argv)

    try:
        result = analyse(read_report(args.report))
    except OSError as exc:
        print(f"Could not read {args.report}: {exc}", file=sys.stderr)
        return 2

    print(render(result), end="")
    if not result.get("parsed_tests"):
        return 2
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
