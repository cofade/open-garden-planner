"""Plant v0 — one readable silhouette per sprite archetype (Phase 17 L1.7, #385).

``build_plant`` is the pipeline's builder for the plant kinds (``TREE``,
``SHRUB``, ``PERENNIAL``): a pure function of one ``Record`` that returns the
plant's meshes in the item-local frame. What it builds is decided by the SAME
recipe the 2D sprite is drawn from (``core/plant_art``, resolved by the same
rule), and how big it is by the plan:

- **archetype** — ``recipe["a"]``: canopy, conifer, mound, climber, ground, hedge,
  rosette, head, grass, allium, feathery, flower, palm. Every archetype of the
  tables has a builder here (``ARCHETYPE_BUILDERS``; pinned by a test, so a new
  2D archetype cannot silently fall back to another one's shape);
- **colours** — only the recipe's palette for foliage, in linear light; wood is
  the 2D BARK fill texture's mean colour (the plant tables hold no wood colour:
  a top-down sprite never shows a trunk);
- **size** — the record's ``height_cm`` and canopy radius. The archetype
  builders build TO those numbers: every one places its highest point at the
  height, its outline on the canopy circle, and keeps its leaves inside by
  turning them — a plant is never built too tall and squashed back. ``_fit``
  then normalises the last millimetre (the bounding box IS the data: top = the
  height, widest span = the canopy diameter, base at z = 0), ends by holding
  every foliage vertex within ``REACH_MAX`` canopy radii of the axis — so where
  a plant's foliage ends is bounded by construction, whatever a builder hands
  over (wood: by the trunk builders' radii) — and REPORTS
  what it had to repair (``FitReport``, ``fit_report``), so tests hold the
  builders to it. The 2D tables' tuning numbers (``leaf_scale``, ``n_out``) are
  read here too: retuning a sprite moves the 3D leaf count and size of that
  species.

v0 is deliberately cheap: a few soft volumes and a shell of large geometric
leaves, at most ``TRIANGLE_BUDGET`` triangles per plant — bounded per ARCHETYPE
and by construction (counts are clipped functions of recipe numbers, never of
the plant's size). It makes no seasonal claim: no fruit, no flowers, no flower
heads (the season gates arrive with Package L3), and a crown is never bare.
Species-accurate models are Package L3 ("Plant Forge", #387).

A shape is built once per (recipe form, seed, proportion step) and remembered;
a plant that grows is that shape scaled — a date scrub is a multiplication per
plant, not a rebuild (``PROPORTION_STEP``, ``SHAPE_CACHE_BYTES``).

A plant the plan gives NO height (``height_cm is None``: no species data, no
measurement) is not guessed: it gets the placeholder — a low, smooth, neutral
dome over its canopy circle that casts no shadow, as it casts none in 2D.

Conventions the engine relies on (``ogp-3d-renderer`` §3): vertex colours are
linear; in the foliage part ``uv.x`` is the wind sway weight (0 at the ground,
1 at the plant's top) and ``uv.y`` the sway phase in [0, 1); wood does not sway.
Foliage normals are bent toward the crown's heart so a crown shades as one soft
volume (``ogp-lush-cinematic`` §2). Randomness is ``Generator.random`` only,
seeded from ``item_seed(record.params["seed"], "plant")``.

Qt-free: numpy, ``core.plant_art`` and the scene3d package.
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Final, NamedTuple, TypeAlias

import numpy as np
from numpy.typing import NDArray

from open_garden_planner.core.plant_art import (
    FLOWERS,
    PALETTES,
    PLANT_KINDS,
    SpriteRef,
    has_recipe,
    palette_key,
    recipe_for,
    resolve_sprite,
)
from open_garden_planner.core.scene3d import (
    MAX_LENGTH_CM,
    PARAM_PLANT_CATEGORY,
    PARAM_RADIUS_CM,
    PARAM_SEED,
    PARAM_SPRITE_SPECIES,
    BuilderRegistry,
    Mesh,
    MeshPart,
    Record,
    default_builder,
    item_seed,
    srgb_to_linear,
)

Floats: TypeAlias = NDArray[np.float64]
Ints: TypeAlias = NDArray[np.int64]

#: Triangles one plant may have — every archetype, every size (the story's gate).
TRIANGLE_BUDGET: Final = 2000
#: No FOLIAGE vertex of a plant is further from its axis than this many canopy
#: radii — by construction: putting whatever foliage is further out onto that
#: circle is the LAST thing ``_fit`` does (``_rein_in``), for any builder and
#: any dice. The story's gate is 1.10 ("no part more than 10 % outside the
#: canopy circle"); the bound sits a step inside it, so float32 and the scale to
#: the plan's size cannot carry a vertex across the gate. It is rarely needed —
#: the builders build inside the circle and the fit's scale moves a leaf tip a
#: few percent at most: ``FitReport.reined_share`` says when it was.
#:
#: That this bounds the whole PLANT rests on one invariant, which is not the
#: fit's but the trunk builders': **foliage is the outermost part.** Wood is a
#: trunk on the plan position, built no wider than 1.45 × 0.22 = 0.32 canopy
#: radii (``_canopy``; a conifer's 0.28, a palm's 0.24), and it is NOT reined in:
#: moving a vertex of a flat-shaded trunk would leave its face with a normal
#: that is no longer its winding normal. The fit's xy scale would have to
#: exceed 3.4 to carry a trunk to the bound (the largest measured: 1.11); the
#: tests hold wood inside ``0.5`` canopy radii for every recipe at every
#: proportion step.
REACH_MAX: Final = 1.09

#: ``MeshPart.name`` values.
PART_WOOD: Final = "wood"
PART_FOLIAGE: Final = "foliage"
PART_PLACEHOLDER: Final = "placeholder"
#: ``plant_archetype`` of a plant the plan gives no height.
PLACEHOLDER: Final = "placeholder"

#: Wood. The 2D plant tables hold no bark colour, so v0 takes the mean colour of
#: the 2D BARK fill texture in linear light (``resources/textures/bark.png``,
#: hue 27.6°) — pinned against the PNG by ``tests/unit/test_scene3d_plants.py``.
BARK_SRGB: Final = "#5d432d"

#: The placeholder: a spherical cap this fraction of the canopy DIAMETER high,
#: never higher than ``PLACEHOLDER_MAX_HEIGHT_CM`` — a marker, not a plant.
PLACEHOLDER_HEIGHT_FRACTION: Final = 0.12
PLACEHOLDER_MAX_HEIGHT_CM: Final = 25.0
#: Its tone: the 2D white (``FLOWERS["white"]``, the petal colour) × this in
#: linear light, sRGB 170 / 167 / 158. The L0 spike's rule for a sun-lit white is
#: × 0.7 (``ogp-lush-cinematic`` §7, the birch trunk — an upright surface); a dome
#: faces the noon sun, and at × 0.7 it rendered at luma 232 through the spike's
#: engine (scratch look, 2026-10-11): unclipped, but the brightest thing in the
#: garden. A marker should not out-shine the plants.
PLACEHOLDER_SHADE: Final = 0.5
_PLACEHOLDER_SIDES: Final = 48

#: How much of its palette's TIP tone an archetype's foliage shows, on average
#: (0 = the base anchors b0/b1, 1 = the tip anchors t0/t1). Measured from the 2D
#: sprites: the tip weight whose mix has the hue of the sprite's rendered
#: foliage, median per archetype over all 123 sprites. It is what keeps the 3D
#: foliage within 10° of the sprite's hue (a palette spans up to 41°). The
#: derivation runs as a test and holds these numbers to its result:
#: ``tests/unit/test_scene3d_plants.py::test_the_tip_weights_are_measured_from_the_sprites``
#: (a ground cover's sprite sits at its palette's base anchors: 0).
FOLIAGE_TIP_WEIGHT: Final[Mapping[str, float]] = MappingProxyType({
    "allium": 0.68,
    "canopy": 0.43,
    "climber": 0.365,
    "conifer": 0.11,
    "feathery": 0.36,
    "flower": 0.225,
    "grass": 0.39,
    "ground": 0.0,
    "head": 0.29,
    "hedge": 0.24,
    "mound": 0.38,
    "palm": 0.505,
    "rosette": 0.31,
})
#: Spread of the tip weight inside one plant: exposure 0 … 1 covers this much of
#: the palette around the archetype's mean.
_TONE_CONTRAST: Final = 0.9
#: Normal bending toward the crown's heart (``ogp-lush-cinematic`` §2: 0.55–0.75).
_SPHERIZE: Final = 0.6
_LEAF_SPHERIZE: Final = 0.7
#: The elements that form a plant's OUTLINE (a rosette's outer leaves, a palm's
#: fronds, an allium's outer blades, a grass tuft's longest blades) reach at
#: least this fraction of the canopy radius and sit within this fraction of an
#: even slot round the axis. A ragged outline cannot fill its canopy circle:
#: with blades of any reach at any angle, the fitted plant left the circle by up
#: to 39 % (feathery; allium 37 %, flower 23 %) — or, scaled back into it,
#: spanned only 72 % of the canopy diameter. Inner elements stay irregular.
_RIM_REACH: Final = 0.97
_RIM_JITTER: Final = 0.10
#: Foliage and the ground, as fractions of the plant's height. A shell leaf grows
#: from at least ``_LEAF_LIFT`` above the ground and no vertex of it comes closer
#: than ``_LEAF_FLOOR``; of a volume that sits on the ground, the triangles lying
#: wholly within ``_GROUND_SKIN`` of it are not built (they are the hidden sole —
#: and, pressed flat at z = 0, they z-fight with the ground: up to 6.7 % of a
#: mound's triangles before this rule).
_LEAF_LIFT: Final = 0.04
_LEAF_FLOOR: Final = 0.015
_GROUND_SKIN: Final = 0.01
#: No shell leaf is longer than this fraction of the canopy RADIUS. A leaf count is
#: fixed by the budget, so leaves grow with the surface they cover — on a plant 40
#: times taller than wide they came out 2.4 radii long. Up to 0.7 radii a leaf can
#: always be turned to lie inside the canopy circle (``_leaves``).
_LEAF_LONGEST: Final = 0.6
#: A blade's width at its tip, as a fraction of its width at the base, and the
#: widest a blade of a tuft is drawn relative to the tuft's width.
_BLADE_TIP: Final = 0.15
_BLADE_WIDEST: Final = 1.2
_TAU: Final = 2.0 * math.pi
_UP: Final[Floats] = np.array([0.0, 0.0, 1.0])


# ── the working mesh ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class _Geo:
    """Geometry before the fit, in centimetres at the plant's real proportions.

    Per vertex: ``exposure`` (0 = deep inside or at the base, 1 = an outer tip —
    it becomes the palette's base → tip mix), ``shade`` (a hue-neutral depth
    darkening), ``tone`` (which of a palette's two anchor pairs: outer 0 … inner
    1) and the wind ``phase``.
    """

    pos: Floats
    nrm: Floats
    tri: Ints
    exposure: Floats
    shade: Floats
    tone: Floats
    phase: Floats


def _geo(pos: Floats, nrm: Floats, tri: Ints, exposure: Floats | float,
         shade: Floats | float, tone: Floats | float, phase: Floats | float) -> _Geo:
    count = len(pos)

    def full(value: Floats | float) -> Floats:
        return np.broadcast_to(np.asarray(value, np.float64), (count,)).copy()

    return _Geo(np.asarray(pos, np.float64).reshape(-1, 3),
                np.asarray(nrm, np.float64).reshape(-1, 3),
                np.asarray(tri, np.int64).reshape(-1, 3),
                full(exposure), full(shade), full(tone), full(phase))


def _join(parts: Sequence[_Geo]) -> _Geo:
    offsets = np.cumsum([0] + [len(part.pos) for part in parts[:-1]])
    return _Geo(
        np.concatenate([part.pos for part in parts]),
        np.concatenate([part.nrm for part in parts]),
        np.concatenate([part.tri + int(offset) for part, offset in zip(parts, offsets, strict=True)]),
        np.concatenate([part.exposure for part in parts]),
        np.concatenate([part.shade for part in parts]),
        np.concatenate([part.tone for part in parts]),
        np.concatenate([part.phase for part in parts]),
    )


def _without_ground_skin(geo: _Geo, skin: float) -> _Geo:
    """``geo`` without the triangles that lie wholly within ``skin`` of the ground,
    and without the vertices only they used."""
    keep = geo.pos[geo.tri][:, :, 2].max(axis=1) > skin
    if bool(keep.all()):
        return geo
    tri = geo.tri[keep]
    used = np.zeros(len(geo.pos), bool)
    used[tri.reshape(-1)] = True
    index = np.cumsum(used) - 1
    return _Geo(geo.pos[used], geo.nrm[used], np.asarray(index[tri], np.int64), geo.exposure[used],
                geo.shade[used], geo.tone[used], geo.phase[used])


class _Dice:
    """The plant's own randomness — uniform numbers only, from one seeded stream.

    The bit generator is named (PCG64), not numpy's default: ``default_rng`` may
    pick another one in a later numpy, and every plant in every plan would change
    its shape. Today the two give the same stream.
    """

    def __init__(self, seed: int) -> None:
        self._rng = np.random.Generator(np.random.PCG64(seed))

    def u(self, low: float, high: float, size: int | tuple[int, ...]) -> Floats:
        return low + (high - low) * self._rng.random(size)

    def uf(self, low: float, high: float) -> float:
        return low + (high - low) * float(self._rng.random())


@dataclass(slots=True)
class _Plan:
    """What an archetype builder is given: the plant's real size, its recipe, its dice."""

    height: float
    radius: float
    recipe: Mapping[str, Any]
    dice: _Dice
    phase: float

    def number(self, key: str, default: float, low: float, high: float) -> float:
        """A recipe number, clipped — a recipe cannot push a count past its budget."""
        value = self.recipe.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            value = default
        return float(min(max(float(value), low), high))

    def flag(self, key: str, default: bool = False) -> bool:
        return bool(self.recipe.get(key, default))

    def leaf_scale(self) -> float:
        """The 2D table's per-species leaf size (0.55 thyme … 1.35 pumpkin)."""
        return self.number("leaf_scale", 1.0, 0.5, 1.5)

    def shell_leaves(self, base: int, default_n_out: float, low: int, high: int) -> int:
        """How many shell leaves: more for a fine-leaved recipe (small ``leaf_scale``,
        large ``n_out``), fewer and larger for a coarse one — coverage stays; clipped."""
        density = self.number("n_out", default_n_out, 1.0, 1000.0) / default_n_out
        count = base * min(max(density, 0.6), 1.5) / self.leaf_scale() ** 2
        return int(min(max(round(count), low), high))


_Shape: TypeAlias = tuple[_Geo | None, _Geo]  # (wood, foliage)
_ArchetypeBuilder: TypeAlias = Callable[[_Plan], _Shape]


# ── primitives (vectorised; no Python loop over vertices) ─────────────────────


def _unit(vectors: Floats) -> Floats:
    norm = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return np.asarray(vectors / np.maximum(norm, 1e-12), np.float64)


def _srgb_to_linear(srgb: Floats) -> Floats:
    """sRGB 0..1 → linear light, vectorised (the pipeline's transfer function,
    ``core.scene3d.srgb_channel_to_linear``; pinned equal by a test)."""
    return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)


def _octasphere(subdivisions: int) -> tuple[Floats, Ints]:
    """A unit sphere from a subdivided octahedron: 32 triangles at 1, 128 at 2."""
    vertices: list[tuple[float, float, float]] = [
        (1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0),
    ]
    faces = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
    for _ in range(subdivisions):
        middles: dict[tuple[int, int], int] = {}

        def middle(i: int, j: int, cache: dict[tuple[int, int], int] = middles) -> int:
            key = (min(i, j), max(i, j))
            if key not in cache:
                x, y, z = (vertices[i][axis] + vertices[j][axis] for axis in range(3))
                length = math.sqrt(x * x + y * y + z * z)
                vertices.append((x / length, y / length, z / length))
                cache[key] = len(vertices) - 1
            return cache[key]

        split = []
        for a, b, c in faces:
            ab, bc, ca = middle(a, b), middle(b, c), middle(c, a)
            split += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = split
    return np.array(vertices, np.float64), np.array(faces, np.int64)


_SPHERE_COARSE: Final = _octasphere(1)   # 18 vertices, 32 triangles
_SPHERE: Final = _octasphere(2)          # 66 vertices, 128 triangles


def _top_out(centers: Floats, radii: Floats, height: float) -> None:
    """Scale the lobes' heights (in place) so the tallest one ends exactly at the
    plant's height: the volumes are the plant's body, and the body is as tall as
    the plan says — not 6 % taller or 12 % shorter by the roll of a die."""
    factor = height / max(float((centers[:, 2] + radii[:, 2]).max()), 1e-12)
    centers[:, 2] *= factor
    radii[:, 2] *= factor


def _lobes(centers: Floats, radii: Floats, heart: Floats, dice: _Dice, phase: float,
           sphere: tuple[Floats, Ints] = _SPHERE, skin: float = 0.0) -> _Geo:
    """Soft ellipsoid volumes — the mass of a crown, a shrub or a cushion.

    A lobe that reaches below the ground sits on it: its vertices there are set
    onto the ground, and the triangles wholly within ``skin`` of the ground —
    its hidden sole — are left out. Normals are the ellipsoid's, bent toward the
    direction away from ``heart``; the further from the heart and the more
    upward a vertex looks, the lighter it is.
    """
    unit_vertices, faces = sphere
    count = len(centers)
    pos = unit_vertices[None, :, :] * radii[:, None, :] + centers[:, None, :]
    own = _unit(unit_vertices[None, :, :] / radii[:, None, :])
    pos[:, :, 2] = np.maximum(pos[:, :, 2], 0.0)
    away = pos - heart[None, None, :]
    distance = np.linalg.norm(away, axis=2)
    depth = np.clip(distance / max(float(distance.max()), 1e-12), 0.0, 1.0)
    nrm = _unit(own * (1.0 - _SPHERIZE) + _unit(away) * _SPHERIZE)
    exposure = 0.10 + 0.40 * depth + 0.25 * (0.5 + 0.5 * own[:, :, 2])
    tone = np.repeat(_stratified(dice, count), len(unit_vertices))
    tri = faces[None, :, :] + (np.arange(count) * len(unit_vertices))[:, None, None]
    return _without_ground_skin(
        _geo(pos.reshape(-1, 3), nrm.reshape(-1, 3), tri.reshape(-1, 3),
             exposure.reshape(-1), (0.62 + 0.38 * depth).reshape(-1), tone, phase), skin)


def _stratified(dice: _Dice, count: int) -> Floats:
    """``count`` tones spread evenly over 0 … 1 in a random order: a handful of
    lobes then still averages the palette's two anchor pairs."""
    order = np.argsort(dice.u(0.0, 1.0, count))
    tones = np.empty(count)
    tones[order] = (np.arange(count) + 0.5) / count
    return tones


def _leaves(dice: _Dice, base: Floats, outward: Floats, length: Floats, aspect: float,
            heart: Floats, phase: float, radius: float, height: float,
            droop: float = 0.15) -> _Geo:
    """Large geometric leaves (a diamond: 4 vertices, 2 triangles) facing ``outward``.

    The shell that breaks a volume's outline. Each leaf lies across its facing
    direction, hangs by ``droop``, and is lightest at its tip.

    A leaf is built INSIDE the plant's size (``radius``, ``height``), never
    squeezed into it afterwards — it is turned, which keeps its size and shape:

    - it grows from at least ``_LEAF_LIFT`` × the height above the ground;
    - a leaf with no room above or below it lies down: its plane is turned about
      its own level line until the leaf, whatever its heading in that plane,
      stays between ``_LEAF_FLOOR`` × the height and the height (on a plant
      60 cm tall and 3.6 m wide, 45 cm leaves lie flat);
    - a leaf whose tip or edge would leave the canopy circle is turned in its
      plane, by quarter turns, to the first heading that keeps it inside — and,
      if none does (a leaf longer than the plant is wide), to the one that
      leaves it least; the fit pulls back what is left and reports it.
    """
    count = len(base)
    length = np.minimum(length, _LEAF_LONGEST * radius)
    base = base.copy()
    base[:, 2] = np.clip(base[:, 2], _LEAF_LIFT * height, height)
    distance = np.hypot(base[:, 0], base[:, 1])
    outside = distance > radius
    base[outside, :2] *= (radius / distance[outside])[:, None]
    facing = _unit(outward + dice.u(-0.35, 0.35, (count, 3)))
    spin = dice.u(-1.0, 1.0, (count, 3))
    along = _unit(spin - (spin * facing).sum(axis=1, keepdims=True) * facing)
    along = _unit(along - np.array([0.0, 0.0, droop]))
    side = _unit(np.cross(along, facing))
    reach = length[:, None]
    half_width = reach * aspect * 0.5
    # ── no room above or below: lie down (turn the leaf's plane toward level) ──
    plane = _unit(np.cross(side, along))                       # the leaf's own normal
    steep = _UP[None, :] - plane[:, 2:3] * plane                # up, projected into the plane
    slope = np.linalg.norm(steep, axis=1)                       # sin of the plane's inclination
    tilted = slope > 1e-9
    steep = np.where(tilted[:, None], steep / np.maximum(slope, 1e-12)[:, None], along)
    level = _unit(np.cross(plane, steep))                       # the plane's level line
    along_level, along_steep = (along * level).sum(axis=1), (along * steep).sum(axis=1)
    side_level, side_steep = (side * level).sum(axis=1), (side * steep).sum(axis=1)
    tall = slope * length                                       # the leaf standing on its tip
    room = np.minimum(height - base[:, 2], base[:, 2] - _LEAF_FLOOR * height)
    with np.errstate(divide="ignore", invalid="ignore"):
        keep = np.minimum(1.0, np.where(tall > 0.0, room / tall, np.inf))
    new_slope = keep * slope
    flat = np.concatenate([steep[:, :2], np.zeros((count, 1))], axis=1)
    lost = np.linalg.norm(flat, axis=1) < 1e-9                  # a vertical plane: any level heading
    flat[lost] = np.cross(_UP[None, :], level[lost])
    steep = (_unit(flat) * np.sqrt(np.maximum(1.0 - new_slope ** 2, 0.0))[:, None]
             + _UP[None, :] * new_slope[:, None])
    along = level * along_level[:, None] + steep * along_steep[:, None]
    side = level * side_level[:, None] + steep * side_steep[:, None]
    # ── a tip or an edge beyond the canopy circle: turn the leaf in its own plane ──
    heading = np.stack([along, side, -along, -side])            # the four quarter turns
    across = np.stack([side, -along, -side, along])
    corners = np.stack([heading * reach, 0.45 * heading * reach + across * half_width,
                        0.45 * heading * reach - across * half_width])     # (3, 4, count, 3)
    far = np.hypot(base[:, 0] + corners[..., 0], base[:, 1] + corners[..., 1]).max(axis=0)
    inside = far <= radius
    turn = np.where(inside.any(axis=0), inside.argmax(axis=0), far.argmin(axis=0))
    each = np.arange(count)
    along, side = heading[turn, each], across[turn, each]
    facing = _unit(np.cross(side, along))
    pos = np.stack([
        base,
        base + along * reach * 0.45 + side * half_width,
        base + along * reach,
        base + along * reach * 0.45 - side * half_width,
    ], axis=1).reshape(-1, 3)
    nrm = _unit(facing * (1.0 - _LEAF_SPHERIZE) + _unit(base - heart[None, :]) * _LEAF_SPHERIZE)
    tri = np.array([[0, 1, 2], [0, 2, 3]], np.int64)[None, :, :] + (
        np.arange(count) * 4)[:, None, None]
    return _geo(pos, np.repeat(nrm, 4, axis=0), tri.reshape(-1, 3),
                np.tile([0.55, 0.80, 1.00, 0.80], count),
                np.repeat(dice.u(0.88, 1.0, count), 4),
                np.repeat(dice.u(0.0, 1.0, count), 4),
                (phase + np.repeat(dice.u(-0.1, 0.1, count), 4)) % 1.0)


def _lobe_surface(origin: Floats, reach: Floats, centers: Floats, radii: Floats
                  ) -> tuple[Floats, Ints]:
    """Where each ray ``origin + t · reach`` leaves the outermost lobe: (t, that
    lobe's index) per ray; t is 0 for a ray that meets no lobe. ``origin`` is one
    point or one per ray. Shell leaves are set on that surface — on an envelope
    instead they were buried where a lobe reached it (bald crown tops in the first
    look through an engine) and hovered in the gaps between lobes."""
    step = reach[:, None, :] / radii[None, :, :]                       # (rays, lobes, 3)
    start = (origin.reshape(-1, 1, 3) - centers[None, :, :]) / radii[None, :, :]
    a = (step * step).sum(axis=2)
    b = 2.0 * (step * start).sum(axis=2)
    c = (start * start).sum(axis=2) - 1.0
    root = b * b - 4.0 * a * c
    far = np.where(root >= 0.0, (-b + np.sqrt(np.maximum(root, 0.0))) / (2.0 * np.maximum(a, 1e-300)), 0.0)
    return (np.asarray(np.maximum(far.max(axis=1), 0.0), np.float64),
            np.asarray(far.argmax(axis=1), np.int64))


def _on_lobes(dice: _Dice, origin: Floats, reach: Floats, centers: Floats, radii: Floats,
              miss: float = 1.0) -> tuple[Floats, Floats]:
    """Points on the lobes' outer surface along the rays (a little in or out, so the
    shell is not a film) and the surface's own normal there. A ray that meets no
    lobe ends at ``miss`` × its reach and keeps its direction.

    The normal is the lobe's, not the ray's: on a flat cushion the surface looks
    up nearly everywhere, and a leaf set by the ray's direction stood on edge —
    45 cm leaves upright on a 60 cm squash, 1.6 times the plant's height.
    """
    start = origin.reshape(-1, 3)
    distance, lobe = _lobe_surface(origin, reach, centers, radii)
    hit = distance > 0.0
    on_surface = start + reach * distance[:, None]
    normal = np.where(hit[:, None], (on_surface - centers[lobe]) / radii[lobe] ** 2, reach)
    distance = np.where(hit, distance, miss) * dice.u(0.96, 1.05, len(reach))
    return np.asarray(start + reach * distance[:, None], np.float64), _unit(normal)


def _shell_points(dice: _Dice, count: int, lowest: float) -> Floats:
    """``count`` unit directions on the part of a sphere above ``lowest`` (z)."""
    z = dice.u(lowest, 1.0, count)
    angle = dice.u(0.0, _TAU, count)
    flat = np.sqrt(np.maximum(1.0 - z * z, 0.0))
    return np.stack([flat * np.cos(angle), flat * np.sin(angle), z], axis=1)


def _ribbons(base: Floats, direction: Floats, reach: Floats, height: Floats, width: Floats,
             segments: int, tone: Floats, phase: Floats, arch: float = 0.0) -> _Geo:
    """Blades: each rises from ``base`` to a tip ``height`` above it and leans
    ``reach`` along its (horizontal) ``direction``, tapering to the tip; ``arch``
    (below 1/3) lets the tip nod. The tip is the blade's highest point, and it is
    ``height`` up — the arch does not shorten it (it used to: blades stopped at
    88 % of the plant's height)."""
    count = len(base)
    f = np.linspace(0.0, 1.0, segments + 1)
    along = np.concatenate([direction, np.zeros((count, 1))], axis=1)
    rise = (f - arch * f ** 3) / (1.0 - arch)
    climb = (1.0 - 3.0 * arch * f ** 2) / (1.0 - arch)
    centre = (base[:, None, :]
              + along[:, None, :] * (reach[:, None] * f[None, :] ** 2)[:, :, None]
              + _UP[None, None, :] * (height[:, None] * rise[None, :])[:, :, None])
    tangent = (along[:, None, :] * (reach[:, None] * 2.0 * f[None, :])[:, :, None]
               + _UP[None, None, :] * (height[:, None] * climb[None, :])[:, :, None])
    side = np.stack([-direction[:, 1], direction[:, 0], np.zeros(count)], axis=1)  # up × direction
    half = (width[:, None] * (1.0 - (1.0 - _BLADE_TIP) * f[None, :]) * 0.5)[:, :, None]
    left = centre + side[:, None, :] * half
    right = centre - side[:, None, :] * half
    face = _unit(np.cross(np.broadcast_to(side[:, None, :], tangent.shape), tangent))
    nrm = _unit(face * 0.7 + _UP[None, None, :] * 0.3)
    pos = np.stack([left, right], axis=2).reshape(count, -1, 3)       # per blade: L0 R0 L1 R1 …
    step = np.arange(segments) * 2
    quad = np.stack([step + 1, step, step + 2, step + 1, step + 2, step + 3], axis=1).reshape(-1, 3)
    tri = quad[None, :, :] + (np.arange(count) * (segments + 1) * 2)[:, None, None]
    per_vertex = (segments + 1) * 2
    return _geo(pos.reshape(-1, 3), np.repeat(nrm, 2, axis=1).reshape(-1, 3), tri.reshape(-1, 3),
                np.tile(np.repeat(f, 2), count),
                np.tile(np.repeat(0.72 + 0.28 * f, 2), count),
                np.repeat(tone, per_vertex), np.repeat(phase, per_vertex))


#: A leaf's outline: its width at evenly spaced cross-sections from base to tip, as
#: fractions of its full width. Broad = a lettuce or cabbage leaf, round at the tip;
#: lance = a frond or a strap leaf, widest low down and pointed.
_BROAD_LEAF: Final[Floats] = np.array([0.18, 0.80, 1.00, 0.74, 0.18])
_LANCE_LEAF: Final[Floats] = np.array([0.25, 0.98, 0.86, 0.58, 0.28, 0.06])
_FROND: Final[Floats] = np.array([0.25, 0.60, 0.98, 0.50, 0.80, 0.35, 0.06])  # notched


def _fronds(base: Floats, tip: Floats, width: Floats, bow: Floats, outline: Floats,
            tone: Floats, phase: Floats, ceiling: float, fold: float = 0.18,
            ripple: float = 0.0) -> _Geo:
    """Leaves with a folded midrib: three vertices across (edge, rib, edge).

    Each runs from ``base`` to ``tip`` with the given ``outline`` and bows up by
    ``bow`` × its length; ``ripple`` waves the edges (a frilly leaf).

    Bow, ripple and fold are heights, and a leaf is as long as the plant is
    WIDE — so each is held to the room the plant has: the bow never lifts the
    leaf above ``ceiling`` (the plant's height), an edge never waves and the rib
    never folds further than half way down to the ground or up to the ceiling.
    On a rosette 30 cm tall and 2.4 m wide the leaves lie nearly flat and the
    inner ring still stands as tall as the plan says (unbounded, the bow alone
    was 48 cm: the plant came out 9 times too tall and was squashed flat).
    """
    count = len(base)
    segments = len(outline) - 1
    f = np.linspace(0.0, 1.0, segments + 1)
    chord = tip - base
    length = np.linalg.norm(chord, axis=1)
    straight = base[:, 2:3] + chord[:, 2:3] * f[None, 1:-1]            # the unbowed leaf's height
    room = ((ceiling - straight) / np.sin(np.pi * f[1:-1])[None, :]).min(axis=1)
    lift = np.maximum(np.minimum(bow * length, room), 0.0)[:, None]
    centre = base[:, None, :] + chord[:, None, :] * f[None, :, None]
    centre[:, :, 2] += lift * np.sin(np.pi * f)[None, :]
    tangent = np.broadcast_to(chord[:, None, :], centre.shape).copy()
    tangent[:, :, 2] += lift * np.pi * np.cos(np.pi * f)[None, :]
    side = np.stack([-chord[:, 1], chord[:, 0], np.zeros(count)], axis=1)          # up × chord
    flat = np.linalg.norm(side, axis=1) < 1e-9 * np.maximum(length, 1e-12)
    side[flat] = [1.0, 0.0, 0.0]
    side = _unit(side)[:, None, :]
    face = _unit(np.cross(tangent, np.broadcast_to(side, tangent.shape)))          # the upper side
    half = (width[:, None] * outline[None, :] * 0.5)[:, :, None]
    grown = np.minimum(1.0, 3.0 * f)   # a leaf leaves its stem flat: ripple and fold grow in
    up_room = np.maximum(ceiling - centre[:, :, 2], 0.0)
    down_room = 0.5 * np.maximum(centre[:, :, 2], 0.0)
    swing = np.minimum(ripple * grown[None, :] * half[:, :, 0], np.minimum(up_room, down_room))
    wave = (swing * np.sin(3.0 * np.pi * f[None, :] + _TAU * tone[:, None]))[:, :, None]
    left = centre + side * half + _UP[None, None, :] * wave
    right = centre - side * half - _UP[None, None, :] * wave
    with np.errstate(divide="ignore", invalid="ignore"):
        deepest = np.where(face[:, :, 2] > 0.0, down_room / face[:, :, 2],
                           np.where(face[:, :, 2] < 0.0, up_room / -face[:, :, 2], np.inf))
    depth = np.minimum(2.0 * fold * half[:, :, 0] * grown[None, :], deepest)[:, :, None]
    rib = centre - face * depth
    pos = np.stack([left, rib, right], axis=2).reshape(count, -1, 3)   # per leaf: L0 M0 R0 L1 …
    lean = depth / np.maximum(half, 1e-12)                             # 2 × fold where there is room
    nrm = np.stack([_unit(face - side * lean), face, _unit(face + side * lean)], axis=2)
    step = np.arange(segments) * 3
    quad = np.stack([
        step + 1, step + 3, step,          # rib, next edge, edge
        step + 1, step + 4, step + 3,      # rib, next rib, next edge
        step + 2, step + 4, step + 1,      # other edge, next rib, rib
        step + 2, step + 5, step + 4,      # other edge, next other edge, next rib
    ], axis=1).reshape(-1, 3)
    tri = quad[None, :, :] + (np.arange(count) * (segments + 1) * 3)[:, None, None]
    exposure = np.stack([0.35 + 0.65 * f, 0.20 + 0.65 * f, 0.35 + 0.65 * f], axis=1).reshape(-1)
    per_vertex = (segments + 1) * 3
    return _geo(pos.reshape(-1, 3), nrm.reshape(-1, 3), tri.reshape(-1, 3),
                np.tile(exposure, count), np.tile(np.repeat(0.78 + 0.22 * f, 3), count),
                np.repeat(tone, per_vertex), np.repeat(phase, per_vertex))


def _revolve(radius: Floats, z: Floats, sides: int, apex: float | None = None,
             underside: float | None = None) -> tuple[Floats, Ints]:
    """A surface of revolution about the plant's axis: rings bottom to top.

    ``radius`` and ``z`` are per ring (m,) or per ring and side (m, sides) — a
    star rim is a ring whose radius alternates. ``apex`` closes the top with a
    point at that height, ``underside`` the bottom with one (facing down).
    Vertices: the rings (ring-major), then the apex, then the underside point.
    """
    rings = len(radius)
    angle = _TAU * np.arange(sides) / sides
    r = np.broadcast_to(np.asarray(radius, np.float64).reshape(rings, -1), (rings, sides))
    height = np.broadcast_to(np.asarray(z, np.float64).reshape(rings, -1), (rings, sides))
    pos = np.stack([r * np.cos(angle)[None, :], r * np.sin(angle)[None, :], height], axis=2)
    vertices = [pos.reshape(-1, 3)]
    j = np.arange(sides)
    k = (j + 1) % sides
    i = np.arange(rings - 1)[:, None] * sides
    a, b, c, e = i + j[None, :], i + k[None, :], i + sides + k[None, :], i + sides + j[None, :]
    faces = [np.stack([a, b, c], axis=2).reshape(-1, 3), np.stack([a, c, e], axis=2).reshape(-1, 3)]
    extra = rings * sides
    if apex is not None:
        top = (rings - 1) * sides
        vertices.append(np.array([[0.0, 0.0, apex]]))
        faces.append(np.stack([top + j, top + k, np.full(sides, extra)], axis=1))
        extra += 1
    if underside is not None:
        vertices.append(np.array([[0.0, 0.0, underside]]))
        faces.append(np.stack([k, j, np.full(sides, extra)], axis=1))
    return np.concatenate(vertices), np.concatenate(faces).astype(np.int64)


def _smooth_normals(pos: Floats, tri: Ints) -> Floats:
    """Area-weighted vertex normals of a triangle soup."""
    cross = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    flat = tri.reshape(-1)
    summed = np.stack([
        np.bincount(flat, weights=np.repeat(cross[:, axis], 3), minlength=len(pos))
        for axis in range(3)
    ], axis=1)
    return _unit(np.asarray(summed, np.float64))


def _vertex_areas(pos: Floats, tri: Ints) -> Floats:
    """The surface area each vertex stands for (a third of its triangles')."""
    cross = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    area = 0.5 * np.linalg.norm(cross, axis=1)
    return np.asarray(np.bincount(tri.reshape(-1), weights=np.repeat(area / 3.0, 3),
                                  minlength=len(pos)), np.float64)


def _trunk(top: float, radius: float, taper: tuple[float, float, float, float],
           sides: int = 8) -> _Geo:
    """A tapered trunk with a root flare, open at the top (it ends inside the crown).

    ``taper``: radius at the ground, above the flare, half way up and at the top,
    as fractions of ``radius``.
    """
    z = np.array([0.0, 0.06, 0.5, 1.0]) * top
    pos, tri = _revolve(np.array(taper) * radius, z, sides)
    return _geo(pos, _smooth_normals(pos, tri), tri, 0.0, 1.0, 0.0, 0.0)


def _lumps(dice: _Dice, amount: float) -> Callable[[Floats], Floats]:
    """A smooth closed curve round the axis, between ``1 - amount`` and 1: two low
    harmonics with a random weight and random phases. Returns curve(angle)."""
    weight, first, second = dice.uf(0.3, 0.7), dice.uf(0.0, _TAU), dice.uf(0.0, _TAU)

    def at(angle: Floats) -> Floats:
        wave = weight * np.sin(2.0 * angle + first) + (1.0 - weight) * np.sin(3.0 * angle + second)
        return np.asarray(1.0 - amount * (0.5 + 0.5 * wave), np.float64)

    return at


def _even_angles(dice: _Dice, count: int, jitter: float) -> Floats:
    """``count`` directions round the axis, one per equal slot, each off its slot's
    middle by at most ``jitter`` slots; the whole ring turned at random."""
    return dice.uf(0.0, _TAU) + _TAU * (np.arange(count) + dice.u(-jitter, jitter, count)) / count


# ── the archetypes ────────────────────────────────────────────────────────────


def _canopy(p: _Plan) -> _Shape:
    """A deciduous tree: a tapered trunk and a crown of seven soft lobes in a leaf shell."""
    h, r, d = p.height, p.radius, p.dice
    base = h * d.uf(0.21, 0.33)          # where the crown starts: no two trees alike
    half = (h - base) / 2.0
    heart = np.array([0.0, 0.0, base + half])
    # five lobes round the crown, each reaching the canopy circle on its own side:
    # together they are the crown's outline (the leaf shell sits on them)
    ring = _even_angles(d, 5, _RIM_JITTER)
    out = r * d.u(0.30, 0.40, 5)
    wide = r * d.u(_RIM_REACH, 1.0, 5) - out
    # the top lobe ends exactly at the tree's height (its thickness is rolled, its top is not)
    top_deep = half * d.uf(0.50, 0.64)
    centers = np.concatenate([
        np.stack([out * np.cos(ring), out * np.sin(ring),
                  heart[2] + half * d.u(-0.38, 0.16, 5)], axis=1),
        np.array([[r * d.uf(-0.08, 0.08), r * d.uf(-0.08, 0.08), h - top_deep],
                  [0.0, 0.0, heart[2] - 0.30 * half]]),
    ])
    top = r * d.uf(0.56, 0.66)
    radii = np.concatenate([
        np.stack([wide, wide, half * d.u(0.55, 0.72, 5)], axis=1),
        np.array([[top, top, top_deep], [0.62 * r, 0.62 * r, 0.62 * half]]),
    ])
    lobes = _lobes(centers, radii, heart, d, p.phase, skin=_GROUND_SKIN * h)
    count = p.shell_leaves(300, 18.0, 160, 480)
    direction = _shell_points(d, count, -0.55)
    shell, normal = _on_lobes(d, heart, direction * np.array([r, r, half])[None, :], centers, radii)
    size = 0.265 * p.leaf_scale() * math.sqrt(r * max(r, half))
    leaves = _leaves(d, shell, normal + np.array([0.0, 0.0, 0.25]),
                     size * d.u(0.8, 1.25, count), 0.75 if p.flag("frilly") else 0.6,
                     heart, p.phase, r, h)
    trunk = _trunk(base + 0.35 * half, min(0.035 * h, 0.22 * r), (1.45, 1.0, 0.86, 0.62))
    return trunk, _join([lobes, leaves])


def _conifer(p: _Plan) -> _Shape:
    """A conifer: a short trunk and a stack of star-rimmed cone tiers, narrowing to a leader.

    The 2D sprite is four interleaved whorls of 14, 12, 10 and 8 serrated sprays
    seen from above; here the whorls are tiers, three to six by the tree's proportions.
    """
    h, r, d = p.height, p.radius, p.dice
    most = 6
    tiers = int(min(max(round(2.0 + 1.6 * h / (2.0 * r)), 3), most))
    foot = 0.10 * h
    step = (h - foot) / tiers
    # no two conifers alike: each whorl sits a little higher or lower, reaches a
    # little less far, is cut a little deeper, hangs a little more and is turned
    # — except the lowest, which is the outline. The dice of ALL six possible
    # whorls are rolled, whether this tree has them or not: how many it has
    # depends on its proportions, and a conifer that grows a fourth whorl must
    # keep the three it had (rolled per whorl built, every later number moved up
    # the stream and the tree became another tree at each such step).
    sits, reaches, cuts = d.u(-0.18, 0.18, most), d.u(0.84, 1.0, most), d.u(0.52, 0.70, most)
    hangs, turns = d.u(0.05, 0.18, most), d.u(0.0, _TAU, most)
    parts: list[_Geo] = []
    for tier in range(tiers):
        points = max(14 - 2 * tier, 8)
        sides = 2 * points
        z0 = foot + step * (tier + (0.0 if tier == 0 else float(sits[tier])))
        reach = r * (1.0 - 0.84 * tier / tiers) ** 0.9 * (1.0 if tier == 0 else float(reaches[tier]))
        tip = np.arange(sides) % 2 == 0
        last = tier == tiers - 1
        tier_height = (h - z0) if last else 1.55 * step
        rim = np.where(tip, reach, float(cuts[tier]) * reach)
        hang = float(hangs[tier])
        rings_r = np.stack([rim, np.where(tip, 0.60, 0.50) * reach, np.full(sides, 0.20 * reach)])
        rings_z = np.stack([
            z0 + np.where(tip, -hang, 0.10) * step,
            np.full(sides, z0 + 0.42 * tier_height),
            np.full(sides, z0 + (0.80 if last else 1.0) * tier_height),
        ])
        pos, tri = _revolve(rings_r, rings_z, sides, apex=h if last else None,
                            underside=z0 + 0.22 * step)
        cos, sin = math.cos(float(turns[tier])), math.sin(float(turns[tier]))
        pos[:, :2] = pos[:, :2] @ np.array([[cos, sin], [-sin, cos]])
        flat = pos[:, :2]
        outward = np.concatenate([flat, 0.45 * np.linalg.norm(flat, axis=1, keepdims=True)], axis=1)
        nrm = _unit(_smooth_normals(pos, tri) * 0.5 + _unit(outward + [0.0, 0.0, 1e-9]) * 0.5)
        nrm[-1] = [0.0, 0.0, -1.0]   # the underside's centre looks down
        exposure = np.concatenate([np.where(tip, 1.0, 0.60), np.full(sides, 0.50),
                                   np.full(sides, 0.25), [0.9] if last else [], [0.0]])
        shade = np.concatenate([np.full(sides, 1.0), np.full(sides, 0.90), np.full(sides, 0.74),
                                [1.0] if last else [], [0.62]])
        parts.append(_geo(pos, nrm, tri, exposure, shade, (tier + 0.5) / tiers, p.phase))
    # the trunk ends inside the top whorls, tapered to a twig: a thicker one poked
    # out above the leader as a bare stub (the L0 spike's spruce)
    trunk = _trunk(0.88 * h, min(0.02 * h, 0.2 * r), (1.4, 1.0, 0.55, 0.12))
    return trunk, _join(parts)


def _dome(p: _Plan, centers: Floats, radii: Floats, sphere: tuple[Floats, Ints], leaf_base: int,
          default_n_out: float, most: int, heart: Floats, envelope: Floats, lowest: float,
          size: float) -> _Geo:
    """Lobes sitting on the ground plus a leaf shell on their surface, cast from
    ``heart`` in the directions of the ellipsoid ``envelope`` above ``lowest``."""
    d = p.dice
    _top_out(centers, radii, p.height)
    lobes = _lobes(centers, radii, heart, d, p.phase, sphere, skin=_GROUND_SKIN * p.height)
    count = p.shell_leaves(leaf_base, default_n_out, 150, most)
    direction = _shell_points(d, count, lowest)
    shell, normal = _on_lobes(d, heart, direction * envelope[None, :], centers, radii)
    narrow, frilly = p.flag("narrow"), p.flag("frilly")
    length = size * p.leaf_scale() * (1.25 if narrow else 1.0) * d.u(0.8, 1.25, count)
    leaves = _leaves(d, shell, normal + np.array([0.0, 0.0, 0.35]), length,
                     0.30 if narrow else 0.80 if frilly else 0.60, heart, p.phase,
                     p.radius, p.height, droop=-0.25 if narrow else 0.15)
    return _join([lobes, leaves])


def _mound(p: _Plan) -> _Shape:
    """A shrub, a bushy perennial, a herb: six lobes sitting on the ground in a leaf shell.

    It leans: the lobes on one side — a different side per plant — are up to 40 %
    taller, and the top sits off-centre toward them. Without the lean two cushions
    of one size were 97 % alike from the side.
    """
    h, r, d = p.height, p.radius, p.dice
    heart = np.array([0.0, 0.0, 0.30 * h])
    # five lobes round the plant, each reaching the canopy circle on its own side
    ring = _even_angles(d, 5, _RIM_JITTER)
    out = r * d.u(0.28, 0.38, 5)
    wide = r * d.u(_RIM_REACH, 1.0, 5) - out
    toward = d.uf(0.0, _TAU)
    taller = 1.0 + d.uf(0.15, 0.40) * np.cos(ring - toward)
    off = r * d.uf(0.05, 0.18)
    centers = np.concatenate([
        np.stack([out * np.cos(ring), out * np.sin(ring), h * d.u(0.16, 0.36, 5) * taller], axis=1),
        np.array([[off * math.cos(toward), off * math.sin(toward), h * d.uf(0.42, 0.50)]]),
    ])
    core = r * d.uf(0.52, 0.78)
    radii = np.concatenate([
        np.stack([wide, wide, h * d.u(0.28, 0.50, 5) * taller], axis=1),
        np.array([[core, core, h * d.uf(0.48, 0.56)]]),
    ])
    size = 0.27 * math.sqrt(r * max(r, 0.62 * h))
    return None, _dome(p, centers, radii, _SPHERE, 300, 16.0, 420, heart,
                       np.array([r, r, 0.70 * h]), -0.30, size)


def _climber(p: _Plan) -> _Shape:
    """A climber without its support: six lobes on a helix — a leafy pillar when the
    plan makes it tall, a sprawling mat when it makes it wide — with tendril curls.

    The helix makes one turn over the plant's height and every lobe reaches the
    canopy circle on its own side: together the six are the outline.
    """
    h, r, d = p.height, p.radius, p.dice
    index = np.arange(6)
    angle = d.uf(0.0, _TAU) + _TAU * (index + d.u(-_RIM_JITTER, _RIM_JITTER, 6)) / 6.0
    out = r * d.u(0.26, 0.38, 6)
    wide = r * d.u(_RIM_REACH, 1.0, 6) - out
    centers = np.stack([out * np.cos(angle), out * np.sin(angle),
                        h * (0.14 + 0.72 * index / 5.0)], axis=1)
    radii = np.stack([wide, wide, np.full(6, 0.20 * h)], axis=1)
    _top_out(centers, radii, h)
    heart = np.array([0.0, 0.0, 0.5 * h])
    lobes = _lobes(centers, radii, heart, d, p.phase, skin=_GROUND_SKIN * h)
    count = p.shell_leaves(280, 16.0, 140, 400)
    z = h * d.u(0.02, 0.98, count)
    turn = d.u(0.0, _TAU, count)
    radial = np.stack([np.cos(turn), np.sin(turn), np.zeros(count)], axis=1)
    # each leaf where a horizontal ray from the axis at its height leaves the lobes
    shell, normal = _on_lobes(d, _UP[None, :] * z[:, None], radial * r, centers, radii, miss=0.3)
    size = 0.27 * p.leaf_scale() * math.sqrt(r * max(r, 0.5 * h))
    leaves = _leaves(d, shell, normal + np.array([0.0, 0.0, 0.25]), size * d.u(0.8, 1.25, count),
                     0.80 if p.flag("frilly") else 0.60, heart, p.phase, r, h)
    curl = d.u(0.0, _TAU, 5)
    start = np.stack([0.3 * r * np.cos(curl), 0.3 * r * np.sin(curl), h * d.u(0.72, 0.90, 5)], axis=1)
    tendrils = _ribbons(start, np.stack([np.cos(curl + 1.3), np.sin(curl + 1.3)], axis=1),
                        r * d.u(0.25, 0.45, 5), h * d.u(0.06, 0.10, 5), np.full(5, 0.05 * r), 4,
                        np.full(5, 0.5), np.full(5, p.phase))
    return None, _join([lobes, leaves, tendrils])


def _ground(p: _Plan) -> _Shape:
    """A ground cover: a low mat of nine small bumps under a dense shell of leaves.

    The eight outer bumps each reach the canopy circle: they are the mat's outline.
    """
    h, r, d = p.height, p.radius, p.dice
    ring = _even_angles(d, 8, 0.2)
    out = np.concatenate([r * d.u(0.56, 0.64, 8), [0.0]])
    angle = np.concatenate([ring, [0.0]])
    wide = np.concatenate([r * d.u(_RIM_REACH, 1.0, 8) - out[:8], [r * d.uf(0.34, 0.42)]])
    # a lumpy skyline: some bumps stand twice as high as others (two flat mats of one
    # size were up to 97.6 % alike from the side)
    centers = np.stack([out * np.cos(angle), out * np.sin(angle), h * d.u(0.10, 0.25, 9)], axis=1)
    radii = np.stack([wide, wide, h * d.u(0.38, 0.85, 9)], axis=1)
    heart = np.array([0.0, 0.0, 0.2 * h])
    return None, _dome(p, centers, radii, _SPHERE_COARSE, 420, 16.0, 500, heart,
                       np.array([r, r, 0.8 * h]), -0.15, 0.20 * r)


def _hedge(p: _Plan) -> _Shape:
    """A clipped hedge section: a drum with a bevelled, nearly flat top in a fine leaf shell.

    A drum, not a box: the record is a circle and a circle has no heading, so a
    box's orientation would be invented. It is cut by hand, not turned on a
    lathe, and no two sections are cut alike: narrower at the top than at the
    foot (the batter a hedge is cut with), the shoulder higher or lower and
    squarer or rounder, the side bulging, the top dipping and a little out of
    level. Two perfect drums were the same drum (side silhouettes 99.9 % alike).
    A hedge section still repeats more than any other plant — clipping is what
    makes hedge plants alike, and the plan gives a section no more than a circle
    and a height.
    """
    h, r, d = p.height, p.radius, p.dice
    sides = 20
    theta = _TAU * np.arange(sides) / sides
    bulge, dip = _lumps(d, 0.10), _lumps(d, 0.14)
    batter = d.uf(0.72, 0.98)            # radius at the shoulder / radius at the foot
    shoulder = d.uf(0.68, 0.90)          # where the side turns into the top, of the height
    square = d.uf(0.74, 0.94)            # the top's radius / the shoulder's: 1 = cut square
    lean, low_side = d.uf(0.0, 0.12), d.uf(0.0, _TAU)   # the top is cut out of level

    def top_at(angle: Floats) -> Floats:
        return np.asarray(dip(angle) * (1.0 - lean * (0.5 + 0.5 * np.cos(angle - low_side))),
                          np.float64)

    side, top = bulge(theta), top_at(theta)
    highest = float(top.max())           # the top's highest point is the hedge's height

    def dip_to_height(angle: Floats) -> Floats:
        return np.asarray(np.minimum(top_at(angle) / highest, 1.0), np.float64)

    top = top / highest
    crown = float(top.mean())
    bevel = shoulder + 0.7 * (1.0 - shoulder)
    pos, tri = _revolve(
        np.stack([side, batter * side, 0.5 * (1.0 + square) * batter * side,
                  square * batter * side]) * r,
        np.stack([np.zeros(sides), shoulder * top, bevel * top, top]) * h, sides, apex=crown * h)
    heart = np.array([0.0, 0.0, 0.45 * h])
    nrm = _unit(_smooth_normals(pos, tri) * (1.0 - _SPHERIZE) + _unit(pos - heart[None, :]) * _SPHERIZE)
    ring_exposure = np.repeat([0.05, 0.40, 0.55, 0.60], sides)
    drum = _geo(pos, nrm, tri, np.concatenate([ring_exposure, [0.60]]),
                np.concatenate([np.repeat([0.66, 0.90, 1.0, 1.0], sides), [1.0]]), 0.5, p.phase)
    count = p.shell_leaves(380, 16.0, 150, 460)
    on_top = d.u(0.0, 1.0, count) < 0.28
    turn = d.u(0.0, _TAU, count)
    radial = np.stack([np.cos(turn), np.sin(turn), np.zeros(count)], axis=1)
    inward = np.where(on_top, np.sqrt(d.u(0.0, 1.0, count)), 1.0)     # 1 = at the rim
    up_side = d.u(0.05, 1.0, count)                                     # 1 = at the shoulder
    reach = r * bulge(turn) * np.where(on_top, square * batter * inward,
                                       1.0 - (1.0 - batter) * up_side)
    z = h * np.where(on_top, crown + (dip_to_height(turn) - crown) * inward,
                     shoulder * dip_to_height(turn) * up_side)
    shell = radial * reach[:, None] + _UP[None, :] * z[:, None]
    outward = np.where(on_top[:, None], _UP[None, :], radial)
    size = 0.16 * p.leaf_scale() * math.sqrt(r * max(r, 0.5 * h))
    leaves = _leaves(d, shell, outward, size * d.u(0.8, 1.2, count), 0.6, heart, p.phase, r, h,
                     droop=0.05)
    return None, _join([drum, leaves])


def _tip_reach(reach: Floats, corner: Floats | float, fold: float = 0.0) -> Floats:
    """How far out a leaf's or blade's TIP may be so that its corners — ``corner``
    to either side of the tip — end on the circle of radius ``reach``, not past it;
    a folded leaf's rib stands out from its tip by up to 2 × ``fold`` × ``corner``."""
    inside = np.sqrt(np.maximum(reach ** 2 - np.asarray(corner) ** 2, 0.0))
    return np.asarray(np.maximum(inside - 2.0 * fold * np.asarray(corner), 0.0), np.float64)


def _whorl(p: _Plan, count: int, tip_radius: float, tip_height: float, width: float, bow: float,
           outline: Floats = _BROAD_LEAF, base_radius: float = 0.06, base_height: float = 0.0,
           ripple: float = 0.0, fold: float = 0.18, rim: bool = False,
           crown: bool = False) -> _Geo:
    """One ring of ``count`` folded leaves rising from the plant's centre to tips
    at ``tip_radius`` × the radius and ``tip_height`` × the height.

    ``rim``: this ring is the plant's outline (``_RIM_REACH``, ``_RIM_JITTER``).
    ``crown``: this ring is the plant's top — its tallest leaf ends exactly at
    ``tip_height`` × the height (the others a little lower)."""
    h, r, d = p.height, p.radius, p.dice
    angle = _even_angles(d, count, _RIM_JITTER if rim else 0.25)
    radial = np.stack([np.cos(angle), np.sin(angle)], axis=1)
    widths = np.full(count, width) * d.u(0.9, 1.1, count)
    out = _tip_reach(r * tip_radius * d.u(_RIM_REACH if rim else 0.86, 1.0, count),
                     0.5 * widths * float(outline[-1]), fold)
    tall = d.u(0.85, 1.0, count)
    if crown:
        tall = tall / float(tall.max())
    base = np.concatenate([radial * (base_radius * r), np.full((count, 1), base_height * h)], axis=1)
    tip = np.concatenate([radial * out[:, None], (h * tip_height * tall)[:, None]], axis=1)
    return _fronds(base, tip, widths, np.full(count, bow), outline, d.u(0.0, 1.0, count),
                   (p.phase + d.u(-0.1, 0.1, count)) % 1.0, h, fold, ripple)


def _rosette(p: _Plan) -> _Shape:
    """A leafy vegetable: shingled rings of folded leaves — flat outside, upright inside —
    around a heart of young leaves (unless the recipe has none)."""
    r, h, d = p.radius, p.height, p.dice
    outer = p.number("n_out", 10.0, 6.0, 16.0)
    width = 0.80 * r * p.number("leaf_scale", 1.0, 0.6, 1.4)
    rings = [
        _whorl(p, round(outer), 1.00, 0.42, width, 0.20, ripple=0.3, rim=True),
        _whorl(p, max(round(0.78 * outer), 5), 0.80, 0.70, 0.86 * width, 0.15, ripple=0.3),
        _whorl(p, max(round(0.61 * outer), 4), 0.56, 0.92, 0.72 * width, 0.10, ripple=0.25),
    ]
    if p.flag("heart", True):
        # the heart is the plant's top: it ends exactly at the plan's height
        heart = np.array([[0.0, 0.0, 0.56 * h]])
        rings.append(_lobes(heart, np.array([[0.36 * r, 0.36 * r, 0.44 * h]]),
                            np.array([0.0, 0.0, 0.2 * h]), d, p.phase, skin=_GROUND_SKIN * h))
        rings[-1].exposure += 0.45   # the heart is the youngest, lightest growth
    else:
        rings.append(_whorl(p, max(round(0.47 * outer), 4), 0.30, 1.00, 0.55 * width, 0.05,
                            crown=True))
    return None, _join(rings)


def _head(p: _Plan) -> _Shape:
    """A brassica or an artichoke: two rings of large leaves — the upper ring is the
    plant's height — around a low bud of young leaves.

    The head itself — a curd, a flower bud — is a flower head, and a flower is a
    seasonal claim: v0 builds the plant that carries it, not the head.
    """
    width = 0.70 * p.radius
    ripple = 0.3 if p.flag("frilly") else 0.15
    return None, _join([
        _whorl(p, 11, 1.00, 0.70, width, 0.22, ripple=ripple, rim=True),
        _whorl(p, 8, 0.74, 1.00, 0.85 * width, 0.14, ripple=ripple, crown=True),
        _whorl(p, 6, 0.24, 0.50, 0.42 * width, 0.05),
    ])


def _blade_tuft(p: _Plan, count: int, foot: Floats, tip: Floats, tall: Floats, width: float,
                segments: int, arch: float) -> _Geo:
    """Blades from ``foot`` (xy, on the ground) whose tips end over ``tip`` (xy); the
    tallest is exactly as tall as the plant, the others ``tall`` (relative) of it."""
    d = p.dice
    lean = tip - foot
    reach = np.linalg.norm(lean, axis=1)
    direction = lean / np.maximum(reach, 1e-12)[:, None]
    base = np.concatenate([foot, np.zeros((count, 1))], axis=1)
    height = p.height * tall / float(tall.max())
    return _ribbons(base, direction, reach, height, width * d.u(0.8, _BLADE_WIDEST, count), segments,
                    d.u(0.0, 1.0, count), (p.phase + d.u(-0.1, 0.1, count)) % 1.0, arch)


def _blade_reach(reach: Floats, width: float) -> Floats:
    """``_tip_reach`` for a blade of a tuft ``width`` wide (its widest possible tip)."""
    return _tip_reach(reach, 0.5 * _BLADE_WIDEST * _BLADE_TIP * width)


def _grass(p: _Plan) -> _Shape:
    """A grass or a bulb's foliage: seven tufts of thin arching blades — one in the
    middle, six around it, each fanning away from the plant's centre.

    The outer tufts' blades are placed by where their TIPS end: evenly round the
    axis, every fourth one on the canopy circle (the outline), the rest a little
    short of it; each blade grows from the tuft nearest to its tip.
    """
    r, d = p.radius, p.dice
    per_tuft = round(p.number("n_out", 11.0, 8.0, 20.0))
    outer = 6 * per_tuft
    count = outer + per_tuft
    tuft_angle = _even_angles(d, 6, _RIM_JITTER)
    tuft_out = 0.38 * r * d.u(0.75, 1.1, 6)
    centre = np.concatenate([
        np.stack([tuft_out * np.cos(tuft_angle), tuft_out * np.sin(tuft_angle)], axis=1),
        np.zeros((1, 2)),
    ])
    width = 0.10 * r * p.leaf_scale()
    # the outer blades: tip direction and tip distance from the axis
    toward = _even_angles(d, outer, 0.3)
    far = _blade_reach(r * np.where(np.arange(outer) % 4 == 0, d.u(_RIM_REACH, 1.0, outer),
                                    d.u(0.80, 1.0, outer)), width)
    tip = far[:, None] * np.stack([np.cos(toward), np.sin(toward)], axis=1)
    apart = np.abs((toward[:, None] - tuft_angle[None, :] + np.pi) % _TAU - np.pi)
    tuft = np.concatenate([apart.argmin(axis=1), np.full(per_tuft, 6)])
    foot = centre[tuft] + r * d.u(-0.03, 0.03, (count, 2))
    # the middle tuft fans all round and stays inside
    middle = d.u(0.0, _TAU, per_tuft)
    inner_tip = (r * d.u(0.25, 0.70, per_tuft))[:, None] * np.stack(
        [np.cos(middle), np.sin(middle)], axis=1)
    return None, _blade_tuft(p, count, foot, np.concatenate([tip, inner_tip]),
                             d.u(0.70, 1.0, count), width, 4, 0.12)


def _allium(p: _Plan) -> _Shape:
    """An onion, a leek, sweet corn: ONE clump, two layers of broad blades — the outer
    arching out, the inner upright."""
    r, d = p.radius, p.dice
    outer = round(p.number("n_out", 16.0, 12.0, 26.0)) + 4
    inner = max(round(0.8 * outer), 10)
    count = outer + inner
    is_outer = np.arange(count) < outer
    angle = np.concatenate([_even_angles(d, outer, _RIM_JITTER), d.u(0.0, _TAU, inner)])
    foot = r * d.u(-0.02, 0.02, (count, 2))
    width = 0.24 * r * p.leaf_scale()
    # where each blade's tip ends, measured from the plant's axis (not from its own foot)
    far = np.where(is_outer, _blade_reach(r * d.u(_RIM_REACH, 1.0, count), width),
                   r * d.u(0.15, 0.50, count))
    tall = np.where(is_outer, d.u(0.62, 0.84, count), d.u(0.85, 1.0, count))
    tip = far[:, None] * np.stack([np.cos(angle), np.sin(angle)], axis=1)
    return None, _blade_tuft(p, count, foot, tip, tall, width, 5, 0.10)


def _feathery(p: _Plan) -> _Shape:
    """Fern-like foliage (carrot, dill, fennel, cosmos): twelve thin arching stems
    carrying narrow leaflets — airy, with no solid volume."""
    h, r, d = p.height, p.radius, p.dice
    stems = 12
    angle = _even_angles(d, stems, _RIM_JITTER)
    thick = 0.035 * r
    # where each stem's tip ends, measured from the plant's axis; the tallest stem
    # is the plant's height
    far = _tip_reach(r * d.u(_RIM_REACH, 1.0, stems), 0.5 * _BLADE_TIP * thick)
    tall = d.u(0.62, 0.98, stems)
    height = h * tall / float(tall.max())
    foot = r * d.u(-0.02, 0.02, (stems, 2))
    lean = far[:, None] * np.stack([np.cos(angle), np.sin(angle)], axis=1) - foot
    reach = np.linalg.norm(lean, axis=1)
    direction = lean / np.maximum(reach, 1e-12)[:, None]
    base = np.concatenate([foot, np.zeros((stems, 1))], axis=1)
    stalks = _ribbons(base, direction, reach, height, np.full(stems, thick), 4,
                      np.full(stems, 0.5), np.full(stems, p.phase))
    per_stem = round(p.number("n_out", 13.0, 8.0, 20.0) * 2.25)
    count = stems * per_stem
    stem = np.repeat(np.arange(stems), per_stem)
    f = d.u(0.22, 1.0, count)
    along = np.concatenate([direction, np.zeros((stems, 1))], axis=1)[stem]
    on_stem = base[stem] + along * (reach[stem] * f ** 2)[:, None] + _UP[None, :] * (height[stem] * f)[:, None]
    outward = _unit(along * 0.6 + d.u(-1.0, 1.0, (count, 3)) + np.array([0.0, 0.0, 0.5]))
    size = 0.20 * p.leaf_scale() * math.sqrt(r * max(r, 0.6 * h))
    leaflets = _leaves(d, on_stem, outward, size * d.u(0.7, 1.2, count), 0.28,
                       np.array([0.0, 0.0, 0.3 * h]), p.phase, r, h, droop=-0.1)
    return None, _join([stalks, leaflets])


def _flower(p: _Plan) -> _Shape:
    """A sunflower before it flowers: one stalk, broad leaves up its length, a leaf bud.

    The 2D sprite is one dominant flower head over a leaf ring; a flower is a
    seasonal claim, so v0 builds the plant that will carry it.
    """
    h, r, d = p.height, p.radius, p.dice
    stalk_radius = min(0.012 * h, 0.10 * r)
    pos, tri = _revolve(np.array([1.2, 1.0, 0.7]) * stalk_radius, np.array([0.0, 0.5, 0.94]) * h, 6)
    stalk = _geo(pos, _smooth_normals(pos, tri), tri, 0.15, 0.85, 0.5, p.phase)
    count = 12
    index = np.arange(count)
    # a spiral up the stalk that still puts one leaf into every twelfth of the circle
    angle = d.uf(0.0, _TAU) + _TAU * (
        (index * 5) % count + d.u(-_RIM_JITTER, _RIM_JITTER, count)) / count
    radial = np.stack([np.cos(angle), np.sin(angle)], axis=1)
    z = h * (0.14 + 0.70 * index / (count - 1))
    width = 0.72 * r
    out = _tip_reach(r * d.u(_RIM_REACH, 1.0, count), 0.5 * width * float(_BROAD_LEAF[-1]), 0.18)
    base = np.concatenate([radial * stalk_radius, z[:, None]], axis=1)
    tip = np.concatenate([radial * out[:, None], (z + h * d.u(-0.03, 0.05, count))[:, None]], axis=1)
    leaves = _fronds(base, tip, np.full(count, width), np.full(count, 0.10), _BROAD_LEAF,
                     d.u(0.0, 1.0, count), (p.phase + d.u(-0.1, 0.1, count)) % 1.0, h)
    # the bud is the plant's top: its tallest leaf ends at the plan's height
    bud = _whorl(p, 5, 0.24, 1.0, 0.30 * r, 0.03, _LANCE_LEAF, base_radius=0.02, base_height=0.90,
                 crown=True)
    return None, _join([stalk, leaves, bud])


def _palm(p: _Plan) -> _Shape:
    """A palm: a slender ringed trunk and a crown of arching, notched fronds."""
    h, r, d = p.height, p.radius, p.dice
    crown = 0.78 * h
    trunk_radius = min(0.03 * h, 0.18 * r)
    rings = np.array([1.35, 1.0, 1.08, 0.95, 1.03, 0.90]) * trunk_radius
    pos, tri = _revolve(rings, np.array([0.0, 0.08, 0.30, 0.52, 0.76, 1.0]) * crown, 8)
    trunk = _geo(pos, _smooth_normals(pos, tri), tri, 0.0, 1.0, 0.0, 0.0)
    count = round(p.number("n_out", 9.0, 6.0, 14.0))
    angle = _even_angles(d, count, _RIM_JITTER)
    radial = np.stack([np.cos(angle), np.sin(angle)], axis=1)
    base = np.concatenate([radial * trunk_radius, np.full((count, 1), crown)], axis=1)
    width = 0.46 * r
    out = _tip_reach(r * d.u(_RIM_REACH, 1.0, count), 0.5 * width * float(_FROND[-1]), 0.22)
    tip = np.concatenate([radial * out[:, None], (h * d.u(0.50, 0.66, count))[:, None]], axis=1)
    length = np.linalg.norm(tip - base, axis=1)
    bow = (h - crown) * d.u(1.25, 1.6, count) / np.maximum(length, 1e-12)
    fronds = _fronds(base, tip, np.full(count, width), bow, _FROND, d.u(0.0, 1.0, count),
                     (p.phase + d.u(-0.1, 0.1, count)) % 1.0, h, fold=0.22)
    # the spear — the youngest, upright fronds — is the palm's top
    spear = _whorl(p, 3, 0.22, 1.0, 0.16 * r, 0.02, _LANCE_LEAF, base_radius=0.01, base_height=0.78,
                   crown=True)
    return trunk, _join([fronds, spear])


#: Archetype (``recipe["a"]``) → its silhouette. Every archetype of the 2D tables
#: is here: ``tests/unit/test_scene3d_plants.py`` pins this map to
#: ``plant_art.ARCHETYPES``, so a new 2D archetype fails a test instead of
#: borrowing another one's shape.
ARCHETYPE_BUILDERS: Final[Mapping[str, _ArchetypeBuilder]] = MappingProxyType({
    "allium": _allium,
    "canopy": _canopy,
    "climber": _climber,
    "conifer": _conifer,
    "feathery": _feathery,
    "flower": _flower,
    "grass": _grass,
    "ground": _ground,
    "head": _head,
    "hedge": _hedge,
    "mound": _mound,
    "palm": _palm,
    "rosette": _rosette,
})


# ── truth and colour ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class FitReport:
    """What it took to make a builder's output the plan's numbers.

    The archetype builders build TO the data — a body as tall as the height,
    an outline on the canopy circle — and the fit only normalises the last
    millimetre. This is the record of that last millimetre, so that a test can
    hold the builders to it (a bounding box that is exact after the fit says
    nothing about the plant: a squash built 1.6 times too tall and squashed back
    had an exact box and its whole body in the lower 63 % of its height).

    - ``built_top``: the builder's top before the fit, as a fraction of the
      height (1.0 = built to the data);
    - ``z_scale``, ``xy_scale``: the factors the fit applied;
    - ``clamped_share``: the share of foliage vertices that lay beyond the
      canopy circle and were pulled back onto it; ``clamped_reach``: the
      farthest of them, in canopy radii (1.0 when there was none);
    - ``pressed_share``: the share of all vertices that lay below the ground
      and were pressed onto it;
    - ``set_down``: how far the plant was set down onto the ground, as a
      fraction of the height (a plant is never lifted);
    - ``centre_shift``: how far the foliage was moved to centre its bounding
      box on the plan position, in canopy radii;
    - ``reach``: where the plant ENDS — its farthest vertex from the axis after
      the fit's last step, foliage or wood, in canopy radii. For the foliage
      never more than ``REACH_MAX``: that is what the last step is. For the
      plant, wherever foliage is its outermost part (the trunk builders'
      invariant — see ``REACH_MAX``); wood is measured here and not moved.
      ``reined_share``: the share of all vertices that step had to move (0.0
      for nearly every plant);
    - ``stretch``: z over xy of the scale from the proportion the shape was
      built at to the plan's (``PROPORTION_STEP``) — 1.0 for the fit itself.
    """

    built_top: float
    z_scale: float
    xy_scale: float
    clamped_share: float
    clamped_reach: float
    pressed_share: float
    set_down: float
    centre_shift: float
    reach: float
    reined_share: float
    stretch: float = 1.0


def _rein_in(pos: Floats, limit: float) -> int:
    """Put every vertex further than ``limit`` from the axis ONTO that circle, in
    place; return how many were moved.

    A vertex is moved along the axis it is NOT farthest on: its larger
    coordinate stays, the smaller one shrinks until the vertex is ``limit``
    from the axis. So a vertex that is an extreme of the bounding box along the
    plant's widest axis stays that extreme — pulling it straight toward the axis
    would shorten the box. Needs every coordinate within ``limit`` already
    (true after the fit's scale: none exceeds the canopy radius).
    """
    flat = pos[:, :2]                                             # a view: written in place
    beyond = np.flatnonzero(np.hypot(flat[:, 0], flat[:, 1]) > limit)
    if len(beyond):
        far = np.abs(flat[beyond])
        major = far.argmax(axis=1)                                # a tie keeps x
        minor = 1 - major
        each = np.arange(len(beyond))
        kept = np.minimum(far[each, major], limit)
        flat[beyond, major] = np.copysign(kept, flat[beyond, major])
        flat[beyond, minor] = np.copysign(np.sqrt(np.maximum(limit * limit - kept * kept, 0.0)),
                                          flat[beyond, minor])
    return int(len(beyond))


def _fit(wood: _Geo | None, foliage: _Geo, height: float, radius: float) -> FitReport:
    """Make the bounding box the data, in place, and report what that took.

    Builders work at the plant's real size and inside it, so little is left to
    do. Foliage that still strays beyond the canopy circle (the corner of a leaf
    lying along the plant's edge) is pulled back onto it. The foliage is then
    centred on the local origin (the canopy circle's centre) — the wood stays
    where it stands: a trunk's foot is the plan position. Whatever dips below
    the plant's ground is pressed onto it; a plant whose lowest point is above
    the ground is set down. Then everything is scaled about the origin: xy so
    the widest span is the canopy diameter, z so the top is the height. Normals
    take the inverse of the scale.

    Each of those steps undoes a little of the one before — centring moves a
    vertex that was pulled onto the circle off it again, and the scale carries it
    further — so none of them says where a vertex ENDS. The last step does:
    whatever FOLIAGE is further than ``REACH_MAX`` canopy radii from the axis is
    put onto that circle (``_rein_in``). Nothing follows it, so for foliage the
    bound holds by construction, for any builder output; and because a vertex
    keeps its larger coordinate, the widest span is still exactly the canopy
    diameter and is still centred. (Along the OTHER axis the box can lose a hair
    if the vertex reined in was that axis's extreme; the report says when
    anything was moved.)

    Wood is not reined in: its faces are flat-shaded, and a moved vertex would
    leave a face whose stored normal is no longer its winding normal (foliage
    normals are bent by design and held to no such rule). It does not need to
    be — a trunk is built within a third of the canopy radius of the axis
    (``REACH_MAX``'s comment) — and the report's ``reach`` measures it all the
    same, so a trunk builder that broke that would be seen.

    Never lift a plant to make its lowest vertex zero: one leaf dipping 9 cm
    under a lavender's base lifted the whole cushion 9 cm into the air, and
    "min z = 0" still held (a sanity render found it, not a gate).

    Why not scale the farthest vertex onto the circle instead: the bounding box
    then spans as little as 72 % of the canopy diameter for a sparse plant.
    """
    parts = [foliage] if wood is None else [wood, foliage]
    vertices = sum(len(part.pos) for part in parts)
    built_top = max(float(part.pos[:, 2].max()) for part in parts) / height
    distance = np.hypot(foliage.pos[:, 0], foliage.pos[:, 1])
    stray = distance > radius * (1.0 + 1e-9)     # beyond the circle, not merely rounded onto it
    clamped_reach = max(float(distance.max()) / radius, 1.0)
    foliage.pos[stray, :2] *= (radius / distance[stray])[:, None]
    low, high = foliage.pos[:, :2].min(axis=0), foliage.pos[:, :2].max(axis=0)
    shift = (low + high) / 2.0
    foliage.pos[:, :2] -= shift
    pressed = 0
    for part in parts:
        pressed += int((part.pos[:, 2] < 0.0).sum())
        part.pos[:, 2] = np.maximum(part.pos[:, 2], 0.0)
    widest = max(float(np.abs(part.pos[:, :2]).max()) for part in parts)
    bottom = min(float(part.pos[:, 2].min()) for part in parts)   # >= 0: only ever set down
    top = max(float(part.pos[:, 2].max()) for part in parts)
    scale = np.array([radius / max(widest, 1e-12), radius / max(widest, 1e-12),
                      height / max(top - bottom, 1e-12)])
    for part in parts:
        part.pos[:, 2] -= bottom
        part.pos *= scale[None, :]
        nrm = part.nrm / scale[None, :]
        length = np.linalg.norm(nrm, axis=1, keepdims=True)
        part.nrm = np.where(length > 1e-12, nrm / np.maximum(length, 1e-12), _UP[None, :])
    # ── the LAST step: nothing follows it, so this is where every foliage vertex ends ──
    reined = _rein_in(foliage.pos, REACH_MAX * radius)
    reach = max(float(np.hypot(part.pos[:, 0], part.pos[:, 1]).max()) for part in parts) / radius
    return FitReport(
        built_top=built_top, z_scale=float(scale[2]), xy_scale=float(scale[0]),
        clamped_share=float(stray.mean()), clamped_reach=clamped_reach,
        pressed_share=pressed / vertices, set_down=bottom / height,
        centre_shift=float(np.hypot(shift[0], shift[1])) / radius,
        reach=reach, reined_share=reined / vertices)


@lru_cache(maxsize=32)
def _palette(name: str) -> Floats:
    """A palette's four leaf anchors (t0, t1, b0, b1) as sRGB 0..1, shape (4, 3)."""
    entry = PALETTES[name]
    rows = [[int(entry[key][i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
            for key in ("t0", "t1", "b0", "b1")]
    anchors = np.array(rows, np.float64)
    anchors.setflags(write=False)
    return anchors


def _foliage_colors(geo: _Geo, palette: Floats, tip_weight: float) -> Floats:
    """Linear RGBA per vertex from the palette alone.

    The mix between the base anchors and the tip anchors follows each vertex's
    exposure, shifted so that the plant's mean — weighted by the surface a
    vertex stands for × its shade^(1/2.4), i.e. by what it contributes to the
    picture in sRGB — is ``tip_weight``, the archetype's measured share of tip
    tone in the 2D sprite. The mix is made in sRGB, as the 2D gradients are;
    the shade is applied in linear light and does not move the hue.
    """
    weight = _vertex_areas(geo.pos, geo.tri) * geo.shade ** (1.0 / 2.4)
    total = max(float(weight.sum()), 1e-12)
    tip = tip_weight + _TONE_CONTRAST * (geo.exposure - float(weight @ geo.exposure) / total)
    tip = np.clip(tip, 0.0, 1.0)
    tip = np.clip(tip + (tip_weight - float(weight @ tip) / total), 0.0, 1.0)
    tone = geo.tone[:, None]
    base_colour = palette[2][None, :] + (palette[3] - palette[2])[None, :] * tone
    tip_colour = palette[0][None, :] + (palette[1] - palette[0])[None, :] * tone
    srgb = base_colour + (tip_colour - base_colour) * tip[:, None]
    rgba = np.ones((len(geo.pos), 4))
    rgba[:, :3] = np.clip(_srgb_to_linear(srgb) * geo.shade[:, None], 0.0, 1.0)
    return rgba


def _solid(pos: Floats, colour: NDArray[np.float32]) -> Floats:
    rgba = np.ones((len(pos), 4))
    rgba[:, :3] = colour[None, :]
    return rgba


# ── the shape cache: a plant that grows is the same shape, scaled ─────────────

#: The proportion (height over canopy radius) a shape is BUILT at is the plan's,
#: rounded to a whole power of this step; the built shape is then scaled to the
#: plan's exact height and radius. So a plant that grows a little is the shape it
#: was, a little larger — a multiplication, not a rebuild — and it changes form
#: only when its proportion has moved by a step. The scale is exact: the top IS
#: the height and the widest span IS the canopy diameter at every size (the
#: rounding moves no number the plan states). What it costs is form: one axis is
#: stretched against the other by at most the square root of the step, 2.5 %.
PROPORTION_STEP: Final = 1.05
#: Bytes of remembered shapes the cache may hold — a memory cap, not a count:
#: the number of shapes follows the plan (one per plant and proportion step it
#: is seen at). One shape measured 18 … 139 kB, 76 kB on average over the 123
#: recipes at their mature size (``shape_bytes``, 2026-10-11), so the cap is
#: about 3,500 average plants and 1,900 of the largest trees; the larger bench
#: plan (320 plants) holds 24 MB. What happens AT the cap: ``_ShapeCache``.
SHAPE_CACHE_BYTES: Final = 256 * 1024 * 1024
#: The smallest height and canopy radius a plant is built at: a micrometre. The
#: largest is the longest length a record can hold, ``core.scene3d.MAX_LENGTH_CM``
#: (10 km). ``build_silhouette`` refuses a size outside that range with a
#: ``ValueError`` — outside it the arithmetic leaves float32 (a height of 1e300
#: gave a mesh of NaNs with only a RuntimeWarning; a radius of 1e-310 an
#: ``OverflowError`` from the logarithm; a height of 5e-324 a ``MeshError``).
#: Inside it every archetype builds an exact, valid plant, the four corners
#: included (pinned).
MIN_SIZE_CM: Final = 1e-4
_UNIT_RADIUS: Final = 100.0
#: The recipe keys an archetype builder may read; ``pal`` and ``a`` are read by
#: ``_form`` itself. A builder that reads another key fails (``_ReadKeys``).
_FORM_KEYS: Final = ("leaf_scale", "n_out", "narrow", "frilly", "heart")


class _ReadKeys(dict[str, Any]):
    """The recipe as a builder sees it: only the keys the cache key is made of.

    A builder that read any other key would be handed a remembered shape built
    for a recipe that differed in exactly that key — so reading one is an error
    here, in every test, and not a wrong plant in a garden."""

    def get(self, key: str, default: Any = None) -> Any:
        if key not in _FORM_KEYS:
            raise KeyError(f"a plant builder may read only {_FORM_KEYS} of a recipe, not {key!r}")
        return super().get(key, default)


@dataclass(frozen=True, slots=True)
class _Form:
    """What of a recipe decides a plant's 3D form — hashable: the cache's key."""

    archetype: str
    palette: str
    leaf_scale: float | None
    n_out: float | None
    narrow: bool
    frilly: bool
    heart: bool

    def recipe(self) -> _ReadKeys:
        values = {"leaf_scale": self.leaf_scale, "n_out": self.n_out, "narrow": self.narrow,
                  "frilly": self.frilly, "heart": self.heart}
        return _ReadKeys({key: value for key, value in values.items() if value is not None})


def _number_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _form(recipe: Mapping[str, Any]) -> _Form:
    archetype = str(recipe.get("a"))
    if archetype not in ARCHETYPE_BUILDERS:
        raise ValueError(f"no 3D builder for archetype {archetype!r}")
    return _Form(archetype, palette_key(recipe), _number_or_none(recipe.get("leaf_scale")),
                 _number_or_none(recipe.get("n_out")), bool(recipe.get("narrow", False)),
                 bool(recipe.get("frilly", False)), bool(recipe.get("heart", True)))


@dataclass(frozen=True, slots=True)
class _Arrays:
    """One part of a built shape: read-only float32 / uint32 arrays, shared by
    every mesh scaled from it (colours, uvs and indices are never copied)."""

    positions: NDArray[np.float32]
    normals: NDArray[np.float32]
    colors: NDArray[np.float32]
    uvs: NDArray[np.float32]
    indices: NDArray[np.uint32]

    @staticmethod
    def of(pos: Floats, nrm: Floats, colors: Floats, uvs: Floats, tri: Ints) -> _Arrays:
        mesh = Mesh.from_arrays(pos, nrm, colors, uvs, tri)     # coerced, private, read-only
        return _Arrays(mesh.positions, mesh.normals, mesh.colors, mesh.uvs, mesh.indices)

    def scaled(self, scale: NDArray[np.float32], stretch: float) -> Mesh:
        """This part at the plan's size: positions × ``scale``, normals re-bent when the
        scale is not uniform; colours, uvs and indices are the remembered arrays themselves.

        The mesh is constructed DIRECTLY, not through ``Mesh.from_arrays`` — that would
        copy the three shared arrays for every plant on every tick. So what
        ``from_arrays`` guarantees for its meshes is established here by other means,
        and this is the one place that says which:

        - *sealed* (read-only for good): the remembered arrays came out of
          ``from_arrays`` (``of``); the two computed here go through ``_sealed``;
        - *finite*: the remembered arrays passed ``from_arrays``' check, and the
          factors are bounded — ``_shape_and_scale`` refuses a size outside
          ``MIN_SIZE_CM`` … ``MAX_LENGTH_CM``, inside which a remembered coordinate
          is at most about 1e12 and a scaled one at most 1.09e6, both far inside
          float32;
        - *dtype and shape*: float32 × float32, and ``_sealed`` keeps the shape.
        """
        positions = _sealed(self.positions * scale[None, :])
        normals = self.normals
        if abs(stretch - 1.0) > 1e-9:                             # not a uniform scale
            bent = normals.astype(np.float64)
            bent[:, 2] /= stretch
            normals = _sealed((bent / np.linalg.norm(bent, axis=1, keepdims=True)).astype(np.float32))
        return Mesh(positions, normals, self.colors, self.uvs, self.indices)

    def nbytes(self) -> int:
        return int(sum(a.nbytes for a in (self.positions, self.normals, self.colors, self.uvs,
                                          self.indices)))


def _sealed(array: NDArray[np.float32]) -> NDArray[np.float32]:
    """``array`` on immutable memory, as ``Mesh.from_arrays`` makes its own: read-only
    for good (``setflags(write=True)`` is refused on it and on its base)."""
    return np.frombuffer(array.tobytes(), dtype=np.float32).reshape(array.shape)


@dataclass(frozen=True, slots=True)
class _BuiltShape:
    """A plant built and fitted at ``_UNIT_RADIUS`` and ``proportion`` × it."""

    proportion: float
    foliage: _Arrays
    wood: _Arrays | None
    report: FitReport

    def nbytes(self) -> int:
        return self.foliage.nbytes() + (self.wood.nbytes() if self.wood is not None else 0)


class ShapeCacheInfo(NamedTuple):
    """The shape cache since it was last cleared (``shape_cache_info``)."""

    hits: int        #: shapes asked for and found
    misses: int      #: shapes asked for and BUILT
    shapes: int      #: shapes held now
    bytes: int       #: … and the bytes of their arrays
    max_bytes: int   #: the cap (``SHAPE_CACHE_BYTES`` unless resized)


_ShapeKey: TypeAlias = tuple[_Form, int, int]              # (form, seed, proportion step)
#: How many keys the cache remembers the last request of (held or not): what lets
#: it tell a shape of the plan in use from a shape nobody asks for any more.
#: This request log is NOT part of ``SHAPE_CACHE_BYTES``: it is bounded by this
#: count, and full it weighs 15–21 MB on top of the cap (measured: 14.6 MB with
#: one recipe form shared by every key, 234 bytes a key; the third review read
#: 20.8 MB). ``clear_shape_cache`` empties it together with the shapes.
_ASKED_KEPT: Final = 1 << 16


class _ShapeCache:
    """Remembered shapes under a cap in BYTES — with no cliff at the cap.

    The count is not capped, so the cache grows with the plan: a plan of any
    number of growing plants is warm as long as their shapes fit the cap.

    At the cap, a plain least-recently-used rule falls off a cliff: a date
    scrub asks for every growing plant once per tick, in the same order, so the
    shape it drops is always the one it needs next — with room for 1,024 shapes
    and 1,025 growing plants EVERY plant was rebuilt on EVERY tick (the first
    cache, as the review measured it: 1.9 s a tick, and none rebuilt with
    1,024). So a new shape gets room only from shapes that nobody asked for
    since this very shape was last asked for:

    - a shape never asked for before (a new plan, a plant that grew a step)
      takes the place of the least recently asked ones;
    - a shape asked for before, and dropped, comes back only in place of shapes
      not asked for since then — if everything held is in use (asked for more
      recently), it is built, handed out and NOT held.

    A scrub over more plants than fit therefore keeps as many shapes as fit and
    rebuilds only the rest, every tick: the cost grows by one plant per plant
    beyond the cap. Shapes of a plan no longer shown are the least recently
    asked and give way first. A shape larger than the cap is never held.

    What the second rule COSTS, at the cap only (below it nothing is ever
    dropped) — a shape that was dropped comes back in TWO builds, not one: on
    the tick it is asked for again everything held is still "in use", so it is
    built and not held; on the next tick it is built again and takes its place.
    Measured, and pinned by tests with these numbers:

    - going back to a plan whose shapes were dropped (64 shapes at a cap of
      64): 64, 64, 0 builds per tick — two cold ticks, where a new plan costs
      one;
    - a scrub BACKWARD at the cap costs twice the forward one: one plant
      crossing a proportion step per tick, 40 ticks: 40 builds forward (each
      step is new), 79 back (each was seen and dropped);
    - two plans shown in turn, tick by tick, each filling the cap: the one that
      came first is rebuilt every time, the other never — half of all builds.

    Call ``clear_shape_cache()`` when a plan is closed and none of this arises
    for the next one.

    Threads: the bookkeeping is under a lock and ``build`` runs outside it, so
    two threads asking for one new shape at once would both build it (to the
    same result). That is by reading. The cache is used from the GUI thread
    only and has NOT been tested under threads.
    """

    def __init__(self, max_bytes: int) -> None:
        self._lock = threading.Lock()
        self._max_bytes = int(max_bytes)
        self._held: OrderedDict[_ShapeKey, _BuiltShape] = OrderedDict()   # least recently asked first
        self._asked: OrderedDict[_ShapeKey, int] = OrderedDict()          # key → when last asked
        self._clock = self._bytes = self._hits = self._misses = 0

    def get(self, key: _ShapeKey, build: Callable[[], _BuiltShape]) -> _BuiltShape:
        with self._lock:
            self._clock += 1
            before = self._asked.pop(key, None)
            self._asked[key] = self._clock
            if len(self._asked) > _ASKED_KEPT:
                self._asked.popitem(last=False)
            held = self._held.get(key)
            if held is not None:
                self._held.move_to_end(key)
                self._hits += 1
                return held
            self._misses += 1
        shape = build()
        with self._lock:
            self._admit(key, shape, before)
        return shape

    def _admit(self, key: _ShapeKey, shape: _BuiltShape, before: int | None) -> None:
        size = shape.nbytes()
        if key in self._held or size > self._max_bytes:
            return
        while self._bytes + size > self._max_bytes:
            oldest = next(iter(self._held))
            if before is not None and self._asked.get(oldest, 0) > before:
                return                      # everything held is in use: this one is not held
            self._bytes -= self._held.pop(oldest).nbytes()
        self._held[key] = shape
        self._bytes += size

    def resize(self, max_bytes: int) -> None:
        with self._lock:
            self._max_bytes = int(max_bytes)
            while self._held and self._bytes > self._max_bytes:
                self._bytes -= self._held.popitem(last=False)[1].nbytes()

    def clear(self) -> None:
        with self._lock:
            self._held.clear()
            self._asked.clear()
            self._clock = self._bytes = self._hits = self._misses = 0

    def info(self) -> ShapeCacheInfo:
        with self._lock:
            return ShapeCacheInfo(self._hits, self._misses, len(self._held), self._bytes,
                                  self._max_bytes)


_SHAPES: Final = _ShapeCache(SHAPE_CACHE_BYTES)


def _proportion_step(height_cm: float, radius_cm: float) -> int:
    return round(math.log(height_cm / radius_cm) / math.log(PROPORTION_STEP))


def _build_shape(form: _Form, seed: int, step: int) -> _BuiltShape:
    proportion = PROPORTION_STEP ** step
    height, radius = proportion * _UNIT_RADIUS, _UNIT_RADIUS
    dice = _Dice(seed)
    wood, foliage = ARCHETYPE_BUILDERS[form.archetype](
        _Plan(height, radius, form.recipe(), dice, dice.uf(0.0, 1.0)))
    report = _fit(wood, foliage, height, radius)
    colours = _foliage_colors(foliage, _palette(form.palette), FOLIAGE_TIP_WEIGHT[form.archetype])
    sway = np.stack([np.clip(foliage.pos[:, 2] / height, 0.0, 1.0),
                     np.minimum(foliage.phase % 1.0, 0.999999)], axis=1)
    bark = None if wood is None else _Arrays.of(
        wood.pos, wood.nrm, _solid(wood.pos, srgb_to_linear(BARK_SRGB)),
        np.zeros((len(wood.pos), 2)), wood.tri)
    return _BuiltShape(proportion, _Arrays.of(foliage.pos, foliage.nrm, colours, sway, foliage.tri),
                       bark, report)


def _shape_and_scale(recipe: Mapping[str, Any], seed: int, height_cm: float, radius_cm: float
                     ) -> tuple[_BuiltShape, NDArray[np.float32], float]:
    # one chained comparison each: a NaN fails it, as zero, a negative and an infinity do
    if not (MIN_SIZE_CM <= height_cm <= MAX_LENGTH_CM and MIN_SIZE_CM <= radius_cm <= MAX_LENGTH_CM):
        raise ValueError(
            f"a plant needs a height and a canopy radius between {MIN_SIZE_CM:g} and "
            f"{MAX_LENGTH_CM:g} cm, got {height_cm!r} × {radius_cm!r}")
    form, own, step = _form(recipe), int(seed), _proportion_step(height_cm, radius_cm)
    shape = _SHAPES.get((form, own, step), lambda: _build_shape(form, own, step))
    across = radius_cm / _UNIT_RADIUS
    up = height_cm / (shape.proportion * _UNIT_RADIUS)
    return shape, np.array([across, across, up], np.float32), up / across


def build_silhouette(recipe: Mapping[str, Any], seed: int, height_cm: float,
                     radius_cm: float) -> tuple[MeshPart, ...]:
    """The silhouette of ``recipe`` at ``height_cm`` × a canopy of ``radius_cm``.

    Pure and deterministic in its arguments: the shape is built once per
    (recipe form, seed, proportion step) and remembered (``PROPORTION_STEP``,
    ``SHAPE_CACHE_BYTES``), then scaled to the exact size — remembering changes
    how long a call takes, never what it returns. The remembered arrays are
    read-only and shared between the meshes scaled from them. Threads: the cache
    keeps its bookkeeping under a lock, but this is called from the GUI thread
    only and has NOT been tested under threads — treat it as GUI-thread code
    until it has.

    ``ValueError`` for an archetype without a builder — never another
    archetype's shape — and for a height or canopy radius outside
    ``MIN_SIZE_CM`` … ``MAX_LENGTH_CM`` (which a NaN, zero, a negative number
    and an infinity all are).
    """
    shape, scale, stretch = _shape_and_scale(recipe, seed, height_cm, radius_cm)
    parts = [MeshPart(shape.foliage.scaled(scale, stretch), "foliage", casts_shadow=True,
                      name=PART_FOLIAGE)]
    if shape.wood is not None:
        parts.insert(0, MeshPart(shape.wood.scaled(scale, stretch), "vc", casts_shadow=True,
                                 name=PART_WOOD))
    return tuple(parts)


def fit_report(recipe: Mapping[str, Any], seed: int, height_cm: float,
               radius_cm: float) -> FitReport:
    """What the fit repaired on the shape ``build_silhouette`` returns for these
    arguments (``FitReport``) — the instrument that holds the builders to
    building to the data."""
    shape, _scale, stretch = _shape_and_scale(recipe, seed, height_cm, radius_cm)
    return replace(shape.report, stretch=stretch)


def shape_bytes(recipe: Mapping[str, Any], seed: int, height_cm: float, radius_cm: float) -> int:
    """Bytes the remembered shape behind ``build_silhouette(...)`` holds — what one
    entry of the shape cache costs against ``SHAPE_CACHE_BYTES``."""
    shape, _scale, _stretch = _shape_and_scale(recipe, seed, height_cm, radius_cm)
    return shape.nbytes()


def shape_cache_info() -> ShapeCacheInfo:
    """Hits, misses (= shapes BUILT), shapes and bytes held, and the cap, since the
    cache was last cleared — how a test or a scrub tells a scaled plant from a
    rebuilt one."""
    return _SHAPES.info()


def clear_shape_cache() -> None:
    """Forget EVERYTHING the shape cache holds: every remembered shape, the
    request log (when each shape was last asked for — so nothing asked before
    the call counts as "asked before" after it) and the counters. The cap stays
    as it is.

    Call it when a plan is closed: the memory is given back at once, and the
    next plan starts as from a fresh process (without it the old plan's shapes
    go only when the cap binds, and coming back to them costs two cold ticks —
    ``_ShapeCache``). Also the cold start a measurement needs, and what a test
    that must see a shape BUILT twice calls in between."""
    _SHAPES.clear()


def resize_shape_cache(max_bytes: int = SHAPE_CACHE_BYTES) -> None:
    """Set the cap of the shape cache in bytes (default: back to
    ``SHAPE_CACHE_BYTES``); the least recently asked shapes beyond it are dropped."""
    _SHAPES.resize(max_bytes)


@lru_cache(maxsize=64)
def _placeholder(radius_cm: float) -> tuple[MeshPart, ...]:
    height = min(PLACEHOLDER_HEIGHT_FRACTION * 2.0 * radius_cm, PLACEHOLDER_MAX_HEIGHT_CM)
    sphere = (radius_cm * radius_cm + height * height) / (2.0 * height)
    rings = radius_cm * np.array([1.0, 0.86, 0.68, 0.46, 0.23])
    z = np.sqrt(sphere * sphere - rings * rings) - (sphere - height)
    z[0] = 0.0
    pos, tri = _revolve(rings, z, _PLACEHOLDER_SIDES, apex=height)
    nrm = _unit(pos + np.array([0.0, 0.0, sphere - height])[None, :])  # the cap's own sphere
    tone = srgb_to_linear(FLOWERS["white"][0]) * np.float32(PLACEHOLDER_SHADE)
    mesh = Mesh.from_arrays(pos, nrm, _solid(pos, tone), np.zeros((len(pos), 2)), tri)
    return (MeshPart(mesh, "vc", casts_shadow=False, name=PART_PLACEHOLDER),)


def placeholder_parts(radius_cm: float) -> tuple[MeshPart, ...]:
    """The honest marker of a plant whose height the plan does not know.

    One part: a smooth spherical cap over the canopy circle,
    ``min(PLACEHOLDER_HEIGHT_FRACTION × diameter, PLACEHOLDER_MAX_HEIGHT_CM)``
    high, in one neutral tone, casting no shadow (the 2D shadow model gives a
    plant without a height none either). The same for every item: a marker has
    no individuality, and it reads nothing but the radius.
    """
    return _placeholder(float(radius_cm))


# ── the pipeline's builder ────────────────────────────────────────────────────


@lru_cache(maxsize=1024)
def _resolve(kind: str, species: str, category: str | None) -> SpriteRef | None:
    return resolve_sprite(kind, species, category, available=has_recipe)


def plant_sprite(record: Record) -> SpriteRef | None:
    """The sprite — and so the recipe — of a plant record, or None when the record
    is not a plant.

    The 2D rule (``plant_art.resolve_sprite``) on EXACTLY the 2D renderer's
    inputs: the item's type, its own species string as it is (the record's
    ``sprite_species`` — raw, and blank for a string of blanks, which takes the
    plant's category sprite in 2D and so it does here) and its plant category.
    Not ``species_name``: that is the species DATA's common name where the item
    has data, and the two differ — a "Pumpkin" from the gallery carries the
    data of "Winter Squash" while its own string is "pumpkin". A species
    ASSIGNED from the plant database writes the item's string (#445), so the
    assigned species is the one both views draw and build (ADR-059 addendum
    "plant art v0", ruling R14, as amended by the #446 addendum).
    """
    if record.kind not in PLANT_KINDS:
        return None
    species = record.params.get(PARAM_SPRITE_SPECIES)
    category = record.params.get(PARAM_PLANT_CATEGORY)
    return _resolve(record.kind, species if isinstance(species, str) else "",
                    category if isinstance(category, str) else None)


def _canopy_radius(record: Record) -> float | None:
    radius = record.params.get(PARAM_RADIUS_CM)
    if isinstance(radius, bool) or not isinstance(radius, (int, float)):
        return None
    return float(radius) if math.isfinite(radius) and radius > 0.0 else None


def _plant_of(record: Record) -> tuple[SpriteRef, float] | None:
    """(sprite, canopy radius) of a record the plant builder builds as a plant;
    None for one it hands to ``default_builder`` — not a plant kind, or a plant
    record without a canopy circle. The one decision ``plant_archetype`` and
    ``build_plant`` both answer from."""
    sprite = plant_sprite(record)
    radius = _canopy_radius(record)
    return None if sprite is None or radius is None else (sprite, radius)


def plant_archetype(record: Record) -> str | None:
    """What ``build_plant`` builds for a record: an archetype name, ``PLACEHOLDER``
    for a plant without a height and without an illustrative fallback (#557),
    None for a record it does not build as a plant
    (not a plant kind, or no canopy circle: that one gets ``default_builder``)."""
    plant = _plant_of(record)
    if plant is None:
        return None
    if record.height_cm is None:
        try:
            from open_garden_planner.core.plant_height_estimate import (
                ESTIMATED_HEIGHT_PARAM,
            )

            _est = record.params.get(ESTIMATED_HEIGHT_PARAM)
            if isinstance(_est, (int, float)) and not isinstance(_est, bool) and float(_est) > 0:
                return str(recipe_for(plant[0])["a"])
        except Exception:
            pass
        return PLACEHOLDER
    return str(recipe_for(plant[0])["a"])


def _estimated_fallback_cm(record: Record) -> float | None:
    """Illustrative fallback height for a height-less plant record (#557)."""
    try:
        from open_garden_planner.core.plant_height_estimate import (
            ESTIMATED_HEIGHT_PARAM,
        )

        _est = record.params.get(ESTIMATED_HEIGHT_PARAM)
        if isinstance(_est, bool) or not isinstance(_est, (int, float)):
            return None
        _est = float(_est)
        return _est if _est > 0.0 else None
    except Exception:
        return None


def build_plant(record: Record) -> tuple[MeshPart, ...]:
    """The builder of the plant kinds (``register``).

    - a plant with a height: its recipe's silhouette, fitted to ``height_cm`` and
      the canopy radius ``params["radius_cm"]``, seeded from ``params["seed"]``;
    - a plant without a height but with an illustrative category fallback
      (``estimated_height_cm``, #557): the same silhouette at the fallback;
    - a plant without a height and without a fallback: ``placeholder_parts``;
    - anything else (not a plant kind, or no canopy circle): ``default_builder``.

    A record cannot hold a length beyond ``MAX_LENGTH_CM``; a height or canopy
    radius under ``MIN_SIZE_CM`` (a micrometre) raises ``ValueError`` as
    ``build_silhouette`` does — ``SceneSync`` contains it: that one item has no
    solid and is listed in ``failures``.

    Reads only the record's geometry part (``core.scene3d.build``).
    """
    plant = _plant_of(record)
    if plant is None:
        return default_builder(record)
    sprite, radius = plant
    height = record.height_cm
    if height is None:
        # Unknown height (#557): render the matching plant form at the
        # illustrative category fallback carried on the transient record.
        # The plan itself keeps height None; analytical sun/shade outputs
        # keep treating it as unknown.
        height = _estimated_fallback_cm(record)
        if height is None:
            return placeholder_parts(radius)
        from open_garden_planner.core.scene3d.record import MAX_LENGTH_CM

        if height > MAX_LENGTH_CM or radius > MAX_LENGTH_CM:
            return placeholder_parts(radius)
    seed = record.params.get(PARAM_SEED)
    return build_silhouette(recipe_for(sprite), item_seed(str(seed) if seed is not None else "", "plant"),
                            height, radius)


def register(registry: BuilderRegistry) -> None:
    """Register ``build_plant`` for every plant kind (``plant_art.PLANT_KINDS`` —
    the table ``plant_renderer.is_plant_type`` answers from)."""
    registry.register_many(sorted(PLANT_KINDS), build_plant)
