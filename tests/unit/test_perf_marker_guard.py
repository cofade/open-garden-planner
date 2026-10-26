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
- **Call resolution is static.** It follows lexical functions, `self`/`cls` methods,
  explicit class calls and local instances constructed or annotated with a named class.
  Dynamic receivers, instance aliases and imported helper function calls are not resolved.
- **It is one-directional.** It proves a marker is *required* where it fires, not that
  every marker present is needed. Two tests in `test_nfr_budgets.py` are marked because
  they build the same scenario on the quiet runner, not because they assert a duration.

A guard whose limits are written down is auditable. One that claims more than it checks is
the defect §11.4 keeps finding, and it has been found in three consecutive reviews of this
very file.

**A measurement that travels in an attribute** (#528) is a third source of sensitivity,
beside the clock itself and the call graph: the stopwatch is in one method and the
assertion reads the attribute it fills - often in ANOTHER module, the class's own. The
guard follows the carrier into the local support modules a test file imports, and an
attribute is timed when a clock-reading method of its class fills it. A value that is
only COUNTED (`len(timestamps)`) is not a duration and does not make a test sensitive:
the gates that count repaints and passes are meant to hold on any machine under any load,
and they run beside the workers (ADR-058).
"""

from __future__ import annotations

import ast
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

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


Function = ast.FunctionDef | ast.AsyncFunctionDef
Scope = tuple[str, ...]


def _body_nodes(func: ast.AST) -> Iterator[ast.AST]:
    """Walk a function body without attributing nested definitions to its caller."""
    pending = list(reversed(list(ast.iter_child_nodes(func))))
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield node
        pending.extend(reversed(list(ast.iter_child_nodes(node))))


@dataclass
class _FunctionIndex:
    """One module's lexical identities, shared by both timing closures.

    The enclosing module is the index's boundary; within it every function's
    key includes its class and enclosing functions. No bare-name fallback is
    allowed for an unresolved receiver: that was #528's false positive.
    """

    functions: dict[Scope, Function] = field(default_factory=dict)
    classes: dict[Scope, ast.ClassDef] = field(default_factory=dict)
    owners: dict[Scope, Scope] = field(default_factory=dict)
    calls: dict[Scope, frozenset[Scope]] = field(default_factory=dict)
    targets: dict[int, Scope] = field(default_factory=dict)
    clock_readers: set[Scope] = field(default_factory=set)

    def collect(self, node: ast.AST, scope: Scope = (), owner: Scope = ()) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                key = (*scope, child.name)
                self.classes[key] = child
                self.collect(child, key, key)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = (*scope, child.name)
                self.functions[key] = child
                self.owners[key] = owner
                self.collect(child, key, owner)
            else:
                self.collect(child, scope, owner)

    def resolve(self, name: str, caller: Scope) -> Scope | None:
        """Python lexical lookup skips the class namespace inside a method."""
        for size in range(len(caller), -1, -1):
            scope = caller[:size]
            if scope in self.classes:
                continue
            key = (*scope, name)
            if key in self.functions or key in self.classes:
                return key
        return None

    def connect(self) -> None:
        for key, func in self.functions.items():
            nodes = tuple(_body_nodes(func))
            instances: dict[str, Scope] = {}
            for node in nodes:
                variable: str | None = None
                constructor: str | None = None
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target, value = node.targets[0], node.value
                    if isinstance(target, ast.Name) and isinstance(value, ast.Call) \
                            and isinstance(value.func, ast.Name):
                        variable, constructor = target.id, value.func.id
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                        and isinstance(node.annotation, ast.Name):
                    variable, constructor = node.target.id, node.annotation.id
                elif isinstance(node, ast.arg) and isinstance(node.annotation, ast.Name):
                    variable, constructor = node.arg, node.annotation.id
                if variable is not None and constructor is not None:
                    owner = self.resolve(constructor, key)
                    if owner in self.classes:
                        instances[variable] = owner
            edges: set[Scope] = set()
            for node in nodes:
                if not isinstance(node, ast.Call):
                    continue
                target: Scope | None = None
                if _call_name(node) in TIMING_SOURCES:
                    self.clock_readers.add(key)
                if isinstance(node.func, ast.Name):
                    target = self.resolve(node.func.id, key)
                elif isinstance(node.func, ast.Attribute) \
                        and isinstance(node.func.value, ast.Name):
                    receiver = node.func.value.id
                    if receiver in {"self", "cls"}:
                        owner = self.owners[key]
                    else:
                        owner = instances.get(receiver) or self.resolve(receiver, key)
                    if owner in self.classes:
                        target = (*owner, node.func.attr)
                if target in self.functions:
                    edges.add(target)
                    self.targets[id(node)] = target
            self.calls[key] = frozenset(edges)


# Keep the parsed tree alive alongside its identity. Build the index and call
# graph once, rather than walking the whole module for every fixed-point step.
_INDICES: dict[int, tuple[ast.Module, _FunctionIndex]] = {}


def _function_index(tree: ast.Module) -> _FunctionIndex:
    cached = _INDICES.get(id(tree))
    if cached is not None and cached[0] is tree:
        return cached[1]
    index = _FunctionIndex()
    index.collect(tree)
    index.connect()
    _INDICES[id(tree)] = (tree, index)
    return index


#: The calls that put a value INTO a container. A measurement that travels in
#: an attribute is usually appended to a list, not assigned to it.
_MUTATORS = frozenset({"append", "add", "extend", "insert"})


def _module_key(path: Path) -> str:
    """The module's name in the repo: its path without the suffix."""
    return path.relative_to(TESTS_ROOT.parent).with_suffix("").as_posix()


def _module_path(module: str) -> Path | None:
    """The file of a dotted module name under ``tests/``, or None."""
    parts = module.split(".")
    if not parts or parts[0] != "tests":
        return None
    candidate = TESTS_ROOT.joinpath(*parts[1:]).with_suffix(".py")
    return candidate if candidate.exists() else None


def _support_modules(path: Path) -> dict[str, ast.Module]:
    """The LOCAL modules a test file imports, parsed.

    A measurement that travels in an attribute usually has its stopwatch in
    the module that owns the class - and that module is often a support
    module beside the test, not the test file itself (#528). The guard has to
    see it, or the wall-clock assertion that reads the attribute is invisible.

    Only the ``from tests.<...> import ...`` form is resolved: a plain
    ``import <name>`` of a module under ``tests/``, or a dotted name that does
    not start with ``tests.``, is not followed. No file in the suite uses
    either form today - checked - so the gap is a stated limit, not a hole.
    """
    tree = _parsed(path)
    found: dict[str, ast.Module] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        support_path = _module_path(node.module)
        if support_path is None or support_path == path:
            continue
        found[_module_key(support_path)] = _parsed(support_path)
    return found


#: The parsed file, by path. The guard reads the same support modules from
#: every test file that imports them, and a big one (the 3D snapshot tests) is
#: imported by several - parsing it once per importer cost the CI runner more
#: than the whole guard's budget.
_PARSED: dict[Path, ast.Module] = {}


def _parsed(path: Path) -> ast.Module:
    """The file's AST, parsed once per process."""
    tree = _PARSED.get(path)
    if tree is None:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        _PARSED[path] = tree
    return tree


#: The timed attributes of one module, by module key. The attributes belong to
#: the module that owns the class, so they are computed per MODULE and the
#: per-test-file answer is their union - not a recomputation per importer.
_TIMED_BY_MODULE: dict[str, tuple[ast.Module, frozenset[tuple[str, str, str]]]] = {}


def _timed_attributes_of(key: str, tree: ast.Module) -> frozenset[tuple[str, str, str]]:
    """The (module, class, attribute) triples this module's classes carry."""
    cached = _TIMED_BY_MODULE.get(key)
    if cached is not None and cached[0] is tree:
        return cached[1]
    timed = _timed_attributes_in(key, tree)
    _TIMED_BY_MODULE[key] = (tree, timed)
    return timed


def _timed_attributes_in(key: str, tree: ast.Module) -> frozenset[tuple[str, str, str]]:
    timed: set[tuple[str, str, str]] = set()
    index = _function_index(tree)
    clock_reading = _reads_a_clock(tree)
    for class_scope, class_node in index.classes.items():
        for method in class_node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (*class_scope, method.name) not in clock_reading:
                continue
            for attr in _attributes_written_with_a_clock(method, clock_reading, index):
                timed.add((key, class_node.name, attr))
    return frozenset(timed)


def _class_modules(trees: Mapping[str, ast.Module]) -> dict[str, str]:
    """Class name -> the module that defines it, for the classes that are
    defined in exactly one of the analysed modules."""
    owners: dict[str, str | None] = {}
    for key, tree in trees.items():
        for scope in _function_index(tree).classes:
            name = scope[-1]
            owners[name] = None if name in owners else key
    return {name: key for name, key in owners.items() if key is not None}


def _mentions_a_clock(
    value: ast.AST, timed: Collection[Scope], index: _FunctionIndex,
) -> bool:
    """True when the expression reads a timing source, directly or through a
    function that does."""
    for node in ast.walk(value):
        if isinstance(node, ast.Call) and (
            _call_name(node) in TIMING_SOURCES or index.targets.get(id(node)) in timed
        ):
            return True
    return False


def _attributes_written_with_a_clock(
    method: Function, timed: Collection[Scope], index: _FunctionIndex,
) -> set[str]:
    """The attributes of ``self`` that this method fills with a measurement."""
    written: set[str] = set()
    for node in _body_nodes(method):
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in _MUTATORS and node.args):
            target, value = node.func.value, node.args[0]
        if target is None or value is None:
            continue
        if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                and target.value.id == "self"):
            continue
        if _mentions_a_clock(value, timed, index):
            written.add(target.attr)
    return written


def _timed_attributes(trees: Mapping[str, ast.Module]) -> set[tuple[str, str, str]]:
    """(module, class, attribute) of every attribute that a measurement travels
    in.

    The carrier is what the guard has to follow: the stopwatch is in one method
    and the assertion reads the attribute later - often in ANOTHER module, the
    test's. The attribute is scoped to its class, so one class's stopwatch
    never taints another class's attribute of the same name (#528).
    """
    timed: set[tuple[str, str, str]] = set()
    for key, tree in trees.items():
        timed |= _timed_attributes_of(key, tree)
    return timed


def _reads_a_timed_attribute(
    func: ast.AST,
    class_name: str | None,
    module_key: str,
    timed_attributes: Collection[tuple[str, str, str]],
    class_modules: Mapping[str, str],
) -> bool:
    """True when the function reads an attribute that carries a measurement.

    ONE walk of the function answers all three questions it needs - the local
    classes, the attributes that are only counted, and the attribute reads
    themselves - because the guard reads every test file in the suite, and three
    walks per function added up on the CI runner.
    """
    if not timed_attributes:
        return False
    local: dict[str, str] = {}
    counted: set[int] = set()
    reads: list[tuple[str | None, str, int]] = []
    for node in _body_nodes(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
            if isinstance(target, ast.Name) and isinstance(value, ast.Call) \
                    and isinstance(value.func, ast.Name):
                local[target.id] = value.func.id
        if isinstance(node, ast.Call) and _call_name(node) == "len" and len(node.args) == 1:
            for inner in ast.walk(node.args[0]):
                if isinstance(inner, ast.Attribute):
                    counted.add(id(inner))
        if isinstance(node, ast.Attribute):
            owner = node.value
            if isinstance(owner, ast.Name) and owner.id == "self":
                reads.append((class_name, node.attr, id(node)))
            elif isinstance(owner, ast.Name) and owner.id in local:
                reads.append((local[owner.id], node.attr, id(node)))
    for owner_class, attr, node_id in reads:
        if node_id in counted:
            continue                       # only counted, not a duration
        if owner_class is None:
            continue
        module_of = module_key if owner_class == class_name else class_modules.get(owner_class)
        if module_of is None:
            continue
        if (module_of, owner_class, attr) in timed_attributes:
            return True
    return False


def _reads_a_clock(tree: ast.Module, seed: Collection[Scope] = ()) -> set[Scope]:
    """Names of functions that reach a timing source, transitively through calls.

    A fixed point rather than a single pass: `_assert_repaint_budget` only becomes
    clock-reading after `_measure_repaints` has, and the ordering in the source file
    is not a dependency order.
    """
    return _closure(set(seed) | _function_index(tree).clock_readers, tree)


def _orders_a_value_against_a_bound(func: ast.AST) -> bool:
    for node in _body_nodes(func):
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
            continue
        if any(isinstance(op, ORDERING_OPS) for op in node.test.ops):
            return True
    return False


def _closure(seed: set[Scope], tree: ast.Module) -> set[Scope]:
    """Grow `seed` to a fixed point over who calls whom, within this module."""
    calls = _function_index(tree).calls
    grown = set(seed)
    changed = True
    while changed:
        changed = False
        for name, targets in calls.items():
            if name in grown:
                continue
            if not targets.isdisjoint(grown):
                grown.add(name)
                changed = True
    return grown


def _sensitive_names(
    tree: ast.Module,
    module_key: str = "",
    timed_attributes: Collection[tuple[str, str, str]] = (),
    class_modules: Mapping[str, str] = {},
) -> set[Scope]:
    """Functions that order a measured duration against a bound, and their callers.

    Two closures, not one. `_reads_a_clock` closes the clock over the call graph, then
    the *sensitivity* is closed the same way — because the propagation has to survive a
    hop that carries only an assertion. The real code does exactly this:

        test_xyz()  ->  run_budget()  ->  _assert_budget()  ->  _measure()

    `test_xyz` never mentions the asserter, and `_assert_budget` never calls a clock
    directly. Closing only the clock and asking whether a test *directly* calls a
    sensitive function misses that whole chain; it was caught executing against this
    file's own `collect_duration_asserts`, which returned `[]` for it.

    A third source joins the clock: an attribute that carries a measurement
    (#528). The stopwatch may sit in another module entirely — in the class
    that owns it — and the assertion reads the attribute, so the reader is
    clock-reading too.
    """
    index = _function_index(tree)
    # A local definition shadows an imported class of the same name. This
    # also lets the original inline-TimedBaker layout be replayed with the
    # remaining support-module imports intact.
    class_modules = dict(class_modules) | {
        scope[-1]: module_key for scope in index.classes if len(scope) == 1
    }
    seed = {
        name for name, func in index.functions.items()
        if _reads_a_timed_attribute(func, index.owners[name][-1] if index.owners[name] else None,
                                    module_key, timed_attributes, class_modules)
    }
    timed = _reads_a_clock(tree, seed)
    sensitive = {
        name for name in timed if _orders_a_value_against_a_bound(index.functions[name])
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


def collect_duration_asserts(
    tree: ast.Module,
    *,
    module_key: str = "",
    support: Mapping[str, ast.Module] | None = None,
) -> list[tuple[str, bool]]:
    """`(node_id, marked)` for every test that can be wall-clock sensitive.

    A test qualifies when it orders a duration itself, or when it calls something that
    does — which is the shape the NFR module uses, where the test's own body contains
    no assertion at all.

    The **marker** is inherited from an enclosing class; the **sensitivity** is not.
    One timing test in a class of twenty ordinary ones must not force all twenty onto
    the quiet runner, and a first version that propagated sensitivity to the class got
    that wrong in the opposite direction - it demanded markers for every sibling test.

    ``support`` holds the LOCAL modules the test file imports (#528): a
    measurement that travels in an attribute has its stopwatch in the module
    that owns the class, which is usually one of them.
    """
    trees: dict[str, ast.Module] = dict(support or {})
    trees[module_key] = tree
    timed_attributes = _timed_attributes(trees)
    class_modules = _class_modules(trees)
    sensitive = _sensitive_names(tree, module_key, timed_attributes, class_modules)
    # The index already visited every definition, including nested classes and
    # helpers. Marker inheritance follows its lexical prefixes; walking every
    # expression in the repository again adds no information (#601).
    index = _function_index(tree)
    definitions = index.classes | index.functions
    return sorted(
        ("::".join(key), any(is_perf_marked(definitions[key[:size]])
                            for size in range(1, len(key) + 1)))
        for key in sensitive if key[-1].startswith("test_")
    )


def _python_files() -> list[Path]:
    return [p for p in TESTS_ROOT.rglob("test_*.py") if "__pycache__" not in p.parts]


def test_no_wall_clock_assertion_is_unmarked() -> None:
    """The guard: any duration assertion without `perf` can flake under workers."""
    offenders: list[str] = []
    scanned = 0
    for path in _python_files():
        tree = _parsed(path)
        support = _support_modules(path)
        for node_id, marked in collect_duration_asserts(
            tree, module_key=_module_key(path), support=support
        ):
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


def test_repository_scan_parses_each_module_once(tmp_path, monkeypatch) -> None:
    """The import-support scan and the main scan must share their AST (#601)."""
    root = tmp_path / "tests"
    root.mkdir()
    path = root / "test_budgets.py"
    path.write_text(
        "import pytest, time\n" + "\n".join(
            f"@pytest.mark.perf\ndef test_budget_{i}():\n"
            "    started = time.monotonic()\n"
            "    assert time.monotonic() - started < 1.0\n"
            for i in range(12)
        ), encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "TESTS_ROOT", root)
    monkeypatch.setitem(globals(), "_python_files", lambda: [path])
    parsed: list[str] = []
    real = ast.parse

    def parse(source, filename="<unknown>", *args, **kwargs):
        parsed.append(str(filename))
        return real(source, filename, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(ast, "parse", parse)
        test_no_wall_clock_assertion_is_unmarked()
    assert parsed == [str(path)]


@pytest.mark.parametrize(("relative", "class_name"), [
    ("ui/test_quick3d_host.py", "TestWaitReady"),
    ("perf/test_scene3d_plants_budget.py", "TestPlantBuildBudget"),
    ("perf/test_nfr_budgets.py", "TestNfrPerf01LinePaintBudgets"),
])
def test_mixed_budget_groups_mark_methods_instead_of_the_class(relative, class_name) -> None:
    """A budget must not serialize its deterministic sibling contracts (#601)."""
    tree = ast.parse((TESTS_ROOT / relative).read_text(encoding="utf-8"))
    group = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                 and node.name == class_name)
    assert not is_perf_marked(group)


def test_a_measurement_that_travels_in_an_attribute_is_seen() -> None:
    """#528, first half: the stopwatch is in ANOTHER module - in the class that
    owns it - and the assertion reads the attribute it fills. The guard has to
    follow the carrier, or the wall-clock assertion is invisible and the marker
    is a comment instead of a rule.

    This is the shape of the ground bake's G3 gate: ``TimedBaker.bake`` times
    itself into ``milliseconds``, and the test compares the median against
    10 ms."""
    support = ast.parse(
        "import time\n"
        "class TimedBaker:\n"
        "    def __init__(self):\n"
        "        self.milliseconds = []\n"
        "    def bake(self, records):\n"
        "        started = time.perf_counter()\n"
        "        try:\n"
        "            return records\n"
        "        finally:\n"
        "            self.milliseconds.append((time.perf_counter() - started) * 1000.0)\n",
        filename="support.py",
    )
    test_module = ast.parse(
        "import statistics\n"
        "from support import TimedBaker\n"
        "def test_the_median_of_a_bake_is_under_ten_milliseconds():\n"
        "    baker = TimedBaker()\n"
        "    baker.bake([])\n"
        "    median = statistics.median(baker.milliseconds)\n"
        "    assert median <= 10.0\n",
        filename="test_the_bake.py",
    )
    verdict = collect_duration_asserts(
        test_module, module_key="tests/test_the_bake", support={"tests/support": support})
    assert verdict == [("test_the_median_of_a_bake_is_under_ten_milliseconds", False)], (
        "the wall-clock assertion behind an attribute was not seen"
    )


def test_a_test_that_times_nothing_is_not_seen() -> None:
    """#528, second half: a stopwatch in a method of the same bare name
    elsewhere does not make an unrelated test a wall-clock assertion.

    The test below calls the timed method and asserts nothing about a
    duration; it must not be dragged onto the quiet runner by a stopwatch that
    lives in another class, in another module."""
    support = ast.parse(
        "import time\n"
        "class TimedBaker:\n"
        "    def bake(self, records):\n"
        "        started = time.perf_counter()\n"
        "        try:\n"
        "            return records\n"
        "        finally:\n"
        "            self.milliseconds.append(time.perf_counter() - started)\n",
        filename="support.py",
    )
    test_module = ast.parse(
        "from support import TimedBaker\n"
        "def test_a_scripted_session_ends_on_a_from_scratch_bake():\n"
        "    baker = TimedBaker()\n"
        "    tiles = baker.bake([])\n"
        "    assert tiles == []\n",
        filename="test_the_session.py",
    )
    verdict = collect_duration_asserts(
        test_module, module_key="tests/test_the_session", support={"tests/support": support})
    assert verdict == [], (
        "a test that times nothing was flagged because a method of the same bare name "
        "elsewhere holds a stopwatch"
    )


def _verdict(source: str) -> list[tuple[str, bool]]:
    return collect_duration_asserts(ast.parse(source))


@pytest.mark.parametrize("timed_first", [False, True])
def test_same_module_bakers_keep_their_own_clock_sensitivity(timed_first: bool) -> None:
    """#528: a count bound on the ordinary baker is not a timing budget.

    Both definition orders matter: last-definition-wins can also hide the
    timed baker's real attribute budget.
    """
    ordinary = (
        "class GroundBaker:\n"
        "    def bake(self, records):\n"
        "        return records\n"
    )
    timed = (
        "class TimedBaker:\n"
        "    def bake(self, records):\n"
        "        started = time.perf_counter()\n"
        "        self.milliseconds.append(time.perf_counter() - started)\n"
        "        return records\n"
    )
    tree = ast.parse(
        "import time, statistics\n"
        + (timed + ordinary if timed_first else ordinary + timed)
        + "class TestAnEditSession:\n"
        "    def test_session(self):\n"
        "        baker = GroundBaker()\n"
        "        tiles = baker.bake([])\n"
        "        assert len(tiles) <= 4\n"
        "class TestBudget:\n"
        "    def test_session(self):\n"
        "        baker = TimedBaker()\n"
        "        baker.bake([])\n"
        "        assert statistics.median(baker.milliseconds) <= 10.0\n"
    )
    assert collect_duration_asserts(tree, module_key="tests/same_module") == [
        ("TestBudget::test_session", False),
    ]


def test_the_original_ground_bake_module_accepts_its_timed_helper_inline() -> None:
    """Replay the real workaround's removal without editing either input file."""
    path = TESTS_ROOT / "integration/test_scene3d_ground_bake.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    support = _support_modules(path)
    helper = next(node for node in support["tests/integration/ground_bake_support"].body
                  if isinstance(node, ast.ClassDef) and node.name == "TimedBaker")
    tree.body.append(helper)
    verdict = dict(collect_duration_asserts(tree, module_key=_module_key(path), support=support))
    assert "TestAnEditSession::test_a_scripted_session_ends_on_the_tiles_of_a_from_scratch_bake" \
        not in verdict
    assert verdict["TestOneSmallEdit::test_a_small_move_repaints_few_tiles_within_its_bound"]


@pytest.mark.parametrize("timed_first", [False, True])
def test_duplicate_methods_keep_both_call_graph_closures_scoped(timed_first: bool) -> None:
    ordinary = (
        "class TestCount:\n"
        "    def measure(self):\n"
        "        return 2\n"
        "    def budget(self):\n"
        "        assert self.measure() <= 4\n"
        "    def test_budget(self):\n"
        "        self.budget()\n"
    )
    timed = (
        "class TestDuration:\n"
        "    def measure(self):\n"
        "        return time.perf_counter()\n"
        "    def budget(self):\n"
        "        assert self.measure() <= 10\n"
        "    def test_budget(self):\n"
        "        self.budget()\n"
    )
    assert _verdict("import time\n" + (timed + ordinary if timed_first else ordinary + timed)) == [
        ("TestDuration::test_budget", False),
    ]


def test_nested_helpers_with_the_same_name_do_not_share_a_clock() -> None:
    assert _verdict(
        "import time\n"
        "def test_count():\n"
        "    def measure():\n"
        "        return 2\n"
        "    assert measure() <= 4\n"
        "def test_duration():\n"
        "    def measure():\n"
        "        return time.perf_counter()\n"
        "    assert measure() <= 10\n"
    ) == [("test_duration", False)]


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
