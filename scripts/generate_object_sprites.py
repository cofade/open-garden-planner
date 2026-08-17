"""Generate all furniture & infrastructure object sprites — issue #308 (Package 3a).

This script IS the provenance record for every file under
`src/open_garden_planner/resources/objects/` (see PROVENANCE.md there).
Style contract: resources/objects/README.md ("Lush Object" — the man-made
sibling of the #281 "Lush Sprite" plant art). Key rules:

- Top-down view, light from straight above: every part shades rim-dark →
  crown-light (symmetric gradients across a part's short axis, radial for
  round parts). NO directional drop shadow is baked — the canvas item paints
  the single shadow (`GardenItem.SHADOW_OFFSET`, View › Shadows), so the art
  stays correct under the USER-controlled rotation of furniture.
- Full Lush parity: per-part gradients, a dark occlusion halo wherever a part
  sits on another, material micro-detail (wood grain, plank gaps, weave
  hatch, ripples, speckles, rivets), gloss on glossy materials.
- Palette lives here: colors come only from `MATERIALS` (+ the ember triad),
  derived via `mix()`/`lighten()` — never hand-edited into an SVG.
- QtSvg subset only (QSvgRenderer ≈ SVG 1.2 Tiny): linear/radial gradients,
  opacity, transforms, stroke caps/joins. No filters, masks, clipPath, CSS,
  text, images.
- viewBox = the object's default footprint in cm (`FURNITURE_DEFAULT_DIMENSIONS`);
  the canvas stretches the art to the user's rect (mild non-uniform stretch
  must degrade gracefully — footprints are rounded rects, not thin circles).
- Deterministic: seeded per object name — identical bytes on every run.

Usage:
    venv/Scripts/python.exe scripts/generate_object_sprites.py           # write all
    venv/Scripts/python.exe scripts/generate_object_sprites.py --check   # verify no drift
    venv/Scripts/python.exe scripts/generate_object_sprites.py --only bench chair
"""

# ruff: noqa: C408 - dict() keyword style is deliberate for the recipe/material tables.

from __future__ import annotations

import argparse
import colorsys
import math
import random
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

OBJECTS_DIR = Path(__file__).parent.parent / "src" / "open_garden_planner" / "resources" / "objects"
FURNITURE_DIR = OBJECTS_DIR / "furniture"
INFRASTRUCTURE_DIR = OBJECTS_DIR / "infrastructure"


# --------------------------------------------------------------------------- #
# color helpers (identical to generate_plant_sprites.py)
# --------------------------------------------------------------------------- #
def _rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def mix(c1: str, c2: str, t: float) -> str:
    a, b = _rgb(c1), _rgb(c2)
    return _hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def lighten(c: str, amt: float) -> str:
    h, s, v = colorsys.rgb_to_hsv(*_rgb(c))
    return _hex(colorsys.hsv_to_rgb(h, max(0.0, s - amt * 0.5), min(1.0, v + amt)))


def darken(c: str, amt: float) -> str:
    h, s, v = colorsys.rgb_to_hsv(*_rgb(c))
    return _hex(colorsys.hsv_to_rgb(h, min(1.0, s + amt * 0.3), max(0.0, v - amt)))


# --------------------------------------------------------------------------- #
# material anchor table: light (crown) / mid / dark (rim) / occ (occlusion) / line (detail)
# --------------------------------------------------------------------------- #
def mat(light: str, mid: str, dark: str, occ: str, line: str) -> dict[str, str]:
    return {"light": light, "mid": mid, "dark": dark, "occ": occ, "line": line}


MATERIALS: dict[str, dict[str, str]] = {
    # woods
    "oak": mat("#dcae70", "#b98350", "#7d5029", "#3f2510", "#8f5c2e"),
    "teak": mat("#c98f56", "#a06a3a", "#69401c", "#33200c", "#7c4c24"),
    "pine": mat("#efd8a0", "#d4b471", "#9e7c40", "#54401e", "#ab8c4c"),
    "walnut": mat("#8f5f3c", "#66432c", "#3f2617", "#1e1109", "#4e3220"),
    "grey_wood": mat("#bdb7aa", "#918a7a", "#5f584b", "#34302a", "#726b5d"),
    "charcoal_wood": mat("#4a4441", "#2f2a28", "#191614", "#0a0908", "#3a3432"),
    "shingle": mat("#a89c8c", "#78695a", "#4b4037", "#231d18", "#5f5246"),
    # metals
    "steel": mat("#eaedf0", "#adb4bc", "#626b73", "#2c3237", "#8e979f"),
    "iron": mat("#7e838a", "#4c525a", "#262a2f", "#0f1113", "#3c424a"),
    "brass": mat("#f4dc8e", "#cca84e", "#8d6d24", "#4a380f", "#ab8930"),
    # enamels & plastics
    "enamel_black": mat("#70757a", "#313538", "#131517", "#050506", "#45494d"),
    "enamel_green": mat("#83b67e", "#3f7c3e", "#204c22", "#0e2810", "#2e612f"),
    "enamel_red": mat("#f28d7d", "#cb3b2d", "#821b13", "#470c07", "#a52b20"),
    "plastic_green": mat("#73ab6e", "#3e7c3c", "#214c21", "#0e2810", "#306c30"),
    "plastic_blue": mat("#84b6ea", "#427bc2", "#224c82", "#10294c", "#3162a2"),
    "plastic_yellow": mat("#fbe792", "#e9c33f", "#a8861c", "#5a470c", "#c9a52a"),
    "rubber": mat("#5c5f63", "#303336", "#151719", "#050606", "#404447"),
    # fabrics
    "canvas_cream": mat("#fcf6e8", "#eee1c6", "#cbba95", "#8b7a58", "#dacba6"),
    "canvas_blue": mat("#a1c0e5", "#5e89bf", "#315787", "#182d4c", "#4c74aa"),
    "canvas_red": mat("#f4a391", "#d65d4b", "#913024", "#4a150e", "#ba4b3c"),
    "canvas_green": mat("#accf9d", "#71a661", "#406e37", "#213c1c", "#5c8b4e"),
    "canvas_grey": mat("#dad7d1", "#aca79e", "#716c62", "#3e3a33", "#918c82"),
    "canvas_teal": mat("#9fd3cf", "#4f9d97", "#27625e", "#12332f", "#3f817c"),
    # minerals
    "terracotta": mat("#eaa377", "#ca7341", "#8c4523", "#4a220e", "#aa5c31"),
    "stone": mat("#d2cdc3", "#a29d93", "#68645c", "#383632", "#837e75"),
    "sandstone": mat("#e5d5b6", "#c4ae86", "#8c7756", "#4a3e2c", "#a28e68"),
    "concrete": mat("#d5d5d2", "#abaca8", "#717370", "#404240", "#8e8f8b"),
    "ash": mat("#c9c5bd", "#8f8b83", "#57544e", "#2b2925", "#6f6b64"),
    # translucent / liquid / ground
    "glass": mat("#f4faff", "#c0dcf0", "#82accb", "#476f8f", "#e8f4fc"),
    "water": mat("#a6dff2", "#43a3d2", "#1e6291", "#0f3a5a", "#cbf0fb"),
    "soil": mat("#7d5c3e", "#573c26", "#352111", "#1a0f06", "#6b4b30"),
    "compost": mat("#725232", "#4c3521", "#2d1d10", "#140c05", "#8b6c3c"),
    "sand": mat("#f6e8c6", "#e4d0a0", "#bfa872", "#8a754a", "#d4bd8a"),
    "grass_bit": mat("#a9d77a", "#5f9a3c", "#2f5c1c", "#1b3a10", "#4a7f2c"),
}
EMBER = ("#fff4b0", "#ff9d3e", "#c8421a")  # highlight / mid / dark
FLAME = ("#fff7c2", "#ffc23a", "#f0621c")


# --------------------------------------------------------------------------- #
# sprite accumulator
# --------------------------------------------------------------------------- #
class Sprite:
    def __init__(self, name: str, w: float, h: float, rng: random.Random) -> None:
        self.name = name
        self.w = float(w)
        self.h = float(h)
        self.rng = rng
        self.key = "".join(p[0] for p in name.split("_"))[:3] + str(len(name))
        self.defs: list[str] = []
        self.body: list[str] = []
        self._n = 0

    def uid(self, tag: str) -> str:
        self._n += 1
        return f"{self.key}_{tag}{self._n}"

    # gradients ------------------------------------------------------------
    def lin(
        self,
        stops: list[tuple[float, str, float | None]],
        x1: float = 0.0,
        y1: float = 0.0,
        x2: float = 0.0,
        y2: float = 1.0,
    ) -> str:
        gid = self.uid("l")
        parts = [f'<linearGradient id="{gid}" x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}">']
        for off, col, op in stops:
            o = "" if op is None else f' stop-opacity="{op:g}"'
            parts.append(f'<stop offset="{off:g}%" stop-color="{col}"{o}/>')
        parts.append("</linearGradient>")
        self.defs.append("".join(parts))
        return gid

    def rad(
        self,
        stops: list[tuple[float, str, float | None]],
        cx: float = 0.5,
        cy: float = 0.5,
        r: float = 0.5,
    ) -> str:
        gid = self.uid("r")
        parts = [f'<radialGradient id="{gid}" cx="{cx * 100:g}%" cy="{cy * 100:g}%" r="{r * 100:g}%">']
        for off, col, op in stops:
            o = "" if op is None else f' stop-opacity="{op:g}"'
            parts.append(f'<stop offset="{off:g}%" stop-color="{col}"{o}/>')
        parts.append("</radialGradient>")
        self.defs.append("".join(parts))
        return gid

    # emit -----------------------------------------------------------------
    def add(self, s: str) -> None:
        self.body.append(s)

    @contextmanager
    def rotated(self, angle: float, cx: float, cy: float) -> Iterator[None]:
        """Everything added inside the block is wrapped in one rotate() group."""
        mark = len(self.body)
        yield
        inner = "".join(self.body[mark:])
        del self.body[mark:]
        self.body.append(rot(angle, cx, cy, inner))

    def svg(self) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w:g} {self.h:g}">\n'
            f"<defs>{''.join(self.defs)}</defs>\n"
            + "\n".join(self.body)
            + "\n</svg>\n"
        )


def f1(v: float) -> str:
    return f"{v:.1f}"


# --------------------------------------------------------------------------- #
# geometry helpers
# --------------------------------------------------------------------------- #
def rect_s(x: float, y: float, w: float, h: float, fill: str, rx: float = 0.0, extra: str = "") -> str:
    r = f' rx="{rx:g}"' if rx else ""
    return f'<rect x="{f1(x)}" y="{f1(y)}" width="{f1(w)}" height="{f1(h)}"{r} fill="{fill}"{extra}/>'


def circ_s(cx: float, cy: float, r: float, fill: str, extra: str = "") -> str:
    return f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(r)}" fill="{fill}"{extra}/>'


def ell_s(cx: float, cy: float, rx: float, ry: float, fill: str, extra: str = "") -> str:
    return f'<ellipse cx="{f1(cx)}" cy="{f1(cy)}" rx="{f1(rx)}" ry="{f1(ry)}" fill="{fill}"{extra}/>'


def line_s(x1: float, y1: float, x2: float, y2: float, stroke: str, w: float, op: float = 1.0,
           cap: str = "round") -> str:
    o = "" if op >= 1.0 else f' opacity="{op:g}"'
    return (f'<line x1="{f1(x1)}" y1="{f1(y1)}" x2="{f1(x2)}" y2="{f1(y2)}" stroke="{stroke}" '
            f'stroke-width="{w:g}" stroke-linecap="{cap}"{o}/>')


def path_s(d: str, fill: str, extra: str = "") -> str:
    return f'<path d="{d}" fill="{fill}"{extra}/>'


def annulus_d(cx: float, cy: float, ro: float, ri: float) -> str:
    """Ring as one path: outer circle clockwise, inner counter-clockwise (nonzero → hole)."""
    return (
        f"M {f1(cx + ro)} {f1(cy)} A {f1(ro)} {f1(ro)} 0 1 1 {f1(cx - ro)} {f1(cy)} "
        f"A {f1(ro)} {f1(ro)} 0 1 1 {f1(cx + ro)} {f1(cy)} Z "
        f"M {f1(cx + ri)} {f1(cy)} A {f1(ri)} {f1(ri)} 0 1 0 {f1(cx - ri)} {f1(cy)} "
        f"A {f1(ri)} {f1(ri)} 0 1 0 {f1(cx + ri)} {f1(cy)} Z"
    )


def wedge_d(cx: float, cy: float, r: float, a0: float, a1: float, ri: float = 0.0) -> str:
    """Pie slice (or ring sector when ri > 0) between angles a0..a1 (degrees)."""
    r0, r1 = math.radians(a0), math.radians(a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    xo0, yo0 = cx + r * math.cos(r0), cy + r * math.sin(r0)
    xo1, yo1 = cx + r * math.cos(r1), cy + r * math.sin(r1)
    if ri <= 0:
        return f"M {f1(cx)} {f1(cy)} L {f1(xo0)} {f1(yo0)} A {f1(r)} {f1(r)} 0 {large} 1 {f1(xo1)} {f1(yo1)} Z"
    xi0, yi0 = cx + ri * math.cos(r0), cy + ri * math.sin(r0)
    xi1, yi1 = cx + ri * math.cos(r1), cy + ri * math.sin(r1)
    return (
        f"M {f1(xi0)} {f1(yi0)} L {f1(xo0)} {f1(yo0)} A {f1(r)} {f1(r)} 0 {large} 1 {f1(xo1)} {f1(yo1)} "
        f"L {f1(xi1)} {f1(yi1)} A {f1(ri)} {f1(ri)} 0 {large} 0 {f1(xi0)} {f1(yi0)} Z"
    )


def strip_in_circle_d(cx: float, cy: float, r: float, x0: float, x1: float) -> str:
    """Vertical strip [x0, x1] clipped to the circle — analytic (no clipPath in QtSvg)."""
    x0 = max(x0, cx - r + 0.01)
    x1 = min(x1, cx + r - 0.01)
    h0 = math.sqrt(max(r * r - (x0 - cx) ** 2, 0.0))
    h1 = math.sqrt(max(r * r - (x1 - cx) ** 2, 0.0))
    return (
        f"M {f1(x0)} {f1(cy - h0)} A {f1(r)} {f1(r)} 0 0 1 {f1(x1)} {f1(cy - h1)} "
        f"L {f1(x1)} {f1(cy + h1)} A {f1(r)} {f1(r)} 0 0 1 {f1(x0)} {f1(cy + h0)} Z"
    )


def chord(r: float, y_off: float) -> float:
    """Half chord length of a circle of radius r at offset y_off from its center."""
    return math.sqrt(max(r * r - y_off * y_off, 0.0))


def rot(a: float, cx: float, cy: float, inner: str) -> str:
    return f'<g transform="rotate({f1(a)} {f1(cx)} {f1(cy)})">{inner}</g>'


# --------------------------------------------------------------------------- #
# material primitives — every part = optional occlusion halo + shaded body + micro-detail
# --------------------------------------------------------------------------- #
def mix_mat(m: dict[str, str], t: float) -> dict[str, str]:
    """A darker variant of a material (parts in shadow, e.g. under-frame braces)."""
    return {k: mix(v, m["occ"], t) for k, v in m.items()}


def halo_rect(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str],
              pad: float = 1.2, rx: float = 2.0, op: float = 0.55) -> None:
    sp.add(rect_s(x - pad, y - pad, w + 2 * pad, h + 2 * pad, m["occ"], rx=rx + pad, extra=f' opacity="{op:g}"'))


def halo_circle(sp: Sprite, cx: float, cy: float, r: float, m: dict[str, str], pad: float = 1.2,
                op: float = 0.55) -> None:
    sp.add(circ_s(cx, cy, r + pad, m["occ"], extra=f' opacity="{op:g}"'))


def plank_grad(sp: Sprite, m: dict[str, str], orient: str) -> str:
    """Symmetric rim-dark → crown-light gradient across the plank's short axis."""
    stops = [(0, m["dark"], None), (22, m["mid"], None), (50, m["light"], None),
             (78, m["mid"], None), (100, m["dark"], None)]
    return sp.lin(stops, 0, 0, 0, 1) if orient == "h" else sp.lin(stops, 0, 0, 1, 0)


def grain_lines(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str], orient: str,
                n: int = 3, op: float = 0.35) -> None:
    rng = sp.rng
    long_len = w if orient == "h" else h
    short_len = h if orient == "h" else w
    for i in range(n):
        off = short_len * (0.18 + 0.64 * (i + rng.uniform(0.2, 0.8)) / n)
        amp = min(short_len * 0.08, 1.2)
        seg = max(int(long_len / 18), 2)
        pts = []
        for k in range(seg + 1):
            t = k / seg
            wobble = amp * math.sin(t * math.pi * rng.uniform(1.5, 3.5) + rng.uniform(0, 6.28))
            if orient == "h":
                pts.append((x + 1.5 + (long_len - 3) * t, y + off + wobble))
            else:
                pts.append((x + off + wobble, y + 1.5 + (long_len - 3) * t))
        d = "M " + " L ".join(f"{f1(px)} {f1(py)}" for px, py in pts)
        sp.add(f'<path d="{d}" fill="none" stroke="{m["line"]}" stroke-width="0.55" '
               f'stroke-linecap="round" opacity="{op:g}"/>')


def plank(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str], orient: str = "h",
          rx: float = 1.4, halo: bool = True, grain: bool = True, knot: bool = True,
          bevel: bool = True) -> None:
    """A wooden board seen from above."""
    if halo:
        halo_rect(sp, x, y, w, h, m, pad=1.0, rx=rx)
    sp.add(rect_s(x, y, w, h, f"url(#{plank_grad(sp, m, orient)})", rx=rx))
    if grain:
        n = 3 if (h if orient == "h" else w) >= 9 else 2
        grain_lines(sp, x, y, w, h, m, orient, n=n)
    if knot and sp.rng.random() < 0.45 and min(w, h) >= 8:
        long_len = w if orient == "h" else h
        t = sp.rng.uniform(0.2, 0.8)
        kx = x + w * (t if orient == "h" else 0.5) + sp.rng.uniform(-1, 1)
        ky = y + h * (0.5 if orient == "h" else t) + sp.rng.uniform(-1, 1)
        kr = min(long_len * 0.03, min(w, h) * 0.22)
        sp.add(ell_s(kx, ky, kr * 1.4, kr, m["dark"], extra=' opacity="0.7"'))
        sp.add(ell_s(kx, ky, kr * 0.7, kr * 0.5, m["occ"], extra=' opacity="0.6"'))
    if bevel:
        # crown highlight along the long axis
        if orient == "h":
            sp.add(line_s(x + rx, y + h * 0.5, x + w - rx, y + h * 0.5, m["light"], 0.6, 0.35))
        else:
            sp.add(line_s(x + w * 0.5, y + rx, x + w * 0.5, y + h - rx, m["light"], 0.6, 0.35))


def wood_surface(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str],
                 orient: str = "h", n: int | None = None, gap: float = 1.2, halo: bool = True,
                 rx: float = 1.2) -> None:
    """A slab of parallel planks running along `orient` (planks stacked across it)."""
    if halo:
        halo_rect(sp, x, y, w, h, m, pad=1.2, rx=rx + 1)
    sp.add(rect_s(x, y, w, h, m["occ"], rx=rx))  # gap ground
    across = h if orient == "h" else w
    if n is None:
        n = max(int(across / 11 + 1e-9), 1)
    pw = (across - gap * (n - 1)) / n
    for i in range(n):
        off = i * (pw + gap)
        if orient == "h":
            plank(sp, x, y + off, w, pw, m, "h", rx=rx, halo=False)
        else:
            plank(sp, x + off, y, pw, h, m, "v", rx=rx, halo=False)


def disc(sp: Sprite, cx: float, cy: float, r: float, m: dict[str, str], halo: bool = True,
         gloss: float = 0.0, rim: float = 0.0) -> None:
    """Round part: rim-dark → crown-light radial shading, optional gloss & rim highlight."""
    if halo:
        halo_circle(sp, cx, cy, r, m)
    g = sp.rad([(0, m["light"], None), (55, m["mid"], None), (100, m["dark"], None)])
    sp.add(circ_s(cx, cy, r, f"url(#{g})"))
    if gloss > 0:
        gl = sp.rad([(0, "#ffffff", gloss), (100, "#ffffff", 0.0)], cx=0.5, cy=0.5, r=0.5)
        sp.add(circ_s(cx - r * 0.22, cy - r * 0.22, r * 0.55, f"url(#{gl})"))
    if rim > 0:
        sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(r - rim)}" fill="none" '
               f'stroke="{m["light"]}" stroke-width="{rim:g}" opacity="0.35"/>')


def ring(sp: Sprite, cx: float, cy: float, ro: float, ri: float, m: dict[str, str],
         halo: bool = True, crown: float = 0.5) -> None:
    """Annulus shaded light at `crown` (fraction ri..ro), dark at both edges."""
    if halo:
        halo_circle(sp, cx, cy, ro, m)
    t = (ri + (ro - ri) * crown) / ro * 100
    g = sp.rad([(max(t - 22, 0), m["dark"], None), (t, m["light"], None), (100, m["dark"], None)])
    sp.add(path_s(annulus_d(cx, cy, ro, ri), f"url(#{g})"))


def puff_overlay(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str],
                 rx: float = 3.0, strength: float = 0.4) -> None:
    """Rotation-safe 'stuffed' shading for fabric: white core → transparent → dark rim."""
    g = sp.rad([(0, "#ffffff", 0.22 * strength), (60, "#ffffff", 0.0), (100, m["occ"], 0.55 * strength)],
               r=0.72)
    sp.add(rect_s(x, y, w, h, f"url(#{g})", rx=rx))


def weave(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str], step: float = 4.0,
          op: float = 0.14) -> None:
    """Diagonal weave hatch confined to the rect."""
    n = int((w + h) / step + 1e-9)
    for i in range(1, n):
        d = i * step
        # line from (x + d, y) to (x, y + d) clipped to the rect
        ax, ay = x + min(d, w), y + max(d - w, 0.0)
        bx, by = x + max(d - h, 0.0), y + min(d, h)
        sp.add(line_s(ax, ay, bx, by, m["dark"], 0.45, op, cap="butt"))


def fabric(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str], rx: float = 3.0,
           halo: bool = True, stripes: tuple[dict[str, str], int, str] | None = None,
           hatch: bool = True, tufts: int = 0, quilt: float = 0.0) -> None:
    """Cushion / canvas panel: base, optional stripes, weave hatch, puff shading, tufts."""
    if halo:
        halo_rect(sp, x, y, w, h, m, pad=1.0, rx=rx)
    g = sp.lin([(0, m["dark"], None), (50, m["mid"], None), (100, m["dark"], None)], 0, 0, 0, 1)
    sp.add(rect_s(x, y, w, h, f"url(#{g})", rx=rx))
    if stripes:
        m2, n, orient = stripes
        g2 = sp.lin([(0, m2["dark"], None), (50, m2["mid"], None), (100, m2["dark"], None)], 0, 0, 0, 1)
        if orient == "v":
            sw = w / (2 * n)
            for i in range(n):
                sp.add(rect_s(x + sw * (2 * i + 0.5), y + 0.4, sw, h - 0.8, f"url(#{g2})", rx=0.4))
        else:
            sh = h / (2 * n)
            for i in range(n):
                sp.add(rect_s(x + 0.4, y + sh * (2 * i + 0.5), w - 0.8, sh, f"url(#{g2})", rx=0.4))
    if hatch:
        weave(sp, x + 0.8, y + 0.8, w - 1.6, h - 1.6, m)
    if quilt > 0:
        k = 1
        while k * quilt < w:
            sp.add(line_s(x + k * quilt, y + 1, x + k * quilt, y + h - 1, m["dark"], 0.5, 0.25))
            k += 1
        k = 1
        while k * quilt < h:
            sp.add(line_s(x + 1, y + k * quilt, x + w - 1, y + k * quilt, m["dark"], 0.5, 0.25))
            k += 1
    puff_overlay(sp, x, y, w, h, m, rx=rx)
    for i in range(tufts):
        tx = x + w * (i + 1) / (tufts + 1)
        sp.add(circ_s(tx, y + h * 0.5, 1.1, m["dark"], extra=' opacity="0.8"'))
        sp.add(circ_s(tx - 0.3, y + h * 0.5 - 0.3, 0.45, m["light"], extra=' opacity="0.7"'))


def metal_bar(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str], orient: str = "h",
              rx: float = 1.5, halo: bool = True) -> None:
    """Brushed metal bar: asymmetric-free 4-stop gradient with a bright crown line."""
    if halo:
        halo_rect(sp, x, y, w, h, m, pad=0.9, rx=rx)
    stops = [(0, m["dark"], None), (35, m["light"], None), (55, m["mid"], None), (100, m["dark"], None)]
    g = sp.lin(stops, 0, 0, 0, 1) if orient == "h" else sp.lin(stops, 0, 0, 1, 0)
    sp.add(rect_s(x, y, w, h, f"url(#{g})", rx=rx))
    if orient == "h":
        sp.add(line_s(x + rx, y + h * 0.36, x + w - rx, y + h * 0.36, "#ffffff", 0.5, 0.45))
    else:
        sp.add(line_s(x + w * 0.36, y + rx, x + w * 0.36, y + h - rx, "#ffffff", 0.5, 0.45))


def screw(sp: Sprite, cx: float, cy: float, r: float, m: dict[str, str] | None = None) -> None:
    m = m or MATERIALS["steel"]
    sp.add(circ_s(cx, cy, r + 0.5, m["occ"], extra=' opacity="0.6"'))
    g = sp.rad([(0, m["light"], None), (70, m["mid"], None), (100, m["dark"], None)])
    sp.add(circ_s(cx, cy, r, f"url(#{g})"))
    sp.add(line_s(cx - r * 0.6, cy, cx + r * 0.6, cy, m["dark"], 0.5, 0.8))


def glass_pane(sp: Sprite, x: float, y: float, w: float, h: float, op: float = 0.62,
               frame: dict[str, str] | None = None) -> None:
    m = MATERIALS["glass"]
    g = sp.lin([(0, m["light"], None), (55, mix(m["light"], m["mid"], 0.6), None), (100, m["mid"], None)],
               0, 0, 1, 1)
    sp.add(rect_s(x, y, w, h, f"url(#{g})", rx=0.6, extra=f' fill-opacity="{op:g}"'))
    # reflection streaks (local frame; rotate with the object like fruit speculars in #281)
    sp.add(line_s(x + w * 0.18, y + h * 0.82, x + w * 0.42, y + h * 0.12, "#ffffff", 1.4, 0.55))
    sp.add(line_s(x + w * 0.30, y + h * 0.88, x + w * 0.58, y + h * 0.10, "#ffffff", 0.6, 0.45))
    if frame:
        sp.add(f'<rect x="{f1(x)}" y="{f1(y)}" width="{f1(w)}" height="{f1(h)}" rx="0.6" fill="none" '
               f'stroke="{frame["dark"]}" stroke-width="0.9" opacity="0.7"/>')


def water_fill(sp: Sprite, shape: str, x: float, y: float, w: float, h: float, rx: float = 0.0,
               ripples: int = 3, sparkle: int = 8, r_light: float = 0.55) -> None:
    """Water body: crown-light radial, concentric ripples, caustic sparkles."""
    m = MATERIALS["water"]
    g = sp.rad([(0, m["light"], None), (55, m["mid"], None), (100, m["dark"], None)], r=r_light)
    cx, cy = x + w / 2, y + h / 2
    if shape == "circle":
        sp.add(circ_s(cx, cy, w / 2, f"url(#{g})"))
    else:
        sp.add(rect_s(x, y, w, h, f"url(#{g})", rx=rx))
    for i in range(1, ripples + 1):
        t = i / (ripples + 1)
        if shape == "circle":
            sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(w / 2 * t)}" fill="none" '
                   f'stroke="{m["line"]}" stroke-width="0.7" opacity="{0.28 - 0.06 * i:.2f}"/>')
        else:
            iw, ih = w * t, h * t
            sp.add(f'<rect x="{f1(cx - iw / 2)}" y="{f1(cy - ih / 2)}" width="{f1(iw)}" height="{f1(ih)}" '
                   f'rx="{f1(rx * t)}" fill="none" stroke="{m["line"]}" stroke-width="0.7" '
                   f'opacity="{0.28 - 0.06 * i:.2f}"/>')
    rng = sp.rng
    for _ in range(sparkle):
        if shape == "circle":
            a = rng.uniform(0, 6.283)
            rr = rng.uniform(0.15, 0.85) * w / 2
            px, py = cx + rr * math.cos(a), cy + rr * math.sin(a)
        else:
            px, py = rng.uniform(x + w * 0.1, x + w * 0.9), rng.uniform(y + h * 0.1, y + h * 0.9)
        ln = rng.uniform(1.5, 4.0)
        ang = rng.uniform(-0.6, 0.6)
        sp.add(line_s(px - ln * math.cos(ang), py - ln * math.sin(ang), px + ln * math.cos(ang),
                      py + ln * math.sin(ang), "#ffffff", 0.7, rng.uniform(0.25, 0.5)))


def granular_fill(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str],
                  rx: float = 1.0, clumps: int = 40, size: tuple[float, float] = (1.2, 3.0),
                  bits: int = 0, shape: str = "rect") -> None:
    """Soil / sand / compost: base radial (mid → dark rim) + clumps + tiny highlights."""
    g = sp.rad([(0, m["light"], None), (45, m["mid"], None), (100, m["dark"], None)], r=0.7)
    cx, cy = x + w / 2, y + h / 2
    if shape == "circle":
        sp.add(circ_s(cx, cy, w / 2, f"url(#{g})"))
    else:
        sp.add(rect_s(x, y, w, h, f"url(#{g})", rx=rx))
    rng = sp.rng
    for i in range(clumps):
        if shape == "circle":
            a = rng.uniform(0, 6.283)
            rr = rng.uniform(0.0, 0.88) * w / 2
            px, py = cx + rr * math.cos(a), cy + rr * math.sin(a)
        else:
            px, py = rng.uniform(x + 2, x + w - 2), rng.uniform(y + 2, y + h - 2)
        s = rng.uniform(*size)
        dark = i % 3 != 0
        col = m["dark"] if dark else m["light"]
        sp.add(ell_s(px, py, s, s * rng.uniform(0.6, 0.9), col,
                     extra=f' opacity="{rng.uniform(0.35, 0.7):.2f}"'))
        if not dark:
            sp.add(circ_s(px - s * 0.25, py - s * 0.25, s * 0.3, "#ffffff", extra=' opacity="0.25"'))
    gb = MATERIALS["grass_bit"]
    for _ in range(bits):
        if shape == "circle":
            a = rng.uniform(0, 6.283)
            rr = rng.uniform(0.0, 0.8) * w / 2
            px, py = cx + rr * math.cos(a), cy + rr * math.sin(a)
        else:
            px, py = rng.uniform(x + 3, x + w - 3), rng.uniform(y + 3, y + h - 3)
        sp.add(rot(rng.uniform(0, 180), px, py,
                   ell_s(px, py, rng.uniform(1.6, 2.6), rng.uniform(0.7, 1.1), gb["mid"], extra=' opacity="0.85"')))


def glow(sp: Sprite, cx: float, cy: float, r: float, strength: float = 0.9) -> None:
    g = sp.rad([(0, EMBER[0], strength), (40, EMBER[1], strength * 0.85), (100, EMBER[2], 0.0)])
    sp.add(circ_s(cx, cy, r, f"url(#{g})"))


def flame(sp: Sprite, cx: float, base_y: float, h: float, w: float, tilt: float = 0.0) -> None:
    g = sp.lin([(0, FLAME[0], None), (45, FLAME[1], None), (100, FLAME[2], None)], 0, 0, 0, 1)
    tip_y = base_y - h
    d = (f"M {f1(cx - w / 2)} {f1(base_y)} Q {f1(cx - w * 0.55)} {f1(base_y - h * 0.55)} {f1(cx + tilt)} {f1(tip_y)} "
         f"Q {f1(cx + w * 0.55)} {f1(base_y - h * 0.55)} {f1(cx + w / 2)} {f1(base_y)} Z")
    sp.add(path_s(d, f"url(#{g})", extra=' opacity="0.92"'))
    d2 = (f"M {f1(cx - w * 0.22)} {f1(base_y)} Q {f1(cx - w * 0.25)} {f1(base_y - h * 0.4)} {f1(cx + tilt * 0.6)} {f1(base_y - h * 0.62)} "
          f"Q {f1(cx + w * 0.25)} {f1(base_y - h * 0.4)} {f1(cx + w * 0.22)} {f1(base_y)} Z")
    sp.add(path_s(d2, FLAME[0], extra=' opacity="0.85"'))


def bevel_frame(sp: Sprite, x: float, y: float, w: float, h: float, m: dict[str, str], rx: float,
                inset: float = 1.6) -> None:
    sp.add(f'<rect x="{f1(x)}" y="{f1(y)}" width="{f1(w)}" height="{f1(h)}" rx="{rx:g}" fill="none" '
           f'stroke="{m["occ"]}" stroke-width="1.0" opacity="0.55"/>')
    sp.add(f'<rect x="{f1(x + inset)}" y="{f1(y + inset)}" width="{f1(w - 2 * inset)}" '
           f'height="{f1(h - 2 * inset)}" rx="{max(rx - inset, 0):g}" fill="none" '
           f'stroke="{m["light"]}" stroke-width="0.7" opacity="0.4"/>')


# --------------------------------------------------------------------------- #
# object builders — furniture
# --------------------------------------------------------------------------- #
def build_table_rectangular(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 150 x 100
    m = MATERIALS["oak"]
    halo_rect(sp, 3, 3, W - 6, H - 6, m, pad=1.5, rx=4, op=0.6)
    sp.add(rect_s(3, 3, W - 6, H - 6, m["occ"], rx=3))
    end = 12.0
    # breadboard ends (planks running across the short axis)
    plank(sp, 4, 4, end, H - 8, m, "v", rx=1.6, halo=False)
    plank(sp, W - 4 - end, 4, end, H - 8, m, "v", rx=1.6, halo=False)
    wood_surface(sp, 4 + end + 1.2, 4, W - 8 - 2 * end - 2.4, H - 8, m, "h", n=6, gap=1.3, halo=False)
    bevel_frame(sp, 3, 3, W - 6, H - 6, m, rx=3)
    st = MATERIALS["steel"]
    for cx, cy in ((10, 10), (W - 10, 10), (10, H - 10), (W - 10, H - 10)):
        screw(sp, cx, cy, 1.6, st)


def build_table_round(sp: Sprite) -> None:
    W = sp.w  # 100
    cx = cy = W / 2
    m = MATERIALS["teak"]
    r = 47.0
    halo_circle(sp, cx, cy, r, m, pad=1.6, op=0.6)
    sp.add(circ_s(cx, cy, r, m["occ"]))
    n = 7
    gap = 1.3
    pw = (2 * r - gap * (n - 1)) / n
    g_v = plank_grad(sp, m, "v")
    for i in range(n):
        x0 = cx - r + i * (pw + gap)
        sp.add(path_s(strip_in_circle_d(cx, cy, r - 0.3, x0, x0 + pw), f"url(#{g_v})"))
        # grain within the strip's vertical extent
        mid = x0 + pw / 2
        hh = chord(r - 2, mid - cx)
        grain_lines(sp, x0, cy - hh, pw, 2 * hh, m, "v", n=2, op=0.3)
    # bevel + parasol-hole cap
    sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(r)}" fill="none" stroke="{m["occ"]}" '
           f'stroke-width="1.2" opacity="0.55"/>')
    sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(r - 2)}" fill="none" stroke="{m["light"]}" '
           f'stroke-width="0.8" opacity="0.4"/>')
    disc(sp, cx, cy, 3.6, MATERIALS["brass"], gloss=0.5)
    sp.add(circ_s(cx, cy, 1.5, MATERIALS["brass"]["occ"], extra=' opacity="0.8"'))


def build_chair(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 50 x 50
    wood = MATERIALS["oak"]
    cush = MATERIALS["canvas_cream"]
    # seat frame
    plank(sp, 4, 9, W - 8, H - 12, wood, "h", rx=2.2, grain=False, knot=False)
    # cushion
    fabric(sp, 8, 13, W - 16, H - 19, cush, rx=3.5, tufts=0)
    for tx, ty in ((18, 24), (32, 24), (18, 38), (32, 38)):
        sp.add(circ_s(tx, ty, 1.0, cush["dark"], extra=' opacity="0.8"'))
        sp.add(circ_s(tx - 0.3, ty - 0.3, 0.4, "#ffffff", extra=' opacity="0.7"'))
    # armrests
    plank(sp, 1, 8, 6, H - 12, wood, "v", rx=2.0, knot=False)
    plank(sp, W - 7, 8, 6, H - 12, wood, "v", rx=2.0, knot=False)
    # backrest (top edge, on top of everything)
    plank(sp, 1, 1, W - 2, 9, wood, "h", rx=3.0, knot=False)
    for i in range(1, 5):
        sx = 1 + (W - 2) * i / 5
        sp.add(line_s(sx, 2.5, sx, 8.5, wood["dark"], 0.7, 0.45))


def build_bench(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 180 x 60
    wood = MATERIALS["teak"]
    iron = MATERIALS["iron"]
    # iron frame ends (armrest + leg tops), under the seat
    for x in (4.0, W - 12.0):
        metal_bar(sp, x, 6, 8, H - 12, iron, "v", rx=3)
    # seat planks
    wood_surface(sp, 10, 18, W - 20, H - 22, wood, "h", n=3, gap=1.6, rx=1.6)
    # backrest slats on top
    wood_surface(sp, 10, 3, W - 20, 13, wood, "h", n=2, gap=1.2, rx=1.6)
    # armrest caps over the frame
    for x in (2.0, W - 14.0):
        plank(sp, x, 8, 12, 7, wood, "h", rx=2.5, grain=False, knot=False)
    st = MATERIALS["steel"]
    for x in (16, W - 16):
        for y in (22, 34, 46):
            screw(sp, x, y, 1.2, st)


def build_parasol(sp: Sprite) -> None:
    W = sp.w  # 300
    cx = cy = W / 2
    R = 143.0
    a_m = MATERIALS["canvas_cream"]
    b_m = MATERIALS["canvas_red"]
    halo_circle(sp, cx, cy, R + 3, a_m, pad=1.5, op=0.6)
    n = 8
    ga = sp.rad([(0, a_m["light"], None), (60, a_m["mid"], None), (100, a_m["dark"], None)])
    gb = sp.rad([(0, b_m["light"], None), (60, b_m["mid"], None), (100, b_m["dark"], None)])
    for i in range(n):
        a0, a1 = 360 * i / n, 360 * (i + 1) / n
        g = ga if i % 2 == 0 else gb
        # scalloped valance: wedge to R + bulge at the middle of the panel
        r0, r1 = math.radians(a0), math.radians(a1)
        xo0, yo0 = cx + R * math.cos(r0), cy + R * math.sin(r0)
        xo1, yo1 = cx + R * math.cos(r1), cy + R * math.sin(r1)
        rm = math.radians((a0 + a1) / 2)
        bx, by = cx + (R + 7) * math.cos(rm), cy + (R + 7) * math.sin(rm)
        d = (f"M {f1(cx)} {f1(cy)} L {f1(xo0)} {f1(yo0)} Q {f1(bx)} {f1(by)} {f1(xo1)} {f1(yo1)} Z")
        sp.add(path_s(d, f"url(#{g})"))
    # panel fold shading + ribs
    for i in range(n):
        a = math.radians(360 * i / n)
        ex, ey = cx + R * math.cos(a), cy + R * math.sin(a)
        sp.add(line_s(cx, cy, ex, ey, a_m["occ"], 2.2, 0.28))
        sp.add(line_s(cx, cy, ex, ey, "#ffffff", 0.7, 0.35))
        rib = MATERIALS["steel"]
        sp.add(circ_s(ex, ey, 2.2, rib["dark"]))
        sp.add(circ_s(ex - 0.5, ey - 0.5, 1.1, rib["light"], extra=' opacity="0.8"'))
    # gentle dome light
    gd = sp.rad([(0, "#ffffff", 0.22), (55, "#ffffff", 0.0), (100, a_m["occ"], 0.35)])
    sp.add(circ_s(cx, cy, R, f"url(#{gd})"))
    # pole cap + finial
    disc(sp, cx, cy, 9, MATERIALS["brass"], gloss=0.6, rim=1.0)
    disc(sp, cx, cy, 3.5, MATERIALS["steel"], halo=False, gloss=0.6)


def build_lounger(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 70 x 190
    al = MATERIALS["steel"]
    cush = MATERIALS["canvas_blue"]
    stripe = MATERIALS["canvas_cream"]
    # frame rails
    metal_bar(sp, 3, 4, 7, H - 8, al, "v", rx=3)
    metal_bar(sp, W - 10, 4, 7, H - 8, al, "v", rx=3)
    metal_bar(sp, 6, 3, W - 12, 6, al, "h", rx=3)
    metal_bar(sp, 6, H - 9, W - 12, 6, al, "h", rx=3)
    # cushion segments: back / seat / leg
    segs = [(40, 96), (99, 148), (151, 184)]
    for y0, y1 in segs:
        fabric(sp, 10, y0, W - 20, y1 - y0, cush, rx=3.5, stripes=(stripe, 3, "v"), quilt=0.0)
    # head pillow
    fabric(sp, 12, 8, W - 24, 28, stripe, rx=6, hatch=True)
    sp.add(line_s(14, 22, W - 14, 22, stripe["dark"], 0.6, 0.35))
    # hinge marks between segments
    for y in (97.5, 149.5):
        sp.add(line_s(11, y, W - 11, y, al["dark"], 1.0, 0.5))


def build_bbq_grill(sp: Sprite) -> None:
    # 80 x 80 — square: the BBQ is a CIRCLE-tool object, so the canvas renders it
    # into a square footprint (a 80x60 viewBox would be stretched vertically)
    en = MATERIALS["enamel_black"]
    st = MATERIALS["steel"]
    wood = MATERIALS["oak"]
    cx, cy, rx, ry = 34.0, 40.0, 30.0, 30.0
    # side shelf under the body edge
    plank(sp, 62, 20, 16, 40, wood, "v", rx=2.5)
    # utensils on the shelf
    sp.add(line_s(68, 26, 68, 54, st["mid"], 1.6, 0.95))
    sp.add(rect_s(65.5, 24, 5, 5, st["light"], rx=0.8))
    sp.add(line_s(73, 28, 73, 54, st["mid"], 1.6, 0.95))
    sp.add(rect_s(71.5, 25, 3, 3, st["light"], rx=1.5))
    # kettle body (open, grate visible)
    sp.add(ell_s(cx, cy, rx + 1.4, ry + 1.4, en["occ"], extra=' opacity="0.6"'))
    g = sp.rad([(0, en["light"], None), (55, en["mid"], None), (100, en["dark"], None)])
    sp.add(ell_s(cx, cy, rx, ry, f"url(#{g})"))
    # bowl interior (darker) + coals
    sp.add(ell_s(cx, cy, rx - 4, ry - 4, en["dark"]))
    for px, py, r in ((cx - 9, cy - 5, 6), (cx + 6, cy - 7, 5.5), (cx - 2, cy + 6, 6.5), (cx + 11, cy + 4, 5)):
        glow(sp, px, py, r, 0.85)
    # grate bars
    for k in range(-5, 6):
        y = cy + k * 4.0
        half = (rx - 4.5) * math.sqrt(max(1 - (k * 4.0 / (ry - 4.5)) ** 2, 0.0))
        sp.add(line_s(cx - half, y + 0.7, cx + half, y + 0.7, en["occ"], 1.4, 0.55))
        sp.add(line_s(cx - half, y, cx + half, y, st["light"], 1.2, 0.95))
    # rim ring
    sp.add(f'<ellipse cx="{f1(cx)}" cy="{f1(cy)}" rx="{f1(rx - 1.5)}" ry="{f1(ry - 1.5)}" fill="none" '
           f'stroke="{st["mid"]}" stroke-width="2.4"/>')
    sp.add(f'<ellipse cx="{f1(cx)}" cy="{f1(cy)}" rx="{f1(rx - 1.5)}" ry="{f1(ry - 1.5)}" fill="none" '
           f'stroke="{st["light"]}" stroke-width="0.8" opacity="0.7"/>')
    # handles left/right + lid hinge
    metal_bar(sp, 1, cy - 6, 5, 12, st, "v", rx=2)
    screw(sp, cx, cy - ry - 4.5, 1.4, st)


def build_fire_pit(sp: Sprite) -> None:
    W = sp.w  # 100
    cx = cy = W / 2
    stone = MATERIALS["sandstone"]
    ash = MATERIALS["ash"]
    halo_circle(sp, cx, cy, 48, stone, pad=1.4, op=0.6)
    sp.add(circ_s(cx, cy, 48, stone["occ"]))
    # stone ring
    n = 14
    rng = sp.rng
    for i in range(n):
        a0 = 360 * i / n + 1.4
        a1 = 360 * (i + 1) / n - 1.4
        tone = mix(stone["mid"], stone["light"], rng.uniform(0.0, 0.7))
        g = sp.rad([(0, lighten(tone, 0.12), None), (100, stone["dark"], None)],
                   cx=0.5 + 0.42 * math.cos(math.radians((a0 + a1) / 2)),
                   cy=0.5 + 0.42 * math.sin(math.radians((a0 + a1) / 2)), r=0.2)
        sp.add(path_s(wedge_d(cx, cy, 47, a0, a1, ri=36), f"url(#{g})"))
        # crown highlight arc on each stone
        rm = math.radians((a0 + a1) / 2)
        sp.add(circ_s(cx + 41.5 * math.cos(rm), cy + 41.5 * math.sin(rm), 2.6, stone["light"],
                      extra=' opacity="0.35"'))
    # ash bed
    g = sp.rad([(0, ash["mid"], None), (60, ash["dark"], None), (100, ash["occ"], None)])
    sp.add(circ_s(cx, cy, 36, f"url(#{g})"))
    for _ in range(18):
        a, rr = rng.uniform(0, 6.283), rng.uniform(4, 33)
        sp.add(circ_s(cx + rr * math.cos(a), cy + rr * math.sin(a), rng.uniform(0.6, 1.4), ash["light"],
                      extra=f' opacity="{rng.uniform(0.2, 0.45):.2f}"'))
    # embers
    for _ in range(9):
        a, rr = rng.uniform(0, 6.283), rng.uniform(3, 20)
        glow(sp, cx + rr * math.cos(a), cy + rr * math.sin(a), rng.uniform(3, 6), 0.9)
    # logs
    log = MATERIALS["walnut"]
    for ang in (-32, 40, 100):
        with sp.rotated(ang, cx, cy):
            plank(sp, cx - 21, cy - 4, 42, 8, log, "h", rx=3.2, knot=False)
            # charred ends
            sp.add(rect_s(cx - 21, cy - 4, 6, 8, log["occ"], rx=3))
            sp.add(rect_s(cx + 15, cy - 4, 6, 8, log["occ"], rx=3))
    # flames
    for fx, fh, fw, tilt in ((cx - 7, 20, 11, -2), (cx + 6, 24, 12, 2), (cx - 1, 15, 8, 0)):
        flame(sp, fx, cy + 8, fh, fw, tilt)


def build_planter_pot(sp: Sprite) -> None:
    W = sp.w  # 50
    cx = cy = W / 2
    tc = MATERIALS["terracotta"]
    ring(sp, cx, cy, 24, 18.5, tc, crown=0.55)
    sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(23.2)}" fill="none" stroke="{tc["light"]}" '
           f'stroke-width="0.8" opacity="0.5"/>')
    sp.add(circ_s(cx, cy, 18.5, tc["occ"], extra=' opacity="0.9"'))
    granular_fill(sp, cx - 17.5, cy - 17.5, 35, 35, MATERIALS["soil"], clumps=16, size=(0.9, 2.0),
                  shape="circle")


# --------------------------------------------------------------------------- #
# object builders — infrastructure
# --------------------------------------------------------------------------- #
def frame_box(sp: Sprite, x: float, y: float, w: float, h: float, t: float, m: dict[str, str],
              posts: bool = True, rx: float = 1.6) -> None:
    """Rectangular timber frame of thickness t (four planks + corner posts)."""
    # occlusion only under the planks (a full-rect halo would murk the interior)
    for hx, hy, hw, hh in ((x, y, w, t), (x, y + h - t, w, t), (x, y, t, h), (x + w - t, y, t, h)):
        halo_rect(sp, hx, hy, hw, hh, m, pad=1.4, rx=rx + 1, op=0.6)
    plank(sp, x, y, w, t, m, "h", rx=rx, halo=False)
    plank(sp, x, y + h - t, w, t, m, "h", rx=rx, halo=False)
    plank(sp, x, y + t, t, h - 2 * t, m, "v", rx=rx, halo=False)
    plank(sp, x + w - t, y + t, t, h - 2 * t, m, "v", rx=rx, halo=False)
    if posts:
        pm = mix(m["mid"], m["dark"], 0.35)
        st = MATERIALS["steel"]
        for px, py in ((x, y), (x + w - t, y), (x, y + h - t), (x + w - t, y + h - t)):
            halo_rect(sp, px, py, t, t, m, pad=0.8, rx=1.2, op=0.6)
            g = sp.rad([(0, lighten(pm, 0.18), None), (100, m["dark"], None)])
            sp.add(rect_s(px, py, t, t, f"url(#{g})", rx=1.2))
            screw(sp, px + t / 2, py + t / 2, min(t * 0.16, 1.6), st)


def build_raised_bed(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 120 x 80
    wood = MATERIALS["oak"]
    t = 11.0
    sp.add(rect_s(t, t, W - 2 * t, H - 2 * t, MATERIALS["soil"]["occ"]))
    granular_fill(sp, t + 0.5, t + 0.5, W - 2 * t - 1, H - 2 * t - 1, MATERIALS["soil"], clumps=42,
                  size=(1.2, 3.2))
    frame_box(sp, 2, 2, W - 4, H - 4, t - 2, wood)
    # inner shadow of the frame on the soil
    sp.add(f'<rect x="{f1(t)}" y="{f1(t)}" width="{f1(W - 2 * t)}" height="{f1(H - 2 * t)}" fill="none" '
           f'stroke="{wood["occ"]}" stroke-width="2.4" opacity="0.45"/>')


def build_compost_bin(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 100 x 100
    wood = MATERIALS["grey_wood"]
    comp = MATERIALS["compost"]
    t = 12.0
    sp.add(rect_s(t, t, W - 2 * t, H - 2 * t, comp["occ"]))
    granular_fill(sp, t + 0.5, t + 0.5, W - 2 * t - 1, H - 2 * t - 1, comp, clumps=34, size=(1.4, 3.6),
                  bits=9)
    # straw bits
    rng = sp.rng
    straw = MATERIALS["pine"]
    for _ in range(22):
        px, py = rng.uniform(t + 4, W - t - 4), rng.uniform(t + 4, H - t - 4)
        a = rng.uniform(0, 3.1416)
        ln = rng.uniform(3, 7)
        sp.add(line_s(px - ln * math.cos(a), py - ln * math.sin(a), px + ln * math.cos(a),
                      py + ln * math.sin(a), straw["light"], 0.9, rng.uniform(0.5, 0.85)))
    # eggshell flecks
    for _ in range(4):
        px, py = rng.uniform(t + 6, W - t - 6), rng.uniform(t + 6, H - t - 6)
        sp.add(ell_s(px, py, 1.6, 1.1, "#ffffff", extra=' opacity="0.7"'))
    frame_box(sp, 2, 2, W - 4, H - 4, t - 2, wood)
    # slat lines on the frame planks (visible slats stacked in height)
    for x in (2 + (t - 2) / 2, W - 2 - (t - 2) / 2):
        for y in range(18, int(H) - 16, 12):
            sp.add(line_s(x - 3.5, y, x + 3.5, y, wood["dark"], 0.7, 0.45))
    for y in (2 + (t - 2) / 2, H - 2 - (t - 2) / 2):
        for x in range(18, int(W) - 16, 12):
            sp.add(line_s(x, y - 3.5, x, y + 3.5, wood["dark"], 0.7, 0.45))
    sp.add(f'<rect x="{f1(t)}" y="{f1(t)}" width="{f1(W - 2 * t)}" height="{f1(H - 2 * t)}" fill="none" '
           f'stroke="{wood["occ"]}" stroke-width="2.4" opacity="0.5"/>')


def build_cold_frame(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 120 x 60
    wood = MATERIALS["pine"]
    soil = MATERIALS["soil"]
    t = 7.0
    # soil + seedlings under the glass
    sp.add(rect_s(t, t, W - 2 * t, H - 2 * t, soil["occ"]))
    granular_fill(sp, t + 0.5, t + 0.5, W - 2 * t - 1, H - 2 * t - 1, soil, clumps=18, size=(1.0, 2.4))
    gb = MATERIALS["grass_bit"]
    rng = sp.rng
    for row in range(2):
        for col in range(6):
            px = t + 9 + col * 17 + rng.uniform(-1.5, 1.5)
            py = t + 12 + row * 22 + rng.uniform(-1.5, 1.5)
            for k in range(4):
                a = 90 * k + rng.uniform(-12, 12)
                sp.add(rot(a, px, py, ell_s(px, py - 3.2, 1.6, 3.0, gb["mid"], extra=' opacity="0.9"')))
            sp.add(circ_s(px, py, 1.2, gb["light"]))
    # glass panes with muntins
    panes = 3
    pw = (W - 2 * t) / panes
    for i in range(panes):
        glass_pane(sp, t + i * pw + 0.6, t + 0.6, pw - 1.2, H - 2 * t - 1.2, op=0.86, frame=wood)
    for i in range(1, panes):
        plank(sp, t + i * pw - 2, t - 1, 4, H - 2 * t + 2, wood, "v", rx=1, grain=False, knot=False,
              halo=False)
    frame_box(sp, 2, 2, W - 4, H - 4, t - 2, wood, posts=False)
    # hinges + handle
    st = MATERIALS["steel"]
    for x in (24, W / 2, W - 24):
        metal_bar(sp, x - 4, 1.5, 8, 4, st, "h", rx=1.2)
    metal_bar(sp, W / 2 - 7, H - 6.5, 14, 4, st, "h", rx=2)


def build_rain_barrel(sp: Sprite) -> None:
    W = sp.w  # 60
    cx = cy = W / 2
    pl = MATERIALS["plastic_green"]
    st = MATERIALS["steel"]
    # overflow spout at the rim (under the lid edge)
    metal_bar(sp, cx + 20, cy - 4, 9.5, 8, st, "h", rx=2)
    disc(sp, cx, cy, 27, pl, gloss=0.35)
    # concentric lid ridges
    for r, op in ((22, 0.4), (16, 0.35), (10, 0.3)):
        sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(r)}" fill="none" stroke="{pl["dark"]}" '
               f'stroke-width="1.1" opacity="{op:g}"/>')
        sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(r - 1.1)}" fill="none" stroke="{pl["light"]}" '
               f'stroke-width="0.7" opacity="{op - 0.05:g}"/>')
    # lid rim bevel
    sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(25.6)}" fill="none" stroke="{pl["light"]}" '
           f'stroke-width="0.9" opacity="0.45"/>')
    # central cap + handle
    disc(sp, cx, cy, 6.5, pl, gloss=0.4)
    plank(sp, cx - 5, cy - 1.6, 10, 3.2, MATERIALS["rubber"], "h", rx=1.6, grain=False, knot=False,
          bevel=False)


def build_water_tap(sp: Sprite) -> None:
    W = sp.w  # 20
    cx = cy = W / 2
    conc = MATERIALS["concrete"]
    brass = MATERIALS["brass"]
    halo_rect(sp, 3, 3, W - 6, W - 6, conc, pad=1.0, rx=2.5)
    g = sp.rad([(0, conc["light"], None), (60, conc["mid"], None), (100, conc["dark"], None)])
    sp.add(rect_s(3, 3, W - 6, W - 6, f"url(#{g})", rx=2.2))
    # spout toward the right edge with a water drop
    metal_bar(sp, cx, cy - 1.6, 8.5, 3.2, brass, "h", rx=1.6)
    disc(sp, cx + 8.6, cy, 1.4, MATERIALS["water"], halo=False, gloss=0.6)
    # standpipe + cross handle
    disc(sp, cx, cy, 3.6, brass, gloss=0.5)
    inner = ""
    for a in (0, 90):
        inner += rot(a, cx, cy, rect_s(cx - 4.2, cy - 0.9, 8.4, 1.8, brass["mid"], rx=0.9))
    sp.add(rot(20, cx, cy, inner))
    disc(sp, cx, cy, 1.5, brass, halo=False, gloss=0.7)


def build_tool_shed(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 200 x 150
    roof = MATERIALS["shingle"]
    ridge_m = MATERIALS["iron"]
    halo_rect(sp, 3, 3, W - 6, H - 6, roof, pad=1.6, rx=3, op=0.6)
    mid = W / 2
    # two slopes: eave dark → ridge light
    gl = sp.lin([(0, roof["dark"], None), (70, roof["mid"], None), (100, roof["light"], None)], 0, 0, 1, 0)
    gr = sp.lin([(0, roof["light"], None), (30, roof["mid"], None), (100, roof["dark"], None)], 0, 0, 1, 0)
    sp.add(rect_s(3, 3, mid - 3, H - 6, f"url(#{gl})", rx=2))
    sp.add(rect_s(mid, 3, mid - 3, H - 6, f"url(#{gr})", rx=2))
    # shingle rows (scalloped lines parallel to the ridge, scallops facing the eave)
    row = 9.0
    sh = 8.0
    k = 1
    while mid - k * row > 8:
        for side in (-1, 1):
            x = mid + side * k * row
            y = 4.0
            d = f"M {f1(x)} {f1(y)}"
            while y < H - 4:
                y2 = min(y + sh, H - 4.0)
                bulge = x + side * 2.6
                d += f" Q {f1(bulge)} {f1((y + y2) / 2)} {f1(x)} {f1(y2)}"
                y = y2
            sp.add(f'<path d="{d}" fill="none" stroke="{roof["occ"]}" stroke-width="1.6" opacity="0.7"/>')
            sp.add(f'<path d="{d}" fill="none" stroke="{roof["light"]}" stroke-width="0.8" opacity="0.5" '
                   f'transform="translate({f1(-side * 1.3)} 0)"/>')
        k += 1
    # ridge cap
    metal_bar(sp, mid - 3.5, 2, 7, H - 4, ridge_m, "v", rx=2)
    # skylight on the right slope
    halo_rect(sp, mid + 34, 42, 30, 34, roof, pad=1.2, rx=1.5, op=0.7)
    glass_pane(sp, mid + 34, 42, 30, 34, op=0.85, frame=MATERIALS["steel"])
    # roof vent on the left slope
    disc(sp, mid - 55, 40, 7, MATERIALS["steel"], gloss=0.4)
    sp.add(circ_s(mid - 55, 40, 3, MATERIALS["steel"]["occ"], extra=' opacity="0.85"'))
    # gutters along both eaves
    metal_bar(sp, 1.5, 6, 3.5, H - 12, MATERIALS["steel"], "v", rx=1.5)
    metal_bar(sp, W - 5, 6, 3.5, H - 12, MATERIALS["steel"], "v", rx=1.5)


# --------------------------------------------------------------------------- #
# object builders — new roster (#308)
# --------------------------------------------------------------------------- #
def build_sandbox(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 150 x 150
    wood = MATERIALS["pine"]
    sand = MATERIALS["sand"]
    t = 12.0
    sp.add(rect_s(t, t, W - 2 * t, H - 2 * t, sand["occ"]))
    granular_fill(sp, t + 0.5, t + 0.5, W - 2 * t - 1, H - 2 * t - 1, sand, clumps=70, size=(0.7, 1.6))
    rng = sp.rng
    # dug hollows and mounds
    for _ in range(3):
        px, py = rng.uniform(t + 20, W - t - 20), rng.uniform(t + 20, H - t - 20)
        sp.add(ell_s(px, py, rng.uniform(8, 14), rng.uniform(6, 10), sand["dark"], extra=' opacity="0.22"'))
    for _ in range(2):
        px, py = rng.uniform(t + 20, W - t - 20), rng.uniform(t + 20, H - t - 20)
        sp.add(ell_s(px, py, rng.uniform(7, 11), rng.uniform(5, 8), sand["light"], extra=' opacity="0.5"'))
    frame_box(sp, 2, 2, W - 4, H - 4, t - 2, wood, posts=False)
    # corner seat boards (triangles)
    for (ax, ay, bx, by, cx_, cy_) in ((2, 2, 40, 2, 2, 40), (W - 2, 2, W - 40, 2, W - 2, 40),
                                       (2, H - 2, 40, H - 2, 2, H - 40), (W - 2, H - 2, W - 40, H - 2, W - 2, H - 40)):
        d = f"M {f1(ax)} {f1(ay)} L {f1(bx)} {f1(by)} L {f1(cx_)} {f1(cy_)} Z"
        sp.add(path_s(d, wood["occ"], extra=' opacity="0.6" transform="translate(0.8 0.8)"'))
        g = sp.lin([(0, wood["dark"], None), (50, wood["light"], None), (100, wood["dark"], None)], 0, 0, 1, 1)
        sp.add(path_s(d, f"url(#{g})"))
        sp.add(line_s((ax + bx) / 2, (ay + by) / 2 + (1 if ay < H / 2 else -1) * 3, (ax + cx_) / 2 + (1 if ax < W / 2 else -1) * 3,
                      (ay + cy_) / 2, wood["line"], 0.6, 0.45))
    # toys: bucket, spade, ball
    red = MATERIALS["enamel_red"]
    bx, by = W * 0.36, H * 0.6
    disc(sp, bx, by, 9, red, gloss=0.45)
    ring(sp, bx, by, 9, 6.5, red, halo=False, crown=0.4)
    sp.add(f'<path d="M {f1(bx - 8)} {f1(by)} A 8 8 0 0 1 {f1(bx + 8)} {f1(by)}" fill="none" '
           f'stroke="{MATERIALS["steel"]["mid"]}" stroke-width="1.2" opacity="0.9"/>')
    yel = MATERIALS["plastic_yellow"]
    sx, sy = W * 0.62, H * 0.42
    with sp.rotated(-35, sx, sy):
        sp.add(rect_s(sx - 2, sy - 16, 4, 24, yel["mid"], rx=2))
        sp.add(line_s(sx - 0.8, sy - 14, sx - 0.8, sy + 6, yel["light"], 0.6, 0.6))
        g = sp.lin([(0, yel["dark"], None), (50, yel["light"], None), (100, yel["dark"], None)], 0, 0, 1, 0)
        sp.add(path_s(f"M {f1(sx - 6)} {f1(sy + 6)} L {f1(sx + 6)} {f1(sy + 6)} L {f1(sx + 5)} {f1(sy + 20)} "
                      f"Q {f1(sx)} {f1(sy + 24)} {f1(sx - 5)} {f1(sy + 20)} Z", f"url(#{g})"))
    disc(sp, W * 0.7, H * 0.72, 6, MATERIALS["plastic_blue"], gloss=0.6)


def build_trampoline(sp: Sprite) -> None:
    W = sp.w  # 300
    cx = cy = W / 2
    pad = MATERIALS["plastic_blue"]
    mat_m = MATERIALS["rubber"]
    st = MATERIALS["steel"]
    R = 148.0
    ring(sp, cx, cy, R, R - 30, pad, crown=0.5)
    # pad piping + stitched segments
    for r, col, op in ((R - 2.5, pad["light"], 0.5), (R - 27.5, pad["light"], 0.4)):
        sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(r)}" fill="none" stroke="{col}" '
               f'stroke-width="1.2" opacity="{op:g}"/>')
    for i in range(12):
        a = math.radians(360 * i / 12 + 15)
        sp.add(line_s(cx + (R - 28) * math.cos(a), cy + (R - 28) * math.sin(a), cx + (R - 2) * math.cos(a),
                      cy + (R - 2) * math.sin(a), pad["dark"], 1.4, 0.55))
    # spring gap ring + springs
    sp.add(path_s(annulus_d(cx, cy, R - 30, R - 40), mat_m["occ"], extra=' opacity="0.85"'))
    for i in range(36):
        a = math.radians(360 * i / 36)
        sp.add(line_s(cx + (R - 39) * math.cos(a), cy + (R - 39) * math.sin(a), cx + (R - 31) * math.cos(a),
                      cy + (R - 31) * math.sin(a), st["light"], 1.6, 0.9))
    # mat
    rm = R - 40
    g = sp.rad([(0, mat_m["light"], None), (55, mat_m["mid"], None), (100, mat_m["dark"], None)], r=0.55)
    sp.add(circ_s(cx, cy, rm, f"url(#{g})"))
    step = 11.0
    k = 1
    while k * step < rm - 2:
        d = k * step
        half = chord(rm - 1, d)
        for sgn in (-1, 1):
            sp.add(line_s(cx - half, cy + sgn * d, cx + half, cy + sgn * d, mat_m["light"], 0.5, 0.18, cap="butt"))
            sp.add(line_s(cx + sgn * d, cy - half, cx + sgn * d, cy + half, mat_m["light"], 0.5, 0.18, cap="butt"))
        k += 1
    sp.add(line_s(cx - rm + 1, cy, cx + rm - 1, cy, mat_m["light"], 0.5, 0.18, cap="butt"))
    sp.add(line_s(cx, cy - rm + 1, cx, cy + rm - 1, mat_m["light"], 0.5, 0.18, cap="butt"))
    # jump-zone marker
    sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="26" fill="none" stroke="{pad["light"]}" '
           f'stroke-width="1.6" opacity="0.35"/>')
    sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="8" fill="none" stroke="{pad["light"]}" '
           f'stroke-width="1.6" opacity="0.35"/>')
    # net top edge + padded poles
    sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(R - 14)}" fill="none" stroke="#ffffff" '
           f'stroke-width="0.9" opacity="0.4"/>')
    for i in range(6):
        a = math.radians(360 * i / 6 + 30)
        px, py = cx + (R - 14) * math.cos(a), cy + (R - 14) * math.sin(a)
        disc(sp, px, py, 6.5, pad, gloss=0.3)
        disc(sp, px, py, 2.6, st, halo=False, gloss=0.6)


def build_hot_tub(sp: Sprite) -> None:
    W = sp.w  # 220 x 220
    wood = MATERIALS["teak"]
    st = MATERIALS["steel"]
    rx = 22.0
    halo_rect(sp, 3, 3, W - 6, W - 6, wood, pad=1.6, rx=rx, op=0.6)
    g = sp.rad([(0, wood["light"], None), (70, wood["mid"], None), (100, wood["dark"], None)], r=0.72)
    sp.add(rect_s(3, 3, W - 6, W - 6, f"url(#{g})", rx=rx))
    # cladding staves around the rim (short lines perpendicular to each edge)
    t = 26.0
    for x in range(int(rx) + 4, int(W - rx) - 2, 8):
        sp.add(line_s(x, 4, x, t - 2, wood["dark"], 0.9, 0.5))
        sp.add(line_s(x + 1, 4, x + 1, t - 2, wood["light"], 0.5, 0.35))
        sp.add(line_s(x, W - t + 2, x, W - 4, wood["dark"], 0.9, 0.5))
        sp.add(line_s(x + 1, W - t + 2, x + 1, W - 4, wood["light"], 0.5, 0.35))
        sp.add(line_s(4, x, t - 2, x, wood["dark"], 0.9, 0.5))
        sp.add(line_s(4, x + 1, t - 2, x + 1, wood["light"], 0.5, 0.35))
        sp.add(line_s(W - t + 2, x, W - 4, x, wood["dark"], 0.9, 0.5))
        sp.add(line_s(W - t + 2, x + 1, W - 4, x + 1, wood["light"], 0.5, 0.35))
    bevel_frame(sp, 3, 3, W - 6, W - 6, wood, rx=rx)
    # water basin
    bx, bw, brx = t, W - 2 * t, 14.0
    sp.add(rect_s(bx - 1.5, bx - 1.5, bw + 3, bw + 3, wood["occ"], rx=brx + 1.5, extra=' opacity="0.7"'))
    water_fill(sp, "rect", bx, bx, bw, bw, rx=brx, ripples=4, sparkle=14, r_light=0.6)
    # submerged seats in the corners
    wm = MATERIALS["water"]
    for sx, sy in ((bx + 26, bx + 26), (bx + bw - 26, bx + 26), (bx + 26, bx + bw - 26), (bx + bw - 26, bx + bw - 26)):
        sp.add(ell_s(sx, sy, 24, 24, wm["light"], extra=' opacity="0.28"'))
    # jets along the rim + bubbles
    for i in range(3):
        for sx, sy in ((bx + bw * (i + 1) / 4, bx + 5), (bx + bw * (i + 1) / 4, bx + bw - 5),
                       (bx + 5, bx + bw * (i + 1) / 4), (bx + bw - 5, bx + bw * (i + 1) / 4)):
            disc(sp, sx, sy, 2.4, st, halo=False, gloss=0.5)
    rng = sp.rng
    for _ in range(26):
        px, py = rng.uniform(bx + 12, bx + bw - 12), rng.uniform(bx + 12, bx + bw - 12)
        r = rng.uniform(0.9, 2.4)
        sp.add(f'<circle cx="{f1(px)}" cy="{f1(py)}" r="{f1(r)}" fill="none" stroke="#ffffff" '
               f'stroke-width="0.6" opacity="{rng.uniform(0.35, 0.7):.2f}"/>')
    # control panel on the rim
    halo_rect(sp, W / 2 - 12, 8, 24, 10, MATERIALS["rubber"], pad=0.8, rx=2)
    g = sp.lin([(0, MATERIALS["rubber"]["mid"], None), (100, MATERIALS["rubber"]["dark"], None)], 0, 0, 0, 1)
    sp.add(rect_s(W / 2 - 12, 8, 24, 10, f"url(#{g})", rx=2))
    for i, col in enumerate((MATERIALS["plastic_blue"], MATERIALS["enamel_red"], MATERIALS["plastic_green"])):
        disc(sp, W / 2 - 7 + i * 7, 13, 1.8, col, halo=False, gloss=0.6)


def build_wheelbarrow(sp: Sprite) -> None:
    W = sp.w  # 60 x 140 (wheel at top, handles at bottom)
    en = MATERIALS["enamel_green"]
    st = MATERIALS["steel"]
    wood = MATERIALS["oak"]
    rub = MATERIALS["rubber"]
    cx = W / 2
    # legs + fork under the tub
    metal_bar(sp, cx - 16, 84, 4, 20, st, "v", rx=1.5)
    metal_bar(sp, cx + 12, 84, 4, 20, st, "v", rx=1.5)
    metal_bar(sp, cx - 7, 8, 3, 30, st, "v", rx=1.5)
    metal_bar(sp, cx + 4, 8, 3, 30, st, "v", rx=1.5)
    # wheel
    disc(sp, cx, 15, 10.5, rub, gloss=0.0)
    sp.add(f'<circle cx="{f1(cx)}" cy="15" r="8.2" fill="none" stroke="{rub["light"]}" stroke-width="0.7" opacity="0.4"/>')
    disc(sp, cx, 15, 3.6, st, halo=False, gloss=0.6)
    # handles (under tub end)
    for hx in (cx - 20, cx + 16):
        plank(sp, hx, 90, 4.5, 46, wood, "v", rx=2.2, knot=False)
        halo_rect(sp, hx - 0.5, 122, 5.5, 14, rub, pad=0.6, rx=2.5)
        sp.add(rect_s(hx - 0.5, 122, 5.5, 14, rub["mid"], rx=2.5))
        sp.add(line_s(hx + 1.2, 124, hx + 1.2, 134, rub["light"], 0.5, 0.5))
    # tub
    tub_d = (f"M {f1(cx - 21)} {f1(100)} L {f1(cx - 25)} {f1(46)} Q {f1(cx - 25)} {f1(24)} {f1(cx)} {f1(22)} "
             f"Q {f1(cx + 25)} {f1(24)} {f1(cx + 25)} {f1(46)} L {f1(cx + 21)} {f1(100)} "
             f"Q {f1(cx)} {f1(107)} {f1(cx - 21)} {f1(100)} Z")
    sp.add(path_s(tub_d, en["occ"], extra=f' stroke="{en["occ"]}" stroke-width="2.4" stroke-linejoin="round" opacity="0.6"'))
    g = sp.rad([(0, en["light"], None), (55, en["mid"], None), (100, en["dark"], None)], cy=0.55, r=0.62)
    sp.add(path_s(tub_d, f"url(#{g})"))
    # inner well + load
    sp.add(ell_s(cx, 63, 18.5, 30, en["dark"]))
    sp.add(ell_s(cx, 63, 17, 28.5, en["occ"], extra=' opacity="0.7"'))
    granular_fill(sp, cx - 15, 40, 30, 46, MATERIALS["soil"], clumps=14, size=(1.0, 2.6), bits=3, shape="circle")
    # rim highlight
    sp.add(f'<path d="{tub_d}" fill="none" stroke="{en["light"]}" stroke-width="1.0" opacity="0.5"/>')


def build_pergola(sp: Sprite) -> None:
    W = sp.w  # 300 x 300
    wood = MATERIALS["oak"]
    post = mix(wood["mid"], wood["dark"], 0.4)
    # posts
    for px, py in ((10, 10), (W - 26, 10), (10, W - 26), (W - 26, W - 26)):
        halo_rect(sp, px, py, 16, 16, wood, pad=1.2, rx=2)
        g = sp.rad([(0, lighten(post, 0.2), None), (100, wood["dark"], None)])
        sp.add(rect_s(px, py, 16, 16, f"url(#{g})", rx=2))
    # rafters (running along y)
    n = 9
    span = W - 60
    for i in range(n):
        x = 30 + span * i / (n - 1) - 4
        plank(sp, x, 0, 8, W, wood, "v", rx=1.5)
    # perimeter beams (along x) over the rafters
    plank(sp, 0, 6, W, 12, wood, "h", rx=2)
    plank(sp, 0, W - 18, W, 12, wood, "h", rx=2)
    # side beams (along y) over the ends
    plank(sp, 6, 0, 12, W, wood, "v", rx=2)
    plank(sp, W - 18, 0, 12, W, wood, "v", rx=2)
    # top purlins (thin cross slats)
    for k in range(1, 6):
        y = 18 + (W - 36) * k / 6 - 2.5
        plank(sp, 4, y, W - 8, 5, wood, "h", rx=1.5, grain=False, knot=False)


def build_swing(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 200 x 150
    wood = MATERIALS["pine"]
    rope = MATERIALS["sandstone"]
    seat_m = MATERIALS["plastic_blue"]
    cy = H / 2 - 12
    # A-frame legs: from the beam outward to the feet, splayed 8 units toward the ends
    L = 64.0
    splay = math.degrees(math.atan2(8.0, L))
    for ex, sgn in ((14.0, 1), (W - 14.0, -1)):
        for dy in (-1, 1):
            with sp.rotated(sgn * dy * splay, ex, cy):
                plank(sp, ex - 3.5, cy if dy > 0 else cy - L, 7, L, wood, "v", rx=3, knot=False)
    # feet caps at the leg ends
    for fx, fy in ((6, cy - 62), (6, cy + 62), (W - 6, cy - 62), (W - 6, cy + 62)):
        disc(sp, fx, fy, 3.2, MATERIALS["rubber"], gloss=0.2)
    # top beam
    plank(sp, 3, cy - 6, W - 6, 12, wood, "h", rx=3)
    # seats swung forward with ropes
    for sx in (W * 0.34, W * 0.66):
        sy = cy + 40
        for dx in (-13, 13):
            sp.add(line_s(sx + dx, cy + 3, sx + dx, sy - 1, rope["dark"], 1.6, 0.9))
            sp.add(line_s(sx + dx, cy + 3, sx + dx, sy - 1, rope["light"], 0.6, 0.6))
        halo_rect(sp, sx - 17, sy - 5, 34, 10, seat_m, pad=1.0, rx=3)
        g = sp.lin([(0, seat_m["dark"], None), (50, seat_m["light"], None), (100, seat_m["dark"], None)], 0, 0, 0, 1)
        sp.add(rect_s(sx - 17, sy - 5, 34, 10, f"url(#{g})", rx=3))
        sp.add(line_s(sx - 14, sy, sx + 14, sy, seat_m["light"], 0.6, 0.4))
    # rope hooks on the beam
    for sx in (W * 0.34 - 13, W * 0.34 + 13, W * 0.66 - 13, W * 0.66 + 13):
        screw(sp, sx, cy, 1.5)


def build_picnic_table(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 180 x 150
    wood = MATERIALS["oak"]
    # A-frame legs under everything: from the table centre line out to the bench edges
    L = H / 2 - 8
    for ex in (16.0, W - 16.0):
        for dy in (-1, 1):
            with sp.rotated(dy * 9, ex, H / 2):
                plank(sp, ex - 3.5, H / 2 if dy > 0 else H / 2 - L, 7, L, mix_mat(wood, 0.35), "v", rx=2.5,
                      knot=False, grain=False)
    # benches
    wood_surface(sp, 14, 6, W - 28, 24, wood, "h", n=2, gap=1.4)
    wood_surface(sp, 14, H - 30, W - 28, 24, wood, "h", n=2, gap=1.4)
    # table top
    wood_surface(sp, 6, 38, W - 12, H - 76, wood, "h", n=5, gap=1.4)
    bevel_frame(sp, 6, 38, W - 12, H - 76, wood, rx=1.6)
    st = MATERIALS["steel"]
    for x in (18, W - 18):
        for y in (46, H / 2, H - 46):
            screw(sp, x, y, 1.3, st)


def build_hammock(sp: Sprite) -> None:
    W, H = sp.w, sp.h  # 300 x 120
    wood = MATERIALS["walnut"]
    fab_a = MATERIALS["canvas_teal"]
    fab_b = MATERIALS["canvas_cream"]
    rope = MATERIALS["sandstone"]
    cy = H / 2
    # stand: base spreader + end bars
    plank(sp, 14, cy - 5, W - 28, 10, mix_mat(wood, 0.3), "h", rx=3, knot=False)
    plank(sp, 4, 18, 12, H - 36, wood, "v", rx=3, knot=False)
    plank(sp, W - 16, 18, 12, H - 36, wood, "v", rx=3, knot=False)
    # rope fans from posts to spreader bars
    a, b = 100.0, 34.0
    cx = W / 2
    for side in (-1, 1):
        px = cx + side * (a + 30)
        bx = cx + side * (a - 6)
        for k in range(5):
            t = -1 + 2 * k / 4
            sp.add(line_s(px - side * 4, cy + t * 8, bx, cy + t * b * 0.9, rope["dark"], 1.3, 0.9))
    # fabric body: 24 stripe facets following an ellipse silhouette
    n = 24
    for i in range(n):
        x0 = cx - a + 2 * a * i / n
        x1 = cx - a + 2 * a * (i + 1) / n
        h0 = b * math.sqrt(max(1 - ((x0 - cx) / a) ** 2, 0.0))
        h1 = b * math.sqrt(max(1 - ((x1 - cx) / a) ** 2, 0.0))
        m = fab_a if i % 2 == 0 else fab_b
        g = sp.lin([(0, m["dark"], None), (50, m["mid"], None), (100, m["dark"], None)], 0, 0, 0, 1)
        d = (f"M {f1(x0)} {f1(cy - h0)} L {f1(x1)} {f1(cy - h1)} L {f1(x1)} {f1(cy + h1)} "
             f"L {f1(x0)} {f1(cy + h0)} Z")
        sp.add(path_s(d, f"url(#{g})"))
    # sag folds + puff shading
    for t in (-0.55, -0.2, 0.2, 0.55):
        yy = cy + t * b
        d = f"M {f1(cx - a * 0.92)} {f1(cy + t * 4)} Q {f1(cx)} {f1(yy + t * 6)} {f1(cx + a * 0.92)} {f1(cy + t * 4)}"
        sp.add(f'<path d="{d}" fill="none" stroke="{fab_a["occ"]}" stroke-width="0.8" opacity="0.28"/>')
    gp = sp.rad([(0, "#ffffff", 0.2), (60, "#ffffff", 0.0), (100, fab_a["occ"], 0.45)], r=0.5)
    sp.add(ell_s(cx, cy, a, b, f"url(#{gp})"))
    # spreader bars over the fabric ends
    for side in (-1, 1):
        bx = cx + side * (a - 6)
        plank(sp, bx - 2.5, cy - b, 5, 2 * b, wood, "v", rx=2, knot=False, grain=False)


def build_bird_bath(sp: Sprite) -> None:
    W = sp.w  # 50
    cx = cy = W / 2
    stone = MATERIALS["stone"]
    disc(sp, cx, cy, 24, stone, gloss=0.0)
    ring(sp, cx, cy, 24, 18.5, stone, halo=False, crown=0.6)
    sp.add(f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(23)}" fill="none" stroke="{stone["light"]}" '
           f'stroke-width="0.7" opacity="0.5"/>')
    sp.add(circ_s(cx, cy, 18.5, stone["occ"], extra=' opacity="0.8"'))
    water_fill(sp, "circle", cx - 17.5, cy - 17.5, 35, 35, ripples=3, sparkle=6, r_light=0.5)
    # floating leaf
    gb = MATERIALS["grass_bit"]
    sp.add(rot(28, cx + 6, cy - 5, ell_s(cx + 6, cy - 5, 3.4, 1.7, gb["mid"], extra=' opacity="0.95"')))
    sp.add(rot(28, cx + 6, cy - 5, line_s(cx + 3, cy - 5, cx + 9, cy - 5, gb["dark"], 0.5, 0.7)))


# --------------------------------------------------------------------------- #
# recipe table — name → dict(view=(w, h), dir=..., build=callable, shape=rect|circle)
# --------------------------------------------------------------------------- #
_KNOWN_KEYS = frozenset({"view", "dir", "build", "shape"})

OBJECTS: dict[str, dict] = {
    # furniture (existing)
    "table_rectangular": dict(view=(150, 100), dir="furniture", build=build_table_rectangular, shape="rect"),
    "table_round": dict(view=(100, 100), dir="furniture", build=build_table_round, shape="circle"),
    "chair": dict(view=(50, 50), dir="furniture", build=build_chair, shape="rect"),
    "bench": dict(view=(180, 60), dir="furniture", build=build_bench, shape="rect"),
    "parasol": dict(view=(300, 300), dir="furniture", build=build_parasol, shape="circle"),
    "lounger": dict(view=(70, 190), dir="furniture", build=build_lounger, shape="rect"),
    "bbq_grill": dict(view=(80, 80), dir="furniture", build=build_bbq_grill, shape="circle"),
    "fire_pit": dict(view=(100, 100), dir="furniture", build=build_fire_pit, shape="circle"),
    "planter_pot": dict(view=(50, 50), dir="furniture", build=build_planter_pot, shape="circle"),
    # infrastructure (existing)
    "raised_bed": dict(view=(120, 80), dir="infrastructure", build=build_raised_bed, shape="rect"),
    "compost_bin": dict(view=(100, 100), dir="infrastructure", build=build_compost_bin, shape="rect"),
    "cold_frame": dict(view=(120, 60), dir="infrastructure", build=build_cold_frame, shape="rect"),
    "rain_barrel": dict(view=(60, 60), dir="infrastructure", build=build_rain_barrel, shape="circle"),
    "water_tap": dict(view=(20, 20), dir="infrastructure", build=build_water_tap, shape="rect"),
    "tool_shed": dict(view=(200, 150), dir="infrastructure", build=build_tool_shed, shape="rect"),
    # new roster (#308)
    "sandbox": dict(view=(150, 150), dir="furniture", build=build_sandbox, shape="rect"),
    "trampoline": dict(view=(300, 300), dir="furniture", build=build_trampoline, shape="circle"),
    "hot_tub": dict(view=(220, 220), dir="furniture", build=build_hot_tub, shape="rect"),
    "swing": dict(view=(200, 150), dir="furniture", build=build_swing, shape="rect"),
    "picnic_table": dict(view=(180, 150), dir="furniture", build=build_picnic_table, shape="rect"),
    "hammock": dict(view=(300, 120), dir="furniture", build=build_hammock, shape="rect"),
    "wheelbarrow": dict(view=(60, 140), dir="infrastructure", build=build_wheelbarrow, shape="rect"),
    "pergola": dict(view=(300, 300), dir="infrastructure", build=build_pergola, shape="rect"),
    "bird_bath": dict(view=(50, 50), dir="infrastructure", build=build_bird_bath, shape="circle"),
}


def build_object(name: str, cfg: dict) -> str:
    unknown = set(cfg) - _KNOWN_KEYS
    if unknown:
        raise ValueError(f"{name}: unknown recipe keys {sorted(unknown)}")
    w, h = cfg["view"]
    sp = Sprite(name, w, h, random.Random(f"ogp-object-{name}"))
    cfg["build"](sp)
    return sp.svg()


def generate_all() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for name, cfg in OBJECTS.items():
        d = FURNITURE_DIR if cfg["dir"] == "furniture" else INFRASTRUCTURE_DIR
        out[d / f"{name}.svg"] = build_object(name, cfg)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify committed files match regeneration (no writes)")
    parser.add_argument("--only", nargs="*", default=None,
                        help="restrict to these object names (stems)")
    args = parser.parse_args(argv)

    files = generate_all()
    if args.only:
        wanted = set(args.only)
        files = {p: t for p, t in files.items() if p.stem in wanted}
        missing = wanted - {p.stem for p in files}
        if missing:
            print(f"unknown object names: {sorted(missing)}")
            return 2

    drift = []
    for path, text in sorted(files.items()):
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                drift.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    if args.check:
        if drift:
            print(f"DRIFT: {len(drift)} file(s) differ from regeneration:")
            for path in drift:
                print(f"  {path}")
            return 1
        print(f"OK: {len(files)} object sprite files match regeneration")
        return 0
    print(f"wrote {len(files)} object sprite files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
