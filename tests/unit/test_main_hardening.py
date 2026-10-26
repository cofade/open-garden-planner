"""Issue #277 hardening in ``main.py``: the frozen ``--selftest`` and the
uncaught-exception backstop that together stop a lazily-imported subsystem
failure from silently killing the process and discarding unsaved work.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import types
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.main import _install_excepthook, _run_selftest, _selftest_quick3d
from tests.integration.quick3d_render_support import isolated_env


class TestExceptHook:
    def test_installs_and_shows_dialog_without_reraising(
        self, qtbot, monkeypatch
    ) -> None:
        from PyQt6.QtWidgets import QMessageBox

        calls: list[tuple] = []
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **_k: calls.append(a))

        original = sys.excepthook
        try:
            _install_excepthook()
            assert sys.excepthook is not original
            # Simulate PyQt handing an uncaught slot exception to the hook.
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                sys.excepthook(*sys.exc_info())
        finally:
            sys.excepthook = original

        assert calls, "excepthook should have shown a recoverable dialog"


def _stub_3d(monkeypatch, *, ok: bool = True, raises: bool = False) -> list[dict[str, Any]]:
    """Replace the engine package's self-test: it RENDERS, which this
    ``QT_QPA_PLATFORM=offscreen`` process cannot do (software scene graph — no 3D).
    Returns the list the stand-in appends its keyword arguments to, per call."""
    from open_garden_planner.ui.view3d.quick3d import selftest

    calls: list[dict[str, Any]] = []

    def run_selftest(**kwargs: Any) -> selftest.SelftestResult:
        calls.append(kwargs)
        if raises:
            raise RuntimeError("the engine package blew up")
        line = "  OK   Qt Quick 3D frame (stand-in)" if ok else "  FAIL Qt Quick 3D frame: stand-in"
        return selftest.SelftestResult(ok, (line,), Path("stand-in.log"))

    monkeypatch.setattr(selftest, "run_selftest", run_selftest)
    return calls


@pytest.fixture()
def keep_the_qt_identity():
    """The self-test names the application when none exists yet (so its log lands in
    the app's log directory). Those names are process-global Qt statics: put them
    back, or every later test resolves ``QStandardPaths`` under them."""
    from PyQt6.QtCore import QCoreApplication

    saved = (QCoreApplication.organizationName(), QCoreApplication.applicationName())
    yield
    QCoreApplication.setOrganizationName(saved[0])
    QCoreApplication.setApplicationName(saved[1])


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="the self-test ships in the Windows exe: its real blocks are run where it ships",
)
@pytest.mark.usefixtures("keep_the_qt_identity")
class TestSelfTest:
    """The Agent API and A1 blocks run for real here; the Qt Quick 3D block (L1.2) is a
    stand-in. The real 3D block runs in a subprocess with a real window system
    (``tests/integration/test_quick3d_selftest.py``, render tier) and in the frozen
    exe before every release. (Until L1.10 a Qt 3D block imported the old view's
    bindings and compared the Qt runtime with their wheel's micro — the #277 detector;
    the two remaining Qt pins are guarded by ``tests/unit/test_qt_runtime_pins.py`` and
    the 3D block renders a frame from the bundle.)"""

    def test_passes_on_a_consistent_qt_stack(self, monkeypatch) -> None:
        _stub_3d(monkeypatch)
        assert _run_selftest() == 0

    def test_a_failed_3d_frame_fails_the_whole_selftest(self, monkeypatch, capsys) -> None:
        """Everything else healthy, the 3D engine not: exit 1."""
        _stub_3d(monkeypatch, ok=False)
        assert _run_selftest() == 1
        assert "SELFTEST: FAIL" in capsys.readouterr().out

    def test_a_mismatched_expected_version_fails_the_selftest(self, monkeypatch, capsys) -> None:
        _stub_3d(monkeypatch)
        monkeypatch.setenv("OGP_EXPECTED_VERSION", "9.9.9")
        assert _run_selftest() == 1
        out = capsys.readouterr().out
        assert "FAIL version selftest" in out
        assert "SELFTEST: FAIL" in out

    def test_the_reported_version_is_the_running_package_version(self, monkeypatch, capsys) -> None:
        import open_garden_planner

        _stub_3d(monkeypatch)
        monkeypatch.delenv("OGP_EXPECTED_VERSION", raising=False)
        assert _run_selftest() == 0
        assert f"OK   version {open_garden_planner.__version__}" in capsys.readouterr().out

    def test_the_real_blocks_build_no_settings_store(self, monkeypatch) -> None:
        """The real Agent API server and A1 checks, in this process: no settings
        store is asked for. (The 3D block and the whole command are shown the same way
        in a child with a real platform: ``tests/integration/test_quick3d_selftest.py``.)
        A consumer that bound the factory's name before this test replaced it would not
        be seen here — the child's start-up hook has no such gap."""
        import open_garden_planner.app.settings as app_settings

        asked: list[int] = []
        real = app_settings.create_qsettings

        def create_qsettings() -> Any:
            asked.append(1)
            return real()

        monkeypatch.setattr(app_settings, "create_qsettings", create_qsettings)
        _stub_3d(monkeypatch)
        assert _run_selftest() == 0
        assert asked == []


#: What a self-test must never name: it runs in the frozen exe under the PRODUCTION
#: settings names, against the user's real settings and data.
_NOT_IN_A_SELFTEST = frozenset({
    "get_settings", "create_qsettings", "AppSettings", "QSettings", "ProjectManager",
    "add_recent_file", "GardenPlannerApp", "get_app_data_dir", "get_plant_library"})


def test_the_selftest_names_no_settings_store_and_loads_no_plan() -> None:
    """The static half (every platform). ``--selftest`` in the frozen exe cannot be
    isolated: there the app's settings are the user's own. So its path — the four
    functions in ``main.py`` — names no settings accessor, no project manager and no
    app-data helper; from the settings module it takes the application's two NAMES and
    nothing else; and the two packages the 3D block runs in do not import the app
    layer at all."""
    import ast

    root = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"
    tree = ast.parse((root / "main.py").read_text(encoding="utf-8"))
    path = {"_run_selftest", "_run_selftest_bounded", "_selftest_quick3d", "_name_application_for_selftest"}
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert path <= set(functions)
    taken: set[str] = set()
    for name in sorted(path):
        function = functions[name]
        named = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        named |= {node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)}
        named |= {alias.name for node in ast.walk(function) if isinstance(node, (ast.Import, ast.ImportFrom))
                  for alias in node.names}
        assert not named & _NOT_IN_A_SELFTEST, (name, sorted(named & _NOT_IN_A_SELFTEST))
        taken |= {alias.name for node in ast.walk(function) if isinstance(node, ast.ImportFrom)
                  and (node.module or "").endswith("app.settings") for alias in node.names}
    assert taken == {"APPLICATION_NAME", "ORGANIZATION_NAME"}
    checked = 0
    for package in (root / "ui" / "view3d" / "quick3d", root / "core" / "scene3d"):
        for source in sorted(package.rglob("*.py")):
            home = ["open_garden_planner", *source.relative_to(root).parent.parts]
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    base = home[:len(home) - node.level + 1] if node.level else []
                    stem = ".".join([*base, *([node.module] if node.module else [])])
                    modules = [stem, *(f"{stem}.{alias.name}" for alias in node.names)]
                elif isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                else:
                    continue
                checked += 1
                for module in modules:
                    assert not module.startswith(("open_garden_planner.app", "open_garden_planner.services",
                                                  "open_garden_planner.core.project")), (
                        f"{source.name} imports {module}")
    assert checked > 60, "the scan read the packages' imports"


@pytest.mark.usefixtures("keep_the_qt_identity")
class TestSelfTestQuick3d:
    """``main._selftest_quick3d`` — the wiring of the 3D block, on every platform."""

    def test_a_pass_prints_the_lines_and_the_log_path(self, monkeypatch, capsys) -> None:
        _stub_3d(monkeypatch)
        assert _selftest_quick3d() is True
        out = capsys.readouterr().out
        assert "  OK   Qt Quick 3D frame (stand-in)" in out
        assert "3D self-test log: stand-in.log" in out

    def test_a_failed_frame_is_a_failure_and_says_why(self, monkeypatch, capsys) -> None:
        _stub_3d(monkeypatch, ok=False)
        assert _selftest_quick3d() is False
        out = capsys.readouterr().out
        assert "FAIL Qt Quick 3D frame: stand-in" in out and "3D self-test log: stand-in.log" in out

    def test_a_crashing_3d_selftest_fails_instead_of_escaping(self, monkeypatch, capsys) -> None:
        _stub_3d(monkeypatch, raises=True)
        assert _selftest_quick3d() is False
        assert "FAIL Qt Quick 3D selftest" in capsys.readouterr().out

    def test_an_existing_application_keeps_its_identity(self, qapp, monkeypatch) -> None:
        """The log directory hangs on Qt's application identity, so the self-test names
        the application — but only when it is the one that will create it. An
        application that already exists (this test process's) keeps its own names.
        The other branch needs a process WITHOUT an application: it is pinned end to
        end, in a child, by ``test_quick3d_selftest.py::
        test_the_selftest_writes_its_log_beside_the_apps_logs_not_into_temp``."""
        from PyQt6.QtCore import QCoreApplication

        before = (QCoreApplication.organizationName(), QCoreApplication.applicationName())
        _stub_3d(monkeypatch)
        assert _selftest_quick3d() is True
        assert (QCoreApplication.organizationName(), QCoreApplication.applicationName()) == before

    def test_standalone_the_3d_block_bounds_itself(self, monkeypatch) -> None:
        calls = _stub_3d(monkeypatch)
        assert _selftest_quick3d() is True
        assert calls == [{}], "no log passed: run_selftest opens its own and arms its own watchdog"

    def test_inside_the_bounded_selftest_it_arms_no_second_watchdog(
            self, monkeypatch, tmp_path) -> None:
        """``faulthandler`` has ONE timer per process: with the caller's log comes the
        caller's watchdog, and a second one would silently replace it."""
        from open_garden_planner.ui.view3d.quick3d.runlog import RenderLog

        calls = _stub_3d(monkeypatch)
        log = RenderLog(tmp_path / "whole.log", mirror=False)
        try:
            assert _selftest_quick3d(log) is True
        finally:
            log.close()
        assert calls == [{"log": log, "watchdog_s": None}]

    def test_main_names_no_engine_module(self) -> None:
        """The import rule: ``main.py`` names no Qt Quick module — the engine imports of
        the self-test live in ``ui/view3d/quick3d/selftest.py``."""
        import ast

        import open_garden_planner.main as ogp_main

        source = Path(ogp_main.__file__).read_text(encoding="utf-8")
        strings = {node.value for node in ast.walk(ast.parse(source))
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert not {s for s in strings if s.startswith(("PyQt6.QtQuick", "PyQt6.QtQml"))}
        assert "open_garden_planner.ui.view3d.quick3d.selftest" in source


class TestMainUtilities:
    def test_get_icon_path(self) -> None:
        from open_garden_planner.main import get_icon_path

        p = get_icon_path()
        assert p.name == "OGP_logo.png"
        assert p.exists()

    def test_write_crash_log(self, tmp_path, monkeypatch) -> None:
        from PyQt6.QtCore import QStandardPaths

        from open_garden_planner.main import _write_crash_log

        monkeypatch.setattr(QStandardPaths, "writableLocation", lambda _loc: str(tmp_path))
        _write_crash_log("test crash entry")
        crash_log = tmp_path / "crash.log"
        assert crash_log.exists()
        assert "test crash entry" in crash_log.read_text(encoding="utf-8")

    def test_main_selftest_dispatch(self, monkeypatch) -> None:
        """``--selftest`` runs the BOUNDED self-test — the one under a watchdog."""
        import open_garden_planner.main as ogp_main

        monkeypatch.setattr(ogp_main, "_run_selftest_bounded", lambda: 42)
        monkeypatch.setattr(ogp_main, "_run_selftest", lambda *_a: pytest.fail("not the bare one"))
        monkeypatch.setattr(sys, "argv", ["ogp", "--selftest"])
        assert ogp_main.main() == 42

    def test_the_supervisor_flag_is_dispatched_first_and_starts_nothing_else(self, monkeypatch) -> None:
        """Review round 2, P2-6. The frozen exe is also the process that supervises a
        running self-test (the internal flag ``--selftest-supervisor`` and six arguments,
        the last of them ``what:--selftest``). Its arguments NAME the self-test — and
        must never start one: a supervisor that ran the self-test would start a
        supervisor that runs the self-test."""
        import open_garden_planner.main as ogp_main
        from open_garden_planner.ui.view3d.quick3d import runlog

        assert ogp_main._SUPERVISOR_FLAG == runlog.SUPERVISOR_FLAG
        handed: list[list[str]] = []
        monkeypatch.setattr(runlog, "supervisor_main", lambda arguments: handed.append(arguments) or 7)
        monkeypatch.setattr(ogp_main, "_run_selftest_bounded",
                            lambda: pytest.fail("the supervisor must not run the self-test"))
        arguments = ["4711", "133", "0123456789abcdef0123456789abcdef", "310",
                     "C:/logs/selftest.log", "what:--selftest"]
        monkeypatch.setattr(sys, "argv", ["ogp", runlog.SUPERVISOR_FLAG, *arguments])
        assert ogp_main.main() == 7 and handed == [arguments]
        # … also when a caller put the self-test flag itself on the command line
        handed.clear()
        monkeypatch.setattr(sys, "argv", ["ogp", "--selftest", runlog.SUPERVISOR_FLAG, *arguments])
        assert ogp_main.main() == 7 and handed == [arguments]

    def test_the_supervisor_is_the_frozen_exe_itself(self, monkeypatch) -> None:
        from open_garden_planner.ui.view3d.quick3d import runlog

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert runlog.self_command() == [sys.executable, "--selftest-supervisor"]


_HUNG_BLOCK = textwrap.dedent("""
    import sys
    import time

    import open_garden_planner.main as ogp_main

    def hangs(log=None):
        print("  OK   A1 checks (stand-in)", flush=True)
        time.sleep(120)   # e.g. the Agent API server that never reports its port
        return 0

    ogp_main.SELFTEST_WATCHDOG_S = 2.0
    ogp_main._run_selftest = hangs
    code = ogp_main._run_selftest_bounded()
    print("returned", code, flush=True)
    sys.exit(code)
""")


class _StandInSupervisor:
    """What ``runlog.start_supervisor`` hands out — without a process behind it."""

    def __init__(self, exit_code: int | None) -> None:
        self.exit_code = exit_code
        self.released = 0

    def describe(self) -> str:
        return "process 4711 (a stand-in), ends this one 310 s from now"

    def release(self) -> None:
        self.released += 1

    def wait(self, _timeout_s: float) -> int | None:
        return self.exit_code


@pytest.mark.usefixtures("keep_the_qt_identity")
class TestBoundedSelfTest:
    """Review P1-4. The watchdog used to cover the 3D render only; the other blocks (the
    Qt 3D imports of the time, the Agent API) could hang a release job until GitHub's
    six-hour limit."""

    @pytest.fixture(autouse=True)
    def supervisors(self, monkeypatch) -> Any:
        """The bounded self-test asks for a SUPERVISED watchdog — a second process that
        ends this one from outside. In-process tests get a stand-in instead of a process
        aimed at pytest; ``outcome`` says what it does: an exit code, ``None`` (it did
        not leave), ``"none"`` (nothing was started) or an exception (it could not be
        started). The real one runs in children (``test_a_hang_in_any_block…`` below,
        ``tests/unit/test_quick3d_selftest.py``, ``tests/integration/test_quick3d_selftest.py``)."""
        from open_garden_planner.ui.view3d.quick3d import runlog

        book = types.SimpleNamespace(asked=[], made=[], outcome=0)

        def start(seconds: float, log_path: Any, what: str) -> Any:
            book.asked.append((seconds, log_path, what))
            if isinstance(book.outcome, Exception):
                raise book.outcome
            if book.outcome == "none":
                return None
            book.made.append(_StandInSupervisor(book.outcome))
            return book.made[-1]

        monkeypatch.setattr(runlog, "start_supervisor", start)
        return book

    def test_the_whole_selftest_is_supervised_from_outside(self, monkeypatch, tmp_path,
                                                           supervisors) -> None:
        """Review round 2, P2-6: in a process deadlocked inside Qt the watchdog wrote its
        dump and the process stayed alive. The supervisor ends it ``GRACE_S`` after the
        watchdog's deadline, and is told where the log is. Round 3, P2-5: the log says
        that it was started, released and gone — the safety net is checked like the
        three subsystems it guards."""
        import open_garden_planner.main as ogp_main
        from open_garden_planner.ui.view3d.quick3d import runlog

        monkeypatch.setattr(sys, "platform", "win32")  # where a supervisor exists
        log_file = tmp_path / "selftest.log"
        monkeypatch.setenv("OGP_SELFTEST_LOG", str(log_file))
        monkeypatch.setattr(ogp_main, "_run_selftest", lambda _log=None: 0)
        assert ogp_main._run_selftest_bounded() == 0
        assert supervisors.asked == [
            (ogp_main.SELFTEST_WATCHDOG_S + runlog.GRACE_S, log_file, "--selftest")]
        assert runlog.GRACE_S == 10.0
        (stand_in,) = supervisors.made
        assert stand_in.released == 1
        text = log_file.read_text(encoding="utf-8")
        order = [text.index(marker) for marker in (
            "what=--selftest supervisor=process 4711 (a stand-in)",
            "[watchdog] released=True what=--selftest supervisor_exit=0",
            "[selftest_supervisor] ok=True detail=started, released, left",
            "[selftest_exit] code=0 result=PASS")]
        assert order == sorted(order), text

    @pytest.mark.parametrize(("outcome", "words"), [
        ("none", "none (it could not be started)"),
        (OSError("no such interpreter"),
         "none (it could not be started: OSError: no such interpreter)"),
        (2, "its supervising process refused: this block was not one it may act for (exit code 2)"),
        (3, "its supervising process failed itself (exit code 3)"),
        # review round 4, P2-1: it left without ever holding this block — and used to say 0
        (4, "its supervising process left without having supervised"),
        (None, "its supervising process had not left 15 s after its release"),
    ], ids=["nothing started", "start raised", "refused", "failed", "never supervised",
            "did not leave"])
    def test_without_its_supervisor_the_selftest_fails_on_windows(
            self, monkeypatch, tmp_path, capsys, supervisors, outcome: Any, words: str) -> None:
        """Review round 3, P2-5 — the #291 pattern in the gate's own safety net. A
        supervisor that could not start was swallowed as ``supervisor=none`` and the
        self-test passed: the day a build could not start it, a deadlocked self-test
        would have held the release job, and no run before that day would have said
        so. Every block passed here; the verdict is FAIL."""
        import open_garden_planner.main as ogp_main

        monkeypatch.setattr(sys, "platform", "win32")
        supervisors.outcome = outcome
        log_file = tmp_path / "selftest.log"
        monkeypatch.setenv("OGP_SELFTEST_LOG", str(log_file))
        ran: list[int] = []
        monkeypatch.setattr(ogp_main, "_run_selftest", lambda _log=None: ran.append(1) or 0)
        assert ogp_main._run_selftest_bounded() == 1
        assert ran == [1], "the blocks still ran: a missing supervisor fails the run, it does not skip it"
        out = capsys.readouterr().out
        assert f"FAIL self-test supervisor -> {words}" in out
        assert "SELFTEST: FAIL (a hang would not have been ended)" in out
        text = log_file.read_text(encoding="utf-8")
        assert "[selftest_supervisor] ok=False" in text and words in text
        assert "[selftest_exit] code=1 result=FAIL" in text
        assert "[selftest_exit] code=0" not in text

    def test_off_windows_there_is_no_supervisor_and_the_log_says_what_bounds_a_deadlock(
            self, monkeypatch, tmp_path, supervisors) -> None:
        """Measured on Linux: the in-process exit ends the deadlock (5 of 5). Beyond that
        the bound is the caller's own time limit — in CI the step's — and the log line
        says so instead of a bare "none"."""
        import open_garden_planner.main as ogp_main
        from open_garden_planner.ui.view3d.quick3d import runlog

        monkeypatch.setattr(sys, "platform", "linux")
        log_file = tmp_path / "selftest.log"
        monkeypatch.setenv("OGP_SELFTEST_LOG", str(log_file))
        monkeypatch.setattr(ogp_main, "_run_selftest", lambda _log=None: 0)
        assert ogp_main._run_selftest_bounded() == 0
        assert supervisors.asked == [], "no supervising process is started off Windows"
        text = log_file.read_text(encoding="utf-8")
        assert f"what=--selftest supervisor={runlog.NOT_NEEDED_HERE}" in text
        assert "_exit ends the process" in runlog.NOT_NEEDED_HERE
        assert "in CI the step's" in runlog.NOT_NEEDED_HERE
        assert "[selftest_supervisor]" not in text and "[selftest_exit] code=0 result=PASS" in text

    def test_every_block_runs_under_one_watchdog_and_one_log(self, monkeypatch, tmp_path) -> None:
        import open_garden_planner.main as ogp_main

        seen: list[Any] = []
        log_file = tmp_path / "selftest.log"
        monkeypatch.setenv("OGP_SELFTEST_LOG", str(log_file))

        def blocks(log: Any = None) -> int:
            seen.append(log)
            log("inside", note="the blocks write to the same log")
            return 0

        monkeypatch.setattr(ogp_main, "_run_selftest", blocks)
        assert ogp_main._run_selftest_bounded() == 0
        text = log_file.read_text(encoding="utf-8")
        assert len(seen) == 1 and seen[0] is not None and seen[0].path == log_file
        order = [text.index(marker) for marker in (
            "[selftest_start]", "[watchdog] armed=True seconds=300.0 what=--selftest", "[inside]",
            "[selftest_exit] code=0 result=PASS")]
        assert order == sorted(order), text

    def test_a_failing_block_is_exit_code_1_in_the_log_too(self, monkeypatch, tmp_path) -> None:
        import open_garden_planner.main as ogp_main

        log_file = tmp_path / "selftest.log"
        monkeypatch.setenv("OGP_SELFTEST_LOG", str(log_file))
        monkeypatch.setattr(ogp_main, "_run_selftest", lambda _log=None: 1)
        assert ogp_main._run_selftest_bounded() == 1
        assert "[selftest_exit] code=1 result=FAIL" in log_file.read_text(encoding="utf-8")

    def test_the_real_blocks_take_the_log_through_to_the_3d_block(
            self, monkeypatch, tmp_path) -> None:
        """Not a stand-in for ``_run_selftest``: its own code passes the log on, so the
        3D block does not arm a second watchdog. Windows only, like ``TestSelfTest``."""
        if sys.platform != "win32":
            pytest.skip("the self-test ships in the Windows exe")
        import open_garden_planner.main as ogp_main

        log_file = tmp_path / "selftest.log"
        monkeypatch.setenv("OGP_SELFTEST_LOG", str(log_file))
        calls = _stub_3d(monkeypatch)
        assert ogp_main._run_selftest_bounded() == 0
        assert len(calls) == 1 and calls[0]["watchdog_s"] is None
        assert calls[0]["log"].path == log_file

    def test_without_a_log_the_selftest_fails_but_is_still_bounded(
            self, monkeypatch, tmp_path, capsys) -> None:
        """The log's directory cannot be created (a FILE is in the way): the blocks still
        run, still under the watchdog, and the verdict is FAIL whatever they returned."""
        import open_garden_planner.main as ogp_main
        from open_garden_planner.ui.view3d.quick3d import runlog

        blocker = tmp_path / "a-file"
        blocker.write_text("not a directory", encoding="utf-8")
        monkeypatch.setenv("OGP_SELFTEST_LOG", str(blocker / "selftest.log"))
        armed: list[tuple[float, str, dict[str, Any]]] = []
        real = runlog.watchdog

        def spy(seconds: float, log: Any, what: str = "the run", **options: Any) -> Any:
            armed.append((seconds, what, options))
            return real(seconds, log, what, **options)

        monkeypatch.setattr(runlog, "watchdog", spy)
        ran: list[Any] = []
        monkeypatch.setattr(ogp_main, "_run_selftest", lambda log=None: ran.append(log) or 0)
        assert ogp_main._run_selftest_bounded() == 1
        assert len(ran) == 1 and ran[0].path is None
        assert armed == [(ogp_main.SELFTEST_WATCHDOG_S, "--selftest", {"supervised": True})]
        out = capsys.readouterr().out
        assert "FAIL self-test log ->" in out and "SELFTEST: FAIL (no log)" in out

    def test_a_hang_in_any_block_ends_the_process_and_the_log_says_why(self, tmp_path) -> None:
        """In a child, because the exit is real: a block that is NOT the 3D render hangs.
        Exit code 1 after the watchdog's two seconds, and the log names the reason in
        words before faulthandler's stack dump — the frame that hangs is in it."""
        log_file = tmp_path / "selftest.log"
        env = isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen", OGP_SELFTEST_LOG=str(log_file))
        proc = subprocess.run(
            [sys.executable, "-c", _HUNG_BLOCK], env=env, capture_output=True, text=True,
            timeout=100, cwd=tmp_path)
        assert proc.returncode == 1, proc.stdout + proc.stderr[-2000:]
        assert "returned" not in proc.stdout, "the hang must end the process, not return a verdict"
        text = log_file.read_text(encoding="utf-8")
        assert "[watchdog] armed=True seconds=2.0 what=--selftest" in text
        if sys.platform == "win32":  # the real supervisor was started, and had nothing to do
            assert "what=--selftest supervisor=process " in text and "[supervisor]" not in text
        assert "[watchdog] fired=True what=--selftest" in text
        assert "--selftest did not finish within 2 s" in text
        assert text.index("[watchdog] fired=True") < text.index("Timeout (0:00:02")
        assert "in hangs" in text and "_run_selftest_bounded" in text
        assert "[selftest_exit]" not in text
