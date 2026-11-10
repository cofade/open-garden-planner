"""Audit A4: executable import contracts, including compatibility identities."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.check_import_boundaries import QT_CORE_ONLY, check_qt_core_only, check_source

SRC = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"


@pytest.mark.parametrize(
    "module",
    [
        "open_garden_planner.core.object_types",
        "open_garden_planner.core.tools.base_tool",
        "open_garden_planner.models.smart_symbol",
    ],
)
def test_leaf_import_does_not_load_ui(module):
    code = (
        f"import {module}; import sys, json; "
        "print(json.dumps([k for k in sys.modules if k.startswith('open_garden_planner.ui')]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert json.loads(result.stdout) == []


@pytest.mark.parametrize(
    "old,new",
    [
        ("app.settings", "config.settings"),
        ("app.paths", "config.paths"),
        ("core.parametric_eval", "models.parametric_eval"),
    ],
)
def test_compatibility_module_has_one_identity(old, new):
    assert importlib.import_module("open_garden_planner." + old) is importlib.import_module(
        "open_garden_planner." + new
    )


@pytest.mark.parametrize(
    "source,relative,forbidden",
    [
        ("from open_garden_planner.ui import theme", "core/x.py", True),
        ("import open_garden_planner.app.application as a", "services/x.py", True),
        ("from ..ui import theme", "core/x.py", True),
        ("from open_garden_planner import ui", "models/x.py", True),
        ("if enabled:\n from open_garden_planner.ui import theme", "core/x.py", True),
        ("class C:\n from open_garden_planner.ui import theme", "core/x.py", True),
        ("def f():\n from open_garden_planner.ui import theme", "core/x.py", False),
        ("if TYPE_CHECKING:\n from open_garden_planner.ui import theme", "core/x.py", False),
        ("from open_garden_planner.config.settings import get_settings", "core/x.py", False),
        ("from open_garden_planner.app.settings import get_settings", "core/x.py", False),
        ("from open_garden_planner.core import Command", "models/x.py", True),
    ],
)
def test_boundary_detector(source, relative, forbidden):
    assert bool(check_source(source, relative)) is forbidden


def test_the_qt_core_only_modules_reach_no_widget_module():
    assert {"core/i18n.py", "services/task_generator.py", "services/soil_service.py"} <= set(
        QT_CORE_ONLY)
    assert check_qt_core_only(SRC) == []


def test_the_qt_core_only_rule_sees_a_widget_import_behind_another_module(tmp_path):
    """What #792 did: the locale module grew a widget class, and two services that only
    ask it for a formatter depended on QtWidgets through it. No layer edge is broken."""
    for folder in ("core", "services"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "core" / "i18n.py").write_text(
        "from PyQt6.QtCore import QLocale\nfrom PyQt6.QtWidgets import QDoubleSpinBox\n",
        encoding="utf-8")
    (tmp_path / "services" / "task_generator.py").write_text(
        "from open_garden_planner.core.i18n import format_decimal\n", encoding="utf-8")
    (tmp_path / "services" / "soil_service.py").write_text(
        "def f():\n    from PyQt6.QtWidgets import QWidget\n", encoding="utf-8")
    errors = check_qt_core_only(tmp_path)
    assert errors == [
        "core/i18n.py: QtCore-only, but reaches PyQt6.QtWidgets at core/i18n.py:2",
        "services/task_generator.py: QtCore-only, but reaches PyQt6.QtWidgets at "
        "core/i18n.py:2 <- services/task_generator.py",
    ], errors


def test_the_locale_module_loads_no_widget_module():
    """In a fresh process, not only in the source: QtCore's locale and translator, no widgets."""
    code = ("import open_garden_planner.core.i18n, sys, json; "
            "print(json.dumps(sorted(k for k in sys.modules "
            "if k in ('PyQt6.QtGui', 'PyQt6.QtWidgets'))))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            check=True, env={**os.environ, "PYTHONPATH": "src"})
    assert json.loads(result.stdout) == []


@pytest.mark.parametrize("package", ["core", "core.tools"])
def test_every_compatibility_export_resolves(package, qtbot):
    module = importlib.import_module("open_garden_planner." + package)
    assert set(module.__all__) == set(module._EXPORTS)
    for name, (owner, attribute) in module._EXPORTS.items():
        assert getattr(module, name) is getattr(importlib.import_module(owner), attribute)
    assert set(module.__all__) <= set(dir(module))
    with pytest.raises(AttributeError):
        _missing = module.missing_export
