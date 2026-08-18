"""Procedural texture forge — the single source of every fill-pattern texture.

Package 3b (#309, ADR-042, FR-30) regenerated ALL 24 textures in
``src/open_garden_planner/resources/textures/`` in the "Lush" language of
the #281 plant sprites and the #308 object sprites: visible material detail,
radial rim-dark → crown-light shading per element, concentric occlusion
halos, mottled grounds — rich, but in a contrast band where the runtime tint
(``core/fill_patterns._tint_texture``, user colour at 80/255 alpha) still
recolours the material instead of flattening it.

Design contract (docs §8.5 / ADR-042 3b section):

- 256×256 px RGB PNG, 1 texture px = 1 cm on the canvas (a tile is 2.56 m).
- Strictly top-down; **no directional light** — the canvas view flips Y and
  fills rotate with nothing, so every shading cue is radial/concentric.
- Seamless BY CONSTRUCTION: every primitive is painted on a torus (window
  indices are taken modulo the canvas), noise fields are periodic lattices,
  structured layouts (courses, planks, laths) divide the tile exactly.
- Pixel-deterministic: all randomness comes from ``random.Random(seed_str)``
  (stream-stable across CPython versions), all painting is float64 numpy
  with sequential accumulation (no rasterizer, no reduction whose order can
  vary), Pillow only ENCODES the final uint8 array. ``--check`` regenerates
  in memory and compares the DECODED PIXELS of the committed PNGs (PNG is
  lossless; the deflate stream itself depends on the zlib build Pillow
  bundles, so file bytes are deliberately not the contract);
  ``tests/unit/test_asset_forge_textures.py`` pins it. The former
  ``ImageFilter.GaussianBlur`` (Pillow-version-dependent) is gone —
  ``wrap_blur`` is an in-repo separable Gaussian with ``np.roll``.
- Provenance = this script (``resources/textures/PROVENANCE.md``).

Usage:
    venv/Scripts/python.exe scripts/generate_asset_forge_textures.py
    venv/Scripts/python.exe scripts/generate_asset_forge_textures.py --check
    venv/Scripts/python.exe scripts/generate_asset_forge_textures.py --only soil grass
"""

from __future__ import annotations

import argparse
import io
import math
import random
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 256
SS = 2  # supersample factor — painted at 512², box-downsampled to 256²
C = SIZE * SS
TEXTURES_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "textures"
)

Color = tuple[float, float, float]

# --------------------------------------------------------------------------- #
# colour helpers
# --------------------------------------------------------------------------- #


def shade(c: Color, f: float) -> Color:
    return (c[0] * f, c[1] * f, c[2] * f)


def mix(a: Color, b: Color, t: float) -> Color:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def jitter(rng: random.Random, c: Color, amount: float) -> Color:
    """Per-element tone variation: multiply by a random factor around 1."""
    f = 1.0 + rng.uniform(-amount, amount)
    return shade(c, f)


# --------------------------------------------------------------------------- #
# periodic fields (numpy, float64, seamless on the C×C torus)
# --------------------------------------------------------------------------- #


def _smooth(f: np.ndarray) -> np.ndarray:
    return f * f * (3.0 - 2.0 * f)


def lattice_noise(rng: random.Random, cells: int) -> np.ndarray:
    """Periodic value noise in [0, 1]: a cells×cells lattice of Python-rng
    values, bilinearly interpolated with smoothstep, wrapping at the edges."""
    vals = np.array(
        [[rng.random() for _ in range(cells)] for _ in range(cells)], dtype=np.float64
    )
    u = np.arange(C, dtype=np.float64) * (cells / C)
    i0 = np.floor(u).astype(np.int64) % cells
    i1 = (i0 + 1) % cells
    f = _smooth(u - np.floor(u))
    fx = f[None, :]
    fy = f[:, None]
    v00 = vals[np.ix_(i0, i0)]
    v10 = vals[np.ix_(i0, i1)]
    v01 = vals[np.ix_(i1, i0)]
    v11 = vals[np.ix_(i1, i1)]
    top = v00 * (1.0 - fx) + v10 * fx
    bot = v01 * (1.0 - fx) + v11 * fx
    return top * (1.0 - fy) + bot * fy


def fbm(rng: random.Random, cells: int, octaves: int, gain: float = 0.5) -> np.ndarray:
    """Fractal sum of lattice noise, normalised to [0, 1] (mean ≈ 0.5)."""
    total = np.zeros((C, C), dtype=np.float64)
    amp = 1.0
    norm = 0.0
    for k in range(octaves):
        total = total + lattice_noise(rng, cells * (2**k)) * amp
        norm += amp
        amp *= gain
    return total / norm


def fine_grain(rng: random.Random) -> np.ndarray:
    """Near-per-pixel grain in [-0.5, 0.5] (lattice at half canvas res)."""
    return lattice_noise(rng, C // 2) - 0.5


def voronoi(
    rng: random.Random,
    grid: int,
    warp: tuple[np.ndarray, np.ndarray] | None = None,
    jitter_amt: float = 0.85,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Torus Voronoi from a jittered grid×grid seed set (no slivers).

    Returns (d1, d2, cell_id) — distance to the nearest and second-nearest
    seed and the nearest seed's index — in CANVAS px. ``warp`` = periodic
    (dx, dy) fields added to the sample coordinates for organic cell edges."""
    pitch = C / grid
    seeds = []
    for j in range(grid):
        for i in range(grid):
            sx = (i + 0.5) * pitch + rng.uniform(-0.5, 0.5) * jitter_amt * pitch
            sy = (j + 0.5) * pitch + rng.uniform(-0.5, 0.5) * jitter_amt * pitch
            seeds.append((sx, sy))
    ys, xs = np.mgrid[0:C, 0:C].astype(np.float64)
    if warp is not None:
        xs = xs + warp[0]
        ys = ys + warp[1]
    d1 = np.full((C, C), np.inf)
    d2 = np.full((C, C), np.inf)
    cid = np.zeros((C, C), dtype=np.int64)
    for k, (sx, sy) in enumerate(seeds):
        dx = ((xs - sx + C / 2) % C) - C / 2
        dy = ((ys - sy + C / 2) % C) - C / 2
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        d1 = np.where(closer, d, d1)
        cid = np.where(closer, k, cid)
    return d1, d2, cid


def _gauss_kernel(sigma: float) -> np.ndarray:
    r = max(1, int(math.ceil(3.0 * sigma)))
    w = np.array([math.exp(-(i * i) / (2.0 * sigma * sigma)) for i in range(-r, r + 1)])
    return w / w.sum()


def wrap_blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur that WRAPS (np.roll) — seamless, in-repo,
    independent of Pillow's filter implementation. sigma in canvas px."""
    if sigma <= 0:
        return arr
    k = _gauss_kernel(sigma)
    r = len(k) // 2
    out = np.zeros_like(arr)
    for i, w in enumerate(k):
        out = out + np.roll(arr, i - r, axis=1) * w
    out2 = np.zeros_like(arr)
    for i, w in enumerate(k):
        out2 = out2 + np.roll(out, i - r, axis=0) * w
    return out2


# --------------------------------------------------------------------------- #
# the torus painter
# --------------------------------------------------------------------------- #


class Tile:
    """A float64 RGB canvas at C×C on which primitives are painted with
    analytic anti-aliased coverage; every window is indexed modulo C, so
    anything crossing an edge continues on the opposite side.

    All primitive coordinates/sizes are in TILE units (0..256 = cm)."""

    def __init__(self, bg: Color) -> None:
        self.a = np.empty((C, C, 3), dtype=np.float64)
        self.a[:, :] = np.array(bg, dtype=np.float64)

    # -- windows ---------------------------------------------------------- #

    def _window(
        self, cx: float, cy: float, rx: float, ry: float
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        cx, cy, rx, ry = cx * SS, cy * SS, rx * SS, ry * SS
        x0 = int(math.floor(cx - rx - 2))
        x1 = int(math.ceil(cx + rx + 2))
        y0 = int(math.floor(cy - ry - 2))
        y1 = int(math.ceil(cy + ry + 2))
        if x1 - x0 >= C:  # too wide to window — use the whole width, torus metric
            xs = np.arange(C, dtype=np.float64)
            X = ((xs - cx + C / 2) % C) - C / 2
        else:
            xs = np.arange(x0, x1 + 1, dtype=np.float64)
            X = xs - cx
        if y1 - y0 >= C:
            ys = np.arange(C, dtype=np.float64)
            Y = ((ys - cy + C / 2) % C) - C / 2
        else:
            ys = np.arange(y0, y1 + 1, dtype=np.float64)
            Y = ys - cy
        return ys.astype(np.int64) % C, xs.astype(np.int64) % C, X[None, :], Y[:, None]

    def _paint(
        self,
        iy: np.ndarray,
        ix: np.ndarray,
        cov: np.ndarray,
        color: np.ndarray | Color,
        clip_wrap: bool = False,
        y_raw: np.ndarray | None = None,
    ) -> None:
        if clip_wrap and y_raw is not None:
            inside = (y_raw >= 0) & (y_raw < C)
            cov = cov * inside
        col = np.asarray(color, dtype=np.float64)
        sub = self.a[np.ix_(iy, ix)]
        c3 = cov[..., None]
        sub = sub * (1.0 - c3) + col * c3
        self.a[np.ix_(iy, ix)] = sub

    # -- primitives ------------------------------------------------------- #

    @staticmethod
    def _rot(X: np.ndarray, Y: np.ndarray, rot_deg: float) -> tuple[np.ndarray, np.ndarray]:
        if rot_deg == 0.0:
            return X, Y
        a = math.radians(rot_deg)
        ca, sa = math.cos(a), math.sin(a)
        return X * ca + Y * sa, -X * sa + Y * ca

    def ellipse(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        color: Color,
        rot: float = 0.0,
        rim: float = 1.0,
        crown: float = 1.0,
        gamma: float = 1.0,
        soft: float = 0.0,
        alpha: float = 1.0,
        clip_wrap: bool = False,
    ) -> None:
        """Ellipse with radial shading: colour × rim at the edge → × crown at
        the centre (gamma bends the ramp). ``soft`` > 0 feathers the edge
        over that many tile px (for occlusion halos)."""
        ext = max(rx, ry) + soft
        iy, ix, X, Y = self._window(cx, cy, ext, ext)
        u, v = self._rot(X, Y, rot)
        rxs, rys = rx * SS, ry * SS
        rho = np.sqrt((u / rxs) ** 2 + (v / rys) ** 2)
        rmin = min(rxs, rys)
        d = (rho - 1.0) * rmin  # ≈ signed distance in canvas px
        if soft > 0:
            cov = np.clip(1.0 - d / (soft * SS), 0.0, 1.0)
            cov = _smooth(cov)
        else:
            cov = np.clip(0.5 - d, 0.0, 1.0)
        cov = cov * alpha
        t = np.clip(1.0 - rho, 0.0, 1.0) ** gamma
        f = rim + (crown - rim) * t
        col = np.asarray(color, dtype=np.float64)[None, None, :] * f[..., None]
        y_raw = None
        if clip_wrap:  # raw (unwrapped) window rows, for painting only inside the tile
            y0 = int(math.floor(cy * SS - ext * SS - 2))
            y_raw = np.arange(y0, y0 + len(iy))[:, None] * np.ones((1, len(ix)))
        self._paint(iy, ix, cov, col, clip_wrap, y_raw)

    def halo(
        self, cx: float, cy: float, rx: float, ry: float, color: Color,
        rot: float = 0.0, grow: float = 1.3, soft: float | None = None, alpha: float = 0.6,
    ) -> None:
        """Concentric occlusion halo (dark, feathered) — draw BEFORE the body.
        Direction-free: only the visible ring around the body reads as
        contact shadow, exactly like the sprite art."""
        s = soft if soft is not None else max(1.0, 0.35 * min(rx, ry))
        self.ellipse(cx, cy, rx * grow, ry * grow, color, rot=rot, soft=s, alpha=alpha)

    def blob(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        color: Color,
        rot: float = 0.0,
        rim: float = 0.74,
        crown: float = 1.16,
        gamma: float = 0.8,
        occ: Color | None = None,
        occ_grow: float = 1.28,
        occ_alpha: float = 0.55,
        gloss: float = 0.0,
    ) -> None:
        """A shaded stone/clod/pebble: optional occlusion halo, radial body,
        optional small centred gloss spot."""
        if occ is not None:
            self.halo(cx, cy, rx, ry, occ, rot=rot, grow=occ_grow, alpha=occ_alpha)
        self.ellipse(cx, cy, rx, ry, color, rot=rot, rim=rim, crown=crown, gamma=gamma)
        if gloss > 0:
            self.ellipse(
                cx, cy, rx * 0.36, ry * 0.36, shade(color, crown * 1.12), rot=rot,
                soft=0.5 * min(rx, ry), alpha=gloss,
            )

    def capsule(
        self,
        x1: float, y1: float, x2: float, y2: float,
        w: float,
        color: Color,
        color2: Color | None = None,
        taper: float = 1.0,
        alpha: float = 1.0,
        rim: float = 1.0,
        crown: float = 1.0,
    ) -> None:
        """Rounded line from (x1,y1) to (x2,y2), width w; ``taper`` = width
        fraction remaining at the end (1 = constant width, ~0 = pointed
        blade). ``color2`` blends along the length (base → tip)."""
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        ext = max(abs(x2 - x1), abs(y2 - y1)) / 2 + w
        iy, ix, X, Y = self._window(cx, cy, ext, ext)
        ax, ay = (x1 - cx) * SS, (y1 - cy) * SS
        bx, by = (x2 - cx) * SS, (y2 - cy) * SS
        ex, ey = bx - ax, by - ay
        L2 = ex * ex + ey * ey
        if L2 <= 1e-9:
            return
        t = np.clip(((X - ax) * ex + (Y - ay) * ey) / L2, 0.0, 1.0)
        px, py = ax + t * ex, ay + t * ey
        dist = np.sqrt((X - px) ** 2 + (Y - py) ** 2)
        half = (w * SS / 2) * (1.0 - (1.0 - taper) * t)
        d = dist - half
        cov = np.clip(0.5 - d, 0.0, 1.0) * alpha
        if rim != 1.0 or crown != 1.0:
            q = np.clip(1.0 - dist / np.maximum(half, 1e-6), 0.0, 1.0)
            f = rim + (crown - rim) * q
        else:
            f = 1.0
        if color2 is not None:
            c1 = np.asarray(color, dtype=np.float64)
            c2 = np.asarray(color2, dtype=np.float64)
            col = c1[None, None, :] + (c2 - c1)[None, None, :] * t[..., None]
        else:
            col = np.asarray(color, dtype=np.float64)[None, None, :] * np.ones_like(t)[..., None]
        if not isinstance(f, float):
            col = col * f[..., None]
        self._paint(iy, ix, cov, col)

    def rect(
        self,
        cx: float, cy: float, w: float, h: float | None,
        color: Color,
        rot: float = 0.0,
        r: float = 0.0,
        bevel: float = 0.0,
        bevel_dark: float = 0.82,
        crown: float = 1.0,
        alpha: float = 1.0,
        clip_wrap: bool = False,
    ) -> None:
        """Rounded rectangle; ``bevel`` = width (tile px) of a darkened rim
        (bevel_dark at the edge → 1.0 inside), ``crown`` lightens the centre.
        ``h=None`` = a full-height plank (the distance field ignores v, so no
        top/bottom edge exists to wrap into a seam band)."""
        if h is None:
            iy, ix, X, Y = self._window(cx, 128.0, w / 2 + 2, 130.0)
            u, _v = self._rot(X, Y, rot)
            hw = w * SS / 2
            d = np.abs(u) - hw
            hh = 1e9
        else:
            ext = math.hypot(w, h) / 2 + 1
            iy, ix, X, Y = self._window(cx, cy, ext, ext)
            u, v = self._rot(X, Y, rot)
            hw, hh, rr = w * SS / 2, h * SS / 2, r * SS
            qx = np.abs(u) - (hw - rr)
            qy = np.abs(v) - (hh - rr)
            outside = np.sqrt(np.maximum(qx, 0.0) ** 2 + np.maximum(qy, 0.0) ** 2)
            inside = np.minimum(np.maximum(qx, qy), 0.0)
            d = outside + inside - rr  # signed distance
        cov = np.clip(0.5 - d, 0.0, 1.0) * alpha
        f = np.ones_like(d)
        if bevel > 0:
            depth = np.clip(-d / (bevel * SS), 0.0, 1.0)
            f = f * (bevel_dark + (1.0 - bevel_dark) * _smooth(depth))
        if crown != 1.0:
            # normalised inset 0 (edge) → 1 (centre)
            inset = np.clip(-d / max(min(hw, hh), 1e-6), 0.0, 1.0)
            f = f * (1.0 + (crown - 1.0) * _smooth(inset))
        col = np.asarray(color, dtype=np.float64)[None, None, :] * f[..., None]
        y_raw = None
        if clip_wrap and h is not None:
            y0 = int(math.floor(cy * SS - ext * SS - 2))
            y_raw = np.arange(y0, y0 + len(iy))[:, None] * np.ones((1, len(ix)))
        self._paint(iy, ix, cov, col, clip_wrap, y_raw)

    def leaf(
        self, cx: float, cy: float, length: float, width: float, rot: float,
        color: Color, rim: float = 0.86, crown: float = 1.12, alpha: float = 1.0,
        shift: float = 0.0,
    ) -> None:
        """Almond leaf (pointed both ends) along the local u axis."""
        ext = length / 2 + width + abs(shift)
        iy, ix, X, Y = self._window(cx, cy, ext, ext)
        u, v = self._rot(X, Y, rot)
        u = u - shift * SS
        L, W = length * SS / 2, width * SS / 2
        s = np.clip(u / L, -1.0, 1.0)
        halfw = W * np.cos(s * (math.pi / 2)) ** 0.75  # pointed almond
        d = np.abs(v) - halfw
        d = np.where(np.abs(u) > L, np.abs(u) - L, d)
        cov = np.clip(0.5 - d, 0.0, 1.0) * alpha
        q = np.clip(1.0 - np.abs(v) / np.maximum(halfw, 1e-6), 0.0, 1.0)
        f = rim + (crown - rim) * q
        col = np.asarray(color, dtype=np.float64)[None, None, :] * f[..., None]
        self._paint(iy, ix, cov, col)

    def vgrain(
        self, x: float, amp: float, k: int, phase: float, w: float, color: Color,
        alpha: float = 1.0, y_from: float | None = None, y_to: float | None = None,
        fade: float = 6.0,
    ) -> None:
        """A vertical wavy grain line x = x0 + amp·sin(2πk·y/256 + phase),
        seamless in y (k whole waves per tile). Optional soft y-range."""
        ext = amp + w + 1
        iy, ix, X, Y = self._window(x, 128.0, ext, 128.0 + 4)
        yy = (Y + 128.0 * SS)  # 0..C along the window (window spans full height)
        off = amp * SS * np.sin(2 * math.pi * k * yy / C + phase)
        d = np.abs(X - off) - w * SS / 2
        cov = np.clip(0.5 - d, 0.0, 1.0) * alpha
        if y_from is not None and y_to is not None:
            yt = (yy / SS) % SIZE
            a0, a1 = y_from % SIZE, y_to % SIZE
            if a0 <= a1:
                m = np.clip((yt - a0) / fade, 0, 1) * np.clip((a1 - yt) / fade, 0, 1)
            else:  # range wraps around the seam
                m = np.maximum(
                    np.clip((yt - a0) / fade, 0, 1),
                    np.clip((a1 - yt) / fade, 0, 1),
                )
            cov = cov * _smooth(m)
        self._paint(iy, ix, cov, np.asarray(color, dtype=np.float64))

    # -- whole-tile field operations -------------------------------------- #

    def mottle(self, rng: random.Random, cells: int, octaves: int, amp: float) -> None:
        f = 1.0 + (fbm(rng, cells, octaves) - 0.5) * 2.0 * amp
        self.a = self.a * f[..., None]

    def grain(self, rng: random.Random, amp: float) -> None:
        f = 1.0 + fine_grain(rng) * 2.0 * amp
        self.a = self.a * f[..., None]

    def multiply(self, field: np.ndarray) -> None:
        self.a = self.a * field[..., None]

    def blend(self, color: Color, weight: np.ndarray) -> None:
        col = np.asarray(color, dtype=np.float64)
        w3 = np.clip(weight, 0.0, 1.0)[..., None]
        self.a = self.a * (1.0 - w3) + col * w3

    # -- output ----------------------------------------------------------- #

    def finish(self, blur: float = 0.0) -> Image.Image:
        arr = self.a
        if blur > 0:
            arr = wrap_blur(arr, blur * SS)
        # box downsample by SS with a fixed, sequential accumulation order
        acc = np.zeros((SIZE, SIZE, 3), dtype=np.float64)
        for i in range(SS):
            for j in range(SS):
                acc = acc + arr[i::SS, j::SS, :]
        acc = acc / (SS * SS)
        out = np.clip(np.rint(acc), 0, 255).astype(np.uint8)
        return Image.fromarray(out, mode="RGB")


# --------------------------------------------------------------------------- #
# shared material helpers
# --------------------------------------------------------------------------- #


def scatter_stones(
    tile: Tile,
    rng: random.Random,
    n: int,
    r_range: tuple[float, float],
    palette: list[Color],
    occ: Color,
    elong: tuple[float, float] = (0.6, 1.0),
    rim: float = 0.74,
    crown: float = 1.16,
    gloss: float = 0.0,
    occ_grow: float = 1.3,
    occ_alpha: float = 0.5,
    tone_jitter: float = 0.06,
) -> None:
    for _ in range(n):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        r = rng.uniform(*r_range)
        e = rng.uniform(*elong)
        rot = rng.uniform(0, 180)
        col = jitter(rng, rng.choice(palette), tone_jitter)
        tile.blob(
            x, y, r, r * e, col, rot=rot, rim=rim, crown=crown, occ=occ,
            occ_grow=occ_grow, occ_alpha=occ_alpha, gloss=gloss,
        )


def grass_blades(
    tile: Tile,
    rng: random.Random,
    n: int,
    base: list[Color],
    tip: list[Color],
    length: tuple[float, float] = (6.0, 15.0),
    width: tuple[float, float] = (1.2, 2.0),
) -> None:
    for _ in range(n):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        L = rng.uniform(*length)
        a = rng.uniform(0, 2 * math.pi)
        i = rng.randrange(len(base))
        w = rng.uniform(*width)
        tile.capsule(
            x, y, x + L * math.cos(a), y + L * math.sin(a), w,
            base[i], tip[i], taper=0.05,
        )


def paver_courses(
    tile: Tile,
    rng: random.Random,
    rows: int,
    per_row: int,
    joint: float,
    palette: list[Color],
    bevel: float,
    bevel_dark: float,
    crown: float,
    r: float = 1.0,
    tone_jitter: float = 0.05,
    bond_offset: float = 0.5,
    wobble: float = 0.0,
    row_widths: bool = False,
    min_w: float = 0.0,
) -> list[tuple[float, float, float, float]]:
    """Running-bond courses that divide the tile exactly. Course boundaries
    are offset by half a pitch so no joint sits ON the wrap seam. Returns
    the placed (cx, cy, w, h) so callers can add per-paver detail."""
    pitch_y = SIZE / rows
    placed = []
    for row in range(rows):
        cy = (row + 0.5) * pitch_y
        h = pitch_y - joint
        if row_widths:
            # random cuts along the row (min width min_w) — one paver wraps
            cuts = []
            while len(cuts) < per_row:
                c = rng.uniform(0, SIZE)
                if all(min(abs(c - o), SIZE - abs(c - o)) >= min_w for o in cuts):
                    cuts.append(c)
            cuts.sort()
            spans = [(cuts[i], cuts[(i + 1) % per_row]) for i in range(per_row)]
            for x0, x1 in spans:
                if x1 <= x0:
                    x1 += SIZE
                w = (x1 - x0) - joint
                cx = (x0 + x1) / 2
                col = jitter(rng, rng.choice(palette), tone_jitter)
                tile.rect(cx, cy, w, h, col, r=r, bevel=bevel, bevel_dark=bevel_dark, crown=crown,
                          rot=rng.uniform(-wobble, wobble))
                placed.append((cx % SIZE, cy, w, h))
        else:
            pitch_x = SIZE / per_row
            off = (row % 2) * bond_offset * pitch_x
            for i in range(per_row):
                cx = (i + 0.5) * pitch_x + off
                w = pitch_x - joint
                col = jitter(rng, rng.choice(palette), tone_jitter)
                tile.rect(cx, cy, w, h, col, r=r, bevel=bevel, bevel_dark=bevel_dark, crown=crown,
                          rot=rng.uniform(-wobble, wobble))
                placed.append((cx % SIZE, cy, w, h))
    return placed


def speckle(tile: Tile, rng: random.Random, n: int, r_range: tuple[float, float],
            colors: list[Color], alpha: float = 1.0) -> None:
    for _ in range(n):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        r = rng.uniform(*r_range)
        tile.ellipse(x, y, r, r * rng.uniform(0.7, 1.0), rng.choice(colors),
                     rot=rng.uniform(0, 180), alpha=alpha)


# --------------------------------------------------------------------------- #
# generators — one per texture, ordered as in FillPattern
# --------------------------------------------------------------------------- #


def generate_grass(rng: random.Random) -> Image.Image:
    """Dense lawn: mottled dark ground, a shadow layer of dark blades, then
    two-tone blades (dark base → light tip) in four greens."""
    t = Tile((64, 118, 48))
    t.mottle(rng, 4, 3, 0.10)
    grass_blades(t, rng, 900, [(42, 86, 32)] * 2, [(58, 108, 44)] * 2, (5, 12), (1.4, 2.2))
    base = [(68, 128, 50), (76, 140, 54), (62, 120, 48), (84, 148, 58)]
    tip = [(128, 192, 86), (140, 204, 94), (116, 182, 80), (154, 212, 102)]
    grass_blades(t, rng, 2400, base, tip, (6, 15), (1.2, 1.9))
    return t.finish(blur=0.35)


def generate_gravel(rng: random.Random) -> Image.Image:
    """Crushed stone: fines ground, hundreds of small angular-ish stones with
    occlusion halos and rim→crown shading, in greys, tans and whites."""
    t = Tile((150, 142, 128))
    t.mottle(rng, 5, 3, 0.07)
    t.grain(rng, 0.05)
    palette = [
        (172, 166, 156), (188, 182, 172), (150, 146, 140), (204, 198, 188),
        (166, 154, 138), (140, 132, 122), (196, 186, 170), (158, 152, 148),
    ]
    scatter_stones(t, rng, 1500, (1.6, 4.4), palette, (96, 90, 82), elong=(0.55, 0.95),
                   rim=0.72, crown=1.18, occ_grow=1.35, occ_alpha=0.5)
    scatter_stones(t, rng, 500, (0.9, 1.8), palette, (96, 90, 82), elong=(0.7, 1.0),
                   rim=0.8, crown=1.12, occ_grow=1.3, occ_alpha=0.35)
    return t.finish(blur=0.3)


def generate_concrete(rng: random.Random) -> Image.Image:
    """Poured concrete: soft cloudy mottle, fine aggregate speckle, a few pits."""
    t = Tile((178, 176, 170))
    t.mottle(rng, 3, 4, 0.06)
    t.mottle(rng, 12, 2, 0.03)
    t.grain(rng, 0.03)
    speckle(t, rng, 900, (0.5, 1.3), [(150, 148, 142), (140, 138, 134), (196, 194, 188), (204, 202, 196)], alpha=0.8)
    for _ in range(40):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        r = rng.uniform(1.0, 2.2)
        t.ellipse(x, y, r, r * 0.8, (146, 144, 138), rot=rng.uniform(0, 180), rim=0.9, crown=1.06)
    return t.finish(blur=0.3)


def generate_wood(rng: random.Random) -> Image.Image:
    """Golden timber planks (8 per tile, 32 cm), wavy grain, knots, bevelled
    edges. Plank joints sit at x = 16 + 32k so the seam falls inside a plank."""
    base = (178, 138, 88)
    t = Tile(base)
    pitch = SIZE / 8
    tones = [(182, 142, 92), (172, 132, 84), (188, 148, 96), (168, 128, 82)]
    for i in range(8):
        cx = (i + 0.5) * pitch + pitch / 2
        col = jitter(rng, tones[i % 4], 0.03)
        t.rect(cx, 128, pitch - 1.6, None, col, bevel=1.6, bevel_dark=0.8, crown=1.03)
        # grain
        for _ in range(11):
            x = cx - pitch / 2 + rng.uniform(2.5, pitch - 2.5)
            dark = rng.random() < 0.7
            gcol = shade(col, rng.uniform(0.78, 0.9)) if dark else shade(col, rng.uniform(1.06, 1.12))
            t.vgrain(x, rng.uniform(0.6, 2.4), rng.choice([1, 1, 2, 3]), rng.uniform(0, 6.283),
                     rng.uniform(0.6, 1.3), gcol, alpha=rng.uniform(0.6, 1.0))
        # knot
        if rng.random() < 0.55:
            kx = cx - pitch / 2 + rng.uniform(7, pitch - 7)
            ky = rng.uniform(0, SIZE)
            k = shade(col, 0.72)
            t.ellipse(kx, ky, 4.2, 5.6, shade(col, 0.9), rot=rng.uniform(-8, 8), rim=0.86, crown=1.0)
            t.ellipse(kx, ky, 3.0, 4.2, k, rot=0, rim=1.0, crown=1.25, gamma=1.4)
            t.ellipse(kx, ky, 1.1, 1.6, shade(col, 0.55))
        # joint shadow line
        jx = cx + pitch / 2
        t.capsule(jx, -4, jx, SIZE + 4, 1.4, shade(base, 0.62))
    t.grain(rng, 0.025)
    return t.finish(blur=0.35)


def generate_water(rng: random.Random) -> Image.Image:
    """Pond water: depth mottle, a caustic light network (ridged fbm), soft
    ripple bands and sparkles — no directional glare."""
    t = Tile((56, 138, 200))
    depth = fbm(rng, 3, 3)
    t.multiply(0.84 + 0.30 * depth)
    n = fbm(rng, 5, 4, gain=0.55)
    ridged = 1.0 - np.abs(2.0 * n - 1.0)
    caustic = np.clip((ridged - 0.70) / 0.30, 0.0, 1.0) ** 2.0
    t.blend((186, 226, 248), caustic * 0.42)
    n2 = fbm(rng, 9, 3, gain=0.5)
    ridged2 = 1.0 - np.abs(2.0 * n2 - 1.0)
    caustic2 = np.clip((ridged2 - 0.76) / 0.24, 0.0, 1.0) ** 2.0
    t.blend((210, 238, 252), caustic2 * 0.26)
    ys = np.arange(C, dtype=np.float64)[:, None]
    xs = np.arange(C, dtype=np.float64)[None, :]
    ripple = np.sin(2 * math.pi * (3 * ys + 1 * xs) / C + 4.0 * (n - 0.5)) * 0.5 + 0.5
    t.multiply(1.0 - 0.05 * ripple)
    for _ in range(18):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        r = rng.uniform(0.8, 1.6)
        t.ellipse(x, y, r, r * 0.6, (236, 248, 255), rot=rng.uniform(0, 180), soft=1.2, alpha=0.7)
    return t.finish(blur=0.5)


def generate_soil(rng: random.Random) -> Image.Image:
    """Garden bed soil: warm brown ground, crumbly clods with occlusion, the
    odd small stone, sand and humus specks."""
    t = Tile((116, 78, 48))
    t.mottle(rng, 3, 4, 0.12)
    t.mottle(rng, 14, 2, 0.05)
    # damp patches (soft, direction-free)
    for _ in range(22):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        r = rng.uniform(10, 26)
        t.ellipse(x, y, r, r * rng.uniform(0.6, 1.0), (92, 60, 36), rot=rng.uniform(0, 180),
                  soft=r * 0.9, alpha=0.35)
    clods = [(126, 86, 54), (108, 72, 44), (136, 94, 58), (100, 66, 42), (120, 84, 52)]
    # crumbs: many small, softly shaded; a few larger clods with gentle halos
    scatter_stones(t, rng, 700, (0.9, 2.6), clods, (70, 46, 28), elong=(0.6, 1.0),
                   rim=0.86, crown=1.1, occ_grow=1.35, occ_alpha=0.3, tone_jitter=0.06)
    scatter_stones(t, rng, 120, (2.6, 6.0), clods, (70, 46, 28), elong=(0.6, 1.0),
                   rim=0.84, crown=1.1, occ_grow=1.25, occ_alpha=0.35, tone_jitter=0.06)
    scatter_stones(t, rng, 26, (1.3, 2.6), [(150, 138, 118), (134, 126, 112), (166, 154, 134)],
                   (70, 46, 28), elong=(0.6, 0.9), rim=0.78, crown=1.14, occ_alpha=0.4)
    speckle(t, rng, 260, (0.45, 0.95), [(164, 132, 92), (72, 48, 30), (176, 150, 110)], alpha=0.75)
    t.grain(rng, 0.06)
    return t.finish(blur=0.35)


def generate_mulch(rng: random.Random) -> Image.Image:
    """Bark mulch: dark humus ground, layered elongated chips in five browns
    with occlusion under each chip, a few pale fresh splinters."""
    t = Tile((70, 46, 28))
    t.mottle(rng, 4, 3, 0.10)
    chips = [(118, 76, 44), (134, 90, 54), (98, 62, 38), (148, 104, 64), (110, 70, 42),
             (150, 92, 58), (104, 78, 52), (128, 80, 46)]
    for _ in range(640):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        L = rng.uniform(8, 24)
        W = rng.uniform(3.4, 8.0)
        rot = rng.uniform(0, 180)
        col = jitter(rng, rng.choice(chips), 0.08)
        if rng.random() < 0.7:
            # flake: rounded, slightly irregular (two overlapping rounded rects)
            t.rect(x, y, L * 1.2, W * 1.35, (52, 34, 20), rot=rot, r=W * 0.7, alpha=0.4, bevel=W * 0.55, bevel_dark=0.0)
            t.rect(x, y, L, W, col, rot=rot, r=W * 0.5, bevel=1.1, bevel_dark=0.8, crown=1.08)
            t.rect(x + rng.uniform(-L * 0.2, L * 0.2), y, L * rng.uniform(0.5, 0.8), W * rng.uniform(0.6, 0.9),
                   shade(col, rng.uniform(0.94, 1.06)), rot=rot + rng.uniform(-14, 14), r=W * 0.4, bevel=1.0,
                   bevel_dark=0.85, crown=1.06)
        else:
            # chunk: elongated blob
            t.blob(x, y, L / 2, W / 2 * 0.9, col, rot=rot, rim=0.8, crown=1.1, occ=(52, 34, 20),
                   occ_grow=1.3, occ_alpha=0.4)
    for _ in range(50):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        L = rng.uniform(4, 9)
        a = rng.uniform(0, math.pi)
        t.capsule(x, y, x + L * math.cos(a), y + L * math.sin(a), 1.4, (176, 136, 90), alpha=0.9)
    return t.finish(blur=0.3)


def generate_roof_tiles(rng: random.Random) -> Image.Image:
    """Beaver-tail clay tiles: 12 staggered courses of rounded tiles, each
    row overlapping the one below, occlusion under every exposed edge."""
    bg = (128, 62, 44)
    t = Tile(bg)
    rows, per_row = 12, 16
    pitch_y = SIZE / rows
    pitch_x = SIZE / per_row
    tile_len = pitch_y * 1.55
    reds = [(192, 100, 68), (178, 90, 62), (204, 112, 76), (170, 86, 58), (186, 96, 64)]

    def draw_row(row: int, y_shift: float, clip: bool) -> None:
        y_top = row * pitch_y + y_shift
        off = (row % 2) * pitch_x / 2
        for i in range(per_row):
            cx = (i + 0.5) * pitch_x + off
            cy = y_top + tile_len / 2
            col = jitter(rng, reds[(i * 7 + row * 3) % len(reds)], 0.05)
            # occlusion halo (concentric, feathered) then body (rounded bottom)
            t.rect(cx, cy + 0.6, pitch_x - 0.4, tile_len + 1.2, (70, 32, 22), r=pitch_x * 0.46,
                   alpha=0.55, bevel=2.2, bevel_dark=0.0, clip_wrap=clip)
            t.rect(cx, cy, pitch_x - 1.6, tile_len, col, r=pitch_x * 0.42, bevel=1.4,
                   bevel_dark=0.8, crown=1.06, clip_wrap=clip)

    # bottom → top so each row overlaps the one below; then repaint the
    # bottom row's wrapped overhang so the seam layering matches the interior
    for row in range(rows - 1, -1, -1):
        draw_row(row, 0.0, False)
    rng_state = rng.getstate()
    draw_row(rows - 1, -SIZE, True)
    rng.setstate(rng_state)
    t.grain(rng, 0.03)
    speckle(t, rng, 160, (0.4, 0.9), [(150, 70, 48), (214, 130, 92)], alpha=0.6)
    return t.finish(blur=0.35)


def generate_sand(rng: random.Random) -> Image.Image:
    """Play/beach sand: pale ground, soft dune mottle, fine grain, quartz
    glints and darker grains."""
    t = Tile((220, 204, 170))
    t.mottle(rng, 3, 3, 0.05)
    t.mottle(rng, 16, 2, 0.025)
    t.grain(rng, 0.045)
    speckle(t, rng, 700, (0.4, 0.9), [(196, 178, 142), (186, 168, 132), (238, 228, 204), (244, 236, 214)], alpha=0.85)
    speckle(t, rng, 40, (0.9, 1.6), [(206, 190, 158), (232, 220, 194)], alpha=0.9)
    return t.finish(blur=0.3)


def generate_stone(rng: random.Random) -> Image.Image:
    """Sandstone pavers in running bond (10 courses × 6), warm/cool grey
    tone variation, bevelled edges, fine speckle, the odd chip."""
    t = Tile((132, 128, 122))
    t.grain(rng, 0.04)
    palette = [(190, 186, 178), (180, 176, 168), (198, 192, 180), (176, 174, 170), (186, 180, 168)]
    paver_courses(t, rng, 10, 6, 2.2, palette, bevel=1.8, bevel_dark=0.8, crown=1.04, r=1.2,
                  tone_jitter=0.04, wobble=0.4)
    t.mottle(rng, 5, 3, 0.05)
    speckle(t, rng, 500, (0.4, 1.0), [(160, 156, 148), (210, 206, 198), (150, 146, 140)], alpha=0.7)
    for _ in range(18):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        t.ellipse(x, y, rng.uniform(1.2, 2.4), rng.uniform(0.8, 1.6), (156, 152, 144), rot=rng.uniform(0, 180), rim=0.85, crown=1.1)
    return t.finish(blur=0.35)


def generate_glass(rng: random.Random) -> Image.Image:
    """Greenhouse glazing seen from above: 4×2 panes (64 × 128 cm) between
    glazing bars, pale sky-blue glass with soft symmetric sheen bands, per-pane
    tone, screw heads at the crossings."""
    t = Tile((198, 224, 240))
    ys = np.arange(C, dtype=np.float64)[:, None]
    xs = np.arange(C, dtype=np.float64)[None, :]
    panes_x, panes_y = 4, 2  # 64 × 128 cm glazing, taller than wide
    pitch_x, pitch_y = C / panes_x, C / panes_y
    # per-pane tone
    pi = np.floor(xs / pitch_x).astype(np.int64)
    pj = np.floor(ys / pitch_y).astype(np.int64)
    tones = np.array([[rng.uniform(0.965, 1.035) for _ in range(panes_x)] for _ in range(panes_y)])
    t.multiply(tones[pj, pi])
    # sheen: two soft diagonal bands per pane, symmetric (no light direction)
    u = (xs % pitch_x) / pitch_x
    v = (ys % pitch_y) / pitch_y
    band = np.exp(-((u + v - 0.55) ** 2) / 0.012) * 0.55 + np.exp(-((u + v - 1.30) ** 2) / 0.006) * 0.35
    t.blend((236, 246, 252), band * 0.9)
    # a faint inner vignette per pane (glass looks deeper toward the edges)
    edge = np.minimum(np.minimum(u, 1 - u) * pitch_x, np.minimum(v, 1 - v) * pitch_y) / pitch_x
    t.multiply(0.94 + 0.06 * _smooth(np.clip(edge / 0.18, 0, 1)))
    # glazing bars: rim-dark → centre-light aluminium
    bar_w = 3.2 * SS
    dx = np.abs(((xs + pitch_x / 2) % pitch_x) - pitch_x / 2)
    dy = np.abs(((ys + pitch_y / 2) % pitch_y) - pitch_y / 2)
    d = np.minimum(dx, dy)
    cov = np.clip(bar_w / 2 + 0.5 - d, 0, 1)
    depth = np.clip(1.0 - d / (bar_w / 2), 0, 1)
    shade_f = 0.78 + 0.34 * _smooth(depth)
    bar_col = np.array((206, 210, 214), dtype=np.float64)
    col = bar_col[None, None, :] * shade_f[..., None]
    t.a = t.a * (1 - cov[..., None]) + col * cov[..., None]
    # bar contact shadow onto the glass (concentric: both sides equally)
    shadow = np.clip(1.0 - (d - bar_w / 2) / (2.4 * SS), 0, 1) * (d > bar_w / 2)
    t.multiply(1.0 - 0.10 * _smooth(shadow))
    # tiny screw heads at bar crossings
    for j in range(panes_y):
        for i in range(panes_x):
            cx = (i * pitch_x) / SS
            cy = (j * pitch_y) / SS
            t.ellipse(cx, cy, 1.4, 1.4, (150, 154, 160), rim=0.85, crown=1.15)
    return t.finish(blur=0.3)


def generate_hedge(rng: random.Random) -> Image.Image:
    """Dense trimmed hedge in the #281 Lush leaf language: occluded
    overlapping almond leaves, dark → light two-tone (unchanged look from the
    2026-07 pilot, now anti-aliased through the numpy painter)."""
    t = Tile((16, 52, 30))
    occ = (9, 42, 22)
    bodies = [(35, 96, 55), (44, 112, 64), (29, 84, 48), (51, 122, 71)]
    for _ in range(300):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        length = rng.uniform(26, 38)
        width = length * rng.uniform(0.52, 0.62)
        angle = rng.uniform(0, 360)
        body = rng.choice(bodies)
        light = tuple(min(c + 26, 255) for c in body)
        t.leaf(x, y, length * 1.2, width * 1.2, angle, occ, rim=1.0, crown=1.0, alpha=0.9)
        t.leaf(x, y, length, width, angle, body, rim=0.84, crown=1.1)
        t.leaf(x, y, length * 0.55, width * 0.5, angle, light, rim=0.95, crown=1.08, shift=length * 0.16)
    return t.finish(blur=0.3)


def generate_brick(rng: random.Random) -> Image.Image:
    """Clay bricks in running bond (24 courses × 8), five reds, bevelled
    edges, per-brick tone, mortar with fine grain."""
    t = Tile((196, 186, 172))
    t.grain(rng, 0.05)
    reds = [(180, 74, 56), (162, 64, 48), (192, 90, 66), (152, 60, 46), (172, 82, 62), (186, 80, 58)]
    paver_courses(t, rng, 24, 8, 1.8, reds, bevel=1.1, bevel_dark=0.8, crown=1.05, r=0.6,
                  tone_jitter=0.05, wobble=0.35)
    t.mottle(rng, 6, 3, 0.05)
    speckle(t, rng, 300, (0.35, 0.8), [(130, 50, 38), (206, 110, 84)], alpha=0.5)
    return t.finish(blur=0.3)


def generate_bark(rng: random.Random) -> Image.Image:
    """Tree bark: vertical wavy ridges (light) between deep furrows (dark),
    inner ridge shading, short cross-cracks and lenticels."""
    base = (112, 82, 56)
    t = Tile((60, 42, 28))
    t.mottle(rng, 3, 3, 0.10)
    ridges = 12
    pitch = SIZE / ridges
    for i in range(ridges):
        x = (i + 0.5) * pitch + rng.uniform(-2.0, 2.0)
        w = pitch * rng.uniform(0.5, 0.72)
        col = jitter(rng, base, 0.06)
        k0, ph0, amp0 = rng.choice([1, 2, 2, 3]), rng.uniform(0, 6.283), rng.uniform(1.5, 3.5)
        # broad ridge bed (dark, soft edge via two widths)
        t.vgrain(x, amp0, k0, ph0, w, shade(col, 0.78))
        t.vgrain(x, amp0, k0, ph0, w * 0.86, shade(col, 0.9))
        # 2–3 wandering sub-ridges: own wave → they split and merge like real bark
        for _ in range(rng.randint(2, 3)):
            k, ph, amp = rng.choice([1, 2, 3]), rng.uniform(0, 6.283), rng.uniform(1.0, 3.5)
            sw = w * rng.uniform(0.26, 0.42)
            sx = x + rng.uniform(-w * 0.28, w * 0.28)
            tone = rng.uniform(0.98, 1.16)
            t.vgrain(sx, amp, k, ph, sw, shade(col, tone), alpha=0.95)
            t.vgrain(sx + rng.uniform(-0.6, 0.6), amp, k, ph, sw * 0.4, shade(col, tone * 1.1), alpha=0.7)
        # a dark longitudinal fissure
        t.vgrain(x + rng.uniform(-w * 0.3, w * 0.3), rng.uniform(1.0, 3.0), rng.choice([1, 2, 3]),
                 rng.uniform(0, 6.283), rng.uniform(0.6, 1.1), (44, 30, 20), alpha=0.7)
        # short offset cross-cracks (never the full ridge width) and lenticels
        for _ in range(4):
            yy = rng.uniform(0, SIZE)
            xx = x + rng.uniform(-w * 0.3, w * 0.3)
            L = w * rng.uniform(0.2, 0.42)
            t.capsule(xx - L / 2, yy, xx + L / 2, yy + rng.uniform(-1.5, 1.5), rng.uniform(0.7, 1.1),
                      (44, 30, 20), alpha=0.6)
        for _ in range(2):
            t.ellipse(x + rng.uniform(-w * 0.3, w * 0.3), rng.uniform(0, SIZE), 1.6, 0.7,
                      (50, 34, 22), rot=rng.uniform(-10, 10), alpha=0.8)
        # deep furrow accents between ridges (soft, elongated)
        for _ in range(3):
            fy = rng.uniform(0, SIZE)
            t.ellipse(x + pitch / 2, fy, 1.6, rng.uniform(8, 22), (38, 26, 16), soft=1.5, alpha=0.5)
    speckle(t, rng, 70, (0.6, 1.3), [(146, 114, 82), (54, 38, 24)], alpha=0.8)
    t.grain(rng, 0.03)
    return t.finish(blur=0.35)


def generate_wildflower(rng: random.Random) -> Image.Image:
    """Flower meadow: looser, warmer grass with small leaves, then flower
    heads (5–6 shaded petals around a centre) in seven colours, buds."""
    t = Tile((66, 112, 46))
    t.mottle(rng, 4, 3, 0.10)
    grass_blades(t, rng, 700, [(42, 82, 32)] * 2, [(56, 102, 42)] * 2, (5, 12), (1.4, 2.2))
    base = [(70, 124, 48), (84, 138, 54), (64, 116, 46), (96, 150, 60)]
    tip = [(130, 186, 86), (146, 200, 96), (118, 176, 80), (160, 208, 108)]
    grass_blades(t, rng, 1700, base, tip, (6, 14), (1.2, 1.9))
    for _ in range(90):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        t.leaf(x, y, rng.uniform(5, 9), rng.uniform(2.2, 3.4), rng.uniform(0, 360), (58, 118, 50), rim=0.8, crown=1.15)
    petals = [
        ((250, 248, 240), (250, 214, 60)),   # daisy
        ((246, 190, 210), (240, 200, 90)),   # pink
        ((248, 214, 70), (196, 120, 40)),    # buttercup
        ((176, 150, 224), (250, 220, 90)),   # lavender
        ((120, 150, 230), (250, 236, 120)),  # cornflower
        ((222, 70, 60), (40, 30, 30)),       # poppy
        ((252, 232, 250), (238, 200, 80)),   # white-pink
    ]
    for _ in range(58):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        pcol, ccol = rng.choice(petals)
        n = rng.choice([5, 5, 6])
        R = rng.uniform(3.0, 5.0)
        rot0 = rng.uniform(0, 360)
        t.ellipse(x, y, R * 1.55, R * 1.55, (30, 60, 26), soft=R * 0.9, alpha=0.5)
        for k in range(n):
            a = math.radians(rot0 + 360 * k / n)
            px, py = x + math.cos(a) * R * 0.62, y + math.sin(a) * R * 0.62
            t.ellipse(px, py, R * 0.55, R * 0.36, jitter(rng, pcol, 0.03), rot=math.degrees(a), rim=0.86, crown=1.06)
        t.ellipse(x, y, R * 0.34, R * 0.34, ccol, rim=0.85, crown=1.15)
    for _ in range(40):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        pcol, _c = rng.choice(petals)
        t.ellipse(x, y, rng.uniform(0.9, 1.5), rng.uniform(0.9, 1.5), pcol, rim=0.85, crown=1.1)
    return t.finish(blur=0.35)


def generate_terracotta(rng: random.Random) -> Image.Image:
    """Terracotta floor tiles (6×6, 42 cm) with grout, per-tile mottle and
    tone, bevelled edges, faint firing speckle."""
    t = Tile((188, 160, 138))
    t.grain(rng, 0.05)
    tones = [(200, 116, 76), (192, 108, 70), (208, 124, 84), (184, 102, 66), (198, 112, 74)]
    n = 6
    pitch = SIZE / n
    for j in range(n):
        for i in range(n):
            cx = (i + 0.5) * pitch + pitch / 2
            cy = (j + 0.5) * pitch + pitch / 2
            col = jitter(rng, tones[(i * 3 + j * 5) % len(tones)], 0.035)
            t.rect(cx, cy, pitch - 2.6, pitch - 2.6, col, r=1.6, bevel=2.2, bevel_dark=0.82, crown=1.05,
                   rot=rng.uniform(-0.3, 0.3))
    t.mottle(rng, 5, 3, 0.06)
    t.mottle(rng, 14, 2, 0.03)
    speckle(t, rng, 260, (0.35, 0.8), [(150, 80, 52), (222, 150, 108)], alpha=0.5)
    return t.finish(blur=0.3)


def generate_pebbles(rng: random.Random) -> Image.Image:
    """River pebbles on sand: large smooth stones (cool/warm greys, cream,
    slate blue) with strong rim→crown shading, gloss and occlusion, small
    pebbles filling the gaps."""
    t = Tile((170, 158, 136))
    t.mottle(rng, 4, 3, 0.06)
    t.grain(rng, 0.04)
    palette = [
        (172, 168, 162), (190, 184, 174), (154, 156, 160), (206, 198, 184),
        (164, 152, 138), (178, 170, 166), (144, 146, 150), (198, 190, 176),
        (186, 174, 156), (168, 160, 150), (196, 176, 150), (158, 148, 132),
        (176, 166, 158), (140, 130, 118),
    ]
    scatter_stones(t, rng, 150, (5.0, 11.0), palette, (92, 84, 72), elong=(0.55, 0.9),
                   rim=0.78, crown=1.12, gloss=0.12, occ_grow=1.22, occ_alpha=0.45, tone_jitter=0.06)
    scatter_stones(t, rng, 220, (2.0, 4.4), palette, (92, 84, 72), elong=(0.6, 0.95),
                   rim=0.8, crown=1.1, gloss=0.0, occ_grow=1.28, occ_alpha=0.4, tone_jitter=0.06)
    return t.finish(blur=0.35)


def generate_slate(rng: random.Random) -> Image.Image:
    """Slate paving: 5 courses of large slabs with random widths (running
    joints), blue-grey tone variation, cleft streaks, bevelled edges."""
    t = Tile((112, 112, 110))
    t.grain(rng, 0.05)
    tones = [(76, 82, 92), (68, 74, 84), (84, 90, 100), (72, 78, 90), (80, 84, 92), (64, 70, 80)]
    placed = paver_courses(t, rng, 5, 4, 2.6, tones, bevel=1.8, bevel_dark=0.78, crown=1.06, r=1.0,
                           tone_jitter=0.05, row_widths=True, min_w=34)
    # cleft texture: faint streaks along each slab
    for cx, cy, w, h in placed:
        for _ in range(9):
            yy = cy + rng.uniform(-h / 2 + 3, h / 2 - 3)
            x0 = cx - w / 2 + rng.uniform(2, w * 0.4)
            L = rng.uniform(w * 0.2, w * 0.7)
            L = min(L, cx + w / 2 - 2 - x0)
            if L <= 2:
                continue
            f = rng.choice([0.86, 0.9, 1.1, 1.14])
            t.capsule(x0, yy, x0 + L, yy + rng.uniform(-0.6, 0.6), rng.uniform(0.6, 1.1),
                      shade((78, 84, 94), f), alpha=0.7)
    t.mottle(rng, 5, 3, 0.05)
    speckle(t, rng, 200, (0.35, 0.8), [(110, 116, 126), (54, 58, 66)], alpha=0.5)
    return t.finish(blur=0.3)


def generate_lattice(rng: random.Random) -> Image.Image:
    """Diagonal wooden trellis over soft foliage: two families of rounded
    laths (8 per direction), woven over/under with contact occlusion at
    every crossing."""
    t = Tile((104, 128, 82))
    t.mottle(rng, 4, 3, 0.10)
    ys = np.arange(C, dtype=np.float64)[:, None]
    xs = np.arange(C, dtype=np.float64)[None, :]
    n = 8
    p = C / n  # spacing along x+y (and x−y)
    lath_w = 5.2 * SS
    sa = (xs + ys) % p
    sb = (xs - ys) % p
    da = np.abs(sa - p / 2) / math.sqrt(2)  # perpendicular distance to family-A centrelines (offset by half pitch)
    db = np.abs(sb - p / 2) / math.sqrt(2)
    ia = np.floor((xs + ys) / p).astype(np.int64)
    ib = np.floor((xs - ys) / p).astype(np.int64)
    a_on_top = ((ia + ib) % 2) == 0
    cov_a = np.clip(lath_w / 2 + 0.5 - da, 0, 1)
    cov_b = np.clip(lath_w / 2 + 0.5 - db, 0, 1)
    wood = np.array((178, 142, 96), dtype=np.float64)
    fa = 0.74 + 0.36 * _smooth(np.clip(1.0 - da / (lath_w / 2), 0, 1))
    fb = 0.74 + 0.36 * _smooth(np.clip(1.0 - db / (lath_w / 2), 0, 1))
    # ground occlusion under laths (both families)
    occ = np.clip(1.0 - (np.minimum(da, db) - lath_w / 2) / (2.5 * SS), 0, 1)
    t.multiply(1.0 - 0.28 * _smooth(occ))
    # lower family first, upper family second, per crossing parity
    lower_a = cov_a * (~a_on_top)
    lower_b = cov_b * a_on_top
    upper_a = cov_a * a_on_top
    upper_b = cov_b * (~a_on_top)
    for cov, f in ((lower_a, fa), (lower_b, fb)):
        col = wood[None, None, :] * f[..., None]
        t.a = t.a * (1 - cov[..., None]) + col * cov[..., None]
    # contact shadow of the upper lath onto the lower one
    sh_a = np.clip(1.0 - (da - lath_w / 2) / (2.0 * SS), 0, 1) * a_on_top * cov_b
    sh_b = np.clip(1.0 - (db - lath_w / 2) / (2.0 * SS), 0, 1) * (~a_on_top) * cov_a
    t.multiply(1.0 - 0.3 * _smooth(np.maximum(sh_a, sh_b)))
    for cov, f in ((upper_a, fa), (upper_b, fb)):
        col = wood[None, None, :] * f[..., None]
        t.a = t.a * (1 - cov[..., None]) + col * cov[..., None]
    t.grain(rng, 0.03)
    return t.finish(blur=0.3)


def generate_compost(rng: random.Random) -> Image.Image:
    """Ripe compost: dark crumb ground, clumps with occlusion, straw
    fragments, leaf bits, eggshell specks and twigs."""
    t = Tile((60, 44, 30))
    t.mottle(rng, 4, 3, 0.10)
    t.grain(rng, 0.05)
    clumps = [(74, 54, 36), (88, 64, 42), (56, 40, 28), (100, 74, 50), (68, 50, 34)]
    scatter_stones(t, rng, 260, (2.4, 8.0), clumps, (30, 20, 12), elong=(0.65, 1.0),
                   rim=0.78, crown=1.14, occ_grow=1.3, occ_alpha=0.5, tone_jitter=0.05)
    for _ in range(46):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        L = rng.uniform(4, 10)
        a = rng.uniform(0, math.pi)
        t.capsule(x, y, x + L * math.cos(a), y + L * math.sin(a), 1.3, (176, 150, 96), alpha=0.9)
    for _ in range(26):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        col = rng.choice([(104, 112, 52), (128, 96, 48), (90, 104, 50)])
        t.leaf(x, y, rng.uniform(4, 8), rng.uniform(2, 3.4), rng.uniform(0, 360), col, rim=0.8, crown=1.12)
    speckle(t, rng, 30, (0.6, 1.2), [(226, 220, 206), (210, 200, 184)], alpha=0.9)
    for _ in range(30):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        L = rng.uniform(3, 8)
        a = rng.uniform(0, math.pi)
        t.capsule(x, y, x + L * math.cos(a), y + L * math.sin(a), 1.0, (40, 28, 18), alpha=0.9)
    return t.finish(blur=0.3)


def generate_flagstone(rng: random.Random) -> Image.Image:
    """Crazy paving: irregular Voronoi slabs (organic edges by domain warp)
    in buff/grey/blue-grey, sandy joints, rim-dark → crown-light slabs."""
    joint_col = (152, 138, 118)
    t = Tile(joint_col)
    t.grain(rng, 0.06)
    t.mottle(rng, 5, 2, 0.05)
    wx = (fbm(rng, 4, 3) - 0.5) * 24 * SS
    wy = (fbm(rng, 4, 3) - 0.5) * 24 * SS
    d1, d2, cid = voronoi(rng, 5, warp=(wx, wy), jitter_amt=0.8)
    gap = d2 - d1
    joint_w = 3.4 * SS
    slab = np.clip((gap - joint_w) / (1.0 * SS) + 0.5, 0.0, 1.0)  # AA coverage of slab
    palette = [
        (172, 164, 150), (156, 150, 140), (180, 172, 156), (162, 154, 138),
        (146, 146, 142), (176, 168, 160), (168, 158, 140), (150, 148, 150),
    ]
    ncell = int(cid.max()) + 1
    cols = np.array([jitter(rng, palette[k % len(palette)], 0.04) for k in range(ncell)])
    slab_col = cols[cid]
    # rim → crown by distance from the joint
    depth = np.clip((gap - joint_w) / (14.0 * SS), 0.0, 1.0)
    f = 0.80 + 0.26 * _smooth(depth)
    slab_col = slab_col * f[..., None]
    t.a = t.a * (1 - slab[..., None]) + slab_col * slab[..., None]
    t.mottle(rng, 6, 3, 0.05)
    t.grain(rng, 0.025)
    speckle(t, rng, 320, (0.35, 0.9), [(130, 124, 114), (206, 200, 188)], alpha=0.5)
    return t.finish(blur=0.35)


def generate_clay(rng: random.Random) -> Image.Image:
    """Dry clay surface: warm ochre with cloudy mottle, a fine shrinkage
    crack network (two Voronoi scales, low contrast), a few pits."""
    t = Tile((190, 124, 80))
    t.mottle(rng, 3, 4, 0.08)
    t.mottle(rng, 12, 2, 0.03)
    t.grain(rng, 0.03)
    wx = (fbm(rng, 5, 2) - 0.5) * 8 * SS
    wy = (fbm(rng, 5, 2) - 0.5) * 8 * SS
    d1, d2, _ = voronoi(rng, 6, warp=(wx, wy), jitter_amt=0.9)
    gap = d2 - d1
    crack = np.clip(1.0 - gap / (1.6 * SS), 0, 1)
    t.multiply(1.0 - 0.22 * _smooth(crack))
    # cell centres slightly lighter (curling plates)
    plate = np.clip(gap / (18.0 * SS), 0, 1)
    t.multiply(0.97 + 0.06 * _smooth(plate))
    d1b, d2b, _ = voronoi(rng, 12, warp=(wx * 0.5, wy * 0.5), jitter_amt=0.9)
    crack2 = np.clip(1.0 - (d2b - d1b) / (1.0 * SS), 0, 1)
    t.multiply(1.0 - 0.07 * _smooth(crack2))
    speckle(t, rng, 120, (0.4, 1.0), [(160, 98, 60), (214, 152, 108)], alpha=0.5)
    return t.finish(blur=0.35)


def generate_decking(rng: random.Random) -> Image.Image:
    """Weathered timber decking: 4 boards (64 cm), grey-brown per-board tone,
    wavy grain, knots, gap shadow and screw heads on 64-cm joists. Board
    joints at x = 32 + 64k so the seam falls inside a board."""
    t = Tile((104, 92, 76))
    pitch = SIZE / 4
    gap = 4.0
    tones = [(158, 142, 118), (147, 131, 108), (162, 147, 124), (151, 136, 112)]
    for i in range(4):
        cx = (i + 0.5) * pitch + pitch / 2
        col = jitter(rng, tones[i], 0.02)
        t.rect(cx, 128, pitch - gap, None, col, bevel=1.4, bevel_dark=0.84, crown=1.03)
        for _ in range(16):
            x = cx - pitch / 2 + gap / 2 + rng.uniform(2.5, pitch - gap - 2.5)
            dark = rng.random() < 0.65
            gcol = shade(col, rng.uniform(0.84, 0.93)) if dark else shade(col, rng.uniform(1.05, 1.1))
            t.vgrain(x, rng.uniform(0.5, 2.0), rng.choice([1, 2, 2, 3]), rng.uniform(0, 6.283),
                     rng.uniform(0.6, 1.4), gcol, alpha=rng.uniform(0.6, 1.0))
        if rng.random() < 0.8:
            kx = cx - pitch / 2 + rng.uniform(10, pitch - 12)
            ky = rng.uniform(0, SIZE)
            t.ellipse(kx, ky, 3.4, 4.6, shade(col, 0.88), rot=rng.uniform(-6, 6), rim=0.86, crown=1.0)
            t.ellipse(kx, ky, 2.4, 3.4, shade(col, 0.74), rim=1.0, crown=1.2, gamma=1.4)
            t.ellipse(kx, ky, 0.9, 1.3, shade(col, 0.56))
        # screws on joists every 64 cm
        for j in range(4):
            sy = 32.0 + j * 64.0
            for sx in (cx - pitch / 2 + 9, cx + pitch / 2 - 9):
                t.ellipse(sx, sy, 1.7, 1.7, (150, 148, 142), rim=0.72, crown=1.2)
                t.ellipse(sx, sy, 0.6, 0.6, (90, 88, 84))
    t.grain(rng, 0.025)
    return t.finish(blur=0.35)


def generate_corten(rng: random.Random) -> Image.Image:
    """Corten steel: layered rust mottle at three scales, faint vertical
    weather streaks, orange and dark speckle."""
    t = Tile((146, 90, 58))
    t.mottle(rng, 3, 3, 0.14)
    t.mottle(rng, 8, 3, 0.10)
    t.mottle(rng, 24, 2, 0.05)
    for _ in range(26):
        x = rng.uniform(0, SIZE)
        f = rng.choice([0.9, 0.93, 1.07, 1.1])
        t.vgrain(x, rng.uniform(1.0, 3.0), rng.choice([1, 2]), rng.uniform(0, 6.283),
                 rng.uniform(1.5, 4.0), shade((146, 90, 58), f), alpha=0.35,
                 y_from=rng.uniform(0, SIZE), y_to=rng.uniform(0, SIZE), fade=12)
    for _ in range(90):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        r = rng.uniform(3, 9)
        col = rng.choice([(160, 104, 66), (128, 74, 44), (150, 96, 60), (118, 68, 42)])
        t.ellipse(x, y, r, r * rng.uniform(0.6, 1.0), col, rot=rng.uniform(0, 180), soft=r * 0.8, alpha=0.5)
    speckle(t, rng, 320, (0.6, 1.8), [(172, 116, 74), (118, 66, 40), (188, 128, 82), (100, 54, 32)], alpha=0.75)
    t.grain(rng, 0.03)
    return t.finish(blur=0.4)


# --------------------------------------------------------------------------- #
# registry + CLI
# --------------------------------------------------------------------------- #

TEXTURES: dict[str, Callable[[random.Random], Image.Image]] = {
    "grass": generate_grass,
    "gravel": generate_gravel,
    "concrete": generate_concrete,
    "wood": generate_wood,
    "water": generate_water,
    "soil": generate_soil,
    "mulch": generate_mulch,
    "roof_tiles": generate_roof_tiles,
    "sand": generate_sand,
    "stone": generate_stone,
    "glass": generate_glass,
    "hedge": generate_hedge,
    "brick": generate_brick,
    "bark": generate_bark,
    "wildflower": generate_wildflower,
    "terracotta": generate_terracotta,
    "pebbles": generate_pebbles,
    "slate": generate_slate,
    "lattice": generate_lattice,
    "compost": generate_compost,
    "flagstone": generate_flagstone,
    "clay": generate_clay,
    "decking": generate_decking,
    "corten": generate_corten,
}


def seed_for(name: str) -> str:
    """One deterministic seed string per texture (`random.Random(str)` is
    stream-stable across CPython versions)."""
    return f"ogp-{name}-lush"


def build_texture(name: str) -> Image.Image:
    rng = random.Random(seed_for(name))  # noqa: S311 — art, not crypto
    return TEXTURES[name](rng)


def encode_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def committed_pixels(path: Path) -> np.ndarray | None:
    """Decoded RGB pixels of a committed texture, or None if it is missing."""
    if not path.exists():
        return None
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def is_current(name: str, path: Path | None = None) -> bool:
    """True when the committed PNG decodes to exactly the generator's pixels."""
    path = path or TEXTURES_DIR / f"{name}.png"
    have = committed_pixels(path)
    if have is None:
        return False
    want = np.asarray(build_texture(name))
    return have.shape == want.shape and bool(np.array_equal(have, want))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="regenerate in memory and fail if any committed PNG's pixels differ")
    parser.add_argument("--only", nargs="*", default=None, help="subset of texture names")
    args = parser.parse_args(argv)
    names = args.only if args.only else list(TEXTURES)
    unknown = [n for n in names if n not in TEXTURES]
    if unknown:
        print(f"unknown texture(s): {unknown}", file=sys.stderr)
        return 2
    stale = []
    for name in names:
        path = TEXTURES_DIR / f"{name}.png"
        img = build_texture(name)
        have = committed_pixels(path)
        same = have is not None and have.shape == (SIZE, SIZE, 3) and bool(
            np.array_equal(have, np.asarray(img))
        )
        if args.check:
            if same:
                print(f"ok     {name}.png")
            else:
                stale.append(name)
                print(f"STALE  {name}.png")
        elif same:
            print(f"same   {name}.png (pixels unchanged - file left alone)")
        else:
            path.write_bytes(encode_png(img))
            print(f"wrote  {path}")
    if args.check:
        if stale:
            print(f"{len(stale)} texture(s) differ from the generator - regenerate and commit.")
            return 1
        print(f"OK - {len(names)} texture(s) are pixel-identical to the generator.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
