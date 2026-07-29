"""Gate: ``app/settings.create_qsettings()`` is the only settings-store factory.

Issue #285, ADR-041. #283 measured what an escape hatch costs: ``UiStateStore``
built its own ``QSettings`` for the real ``cofade / Open Garden Planner`` key, so
the conftest isolation — which only knew about ``AppSettings`` — did not cover
it, and every full-app test read *and overwrote* the developer's own window
state (120 writes from one test file). Fixing that one store is not the repair;
the repair is that a *new* store cannot repeat it.

Three rules, over ``src/`` **and** ``tests/`` (the incident was observed from the
test side, and a stray store in a test leaks exactly as hard):

1. Only ``app/settings.py`` may name ``QSettings`` at all — import it, annotate
   with it, or construct it. Everything else takes a store from the factory.
   Three test modules are exempt for stated reasons; the exemption list is
   itself asserted to be exactly those three, in both directions.
2. Nobody may call ``QSettings.setDefaultFormat()`` / ``setPath()``: those are
   process-global statics Qt never reverts (§11.4 — a leaked ``setPath`` to a
   deleted ``tmp_path`` once broke six unrelated tests two-thirds of the way
   through a session).
3. Nobody may build a store at **import time** — not via ``create_qsettings()``
   and not via any wrapper that owns one (``AppSettings``, ``UiStateStore``,
   ``get_settings``), at module scope, in a class body, in a decorator, in a
   default argument or in an annotation. This is the invariant the whole test
   isolation rests on and the mechanism's one real hole: the session fixture
   redirects by rebinding the factory's org/app names, which retargets every
   store built *afterwards* but cannot retarget one that already exists — and an
   import-time call runs before any fixture. A module-level
   ``_PREFS = AppSettings()`` would therefore sit on the user's real key for the
   whole session, reintroducing #283 with no singleton reset to save it.

The scan is an AST walk, not a regex, and every detector has a positive control
in ``TestDetectorsCatchKnownEscapes`` — fed the exact escape it exists to catch.
Both disciplines were bought the hard way, one review at a time: a line-anchored
regex missed ``from PyQt6.QtCore import (\n    QSettings as _Q,\n)`` (the class is
named on a line with no ``import`` keyword), and a first cut of rule 3 matched
only the literal name ``create_qsettings`` — so a module-level ``AppSettings()``,
which is what a developer would actually write, sailed straight through the gate
named after that very invariant. Falsify against the API people use, not the
primitive the gate is written in terms of.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Collection
from pathlib import Path

import pytest

import open_garden_planner.app.settings as settings_module

SRC_ROOT = Path(settings_module.__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parents[1]
TESTS_ROOT = REPO_ROOT / "tests"
CHOKEPOINT = SRC_ROOT / "app" / "settings.py"

STORE_CLASS = "QSettings"
GLOBAL_STATICS = frozenset({"setDefaultFormat", "setPath"})

# Anything whose construction yields (or fetches) an object holding a store.
# Naming only the low-level factory here was a real gate hole — see the module
# docstring; nobody caches `create_qsettings()`, they cache the wrapper.
STORE_BUILDERS = frozenset(
    {"create_qsettings", "AppSettings", "UiStateStore", "get_settings"}
)

# Test modules that legitimately name QSettings, each with the reason. Kept tiny
# and asserted exact (`test_the_exemptions_are_exactly_these_and_all_needed`) so
# growing it is a deliberate, reviewed act rather than the path of least effort.
STORE_CLASS_EXEMPT_TESTS = {
    "tests/conftest.py",  # captures/restores the defaultFormat static (tripwire)
    "tests/unit/test_ui_state.py",  # builds the temp-INI store the fixture injects
    "tests/integration/test_settings_isolation.py",  # spies value()/setValue()
}

Detector = Callable[[ast.AST], list[int]]


def _callee(func: ast.expr) -> str:
    """Trailing name of a call target: ``a.b.c()`` -> ``"c"``, ``f()`` -> ``"f"``."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _owner(func: ast.expr) -> str:
    """Name the call is made *on*: ``QSettings.setPath()`` -> ``"QSettings"``."""
    if isinstance(func, ast.Attribute):
        return _callee(func.value)
    return ""


def _names_the_store_class(tree: ast.AST) -> list[int]:
    """Lines that import, reference or construct ``QSettings`` in any form."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            # Covers `import x.QSettings`, `from x import QSettings`, and every
            # alias/parenthesised spelling of either.
            if any(alias.name.split(".")[-1] == STORE_CLASS for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id == STORE_CLASS:
            lines.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == STORE_CLASS:
            # `QtCore.QSettings(...)` needs no QSettings import at all.
            lines.append(node.lineno)
    return sorted(set(lines))


def _calls_global_statics(tree: ast.AST) -> list[int]:
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _callee(node.func) in GLOBAL_STATICS
        and _owner(node.func) == STORE_CLASS
    )


def _builds_a_store_at_import_time(tree: ast.AST) -> list[int]:
    """Store-building calls evaluated when the module is imported.

    Deferred (fine): anything inside a function or lambda *body*. Immediate (not
    fine): module scope, class body, a decorator, a default argument, an
    annotation — all evaluated while the surrounding statement executes.
    """
    lines: list[int] = []

    def visit(node: ast.AST, deferred: bool) -> None:
        if (
            not deferred
            and isinstance(node, ast.Call)
            and _callee(node.func) in STORE_BUILDERS
        ):
            lines.append(node.lineno)

        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            args = node.args
            immediate = [
                *node.decorator_list,
                *args.defaults,
                *(d for d in args.kw_defaults if d is not None),
                *(
                    a.annotation
                    for a in (
                        *args.posonlyargs,
                        *args.args,
                        *args.kwonlyargs,
                        args.vararg,
                        args.kwarg,
                    )
                    if a is not None and a.annotation is not None
                ),
            ]
            if node.returns is not None:
                immediate.append(node.returns)
            for expr in immediate:
                visit(expr, deferred)
            for stmt in node.body:
                visit(stmt, True)
            return

        if isinstance(node, ast.Lambda):
            for expr in (
                *node.args.defaults,
                *(d for d in node.args.kw_defaults if d is not None),
            ):
                visit(expr, deferred)
            visit(node.body, True)
            return

        for child in ast.iter_child_nodes(node):
            visit(child, deferred)

    visit(tree, False)
    return sorted(set(lines))


def _python_sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _all_sources() -> list[Path]:
    return _python_sources(SRC_ROOT) + _python_sources(TESTS_ROOT)


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _scan(detector: Detector, *, exempt: Collection[str] = ()) -> list[str]:
    """Run a detector over every scanned module, formatting hits as ``path:line``."""
    offenders: list[str] = []
    for path in _all_sources():
        rel = _rel(path)
        if rel in exempt:
            continue
        offenders += [f"{rel}:{line}" for line in detector(_parse(path))]
    return offenders


class TestSingleConstructionSite:
    def test_the_scan_actually_covers_both_trees(self) -> None:
        """Anti-vacuity: a mis-resolved root would make every gate below pass."""
        sources = _all_sources()
        assert len(sources) > 50, f"only found {len(sources)} modules"
        assert CHOKEPOINT in sources
        assert TESTS_ROOT / "conftest.py" in sources

    def test_the_chokepoint_itself_still_names_the_store_class(self) -> None:
        """Anti-vacuity: the detector must see the one legitimate site."""
        assert _names_the_store_class(_parse(CHOKEPOINT)), (
            "the detector no longer matches create_qsettings() — the gate below "
            "would pass no matter what other modules do"
        )

    def test_nothing_else_names_the_store_class(self) -> None:
        offenders = _scan(
            _names_the_store_class,
            exempt={_rel(CHOKEPOINT), *STORE_CLASS_EXEMPT_TESTS},
        )
        assert offenders == [], (
            "only app/settings.py may import, annotate with or construct "
            "QSettings; everything else takes a store from create_qsettings() "
            "(issue #285):\n" + "\n".join(offenders)
        )

    def test_the_exemptions_are_exactly_these_and_all_needed(self) -> None:
        """No dead exemptions, and no silent additions.

        An exemption that no longer needs to exist is an open door nobody is
        watching; an exemption added casually is how the gate rots.
        """
        for rel in sorted(STORE_CLASS_EXEMPT_TESTS):
            path = REPO_ROOT / rel
            assert path.exists(), f"exempt file no longer exists: {rel}"
            assert _names_the_store_class(_parse(path)), (
                f"{rel} no longer names QSettings — drop its exemption"
            )


class TestNoProcessGlobalQSettingsStatics:
    def test_only_the_conftest_tripwire_touches_the_global_statics(self) -> None:
        """`src/` may never; the one sanctioned call restores what it captured."""
        offenders = _scan(_calls_global_statics, exempt={"tests/conftest.py"})
        assert offenders == [], (
            "QSettings.setDefaultFormat()/setPath() are process-global and never "
            "reverted by Qt (§11.4):\n" + "\n".join(offenders)
        )


class TestNoStoreIsBuiltAtImportTime:
    def test_nothing_builds_a_store_at_import_time(self) -> None:
        """The invariant the session-wide test isolation silently depends on.

        Rebinding the factory's names redirects stores built *after* the
        rebinding. An import-time store is constructed before any fixture, so it
        is pinned to the user's real key for the whole session — #283, again.
        """
        offenders = _scan(_builds_a_store_at_import_time)
        assert offenders == [], (
            "a settings store must be built at runtime, never at import time "
            "(module scope, class body, decorator, default argument or "
            "annotation) — such a store cannot be redirected by the test "
            "isolation (ADR-041):\n" + "\n".join(offenders)
        )


class TestDetectorsCatchKnownEscapes:
    """Positive controls: each detector, fed the exact form it exists to catch.

    Without these, a detector that quietly stops matching (a refactor, a new
    Python syntax, a typo in a node type) turns the whole gate green.
    """

    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("plain import", "from PyQt6.QtCore import QSettings"),
            ("aliased import", "from PyQt6.QtCore import QSettings as _Q"),
            # The form that broke the original line-anchored regex gate: the
            # class is named on a line carrying no `import` keyword.
            (
                "parenthesised aliased import",
                "from PyQt6.QtCore import (\n    QSettings as _Q,\n)",
            ),
            ("module-attribute construction", 'QtCore.QSettings("cofade", "OGP")'),
            ("bare construction", 'QSettings("cofade", "OGP")'),
            ("annotation only", "def f(s: QSettings) -> None: ..."),
        ],
    )
    def test_store_class_detector(self, label: str, source: str) -> None:
        assert _names_the_store_class(ast.parse(source)), f"missed: {label}"

    def test_global_statics_detector(self) -> None:
        assert _calls_global_statics(
            ast.parse("QSettings.setDefaultFormat(fmt)\nQSettings.setPath(a, b, c)")
        ) == [1, 2]
        # Must not fire on the many unrelated setPath() calls in src/ (QPainterPath).
        assert _calls_global_statics(ast.parse("item.setPath(path)")) == []

    @pytest.mark.parametrize(
        ("label", "source", "expected"),
        [
            # Every wrapper, not just the primitive — the hole a review found in
            # the first cut of this detector.
            ("module scope, factory", "_S = create_qsettings()", True),
            ("module scope, qualified", "_S = settings.create_qsettings()", True),
            ("module scope, AppSettings", "_PREFS = AppSettings()", True),
            ("module scope, UiStateStore", "_UI = UiStateStore()", True),
            ("module scope, get_settings", "_S = get_settings()", True),
            ("class body", "class C:\n    store = get_settings()", True),
            ("nested class body", "class A:\n    class B:\n        s = AppSettings()", True),
            ("default argument", "def f(s=AppSettings()):\n    pass", True),
            ("annotation position", "def f(x: type(AppSettings())) -> None: ...", True),
            ("decorator", "@wrap(get_settings())\ndef f():\n    pass", True),
            ("module-level try", "try:\n    _S = AppSettings()\nexcept Exception:\n    _S = None", True),
            ("module-level comprehension", "_L = [AppSettings() for _ in (1,)]", True),
            ("walrus at module scope", "if (s := get_settings()):\n    pass", True),
            ("function body", "def f():\n    return create_qsettings()", False),
            ("method body", "class C:\n    def f(self):\n        AppSettings()", False),
            ("lambda body", "f = lambda: get_settings()", False),
        ],
    )
    def test_import_time_detector(
        self, label: str, source: str, expected: bool
    ) -> None:
        assert bool(_builds_a_store_at_import_time(ast.parse(source))) is expected, (
            f"wrong verdict for: {label}"
        )


class TestChokepointContract:
    def test_names_and_factory_agree(self) -> None:
        """The factory must read the module names, not a private copy of them."""
        store = settings_module.create_qsettings()
        assert store.organizationName() == settings_module.ORGANIZATION_NAME
        assert store.applicationName() == settings_module.APPLICATION_NAME

    def test_rebinding_the_names_redirects_new_stores(self, monkeypatch) -> None:
        """The property the session-wide isolation in conftest.py depends on.

        If ``create_qsettings`` ever captures the names at import time (default
        argument, module-level tuple, ``functools.partial``), the whole test
        suite silently starts writing to the user's real store again.
        """
        monkeypatch.setattr(settings_module, "ORGANIZATION_NAME", "ogp_gate_org")
        monkeypatch.setattr(settings_module, "APPLICATION_NAME", "ogp_gate_app")

        store = settings_module.create_qsettings()

        assert store.organizationName() == "ogp_gate_org"
        assert store.applicationName() == "ogp_gate_app"

    def test_rebinding_does_not_retarget_an_existing_store(self, monkeypatch) -> None:
        """The limit of the seam, stated so nobody documents it wrongly again.

        A store binds its (organization, application) at construction. The
        isolation works because both wrappers build one per instance and
        conftest nulls the ``AppSettings`` singleton — *not* because existing
        objects follow the rebinding. This is why import-time construction is
        gated above (ADR-041).
        """
        original = settings_module.ORGANIZATION_NAME
        before = settings_module.create_qsettings()
        assert before.organizationName() == original

        monkeypatch.setattr(settings_module, "ORGANIZATION_NAME", "ogp_gate_org")

        # Asserted as equality against the captured name, not `!= "ogp_gate_org"`:
        # the inequality form also passes for "", i.e. in a broken state.
        assert before.organizationName() == original
        assert settings_module.create_qsettings().organizationName() == "ogp_gate_org"

    def test_appsettings_and_ui_state_share_the_backend(self) -> None:
        """One chokepoint means one file/key — the point of the whole exercise."""
        from open_garden_planner.app.settings import AppSettings
        from open_garden_planner.app.ui_state import UiStateStore

        assert AppSettings()._settings.fileName() == UiStateStore()._settings.fileName()
