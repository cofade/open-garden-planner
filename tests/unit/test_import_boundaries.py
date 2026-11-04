"""Audit A4: executable import contracts, including compatibility identities."""

import importlib
import json
import os
import subprocess
import sys

import pytest
from scripts.check_import_boundaries import check_source


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


@pytest.mark.parametrize("package", ["core", "core.tools"])
def test_every_compatibility_export_resolves(package, qtbot):
    module = importlib.import_module("open_garden_planner." + package)
    assert set(module.__all__) == set(module._EXPORTS)
    for name, (owner, attribute) in module._EXPORTS.items():
        assert getattr(module, name) is getattr(importlib.import_module(owner), attribute)
    assert set(module.__all__) <= set(dir(module))
    with pytest.raises(AttributeError):
        _missing = module.missing_export
