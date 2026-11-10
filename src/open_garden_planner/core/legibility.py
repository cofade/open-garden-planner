"""How readable a colour is on another: the WCAG contrast arithmetic (Qt-free).

Text on the canvas lies on whatever the plan holds: a red roof, dark soil, a
bright lawn, the grey around the plan. The canvas therefore never relies on the
background. Every label carries its own surround (a halo, ``ui.canvas.items.
halo_text``), and this module says which ink and which halo go together: the
pair must reach ``MIN_TEXT_CONTRAST`` (#793).

Colours are ``(red, green, blue)`` with channels 0..255.
"""

from __future__ import annotations

Rgb = tuple[int, int, int]

#: The least contrast a label shows between its ink and what surrounds the ink,
#: as painted: WCAG 2.x level AA for normal-size text. The canvas tests measure
#: it on pixels (``tests/integration/test_canvas_legibility.py``).
MIN_TEXT_CONTRAST = 4.5

#: The contrast an ink COLOUR is given against its halo colour. Higher than the
#: minimum on purpose: a 10 pt glyph is a pixel or two wide, anti-aliasing
#: blends its edge with the halo, and the halo is not quite opaque, so a pair
#: that is 4.6:1 as colours (the dimension blue on white) is painted at about
#: 3.5:1. WCAG's level AAA value leaves that margin. A label that states a
#: colour of its own (a dimension in its constraint's colour) is darkened or
#: lightened, hue kept, until it reaches this.
INK_CONTRAST_TARGET = 7.0

#: The two halos. A dark ink gets the light one, a light ink the dark one.
LIGHT_HALO: Rgb = (255, 255, 255)
DARK_HALO: Rgb = (24, 24, 24)
#: An ink up to this luminance counts as dark and gets the light halo. The plan
#: is a light surface and its labels are dark, so the light halo is the rule:
#: a mid-tone ink (a constraint's green, gold or teal) is darkened a little to
#: go with it, instead of being the one label on the plan with a black edge.
#: Only an ink that would have to lose its colour for that gets the dark halo.
LIGHT_HALO_MAX_INK_LUMINANCE = 0.3


def relative_luminance(rgb: Rgb) -> float:
    """WCAG relative luminance of an sRGB colour, 0 (black) to 1 (white)."""

    def linear(channel: int) -> float:
        value = max(0, min(255, channel)) / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = rgb
    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def contrast_ratio(first: Rgb, second: Rgb) -> float:
    """WCAG contrast ratio of two colours: 1 (the same) to 21 (black on white)."""
    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def halo_for(ink: Rgb) -> Rgb:
    """The halo a label of this ink colour gets: light for a dark ink, dark for a light one."""
    if relative_luminance(ink) <= LIGHT_HALO_MAX_INK_LUMINANCE:
        return LIGHT_HALO
    return DARK_HALO


def legible_ink(ink: Rgb, halo: Rgb, minimum: float = INK_CONTRAST_TARGET) -> Rgb:
    """``ink`` moved away from ``halo`` until the two reach ``minimum`` contrast.

    The hue is kept: the channels are scaled toward black on a light halo and
    toward white on a dark one, in the smallest of 32 steps that is enough. An
    ink that already contrasts is returned unchanged: black stays black.
    """
    if contrast_ratio(ink, halo) >= minimum:
        return ink
    toward = (0, 0, 0) if relative_luminance(halo) > 0.5 else (255, 255, 255)
    for step in range(1, 33):
        share = step / 32.0
        mixed = (
            round(ink[0] + (toward[0] - ink[0]) * share),
            round(ink[1] + (toward[1] - ink[1]) * share),
            round(ink[2] + (toward[2] - ink[2]) * share),
        )
        if contrast_ratio(mixed, halo) >= minimum:
            return mixed
    return toward
