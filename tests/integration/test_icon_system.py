"""End-to-end integration tests for the themed icon system (#279, ADR-039).

§8.10 policy: prove the whole pipeline in one place — every shipped icon
renders visibly on BOTH themes through the central provider, the real app's
toolbars and menus carry provider icons, a live theme switch re-tints them,
and the text fallback for unknown icon names still works.
"""

# ruff: noqa: ARG001, ARG002, ARG005

import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QMessageBox

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui import icons
from open_garden_planner.ui.theme import ThemeMode, apply_theme
from open_garden_planner.ui.widgets.toolbar import MainToolbar


def _make_app(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    # A dirty project would pop a close prompt and block headless teardown.
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    # The app arms a 500 ms QTimer.singleShot(_startup_sequence) that opens the
    # MODAL Welcome dialog. Headless, its exec() blocks pytest-qt's event
    # processing forever once a test keeps the app alive past the timer — which
    # these theme-switch tests do (pixel scans + full restyles). See §11.4.
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda self: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


def _image(pixmap: QPixmap) -> QImage:
    return pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _visible(pixmap: QPixmap) -> bool:
    image = _image(pixmap)
    return any(
        image.pixelColor(x, y).alpha() > 0
        for x in range(image.width())
        for y in range(image.height())
    )


class TestEveryIconRendersOnBothThemes:
    @pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
    def test_all_registered_icons_render(self, qtbot, mode) -> None:
        app = QApplication.instance()
        apply_theme(app, mode)
        try:
            names = icons.available_icons()
            assert len(names) >= 70
            for name in names:
                icon = icons.get_icon(name)
                assert icon is not None, name
                assert _visible(icon.pixmap(QSize(24, 24))), f"{name} paints nothing"
        finally:
            apply_theme(app, ThemeMode.LIGHT)


class TestAppWiring:
    def test_toolbars_and_menus_carry_icons(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)

        for tool_type, button in win.main_toolbar._buttons.items():
            assert not button.icon().isNull(), tool_type

        assert win.constraint_toolbar._icon_buttons, "constraint buttons tracked"
        for button, icon_name in win.constraint_toolbar._icon_buttons:
            assert not button.icon().isNull(), icon_name

        assert win.category_toolbar._category_buttons
        for button in win.category_toolbar._category_buttons:
            assert not button.icon().isNull()

        # Menu actions tracked by _set_action_icon all carry an icon.
        assert len(win._icon_actions) >= 20
        for action, icon_name in win._icon_actions:
            assert not action.icon().isNull(), icon_name

    def test_live_theme_switch_retints_toolbar(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        app = QApplication.instance()
        apply_theme(app, ThemeMode.LIGHT)
        try:
            button = next(iter(win.main_toolbar._buttons.values()))
            light_image = _image(button.icon().pixmap(QSize(24, 24)))

            apply_theme(app, ThemeMode.DARK)
            dark_image = _image(button.icon().pixmap(QSize(24, 24)))
            # The refresh walk re-set the icon; dark ink differs from light.
            assert light_image != dark_image
        finally:
            apply_theme(app, ThemeMode.LIGHT)

    def test_unknown_icon_name_falls_back_to_text(self, qtbot) -> None:
        toolbar = MainToolbar()
        qtbot.addWidget(toolbar)
        toolbar._add_tool_button(
            ToolType.SELECT, "definitely_not_an_icon", "Fallback", "tooltip", ""
        )
        button = toolbar._buttons[ToolType.SELECT]
        assert button.icon().isNull()
        assert button.text() == "Fallback"
