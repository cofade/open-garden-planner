"""Drive the REAL app — ``main()`` from source, or the frozen exe — through the 3D
workspace, with a settings store that is never the developer's (Phase 17 L1.3).

Not a test module. Two ways in, one behaviour:

- **from source**: ``workspace_gate_child.py`` imports this module and then calls the
  app's own ``main()`` — the translator, the theme, the exception hook, the window,
  ``app.exec()`` and the interpreter's shutdown are the product's, not a test's;
- **frozen**: the gate build (``workspace_gate.spec``) lists this file as a PyInstaller
  RUNTIME HOOK, so it runs inside the exe before the app's entry script.

WHY IT EXISTS. The app keeps its settings in a store built from two names in
``open_garden_planner.app.settings`` — on Windows a registry key that no environment
variable moves. A scripted run that opens a plan writes Recent Files, and a clean
close writes the window geometry: into the developer's own settings, unless the
names are rebound BEFORE anything builds a store. So this module, first of all,

1. waits for the import of the settings module and rebinds the two names the moment
   its body has run (a meta-path finder, as ``quick3d_child_site/sitecustomize.py``
   does for test children) — to ``cofade_test`` and the name the gate was given;
2. wraps ``create_qsettings`` — the one place a store is built (ADR-041) — so that
   every store is RECORDED with the names Qt reports for it, and so that a store
   under any other organisation is REFUSED before it exists: the process ends with
   exit code ``REFUSED`` (97). The guard fails closed;
3. turns the Welcome dialog and the Agent API off in that throw-away store (a modal
   dialog and a listening port have no place in a scripted run);
4. answers every ``urllib.request.urlopen`` with "offline", at once, and counts the
   calls (``_no_network``). A gate run talks to nobody — and the FROZEN app asks
   GitHub for a newer release two seconds after its window exists
   (``GardenPlannerApp._start_update_check``, frozen only). That request runs in a
   ``QThread`` owned by the main window and nothing joins it: a window closed while
   the answer is still on its way takes the running thread with it, and Qt aborts the
   process ("QThread: Destroyed while thread is still running", exit code
   0xC0000409). That is a defect of the shipped app, written up as a follow-up issue
   — and it made "the frozen app closes clean" depend on how fast GitHub answered
   (it failed once in a loaded run, in the scenario that closes about two seconds
   after the start). So the close gates say nothing about a close DURING an update
   check; the report's ``network`` field says so in every run.

Then, if ``OGP_WORKSPACE_GATE`` names a JSON file ``{"scenario", "out", "store",
"args"}``, it arms a scenario that runs INSIDE the app on the GUI thread once the
main window exists — "enter 3D, wait for the first frame, close" and its variants —
and writes what happened to ``out`` after every step (a process that dies leaves
the last step it reached).

Standard library only at import; everything of Qt and of the app is imported
lazily, inside the functions that run once the app has imported it itself.
"""

from __future__ import annotations

import atexit
import contextlib
import importlib.abc
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

SPEC_VARIABLE = "OGP_WORKSPACE_GATE"
SETTINGS_MODULE = "open_garden_planner.app.settings"
APPLICATION_MODULE = "open_garden_planner.app.application"
TEST_ORGANIZATION = "cofade_test"  # the organisation tests/conftest.py uses
#: The exit code of a process that was about to build a store on another organisation.
REFUSED = 97
#: How long a scenario waits for a condition before it gives up and closes the app.
PATIENCE_S = 60.0

_spec: dict[str, Any] = {}
_stores: list[list[str]] = []
_steps: list[dict[str, Any]] = []
_state: dict[str, Any] = {"production": None, "settings": None, "started": time.time()}


def _load_spec() -> None:
    path = os.environ.get(SPEC_VARIABLE)
    if path:
        with contextlib.suppress(OSError, ValueError):
            _spec.update(json.loads(Path(path).read_text(encoding="utf-8")))


def store_name() -> str:
    """The application name of the gate's throw-away store. A NAMED one (from the
    spec) lets two runs share a log directory — the crash marker's story needs a
    process that dies and one that starts after it; otherwise one per process."""
    return str(_spec.get("store") or f"Open Garden Planner Gate {os.getpid()}")


def _write() -> None:
    out = _spec.get("out")
    if not out:
        return
    report = {
        "scenario": _spec.get("scenario"), "pid": os.getpid(), "steps": _steps,
        "stores": _stores, "production": _state["production"],
        "late": bool(_state.get("late")),
        "frozen": bool(getattr(sys, "frozen", False)),
        "network": _state.get("network", "real"),
        "network_calls": int(_state.get("network_calls", 0)),
        "seconds": round(time.time() - _state["started"], 2),
    }
    with contextlib.suppress(OSError):
        temporary = Path(str(out) + ".tmp")
        temporary.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        os.replace(temporary, out)


def step(name: str, **fields: Any) -> None:
    """Record a step of the scenario and write the report (flushed every time)."""
    _steps.append({"step": name, "t": round(time.time() - _state["started"], 3), **fields})
    _write()


# ── 1 + 2 + 3: the settings store ────────────────────────────────────────────


def _guard_settings(module: ModuleType) -> None:
    """The settings module's body has just run: no store can exist yet."""
    if _state["settings"] is None:
        _state["production"] = [module.ORGANIZATION_NAME, module.APPLICATION_NAME]
    _state["settings"] = module
    module.ORGANIZATION_NAME = TEST_ORGANIZATION  # type: ignore[attr-defined]
    module.APPLICATION_NAME = store_name()  # type: ignore[attr-defined]
    factory = module.create_qsettings

    def create_qsettings(*arguments: Any, **options: Any) -> Any:
        if module.ORGANIZATION_NAME != TEST_ORGANIZATION:
            # fail closed: somebody put the names back. No store is built.
            step("REFUSED", organization=str(module.ORGANIZATION_NAME),
                 application=str(module.APPLICATION_NAME))
            os._exit(REFUSED)
        store = factory(*arguments, **options)
        names = [str(store.organizationName()), str(store.applicationName())]
        if names[0] != TEST_ORGANIZATION:
            step("REFUSED", organization=names[0], application=names[1])
            os._exit(REFUSED)
        if names not in _stores:
            _stores.append(names)
        return store

    create_qsettings.__doc__ = factory.__doc__
    module.create_qsettings = create_qsettings  # type: ignore[attr-defined]
    quiet = module.create_qsettings()
    quiet.setValue(module.AppSettings.KEY_SHOW_WELCOME, False)
    quiet.setValue(module.AppSettings.KEY_AGENT_API_ENABLED, False)
    quiet.sync()


def _no_network() -> None:
    """4. of the module docstring: every ``urllib.request.urlopen`` of this process is
    answered with "offline" at once (the app's update check and its weather forecast
    both go through it, and both treat an ``OSError`` as "no network today")."""
    import urllib.request

    def offline(*_arguments: Any, **_options: Any) -> Any:
        _state["network_calls"] = int(_state.get("network_calls", 0)) + 1
        raise OSError("the workspace gate runs without a network")

    urllib.request.urlopen = offline
    _state["network"] = "offline"


def _arm(module: ModuleType) -> None:
    """The application module's body has just run: start the scenario when the main
    window has been built."""
    if not _spec.get("scenario"):
        return
    window_class = module.GardenPlannerApp
    original = window_class.__init__

    def __init__(self: Any, *arguments: Any, **options: Any) -> None:
        original(self, *arguments, **options)
        from PyQt6.QtCore import QTimer

        _quiet_message_boxes()
        self._gate_runner = _Runner(self)
        QTimer.singleShot(0, self._gate_runner.start)

    window_class.__init__ = __init__


class _Rebinder(importlib.abc.MetaPathFinder):
    """Finds nothing itself: for the two modules it asks the real finders and wraps the
    loader they name, so that ``after`` runs right after the module's body."""

    def __init__(self) -> None:
        self._after: dict[str, Callable[[ModuleType], None]] = {
            SETTINGS_MODULE: _guard_settings, APPLICATION_MODULE: _arm}
        self._asking: set[str] = set()

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> ModuleSpec | None:
        after = self._after.get(fullname)
        if after is None or fullname in self._asking:
            # the second case: ANOTHER delegating finder (the test children's own
            # settings hook) is asking the finders in turn, this one among them — two
            # such finders would otherwise ask each other for ever
            return None
        self._asking.add(fullname)
        try:
            for finder in sys.meta_path:
                find = getattr(finder, "find_spec", None)
                if finder is self or find is None:
                    continue
                spec = find(fullname, path, target)
                if spec is not None and spec.loader is not None:
                    run = spec.loader.exec_module

                    def exec_module(module: ModuleType, run: Any = run,
                                    after: Any = after) -> None:
                        run(module)
                        after(module)

                    spec.loader.exec_module = exec_module  # type: ignore[method-assign]
                    return spec
            return None
        finally:
            self._asking.discard(fullname)


def _at_exit() -> None:
    _write()
    module = _state["settings"]
    if module is not None and _stores and not _spec.get("keep_store"):
        with contextlib.suppress(Exception):  # best effort while the interpreter shuts down
            store = module.create_qsettings()
            store.clear()
            store.sync()


# ── the scenarios (GUI thread, inside the running app) ────────────────────────


def _quiet_message_boxes() -> None:
    """A modal box nobody can click would hold a scripted run for ever: record it."""
    from PyQt6.QtWidgets import QMessageBox

    def recorder(kind: str, answer: Any) -> Any:
        def box(*arguments: Any, **_options: Any) -> Any:
            texts = [str(a)[:300] for a in arguments[1:3]]
            step("message_box", kind=kind, texts=texts)
            return answer

        return staticmethod(box)

    buttons = QMessageBox.StandardButton
    QMessageBox.critical = recorder("critical", buttons.Ok)  # type: ignore[method-assign,assignment]
    QMessageBox.warning = recorder("warning", buttons.Ok)  # type: ignore[method-assign,assignment]
    QMessageBox.information = recorder("information", buttons.Ok)  # type: ignore[method-assign,assignment]
    QMessageBox.question = recorder("question", buttons.Discard)  # type: ignore[method-assign,assignment]


class _Runner:
    """Runs one scenario — a generator — on the GUI thread. The scenario yields a
    number (wait that many milliseconds) or a callable (wait until it answers true,
    at most ``PATIENCE_S``; a callable that never does is recorded and ends the run)."""

    def __init__(self, window: Any) -> None:
        self.window = window
        self._steps: Iterator[Any] | None = None
        self._waiting: Callable[[], Any] | None = None
        self._deadline = 0.0

    def start(self) -> None:
        name = str(_spec.get("scenario"))
        scenario = SCENARIOS.get(name)
        if scenario is None:
            scenario = _measured_scenario(name)
        step("start", scenario=name, known=scenario is not None)
        if scenario is None:
            self._finish()
            return
        self._steps = scenario(self.window, dict(_spec.get("args") or {}))
        self._advance()

    def _advance(self) -> None:
        from PyQt6.QtCore import QTimer

        try:
            if self._waiting is not None:
                if not self._waiting():
                    if time.time() < self._deadline:
                        QTimer.singleShot(40, self._advance)
                        return
                    step("TIMEOUT", waiting_for=getattr(self._waiting, "__name__", "condition"))
                    self._waiting = None
                    self._finish()
                    return
                self._waiting = None
            assert self._steps is not None
            wanted = next(self._steps)
        except StopIteration:
            self._finish()
            return
        except Exception as error:
            import traceback

            step("EXCEPTION", error=f"{type(error).__name__}: {error}",
                 traceback=traceback.format_exc()[-3000:])
            self._finish()
            return
        if callable(wanted):
            self._waiting, self._deadline = wanted, time.time() + PATIENCE_S
            QTimer.singleShot(0, self._advance)
        else:
            QTimer.singleShot(int(wanted), self._advance)

    def _finish(self) -> None:
        """Close the main window the way the user does; ``app.exec()`` then returns."""
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        step("closing")
        closed = bool(self.window.close())
        # what this run wrote, read back through the app's own settings object — whose
        # store is one of the recorded ones: Recent Files (a plan was opened) and the
        # window geometry (closeEvent saved it)
        module = _state["settings"]
        recent = list(module.get_settings().recent_files) if module is not None else []
        geometry = (module.create_qsettings().value("UiState/geometry") is not None
                    if module is not None else False)
        step("closed", accepted=closed, recent_files=recent, geometry_saved=bool(geometry))

        def still_running() -> None:
            # the last window is gone and exec() has not returned: say so, then end it
            step("FORCED_QUIT")
            application = QApplication.instance()
            if application is not None:
                application.quit()

        QTimer.singleShot(5000, still_running)


def workspace_facts(window: Any) -> dict[str, Any]:
    """What a scenario reports about the workspace at one moment."""
    workspace = window._workspace
    if workspace is None:
        return {"workspace": None}
    facts: dict[str, Any] = {
        # what of Qt Quick this process has imported so far: nothing before 3D is asked for
        "quick_modules": sorted(name for name in sys.modules if name.startswith("PyQt6.QtQuick")),
        "mode": workspace.mode.value, "state": workspace.view3d_state.value,
        "guard_mode": getattr(workspace.guard.mode, "value", None) if workspace._guard else None,
        "guard_reason": workspace.guard.reason.value if workspace._guard else None,
        "compat": workspace.compat_text(), "message": workspace.message_text(),
        "status": workspace.status_text(), "problems": workspace.problems_text(),
    }
    host = workspace.host
    if host is not None:
        health = host.health()
        facts.update({
            "host_state": host.state.value, "frames_presented": health.frames_presented,
            "qml_warnings": list(health.qml_warnings), "scene_graph_error": health.scene_graph_error,
            "graphics_api": host.graphics_api(), "prefers_software": host.prefers_software,
            "parts": host.part_count(), "stale_frames": host.stale_frames,
            "off_gui_thread": host.slot_calls_off_the_gui_thread,
        })
    controller = workspace.controller
    if controller is not None:
        facts.update({"records": len(controller.sync.records), "snapshots": controller.snapshot_count,
                      "applies": controller.apply_count, "recoveries": controller.recovery_count,
                      "last_error": controller.last_error, "active": controller.active})
    directory = workspace.guard._directory if workspace._guard else None
    if directory is not None and Path(directory).is_dir():
        facts["guard_files"] = sorted(p.name for p in Path(directory).iterdir()
                                      if p.name.startswith("view3d-"))
        facts["guard_directory"] = str(directory)
    return facts


def _still_look() -> None:
    """A STILL scene at ONE preset, for every scenario of the gate (L1.4): the soak and
    the gate tests compare readbacks exactly, and a wind that sways or an automatic
    quality that steps would make two frames of the same plan differ. Reduced motion
    rests the wind's clock at 0 ("at rest means the clock IS 0"); the preset is the
    one the engine story measured with. Written to the gate's own throw-away store
    (``_guard_settings``), before the 3D pane is first opened — the look controller
    reads it when it is built."""
    module = sys.modules.get(SETTINGS_MODULE)
    if module is None:
        return
    settings = module.get_settings()
    settings.view3d_reduced_motion = True
    settings.view3d_quality = "high"


def _enter(window: Any, mode: str) -> None:
    """Switch the mode the way the View menu does: through its action."""
    _still_look()
    workspace = window._workspace
    index = {"plan": 0, "3d": 1, "split": 2}[mode]
    workspace.mode_actions()[index].trigger()
    if workspace.look is not None:   # a pane that was open before this call
        workspace.apply_look_settings()


def _running(window: Any) -> Callable[[], bool]:
    def first_frame_confirmed() -> bool:
        return bool(window._workspace.view3d_state.value in ("running", "unavailable", "failed"))

    return first_frame_confirmed


def _settled(window: Any) -> Callable[[], bool]:
    def pipeline_idle() -> bool:
        controller = window._workspace.controller
        return controller is None or not controller.dirty

    return pipeline_idle


def _scenario_never(window: Any, _args: dict[str, Any]) -> Iterator[Any]:
    step("shown", **workspace_facts(window))
    yield 700


def _scenario_visible(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    _enter(window, str(args.get("mode", "3d")))
    step("entered", **workspace_facts(window))
    yield _running(window)
    yield _settled(window)
    yield 400
    step("visible", **workspace_facts(window))


def _scenario_hidden(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    yield from _scenario_visible(window, args)
    _enter(window, "plan")
    yield 300
    step("hidden", **workspace_facts(window))


def _scenario_die_in_init(window: Any, _args: dict[str, Any]) -> Iterator[Any]:
    """A process that dies inside its first 3D start: no close, no exit handler."""
    _enter(window, "3d")
    step("dying", **workspace_facts(window))
    os._exit(3)
    yield 0  # pragma: no cover - never reached


def _scenario_try_hardware(window: Any, args: dict[str, Any]) -> Iterator[Any]:
    yield from _scenario_visible(window, args)
    button = window._workspace._compat_button
    step("button", visible=bool(button.isVisible()), text=str(button.text()))
    button.click()
    yield 100
    step("asked_for_hardware", **workspace_facts(window))


SCENARIOS: dict[str, Callable[[Any, dict[str, Any]], Iterator[Any]]] = {
    "never": _scenario_never,
    "visible": _scenario_visible,
    "hidden": _scenario_hidden,
    "die_in_init": _scenario_die_in_init,
    "try_hardware": _scenario_try_hardware,
}


def _measured_scenario(name: str) -> Callable[[Any, dict[str, Any]], Iterator[Any]] | None:
    """The measuring scenarios live beside this file and exist from source only (the
    frozen gate build carries this one file): the workspace story's, and the default
    flip's (L1.9)."""
    for module_name in ("workspace_gate_measure", "workspace_default_measure"):
        try:
            module = __import__(module_name)
        except ImportError:
            continue
        found = getattr(module, "SCENARIOS", {}).get(name)
        if callable(found):
            return found  # type: ignore[no-any-return]
    return None


_load_spec()
_no_network()
sys.meta_path.insert(0, _Rebinder())
atexit.register(_at_exit)
# Imported too late — the app's modules are loaded already: rebind and guard NOW (a
# store built before this line was built on whatever names were bound then; the
# report says so, and the test that reads it fails).
if SETTINGS_MODULE in sys.modules:
    _state["late"] = True
    _guard_settings(sys.modules[SETTINGS_MODULE])
if APPLICATION_MODULE in sys.modules:
    _arm(sys.modules[APPLICATION_MODULE])
