"""Generate all plant sprite SVGs (108 species + 15 categories) — issue #281.

This script IS the provenance record for every file under
`src/open_garden_planner/resources/plants/` (see PROVENANCE.md there).
Style contract: resources/plants/README.md ("Lush Sprite" — user-approved
2026-07-26). Key rules:

- Top-down view, radial shading only (light from straight above) — sprites
  stay correct under the per-item random rotation applied by
  `core/plant_renderer.py`.
- Individual leaves in shingled rings; per-leaf gradient from warm light tip
  to cool dark base; dark occlusion copy under every leaf; glossy fruit and
  chunky bloom clusters with occlusion + specular.
- QtSvg subset only (QSvgRenderer ≈ SVG 1.2 Tiny): linear/radial gradients,
  opacity, transforms. No filters, masks, clipPath, CSS, text.
- Deterministic: seeded per sprite name — identical bytes on every run.

Usage:
    venv/Scripts/python.exe scripts/generate_plant_sprites.py           # write all
    venv/Scripts/python.exe scripts/generate_plant_sprites.py --check   # verify no drift
    venv/Scripts/python.exe scripts/generate_plant_sprites.py --only tomato lettuce
"""

# ruff: noqa: C408 - dict() keyword style is deliberate: the 123-entry recipe
# tables read far better as dict(a=..., pal=...) than as quoted-key literals.

from __future__ import annotations

import argparse
import colorsys
import math
import random
import sys
from pathlib import Path

PLANTS_DIR = Path(__file__).parent.parent / "src" / "open_garden_planner" / "resources" / "plants"
SPECIES_DIR = PLANTS_DIR / "species"
CATEGORIES_DIR = PLANTS_DIR / "categories"


# --------------------------------------------------------------------------- #
# color helpers
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


# palette = leaf-ring color anchors: tip outer->inner, base outer->inner + occlusion + rib
def pal(t0: str, t1: str, b0: str, b1: str, occ: str, rib: str) -> dict[str, str]:
    return {"t0": t0, "t1": t1, "b0": b0, "b1": b1, "occ": occ, "rib": rib}


PALETTES: dict[str, dict[str, str]] = {
    # approved in the #281 style lab
    "fresh": pal("#54ab4b", "#b7f094", "#1b5a2e", "#4aa557", "#0f3d22", "#1c5230"),
    "crisp": pal("#5cb63e", "#a8e678", "#276e1d", "#55a53a", "#143f10", "#2c6e1e"),
    "silver": pal("#93b287", "#c7dabc", "#42603c", "#66875e", "#26381f", "#3f5b39"),
    # supporting families
    "dark": pal("#3d8f45", "#8fd07a", "#12452a", "#2f7f42", "#092e18", "#144a2c"),
    "teal": pal("#4f9070", "#a8d8b8", "#1d4a38", "#3c7a5c", "#0f2e21", "#1e5240"),
    "yellow": pal("#7dbb45", "#d6ef9a", "#3f7423", "#6aa63d", "#23480f", "#33641c"),
    "olive": pal("#7d9c4a", "#c3d795", "#46601f", "#6d8a3a", "#2a3c11", "#3e5519"),
    "redleaf": pal("#a04a52", "#d99aa0", "#5c1f28", "#8a3a44", "#3a1016", "#5c1f28"),
    "autumn": pal("#b3703c", "#e8b06a", "#6b3318", "#96562a", "#401c0a", "#6b3318"),
}

# fruit / berry gradient triads: (highlight, mid, dark)
FRUITS: dict[str, tuple[str, str, str]] = {
    "apple": ("#ff8a63", "#e33f28", "#941106"),
    "cherry": ("#ff7a6e", "#d92c3a", "#8a0f1f"),
    "plum": ("#9d8fdd", "#6a55b8", "#3b2f78"),
    "peach": ("#ffc08a", "#f08a4a", "#b35418"),
    "pear": ("#e4e08a", "#c3cf56", "#8a9a2e"),
    "lemon": ("#fff2a0", "#f2d549", "#c9a422"),
    "orange": ("#ffc069", "#f2952e", "#c26a10"),
    "olive": ("#7a8a52", "#4a5630", "#2a3418"),
    "fig": ("#8a6a9d", "#5c3f78", "#33204a"),
    "nut": ("#c9d47a", "#a3b34e", "#6b7a2a"),
    "blueberry": ("#8fa4e0", "#5468b8", "#2c3a78"),
    "blackberry": ("#7a6a94", "#443a5e", "#201a30"),
    "gooseberry": ("#d8e89a", "#a8c860", "#6e8a34"),
    "tomato": ("#ff8a63", "#e8402a", "#9c1608"),
    "green": ("#b8d878", "#7aa843", "#476b22"),
    "eggplant": ("#7a5bb5", "#4a2f80", "#291452"),
    "pumpkin": ("#ffb35c", "#ef8324", "#b3540c"),
    "butternut": ("#f0d09a", "#d4a860", "#9a7232"),
}

# flower petal specs: (petal_outer, petal_tip_light, center)
FLOWERS: dict[str, tuple[str, str, str]] = {
    "white": ("#e8e4d8", "#fbf9f2", "#e8c34a"),
    "pink": ("#e88aa8", "#f7c3d3", "#e8c34a"),
    "rose_red": ("#c9384f", "#ef7f92", "#8a1c30"),
    "magenta": ("#c04a94", "#e894c4", "#f0d060"),
    "purple": ("#8a5fc0", "#c3a3e8", "#f0d060"),
    "violet_face": ("#6a4aa8", "#9a7fd0", "#f2cf4e"),
    "blue": ("#5c7fd0", "#a3b8ec", "#f0d060"),
    "yellow": ("#f2c53a", "#fae48a", "#c98a1e"),
    "gold": ("#f0a832", "#f8cf6e", "#a86414"),
    "orange": ("#ef8330", "#f8b878", "#b3540c"),
    "red": ("#d8402e", "#f28a70", "#8a1608"),
    "cream": ("#f2ecd0", "#fbf8ea", "#d8b84a"),
    "lilac": ("#a98fe0", "#d0c0f0", "#6b46ab"),
}


# --------------------------------------------------------------------------- #
# geometry primitives
# --------------------------------------------------------------------------- #
def leaf_d(yt: float, yb: float, w: float, cx: float = 50.0, frilly: bool = False) -> str:
    ln = yb - yt
    if frilly:
        return (
            f"M {cx:.1f} {yt:.1f} "
            f"C {cx + w * 0.72:.1f} {yt + ln * 0.10:.1f}, {cx + w * 0.30:.1f} {yt + ln * 0.26:.1f}, "
            f"{cx + w * 0.60:.1f} {yt + ln * 0.40:.1f} "
            f"C {cx + w * 0.88:.1f} {yt + ln * 0.52:.1f}, {cx + w * 0.42:.1f} {yt + ln * 0.72:.1f}, {cx:.1f} {yb:.1f} "
            f"C {cx - w * 0.42:.1f} {yt + ln * 0.72:.1f}, {cx - w * 0.88:.1f} {yt + ln * 0.52:.1f}, "
            f"{cx - w * 0.60:.1f} {yt + ln * 0.40:.1f} "
            f"C {cx - w * 0.30:.1f} {yt + ln * 0.26:.1f}, {cx - w * 0.72:.1f} {yt + ln * 0.10:.1f}, {cx:.1f} {yt:.1f} Z"
        )
    return (
        f"M {cx:.1f} {yt:.1f} "
        f"C {cx + w * 0.58:.1f} {yt + ln * 0.22:.1f}, {cx + w * 0.52:.1f} {yb - ln * 0.28:.1f}, {cx:.1f} {yb:.1f} "
        f"C {cx - w * 0.52:.1f} {yb - ln * 0.28:.1f}, {cx - w * 0.58:.1f} {yt + ln * 0.22:.1f}, {cx:.1f} {yt:.1f} Z"
    )


def leaf_group(
    angle: float,
    rb: float,
    ln: float,
    w: float,
    grad_id: str,
    p: dict[str, str],
    tip: str,
    rng: random.Random,
    frilly: bool = False,
    rib_color: str | None = None,
    rib_width: float = 0.55,
) -> str:
    a = angle + rng.uniform(-3.5, 3.5)
    ln = ln * rng.uniform(0.9, 1.12)
    w = w * rng.uniform(0.92, 1.08)
    rb = rb + rng.uniform(-1.0, 1.0)
    yb = 50 - rb
    yt = yb - ln
    # small leaves: smooth occlusion underlay + no veins — visually identical
    # at canvas scale, roughly halves the bytes of dense frilly domes
    big_leaf = ln >= 12
    parts = [
        f'<path d="{leaf_d(yt - 1.4, yb + 0.8, w * 1.3, frilly=frilly and big_leaf)}" '
        f'fill="{p["occ"]}" opacity="0.9"/>',
        f'<path d="{leaf_d(yt, yb, w, frilly=frilly)}" fill="url(#{grad_id})"/>',
    ]
    if w >= 4.5:
        parts.append(
            f'<path d="{leaf_d(yt + ln * 0.10, yb - ln * 0.38, w * 0.5, cx=50 - w * 0.18)}" '
            f'fill="{lighten(tip, 0.18)}" opacity="0.5"/>'
        )
        parts.append(
            f'<line x1="50" y1="{yb - ln * 0.08:.1f}" x2="50" y2="{yt + ln * 0.18:.1f}" '
            f'stroke="{rib_color or p["rib"]}" stroke-width="{rib_width}" '
            f'opacity="{0.9 if rib_color else 0.5}"/>'
        )
    if frilly and w >= 8 and big_leaf:
        for frac in (0.35, 0.6):
            ym = yb - ln * frac
            for sgn in (1, -1):
                parts.append(
                    f'<line x1="50" y1="{ym:.1f}" x2="{50 + sgn * w * 0.42:.1f}" '
                    f'y2="{ym - ln * 0.14:.1f}" stroke="{rib_color or p["rib"]}" '
                    f'stroke-width="0.4" opacity="0.4"/>'
                )
    return f'<g transform="rotate({a:.1f} 50 50)">' + "".join(parts) + "</g>"


def ring_defs(key: str, idx: int, tip: str, base: str) -> str:
    return (
        f'<linearGradient id="{key}_r{idx}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{tip}"/>'
        f'<stop offset="48%" stop-color="{mix(tip, base, 0.45)}"/>'
        f'<stop offset="100%" stop-color="{base}"/>'
        f"</linearGradient>"
    )


def shadow_def(key: str, dark: str = "#12300d") -> str:
    return (
        f'<radialGradient id="{key}_shadow" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{dark}" stop-opacity="0.28"/>'
        f'<stop offset="62%" stop-color="{dark}" stop-opacity="0.25"/>'
        f'<stop offset="100%" stop-color="{dark}" stop-opacity="0"/>'
        f"</radialGradient>"
    )


def base_cloud(ring_r: float, circ_r: float, dark: str, mid: str, n: int = 9) -> str:
    parts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        parts.append(
            f'<circle cx="{50 + ring_r * math.cos(a):.1f}" '
            f'cy="{50 + ring_r * math.sin(a):.1f}" r="{circ_r:.1f}" fill="{dark}"/>'
        )
    parts.append(f'<circle cx="50" cy="50" r="{ring_r + 2:.1f}" fill="{mid}"/>')
    return "".join(parts)


def leaf_rings(
    key: str,
    p: dict[str, str],
    rng: random.Random,
    r_out: float = 42.0,
    leaf_len: float = 17.0,
    leaf_w: float = 11.5,
    n_out: int = 18,
    n_rings: int | None = None,
    frilly: bool = False,
    rib_color: str | None = None,
    rib_width: float = 0.55,
) -> tuple[list[str], list[str]]:
    """Shingled leaf rings outside-in. Returns (defs, body)."""
    defs, body = [], []
    rb = r_out - leaf_len
    ln, w, n = leaf_len, leaf_w, float(n_out)
    ring_list = []
    while len(ring_list) < 10:
        ring_list.append((max(rb, 0.0), ln, w, max(int(n), 5)))
        rb -= max(ln * 0.52, r_out * 0.12)
        ln = max(ln * 0.86, leaf_len * 0.55)
        w = max(w * 0.9, leaf_w * 0.6)
        n *= 0.78
        if n_rings is not None and len(ring_list) >= n_rings:
            break
        if rb <= 0.5:
            ring_list.append((0.0, ln * 0.8, w * 0.8, max(int(n * 0.8), 4)))
            break
    k = max(len(ring_list) - 1, 1)
    for i, (rb_i, ln_i, w_i, n_i) in enumerate(ring_list):
        t = i / k
        tip = mix(p["t0"], p["t1"], t)
        base = mix(p["b0"], p["b1"], t)
        defs.append(ring_defs(key, i, tip, base))
        phase = rng.uniform(0, 360)
        for j in range(n_i):
            body.append(
                leaf_group(
                    phase + 360.0 * j / n_i, rb_i, ln_i, w_i,
                    f"{key}_r{i}", p, tip, rng, frilly, rib_color, rib_width,
                )
            )
    return defs, body


def dome_leaf_rings(
    key: str,
    p: dict[str, str],
    rng: random.Random,
    r_out: float,
    leaf_len: float,
    leaf_w: float,
    tang_gap: float = 0.78,
    frilly: bool = False,
    rib_color: str | None = None,
    rib_width: float = 0.55,
    floor: float = 0.38,
) -> tuple[list[str], list[str]]:
    """Foreshortened shingled rings — the canopy reads as a sphere from above.

    A hemisphere viewed orthographically from the top compresses surface
    detail radially by cos(theta) = sqrt(1 - (rho/R)^2): leaves are LARGEST
    at the crown, get radially squat toward the rim, and the ring leaf count
    grows with the circumference (tangential spacing stays constant), so
    overlap visibly densifies at the silhouette (#282 manual-test feedback —
    the previous outward-growing leaves read as a flat plate).
    """
    defs, body = [], []
    big_r = r_out + 1.0
    # fixed dome latitudes (fractions of r_out) keep ring count — and thus the
    # element budget — bounded regardless of leaf size
    fracs = [1.0, 0.93, 0.84, 0.72, 0.57, 0.40]
    rings = []
    for i, frac in enumerate(fracs):
        rho = r_out * frac
        step = (rho - r_out * fracs[i + 1]) if i + 1 < len(fracs) else rho * 0.45
        mid_guess = rho - leaf_len * 0.4
        f = max(math.sqrt(max(1.0 - (mid_guess / big_r) ** 2, 0.0)), floor)
        ln = max(leaf_len * f, step * 1.45)  # guarantee radial shingle overlap
        rb = max(rho - ln, 0.0)
        mid = rho - ln / 2
        w = leaf_w * (0.82 + 0.18 * f)
        circ = 2 * math.pi * max(mid, 6.0)
        n = int(circ / (w * tang_gap))
        if n > 32:  # cap the count; widen leaves (≤1.5x) to close the ring
            w = min(circ / (32 * tang_gap), leaf_w * 1.5)
            n = min(int(circ / (w * tang_gap)), 32)
        rings.append((rb, ln, w, max(n, 6)))
    total = sum(n for _, _, _, n in rings)
    if total > 110:  # element/byte budget: scale counts down proportionally
        rings = [(rb, ln, w, max(int(n * 110 / total), 5)) for rb, ln, w, n in rings]
    rings.append((0.0, leaf_len * 0.75, leaf_w * 0.8, 5))
    k = max(len(rings) - 1, 1)
    for i, (rb_i, ln_i, w_i, n_i) in enumerate(rings):
        t = i / k
        tip = mix(p["t0"], p["t1"], t)
        base = mix(p["b0"], p["b1"], t)
        defs.append(ring_defs(key, i, tip, base))
        phase = rng.uniform(0, 360)
        for j in range(n_i):
            body.append(
                leaf_group(
                    phase + 360.0 * j / n_i, rb_i, ln_i, w_i,
                    f"{key}_r{i}", p, tip, rng, frilly, rib_color, rib_width,
                )
            )
    return defs, body


def annulus_points(
    rng: random.Random, n: int, r0: float, r1: float, min_dist: float = 7.0
) -> list[tuple[float, float]]:
    """Best-effort dart-throwing: returns UP TO n points (deterministically
    fewer when min_dist packing fails within 400 attempts) — feature counts
    in recipes are requests, not guarantees."""
    pts: list[tuple[float, float]] = []
    for _ in range(400):
        if len(pts) >= n:
            break
        r = rng.uniform(r0, r1)
        a = rng.uniform(0, 2 * math.pi)
        x, y = 50 + r * math.cos(a), 50 + r * math.sin(a)
        if all((x - q[0]) ** 2 + (y - q[1]) ** 2 >= min_dist**2 for q in pts):
            pts.append((x, y))
    return pts


def fruit_defs(key: str, triad: tuple[str, str, str]) -> str:
    hi, mid_c, dark = triad
    return (
        f'<radialGradient id="{key}_fruit" cx="38%" cy="35%" r="65%">'
        f'<stop offset="0%" stop-color="{hi}"/>'
        f'<stop offset="48%" stop-color="{mid_c}"/>'
        f'<stop offset="100%" stop-color="{dark}"/>'
        f"</radialGradient>"
    )


def fruit_svg(x: float, y: float, r: float, key: str, occ: str = "#3f0e04") -> str:
    dx, dy = x - 50, y - 50
    dist = max(math.hypot(dx, dy), 0.001)
    ux, uy = dx / dist, dy / dist
    return (
        f'<circle cx="{x + ux * 0.9:.1f}" cy="{y + uy * 0.9:.1f}" r="{r * 1.26:.1f}" '
        f'fill="{occ}" opacity="0.5"/>'
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="url(#{key}_fruit)"/>'
        f'<circle cx="{x - r * 0.35:.1f}" cy="{y - r * 0.35:.1f}" r="{r * 0.28:.1f}" '
        f'fill="#ffffff" opacity="0.85"/>'
    )


def fruit_clusters(
    key: str, rng: random.Random, n_clusters: int, r_fruit: tuple[float, float],
    r_zone: tuple[float, float] = (14.0, 23.0), per_cluster: tuple[int, int] = (2, 3),
    occ: str = "#3f0e04",
) -> list[str]:
    body = []
    for i in range(n_clusters):
        ca = 360.0 * i / n_clusters + rng.uniform(-14, 14)
        cr = rng.uniform(*r_zone)
        a = ca * math.pi / 180
        cxx, cyy = 50 + cr * math.cos(a), 50 + cr * math.sin(a)
        for _ in range(rng.randint(*per_cluster)):
            r = rng.uniform(*r_fruit)
            body.append(
                fruit_svg(cxx + rng.uniform(-3.8, 3.8), cyy + rng.uniform(-3.8, 3.8), r, key, occ)
            )
    return body


def berry_scatter(
    key: str, rng: random.Random, n: int, r_fruit: tuple[float, float],
    r_zone: tuple[float, float] = (8.0, 30.0), occ: str = "#1a0a20",
) -> list[str]:
    return [
        fruit_svg(x, y, rng.uniform(*r_fruit), key, occ)
        for x, y in annulus_points(rng, n, r_zone[0], r_zone[1], min_dist=6.5)
    ]


def flower_head(
    x: float, y: float, radius: float, petals: int, spec: tuple[str, str, str],
    rng: random.Random, double: bool = False, occ: str = "#1c3d14",
) -> str:
    p_out, p_tip, center = spec
    rot0 = rng.uniform(0, 360)
    parts = [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius * 1.08:.1f}" fill="{occ}" opacity="0.4"/>']
    rings = [(radius, petals, p_out, rot0)]
    if double:
        rings.append((radius * 0.62, petals, mix(p_out, p_tip, 0.45), rot0 + 180.0 / petals))
    for rr, np_, col, base_rot in rings:
        for i in range(np_):
            a = base_rot + 360.0 * i / np_
            parts.append(
                f'<g transform="rotate({a:.1f} {x:.1f} {y:.1f})">'
                f'<ellipse cx="{x:.1f}" cy="{y - rr * 0.55:.1f}" rx="{rr * 0.30:.1f}" '
                f'ry="{rr * 0.52:.1f}" fill="{col}"/>'
                f'<ellipse cx="{x:.1f}" cy="{y - rr * 0.68:.1f}" rx="{rr * 0.16:.1f}" '
                f'ry="{rr * 0.30:.1f}" fill="{p_tip}" opacity="0.85"/>'
                f"</g>"
            )
    parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius * 0.28:.1f}" fill="{center}"/>')
    parts.append(
        f'<circle cx="{x - radius * 0.08:.1f}" cy="{y - radius * 0.08:.1f}" '
        f'r="{radius * 0.12:.1f}" fill="{lighten(center, 0.2)}"/>'
    )
    return "".join(parts)


def flower_scatter(
    rng: random.Random, n: int, radius: float, petals: int, spec: tuple[str, str, str],
    r_zone: tuple[float, float] = (8.0, 28.0), double: bool = False, occ: str = "#1c3d14",
) -> list[str]:
    return [
        flower_head(x, y, radius * rng.uniform(0.85, 1.15), petals, spec, rng, double, occ)
        for x, y in annulus_points(rng, n, r_zone[0], r_zone[1], min_dist=radius * 1.7)
    ]


def bloom_puffs(
    rng: random.Random, n_puffs: int, dark: str, light: str,
    r_start_range: tuple[float, float] = (19.0, 21.5), occ: str = "#2e1f5e",
) -> list[str]:
    """Radial plump bloom chains (the approved lavender design)."""
    body = []
    for i in range(n_puffs):
        a = 360.0 * i / n_puffs + rng.uniform(-8, 8)
        r_start = rng.uniform(*r_start_range)
        radii = [3.4, 3.0, 2.6, 2.0]
        if rng.random() < 0.4:
            radii = radii[:3]
        parts = []
        for b, r in enumerate(radii):
            y = 50 - (r_start + b * 2.6)
            col = mix(dark, light, b / max(len(radii) - 1, 1))
            parts.append(f'<circle cx="50" cy="{y + 0.8:.1f}" r="{r * 1.15:.1f}" fill="{occ}" opacity="0.5"/>')
            parts.append(f'<circle cx="50" cy="{y:.1f}" r="{r:.1f}" fill="{col}"/>')
            parts.append(
                f'<circle cx="{50 - r * 0.32:.1f}" cy="{y - r * 0.35:.1f}" r="{r * 0.42:.1f}" '
                f'fill="{lighten(col, 0.18)}" opacity="0.8"/>'
            )
        tip_y = 50 - (r_start + (len(radii) - 1) * 2.6 + 2.4)
        parts.append(f'<circle cx="50" cy="{tip_y:.1f}" r="1.4" fill="{lighten(light, 0.1)}"/>')
        body.append(f'<g transform="rotate({a:.1f} 50 50)">' + "".join(parts) + "</g>")
    return body


def cluster_puff(
    x: float, y: float, radius: float, dark: str, light: str, rng: random.Random,
    occ: str = "#2e1f5e", n_dots: int = 7,
) -> str:
    """Round bloom cluster at a point (lilac / hydrangea / viburnum style)."""
    parts = [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius * 1.12:.1f}" fill="{occ}" opacity="0.5"/>']
    parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{dark}"/>')
    for i in range(n_dots):
        a = 2 * math.pi * i / n_dots + rng.uniform(-0.3, 0.3)
        rr = radius * rng.uniform(0.45, 0.62)
        dx, dy = rr * math.cos(a), rr * math.sin(a)
        dot_r = radius * rng.uniform(0.34, 0.44)
        col = mix(dark, light, rng.uniform(0.35, 0.8))
        parts.append(f'<circle cx="{x + dx:.1f}" cy="{y + dy:.1f}" r="{dot_r:.1f}" fill="{col}"/>')
    parts.append(
        f'<circle cx="{x - radius * 0.25:.1f}" cy="{y - radius * 0.28:.1f}" '
        f'r="{radius * 0.38:.1f}" fill="{light}" opacity="0.85"/>'
    )
    return "".join(parts)


def umbel(x: float, y: float, radius: float, col: str, light: str, rng: random.Random) -> str:
    parts = [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius * 1.1:.1f}" fill="#1c3d14" opacity="0.35"/>']
    for _ in range(10):
        a = rng.uniform(0, 2 * math.pi)
        rr = radius * math.sqrt(rng.uniform(0, 1)) * 0.85
        parts.append(
            f'<circle cx="{x + rr * math.cos(a):.1f}" cy="{y + rr * math.sin(a):.1f}" '
            f'r="{radius * 0.22:.1f}" fill="{col}"/>'
        )
    parts.append(f'<circle cx="{x - radius * 0.2:.1f}" cy="{y - radius * 0.2:.1f}" r="{radius * 0.3:.1f}" fill="{light}" opacity="0.7"/>')
    return "".join(parts)


def pod_scatter(
    rng: random.Random, n: int, dark: str, light: str,
    r_zone: tuple[float, float] = (12.0, 28.0), length: float = 8.5,
) -> list[str]:
    body = []
    for x, y in annulus_points(rng, n, r_zone[0], r_zone[1], min_dist=8.0):
        a = math.degrees(math.atan2(y - 50, x - 50)) + 90 + rng.uniform(-25, 25)
        half = length / 2
        body.append(
            f'<g transform="rotate({a:.1f} {x:.1f} {y:.1f})">'
            f'<line x1="{x:.1f}" y1="{y - half:.1f}" x2="{x:.1f}" y2="{y + half:.1f}" '
            f'stroke="#153a0a" stroke-width="5" stroke-linecap="round"/>'
            f'<line x1="{x:.1f}" y1="{y - half + 0.4:.1f}" x2="{x:.1f}" y2="{y + half - 0.4:.1f}" '
            f'stroke="{dark}" stroke-width="3.4" stroke-linecap="round"/>'
            f'<line x1="{x:.1f}" y1="{y - half + 1:.1f}" x2="{x:.1f}" y2="{y + half - 1.4:.1f}" '
            f'stroke="{lighten(light, 0.12)}" stroke-width="1.9" stroke-linecap="round"/>'
            f"</g>"
        )
    return body


def bulb_center(
    key: str, radius: float, triad: tuple[str, str, str],
) -> tuple[list[str], list[str]]:
    defs = [
        f'<radialGradient id="{key}_bulb" cx="40%" cy="38%" r="62%">'
        f'<stop offset="0%" stop-color="{triad[0]}"/>'
        f'<stop offset="55%" stop-color="{triad[1]}"/>'
        f'<stop offset="100%" stop-color="{triad[2]}"/>'
        f"</radialGradient>"
    ]
    body = [
        f'<circle cx="50" cy="50" r="{radius * 1.18:.1f}" fill="#3a2412" opacity="0.5"/>',
        f'<circle cx="50" cy="50" r="{radius:.1f}" fill="url(#{key}_bulb)"/>',
        f'<circle cx="{50 - radius * 0.3:.1f}" cy="{50 - radius * 0.3:.1f}" '
        f'r="{radius * 0.28:.1f}" fill="#ffffff" opacity="0.55"/>',
    ]
    return defs, body


def tendrils(rng: random.Random, n: int, col: str, r_start: float = 30.0) -> list[str]:
    body = []
    for i in range(n):
        a = 360.0 * i / n + rng.uniform(-15, 15)
        curl = rng.choice([-1, 1])
        body.append(
            f'<g transform="rotate({a:.1f} 50 50)">'
            f'<path d="M 50 {50 - r_start:.1f} q {4 * curl} -5 {2 * curl} -9 q {-2 * curl} -4 {-5 * curl} -3" '
            f'fill="none" stroke="{col}" stroke-width="1.1" stroke-linecap="round"/>'
            f"</g>"
        )
    return body
# --------------------------------------------------------------------------- #
# archetype builders
# --------------------------------------------------------------------------- #
def _heart(p: dict[str, str], radius: float = 13.5) -> list[str]:
    inner = mix(p["t1"], "#ffffff", 0.25)
    body = [
        f'<circle cx="50" cy="50" r="{radius * 1.08:.1f}" fill="{p["occ"]}" opacity="0.5"/>',
        f'<circle cx="50" cy="50" r="{radius:.1f}" fill="{mix(p["t0"], p["t1"], 0.5)}"/>',
    ]
    for i in range(6):
        a = 2 * math.pi * i / 6
        body.append(
            f'<circle cx="{50 + radius * 0.63 * math.cos(a):.1f}" '
            f'cy="{50 + radius * 0.63 * math.sin(a):.1f}" r="{radius * 0.37:.1f}" '
            f'fill="{mix(p["t1"], inner, 0.4)}"/>'
        )
    body.append(f'<circle cx="50" cy="50" r="{radius * 0.4:.1f}" fill="{inner}"/>')
    body.append(f'<circle cx="50" cy="50" r="{radius * 0.16:.1f}" fill="{lighten(inner, 0.15)}"/>')
    return body


def _blades(
    key: str, p: dict[str, str], rng: random.Random, r_out: float,
    n0: int = 26, w: float = 2.2, layers: int = 3,
) -> tuple[list[str], list[str]]:
    defs, body = [], []
    for i in range(layers):
        t = i / max(layers - 1, 1)
        tip, base = mix(p["t0"], p["t1"], t), mix(p["b0"], p["b1"], t)
        defs.append(ring_defs(key, i, tip, base))
        n = max(int(n0 * (0.78**i)), 6)
        ln = (r_out - 3 - i * 5.0) * 0.96
        phase = rng.uniform(0, 360)
        for j in range(n):
            body.append(
                leaf_group(phase + 360.0 * j / n, 2.5 + i * 1.5, ln, w, f"{key}_r{i}", p, tip, rng)
            )
    return defs, body


def _palm_fronds(p: dict[str, str], rng: random.Random, r_out: float, n_fronds: int = 10) -> list[str]:
    body = []
    for i in range(n_fronds):
        a = 360.0 * i / n_fronds + rng.uniform(-6, 6)
        parts = [
            f'<line x1="50" y1="46" x2="50" y2="{50 - r_out:.1f}" '
            f'stroke="{p["rib"]}" stroke-width="1.6"/>'
        ]
        steps = 8
        for s in range(steps):
            t = s / (steps - 1)
            y = 50 - (8 + t * (r_out - 11))
            ll = 13.0 * (1 - 0.45 * t) * rng.uniform(0.9, 1.1)
            col = mix(mix(p["b0"], p["t0"], 0.5), p["t1"], t)
            for sgn in (1, -1):
                parts.append(
                    f'<g transform="rotate({sgn * 55} 50 {y:.1f})">'
                    f'<path d="{leaf_d(y - ll - 1, y + 1.6, 4.1, cx=50)}" fill="{p["occ"]}" opacity="0.7"/>'
                    f'<path d="{leaf_d(y - ll, y + 1.2, 3.2, cx=50)}" fill="{col}"/>'
                    f"</g>"
                )
        body.append(f'<g transform="rotate({a:.1f} 50 50)">' + "".join(parts) + "</g>")
    return body


def _veg_head(p: dict[str, str], rng: random.Random, head: tuple[str, str, str], r_head: float) -> list[str]:
    lo, mid_c, hi = head
    body = [f'<circle cx="50" cy="50" r="{r_head * 1.12:.1f}" fill="{p["occ"]}" opacity="0.85"/>']
    body.append(f'<circle cx="50" cy="50" r="{r_head:.1f}" fill="{lo}"/>')
    for _ in range(16):
        a = rng.uniform(0, 2 * math.pi)
        rr = r_head * math.sqrt(rng.uniform(0, 1)) * 0.82
        x, y = 50 + rr * math.cos(a), 50 + rr * math.sin(a)
        r = r_head * rng.uniform(0.18, 0.3)
        body.append(f'<circle cx="{x:.1f}" cy="{y + 0.6:.1f}" r="{r:.1f}" fill="{lo}" opacity="0.9"/>')
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{mix(mid_c, hi, rng.uniform(0, 0.7))}"/>')
    body.append(
        f'<circle cx="{50 - r_head * 0.28:.1f}" cy="{50 - r_head * 0.28:.1f}" '
        f'r="{r_head * 0.3:.1f}" fill="{hi}" opacity="0.5"/>'
    )
    return body


# every key a recipe may use — build_sprite refuses unknown keys so a typo
# (n_our=18) fails loudly instead of silently shipping a wrong sprite
_KNOWN_KEYS = frozenset({
    "a", "pal", "r", "n_out", "leaf_scale", "frilly", "narrow", "rib_color",
    "rib_width", "heart", "head", "head_scale", "shadow_col", "fruit",
    "fruit2", "flowers", "puffs", "clusters", "umbels", "pods", "bulb",
})


def build_sprite(name: str, cfg: dict) -> str:
    unknown = set(cfg) - _KNOWN_KEYS
    if unknown:
        raise ValueError(f"{name}: unknown recipe keys {sorted(unknown)}")
    rng = random.Random(f"ogp-sprite-{name}")
    key = "".join(w[0] for w in name.split("_"))[:3] + str(len(name))
    arch = cfg["a"]
    p = dict(PALETTES[cfg.get("pal", "fresh")])
    r = cfg.get("r", {"canopy": 44, "mound": 38, "rosette": 38, "grass": 40, "feathery": 38,
                      "conifer": 44, "palm": 44, "allium": 38, "head": 38, "ground": 40,
                      "flower": 44, "climber": 36}.get(arch, 40))
    defs: list[str] = [shadow_def(key, cfg.get("shadow_col", "#12300d"))]
    body: list[str] = [f'<circle cx="50" cy="50" r="{min(r + 3, 46):.1f}" fill="url(#{key}_shadow)"/>']

    frilly = cfg.get("frilly", False)
    rib_color = cfg.get("rib_color")
    rib_width = cfg.get("rib_width", 0.55)
    scale = cfg.get("leaf_scale", 1.0)

    if arch == "canopy":
        body.append(base_cloud(r * 0.61, r * 0.37, p["b0"], mix(p["b0"], p["b1"], 0.5)))
        gap = min(max(0.78 * 18 / cfg.get("n_out", 18), 0.55), 1.15)
        d, b = dome_leaf_rings(key, p, rng, r_out=r - 1, leaf_len=r * 0.42 * scale,
                               leaf_w=r * 0.28 * scale, tang_gap=gap,
                               frilly=frilly, rib_color=rib_color, rib_width=rib_width)
        defs += d
        body += b
    elif arch == "mound":
        body.append(base_cloud(r * 0.58, r * 0.35, p["b0"], mix(p["b0"], p["b1"], 0.5)))
        if cfg.get("narrow"):
            # narrow-leaf cushions (lavender/rosemary/tarragon) are tufts, not
            # spheres — keep the flat shingle look that was signed off
            d, b = leaf_rings(key, p, rng, r_out=r - 1, leaf_len=r * 0.34 * scale,
                              leaf_w=r * 0.13 * scale, n_out=cfg.get("n_out", 26),
                              frilly=frilly, rib_color=rib_color, rib_width=rib_width)
        else:
            gap = min(max(0.78 * 16 / cfg.get("n_out", 16), 0.55), 1.15)
            d, b = dome_leaf_rings(key, p, rng, r_out=r - 1, leaf_len=r * 0.38 * scale,
                                   leaf_w=r * 0.26 * scale, tang_gap=gap,
                                   frilly=frilly, rib_color=rib_color, rib_width=rib_width)
        defs += d
        body += b
    elif arch == "rosette":
        d, b = leaf_rings(key, p, rng, r_out=r - 1, leaf_len=r * 0.5 * scale,
                          leaf_w=r * 0.3 * scale, n_out=cfg.get("n_out", 10),
                          frilly=True, rib_color=rib_color, rib_width=rib_width)
        defs += d
        body += b
        if cfg.get("heart", True):
            body += _heart(p, radius=r * 0.36)
    elif arch in ("grass", "feathery", "allium"):
        n0 = {"grass": 30, "feathery": 34, "allium": 18}[arch]
        w = {"grass": 2.2, "feathery": 1.7, "allium": 3.2}[arch]
        d, b = _blades(key, p, rng, r, n0=cfg.get("n_out", n0), w=w * scale)
        defs += d
        body += b
    elif arch == "conifer":
        body.append(base_cloud(r * 0.42, r * 0.3, p["b0"], mix(p["b0"], p["b1"], 0.4), n=8))
        d, b = leaf_rings(key, p, rng, r_out=r - 1, leaf_len=r * 0.62, leaf_w=4.4,
                          n_out=13, n_rings=3)
        defs += d
        body += b
    elif arch == "palm":
        body.append(f'<circle cx="50" cy="50" r="9" fill="{p["b0"]}"/>')
        body += _palm_fronds(p, rng, r - 2, n_fronds=cfg.get("n_out", 9))
        body.append(f'<circle cx="50" cy="50" r="4.5" fill="{mix(p["b1"], p["t0"], 0.5)}"/>')
        body.append(f'<circle cx="50" cy="50" r="2" fill="{p["t1"]}"/>')
    elif arch == "head":
        d, b = leaf_rings(key, p, rng, r_out=r - 1, leaf_len=r * 0.46, leaf_w=r * 0.3,
                          n_out=11, n_rings=2, frilly=frilly)
        defs += d
        body += b
        body += _veg_head(p, rng, cfg["head"], r * cfg.get("head_scale", 0.42))
    elif arch == "climber":
        body.append(base_cloud(r * 0.56, r * 0.34, p["b0"], mix(p["b0"], p["b1"], 0.5)))
        d, b = dome_leaf_rings(key, p, rng, r_out=r - 1, leaf_len=r * 0.4 * scale,
                               leaf_w=r * 0.27 * scale, tang_gap=0.85, frilly=frilly)
        defs += d
        body += b
        body += tendrils(rng, 7, mix(p["b1"], p["t0"], 0.5), r_start=r - 5)
    elif arch == "ground":
        body.append(base_cloud(r * 0.6, r * 0.34, p["b0"], mix(p["b0"], p["b1"], 0.6), n=11))
        defs.append(ring_defs(key, 0, mix(p["t0"], p["t1"], 0.35), mix(p["b0"], p["b1"], 0.4)))
        defs.append(ring_defs(key, 1, mix(p["t0"], p["t1"], 0.75), mix(p["b0"], p["b1"], 0.8)))
        tip_mid = mix(p["t0"], p["t1"], 0.6)
        for idx, (x, y) in enumerate(annulus_points(rng, 30, 2, r - 9, min_dist=5.5)):
            a = rng.uniform(0, 360)
            ll, ww = 11.0 * rng.uniform(0.85, 1.15), 6.5 * rng.uniform(0.9, 1.1)
            body.append(
                f'<g transform="rotate({a:.1f} {x:.1f} {y:.1f})">'
                f'<path d="{leaf_d(y - ll, y, ww * 1.25, cx=x)}" fill="{p["occ"]}" opacity="0.85"/>'
                f'<path d="{leaf_d(y - ll + 1, y - 0.5, ww, cx=x)}" fill="url(#{key}_r{idx % 2})"/>'
                f'<path d="{leaf_d(y - ll + 2, y - ll * 0.45, ww * 0.5, cx=x - ww * 0.15)}" '
                f'fill="{lighten(tip_mid, 0.18)}" opacity="0.5"/>'
                f"</g>"
            )
    elif arch == "flower":
        # one dominant flower head (sunflower archetype) over a leaf ring
        d, b = leaf_rings(key, p, rng, r_out=r - 1, leaf_len=r * 0.42, leaf_w=r * 0.26,
                          n_out=11, n_rings=2)
        defs += d
        body += b
        fl = cfg["flowers"]
        body.append(
            flower_head(50, 50, r * 0.62, fl.get("petals", 14), FLOWERS[fl["spec"]], rng,
                        double=fl.get("double", True), occ=p["occ"])
        )
    else:
        raise ValueError(f"unknown archetype {arch!r} for {name}")

    # ---- features on top of the foliage ----
    if "pods" in cfg:
        pd = cfg["pods"]
        body += pod_scatter(rng, pd.get("n", 9), pd.get("dark", "#2f6b1d"),
                            pd.get("light", "#7cc551"), r_zone=pd.get("zone", (12, r - 10)),
                            length=pd.get("length", 8.0))
    if "fruit" in cfg:
        fr = cfg["fruit"]
        triad = FRUITS[fr["kind"]]
        defs.append(fruit_defs(key, triad))
        if fr.get("scatter"):
            body += berry_scatter(key, rng, fr.get("n", 12), fr.get("size", (1.7, 2.4)),
                                  r_zone=fr.get("zone", (8, r - 10)), occ=fr.get("occ", "#1a0a20"))
        else:
            body += fruit_clusters(key, rng, fr.get("n", 4), fr.get("size", (3.2, 4.1)),
                                   r_zone=fr.get("zone", (14, min(23, r - 14))),
                                   per_cluster=fr.get("per", (2, 3)), occ=fr.get("occ", "#3f0e04"))
    if "fruit2" in cfg:  # secondary fruit (e.g. unripe green tomatoes)
        fr = cfg["fruit2"]
        key2 = key + "b"
        defs.append(fruit_defs(key2, FRUITS[fr["kind"]]))
        body += berry_scatter(key2, rng, fr.get("n", 4), fr.get("size", (2.0, 2.6)),
                              r_zone=fr.get("zone", (10, r - 12)), occ=fr.get("occ", "#14300a"))
    if "flowers" in cfg and arch != "flower":
        fl = cfg["flowers"]
        body += flower_scatter(rng, fl.get("n", 6), fl.get("radius", 6.0),
                               fl.get("petals", 5), FLOWERS[fl["spec"]],
                               r_zone=fl.get("zone", (8, r - 10)),
                               double=fl.get("double", False), occ=p["occ"])
    if "puffs" in cfg:
        pf = cfg["puffs"]
        body += bloom_puffs(rng, pf.get("n", 9), pf["dark"], pf["light"],
                            r_start_range=pf.get("start", (19.0, 21.5)),
                            occ=pf.get("occ", "#2e1f5e"))
    if "clusters" in cfg:
        cl = cfg["clusters"]
        for x, y in annulus_points(rng, cl.get("n", 7), *cl.get("zone", (10, r - 12)),
                                   min_dist=cl.get("radius", 7.0) * 1.8):
            body.append(cluster_puff(x, y, cl.get("radius", 7.0) * rng.uniform(0.85, 1.15),
                                     cl["dark"], cl["light"], rng,
                                     occ=cl.get("occ", "#2e1f5e")))
    if "umbels" in cfg:
        um = cfg["umbels"]
        for x, y in annulus_points(rng, um.get("n", 5), *um.get("zone", (8, r - 14)), min_dist=11):
            body.append(umbel(x, y, um.get("radius", 5.5), um["col"], um["light"], rng))
    if "bulb" in cfg:
        bu = cfg["bulb"]
        d, b = bulb_center(key, bu.get("radius", 7.0), bu["triad"])
        defs += d
        body += b

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">\n'
        f"<!-- {name} — generated by scripts/generate_plant_sprites.py (do not hand-edit) -->\n"
        "<defs>" + "".join(defs) + "</defs>\n" + "\n".join(body) + "\n</svg>\n"
    )


def build_hedge(name: str) -> str:
    """hedge_section keeps its legacy rectangular viewBox (10 25 80 50).

    NOTE: this branch bypasses build_sprite and therefore the _KNOWN_KEYS
    guard — fine while the hedge recipe has exactly one key ("a"), but any
    future rect-viewBox archetype with real parameters must add its own
    key validation (or route through build_sprite).
    """
    rng = random.Random(f"ogp-sprite-{name}")
    p = PALETTES["dark"]
    defs = [
        ring_defs("hg", 0, mix(p["t0"], p["t1"], 0.3), mix(p["b0"], p["b1"], 0.35)),
        ring_defs("hg", 1, mix(p["t0"], p["t1"], 0.65), mix(p["b0"], p["b1"], 0.7)),
    ]
    tip_mid = mix(p["t0"], p["t1"], 0.5)
    body = [
        f'<rect x="12" y="27" width="76" height="46" rx="8" ry="8" fill="{p["occ"]}"/>',
        f'<rect x="13.5" y="28.5" width="73" height="43" rx="7" ry="7" '
        f'fill="{mix(p["b0"], p["b1"], 0.4)}"/>',
    ]
    for gx in range(13):
        for gy in range(7):
            x = 15 + gx * 5.7 + rng.uniform(-1.3, 1.3) + (2.9 if gy % 2 else 0)
            y = 30.5 + gy * 6.6 + rng.uniform(-1.1, 1.1)
            if not (14.5 < x < 85.5 and 28.5 < y < 71.5):
                continue
            a = rng.uniform(0, 360)
            ll, ww = 8.5 * rng.uniform(0.85, 1.15), 5.0 * rng.uniform(0.9, 1.1)
            body.append(
                f'<g transform="rotate({a:.1f} {x:.1f} {y:.1f})">'
                f'<path d="{leaf_d(y - ll, y, ww * 1.25, cx=x)}" fill="{p["occ"]}" opacity="0.85"/>'
                f'<path d="{leaf_d(y - ll + 1, y - 0.5, ww, cx=x)}" fill="url(#hg_r{(gx + gy) % 2})"/>'
                f'<path d="{leaf_d(y - ll + 1.8, y - ll * 0.45, ww * 0.5, cx=x - ww * 0.15)}" '
                f'fill="{lighten(tip_mid, 0.18)}" opacity="0.5"/>'
                f"</g>"
            )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 25 80 50">\n'
        f"<!-- {name} — generated by scripts/generate_plant_sprites.py (do not hand-edit) -->\n"
        "<defs>" + "".join(defs) + "</defs>\n" + "\n".join(body) + "\n</svg>\n"
    )
# --------------------------------------------------------------------------- #
# species table — one compact recipe per species (108)
# --------------------------------------------------------------------------- #
SPECIES: dict[str, dict] = {
    # trees
    "apple_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="apple", n=4)),
    "pear_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="pear", n=4)),
    "plum_tree": dict(a="canopy", pal="dark", fruit=dict(kind="plum", n=4, size=(2.8, 3.5))),
    "peach_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="peach", n=4)),
    "cherry_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="cherry", n=5, size=(2.2, 2.8))),
    "fig_tree": dict(a="canopy", pal="dark", leaf_scale=1.25, n_out=12, frilly=True,
                     fruit=dict(kind="fig", n=3, size=(3.0, 3.8), per=(1, 2))),
    "olive_tree": dict(a="canopy", pal="silver", leaf_scale=0.8, n_out=22,
                       fruit=dict(kind="olive", scatter=True, n=8, size=(1.6, 2.1))),
    "lemon_tree": dict(a="canopy", pal="dark", fruit=dict(kind="lemon", n=4, size=(3.0, 3.8))),
    "orange_tree": dict(a="canopy", pal="dark", fruit=dict(kind="orange", n=4, size=(3.2, 4.0))),
    "walnut_tree": dict(a="canopy", pal="fresh", leaf_scale=1.1,
                        fruit=dict(kind="nut", scatter=True, n=6, size=(2.2, 2.8), occ="#2a3311")),
    "oak": dict(a="canopy", pal="dark", frilly=True, leaf_scale=1.15, n_out=14),
    "maple": dict(a="canopy", pal="autumn", leaf_scale=1.1, n_out=15, frilly=True),
    "birch": dict(a="canopy", pal="yellow", leaf_scale=0.75, n_out=20),
    "willow": dict(a="canopy", pal="silver", leaf_scale=0.9, n_out=24),
    "magnolia": dict(a="canopy", pal="fresh", leaf_scale=1.1, n_out=14,
                     flowers=dict(spec="pink", petals=9, radius=8.0, n=5)),
    "pine": dict(a="conifer", pal="dark"),
    "spruce": dict(a="conifer", pal="teal", r=45),
    # shrubs
    "boxwood": dict(a="mound", pal="dark", leaf_scale=0.7, n_out=20),
    "rhododendron": dict(a="mound", pal="dark",
                         clusters=dict(radius=8.5, dark="#b3487f", light="#eeb3d3",
                                       occ="#6b1f4a", n=5)),
    "holly": dict(a="mound", pal="dark", frilly=True, leaf_scale=0.95,
                  fruit=dict(kind="cherry", n=4, size=(1.8, 2.3), per=(2, 4))),
    "privet": dict(a="mound", pal="dark", leaf_scale=0.8, n_out=18,
                   umbels=dict(col="#f2ecd0", light="#fbf8ea", n=3, radius=4.0)),
    "juniper": dict(a="conifer", pal="teal", r=40),
    "forsythia": dict(a="mound", pal="yellow",
                      flowers=dict(spec="yellow", petals=4, radius=4.4, n=11, zone=(6, 30))),
    "lilac": dict(a="mound", pal="fresh",
                  clusters=dict(radius=8.0, dark="#8a68c0", light="#d0c0f0",
                                occ="#4a2f80", n=5)),
    "viburnum": dict(a="mound", pal="dark",
                     clusters=dict(radius=7.5, dark="#d8d4c0", light="#fbf9f0",
                                   occ="#6b6a50", n=5)),
    "barberry": dict(a="mound", pal="redleaf", shadow_col="#2a0d10",
                     fruit=dict(kind="cherry", scatter=True, n=8, size=(1.4, 1.9))),
    "camellia": dict(a="mound", pal="dark",
                     flowers=dict(spec="pink", petals=8, radius=7.0, n=5, double=True)),
    "spirea": dict(a="mound", pal="fresh",
                   flowers=dict(spec="white", petals=5, radius=3.0, n=11, zone=(8, 30))),
    "elderberry": dict(a="mound", pal="dark",
                       umbels=dict(col="#f2ecd0", light="#fbf8ea", n=5, radius=6.0)),
    "blueberry": dict(a="mound", pal="teal",
                      fruit=dict(kind="blueberry", scatter=True, n=12, size=(1.7, 2.3))),
    "raspberry": dict(a="mound", pal="fresh", frilly=True,
                      fruit=dict(kind="cherry", scatter=True, n=10, size=(2.0, 2.6))),
    "blackberry": dict(a="mound", pal="dark",
                       fruit=dict(kind="blackberry", scatter=True, n=11, size=(1.9, 2.6))),
    "gooseberry": dict(a="mound", pal="fresh",
                       fruit=dict(kind="gooseberry", scatter=True, n=9, size=(2.0, 2.6),
                                  occ="#2a3a10")),
    "currant": dict(a="mound", pal="fresh",
                    fruit=dict(kind="cherry", scatter=True, n=13, size=(1.5, 2.0))),
    "rose": dict(a="mound", pal="dark",
                 flowers=dict(spec="rose_red", petals=9, radius=6.5, n=5, double=True)),
    "hydrangea": dict(a="mound", pal="fresh",
                      clusters=dict(radius=9.0, dark="#5c7fd0", light="#c3d0f0",
                                    occ="#2a3a78", n=5)),
    "hibiscus": dict(a="mound", pal="dark",
                     flowers=dict(spec="red", petals=5, radius=8.5, n=4)),
    "jasmine": dict(a="climber", pal="dark",
                    flowers=dict(spec="white", petals=5, radius=4.0, n=9)),
    "clematis": dict(a="climber", pal="fresh",
                     flowers=dict(spec="purple", petals=6, radius=7.5, n=5)),
    "wisteria": dict(a="climber", pal="fresh",
                     clusters=dict(radius=6.5, dark="#8a68c0", light="#d0c0f0",
                                   occ="#4a2f80", n=7, zone=(10, 28))),
    # vegetables
    "tomato": dict(a="mound", pal="fresh", fruit=dict(kind="tomato", n=4, size=(3.4, 4.3)),
                   fruit2=dict(kind="green", n=3, size=(2.2, 2.8))),
    "pepper": dict(a="mound", pal="fresh", fruit=dict(kind="tomato", n=3, size=(3.4, 4.2)),
                   fruit2=dict(kind="lemon", n=3, size=(2.6, 3.2))),
    "eggplant": dict(a="mound", pal="dark",
                     fruit=dict(kind="eggplant", n=3, size=(3.6, 4.6), per=(1, 2))),
    "zucchini": dict(a="mound", pal="crisp", frilly=True, leaf_scale=1.3, n_out=10,
                     pods=dict(n=4, dark="#1f5c14", light="#5ca438", length=10.0),
                     flowers=dict(spec="yellow", petals=5, radius=4.0, n=2)),
    "cucumber": dict(a="climber", pal="crisp", frilly=True,
                     pods=dict(n=6, dark="#3f8226", light="#9fdf6f", length=9.0),
                     flowers=dict(spec="yellow", petals=5, radius=3.2, n=3)),
    "pumpkin": dict(a="mound", pal="fresh", frilly=True, leaf_scale=1.35, n_out=10,
                    fruit=dict(kind="pumpkin", n=2, size=(6.0, 8.0), per=(1, 1),
                               zone=(12, 20))),
    "squash": dict(a="mound", pal="fresh", frilly=True, leaf_scale=1.3, n_out=10,
                   fruit=dict(kind="butternut", n=2, size=(4.5, 6.0), per=(1, 2),
                              zone=(12, 20))),
    "bean": dict(a="climber", pal="fresh", pods=dict(n=9, dark="#3f8226", light="#9fdf6f")),
    "pea": dict(a="climber", pal="crisp", pods=dict(n=8, dark="#3f8226", light="#9fdf6f"),
                flowers=dict(spec="white", petals=5, radius=3.6, n=3)),
    "corn": dict(a="allium", pal="yellow", n_out=14,
                 umbels=dict(n=1, zone=(0, 2), radius=6.5, col="#f0cf5a", light="#fae89a")),
    "carrot": dict(a="feathery", pal="crisp",
                   bulb=dict(radius=6.0, triad=("#f2a950", "#e07f28", "#a04f0e"))),
    "radish": dict(a="rosette", pal="crisp", leaf_scale=0.85, heart=False,
                   bulb=dict(radius=6.5, triad=("#f28a96", "#d8404f", "#8a1626"))),
    "beet": dict(a="rosette", pal="dark", rib_color="#c93548", rib_width=1.1, heart=False,
                 bulb=dict(radius=7.5, triad=("#c05a6a", "#8a2038", "#4a0f1e"))),
    "turnip": dict(a="rosette", pal="fresh", heart=False,
                   bulb=dict(radius=7.0, triad=("#f4eede", "#d9c3dd", "#8a5f9d"))),
    "potato": dict(a="mound", pal="fresh",
                   flowers=dict(spec="white", petals=5, radius=3.8, n=4)),
    "onion": dict(a="allium", pal="fresh",
                  bulb=dict(radius=7.0, triad=("#e8c890", "#c89050", "#8a5a24"))),
    "garlic": dict(a="allium", pal="silver",
                   bulb=dict(radius=6.0, triad=("#f4efe0", "#ddd2b8", "#a89878"))),
    "leek": dict(a="allium", pal="teal",
                 bulb=dict(radius=5.0, triad=("#e8f0d8", "#c3d8a8", "#8aa86a"))),
    "celery": dict(a="rosette", pal="yellow", leaf_scale=0.9, rib_color="#cde8a0",
                   rib_width=1.3),
    "broccoli": dict(a="head", pal="teal", head=("#2a5f33", "#4a8a50", "#77b070")),
    "cauliflower": dict(a="head", pal="fresh", head=("#c9bf98", "#e8dfc0", "#f8f2e0")),
    "cabbage": dict(a="rosette", pal="teal", leaf_scale=1.1),
    "kale": dict(a="rosette", pal="teal", leaf_scale=1.05, heart=False, n_out=11),
    "spinach": dict(a="rosette", pal="fresh", leaf_scale=0.95),
    "lettuce": dict(a="rosette", pal="crisp"),
    "arugula": dict(a="rosette", pal="yellow", leaf_scale=0.9, n_out=11),
    "chard": dict(a="rosette", pal="crisp", rib_color="#d63b47", rib_width=1.1),
    "artichoke": dict(a="head", pal="silver", frilly=True,
                      head=("#55684a", "#7a8f62", "#a8b88a"), head_scale=0.32),
    "asparagus": dict(a="feathery", pal="olive"),
    "rhubarb": dict(a="rosette", pal="fresh", leaf_scale=1.3, n_out=8,
                    rib_color="#c93548", rib_width=1.3, heart=False),
    "okra": dict(a="mound", pal="yellow",
                 pods=dict(n=6, dark="#3f7423", light="#a8cf70", length=9.0),
                 flowers=dict(spec="cream", petals=5, radius=5.0, n=2)),
    # herbs
    "basil": dict(a="mound", pal="crisp", leaf_scale=1.1),
    "rosemary": dict(a="mound", pal="dark", narrow=True, n_out=30,
                     flowers=dict(spec="blue", petals=4, radius=2.6, n=5)),
    "thyme": dict(a="mound", pal="olive", leaf_scale=0.55, n_out=22,
                  flowers=dict(spec="pink", petals=4, radius=2.4, n=6)),
    "sage": dict(a="mound", pal="silver", leaf_scale=0.9,
                 flowers=dict(spec="purple", petals=4, radius=3.0, n=5)),
    "mint": dict(a="mound", pal="crisp", frilly=True, leaf_scale=0.95),
    "parsley": dict(a="rosette", pal="crisp", leaf_scale=0.8, n_out=12, heart=False),
    "cilantro": dict(a="rosette", pal="yellow", leaf_scale=0.75, heart=False,
                     umbels=dict(col="#f4f0e0", light="#ffffff", n=3, radius=4.0)),
    "dill": dict(a="feathery", pal="yellow",
                 umbels=dict(col="#e8c34a", light="#f8e48a", n=4, radius=5.0)),
    "chives": dict(a="allium", pal="crisp", n_out=22,
                   clusters=dict(radius=3.4, dark="#8a5fc0", light="#d0c0f0",
                                 occ="#4a2f80", n=7, zone=(20, 32))),
    "oregano": dict(a="mound", pal="yellow", leaf_scale=0.75,
                    flowers=dict(spec="pink", petals=4, radius=3.0, n=7)),
    "tarragon": dict(a="mound", pal="olive", narrow=True, n_out=28),
    "lemongrass": dict(a="grass", pal="yellow", r=42, n_out=34),
    "chamomile": dict(a="feathery", pal="yellow",
                      flowers=dict(spec="white", petals=10, radius=4.8, n=8)),
    "fennel": dict(a="feathery", pal="olive",
                   umbels=dict(col="#e8c34a", light="#f8e48a", n=3, radius=5.0)),
    "marjoram": dict(a="mound", pal="yellow", leaf_scale=0.7, n_out=18,
                     flowers=dict(spec="white", petals=4, radius=2.8, n=6)),
    "bay_laurel": dict(a="mound", pal="dark"),
    "stevia": dict(a="mound", pal="crisp", leaf_scale=0.85),
    "sorrel": dict(a="rosette", pal="crisp", heart=False, n_out=9),
    "borage": dict(a="mound", pal="silver",
                   flowers=dict(spec="blue", petals=5, radius=4.5, n=7)),
    "lovage": dict(a="rosette", pal="yellow", leaf_scale=1.1, heart=False),
    # flowers
    "lavender": dict(a="mound", pal="silver", narrow=True, n_out=26,
                     puffs=dict(dark="#6b46ab", light="#a98fe0", n=9, start=(20.0, 22.5))),
    "tulip": dict(a="grass", pal="crisp", r=36,
                  flowers=dict(spec="red", petals=6, radius=6.0, n=5, zone=(8, 24))),
    "daffodil": dict(a="grass", pal="crisp", r=36,
                     flowers=dict(spec="yellow", petals=6, radius=6.5, n=5, zone=(8, 24))),
    "dahlia": dict(a="mound", pal="fresh",
                   flowers=dict(spec="magenta", petals=12, radius=8.0, n=4, double=True)),
    "peony": dict(a="mound", pal="fresh",
                  flowers=dict(spec="pink", petals=10, radius=8.5, n=4, double=True)),
    "iris": dict(a="grass", pal="teal", r=38,
                 flowers=dict(spec="purple", petals=3, radius=7.5, n=4, double=True,
                              zone=(8, 26))),
    "lily": dict(a="grass", pal="crisp", r=36,
                 flowers=dict(spec="orange", petals=6, radius=7.5, n=4, zone=(8, 24))),
    "marigold": dict(a="mound", pal="fresh",
                     flowers=dict(spec="gold", petals=10, radius=6.0, n=6, double=True)),
    "zinnia": dict(a="mound", pal="fresh",
                   flowers=dict(spec="red", petals=10, radius=6.0, n=6, double=True)),
    "cosmos": dict(a="feathery", pal="fresh",
                   flowers=dict(spec="pink", petals=8, radius=6.5, n=6)),
    "aster": dict(a="mound", pal="fresh",
                  flowers=dict(spec="purple", petals=12, radius=6.5, n=6)),
    "chrysanthemum": dict(a="mound", pal="fresh",
                          flowers=dict(spec="gold", petals=12, radius=7.0, n=5, double=True)),
    "geranium": dict(a="mound", pal="fresh",
                     clusters=dict(radius=6.5, dark="#c03030", light="#f28a80",
                                   occ="#5c1010", n=6)),
    "petunia": dict(a="mound", pal="fresh",
                    flowers=dict(spec="magenta", petals=5, radius=6.5, n=7)),
    "pansy": dict(a="mound", pal="crisp", r=34,
                  flowers=dict(spec="violet_face", petals=5, radius=6.0, n=6)),
    "crocus": dict(a="grass", pal="crisp", r=34,
                   flowers=dict(spec="purple", petals=6, radius=5.0, n=5, zone=(6, 22))),
    "sunflower": dict(a="flower", pal="fresh",
                      flowers=dict(spec="gold", petals=16, double=True)),
}

# --------------------------------------------------------------------------- #
# category table (15)
# --------------------------------------------------------------------------- #
CATEGORIES: dict[str, dict] = {
    "round_deciduous": dict(a="canopy", pal="fresh"),
    "columnar_tree": dict(a="canopy", pal="dark", r=36, leaf_scale=0.8, n_out=20),
    "weeping_tree": dict(a="canopy", pal="silver", leaf_scale=0.9, n_out=24),
    "conifer": dict(a="conifer", pal="dark"),
    "spreading_shrub": dict(a="mound", pal="fresh", r=42),
    "compact_shrub": dict(a="mound", pal="dark", r=34, leaf_scale=0.8),
    "ornamental_grass": dict(a="grass", pal="olive"),
    "flowering_perennial": dict(a="mound", pal="fresh",
                                flowers=dict(spec="pink", petals=8, radius=6.0, n=6)),
    "ground_cover": dict(a="ground", pal="crisp",
                         flowers=dict(spec="white", petals=5, radius=3.0, n=5)),
    "climbing_plant": dict(a="climber", pal="fresh",
                           flowers=dict(spec="purple", petals=5, radius=5.0, n=5)),
    "hedge_section": dict(a="hedge"),
    "vegetable": dict(a="rosette", pal="crisp", leaf_scale=0.95),
    "herb": dict(a="mound", pal="crisp", leaf_scale=0.8,
                 flowers=dict(spec="white", petals=4, radius=2.8, n=4)),
    "fruit_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="apple", n=4)),
    "palm": dict(a="palm", pal="olive"),
}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def generate_all() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for name, cfg in SPECIES.items():
        out[SPECIES_DIR / f"{name}.svg"] = build_sprite(name, cfg)
    for name, cfg in CATEGORIES.items():
        text = build_hedge(name) if cfg["a"] == "hedge" else build_sprite(name, cfg)
        out[CATEGORIES_DIR / f"{name}.svg"] = text
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify committed files match regeneration (no writes)")
    parser.add_argument("--only", nargs="*", default=None,
                        help="restrict to these sprite names (stems)")
    args = parser.parse_args(argv)

    assert len(SPECIES) == 108, f"species table has {len(SPECIES)} entries, expected 108"
    assert len(CATEGORIES) == 15, f"category table has {len(CATEGORIES)} entries, expected 15"

    files = generate_all()
    if args.only:
        wanted = set(args.only)
        files = {p: t for p, t in files.items() if p.stem in wanted}
        missing = wanted - {p.stem for p in files}
        if missing:
            print(f"unknown sprite names: {sorted(missing)}")
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
        print(f"OK: {len(files)} sprite files match regeneration")
        return 0
    print(f"wrote {len(files)} sprite files")
    return 0


if __name__ == "__main__":
    sys.exit(main())

