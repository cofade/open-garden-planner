"""Allow running the package with python -m open_garden_planner."""

import sys

# Windows-specific taskbar icon grouping — MUST be set before any GUI or Qt imports
if sys.platform == "win32" and "--selftest-supervisor" not in sys.argv:
    try:
        import ctypes

        myappid = "cofade.opengardenplanner.app"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except (AttributeError, ImportError):
        pass

from open_garden_planner.main import main

if __name__ == "__main__":
    sys.exit(main())
