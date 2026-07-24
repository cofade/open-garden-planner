"""Main entry point for Open Garden Planner."""

import sys
from pathlib import Path

from dotenv import load_dotenv

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

# Windows-specific imports for taskbar icon support
try:
    import ctypes
    # Tell Windows this is a distinct app (not Python) for taskbar icon grouping
    myappid = 'cofade.opengarden.planner.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except (AttributeError, ImportError):
    # Not on Windows or ctypes not available
    pass


def get_icon_path() -> Path:
    """Get the path to the application icon."""
    return Path(__file__).parent / "resources" / "icons" / "OGP_logo.png"


def _run_selftest() -> int:
    """Headless self-test for lazily-imported subsystems (issue #277).

    The pre-release exe smoke test only exercises startup; the 3D view's Qt3D
    bindings are imported lazily (ADR-038), so a Qt micro-version mismatch
    passes startup and only crashes when the user opens the 3D view. This
    imports every Qt3D binding the view uses — the DLL load + symbol resolution
    here is the EXACT failure surface of #277 — and checks the runtime Qt equals
    the Qt version the Qt3D wheels were built for. No window and no GL context,
    so it runs on a headless CI runner. Returns non-zero on any failure so a
    broken frozen build fails the release instead of shipping.

    A windowed (console=False) frozen exe has no stdout, so CI reads the
    process EXIT CODE (Start-Process -Wait -PassThru); the prints are for a
    local/dev run.
    """
    from importlib.metadata import PackageNotFoundError, version

    from PyQt6.QtCore import qVersion

    ok = True
    for mod in (
        "PyQt6.Qt3DCore",
        "PyQt6.Qt3DExtras",
        "PyQt6.Qt3DRender",
        "PyQt6.Qt3DInput",
        "PyQt6.Qt3DLogic",
        "PyQt6.Qt3DAnimation",
    ):
        try:
            __import__(mod)
            print(f"  OK   import {mod}")
        except Exception as exc:  # noqa: BLE001 - report every failure, never abort
            ok = False
            print(f"  FAIL import {mod} -> {exc}")

    runtime = qVersion()
    try:
        qt3d_qt = version("PyQt6-3D-Qt6")
    except PackageNotFoundError:
        qt3d_qt = "?"
    print(f"Qt runtime (Qt6Core.dll): {runtime}   Qt3D wheels built for: {qt3d_qt}")
    if runtime != qt3d_qt:
        ok = False
        print("  FAIL Qt runtime micro != Qt3D wheel micro (issue #277 mismatch)")

    print("SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _install_excepthook() -> None:
    """Route unhandled exceptions to a dialog instead of aborting the process.

    Under PyQt6 an exception that escapes a Qt slot calls ``sys.excepthook``
    and then, with the DEFAULT hook, aborts the process — silently killing the
    app and any unsaved plan. Issue #277 hit exactly this: an ``ImportError``
    from the lazily imported 3D view took the whole process down. Installing a
    custom hook suppresses the abort; we print the traceback (frozen builds
    still surface it in logs) and show a recoverable dialog so the user can
    save. The 3D-open path also catches its own ``ImportError`` for a clearer
    message; this is the broad backstop for everything else.
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
        traceback.print_exception(exc_type, exc_value, exc_tb)
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
    # Headless subsystem self-test (issue #277) — before any Qt UI is created.
    if "--selftest" in sys.argv:
        return _run_selftest()

    # Import here to avoid slow startup for --help, --version, etc.
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import get_settings
    from open_garden_planner.core.i18n import load_translator
    from open_garden_planner.ui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("Open Garden Planner")
    app.setOrganizationName("cofade")
    app.setOrganizationDomain("github.com/cofade")

    # Set application icon (appears in taskbar, window title bar, etc.)
    icon_path = get_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Apply saved preferences
    settings = get_settings()
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
