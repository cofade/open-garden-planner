"""A9: the post-show refresh retains colors/title bars without a second restyle."""

from PyQt6.QtWidgets import QApplication, QWidget

from open_garden_planner.ui import theme


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
