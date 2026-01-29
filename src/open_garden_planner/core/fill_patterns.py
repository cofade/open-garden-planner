"""Fill pattern definitions and generators for object styling."""

from enum import Enum, auto

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPixmap


class FillPattern(Enum):
    """Available fill patterns for objects."""

    SOLID = auto()  # Solid color fill
    GRASS = auto()  # Grass texture
    GRAVEL = auto()  # Gravel/stone texture
    CONCRETE = auto()  # Concrete texture
    WOOD = auto()  # Wood grain texture
    WATER = auto()  # Water texture
    SOIL = auto()  # Soil/dirt texture
    MULCH = auto()  # Mulch texture
    ROOF_TILES = auto()  # Roof tile texture


def create_pattern_brush(pattern: FillPattern, color: QColor) -> QBrush:
    """Create a QBrush with the specified pattern and base color.

    Args:
        pattern: The fill pattern to use
        color: The base color for the pattern

    Returns:
        A QBrush configured with the pattern
    """
    if pattern == FillPattern.SOLID:
        return QBrush(color)
    elif pattern == FillPattern.GRASS:
        return _create_grass_pattern(color)
    elif pattern == FillPattern.GRAVEL:
        return _create_gravel_pattern(color)
    elif pattern == FillPattern.CONCRETE:
        return _create_concrete_pattern(color)
    elif pattern == FillPattern.WOOD:
        return _create_wood_pattern(color)
    elif pattern == FillPattern.WATER:
        return _create_water_pattern(color)
    elif pattern == FillPattern.SOIL:
        return _create_soil_pattern(color)
    elif pattern == FillPattern.MULCH:
        return _create_mulch_pattern(color)
    elif pattern == FillPattern.ROOF_TILES:
        return _create_roof_tiles_pattern(color)
    else:
        return QBrush(color)


def _create_grass_pattern(color: QColor) -> QBrush:
    """Create a simple grass pattern."""
    # Create a small tileable pattern
    size = 20
    pixmap = QPixmap(size, size)
    pixmap.fill(color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw small vertical lines to suggest grass blades
    darker = color.darker(120)
    painter.setPen(darker)
    for i in range(8):
        x = (i * 7) % size
        y = (i * 11) % size
        painter.drawLine(x, y, x, y + 3)

    painter.end()
    return QBrush(pixmap)


def _create_gravel_pattern(color: QColor) -> QBrush:
    """Create a simple gravel/stone pattern."""
    size = 24
    pixmap = QPixmap(size, size)
    pixmap.fill(color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw small irregular dots to suggest stones
    darker = color.darker(130)
    lighter = color.lighter(110)

    painter.setPen(Qt.PenStyle.NoPen)
    # Draw darker stones
    painter.setBrush(darker)
    painter.drawEllipse(2, 3, 3, 3)
    painter.drawEllipse(10, 8, 4, 3)
    painter.drawEllipse(18, 5, 3, 4)
    painter.drawEllipse(6, 14, 4, 4)
    painter.drawEllipse(16, 16, 3, 3)

    # Draw lighter stones
    painter.setBrush(lighter)
    painter.drawEllipse(5, 6, 2, 2)
    painter.drawEllipse(14, 2, 3, 2)
    painter.drawEllipse(20, 12, 2, 3)
    painter.drawEllipse(2, 18, 3, 2)
    painter.drawEllipse(12, 19, 2, 2)

    painter.end()
    return QBrush(pixmap)


def _create_concrete_pattern(color: QColor) -> QBrush:
    """Create a simple concrete pattern."""
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(color)

    painter = QPainter(pixmap)

    # Add slight mottled effect
    darker = color.darker(105)
    lighter = color.lighter(103)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(darker)
    painter.setOpacity(0.3)
    painter.drawRect(0, 0, 16, 16)
    painter.drawRect(16, 16, 16, 16)

    painter.setBrush(lighter)
    painter.drawRect(16, 0, 16, 16)
    painter.drawRect(0, 16, 16, 16)

    painter.end()
    return QBrush(pixmap)


def _create_wood_pattern(color: QColor) -> QBrush:
    """Create a simple wood grain pattern."""
    size = 24
    pixmap = QPixmap(size, size)
    pixmap.fill(color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw horizontal lines to suggest wood grain
    darker = color.darker(115)
    painter.setPen(darker)

    for y in range(0, size, 4):
        # Vary the line slightly for natural look
        offset = (y // 4) % 3
        painter.drawLine(offset, y, size - offset, y)

    painter.end()
    return QBrush(pixmap)


def _create_water_pattern(color: QColor) -> QBrush:
    """Create a simple water pattern with wavy lines."""
    size = 28
    pixmap = QPixmap(size, size)
    pixmap.fill(color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw wavy horizontal lines
    lighter = color.lighter(115)
    darker = color.darker(110)

    painter.setPen(lighter)
    painter.drawLine(0, 8, 8, 6)
    painter.drawLine(8, 6, 16, 8)
    painter.drawLine(16, 8, 24, 6)

    painter.setPen(darker)
    painter.drawLine(4, 20, 12, 18)
    painter.drawLine(12, 18, 20, 20)

    painter.end()
    return QBrush(pixmap)


def _create_soil_pattern(color: QColor) -> QBrush:
    """Create a simple soil/dirt pattern."""
    size = 22
    pixmap = QPixmap(size, size)
    pixmap.fill(color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw small irregular shapes to suggest soil texture
    darker = color.darker(125)
    lighter = color.lighter(108)

    painter.setPen(Qt.PenStyle.NoPen)

    # Darker clumps
    painter.setBrush(darker)
    painter.drawEllipse(1, 2, 4, 3)
    painter.drawEllipse(8, 5, 3, 4)
    painter.drawEllipse(14, 1, 5, 3)
    painter.drawEllipse(3, 12, 4, 4)
    painter.drawEllipse(12, 14, 3, 5)
    painter.drawEllipse(18, 10, 3, 3)

    # Lighter spots
    painter.setBrush(lighter)
    painter.drawEllipse(6, 8, 2, 2)
    painter.drawEllipse(16, 6, 2, 3)
    painter.drawEllipse(2, 18, 3, 2)
    painter.drawEllipse(10, 18, 2, 2)

    painter.end()
    return QBrush(pixmap)


def _create_mulch_pattern(color: QColor) -> QBrush:
    """Create a simple mulch pattern with small elongated pieces."""
    size = 26
    pixmap = QPixmap(size, size)
    pixmap.fill(color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw small elongated shapes at various angles
    darker = color.darker(130)
    lighter = color.lighter(110)

    painter.setPen(Qt.PenStyle.NoPen)

    # Darker pieces
    painter.setBrush(darker)
    painter.drawRect(2, 3, 6, 2)
    painter.drawRect(10, 1, 2, 5)
    painter.drawRect(16, 6, 7, 2)
    painter.drawRect(4, 12, 5, 2)
    painter.drawRect(12, 16, 2, 6)
    painter.drawRect(20, 18, 4, 2)

    # Lighter pieces
    painter.setBrush(lighter)
    painter.drawRect(8, 8, 4, 2)
    painter.drawRect(18, 2, 2, 4)
    painter.drawRect(2, 20, 6, 2)
    painter.drawRect(14, 22, 2, 3)

    painter.end()
    return QBrush(pixmap)


def _create_roof_tiles_pattern(color: QColor) -> QBrush:
    """Create a simple roof tile pattern with overlapping scales."""
    size = 24
    pixmap = QPixmap(size, size)
    pixmap.fill(color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw overlapping tile shapes
    darker = color.darker(125)
    lighter = color.lighter(105)

    painter.setPen(Qt.PenStyle.NoPen)

    # First row of tiles (darker)
    painter.setBrush(darker)
    painter.drawRoundedRect(0, 0, 11, 8, 2, 2)
    painter.drawRoundedRect(12, 0, 11, 8, 2, 2)

    # Second row of tiles (offset, lighter)
    painter.setBrush(lighter)
    painter.drawRoundedRect(6, 6, 11, 8, 2, 2)
    painter.drawRoundedRect(-6, 6, 11, 8, 2, 2)
    painter.drawRoundedRect(18, 6, 11, 8, 2, 2)

    # Third row of tiles (darker)
    painter.setBrush(darker)
    painter.drawRoundedRect(0, 12, 11, 8, 2, 2)
    painter.drawRoundedRect(12, 12, 11, 8, 2, 2)

    # Fourth row of tiles (offset, lighter)
    painter.setBrush(lighter)
    painter.drawRoundedRect(6, 18, 11, 8, 2, 2)
    painter.drawRoundedRect(-6, 18, 11, 8, 2, 2)
    painter.drawRoundedRect(18, 18, 11, 8, 2, 2)

    painter.end()
    return QBrush(pixmap)
