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


def main() -> int:
    """Run the Open Garden Planner application."""
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
