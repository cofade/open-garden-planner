"""Every wall-clock assertion must sit on the quiet runner (#509).

`addopts` carries `-m 'not perf'`, so the `perf` marker decides whether a test runs in
the default parallel run or on a quiet runner of its own. That makes the marker a
**correctness contract for the gate**, not a label.

This guard exists because prose decays. §8.10.4 asserted the marker audit was complete
when four wall-clock bounds were still unmarked, two of them in classes literally named
`TestPerf` — and the previous version of this file, which matched an allowlist of
variable *names*, would not have caught any of them either. It was defeated seven ways,
including the entire NFR-PERF-01 budget module, where no test function contains an
`ast.Assert` at all.

**So this matches timing SOURCES, not timing NAMES**, and follows them across calls to a
fixed point — twice, once for the clock and once for the assertion, because the real code
puts them in different functions:

    test_xyz()  ->  run_budget()  ->  _assert_budget()  ->  _measure_repaints()

`test_xyz` never names the asserter; `_assert_budget` never calls a clock. Closing only
the clock and then asking whether a test *directly* calls a sensitive function misses
that entire chain, and did — it was caught executing against this file's own
`collect_duration_asserts`, which returned `[]` for exactly that shape.

**What this guard does NOT claim, stated precisely rather than hedged.** Each item below
is a real hole, verified, not a caveat about a hypothetical:

- **The timing-source set is an enumeration, not "any clock".** `time.time`,
  `time.thread_time` and `timeit.default_timer` are measurable and not listed. Nothing
  here uses them for a budget — `time.time` is non-monotonic, which is the reason — but a
  future test that does would be missed.
- **Not every wall-clock assertion is an `assert` with a comparison operator.**
  `self.assertLess(...)`, `assert not (delta >= limit)` and `pytest.approx` on a
  duration are all invisible to it. `self.assertLess` does not occur in this suite; that
  is a fact about today, not a guarantee.
- **A budget inside a `@pytest.fixture` is not attributed to the tests that use it.** The
  guard would see the fixture function itself, and a fixture is not a test.
- **Functions are keyed by bare name across the whole module**, so duplicate method names
  resolve last-definition-wins. `test_agent_api_writes.py` has 37 `body` definitions, so
  the collision is real in this suite; it is currently harmless because no timing helper
  shares a name with a test elsewhere in a module, and that is a latent landmine, not a
  safety property.
- **It is one-directional.** It proves a marker is *required* where it fires, not that
  every marker present is needed. Two tests in `test_nfr_budgets.py` are marked because
  they build the same scenario on the quiet runner, not because they assert a duration.

A guard whose limits are written down is auditable. One that claims more than it checks is
the defect §11.4 keeps finding, and it has been found in three consecutive reviews of this
very file.
"""

from __future__ import annotations

import ast
from collections.abc import Collection
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parents[1]

# The sources of a measured duration. This is the property, not a convention — but it
# is an enumeration, and the honest scope note is that it is not the whole stdlib.
# `time.time`, `time.thread_time` and `timeit.default_timer` are measurable and are NOT
# listed; `time.time` is the wall clock and is not monotonic, which is why nothing in
# this suite uses it for a budget. A future test that does, and is therefore not caught,
# is a known limit of this guard rather than a defect in it — see the docstring.
TIMING_SOURCES = frozenset({
    "perf_counter", "perf_counter_ns", "monotonic", "process_time", "process_time_ns",
})
ORDERING_OPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
MARKER = "perf"


def _call_name(node: ast.AST) -> str | None:
    """Bare name of a call target, for both `f()` and `obj.f()`."""
    func = node.func if isinstance(node, ast.Call) else None
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _calls_any(func: ast.AST, names: Collection[str]) -> bool:
    return any(
        isinstance(node, ast.Call) and _call_name(node) in names
        for node in ast.walk(func)
    )


def _reads_a_clock(tree: ast.Module) -> set[str]:
    """Names of functions that reach a timing source, transitively through calls.

    A fixed point rather than a single pass: `_assert_repaint_budget` only becomes
    clock-reading after `_measure_repaints` has, and the ordering in the source file
    is not a dependency order.
    """
    functions = _functions(tree)
    timed: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, func in functions.items():
            if name in timed:
                continue
            if _calls_any(func, TIMING_SOURCES) or _calls_any(func, timed):
                timed.add(name)
                changed = True
    return timed


def _orders_a_value_against_a_bound(func: ast.AST) -> bool:
    for node in ast.walk(func):
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
            continue
        if any(isinstance(op, ORDERING_OPS) for op in node.test.ops):
            return True
    return False


def _closure(seed: set[str], tree: ast.Module) -> set[str]:
    """Grow `seed` to a fixed point over who calls whom, within this module."""
    functions = _functions(tree)
    grown = set(seed)
    changed = True
    while changed:
        changed = False
        for name, func in functions.items():
            if name in grown:
                continue
            if _calls_any(func, grown):
                grown.add(name)
                changed = True
    return grown


def _sensitive_names(tree: ast.Module) -> set[str]:
    """Functions that order a measured duration against a bound, and their callers.

    Two closures, not one. `_reads_a_clock` closes the clock over the call graph, then
    the *sensitivity* is closed the same way — because the propagation has to survive a
    hop that carries only an assertion. The real code does exactly this:

        test_xyz()  ->  run_budget()  ->  _assert_budget()  ->  _measure()

    `test_xyz` never mentions the asserter, and `_assert_budget` never calls a clock
    directly. Closing only the clock and asking whether a test *directly* calls a
    sensitive function misses that whole chain; it was caught executing against this
    file's own `collect_duration_asserts`, which returned `[]` for it.
    """
    timed = _reads_a_clock(tree)
    sensitive = {
        name for name in timed if _orders_a_value_against_a_bound(_functions(tree)[name])
    }
    return _closure(sensitive, tree)


def _marker_names(node: ast.AST) -> set[str]:
    """Marker attribute names applied to a function or class."""
    found: set[str] = set()
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        parts: list[str] = []
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
        # An exact `perf` in a `pytest.mark....` chain. Deliberately not a substring
        # test: `parametrize("kind", ["perf"])`, `ids=["perf_x"]` and
        # `skipif(True, reason="perf")` all contain the word and none of them marks
        # anything, and a guard that reads them as markers fails toward hiding a test.
        if len(parts) >= 2 and "mark" in parts[:-1]:
            found.add(parts[0])
    return found


def is_perf_marked(node: ast.AST) -> bool:
    return MARKER in _marker_names(node)


def collect_duration_asserts(tree: ast.Module) -> list[tuple[str, bool]]:
    """`(node_id, marked)` for every test that can be wall-clock sensitive.

    A test qualifies when it orders a duration itself, or when it calls something that
    does — which is the shape the NFR module uses, where the test's own body contains
    no assertion at all.

    The **marker** is inherited from an enclosing class; the **sensitivity** is not.
    One timing test in a class of twenty ordinary ones must not force all twenty onto
    the quiet runner, and a first version that propagated sensitivity to the class got
    that wrong in the opposite direction - it demanded markers for every sibling test.
    """
    sensitive = _sensitive_names(tree)
    found: list[tuple[str, bool]] = []

    def visit(node: ast.AST, marked: bool, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, marked or is_perf_marked(child), f"{prefix}{child.name}::")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                own = marked or is_perf_marked(child)
                if child.name.startswith("test_") and (
                    child.name in sensitive or _calls_any(child, sensitive)
                ):
                    found.append((f"{prefix}{child.name}", own))
                visit(child, own, prefix)
            else:
                visit(child, marked, prefix)

    visit(tree, False, "")
    return sorted(set(found))


def _python_files() -> list[Path]:
    return [p for p in TESTS_ROOT.rglob("test_*.py") if "__pycache__" not in p.parts]


def test_no_wall_clock_assertion_is_unmarked() -> None:
    """The guard: any duration assertion without `perf` can flake under workers."""
    offenders: list[str] = []
    scanned = 0
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node_id, marked in collect_duration_asserts(tree):
            scanned += 1
            if not marked:
                rel = path.relative_to(TESTS_ROOT.parent).as_posix()
                offenders.append(f"{rel}::{node_id}")
    assert scanned >= 12, (
        f"the guard matched {scanned} wall-clock-sensitive test(s); the perf set is 14, "
        "of which 12 assert a duration and 2 are marked for scenario consistency on the "
        "quiet runner. A count below 12 means the detection has regressed - re-check the "
        "call-graph closure, not the floor."
    )
    assert not offenders, (
        "wall-clock assertions without @pytest.mark.perf — they run beside up to "
        "`-n auto` workers in the default run and fail intermittently there:\n  "
        + "\n  ".join(offenders)
        + "\nAdd the marker, or rewrite the assertion to be robust (§11.4 #354)."
    )


def _verdict(source: str) -> list[tuple[str, bool]]:
    return collect_duration_asserts(ast.parse(source))


def test_the_guard_cannot_be_defeated_by_spelling() -> None:
    """The shapes that beat the previous allowlist-of-names version.

    Each one defeated the name-based guard; a regression to it would reopen the hole
    silently, which is why these are written as executable examples rather than prose.
    """
    # 1. The NFR module's shape: the clock is read in one helper, the assert is in
    #    another, and the test only calls the second. Neither one-hop nor one-function
    #    analysis finds this.
    nfr_shape = (
        "import pytest, time, statistics\n"
        "@pytest.mark.perf\n"
        "class TestBudget:\n"
        "    def test_x(self):\n"
        "        _assert_budget()\n"
        "def _measure(view):\n"
        "    t0 = time.perf_counter()\n"
        "    return [time.perf_counter() - t0]\n"
        "def _assert_budget():\n"
        "    best = min(statistics.median(_measure(None)) for _ in range(8))\n"
        "    assert best <= 16.7\n"
    )
    assert _verdict(nfr_shape) == [("TestBudget::test_x", True)]

    # 1b. THE ONE ROUND 4 CAUGHT, and the reason sensitivity gets its own closure.
    #     Three hops, and the test names none of the functions that measure or assert.
    #     The round-3 version returned `[]` for this: it closed the clock but then asked
    #     only whether the test DIRECTLY called a sensitive function, so one
    #     intermediate `return _assert_budget()` was enough to hide the whole chain.
    #     `_assert_budget` reaches the clock through `_measure`, and orders the result;
    #     `run_budget` only forwards. Sensitivity has to propagate the same way the clock
    #     does, or the forwarding layer is where the trace goes cold.
    three_hops = (
        "import pytest, time\n"
        "@pytest.mark.perf\n"
        "def test_wrapped():\n"
        "    run_budget()\n"
        "def run_budget():\n"
        "    return _assert_budget()\n"
        "def _assert_budget():\n"
        "    assert _measure() < 16.7\n"
        "def _measure():\n"
        "    t0 = time.perf_counter()\n"
        "    return time.perf_counter() - t0\n"
    )
    assert _verdict(three_hops) == [("test_wrapped", True)]

    # 2. A name the allowlist never contained, measured through a list.
    assert _verdict(
        "import pytest, time, statistics\n@pytest.mark.perf\n"
        "def test_y():\n"
        "    samples = []\n"
        "    for _ in range(8):\n"
        "        t0 = time.perf_counter()\n"
        "        samples.append((time.perf_counter() - t0) * 1000)\n"
        "    assert statistics.median(samples) < 200\n"
    ) == [("test_y", True)]

    # 3. The direct form, with an unfamiliar name.
    assert _verdict(
        "import pytest, time\n@pytest.mark.perf\n"
        "def test_z():\n    started_at = time.monotonic()\n"
        "    assert time.monotonic() - started_at < 0.5\n"
    ) == [("test_z", True)]

    # 4. Words containing 'perf' that mark nothing must not read as markers.
    for decorator in (
        '@pytest.mark.parametrize("kind", ["perf", "unit"])',
        '@pytest.mark.skipif(True, reason="perf budget")',
        "@pytest.mark.performance",
    ):
        verdict = _verdict(
            "import pytest, time\n"
            + decorator
            + "\ndef test_w():\n    delta = time.perf_counter() - 1.0\n"
            "    assert delta < 1.0\n"
        )
        assert verdict == [("test_w", False)], (
            f"{decorator} was read as a perf marker: {verdict}"
        )

    # 5. Equality on a configured interval is not a measurement - no ordering operator.
    assert _verdict(
        "import time\ndef test_q():\n    expected_ms = 500\n"
        "    assert timer.interval() == expected_ms\n"
    ) == []

    # 6. A test that never touches a clock is not swept up, even inside a marked class.
    assert _verdict(
        "import pytest\n@pytest.mark.perf\nclass TestThing:\n"
        "    def test_r(self):\n        assert species_key == 'x'\n"
    ) == []

    # 7. Reading a clock is not enough - it must be ordered against a bound. This test
    #    calls a helper that times something and then asserts something else entirely.
    #    (The first draft of this case asserted `_measure() > 0`, which IS a bound, and
    #    the guard rightly flagged it. The example, not the guard, was wrong.)
    assert _verdict(
        "import time\n"
        "def _log_duration():\n"
        "    t0 = time.perf_counter()\n"
        "    return time.perf_counter() - t0\n"
        "def test_s():\n"
        "    _log_duration()\n"
        "    assert 1 + 1 == 2\n"
    ) == []
