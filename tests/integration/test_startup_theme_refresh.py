"""A9: the post-show refresh retains colors/title bars without a second restyle."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QWidget

from open_garden_planner.ui import theme
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView


def test_system_theme_follows_live_scheme_and_explicit_theme_stays_pinned(
    qtbot, qapp, monkeypatch
):
    scheme = Qt.ColorScheme.Light
    monkeypatch.setattr(theme, "_system_color_scheme", lambda: scheme)
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)
    hints = QGuiApplication.styleHints()

    try:
        theme.apply_theme(qapp, theme.ThemeMode.SYSTEM)
        light_surround = scene.OUTSIDE_COLOR.name()
        scheme = Qt.ColorScheme.Dark
        hints.colorSchemeChanged.emit(scheme)
        QApplication.processEvents()
        assert theme.is_dark_theme()
        assert scene.OUTSIDE_COLOR.name() == theme.ThemeColors.DARK["canvas_outside"]
        assert scene.OUTSIDE_COLOR.name() != light_surround
        assert scene.CANVAS_COLOR.name() == theme.ThemeColors.LIGHT["canvas_background"]

        scheme = Qt.ColorScheme.Light
        hints.colorSchemeChanged.emit(scheme)
        QApplication.processEvents()
        assert not theme.is_dark_theme()
        assert scene.OUTSIDE_COLOR.name() == light_surround

        theme.apply_theme(qapp, theme.ThemeMode.LIGHT)
        scheme = Qt.ColorScheme.Dark
        hints.colorSchemeChanged.emit(scheme)
        QApplication.processEvents()
        assert not theme.is_dark_theme()
    finally:
        theme.apply_theme(qapp, theme.ThemeMode.LIGHT)


def test_new_windows_get_palette_without_reapplying_stylesheet(qtbot, monkeypatch):
    app = QApplication.instance()
    writes = []
    original = app.setStyleSheet
    def stylesheet(text):
        writes.append(text)
        original(text)
    monkeypatch.setattr(app, "setStyleSheet", stylesheet)
    theme.apply_theme(app, theme.ThemeMode.DARK)
    seen, frames = [], []
    class Window(QWidget):
        def apply_theme_colors(self, colors):
            seen.append(colors)
    window = Window()
    qtbot.addWidget(window)
    window.show()
    monkeypatch.setattr(theme, "_set_windows_dark_titlebar",
                        lambda widget, dark: frames.append((widget, dark)))
    theme.refresh_window_theme(app, theme.ThemeMode.DARK)
    assert len(writes) == 1
    assert seen == [theme.ThemeColors.DARK]
    assert (window, True) in frames
    theme.apply_theme(app, theme.ThemeMode.LIGHT)
    assert len(writes) == 2 and seen[-1] is theme.ThemeColors.LIGHT
