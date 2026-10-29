"""The engine boundary, pinned (Phase 17 L1.2, #385 — gates G1 and G2; ADR-048).

One package talks to Qt Quick 3D: ``ui/view3d/quick3d/``. Everything else in the
product — the Qt-free scene core, the snapshot, the workspace, ``main.py`` — is
free of ``PyQt6.QtQuick3D`` / ``QtQuick`` / ``QtQml`` / ``QtQuickWidgets``, so
the engine can be replaced (or fail to load) without taking the 2D app with it,
and so a normal start never pays for it.

The scan is an AST scan over the WHOLE source tree, and it also reads module
names out of string literals: ``__import__("PyQt6.QtQuick3D")`` is an import.
Since L1.10 there is no exception: the dormant L0 spike, which kept an older rule of
its own, was deleted with Qt 3D.

The second half of the file is the same kind of scan for a second boundary: NO
PYTHON ON QT'S RENDER THREAD (review round 3; see the section's own comment).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.quick3d_render_support import isolated_env

SRC = Path(__file__).resolve().parents[2] / "src"
PRODUCT = SRC / "open_garden_planner"
PACKAGE = PRODUCT / "ui" / "view3d" / "quick3d"
ENGINE_MODULES = ("PyQt6.QtQuick3D", "PyQt6.QtQuick", "PyQt6.QtQml", "PyQt6.QtQuickWidgets")

#: The files outside the engine package that may touch the engine: none (the L0 spike's
#: engine module was the one exception until L1.10 deleted the spike).
ALLOWED_OUTSIDE: set[Path] = set()
#: Inside the package: the modules that IMPORT the engine …
ENGINE_IMPORTERS = {"geometry.py", "ground_tiles.py", "host.py", "patterns.py"}  # L1.5, #628
#: … and the one that names its bindings as strings, to import them one by one and
#: report each (the self-test).
ENGINE_NAMERS = {"selftest.py"}


def _is_engine(name: str) -> bool:
    return any(name == module or name.startswith(module + ".") for module in ENGINE_MODULES)


def engine_imports(path: Path) -> set[str]:
    """Engine modules a file imports — by statement, in either spelling."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if _is_engine(alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if _is_engine(node.module):
                found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names
                         if _is_engine(f"{node.module}.{alias.name}"))
    return found


def engine_names(path: Path) -> set[str]:
    """Engine modules a file names in a string literal (``__import__``, ``importlib``)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and _is_engine(node.value)}


def _sources() -> list[Path]:
    return sorted(PRODUCT.rglob("*.py"))


def test_the_scan_covers_the_whole_tree() -> None:
    files = _sources()
    assert len(files) > 250, "the scan must walk the whole product, sub-packages included"
    assert PRODUCT / "main.py" in files and PACKAGE / "host.py" in files
    assert PRODUCT / "core" / "scene3d" / "interleave.py" in files


def test_only_the_engine_package_imports_the_engine() -> None:
    """G1. Any other module that imports (or names) a Qt Quick module is an offender."""
    offenders = sorted(
        str(path.relative_to(PRODUCT)) for path in _sources()
        if (engine_imports(path) or engine_names(path))
        and PACKAGE not in path.parents and path not in ALLOWED_OUTSIDE)
    assert offenders == []


def test_inside_the_package_only_the_engine_modules_import_it() -> None:
    """The package's own split: ``geometry`` and ``host`` are the engine; ``adapter``,
    ``materials``, ``look``, ``shots``, ``qt_messages``, ``runlog`` hold every decision
    that is not a Qt call — which is what lets the GPU-less run cover them."""
    importers = {path.name for path in PACKAGE.glob("*.py") if engine_imports(path)}
    namers = {path.name for path in PACKAGE.glob("*.py") if engine_names(path)}
    assert importers == ENGINE_IMPORTERS
    assert namers == ENGINE_NAMERS
    assert {path.name for path in PACKAGE.glob("*.py")} >= {
        "__init__.py", "adapter.py", "geometry.py", "host.py", "look.py", "materials.py",
        "offscreen.py", "qt_messages.py", "runlog.py", "selftest.py", "shots.py"}


def test_the_product_never_uses_a_qquickwidget() -> None:
    """ADR-048 criterion 3: a ``QQuickWidget`` moves the whole top-level window onto RHI
    composition (2D pan x1.4–x5.7). The engine package hosts a ``QQuickView``; it does
    not even import the widgets binding."""
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        used |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert "QQuickWidget" not in used, path.name  # docstrings may say why not
        assert not any("QtQuickWidgets" in name
                       for name in engine_imports(path) | engine_names(path)), path.name


@pytest.mark.parametrize(("source", "expected"), [
    ("from PyQt6 import QtQuick3D\n", {"PyQt6.QtQuick3D"}),
    ("import PyQt6.QtQml\n", {"PyQt6.QtQml"}),
    ("from PyQt6.QtQuick import QQuickView\n", {"PyQt6.QtQuick", "PyQt6.QtQuick.QQuickView"}),
    ("def f():\n    from PyQt6.QtQuickWidgets import QQuickWidget\n",
     {"PyQt6.QtQuickWidgets", "PyQt6.QtQuickWidgets.QQuickWidget"}),
    ("from PyQt6.QtCore import QObject\nfrom PyQt6 import QtGui, QtWidgets\n", set()),
    ("import PyQt6.QtQuickControls2\n", set()),  # not one of the four: a prefix is not a match
])
def test_the_scan_sees_every_import_spelling(tmp_path: Path, source: str, expected: set[str]) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    assert engine_imports(probe) == expected


def test_the_scan_sees_imports_by_name(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text('import importlib\nmodule = importlib.import_module("PyQt6.QtQuick3D")\n'
                     '__import__("PyQt6.QtQml")\nlabel = "PyQt6.QtCore"\n', encoding="utf-8")
    assert engine_imports(probe) == set()
    assert engine_names(probe) == {"PyQt6.QtQuick3D", "PyQt6.QtQml"}


# What ``tests/conftest.py`` does for the test process, for a child that builds the app:
# its settings go to a throwaway store (never the developer's), which it empties again.
_OWN_SETTINGS = (
    "import os\n"
    "import open_garden_planner.app.settings as app_settings\n"
    "app_settings.ORGANIZATION_NAME = 'cofade_test'\n"
    "app_settings.APPLICATION_NAME = f'Open Garden Planner Boundary Probe {os.getpid()}'\n"
)
_DROP_SETTINGS = "app_settings.create_qsettings().clear()\n"


def _child(code: str, scratch: Path) -> subprocess.CompletedProcess[str]:
    """A fresh interpreter importing THIS checkout's src: ``sys.modules`` of the shared
    test process proves nothing (other tests import the engine). Its app data and its
    user profile are the test's own (``isolated_env``)."""
    return subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", code], env=isolated_env(scratch, QT_QPA_PLATFORM="offscreen"),
        capture_output=True, text=True, timeout=170, cwd=scratch)


def test_app_start_loads_neither_the_engine_nor_its_package(tmp_path: Path) -> None:
    """G2. Constructing the real main window imports no Qt Quick binding and nothing of
    ``ui/view3d/`` — the 3D engine costs a normal start nothing (measured on the dev
    box: the package 1 ms, its engine-free half 17 ms, the engine itself 17 ms, all
    of it paid when 3D is first opened).

    The child builds the REAL main window, so it gets what the test process gets from
    ``tests/conftest.py``: a settings store of its own (review round 2 found this
    child reading the developer's), and app data and a user profile under
    ``tmp_path``."""
    proc = _child(
        _OWN_SETTINGS
        + "import sys\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "from open_garden_planner.app.application import GardenPlannerApp\n"
        "window = GardenPlannerApp()\n"
        "loaded = sorted(m for m in sys.modules if m.startswith(("
        "'PyQt6.QtQuick', 'PyQt6.QtQml', 'open_garden_planner.ui.view3d.quick3d')))\n"
        "store = app_settings.create_qsettings()\n"
        "print('STORE', store.organizationName(), '|', store.applicationName())\n"
        + _DROP_SETTINGS
        + "print(loaded)\n", tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    lines = proc.stdout.strip().splitlines()
    assert lines[-1] == "[]"
    (store,) = [line for line in lines if line.startswith("STORE ")]
    assert store.startswith("STORE cofade_test | Open Garden Planner Boundary Probe ")


def test_importing_the_package_is_free(tmp_path: Path) -> None:
    """Naming the package loads the package and nothing else — no Qt, no numpy core,
    no engine: ``__init__`` is a docstring."""
    proc = _child(
        "import sys\n"
        "import open_garden_planner.ui.view3d\n"
        "before = set(sys.modules)\n"
        "import open_garden_planner.ui.view3d.quick3d\n"
        "print(sorted(set(sys.modules) - before))\n", tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().splitlines()[-1] == "['open_garden_planner.ui.view3d.quick3d']"
    tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    assert [type(node).__name__ for node in tree.body] == ["Expr"], "__init__ is a docstring only"


def test_the_engine_free_modules_load_without_the_engine(tmp_path: Path) -> None:
    """Everything the GPU-less test tier imports — the sink, the host's state table, the
    look, the shots, the self-test's scene and judge — works in a process that never
    loads Qt Quick."""
    proc = _child(
        "import sys\n"
        "from open_garden_planner.ui.view3d.quick3d import (adapter, adapter_info, lifecycle, look, materials,\n"
        "                                                    qt_messages, runlog, selftest, shots)\n"
        "assert selftest.judge_frame is not None and adapter.Quick3DSink is not None\n"
        "assert adapter_info.detect_is_software is not None\n"
        "assert lifecycle.state_of(None) is lifecycle.HostState.CLOSED\n"
        "print(sorted(m for m in sys.modules if m.startswith(('PyQt6.QtQuick', 'PyQt6.QtQml'))))\n",
        tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().splitlines()[-1] == "[]"


# ── no Python on Qt's render thread (review rounds 2 and 3) ──────────────────
#
# Qt renders a shown Qt Quick window on a thread of its own. Python that Qt calls on that
# thread needs the interpreter lock; when the GUI thread holds it inside a Qt call that
# waits for the render thread (``hide()``), the process deadlocks for good — measured 5 of
# 5 on Direct3D 11 (GPU and WARP) and on xcb, with a Python Qt message handler
# (``qt_messages.py``; the render tier's control is
# ``test_a_python_message_handler_beside_a_shown_window_deadlocks``).
#
# The host does NOT refuse to show itself while such a handler is installed (ruled out:
# the host cannot know whose handler it is). What keeps the product clear of the hazard is
# static, and it is this scan. It is NECESSARY, NOT SUFFICIENT. It sees: this repository's
# own source naming a process-wide hook, reaching the recorder's ``install``, or touching a
# render-thread signal other than through the queued helper. It cannot see: a handler that
# a third-party package or a plugin installs (pytest-qt does, per test — the tests that
# show hosts switch it off: ``no_qt_log``); C++ code; a name put together at run time;
# and a Python OVERRIDE of a virtual that Qt calls on the render thread
# (``QQuickItem.updatePaintNode``, a ``QSGRenderNode``, a ``QQuickFramebufferObject``
# renderer) — the product has none, and anybody who adds one owns this problem. The
# run-time witness is ``Quick3DHost.slot_calls_off_the_gui_thread``, which the render
# tier requires to be 0.

#: Qt calls that install a process-wide Python callback, run on WHATEVER thread logs.
PROCESS_WIDE_HOOKS = frozenset({"qInstallMessageHandler", "installFilter"})
#: The one file that may name one: the offscreen render's recorder (the L0 spike's own,
#: which installed one beside shown windows, left with the spike in L1.10).
HOOK_FILES = {PACKAGE / "qt_messages.py"}
#: The one module that may reach the recorder's ``install``: the offscreen render, which
#: refuses beside a shown window BEFORE it installs.
RECORDER = "qt_messages"
RECORDER_CALLERS = {PACKAGE / "offscreen.py"}
#: Signals a Qt Quick window emits on its render thread (or may: Qt documents them as
#: "emitted from the scene graph rendering thread" under the threaded render loop).
RENDER_THREAD_SIGNALS = frozenset({
    "frameSwapped", "sceneGraphError", "sceneGraphInitialized", "sceneGraphInvalidated",
    "sceneGraphAboutToStop", "beforeSynchronizing", "afterSynchronizing", "beforeRendering",
    "afterRendering", "beforeRenderPassRecording", "afterRenderPassRecording",
    "beforeFrameBegin", "afterFrameEnd"})
#: The one way to connect one: ``host._connect_queued(signal, slot)``.
QUEUED_HELPER = "_connect_queued"


def hook_names(path: Path) -> set[str]:
    """Every way a file can NAME a process-wide hook: as a name, an attribute, an
    imported name, or a string (``getattr(QtCore, "qInstallMessageHandler")``)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found & PROCESS_WIDE_HOOKS


def recorder_reach(path: Path) -> set[str]:
    """How a file can reach the recorder's ``install``: it binds the module
    ``qt_messages`` (then every call on it counts), imports ``install`` / ``uninstall``
    from it, or names the module in a string. Importing its pure helpers
    (``classify``, ``graphics_adapter``) is not a reach."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names
                         if alias.name.rsplit(".", 1)[-1] == RECORDER)
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").rsplit(".", 1)[-1]
            for alias in node.names:
                if alias.name == RECORDER:
                    found.add(f"from {'.' * node.level}{node.module or ''} import {RECORDER}")
                elif module == RECORDER and alias.name in ("install", "uninstall", "*"):
                    found.add(f"{RECORDER}.{alias.name}")
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and node.value.rsplit(".", 1)[-1] == RECORDER and " " not in node.value):
            found.add(repr(node.value))
    return found


def unqueued_render_thread_signals(path: Path) -> list[str]:
    """Uses of a render-thread signal that are NOT the first argument of the queued
    helper — a direct ``.connect``, a connect with the connection type spelled out by
    hand, the signal handed to anything else, or its name in a string (``getattr``)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    queued = {id(node.args[0]) for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == QUEUED_HELPER and node.args}
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and node.attr in RENDER_THREAD_SIGNALS
                and id(node) not in queued):
            found.append(f"{path.name}:{node.lineno} {ast.unparse(node)}")
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and node.value in RENDER_THREAD_SIGNALS):
            found.append(f"{path.name}:{node.lineno} {node.value!r}")
    return found


def _product_sources() -> list[Path]:
    """The shipped product — all of it since L1.10 deleted the dormant spike, which
    predated every rule here."""
    return list(_sources())


def test_only_the_recorder_names_a_process_wide_qt_hook() -> None:
    """``qInstallMessageHandler`` and ``QLoggingCategory.installFilter`` — nowhere in
    ``src/`` but in the two allow-listed files."""
    namers = {path for path in _sources() if hook_names(path)}
    assert namers <= HOOK_FILES, sorted(str(path.relative_to(SRC)) for path in namers - HOOK_FILES)
    assert hook_names(PACKAGE / "qt_messages.py") == {"qInstallMessageHandler"}
    assert not any(hook_names(path) for path in _product_sources()
                   if path != PACKAGE / "qt_messages.py")


def test_only_the_offscreen_render_reaches_the_recorders_install() -> None:
    """…and it refuses beside a shown window before it does (``render_records``): the
    refusal's question is asked on an earlier line than the install."""
    reachers = {path for path in _product_sources() if recorder_reach(path)}
    assert reachers == RECORDER_CALLERS, sorted(str(path.relative_to(SRC)) for path in reachers)
    tree = ast.parse((PACKAGE / "offscreen.py").read_text(encoding="utf-8"))
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    installs = [(function.name, node.lineno) for function in functions for node in ast.walk(function)
                if isinstance(node, ast.Call) and ast.unparse(node.func) == f"{RECORDER}.install"]
    assert [name for name, _line in installs] == ["render_records"], installs
    (render,) = [function for function in functions if function.name == "render_records"]
    asked = [node.lineno for node in ast.walk(render)
             if isinstance(node, ast.Call) and ast.unparse(node.func) == "shown_quick_windows"]
    raised = [node.lineno for node in ast.walk(render) if isinstance(node, ast.Raise)]
    assert asked and asked[0] < installs[0][1], "the question comes before the install"
    assert any(asked[0] < line < installs[0][1] for line in raised), "and so does the refusal"


def test_every_render_thread_signal_is_connected_queued() -> None:
    """A Python slot on ``frameSwapped`` / ``sceneGraphError`` / the ``afterRendering``
    family runs on the render thread unless the connection is queued — the same hazard
    as a message handler. The product touches these signals only through ONE helper,
    whose body is the queued connect. (Qt's automatic connection type would queue as
    well while the receiver lives on the GUI thread; the explicit form does not depend
    on where the receiver lives.)"""
    offenders = [use for path in _product_sources() for use in unqueued_render_thread_signals(path)]
    assert offenders == []
    host = ast.parse((PACKAGE / "host.py").read_text(encoding="utf-8"))
    helpers = [(path.name, node) for path in _product_sources()
               for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
               if isinstance(node, ast.FunctionDef) and node.name == QUEUED_HELPER]
    assert [name for name, _node in helpers] == ["host.py"], "one helper, one definition"
    body = [statement for statement in helpers[0][1].body
            if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))]
    assert [ast.unparse(statement) for statement in body] == ["signal.connect(slot, _QUEUED)"]
    queued = [ast.unparse(node.value) for node in ast.walk(host)
              if isinstance(node, ast.AnnAssign) and ast.unparse(node.target) == "_QUEUED"]
    assert queued == ["Qt.ConnectionType.QueuedConnection"]
    connected = sorted(ast.unparse(node.args[0]).rsplit(".", 1)[-1] for node in ast.walk(host)
                       if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                       and node.func.id == QUEUED_HELPER)
    assert connected == ["frameSwapped", "sceneGraphError"], "what the host listens to today"


def test_the_spike_is_gone_and_nothing_names_it() -> None:
    """The L0 spike installed a process-wide Python handler and connected render-thread
    signals directly, beside shown windows — the one exception to this file's rules,
    tolerated while it was dormant. L1.10 deleted it: no package, no ``--spike-q3d``."""
    assert not (PRODUCT / "spike_q3d").exists()
    assert not [str(path.relative_to(PRODUCT)) for path in _product_sources()
                if "spike_q3d" in path.read_text(encoding="utf-8")
                or "--spike-q3d" in path.read_text(encoding="utf-8")]


@pytest.mark.parametrize(("source", "expected"), [
    ("from PyQt6.QtCore import qInstallMessageHandler\n", {"qInstallMessageHandler"}),
    ("from PyQt6.QtCore import qInstallMessageHandler as hook\n", {"qInstallMessageHandler"}),
    ("from PyQt6 import QtCore\nQtCore.qInstallMessageHandler(print)\n", {"qInstallMessageHandler"}),
    ("import PyQt6.QtCore as c\nh = c.qInstallMessageHandler\n", {"qInstallMessageHandler"}),
    ("from PyQt6 import QtCore\nh = getattr(QtCore, 'qInstallMessageHandler')\n",
     {"qInstallMessageHandler"}),
    ("from PyQt6.QtCore import QLoggingCategory\nQLoggingCategory.installFilter(print)\n",
     {"installFilter"}),
    ("def f(view, watch):\n    view.installEventFilter(watch)\n", set()),
    ('"""Never call qInstallMessageHandler beside a shown window."""\n', set()),
])
def test_the_hook_scan_sees_every_spelling(tmp_path: Path, source: str, expected: set[str]) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    assert hook_names(probe) == expected


@pytest.mark.parametrize(("source", "reaches"), [
    ("from . import qt_messages\n", True),
    ("from . import qt_messages as recorder\n", True),
    ("from open_garden_planner.ui.view3d.quick3d import qt_messages\n", True),
    ("import open_garden_planner.ui.view3d.quick3d.qt_messages\n", True),
    ("from .qt_messages import install\n", True),
    ("from .qt_messages import uninstall as off\n", True),
    ("from .qt_messages import *\n", True),
    ("import importlib\nm = importlib.import_module('open_garden_planner.ui.view3d.quick3d.qt_messages')\n",
     True),
    ("from .qt_messages import classify, graphics_adapter\n", False),
    ('"""See qt_messages.py for why."""\nfrom .host import Quick3DHost\n', False),
])
def test_the_recorder_scan_sees_every_way_in(tmp_path: Path, source: str, reaches: bool) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    assert bool(recorder_reach(probe)) is reaches


@pytest.mark.parametrize(("source", "unqueued"), [
    ("def f(view, slot):\n    _connect_queued(view.frameSwapped, slot)\n", 0),
    ("def f(view, slot):\n    view.frameSwapped.connect(slot)\n", 1),
    ("def f(view, slot):\n    view.afterRendering.connect(slot, Qt.ConnectionType.QueuedConnection)\n", 1),
    ("def f(view, slot):\n    view.sceneGraphError.connect(slot, Qt.ConnectionType.DirectConnection)\n", 1),
    ("def f(view, slot):\n    signal = view.beforeSynchronizing\n    signal.connect(slot)\n", 1),
    ("def f(view, slot):\n    getattr(view, 'afterFrameEnd').connect(slot)\n", 1),
    ("def f(view, slot):\n    _connect_queued(slot, view.frameSwapped)\n", 1),
    ("def f(view, slot):\n    view.widthChanged.connect(slot)\n", 0),
])
def test_the_signal_scan_sees_every_connect_that_is_not_the_helpers(
        tmp_path: Path, source: str, unqueued: int) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    assert len(unqueued_render_thread_signals(probe)) == unqueued
