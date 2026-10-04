"""Qt-free procedural meshes for the Qt Quick 3D spike (ADR-047, Phase 17 L0).

All geometry is plain numpy in the SCENE frame — x = East, y = North, z = up,
centimetres — exactly the frame ``core/shadow_geometry`` and ``core/scene3d``
use. The engine adapter maps it to the engine frame once
(``core.scene3d.to_engine_frame``); nothing here knows about Qt.

Look rules ("Lush Cinematic", plan §5): colours come from the 2D sprite
palettes (copied here for the spike; Package L1.7 moves the tables to
``core/plant_art``), foliage uses *geometric micro-leaves* (no alpha cards) with
*spherized normals* so crowns shade like soft clouds, and every plant is seeded
from its item id so no two plants are clones.

These are prototypes: they graduate into ``core/scene3d/builders`` (L1.6) and
``core/plant_forge`` (L1.7, L3.x) with the fidelity gates of the plan.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from open_garden_planner.core.scene3d import extrude_footprint, triangulate_polygon

Point = tuple[float, float]
Polygon = list[Point]

# ── palettes (copied from scripts/generate_plant_sprites.py — L1.7 shares them) ──

PALETTES: dict[str, tuple[str, str, str, str]] = {
    # tip outer, tip inner, base outer, base inner
    "fresh": ("#54ab4b", "#b7f094", "#1b5a2e", "#4aa557"),
    "crisp": ("#5cb63e", "#a8e678", "#276e1d", "#55a53a"),
    "silver": ("#93b287", "#c7dabc", "#42603c", "#66875e"),
    "dark": ("#3d8f45", "#8fd07a", "#12452a", "#2f7f42"),
    "teal": ("#4f9070", "#a8d8b8", "#1d4a38", "#3c7a5c"),
    "yellow": ("#7dbb45", "#d6ef9a", "#3f7423", "#6aa63d"),
    "olive": ("#7d9c4a", "#c3d795", "#46601f", "#6d8a3a"),
    "redleaf": ("#a04a52", "#d99aa0", "#5c1f28", "#8a3a44"),
    "autumn": ("#b3703c", "#e8b06a", "#6b3318", "#96562a"),
}
ACCENTS: dict[str, str] = {
    "apple": "#e33f28", "cherry": "#d92c3a", "pear": "#c3cf56", "plum": "#6a55b8",
    "tomato": "#e8402a", "tomato_green": "#7aa843", "blueberry": "#5468b8",
    "pink": "#e88aa8", "rose_red": "#c9384f", "magenta": "#c04a94", "purple": "#8a5fc0",
    "blue": "#5c7fd0", "yellow": "#f2c53a", "gold": "#f0a832", "orange": "#ef8330",
    "red": "#d8402e", "white": "#e8e4d8", "lilac": "#a98fe0", "cream": "#f2ecd0",
    "gooseberry": "#a8c860", "pepper_yellow": "#f2d549",
}

# species common name → (archetype, palette, accent kind, accent colour)
SPECIES_LOOK: dict[str, tuple[str, str, str, str]] = {
    "apple tree": ("canopy", "fresh", "fruit", "apple"),
    "cherry tree": ("canopy", "fresh", "fruit", "cherry"),
    "pear tree": ("canopy", "fresh", "fruit", "pear"),
    "plum tree": ("canopy", "dark", "fruit", "plum"),
    "birch": ("canopy", "yellow", "", ""),
    "maple": ("canopy", "autumn", "", ""),
    "magnolia": ("canopy", "fresh", "flower", "pink"),
    "walnut tree": ("canopy", "fresh", "", ""),
    "spruce": ("conifer", "teal", "", ""),
    "pine": ("conifer", "dark", "", ""),
    "hydrangea": ("mound", "fresh", "cluster", "blue"),
    "rose": ("mound", "dark", "flower", "rose_red"),
    "lilac": ("mound", "fresh", "cluster", "lilac"),
    "boxwood": ("mound", "dark", "", ""),
    "forsythia": ("mound", "yellow", "flower", "yellow"),
    "rhododendron": ("mound", "dark", "cluster", "magenta"),
    "blueberry": ("mound", "teal", "fruit", "blueberry"),
    "raspberry": ("mound", "fresh", "fruit", "cherry"),
    "currant": ("mound", "fresh", "fruit", "cherry"),
    "gooseberry": ("mound", "fresh", "fruit", "gooseberry"),
    "lavender": ("mound", "silver", "spike", "purple"),
    "peony": ("mound", "fresh", "flower", "pink"),
    "iris": ("blades", "teal", "flower", "purple"),
    "echinacea": ("mound", "fresh", "flower", "magenta"),
    "aster": ("mound", "fresh", "flower", "purple"),
    "geranium": ("mound", "fresh", "cluster", "red"),
    "chrysanthemum": ("mound", "fresh", "flower", "gold"),
    "lily": ("blades", "crisp", "flower", "orange"),
    "borage": ("mound", "silver", "flower", "blue"),
    "pansy": ("mound", "crisp", "flower", "purple"),
    "tomato": ("mound", "fresh", "fruit", "tomato"),
    "basil": ("mound", "crisp", "", ""),
    "sweet pepper": ("mound", "fresh", "fruit", "red"),
    "lettuce": ("rosette", "crisp", "", ""),
    "cabbage": ("rosette", "teal", "heart", "teal"),
    "kale": ("rosette", "teal", "", ""),
    "carrot": ("feathery", "crisp", "", ""),
    "onion": ("blades", "fresh", "", ""),
    "leek": ("blades", "teal", "", ""),
    "chives": ("blades", "crisp", "pompom", "lilac"),
    "beet": ("rosette", "dark", "", ""),
    "spinach": ("rosette", "fresh", "", ""),
    "zucchini": ("mound", "crisp", "flower", "yellow"),
    "bean (bush)": ("mound", "fresh", "", ""),
    "runner bean": ("climber", "fresh", "flower", "red"),
    "cucumber": ("climber", "crisp", "flower", "yellow"),
    "rosemary": ("mound", "dark", "spike", "blue"),
    "thyme": ("mound", "olive", "flower", "pink"),
    "sage": ("mound", "silver", "spike", "purple"),
    "oregano": ("mound", "yellow", "flower", "pink"),
    "parsley": ("rosette", "crisp", "", ""),
    "sunflower": ("sunflower", "fresh", "flower", "gold"),
    "dahlia": ("mound", "fresh", "flower", "magenta"),
    "marigold": ("mound", "fresh", "flower", "gold"),
    "cosmos": ("feathery", "fresh", "flower", "pink"),
    "zinnia": ("mound", "fresh", "flower", "red"),
    "tulip": ("blades", "crisp", "flower", "red"),
}


@dataclass(frozen=True)
class CanopyForm:
    """The shape of a deciduous crown, per species — form only: ``fit_to`` still makes the
    bounding box the plan's height × spread.

    ``trunk``: clear trunk (the crown's base) as a fraction of the height; ``taper``:
    crown width at its base vs its top (> 0 egg or pyramid, < 0 vase); ``droop``: how far
    leaf tips hang (``leaves``); ``bark``: wood colour, × ``bark_shade`` in linear light;
    ``leaf_scale``: the 2D sprite table's per-species leaf size
    (``scripts/generate_plant_sprites.py`` SPECIES).
    The default IS the L0 crown (one ellipsoid on a 0.34 trunk) for unknown species.
    """

    trunk: float = 0.34
    taper: float = 0.0
    droop: float = 0.15
    bark: str = "#5a4632"
    leaf_scale: float = 1.0
    bark_shade: float = 1.0


# White bark = the 2D white × this, in LINEAR light (the ridge cap's rule): at the full
# #e8e4d8 the sun-lit side of the birch clipped (3D reviewer pass 3) — trunk pixels at a
# channel ≥ 254, low preset: walk 874 → 13, december_noon 441 → 291 (a 14° sun lights a
# vertical trunk at n·l ≈ 0.97).
WHITE_BARK_SHADE = 0.7


# Habit per species (standard dendrology descriptions): apple rounded and spreading on a
# short trunk, branches hanging under fruit; pear upright, pyramidal; cherry broad oval;
# plum rounded; birch a narrow ovoid crown reaching low, pendulous twigs, white bark
# (ACCENTS["white"]); magnolia low-branched and broad, wider above; maple broad, rounded,
# slightly wider above; walnut a broad spreading dome on a tall clear trunk. Reviewer
# pass 3 (side silhouettes at one size, review3/silhouettes.py): mean overlap across
# species 0.730 → 0.700 with the apple, pear, maple and walnut values below.
CANOPY_FORM: dict[str, CanopyForm] = {
    "apple tree": CanopyForm(trunk=0.20, taper=0.15, droop=0.45),
    "pear tree": CanopyForm(trunk=0.24, taper=0.7, droop=0.1),
    "cherry tree": CanopyForm(trunk=0.30, taper=0.1, droop=0.15),
    "plum tree": CanopyForm(trunk=0.28, taper=0.05, droop=0.25),
    "birch": CanopyForm(trunk=0.2, taper=0.25, droop=0.65, bark=ACCENTS["white"],
                        leaf_scale=0.75, bark_shade=WHITE_BARK_SHADE),
    "magnolia": CanopyForm(trunk=0.12, taper=-0.45, droop=0.05, leaf_scale=1.1),
    "maple": CanopyForm(trunk=0.3, taper=-0.15, droop=0.15, leaf_scale=1.1),
    "walnut tree": CanopyForm(trunk=0.40, taper=-0.2, droop=0.15, leaf_scale=1.1),
}


def srgb_to_linear(hex_color: str) -> np.ndarray:
    """``#rrggbb`` → linear RGB float32 (vertex colours are not sRGB-decoded)."""
    rgb = np.array([int(hex_color[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float64) / 255.0
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return lin.astype(np.float32)


def item_seed(item_id: str, salt: str = "") -> int:
    """Stable per-item seed (same idea as plant_renderer's md5 seed)."""
    digest = hashlib.md5(f"{item_id}:{salt}".encode(), usedforsecurity=False)
    return int(digest.hexdigest()[:12], 16)


# ── mesh container ──────────────────────────────────────────────────────


@dataclass
class MeshData:
    """Indexed triangle mesh, SCENE frame, float32 attributes."""

    positions: np.ndarray  # (N, 3)
    normals: np.ndarray  # (N, 3)
    colors: np.ndarray  # (N, 4) linear RGBA
    uv: np.ndarray  # (N, 2) u = wind weight 0..1, v = phase 0..1 (or texture uv)
    indices: np.ndarray  # (M,) uint32

    @property
    def triangle_count(self) -> int:
        return int(len(self.indices) // 3)

    @property
    def vertex_count(self) -> int:
        return int(len(self.positions))

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.positions.min(axis=0), self.positions.max(axis=0)

    @staticmethod
    def empty() -> MeshData:
        z3 = np.zeros((0, 3), np.float32)
        return MeshData(z3, z3.copy(), np.zeros((0, 4), np.float32),
                        np.zeros((0, 2), np.float32), np.zeros(0, np.uint32))

    @staticmethod
    def concat(meshes: Sequence[MeshData]) -> MeshData:
        meshes = [m for m in meshes if m.vertex_count]
        if not meshes:
            return MeshData.empty()
        offsets = np.cumsum([0] + [m.vertex_count for m in meshes[:-1]])
        return MeshData(
            np.concatenate([m.positions for m in meshes]).astype(np.float32),
            np.concatenate([m.normals for m in meshes]).astype(np.float32),
            np.concatenate([m.colors for m in meshes]).astype(np.float32),
            np.concatenate([m.uv for m in meshes]).astype(np.float32),
            np.concatenate([m.indices + o for m, o in zip(meshes, offsets, strict=True)])
            .astype(np.uint32),
        )


def _mesh(pos, nrm, col, uv, idx) -> MeshData:
    return MeshData(
        np.asarray(pos, np.float32).reshape(-1, 3),
        np.asarray(nrm, np.float32).reshape(-1, 3),
        np.asarray(col, np.float32).reshape(-1, 4),
        np.asarray(uv, np.float32).reshape(-1, 2),
        np.asarray(idx, np.uint32).reshape(-1),
    )


def _rgba(color: np.ndarray | str, n: int, alpha: float = 1.0) -> np.ndarray:
    rgb = srgb_to_linear(color) if isinstance(color, str) else np.asarray(color, np.float32)
    out = np.empty((n, 4), np.float32)
    out[:, :3] = rgb
    out[:, 3] = alpha
    return out


def _normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(norm, 1e-9)


def normal_vs_winding(mesh: MeshData) -> tuple[np.ndarray, np.ndarray]:
    """Per non-degenerate triangle: (stored normal · winding normal, is-flat mask).

    The flat-normal gate's instrument. A triangle is *flat-shaded* when its
    three stored vertex normals are identical — how every flat builder emits
    faces; its stored normal must then equal the winding normal (dot ≥ 0.99).
    Smooth triangles (interpolated normals) report the dot of their mean
    normal, which must at least face the same way (> 0).
    """
    tri = mesh.indices.reshape(-1, 3)
    p = mesh.positions.astype(np.float64)
    cross = np.cross(p[tri[:, 1]] - p[tri[:, 0]], p[tri[:, 2]] - p[tri[:, 0]])
    area2 = np.linalg.norm(cross, axis=1)
    keep = area2 > 1e-6
    winding = cross[keep] / area2[keep, None]
    n = mesh.normals.astype(np.float64)[tri[keep]]  # (T, 3 vertices, 3)
    flat = np.abs(n - n[:, :1]).max(axis=(1, 2)) < 1e-6
    stored = n.mean(axis=1)
    stored /= np.maximum(np.linalg.norm(stored, axis=1, keepdims=True), 1e-12)
    return (stored * winding).sum(axis=1), flat


def _face_normal(pos: np.ndarray, idx: Sequence[int] | np.ndarray) -> np.ndarray:
    """Unit normal of a planar triangle set, derived from its WINDING.

    Area-weighted (sum of the triangles' cross products), so a sliver triangle
    cannot tip it. Flat faces take their stored normal from here, never from a
    hand-written formula: the spike's roof slabs once stored the OTHER slope's
    normal, and the sun lit the wrong roof face (reviewer finding, L0).
    """
    tri = np.asarray(idx).reshape(-1, 3)
    p = np.asarray(pos, np.float64)
    cross = np.cross(p[tri[:, 1]] - p[tri[:, 0]], p[tri[:, 2]] - p[tri[:, 0]]).sum(axis=0)
    return _normalize(cross).astype(np.float32)


# ── primitives ──────────────────────────────────────────────────────────


def prism(footprint: Polygon, height: float, base: float, side: str, top: str | None = None) -> MeshData:
    """Extruded footprint (reuses the shipped Qt-free extrusion)."""
    pos, nrm = extrude_footprint(footprint, height, base)
    if not pos:
        return MeshData.empty()
    p = np.asarray(pos, np.float32).reshape(-1, 3)
    n = np.asarray(nrm, np.float32).reshape(-1, 3)
    col = _rgba(side, len(p))
    if top is not None:
        col[n[:, 2] > 0.5, :3] = srgb_to_linear(top)
    return _mesh(p, n, col, np.zeros((len(p), 2)), np.arange(len(p)))


def box(cx: float, cy: float, z0: float, sx: float, sy: float, sz: float, color: str,
        angle_deg: float = 0.0) -> MeshData:
    """Axis box (optionally rotated about z), centred on (cx, cy), from z0 up."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    hx, hy = sx / 2.0, sy / 2.0
    corners = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    fp = [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in corners]
    return prism(fp, sz, z0, color)


def _unit_sphere(subdiv: int = 1) -> tuple[np.ndarray, np.ndarray]:
    verts = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float)
    faces = np.array([[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4],
                      [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]])
    for _ in range(subdiv):
        cache: dict[tuple[int, int], int] = {}
        vlist = list(verts)

        def mid(i: int, j: int, cache=cache, vlist=vlist) -> int:
            key = (min(i, j), max(i, j))
            if key not in cache:
                m = (vlist[i] + vlist[j]) / 2.0
                vlist.append(m / np.linalg.norm(m))
                cache[key] = len(vlist) - 1
            return cache[key]

        new = []
        for a, b, c in faces:
            ab, bc, ca_ = mid(a, b), mid(b, c), mid(c, a)
            new += [[a, ab, ca_], [b, bc, ab], [c, ca_, bc], [ab, bc, ca_]]
        verts, faces = np.array(vlist), np.array(new)
    return verts.astype(np.float32), faces.astype(np.uint32)


_SPHERE_V, _SPHERE_F = _unit_sphere(1)
# close-up props: 3× subdivided, 512 triangles, a 32-gon at the equator (2× left the BBQ
# kettle's rim a visible 16-gon at 1.5 m in the walk shot, reviewer pass 3)
_SPHERE_SMOOTH_V, _SPHERE_SMOOTH_F = _unit_sphere(3)


def spheres(centers: np.ndarray, radii: np.ndarray | float, color: str | np.ndarray,
            squash: float = 1.0, smooth: bool = False) -> MeshData:
    """Many low-poly spheres (fruit, flower clusters, heads) in one mesh.

    ``smooth`` uses the 3× subdivided sphere for close-up props (the BBQ kettle).
    """
    sv, sf = (_SPHERE_SMOOTH_V, _SPHERE_SMOOTH_F) if smooth else (_SPHERE_V, _SPHERE_F)
    centers = np.asarray(centers, np.float32).reshape(-1, 3)
    k = len(centers)
    if k == 0:
        return MeshData.empty()
    r = np.broadcast_to(np.asarray(radii, np.float32), (k,))
    v = sv[None, :, :] * r[:, None, None]
    v[:, :, 2] *= squash
    pos = (v + centers[:, None, :]).reshape(-1, 3)
    # a squashed sphere's normals take the inverse-transpose of the squash (the unit
    # sphere's own normals lit the BBQ kettle as if it were round)
    ellipsoid = _normalize(sv / np.array([1.0, 1.0, squash], np.float32)).astype(np.float32)
    nrm = np.broadcast_to(ellipsoid[None], (k, len(sv), 3)).reshape(-1, 3)
    idx = (sf[None, :, :] + (np.arange(k) * len(sv))[:, None, None]).reshape(-1)
    col = color if isinstance(color, np.ndarray) and color.ndim == 2 else None
    cols = np.repeat(col, len(sv), axis=0) if col is not None else _rgba(color, len(pos))
    return _mesh(pos, nrm, cols, np.zeros((len(pos), 2)), idx)


def cylinder(p0: Sequence[float], p1: Sequence[float], r0: float, r1: float,
             color: str | np.ndarray, sides: int = 8) -> MeshData:
    return tubes(np.asarray([p0], np.float32), np.asarray([p1], np.float32),
                 np.asarray([r0], np.float32), np.asarray([r1], np.float32), color, sides)


def tubes(a: np.ndarray, b: np.ndarray, ra: np.ndarray, rb: np.ndarray,
          color: str | np.ndarray, sides: int = 6) -> MeshData:
    """Frustums from a[i] to b[i] (branches, stems, posts) — one vectorised mesh."""
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    s = len(a)
    if s == 0:
        return MeshData.empty()
    axis = _normalize(b - a)
    helper = np.where(np.abs(axis[:, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
    u = _normalize(np.cross(axis, helper))
    v = np.cross(axis, u)
    th = np.linspace(0.0, 2.0 * math.pi, sides, endpoint=False)
    ring = np.cos(th)[None, :, None] * u[:, None, :] + np.sin(th)[None, :, None] * v[:, None, :]
    bottom = a[:, None, :] + ring * np.asarray(ra, np.float32)[:, None, None]
    top = b[:, None, :] + ring * np.asarray(rb, np.float32)[:, None, None]
    pos = np.concatenate([bottom, top], axis=1).reshape(-1, 3)
    nrm = np.concatenate([ring, ring], axis=1).reshape(-1, 3)
    j = np.arange(sides)
    jn = (j + 1) % sides
    quad = np.stack([j, jn, jn + sides, j, jn + sides, j + sides], axis=1).reshape(-1)
    idx = (quad[None, :] + (np.arange(s) * 2 * sides)[:, None]).reshape(-1)
    if isinstance(color, np.ndarray) and color.ndim == 2:
        cols = np.repeat(color, 2 * sides, axis=0)
    else:
        cols = _rgba(color, len(pos))
    return _mesh(pos, nrm, cols, np.zeros((len(pos), 2)), idx)


def _perpendicular(b: Sequence[float], a: Sequence[float]) -> list[float]:
    """``b`` projected onto the plane ⊥ unit ``a``, normalised (any perpendicular if b ∥ a)."""
    d = b[0] * a[0] + b[1] * a[1] + b[2] * a[2]
    x, y, z = b[0] - d * a[0], b[1] - d * a[1], b[2] - d * a[2]
    length = math.sqrt(x * x + y * y + z * z)
    if length < 1e-6:
        h = (1.0, 0.0, 0.0) if abs(a[2]) >= 0.9 else (0.0, 0.0, 1.0)
        x, y, z = a[1] * h[2] - a[2] * h[1], a[2] * h[0] - a[0] * h[2], a[0] * h[1] - a[1] * h[0]
        length = math.sqrt(x * x + y * y + z * z) or 1.0
    return [x / length, y / length, z / length]


def limb_tubes(pts: np.ndarray, par: np.ndarray, radius: np.ndarray, is_cont: np.ndarray,
               colors: np.ndarray, sides: int = 7) -> MeshData:
    """A branch skeleton as tubes whose joints SHARE one ring per node (seamless limbs).

    Segment ``par[i] → i`` for every node ``i ≥ 1``. Where the segment continues
    its parent's limb (``is_cont[i]``) its bottom ring IS the ring of node
    ``par[i]`` — same vertices, same normals, same radius — so a limb tapers and
    shades continuously; the ring's frame follows the bisector of the segments
    meeting at the node. A side branch starts with its own ring inside the
    parent's wood. (The L0 tubes gave every segment its own frame and ended it
    at 0.92 × its radius: a ledge and a shading step at every joint — the
    "banded" trunk.) ``colors`` holds one RGBA row per segment.
    """
    n = len(pts)
    seg_i = np.arange(1, n)
    if len(seg_i) == 0:
        return MeshData.empty()
    pts = np.asarray(pts, np.float64)
    seg_dir = np.zeros((n, 3))
    seg_dir[seg_i] = _normalize(pts[seg_i] - pts[par[seg_i]])
    cont = seg_i[is_cont[seg_i]]
    cont_child = np.full(n, -1)
    cont_child[par[cont]] = cont
    tangent = seg_dir.copy()
    has = np.where(cont_child >= 0)[0]
    bisector = seg_dir[has] + seg_dir[cont_child[has]]
    ok = np.linalg.norm(bisector, axis=1) > 1e-6
    tangent[has[ok]] = _normalize(bisector[ok])
    if cont_child[0] >= 0:
        tangent[0] = seg_dir[cont_child[0]]  # the root ring faces up its trunk
    # ring frames by PARALLEL TRANSPORT from parent to child (rotation-minimising):
    # a frame picked per node from a fixed helper axis flips phase where a limb bends
    # through the helper's threshold and twists that segment. One pass over the
    # NODES (parents come first), not over vertices.
    t_list, d_list = tangent.tolist(), seg_dir.tolist()
    u_node: list[list[float]] = [[0.0, 0.0, 0.0]] * n
    u_own: list[list[float]] = [[0.0, 0.0, 0.0]] * n
    u_node[0] = _perpendicular([1.0, 0.0, 0.0] if abs(t_list[0][2]) >= 0.9 else [0.0, 0.0, 1.0],
                               t_list[0])
    for i in range(1, n):
        p = int(par[i])
        u_node[i] = _perpendicular(u_node[p], t_list[i])
        u_own[i] = _perpendicular(u_node[p], d_list[i])
    th = np.linspace(0.0, 2.0 * math.pi, sides, endpoint=False)

    def rings(axis: np.ndarray, u: np.ndarray) -> np.ndarray:
        v = np.cross(axis, u)
        ring: np.ndarray = (np.cos(th)[None, :, None] * u[:, None, :]
                            + np.sin(th)[None, :, None] * v[:, None, :])
        return ring

    node_dir = rings(tangent, np.asarray(u_node))   # (n, sides, 3) unit radial directions
    own_dir = rings(seg_dir[seg_i], np.asarray(u_own)[seg_i])  # a side branch's own first ring
    c = is_cont[seg_i][:, None, None]
    bottom_dir = np.where(c, node_dir[par[seg_i]], own_dir)
    bottom_r = np.where(is_cont[seg_i], radius[par[seg_i]], radius[seg_i])
    bottom = pts[par[seg_i]][:, None, :] + bottom_dir * bottom_r[:, None, None]
    top = pts[seg_i][:, None, :] + node_dir[seg_i] * radius[seg_i][:, None, None]
    pos = np.concatenate([bottom, top], axis=1).reshape(-1, 3)
    nrm = np.concatenate([bottom_dir, node_dir[seg_i]], axis=1).reshape(-1, 3)
    j = np.arange(sides)
    jn = (j + 1) % sides
    quad = np.stack([j, jn, jn + sides, j, jn + sides, j + sides], axis=1).reshape(-1)
    idx = (quad[None, :] + (np.arange(len(seg_i)) * 2 * sides)[:, None]).reshape(-1)
    cols = np.repeat(np.asarray(colors, np.float32), 2 * sides, axis=0)
    return _mesh(pos, nrm, cols, np.zeros((len(pos), 2)), idx)


# ── micro-leaves (the foliage workhorse) ─────────────────────────────────


def leaves(positions: np.ndarray, outward: np.ndarray, length: np.ndarray, width: np.ndarray,
           colors: np.ndarray, rng: np.random.Generator, center: np.ndarray | None = None,
           spherize: float = 0.75, droop: float = 0.15) -> MeshData:
    """Diamond micro-leaves (4 verts / 2 tris) facing ``outward``.

    Normals are blended toward the vector from ``center`` (crown centre) —
    "normal spherization": a canopy then shades like one soft volume instead of
    thousands of flickering facets. ``uv.u`` carries the wind weight.
    """
    k = len(positions)
    if k == 0:
        return MeshData.empty()
    n0 = _normalize(outward + rng.normal(0.0, 0.35, (k, 3)))
    rnd = _normalize(rng.normal(0.0, 1.0, (k, 3)))
    along = _normalize(rnd - (rnd * n0).sum(1, keepdims=True) * n0)
    along = _normalize(along - np.array([0.0, 0.0, droop], np.float32))
    side = np.cross(along, n0)
    ln = np.asarray(length, np.float32).reshape(-1, 1)
    wd = np.asarray(width, np.float32).reshape(-1, 1)
    base = positions
    v0 = base
    v1 = base + along * ln * 0.45 + side * wd * 0.5
    v2 = base + along * ln
    v3 = base + along * ln * 0.45 - side * wd * 0.5
    pos = np.stack([v0, v1, v2, v3], axis=1).reshape(-1, 3)
    if center is not None and spherize > 0:
        radial = _normalize(positions - center[None, :])
        n = _normalize(n0 * (1.0 - spherize) + radial * spherize)
    else:
        n = n0
    nrm = np.repeat(n, 4, axis=0)
    cols = np.repeat(colors, 4, axis=0)
    tip = np.arange(len(cols)) % 4 == 2
    cols[tip, :3] = np.minimum(cols[tip, :3] * 1.06 + 0.01, 1.0)  # a soft tip, not a speckle
    weight = np.clip((positions[:, 2:3] / max(float(positions[:, 2].max()), 1.0)), 0.0, 1.0)
    uv = np.concatenate([np.repeat(weight, 4, axis=0),
                         np.repeat(rng.random((k, 1)), 4, axis=0)], axis=1)
    quad = np.array([0, 1, 2, 0, 2, 3])
    idx = (quad[None, :] + (np.arange(k) * 4)[:, None]).reshape(-1)
    return _mesh(pos, nrm, cols, uv, idx)


def _palette_colors(palette: str, t: np.ndarray, rng: np.random.Generator,
                    depth: np.ndarray | None = None) -> np.ndarray:
    """Leaf colours: base→tip palette gradient + jitter, darker inside (fake AO)."""
    t0, t1, b0, b1 = (srgb_to_linear(c) for c in PALETTES.get(palette, PALETTES["fresh"]))
    t = np.clip(t, 0.0, 1.0)[:, None]
    mix = rng.random((len(t), 1)) * 0.6
    base = b0 * (1 - mix) + b1 * mix
    tip = t0 * (1 - mix) + t1 * mix
    rgb = base * (1 - t) + tip * t
    rgb *= rng.uniform(0.94, 1.06, (len(t), 1)).astype(np.float32)  # calm value noise
    if depth is not None:
        rgb *= (0.55 + 0.45 * np.clip(depth, 0.0, 1.0))[:, None]
    out = np.ones((len(t), 4), np.float32)
    out[:, :3] = np.clip(rgb, 0.0, 1.0)
    return out


def flowers(centers: np.ndarray, normals: np.ndarray, radius: float, petal: str, disk: str,
            rng: np.random.Generator, petals: int = 6) -> MeshData:
    """Simple flowers: a centre dot + a ring of petal diamonds facing ``normals``."""
    k = len(centers)
    if k == 0:
        return MeshData.empty()
    parts = [spheres(centers + normals * radius * 0.15, radius * 0.28, disk, squash=0.6)]
    n = _normalize(normals)
    helper = np.where(np.abs(n[:, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
    u = _normalize(np.cross(n, helper))
    v = np.cross(n, u)
    pos_list, out_list = [], []
    for j in range(petals):
        ang = 2 * math.pi * j / petals + rng.random(k) * 0.3
        d = np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * v
        pos_list.append(centers + d * radius * 0.15)
        out_list.append(_normalize(d + n * 0.35))
    p = np.concatenate(pos_list)
    o = np.concatenate(out_list)
    cols = _rgba(petal, len(p))
    cols[:, :3] *= rng.uniform(0.9, 1.1, (len(p), 1))
    petal_mesh = leaves(p, np.repeat(n, petals, axis=0) * 0.3 + o, np.full(len(p), radius),
                        np.full(len(p), radius * 0.6), cols, rng, spherize=0.0, droop=0.0)
    parts.append(petal_mesh)
    return MeshData.concat(parts)


# ── plants ──────────────────────────────────────────────────────────────


# Per-plant triangle budgets (ADR-047 plan §9, the reviewer's budget gate): a tree's
# wood + leaves + fruit/flowers stay within TREE_TRIANGLE_BUDGET; any other plant
# within PLANT_TRIANGLE_BUDGET (measured headroom on the bench plans: max 3,252, a
# zucchini). A crown whose surface asks for more leaves than the budget leaves room
# for gets FEWER, LARGER leaves with the same coverage (1.6) — never a sparser crown.
TREE_TRIANGLE_BUDGET = 25_000
PLANT_TRIANGLE_BUDGET = 6_000
TREE_FLOWERS = 140  # flowers on a flowering tree (magnolia), in season
FLOWER_PETALS = 6
# needle sprays on a conifer, at most: 2 triangles each plus the 16-triangle trunk
CONIFER_SPRAYS_MAX = 12_000


def _tree_accent_triangles(accent: tuple[str, str], n_twig: int, spread: float) -> int:
    """Triangles ``space_colonization_tree`` spends on fruit or flowers — an upper bound.

    Counted BEFORE the leaves are placed, so the leaf budget can leave room for them
    (140 magnolia flowers cost 6,160 triangles: a fixed margin did not cover them).
    """
    kind, name = accent
    if name not in ACCENTS:
        return 0
    if kind == "fruit":
        return min(n_twig, max(6, int(spread / 25))) * len(_SPHERE_F)
    if kind == "flower":
        return TREE_FLOWERS * (len(_SPHERE_F) + 2 * FLOWER_PETALS)
    return 0


def _ellipsoid_points(rng: np.random.Generator, n: int, radii: np.ndarray,
                      shell: float = 0.0) -> np.ndarray:
    """Uniform points inside an ellipsoid (or a shell of relative thickness)."""
    pts = []
    need = n
    while need > 0:
        cand = rng.uniform(-1.0, 1.0, (need * 3, 3))
        r = np.linalg.norm(cand, axis=1)
        ok = (r <= 1.0) & (r >= shell)
        pts.append(cand[ok][:need])
        need -= len(pts[-1])
    return np.concatenate(pts) * radii[None, :]


def space_colonization_tree(seed: int, height: float, spread: float, palette: str,
                            accent: tuple[str, str] = ("", ""), leaf_scale: float = 1.0,
                            form: CanopyForm | None = None) -> MeshData:
    """A deciduous tree grown by space colonization (Runions et al. 2007).

    The crown sits on a clear trunk of ``form.trunk`` × the height and fills an
    ellipsoid of the measured spread, tapered by ``form.taper``; the pipe model
    (r_parent^2.5 = Σ r_child^2.5) sizes the branches; twigs carry spherized
    micro-leaves; optional fruit/flowers from the sprite accents. The bounding
    box matches ``height`` × ``spread`` (fidelity gate, via ``fit_to``).
    """
    form = form or CanopyForm()
    rng = np.random.default_rng(seed)
    trunk_h = height * form.trunk
    crown_h = height - trunk_h
    crown_c = np.array([0.0, 0.0, trunk_h + crown_h * 0.5])
    radii = np.array([spread * 0.5, spread * 0.5, crown_h * 0.5])

    def taper_xy(z: np.ndarray) -> np.ndarray:
        """Crown width factor at height z: 1 + taper at the crown's base, 1 - taper at its top."""
        zn = np.clip((z - crown_c[2]) / radii[2], -1.0, 1.0)
        return 1.0 - form.taper * zn

    attractors = _ellipsoid_points(rng, 520, radii * 0.92) + crown_c
    if form.taper:
        attractors[:, :2] *= taper_xy(attractors[:, 2])[:, None]
    seg = max(height / 28.0, 6.0)
    influence, kill = seg * 7.0, seg * 1.6
    nodes = [np.array([0.0, 0.0, 0.0])]
    parents = [-1]
    while nodes[-1][2] < trunk_h:
        nodes.append(nodes[-1] + np.array([rng.normal(0, 0.04) * seg, rng.normal(0, 0.04) * seg, seg]))
        parents.append(len(nodes) - 2)
    for _ in range(140):
        if len(attractors) == 0 or len(nodes) > 1800:
            break
        n_arr = np.asarray(nodes)
        d = np.linalg.norm(attractors[:, None, :] - n_arr[None, :, :], axis=2)
        nearest = d.argmin(axis=1)
        dmin = d[np.arange(len(attractors)), nearest]
        active = dmin < influence
        if not active.any():
            break
        dirs = np.zeros_like(n_arr)
        vec = _normalize(attractors[active] - n_arr[nearest[active]])
        np.add.at(dirs, nearest[active], vec)
        growers = np.unique(nearest[active])
        grown = 0
        for g in growers:
            direction = _normalize(dirs[g] + np.array([0.0, 0.0, 0.12]) + rng.normal(0, 0.08, 3))
            new = n_arr[g] + direction * seg
            if np.min(np.linalg.norm(n_arr - new, axis=1)) < seg * 0.35:
                continue
            nodes.append(new)
            parents.append(int(g))
            grown += 1
        if grown == 0:
            break
        n_arr = np.asarray(nodes)
        d2 = np.linalg.norm(attractors[:, None, :] - n_arr[None, -grown:, :], axis=2)
        attractors = attractors[d2.min(axis=1) > kill]
    pts = np.asarray(nodes, np.float32)
    par = np.asarray(parents)
    children = np.zeros(len(pts), int)
    np.add.at(children, par[par >= 0], 1)
    radius = np.full(len(pts), 0.45, np.float64)
    for i in range(len(pts) - 1, 0, -1):  # children always come after parents
        p = par[i]
        radius[p] = (radius[p] ** 2.5 + radius[i] ** 2.5) ** (1 / 2.5) if children[p] else radius[i]
    radius *= (height * 0.018) / max(radius[0], 1e-6)  # trunk base = 1.8 % of the height
    radius = np.maximum(radius, 0.35)
    seg_i = np.arange(1, len(pts))
    # one bark shade per BRANCH (a node continues its parent's branch when it is
    # the parent's first child): a per-segment shade banded the trunk like a ladder
    branch = np.zeros(len(pts), int)
    continued = np.zeros(len(pts), bool)  # node already has its continuation child
    is_cont = np.zeros(len(pts), bool)    # node continues its parent's limb
    n_branches = 1
    for i in range(1, len(pts)):
        p = par[i]
        if continued[p]:
            branch[i] = n_branches
            n_branches += 1
        else:
            continued[p] = is_cont[i] = True
            branch[i] = branch[p]
    shade = np.random.default_rng(seed + 1).uniform(0.92, 1.08, n_branches).astype(np.float32)
    bark = _rgba(form.bark, len(seg_i))
    bark[:, :3] *= shade[branch[seg_i]][:, None] * form.bark_shade
    wood = limb_tubes(pts, par, radius, is_cont, bark, sides=7)
    # foliage: leaf clusters on every thin branch inside the crown; the leaf count
    # follows the crown's surface area so coverage (not a magic number) is the knob
    thin_cut = np.percentile(radius[1:], 60) if len(radius) > 1 else radius[0]
    twig = np.where((radius <= thin_cut) & (pts[:, 2] > trunk_h * 0.85))[0]
    if len(twig) == 0:
        twig = np.arange(len(pts))
    a, b, c = radii
    surface = 4 * math.pi * (((a * b) ** 1.6 + (a * c) ** 1.6 + (b * c) ** 1.6) / 3) ** (1 / 1.6)
    leaf_l = float(np.clip(height * 0.04, 9.0, 22.0) * leaf_scale * form.leaf_scale)
    # a micro-leaf covers 0.5 · l · 0.6 l; coverage 1.6 of the crown's surface
    n_leaves = max(surface / (0.5 * leaf_l * leaf_l * 0.6) * 1.6, 1500.0)
    # the budget: wood and accents first, two triangles per leaf for the rest. A crown
    # over it keeps its coverage with fewer, larger leaves (n · l² stays the same): the
    # old fixed cap of 16,000 leaves was 32,000 triangles by itself, and a small-leaved
    # birch (leaf_scale 0.75 → 1.78× the leaves) reached 40,954 on the bench plans
    n_max = (TREE_TRIANGLE_BUDGET - wood.triangle_count
             - _tree_accent_triangles(accent, len(twig), spread)) // 2
    n_target = int(min(n_leaves, n_max))
    per = max(2, n_target // len(twig))
    if n_leaves > n_max:  # sized on the count actually PLACED (per rounds it down ≤ 5 %)
        leaf_l *= math.sqrt(n_leaves / (len(twig) * per))
    centers = np.repeat(pts[twig], per, axis=0) + rng.normal(0, seg * 1.1, (len(twig) * per, 3))
    rel = (centers - crown_c) / radii
    if form.taper:  # depth inside the TAPERED crown (the fake-AO darkening)
        rel[:, :2] /= taper_xy(centers[:, 2])[:, None]
    depth = np.clip(np.linalg.norm(rel, axis=1), 0.0, 1.0)
    t = np.clip((centers[:, 2] - trunk_h) / crown_h, 0, 1) * 0.6 + depth * 0.4
    cols = _palette_colors(palette, t, rng, depth)
    leaf_len = np.full(len(centers), leaf_l)
    foliage = leaves(centers.astype(np.float32), (centers - crown_c).astype(np.float32),
                     leaf_len * rng.uniform(0.8, 1.2, len(centers)), leaf_len * 0.6, cols, rng,
                     center=crown_c.astype(np.float32), droop=form.droop)
    parts = [wood, foliage]
    kind, accent_name = accent
    if kind == "fruit" and accent_name in ACCENTS:
        pick = rng.choice(len(twig), size=min(len(twig), max(6, int(spread / 25))), replace=False)
        fc = pts[twig[pick]] + rng.normal(0, seg * 0.4, (len(pick), 3)) - [0, 0, seg * 0.6]
        parts.append(spheres(fc, np.clip(spread * 0.012, 3.0, 6.0), ACCENTS[accent_name]))
    elif kind == "flower" and accent_name in ACCENTS:
        pick = rng.choice(len(centers), size=min(len(centers), TREE_FLOWERS), replace=False)
        parts.append(flowers(centers[pick], _normalize(centers[pick] - crown_c), 9.0,
                             ACCENTS[accent_name], "#f7e3a0", rng, petals=FLOWER_PETALS))
    return MeshData.concat(parts)


def conifer(seed: int, height: float, spread: float, palette: str) -> MeshData:
    """Stylised spruce: trunk + tiers of drooping needle sprays on a cone.

    The trunk tapers to a point at 0.90 × the height, inside the top whorls (at 0.97
    it poked out above the sparse leader as a bare stub). At most ``CONIFER_SPRAYS_MAX``
    sprays (the tree budget); a cone that asks for more gets fewer, larger sprays with
    the same total area (n · ln² unchanged).
    """
    rng = np.random.default_rng(seed)
    trunk = cylinder((0, 0, 0), (0, 0, height * 0.90), height * 0.02, 0.0, "#4b3a2a")
    n_raw = height * spread / 22.0
    n = int(np.clip(n_raw, 3000, CONIFER_SPRAYS_MAX))
    z = height * (0.12 + 0.86 * (1 - np.sqrt(rng.random(n))))  # denser near the bottom
    frac = (height - z) / (height * 0.88)
    r = spread * 0.5 * np.clip(frac, 0, 1) * rng.uniform(0.35, 1.0, n) ** 0.5
    th = rng.uniform(0, 2 * math.pi, n)
    tier = np.sin(z / height * 9 * math.pi) * 0.12 + 0.88  # gentle whorl banding
    pos = np.stack([np.cos(th) * r * tier, np.sin(th) * r * tier, z - r * 0.25], axis=1)
    axis_pt = np.stack([np.zeros(n), np.zeros(n), z + spread * 0.15], axis=1)
    out = pos - axis_pt
    depth = np.clip(r / (spread * 0.5 * np.clip(frac, 0.05, 1)), 0, 1)
    cols = _palette_colors(palette, depth * 0.7 + 0.15, rng, depth)
    ln = float(np.clip(height * 0.035, 10, 28))
    if n_raw > CONIFER_SPRAYS_MAX:
        ln *= math.sqrt(n_raw / CONIFER_SPRAYS_MAX)
    foliage = leaves(pos.astype(np.float32), out.astype(np.float32), np.full(n, ln),
                     np.full(n, ln * 0.42), cols, rng,
                     center=np.array([0, 0, height * 0.45], np.float32), spherize=0.55,
                     droop=0.5)
    return MeshData.concat([trunk, foliage])


def mound(seed: int, height: float, spread: float, palette: str, accent: tuple[str, str],
          narrow: bool = False) -> MeshData:
    """Shrubs, perennials, herbs, bushy vegetables: a leafy dome on short stems."""
    rng = np.random.default_rng(seed)
    radii = np.array([spread * 0.5, spread * 0.5, height * 0.62])
    center = np.array([0.0, 0.0, height * 0.38])
    area = 2 * math.pi * (spread * 0.5) ** 2
    leaf = float(np.clip(spread * 0.11, 3.5, 13.0))
    n = int(np.clip(area / (leaf * leaf * 0.32), 60, 1400))
    pts = _ellipsoid_points(rng, n, radii, shell=0.55) + center
    pts[:, 2] = np.maximum(pts[:, 2], height * 0.04)
    rel = (pts - center) / radii
    depth = np.clip(np.linalg.norm(rel, axis=1), 0, 1)
    cols = _palette_colors(palette, np.clip(pts[:, 2] / height, 0, 1), rng, depth)
    w = 0.32 if narrow else 0.6
    foliage = leaves(pts.astype(np.float32), (pts - center + [0, 0, height * 0.2]).astype(np.float32),
                     np.full(n, leaf) * rng.uniform(0.8, 1.25, n), np.full(n, leaf * w), cols, rng,
                     center=center.astype(np.float32))
    stems = tubes(np.zeros((5, 3), np.float32),
                  (rng.normal(0, 1, (5, 3)) * [spread * 0.18, spread * 0.18, 0]
                   + [0, 0, height * 0.5]).astype(np.float32),
                  np.full(5, max(spread * 0.012, 0.4)), np.full(5, max(spread * 0.006, 0.3)),
                  "#5d6b33", sides=5)
    parts = [stems, foliage]
    kind, name = accent
    if name in ACCENTS:
        top = pts[pts[:, 2] > height * 0.55]
        if len(top):
            if kind == "fruit":
                m = min(len(top), max(4, int(spread / 9)))
                sel = top[rng.choice(len(top), m, replace=False)]
                parts.append(spheres(sel - [0, 0, leaf * 0.4], np.clip(spread * 0.035, 1.2, 4.5),
                                     ACCENTS[name]))
                if name == "tomato":
                    sel2 = top[rng.choice(len(top), max(2, m // 2), replace=False)]
                    parts.append(spheres(sel2, np.clip(spread * 0.03, 1.2, 3.8),
                                         ACCENTS["tomato_green"]))
            elif kind in ("flower", "cluster", "spike"):
                m = min(len(top), max(5, int(spread / (6 if kind == "flower" else 12))))
                sel = top[rng.choice(len(top), m, replace=False)]
                if kind == "cluster":
                    parts.append(spheres(sel, np.clip(spread * 0.07, 2.0, 9.0), ACCENTS[name]))
                elif kind == "spike":
                    tipz = sel + [0, 0, height * 0.25]
                    parts.append(tubes(sel, tipz, np.full(m, 1.0), np.full(m, 0.6), ACCENTS[name],
                                       sides=4))
                else:
                    parts.append(flowers(sel, _normalize(sel - center + [0, 0, height * 0.6]),
                                         np.clip(spread * 0.06, 1.8, 6.0), ACCENTS[name],
                                         "#f0d060", rng))
    return MeshData.concat(parts)


def rosette(seed: int, height: float, spread: float, palette: str, heart: bool) -> MeshData:
    """Lettuce/cabbage/beet/parsley: phyllotaxis leaves (golden angle) from the crown."""
    rng = np.random.default_rng(seed)
    n = int(np.clip(spread * 0.9, 14, 40))
    golden = math.radians(137.508)
    i = np.arange(n)
    ang = i * golden
    radial = np.sqrt((i + 1) / n)
    length = spread * 0.36 * (0.55 + 0.45 * radial) * rng.uniform(0.9, 1.1, n)
    base = np.zeros((n, 3))
    base[:, 2] = height * 0.05
    out = np.stack([np.cos(ang), np.sin(ang), 1.1 - radial * 0.9], axis=1)
    cols = _palette_colors(palette, 1.0 - radial * 0.6, rng)
    m = leaves(base.astype(np.float32), out.astype(np.float32), length, length * 0.75, cols, rng,
               center=np.array([0, 0, -height * 0.4], np.float32), spherize=0.6, droop=-0.2)
    # lift leaf tips so the rosette has height
    parts = [m]
    if heart:
        parts.append(spheres(np.array([[0, 0, height * 0.45]]), spread * 0.2,
                             PALETTES[palette][1], squash=0.85))
    return MeshData.concat(parts)


def blades(seed: int, height: float, spread: float, palette: str,
           accent: tuple[str, str]) -> MeshData:
    """Onion/leek/chives/iris/tulip/grassy plants: a fountain of curved blades."""
    rng = np.random.default_rng(seed)
    n = int(np.clip(spread * 0.6, 8, 26))
    segs = 4
    ang = rng.uniform(0, 2 * math.pi, n)
    lean = rng.uniform(0.15, 0.55, n)
    hgt = height * rng.uniform(0.75, 1.0, n)
    width = np.clip(spread * 0.06, 0.8, 3.0)
    pos, nrm, col, uv = [], [], [], []
    idx = []
    t0, t1, b0, b1 = (srgb_to_linear(c) for c in PALETTES[palette])
    for k in range(n):
        d = np.array([math.cos(ang[k]), math.sin(ang[k]), 0.0])
        side = np.array([-d[1], d[0], 0.0])
        for s in range(segs + 1):
            f = s / segs
            center = d * (lean[k] * hgt[k] * f * f) + np.array([0, 0, hgt[k] * f])
            w = width * (1.0 - f * 0.85)
            for sign in (-1, 1):
                pos.append(center + side * w * 0.5 * sign)
                nrm.append(_normalize(d * 0.6 + np.array([0, 0, 0.8])))
                c = b0 * (1 - f) + t1 * f * 0.6 + t0 * f * 0.4
                col.append([*np.clip(c, 0, 1), 1.0])
                uv.append([f, rng.random()])
            if s < segs:
                o = k * (segs + 1) * 2 + s * 2
                idx += [o, o + 1, o + 3, o, o + 3, o + 2]
    parts = [_mesh(pos, nrm, col, uv, idx)]
    kind, name = accent
    if name in ACCENTS:
        # exactly the blade's tip (the f = 1 centre above), so a head sits ON its blade
        tips = np.array([[math.cos(a) * lean[i] * hgt[i], math.sin(a) * lean[i] * hgt[i],
                          hgt[i]] for i, a in enumerate(ang)])
        # the blade's direction at its tip, d/df of the centre line at f = 1: a head faces
        # along its own stem's lean (they all faced straight up)
        tangent = _normalize(np.stack([2.0 * lean * np.cos(ang), 2.0 * lean * np.sin(ang),
                                       np.ones(n)], axis=1))
        pick = rng.choice(n, max(1, n // 4), replace=False)
        sel = tips[pick]
        if kind == "pompom":
            parts.append(spheres(sel, np.clip(spread * 0.08, 1.5, 3.0), ACCENTS[name]))
        else:
            parts.append(flowers(sel, tangent[pick], np.clip(spread * 0.18, 3.0, 7.0),
                                 ACCENTS[name], "#f2cf4e", rng, petals=6))
    return MeshData.concat(parts)


def sunflower(seed: int, height: float, spread: float, head: bool = True) -> MeshData:
    """Stem, broad leaves, and a head facing EAST (mature heads do; buds track the sun).

    ``head`` False (out of the frost-free season) leaves stem and leaves only.
    """
    rng = np.random.default_rng(seed)
    stem = cylinder((0, 0, 0), (0, 0, height * 0.95), 1.6, 1.0, "#4f7a2c")
    zs = np.linspace(height * 0.15, height * 0.8, 7)
    lp = np.stack([np.zeros(7), np.zeros(7), zs], axis=1)
    lo = np.stack([np.cos(np.arange(7) * 2.4), np.sin(np.arange(7) * 2.4), np.full(7, 0.2)], 1)
    leafs = leaves(lp.astype(np.float32), lo.astype(np.float32), np.full(7, spread * 0.32),
                   np.full(7, spread * 0.24), _palette_colors("fresh", np.full(7, 0.6), rng), rng,
                   spherize=0.0)
    if not head:
        return MeshData.concat([stem, leafs])
    face = _normalize(np.array([[1.0, rng.normal(0, 0.15), 0.35]]))  # east, tilted up
    head_c = np.array([[0.0, 0.0, height * 0.95]]) + face * 4.0
    head = flowers(head_c, face, spread * 0.22, ACCENTS["gold"], "#5b3a1a", rng, petals=16)
    disk = spheres(head_c + face * 1.0, spread * 0.09, "#4a2e14", squash=0.5)
    return MeshData.concat([stem, leafs, head, disk])


def fit_to(mesh: MeshData, height: float, spread: float) -> MeshData:
    """Scale a plant mesh so its bounding box IS the data: z ∈ [0, height], xy-span = spread.

    The builders produce *shape*; this final fit enforces *truth* — the
    resolver's height and the 2D canopy spread — for every archetype at once
    (the plan's fidelity gates: height ±3 %, spread ±10 %). Normals take the
    inverse-transpose of the non-uniform scale.
    """
    if mesh.vertex_count == 0 or height <= 0 or spread <= 0:
        return mesh
    lo, hi = mesh.bounds()
    span_xy = max(float(hi[0] - lo[0]), float(hi[1] - lo[1]), 1e-3)
    z0 = min(float(lo[2]), 0.0)  # leaves that dip below the crown rest ON the ground
    span_z = max(float(hi[2]) - z0, 1e-3)
    sxy = spread / span_xy
    sz = height / span_z
    scale = np.array([sxy, sxy, sz], np.float32)
    cx = (lo[0] + hi[0]) / 2.0
    cy = (lo[1] + hi[1]) / 2.0
    pos = (mesh.positions - np.array([cx, cy, z0], np.float32)) * scale
    nrm = _normalize(mesh.normals / scale)
    return MeshData(pos.astype(np.float32), nrm.astype(np.float32), mesh.colors, mesh.uv,
                    mesh.indices)


def fit_height(mesh: MeshData, height: float, top: float | None = None) -> MeshData:
    """Scale a built object in z, about the ground, so its top IS the resolved height.

    The built-world twin of ``fit_to``: builders produce *shape* (posts above
    the pickets, a wall cap, a ridge cap, a kettle) and this final fit
    enforces *truth* — the bounding-box top equals ``effective_height_cm``
    (the §1 height gate). ``top`` lets the meshes of one item (a greenhouse's
    frame and glass) share ONE scale: pass the top of their union. Normals
    take the inverse-transpose of the scale, so a flat face keeps
    normal · winding = 1.
    """
    if mesh.vertex_count == 0 or height <= 0:
        return mesh
    current = float(mesh.positions[:, 2].max()) if top is None else float(top)
    if current <= 0:
        return mesh
    s = height / current
    if abs(s - 1.0) < 1e-7:
        return mesh
    pos = mesh.positions.copy()
    pos[:, 2] *= s
    nrm = _normalize(mesh.normals / np.array([1.0, 1.0, s], np.float32))
    return MeshData(pos.astype(np.float32), nrm.astype(np.float32), mesh.colors, mesh.uv,
                    mesh.indices)


def plant_mesh(species: str, seed: int, height: float, spread: float,
               object_type: str, in_season: bool = True) -> MeshData:
    """A plant of the given species, fitted to ``height`` × ``spread`` at the origin.

    ``in_season`` False drops the fruit and flower accents (``SEASONAL_ACCENTS``):
    the caller decides it from the PLAN's frost dates (``runner.in_frost_free_season``),
    never from what looks nicer. Foliage and form are unchanged — the growth model has
    no seasonal leaf-off (``core/growth_model.py``), and bare crowns are an owner question.
    """
    return fit_to(_plant_shape(species, seed, height, spread, object_type, in_season),
                  height, spread)


# Accent kinds that are fruit or flowers — they exist only in the frost-free season.
# "heart" (a cabbage's head) is leaves, coloured from the plant's own palette: it stays.
SEASONAL_ACCENTS = frozenset({"fruit", "flower", "cluster", "spike", "pompom"})


def _plant_shape(species: str, seed: int, height: float, spread: float,
                 object_type: str, in_season: bool = True) -> MeshData:
    """Dispatch a plant to its archetype; centred on the origin (caller translates)."""
    archetype, palette, kind, accent = SPECIES_LOOK.get(
        species.lower(),
        ("canopy" if object_type == "TREE" else "mound", "fresh", "", ""),
    )
    if not in_season and kind in SEASONAL_ACCENTS:
        kind, accent = "", ""
    if archetype == "canopy":
        return space_colonization_tree(seed, height, spread, palette, (kind, accent),
                                       form=CANOPY_FORM.get(species.lower()))
    if archetype == "conifer":
        return conifer(seed, height, spread, palette)
    if archetype == "rosette":
        return rosette(seed, height, spread, palette, heart=(kind == "heart"))
    if archetype == "blades":
        return blades(seed, height, spread, palette, (kind, accent))
    if archetype == "sunflower":
        return sunflower(seed, height, spread, head=bool(kind))
    if archetype == "feathery":
        return mound(seed, height, spread, palette, (kind, accent), narrow=True)
    if archetype == "climber":
        return mound(seed, height, max(spread * 0.6, 30.0), palette, (kind, accent))
    return mound(seed, height, spread, palette, (kind, accent),
                 narrow=species.lower() in ("lavender", "rosemary"))


def translated(mesh: MeshData, dx: float, dy: float, dz: float) -> MeshData:
    return MeshData(mesh.positions + np.array([dx, dy, dz], np.float32), mesh.normals,
                    mesh.colors, mesh.uv, mesh.indices)


# ── grass ────────────────────────────────────────────────────────────────


def _point_in_polygon(px: np.ndarray, py: np.ndarray, poly: Polygon) -> np.ndarray:
    inside = np.zeros(px.shape, bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = (y1 > py) != (y2 > py)
        xint = (x2 - x1) * (py - y1) / ((y2 - y1) + 1e-12) + x1
        inside ^= cond & (px < xint)
    return inside


GRASS_BLADE_BASE = "#4c8c36"  # scripts/generate_asset_forge_textures.py generate_grass, base
GRASS_BLADE_TIP = "#8ccc5e"  # ... and its matching tip (2D lawn hue 104.9°)


def grass(polygon: Polygon, seed: int, density_per_m2: float, exclude: Sequence[Polygon] = (),
          blade_height: float = 14.0) -> MeshData:
    """Merged grass blades inside ``polygon`` (minus ``exclude``), wind weight in uv.u."""
    rng = np.random.default_rng(seed)
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    area_m2 = (max(xs) - min(xs)) * (max(ys) - min(ys)) / 10000.0
    n = int(area_m2 * density_per_m2)
    px = rng.uniform(min(xs), max(xs), n)
    py = rng.uniform(min(ys), max(ys), n)
    keep = _point_in_polygon(px, py, polygon)
    for ex in exclude:
        keep &= ~_point_in_polygon(px, py, ex)
    px, py = px[keep], py[keep]
    k = len(px)
    if k == 0:
        return MeshData.empty()
    h = blade_height * rng.uniform(0.6, 1.3, k)
    ang = rng.uniform(0, 2 * math.pi, k)
    lean = rng.uniform(0.1, 0.45, k) * h
    w = rng.uniform(0.8, 1.4, k)
    d = np.stack([np.cos(ang), np.sin(ang), np.zeros(k)], 1)
    side = np.stack([-np.sin(ang), np.cos(ang), np.zeros(k)], 1)
    base = np.stack([px, py, np.full(k, 0.3)], 1)
    rows = []
    for f, wf in ((0.0, 1.0), (0.45, 0.75), (1.0, 0.0)):
        c = base + d * (lean[:, None] * f * f) + np.array([0, 0, 1.0]) * (h[:, None] * f)
        rows.append((c - side * (w[:, None] * wf * 0.5), c + side * (w[:, None] * wf * 0.5), f))
    pos = np.stack([rows[0][0], rows[0][1], rows[1][0], rows[1][1], rows[2][0]], 1).reshape(-1, 3)
    nrm = np.repeat(_normalize(d * 0.4 + np.array([0, 0, 1.0])), 5, axis=0)
    # the 2D lawn's own blade pair (generate_asset_forge_textures.generate_grass:
    # base (76, 140, 54), tip (140, 204, 94)) — never a new literal
    base_c = srgb_to_linear(GRASS_BLADE_BASE)
    tip_c = srgb_to_linear(GRASS_BLADE_TIP)
    fracs = np.array([0.0, 0.0, 0.45, 0.45, 1.0], np.float32)
    jitter = rng.uniform(0.82, 1.12, (k, 1)).astype(np.float32)
    col = np.empty((k, 5, 4), np.float32)
    col[:, :, :3] = (base_c[None, None, :] * (1 - fracs[None, :, None])
                     + tip_c[None, None, :] * fracs[None, :, None]) * jitter[:, :, None]
    col[:, :, 3] = 1.0
    uv = np.stack([np.tile(fracs, k), np.repeat(rng.random(k), 5)], 1)
    tri = np.array([0, 1, 3, 0, 3, 2, 2, 3, 4])
    idx = (tri[None, :] + (np.arange(k) * 5)[:, None]).reshape(-1)
    return _mesh(pos, nrm, col.reshape(-1, 4), uv, idx)


# ── built world ──────────────────────────────────────────────────────────


def _clip_halfplane(poly: Polygon, a: Point, b: Point, keep_left: bool) -> Polygon:
    """Sutherland–Hodgman clip of ``poly`` by the line a→b."""
    def side(p: Point) -> float:
        val = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        return val if keep_left else -val
    out: Polygon = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        sp, sq = side(p), side(q)
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def _offset_convex(poly: Polygon, dist: float) -> Polygon:
    """Outward offset of a (roughly) convex polygon via its centroid (spike-grade)."""
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    out = []
    for x, y in poly:
        dx, dy = x - cx, y - cy
        r = math.hypot(dx, dy) or 1.0
        out.append((x + dx / r * dist * 1.41, y + dy / r * dist * 1.41))
    return out


RIDGE_CAP_SHADE = 0.8  # ridge cap = roof colour × this, in linear light


def gable_house(footprint: Polygon, ridge: tuple[Point, Point], ridge_height: float,
                wall: str = "#efe4cf", roof: str = "#b4553d", pitch_deg: float = 38.0,
                overhang: float = 35.0) -> MeshData:
    """The whole house as one mesh: ``gable_house_parts`` walls + roof, concatenated."""
    return MeshData.concat(gable_house_parts(footprint, ridge, ridge_height, wall, roof,
                                             pitch_deg, overhang))


def gable_house_parts(footprint: Polygon, ridge: tuple[Point, Point], ridge_height: float,
                      wall: str = "#efe4cf", roof: str = "#b4553d", pitch_deg: float = 38.0,
                      overhang: float = 35.0) -> tuple[MeshData, MeshData]:
    """(walls, roof): walls to eave height + gable ends, and a two-plane roof along the 2D
    ridge with its soffit and ridge cap — two meshes, so the roof wears its own material
    (``ogp-lush-cinematic`` §4 roof tiles; the runner emits it as kind ``"roof"``).

    Heights: the TOP of the mesh — the ridge cap — is ``ridge_height``, the
    house's effective height (D4: a HOUSE's ``object_height_cm`` is its ridge
    height), so the bounding box IS the data. The roof planes' mid-plane meets
    at the gable apex, ``rise + 6`` cm below that (cap rise + half the 12 cm
    slab); eave = apex − tan(pitch)·(max distance from the ridge). Where that
    falls below 220 cm, the eave becomes min(220 cm, 0.75·apex) and the pitch
    steepens to meet it, so a low shed keeps a pitched roof with an eave below
    220 cm (the plan's D4 clamp is L1.6 work). Spike scope: convex footprints whose ridge
    touches the boundary — exactly what ``core.roof_ridge`` produces for
    rectangles. Every flat face takes its normal from its winding.
    """
    (ax, ay), (bx, by) = ridge
    lx, ly = bx - ax, by - ay
    ll = math.hypot(lx, ly) or 1.0
    nx, ny = -ly / ll, lx / ll

    def dist(p: Point) -> float:
        return abs((p[0] - ax) * nx + (p[1] - ay) * ny)

    ext = (ax - lx / ll * overhang, ay - ly / ll * overhang)
    ext_b = (bx + lx / ll * overhang, by + ly / ll * overhang)
    # the ridge cap is the top of the house: build it at z = 0, measure how far
    # its hexagon rises above its axis, and hang everything else below it. Its colour
    # is the roof's, × RIDGE_CAP_SHADE in linear light (a fixed terracotta cap sat on
    # the shingle shed roof)
    cap_rgba = _rgba(roof, 1)
    cap_rgba[:, :3] *= RIDGE_CAP_SHADE
    cap = cylinder((ext[0], ext[1], 0.0), (ext_b[0], ext_b[1], 0.0), 7.0, 7.0, cap_rgba, sides=6)
    cap_z = ridge_height - float(cap.positions[:, 2].max())
    apex = cap_z - 6.0  # slab mid-plane at the ridge line; the slab tops meet the cap axis
    dmax = max(dist(p) for p in footprint) or 1.0
    slope = math.tan(math.radians(pitch_deg))
    eave = apex - slope * dmax
    if eave < 220.0:
        eave = min(220.0, apex * 0.75)
        slope = (apex - eave) / dmax
    parts = [prism(footprint, eave, 0.0, wall)]
    roof_parts: list[MeshData] = []
    # gable end triangles where the ridge meets the outline
    for end in (ridge[0], ridge[1]):
        n = len(footprint)
        for i in range(n):
            p, q = footprint[i], footprint[(i + 1) % n]
            ex, ey = q[0] - p[0], q[1] - p[1]
            el = math.hypot(ex, ey) or 1.0
            cross = abs((end[0] - p[0]) * ey - (end[1] - p[1]) * ex) / el
            t = ((end[0] - p[0]) * ex + (end[1] - p[1]) * ey) / (el * el)
            if cross < 2.0 and -0.01 <= t <= 1.01:
                tri = np.array([[p[0], p[1], eave], [q[0], q[1], eave],
                                [end[0], end[1], apex]], np.float32)
                normal = _normalize(np.cross(tri[1] - tri[0], tri[2] - tri[0]))
                center = np.array([sum(v[0] for v in footprint) / n,
                                   sum(v[1] for v in footprint) / n, eave])
                if np.dot(normal, tri[0] - center) < 0:
                    tri = tri[[1, 0, 2]]
                    normal = -normal
                parts.append(_mesh(tri, np.repeat(normal[None], 3, 0), _rgba(wall, 3),
                                   np.zeros((3, 2)), [0, 1, 2]))
    # two roof slabs (12 cm thick) over the overhang-expanded outline
    big = _offset_convex(footprint, overhang)
    for keep_left in (True, False):
        half = _clip_halfplane(big, ext, ext_b, keep_left)
        if len(half) < 3:
            continue
        tris = triangulate_polygon(half)
        top = np.array([[x, y, apex - slope * dist((x, y)) + 6.0] for x, y in half],
                       np.float32)
        idx = np.array(tris, np.uint32).reshape(-1)
        if _face_normal(top, idx)[2] < 0:  # orient the slab's top face upward
            idx = idx.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
        normal = _face_normal(top, idx)  # from the winding: this slope's own normal
        roof_col = _rgba(roof, len(top))
        roof_col[:, :3] *= np.random.default_rng(len(half)).uniform(0.94, 1.04, (len(top), 1))
        roof_parts.append(_mesh(top, np.repeat(normal[None], len(top), 0), roof_col,
                                np.zeros((len(top), 2)), idx))
        under = top - np.array([0, 0, 12.0], np.float32)
        roof_parts.append(_mesh(under, np.repeat(-normal[None], len(top), 0),
                                _rgba("#6b4a35", len(top)), np.zeros((len(top), 2)),
                                idx.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)))
    roof_parts.append(translated(cap, 0.0, 0.0, cap_z))
    return MeshData.concat(parts), MeshData.concat(roof_parts)


def polyline_posts_and_pickets(points: Sequence[Point], height: float, wood: str = "#a0744a",
                               spacing: float = 200.0, picket: float = 12.0) -> MeshData:
    """A wooden picket fence along a polyline: posts every ≤ 2 m, two rails, pickets.

    The posts are the top (= ``height``); pickets stop 0.3–4 cm below them.
    """
    parts = []
    for (x1, y1), (x2, y2) in zip(points[:-1], points[1:], strict=True):
        seg = math.hypot(x2 - x1, y2 - y1)
        if seg < 1:
            continue
        ux, uy = (x2 - x1) / seg, (y2 - y1) / seg
        ang = math.degrees(math.atan2(uy, ux))
        nposts = max(2, int(math.ceil(seg / spacing)) + 1)
        for i in range(nposts):
            t = seg * i / (nposts - 1)
            parts.append(box(x1 + ux * t, y1 + uy * t, 0, 9, 9, height, "#7c5a3a", ang))
        for z in (height * 0.25, height * 0.75):
            parts.append(box((x1 + x2) / 2, (y1 + y2) / 2, z, seg, 4, 6, "#8a6542", ang))
        npick = int(seg / picket)
        for i in range(npick):
            t = (i + 0.5) * picket
            jitter = (i * 7919 % 13) / 13.0 * 4.0
            parts.append(box(x1 + ux * t, y1 + uy * t, 2, picket * 0.62, 2.2,
                             height - 6 + jitter, wood, ang))
    return MeshData.concat(parts)


def stone_wall(points: Sequence[Point], height: float, thickness: float = 30.0) -> MeshData:
    """Wall body plus a coping cap; the cap's top is ``height``."""
    cap = min(8.0, height * 0.2)
    parts = []
    for (x1, y1), (x2, y2) in zip(points[:-1], points[1:], strict=True):
        seg = math.hypot(x2 - x1, y2 - y1)
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        parts.append(box((x1 + x2) / 2, (y1 + y2) / 2, 0, seg, thickness, height - cap, "#9b9384",
                         ang))
        parts.append(box((x1 + x2) / 2, (y1 + y2) / 2, height - cap, seg + 6, thickness + 8, cap,
                         "#bdb5a5", ang))
    return MeshData.concat(parts)


def hedge(footprint: Polygon, height: float, seed: int) -> MeshData:
    """A clipped hedge: dark core prism + a leafy shell on top and sides."""
    rng = np.random.default_rng(seed)
    core = prism(footprint, height * 0.94, 0.0, "#1f4a26")
    xs = [p[0] for p in footprint]
    ys = [p[1] for p in footprint]
    w, d = max(xs) - min(xs), max(ys) - min(ys)
    area = 2 * (w + d) * height + w * d
    n = int(np.clip(area / 30.0, 200, 6000))
    u = rng.random(n)
    pts = np.zeros((n, 3))
    out = np.zeros((n, 3))
    top_share = (w * d) / area
    top = u < top_share
    pts[top] = np.stack([rng.uniform(min(xs), max(xs), top.sum()),
                         rng.uniform(min(ys), max(ys), top.sum()),
                         np.full(top.sum(), height * 0.97)], 1)
    out[top] = [0, 0, 1]
    side = ~top
    m = side.sum()
    face = rng.integers(0, 4, m)
    sx = np.where(face == 0, min(xs), np.where(face == 1, max(xs), rng.uniform(min(xs), max(xs), m)))
    sy = np.where(face == 2, min(ys), np.where(face == 3, max(ys), rng.uniform(min(ys), max(ys), m)))
    # a 9 cm leaf can point straight down: root it ≥ 9.5 cm up so none sinks into the ground
    pts[side] = np.stack([sx, sy, np.maximum(rng.uniform(0.05, 0.95, m) * height, 9.5)], 1)
    out[side] = np.stack([np.where(face == 0, -1, np.where(face == 1, 1, 0)),
                          np.where(face == 2, -1, np.where(face == 3, 1, 0)), np.zeros(m)], 1)
    cols = _palette_colors("dark", np.clip(pts[:, 2] / height, 0, 1) * 0.7 + 0.2, rng)
    foliage = leaves(pts.astype(np.float32), out.astype(np.float32), np.full(n, 9.0),
                     np.full(n, 6.0), cols, rng, spherize=0.0, droop=0.0)
    # the leaf shell pokes a few cm above the clipped top: the fit makes the top the data
    return fit_height(MeshData.concat([core, foliage]), height)


def raised_bed(footprint: Polygon, height: float) -> MeshData:
    """Plank sides, soil top just below the rim."""
    wood = prism(footprint, height, 0.0, "#9a6b3f", top="#4a3222")
    return wood


def pergola(footprint: Polygon, height: float) -> MeshData:
    """Four posts, two beams, and rafters ON the beams; the rafters' top is ``height``."""
    xs = [p[0] for p in footprint]
    ys = [p[1] for p in footprint]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    rafter, beam = 12.0, 18.0
    deck = height - rafter  # top of posts and beams = underside of the rafters
    parts = []
    for px in (x0 + 8, x1 - 8):
        for py in (y0 + 8, y1 - 8):
            parts.append(box(px, py, 0, 12, 12, deck, "#8b6a48"))
    for py in (y0 + 8, y1 - 8):
        parts.append(box((x0 + x1) / 2, py, deck - beam, x1 - x0 + 40, 8, beam, "#7d5d3e"))
    n = int((x1 - x0) / 32)
    for i in range(n + 1):
        px = x0 + i * (x1 - x0) / max(n, 1)
        parts.append(box(px, (y0 + y1) / 2, deck, 6, y1 - y0 + 50, rafter, "#94714d"))
    return MeshData.concat(parts)


def greenhouse(footprint: Polygon, height: float) -> tuple[MeshData, MeshData]:
    """(frame, glass): aluminium edges + glass walls and a pitched glass roof.

    The ridge beam's top is ``height``; each roof pane is wound so its winding
    normal points up and out, and stores exactly that normal.
    """
    xs = [p[0] for p in footprint]
    ys = [p[1] for p in footprint]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    eave = height * 0.7
    ridge_x = (x0 + x1) / 2
    beam = cylinder((ridge_x, y0, 0.0), (ridge_x, y1, 0.0), 3, 3, "#d9dde0", 6)
    ridge = height - float(beam.positions[:, 2].max())  # beam axis: its top IS the height
    frame = [translated(beam, 0.0, 0.0, ridge)]
    for px in (x0, x1):
        for py in (y0, y1):
            frame.append(box(px, py, 0, 5, 5, eave, "#d9dde0"))
    for py in np.linspace(y0, y1, 5):
        frame.append(cylinder((x0, py, eave), (ridge_x, py, ridge), 2, 2, "#d9dde0", 5))
        frame.append(cylinder((x1, py, eave), (ridge_x, py, ridge), 2, 2, "#d9dde0", 5))
    glass = [prism(footprint, eave, 0.0, "#cfe6ef")]
    for ex in (x0, x1):
        quad = np.array([[ex, y0, eave], [ex, y1, eave], [ridge_x, y1, ridge],
                         [ridge_x, y0, ridge]], np.float32)
        idx = [0, 1, 2, 0, 2, 3]
        if _face_normal(quad, idx)[2] < 0:  # the pane faces the sky, not the floor
            idx = [0, 2, 1, 0, 3, 2]
        nrm = _face_normal(quad, idx)
        glass.append(_mesh(quad, np.repeat(nrm[None], 4, 0), _rgba("#cfe6ef", 4),
                           np.zeros((4, 2)), idx))
    return MeshData.concat(frame), MeshData.concat(glass)


def table(cx: float, cy: float, w: float, d: float, h: float = 75.0) -> MeshData:
    parts = [box(cx, cy, h - 4, w, d, 4, "#a77a4f")]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box(cx + sx * (w / 2 - 6), cy + sy * (d / 2 - 6), 0, 5, 5, h - 4,
                             "#7a5636"))
    return MeshData.concat(parts)


def chair(cx: float, cy: float, facing_deg: float, height: float = 85.0) -> MeshData:
    """Seat at ≤ 44 cm, the backrest's top is ``height``."""
    a = math.radians(facing_deg)
    bx, by = cx - math.cos(a) * 18, cy - math.sin(a) * 18
    seat = min(44.0, height * 0.5)
    parts = [box(cx, cy, seat, 42, 42, 4, "#b98a5a", facing_deg)]
    parts.append(box(bx, by, seat + 4, 4, 40, max(height - seat - 4, 1.0), "#a87a4c", facing_deg))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box(cx + sx * 17, cy + sy * 17, 0, 4, 4, seat, "#6e4e30"))
    return MeshData.concat(parts)


def bench(cx: float, cy: float, w: float, d: float, height: float = 85.0) -> MeshData:
    """Seat at ≤ 42 cm, the backrest's top is ``height``."""
    seat = min(42.0, height * 0.5)
    parts = [box(cx, cy, seat, w, d * 0.8, 5, "#b0835a"),
             box(cx, cy + d * 0.4, seat + 5, w, 4, max(height - seat - 5, 1.0), "#a07650")]
    for sx in (-1, 1):
        parts.append(box(cx + sx * (w / 2 - 10), cy, 0, 6, d * 0.8, seat, "#5b5b5b"))
    return MeshData.concat(parts)


# the 2D trampoline sprite's jumping mat: scripts/generate_object_sprites.py
# MATERIALS["rubber"]["mid"] (the literal #1d2126 was in no 2D table and below the
# §2 albedo floor of ~40)
TRAMPOLINE_MAT = "#303336"


def trampoline(cx: float, cy: float, r: float, height: float = 90.0) -> MeshData:
    """Frame ring on six legs; the ring tube's top is ``height``."""
    th = np.linspace(0, 2 * math.pi, 24, endpoint=False)
    ring_a = np.stack([cx + np.cos(th) * r, cy + np.sin(th) * r, np.zeros(24)], 1)
    ring_b = np.roll(ring_a, -1, axis=0)
    frame = tubes(ring_a, ring_b, np.full(24, 3.5), np.full(24, 3.5), "#3b6fb6", 6)
    ring_z = height - float(frame.positions[:, 2].max())
    frame = translated(frame, 0.0, 0.0, ring_z)
    legs = tubes(ring_a[::4], ring_a[::4] + [0, 0, ring_z], np.full(6, 2.5), np.full(6, 2.5),
                 "#6f7782", 6)
    mat_fp = [(cx + math.cos(t) * r * 0.9, cy + math.sin(t) * r * 0.9) for t in th]
    mat = prism(mat_fp, 1.0, ring_z - 2.0, TRAMPOLINE_MAT)
    return MeshData.concat([frame, legs, mat])


def bbq_grill(cx: float, cy: float, r: float, height: float = 90.0) -> MeshData:
    """Kettle grill on three legs; the lid's top is ``height`` (the kettle stays in the footprint)."""
    squash = 0.8
    zc = height - r * squash  # the smooth sphere's pole is its top vertex
    kettle = spheres(np.array([[cx, cy, zc]]), r, "#2a2a2e", squash=squash, smooth=True)
    feet = np.array([[cx + r * 0.5, cy, 0.0], [cx - r * 0.27, cy + r * 0.43, 0.0],
                     [cx - r * 0.27, cy - r * 0.43, 0.0]], np.float32)
    legs = tubes(feet, np.array([[cx, cy, zc]] * 3, np.float32), np.full(3, 1.5), np.full(3, 1.5),
                 "#3b3b3b", 5)
    return MeshData.concat([kettle, legs])


def bird_bath(cx: float, cy: float, r: float, height: float = 90.0) -> MeshData:
    """Pedestal + basin; the basin's rim is ``height`` and its radius the item's radius.

    (The L0 board drew the basin at 1.6× the item radius — wider than the
    plan's footprint.)
    """
    basin = min(12.0, height * 0.3)
    pedestal = cylinder((cx, cy, 0.0), (cx, cy, height - basin), r * 0.32, r * 0.24, "#c9c1b2")
    bowl = translated(round_thing(cx, cy, r, basin, "#d6cfc2", "#7fb3c8"), 0.0, 0.0, height - basin)
    return MeshData.concat([pedestal, bowl])


def round_thing(cx: float, cy: float, r: float, h: float, color: str, top: str | None = None) -> MeshData:
    th = np.linspace(0, 2 * math.pi, 20, endpoint=False)
    fp = [(cx + math.cos(t) * r, cy + math.sin(t) * r) for t in th]
    return prism(fp, h, 0.0, color, top)


WATER_ALBEDO = "#4d92c5"  # linear mean of resources/textures/water.png (hue 205.5°)


def water_surface(footprint: Polygon, z: float = 2.0) -> MeshData:
    tris = triangulate_polygon(footprint)
    pos = np.array([[x, y, z] for x, y in footprint], np.float32)
    idx = np.array(tris, np.uint32).reshape(-1)
    a, b, c = pos[idx[0]], pos[idx[1]], pos[idx[2]]
    if np.cross(b - a, c - a)[2] < 0:
        idx = idx.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
    # the engine's water material carries the colour (the same WATER_ALBEDO, set
    # once by the runner); the vertices keep it too, so the data never disagrees
    return _mesh(pos, np.tile([0, 0, 1.0], (len(pos), 1)), _rgba(WATER_ALBEDO, len(pos)),
                 np.zeros((len(pos), 2)), idx)


def ground_quad(x0: float, y0: float, x1: float, y1: float, z: float = 0.0) -> MeshData:
    """A textured ground rectangle; uv maps (x0,y1)→(0,0) top-left (north-up image)."""
    pos = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]], np.float32)
    uv = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float32)
    return _mesh(pos, np.tile([0, 0, 1.0], (4, 1)), _rgba("#ffffff", 4), uv, [0, 1, 2, 0, 2, 3])
