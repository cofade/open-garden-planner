"""Preferences remains editable at laptop heights and with larger fonts."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QLineEdit, QPushButton, QScrollArea

from open_garden_planner.app.settings import get_settings
from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog
from open_garden_planner.ui.theme import ThemeMode, generate_stylesheet


@pytest.mark.parametrize("height", [400, 800])
@pytest.mark.parametrize("font_size", [10, 14])
def test_preferences_controls_scroll_without_compression(qtbot, height, font_size) -> None:
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.setStyleSheet(generate_stylesheet(ThemeMode.DARK))
    font = dialog.font()
    font.setPointSize(font_size)
    dialog.setFont(font)
    dialog.resize(550, height)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.activateWindow()
    qtbot.waitUntil(dialog.isActiveWindow)

    assert dialog.height() == height
    controls = (
        dialog.findChildren(QLineEdit)
        + dialog.findChildren(QPushButton)
        + dialog.findChildren(QComboBox)
    )
    for control in controls:
        if control.isVisible():
            assert control.height() >= control.minimumSizeHint().height()

    scroll = dialog.findChild(QScrollArea)
    assert scroll is not None
    assert scroll.verticalScrollBar().maximum() > 0
    save = next(b for b in dialog.findChildren(QPushButton) if b.text() == dialog.tr("Save"))
    cancel = next(b for b in dialog.findChildren(QPushButton) if b.text() == dialog.tr("Cancel"))
    for button in (save, cancel):
        assert not scroll.isAncestorOf(button)
        assert dialog.rect().contains(button.geometry())

    # Tab from the penultimate setting must bring the last setting into view.
    dialog._view3d_quality_combo.setFocus()
    qtbot.keyClick(dialog._view3d_quality_combo, Qt.Key.Key_Tab)
    last = dialog._view3d_reduced_motion_check
    assert last.hasFocus()
    assert scroll.viewport().rect().contains(last.mapTo(scroll.viewport(), last.rect().center()))
    original = last.isChecked()
    qtbot.keyClick(last, Qt.Key.Key_Space)
    qtbot.mouseClick(save, Qt.MouseButton.LeftButton)
    assert get_settings().view3d_reduced_motion == (not original)

    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    reopened.show()
    assert reopened._view3d_reduced_motion_check.isChecked() == (not original)
    reopened._view3d_reduced_motion_check.setChecked(original)
    cancel = next(b for b in reopened.findChildren(QPushButton) if b.text() == reopened.tr("Cancel"))
    qtbot.mouseClick(cancel, Qt.MouseButton.LeftButton)
    assert get_settings().view3d_reduced_motion == (not original)
