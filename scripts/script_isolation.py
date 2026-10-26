"""Keep a script's hands off the user's own stores (Phase 17 L1.1, #385; section 8.10).

A script under ``scripts/`` that imports the app runs OUTSIDE pytest, where no
conftest redirects anything. There the app's settings are the user's own — on
Windows a registry key that no environment variable moves — and so are its
app-data folder and every ``QStandardPaths`` location. ``ProjectManager.save()``
and ``.load()`` end with ``add_recent_file``: a script that writes a fixture
through the real serializer, or a probe that loads one, writes into the user's
Recent Files unless something stops it. (Found on 2026-10-11: scripts run that
way had replaced a developer's whole list with fixture paths.)

Three things are moved, each by the only route that reaches it — all explicit,
all safe to repeat:

- ``isolate_profile()`` — BEFORE the first ``open_garden_planner`` import. Points
  ``USERPROFILE``, ``HOME``, ``APPDATA``, ``LOCALAPPDATA`` and the three ``XDG_*``
  variables at a temporary directory of this process, removed at exit. Before
  the import, because a library may read its user files while it is imported
  (ezdxf reads its config then). Child processes inherit it.
- ``isolate_settings()`` — before anything is BUILT (an application, a scene, a
  ``ProjectManager``). Rebinds the two names the app builds every settings store
  from (``app.settings.ORGANIZATION_NAME`` / ``APPLICATION_NAME``, ADR-041) to
  the test organisation and a name of this process, and clears that key at
  exit. Stores are built lazily and bind their names when they are constructed,
  so the first line of ``main()`` is early enough. Child processes do NOT
  inherit it: a child must isolate itself (pytest does, in ``tests/conftest.py``).
- ``redirect_qt_locations(root)`` — what the app asks ``QStandardPaths`` for. On
  Windows the profile variables move only some of it: ``AppDataLocation`` and
  ``DocumentsLocation`` follow them, ``AppLocalDataLocation`` and
  ``CacheLocation`` (the companion, climate and thumbnail caches) do not — Qt
  asks the shell (measured in the review of fix round 3). So the Python-level
  function is replaced for the five locations the app writes through. THE one
  stand-in: ``tests/conftest.py`` installs this same function for the suite.
  Child processes do not inherit it.

``isolate()`` does all three.

How a script uses it::

    import script_isolation            # scripts/ is on sys.path when a script runs

    if __name__ == "__main__":         # run as a script: before the app is imported
        script_isolation.isolate_profile()

    from open_garden_planner... import ...

    def main() -> int:
        script_isolation.isolate()     # all three — the first line

Deliberately NOT at the import of this module, and not at the import of a script
either: tests import the fixture generators into the pytest process, whose stores
``tests/conftest.py`` has already redirected, and a second redirection there
would take the process's test key away for the rest of the session.
``tests/integration/test_script_isolation.py`` runs each script that uses this in
a child process and checks every store it builds.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

#: The variables a user's profile is found through — Windows, Linux and (``HOME``) macOS.
PROFILE_VARIABLES: tuple[str, ...] = (
    "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA",
    "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
)
#: The organisation the test suite's own stores live under (``tests/conftest.py``).
SCRIPT_ORGANIZATION = "cofade_test"
#: The ``QStandardPaths`` locations the app writes through: ``crash.log`` and
#: ``app.log`` (AppDataLocation), the companion, climate and thumbnail caches
#: (AppLocalDataLocation, CacheLocation), the default project folder (Documents).
QT_LOCATIONS: tuple[str, ...] = (
    "AppDataLocation", "AppLocalDataLocation", "AppConfigLocation", "CacheLocation",
    "DocumentsLocation",
)

_state: dict[str, object] = {}


def isolate_profile() -> Path:
    """Point every profile variable at a temporary directory of this process and
    return that directory. Call it before the app is imported."""
    root = _state.get("root")
    if not isinstance(root, Path):
        root = Path(tempfile.mkdtemp(prefix="ogp-script-"))
        _state["root"] = root
        for name in PROFILE_VARIABLES:
            folder = root / name.lower()
            folder.mkdir()
            os.environ[name] = str(folder)
        atexit.register(shutil.rmtree, str(root), ignore_errors=True)
    return root


def isolate_settings() -> tuple[str, str]:
    """Rebind the app's settings names to a throwaway key of this process and
    return the names they had. Call it before anything is built."""
    import open_garden_planner.app.settings as app_settings

    found = _state.get("found")
    if not isinstance(found, tuple):
        found = (app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME)
        _state["found"] = found
        app_settings.ORGANIZATION_NAME = SCRIPT_ORGANIZATION
        app_settings.APPLICATION_NAME = f"Open Garden Planner Script {os.getpid()}"
        atexit.register(_forget_settings)
    return found[0], found[1]


def redirect_qt_locations(root: Path) -> frozenset[Any]:
    """Make ``QStandardPaths.writableLocation`` name a folder under ``root`` for
    ``QT_LOCATIONS`` — the path only, forward slashes, as Qt answers: Qt does not
    create the folder it names and neither does this, so a writer that forgets
    its ``mkdir`` fails as it would on a user's first run. Every other location
    is Qt's own answer. Returns the locations that are redirected; a second call
    changes nothing (the first ``root`` stays)."""
    from PyQt6.QtCore import QStandardPaths

    locations = _state.get("qt")
    if not isinstance(locations, frozenset):
        locations = frozenset(getattr(QStandardPaths.StandardLocation, name) for name in QT_LOCATIONS)
        _state["qt"] = locations
        qt_answer = QStandardPaths.writableLocation

        def writable_location(location: Any) -> str:
            if location in locations:
                return (root / "qt" / location.name).as_posix()
            return str(qt_answer(location))

        QStandardPaths.writableLocation = writable_location  # type: ignore[method-assign]
    return locations


def isolate() -> None:
    """All three: the profile, the settings, Qt's locations. The first line of a
    script's ``main()``."""
    redirect_qt_locations(isolate_profile())
    isolate_settings()


def _forget_settings() -> None:
    """Remove this process's throwaway key again — best effort, at exit."""
    try:
        import open_garden_planner.app.settings as app_settings

        if app_settings.ORGANIZATION_NAME == SCRIPT_ORGANIZATION:
            store = app_settings.create_qsettings()
            store.clear()
            store.sync()
    except Exception:
        pass
