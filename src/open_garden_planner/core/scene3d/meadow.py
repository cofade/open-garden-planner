"""The endless meadow around the plan (Phase 17 L4, #388). Qt-free.

The meadow is a square ``2 × MEADOW_HALF_CM`` wide (20 km; its edge lies in full fog,
its corners inside the workspace's 16 km far plane) centred on the plan, IN the plan's plane, with the plan's rectangle cut out —
less ``MEADOW_OVERLAP_CM`` on each side — and cut into cells of at most
``MEADOW_CELL_CM``. Nothing of it lies under the plan.

Two earlier forms lost the depth test to the plan's ground tiles. Both were ONE quad of
two triangles under the whole plan (3D review of #388), first 1 cm under it, then 5 cm.
A triangle 2 km across interpolates its depth with more than 5 cm of error at 55-90 m.
So from the workspace's default framing, a few wheel notches out, the meadow drew over
up to 52 % of the plan: the pond, the terraces and the paths were gone. The same quad
cut into 100 m cells lost no view. The 5 cm step also drew an ambient-occlusion line
along every plan edge (±14 luma), and the shadows that crossed the edge jumped there.

The strip under the plan's edge (``MEADOW_OVERLAP_CM``, 1 mm): the tiles' vertices along
the edge are not the meadow's, and an edge shared without its vertices can leave pixels
that neither side covers. In that strip the meadow and the plan are coplanar, and the
meadow wins; at 1 cm it took a visible centimetre of a surface painted to the edge.
Without a plan the square has no hole.

``meadow_frame`` builds the mesh in the scene frame (E, N, up), at the scene origin, with
the faces up. The host loads it into ONE geometry of the scene's one meadow Model
(``Quick3DHost``), as it loads the selection ring.

THE GRASS (#798, ADR-048 addendum). The meadow — and the plan's open ground, where the
look says so — is not one flat colour (on master 80 % of the default framing was flat
green: "a model on a green felt table"). It is the canvas's own GRASS texture
(``resources/textures/grass.png``, the 2D fill's picture: no new asset), laid in world
space at the canvas's scale (one texel a centimetre, ``GRASS_REPEAT_CM``), and a slow
variation over it (``GRASS_VARIATION``). ``grass_detail`` turns the texture into what
``ground.frag`` samples: its colour in LINEAR light (the engine's own polynomial) over
its own mean, so the surface's mean IS the meadow's albedo however the texture changes
and at every mip level (the mips of a linear, float texture average light; the mips of
the sRGB bytes would not: the far meadow would darken by the gap). ``MEADOW_ALBEDO`` is
the texture's linear mean by its derivation (L0); ``grass_mean_linear`` re-measures it.
"""

from __future__ import annotations

from typing import Final

import numpy as np

from .mesh import Mesh

#: Half the meadow's side, cm: 10 km, so its edge lies in full fog even at low pitch.
MEADOW_HALF_CM: Final = 1_000_000.0
#: The largest cell, cm. A 4 km quad of two triangles drew over the plan from the
#: default framing; cells of 100 m drew over it from no view (3D review of #388).
MEADOW_CELL_CM: Final = 10_000.0
#: How far the meadow reaches under the plan's edge, cm (module docstring). At 1 cm the
#: meadow won the strip's equal depth test and took the outer centimetre of a surface
#: painted up to the edge (4 px at 0.5 m); 1 mm shows none,
#: and no crack either.
MEADOW_OVERLAP_CM: Final = 0.1
#: A cell line this close to one of the plan's edges is dropped for the edge, cm.
_MERGE_CM: Final = 0.5


def meadow_frame(plan: tuple[float, float, float, float] | None) -> Mesh:
    """The meadow around ``plan`` = (east0, north0, east1, north1), scene cm, or the whole
    square around the scene origin for None (or for a plan narrower than twice the
    overlap). Faces up, white vertex colour."""
    hole: tuple[float, float, float, float] | None = None
    centre = (0.0, 0.0)
    if plan is not None:
        east0, north0, east1, north1 = (float(value) for value in plan)
        if not all(np.isfinite((east0, north0, east1, north1))):
            raise ValueError(f"a plan rectangle of finite numbers, got {plan!r}")
        centre = ((east0 + east1) / 2.0, (north0 + north1) / 2.0)
        inner = (east0 + MEADOW_OVERLAP_CM, north0 + MEADOW_OVERLAP_CM,
                 east1 - MEADOW_OVERLAP_CM, north1 - MEADOW_OVERLAP_CM)
        if inner[2] > inner[0] and inner[3] > inner[1]:
            hole = inner
    xs = _lines(centre[0], None if hole is None else (hole[0], hole[2]))
    ys = _lines(centre[1], None if hole is None else (hole[1], hole[3]))
    grid_x, grid_y = np.meshgrid(xs, ys)  # (len(ys), len(xs)), row = y
    positions = np.column_stack([grid_x.ravel(), grid_y.ravel(), np.zeros(grid_x.size)])
    columns = len(xs)
    cell_i, cell_j = np.meshgrid(np.arange(columns - 1), np.arange(len(ys) - 1))
    i, j = cell_i.ravel(), cell_j.ravel()
    if hole is not None:
        middle_x = (xs[i] + xs[i + 1]) / 2.0
        middle_y = (ys[j] + ys[j + 1]) / 2.0
        outside = ~((middle_x > hole[0]) & (middle_x < hole[2])
                    & (middle_y > hole[1]) & (middle_y < hole[3]))
        i, j = i[outside], j[outside]
    a = j * columns + i
    # counter-clockwise seen from above: (a, a+1, a+columns) and (a+1, a+columns+1, a+columns)
    triangles = np.concatenate([np.column_stack([a, a + 1, a + columns]),
                                np.column_stack([a + 1, a + columns + 1, a + columns])])
    count = len(positions)
    return Mesh.from_arrays(positions, np.tile([0.0, 0.0, 1.0], (count, 1)),
                            np.ones((count, 4)), np.zeros((count, 2)), triangles)


def _lines(middle: float, hole: tuple[float, float] | None) -> np.ndarray:
    """The grid's lines along one axis: every ``MEADOW_CELL_CM`` across the square, and
    the hole's two edges. A cell line within ``_MERGE_CM`` of an edge goes, never the
    edge: a cell line kept in its place would move the meadow's edge off the plan's and
    open a gap there."""
    steps = round(2.0 * MEADOW_HALF_CM / MEADOW_CELL_CM)
    at = middle - MEADOW_HALF_CM + MEADOW_CELL_CM * np.arange(steps + 1)
    if hole is not None:
        edges = np.asarray(hole, dtype=np.float64)
        near = np.abs(at[:, None] - edges[None, :]).min(axis=1) <= _MERGE_CM
        at = np.concatenate([at[~near], edges])
    return np.asarray(np.sort(at), dtype=np.float64)


# ── the grass (#798) ─────────────────────────────────────────────────────────

#: The grass texture's repeat, cm: the canvas paints a fill texture at one texel a
#: centimetre (``record.PATTERN_TILE_CM``), and ``ground.frag`` samples it at that scale
#: (and a second time turned 37° at 1.618 times it, so the repeat does not show).
GRASS_REPEAT_CM: Final = 256.0
#: The variation over the grass, as ``ground.frag``'s ``uMeadowVariation``: the
#: brightness's amplitude at 3.1 m, 9 m and 41 m and the hue's at 17 m (smooth value noise
#: in -1..1, mean 0, each octave turned another way so that no cell grid lines up; the
#: hue term moves red up and blue down, warmer and drier, or the other way, lusher). The
#: issue's proposal: about ±7 % brightness, ±4° hue. The 3.1 m octave stands in for the
#: texture's own mottle, which ``grass_detail`` takes out because it repeats.
#: ``ground.frag`` fades each octave as a pixel's reach on the ground grows from 0.05 to
#: 0.15 of its wavelength (``meadowOctave``): a value noise has no mips.
GRASS_VARIATION: Final = (0.04, 0.06, 0.07, 0.035)
#: The grass's own mottle — what it holds beyond this many centimetres (the sigma of the
#: Gaussian taken out) — repeats with the texture every 2.56 m and drew a lattice over the
#: meadow seen from above (correlation 0.34 one repeat away, 0.03 elsewhere); the blades
#: stay. ``GRASS_VARIATION``'s octaves take its place, and repeat nowhere.
GRASS_HIGH_PASS_CM: Final = 16.0
#: How strongly the grass's relief tilts the detail normal, per unit of ``uDetail``: the
#: texture is a LINEAR ratio (mean 1), where the tiles read sRGB codes (0..1, the grass
#: about 0.43 at its mean, and a linear ratio swings about 2.2 times as far as its code),
#: so the meadow's relief matches a lawn painted with the same texture at ~0.43 / 2.2.
GRASS_RELIEF: Final = 0.2

#: Qt Quick 3D's linearisation of an sRGB channel (``ground.frag``'s ``groundLinear``):
#: a polynomial, not the sRGB curve (``ogp-3d-renderer`` section 14).
_ENGINE_POLY: Final = (0.305306011, 0.682171111, 0.012522878)


def engine_linear(codes: np.ndarray) -> np.ndarray:
    """sRGB channel values (0..1) as the engine linearises them — ``ground.frag``'s
    ``groundLinear``, the numbers the tiles and the meadow are lit with."""
    a, b, c = _ENGINE_POLY
    values = np.asarray(codes, dtype=np.float64)
    return np.asarray(values * (values * (values * a + b) + c))


def grass_mean_linear(rgba8: np.ndarray) -> np.ndarray:
    """The mean colour of a texture (``(h, w, 4)`` RGBA8 codes) in linear light, as the
    engine linearises it — per channel, rgb."""
    pixels = np.asarray(rgba8, dtype=np.float64)[..., :3] / 255.0
    return np.asarray(engine_linear(pixels).reshape(-1, 3).mean(axis=0))


def high_pass_wrapped(values: np.ndarray, sigma: float) -> np.ndarray:
    """``values`` (h x w) less its Gaussian blur of ``sigma`` pixels, the image repeated
    on every side (it is a tileable texture): the same mean, nothing slower than ~sigma."""
    data = np.asarray(values, dtype=np.float64)
    rows, cols = data.shape
    fy = np.fft.fftfreq(rows)[:, None]
    fx = np.fft.rfftfreq(cols)[None, :]
    keep = np.exp(-2.0 * (np.pi * sigma) ** 2 * (fx * fx + fy * fy))
    blurred = np.fft.irfft2(np.fft.rfft2(data) * keep, s=data.shape)
    return np.asarray(data - blurred + blurred.mean())


def grass_detail(rgba8: np.ndarray) -> np.ndarray:
    """What ``ground.frag`` samples as ``uGrass``: the texture's linear colour over its
    own mean, per channel (mean exactly 1), less its mottle (``GRASS_HIGH_PASS_CM``),
    alpha 1 — float32 ``(h, w, 4)``, rows as the image's. A texture without light in a
    channel is refused (its mean would be 0)."""
    pixels = np.asarray(rgba8)
    if pixels.ndim != 3 or pixels.shape[2] != 4 or pixels.shape[0] < 1 or pixels.shape[1] < 1:
        raise ValueError(f"an (h, w, 4) RGBA image, got shape {pixels.shape}")
    linear = engine_linear(pixels[..., :3].astype(np.float64) / 255.0)
    mean = linear.reshape(-1, 3).mean(axis=0)
    if not np.all(mean > 0.0):
        raise ValueError(f"a texture with light in every channel, got a linear mean {mean}")
    out = np.ones(pixels.shape[:2] + (4,), dtype=np.float32)
    for channel in range(3):
        detail = high_pass_wrapped(linear[..., channel] / mean[channel], GRASS_HIGH_PASS_CM)
        out[..., channel] = np.maximum(detail, 0.02)
    return out


def grass_detail_rgba16f(rgba8: np.ndarray) -> bytes:
    """``grass_detail`` as the bytes of an RGBA16F texture (little-endian half floats)."""
    return grass_detail(rgba8).astype("<f2").tobytes()


__all__ = ["GRASS_HIGH_PASS_CM", "GRASS_RELIEF", "GRASS_REPEAT_CM", "GRASS_VARIATION",
           "MEADOW_CELL_CM",
           "MEADOW_HALF_CM", "MEADOW_OVERLAP_CM", "engine_linear", "grass_detail",
           "grass_detail_rgba16f", "grass_mean_linear", "high_pass_wrapped", "meadow_frame"]
