"""#858: on a narrow window the status message keeps its room."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.app.application import GardenPlannerApp


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "open_garden_planner.services.example_library.user_templates_dir", lambda: tmp_path
    )
    win = GardenPlannerApp()
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    qtbot.addWidget(win)
    return win


def _settle() -> None:
    QApplication.processEvents()
    QApplication.processEvents()


def test_optional_status_segments_step_aside_on_a_narrow_window(window) -> None:
    window.resize(1280, 800)
    window.show()
    _settle()
    assert window.selection_label.isHidden()
    assert window.tool_label.isHidden()
    assert window.season_label.isHidden()
    assert window.location_label.isVisible()

    window.resize(1600, 900)
    _settle()
    assert window.selection_label.isVisible()
    assert window.tool_label.isVisible()
    assert window.season_label.isVisible()
    assert window.location_label.isVisible()


def test_the_opened_message_names_the_file_not_its_whole_path(window, tmp_path: Path) -> None:
    target = tmp_path / "family-garden.ogp"
    window._save_to_file(target)
    window._load_project_file(str(target))
    message = window.statusBar().currentMessage()
    assert message == "Opened: family-garden.ogp"
    assert str(tmp_path) not in message
