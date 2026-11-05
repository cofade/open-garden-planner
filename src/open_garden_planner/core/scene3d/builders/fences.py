"""The fences, one per fence style (Phase 17 L1.6).

Geometry only: which polyline becomes which fence is decided in ``lines.py``.

=================  =========================================================
``WOODEN_FENCE``   posts, two rails, pickets
``METAL_FENCE``    slim posts, two rails, square bars with spear tips
``CHAIN_LINK``     posts, a top rail, a diamond mesh of wires
``HEDGE_FENCE``    a hedge block along the line (``hedges.py``)
``PLAIN``          a plain panel: the drawn stroke, as wide as it is drawn,
                   up to the height — what a line in a style no builder knows
                   is built as. Nothing is invented for it.
=================  =========================================================

(The fifth fence style, ``STONE_WALL``, is the wall of ``walls.py``.)

Everything is built from the polyline's centre line, along its smooth spans (a vertex
turning less than ``CORNER_DEG`` is part of a span): posts, pickets and bars are spaced
by ARC LENGTH, so a filleted corner keeps the straight runs' spacing instead of one post
per 2 cm sampled step (#675). The rails stay one box per drawn segment — together they
follow the arc. Never from the stroke outline in ``record.footprints``: a fence round a
garden is a closed loop — one outer ring with the garden as its hole (``record.holes``) —
and nothing may stand over that hole (``build.verify_builder`` refuses it).

Colour: in 2D every style paints from the item's own stroke colour (the style
table only pre-sets it), so every part is ``tinted`` — pure white vertices the
sink multiplies with the record's material. A recolour never rebuilds a fence.

The plan holds no cross-section for a fence — its stroke is a line weight
(2–3 cm). Posts, rails and pickets have the L0 board's sizes; a stroke drawn
wider than a post widens the posts. The POSTS are the top: exactly the height.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

import numpy as np

from ..mesh import Mesh, MeshPart
from ..record import ParamValue, Record
from .hedges import (
    CORE_DROP_CM,
    CORE_INSET_CM,
    MAX_LEAVES,
    hedge_parts,
    line_shell,
    seed_of,
)
from .palette import TINT
from .primitives import F64, bevelled_boxes, boxes, sweep, tubes

#: The ``PathFenceStyle`` names of the "fence" category (the others are paths).
#: A mirror — ``core/object_types.py`` imports Qt — pinned against
#: ``PATH_FENCE_STYLES`` by ``tests/unit/test_scene3d_builders_palette.py``: a
#: fence style added there fails that test until a builder is chosen for it here.
FENCE_STYLES: Final = frozenset(
    {"WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK", "HEDGE_FENCE", "STONE_WALL"}
)
#: What a FENCE that carries NO style is built as (the L0 board's fence).
DEFAULT_FENCE_STYLE: Final = "WOODEN_FENCE"
#: What a line in a style no builder knows is built as: its stroke, to the height.
PLAIN: Final = "PLAIN"
#: The stroke strip of a plain panel is at least this wide (cm).
PLAIN_MIN_WIDTH_CM: Final = 1.0

# picket fence (the spike's ``polyline_posts_and_pickets``)
POST_CM: Final = 9.0
POST_SPACING_CM: Final = 200.0
POST_BEVEL_CM: Final = 1.0
RAIL_ACROSS_CM: Final = 4.0
RAIL_TALL_CM: Final = 6.0
PICKET_PITCH_CM: Final = 12.0
PICKET_WIDE_CM: Final = PICKET_PITCH_CM * 0.62
PICKET_THICK_CM: Final = 2.2
# metal fence
METAL_POST_CM: Final = 4.0
METAL_RAIL_CM: Final = 2.5
METAL_BAR_CM: Final = 1.6
METAL_BAR_PITCH_CM: Final = 11.0
# chain link
CHAIN_POST_CM: Final = 5.0
CHAIN_POST_SPACING_CM: Final = 250.0
CHAIN_RAIL_CM: Final = 3.0
CHAIN_WIRE_RADIUS_CM: Final = 0.4
CHAIN_WIRE_PITCH_CM: Final = 25.0
# hedge fence
HEDGE_THICKNESS_CM: Final = 40.0


def is_fence_style(style: ParamValue | None) -> bool:
    return isinstance(style, str) and style in FENCE_STYLES


#: A vertex whose turn is at least this many degrees is a corner. Short of it the
#: polyline is a smooth span (a filleted corner is a dense run of 2-5 degree turns),
#: and posts/pickets are spaced by ARC LENGTH across the whole span, not per segment —
#: otherwise every 2 cm arc segment gets its own two posts and the corner becomes a
#: solid block of planks (#675). A real corner (90 degrees, a chamfer's 45) exceeds it.
CORNER_DEG: Final = 20.0


class _Arc:
    """A smooth span of a ``_Run``: its points and the angle of each segment."""

    def __init__(self, points: F64, angle: F64) -> None:
        self.points = points
        step = points[1:] - points[:-1]
        self.length = np.linalg.norm(step, axis=1)
        self.cum = np.concatenate([[0.0], np.cumsum(self.length)])
        self.angle = angle

    @property
    def total(self) -> float:
        return float(self.cum[-1])

    def at(self, distance: F64) -> tuple[F64, F64]:
        """Plan points ``distance`` cm along the arc, and their segment angles."""
        values = np.asarray(distance, dtype=np.float64)
        index = np.clip(np.searchsorted(self.cum, values, side="left") - 1,
                        0, len(self.length) - 1)
        fraction = (values - self.cum[index]) / np.maximum(self.length[index], 1e-12)
        points = self.points[index] + (self.points[index + 1] - self.points[index]) * fraction[:, None]
        return points, self.angle[index]


class _Run:
    """A centre line as its smooth arcs (``CORNER_DEG`` splits them)."""

    def __init__(self, line: F64, closed: bool) -> None:
        self.closed = closed
        self.line = line
        self.start = line if closed else line[:-1]
        end = np.roll(line, -1, axis=0) if closed else line[1:]
        step = end - self.start
        self.length = np.linalg.norm(step, axis=1)
        self.along = step / np.maximum(self.length, 1e-12)[:, None]
        self.angle = np.degrees(np.arctan2(self.along[:, 1], self.along[:, 0]))
        self.count = len(self.start)

    def _turn(self, vertex: int) -> float:
        """The turn at a vertex, degrees (0 = straight on, 180 = doubled back)."""
        incoming = vertex - 1 if vertex > 0 else self.count - 1
        cosine = float(np.clip(np.dot(self.along[incoming], self.along[vertex]), -1.0, 1.0))
        return math.degrees(math.acos(cosine))

    def arcs(self) -> list[_Arc]:
        """The smooth spans between real corners, in line order."""
        if self.count == 0:
            return []
        if not self.closed:
            corners = [index for index in range(1, self.count)
                       if self._turn(index) >= CORNER_DEG]
            breaks = [0, *corners, self.count]
            return [self._arc(breaks[index], breaks[index + 1] - breaks[index], False)
                    for index in range(len(breaks) - 1)]
        corners = [index for index in range(self.count) if self._turn(index) >= CORNER_DEG]
        if not corners:
            return [self._arc(0, self.count, True)]
        arcs: list[_Arc] = []
        for index, start in enumerate(corners):
            end = corners[(index + 1) % len(corners)]
            count = (end - start) % self.count or self.count
            arcs.append(self._arc(start, count, True))
        return arcs

    def _arc(self, start: int, count: int, wrap: bool) -> _Arc:
        if wrap:
            points = self.line[(start + np.arange(count + 1)) % self.count]
            angles = self.angle[(start + np.arange(count)) % self.count]
        else:
            points = self.line[start:start + count + 1]
            angles = self.angle[start:start + count]
        return _Arc(points, angles)

    def posts(self, spacing: float) -> tuple[F64, F64]:
        """Post centres and their segments' angles: one at every real corner and every
        ``spacing`` cm at most ALONG each smooth span, a shared corner only once."""
        out: list[F64] = []
        angles: list[F64] = []
        for index, arc in enumerate(self.arcs()):
            total = arc.total
            if total <= 0.0:
                continue
            number = max(1, int(math.ceil(total / spacing - 1e-9)))
            first = 0 if (not self.closed and index == 0) else 1
            points, angle = arc.at(np.arange(first, number + 1) * (total / number))
            out.append(points)
            angles.append(angle)
        if not out:
            return np.zeros((0, 2)), np.zeros(0)
        return np.concatenate(out), np.concatenate(angles)

    def every(self, pitch: float) -> tuple[F64, F64, F64]:
        """Things centred every ``pitch`` cm along each smooth span: (centres, angles, index)."""
        out: list[F64] = []
        angles: list[F64] = []
        indices: list[F64] = []
        for arc in self.arcs():
            count = int(math.floor(arc.total / pitch + 1e-9))
            if count <= 0:
                continue
            points, angle = arc.at((np.arange(count) + 0.5) * pitch)
            out.append(points)
            angles.append(angle)
            indices.append(np.arange(count, dtype=np.float64))
        if not out:
            return np.zeros((0, 2)), np.zeros(0), np.zeros(0)
        return np.concatenate(out), np.concatenate(angles), np.concatenate(indices)

    def wire_runs(self, rise: float, pitch: float) -> tuple[F64, F64, F64, F64]:
        """Diagonal chain-link wire ends across each smooth span.

        For every wire: its two plan points, its distance from the panel's starting
        edge at each end (``near`` / ``far`` minus the wire's origin)."""
        near_points: list[F64] = []
        far_points: list[F64] = []
        near_offsets: list[F64] = []
        far_offsets: list[F64] = []
        for arc in self.arcs():
            total = arc.total
            if total <= 0.0:
                continue
            count = max(1, int(math.ceil((total + rise) / pitch - 1e-9)))
            origin = np.arange(count) * pitch - rise
            near = np.maximum(origin, 0.0)
            far = np.minimum(origin + rise, total)
            keep = far - near > 0.5
            if not keep.any():
                continue
            near, far, origin = near[keep], far[keep], origin[keep]
            near_points.append(arc.at(near)[0])
            far_points.append(arc.at(far)[0])
            near_offsets.append(near - origin)
            far_offsets.append(far - origin)
        if not near_points:
            return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0), np.zeros(0)
        return (np.concatenate(near_points), np.concatenate(far_points),
                np.concatenate(near_offsets), np.concatenate(far_offsets))

    def mid(self) -> F64:
        centres: F64 = self.start + self.along * (self.length / 2.0)[:, None]
        return centres


def _scale(height_cm: float) -> float:
    """Details shrink with a fence lower than 60 cm (a knee rail), never grow."""
    return min(1.0, height_cm / 60.0)


def picket_fence(run: _Run, height_cm: float, post_cm: float) -> Mesh:
    k = _scale(height_cm)
    post_at, post_angle = run.posts(POST_SPACING_CM)
    posts = bevelled_boxes(post_at, (post_cm, post_cm), 0.0, height_cm, POST_BEVEL_CM * k,
                           post_angle, TINT)
    rail_size = np.stack([run.length, np.full(run.count, RAIL_ACROSS_CM)], axis=1)
    rails = [boxes(run.mid(), rail_size, share * height_cm,
                   min(share * height_cm + RAIL_TALL_CM, (share + 0.2) * height_cm), run.angle, TINT)
             for share in (0.25, 0.75)]
    at, angle, index = run.every(PICKET_PITCH_CM)
    jitter = (index * 7919 % 13) / 13.0 * 4.0  # 0 … 3.7 cm: no two neighbours level
    pickets = boxes(at, (PICKET_WIDE_CM, PICKET_THICK_CM), 2.0 * k, height_cm - (4.0 - jitter) * k,
                    angle, TINT)
    return Mesh.merge([posts, *rails, pickets])


def metal_fence(run: _Run, height_cm: float, post_cm: float) -> Mesh:
    k = _scale(height_cm)
    post_at, post_angle = run.posts(POST_SPACING_CM)
    posts = boxes(post_at, (post_cm, post_cm), 0.0, height_cm, post_angle, TINT)
    rail_size = np.stack([run.length, np.full(run.count, METAL_RAIL_CM)], axis=1)
    low, high = 10.0 * k, height_cm - 12.0 * k
    rails = [boxes(run.mid(), rail_size, z, z + METAL_RAIL_CM * k, run.angle, TINT)
             for z in (low, high - METAL_RAIL_CM * k)]
    at, angle, _index = run.every(METAL_BAR_PITCH_CM)
    bars = boxes(at, (METAL_BAR_CM, METAL_BAR_CM), low, height_cm - 2.0 * k, angle, TINT)
    return Mesh.merge([posts, *rails, bars])


def chain_link_fence(run: _Run, height_cm: float, post_cm: float) -> Mesh:
    k = _scale(height_cm)
    post_at, post_angle = run.posts(CHAIN_POST_SPACING_CM)
    posts = boxes(post_at, (post_cm, post_cm), 0.0, height_cm, post_angle, TINT)
    rail_size = np.stack([run.length, np.full(run.count, CHAIN_RAIL_CM)], axis=1)
    bottom, top = 3.0 * k, height_cm - 5.0 * k
    rail = boxes(run.mid(), rail_size, top, top + CHAIN_RAIL_CM * k, run.angle, TINT)
    # two families of 45° wires across each panel, clipped to it
    rise = top - bottom
    near_points, far_points, near_offsets, far_offsets = run.wire_runs(
        rise, CHAIN_WIRE_PITCH_CM)
    wires = []
    if len(near_points):
        for sign, base in ((1.0, bottom), (-1.0, top)):
            a = np.concatenate([near_points, (base + sign * near_offsets)[:, None]], axis=1)
            b = np.concatenate([far_points, (base + sign * far_offsets)[:, None]], axis=1)
            wires.append(tubes(a, b, CHAIN_WIRE_RADIUS_CM * k, CHAIN_WIRE_RADIUS_CM * k,
                               TINT, sides=3))
    return Mesh.merge([posts, rail, *wires])


def hedge_fence_parts(record: Record, line: F64, closed: bool,
                      height_cm: float) -> tuple[MeshPart, ...]:
    half = max(record.path_width_cm or 0.0, HEDGE_THICKNESS_CM) / 2.0 - CORE_INSET_CM
    core_top = max(height_cm - CORE_DROP_CM, 0.5 * height_cm)
    profile = [(-half, 0.0), (half, 0.0), (half, core_top), (-half, core_top)]
    core = sweep(profile, line, TINT, closed=closed, edges=[False, True, True, True])
    shell = line_shell(line, closed, half, height_cm)
    return hedge_parts(core, shell, height_cm, seed_of(record), tinted=True)


def plain_width_cm(record: Record) -> float:
    """A plain panel is as wide as the line is drawn."""
    return max(record.path_width_cm or 0.0, PLAIN_MIN_WIDTH_CM)


def plain_fence(line: F64, closed: bool, width_cm: float, height_cm: float) -> Mesh:
    """The stroke strip along ``line``, from the ground to ``height_cm`` — exactly
    the solid the 2D shadow model casts for the item."""
    half = width_cm / 2.0
    profile = [(-half, 0.0), (half, 0.0), (half, height_cm), (-half, height_cm)]
    return sweep(profile, line, TINT, closed=closed, edges=[False, True, True, True])


#: fence style -> (the builder of its mesh, its nominal post size in cm)
_POST_FENCES: Final = {
    "WOODEN_FENCE": (picket_fence, POST_CM),
    "METAL_FENCE": (metal_fence, METAL_POST_CM),
    "CHAIN_LINK": (chain_link_fence, CHAIN_POST_CM),
}


def fence_parts(record: Record, line: F64, closed: bool, height_cm: float,
                style: str) -> tuple[MeshPart, ...]:
    """The parts of a fence along ``line`` in ``style`` — one of the styles built
    here (module docstring). Any other name is a programming error: the caller
    (``lines.py``) decides what an unknown style becomes, this function never
    guesses a look."""
    if style == "HEDGE_FENCE":
        return hedge_fence_parts(record, line, closed, height_cm)
    if style == PLAIN:
        mesh = plain_fence(line, closed, plain_width_cm(record), height_cm)
    elif style in _POST_FENCES:
        build, post_cm = _POST_FENCES[style]
        mesh = build(_Run(line, closed), height_cm, max(post_cm, record.path_width_cm or 0.0))
    else:
        raise ValueError(f"no fence is built in the style {style!r}")
    return (MeshPart(mesh, "vc", tinted=True, name="fence"),)


def triangle_budget(line: F64, closed: bool, segments: int, style: str) -> int:
    """The most triangles a fence may have, by style — per METRE of centre line
    and per segment, so 50 m of fence cannot explode:

    picket 105 / m + 60 / segment · metal 100 / m + 35 / segment ·
    chain link 55 / m + 110 / segment · each + 60. A hedge fence: its leaves and
    its core. A plain panel: 3 faces per segment, as many again for a bevelled
    joint, and two ends — 12 / segment + 8.
    """
    if style == "HEDGE_FENCE":
        return 2 * MAX_LEAVES + 16 * max(segments, 1) + 40
    if style == PLAIN:
        return 12 * max(segments, 1) + 8
    metres = float(_Run(line, closed).length.sum()) / 100.0 if len(line) >= 2 else 0.0
    per_metre, per_segment = {"WOODEN_FENCE": (105, 60), "METAL_FENCE": (100, 35),
                              "CHAIN_LINK": (55, 110)}[style]
    return int(per_metre * metres) + per_segment * max(segments, 1) + 60


#: Fence styles whose 3D panels have open gaps between posts, rails, and infill (#440).
#: ``HEDGE_FENCE``, ``STONE_WALL``, ``WALL``, and ``PLAIN`` panels are opaque (0.0 open).
POROUS_FENCE_STYLES: Final = frozenset({"WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK"})


def fence_segment_occlusion(
    style: str,
    height_cm: float = 150.0,
    stroke_cm: float = 3.0,
    elevation_deg: float = 35.0,
    c_perp: float = 1.0,
    c_par: float = 0.0,
    run_len_cm: float = 1000.0,
    *,
    shared_start_post: bool = False,
    post_count: float | None = None,
) -> float:
    """Analytical shadow occlusion fraction ``[0.0, 1.0]`` for one fence segment (#440).

    Derived directly from the 3D structural constants above (posts, rails, and infill
    pickets/bars/diamond wires) at solar elevation ``elevation_deg`` and horizontal ray
    direction components ``(c_perp, c_par)`` relative to the segment:

    - Glancing azimuths (``c_perp -> 0``, ``c_par -> 1``) widen the projected along-fence
      footprint of posts, pickets, and bars ``(w_along * c_perp + w_across * c_par) /
      (pitch * c_perp)``, closing the gaps at oblique angles.
    - Steeper elevations widen the vertical shadow cast by horizontal rails
      ``rail_tall + rail_across * tan(elevation) * c_perp``.

    ``post_count`` overrides the post count for this piece (a smooth span distributes
    its posts by arc length; a caller passes the piece's share of them). It is the
    builder's own count — a dense sampled curve must not read one post per 2 cm chord
    (#675's shadow side).
    """
    if style not in POROUS_FENCE_STYLES or height_cm <= 0.0:
        return 1.0
    k = _scale(height_cm)
    tan_a = math.tan(math.radians(max(elevation_deg, 1.0))) if elevation_deg > 0.0 else 0.0
    cp = max(abs(c_perp), 1e-6)
    cl = abs(c_par)
    run = max(run_len_cm, 1.0)

    if style == "WOODEN_FENCE":
        post_w = max(POST_CM, stroke_cm)
        per_seg = max(2.0, math.ceil(run / POST_SPACING_CM) + 1.0)
        n_posts = (post_count if post_count is not None
                   else per_seg - (1.0 if shared_start_post else 0.0))
        o_post = min(1.0, (n_posts * (post_w * cp + post_w * cl)) / (run * cp))
        rail_h = min(RAIL_TALL_CM, 0.2 * height_cm)
        o_rail = min(1.0, 2.0 * (rail_h + RAIL_ACROSS_CM * tan_a * cp) / height_cm)
        h_picket = max(0.0, height_cm - 4.15 * k) / height_cm
        w_picket = min(1.0, (PICKET_WIDE_CM * cp + PICKET_THICK_CM * cl) / (PICKET_PITCH_CM * cp))
        o_infill = h_picket * w_picket
    elif style == "METAL_FENCE":
        post_w = max(METAL_POST_CM, stroke_cm)
        per_seg = max(2.0, math.ceil(run / POST_SPACING_CM) + 1.0)
        n_posts = (post_count if post_count is not None
                   else per_seg - (1.0 if shared_start_post else 0.0))
        o_post = min(1.0, (n_posts * (post_w * cp + post_w * cl)) / (run * cp))
        o_rail = min(1.0, 2.0 * (METAL_RAIL_CM * k + METAL_RAIL_CM * tan_a * cp) / height_cm)
        h_bar = max(0.0, height_cm - 12.0 * k) / height_cm
        w_bar = min(1.0, (METAL_BAR_CM * cp + METAL_BAR_CM * cl) / (METAL_BAR_PITCH_CM * cp))
        o_infill = h_bar * w_bar
    else:  # CHAIN_LINK
        post_w = max(CHAIN_POST_CM, stroke_cm)
        per_seg = max(2.0, math.ceil(run / CHAIN_POST_SPACING_CM) + 1.0)
        n_posts = (post_count if post_count is not None
                   else per_seg - (1.0 if shared_start_post else 0.0))
        o_post = min(1.0, (n_posts * (post_w * cp + post_w * cl)) / (run * cp))
        o_rail = min(1.0, (CHAIN_RAIL_CM * k + CHAIN_RAIL_CM * tan_a * cp) / height_cm)
        h_wire = max(0.0, height_cm - 8.0 * k) / height_cm
        # 3-sided tube prism (``primitives.tubes(..., sides=3)``) of circumradius R has mean
        # projected width 1.5 * R across horizontal/sloped rays; two 45-degree wire families.
        d_eff = (
            1.5
            * (CHAIN_WIRE_RADIUS_CM * k)
            * math.sqrt(1.0 + 0.5 * (tan_a * cp) ** 2 + 0.5 * (cl / cp) ** 2)
        )
        p_single = min(1.0, math.sqrt(2.0) * d_eff / CHAIN_WIRE_PITCH_CM)
        o_infill = h_wire * (1.0 - (1.0 - p_single) ** 2)

    transmittance = (1.0 - o_post) * (1.0 - o_rail) * (1.0 - o_infill)
    return float(min(1.0, max(0.0, 1.0 - transmittance)))


def fence_transmittance(
    style: str,
    height_cm: float,
    stroke_cm: float,
    elevation_deg: float,
    azimuth_deg: float,
    points: Sequence[tuple[float, float]] = (),
) -> float:
    """Angle-dependent open transmittance ``[0.0, 1.0]`` for a fence caster (#440).

    Returns ``0.0`` for opaque styles (``HEDGE_FENCE``, ``STONE_WALL``, ``PLAIN``, or
    any non-porous style) and ``1.0 - occlusion`` weighted by each segment's projected
    shadow area for ``WOODEN_FENCE``, ``METAL_FENCE``, and ``CHAIN_LINK``.
    """
    if style not in POROUS_FENCE_STYLES or height_cm <= 0.0:
        return 0.0
    if len(points) < 2:
        return 1.0 - fence_segment_occlusion(
            style, height_cm, stroke_cm, elevation_deg, c_perp=1.0, c_par=0.0
        )

    opp_rad = math.radians((azimuth_deg + 180.0) % 360.0)
    dx = math.sin(opp_rad)
    dy = math.cos(opp_rad)
    closed = (
        len(points) >= 3
        and math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) <= 1e-6
    )
    spacing = {"WOODEN_FENCE": POST_SPACING_CM,
               "METAL_FENCE": POST_SPACING_CM,
               "CHAIN_LINK": CHAIN_POST_SPACING_CM}[style]

    weighted_occ = 0.0
    total_weight = 0.0
    line = np.asarray(points[:-1] if closed else points, dtype=np.float64)
    for arc_index, arc in enumerate(_Run(line, closed).arcs()):
        span_len = arc.total
        if span_len <= 1e-6:
            continue
        # The posts the 3D builder stands on this smooth span (``_Run.posts``): every
        # ``spacing`` cm at most, a shared corner only once. A dense sampled curve must
        # not read a post per 2 cm chord (#675's shadow side).
        per_span = max(2.0, math.ceil(span_len / spacing) + 1.0)
        shared_start = closed or arc_index > 0
        n_posts = per_span - (1.0 if shared_start else 0.0)
        for segment in range(len(arc.length)):
            seg_len = float(arc.length[segment])
            if seg_len <= 1e-6:
                continue
            ax, ay = arc.points[segment]
            bx, by = arc.points[segment + 1]
            ux = (bx - ax) / seg_len
            uy = (by - ay) / seg_len
            c_par = abs(ux * dx + uy * dy)
            c_perp = abs(ux * dy - uy * dx)
            occ = fence_segment_occlusion(
                style,
                height_cm,
                stroke_cm,
                elevation_deg,
                c_perp=c_perp,
                c_par=c_par,
                run_len_cm=seg_len,
                post_count=n_posts * seg_len / span_len,
            )
            weight = seg_len * max(c_perp, 0.05)
            weighted_occ += weight * occ
            total_weight += weight

    if total_weight <= 0.0:
        return 1.0 - fence_segment_occlusion(
            style, height_cm, stroke_cm, elevation_deg, c_perp=1.0, c_par=0.0
        )
    return float(min(1.0, max(0.0, 1.0 - (weighted_occ / total_weight))))


#: Nominal normal-incidence (c_perp=1, c_par=0, elevation=0°, H=150 cm, L=1000 cm)
#: open fractions for every ``PathFenceStyle`` value (#440):
#:
#: ================  ==============  ====================================================
#: Style             Open fraction   Structural breakdown at normal incidence (150 cm)
#: ================  ==============  ====================================================
#: ``WOODEN_FENCE``  ~0.341 (34.1%)  7.44/12 cm pickets (38% raw gap), two 6 cm rails,
#:                                   9 cm posts every 200 cm
#: ``METAL_FENCE``   ~0.812 (81.2%)  1.6/11 cm bars (85.5% raw gap), two 2.5 cm rails,
#:                                   4 cm posts every 200 cm
#: ``CHAIN_LINK``    ~0.885 (88.5%)  0.8 cm wires at 25 cm diamond pitch (93.4% raw gap),
#:                                   one 3 cm top rail, 5 cm posts every 250 cm
#: ``HEDGE_FENCE``   0.000 (0.0%)    opaque foliage block + shell
#: ``STONE_WALL``    0.000 (0.0%)    opaque masonry wall
#: ``GRAVEL_PATH``   0.000 (0.0%)    ground path (not a vertical fence caster)
#: ``STEPPING_STONES`` 0.000 (0.0%)  ground path (not a vertical fence caster)
#: `` PAVED_PATH``   0.000 (0.0%)    ground path (not a vertical fence caster)
#: ``WOODCHIP_PATH`` 0.000 (0.0%)    ground path (not a vertical fence caster)
#: ``PLAIN``         0.000 (0.0%)    opaque plain panel
#: ================  ==============  ====================================================
NOMINAL_FENCE_OPEN_FRACTION: Final[dict[str, float]] = {
    "WOODEN_FENCE": round(
        1.0 - fence_segment_occlusion("WOODEN_FENCE", 150.0, 3.0, 0.0, 1.0, 0.0, 1000.0), 4
    ),
    "METAL_FENCE": round(
        1.0 - fence_segment_occlusion("METAL_FENCE", 150.0, 3.0, 0.0, 1.0, 0.0, 1000.0), 4
    ),
    "CHAIN_LINK": round(
        1.0 - fence_segment_occlusion("CHAIN_LINK", 150.0, 3.0, 0.0, 1.0, 0.0, 1000.0), 4
    ),
    "HEDGE_FENCE": 0.0,
    "STONE_WALL": 0.0,
    "GRAVEL_PATH": 0.0,
    "STEPPING_STONES": 0.0,
    "PAVED_PATH": 0.0,
    "WOODCHIP_PATH": 0.0,
    "PLAIN": 0.0,
}
