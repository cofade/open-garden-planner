"""The test harness must never touch the user's real data directory.

What happened (2026-10-11, §11.4): ``services.plant_library.get_app_data_dir()``
resolved ``%APPDATA%/OpenGardenPlanner`` in every test process, because
``tests/conftest.py`` redirected the settings store and nothing else. One test
of the plant database panel reached its save path, and the developer's real
``custom_plants.json`` held 207 duplicate "Walnut" entries of 209 — one more
with every full run of the suite, by anyone, on that machine.

``tests/conftest.py`` now points the directory at a per-process temporary root
at import time. This file pins the mechanism (where it lives, that it took,
that a child process inherits it) and, end to end, that building the whole
application and pressing the two save paths that wrote there before opens
nothing under the place the directory used to be.

The real directory is never touched here — not even read: where it used to be
is *computed* from what the environment said before the redirection, and the
test watches what the process opens, renames and creates (a ``sys`` audit
hook). Access from inside Qt's own C++ is not visible to it; the app's stores
are plain Python file I/O.
"""

# ruff: noqa: ARG002

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QStandardPaths

from open_garden_planner.core.object_types import ObjectType

# Imported while this module is collected — before any QApplication exists, which
# ``main`` insists on (it imports QtWebEngineWidgets).
from open_garden_planner.main import _write_crash_log
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services import plant_library as library_module
from tests.conftest import (
    PRODUCTION_DATA_ENV,
    REDIRECTED_QT_LOCATIONS,
    TEST_DATA_ROOT,
    _rebind_get_app_data_dir,
)

#: The four environment variables conftest points into the test root.
REDIRECTED_ENV = ("APPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")

REPO = Path(__file__).resolve().parents[2]
CONFTEST = REPO / "tests" / "conftest.py"


def production_app_data_dir() -> Path:
    """Where ``get_app_data_dir()`` pointed before the redirection: the function's
    own rule applied to the environment as it was. Computed, never touched."""
    if sys.platform == "win32":
        base = PRODUCTION_DATA_ENV["APPDATA"] or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = PRODUCTION_DATA_ENV["XDG_DATA_HOME"] or str(Path.home() / ".local" / "share")
    return Path(base) / "OpenGardenPlanner"


def under(path: Path | str, root: Path) -> bool:
    """True when ``path`` is ``root`` or lies below it (neither needs to exist)."""
    resolved, base = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    return resolved == base or base in resolved.parents


# ── what the process opens, renames and creates ───────────────────────────────

#: Audit events that name a path the process reads, writes, creates or deletes,
#: and how many of their leading arguments are paths.
_PATH_EVENTS = {"open": 1, "os.mkdir": 1, "os.remove": 1, "os.rmdir": 1, "os.listdir": 1,
                "os.scandir": 1, "os.rename": 2, "shutil.copyfile": 2, "shutil.move": 2}
_watched: list[tuple[str, str]] | None = None


def _audit(event: str, args: tuple[Any, ...]) -> None:
    """Record path events while a test is watching. An audit hook cannot be
    removed again, so this one is inert — one comparison — outside that window."""
    if _watched is None or event not in _PATH_EVENTS:
        return
    for value in args[:_PATH_EVENTS[event]]:
        if isinstance(value, (str, bytes, os.PathLike)):
            _watched.append((event, os.fsdecode(value)))


sys.addaudithook(_audit)


@pytest.fixture
def file_access() -> Any:
    """Every path the process opens, renames, creates, lists or removes during the test."""
    global _watched
    _watched = []
    try:
        yield _watched
    finally:
        _watched = None


# ── the mechanism ─────────────────────────────────────────────────────────────


class TestTheRedirectionMechanismItself:
    """Pin *where* the redirection lives, as ``test_settings_chokepoint.py`` does
    for the settings: at conftest module scope, before the first import of the
    app. Moved into a fixture it would run after collection — after a store
    built during an import has already resolved the real directory."""

    @staticmethod
    def _module_scope() -> tuple[dict[str, int], int]:
        """→ (line of each ``os.environ[NAME] = …`` at module scope, line of the
        first module-scope import of ``open_garden_planner``)."""
        tree = ast.parse(CONFTEST.read_text(encoding="utf-8"))
        assigned: dict[str, int] = {}
        first_app_import = 10**9
        for stmt in tree.body:  # top level only — not nested in anything
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if (isinstance(target, ast.Subscript)
                            and ast.unparse(target.value) == "os.environ"
                            and isinstance(target.slice, ast.Constant)):
                        assigned[str(target.slice.value)] = stmt.lineno
            names = ([alias.name for alias in stmt.names] if isinstance(stmt, ast.Import)
                     else [stmt.module or ""] if isinstance(stmt, ast.ImportFrom) else [])
            if any(name.startswith("open_garden_planner") for name in names):
                first_app_import = min(first_app_import, stmt.lineno)
        return assigned, first_app_import

    def test_the_environment_is_redirected_at_conftest_module_scope(self) -> None:
        assigned, first_app_import = self._module_scope()
        assert set(assigned) >= set(REDIRECTED_ENV), (
            "tests/conftest.py must set ALL FOUR variables at module scope — in a fixture "
            "they are set after collection, when a store built during an import has "
            "already resolved the user's real directory (and ezdxf has read its config)"
        )
        assert first_app_import < 10**9
        assert max(assigned[name] for name in REDIRECTED_ENV) < first_app_import, (
            "the redirection must come before the first import of open_garden_planner"
        )

    def test_the_redirection_actually_took(self) -> None:
        """Behavioural counterpart: the AST check could pass with wrong values."""
        for name in REDIRECTED_ENV:
            assert under(os.environ[name], TEST_DATA_ROOT), name
            assert os.environ[name] != PRODUCTION_DATA_ENV[name]
            assert Path(os.environ[name]).is_dir()
        resolved = library_module.get_app_data_dir()
        assert resolved.name == "OpenGardenPlanner" and resolved.is_dir()
        assert under(resolved, TEST_DATA_ROOT)
        real = production_app_data_dir()
        assert not under(resolved, real) and not under(real, TEST_DATA_ROOT)
        assert TEST_DATA_ROOT.is_dir() and str(os.getpid()) in TEST_DATA_ROOT.name

    def test_the_root_is_removed_when_the_interpreter_exits(self) -> None:
        """Checked on a process of its own: this one is still running."""
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import tests.conftest as c; "
                "print(c.TEST_DATA_ROOT)")
        done = subprocess.run([sys.executable, "-c", code, str(REPO)], capture_output=True,
                              text=True, timeout=120, cwd=str(REPO))
        assert done.returncode == 0, done.stderr[-2000:]
        root = Path(done.stdout.strip().splitlines()[-1])
        assert root.name.startswith("ogp-tests-") and root != TEST_DATA_ROOT
        assert not root.exists()  # it existed while that process ran; atexit took it away

    @pytest.mark.skipif(
        sys.platform == "darwin",
        reason="macOS reads no environment variable: a child that has not imported conftest "
               "would resolve — and CREATE — the real ~/Library/Application Support/OpenGardenPlanner",
    )
    def test_a_child_process_inherits_it(self) -> None:
        """A script or the app started by a test must land in the test root too —
        the reason the mechanism is the environment and not a patched function."""
        code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                "from open_garden_planner.services.plant_library import get_app_data_dir; "
                "print(get_app_data_dir())")
        done = subprocess.run([sys.executable, "-c", code, str(REPO / "src")],
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr[-2000:]
        assert under(done.stdout.strip().splitlines()[-1], TEST_DATA_ROOT)

    def test_the_macos_route(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """macOS reads no environment variable, so there the function itself is
        replaced. No Mac runs this suite; the replacement is exercised here by
        hand, on the modules that bound the name with ``from … import``."""
        from open_garden_planner.services import companion_planting_service, weather_service

        modules = (library_module, companion_planting_service, weather_service)
        original = library_module.get_app_data_dir
        for module in modules:  # registered with monkeypatch only so that it is undone afterwards
            assert module.get_app_data_dir is original
            monkeypatch.setattr(module, "get_app_data_dir", original)
        _rebind_get_app_data_dir(tmp_path / "mac")
        for module in modules:
            assert module.get_app_data_dir is not original
            assert module.get_app_data_dir() == tmp_path / "mac" / "OpenGardenPlanner"
        assert (tmp_path / "mac" / "OpenGardenPlanner").is_dir()
        assert library_module.PlantLibrary()._library_path.parent == tmp_path / "mac" / "OpenGardenPlanner"

    def test_the_locations_qt_hands_out(self) -> None:
        """The crash log, ``app.log``, the caches and the default project folder
        are found through ``QStandardPaths.writableLocation``; on Windows no
        environment variable moves those."""
        locations = QStandardPaths.StandardLocation
        assert {locations.AppDataLocation, locations.AppLocalDataLocation,
                locations.DocumentsLocation, locations.CacheLocation} <= REDIRECTED_QT_LOCATIONS
        for location in REDIRECTED_QT_LOCATIONS:
            answer = QStandardPaths.writableLocation(location)
            assert under(answer, TEST_DATA_ROOT), location
            assert "\\" not in answer  # as Qt writes a path
        # … and nothing else is touched: the temp directory is the machine's own
        assert not under(QStandardPaths.writableLocation(locations.TempLocation), TEST_DATA_ROOT)

    def test_asking_for_a_location_creates_nothing(self) -> None:
        """Qt names a folder; it does not make it. Neither does the stand-in — or a
        writer that forgot its ``mkdir`` would pass every test and fail on a user's
        first run (review round 3: the first version of the stand-in created it)."""
        nothing_writes_here = QStandardPaths.StandardLocation.AppConfigLocation
        assert nothing_writes_here in REDIRECTED_QT_LOCATIONS
        for _ in range(2):
            answer = Path(QStandardPaths.writableLocation(nothing_writes_here))
            assert under(answer, TEST_DATA_ROOT) and not answer.exists()

    def test_the_writers_make_their_own_folder(self, monkeypatch: pytest.MonkeyPatch,
                                               tmp_path: Path) -> None:
        """… and every writer of the app does make it: each is pointed at a folder
        that does not exist, the way a first run finds it."""
        from open_garden_planner.app import paths
        from open_garden_planner.core.logging_config import resolve_log_dir
        from open_garden_planner.services import companion_cache
        from open_garden_planner.services.climate_service import ClimateService
        from open_garden_planner.services.plant_api import thumbnail_loader

        fresh = tmp_path / "never" / "made"
        monkeypatch.setattr(QStandardPaths, "writableLocation", lambda _location: fresh.as_posix())
        assert not fresh.exists()
        made = [paths.get_projects_dir(), resolve_log_dir(), companion_cache.get_cache_dir(),
                ClimateService._get_cache_dir(), thumbnail_loader.get_cache_dir()]
        assert all(folder.is_dir() and under(folder, fresh) for folder in made)
        _write_crash_log("written into a folder that did not exist")
        assert "did not exist" in (fresh / "crash.log").read_text(encoding="utf-8")

    def test_ezdxf_keeps_its_files_in_the_test_root(self) -> None:
        """The DXF library has user files of its own (read in ezdxf 1.4.3): a config
        ``ezdxf.ini`` it loads when it is imported, and a font index it BUILDS AND
        WRITES when it is missing — both under ``~/.config`` / ``~/.cache`` unless
        ``XDG_CONFIG_HOME`` / ``XDG_CACHE_HOME`` say otherwise. They do."""
        import ezdxf
        from ezdxf.fonts import fonts

        config_home = ezdxf.options.xdg_path("XDG_CONFIG_HOME", ".config")
        font_index = fonts._get_font_manager_path()
        assert under(config_home, TEST_DATA_ROOT) and config_home.name == "ezdxf"
        assert under(font_index, TEST_DATA_ROOT) and font_index.name == "font_manager_cache.json"
        home = Path.home()
        assert not under(config_home, home / ".config") and not under(font_index, home / ".cache")
        # what it actually loaded when it was imported: nothing from the user's home
        assert all(not under(loaded, home / ".config") for loaded in ezdxf.options.loaded_config_files)

    def test_the_writers_that_go_through_qt(self) -> None:
        from open_garden_planner.app import paths
        from open_garden_planner.core.logging_config import resolve_log_dir
        from open_garden_planner.services import companion_cache
        from open_garden_planner.services.climate_service import ClimateService

        for place in (paths.get_documents_dir(), paths.get_projects_dir(), resolve_log_dir(),
                      companion_cache.get_cache_dir(), ClimateService._get_cache_dir()):
            assert under(place, TEST_DATA_ROOT), place
        _write_crash_log("written by test_app_data_isolation")
        crash_log = Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation)) / "crash.log"
        assert "written by test_app_data_isolation" in crash_log.read_text(encoding="utf-8")


# ── end to end ────────────────────────────────────────────────────────────────


class TestNothingReachesTheRealDirectory:
    def test_every_store_resolves_under_the_test_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from open_garden_planner.models import plant_lists, seed_inventory
        from open_garden_planner.services import companion_planting_service, smart_symbol_library
        from open_garden_planner.services.weather_service import WeatherService

        # fresh stores, so the paths are resolved NOW and not by an earlier test
        monkeypatch.setattr(library_module, "_library_instance", None)
        monkeypatch.setattr(plant_lists, "_STORE", None)
        monkeypatch.setattr(seed_inventory, "_store", None)
        resolved = {
            "custom plants": library_module.get_plant_library()._library_path,
            "plant lists": plant_lists.get_plant_list_store().path,
            "seed inventory": seed_inventory.get_seed_inventory()._path,
            "companion rules": (companion_planting_service.get_app_data_dir()
                                / companion_planting_service._CUSTOM_RULES_FILENAME),
            "smart symbols": smart_symbol_library._user_dir(),
            "weather cache": WeatherService()._cache_path(52.5, 13.4),
        }
        real = production_app_data_dir()
        for label, path in resolved.items():
            assert under(path, TEST_DATA_ROOT), (label, path)
            assert not under(path, real), (label, path)

    def test_the_whole_app_and_the_two_save_paths(
        self, qtbot: Any, monkeypatch: pytest.MonkeyPatch, file_access: list[tuple[str, str]]
    ) -> None:
        """The incident, replayed: the whole application, the plant database
        panel's save path (the call that wrote the 207 Walnuts) and the
        plant-list store (rewritten in the real directory the same morning)."""
        from open_garden_planner.app.application import GardenPlannerApp
        from open_garden_planner.models import plant_lists
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem
        from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel

        monkeypatch.setattr(library_module, "_library_instance", None)
        monkeypatch.setattr(plant_lists, "_STORE", None)

        window = GardenPlannerApp()
        qtbot.addWidget(window)

        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        tree = CircleItem(center_x=0, center_y=0, radius=20, object_type=ObjectType.TREE, name="Tree")
        species = PlantSpeciesData(scientific_name="Juglans regia", common_name="Walnut")
        tree.metadata["plant_species"] = species.to_dict()
        panel.set_selected_items([tree])
        panel._on_field_changed()  # … saves a custom plant through the real PlantLibrary

        store = plant_lists.get_plant_list_store()
        assert store.toggle_favorite(species) is True
        store.create_list("Orchard")
        window.close()

        # what was saved is where a test's data belongs …
        data_dir = library_module.get_app_data_dir()
        assert under(data_dir, TEST_DATA_ROOT)
        saved = json.loads((data_dir / "custom_plants.json").read_text(encoding="utf-8"))
        assert [plant["scientific_name"] for plant in saved["plants"].values()].count("Juglans regia") >= 1
        lists = json.loads((data_dir / "plant_lists.json").read_text(encoding="utf-8"))
        assert "Orchard" in json.dumps(lists)

        # … and the process opened, created, renamed or listed NOTHING under the
        # directory those two files used to be written to
        real = production_app_data_dir()
        opened_here = [access for access in file_access if under(access[1], TEST_DATA_ROOT)]
        assert opened_here, "the watch saw none of the writes it exists to see"
        reached = [access for access in file_access if under(access[1], real)]
        assert reached == [], f"the test process reached the user's real data directory: {reached[:5]}"

    @pytest.mark.skipif(sys.platform == "darwin", reason="macOS reads no environment variable")
    def test_the_watch_would_have_caught_the_incident(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, file_access: list[tuple[str, str]]
    ) -> None:
        """Positive control for the test above, on a directory that stands in for
        the real one: with the variable pointing THERE, the very save that made
        the 207 Walnuts is seen — a directory created, a file opened for writing."""
        pretend = tmp_path / "pretend-real"
        monkeypatch.setenv("APPDATA", str(pretend))
        monkeypatch.setenv("XDG_DATA_HOME", str(pretend))
        monkeypatch.setattr(library_module, "_library_instance", None)
        library = library_module.get_plant_library()
        library.add_plant(PlantSpeciesData(scientific_name="Juglans regia", common_name="Walnut"))
        seen = [(event, Path(path).name) for event, path in file_access
                if under(path, pretend / "OpenGardenPlanner")]
        assert ("os.mkdir", "OpenGardenPlanner") in seen
        assert ("open", "custom_plants.json") in seen
        assert (pretend / "OpenGardenPlanner" / "custom_plants.json").is_file()

    def test_the_watch_sees_a_write_into_a_directory(
        self, tmp_path: Path, file_access: list[tuple[str, str]]
    ) -> None:
        """Positive control: the assertion above is only worth something if the
        watch catches the forms of access the stores use."""
        target = tmp_path / "pretend-real" / "OpenGardenPlanner"
        target.mkdir(parents=True)
        (target / "a.json").write_text("{}", encoding="utf-8")
        with open(target / "b.json", "w", encoding="utf-8") as handle:
            json.dump({}, handle)
        os.replace(target / "b.json", target / "c.json")
        (target / "a.json").read_text(encoding="utf-8")
        os.listdir(target)
        events = {event for event, path in file_access if under(path, target)}
        assert {"os.mkdir", "open", "os.rename", "os.listdir"} <= events
        assert sum(1 for event, path in file_access if event == "open" and under(path, target)) == 3
