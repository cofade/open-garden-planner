"""Preferences stays usable at laptop heights and with larger fonts (#569)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QPushButton,
    QWidget,
)

from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES
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


def test_preferences_are_split_into_structured_tabs(qtbot) -> None:
    """#986: the one long form is a small set of named, single-purpose tabs."""
    from PyQt6.QtWidgets import QGroupBox

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    titles = [dialog._tabs.tabText(index) for index in range(dialog._tabs.count())]
    assert titles == [
        dialog.tr("General"),
        dialog.tr("Weather"),
        dialog.tr("Online services"),
        dialog.tr("Agent API"),
        dialog.tr("3D View"),
    ]
    homes: dict[str, int] = {}
    for index in range(dialog._tabs.count()):
        page = dialog._tabs.widget(index)
        assert page is not None
        for group in page.findChildren(QGroupBox):
            homes[group.title()] = index
    assert homes[dialog.tr("Units")] == 0
    assert homes[dialog.tr("Canvas")] == 0
    assert homes[dialog.tr("Weather")] == 1
    assert homes[dialog.tr("Google Maps")] == 2
    assert homes[dialog.tr("Agent API")] == 3
    assert homes[dialog.tr("3D View")] == 4


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


@pytest.mark.parametrize("theme", [ThemeMode.LIGHT, ThemeMode.DARK])
@pytest.mark.parametrize("lang", list(SUPPORTED_LANGUAGES))
def test_tab_bar_fits_all_five_tabs_without_scroll_arrows_on_open(
    qtbot, theme, lang
) -> None:
    """#986: initial width sizes from the styled tab bar so all 5 tabs fit without
    horizontal scroll arrows in every shipped locale. A narrow screen skips only
    the locale it cannot fit, not the rest."""
    from PyQt6.QtWidgets import QToolButton

    from open_garden_planner.core.i18n import load_translator

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    prev_sheet = app.styleSheet()
    app.setStyleSheet(generate_stylesheet(theme))
    try:
        load_translator(app, lang)
        dialog = PreferencesDialog()
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        tab_bar = dialog._tabs.tabBar()
        assert tab_bar is not None
        screen = dialog.screen() or app.primaryScreen()
        assert screen is not None
        max_w = max(dialog.minimumWidth(), screen.availableGeometry().width() - 40)
        if tab_bar.sizeHint().width() + 48 > max_w:
            pytest.skip(
                f"{theme.value}/{lang}: screen {max_w}px cannot fit the "
                f"uncapped tab bar {tab_bar.sizeHint().width()}px"
            )
        assert tab_bar.sizeHint().width() <= dialog._tabs.width(), (
            f"{theme.value}/{lang}: tab bar {tab_bar.sizeHint().width()}px "
            f"overflows tabs widget {dialog._tabs.width()}px"
        )
        visible_arrows = [
            b for b in tab_bar.findChildren(QToolButton) if b.isVisible()
        ]
        assert visible_arrows == [], (
            f"{theme.value}/{lang}: unexpected tab bar scroll arrows"
        )
        dialog.close()
    finally:
        load_translator(app, "en")
        app.setStyleSheet(prev_sheet)


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
        # #986: every tab is checked, not only the first one. A control must
        # never be squeezed below its hint on any page.
        for index in range(dialog._tabs.count()):
            dialog._tabs.setCurrentIndex(index)
            qtbot.wait(1)
            for control in _visible_controls(dialog):
                # A themed stylesheet may shave a 2 px border from the hint; the
                # regression this pins is 0/14 px against a 26 px hint, not that
                # difference. Never accept a control below 24 px.
                assert control.height() >= min(control.minimumSizeHint().height(), 24)

        # The longest tab still scrolls rather than compressing its groups.
        scrolls = [
            dialog._tabs.widget(index) for index in range(dialog._tabs.count())
        ]
        if height < 600:
            # A laptop-height window must scroll rather than compress. At 800 px
            # the #986 tabs fit the whole form, which is the point of the split.
            assert any(scroll.verticalScrollBar().maximum() > 0 for scroll in scrolls)
        save = next(b for b in dialog.findChildren(QPushButton) if b.text() == dialog.tr("Save"))
        cancel = next(
            b for b in dialog.findChildren(QPushButton) if b.text() == dialog.tr("Cancel")
        )
        for scroll in scrolls:
            for button in (save, cancel):
                assert not scroll.isAncestorOf(button)
                assert dialog.rect().contains(button.geometry())

        # Tab from the penultimate setting must bring the last setting into view
        # (the Sky combo since Phase 17 L7, #391; the quality combo before it).
        dialog._tabs.setCurrentIndex(4)  # 3D View
        qtbot.wait(1)
        scroll = dialog._tabs.currentWidget()
        dialog._view3d_sky_combo.setFocus()
        qtbot.keyClick(dialog._view3d_sky_combo, Qt.Key.Key_Tab)
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
