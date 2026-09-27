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

from open_garden_planner.agent_api.exports import (
    resolve_export_path,
    validate_new_plan,
    validate_open_plan,
)
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

    def test_default_filename_not_needed_when_path_given(
        self, project_manager: ProjectManager, tmp_path: Path
    ) -> None:
        """default_filename is only consulted when requested is None — omitting
        it when an explicit path is given must not raise (save_plan_file's
        explicit-path branch relies on this)."""
        requested = tmp_path / "explicit.ogp"

        path = resolve_export_path(str(requested), suffix=".ogp", project_manager=project_manager)

        assert path == requested

    def test_missing_default_filename_raises_when_path_omitted(
        self, project_manager: ProjectManager
    ) -> None:
        with pytest.raises(ValueError, match="default_filename is required"):
            resolve_export_path(None, suffix=".pdf", project_manager=project_manager)


class TestValidateNewPlan:
    """``new_plan``'s canvas resolution (issue #365). The new-document work
    itself is the GUI's own path — only the argument checking is here."""

    def test_omitting_both_keeps_the_current_canvas(self) -> None:
        assert validate_new_plan(None, None, 800.0, 600.0) == (800.0, 600.0)

    def test_omitting_one_keeps_that_dimension(self) -> None:
        assert validate_new_plan(1200.0, None, 800.0, 600.0) == (1200.0, 600.0)
        assert validate_new_plan(None, 900.0, 800.0, 600.0) == (800.0, 900.0)

    def test_explicit_values_win(self) -> None:
        assert validate_new_plan(1000.0, 500.0, 800.0, 600.0) == (1000.0, 500.0)

    @pytest.mark.parametrize(
        ("width", "height"),
        [
            (0.0, 500.0),
            (-100.0, 500.0),
            (49.0, 500.0),
            (500.0, 0.0),
            (500.0, 1e9),
            (float("nan"), 500.0),
            (500.0, float("inf")),
        ],
    )
    def test_out_of_range_or_non_finite_refuses(self, width: float, height: float) -> None:
        """Refused, never clamped: a clamped canvas is a silently different
        plan than the agent asked for."""
        with pytest.raises(ValueError):
            validate_new_plan(width, height, 800.0, 600.0)

    def test_the_error_names_the_offending_dimension(self) -> None:
        with pytest.raises(ValueError, match="height_cm"):
            validate_new_plan(800.0, 0.0, 800.0, 600.0)


class TestValidateOpenPlan:
    def test_accepts_an_existing_ogp(self, tmp_path: Path) -> None:
        plan = tmp_path / "my-garden.ogp"
        plan.write_text("{}", encoding="utf-8")
        assert validate_open_plan(str(plan)) == plan

    def test_relative_path_is_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        plan = tmp_path / "x.ogp"
        plan.write_text("{}", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert validate_open_plan("x.ogp") == plan

    def test_empty_path_refuses(self) -> None:
        with pytest.raises(ValueError, match="required"):
            validate_open_plan("   ")

    def test_non_ogp_suffix_refuses(self, tmp_path: Path) -> None:
        other = tmp_path / "plan.txt"
        other.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match=r"\.ogp"):
            validate_open_plan(str(other))

    def test_missing_file_refuses(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No such plan file"):
            validate_open_plan(str(tmp_path / "nope.ogp"))

    def test_a_directory_refuses(self, tmp_path: Path) -> None:
        # A directory named `x.ogp` passes exists() and is_file() is the
        # only thing that catches it.
        (tmp_path / "weird.ogp").mkdir()
        with pytest.raises(ValueError, match="Not a file"):
            validate_open_plan(str(tmp_path / "weird.ogp"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
