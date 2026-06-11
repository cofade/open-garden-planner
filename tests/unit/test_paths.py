"""Unit tests for user-data path helpers (issue #199)."""

from pathlib import Path

from PyQt6.QtCore import QStandardPaths

from open_garden_planner.app import paths


def test_get_projects_dir_under_documents(monkeypatch: object, tmp_path: Path) -> None:
    """Projects dir is the OGP sub-folder under the OS Documents location."""
    monkeypatch.setattr(  # type: ignore[attr-defined]
        QStandardPaths, "writableLocation", lambda _loc: str(tmp_path)
    )

    projects = paths.get_projects_dir()

    assert projects == tmp_path / "Open Garden Planner"
    assert projects.name == "Open Garden Planner"


def test_get_projects_dir_is_created(monkeypatch: object, tmp_path: Path) -> None:
    """The directory is created on first use so dialogs have a valid target."""
    monkeypatch.setattr(  # type: ignore[attr-defined]
        QStandardPaths, "writableLocation", lambda _loc: str(tmp_path)
    )

    projects = paths.get_projects_dir()

    assert projects.is_dir()


def test_get_projects_dir_falls_back_to_home(monkeypatch: object) -> None:
    """When the OS reports no Documents location, fall back to ~/Documents."""
    monkeypatch.setattr(  # type: ignore[attr-defined]
        QStandardPaths, "writableLocation", lambda _loc: ""
    )

    projects = paths.get_projects_dir()

    assert projects == Path.home() / "Documents" / "Open Garden Planner"


def test_default_dialog_dir_without_project(monkeypatch: object, tmp_path: Path) -> None:
    """With no open project, the chokepoint resolves to the projects dir."""
    monkeypatch.setattr(paths, "get_documents_dir", lambda: tmp_path)  # type: ignore[attr-defined]

    assert paths.default_dialog_dir(None) == tmp_path / "Open Garden Planner"


def test_default_dialog_dir_follows_current_file(tmp_path: Path) -> None:
    """With an open project, the chokepoint anchors on that file's folder."""
    project = tmp_path / "garden" / "plan.ogp"
    project.parent.mkdir()
    project.write_text("{}", encoding="utf-8")

    assert paths.default_dialog_dir(project) == tmp_path / "garden"


def test_default_dialog_dir_ignores_missing_parent(monkeypatch: object, tmp_path: Path) -> None:
    """A current_file whose folder no longer exists falls back to projects dir."""
    monkeypatch.setattr(paths, "get_documents_dir", lambda: tmp_path)  # type: ignore[attr-defined]
    stale = tmp_path / "deleted_dir" / "plan.ogp"  # parent never created

    assert paths.default_dialog_dir(stale) == tmp_path / "Open Garden Planner"


def test_default_save_path_joins_filename(monkeypatch: object, tmp_path: Path) -> None:
    """default_save_path appends the filename to the resolved safe directory."""
    monkeypatch.setattr(paths, "get_documents_dir", lambda: tmp_path)  # type: ignore[attr-defined]

    result = Path(paths.default_save_path("garden_2026.ogp"))

    assert result == tmp_path / "Open Garden Planner" / "garden_2026.ogp"
