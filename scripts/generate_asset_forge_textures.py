"""Procedural texture generator for the asset-forge pilot (US-E9, #264).

Generates the pilot fill-pattern textures DETERMINISTICALLY (fixed seed,
pure Pillow) in the established house style: 256×256, flat illustrative,
muted naturalistic palette, top-down. Seamlessness is by construction —
every primitive is stamped at (x, y) AND at all ±W/±H wrap offsets, so the
tile has no seam to hide.

Provenance: running this script IS the asset's provenance — no external
generator, no model, no third-party license. Recorded per-file in
``src/open_garden_planner/resources/textures/PROVENANCE.md``.

Usage:  venv/Scripts/python.exe scripts/generate_asset_forge_textures.py
Regenerating with the same seed reproduces the committed PNGs.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 256


def _wrap_blur(img: Image.Image, radius: float) -> Image.Image:
    """Gaussian blur that WRAPS: Pillow's blur clamps at the borders and
    paints a subtle frame (a real seam); blurring a 3×3 tiling and
    cropping the center keeps the tile seamless."""
    tiled = Image.new("RGB", (SIZE * 3, SIZE * 3))
    for ix in range(3):
        for iy in range(3):
            tiled.paste(img, (ix * SIZE, iy * SIZE))
    blurred = tiled.filter(ImageFilter.GaussianBlur(radius))
    return blurred.crop((SIZE, SIZE, SIZE * 2, SIZE * 2))
TEXTURES_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "textures"
)


def _wrap_ellipse(draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, color) -> None:
    """Stamp an ellipse at every wrap offset — seamless by construction."""
    for dx in (-SIZE, 0, SIZE):
        for dy in (-SIZE, 0, SIZE):
            draw.ellipse(
                [x + dx, y + dy, x + dx + w, y + dy + h], fill=color
            )


def _wrap_line(draw: ImageDraw.ImageDraw, x1: float, y: float, x2: float, color, width: int = 1) -> None:
    """Horizontal line segment stamped at every x/y wrap offset."""
    for dx in (-SIZE, 0, SIZE):
        for dy in (-SIZE, 0, SIZE):
            draw.line([x1 + dx, y + dy, x2 + dx, y + dy], fill=color, width=width)


def generate_decking(rng: random.Random) -> Image.Image:
    """Weathered timber decking: 4 VERTICAL boards per tile + grain.

    Boards run vertically like the existing wood.png — the grain then
    crosses the y-wrap smoothly and the board gaps repeat exactly at the
    x-wrap (64 px pitch divides the tile)."""
    base = (154, 138, 115)
    img = Image.new("RGB", (SIZE, SIZE), base)
    draw = ImageDraw.Draw(img)
    board_w = SIZE // 4  # 64 px pitch — exact horizontal repeat
    gap = 4
    board_tones = [
        (158, 142, 118),
        (147, 131, 108),
        (162, 147, 124),
        (151, 136, 112),
    ]
    for index in range(4):
        left = index * board_w
        draw.rectangle(
            [left, 0, left + board_w - gap, SIZE], fill=board_tones[index]
        )
        # Grain: long muted VERTICAL streaks, wrap-stamped in y.
        for _ in range(26):
            x = rng.uniform(left + 3, left + board_w - gap - 3)
            y = rng.uniform(0, SIZE)
            length = rng.uniform(30, 140)
            tone = rng.choice([-14, -9, -5, 6, 9])
            r, g, b = board_tones[index]
            color = (r + tone, g + tone, b + tone)
            for dy in (-SIZE, 0, SIZE):
                draw.line([x, y + dy, x, y + dy + length], fill=color, width=1)
        # Occasional knot.
        if rng.random() < 0.8:
            kx = rng.uniform(left + 8, left + board_w - gap - 12)
            ky = rng.uniform(0, SIZE)
            r, g, b = board_tones[index]
            _wrap_ellipse(draw, kx, ky, 5, 7, (r - 24, g - 24, b - 22))
            _wrap_ellipse(draw, kx + 1.5, ky + 2, 2, 3, (r - 38, g - 38, b - 34))
        # Board gap shadow.
        draw.rectangle(
            [left + board_w - gap, 0, left + board_w - 1, SIZE],
            fill=(118, 105, 88),
        )
    return _wrap_blur(img, 0.4)


def generate_corten(rng: random.Random) -> Image.Image:
    """Corten (weathering) steel: muted rust mottle, subtle streaking."""
    base = (146, 90, 58)
    img = Image.new("RGB", (SIZE, SIZE), base)
    draw = ImageDraw.Draw(img)
    # Large soft patches, then medium, then speckle — all wrap-stamped.
    palette_large = [(155, 99, 64), (137, 82, 52), (150, 94, 60), (129, 76, 47)]
    for _ in range(28):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        w = rng.uniform(46, 110)
        h = rng.uniform(30, 80)
        _wrap_ellipse(draw, x, y, w, h, rng.choice(palette_large))
    img = _wrap_blur(img, 6)
    draw = ImageDraw.Draw(img)
    palette_mid = [(160, 104, 66), (128, 74, 44), (149, 96, 60), (118, 68, 42)]
    for _ in range(70):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        w = rng.uniform(10, 34)
        h = rng.uniform(8, 26)
        _wrap_ellipse(draw, x, y, w, h, rng.choice(palette_mid))
    img = _wrap_blur(img, 2.2)
    draw = ImageDraw.Draw(img)
    for _ in range(240):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        s = rng.uniform(1.2, 3.6)
        tone = rng.choice([(168, 112, 72), (122, 70, 42), (140, 86, 54)])
        _wrap_ellipse(draw, x, y, s, s * 0.8, tone)
    return _wrap_blur(img, 0.7)


def main() -> None:
    rng = random.Random(42)  # noqa: S311 — art, not crypto; fixed for reproducibility
    decking = generate_decking(rng)
    corten = generate_corten(rng)
    decking.save(TEXTURES_DIR / "decking.png")
    corten.save(TEXTURES_DIR / "corten.png")
    print(f"wrote {TEXTURES_DIR / 'decking.png'}")
    print(f"wrote {TEXTURES_DIR / 'corten.png'}")


if __name__ == "__main__":
    main()
