#!/usr/bin/env python
"""Replay eight in-tree perturbations of ``ci.yml`` and assert the perf gate pin notices.

``tests/unit/test_gate_commands.py::test_ci_runs_the_whole_perf_set_serially`` is the
pin that keeps the perf gate honest: the ``Test`` job must run the wall-clock-sensitive
tests alone and serially, and the ``Coverage`` job must deselect them in one step and
append them in a second. Two review rounds of #509 found that a commit whose *stated*
purpose was to strengthen that pin had actually deleted a regression test while its
comment kept claiming the shapes were checked — seven mutations passed the pin, and the
only reason it was caught is that a reviewer wrote their own harness. That harness lived
in a scratch directory, so "13/13 behaved as expected" could not be re-run from the
repository.

This is that harness, committed. Each case edits ``ci.yml``, runs the pin, and records
whether the pin failed. A case that *should* be caught but is not, or a case that should
pass but fails, is a real finding: the pin has stopped watching a shape, or has started
rejecting valid configuration.

Run it alone::

    venv/Scripts/python.exe scripts/replay_gate_mutations.py
    venv/Scripts/python.exe scripts/replay_gate_mutations.py -v
    venv/Scripts/python.exe scripts/replay_gate_mutations.py --only quiet-runner-n0

It rewrites ``.github/workflows/ci.yml`` in the working tree, so it is **not** in CI and
must not be run beside another pytest process that reads the workflow. A pid lock makes a
second invocation exit rather than interleave writes, and a backup at
``scripts/.replay_gate_mutations.backup`` is restored by **copy** on every path (a restore
that consumed its own backup is how ``ci.yml`` was left mutated twice during #509).

Exit code 0 means every case behaved as its expectation says.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
PIN = "tests/unit/test_gate_commands.py"
BACKUP = Path(__file__).resolve().parent / ".replay_gate_mutations.backup"
LOCK = Path(__file__).resolve().parent / ".replay_gate_mutations.lock"

#: The pin's own file, as pytest reports a failure inside it.
_FAILED_IN_PIN = re.compile(
    r"FAILED tests/unit/test_gate_commands\.py::(?P<name>[\w\[\]:.\-]+)"
)

QIUET_STEP = "Run performance budgets on a quiet runner"
SERIAL_STEP = "Measure the perf tests serially and append"


def _step(parsed: dict[str, Any], job: str, name: str) -> dict[str, Any]:
    for step in parsed["jobs"][job]["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step {name!r} in job {job!r}")


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError(
            f"anchor appears {text.count(old)} times, expected exactly 1: {old!r}"
        )
    return text.replace(old, new, 1)


def _noop(_parsed: dict[str, Any]) -> None:
    return None


def _unchanged(original: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    def verify(parsed: dict[str, Any]) -> None:
        assert parsed == original, "a benign mutation changed the parsed workflow"

    return verify


@dataclass(frozen=True)
class Mutation:
    label: str
    expected: str  # "caught" or "passes"
    apply: Callable[[str], str]
    verify: Callable[[dict[str, Any]], None]


# Each `verify` asserts the intended *semantic* change actually landed in parsed YAML.
# A mutation that only looks applied — a text edit YAML reads as a separate list item, say
# — must be reported as an invalid mutation, never as an honest "not caught".
MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        "quiet-runner step continue-on-error",
        "caught",
        lambda t: _replace(
            t,
            f"      - name: {QIUET_STEP}\n",
            f"      - name: {QIUET_STEP}\n        continue-on-error: true\n",
        ),
        lambda p: _assert_true(_step(p, "test", QIUET_STEP).get("continue-on-error")),
    ),
    Mutation(
        "quiet-runner step if:",
        "caught",
        lambda t: _replace(
            t,
            f"      - name: {QIUET_STEP}\n",
            f"      - name: {QIUET_STEP}\n        if: true\n",
        ),
        lambda p: _assert_present(_step(p, "test", QIUET_STEP), "if"),
    ),
    Mutation(
        "serial step continue-on-error",
        "caught",
        lambda t: _replace(
            t,
            f"      - name: {SERIAL_STEP}\n",
            f"      - name: {SERIAL_STEP}\n        continue-on-error: true\n",
        ),
        lambda p: _assert_true(_step(p, "coverage", SERIAL_STEP).get("continue-on-error")),
    ),
    Mutation(
        "serial step if:",
        "caught",
        lambda t: _replace(
            t,
            f"      - name: {SERIAL_STEP}\n",
            f"      - name: {SERIAL_STEP}\n        if: true\n",
        ),
        lambda p: _assert_present(_step(p, "coverage", SERIAL_STEP), "if"),
    ),
    Mutation(
        "test job continue-on-error",
        "caught",
        lambda t: _replace(
            t, "  test:\n    name: Test\n", "  test:\n    continue-on-error: true\n    name: Test\n"
        ),
        lambda p: _assert_true(p["jobs"]["test"].get("continue-on-error")),
    ),
    Mutation(
        "test job if:",
        "caught",
        lambda t: _replace(t, "  test:\n    name: Test\n", "  test:\n    if: true\n    name: Test\n"),
        lambda p: _assert_present(p["jobs"]["test"], "if"),
    ),
    Mutation(
        "coverage job continue-on-error",
        "caught",
        lambda t: _replace(
            t,
            "  coverage:\n    name: Coverage\n",
            "  coverage:\n    continue-on-error: true\n    name: Coverage\n",
        ),
        lambda p: _assert_true(p["jobs"]["coverage"].get("continue-on-error")),
    ),
    Mutation(
        "needs: a dependency that can never run",
        "caught",
        lambda t: _replace(
            _replace(
                t,
                "  test:\n    name: Test\n",
                "  test:\n    name: Test\n    needs: [dead-gate]\n",
            ),
            "  security:\n",
            "  dead-gate:\n    if: false\n    runs-on: ubuntu-latest\n    steps:\n"
            '      - run: "true"\n\n  security:\n',
        ),
        lambda p: (
            _assert_true(
                sorted(p["jobs"]["test"]["needs"]) == ["dead-gate"]
            ),
            _assert_present(p["jobs"]["dead-gate"], "if"),
        ),
    ),
    Mutation(
        "tests/perf instead of tests/",
        "caught",
        lambda t: _replace(
            t,
            "        run: pytest tests/ -m perf -v -n 0\n",
            "        run: pytest tests/perf -m perf -v -n 0\n",
        ),
        lambda p: _assert_true("tests/perf" in _step(p, "test", QIUET_STEP)["run"]),
    ),
    Mutation(
        "dropped -n 0",
        "caught",
        lambda t: _replace(
            t,
            "        run: pytest tests/ -m perf -v -n 0\n",
            "        run: pytest tests/ -m perf -v\n",
        ),
        lambda p: _assert_true(_step(p, "test", QIUET_STEP)["run"].endswith("-m perf -v")),
    ),
    Mutation(
        "dropped --cov-append",
        "caught",
        lambda t: _replace(
            t,
            "          --cov=open_garden_planner --cov-branch --cov-append\n",
            "          --cov=open_garden_planner --cov-branch\n",
        ),
        lambda p: _assert_true("--cov-append" not in _step(p, "coverage", SERIAL_STEP)["run"]),
    ),
    Mutation(
        "|| true on the quiet runner",
        "passes",
        lambda t: _replace(
            t,
            "        run: pytest tests/ -m perf -v -n 0\n",
            "        run: pytest tests/ -m perf -v -n 0 || true\n",
        ),
        lambda p: _assert_true("|| true" in _step(p, "test", QIUET_STEP)["run"]),
    ),
    Mutation(
        '-o addopts="--co" on the quiet runner',
        "passes",
        lambda t: _replace(
            t,
            "        run: pytest tests/ -m perf -v -n 0\n",
            '        run: pytest tests/ -m perf -v -n 0 -o addopts="--co"\n',
        ),
        lambda p: _assert_true("--co" in _step(p, "test", QIUET_STEP)["run"]),
    ),
    Mutation(
        "PYTEST_ADDOPTS in the quiet runner's env",
        "passes",
        lambda t: _replace(
            t,
            f"      - name: {QIUET_STEP}\n        env:\n          QT_QPA_PLATFORM: offscreen\n",
            f"      - name: {QIUET_STEP}\n        env:\n"
            "          QT_QPA_PLATFORM: offscreen\n          PYTEST_ADDOPTS: --co\n",
        ),
        lambda p: _assert_true(
            _step(p, "test", QIUET_STEP)["env"].get("PYTEST_ADDOPTS") == "--co"
        ),
    ),
    Mutation(
        "DIAMOND in the needs graph (valid YAML, still passes)",
        "passes",
        lambda t: _replace(
            _replace(
                t,
                "  test:\n    name: Test\n",
                "  test:\n    name: Test\n    needs: [lint, agent-context]\n",
            ),
            "  lint:\n    name: Lint\n",
            "  lint:\n    name: Lint\n    needs: [agent-context]\n",
        ),
        lambda p: _assert_true(
            sorted(p["jobs"]["test"]["needs"]) == ["agent-context", "lint"]
            and p["jobs"]["lint"]["needs"] == ["agent-context"]
        ),
    ),
    Mutation(
        "a comment line that changes nothing",
        "passes",
        lambda t: _replace(
            t,
            f"      - name: {QIUET_STEP}\n",
            f"      # benign: a comment changes no configuration\n      - name: {QIUET_STEP}\n",
        ),
        None,  # filled in below: it must leave parsed YAML identical
    ),
)


def _assert_true(condition: object) -> None:
    assert condition, "mutation did not land"


def _assert_present(mapping: dict[str, Any], key: str) -> None:
    assert key in mapping, f"mutation did not land: {key!r} absent from {sorted(mapping)}"


class AlreadyRunning(RuntimeError):
    """Another instance holds the lock; the tree would be interleaved."""


def _acquire_lock() -> None:
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        owner = (LOCK.read_text(encoding="utf-8", errors="replace").strip().lstrip("\ufeff")) or "?"
        raise AlreadyRunning(owner) from exc
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)


def _restore_leftover(original: bytes) -> None:
    """A backup left by a crashed run is restored before anything else happens.

    The backup is written *before* the first mutation and deleted only on a clean exit,
    so its presence at startup means the previous run died with ``ci.yml`` possibly
    mutated. Restoring from it is the safe direction, and the caller re-snapshots the
    (restored) bytes immediately afterwards.
    """
    if not BACKUP.exists():
        return
    data = BACKUP.read_bytes()
    if data != original:
        WORKFLOW.write_bytes(data)
        print(f"restored {WORKFLOW.name} from a backup left by a previous run")


def _verdict(returncode: int, stdout: str, expected: str) -> str:
    caught = returncode != 0 and bool(_FAILED_IN_PIN.search(stdout))
    if expected == "caught":
        if caught:
            match = _FAILED_IN_PIN.search(stdout)
            return f"caught ({match.group('name')})" if match else "caught"
        if returncode != 0:
            return "INVALID (the pin did not run cleanly; not a real catch)"
        return "NOT CAUGHT"
    # expected "passes"
    if returncode == 0:
        return "passes"
    return "FAILED (a valid configuration was rejected)"


def _run_pin() -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "pytest", PIN, "-q", "--no-header", "-n", "0"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        check=False,
    )
    return proc.returncode, proc.stdout


def _run(only: set[str], verbose: bool) -> int:
    original_bytes = WORKFLOW.read_bytes()
    _restore_leftover(original_bytes)
    original_bytes = WORKFLOW.read_bytes()
    # The working tree may hold CRLF endings (Windows checkout); the mutation anchors are
    # written with `\n`, so normalise in, and convert back out. The naked `\n` form is what
    # the file carries in git, and a checkout on Linux writes that form directly.
    newline = "\r\n" if "\r\n" in original_bytes.decode("utf-8") else "\n"
    original_text = original_bytes.decode("utf-8").replace("\r\n", "\n")
    original_parsed = yaml.safe_load(original_text)
    shutil.copyfile(WORKFLOW, BACKUP)

    results: list[tuple[str, str, str]] = []
    try:
        for mutation in MUTATIONS:
            if only and mutation.label not in only:
                continue
            mutated = mutation.apply(original_text)
            parsed = yaml.safe_load(mutated)
            try:
                mutation.verify(parsed) if mutation.verify else _unchanged(original_parsed)(
                    parsed
                )
            except AssertionError as exc:
                results.append((mutation.label, mutation.expected, f"INVALID MUTATION ({exc})"))
                print(f"  [FAIL] {mutation.label:<46} INVALID MUTATION ({exc})")
                continue
            tmp = WORKFLOW.with_suffix(".yml.tmp")
            tmp.write_bytes(mutated.replace("\n", newline).encode("utf-8"))
            os.replace(tmp, WORKFLOW)
            try:
                returncode, stdout = _run_pin()
            finally:
                # Restore by COPY: os.replace(BACKUP, WORKFLOW) would MOVE the backup,
                # consuming it — the mistake that left ci.yml mutated twice during #509.
                shutil.copyfile(BACKUP, WORKFLOW)
            if WORKFLOW.read_bytes() != original_bytes:
                raise RuntimeError(f"ci.yml did not restore byte-identically after {mutation.label!r}")
            verdict = _verdict(returncode, stdout, mutation.expected)
            ok = (mutation.expected == "caught" and verdict.startswith("caught")) or (
                mutation.expected == "passes" and verdict == "passes"
            )
            results.append((mutation.label, mutation.expected, verdict))
            marker = "OK  " if ok else "FAIL"
            print(f"  [{marker}] {mutation.label:<46} expected {mutation.expected:<7} -> {verdict}")
            if verbose and not ok:
                tail = "\n".join(stdout.splitlines()[-25:])
                print(f"        pytest tail:\n        {tail.replace(chr(10), chr(10) + '        ')}")
    finally:
        shutil.copyfile(BACKUP, WORKFLOW)
        BACKUP.unlink(missing_ok=True)

    if WORKFLOW.read_bytes() != original_bytes:
        print("ci.yml was NOT restored to its original bytes")
        return 1

    bad = [
        (label, expected, verdict)
        for label, expected, verdict in results
        if not (
            (expected == "caught" and verdict.startswith("caught"))
            or (expected == "passes" and verdict == "passes")
        )
    ]
    print()
    if bad:
        print(f"{len(bad)} of {len(results)} mutations did not behave as expected:")
        for label, expected, verdict in bad:
            print(f"  - {label}: expected {expected}, got {verdict}")
        return 1
    print(f"All {len(results)} mutations behaved as expected; the pin is verified.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="print pytest output on failure")
    parser.add_argument("--only", action="append", default=[], help="run only these mutation labels")
    parser.add_argument("--list", action="store_true", help="list mutation labels and exit")
    args = parser.parse_args()

    if args.list:
        for mutation in MUTATIONS:
            print(f"{mutation.expected:<7} {mutation.label}")
        return 0

    try:
        _acquire_lock()
    except AlreadyRunning as exc:
        print(
            f"refusing to run: {LOCK.name} exists, held by pid {exc}. Two runs would "
            "interleave writes into the same workflow file. Delete the lock if no run is "
            "in progress."
        )
        return 1
    try:
        print(f"Replaying {len(MUTATIONS)} ci.yml mutations against {PIN}\n")
        return _run(set(args.only), args.verbose)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
