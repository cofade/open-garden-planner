"""Filesystem path helpers for user-facing data.

User projects (`.ogp` files) and exports must never default into the install
directory: on Windows the installer wipes that directory on upgrade/uninstall,
which destroyed user data (issue #199). These helpers resolve a safe, writable
location under the OS Documents folder instead.
"""

from pathlib import Path

from PyQt6.QtCore import QStandardPaths

#: Sub-folder created under the user's Documents directory for OGP projects.
PROJECTS_FOLDER_NAME = "Open Garden Planner"


def get_documents_dir() -> Path:
    """Return the OS Documents directory, falling back to ``~/Documents``."""
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(docs) if docs else Path.home() / "Documents"


def get_projects_dir() -> Path:
    """Return the default directory for user ``.ogp`` projects.

    This is ``<Documents>/Open Garden Planner``. The directory is created if it
    does not yet exist so file dialogs always open in a valid location.
    """
    projects = get_documents_dir() / PROJECTS_FOLDER_NAME
    projects.mkdir(parents=True, exist_ok=True)
    return projects


def default_dialog_dir(current_file: Path | str | None = None) -> Path:
    """Resolve a safe directory for a save/open dialog to start in.

    Returns the folder of ``current_file`` when one is supplied and exists (so
    users stay where they last worked), otherwise ``get_projects_dir()``. This
    is the single chokepoint every file dialog must use — it never returns the
    process working directory, which for a packaged build is the install folder
    (issue #199).
    """
    if current_file is not None:
        parent = Path(current_file).parent
        if parent.is_dir():
            return parent
    return get_projects_dir()


def default_save_path(filename: str, current_file: Path | str | None = None) -> str:
    """Build a full default path (safe dir + ``filename``) for a save dialog."""
    return str(default_dialog_dir(current_file) / filename)
