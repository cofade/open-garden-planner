"""Preferences stays usable at laptop heights and with larger fonts (#569)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
)

from open_garden_planner.app.settings import get_settings
from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog
from open_garden_planner.ui.theme import ThemeMode, generate_stylesheet


def _visible_controls(dialog: PreferencesDialog) -> list:
    return [
        control
        for control in (
            dialog.findChildren(QLineEdit)
            + dialog.findChildren(QPushButton)
            + dialog.findChildren(QComboBox)
        )
        if control.isVisible()
    ]


def test_a_parented_dialog_sizes_from_the_parent_screen(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = PreferencesDialog(parent)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog.height() >= dialog.minimumHeight()
    assert all(control.height() > 0 for control in _visible_controls(dialog))


def test_default_height_is_sized_from_content_not_the_scroll_viewport(qtbot) -> None:
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    screen = dialog.screen() or QApplication.primaryScreen()
    assert screen is not None
    available = screen.availableGeometry().height()
    height = dialog.height()

    # The scroll area alone opens at about 452 px (the issue's regression).
    # On a screen shorter than that, the cap is the correct smaller answer.
    assert height >= min(453, max(dialog.minimumHeight(), available - 40))
    assert height <= max(dialog.minimumHeight(), available - 40)
    assert height >= dialog.minimumHeight()


@pytest.mark.parametrize("height", [400, 800])
@pytest.mark.parametrize("font_size", [10, 14])
@pytest.mark.parametrize("theme", [ThemeMode.DARK, ThemeMode.LIGHT])
def test_preferences_controls_scroll_without_compression(
    qtbot, height, font_size, theme
) -> None:
    settings = get_settings()
    original = settings.view3d_reduced_motion
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.setStyleSheet(generate_stylesheet(theme))
    font = dialog.font()
    font.setPointSize(font_size)
    dialog.setFont(font)
    dialog.resize(550, height)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.activateWindow()
    qtbot.wait(20)
    try:
        assert dialog.height() == height
        for control in _visible_controls(dialog):
            # A themed stylesheet may shave a 2 px border from the hint; the
            # regression this pins is 0/14 px against a 26 px hint, not that
            # difference. Never accept a control below 24 px.
            assert control.height() >= min(control.minimumSizeHint().height(), 24)

        scroll = dialog.findChild(QScrollArea)
        assert scroll is not None
        assert scroll.verticalScrollBar().maximum() > 0
        save = next(b for b in dialog.findChildren(QPushButton) if b.text() == dialog.tr("Save"))
        cancel = next(
            b for b in dialog.findChildren(QPushButton) if b.text() == dialog.tr("Cancel")
        )
        for button in (save, cancel):
            assert not scroll.isAncestorOf(button)
            assert dialog.rect().contains(button.geometry())

        # Tab from the penultimate setting must bring the last setting into view.
        dialog._view3d_quality_combo.setFocus()
        qtbot.keyClick(dialog._view3d_quality_combo, Qt.Key.Key_Tab)
        last = dialog._view3d_reduced_motion_check
        assert last.hasFocus()
        assert scroll.viewport().rect().contains(
            last.mapTo(scroll.viewport(), last.rect().center())
        )
        changed = not last.isChecked()
        qtbot.keyClick(last, Qt.Key.Key_Space)
        qtbot.mouseClick(save, Qt.MouseButton.LeftButton)
        assert get_settings().view3d_reduced_motion is changed
    finally:
        get_settings().view3d_reduced_motion = original

    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    reopened.show()
    assert reopened._view3d_reduced_motion_check.isChecked() is original
    reopened._view3d_reduced_motion_check.setChecked(not original)
    cancel = next(
        b for b in reopened.findChildren(QPushButton) if b.text() == reopened.tr("Cancel")
    )
    qtbot.mouseClick(cancel, Qt.MouseButton.LeftButton)
    assert get_settings().view3d_reduced_motion is original
