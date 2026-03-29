"""Generate tileable PNG textures for the garden planner.

Run this script to regenerate texture assets in resources/textures/.
Requires PyQt6 to be installed.

Usage:
    python scripts/generate_textures.py
"""

import math
import random
import sys
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication

# Ensure QApplication exists for QPainter
app = QApplication.instance() or QApplication(sys.argv)

TEXTURE_SIZE = 256
OUTPUT_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "textures"
)


def _seeded_random(seed: int) -> random.Random:
    """Create a seeded random instance for reproducible textures."""
    return random.Random(seed)


def generate_grass_texture() -> QPixmap:
    """Generate a tileable grass texture with natural blade patterns."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(90, 150, 60)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(42)

    # Layer 1: Background color variation patches
    for _ in range(60):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(15, 50)
        h = rng.randint(15, 50)
        variation = rng.randint(-20, 20)
        c = QColor(
            max(0, min(255, base.red() + variation)),
            max(0, min(255, base.green() + variation + rng.randint(-10, 10))),
            max(0, min(255, base.blue() + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.3)
        # Wrap around for tileability
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)
        if x + w > size and y + h > size:
            painter.drawEllipse(x - size, y - size, w, h)

    painter.setOpacity(1.0)

    # Layer 2: Individual grass blades
    for _ in range(800):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        blade_len = rng.randint(4, 14)
        angle = rng.gauss(0, 15)  # Mostly upright with variation
        green_var = rng.randint(-30, 30)
        c = QColor(
            max(0, min(255, 70 + green_var // 2)),
            max(0, min(255, 140 + green_var)),
            max(0, min(255, 40 + green_var // 3)),
        )
        pen = QPen(c)
        pen.setWidthF(rng.uniform(0.5, 1.5))
        painter.setPen(pen)

        dx = blade_len * math.sin(math.radians(angle))
        dy = -blade_len * math.cos(math.radians(angle))
        painter.drawLine(QPointF(x, y), QPointF(x + dx, y + dy))
        # Wrap for tileability
        if x + dx > size or x + dx < 0:
            painter.drawLine(
                QPointF(x - size if x > size // 2 else x + size, y),
                QPointF(x - size + dx if x > size // 2 else x + size + dx, y + dy),
            )
        if y + dy > size or y + dy < 0:
            painter.drawLine(
                QPointF(x, y - size if y > size // 2 else y + size),
                QPointF(x + dx, y - size + dy if y > size // 2 else y + size + dy),
            )

    # Layer 3: Lighter highlights
    for _ in range(150):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        c = QColor(130, 190, 80)
        pen = QPen(c)
        pen.setWidthF(0.7)
        painter.setPen(pen)
        blade_len = rng.randint(3, 8)
        angle = rng.gauss(0, 10)
        dx = blade_len * math.sin(math.radians(angle))
        dy = -blade_len
        painter.drawLine(QPointF(x, y), QPointF(x + dx, y + dy))

    painter.end()
    return pixmap


def generate_gravel_texture() -> QPixmap:
    """Generate a tileable gravel/stone texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(170, 165, 155)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(123)

    # Draw many small stones
    for _ in range(350):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(4, 14)
        h = rng.randint(3, 12)

        grey = rng.randint(120, 210)
        variation = rng.randint(-15, 15)
        c = QColor(grey + variation, grey + variation - 5, grey + variation - 10)

        painter.setPen(QPen(c.darker(130), 0.5))
        painter.setBrush(QBrush(c))
        painter.drawEllipse(x, y, w, h)
        # Wrap
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    # Add some darker shadow dots between stones
    for _ in range(200):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        r = rng.uniform(0.5, 2.0)
        c = QColor(100, 95, 85)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.4)
        painter.drawEllipse(QPointF(x, y), r, r)

    painter.setOpacity(1.0)
    painter.end()
    return pixmap


def generate_concrete_texture() -> QPixmap:
    """Generate a tileable concrete/pavement texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(190, 188, 183)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(456)

    # Surface noise - small speckles
    for _ in range(2000):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        grey = rng.randint(160, 210)
        c = QColor(grey, grey - 2, grey - 4)
        painter.setPen(QPen(c, 0.5))
        painter.drawPoint(x, y)

    # Larger mottled patches
    for _ in range(40):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(20, 60)
        h = rng.randint(20, 60)
        variation = rng.randint(-10, 10)
        c = QColor(
            190 + variation,
            188 + variation,
            183 + variation,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.25)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Fine surface cracks (subtle)
    for _ in range(8):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        c = QColor(160, 155, 150)
        pen = QPen(c, 0.3)
        painter.setPen(pen)
        length = rng.randint(15, 50)
        segments = rng.randint(2, 5)
        cx, cy = float(x), float(y)
        for _ in range(segments):
            dx = rng.uniform(-length / segments, length / segments)
            dy = rng.uniform(-length / segments, length / segments)
            painter.drawLine(QPointF(cx, cy), QPointF(cx + dx, cy + dy))
            cx += dx
            cy += dy

    painter.end()
    return pixmap


def generate_wood_texture() -> QPixmap:
    """Generate a tileable wood deck board texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(165, 120, 75)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(789)

    # Draw horizontal wood grain lines across the full width
    y = 0.0
    while y < size:
        spacing = rng.uniform(2.0, 5.0)
        y += spacing
        variation = rng.randint(-15, 15)
        c = QColor(
            max(0, min(255, 150 + variation)),
            max(0, min(255, 105 + variation)),
            max(0, min(255, 60 + variation)),
        )
        pen = QPen(c, rng.uniform(0.3, 1.2))
        painter.setPen(pen)

        # Draw slightly wavy line for natural grain
        points = []
        for x in range(0, size + 1, 4):
            wave = rng.uniform(-0.8, 0.8)
            points.append(QPointF(x, y + wave))
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

    # Add board separation lines (vertical gaps between deck boards)
    board_width = rng.randint(55, 70)
    x = board_width
    while x < size:
        c = QColor(100, 70, 40)
        pen = QPen(c, 2.0)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, 0), QPointF(x, size))

        # Shadow edge
        c2 = QColor(130, 90, 55)
        pen2 = QPen(c2, 1.0)
        painter.setPen(pen2)
        painter.drawLine(QPointF(x + 2, 0), QPointF(x + 2, size))

        x += board_width

    # Add subtle knot marks
    for _ in range(3):
        kx = rng.randint(10, size - 10)
        ky = rng.randint(10, size - 10)
        kr = rng.randint(4, 10)
        c = QColor(130, 85, 45)
        painter.setPen(QPen(c.darker(120), 0.8))
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.5)
        painter.drawEllipse(QPointF(kx, ky), kr, kr * 0.7)

    painter.setOpacity(1.0)
    painter.end()
    return pixmap


def generate_water_texture() -> QPixmap:
    """Generate a tileable water texture with ripple effects."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(65, 145, 200)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(321)

    # Color variation patches for depth
    for _ in range(30):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(30, 80)
        h = rng.randint(30, 80)
        blue_var = rng.randint(-20, 20)
        c = QColor(
            max(0, min(255, 55 + blue_var // 2)),
            max(0, min(255, 135 + blue_var)),
            max(0, min(255, 195 + blue_var)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.2)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Ripple/wave lines
    for wave_y in range(0, size, 12):
        offset = rng.uniform(0, 2 * math.pi)
        amplitude = rng.uniform(1.5, 4.0)
        freq = rng.uniform(0.02, 0.05)
        lightness = rng.randint(160, 220)
        c = QColor(lightness, lightness + 20, 255)
        pen = QPen(c, rng.uniform(0.5, 1.5))
        painter.setPen(pen)
        painter.setOpacity(rng.uniform(0.15, 0.35))

        points = []
        for x in range(0, size + 1, 3):
            wy = wave_y + amplitude * math.sin(freq * x + offset)
            points.append(QPointF(x, wy))
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

    painter.setOpacity(1.0)

    # Light sparkle/reflection dots
    for _ in range(50):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        r = rng.uniform(0.5, 2.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(200, 230, 255)))
        painter.setOpacity(rng.uniform(0.1, 0.3))
        painter.drawEllipse(QPointF(x, y), r, r)

    painter.setOpacity(1.0)
    painter.end()
    return pixmap


def generate_soil_texture() -> QPixmap:
    """Generate a tileable soil/earth texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(115, 80, 50)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(654)

    # Background variation
    for _ in range(50):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(20, 70)
        h = rng.randint(20, 70)
        variation = rng.randint(-20, 20)
        c = QColor(
            max(0, min(255, 115 + variation)),
            max(0, min(255, 80 + variation)),
            max(0, min(255, 50 + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.3)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Soil clumps and particles
    for _ in range(300):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(2, 8)
        h = rng.randint(2, 7)
        brown_var = rng.randint(-30, 30)
        c = QColor(
            max(0, min(255, 100 + brown_var)),
            max(0, min(255, 65 + brown_var)),
            max(0, min(255, 35 + brown_var)),
        )
        painter.setPen(QPen(c.darker(120), 0.3))
        painter.setBrush(QBrush(c))
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    # Small pebbles
    for _ in range(30):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(3, 7)
        h = rng.randint(2, 6)
        grey = rng.randint(130, 170)
        c = QColor(grey, grey - 10, grey - 20)
        painter.setPen(QPen(c.darker(130), 0.4))
        painter.setBrush(QBrush(c))
        painter.drawEllipse(x, y, w, h)

    # Tiny organic matter
    for _ in range(100):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        c = QColor(80, 55, 30)
        painter.setPen(QPen(c, 0.5))
        l = rng.randint(1, 4)
        angle = rng.uniform(0, math.pi)
        dx = l * math.cos(angle)
        dy = l * math.sin(angle)
        painter.drawLine(QPointF(x, y), QPointF(x + dx, y + dy))

    painter.end()
    return pixmap


def generate_mulch_texture() -> QPixmap:
    """Generate a tileable mulch/bark texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(120, 75, 40)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(987)

    # Background variation
    for _ in range(40):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(25, 70)
        h = rng.randint(25, 70)
        variation = rng.randint(-15, 15)
        c = QColor(
            max(0, min(255, 120 + variation)),
            max(0, min(255, 75 + variation)),
            max(0, min(255, 40 + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.3)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Bark pieces - elongated rectangles at various angles
    for _ in range(250):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(8, 25)
        h = rng.randint(3, 8)
        angle = rng.uniform(0, 180)
        brown_var = rng.randint(-35, 35)
        c = QColor(
            max(0, min(255, 115 + brown_var)),
            max(0, min(255, 70 + brown_var)),
            max(0, min(255, 35 + brown_var)),
        )

        painter.save()
        painter.translate(x, y)
        painter.rotate(angle)
        painter.setPen(QPen(c.darker(130), 0.5))
        painter.setBrush(QBrush(c))
        painter.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), 2, 2)
        painter.restore()

        # Wrap check (simplified - draw at wrapped positions too)
        if x < w:
            painter.save()
            painter.translate(x + size, y)
            painter.rotate(angle)
            painter.setPen(QPen(c.darker(130), 0.5))
            painter.setBrush(QBrush(c))
            painter.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), 2, 2)
            painter.restore()
        if x > size - w:
            painter.save()
            painter.translate(x - size, y)
            painter.rotate(angle)
            painter.setPen(QPen(c.darker(130), 0.5))
            painter.setBrush(QBrush(c))
            painter.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), 2, 2)
            painter.restore()
        if y < h:
            painter.save()
            painter.translate(x, y + size)
            painter.rotate(angle)
            painter.setPen(QPen(c.darker(130), 0.5))
            painter.setBrush(QBrush(c))
            painter.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), 2, 2)
            painter.restore()
        if y > size - h:
            painter.save()
            painter.translate(x, y - size)
            painter.rotate(angle)
            painter.setPen(QPen(c.darker(130), 0.5))
            painter.setBrush(QBrush(c))
            painter.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), 2, 2)
            painter.restore()

    painter.end()
    return pixmap


def generate_sand_texture() -> QPixmap:
    """Generate a tileable sand texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(210, 195, 160)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(555)

    # Broad color variation
    for _ in range(50):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(25, 80)
        h = rng.randint(25, 80)
        variation = rng.randint(-12, 12)
        c = QColor(
            max(0, min(255, 210 + variation)),
            max(0, min(255, 195 + variation)),
            max(0, min(255, 160 + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.2)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Individual sand grains
    for _ in range(3000):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        sand_var = rng.randint(-20, 20)
        c = QColor(
            max(0, min(255, 205 + sand_var)),
            max(0, min(255, 190 + sand_var)),
            max(0, min(255, 155 + sand_var)),
        )
        painter.setPen(QPen(c, 0.5))
        painter.drawPoint(x, y)

    # Slightly larger grains scattered
    for _ in range(200):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        r = rng.uniform(0.5, 1.5)
        sand_var = rng.randint(-25, 25)
        c = QColor(
            max(0, min(255, 200 + sand_var)),
            max(0, min(255, 185 + sand_var)),
            max(0, min(255, 150 + sand_var)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.drawEllipse(QPointF(x, y), r, r)

    # Subtle wind ripple lines
    for wy in range(0, size, 20):
        offset = rng.uniform(0, 2 * math.pi)
        amplitude = rng.uniform(1.0, 3.0)
        freq = rng.uniform(0.015, 0.04)
        c = QColor(195, 180, 145)
        pen = QPen(c, 0.5)
        painter.setPen(pen)
        painter.setOpacity(0.2)

        points = []
        for x in range(0, size + 1, 4):
            sy = wy + amplitude * math.sin(freq * x + offset)
            points.append(QPointF(x, sy))
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

    painter.setOpacity(1.0)
    painter.end()
    return pixmap


def generate_stone_texture() -> QPixmap:
    """Generate a tileable stone paving texture with rectangular stones and grout."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    grout_color = QColor(140, 135, 125)
    pixmap.fill(grout_color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(777)

    # Draw stone paving pattern (brick-like layout)
    stone_h = 40
    stone_w = 60
    grout_w = 3

    for row in range(0, size + stone_h, stone_h + grout_w):
        offset = (stone_w // 2) if ((row // (stone_h + grout_w)) % 2 == 1) else 0
        for col in range(-stone_w, size + stone_w, stone_w + grout_w):
            x = col + offset
            y = row

            # Stone color with variation
            grey = rng.randint(165, 205)
            variation = rng.randint(-10, 10)
            c = QColor(grey + variation, grey + variation - 3, grey + variation - 8)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            stone_rect = QRectF(x, y, stone_w, stone_h)
            painter.drawRect(stone_rect)

            # Wrap for tileability
            if x + stone_w > size:
                painter.drawRect(QRectF(x - size, y, stone_w, stone_h))
            if y + stone_h > size:
                painter.drawRect(QRectF(x, y - size, stone_w, stone_h))
            if x + stone_w > size and y + stone_h > size:
                painter.drawRect(QRectF(x - size, y - size, stone_w, stone_h))
            if x < 0:
                painter.drawRect(QRectF(x + size, y, stone_w, stone_h))
                if y + stone_h > size:
                    painter.drawRect(QRectF(x + size, y - size, stone_w, stone_h))

            # Add surface texture to each stone
            for _ in range(15):
                sx = x + rng.randint(2, stone_w - 2)
                sy = y + rng.randint(2, stone_h - 2)
                sc = QColor(grey + rng.randint(-15, 15), grey + rng.randint(-15, 15), grey + rng.randint(-18, 12))
                painter.setPen(QPen(sc, 0.4))
                painter.drawPoint(int(sx) % size, int(sy) % size)

    painter.end()
    return pixmap


def generate_roof_tiles_texture() -> QPixmap:
    """Generate a tileable roof tile texture with overlapping scalloped rows."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(175, 90, 60)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(111)

    tile_w = 40
    tile_h = 30

    for row_idx in range(0, size // tile_h + 2):
        y = row_idx * tile_h
        offset = (tile_w // 2) if (row_idx % 2 == 1) else 0

        for col in range(-tile_w, size + tile_w, tile_w):
            x = col + offset

            # Tile color variation
            variation = rng.randint(-20, 20)
            c = QColor(
                max(0, min(255, 175 + variation)),
                max(0, min(255, 90 + variation // 2)),
                max(0, min(255, 60 + variation // 3)),
            )

            # Draw scalloped tile shape
            painter.setPen(QPen(c.darker(140), 1.0))
            painter.setBrush(QBrush(c))

            # Arc-based tile
            tile_rect = QRectF(x, y - tile_h // 4, tile_w, tile_h + tile_h // 4)
            painter.drawRoundedRect(tile_rect, tile_w // 4, tile_h // 4)

            # Highlight at top of tile
            highlight = QColor(
                min(255, c.red() + 20),
                min(255, c.green() + 15),
                min(255, c.blue() + 10),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(highlight))
            painter.setOpacity(0.3)
            painter.drawRect(QRectF(x + 2, y, tile_w - 4, tile_h // 4))
            painter.setOpacity(1.0)

            # Wrap
            wrapped_x = x % size if x >= 0 else x + size
            if wrapped_x + tile_w > size:
                painter.setPen(QPen(c.darker(140), 1.0))
                painter.setBrush(QBrush(c))
                painter.drawRoundedRect(
                    QRectF(wrapped_x - size, y - tile_h // 4, tile_w, tile_h + tile_h // 4),
                    tile_w // 4,
                    tile_h // 4,
                )

    painter.end()
    return pixmap


def generate_glass_texture() -> QPixmap:
    """Generate a tileable greenhouse glass pane texture.

    Renders a grid of rectangular glass panes separated by thin
    silver/aluminium frame mullions, with subtle reflections and
    transparency variations to look like a real glasshouse roof.
    """
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    # Light sky-blue tinted glass base
    pixmap.fill(QColor(210, 230, 245))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(2024)

    pane_w = 64  # pane width  (4 columns in 256px)
    pane_h = 64  # pane height (4 rows in 256px)
    frame_w = 3  # mullion thickness

    # Draw panes
    for row in range(0, size, pane_h):
        for col in range(0, size, pane_w):
            # Each pane has a slightly different blue/green tint
            blue_var = rng.randint(-12, 12)
            green_var = rng.randint(-8, 8)
            pane_color = QColor(
                max(0, min(255, 200 + blue_var // 2)),
                max(0, min(255, 228 + green_var)),
                max(0, min(255, 242 + blue_var)),
            )

            # Pane interior (inside the frame)
            pane_rect = QRectF(
                col + frame_w,
                row + frame_w,
                pane_w - frame_w * 2,
                pane_h - frame_w * 2,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(pane_color))
            painter.drawRect(pane_rect)

            # Subtle diagonal reflection highlight across each pane
            painter.setOpacity(0.15)
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            # Highlight strip (top-left to lower area)
            highlight_points = [
                QPointF(col + frame_w, row + frame_w),
                QPointF(col + pane_w * 0.45, row + frame_w),
                QPointF(col + frame_w, row + pane_h * 0.45),
            ]
            from PyQt6.QtGui import QPolygonF
            painter.drawPolygon(QPolygonF(highlight_points))

            # Second smaller highlight
            painter.setOpacity(0.08)
            highlight2 = [
                QPointF(col + pane_w * 0.5, row + frame_w),
                QPointF(col + pane_w * 0.7, row + frame_w),
                QPointF(col + frame_w, row + pane_h * 0.7),
                QPointF(col + frame_w, row + pane_h * 0.5),
            ]
            painter.drawPolygon(QPolygonF(highlight2))
            painter.setOpacity(1.0)

    # Draw frame/mullion grid on top
    frame_color = QColor(180, 185, 190)  # Silver/aluminium
    frame_highlight = QColor(210, 215, 220)  # Lighter edge
    frame_shadow = QColor(145, 150, 155)  # Darker edge

    # Horizontal mullions
    for row in range(0, size + 1, pane_h):
        y = row % size
        # Shadow line
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(frame_shadow))
        painter.drawRect(QRectF(0, y, size, 1))
        # Main frame
        painter.setBrush(QBrush(frame_color))
        painter.drawRect(QRectF(0, y + 1, size, frame_w - 2))
        # Highlight line
        painter.setBrush(QBrush(frame_highlight))
        painter.drawRect(QRectF(0, y + frame_w - 1, size, 1))

    # Vertical mullions
    for col in range(0, size + 1, pane_w):
        x = col % size
        painter.setBrush(QBrush(frame_shadow))
        painter.drawRect(QRectF(x, 0, 1, size))
        painter.setBrush(QBrush(frame_color))
        painter.drawRect(QRectF(x + 1, 0, frame_w - 2, size))
        painter.setBrush(QBrush(frame_highlight))
        painter.drawRect(QRectF(x + frame_w - 1, 0, 1, size))

    painter.end()
    return pixmap


def generate_hedge_texture() -> QPixmap:
    """Generate a tileable hedge texture with fine dense foliage dots."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(40, 82, 24)  # Dark green base
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(314)

    # Layer 1: Subtle background color variation (small patches for depth)
    for _ in range(60):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(6, 18)
        h = rng.randint(6, 18)
        variation = rng.randint(-12, 12)
        c = QColor(
            max(0, min(255, 40 + variation)),
            max(0, min(255, 82 + variation * 2)),
            max(0, min(255, 24 + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.4)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Layer 2: Fine foliage clusters (many small blobs)
    for _ in range(350):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        r = rng.uniform(1.5, 5.5)
        green_var = rng.randint(-15, 35)
        c = QColor(
            max(0, min(255, 48 + green_var // 3)),
            max(0, min(255, 108 + green_var)),
            max(0, min(255, 28 + green_var // 4)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(rng.uniform(0.55, 0.85))
        ry = r * rng.uniform(0.65, 1.0)
        painter.drawEllipse(QPointF(x, y), r, ry)
        if x + r > size:
            painter.drawEllipse(QPointF(x - size, y), r, ry)
        if y + ry > size:
            painter.drawEllipse(QPointF(x, y - size), r, ry)

    painter.setOpacity(1.0)

    # Layer 3: Fine highlight dots (light leaf tips)
    for _ in range(600):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        r = rng.uniform(0.5, 2.2)
        green_var = rng.randint(15, 55)
        c = QColor(
            max(0, min(255, 58 + green_var // 4)),
            max(0, min(255, 128 + green_var)),
            max(0, min(255, 32 + green_var // 5)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(rng.uniform(0.45, 0.8))
        painter.drawEllipse(QPointF(x, y), r, r)
        if x + r > size:
            painter.drawEllipse(QPointF(x - size, y), r, r)
        if y + r > size:
            painter.drawEllipse(QPointF(x, y - size), r, r)

    painter.setOpacity(1.0)

    # Layer 4: Tiny dark shadow dots (depth between leaves)
    for _ in range(250):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        r = rng.uniform(0.5, 1.8)
        c = QColor(18, 44, 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(rng.uniform(0.35, 0.65))
        painter.drawEllipse(QPointF(x, y), r, r)

    painter.setOpacity(1.0)
    painter.end()
    return pixmap


def generate_brick_texture() -> QPixmap:
    """Generate a tileable running bond brick pattern."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    mortar = QColor(195, 190, 180)
    pixmap.fill(mortar)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(1100)

    brick_w = 50
    brick_h = 22
    mortar_w = 3

    for row_idx in range(0, size // (brick_h + mortar_w) + 2):
        y = row_idx * (brick_h + mortar_w)
        offset = (brick_w // 2 + mortar_w // 2) if (row_idx % 2 == 1) else 0

        for col in range(-brick_w, size + brick_w, brick_w + mortar_w):
            x = col + offset
            variation = rng.randint(-18, 18)
            c = QColor(
                max(0, min(255, 165 + variation)),
                max(0, min(255, 75 + variation // 2)),
                max(0, min(255, 55 + variation // 3)),
            )

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            brick_rect = QRectF(x, y, brick_w, brick_h)
            painter.drawRect(brick_rect)

            # Surface speckle on brick
            for _ in range(8):
                sx = x + rng.randint(2, brick_w - 2)
                sy = y + rng.randint(2, brick_h - 2)
                sc = QColor(
                    max(0, min(255, c.red() + rng.randint(-12, 12))),
                    max(0, min(255, c.green() + rng.randint(-8, 8))),
                    max(0, min(255, c.blue() + rng.randint(-6, 6))),
                )
                painter.setPen(QPen(sc, 0.5))
                painter.drawPoint(int(sx) % size, int(sy) % size)
            painter.setPen(Qt.PenStyle.NoPen)

            # Wrap for tileability
            if x + brick_w > size:
                painter.setBrush(QBrush(c))
                painter.drawRect(QRectF(x - size, y, brick_w, brick_h))
            if y + brick_h > size:
                painter.setBrush(QBrush(c))
                painter.drawRect(QRectF(x, y - size, brick_w, brick_h))
            if x < 0:
                painter.setBrush(QBrush(c))
                painter.drawRect(QRectF(x + size, y, brick_w, brick_h))

    painter.end()
    return pixmap


def generate_bark_texture() -> QPixmap:
    """Generate a tileable tree bark texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(95, 65, 40)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(1200)

    # Background patches
    for _ in range(40):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(20, 60)
        h = rng.randint(30, 80)
        variation = rng.randint(-15, 15)
        c = QColor(
            max(0, min(255, 95 + variation)),
            max(0, min(255, 65 + variation)),
            max(0, min(255, 40 + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.3)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Vertical bark ridges (wavy vertical lines)
    x_pos = 0.0
    while x_pos < size:
        spacing = rng.uniform(6, 14)
        x_pos += spacing
        dark_var = rng.randint(-20, 10)
        c = QColor(
            max(0, min(255, 60 + dark_var)),
            max(0, min(255, 38 + dark_var)),
            max(0, min(255, 22 + dark_var)),
        )
        pen = QPen(c, rng.uniform(1.0, 3.0))
        painter.setPen(pen)
        painter.setOpacity(rng.uniform(0.4, 0.8))

        points = []
        for y in range(0, size + 1, 4):
            wave = rng.uniform(-2.5, 2.5)
            points.append(QPointF(x_pos + wave, y))
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

        # Wrap
        if x_pos < 10:
            for i in range(len(points) - 1):
                p1 = QPointF(points[i].x() + size, points[i].y())
                p2 = QPointF(points[i + 1].x() + size, points[i + 1].y())
                painter.drawLine(p1, p2)

    painter.setOpacity(1.0)

    # Horizontal cross-hatching (short marks)
    for _ in range(200):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        length = rng.randint(4, 15)
        c = QColor(70, 45, 25)
        painter.setPen(QPen(c, rng.uniform(0.3, 1.0)))
        painter.setOpacity(rng.uniform(0.2, 0.5))
        painter.drawLine(QPointF(x, y), QPointF(x + length, y + rng.uniform(-1, 1)))

    painter.setOpacity(1.0)

    # Light highlights
    for _ in range(100):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        c = QColor(140, 105, 70)
        painter.setPen(QPen(c, 0.5))
        painter.setOpacity(rng.uniform(0.2, 0.4))
        painter.drawPoint(x, y)

    painter.setOpacity(1.0)
    painter.end()
    return pixmap


def generate_wildflower_texture() -> QPixmap:
    """Generate a tileable wildflower meadow texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(85, 140, 55)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(1300)

    # Grass base variation
    for _ in range(50):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(15, 50)
        h = rng.randint(15, 50)
        variation = rng.randint(-15, 15)
        c = QColor(
            max(0, min(255, 85 + variation)),
            max(0, min(255, 140 + variation)),
            max(0, min(255, 55 + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.3)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Grass blades (shorter than pure grass texture)
    for _ in range(400):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        blade_len = rng.randint(3, 10)
        angle = rng.gauss(0, 15)
        green_var = rng.randint(-25, 25)
        c = QColor(
            max(0, min(255, 65 + green_var // 2)),
            max(0, min(255, 130 + green_var)),
            max(0, min(255, 40 + green_var // 3)),
        )
        painter.setPen(QPen(c, rng.uniform(0.4, 1.2)))
        dx = blade_len * math.sin(math.radians(angle))
        dy = -blade_len * math.cos(math.radians(angle))
        painter.drawLine(QPointF(x, y), QPointF(x + dx, y + dy))

    # Flower heads - scattered colored dots
    flower_colors = [
        QColor(240, 220, 50),   # Yellow
        QColor(255, 180, 200),  # Pink
        QColor(200, 160, 240),  # Lavender
        QColor(255, 255, 240),  # White
        QColor(255, 140, 60),   # Orange
        QColor(220, 80, 80),    # Red
        QColor(100, 160, 240),  # Blue
    ]
    for _ in range(120):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        r = rng.uniform(1.5, 4.0)
        c = rng.choice(flower_colors)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(rng.uniform(0.5, 0.85))
        painter.drawEllipse(QPointF(x, y), r, r)
        if x + r > size:
            painter.drawEllipse(QPointF(x - size, y), r, r)
        if y + r > size:
            painter.drawEllipse(QPointF(x, y - size), r, r)

    painter.setOpacity(1.0)
    painter.end()
    return pixmap


def generate_terracotta_texture() -> QPixmap:
    """Generate a tileable terracotta tile texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    grout = QColor(190, 180, 165)
    pixmap.fill(grout)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(1400)

    tile_size = 62
    grout_w = 3

    for row in range(0, size + tile_size, tile_size + grout_w):
        for col in range(0, size + tile_size, tile_size + grout_w):
            x = col
            y = row
            variation = rng.randint(-15, 15)
            c = QColor(
                max(0, min(255, 195 + variation)),
                max(0, min(255, 110 + variation // 2)),
                max(0, min(255, 70 + variation // 3)),
            )

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            tile_rect = QRectF(x, y, tile_size, tile_size)
            painter.drawRect(tile_rect)

            # Surface speckling
            for _ in range(20):
                sx = x + rng.randint(2, tile_size - 2)
                sy = y + rng.randint(2, tile_size - 2)
                sc = QColor(
                    max(0, min(255, c.red() + rng.randint(-15, 15))),
                    max(0, min(255, c.green() + rng.randint(-10, 10))),
                    max(0, min(255, c.blue() + rng.randint(-8, 8))),
                )
                painter.setPen(QPen(sc, 0.5))
                painter.drawPoint(int(sx) % size, int(sy) % size)
            painter.setPen(Qt.PenStyle.NoPen)

            # Wrap
            if x + tile_size > size:
                painter.setBrush(QBrush(c))
                painter.drawRect(QRectF(x - size, y, tile_size, tile_size))
            if y + tile_size > size:
                painter.setBrush(QBrush(c))
                painter.drawRect(QRectF(x, y - size, tile_size, tile_size))

    painter.end()
    return pixmap


def generate_pebbles_texture() -> QPixmap:
    """Generate a tileable river pebbles texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(170, 160, 145)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(1500)

    # Background sandy fill
    for _ in range(40):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(20, 60)
        h = rng.randint(20, 60)
        variation = rng.randint(-10, 10)
        c = QColor(
            max(0, min(255, 170 + variation)),
            max(0, min(255, 160 + variation)),
            max(0, min(255, 145 + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.25)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Smooth pebbles - larger than gravel, rounder
    for _ in range(90):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        rx = rng.randint(8, 18)
        ry = rng.randint(6, 15)
        angle = rng.uniform(0, 180)

        grey = rng.randint(120, 210)
        warm = rng.randint(-10, 15)
        c = QColor(
            max(0, min(255, grey + warm)),
            max(0, min(255, grey + warm - 5)),
            max(0, min(255, grey - 5)),
        )

        painter.save()
        painter.translate(x, y)
        painter.rotate(angle)
        # Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(80, 75, 65)))
        painter.setOpacity(0.25)
        painter.drawEllipse(QRectF(-rx + 2, -ry + 2, rx * 2, ry * 2))
        # Pebble
        painter.setOpacity(1.0)
        painter.setPen(QPen(c.darker(130), 0.5))
        painter.setBrush(QBrush(c))
        painter.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))
        # Highlight
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 250)))
        painter.setOpacity(0.2)
        painter.drawEllipse(QRectF(-rx * 0.4, -ry * 0.5, rx * 0.6, ry * 0.5))
        painter.restore()

        # Wrap
        if x + rx > size:
            painter.save()
            painter.translate(x - size, y)
            painter.rotate(angle)
            painter.setPen(QPen(c.darker(130), 0.5))
            painter.setBrush(QBrush(c))
            painter.setOpacity(1.0)
            painter.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))
            painter.restore()
        if y + ry > size:
            painter.save()
            painter.translate(x, y - size)
            painter.rotate(angle)
            painter.setPen(QPen(c.darker(130), 0.5))
            painter.setBrush(QBrush(c))
            painter.setOpacity(1.0)
            painter.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))
            painter.restore()

    painter.end()
    return pixmap


def generate_slate_texture() -> QPixmap:
    """Generate a tileable slate slab texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    gap_color = QColor(100, 95, 85)
    pixmap.fill(gap_color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(1600)

    # Irregular slate rectangles
    slab_h_base = 45
    slab_w_base = 80
    gap = 3

    y = 0
    while y < size + slab_h_base:
        slab_h = slab_h_base + rng.randint(-8, 8)
        x = rng.randint(-20, 0)
        while x < size + slab_w_base:
            slab_w = slab_w_base + rng.randint(-20, 20)

            grey = rng.randint(55, 85)
            variation = rng.randint(-8, 8)
            c = QColor(grey + variation, grey + variation + 2, grey + variation + 5)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            slab_rect = QRectF(x, y, slab_w - gap, slab_h - gap)
            painter.drawRect(slab_rect)

            # Surface scoring lines
            for _ in range(rng.randint(1, 3)):
                sx = x + rng.randint(5, max(6, slab_w - 10))
                sy = y + rng.randint(2, max(3, slab_h - 5))
                sl = rng.randint(10, 30)
                sc = QColor(grey - 10, grey - 8, grey - 5)
                painter.setPen(QPen(sc, 0.5))
                painter.setOpacity(0.4)
                painter.drawLine(
                    QPointF(sx, sy),
                    QPointF(sx + sl + rng.uniform(-3, 3), sy + rng.uniform(-2, 2)),
                )
                painter.setOpacity(1.0)

            # Wrap
            if x + slab_w > size:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(c))
                painter.drawRect(QRectF(x - size, y, slab_w - gap, slab_h - gap))
            if y + slab_h > size:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(c))
                painter.drawRect(QRectF(x, y - size, slab_w - gap, slab_h - gap))

            x += slab_w
        y += slab_h

    painter.end()
    return pixmap


def generate_lattice_texture() -> QPixmap:
    """Generate a tileable trellis/lattice diamond pattern."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    # Background visible through lattice gaps
    bg = QColor(180, 200, 160)
    pixmap.fill(bg)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(1700)

    strip_w = 8
    spacing = 28  # Diamond opening size

    # Diagonal strips at +45 degrees
    wood_color_1 = QColor(165, 120, 70)
    for i in range(-size, size * 2, spacing):
        variation = rng.randint(-10, 10)
        c = QColor(
            max(0, min(255, wood_color_1.red() + variation)),
            max(0, min(255, wood_color_1.green() + variation)),
            max(0, min(255, wood_color_1.blue() + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        # Draw strip from top-left to bottom-right
        points = [
            QPointF(i, 0),
            QPointF(i + strip_w, 0),
            QPointF(i + strip_w + size, size),
            QPointF(i + size, size),
        ]
        from PyQt6.QtGui import QPolygonF
        painter.drawPolygon(QPolygonF(points))

        # Shadow edge
        painter.setPen(QPen(c.darker(140), 0.5))
        painter.drawLine(QPointF(i + size, size), QPointF(i, 0))

    # Diagonal strips at -45 degrees (crossing)
    wood_color_2 = QColor(155, 112, 65)
    for i in range(-size, size * 2, spacing):
        variation = rng.randint(-10, 10)
        c = QColor(
            max(0, min(255, wood_color_2.red() + variation)),
            max(0, min(255, wood_color_2.green() + variation)),
            max(0, min(255, wood_color_2.blue() + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        points = [
            QPointF(i, size),
            QPointF(i + strip_w, size),
            QPointF(i + strip_w + size, 0),
            QPointF(i + size, 0),
        ]
        painter.drawPolygon(QPolygonF(points))

    painter.end()
    return pixmap


def generate_compost_texture() -> QPixmap:
    """Generate a tileable composted soil texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(55, 38, 22)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(1800)

    # Dark background variation
    for _ in range(50):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(20, 65)
        h = rng.randint(20, 65)
        variation = rng.randint(-10, 10)
        c = QColor(
            max(0, min(255, 55 + variation)),
            max(0, min(255, 38 + variation)),
            max(0, min(255, 22 + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.35)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Organic debris - small leaf/twig fragments
    for _ in range(180):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        length = rng.randint(3, 12)
        angle = rng.uniform(0, math.pi)
        brown_var = rng.randint(-15, 20)
        c = QColor(
            max(0, min(255, 80 + brown_var)),
            max(0, min(255, 55 + brown_var)),
            max(0, min(255, 30 + brown_var)),
        )
        painter.setPen(QPen(c, rng.uniform(0.5, 1.8)))
        painter.setOpacity(rng.uniform(0.4, 0.7))
        dx = length * math.cos(angle)
        dy = length * math.sin(angle)
        painter.drawLine(QPointF(x, y), QPointF(x + dx, y + dy))

    painter.setOpacity(1.0)

    # Worm-like curves
    for _ in range(15):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        c = QColor(
            max(0, min(255, 90 + rng.randint(-10, 10))),
            max(0, min(255, 60 + rng.randint(-10, 10))),
            max(0, min(255, 35 + rng.randint(-5, 5))),
        )
        painter.setPen(QPen(c, rng.uniform(0.8, 1.5)))
        painter.setOpacity(0.5)
        cx, cy = float(x), float(y)
        for _ in range(rng.randint(3, 6)):
            dx = rng.uniform(-8, 8)
            dy = rng.uniform(-8, 8)
            painter.drawLine(QPointF(cx, cy), QPointF(cx + dx, cy + dy))
            cx += dx
            cy += dy

    painter.setOpacity(1.0)

    # Light specks (perlite/mineral)
    for _ in range(80):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        r = rng.uniform(0.5, 2.0)
        c = QColor(200, 195, 180)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(rng.uniform(0.3, 0.6))
        painter.drawEllipse(QPointF(x, y), r, r)
        if x + r > size:
            painter.drawEllipse(QPointF(x - size, y), r, r)
        if y + r > size:
            painter.drawEllipse(QPointF(x, y - size), r, r)

    painter.setOpacity(1.0)
    painter.end()
    return pixmap


def generate_flagstone_texture() -> QPixmap:
    """Generate a tileable flagstone paving texture with irregular polygons."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    mortar = QColor(165, 155, 140)
    pixmap.fill(mortar)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(1900)

    # Generate irregular stones using a grid with jittered centers
    cell_size = 55
    gap = 4

    for row in range(-1, size // cell_size + 2):
        for col in range(-1, size // cell_size + 2):
            cx = col * cell_size + cell_size // 2 + rng.randint(-8, 8)
            cy = row * cell_size + cell_size // 2 + rng.randint(-8, 8)

            # Generate irregular polygon (6-8 vertices)
            n_verts = rng.randint(5, 7)
            stone_r = cell_size // 2 - gap
            points = []
            for v in range(n_verts):
                angle = (v / n_verts) * 2 * math.pi + rng.uniform(-0.3, 0.3)
                r = stone_r + rng.randint(-8, 5)
                px = cx + r * math.cos(angle)
                py = cy + r * math.sin(angle)
                points.append(QPointF(px, py))

            grey = rng.randint(155, 200)
            warm = rng.randint(-8, 12)
            c = QColor(
                max(0, min(255, grey + warm)),
                max(0, min(255, grey + warm - 3)),
                max(0, min(255, grey - 5)),
            )

            from PyQt6.QtGui import QPolygonF
            painter.setPen(QPen(c.darker(130), 0.8))
            painter.setBrush(QBrush(c))
            painter.drawPolygon(QPolygonF(points))

            # Surface texture specks
            for _ in range(8):
                sx = cx + rng.randint(-stone_r, stone_r)
                sy = cy + rng.randint(-stone_r, stone_r)
                sc = QColor(
                    max(0, min(255, c.red() + rng.randint(-12, 12))),
                    max(0, min(255, c.green() + rng.randint(-10, 10))),
                    max(0, min(255, c.blue() + rng.randint(-8, 8))),
                )
                painter.setPen(QPen(sc, 0.4))
                painter.drawPoint(int(sx) % size, int(sy) % size)

    painter.end()
    return pixmap


def generate_clay_texture() -> QPixmap:
    """Generate a tileable clay surface texture."""
    size = TEXTURE_SIZE
    pixmap = QPixmap(size, size)
    base = QColor(175, 110, 65)
    pixmap.fill(base)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rng = _seeded_random(2000)

    # Background variation
    for _ in range(50):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        w = rng.randint(25, 80)
        h = rng.randint(25, 80)
        variation = rng.randint(-15, 15)
        c = QColor(
            max(0, min(255, 175 + variation)),
            max(0, min(255, 110 + variation)),
            max(0, min(255, 65 + variation)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.setOpacity(0.25)
        painter.drawEllipse(x, y, w, h)
        if x + w > size:
            painter.drawEllipse(x - size, y, w, h)
        if y + h > size:
            painter.drawEllipse(x, y - size, w, h)

    painter.setOpacity(1.0)

    # Surface speckles
    for _ in range(2000):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        variation = rng.randint(-20, 20)
        c = QColor(
            max(0, min(255, 170 + variation)),
            max(0, min(255, 105 + variation)),
            max(0, min(255, 60 + variation)),
        )
        painter.setPen(QPen(c, 0.5))
        painter.drawPoint(x, y)

    # Crack lines
    for _ in range(12):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        c = QColor(130, 75, 40)
        painter.setPen(QPen(c, rng.uniform(0.3, 1.0)))
        painter.setOpacity(rng.uniform(0.25, 0.55))

        cx, cy = float(x), float(y)
        length = rng.randint(20, 80)
        segments = rng.randint(3, 7)
        for _ in range(segments):
            dx = rng.uniform(-length / segments, length / segments)
            dy = rng.uniform(-length / (segments * 3), length / (segments * 3))
            painter.drawLine(QPointF(cx, cy), QPointF(cx + dx, cy + dy))
            cx += dx
            cy += dy

    painter.setOpacity(1.0)

    # Fine horizontal scratches for clay-like feel
    for _ in range(30):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        length = rng.randint(15, 50)
        c = QColor(155, 95, 50)
        painter.setPen(QPen(c, 0.4))
        painter.setOpacity(rng.uniform(0.15, 0.35))
        painter.drawLine(QPointF(x, y), QPointF(x + length, y + rng.uniform(-1, 1)))

    painter.setOpacity(1.0)
    painter.end()
    return pixmap


def main() -> None:
    """Generate all textures and save to resources/textures/."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    textures = {
        "grass": generate_grass_texture,
        "gravel": generate_gravel_texture,
        "concrete": generate_concrete_texture,
        "wood": generate_wood_texture,
        "water": generate_water_texture,
        "soil": generate_soil_texture,
        "mulch": generate_mulch_texture,
        "sand": generate_sand_texture,
        "stone": generate_stone_texture,
        "roof_tiles": generate_roof_tiles_texture,
        "glass": generate_glass_texture,
        "hedge": generate_hedge_texture,
        "brick": generate_brick_texture,
        "bark": generate_bark_texture,
        "wildflower": generate_wildflower_texture,
        "terracotta": generate_terracotta_texture,
        "pebbles": generate_pebbles_texture,
        "slate": generate_slate_texture,
        "lattice": generate_lattice_texture,
        "compost": generate_compost_texture,
        "flagstone": generate_flagstone_texture,
        "clay": generate_clay_texture,
    }

    for name, generator in textures.items():
        print(f"Generating {name}...")
        pixmap = generator()
        output_path = OUTPUT_DIR / f"{name}.png"
        pixmap.save(str(output_path), "PNG")
        print(f"  Saved to {output_path} ({output_path.stat().st_size} bytes)")

    print(f"\nAll {len(textures)} textures generated in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
