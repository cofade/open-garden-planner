"""Tests for application icons and multi-resolution Windows taskbar support."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QApplication
from scripts.generate_app_icons import STANDARD_SIZES, check_icons

from open_garden_planner.main import get_app_icon, get_icon_path


def test_app_icon_conformance() -> None:
    """Ensure all multi-resolution .ico files exist and have standard sizes."""
    assert check_icons(), "Icon files must exist with all standard resolutions"


def test_get_icon_path_backward_compat() -> None:
    """Ensure get_icon_path() continues to return the master PNG logo."""
    p = get_icon_path()
    assert isinstance(p, Path)
    assert p.is_file()
    assert p.suffix.lower() == ".png"
    assert "OGP_logo.png" in p.name


def test_get_app_icon_resolutions(qtbot) -> None:  # noqa: ARG001
    """Ensure get_app_icon() provides multi-resolution frames."""
    _app = QApplication.instance() or QApplication([])
    icon = get_app_icon()
    assert not icon.isNull()
    available = {(s.width(), s.height()) for s in icon.availableSizes()}
    for standard in STANDARD_SIZES:
        assert standard in available, f"Missing standard resolution {standard}"


def test_main_window_has_window_icon(qtbot) -> None:
    """Ensure GardenPlannerApp main window has its window icon set explicitly."""
    from open_garden_planner.app.application import GardenPlannerApp

    app = QApplication.instance() or QApplication([])
    app_icon = get_app_icon()
    app.setWindowIcon(app_icon)

    window = GardenPlannerApp()
    qtbot.addWidget(window)
    assert not window.windowIcon().isNull(), "GardenPlannerApp should have a window icon"
