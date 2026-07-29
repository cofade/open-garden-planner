"""Gate: ``app/settings.create_qsettings()`` is the only settings-store factory.

Issue #285, ADR-041. #283 measured what an escape hatch costs: ``UiStateStore``
built its own ``QSettings`` for the real ``cofade / Open Garden Planner`` key, so
the conftest isolation — which only knew about ``AppSettings`` — did not cover
it, and every full-app test read *and overwrote* the developer's own window
state (120 writes from one test file). Fixing that store is not the repair; the
repair is that a *new* store cannot repeat it. Hence a grep gate over ``src/``
rather than a third isolation fixture.

The scan is textual, so a future comment or docstring that spells out a store
construction verbatim will trip it. That is the intended failure mode: loud, in
the right place, and one word away from fixed.
"""

from __future__ import annotations

import re
from pathlib import Path

import open_garden_planner.app.settings as settings_module

SRC_ROOT = Path(settings_module.__file__).resolve().parents[1]
CHOKEPOINT = SRC_ROOT / "app" / "settings.py"

# Two patterns, because either alone has a hole a real edit could walk through.
#
# The import gate is the primary one: you cannot construct a store without
# first naming the class, and matching the import also catches an alias
# (`from PyQt6.QtCore import QSettings as _Q`, which slipped past a
# construction-only regex during this gate's own falsification run). No module
# outside the chokepoint has any business naming the type at all today — not
# even for an annotation — so a legitimate future need is exactly the kind of
# change that should surface in review.
_IMPORT = re.compile(r"^\s*(from\s+\S+\s+)?import\s+.*\bQSettings\b")

# The construction gate then covers the module-attribute route, which needs no
# `QSettings` import at all: `from PyQt6 import QtCore` … `QtCore.QSettings(…)`.
_CONSTRUCTION = re.compile(r"\bQSettings\s*\(")

# Process-global statics Qt never reverts. Calling either from application code
# would rewire every store in the process, including a test session's isolated
# one — the §11.4 "dead tmp_path poisons the rest of the suite" incident.
_GLOBAL_STATICS = re.compile(r"\bQSettings\.(setDefaultFormat|setPath)\s*\(")


def _python_sources() -> list[Path]:
    return sorted(p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _hits(pattern: re.Pattern[str], path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    rel = path.relative_to(SRC_ROOT.parent)
    return [
        f"{rel.as_posix()}:{n}: {line.strip()}"
        for n, line in enumerate(lines, start=1)
        if pattern.search(line)
    ]


def _scan_outside_chokepoint(pattern: re.Pattern[str]) -> list[str]:
    return [
        hit
        for path in _python_sources()
        if path != CHOKEPOINT
        for hit in _hits(pattern, path)
    ]


class TestSingleConstructionSite:
    """Exactly one module in ``src/`` may build a settings store."""

    def test_the_scan_actually_covers_the_source_tree(self) -> None:
        """Anti-vacuity: a mis-resolved root would make every gate below pass."""
        sources = _python_sources()
        assert len(sources) > 50, f"only found {len(sources)} modules under {SRC_ROOT}"
        assert CHOKEPOINT in sources

    def test_the_chokepoint_itself_matches_both_patterns(self) -> None:
        """Anti-vacuity for the regexes: both must match the one real call site."""
        assert _hits(_IMPORT, CHOKEPOINT), "the import pattern matches nothing"
        assert _hits(_CONSTRUCTION, CHOKEPOINT), (
            "the construction pattern no longer matches create_qsettings() — "
            "the gates below would pass no matter what other modules do"
        )

    def test_no_other_module_imports_qsettings(self) -> None:
        offenders = _scan_outside_chokepoint(_IMPORT)
        assert offenders == [], (
            "only app/settings.py may name QSettings; everything else takes a "
            "store from create_qsettings() (issue #285):\n" + "\n".join(offenders)
        )

    def test_no_other_module_constructs_a_store(self) -> None:
        offenders = _scan_outside_chokepoint(_CONSTRUCTION)
        assert offenders == [], (
            "QSettings must only be constructed in app/settings.create_qsettings() "
            "(issue #285) — offending lines:\n" + "\n".join(offenders)
        )


class TestNoProcessGlobalQSettingsStatics:
    def test_src_never_touches_setdefaultformat_or_setpath(self) -> None:
        offenders = [
            hit for path in _python_sources() for hit in _hits(_GLOBAL_STATICS, path)
        ]
        assert offenders == [], (
            "QSettings.setDefaultFormat()/setPath() are process-global and never "
            "reverted by Qt (§11.4) — offending lines:\n" + "\n".join(offenders)
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

    def test_appsettings_and_ui_state_share_the_backend(self) -> None:
        """One chokepoint means one file/key — the point of the whole exercise."""
        from open_garden_planner.app.settings import AppSettings
        from open_garden_planner.app.ui_state import UiStateStore

        assert AppSettings()._settings.fileName() == UiStateStore()._settings.fileName()
