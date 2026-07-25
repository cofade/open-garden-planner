"""Pins the mechanical icon-conformance gate into the test battery (#279).

Mirrors ``tests/unit/test_texture_tileability.py``: the same checks the
standalone gate script runs, executed in-process over every shipped icon.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_ICONS_DIR = (
    _REPO_ROOT / "src" / "open_garden_planner" / "resources" / "icons" / "ui"
)


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # check_icon_conformance imports its sibling normalize_icons by name.
    sys.path.insert(0, str(_SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_SCRIPTS_DIR))
    return module


_gate = _load_script("check_icon_conformance")
_ICON_FILES = sorted(_ICONS_DIR.glob("*.svg"))
_PROVENANCE = (_ICONS_DIR / "PROVENANCE.md").read_text(encoding="utf-8")


def test_icon_set_is_not_empty() -> None:
    assert len(_ICON_FILES) >= 70, "the themed icon set must ship with the app"


def test_provenance_has_no_orphan_entries() -> None:
    assert _gate.check_provenance_orphans(_ICONS_DIR, _PROVENANCE) == []


@pytest.mark.parametrize("icon_path", _ICON_FILES, ids=lambda p: p.stem)
def test_icon_conforms(icon_path: Path) -> None:
    problems = _gate.check_icon(icon_path, _PROVENANCE)
    assert problems == [], f"{icon_path.name}: {problems}"
