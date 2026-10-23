"""The compass rose's letters as outlines (Phase 17 L2.2, #386). Engine-free.

QML carries no user-visible text (``pylupdate6`` does not extract ``qsTr``), and a
letter on the 3D ground is text: so the four cardinal letters are TRANSLATED here
(German "O" for east, Spanish "O" for west …), drawn with the application font and
handed to ``core.scene3d.sun_path.compass_mesh`` as outlines — closed rings in em
units, centred on (0, 0), one unit high, y up the letter — which it fills and lays
flat on the ground. A texture would have been the other way: one more texture per
language change, and the engine's texture rules (#532) for four letters.
"""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, QPointF
from PyQt6.QtGui import QFont, QPainterPath

Ring = list[tuple[float, float]]

#: Pixel size the outlines are taken at: fine enough for smooth curves after
#: ``toSubpathPolygons`` flattens them, normalised to one unit afterwards.
_PIXEL_SIZE = 200


def cardinal_letters() -> dict[float, str]:
    """The four letters by bearing, in the UI language."""
    return {
        0.0: QCoreApplication.translate("Compass", "N"),
        90.0: QCoreApplication.translate("Compass", "E"),
        180.0: QCoreApplication.translate("Compass", "S"),
        270.0: QCoreApplication.translate("Compass", "W"),
    }


def glyph_outlines(text: str, font: QFont | None = None) -> list[Ring]:
    """``text``'s outlines (module docstring); nothing for text without a shape."""
    face = QFont(font) if font is not None else QFont()
    face.setPixelSize(_PIXEL_SIZE)
    face.setBold(True)
    path = QPainterPath()
    path.addText(QPointF(0.0, 0.0), face, text)
    rings: list[Ring] = []
    for polygon in path.toSubpathPolygons():
        points: Ring = []
        for point in polygon:
            here = (float(point.x()), -float(point.y()))  # y DOWN in the font, up in the plan
            if not points or here != points[-1]:
                points.append(here)
        if len(points) > 1 and points[0] == points[-1]:
            points.pop()
        if len(points) >= 3:
            rings.append(points)
    if not rings:
        return []
    xs = [x for ring in rings for x, _ in ring]
    ys = [y for ring in rings for _, y in ring]
    height = max(ys) - min(ys)
    if height <= 0.0:
        return []
    cx, cy = (max(xs) + min(xs)) / 2.0, (max(ys) + min(ys)) / 2.0
    return [[((x - cx) / height, (y - cy) / height) for x, y in ring] for ring in rings]


def cardinal_glyphs() -> dict[float, list[Ring]]:
    """The four letters' outlines by bearing — what ``compass_mesh`` takes."""
    return {bearing: glyph_outlines(letter) for bearing, letter in cardinal_letters().items()}
