"""Integration tests: file dialogs never default into the install dir (#199).

Users lost data because Open/Save-As dialogs opened in the process working
directory — the install folder for a packaged build — and the installer wipes
that folder on upgrade. These tests assert the dialogs now start in a safe
location: the open project's folder when one exists, else
``<Documents>/Open Garden Planner``.
"""

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog

from open_garden_planner.app import paths
from open_garden_planner.app.application import GardenPlannerApp


def _capture_dialog_dir(monkeypatch: object) -> dict[str, str]:
    """Patch both QFileDialog static helpers to record the start directory.

    Returns a dict that will hold ``{"dir": <3rd positional arg>}`` after a
    dialog is invoked. Both helpers return an empty selection so the handler
    short-circuits without touching the filesystem.
    """
    captured: dict[str, str] = {}

    def fake_save(_parent: object, _caption: str, directory: str, *_args: object) -> tuple[str, str]:
        captured["dir"] = directory
        return ("", "")

    def fake_open(_parent: object, _caption: str, directory: str, *_args: object) -> tuple[str, str]:
        captured["dir"] = directory
        return ("", "")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake_save)  # type: ignore[attr-defined]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_open)  # type: ignore[attr-defined]
    return captured


def test_save_as_defaults_to_projects_dir(qtbot: object, monkeypatch: object, tmp_path: Path) -> None:
    """With no project open, Save As starts in <Documents>/Open Garden Planner."""
    monkeypatch.setattr(paths, "get_documents_dir", lambda: tmp_path)  # type: ignore[attr-defined]
    captured = _capture_dialog_dir(monkeypatch)

    window = GardenPlannerApp()
    qtbot.addWidget(window)  # type: ignore[attr-defined]

    window._on_save_as()

    start_dir = Path(captured["dir"]).parent  # save dialog dir + filename
    assert start_dir == tmp_path / "Open Garden Planner"
    assert Path(captured["dir"]).name.endswith(".ogp")


def test_open_defaults_to_projects_dir(qtbot: object, monkeypatch: object, tmp_path: Path) -> None:
    """With no project open, Open starts in <Documents>/Open Garden Planner."""
    monkeypatch.setattr(paths, "get_documents_dir", lambda: tmp_path)  # type: ignore[attr-defined]
    captured = _capture_dialog_dir(monkeypatch)

    window = GardenPlannerApp()
    qtbot.addWidget(window)  # type: ignore[attr-defined]

    window._on_open_project()

    assert Path(captured["dir"]) == tmp_path / "Open Garden Planner"


def test_dialog_dir_follows_current_project(qtbot: object, monkeypatch: object, tmp_path: Path) -> None:
    """When a project is loaded, dialogs start in that project's folder."""
    captured = _capture_dialog_dir(monkeypatch)

    project_dir = tmp_path / "my garden"
    project_dir.mkdir()
    project_file = project_dir / "plan.ogp"
    project_file.write_text("{}", encoding="utf-8")

    window = GardenPlannerApp()
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window._project_manager._current_file = project_file

    window._on_save_as()

    assert Path(captured["dir"]).parent == project_dir


def test_simple_exports_default_to_projects_dir(
    qtbot: object, monkeypatch: object, tmp_path: Path
) -> None:
    """The export handlers without a pre-dialog never default to the install dir.

    SVG / CSV / DXF go straight to the save dialog, so they prove the export
    code paths route through the safe-dir chokepoint. (PNG/PDF gate behind their
    own option dialogs and are covered by the chokepoint unit tests instead.)
    """
    monkeypatch.setattr(paths, "get_documents_dir", lambda: tmp_path)  # type: ignore[attr-defined]
    captured = _capture_dialog_dir(monkeypatch)

    window = GardenPlannerApp()
    qtbot.addWidget(window)  # type: ignore[attr-defined]

    safe = tmp_path / "Open Garden Planner"
    for handler in (window._on_export_svg, window._on_export_plant_csv, window._on_export_dxf):
        captured.clear()
        handler()
        assert Path(captured["dir"]).parent == safe, handler.__name__


def test_gated_exports_default_to_projects_dir(
    qtbot: object, monkeypatch: object, tmp_path: Path
) -> None:
    """PNG and PDF export (gated behind option dialogs) also use the safe dir.

    These accept-then-save handlers don't go straight to the save dialog, so
    cover them explicitly by auto-accepting the option dialog.
    """
    from open_garden_planner.ui.dialogs.export_dialog import ExportPngDialog
    from open_garden_planner.ui.dialogs.pdf_report_dialog import PdfReportDialog

    monkeypatch.setattr(paths, "get_documents_dir", lambda: tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        ExportPngDialog, "exec", lambda _self: ExportPngDialog.DialogCode.Accepted
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        PdfReportDialog, "exec", lambda _self: PdfReportDialog.DialogCode.Accepted
    )
    captured = _capture_dialog_dir(monkeypatch)

    window = GardenPlannerApp()
    qtbot.addWidget(window)  # type: ignore[attr-defined]

    safe = tmp_path / "Open Garden Planner"
    for handler in (window._on_export_png, window._on_export_pdf_report):
        captured.clear()
        handler()
        assert Path(captured["dir"]).parent == safe, handler.__name__


def test_season_manager_new_ogp_defaults_to_projects_dir(
    qtbot: object, monkeypatch: object, tmp_path: Path
) -> None:
    """A new season .ogp with no saved project defaults to the projects dir, not CWD.

    This is the exact data-loss vector of #199 reproduced in a standalone dialog.
    """
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.ui.dialogs.season_manager_dialog import SeasonManagerDialog

    monkeypatch.setattr(paths, "get_documents_dir", lambda: tmp_path)  # type: ignore[attr-defined]
    captured = _capture_dialog_dir(monkeypatch)

    pm = ProjectManager()  # fresh manager → no current_file
    dialog = SeasonManagerDialog(pm)
    qtbot.addWidget(dialog)  # type: ignore[attr-defined]

    dialog._on_create_season()

    assert Path(captured["dir"]).parent == tmp_path / "Open Garden Planner"
