"""PEP 639 license metadata for the project itself (#574).

setuptools 82/84 warns that ``project.license = {text = ...}`` and the
``License ::`` classifier are deprecated (due 2027-02-18), and an isolated build
(``[build-system] requires`` floats) picks up the newest setuptools regardless of
the build group's pin. The manifest is therefore an SPDX expression plus
``license-files``, and the build floor is high enough to understand it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


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
