"""Python imports this at start-up in every child process a test of the engine package starts.

``quick3d_render_support.isolated_env`` puts this directory FIRST on the child's
``PYTHONPATH``; the interpreter imports ``sitecustomize`` before it runs anything.

WHY. The app keeps its settings in a store built from two names in
``open_garden_planner.app.settings`` — on Windows a registry key, which no environment
variable redirects (docs/08-crosscutting-concepts §8.8). ``tests/conftest.py`` rebinds
those names for the test PROCESS; a child does not import conftest. A child that
imports the app and builds a store would read, and write, the developer's own
settings: loading a plan ends with a write to Recent Files.

WHAT. Nothing of the app is imported here — a child that never touches the app stays
free of it (the host tier's canary depends on that). A finder waits for the import of
the settings module and rebinds the two names the moment the module's body has run,
which is before any code can build a store: to a key of this process's own, under the
organisation the test suite uses. A store that was built is emptied when the process
exits.

It also counts the stores the process builds, and — when ``OGP_TEST_CHILD_STORES``
names a file — writes ``<settings module imported: 0|1> <stores built>`` there at exit.
That is how a test shows that ``--selftest`` builds none: the frozen exe runs the same
code under the PRODUCTION names, where nothing can rebind them.

Standard library only. No ``QSettings`` is named here (§8.8: only the factory may).
"""

from __future__ import annotations

import atexit
import contextlib
import importlib.abc
import os
import sys
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any

SETTINGS_MODULE = "open_garden_planner.config.settings"
TEST_ORGANIZATION = "cofade_test"  # the organisation tests/conftest.py uses
REPORT_VARIABLE = "OGP_TEST_CHILD_STORES"

#: The settings module once it was imported, and one entry per store this process built.
imported: list[ModuleType] = []
stores_built: list[int] = []


def child_application() -> str:
    """The application name of this process's own settings key."""
    return f"Open Garden Planner Test Child {os.getpid()}"


def _rebind(module: ModuleType) -> None:
    """The settings module's body has just run: no store can exist yet."""
    module.ORGANIZATION_NAME = TEST_ORGANIZATION  # type: ignore[attr-defined]
    module.APPLICATION_NAME = child_application()  # type: ignore[attr-defined]
    factory = module.create_qsettings

    def create_qsettings(*arguments: Any, **options: Any) -> Any:
        stores_built.append(1)
        return factory(*arguments, **options)

    create_qsettings.__doc__ = factory.__doc__
    module.create_qsettings = create_qsettings  # type: ignore[attr-defined]
    if module not in imported:  # a reload runs the body again: rebind again, count once
        imported.append(module)


class _SettingsRebinder(importlib.abc.MetaPathFinder):
    """Finds nothing itself. For the settings module it asks the real finders and wraps
    the loader they name, so that the names are rebound right after the module's body."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> ModuleSpec | None:
        if fullname != SETTINGS_MODULE:
            return None
        for finder in sys.meta_path:
            find = getattr(finder, "find_spec", None)
            if finder is self or find is None:
                continue
            spec = find(fullname, path, target)
            if spec is not None and spec.loader is not None:
                run = spec.loader.exec_module

                def exec_module(module: ModuleType, run: Any = run) -> None:
                    run(module)
                    _rebind(module)

                spec.loader.exec_module = exec_module  # type: ignore[method-assign]
                return spec
        return None


def _at_exit() -> None:
    report = os.environ.get(REPORT_VARIABLE)
    if report:
        with contextlib.suppress(OSError), open(report, "w", encoding="utf-8") as handle:
            handle.write(f"{len(imported)} {len(stores_built)}\n")
    if imported and stores_built:
        with contextlib.suppress(Exception):  # best effort while the interpreter shuts down
            store = imported[0].create_qsettings()  # the test key of this process …
            store.clear()                           # … emptied …
            # … and WRITTEN, explicitly. This handler was registered before PyQt was
            # imported, so it runs after PyQt's own exit handler: the store's destructor
            # no longer flushes then, and on the file backends (Linux, macOS) a clear()
            # without sync() left the file as it was (measured on Linux).
            store.sync()


sys.meta_path.insert(0, _SettingsRebinder())
atexit.register(_at_exit)
