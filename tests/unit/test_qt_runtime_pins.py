"""The two Qt pins move together, and what they pin carries Qt Quick 3D (Phase 17 L1.10).

Successor of the #277 guard. Until L1.10 four Qt wheels had to share one micro — PyQt6,
PyQt6-Qt6 and the two Qt 3D wheels, whose bindings link Qt's private internals — and a
fresh resolve that floated the core runtime to 6.11.1 next to Qt 3D wheels built for 6.11.0
shipped a 3D view that killed the process (ADR-038 addendum "issue #277"). Qt 3D is gone; the
3D view is Qt Quick 3D, which ships INSIDE the two remaining wheels (ADR-048): the bindings
(``PyQt6.QtQuick3D``) in ``PyQt6``, the runtime (``Qt6Quick3D``, its QML modules) in
``PyQt6-Qt6``. So the invariant is now: the two pins are exact and equal; the installed
wheels are the pinned ones and the loaded Qt runtime is their micro; and Qt Quick 3D is in
what they pin. Metadata and ``qVersion()`` only — no engine module is imported, so this runs
offscreen in the default tier. The shipped artifact is guarded by the frozen ``--selftest``,
which renders a frame (``ui/view3d/quick3d/selftest.py``).
"""

from __future__ import annotations

import re
import tomllib
from importlib.metadata import files, version
from importlib.util import find_spec
from pathlib import Path

from PyQt6.QtCore import qVersion

REPO = Path(__file__).resolve().parents[2]
CORE_PINS = ("PyQt6", "PyQt6-Qt6")


def _pins() -> dict[str, str]:
    manifest = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    pins: dict[str, str] = {}
    for requirement in manifest["project"]["dependencies"]:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*==\s*([0-9][0-9A-Za-z.]*)", requirement.strip())
        if match:
            pins[match.group(1)] = match.group(2)
    return pins


def _locked(name: str) -> set[str]:
    """Every version ``uv.lock`` records for the package ``name``."""
    lock = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))
    return {str(package["version"]) for package in lock["package"]
            if str(package["name"]).lower() == name.lower()}


def test_the_two_qt_pins_are_exact_and_equal() -> None:
    pins = _pins()
    assert set(CORE_PINS) <= set(pins), f"PyQt6 and PyQt6-Qt6 must be pinned with ==: {pins}"
    assert pins["PyQt6"] == pins["PyQt6-Qt6"], (
        f"PyQt6 {pins['PyQt6']} != PyQt6-Qt6 {pins['PyQt6-Qt6']}: bump them together")


def test_the_lock_holds_exactly_the_pinned_qt() -> None:
    pins = _pins()
    for name in CORE_PINS:
        assert _locked(name) == {pins[name]}, (name, _locked(name), pins[name])


def test_the_loaded_qt_is_the_pinned_qt(qtbot) -> None:
    pins = _pins()
    assert version("PyQt6") == pins["PyQt6"]
    assert version("PyQt6-Qt6") == pins["PyQt6-Qt6"]
    assert qVersion() == pins["PyQt6-Qt6"], (
        f"the loaded Qt runtime {qVersion()} is not the pinned {pins['PyQt6-Qt6']}")


def test_qt_quick_3d_ships_inside_the_two_pinned_wheels() -> None:
    """The 3D view needs no third wheel: its bindings are PyQt6's, its runtime PyQt6-Qt6's."""
    assert find_spec("PyQt6.QtQuick3D") is not None
    bindings = [str(path) for path in files("PyQt6") or ()]
    assert any(re.search(r"QtQuick3D\.(pyd|so|abi3\.so|pyi)$", path) for path in bindings), (
        "PyQt6 carries no QtQuick3D binding")
    runtime = [str(path) for path in files("PyQt6-Qt6") or ()]
    assert any(re.search(r"Qt6Quick3D(Runtime)?(\.dll|\.so)", path) for path in runtime), (
        "PyQt6-Qt6 carries no Qt Quick 3D runtime library")
    assert any("qml/QtQuick3D" in path.replace("\\", "/") for path in runtime), (
        "PyQt6-Qt6 carries no QtQuick3D QML module")
