"""Gate of Phase 17 L1.10: Qt 3D is gone (ADR-048's closing addendum).

The 3D view runs on Qt Quick 3D since L1.9, and L1.10 deleted the Qt 3D window, its adapter,
its legacy record contract, the two ``PyQt6-3D*`` pins, their lock entries, the six hidden
imports of the frozen build and the Qt 3D block of ``--selftest``. This test keeps it so: no
tracked file of the CODE AREAS — ``src/``, ``installer/``, ``scripts/``, ``tests/``,
``.github/``, ``quality/``, ``pyproject.toml`` and the two locks — names Qt 3D's modules,
wheels or DLLs (``Qt3D…``, ``PyQt6-3D…``, ``PyQt6_3D…``, ``Qt63D….dll``), case-blind.
Documentation may keep the history, but only where history lives: the allowed paths are
named in ``HISTORY`` below, and any other document that names Qt 3D's modules fails.

It reads the files ``git ls-files`` lists (what a clone contains), so a stray build folder
cannot fail it and an untracked file cannot hide from review by not being committed.
Mutation-checked when it was written (§8.10.13): an import, a pin, a spec line and a
self-test line put back each fail it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
#: Qt 3D's Python modules (PyQt6.Qt3DCore …), wheels (PyQt6-3D, PyQt6-3D-Qt6; pyqt6-3d in
#: the locks; PyQt6_3D in a wheel or dist-info name) and DLLs (Qt63DCore.dll …).
NAMES = re.compile(r"qt3d|pyqt6[-_]3d|qt6\s?3d", re.IGNORECASE)
#: Where code lives: nothing here may name Qt 3D.
CODE_AREAS = ("src/", "installer/", "scripts/", "tests/", ".github/", "quality/")
CODE_FILES = ("pyproject.toml", "uv.lock", "pylock.toml")
#: Where documentation lives.
DOC_AREAS = ("docs/", ".claude/", ".agents/", ".codex/")
DOC_FILES = ("README.md", "CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md",
             "ACCESSIBILITY.md")
#: The ONLY places that may name Qt 3D: the history of the decision and of what was learned.
HISTORY = frozenset({
    "docs/09-architecture-decisions/README.md",        # ADR-038, ADR-048 and their addenda
    "docs/roadmap.md",                                 # what shipped when (Phase 14, L0, L1)
    "docs/11-risks-and-technical-debt/README.md",      # §11.1 / §11.4: what was learned
    "docs/11-risks-and-technical-debt/audits/2026-10/audit-2026-10.md",  # a dated snapshot, never edited
    ".claude/skills/ogp-failure-archaeology/SKILL.md",  # the chronicle of settled battles
    ".agents/skills/ogp-failure-archaeology/SKILL.md",
    ".claude/skills/debug-verbose/SKILL.md",            # case studies of fixed bugs
    ".agents/skills/debug-verbose/SKILL.md",
    # the Phase 14 campaign's reference: its engine gate chose Qt 3D (ADR-038), and its
    # intro says the view it built was retired in L1.10
    ".claude/skills/ogp-3d-sunshade-campaign/SKILL.md",
    ".agents/skills/ogp-3d-sunshade-campaign/SKILL.md",
})
HISTORY_DIRS = ("docs/09-architecture-decisions/adr-048-evidence/",)  # measured runs, kept
#: This gate's own name: citing it is not naming Qt 3D.
SELF = "test_no_qt3d_left"
#: Files in the code areas that may name Qt 3D, each with its reason.
ALLOWED_CODE = frozenset({
    "tests/unit/test_no_qt3d_left.py",   # this test: the names it looks for
    "tests/data/issue_registry.json",    # the titles of closed GitHub issues (#277), as filed
})


def _tracked() -> list[str]:
    try:
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True,  # noqa: S607
                                check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as error:
        pytest.fail(f"git ls-files is needed to know what is tracked: {error}")
    return [name for name in listed.decode("utf-8").split("\0") if name]


def _mentions(path: str) -> list[str]:
    try:
        text = (REPO / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []  # deleted in the working tree: nothing left to name anything
    return [f"{path}:{number}: {line.strip()[:160]}"
            for number, line in enumerate(text.splitlines(), 1) if names_qt3d(line)]


def names_qt3d(line: str) -> bool:
    """Whether ``line`` names Qt 3D — this gate's own file name does not count."""
    return NAMES.search(line.replace(SELF, "")) is not None


def offending_code(tracked: list[str]) -> list[str]:
    """Every line of a code-area file that names Qt 3D (except the allowed files)."""
    found: list[str] = []
    for path in tracked:
        in_code = path.startswith(CODE_AREAS) or path in CODE_FILES
        if in_code and path not in ALLOWED_CODE and not path.endswith((".qm", ".png", ".ico")):
            found += _mentions(path)
    return found


def offending_docs(tracked: list[str]) -> list[str]:
    """Every line of a document outside the history that names Qt 3D."""
    found: list[str] = []
    for path in tracked:
        is_doc = path.startswith(DOC_AREAS) or path in DOC_FILES
        if (is_doc and path not in HISTORY and not path.startswith(HISTORY_DIRS)
                and path.endswith((".md", ".toml", ".txt"))):
            found += _mentions(path)
    return found


def test_no_code_area_names_qt3d() -> None:
    found = offending_code(_tracked())
    assert found == [], "Qt 3D is gone (L1.10) — these name it:\n" + "\n".join(found[:60])


def test_documentation_names_qt3d_only_where_its_history_lives() -> None:
    found = offending_docs(_tracked())
    assert found == [], ("Only the history may name Qt 3D (HISTORY) — these do:\n"
                         + "\n".join(found[:60]))


def test_the_names_are_seen_where_they_would_be_written() -> None:
    """The pattern's positive control: every way Qt 3D was ever named in this tree."""
    for line in ("from PyQt6.Qt3DCore import QEntity", '"PyQt6-3D==6.11.0",',
                 'name = "pyqt6-3d-qt6"', "PyQt6_3D-6.11.0.dist-info", "Qt63DRender.dll",
                 '"PyQt6.Qt3DExtras",', "Qt6 3D", "QT3D_RENDERER=opengl"):
        assert names_qt3d(line), line
    for line in ("PyQt6.QtQuick3D", "Qt Quick 3D", "QtQuick3D.pyd", "Qt6Quick3D.dll",
                 "quick3d", "PyQt6-Qt6==6.11.0", "tests/unit/test_no_qt3d_left.py"):
        assert not names_qt3d(line), line


def test_every_history_path_exists() -> None:
    """An allow-list entry for a file that is gone would hide nothing — and say nothing."""
    tracked = set(_tracked())
    assert not HISTORY - tracked, sorted(HISTORY - tracked)
    assert not ALLOWED_CODE - tracked, sorted(ALLOWED_CODE - tracked)
