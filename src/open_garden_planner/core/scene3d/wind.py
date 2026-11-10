"""The wind's sway of a plant: the amplitude rule and the motion, as data (#800). Qt-free.

The shaders move every vertex of a plant by ONE function of the plant's own size, the
vertex's place in it and the wind's clock — ``plantSway`` in ``qml/foliage.vert``, its
screen door ``qml/foliage_door.vert`` and ``qml/plant_sway.vert`` (a plant's wood and
fruit). This module states that function in numpy (``sway_offsets``) so the rule can be
tested without a GPU; ``tests/unit/test_scene3d_wind.py`` pins the two to each other.

The rule (ADR-059 addendum "the wind that shows", #800):

- **The amplitude is a share of the plant's height** (``SWAY_SHARE``, 0.5 %) under a
  clear day's wind (``look.WIND_STRENGTH``), linear in the look's wind strength: a 9.5 m
  birch sways 4.75 cm at its top, a 1.7 m lilac 0.87 cm, a 60 cm basil 0.3 cm. Calm
  (strength 0) is still; the rain's 5.0 doubles it, the snow's 1.5 takes 0.6 of it.
- **A cantilever**: the displacement grows with the square of the height fraction, so a
  plant's foot stays where the plan puts it and its top moves most.
- **The whole plant leans downwind and swings about that lean** at its own frequency,
  lower the taller it is (``sway_frequency_hz``: 1.2 Hz at 1 m over the root of the
  height, 0.39 Hz for a 9.5 m tree, each plant within 10 % of that by its phase), with a
  slower figure-of-eight across the wind.
- **Branches**: the further out from the axis and the higher, the more (``BRANCH_SHARE``),
  by a field that is smooth in space — a twig and the leaves on it move together.
- **Leaves flutter** along their normal (``FLUTTER_SHARE``), at least 2 Hz, each at its
  own phase — never near a frame rate's Nyquist (at most 5.1 Hz: six frames a cycle at
  30 fps).
- **A gust** (``GUST_HZ``, 14 s) swells and eases the whole plant, travelling downwind
  across the garden, so neighbours are out of step; each plant also takes its own phase
  from its item id (``sway_frame``), never from its position.
- **At rest** (the clock at 0) nothing moves: every term is multiplied by the rest ramp
  (0 at 0 s, full from 2 s — the clock's rule since L1.4), so a still picture, a truth
  probe and the height and spread gates see the mesh as built.
- **Seamless at the clock's wrap**: ``Garden.qml`` wraps the clock from 3602 s to 2 s;
  every frequency is rounded to a whole number of cycles an hour (``hourly``).

Frame: the ENGINE frame (x = East, y = up, z = −North, cm), item-local positions as
``engine_buffers`` uploads them; the model matrix poses them (``frame.engine_model_matrix``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .build import item_seed
from .look import WIND_STRENGTH
from .mesh import MeshPart

#: Where the wind comes from: the west-south-west (a prevailing westerly). A look, not
#: meteorology — the falling particles drift the same way (``weather.py``).
WIND_FROM_DEG: Final = 250.0
#: The sway at a plant's top under a clear day's wind, as a share of its height.
SWAY_SHARE: Final = 0.005
#: The lean downwind, as a share of the swing (the swing swings about it).
LEAN: Final = 0.35
#: The swing across the wind, as a share of the swing along it.
ACROSS_SHARE: Final = 0.4
#: The branches' own sway at the crown's outer top, as a share of the amplitude.
BRANCH_SHARE: Final = 0.45
#: A leaf's flutter at the top, as a share of the amplitude.
FLUTTER_SHARE: Final = 0.25
#: The plant's swing: this many Hz for a plant 1 m tall, over the root of its height in m
#: (a cantilever whose thickness grows with its height), within ``SWAY_HZ_RANGE`` — and
#: each plant within ``SWAY_HZ_SPREAD`` of that by its phase, so two plants alike drift in
#: and out of step instead of swinging in a fixed relation.
SWAY_HZ_AT_1M: Final = 1.2
SWAY_HZ_RANGE: Final = (0.25, 2.5)
SWAY_HZ_SPREAD: Final = (0.9, 1.1)
#: Frequencies of the across swing and the branches, relative to the plant's swing.
ACROSS_OF_SWAY: Final = 0.71
BRANCH_OF_SWAY: Final = (1.9, 2.15, 1.65)
#: A leaf flutters at least this fast, and at least this many times the plant's swing,
#: each leaf within ``FLUTTER_SPREAD`` of that (by its phase).
FLUTTER_MIN_HZ: Final = 2.0
FLUTTER_OF_SWAY: Final = 1.6
FLUTTER_SPREAD: Final = (0.85, 1.15)
#: The gust: how slowly it comes and goes, how deep it is, and how fast it travels.
GUST_HZ: Final = 0.07
GUST_DEPTH: Final = 0.35
GUST_WAVE_PER_CM: Final = 0.0021
#: The clock's period: ``Garden.qml`` wraps the wind's clock from 3602 s to 2 s.
CLOCK_PERIOD_S: Final = 3600.0
#: The sway eases in over the clock's first seconds: exactly nothing at 0.
REST_RAMP_S: Final = 2.0

TAU: Final = 2.0 * math.pi

Floats = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class SwayFrame:
    """What the shaders know of the plant a part belongs to: its height and canopy radius
    (cm, from its own meshes — fitted to the data, so the data's) and its phase 0..1 (from
    its item id). ``NO_SWAY`` (height 0): the part does not sway."""

    height_cm: float
    radius_cm: float
    phase: float

    @property
    def sways(self) -> bool:
        return self.height_cm > 0.0

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.height_cm, self.radius_cm, self.phase)


NO_SWAY: Final = SwayFrame(0.0, 0.0, 0.0)

#: The material kinds a plant is made of and that sway with it (leaves; wood and fruit).
SWAY_KINDS: Final = frozenset({"foliage", "vc"})


def sway_frame(item_id: str, parts: Sequence[MeshPart]) -> SwayFrame:
    """The sway frame of an item made of ``parts``: an item with leaves (a part of the
    ``foliage`` kind: a plant, a hedge) sways as a whole — its height is the top of all
    its parts, its radius their farthest reach from its axis — and anything else does not.
    Every part of one item gets the same frame, so wood, leaves and fruit move together."""
    if not any(part.material_kind == "foliage" and part.mesh.vertex_count for part in parts):
        return NO_SWAY
    top = 0.0
    reach = 0.0
    for part in parts:
        if not part.mesh.vertex_count:
            continue
        positions = part.mesh.positions
        top = max(top, float(positions[:, 2].max()))
        reach = max(reach, float(np.hypot(positions[:, 0], positions[:, 1]).max()))
    if not (math.isfinite(top) and top > 0.0):
        return NO_SWAY
    phase = (item_seed(item_id, "sway") % 1_000_003) / 1_000_003.0
    return SwayFrame(top, max(reach, 1.0), phase)


def sway_amplitude_cm(height_cm: float, wind_strength: float = WIND_STRENGTH) -> float:
    """The sway at the top of a plant ``height_cm`` tall under ``wind_strength``."""
    return SWAY_SHARE * max(float(height_cm), 0.0) * max(float(wind_strength), 0.0) / WIND_STRENGTH


def sway_frequency_hz(height_cm: float, phase: float = 0.5) -> float:
    """How fast a plant ``height_cm`` tall with ``phase`` swings (before ``hourly`` rounds
    it); ``phase`` 0.5 is the middle of the spread."""
    low, high = SWAY_HZ_RANGE
    base = min(max(SWAY_HZ_AT_1M / math.sqrt(max(float(height_cm), 1.0) / 100.0), low), high)
    spread = SWAY_HZ_SPREAD[0] + (SWAY_HZ_SPREAD[1] - SWAY_HZ_SPREAD[0]) * float(phase)
    return base * spread


def hourly(hz: ArrayLike) -> Floats:
    """Angular frequency (rad/s) of ``hz`` rounded to a whole number of cycles in the
    clock's period: every term returns to itself where the clock wraps."""
    return np.asarray(TAU * np.floor(np.asarray(hz, dtype=np.float64) * CLOCK_PERIOD_S + 0.5)
                      / CLOCK_PERIOD_S)


def rest_ramp(time_s: float) -> float:
    """``smoothstep(0, REST_RAMP_S, t)``: 0 at rest, 1 from ``REST_RAMP_S`` on."""
    x = min(max(float(time_s) / REST_RAMP_S, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def wind_sway_scene(wind_strength: float) -> tuple[float, float]:
    """Downwind (east, north) in the garden, times the wind's strength over a clear
    day's — what the shaders' ``uWindSway`` is in the engine frame. (0, 0): calm."""
    scale = max(float(wind_strength), 0.0) / WIND_STRENGTH
    blowing = math.radians(WIND_FROM_DEG + 180.0)    # the wind blows TOWARDS this
    return (math.sin(blowing) * scale, math.cos(blowing) * scale)


def sway_offsets(points: ArrayLike, frame: SwayFrame, model: ArrayLike,
                 wind_sway_engine: ArrayLike, time_s: float, *,
                 leaf_phase: ArrayLike | None = None, normals: ArrayLike | None = None) -> Floats:
    """The shaders' displacement of item-local ENGINE-frame ``points`` (n, 3), cm, of a
    part with ``frame``, posed by the 4x4 ``model`` matrix, at the clock's ``time_s`` —
    the rest ramp included, so it is exactly 0 at 0 s. ``leaf_phase`` (n,) and
    ``normals`` (n, 3): a leaf's phase (its uv.y) and normal — given, the leaf flutters
    (``foliage.vert``); omitted, the part is wood or fruit (``plant_sway.vert``)."""
    p = np.atleast_2d(np.asarray(points, dtype=np.float64))
    out = np.zeros_like(p)
    wind_vec = np.asarray(wind_sway_engine, dtype=np.float64)
    wind = float(np.linalg.norm(wind_vec))
    if not frame.sways or wind <= 0.0:
        return out
    m = np.asarray(model, dtype=np.float64)
    h = frame.height_cm
    r = max(frame.radius_cm, 1.0)
    seed = TAU * frame.phase
    amp = SWAY_SHARE * h * wind
    t = float(time_s)
    origin = m[:3, 3]
    down = wind_vec / wind
    across = np.array([-down[2], 0.0, down[0]])
    hz = sway_frequency_hz(h, frame.phase)
    w = float(hourly(hz))
    gust = 1.0 - GUST_DEPTH + GUST_DEPTH * math.sin(
        float(hourly(GUST_HZ)) * t - GUST_WAVE_PER_CM * float(origin[0] * down[0] + origin[2] * down[2]) + seed)
    y = np.clip(p[:, 1] / h, 0.0, 1.0)
    swing = LEAN + math.sin(w * t + seed)
    cross = ACROSS_SHARE * math.sin(float(hourly(ACROSS_OF_SWAY * hz)) * t + seed + 1.7)
    body_world = (y * y)[:, None] * (down * swing + across * cross)[None, :]
    offset = body_world @ m[:3, :3]                 # world -> the model's own axes (GLSL v * M)
    reach = np.clip(np.hypot(p[:, 0], p[:, 2]) / r, 0.0, 1.0) * y
    b1, b2, b3 = (float(hourly(k * hz)) for k in BRANCH_OF_SWAY)
    offset[:, 0] += BRANCH_SHARE * reach * np.sin(b1 * t + 3.1 * p[:, 0] / r + 1.3 * p[:, 1] / h + seed)
    offset[:, 1] += BRANCH_SHARE * reach * 0.35 * np.sin(b2 * t + 2.3 * p[:, 2] / r + seed)
    offset[:, 2] += BRANCH_SHARE * reach * np.sin(b3 * t + 2.7 * p[:, 2] / r + 0.9 * p[:, 1] / h + seed)
    if leaf_phase is not None and normals is not None:
        lp = np.asarray(leaf_phase, dtype=np.float64).reshape(-1)
        n = np.atleast_2d(np.asarray(normals, dtype=np.float64))
        spread = FLUTTER_SPREAD[0] + (FLUTTER_SPREAD[1] - FLUTTER_SPREAD[0]) * np.mod(lp * 7.31, 1.0)
        fw = hourly(max(FLUTTER_MIN_HZ, FLUTTER_OF_SWAY * hz) * spread)
        offset += (FLUTTER_SHARE * y * np.sin(fw * t + TAU * lp * 13.0))[:, None] * n
    return np.asarray(amp * gust * rest_ramp(t) * offset)


__all__ = [
    "ACROSS_OF_SWAY", "ACROSS_SHARE", "BRANCH_OF_SWAY", "BRANCH_SHARE", "CLOCK_PERIOD_S",
    "FLUTTER_MIN_HZ", "FLUTTER_OF_SWAY", "FLUTTER_SHARE", "FLUTTER_SPREAD", "GUST_DEPTH",
    "GUST_HZ", "GUST_WAVE_PER_CM", "LEAN", "NO_SWAY", "REST_RAMP_S", "SWAY_HZ_AT_1M",
    "SWAY_HZ_RANGE", "SWAY_HZ_SPREAD", "SWAY_KINDS", "SWAY_SHARE", "SwayFrame", "WIND_FROM_DEG", "hourly",
    "rest_ramp", "sway_amplitude_cm", "sway_frame", "sway_frequency_hz", "sway_offsets",
    "wind_sway_scene",
]
