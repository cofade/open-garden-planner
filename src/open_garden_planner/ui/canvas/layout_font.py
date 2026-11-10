"""The size a font really has on the canvas (#836).

A scene item lays its text out with no paint device, so a font given in
*points* is resolved at the screen's logical resolution (96 per inch on
Windows and on a default Linux desktop): 28 pt is a 37-pixel em. Two things
follow, and both went wrong before they were written down here:

* **In item coordinates a pixel is a plan centimetre.** A ``TextItem`` scales
  with the plan, so its 37-pixel em is 37 cm of garden — not the "1 cm" its
  stored ``font_size`` of 1.0 was documented as.
* **A painter resolves the same font for ITS device.** ``painter.setFont`` of a
  7 pt font is 9 pixels on a ``QImage`` and 117 on a 1200-dpi printer, while
  ``QFontMetricsF(font)`` still answers for the screen. Text drawn by hand in a
  box measured that way overflows its box in a printout (PF-CAN-59). Draw with
  ``device_independent`` instead: a font sized in pixels is the same number of
  device units everywhere.
"""

from __future__ import annotations

from PyQt6.QtGui import QFont, QFontInfo, QGuiApplication

_FALLBACK_DPI = 96.0


def layout_dpi() -> float:
    """Pixels per inch at which a font in points is laid out without a device."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return _FALLBACK_DPI
    dpi = screen.logicalDotsPerInchY()
    return float(dpi) if dpi > 0 else _FALLBACK_DPI


def layout_pixel_size(font: QFont) -> float:
    """The em of *font* in pixels, as a scene item lays it out.

    What the font engine resolved where it says so (Windows gives whole
    pixels: 28 pt is 37, not 37.33); the arithmetic where it does not (the
    offscreen platform of the test suite has no real fonts).
    """
    if font.pixelSize() > 0:
        return float(font.pixelSize())
    resolved = QFontInfo(font).pixelSize()
    if resolved > 0:
        return float(resolved)
    return float(max(1, round(font.pointSizeF() * layout_dpi() / 72.0)))


def device_independent(font: QFont) -> QFont:
    """*font* sized in pixels: the same size on a screen, a picture and a printer."""
    sized = QFont(font)
    sized.setPixelSize(max(1, round(layout_pixel_size(font))))
    return sized
