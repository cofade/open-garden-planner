"""Gate: ``app/settings.create_qsettings()`` is the only settings-store factory.

Issue #285, ADR-041. #283 measured what an escape hatch costs: ``UiStateStore``
built its own ``QSettings`` for the real ``cofade / Open Garden Planner`` key, so
the conftest isolation — which only knew about ``AppSettings`` — did not cover
it, and every full-app test read *and overwrote* the developer's own window
state (120 writes from one test file). Fixing that one store is not the repair;
the repair is that a *new* store cannot repeat it.

Three rules, all over ``src/``:

1. Only ``app/settings.py`` may name ``QSettings`` at all — import it, annotate
   with it, or construct it. Everything else takes a store from the factory.
2. Nobody may call ``QSettings.setDefaultFormat()`` / ``setPath()``: those are
   process-global statics Qt never reverts (§11.4 — a leaked ``setPath`` to a
   deleted ``tmp_path`` once broke six unrelated tests two-thirds of the way
   through a session).
3. Nobody may call ``create_qsettings()`` at **import time** (module scope, class
   body, decorator, or default argument). This is the invariant the whole test
   isolation rests on and the one hole the mechanism genuinely has: the session
   fixture redirects by rebinding the factory's org/app names, which retargets
   every store built *afterwards* but cannot retarget one already constructed —
   and an import-time call happens before any fixture runs. A module-level
   ``_STORE = create_qsettings()`` would therefore silently reintroduce #283,
   with no singleton reset to save it (see ADR-041).

The scan is an AST walk, not a regex. A line-anchored regex was the first cut and
a senior review broke it in one experiment: ``from PyQt6.QtCore import (\n
QSettings as _Q,\n)`` names the class on a line with no ``import`` keyword, so
both patterns passed while the behavioural test caught the bug alone. Every
detector below therefore has a positive control in
``TestDetectorsCatchKnownEscapes`` — an anti-vacuity test that feeds it the
exact escape and asserts it is seen, because a detector that stops matching
anything reads as a green gate forever.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import open_garden_planner.app.settings as settings_module

SRC_ROOT = Path(settings_module.__file__).resolve().parents[1]
CHOKEPOINT = SRC_ROOT / "app" / "settings.py"

STORE_CLASS = "QSettings"
FACTORY = "create_qsettings"
GLOBAL_STATICS = frozenset({"setDefaultFormat", "setPath"})


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
    """Factory calls evaluated when the module is imported.

    Deferred (fine): anything inside a function or lambda *body*. Immediate (not
    fine): module scope, class body, a decorator expression, or a default
    argument — all of which run while the `def`/`class` statement executes.
    """
    lines: list[int] = []

    def visit(node: ast.AST, deferred: bool) -> None:
        if (
            not deferred
            and isinstance(node, ast.Call)
            and _callee(node.func) == FACTORY
        ):
            lines.append(node.lineno)

        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for expr in (
                *node.decorator_list,
                *node.args.defaults,
                *(d for d in node.args.kw_defaults if d is not None),
            ):
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


def _python_sources() -> list[Path]:
    return sorted(p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _scan(
    detector: object, *, skip_chokepoint: bool = False
) -> list[str]:
    """Run a detector over ``src/`` and format any hits as ``path:line``."""
    offenders: list[str] = []
    for path in _python_sources():
        if skip_chokepoint and path == CHOKEPOINT:
            continue
        rel = path.relative_to(SRC_ROOT.parent).as_posix()
        offenders += [f"{rel}:{line}" for line in detector(_parse(path))]  # type: ignore[operator]
    return offenders


class TestSingleConstructionSite:
    def test_the_scan_actually_covers_the_source_tree(self) -> None:
        """Anti-vacuity: a mis-resolved root would make every gate below pass."""
        sources = _python_sources()
        assert len(sources) > 50, f"only found {len(sources)} modules under {SRC_ROOT}"
        assert CHOKEPOINT in sources

    def test_the_chokepoint_itself_still_names_the_store_class(self) -> None:
        """Anti-vacuity: the detector must see the one legitimate site."""
        assert _names_the_store_class(_parse(CHOKEPOINT)), (
            "the detector no longer matches create_qsettings() — the gate below "
            "would pass no matter what other modules do"
        )

    def test_no_other_module_names_the_store_class(self) -> None:
        offenders = _scan(_names_the_store_class, skip_chokepoint=True)
        assert offenders == [], (
            "only app/settings.py may import, annotate with or construct "
            "QSettings; everything else takes a store from create_qsettings() "
            "(issue #285):\n" + "\n".join(offenders)
        )


class TestNoProcessGlobalQSettingsStatics:
    def test_src_never_touches_setdefaultformat_or_setpath(self) -> None:
        offenders = _scan(_calls_global_statics)
        assert offenders == [], (
            "QSettings.setDefaultFormat()/setPath() are process-global and never "
            "reverted by Qt (§11.4):\n" + "\n".join(offenders)
        )


class TestNoStoreIsBuiltAtImportTime:
    def test_no_module_caches_a_store_at_import_time(self) -> None:
        """The invariant the session-wide test isolation silently depends on.

        Rebinding the factory's names redirects stores built *after* the
        rebinding. An import-time call runs before any fixture, so its store is
        pinned to the user's real key for the whole session — #283, again.
        """
        offenders = _scan(_builds_a_store_at_import_time)
        assert offenders == [], (
            "create_qsettings() must be called at runtime, never at import time "
            "(module scope, class body, decorator or default argument) — such a "
            "store cannot be redirected by the test isolation (ADR-041):\n"
            + "\n".join(offenders)
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
            ("module scope", "_STORE = create_qsettings()", True),
            ("module scope, qualified", "_S = settings.create_qsettings()", True),
            ("class body", "class C:\n    store = create_qsettings()", True),
            ("default argument", "def f(s=create_qsettings()):\n    pass", True),
            ("decorator", "@wrap(create_qsettings())\ndef f():\n    pass", True),
            ("function body", "def f():\n    return create_qsettings()", False),
            ("method body", "class C:\n    def f(self):\n        create_qsettings()", False),
            ("lambda body", "f = lambda: create_qsettings()", False),
        ],
    )
    def test_import_time_detector(self, label: str, source: str, expected: bool) -> None:
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
        before = settings_module.create_qsettings()

        monkeypatch.setattr(settings_module, "ORGANIZATION_NAME", "ogp_gate_org")

        assert before.organizationName() != "ogp_gate_org"
        assert settings_module.create_qsettings().organizationName() == "ogp_gate_org"

    def test_appsettings_and_ui_state_share_the_backend(self) -> None:
        """One chokepoint means one file/key — the point of the whole exercise."""
        from open_garden_planner.app.settings import AppSettings
        from open_garden_planner.app.ui_state import UiStateStore

        assert AppSettings()._settings.fileName() == UiStateStore()._settings.fileName()
