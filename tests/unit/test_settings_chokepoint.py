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
   Three test modules are exempt for stated reasons, and a test fails if an
   exemption stops being needed (the other direction — "nobody adds a fourth" —
   is a review duty, not something a check in this file could honestly enforce).
2. Nobody may call ``QSettings.setDefaultFormat()`` / ``setPath()``: those are
   process-global statics Qt never reverts (§11.4 — a leaked ``setPath`` to a
   deleted ``tmp_path`` once broke six unrelated tests two-thirds of the way
   through a session).
3. Nobody *should* build a store at **import time** — not via
   ``create_qsettings()`` and not via any wrapper that owns one
   (``AppSettings``, ``UiStateStore``, ``get_settings``), at module scope, in a
   class body, in a decorator, in a default argument or in an annotation. Note
   the weaker verb: this rule is **belt-and-braces**, not what makes the test
   isolation hold. ``tests/conftest.py`` rebinds the factory's org/app names at
   its own *import* time (module scope, not in a fixture), and pytest imports the
   root conftest before any test module — so even an import-time store is built
   after the redirection and lands in the test key. What the rule still buys: a
   store constructed at import time can be redirected by *nothing* afterwards (a
   ``QSettings`` binds its organization/application at construction), so it is a
   latent trap for any other isolation scheme and a smell in its own right.

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
SCRIPTS_ROOT = REPO_ROOT / "scripts"
CHOKEPOINT = SRC_ROOT / "app" / "settings.py"
CONFTEST = TESTS_ROOT / "conftest.py"

STORE_CLASS = "QSettings"
GLOBAL_STATICS = frozenset({"setDefaultFormat", "setPath"})

# The real user store's organization. Hardcoded on purpose: by the time this
# module is imported the module global has already been redirected, and the point
# is that this literal must never be what the suite is pointed at.
PRODUCTION_ORGANIZATION = "cofade"

# Anything whose construction yields (or fetches) an object holding a store.
# Naming only the low-level factory here was a real gate hole — see the module
# docstring; nobody caches `create_qsettings()`, they cache the wrapper.
STORE_BUILDERS = frozenset(
    {"create_qsettings", "AppSettings", "UiStateStore", "get_settings"}
)

# Test modules that legitimately name QSettings, each with the reason. Kept tiny;
# `test_no_exemption_is_dead` fails if one stops being needed. Adding a fourth is
# caught by review, not by this file — a length assertion against a literal three
# lines above would be tautological, so it is not pretended here.
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


def _builder_names(tree: ast.AST) -> frozenset[str]:
    """Local spellings in this module that resolve to a store builder.

    ``_callee()`` can only see the call-site spelling, so the raw
    ``STORE_BUILDERS`` names are not enough: ``AppSettings as _Prefs`` …
    ``_Prefs()`` walked past an earlier cut of this detector (review round 3,
    one experiment — the same way rounds 1 and 2 broke the two before it). Also
    resolves subclasses and plain assignment aliases, transitively, so
    ``class P(AppSettings)`` … ``P()`` and ``_Mk = AppSettings`` … ``_Mk()``
    count. Terminates because ``names`` only ever grows and is bounded by the
    module's alias/ClassDef/Assign count.
    """
    names = set(STORE_BUILDERS)
    while True:
        grown = set(names)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                grown |= {
                    alias.asname
                    for alias in node.names
                    if alias.asname and alias.name.split(".")[-1] in names
                }
            elif isinstance(node, ast.ClassDef) and any(
                _callee(base) in names for base in node.bases
            ):
                grown.add(node.name)
            elif (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Name | ast.Attribute)
                and _callee(node.value) in names
            ):
                # `_Mk = AppSettings` … `_Mk()`. Same escape class as the import
                # alias, one keystroke away — the pattern that cost three review
                # rounds, so both spellings are handled rather than just the one
                # that was demonstrated.
                grown |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        if grown == names:
            return frozenset(names)
        names = grown


def _builds_a_store_at_import_time(tree: ast.AST) -> list[int]:
    """Store-building calls evaluated when the module is imported.

    Deferred (fine): anything inside a function or lambda *body*. Immediate (not
    fine): module scope, class body, a decorator, a default argument, an
    annotation. Annotations and ``if TYPE_CHECKING`` blocks are flagged even
    though `from __future__ import annotations` means they are never evaluated —
    deliberately over-strict, since nothing legitimate builds a store there.

    **Acknowledged limit:** this reads names, so one level of indirection defeats
    it. Direct *renamings* are resolved (import alias, subclass, assignment
    alias), but a call through a **helper** is not — ``def _b(): return
    AppSettings()`` then ``_P = _b()`` at module scope is invisible, as is a
    constructor that builds a store transitively (a module-level
    ``GardenPlannerApp()`` would), and so are `functools.partial` / container
    lookups. That is affordable because this rule is **not** what makes the test
    isolation hold: `tests/conftest.py` redirects at import time, so even an
    import-time store lands in the test key. The rule is belt-and-braces against
    a store nothing can redirect later, and a code smell in its own right.
    """
    builders = _builder_names(tree)
    lines: list[int] = []

    def visit(node: ast.AST, deferred: bool) -> None:
        if (
            not deferred
            and isinstance(node, ast.Call)
            and _callee(node.func) in builders
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
    # `scripts/` is in scope too: a dev script runs outside pytest, where no
    # conftest redirects anything, so a store built there is by definition the
    # real one. (This does not by itself close the §11.4 probe-script incident —
    # that probe wrote through `get_settings()` at *runtime*, which no static gate
    # can forbid; the mitigation for that is the recipe in the debug-verbose
    # skill's corollary. Scanning is still worth it: it keeps the one place a
    # script could hand-roll a store closed.)
    return (
        _python_sources(SRC_ROOT)
        + _python_sources(TESTS_ROOT)
        + _python_sources(SCRIPTS_ROOT)
    )


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
        assert CONFTEST in sources
        assert SCRIPTS_ROOT.is_dir() and any(
            p.is_relative_to(SCRIPTS_ROOT) for p in sources
        )

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

    def test_no_exemption_is_dead(self) -> None:
        """An exemption that no longer needs to exist is an unwatched open door."""
        for rel in sorted(STORE_CLASS_EXEMPT_TESTS):
            path = REPO_ROOT / rel
            assert path.exists(), f"exempt file no longer exists: {rel}"
            assert _names_the_store_class(_parse(path)), (
                f"{rel} no longer names QSettings — drop its exemption"
            )


class TestNoProcessGlobalQSettingsStatics:
    def test_the_conftest_tripwire_still_exists(self) -> None:
        """Guards the exemption below against pointing at a file that stopped
        needing it — which would silently retire the §11.4 six-broken-tests
        backstop while leaving an unwatched hole in this gate."""
        assert _calls_global_statics(_parse(CONFTEST)), (
            "conftest no longer touches QSettings.defaultFormat() — either the "
            "tripwire was removed (restore it) or its exemption is now dead"
        )

    def test_only_the_conftest_tripwire_touches_the_global_statics(self) -> None:
        """Nothing may set them; the one sanctioned call restores what it captured."""
        offenders = _scan(_calls_global_statics, exempt={_rel(CONFTEST)})
        assert offenders == [], (
            "QSettings.setDefaultFormat()/setPath() are process-global and never "
            "reverted by Qt (§11.4):\n" + "\n".join(offenders)
        )


class TestNoStoreIsBuiltAtImportTime:
    def test_nothing_builds_a_store_at_import_time(self) -> None:
        """Belt-and-braces, not the load-bearing guarantee — see the module
        docstring's rule 3 and ``test_the_redirection_is_at_conftest_module_scope``
        below, which pins the mechanism that actually holds.

        A store built at import time is fixed to whatever names were in effect at
        that moment and can be redirected by nothing afterwards. Under this
        suite's conftest that is already the test key, so this is a smell rather
        than a leak — but it is a trap for anyone isolating differently.
        """
        offenders = _scan(_builds_a_store_at_import_time)
        assert offenders == [], (
            "a settings store must be built at runtime, never at import time "
            "(module scope, class body, decorator, default argument or "
            "annotation) — such a store cannot be redirected by the test "
            "isolation (ADR-041):\n" + "\n".join(offenders)
        )


class TestTheRedirectionMechanismItself:
    """Pin *where* the redirection lives, because everything defers to it.

    Since the rules above are belt-and-braces, the isolation's actual guarantee
    is that ``tests/conftest.py`` rebinds the two names at **module scope**, i.e.
    at conftest import time — before pytest imports any test module, so a store
    built during an import is still redirected. Demote those two lines into a
    fixture (or into an ``if``/``try`` block) and the guarantee silently weakens
    to what it was before this test existed, with nothing else noticing.
    """

    @staticmethod
    def _module_scope_rebindings() -> set[str]:
        tree = _parse(CONFTEST)
        return {
            target.attr
            for stmt in tree.body  # top level only — not nested in anything
            if isinstance(stmt, ast.Assign)
            for target in stmt.targets
            if isinstance(target, ast.Attribute)
            and target.attr in {"ORGANIZATION_NAME", "APPLICATION_NAME"}
        }

    def test_the_redirection_is_at_conftest_module_scope(self) -> None:
        assert self._module_scope_rebindings() == {
            "ORGANIZATION_NAME",
            "APPLICATION_NAME",
        }, (
            "tests/conftest.py must rebind BOTH settings names at module scope. "
            "Anywhere else (a fixture, a guard) runs after collection, and a "
            "QSettings built during a module import can never be retargeted "
            "afterwards — see ADR-041."
        )

    def test_the_redirection_actually_took(self) -> None:
        """Behavioural counterpart: the AST check above could pass while the
        values assigned were wrong."""
        assert settings_module.create_qsettings().organizationName() != (
            PRODUCTION_ORGANIZATION
        ), "the running suite is pointed at the real user store"


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
            # Aliases and subclasses change the call-site spelling, which is all
            # `_callee()` can see — the round-3 escape.
            (
                "aliased wrapper import",
                "from x import AppSettings as _Prefs\n_P = _Prefs()",
                True,
            ),
            (
                "aliased factory import",
                "from x import create_qsettings as _mk\n_S = _mk()",
                True,
            ),
            ("subclass", "class P(AppSettings):\n    pass\n_P = P()", True),
            ("assignment alias", "_Mk = AppSettings\n_P = _Mk()", True),
            (
                "assignment alias of an aliased import",
                "from x import AppSettings as _A\n_Mk = _A\n_P = _Mk()",
                True,
            ),
            # Documented limit, asserted so the docstring cannot drift from it:
            # a call through a helper function is NOT seen.
            (
                "helper indirection (known limit)",
                "def _b():\n    return AppSettings()\n_P = _b()",
                False,
            ),
            (
                "subclass of a subclass",
                "class A(AppSettings): pass\nclass B(A): pass\n_B = B()",
                True,
            ),
            (
                "aliased import used only inside a function",
                "from x import AppSettings as _Prefs\ndef f():\n    return _Prefs()",
                False,
            ),
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
