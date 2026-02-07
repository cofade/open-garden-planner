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
