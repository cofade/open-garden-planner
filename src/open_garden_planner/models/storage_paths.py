"""Qt-free per-user data location shared by model stores and services."""

from pathlib import Path


def get_app_data_dir() -> Path:
    """Get the application data directory for storing user data.

    Returns:
        Path to the application data directory
    """
    import sys

    if sys.platform == "win32":
        # Windows: %APPDATA%/OpenGardenPlanner
        import os

        app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        # macOS: ~/Library/Application Support/OpenGardenPlanner
        app_data = Path.home() / "Library" / "Application Support"
    else:
        # Linux/Unix: ~/.local/share/OpenGardenPlanner
        import os

        xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        app_data = Path(xdg_data)

    app_dir = app_data / "OpenGardenPlanner"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir
