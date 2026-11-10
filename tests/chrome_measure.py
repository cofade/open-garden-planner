"""Measure rendered chrome: contrast, clipping and the Windows mode (#791, #792, #796).

The checks in this module look at what a widget PAINTS (``QWidget.grab()``), never at
the colour its code asked for: a label can ask for ``palette(text)`` and still paint
white on cream when the palette belongs to another colour scheme than the stylesheet.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPalette
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

#: WCAG 2.x thresholds: body text, and the outline of a control or a glyph.
TEXT_CONTRAST = 4.5
GRAPHIC_CONTRAST = 3.0


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(color: QColor) -> float:
    """Relative luminance (WCAG 2.x)."""
    return (0.2126 * _channel(color.red()) + 0.7152 * _channel(color.green())
            + 0.0722 * _channel(color.blue()))


def contrast(a: QColor | str, b: QColor | str) -> float:
    """WCAG contrast ratio of two colours, 1.0 … 21.0."""
    la, lb = luminance(QColor(a)), luminance(QColor(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def grab_image(widget: QWidget, rect: QRect | None = None) -> QImage:
    """What the user sees in ``widget`` (or in ``rect`` of it), as an image.

    Grabbed THROUGH the widget's window: a label has no background of its own, and
    ``label.grab()`` would paint it over the palette's window colour instead of the
    surface the stylesheet gives its parents — the very difference this measures.
    """
    window = widget.window()
    local = rect if rect is not None else widget.rect()
    target = QRect(widget.mapTo(window, local.topLeft()), local.size())
    return window.grab(target).toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _pixels(image: QImage) -> Iterator[QColor]:
    for y in range(image.height()):
        for x in range(image.width()):
            yield image.pixelColor(x, y)


def background_of(image: QImage) -> QColor:
    """The colour most of the picture has."""
    counts = Counter(c.rgb() for c in _pixels(image))
    return QColor(counts.most_common(1)[0][0])


def ink_contrast(image: QImage) -> float:
    """Contrast of the picture's strongest ink against its background.

    Text is anti-aliased, so most of its pixels are blends; the pixel furthest from
    the background is the one the glyph's core has, and that is the colour a reader
    sees the text in.
    """
    background = background_of(image)
    return max((contrast(c, background) for c in _pixels(image)), default=1.0)


def text_contrast(widget: QWidget, rect: QRect | None = None) -> float:
    """Contrast of what ``widget`` paints (its text) against its own background."""
    return ink_contrast(grab_image(widget, rect))


def simulate_windows_mode(app: QApplication, dark: bool) -> None:
    """Leave Qt as a light or a dark Windows leaves it BEFORE the app themes itself.

    Two things carry the operating system's mode into a Qt application, and both are
    set here: the colour scheme (on a platform that has one, the native style and the
    platform palette follow it) and the application palette (every platform — the
    offscreen platform of CI has no schemes).
    """
    hints = app.styleHints()
    if hints is not None and hasattr(hints, "setColorScheme"):
        hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    palette = QPalette()
    window, base, text, button, link = (
        ("#1e1e1e", "#2d2d2d", "#ffffff", "#3c3c3c", "#fb9d8b") if dark
        else ("#f3f3f3", "#ffffff", "#000000", "#fdfdfd", "#9e0912")
    )
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        palette.setColor(group, QPalette.ColorRole.Window, QColor(window))
        palette.setColor(group, QPalette.ColorRole.Base, QColor(base))
        palette.setColor(group, QPalette.ColorRole.AlternateBase, QColor(window))
        palette.setColor(group, QPalette.ColorRole.Button, QColor(button))
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.ButtonText, QPalette.ColorRole.PlaceholderText):
            palette.setColor(group, role, QColor(text))
        palette.setColor(group, QPalette.ColorRole.Link, QColor(link))
    app.setPalette(palette)


def clipped_labels(root: QWidget) -> list[str]:
    """Visible labels under ``root`` that are narrower or lower than their text.

    A label that wraps is measured by the height its width needs; one that shows a
    pixmap, or nothing, is skipped. Returns ``"text (have WxH, need WxH)"`` lines.
    """
    problems: list[str] = []
    for label in root.findChildren(QLabel):
        if not label.isVisibleTo(root) or not label.text().strip():
            continue
        if label.pixmap() is not None and not label.pixmap().isNull():
            continue
        have = label.size()
        if label.wordWrap():
            need_w = label.minimumSizeHint().width()
            need_h = label.heightForWidth(have.width())
        else:
            hint = label.sizeHint()
            need_w, need_h = hint.width(), hint.height()
        # 1 px of tolerance: a layout rounds a hint down by one at fractional scales
        if have.width() + 1 < need_w or have.height() + 1 < need_h:
            problems.append(
                f"{label.text()[:40]!r} (have {have.width()}x{have.height()}, "
                f"need {need_w}x{need_h})"
            )
    return problems
