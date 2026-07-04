"""Unit tests for the Agent API export path resolution (US-D1.4).

``resolve_export_path`` picks a default location via the same ``app/paths.py``
chokepoint the GUI's export dialogs use when no explicit path is given, and
normalizes the suffix + validates the parent directory otherwise — mirrors
what a ``QFileDialog`` save dialog would allow, since no dialog is available
to an agent caller.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from open_garden_planner.agent_api.exports import resolve_export_path
from open_garden_planner.app import paths as paths_module
from open_garden_planner.core.project import ProjectManager


@pytest.fixture
def project_manager(qtbot: object) -> ProjectManager:  # noqa: ARG001
    return ProjectManager()


class TestResolveExportPathDefaults:
    def test_default_path_with_no_open_project(
        self, project_manager: ProjectManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(paths_module, "get_documents_dir", lambda: tmp_path)

        path = resolve_export_path(
            None,
            default_filename="Untitled.pdf",
            suffix=".pdf",
            project_manager=project_manager,
        )

        assert path == tmp_path / "Open Garden Planner" / "Untitled.pdf"

    def test_default_path_next_to_open_project(
        self, project_manager: ProjectManager, tmp_path: Path
    ) -> None:
        project_manager._current_file = tmp_path / "my_garden.ogp"

        path = resolve_export_path(
            None,
            default_filename="my_garden.pdf",
            suffix=".pdf",
            project_manager=project_manager,
        )

        assert path == tmp_path / "my_garden.pdf"


class TestResolveExportPathExplicit:
    def test_explicit_absolute_path_honored(
        self, project_manager: ProjectManager, tmp_path: Path
    ) -> None:
        requested = tmp_path / "custom.pdf"

        path = resolve_export_path(
            str(requested),
            default_filename="ignored.pdf",
            suffix=".pdf",
            project_manager=project_manager,
        )

        assert path == requested

    def test_suffix_forced_when_missing(
        self, project_manager: ProjectManager, tmp_path: Path
    ) -> None:
        path = resolve_export_path(
            str(tmp_path / "custom"),
            default_filename="ignored.dxf",
            suffix=".dxf",
            project_manager=project_manager,
        )

        assert path == tmp_path / "custom.dxf"

    def test_suffix_forced_when_wrong(
        self, project_manager: ProjectManager, tmp_path: Path
    ) -> None:
        path = resolve_export_path(
            str(tmp_path / "custom.txt"),
            default_filename="ignored.csv",
            suffix=".csv",
            project_manager=project_manager,
        )

        assert path == tmp_path / "custom.csv"

    def test_relative_path_resolved_against_default_dir(
        self, project_manager: ProjectManager, tmp_path: Path
    ) -> None:
        project_manager._current_file = tmp_path / "my_garden.ogp"
        (tmp_path / "reports").mkdir()

        path = resolve_export_path(
            "reports/out.pdf",
            default_filename="ignored.pdf",
            suffix=".pdf",
            project_manager=project_manager,
        )

        assert path == tmp_path / "reports" / "out.pdf"

    def test_expanduser_applied(
        self, project_manager: ProjectManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        path = resolve_export_path(
            "~/out.pdf",
            default_filename="ignored.pdf",
            suffix=".pdf",
            project_manager=project_manager,
        )

        assert path == tmp_path / "out.pdf"

    def test_missing_parent_directory_raises(
        self, project_manager: ProjectManager, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            resolve_export_path(
                str(tmp_path / "no_such_folder" / "out.pdf"),
                default_filename="ignored.pdf",
                suffix=".pdf",
                project_manager=project_manager,
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
