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
        # 20+ after #279; 80+ after #310 (every File/Edit/View/Plants/Garden/Help
        # action, the View submenus, per-format Export glyphs, Align/Distribute).
        assert len(win._icon_actions) >= 80
        for action, icon_name in win._icon_actions:
            assert not action.icon().isNull(), icon_name

        # #310: EVERY menu action carries an icon — recursively through submenus —
        # except the exclusive-choice radio groups (Theme, Language, Auto-Save
        # intervals) and the dynamic recent-files list, whose entries are content.
        exempt_submenus = {"&Theme", "&Language", "Auto-&Save", "Open &Recent"}
        missing: list[str] = []

        def walk(menu, path: str) -> None:
            for action in menu.actions():
                if action.isSeparator():
                    continue
                label = f"{path} > {action.text()}"
                submenu = action.menu()
                if submenu is not None:
                    if action.icon().isNull():
                        missing.append(label + " (submenu)")
                    if action.text() not in exempt_submenus:
                        walk(submenu, label)
                elif action.icon().isNull():
                    missing.append(label)

        for top in win.menuBar().actions():
            walk(top.menu(), top.text())
        # the Enable Auto-Save toggle inside the exempt submenu is a toggle, not a radio
        assert not win._autosave_action.icon().isNull()
        assert missing == [], missing

        # View menu is regrouped (#310): Snapping / Overlays / Sun & 3D submenus,
        # Theme + Language still top-level, the toggle attributes unchanged.
        view_menu = next(a.menu() for a in win.menuBar().actions() if a.text() == "&View")
        submenu_titles = [a.text() for a in view_menu.actions() if a.menu() is not None]
        assert submenu_titles == ["&Snapping", "&Overlays", "S&un && 3D", "&Theme", "&Language"], submenu_titles
        snap_menu = next(a.menu() for a in view_menu.actions() if a.text() == "&Snapping")
        assert win.grid_action in snap_menu.actions() and win._dynamic_input_action in snap_menu.actions()
        overlays = next(a.menu() for a in view_menu.actions() if a.text() == "&Overlays")
        assert win._minimap_action in overlays.actions() and win._labels_action in overlays.actions()
        sun_menu = next(a.menu() for a in view_menu.actions() if a.text() == "S&un && 3D")
        assert win._shadows_action in sun_menu.actions() and win._view3d_action in sun_menu.actions()
        # Fullscreen Preview stays top-level (the "Panels" slot)
        assert win._preview_action in view_menu.actions()

        # Status bar: every segment has a themed pixmap label; dashboard tabs carry icons.
        assert len(win._icon_labels) >= 8
        for label, icon_name, _size in win._icon_labels:
            pixmap = label.pixmap()
            assert pixmap is not None and not pixmap.isNull(), icon_name
        for index in range(win._tab_widget.count()):
            assert not win._tab_widget.tabIcon(index).isNull(), win._tab_widget.tabText(index)

        # Tasks / Harvest tab shortcuts are contiguous Ctrl+4 / Ctrl+5 (#310).
        shortcuts = {a.shortcut().toString() for a in win.actions()}
        assert "Ctrl+4" in shortcuts and "Ctrl+5" in shortcuts and "Ctrl+6" not in shortcuts

    def test_live_theme_switch_retints_toolbar(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        app = QApplication.instance()
        apply_theme(app, ThemeMode.LIGHT)
        try:
            button = next(iter(win.main_toolbar._buttons.values()))
            light_image = _image(button.icon().pixmap(QSize(24, 24)))

            label, _name, _size = win._icon_labels[0]
            light_label = _image(label.pixmap())
            light_tab = _image(win._tab_widget.tabIcon(0).pixmap(QSize(24, 24)))

            apply_theme(app, ThemeMode.DARK)
            dark_image = _image(button.icon().pixmap(QSize(24, 24)))
            # The refresh walk re-set the icon; dark ink differs from light.
            assert light_image != dark_image
            # #310: status-bar pixmap labels and tab icons join the refresh path.
            assert _image(label.pixmap()) != light_label
            assert _image(win._tab_widget.tabIcon(0).pixmap(QSize(24, 24))) != light_tab
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
