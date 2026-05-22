"""Standard paper sizes used by Paper Space layouts.

Sizes are in millimetres; the scene uses cm so callers should multiply
by 0.1 to convert. Names match the dropdown shown to users.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageSize:
    """A paper size with portrait dimensions in mm."""

    name: str
    width_mm: float
    height_mm: float

    def landscape(self) -> tuple[float, float]:
        """Return ``(width_mm, height_mm)`` in landscape orientation."""
        return (max(self.width_mm, self.height_mm), min(self.width_mm, self.height_mm))

    def portrait(self) -> tuple[float, float]:
        return (min(self.width_mm, self.height_mm), max(self.width_mm, self.height_mm))


A4 = PageSize("A4", 210.0, 297.0)
A3 = PageSize("A3", 297.0, 420.0)
LETTER = PageSize("Letter", 215.9, 279.4)

PAGE_SIZES: dict[str, PageSize] = {
    "A4": A4,
    "A3": A3,
    "Letter": LETTER,
}

DEFAULT_PAGE_NAME = "A4"
DEFAULT_ORIENTATION = "landscape"  # "landscape" or "portrait"


def get_page(name: str) -> PageSize:
    """Return the page-size record for ``name`` or fall back to A4."""
    return PAGE_SIZES.get(name, A4)


def page_size_cm(name: str, orientation: str) -> tuple[float, float]:
    """Return ``(width_cm, height_cm)`` for the named page in the given orientation."""
    page = get_page(name)
    if orientation == "portrait":
        w_mm, h_mm = page.portrait()
    else:
        w_mm, h_mm = page.landscape()
    return (w_mm / 10.0, h_mm / 10.0)
