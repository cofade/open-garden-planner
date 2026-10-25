"""PEP 639 license metadata for the project itself (#574).

setuptools 82/84 warns that ``project.license = {text = ...}`` and the
``License ::`` classifier are deprecated (due 2027-02-18), and an isolated build
(``[build-system] requires`` floats) picks up the newest setuptools regardless of
the build group's pin. The manifest is therefore an SPDX expression plus
``license-files``, and the build floor is high enough to understand it.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

import open_garden_planner

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_generated_version_module_is_a_build_artifact() -> None:
    """The stale tracked `_version.py` 1.2.0 made a direct PyInstaller About say 1.2.0.

    `build_installer.py` writes the module for a release; a direct PyInstaller
    build has none, so the frozen app falls back to `__version__`.
    """
    assert open_garden_planner.__version__ == PYPROJECT["project"]["version"]
    assert "src/open_garden_planner/_version.py" in (ROOT / ".gitignore").read_text(
        encoding="utf-8"
    )
    from open_garden_planner.services.update_checker import get_current_version

    assert get_current_version() == open_garden_planner.__version__


def test_the_frozen_version_falls_back_without_the_generated_module(monkeypatch) -> None:
    from open_garden_planner.services.update_checker import get_current_version

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setitem(sys.modules, "open_garden_planner._version", None)
    assert get_current_version() == open_garden_planner.__version__


def test_the_frozen_release_reads_the_version_module_it_wrote(monkeypatch) -> None:
    """The release path still wins: ``build_installer.py`` writes the release version.

    It may lead ``pyproject.toml`` until the automatic version-sync PR, so a
    frozen release build must report the module, not ``__version__``.
    """
    from types import ModuleType

    from open_garden_planner.services.update_checker import get_current_version

    module = ModuleType("open_garden_planner._version")
    module.__version__ = "9.9.9"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setitem(sys.modules, "open_garden_planner._version", module)
    assert get_current_version() == "9.9.9"


def test_the_frozen_spec_bundles_a_generated_version_module() -> None:
    """PyInstaller sees only STATIC imports; the dynamic read needs the spec to list it.

    `build_installer.py` writes `_version.py` before PyInstaller runs, and a
    release build must therefore add it as a hidden import when it exists. A
    direct build has no file, so the entry is conditional.
    """
    spec = (ROOT / "installer" / "ogp.spec").read_text(encoding="utf-8")
    assert 'GENERATED_VERSION_MODULE = SRC / "open_garden_planner" / "_version.py"' in spec
    assert re.search(
        r'\[\s*"open_garden_planner\._version"\s*\]\s*if GENERATED_VERSION_MODULE\.exists\(\)',
        spec,
    ), "a release build must bundle the dynamically imported version module"


def test_license_is_an_spdx_expression() -> None:
    project = PYPROJECT["project"]
    assert project["license"] == "GPL-3.0-or-later"
    assert project["license-files"] == ["LICENSE"]
    assert not [c for c in project["classifiers"] if c.startswith("License ::")], (
        "a License :: classifier is deprecated when an SPDX license expression is present"
    )


def test_the_license_file_is_shipped() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8", errors="replace")
    assert "GNU GENERAL PUBLIC LICENSE" in text


def test_the_build_floor_supports_pep_639() -> None:
    """PEP 639 support arrived in setuptools 77; an isolated build must not fall below it."""
    requires = PYPROJECT["build-system"]["requires"]
    floors = [
        tuple(int(part) for part in raw.split(">=", 1)[1].split("."))
        for raw in requires
        if raw.startswith("setuptools>=")
    ]
    assert floors, requires
    assert floors[0] >= (77,), requires
