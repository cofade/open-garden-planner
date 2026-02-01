"""Main entry point for Open Garden Planner."""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file in project root
# Find the .env file relative to this source file
_src_dir = Path(__file__).parent.parent.parent  # Go up to project root
_env_file = _src_dir / ".env"
load_dotenv(_env_file)

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

    app = QApplication(sys.argv)
    app.setApplicationName("Open Garden Planner")
    app.setOrganizationName("cofade")
    app.setOrganizationDomain("github.com/cofade")

    # Set application icon (appears in taskbar, window title bar, etc.)
    icon_path = get_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = GardenPlannerApp()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
