"""Theme management for the application.

Provides light and dark color schemes with comprehensive styling.
"""

import os
import tempfile
from enum import Enum

from PyQt6.QtWidgets import QApplication


class ThemeMode(Enum):
    """Available theme modes."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class ThemeColors:
    """Color definitions for light and dark themes."""

    # Light theme colors - branded garden green with cream accents
    LIGHT = {
        # Base colors
        "background": "#fafaf5",
        "background_alt": "#f0efe8",
        "surface": "#f5f4ed",
        "surface_alt": "#dddcce",
        # Text colors
        "text_primary": "#1b2e1b",
        "text_secondary": "#5a6b5a",
        "text_disabled": "#9aa39a",
        # Border colors
        "border": "#c8d1c0",
        "border_focus": "#4a9e4a",
        # Canvas colors
        "canvas_background": "#f5f5dc",
        "canvas_outside": "#707070",
        "grid_line": "#c8c8a8",
        "grid_line_major": "#b0b090",
        "canvas_border": "#5a6b5a",
        "scale_bar_fg": "#283828",
        "scale_bar_outline": "#ffffff",
        # Accent colors - garden green
        "accent": "#3d8b37",
        "accent_hover": "#2e7d32",
        "accent_pressed": "#1b5e20",
        "accent_text": "#ffffff",
        # Status colors
        "success": "#43a047",
        "warning": "#ef6c00",
        "error": "#d32f2f",
        "info": "#2e7d32",
        # UI element colors
        "button": "#eeeddf",
        "button_hover": "#dddcce",
        "button_pressed": "#c8d1c0",
        "input": "#ffffff",
        "input_disabled": "#f0efe8",
        # Selection colors
        "selection": "#c8e6c9",
        "selection_inactive": "#dddcce",
    }

    # Dark theme colors - slate with soft sage-green accents
    DARK = {
        # Base colors
        "background": "#1a1e1a",
        "background_alt": "#22271f",
        "surface": "#272d25",
        "surface_alt": "#353d32",
        # Text colors
        "text_primary": "#dce0d8",
        "text_secondary": "#a3ab9d",
        "text_disabled": "#606860",
        # Border colors
        "border": "#3a4238",
        "border_focus": "#66bb6a",
        # Canvas colors - keep same as light theme so the garden plan
        # always looks bright and natural; only UI chrome goes dark
        "canvas_background": "#f5f5dc",
        "canvas_outside": "#707070",
        "grid_line": "#c8c8a8",
        "grid_line_major": "#b0b090",
        "canvas_border": "#5a6b5a",
        "scale_bar_fg": "#283828",
        "scale_bar_outline": "#ffffff",
        # Accent colors - softer green for dark mode
        "accent": "#66bb6a",
        "accent_hover": "#81c784",
        "accent_pressed": "#4caf50",
        "accent_text": "#1a1e1a",
        # Status colors
        "success": "#66bb6a",
        "warning": "#ffa726",
        "error": "#ef5350",
        "info": "#66bb6a",
        # UI element colors
        "button": "#353d32",
        "button_hover": "#3e4a3a",
        "button_pressed": "#4a5648",
        "input": "#272d25",
        "input_disabled": "#22271f",
        # Selection colors
        "selection": "#2e5630",
        "selection_inactive": "#353d32",
    }

    @classmethod
    def get_colors(cls, mode: ThemeMode) -> dict[str, str]:
        """Get color palette for the specified theme mode.

        Args:
            mode: Theme mode (light, dark, or system)

        Returns:
            Dictionary mapping color names to hex values
        """
        if mode == ThemeMode.SYSTEM:
            # Detect system theme preference
            mode = cls.detect_system_theme()

        return cls.DARK if mode == ThemeMode.DARK else cls.LIGHT

    @staticmethod
    def detect_system_theme() -> ThemeMode:
        """Detect the system's preferred color scheme.

        Returns:
            ThemeMode.DARK if system prefers dark, ThemeMode.LIGHT otherwise
        """
        # Qt 6.5+ has better dark mode detection, but for compatibility
        # we'll check the application's palette
        palette = QApplication.palette()
        window_color = palette.color(palette.ColorRole.Window)

        # If the background is dark (low luminance), use dark theme
        luminance = (0.299 * window_color.red() +
                     0.587 * window_color.green() +
                     0.114 * window_color.blue()) / 255.0

        return ThemeMode.DARK if luminance < 0.5 else ThemeMode.LIGHT


def generate_stylesheet(mode: ThemeMode) -> str:
    """Generate complete application stylesheet for the given theme mode.

    Args:
        mode: Theme mode (light, dark, or system)

    Returns:
        Complete CSS stylesheet as string
    """
    colors = ThemeColors.get_colors(mode)

    # Write tiny SVG arrow files to temp dir — Qt QSS image: url() requires
    # file paths; inline data URIs are not supported by Qt's QSS image loader.
    _c = colors["text_secondary"]
    _tmp = tempfile.gettempdir()
    _key = _c.lstrip("#")
    _up_path = os.path.join(_tmp, f"ogp_arrow_up_{_key}.svg").replace("\\", "/")
    _dn_path = os.path.join(_tmp, f"ogp_arrow_dn_{_key}.svg").replace("\\", "/")
    with open(_up_path, "w", encoding="utf-8") as _f:
        _f.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            f'<text x="5" y="9" text-anchor="middle" font-size="11" fill="{_c}">▲</text>'
            f"</svg>"
        )
    with open(_dn_path, "w", encoding="utf-8") as _f:
        _f.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            f'<text x="5" y="9" text-anchor="middle" font-size="11" fill="{_c}">▼</text>'
            f"</svg>"
        )

    return f"""
    /* Global application styles */
    QMainWindow, QDialog, QWidget {{
        background-color: {colors['background']};
        color: {colors['text_primary']};
    }}

    /* Menu bar */
    QMenuBar {{
        background-color: {colors['background']};
        color: {colors['text_primary']};
        border-bottom: 1px solid {colors['border']};
    }}

    QMenuBar::item {{
        background-color: transparent;
        padding: 4px 8px;
    }}

    QMenuBar::item:selected {{
        background-color: {colors['button_hover']};
    }}

    QMenuBar::item:pressed {{
        background-color: {colors['button_pressed']};
    }}

    /* Menus */
    QMenu {{
        background-color: {colors['surface']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
    }}

    QMenu::item {{
        padding: 6px 24px;
    }}

    QMenu::item:selected {{
        background-color: {colors['accent']};
        color: {colors['accent_text']};
    }}

    QMenu::item:disabled {{
        color: {colors['text_disabled']};
    }}

    QMenu::separator {{
        height: 1px;
        background-color: {colors['border']};
        margin: 4px 0px;
    }}

    /* Status bar */
    QStatusBar {{
        background-color: {colors['surface']};
        color: {colors['text_primary']};
        border-top: 1px solid {colors['border']};
    }}

    QStatusBar QLabel {{
        background-color: transparent;
        padding: 2px 4px;
    }}

    /* Buttons */
    QPushButton {{
        background-color: {colors['button']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 4px;
        padding: 6px 12px;
        min-width: 80px;
    }}

    QPushButton:hover {{
        background-color: {colors['button_hover']};
        border-color: {colors['border_focus']};
    }}

    QPushButton:pressed {{
        background-color: {colors['button_pressed']};
    }}

    QPushButton:disabled {{
        background-color: {colors['input_disabled']};
        color: {colors['text_disabled']};
    }}

    /* Tool buttons */
    QToolButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 3px;
        padding: 4px;
    }}

    QToolButton:hover {{
        background-color: {colors['button_hover']};
        border-color: {colors['border']};
    }}

    QToolButton:pressed, QToolButton:checked {{
        background-color: {colors['button_pressed']};
        border-color: {colors['accent']};
    }}

    /* Text inputs */
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background-color: {colors['input']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 3px;
        padding: 4px;
        selection-background-color: {colors['selection']};
    }}

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border-color: {colors['border_focus']};
    }}

    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
        background-color: {colors['input_disabled']};
        color: {colors['text_disabled']};
    }}

    /* Spin boxes */
    QSpinBox, QDoubleSpinBox {{
        background-color: {colors['input']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 3px;
        padding: 4px 20px 4px 4px;
    }}

    QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {colors['border_focus']};
    }}

    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 16px;
        border-left: 1px solid {colors['border']};
        border-bottom: 1px solid {colors['border']};
        border-top-right-radius: 3px;
        background-color: {colors['button']};
    }}

    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
        background-color: {colors['button_hover']};
    }}

    QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed {{
        background-color: {colors['button_pressed']};
    }}

    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 16px;
        border-left: 1px solid {colors['border']};
        border-bottom-right-radius: 3px;
        background-color: {colors['button']};
    }}

    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
        background-color: {colors['button_hover']};
    }}

    QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
        background-color: {colors['button_pressed']};
    }}

    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url("{_up_path}");
        width: 10px;
        height: 10px;
    }}

    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url("{_dn_path}");
        width: 10px;
        height: 10px;
    }}

    /* Date edit */
    QDateEdit {{
        background-color: {colors['input']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 3px;
        padding: 4px;
    }}

    QDateEdit:focus {{
        border-color: {colors['border_focus']};
    }}

    QDateEdit::drop-down {{
        border-left: 1px solid {colors['border']};
    }}

    QDateEdit::down-arrow {{
        border-color: {colors['text_primary']};
    }}

    /* Calendar widget */
    QCalendarWidget {{
        background-color: {colors['surface']};
        color: {colors['text_primary']};
    }}

    QCalendarWidget QToolButton {{
        background-color: {colors['button']};
        color: {colors['text_primary']};
    }}

    QCalendarWidget QMenu {{
        background-color: {colors['surface']};
        color: {colors['text_primary']};
    }}

    QCalendarWidget QSpinBox {{
        background-color: {colors['input']};
        color: {colors['text_primary']};
    }}

    QCalendarWidget QAbstractItemView {{
        background-color: {colors['surface']};
        color: {colors['text_primary']};
        selection-background-color: {colors['selection']};
        selection-color: {colors['text_primary']};
    }}

    /* Combo boxes */
    QComboBox {{
        background-color: {colors['input']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 3px;
        padding: 4px;
    }}

    QComboBox:focus {{
        border-color: {colors['border_focus']};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {colors['surface']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        selection-background-color: {colors['selection']};
    }}

    /* Checkboxes and radio buttons */
    QCheckBox, QRadioButton {{
        color: {colors['text_primary']};
        spacing: 6px;
    }}

    QCheckBox:disabled, QRadioButton:disabled {{
        color: {colors['text_disabled']};
    }}

    /* List widgets */
    QListWidget {{
        background-color: {colors['input']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 3px;
    }}

    QListWidget::item {{
        padding: 4px;
    }}

    QListWidget::item:selected {{
        background-color: {colors['selection']};
    }}

    QListWidget::item:hover {{
        background-color: {colors['button_hover']};
    }}

    /* Table widgets */
    QTableWidget {{
        background-color: {colors['input']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        gridline-color: {colors['border']};
    }}

    QTableWidget::item:selected {{
        background-color: {colors['selection']};
    }}

    QHeaderView::section {{
        background-color: {colors['surface']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        padding: 4px;
    }}

    /* Scroll bars */
    QScrollBar:vertical {{
        background-color: {colors['background_alt']};
        width: 14px;
        border: none;
    }}

    QScrollBar::handle:vertical {{
        background-color: {colors['surface_alt']};
        min-height: 30px;
        border-radius: 7px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {colors['button_hover']};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: {colors['background_alt']};
        height: 14px;
        border: none;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {colors['surface_alt']};
        min-width: 30px;
        border-radius: 7px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background-color: {colors['button_hover']};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* Sliders */
    QSlider::groove:horizontal {{
        background-color: {colors['surface_alt']};
        height: 6px;
        border-radius: 3px;
    }}

    QSlider::handle:horizontal {{
        background-color: {colors['accent']};
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }}

    QSlider::handle:horizontal:hover {{
        background-color: {colors['accent_hover']};
    }}

    /* Tab widgets */
    QTabWidget::pane {{
        border: 1px solid {colors['border']};
        background-color: {colors['surface']};
    }}

    QTabBar::tab {{
        background-color: {colors['button']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        padding: 6px 12px;
        margin-right: 2px;
    }}

    QTabBar::tab:selected {{
        background-color: {colors['surface']};
        border-bottom-color: {colors['surface']};
    }}

    QTabBar::tab:hover {{
        background-color: {colors['button_hover']};
    }}

    /* Group boxes */
    QGroupBox {{
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 4px;
        background-color: {colors['background']};
        color: {colors['text_primary']};
    }}

    /* Form layouts - ensure labels are visible */
    QFormLayout QLabel {{
        color: {colors['text_primary']};
    }}

    /* Frames */
    QFrame[frameShape="4"], QFrame[frameShape="5"] {{
        border: 1px solid {colors['border']};
    }}

    /* Splitter */
    QSplitter::handle {{
        background-color: {colors['border']};
    }}

    QSplitter::handle:horizontal {{
        width: 1px;
    }}

    QSplitter::handle:vertical {{
        height: 1px;
    }}

    /* Progress bars */
    QProgressBar {{
        background-color: {colors['surface_alt']};
        border: 1px solid {colors['border']};
        border-radius: 3px;
        text-align: center;
    }}

    QProgressBar::chunk {{
        background-color: {colors['accent']};
        border-radius: 2px;
    }}

    /* Tooltips */
    QToolTip {{
        background-color: {colors['surface']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        padding: 4px;
    }}

    /* Labels */
    QLabel {{
        color: {colors['text_primary']};
        background-color: transparent;
    }}

    /* Secondary / hint text — activated by setProperty("secondary", True) or
       setProperty("hint", True).  Higher specificity than the plain QLabel rule
       above, so they reliably override palette(mid) which is near-invisible in
       dark themes. */
    QLabel[secondary="true"] {{
        color: {colors['text_secondary']};
    }}

    QLabel[hint="true"] {{
        color: {colors['text_secondary']};
        font-size: 11px;
    }}

    /* Scroll area */
    QScrollArea {{
        background-color: transparent;
        border: none;
    }}

    QScrollArea > QWidget > QWidget {{
        background-color: transparent;
    }}

    /* Graphics View (Canvas) */
    QGraphicsView {{
        background-color: {colors['canvas_outside']};
        border: 1px solid {colors['border']};
    }}

    /* Collapsible Panel Headers */
    CollapsiblePanel > QFrame {{
        background-color: {colors['surface']};
        border: 1px solid {colors['border']};
    }}

    CollapsiblePanel > QFrame:hover {{
        background-color: {colors['surface_alt']};
    }}

    CollapsiblePanel QLabel {{
        color: {colors['text_primary']};
    }}

    /* Drawing Tools Panel - Category Labels */
    DrawingToolsPanel QLabel {{
        color: {colors['text_primary']};
        font-weight: bold;
        border-bottom: 1px solid {colors['border']};
    }}

    /* Drawing Tools Panel - Tool Buttons */
    DrawingToolsPanel QToolButton {{
        border: 1px solid {colors['border']};
        background-color: {colors['button']};
    }}

    DrawingToolsPanel QToolButton:hover {{
        background-color: {colors['button_hover']};
        border-color: {colors['border_focus']};
    }}

    DrawingToolsPanel QToolButton:checked {{
        background-color: {colors['accent']};
        border: 2px solid {colors['accent_pressed']};
    }}
    """


def _set_windows_dark_titlebar(window, dark: bool) -> None:
    """Set Windows title bar to dark or light mode (Windows 10 1809+).

    Args:
        window: QWidget with window handle
        dark: True for dark title bar, False for light
    """
    try:
        import ctypes
        import sys

        if sys.platform != "win32":
            return

        hwnd = window.winId()
        if hwnd is None:
            return

        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 10 20H1+)
        # For older Windows 10 versions, use 19
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20

        # Try the newer attribute first
        value = ctypes.c_int(1 if dark else 0)
        try:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd),
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            # Try older attribute for Windows 10 1809-2004
            DWMWA_USE_IMMERSIVE_DARK_MODE = 19
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd),
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except Exception:
        # Silently fail on systems that don't support this
        pass


def apply_theme(app: QApplication, mode: ThemeMode) -> None:
    """Apply the specified theme to the application.

    Args:
        app: QApplication instance
        mode: Theme mode to apply
    """
    stylesheet = generate_stylesheet(mode)
    app.setStyleSheet(stylesheet)

    # Apply dark title bar on Windows if using dark mode
    colors = ThemeColors.get_colors(mode)
    is_dark = colors == ThemeColors.DARK

    # Update all top-level windows
    for widget in app.topLevelWidgets():
        if widget.isWindow():
            _set_windows_dark_titlebar(widget, is_dark)

    # Propagate theme colors to any open canvas views
    _apply_theme_to_canvas_views(app, colors)


def _apply_theme_to_canvas_views(app: QApplication, colors: dict[str, str]) -> None:
    """Propagate theme colors to all CanvasView instances.

    Args:
        app: QApplication instance
        colors: Theme color dictionary
    """
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

    for widget in app.allWidgets():
        if isinstance(widget, CanvasView):
            widget.apply_theme_colors(colors)
