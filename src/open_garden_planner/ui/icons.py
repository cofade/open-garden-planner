"""Central themed icon provider (#279, ADR-039).

The single render path for every chrome icon (toolbars, gallery chips,
menus).  SVGs in ``resources/icons/ui/`` are authored on the house contract
(``currentColor`` primary line + the accent sentinel ``#3D8B37``) and MUST
NOT be fed to QSvgRenderer directly — QSvgRenderer paints raw
``currentColor`` black.  This module substitutes the active theme's colors
into the SVG text before rasterizing, renders at the device pixel ratio for
HiDPI crispness, and caches per ``(name, size, tint, accent)``.

Theme integration: a theme listener registered at import clears the cache
on every ``apply_theme()``; widgets re-request their icons via
``refresh_theme_icons()`` hooks (see §8.21).  ``get_icon``/``get_pixmap``
return ``None`` for unknown names so every caller's existing emoji/text
fallback keeps working.
"""

from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from open_garden_planner.ui.theme import current_colors, register_theme_listener

_ICONS_DIR = Path(__file__).parent.parent / "resources" / "icons" / "ui"

#: Reserved accent color baked into the SVGs — replaced with the active
#: theme's ``accent`` token at render time (equals the light-theme accent so
#: raw files preview correctly in editors).
ACCENT_SENTINEL = "#3D8B37"
_ACCENT_RE = re.compile(re.escape(ACCENT_SENTINEL), re.IGNORECASE)

_svg_cache: dict[str, str | None] = {}
_icon_cache: dict[tuple[str, int, int, str, str], QIcon] = {}
_pixmap_cache: dict[tuple[str, int, int, str, str], QPixmap] = {}


def clear_cache() -> None:
    """Drop cached icons/pixmaps (called automatically on theme switch).

    The raw SVG text cache survives — file contents do not depend on the
    theme, so a switch must not force 70+ file re-reads.
    """
    _icon_cache.clear()
    _pixmap_cache.clear()


register_theme_listener(lambda _colors: clear_cache())


def available_icons() -> list[str]:
    """All icon names shipped in resources/icons/ui/ (for tests/gates)."""
    return sorted(path.stem for path in _ICONS_DIR.glob("*.svg"))


def _svg_text(name: str) -> str | None:
    if name not in _svg_cache:
        path = _ICONS_DIR / f"{name}.svg"
        _svg_cache[name] = (
            path.read_text(encoding="utf-8") if name and path.exists() else None
        )
    return _svg_cache[name]


def _device_pixel_ratio() -> float:
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if isinstance(app, QGuiApplication) else None
    return screen.devicePixelRatio() if screen is not None else 1.0


def _render(
    svg_text: str, size: int, tint: str, accent: str, dpr: float
) -> QPixmap | None:
    # Accent first: a caller-supplied tint could itself be the sentinel hex,
    # and must not be re-substituted afterwards.
    data = _ACCENT_RE.sub(accent, svg_text).replace("currentColor", tint)
    renderer = QSvgRenderer(QByteArray(data.encode("utf-8")))
    if not renderer.isValid():
        return None
    pixel_size = max(1, round(size * dpr))
    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def get_pixmap(name: str, size: int = 64, color: str | None = None) -> QPixmap | None:
    """Render an icon as a plain pixmap (gallery thumbnails).

    Args:
        name: Semantic icon name (file stem in resources/icons/ui/).
        size: Logical edge length in px (rendered at size x devicePixelRatio).
        color: Optional hex override for the primary line (defaults to the
            theme's ``text_primary``); the accent sentinel is always mapped
            to the theme's ``accent``.

    Returns:
        The pixmap, or None if the icon is unknown/invalid (callers fall
        back exactly as before).
    """
    svg_text = _svg_text(name)
    if svg_text is None:
        return None
    colors = current_colors()
    tint = color or colors["text_primary"]
    accent = colors["accent"]
    dpr = _device_pixel_ratio()
    key = (name, size, round(dpr * 100), tint.lower(), accent.lower())
    pixmap = _pixmap_cache.get(key)
    if pixmap is None:
        pixmap = _render(svg_text, size, tint, accent, dpr)
        if pixmap is None:
            return None
        _pixmap_cache[key] = pixmap
    return pixmap


def get_icon(name: str, size: int = 24, color: str | None = None) -> QIcon | None:
    """Render an icon as a QIcon with Normal + Disabled modes.

    Same contract as :func:`get_pixmap`; the Disabled variant substitutes
    the theme's ``text_disabled`` for BOTH tokens, so disabled buttons
    (e.g. the constraint toolbar's coming-soon entries) gray out fully.
    """
    svg_text = _svg_text(name)
    if svg_text is None:
        return None
    colors = current_colors()
    tint = color or colors["text_primary"]
    accent = colors["accent"]
    dpr = _device_pixel_ratio()
    key = (name, size, round(dpr * 100), tint.lower(), accent.lower())
    icon = _icon_cache.get(key)
    if icon is None:
        normal = _render(svg_text, size, tint, accent, dpr)
        if normal is None:
            return None
        icon = QIcon()
        icon.addPixmap(normal, QIcon.Mode.Normal)
        disabled_tint = colors["text_disabled"]
        grayed = _render(svg_text, size, disabled_tint, disabled_tint, dpr)
        if grayed is not None:
            icon.addPixmap(grayed, QIcon.Mode.Disabled)
        _icon_cache[key] = icon
    return icon
