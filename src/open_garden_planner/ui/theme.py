"""Theme management for the application.

Provides light and dark color schemes with comprehensive styling.
"""

import contextlib
import os
import tempfile
from collections.abc import Callable
from enum import Enum

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QWidget


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
        # Section-header background (e.g. category-row stripes in tables).
        # Light-pastel green that reads as a banded heading on a cream surface.
        "section_header": "#e8f5e9",
        # Semantic status surfaces — tinted backgrounds for banners/cards
        "success_bg": "#e3f2e3",
        "warning_bg": "#fdf0dd",
        "error_bg": "#fbe3e3",
        "info_bg": "#e6f0fa",
        # "This week" urgency — a yellow that stays readable on light chrome
        "caution": "#b58b00",
        # Canvas overlay chrome (dynamic input): sits on the always-light
        # canvas, so these stay constant across themes (same rationale as the
        # canvas colors).  rgba strings — not parseable by theme_qcolor().
        "overlay_bg": "rgba(30, 30, 30, 200)",
        "overlay_border": "rgba(120, 200, 120, 180)",
        "overlay_text": "#ffffff",
        "overlay_field_bg": "rgba(60, 60, 60, 220)",
        "overlay_field_border": "rgba(120, 200, 120, 100)",
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
        # Section-header background — sage-toned dark green that stays
        # readable against the dark surface and matches the accent palette.
        "section_header": "#264a2c",
        # Semantic status surfaces — tinted backgrounds for banners/cards
        "success_bg": "#25382a",
        "warning_bg": "#3d3222",
        "error_bg": "#3d2626",
        "info_bg": "#22303d",
        # "This week" urgency — brighter yellow for dark chrome
        "caution": "#f1c40f",
        # Canvas overlay chrome — constant across themes (see LIGHT).
        "overlay_bg": "rgba(30, 30, 30, 200)",
        "overlay_border": "rgba(120, 200, 120, 180)",
        "overlay_text": "#ffffff",
        "overlay_field_bg": "rgba(60, 60, 60, 220)",
        "overlay_field_border": "rgba(120, 200, 120, 100)",
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


# ---------------------------------------------------------------------------
# Live palette access
#
# _current_colors always holds the palette of the most recently applied theme
# (LIGHT until apply_theme() first runs).  Widget code uses theme_color() /
# theme_qcolor() / rgba() instead of hardcoding hex values so runtime-built
# QSS strings and QColor usages follow theme switches.
# ---------------------------------------------------------------------------

_current_colors: dict[str, str] = ThemeColors.LIGHT
_theme_listeners: list[Callable[[dict[str, str]], None]] = []


# Muted per-category identity tints for the gallery category chip icons
# (icon_name slug -> (light_hex, dark_hex)).  Applied by the icon provider as
# the primary-line tint; unknown slugs fall back to text_primary (neutral).
CATEGORY_ICON_TINTS: dict[str, tuple[str, str]] = {
    "garden_bed": ("#7a5c3e", "#b99b78"),
    "rectangle": ("#5a6b5a", "#a3ab9d"),
    "tree": ("#3d7a44", "#7cb87f"),
    "shrub": ("#4e7d5b", "#8fbf9a"),
    "flower": ("#8a5a7a", "#c495b3"),
    "vegetable": ("#a1682f", "#d0a05e"),
    "house": ("#6b5b4a", "#b0a08c"),
    "furniture": ("#5c6b7a", "#9fb0c0"),
    "fence": ("#726a52", "#b3a987"),
    "infrastructure": ("#556677", "#8fa3b5"),
}


def current_colors() -> dict[str, str]:
    """Return the palette of the most recently applied theme."""
    return _current_colors


def is_dark_theme() -> bool:
    """True when the most recently applied palette is the dark one."""
    return _current_colors == ThemeColors.DARK


def theme_color(name: str) -> str:
    """Return a color token from the active palette (hex or rgba string)."""
    return _current_colors[name]


def theme_qcolor(name: str) -> QColor:
    """Return a hex color token as QColor (not for the rgba overlay_* tokens)."""
    return QColor(_current_colors[name])


def rgba(name: str, alpha: int) -> str:
    """Return an ``rgba(r, g, b, a)`` QSS string for a hex token with custom alpha."""
    color = QColor(_current_colors[name])
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


def register_theme_listener(callback: Callable[[dict[str, str]], None]) -> None:
    """Subscribe to palette changes; called with the new colors on every apply_theme()."""
    _theme_listeners.append(callback)


def set_text_role(
    widget: QWidget,
    role: str | None = None,
    color_role: str | None = None,
) -> None:
    """Assign typography/color roles styled centrally by the app stylesheet.

    Sets the ``textRole`` (h1/h2/hint/small/placeholder) and ``colorRole``
    (success/warning/error/info/caution/disabled/secondary) dynamic properties
    and re-polishes so a change after first polish takes effect (§8.17.6).
    """
    if role is not None:
        widget.setProperty("textRole", role)
    if color_role is not None:
        widget.setProperty("colorRole", color_role)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


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
        border-radius: 4px;
        margin: 1px 4px;
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
        border-radius: 6px;
        padding: 6px 14px;
        min-width: 80px;
    }}

    QPushButton:hover {{
        background-color: {colors['button_hover']};
        border-color: {colors['border_focus']};
    }}

    QPushButton:pressed {{
        background-color: {colors['button_pressed']};
    }}

    QPushButton:focus {{
        border: 2px solid {colors['border_focus']};
        padding: 5px 13px;
    }}

    QPushButton:default {{
        background-color: {colors['accent']};
        color: {colors['accent_text']};
        border: 1px solid {colors['accent_pressed']};
    }}

    QPushButton:default:hover {{
        background-color: {colors['accent_hover']};
    }}

    QPushButton:default:pressed {{
        background-color: {colors['accent_pressed']};
    }}

    QPushButton:disabled {{
        background-color: {colors['input_disabled']};
        color: {colors['text_disabled']};
        border-color: {colors['border']};
    }}

    /* Dialog CTA roles — setProperty("buttonRole", "primary"/"secondary") */
    QPushButton[buttonRole="primary"] {{
        background-color: {colors['accent']};
        color: {colors['accent_text']};
        border: 1px solid {colors['accent_pressed']};
        font-weight: 600;
    }}

    QPushButton[buttonRole="primary"]:hover {{
        background-color: {colors['accent_hover']};
    }}

    QPushButton[buttonRole="primary"]:pressed {{
        background-color: {colors['accent_pressed']};
    }}

    QPushButton[buttonRole="secondary"] {{
        background-color: transparent;
        color: {colors['accent']};
        border: 1px solid {colors['accent']};
    }}

    QPushButton[buttonRole="secondary"]:hover {{
        background-color: {colors['selection']};
    }}

    QPushButton[buttonRole="secondary"]:disabled {{
        color: {colors['text_disabled']};
        border-color: {colors['border']};
        background-color: transparent;
    }}

    /* Tool buttons */
    QToolButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 5px;
        padding: 4px;
    }}

    QToolButton:hover {{
        background-color: {colors['button_hover']};
        border-color: {colors['border']};
    }}

    QToolButton:pressed {{
        background-color: {colors['button_pressed']};
        border-color: {colors['accent']};
    }}

    QToolButton:checked {{
        background-color: {colors['selection']};
        border-color: {colors['accent']};
    }}

    /* Text inputs */
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background-color: {colors['input']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
        padding: 5px 8px;
        selection-background-color: {colors['selection']};
    }}

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 2px solid {colors['border_focus']};
        padding: 4px 7px;
    }}

    /* Validation error state — setProperty("inputError", True) + re-polish */
    QLineEdit[inputError="true"] {{
        border: 2px solid {colors['error']};
        padding: 4px 7px;
        background-color: {colors['error_bg']};
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
        border-radius: 6px;
        padding: 5px 20px 5px 8px;
    }}

    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 2px solid {colors['border_focus']};
        padding: 4px 19px 4px 7px;
    }}

    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 16px;
        border-left: 1px solid {colors['border']};
        border-bottom: 1px solid {colors['border']};
        border-top-right-radius: 5px;
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
        border-bottom-right-radius: 5px;
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
        border-radius: 6px;
        padding: 5px 8px;
    }}

    QDateEdit:focus {{
        border: 2px solid {colors['border_focus']};
        padding: 4px 7px;
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
        border-radius: 6px;
        padding: 5px 8px;
    }}

    QComboBox:focus {{
        border: 2px solid {colors['border_focus']};
        padding: 4px 7px;
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

    QRadioButton::indicator {{
        width: 14px;
        height: 14px;
        border-radius: 7px;
        border: 2px solid {colors['border']};
        background-color: {colors['input']};
    }}

    QRadioButton::indicator:checked {{
        background-color: {colors['accent']};
        border-color: {colors['accent']};
        image: url();
    }}

    QRadioButton::indicator:unchecked:hover {{
        border-color: {colors['accent']};
    }}

    QRadioButton::indicator:disabled {{
        border-color: {colors['text_disabled']};
        background-color: {colors['input_disabled']};
    }}

    /* List widgets */
    QListWidget {{
        background-color: {colors['input']};
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
    }}

    QListWidget::item {{
        padding: 5px 6px;
        border-radius: 4px;
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
        border: none;
        border-bottom: 1px solid {colors['border']};
        border-right: 1px solid {colors['background_alt']};
        padding: 5px 6px;
        font-weight: 600;
    }}

    /* Scroll bars — slim, transparent track */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 10px;
        border: none;
    }}

    QScrollBar::handle:vertical {{
        background-color: {colors['surface_alt']};
        min-height: 30px;
        border-radius: 4px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {colors['button_hover']};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: transparent;
        height: 10px;
        border: none;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {colors['surface_alt']};
        min-width: 30px;
        border-radius: 4px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background-color: {colors['button_hover']};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    QScrollBar::add-page, QScrollBar::sub-page {{
        background: none;
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

    /* Tab widgets — underline style (documentMode: style QTabBar::tab directly) */
    QTabWidget::pane {{
        border: none;
        border-top: 1px solid {colors['border']};
        background-color: {colors['surface']};
    }}

    QTabBar::tab {{
        background-color: transparent;
        color: {colors['text_secondary']};
        border: none;
        border-bottom: 2px solid transparent;
        padding: 7px 16px;
        margin-right: 2px;
    }}

    QTabBar::tab:selected {{
        color: {colors['text_primary']};
        border-bottom: 2px solid {colors['accent']};
    }}

    QTabBar::tab:hover:!selected {{
        background-color: {colors['background_alt']};
    }}

    /* Group boxes */
    QGroupBox {{
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
        margin-top: 8px;
        padding-top: 8px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 4px;
        background-color: {colors['background']};
        color: {colors['accent']};
        font-weight: 600;
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

    /* Typography roles — set via theme.set_text_role(widget, role, color_role).
       textRole controls size/weight, colorRole the semantic text color; the
       two properties are orthogonal and combinable. */
    QLabel[textRole="h1"] {{
        font-size: 13pt;
        font-weight: 600;
    }}

    QLabel[textRole="h2"] {{
        font-size: 10pt;
        font-weight: 600;
    }}

    QLabel[textRole="hint"] {{
        font-size: 8pt;
        color: {colors['text_secondary']};
    }}

    QLabel[textRole="small"] {{
        font-size: 8pt;
    }}

    QLabel[textRole="placeholder"] {{
        font-style: italic;
        color: {colors['text_secondary']};
    }}

    QLabel[colorRole="success"] {{ color: {colors['success']}; }}
    QLabel[colorRole="warning"] {{ color: {colors['warning']}; }}
    QLabel[colorRole="error"] {{ color: {colors['error']}; }}
    QLabel[colorRole="info"] {{ color: {colors['info']}; }}
    QLabel[colorRole="caution"] {{ color: {colors['caution']}; }}
    QLabel[colorRole="disabled"] {{ color: {colors['text_disabled']}; }}
    QLabel[colorRole="secondary"] {{ color: {colors['text_secondary']}; }}

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

    /* Collapsible Panel Headers (US-226 accordion: panelState property) */
    CollapsiblePanel > QFrame {{
        background-color: {colors['surface']};
        border: 1px solid {colors['border']};
    }}

    /* Instant hover affordance before the peek debounce commits (~140 ms). */
    CollapsiblePanel[panelState="collapsed"] > QFrame:hover {{
        background-color: {colors['surface_alt']};
    }}

    /* Peeking: hover-expanded in place — accent border + lighter fill. */
    CollapsiblePanel[panelState="peeking"] > QFrame {{
        background-color: {colors['surface_alt']};
        border: 1px solid {colors['accent']};
    }}

    /* Pinned: 3px left accent rail marks panels held open by the user. */
    CollapsiblePanel[panelState="pinned"] > QFrame {{
        background-color: {colors['surface']};
        border: 1px solid {colors['border']};
        border-left: 3px solid {colors['accent']};
    }}

    CollapsiblePanel QLabel {{
        color: {colors['text_primary']};
    }}

    /* Dashboard panel header (Planting Calendar – Today's Tasks) */
    QFrame#dashboardPanelHeader {{
        background-color: {colors['surface']};
        border-bottom: 1px solid {colors['border']};
    }}

    /* Mark-done button in dashboard task rows */
    QPushButton#taskDoneBtn {{
        background-color: transparent;
        border: 1px solid {colors['border']};
        border-radius: 3px;
        color: {colors['text_secondary']};
        font-size: 8pt;
        padding: 1px 4px;
    }}

    QPushButton#taskDoneBtn:hover {{
        border-color: {colors['accent']};
        color: {colors['accent']};
    }}

    QPushButton#taskDoneBtn:checked {{
        background-color: {colors['accent']};
        border-color: {colors['accent_pressed']};
        color: {colors['accent_text']};
    }}

    /* Constraints-panel delete-all header button */
    QToolButton#constraintsDeleteAllBtn {{
        color: {colors['error']};
        font-weight: 600;
    }}

    /* Notification banners — widgets carry only an objectName; all styling
       lives here so a theme switch restyles them automatically. */
    #TaskReminderBar {{
        background-color: {colors['warning_bg']};
        border: none;
        border-bottom: 1px solid {colors['warning']};
    }}

    #TaskReminderBar QLabel {{
        color: {colors['text_primary']};
        font-weight: 600;
        background-color: transparent;
    }}

    #TaskReminderBar QPushButton {{
        background-color: transparent;
        color: {colors['text_primary']};
        border: 1px solid {colors['warning']};
        border-radius: 4px;
        padding: 2px 10px;
        min-width: 0px;
    }}

    #TaskReminderBar QPushButton:hover {{
        background-color: {colors['button_hover']};
    }}

    #UpdateBar {{
        background-color: {colors['info_bg']};
        border: none;
        border-bottom: 1px solid {colors['border']};
    }}

    #UpdateBar QLabel {{
        color: {colors['text_primary']};
        background-color: transparent;
    }}

    #UpdateBar QPushButton {{
        background-color: transparent;
        color: {colors['text_primary']};
        border: 1px solid {colors['border']};
        border-radius: 4px;
        padding: 2px 10px;
        min-width: 0px;
    }}

    #UpdateBar QPushButton:hover {{
        background-color: {colors['button_hover']};
    }}

    /* Weather forecast day cards — dynamic properties weatherCard +
       frostSeverity ("orange"/"red"), re-polished on change. */
    QFrame[weatherCard="true"] {{
        background-color: {colors['surface']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
    }}

    QFrame[weatherCard="true"][frostSeverity="orange"] {{
        background-color: {colors['warning_bg']};
        border-color: {colors['warning']};
    }}

    QFrame[weatherCard="true"][frostSeverity="red"] {{
        background-color: {colors['error_bg']};
        border-color: {colors['error']};
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
    global _current_colors

    # Publish the resolved palette BEFORE restyling so listeners and
    # re-polished widgets that call theme_color() during the restyle
    # already see the new values.
    colors = ThemeColors.get_colors(mode)
    _current_colors = colors

    stylesheet = generate_stylesheet(mode)
    app.setStyleSheet(stylesheet)

    # Notify subscribers (e.g. the icon provider) of the new palette.
    for listener in list(_theme_listeners):
        with contextlib.suppress(Exception):
            listener(colors)

    # Apply dark title bar on Windows if using dark mode
    is_dark = colors == ThemeColors.DARK

    # Update all top-level windows
    for widget in app.topLevelWidgets():
        if widget.isWindow():
            _set_windows_dark_titlebar(widget, is_dark)

    # Propagate theme colors to widgets that opt in (canvas views,
    # dashboard views, … — anything exposing apply_theme_colors(colors)).
    _propagate_theme_colors(app, colors)


def _propagate_theme_colors(app: QApplication, colors: dict[str, str]) -> None:
    """Push the new palette to every widget that opts in (duck-typed).

    Two hooks, both optional per widget:
    - ``apply_theme_colors(colors)`` — palette-driven redraws (CanvasView,
      dashboard views, …)
    - ``refresh_theme_icons()`` — re-request icons from ui/icons.py after
      its cache was cleared (toolbars, the main window's menu actions)

    Args:
        app: QApplication instance
        colors: Theme color dictionary
    """
    for widget in app.allWidgets():
        handler = getattr(widget, "apply_theme_colors", None)
        if callable(handler):
            handler(colors)
        refresh = getattr(widget, "refresh_theme_icons", None)
        if callable(refresh):
            refresh()
