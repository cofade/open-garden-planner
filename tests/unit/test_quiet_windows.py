"""Windows of test runs and tools stay out of the way (owner's request during #390).

Each case runs in a child of its own: the switch patches Qt's classes for a whole process, and
this one's windows are none of its business. The render tier's ``host`` scenario shows that a
window kept behind still renders the same frames (``test_directors_cut_render.py``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from scripts.quiet_windows import OPT_OUT_VARIABLE

from tests.integration.quick3d_render_support import REPO, isolated_env

PREAMBLE = """
import json, sys
sys.path.insert(0, {scripts!r})
"""

SHOW_THEM = """
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QWindow
from PyQt6.QtWidgets import QApplication, QWidget

app = QApplication(sys.argv[:1])
window = QWindow()
window.show()
widget = QWidget()
widget.show()
child = QWidget(widget)
child.show()
big = QWidget()
big.showMaximized()
inner_parent = QWindow()
inner = QWindow(inner_parent)
inner.show()
hint = Qt.WindowType.WindowStaysOnBottomHint
print(json.dumps({{
    "window_no_activation": window.property("_q_showWithoutActivating"),
    "window_bottom": bool(window.flags() & hint),
    "window_visible": window.isVisible(),
    "widget_no_activation": widget.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating),
    "widget_bottom": bool(widget.windowFlags() & hint),
    "widget_visible": widget.isVisible(),
    "child_bottom": bool(child.windowFlags() & hint),
    "maximized_bottom": bool(big.windowFlags() & hint),
    "inner_touched": inner.property("_q_showWithoutActivating") is not None,
}}))
"""


def run(tmp_path: Path, body: str, **extra: str) -> dict:
    code = textwrap.dedent(PREAMBLE.format(scripts=str(REPO / "scripts"))) + textwrap.dedent(body)
    env = isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen", **extra)
    env.pop(OPT_OUT_VARIABLE, None) if OPT_OUT_VARIABLE not in extra else None
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                          timeout=120, cwd=tmp_path, check=False)
    assert done.returncode == 0, done.stderr[-1500:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_window_and_a_widget_are_shown_quietly_and_they_are_really_shown(tmp_path: Path) -> None:
    result = run(tmp_path, """
from quiet_windows import keep_windows_behind
assert keep_windows_behind(everywhere=True)
""" + SHOW_THEM.format())
    assert result["window_no_activation"] is True and result["window_bottom"]
    assert result["widget_no_activation"] and result["widget_bottom"]
    assert result["window_visible"] and result["widget_visible"]
    assert result["maximized_bottom"], "the whole show family"
    assert not result["child_bottom"], "a child widget is not a window"
    assert not result["inner_touched"], "an embedded window follows its top-level one"


def test_it_also_works_when_qt_was_imported_first(tmp_path: Path) -> None:
    result = run(tmp_path, """
import PyQt6.QtGui, PyQt6.QtWidgets
from quiet_windows import keep_windows_behind
keep_windows_behind(everywhere=True)
keep_windows_behind(everywhere=True)
""" + SHOW_THEM.format())
    assert result["window_bottom"] and result["widget_bottom"]


def test_the_switch_loads_no_qt_until_the_process_does(tmp_path: Path) -> None:
    """A child that never touches Qt stays free of it (the host tier's canary needs that)."""
    result = run(tmp_path, """
from quiet_windows import keep_windows_behind
keep_windows_behind(everywhere=True)
print(json.dumps({"qt": [name for name in sys.modules if name.startswith("PyQt6")]}))
""")
    assert result["qt"] == []


def test_the_opt_out_leaves_windows_as_they_are(tmp_path: Path) -> None:
    result = run(tmp_path, """
from quiet_windows import keep_windows_behind
assert keep_windows_behind(everywhere=True) is False
""" + SHOW_THEM.format(), **{OPT_OUT_VARIABLE: "1"})
    assert result["window_no_activation"] is None
    assert not result["window_bottom"] and not result["widget_bottom"]


def test_it_does_nothing_outside_windows_unless_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.quiet_windows as quiet

    monkeypatch.setattr(quiet.sys, "platform", "linux")
    monkeypatch.delenv(OPT_OUT_VARIABLE, raising=False)
    assert quiet.keep_windows_behind() is False


@pytest.mark.skipif(sys.platform != "win32", reason="the switch is for a Windows desktop")
def test_every_child_of_the_engines_tests_has_it_on(tmp_path: Path) -> None:
    """The start-up hook switches it on, without any line in the child."""
    env = isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen")
    env.pop(OPT_OUT_VARIABLE, None)
    code = ("from PyQt6.QtGui import QWindow\n"
            "print(getattr(QWindow.show, 'ogp_quiet', False))\n")
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                          timeout=120, cwd=tmp_path, check=False)
    assert done.stdout.strip() == "True", done.stderr[-800:]


@pytest.mark.skipif(sys.platform != "win32", reason="the switch is for a Windows desktop")
def test_a_script_that_isolates_itself_has_it_on(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.pop(OPT_OUT_VARIABLE, None)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(REPO / "scripts")
    code = ("import script_isolation\n"
            "script_isolation.isolate_profile()\n"
            "from PyQt6.QtWidgets import QWidget\n"
            "print(getattr(QWidget.show, 'ogp_quiet', False))\n")
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                          timeout=120, cwd=tmp_path, check=False)
    assert done.stdout.strip() == "True", done.stderr[-800:]


@pytest.mark.parametrize("driver", [
    "quick3d_render_driver.py", "view3d_living_driver.py", "view3d_looks_driver.py",
    "view3d_selection_driver.py", "quick3d_lifecycle_child.py", "ground_bake_render_driver.py",
    "plant_forge_render_driver.py", "view3d_analysis_driver.py", "view3d_capture_driver.py",
])
def test_a_driver_run_by_hand_has_it_on_too(driver: str) -> None:
    """The docs tell people to run these directly, where no start-up hook is installed."""
    source = (REPO / "tests" / "integration" / driver).read_text(encoding="utf-8")
    assert "keep_windows_behind" in source, driver


def test_two_copies_of_the_module_do_not_ask_each_other_for_ever(tmp_path: Path) -> None:
    """The child hook loads it by its path, a driver through ``scripts``: a module each. Two
    finders, each asking the other, ran out of stack on the first Qt import of every child but one."""
    result = run(tmp_path, """
import importlib.util
import quiet_windows
spec = importlib.util.spec_from_file_location("another_copy", quiet_windows.__file__)
other = importlib.util.module_from_spec(spec)
spec.loader.exec_module(other)
assert quiet_windows.keep_windows_behind(everywhere=True)
assert other.keep_windows_behind(everywhere=True)
from PyQt6.QtGui import QWindow
from PyQt6.QtWidgets import QWidget
print(json.dumps({
    "finders": sum(type(finder).__name__ == "_AfterImport" for finder in sys.meta_path),
    "window": getattr(QWindow.show, "ogp_quiet", False),
    "widget": getattr(QWidget.show, "ogp_quiet", False),
}))
""")
    assert result == {"finders": 1, "window": True, "widget": True}

