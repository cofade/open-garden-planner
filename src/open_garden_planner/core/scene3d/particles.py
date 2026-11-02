"""Rain, snow, falling leaves, butterflies and fireflies as data (Phase 17 L5.2, #389,
ADR-070). Qt-free (stdlib + numpy).

THE PARTICLES ARE GEOMETRY THAT A SHADER MOVES. There is no particle simulation on
the CPU and no particle module of the engine: every particle is a quad whose
vertices carry its seeds, and the vertex shaders (``qml/precipitation.vert``,
``qml/ambient.vert``) put it where it is at the shaders' clock — the wind's clock of
L1.4 (``windTime``). So the animation policy that runs the wind runs the particles:
hidden, nothing ticks; reduced motion RESTS the clock at 0 and every particle stands
still where its seed puts it — a photograph, and an idle view presents no frame.

Two buffers, each loaded into ONE Model of the scene for its whole life (like the
selection ring and the analysis overlays — ADR-060: a destroyed Model leaves graphics
state behind):

- **precipitation** (``precipitation_buffers``) — ``PRECIP_COUNT`` quads with unit
  seeds, the same for every plan; the shader lays them out in a volume around the
  camera's target, as rain streaks or snowflakes (``AtmosphereSpec.precipitation``),
  world-anchored (they wrap at the volume's edges, so orbiting does not drag them).
- **ambient life** (``ambient_buffers``) — the plan's own: falling leaves under the
  deciduous trees and shrubs that are dropping them on the plan date, butterflies at
  the plants in flower, fireflies among the plants on a summer night — and the glowing
  bulbs of the garden lights (L5.4, ``core/scene3d/lights.py``). WHICH plants is
  ``ambient_emitters``, from the records and their phenology (L3); WHEN — by day,
  dry, at dusk — is the look's (``AtmosphereSpec.leaves`` / ``butterflies`` /
  ``fireflies``), a uniform, so the time of day never rebuilds a buffer.

THE BUDGET: at most ``MAX_PARTICLES`` (5,000, issue #389) — the precipitation's count
plus every ambient cap; pinned by a test.

VERTEX LAYOUT — the package's one layout (``interleave.py``), with the slots carrying
particle parameters instead of a mesh's (documented per buffer below). Positions that
are places in the garden go through ``frame.scene_to_engine_points`` — THE frame
mapping, once, as for every mesh; seeds are not places and are not mapped.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final

import numpy as np

from .frame import scene_to_engine_points
from .interleave import VERTEX_STRIDE, EngineBuffers

if TYPE_CHECKING:
    from ..phenology import PhenologyState
    from .record import Record

__all__ = [
    "AMBIENT_KINDS", "BULB_CODE", "BUTTERFLY_CODE", "FIREFLY_CODE", "LEAF_CODE", "MAX_BULBS",
    "MAX_BUTTERFLIES", "MAX_FIREFLIES", "MAX_LEAVES", "MAX_PARTICLES", "PRECIP_COUNT", "Emitter",
    "ParticleVolume", "ambient_buffers", "ambient_emitters", "ambient_particle_count",
    "is_firefly_season", "precipitation_buffers", "precipitation_volume",
]

#: Issue #389's budget for every particle the scene can draw at once.
MAX_PARTICLES: Final = 5_000
#: Raindrops or snowflakes — one buffer for both (a frame has one precipitation).
PRECIP_COUNT: Final = 3_600
#: The ambient caps: the plan's emitters share them. The glowing bulbs of the garden
#: lights (L5.4) are particles of the same buffer: ``lights.MAX_BULBS`` (360).
MAX_LEAVES: Final = 560
MAX_BUTTERFLIES: Final = 80
MAX_FIREFLIES: Final = 360
MAX_BULBS: Final = 360
AMBIENT_KINDS: Final = ("leaf", "butterfly", "firefly", "bulb")
#: The kind of an ambient particle, as ``ambient.vert`` reads it from the colour's
#: alpha: ``int(alpha * 4)`` = 0, 1, 2, 3.
LEAF_CODE: Final = 0.125
BUTTERFLY_CODE: Final = 0.375
FIREFLY_CODE: Final = 0.625
BULB_CODE: Final = 0.875
_CODES: Final = {"leaf": LEAF_CODE, "butterfly": BUTTERFLY_CODE, "firefly": FIREFLY_CODE,
                 "bulb": BULB_CODE}
#: Vertices per particle: a quad — a butterfly is two (its wings).
_CORNERS: Final = {"leaf": 4, "butterfly": 8, "firefly": 4, "bulb": 4}
_FLOATS: Final = VERTEX_STRIDE // 4
#: The precipitation buffer's bounds: far beyond anything the camera frames (the
#: shader places the drops, the engine culls by what it is told).
_FAR_CM: Final = 1.0e6

# ── the precipitation ────────────────────────────────────────────────────────


def _quads(count: int) -> np.ndarray:
    """``count`` quads' indices: corners 0 1 2 / 0 2 3, counter-clockwise."""
    base = (np.arange(count, dtype=np.uint32) * 4)[:, None]
    return (base + np.array((0, 1, 2, 0, 2, 3), dtype=np.uint32)[None, :]).reshape(-1)


def _pack(vertices: np.ndarray, indices: np.ndarray,
          low: tuple[float, float, float], high: tuple[float, float, float]) -> EngineBuffers:
    vertices = np.ascontiguousarray(vertices, dtype="<f4")
    indices = np.ascontiguousarray(indices, dtype="<u4")
    return EngineBuffers(vertex_data=vertices.tobytes(), index_data=indices.tobytes(),
                         vertex_count=int(vertices.shape[0]), index_count=int(indices.size),
                         bounds_min=low, bounds_max=high)


def precipitation_buffers(count: int = PRECIP_COUNT, seed: int = 389) -> EngineBuffers:
    """The precipitation's ONE buffer (module docstring): ``count`` quads, seeded.

    Per vertex — the four corners of a particle share all but the corner:

    - position: the particle's seed in the unit cube (x across, y the fall's phase,
      z along) — NOT a place: the shader lays it into the volume;
    - normal: (phase, speed jitter, size jitter), each 0..1;
    - colour: (tint jitter r, g, b — around 1 — and the particle's rank 0..1: the
      shader draws the ranks under ``precipDensity``);
    - uv: (corner 0..3, 0).
    """
    if count < 0 or count > PRECIP_COUNT:
        raise ValueError(f"a precipitation has 0..{PRECIP_COUNT} particles, got {count!r}")
    rng = np.random.default_rng(seed)
    seeds = rng.random((count, 3))
    params = rng.random((count, 3))
    tint = 1.0 + (rng.random((count, 3)) - 0.5) * 0.12
    rank = (np.arange(count) + rng.random(count)) / max(count, 1)
    rng.shuffle(rank)
    per = np.empty((count, _FLOATS))
    per[:, 0:3] = seeds
    per[:, 3:6] = params
    per[:, 6:9] = tint
    per[:, 9] = rank
    per[:, 11] = 0.0
    vertices = np.repeat(per, 4, axis=0)
    vertices[:, 10] = np.tile(np.arange(4, dtype=np.float64), count)
    return _pack(vertices, _quads(count), (-_FAR_CM, -_FAR_CM, -_FAR_CM),
                 (_FAR_CM, _FAR_CM, _FAR_CM))


@dataclass(frozen=True, slots=True)
class ParticleVolume:
    """Where the precipitation falls: a box around the camera's target, scene frame —
    its centre on the ground, ``size_cm`` across in E and N, ``height_cm`` tall."""

    center_scene: tuple[float, float]
    size_cm: float
    height_cm: float


#: The precipitation's box: 1.4x the camera's distance to its target across, never
#: under 16 m nor over 80 m; half as tall, 8 to 25 m.
_VOLUME_SHARE: Final = 1.4
_VOLUME_MIN_CM, _VOLUME_MAX_CM = 1_600.0, 8_000.0
_HEIGHT_MIN_CM, _HEIGHT_MAX_CM = 800.0, 2_500.0


def precipitation_volume(eye_scene: tuple[float, float, float],
                         target_scene: tuple[float, float, float]) -> ParticleVolume:
    """The volume the precipitation falls in for a camera at ``eye_scene`` looking at
    ``target_scene`` (scene frame, cm): around the point it looks at, as wide as it
    sees there (walk mode: the walker's gaze point, a few metres ahead)."""
    distance = math.dist(eye_scene, target_scene)
    if not math.isfinite(distance):
        raise ValueError(f"a camera at finite points, got {eye_scene!r} -> {target_scene!r}")
    size = min(max(_VOLUME_SHARE * distance, _VOLUME_MIN_CM), _VOLUME_MAX_CM)
    height = min(max(0.5 * size, _HEIGHT_MIN_CM), _HEIGHT_MAX_CM)
    return ParticleVolume((float(target_scene[0]), float(target_scene[1])), size, height)


# ── the ambient life ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Emitter:
    """Where one kind of life lives around one plant, scene frame (cm)."""

    kind: str
    item_id: str
    east_cm: float
    north_cm: float
    #: The crown's top above the scene ground: leaves start here, butterflies hover
    #: over it, fireflies stay below it.
    top_cm: float
    #: The soil the plant stands on (its ``base_cm``): where a leaf lands.
    base_cm: float
    radius_cm: float
    count: int
    color_linear: tuple[float, float, float] = (1.0, 1.0, 1.0)

    def __post_init__(self) -> None:
        if self.kind not in AMBIENT_KINDS:
            raise ValueError(f"an emitter's kind is one of {AMBIENT_KINDS}, got {self.kind!r}")
        if self.count < 0 or not all(math.isfinite(v) for v in (
                self.east_cm, self.north_cm, self.top_cm, self.base_cm, self.radius_cm)):
            raise ValueError(f"an emitter needs a count >= 0 and finite numbers: {self!r}")


#: Northern summer months — the southern hemisphere's are six months on.
_SUMMER_NORTH: Final = frozenset({6, 7, 8})
_SUMMER_SOUTH: Final = frozenset({12, 1, 2})
#: A tree or shrub drops its leaves while it has between these shares of them left
#: and has turned (``PhenologyState.autumn_color``).
_DROPPING: Final = (0.03, 0.97)
_TURNED: Final = 0.2
#: A plant is in flower from this ``bloom`` up — and a butterfly visits it when its
#: flowers are within reach: a tall tree's crown is not where they flutter (board, L5).
_IN_FLOWER: Final = 0.35
_FLOWER_HEIGHT_MAX_CM: Final = 350.0
#: The autumn leaves' palette (linear): amber, rust, ochre, a late green.
LEAF_PALETTE: Final = ((0.62, 0.27, 0.04), (0.45, 0.11, 0.03), (0.52, 0.38, 0.07),
                       (0.30, 0.33, 0.06))
#: The butterflies' wings (linear): a white, a brimstone yellow, a peacock orange, a blue.
BUTTERFLY_PALETTE: Final = ((0.86, 0.86, 0.80), (0.90, 0.80, 0.18), (0.80, 0.30, 0.05),
                            (0.20, 0.36, 0.85))


def is_firefly_season(plan_date: date, latitude_deg: float) -> bool:
    """Midsummer on the plan's hemisphere: June–August north of the equator,
    December–February south of it."""
    return plan_date.month in (_SUMMER_SOUTH if latitude_deg < 0.0 else _SUMMER_NORTH)


def _plant_size(record: Record) -> tuple[float, float] | None:
    """(canopy radius, height) of a plant record, as the plant builder builds it — the
    record's height or its illustrative fallback (#557); None for no plant shape."""
    from .builders.plants import _estimated_fallback_cm, plant_sprite
    from .record import PARAM_RADIUS_CM

    if plant_sprite(record) is None:
        return None
    radius = record.params.get(PARAM_RADIUS_CM)
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not radius > 0.0:
        return None
    height = record.height_cm if record.height_cm is not None else _estimated_fallback_cm(record)
    if height is None or not math.isfinite(float(radius)) or not math.isfinite(height):
        return None
    return float(radius), float(height)


def _share(weights: list[float], budget: int, *, at_least: int = 1) -> list[int]:
    """``budget`` split by ``weights`` (largest remainder), ``at_least`` each while the
    budget lasts — deterministic for the same input."""
    if not weights or budget <= 0:
        return [0] * len(weights)
    floor = min(at_least, budget // len(weights))
    counts = [floor] * len(weights)
    left = budget - floor * len(weights)
    total = sum(weights)
    if left <= 0 or total <= 0.0:
        return counts
    exact = [w / total * left for w in weights]
    extra = [int(math.floor(e)) for e in exact]
    remainder = left - sum(extra)
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - extra[i]), i))
    for i in order[:remainder]:
        extra[i] += 1
    return [c + e for c, e in zip(counts, extra, strict=True)]


def ambient_emitters(records: Iterable[Record], seasons: Mapping[str, PhenologyState],
                     plan_date: date, latitude_deg: float) -> tuple[Emitter, ...]:
    """The plan's life on ``plan_date`` (module docstring): falling leaves under every
    tree and shrub that is dropping them, butterflies at the plants in flower, and in
    midsummer fireflies among the plants. Counts within ``MAX_LEAVES`` /
    ``MAX_BUTTERFLIES`` / ``MAX_FIREFLIES``, shared by size; sorted by item id, so the
    same plan and date give the same emitters."""
    plants: list[tuple[Record, float, float]] = []
    for record in sorted(records, key=lambda r: r.item_id):
        size = _plant_size(record)
        if size is not None:
            plants.append((record, *size))
    leaves = [(r, rad, h) for r, rad, h in plants
              if r.kind in ("TREE", "SHRUB") and (state := seasons.get(r.item_id)) is not None
              and _DROPPING[0] < state.leaf_density < _DROPPING[1]
              and state.autumn_color > _TURNED]
    flowering = [(r, rad, h) for r, rad, h in plants
                 if (state := seasons.get(r.item_id)) is not None and state.bloom >= _IN_FLOWER
                 and h <= _FLOWER_HEIGHT_MAX_CM]
    flowering = sorted(flowering, key=lambda p: (-seasons[p[0].item_id].bloom, p[0].item_id))
    flowering = sorted(flowering[:MAX_BUTTERFLIES], key=lambda p: p[0].item_id)
    lights = plants if is_firefly_season(plan_date, latitude_deg) else []

    out: list[Emitter] = []

    def add(kind: str, group: list[tuple[Record, float, float]], counts: list[int]) -> None:
        for (record, radius, height), count in zip(group, counts, strict=True):
            if count <= 0:
                continue
            t = record.transform
            out.append(Emitter(kind, record.item_id, float(t.east_cm), float(t.north_cm),
                               float(t.base_cm) + height, float(t.base_cm), radius, count))

    add("leaf", leaves, _share([r * r for _r, r, _h in leaves], MAX_LEAVES, at_least=3))
    add("butterfly", flowering,
        _share([1.0 + (r > 60.0) for _r, r, _h in flowering], MAX_BUTTERFLIES))
    add("firefly", lights, _share([r for _r, r, _h in lights], MAX_FIREFLIES, at_least=0))
    return tuple(out)


def ambient_particle_count(emitters: Iterable[Emitter]) -> int:
    """How many particles ``emitters`` make (a butterfly is one particle, two quads)."""
    return sum(emitter.count for emitter in emitters)


def _stable_seed(*parts: object) -> int:
    return zlib.crc32("|".join(str(part) for part in parts).encode("utf-8"))


def ambient_buffers(emitters: Iterable[Emitter]) -> EngineBuffers:
    """The ambient life's ONE buffer (module docstring) — empty for no emitters.

    Per vertex — the corners of a particle share all but the corner:

    - position: the emitter's centre at its crown's top, ENGINE frame (mapped by
      ``scene_to_engine_points``, the frame mapping);
    - normal: (phase 0..1, speed 0..1, the emitter's radius in cm — a bulb's glow);
    - colour: (linear rgb of the particle, its kind's code — ``LEAF_CODE`` …);
    - uv: (corner — 0..3, a butterfly's 0..7 —, the soil's height, engine y = up).
    """
    rows: list[np.ndarray] = []
    corners: list[np.ndarray] = []
    quads = 0
    low = np.full(3, np.inf)
    high = np.full(3, -np.inf)
    for index, emitter in enumerate(emitters):
        if emitter.count <= 0:
            continue
        rng = np.random.default_rng(_stable_seed(emitter.kind, emitter.item_id, index))
        center = scene_to_engine_points(np.array(
            [[emitter.east_cm, emitter.north_cm, emitter.top_cm]], dtype=np.float64))[0]
        n = emitter.count
        per = np.empty((n, _FLOATS))
        per[:, 0:3] = center
        per[:, 3] = rng.random(n)
        per[:, 4] = rng.random(n)
        per[:, 5] = emitter.radius_cm
        palette = {"leaf": LEAF_PALETTE, "butterfly": BUTTERFLY_PALETTE}.get(
            emitter.kind, ((1.0, 1.0, 1.0),))
        pick = rng.integers(0, len(palette), n)
        per[:, 6:9] = np.asarray(palette, dtype=np.float64)[pick] * np.asarray(
            emitter.color_linear, dtype=np.float64)
        per[:, 9] = _CODES[emitter.kind]
        per[:, 11] = emitter.base_cm                       # engine y = scene up
        k = _CORNERS[emitter.kind]
        rows.append(np.repeat(per, k, axis=0))
        corners.append(np.tile(np.arange(k, dtype=np.float64), n))
        quads += n * (k // 4)
        reach = emitter.radius_cm + 300.0
        low = np.minimum(low, center - reach)
        high = np.maximum(high, center + reach)
        low[1] = min(low[1], emitter.base_cm - 10.0)
        high[1] = max(high[1], center[1] + 300.0)
    if not rows:
        return _pack(np.zeros((0, _FLOATS)), np.zeros(0, dtype=np.uint32), (0.0, 0.0, 0.0),
                     (0.0, 0.0, 0.0))
    vertices = np.concatenate(rows)
    vertices[:, 10] = np.concatenate(corners)
    return _pack(vertices, _quads(quads), (float(low[0]), float(low[1]), float(low[2])),
                 (float(high[0]), float(high[1]), float(high[2])))
