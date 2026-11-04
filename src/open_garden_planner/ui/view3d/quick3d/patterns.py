"""The plan's own fill pictures for 3D solids (#628 follow-up). ENGINE module.

A lawn, path, terrace, generic shape or garden bed keeps the fill the ground bake
painted while it lay flat when the user gives it a height: ``MeshPart.fill_texture``
names such a part, and the sink hands its Model a picture of the item's fill — the
fill pattern tinted with the fill colour, or that colour alone for SOLID
(``core.fill_patterns.tinted_pattern_pixels``).

One picture per (pattern, colour), shared by every Model that shows it, and never
re-pointed at another ``QQuick3DTextureData`` (that makes the ``Texture`` white:
``ogp-3d-renderer`` §5). The sink refcounts the pictures it shows and calls
``EngineScene.release_fill`` with the last user, so recolouring a raised lawn
leaves nothing behind.
"""

from __future__ import annotations

import weakref
from typing import ClassVar

from PyQt6 import sip
from PyQt6.QtCore import QByteArray, QSize
from PyQt6.QtQuick3D import QQuick3DTextureData

__all__ = ["PatternTexture", "textures_alive"]


class PatternTexture(QQuick3DTextureData):
    """One fill picture on its way to the GPU: RGBA8, uploaded once, at construction."""

    #: Uploads made in this process — the instrument behind "a raised plan shows one
    #: picture per (pattern, colour), not one per Model".
    uploads: ClassVar[int] = 0

    def __init__(self, width: int, height: int, pixels: bytes) -> None:
        super().__init__()
        _MADE.add(self)
        self.setSize(QSize(width, height))
        self.setFormat(QQuick3DTextureData.Format.RGBA8)
        self.setHasTransparency(False)
        self.setTextureData(QByteArray(pixels))
        # QQuick3DObject.update() exists at runtime; PyQt6 6.11's stubs do not declare it
        self.update()  # type: ignore[attr-defined]
        PatternTexture.uploads += 1


#: Every fill picture made in this process, held WEAKLY: what ``textures_alive`` counts.
_MADE: weakref.WeakSet[PatternTexture] = weakref.WeakSet()


def textures_alive() -> int:
    """``PatternTexture`` objects that EXIST on the C++ side right now — the
    keep-alive rule as a number (the same instrument as
    ``ground_tiles.textures_alive``, and asked of sip for the same reason)."""
    return sum(1 for texture in list(_MADE) if not sip.isdeleted(texture))
