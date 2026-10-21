"""Main entry point for Open Garden Planner."""

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

# Windows-specific taskbar icon support: Tell Windows this is a distinct app
# (not generic Python) for taskbar icon grouping. MUST be called before creating
# any UI or importing GUI engines (like WebEngine) so the AUMID is established early.
if sys.platform == "win32" and "--selftest-supervisor" not in sys.argv:
    try:
        import ctypes

        myappid = "cofade.opengarden.planner.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except (AttributeError, ImportError):
        pass

from dotenv import load_dotenv

if TYPE_CHECKING:
    from PyQt6.QtGui import QIcon

    from open_garden_planner.ui.view3d.quick3d.runlog import RenderLog

# QtWebEngineWidgets (used by the satellite map picker) must be imported
# before QApplication is created — Qt enforces this so it can configure
# OpenGL sharing in time. Importing here at module load satisfies the
# requirement regardless of whether the picker is opened this session.
from PyQt6 import QtWebEngineWidgets  # noqa: F401, E402

# Load environment variables from a ``.env`` file. Two layouts to support:
# - Dev (source run): repo-root ``.env`` (three parents up from this file).
# - Frozen (PyInstaller exe): ``.env`` placed next to the .exe by the user;
#   ``__file__`` is inside ``_internal/`` so the source-relative lookup
#   misses, leaving the menu permanently disabled. Check both — the first
#   hit wins.
_dev_env = Path(__file__).parent.parent.parent / ".env"
_frozen_env = (
    Path(sys.executable).parent / ".env" if getattr(sys, "frozen", False) else None
)
for _candidate in (_frozen_env, _dev_env):
    if _candidate and _candidate.is_file():
        load_dotenv(_candidate)
        break


def get_icon_path() -> Path:
    """Get the path to the application icon."""
    return Path(__file__).parent / "resources" / "icons" / "OGP_logo.png"


def get_app_icon() -> "QIcon":
    """Get the application QIcon with all available multi-resolution frames."""
    from PyQt6.QtGui import QIcon

    icon = QIcon()
    icons_dir = Path(__file__).parent / "resources" / "icons"
    ico_path = icons_dir / "ogp_app.ico"
    if ico_path.exists():
        icon.addFile(str(ico_path))
    png_path = icons_dir / "OGP_logo.png"
    if png_path.exists():
        icon.addFile(str(png_path))
    return icon


#: A whole ``--selftest`` that has not finished after this many seconds is a hang:
#: a watchdog ends the process with exit code 1. Measured (ADR-048 addendum L1.2):
#: 3-7 s in the frozen exe on a GPU and on WARP.
SELFTEST_WATCHDOG_S = 300.0

#: The flag of the process that supervises a running ``--selftest`` (the same
#: string as ``runlog.SUPERVISOR_FLAG``; pinned by a test — not imported here, so
#: that a normal start loads nothing of the 3D package).
_SUPERVISOR_FLAG = "--selftest-supervisor"


def _run_selftest(log: "RenderLog | None" = None) -> int:
    """Headless self-test for lazily-imported subsystems (issue #277).

    The pre-release exe smoke test only exercises startup; a subsystem that is
    imported lazily passes startup and only fails when the user reaches it. That
    is how #277 shipped: the 3D view of the time (Qt 3D, ADR-038, removed in
    Phase 17 L1.10) was built against another Qt micro than the bundled runtime
    and killed the process when it was opened. The lesson stands for every
    block below: exercise the REAL artifact's lazily-loaded parts — the Agent API
    server binds a port, the A1 checks run, and the 3D engine (Qt Quick 3D) loads
    its scene from the bundle and RENDERS a frame, which fails on a mismatched or
    missing Qt Quick 3D library as the #277 import did. Returns non-zero on any
    failure so a broken frozen build fails the release instead of shipping.

    A windowed (console=False) frozen exe is given no CONSOLE, so when it is
    launched detached -- `Start-Process -Wait -PassThru`, what CI does -- it has
    no stdout at all and the EXIT CODE is the only channel. Launched from a
    shell that redirects (a pipe), it *does* inherit a handle and the prints
    below are visible; that is the local/dev case.
    """
    ok = True

    # --- Agent API embedded server (issue #291) ---------------------------
    #
    # The 8-second exe smoke test only proves the app survives startup, which a
    # silently-dead subsystem passes. The Agent API server died in every
    # released windowed build because uvicorn's default log config calls
    # sys.stdout.isatty(), and a console=False frozen exe launched with no
    # inherited stdout handle has sys.stdout is None.
    #
    # Starting a real server here exercises the real failure surface in the
    # real artifact -- the reasoning of #277 (the docstring above).
    #
    # But note WHICH launch reproduces #291, because this was stated wrongly for
    # a while (see PF-CI-04): `console=False` means
    # no console is ALLOCATED, not that stdout is unconditionally None. Run this
    # exe through a shell pipe and it inherits a real handle -- measured, ~300
    # bytes of the prints below reached stdout -- so `isatty()` answers and a
    # regression of the `log_config=None` fix would pass. Only a launch with no
    # inherited stdout handle (Start-Process, or a double-click) has
    # `sys.stdout is None`. The gate must use that form or it is testing the
    # wrong condition.
    try:
        import socket

        from open_garden_planner.agent_api import AgentApiServer, AgentProviders

        def _never(*_a: object, **_k: object) -> dict[str, object]:
            raise AssertionError("selftest must not invoke a provider")

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
        probe.close()

        # Populate EVERY provider field from the dataclass itself rather than
        # listing them. The explicit list this replaced was a drift guard that
        # fired in the wrong direction: adding a provider field and forgetting
        # THIS file failed the selftest, even though the selftest's own job is
        # only to prove a real AgentApiServer binds (the #291 check). It never
        # verified application.py's wiring, which is the thing actually worth
        # catching — and a missing field there is a startup TypeError the app
        # hits immediately anyway. Deriving the fields keeps the tripwire (every
        # value is still `_never`, so an accidental provider call still fails
        # loudly) and can never drift.
        server = AgentApiServer(
            AgentProviders(
                # cast keeps mypy happy: `**dict` cannot be matched against the
                # dataclass's per-field Callable types, and the explicit list this
                # replaced was giving that check for free. mypy is baseline-gated in CI;
                # this explicit type keeps the provider contract checked.
                **cast("dict[str, Any]", dict.fromkeys(AgentProviders.__dataclass_fields__, _never))
            ),
            port=free_port,
        )
        try:
            server.start()
            if server.is_running:
                print(f"  OK   Agent API server started on {free_port}")
            else:
                ok = False
                print("  FAIL Agent API server did not start (issue #291 class)")
        finally:
            server.stop()
    except Exception as exc:  # noqa: BLE001 - report every failure, never abort
        ok = False
        print(f"  FAIL Agent API server selftest -> {exc!r}")

    try:
        _run_a1_selftest()
        print("  OK   A1 strict plan I/O, image codecs and verified installer check")
    except Exception as exc:
        ok = False
        print(f"  FAIL A1 ingestion selftest -> {exc!r}")

    # --- Qt Quick 3D engine (Phase 17 L1.2, ADR-048) ----------------------
    if not _selftest_quick3d(log):
        ok = False

    print("SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _name_application_for_selftest() -> None:
    """Give Qt the application's identity when no application exists yet.

    The self-test log lives in the app's per-user log directory, which hangs on
    that identity (QStandardPaths.AppDataLocation). main() names the application
    only after creating its QApplication; the self-test runs before that, so it
    uses the same pair itself -- and leaves an existing application's alone.
    """
    from PyQt6.QtCore import QCoreApplication

    from open_garden_planner.app.settings import APPLICATION_NAME, ORGANIZATION_NAME

    if QCoreApplication.instance() is None:
        QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
        QCoreApplication.setApplicationName(APPLICATION_NAME)


def _run_selftest_bounded() -> int:
    """``--selftest`` as the frozen exe runs it: EVERY block under one watchdog.

    A self-test that hangs must fail, not hold a release job for six hours (the
    GitHub default): after ``SELFTEST_WATCHDOG_S`` the watchdog writes the reason
    and every thread's stack into the self-test log and ends the process with
    exit code 1. It covers the Agent API block and the A1 ingestion checks too,
    not only the 3D render. The log also records the overall exit code, so a log
    whose 3D part passed and whose exit code is 1 points at the first two
    blocks.

    The watchdog is SUPERVISED: a second, tiny process (this exe with
    ``--selftest-supervisor``) ends this one from outside when it is still alive
    ten seconds after the deadline. The in-process exit alone was measured not
    to end a process that is deadlocked inside Qt and the graphics driver
    (``runlog.py``). That safety net is a subsystem like the three under test:
    on Windows the self-test FAILS when its supervising process did not start,
    refused, never found this block, or did not leave when it was released
    (the #291 pattern - a dead subsystem that the gate itself would never have
    noticed). Its line, "FAIL self-test supervisor -> ...", names which.

    If the log cannot be opened the blocks still run, still under the watchdog
    (it ends a hang without a file to dump into), and the result is FAIL: a
    self-test that cannot say why it failed has failed.
    """
    try:
        from open_garden_planner.ui.view3d.quick3d.runlog import RenderLog, watchdog
    except Exception as exc:  # noqa: BLE001 - report every failure, never abort
        print(f"  FAIL the self-test's log and watchdog cannot be imported -> {exc!r}")
        print("SELFTEST: FAIL")
        return 1
    log_error: Exception | None = None
    try:
        _name_application_for_selftest()
        from open_garden_planner.ui.view3d.quick3d.selftest import default_log_path

        log = RenderLog(default_log_path(), mirror=False)
    except Exception as exc:  # noqa: BLE001 - report every failure, never abort
        log_error = exc
        log = RenderLog(None, mirror=False)  # writes nowhere; the watchdog still ends a hang
    try:
        log("selftest_start", frozen=bool(getattr(sys, "frozen", False)),
            python=sys.version.split()[0])
        with watchdog(SELFTEST_WATCHDOG_S, log, what="--selftest", supervised=True) as armed:
            code = _run_selftest(log)
        if sys.platform == "win32":
            # "" only when a supervising process started, held this block's release
            # event, and left when it was released (runlog.Armed.gap)
            missing = armed.gap
            log("selftest_supervisor", ok=not missing, detail=missing or "started, released, left")
            if missing:
                print(f"  FAIL self-test supervisor -> {missing}")
                print("SELFTEST: FAIL (a hang would not have been ended)")
                code = 1
        if log_error is not None:
            print(f"  FAIL self-test log -> {log_error!r}")
            print("SELFTEST: FAIL (no log)")
            code = 1
        log("selftest_exit", code=code, result="PASS" if code == 0 else "FAIL",
            note="covers the Agent API server, the A1 ingestion checks and the Qt Quick 3D "
                 "frame")
        return code
    finally:
        log.close()


def _selftest_quick3d(log: "RenderLog | None" = None) -> bool:
    """The Qt Quick 3D part of the self-test (Phase 17 L1.2, ADR-048); True for a pass.

    The 3D engine is loaded lazily, so the reasoning of #277 applies (the
    docstring of ``_run_selftest``) -- and importing its bindings is not enough: its scene is QML and
    shader FILES in the bundle, and a shader that does not compile is only a
    Qt warning. So this RENDERS: it loads Garden.qml from the bundle, draws one
    160x120 frame WITHOUT showing a window (a lit box, its shadow, one swatch
    per material kind) and checks the pixels. It needs no GPU: the release
    runner renders it with Direct3D 11 on WARP. A hang is bounded by a
    watchdog (stack dump into the log, exit code 1): the one around the whole
    self-test when ``log`` is passed (``_run_selftest_bounded``), its own
    around the render otherwise.

    The engine imports stay inside ui/view3d/quick3d/ (the import rule). The
    log path is printed because the exit code alone cannot say WHICH check
    failed, and a detached windowed exe has no stdout.

    The log goes into the app's ONE per-user log directory, beside app.log and
    crash.log -- never under a predictable name in the temp directory, which
    on Linux other users can write to (CWE-377). That directory hangs on the
    application's identity (QStandardPaths.AppDataLocation), which main() gives
    Qt only after it created its QApplication. The self-test runs before that,
    so it names the application itself, with the same pair -- unless an
    application already exists, whose identity is not ours to change.
    """
    try:
        from open_garden_planner.ui.view3d.quick3d.selftest import run_selftest

        _name_application_for_selftest()
        # one faulthandler timer per process: with the caller's log comes the
        # caller's watchdog, and run_selftest must not arm a second one
        quick3d = run_selftest() if log is None else run_selftest(log=log, watchdog_s=None)
        for line in quick3d.lines:
            print(line)
        print(f"  3D self-test log: {quick3d.log_path}")
        return quick3d.ok
    except Exception as exc:  # noqa: BLE001 - report every failure, never abort
        print(f"  FAIL Qt Quick 3D selftest -> {exc!r}")
        return False


def _run_a1_selftest() -> None:
    """Exercise the packaged ingestion code/codecs with isolated local fixtures."""
    import hashlib
    import io
    import tempfile

    from PIL import Image

    from open_garden_planner.core.plan_io import PlanValidationError, read_plan, write_plan
    from open_garden_planner.services.image_download import decode_image
    from open_garden_planner.services.verified_update import VerifiedInstaller

    with tempfile.TemporaryDirectory(prefix="ogp-a1-selftest-") as directory:
        path = Path(directory) / "fixture.ogp"
        write_plan(path, {"objects": []})
        assert read_plan(path)["objects"] == []
        original = path.read_bytes()
        try:
            write_plan(path, {"objects": [{"x": float("nan")} ]})
        except PlanValidationError:
            pass
        else:
            raise AssertionError("Invalid plan numbers were accepted")
        assert path.read_bytes() == original
        for fmt in ("PNG", "JPEG", "WEBP", "GIF"):
            encoded = io.BytesIO()
            Image.new("RGB", (2, 2), "green").save(encoded, format=fmt)
            assert decode_image(encoded.getvalue(), max_pixels=4).size == (2, 2)
        installer = Path(directory) / "fixture.bin"
        installer.write_bytes(b"synthetic installer")
        VerifiedInstaller(installer, 19, hashlib.sha256(b"synthetic installer").hexdigest()).check()
        assert get_icon_path().is_file()
        assert (get_icon_path().parent / "ogp_app.ico").is_file()


def _write_crash_log(message: str) -> None:
    """Best-effort append of a traceback to a user-findable crash log.

    A windowed (``console=False``) frozen exe launched with no inherited handle
    has ``sys.stderr is None``. An unhandled exception would then leave no
    trace on disk. This function writes into the app-data dir. It never
    raises.
    """
    import contextlib

    with contextlib.suppress(Exception):
        from PyQt6.QtCore import QStandardPaths

        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        if not base:
            return
        log_dir = Path(base)
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "crash.log", "a", encoding="utf-8") as fh:
            fh.write(message)
            fh.write("\n")


def _install_excepthook() -> None:
    """Route unhandled exceptions to a dialog instead of aborting the process.

    Under PyQt6 an exception that escapes a Qt slot calls ``sys.excepthook``.
    With the DEFAULT hook that call aborts the process. It silently kills the
    app and any unsaved plan. Issue #277 hit this path: an ``ImportError``
    from the lazily imported 3D view took the whole process down. The custom
    hook stops the abort. It writes the traceback to stderr in a dev run and
    to a best-effort ``crash.log`` in the app-data dir. The log records the
    traceback for a windowed frozen build. Such a build launched with no
    inherited handle has ``sys.stderr is None``. The hook then shows a
    recoverable dialog so the user can save. The 3D-open path also catches
    its own ``ImportError`` for a clearer message. This hook is the broad
    backstop for everything else.
    """
    import contextlib
    import traceback
    from types import TracebackType

    from PyQt6.QtWidgets import QApplication, QMessageBox

    def _hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        if sys.stderr is not None:
            with contextlib.suppress(Exception):
                sys.stderr.write(message)
        _write_crash_log(message)
        if QApplication.instance() is None:
            return
        # The hook itself must never raise (that would re-enter excepthook).
        with contextlib.suppress(Exception):
            QMessageBox.critical(
                None,
                QApplication.translate("main", "Unexpected Error"),
                QApplication.translate(
                    "main",
                    "An unexpected error occurred. The application will keep "
                    "running so you can save your work.\n\nDetails: {error}",
                ).format(error=exc_value),
            )

    sys.excepthook = _hook


def main() -> int:
    """Run the Open Garden Planner application."""
    # The process that supervises a running self-test (runlog.py). FIRST: its
    # arguments name what it supervises, and nothing of them may start anything else.
    if _SUPERVISOR_FLAG in sys.argv:
        from open_garden_planner.ui.view3d.quick3d.runlog import supervisor_main

        return supervisor_main(sys.argv[sys.argv.index(_SUPERVISOR_FLAG) + 1:])

    # Headless subsystem self-test (issue #277) — before any Qt UI is created.
    if "--selftest" in sys.argv:
        return _run_selftest_bounded()

    # Import here to avoid slow startup for --help, --version, etc.
    from PyQt6.QtWidgets import QApplication

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import (
        APPLICATION_NAME,
        ORGANIZATION_NAME,
        SettingsSecurityError,
        get_settings,
    )
    from open_garden_planner.core.i18n import load_translator
    from open_garden_planner.core.logging_config import setup_logging
    from open_garden_planner.ui.theme import apply_theme

    app = QApplication(sys.argv)
    # Same pair the settings chokepoint builds every store from (ADR-041) — read
    # from there rather than repeated, so there is one source of truth for it.
    app.setApplicationName(APPLICATION_NAME)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setOrganizationDomain("github.com/cofade")

    # Initialize persistent application logging (AUD-063, TD-023, #405)
    setup_logging()

    # Set application icon (appears in taskbar, window title bar, etc.)
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # Apply saved preferences
    try:
        settings = get_settings()
    except SettingsSecurityError as exc:
        from PyQt6.QtCore import QLocale
        from PyQt6.QtWidgets import QMessageBox

        load_translator(app, QLocale.system().name().split("_")[0])
        logging.getLogger(__name__).error("Settings protection failed for %s", exc.path)
        QMessageBox.critical(
            None, app.translate("main", "Settings Access Error"),
            app.translate("main", "Open Garden Planner cannot secure its settings file:\n{path}\n\n"
                          "The file must be owned by your account with owner-only read and write access. "
                          "Correct its permissions and restart the app.").format(path=exc.path),
        )
        return 1
    load_translator(app, settings.language)
    apply_theme(app, settings.theme_mode)

    # Turn an uncaught slot exception into a recoverable dialog instead of a
    # silent process kill that discards unsaved work (issue #277).
    _install_excepthook()

    window = GardenPlannerApp()
    window.show()

    # Reapply theme after window is shown to update title bar
    apply_theme(app, settings.theme_mode)

    # Open file passed as command-line argument (e.g. double-click .ogp file)
    args = app.arguments()
    if len(args) > 1:
        file_arg = Path(args[-1])
        if file_arg.suffix.lower() == ".ogp" and file_arg.is_file():
            window._open_project_file(str(file_arg))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
