"""Windows of test runs and tools stay out of the way (owner's request during #390).

The render tier, its drivers, the Beauty Board and the probes need REAL windows: the engine
draws nothing under ``QT_QPA_PLATFORM=offscreen`` (§8.10). They do not need to be looked at.
On a developer's desktop each of them used to pop up in front of whatever was being worked
on, and take the keyboard with it.

``keep_windows_behind()`` makes every top-level window this process shows from then on

- **not take the focus** (Qt's ``_q_showWithoutActivating``, ``SW_SHOWNOACTIVATE``), and
- **stay under all the others** (``WindowStaysOnBottomHint``: ``HWND_BOTTOM``, and ``raise`` is
  a no-op). It stays a real window: exposed, rendering, with a swap chain. Windows does not tell
  an application that it is covered, and frames are read back, not looked at.

Nothing of the product changes: the app itself and the frozen exe never run this. It is
switched on where such processes start, by ``quick3d_child_site/sitecustomize.py`` (every child
of the engine's tests), by ``script_isolation.isolate_profile`` (the scripts and probes), and by
the render drivers when run by hand. The Python-level ``show`` family is wrapped: no event
filter, because one in Python would cost every event of a process whose budgets are measured.

``OGP_WINDOWS_IN_FRONT=1`` switches it off, to watch a run. On other platforms it does nothing
(xvfb has nobody to disturb).

Standard library only until PyQt6 is imported: importing this module loads no Qt.
"""

from __future__ import annotations

import importlib.abc
import os
import sys
from collections.abc import Callable
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any, Final

__all__ = ["OPT_OUT_VARIABLE", "keep_windows_behind"]

OPT_OUT_VARIABLE: Final = "OGP_WINDOWS_IN_FRONT"
#: Qt's Windows platform plugin reads this dynamic property when it shows a window.
_NO_ACTIVATION: Final = "_q_showWithoutActivating"
_WINDOW_SHOWS: Final = ("show", "showNormal", "showMaximized", "showFullScreen", "setVisible")
_WIDGET_SHOWS: Final = ("show", "showNormal", "showMaximized", "showFullScreen")

_state: dict[str, bool] = {"installed": False}


def _bottom_hint() -> Any:
    from PyQt6.QtCore import Qt

    return Qt.WindowType.WindowStaysOnBottomHint


def _quiet_window(window: Any) -> None:
    """A ``QWindow`` about to be shown. Embedded ones follow their top-level window."""
    if window.isTopLevel() and not window.isVisible():
        window.setProperty(_NO_ACTIVATION, True)
        window.setFlag(_bottom_hint(), True)


def _quiet_widget(widget: Any) -> None:
    """A ``QWidget`` about to be shown. Only a window is a window."""
    if widget.isWindow() and not widget.isVisible():
        from PyQt6.QtCore import Qt

        widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        widget.setWindowFlag(_bottom_hint(), True)


def _wrap(owner: type, names: tuple[str, ...], quiet: Callable[[Any], None]) -> None:
    for name in names:
        original = getattr(owner, name)
        if getattr(original, "ogp_quiet", False):
            continue

        def shown(self: Any, *arguments: Any, original: Any = original, name: str = name) -> Any:
            if name != "setVisible" or (arguments and arguments[0]):
                quiet(self)
            return original(self, *arguments)

        shown.ogp_quiet = True  # type: ignore[attr-defined]
        setattr(owner, name, shown)


def _patch_gui(module: ModuleType) -> None:
    _wrap(module.QWindow, _WINDOW_SHOWS, _quiet_window)


def _patch_widgets(module: ModuleType) -> None:
    _wrap(module.QWidget, _WIDGET_SHOWS, _quiet_widget)


_PATCHES: Final = {"PyQt6.QtGui": _patch_gui, "PyQt6.QtWidgets": _patch_widgets}


class _AfterImport(importlib.abc.MetaPathFinder):
    """Finds nothing itself. It wraps the loader of a Qt module the real finders name, so that
    the classes are patched right after the module's body ran, before anything is shown."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> ModuleSpec | None:
        patch = _PATCHES.get(fullname)
        if patch is None:
            return None
        for finder in sys.meta_path:
            find = getattr(finder, "find_spec", None)
            if finder is self or find is None:
                continue
            spec = find(fullname, path, target)
            if spec is not None and spec.loader is not None:
                run = spec.loader.exec_module

                def exec_module(module: ModuleType, run: Any = run, patch: Any = patch) -> None:
                    run(module)
                    patch(module)

                spec.loader.exec_module = exec_module  # type: ignore[method-assign]
                return spec
        return None


def keep_windows_behind(*, everywhere: bool = False) -> bool:
    """Switch it on for this process (module docstring); safe to repeat, and whether Qt was
    imported yet does not matter. True: it is on. ``everywhere``: on any platform (a test)."""
    if (sys.platform != "win32" and not everywhere) or os.environ.get(OPT_OUT_VARIABLE):
        return False
    if _state["installed"]:
        return True
    _state["installed"] = True
    for name, patch in _PATCHES.items():
        module = sys.modules.get(name)
        if module is not None:
            patch(module)
    sys.meta_path.insert(0, _AfterImport())
    return True
