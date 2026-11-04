"""Hedges: a soft clipped block (Phase 17 L1.6).

``HEDGE_SECTION`` and ``HEDGE_POLYGON`` — and, through ``fences.py``, a polyline
in the ``HEDGE_FENCE`` style — are a dark core with a shell of micro-leaves on
top and sides (two triangles each, no alpha cards: ``ogp-lush-cinematic`` §2).

Truth:

- the top is TRIMMED at the hedge's height — a leaf that reaches above it is
  pushed down until its tip is on it, and the highest leaf sits exactly on it:
  a clipped hedge, and the mesh top is the plan's height by construction, not
  by a fit;
- no leaf goes below the ground (one that would is lifted out, whole);
- the core is the footprint drawn in by 4 cm and the leaves are rooted on it, so
  the block stays on its footprint (a leaf tip may reach a few centimetres past
  a corner);
- the seed is the item's id: two hedges are never clones, one hedge never
  changes between runs.

ONE part, kind ``foliage`` — core and leaves in one mesh, as on the L0 board:
the core is drawn with the foliage material too (a hedge's dark inside is not a
polished box: in a scratch render with the core in the plain material its flat
top shone tan against a low sun; in the foliage material it is darker, though
it still catches that light where leaves leave it bare). uv = (wind weight,
phase) for the sway shader; the core's is (0, 0), so it stands still. Leaf count follows the shell's
AREA — one leaf per 30 cm², 200 … 6,000 (the L0 board's hedge) — never a magic
number per hedge.
"""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import ArrayLike

from ..build import BuilderRegistry, item_seed
from ..mesh import Mesh, MeshPart
from ..record import PARAM_SEED, Record
from . import palette
from .common import BuiltBuilder, corner_count, footprint_of
from .primitives import (
    F64,
    ccw_ring,
    offset_ring,
    polygon_triangles,
    prism,
    quad_triangles,
    signed_area,
)

LEAF_LENGTH_CM: Final = 9.0
LEAF_WIDTH_CM: Final = 6.0
#: Shell area per leaf (cm²).
LEAF_AREA_CM2: Final = 30.0
MIN_LEAVES: Final = 200
MAX_LEAVES: Final = 6000
#: The core is the footprint drawn in by this much; leaves are rooted on it.
CORE_INSET_CM: Final = 4.0
#: The core's top lies this far under the clipped top; top leaves root halfway.
CORE_DROP_CM: Final = 3.0
#: Side leaves root at least this high (or 30 % of a low hedge): none lies on the ground.
SIDE_LEAF_MIN_Z_CM: Final = 9.5

Shell = tuple[F64, F64]  # triangles (t, 3, 3) and their outward normals (t, 3)


def leaf_count(shell_area_cm2: float) -> int:
    """Leaves for a shell of that area: coverage, clamped to a budget."""
    return int(np.clip(shell_area_cm2 / LEAF_AREA_CM2, MIN_LEAVES, MAX_LEAVES))


def core_ring(footprint: ArrayLike) -> F64:
    """The footprint drawn in by ``CORE_INSET_CM`` — or the footprint itself when
    it is too small to draw in (the inset would fold over)."""
    ring = ccw_ring(footprint)
    if len(ring) < 3:
        return ring
    inner = offset_ring(ring, -CORE_INSET_CM)
    span = ring.max(axis=0) - ring.min(axis=0)
    if float(span.min()) <= 4.0 * CORE_INSET_CM or signed_area(inner) <= 0.25 * signed_area(ring):
        return ring
    return inner


def ring_shell(ring: F64, height_cm: float) -> Shell:
    """The surface leaves grow on, for a block over ``ring``: its walls and its lid."""
    root = height_cm - CORE_DROP_CM / 2.0
    following = np.roll(ring, -1, axis=0)
    low = np.concatenate([ring, np.zeros((len(ring), 1))], axis=1)
    low_next = np.concatenate([following, np.zeros((len(ring), 1))], axis=1)
    lift = np.array([0.0, 0.0, root])
    walls = quad_triangles(np.stack([low, low_next, low_next + lift, low + lift], axis=1))
    edge = following - ring
    out = np.stack([edge[:, 1], -edge[:, 0], np.zeros(len(ring))], axis=1)
    out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
    lid_plan = polygon_triangles(ring)
    lid = np.concatenate([lid_plan, np.full((len(lid_plan), 3, 1), root)], axis=2)
    normals = np.concatenate([np.repeat(out, 2, axis=0), np.tile([0.0, 0.0, 1.0], (len(lid), 1))])
    return np.concatenate([walls, lid]), normals


def line_shell(line: F64, closed: bool, half_width_cm: float, height_cm: float) -> Shell:
    """The surface leaves grow on, for a block along a centre line: per segment its
    two sides and its top, and the two ends of an open line. Segment by segment —
    a closed line encloses nothing."""
    root = height_cm - CORE_DROP_CM / 2.0
    start = line if closed else line[:-1]
    end = np.roll(line, -1, axis=0) if closed else line[1:]
    travel = end - start
    travel /= np.maximum(np.linalg.norm(travel, axis=1, keepdims=True), 1e-12)
    left = np.stack([-travel[:, 1], travel[:, 0]], axis=1) * half_width_cm

    def at(points: F64, z: float) -> F64:
        return np.concatenate([points, np.full((len(points), 1), z)], axis=1)

    quads = [
        np.stack([at(start + left, 0.0), at(end + left, 0.0), at(end + left, root),
                  at(start + left, root)], axis=1),
        np.stack([at(start - left, 0.0), at(end - left, 0.0), at(end - left, root),
                  at(start - left, root)], axis=1),
        np.stack([at(start - left, root), at(end - left, root), at(end + left, root),
                  at(start + left, root)], axis=1),
    ]
    zero = np.zeros((len(start), 1))
    side = np.concatenate([left / half_width_cm, zero], axis=1)
    normals = [side, -side, np.tile([0.0, 0.0, 1.0], (len(start), 1))]
    if not closed:
        for point, offset, facing in ((start[:1], left[:1], -travel[:1]),
                                      (end[-1:], left[-1:], travel[-1:])):
            quads.append(np.stack([at(point - offset, 0.0), at(point + offset, 0.0),
                                   at(point + offset, root), at(point - offset, root)], axis=1))
            normals.append(np.concatenate([facing, np.zeros((1, 1))], axis=1))
    triangles = np.concatenate([quad_triangles(q) for q in quads])
    return triangles, np.concatenate([np.repeat(n, 2, axis=0) for n in normals])


def leaf_shell(shell: Shell, height_cm: float, seed: int, *, tinted: bool) -> Mesh:
    """Micro-leaves scattered over ``shell``, trimmed at ``height_cm``.

    Diamond leaves (4 vertices, 2 triangles) facing along the surface normal with
    a little scatter — ported from the spike's ``leaves`` (no spherize, no droop:
    a clipped hedge is a box). uv = (wind weight: root height / hedge height,
    phase). Colours: the hedge texture's four greens, darker low and lighter
    high; pure white when ``tinted`` (the item's colour is the hedge's).
    """
    triangles, normals = shell
    if not len(triangles) or height_cm <= 0.0:
        return Mesh.empty()
    # the bit generator by NAME: numpy may change what ``default_rng`` picks, and that
    # would reshuffle every hedge in every plan
    rng = np.random.Generator(np.random.PCG64(seed))
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    area = np.linalg.norm(cross, axis=1) / 2.0
    total = float(area.sum())
    if total <= 0.0:
        return Mesh.empty()
    count = leaf_count(total)
    face = rng.choice(len(triangles), size=count, p=area / total)
    r1, r2 = np.sqrt(rng.random(count)), rng.random(count)
    weights = np.stack([1.0 - r1, r1 * (1.0 - r2), r1 * r2], axis=1)
    root = (triangles[face] * weights[:, :, None]).sum(axis=1)
    outward = normals[face]
    on_side = outward[:, 2] < 0.5
    floor = min(SIDE_LEAF_MIN_Z_CM, 0.3 * height_cm)
    root[on_side, 2] = np.maximum(root[on_side, 2], floor)

    scale = min(1.0, height_cm / 40.0)  # a knee-high hedge has smaller leaves
    facing = outward + rng.normal(0.0, 0.35, (count, 3))
    facing /= np.maximum(np.linalg.norm(facing, axis=1, keepdims=True), 1e-9)
    scatter = rng.normal(0.0, 1.0, (count, 3))
    along = scatter - (scatter * facing).sum(axis=1, keepdims=True) * facing
    along /= np.maximum(np.linalg.norm(along, axis=1, keepdims=True), 1e-9)
    across = np.cross(along, facing)
    length, width = LEAF_LENGTH_CM * scale, LEAF_WIDTH_CM * scale
    leaf = np.stack([
        root,
        root + along * (length * 0.45) + across * (width * 0.5),
        root + along * length,
        root + along * (length * 0.45) - across * (width * 0.5),
    ], axis=1)  # (count, 4, 3)
    # The trim: a leaf that reaches above the hedge's height is pushed down until
    # its tip is ON the height, one that dips into the ground is lifted out — each
    # leaf whole, so it keeps its shape and its facing. The highest leaf of all
    # sits on the height, so the mesh top is the plan's number by construction.
    leaf[:, :, 2] -= np.maximum(leaf[:, :, 2].max(axis=1) - height_cm, 0.0)[:, None]
    leaf[:, :, 2] += np.maximum(-leaf[:, :, 2].min(axis=1), 0.0)[:, None]
    highest = int(leaf[:, :, 2].max(axis=1).argmax())
    leaf[highest, :, 2] += height_cm - float(leaf[highest, :, 2].max())
    positions = np.minimum(leaf.reshape(-1, 3), [np.inf, np.inf, height_cm])

    level = np.clip(root[:, 2] / height_cm, 0.0, 1.0)
    if tinted:
        colors = np.broadcast_to(np.asarray(palette.TINT), (count, 4))
    else:
        greens = np.asarray([leaf.linear for leaf in palette.HEDGE_LEAVES])
        tone = np.clip(np.floor(level * 2.0 + rng.random(count) * 2.4 - 0.2), 0, len(greens) - 1)
        colors = greens[tone.astype(np.int64)]
    uv = np.stack([level, rng.random(count)], axis=1)
    quad = np.array([0, 1, 2, 0, 2, 3])
    index = quad[None, :] + (np.arange(count) * 4)[:, None]
    return Mesh.from_arrays(positions, np.repeat(facing, 4, axis=0), np.repeat(colors, 4, axis=0),
                            np.repeat(uv, 4, axis=0), index.reshape(-1))


def seed_of(record: Record) -> int:
    """The item's own seed (``params["seed"]`` is the item id)."""
    return item_seed(str(record.params.get(PARAM_SEED, "")), "hedge")


def hedge_parts(core: Mesh, shell: Shell, height_cm: float, seed: int, *,
                tinted: bool) -> tuple[MeshPart, ...]:
    """Any hedge as its one part: the core, then the leaves, in one foliage mesh."""
    leaves = leaf_shell(shell, height_cm, seed, tinted=tinted)
    return (MeshPart(Mesh.merge([core, leaves]), "foliage", tinted=tinted, name="hedge"),)


def _hedge(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    ring = core_ring(footprint_of(record))
    if len(ring) < 3:
        return ()
    core = prism(ring, 0.0, max(height_cm - CORE_DROP_CM, 0.5 * height_cm),
                 palette.HEDGE_CORE.linear)
    return hedge_parts(core, ring_shell(ring, height_cm), height_cm, seed_of(record), tinted=False)


build_hedge: Final = BuiltBuilder(_hedge, "hedge")


def shell_area_cm2(shell: Shell) -> float:
    triangles = shell[0]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    return float(np.linalg.norm(cross, axis=1).sum() / 2.0)


def triangle_budget(record: Record) -> int:
    """The most triangles a hedge may have: two per leaf (never more than 6,000
    leaves) plus its core — 4 per footprint corner."""
    return 2 * MAX_LEAVES + 4 * max(corner_count(record), 3) + 40


def register(registry: BuilderRegistry) -> None:
    registry.register_many(("HEDGE_SECTION", "HEDGE_POLYGON"), build_hedge)
