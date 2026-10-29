"""Sun path arcs, a compass rose and the ground probe's pin (Phase 17 L2.2, #386). Qt-free.

Where the sun goes over the garden, drawn as arcs on a dome over the plan:

- ``key_days`` — the four days the 3D view draws: the plan date (``today``), the
  June and the December solstice and the March equinox of the plan's year (fixed
  calendar dates — 21 June, 21 December, 20 March — within a day of the
  astronomical ones every year; the arcs of the two days on either side are within
  a fraction of a degree, which no one can see at the dome's scale).
- ``day_arc`` — one LOCAL day of one place, sampled every ``ARC_STEP_MINUTES`` of
  wall time in the clock's zone (``core.sim_clock.SimInstant``: the same wall time →
  instant rule as the toolbar), every point from ``core.solar.solar_position`` and
  nothing chosen. The part above the horizon is kept, each end cut where the sun
  crosses it (the crossing's instant interpolated, its position computed again),
  and the day's highest point — SOLAR NOON — is found to the second and inserted.
  A UTC civil day (the heatmap's sampling window) would split the arc of a garden
  far from Greenwich in two; a local day never does.
- ``dome_point`` — THE one mapping from a sun position to the dome: elevation ``e``
  and azimuth ``a`` (compass bearing, clockwise from north) go to
  ``centre + R · (cos e · sin a, cos e · cos a, sin e)`` in the scene frame (E, N,
  up) — ``frame.sun_direction_scene`` scaled by the radius. The gate of L2.2: the
  noon point of every arc IS ``dome_point`` of ``solar_position`` at its instant.

The meshes (scene frame, scene origin, normals for an unshaded material):

- ``sun_path_mesh`` — a thin tube along each arc in its own colour
  (``ARC_RGBA``), a bead on each whole hour of the plan date, and the sun itself as
  a larger ball at the sim instant when it is up;
- ``compass_mesh`` — on the ground at the dome's rim: a ring, a tick every 15°
  (long ones at the four cardinal points), a north arrow and the four letters,
  which come from the caller as glyph outlines (``ui/view3d/compass_glyphs.py``
  turns the TRANSLATED letters into outlines: QML carries no text);
- ``probe_pin_mesh`` — a pin standing where the ground was probed.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Final, TypeAlias

import numpy as np
from numpy.typing import NDArray

from ..sim_clock import SimInstant
from ..solar import solar_position
from .color import Rgba, srgb8_to_linear
from .mesh import Mesh
from .polygon import (
    Region,
    RegionTooLargeError,
    group_rings,
    point_in_ring,
    ring_area,
    triangulate_region,
)

_log = logging.getLogger(__name__)

Vector: TypeAlias = tuple[float, float, float]
GlyphRing: TypeAlias = Sequence[tuple[float, float]]
_F64: TypeAlias = NDArray[np.float64]

#: The arcs, in the order they are drawn and listed in the strip's legend.
ARC_KINDS: Final = ("today", "june_solstice", "december_solstice", "march_equinox")
#: Each arc's colour as the strip's LEGEND shows it, sRGB.
ARC_RGBA: Final[Mapping[str, Rgba]] = {
    "today": (255, 196, 64, 255),
    "june_solstice": (232, 106, 64, 255),
    "december_solstice": (90, 150, 230, 255),
    "march_equinox": (120, 200, 120, 255),
}
#: The colour each arc's tube is BUILT with, sRGB: the legend's colour pre-compensated
#: for the engine's filmic curve, which bends a saturated colour's hue on its way to the
#: screen (the legend's own colours read +9 to +14 degrees off for the plan date, -8 to
#: -11 for 21 December). With the overlay's exposure division (``overlay.frag``) these
#: land within 2.5 degrees of the legend's hue at noon, golden hour, sunset, a December
#: noon and night alike (3D review of #386; re-measured 2026-10-24 on D3D11: +2.4 / +2.7 /
#: -2.4 / +0.1 degrees for the plan date / 21 June / 21 December / 20 March).
ARC_ENGINE_RGBA: Final[Mapping[str, Rgba]] = {
    "today": (232, 150, 40, 255),
    "june_solstice": (220, 90, 56, 255),
    "december_solstice": (80, 130, 230, 255),
    "march_equinox": (120, 200, 120, 255),
}
#: The plan date's arc is this much thicker than the others and drawn last: on a key
#: day it lies exactly on its twin (21 June is the June solstice) and was hidden under it.
TODAY_TUBE_FACTOR: Final = 1.5
COMPASS_RGBA: Final[Rgba] = (236, 234, 224, 255)
NORTH_RGBA: Final[Rgba] = (214, 62, 52, 255)
SUN_RGBA: Final[Rgba] = (255, 222, 120, 255)
PIN_RGBA: Final[Rgba] = (214, 52, 160, 255)
#: Wall-time sampling of an arc (minutes).
ARC_STEP_MINUTES: Final = 5
#: The dome's radius is this share of the plan's diagonal — just outside its corners,
#: which lie at half the diagonal — and never smaller than ``MIN_DOME_RADIUS_CM``.
DOME_SHARE: Final = 0.55
MIN_DOME_RADIUS_CM: Final = 500.0
#: Sizes as shares of the dome's radius (tubes, beads, the compass) — drawn as large
#: as the dome, so a garden of any size gets the same picture.
TUBE_SHARE: Final = 0.0035
BEAD_SHARE: Final = 0.009
SUN_SHARE: Final = 0.03
RIM_SHARE: Final = 0.004
TICK_SHARE: Final = 0.035
CARDINAL_TICK_SHARE: Final = 0.08
ARROW_SHARE: Final = 0.07
LETTER_SHARE: Final = 0.12   # 0.065 left E and W about 6 px high from the default camera
#: How far above the ground the compass lies (cm) — the drape's lift and a hair more.
COMPASS_LIFT_CM: Final = 4.0
#: The compass's letters by bearing: N, E, S, W.
CARDINAL_BEARINGS: Final = (0.0, 90.0, 180.0, 270.0)
_TUBE_SIDES: Final = 6
_SOLAR_NOON_ITERATIONS: Final = 60


@dataclass(frozen=True, slots=True)
class SunPoint:
    """One position of the sun: its instant (UTC) and where it stood."""

    utc: datetime
    elevation_deg: float
    azimuth_deg: float


@dataclass(frozen=True, slots=True)
class DayArc:
    """The sun's path over one local day (module docstring).

    ``segments``: the runs of the day with the sun above the horizon, each in time
    order — normally one, from sunrise to sunset; none in polar night; one closed
    run of the whole day under the midnight sun. ``noon``: the day's highest
    point, None in polar night; it is also a point of its segment.
    """

    kind: str
    day: date
    segments: tuple[tuple[SunPoint, ...], ...]
    noon: SunPoint | None


def key_days(plan_date: date) -> dict[str, date]:
    """The four days of ``ARC_KINDS`` for the plan date (module docstring)."""
    year = plan_date.year
    return {"today": plan_date, "june_solstice": date(year, 6, 21),
            "december_solstice": date(year, 12, 21), "march_equinox": date(year, 3, 20)}


def _position(lat: float, lon: float, utc: datetime) -> SunPoint:
    found = solar_position(lat, lon, utc)
    return SunPoint(utc, found.elevation_deg, found.azimuth_deg)


def _solar_noon(lat: float, lon: float, start: datetime, end: datetime) -> SunPoint:
    """The highest point of the sun between ``start`` and ``end`` (one maximum inside),
    to the second: a golden-section search on ``solar_position``'s elevation."""
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    low, high = start, end
    for _ in range(_SOLAR_NOON_ITERATIONS):
        span = (high - low).total_seconds()
        if span <= 0.5:
            break
        left = low + timedelta(seconds=span * (1.0 - ratio))
        right = low + timedelta(seconds=span * ratio)
        if solar_position(lat, lon, left).elevation_deg < solar_position(lat, lon, right).elevation_deg:
            low = left
        else:
            high = right
    return _position(lat, lon, low + (high - low) / 2)


def _crossing(lat: float, lon: float, below: SunPoint, above: SunPoint) -> SunPoint:
    """Where the sun crosses the horizon between two samples: the instant interpolated
    on the elevation, the position computed there, the elevation set to 0."""
    share = below.elevation_deg / (below.elevation_deg - above.elevation_deg)
    instant = below.utc + (above.utc - below.utc) * share
    found = _position(lat, lon, instant)
    return SunPoint(found.utc, 0.0, found.azimuth_deg)


def day_arc(lat_deg: float, lon_deg: float, day: date, tz: tzinfo | None, kind: str = "today",
            step_minutes: int = ARC_STEP_MINUTES) -> DayArc:
    """The sun's path over the LOCAL ``day`` at a place (module docstring)."""
    steps = 24 * 60 // step_minutes
    samples = [_position(lat_deg, lon_deg, SimInstant.from_datetime(
        datetime.combine(day, time()) + timedelta(minutes=step_minutes * k), tz).utc)
        for k in range(steps)]
    end = SimInstant.from_datetime(datetime.combine(day, time()), tz).utc + timedelta(days=1)
    samples.append(_position(lat_deg, lon_deg, end))
    highest = max(range(len(samples)), key=lambda index: samples[index].elevation_deg)
    noon: SunPoint | None = None
    if samples[highest].elevation_deg > 0.0:
        low = samples[max(highest - 1, 0)].utc
        high = samples[min(highest + 1, len(samples) - 1)].utc
        noon = _solar_noon(lat_deg, lon_deg, low, high)
    segments: list[tuple[SunPoint, ...]] = []
    run: list[SunPoint] = []
    for previous, current in zip([None, *samples[:-1]], samples, strict=True):
        up = current.elevation_deg > 0.0
        if previous is not None and (previous.elevation_deg > 0.0) != up:
            crossing = (_crossing(lat_deg, lon_deg, previous, current) if up
                        else _crossing(lat_deg, lon_deg, current, previous))
            if up:
                run = [crossing]
            else:
                run.append(crossing)
                segments.append(tuple(run))
                run = []
        if up:
            run.append(current)
    if run:
        segments.append(tuple(run))
    if noon is not None:
        segments = [_with_noon(segment, noon) for segment in segments]
    return DayArc(kind, day, tuple(segments), noon)


def _with_noon(segment: tuple[SunPoint, ...], noon: SunPoint) -> tuple[SunPoint, ...]:
    """The segment with ``noon`` put in its place in time — when it lies inside it."""
    if not segment or not segment[0].utc < noon.utc < segment[-1].utc:
        return segment
    after = next(index for index, point in enumerate(segment) if point.utc > noon.utc)
    return (*segment[:after], noon, *segment[after:])


def dome_radius(width_cm: float, depth_cm: float) -> float:
    """The dome's radius over a plan ``width`` x ``depth`` (``DOME_SHARE``)."""
    return max(DOME_SHARE * math.hypot(width_cm, depth_cm), MIN_DOME_RADIUS_CM)


def dome_point(center: tuple[float, float], radius_cm: float, elevation_deg: float,
               azimuth_deg: float) -> Vector:
    """THE mapping from a sun position to the dome (module docstring)."""
    e, a = math.radians(elevation_deg), math.radians(azimuth_deg)
    return (center[0] + radius_cm * math.cos(e) * math.sin(a),
            center[1] + radius_cm * math.cos(e) * math.cos(a),
            radius_cm * math.sin(e))


# ── meshes ───────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _Builder:
    """Accumulates vertices and triangles of one mesh."""

    positions: list[_F64]
    normals: list[_F64]
    colors: list[_F64]
    triangles: list[NDArray[np.int64]]
    count: int = 0

    @classmethod
    def new(cls) -> _Builder:
        return cls([], [], [], [])

    def add(self, positions: _F64, normals: _F64, rgba: Rgba, triangles: NDArray[np.int64]) -> None:
        if not len(triangles):
            return
        self.positions.append(positions)
        self.normals.append(normals)
        self.colors.append(np.tile(np.asarray(srgb8_to_linear(rgba)), (len(positions), 1)))
        self.triangles.append(np.asarray(triangles, dtype=np.int64) + self.count)
        self.count += len(positions)

    def mesh(self) -> Mesh:
        if not self.count:
            return Mesh.empty()
        return Mesh.from_arrays(np.concatenate(self.positions), np.concatenate(self.normals),
                                np.concatenate(self.colors), np.zeros((self.count, 2)),
                                np.concatenate(self.triangles))


def _unit(vector: _F64) -> _F64:
    length = float(np.linalg.norm(vector))
    return vector / length if length > 1e-12 else vector


def _tube(builder: _Builder, points: _F64, radius: float, rgba: Rgba) -> None:
    """A tube of ``_TUBE_SIDES`` sides along a polyline — the ring at each point in the
    plane across the path, carried along by parallel transport (no twist where the
    path turns towards the vertical: an arc rises straight up at the equator)."""
    if len(points) < 2:
        return
    gradient: _F64 = np.asarray(np.gradient(points, axis=0), dtype=np.float64)
    tangents = np.array([_unit(t) for t in gradient])
    reference = np.array([0.0, 0.0, 1.0]) if abs(tangents[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    normal = _unit(np.cross(tangents[0], reference))
    angles = np.linspace(0.0, 2.0 * math.pi, _TUBE_SIDES, endpoint=False)
    rings_p, rings_n = [], []
    for tangent in tangents:
        normal = _unit(normal - np.dot(normal, tangent) * tangent)
        binormal = np.cross(tangent, normal)
        radial = np.cos(angles)[:, None] * normal + np.sin(angles)[:, None] * binormal
        rings_n.append(radial)
        rings_p.append(radial * radius)
    positions = (np.repeat(points, _TUBE_SIDES, axis=0)
                 + np.concatenate(rings_p))
    normals = np.concatenate(rings_n)
    n = _TUBE_SIDES
    triangles = []
    for i in range(len(points) - 1):
        for side in range(n):
            a, b = i * n + side, i * n + (side + 1) % n
            c, d = a + n, b + n
            triangles.append((a, b, d))
            triangles.append((a, d, c))
    builder.add(positions, normals, rgba, np.asarray(triangles, dtype=np.int64))


def _ball(builder: _Builder, center: Sequence[float], radius: float, rgba: Rgba,
          rows: int = 6, columns: int = 10) -> None:
    """A small UV sphere (unshaded: its outline is what reads)."""
    positions, normals = [], []
    for row in range(rows + 1):
        polar = math.pi * row / rows
        for column in range(columns):
            turn = 2.0 * math.pi * column / columns
            normal = (math.sin(polar) * math.cos(turn), math.sin(polar) * math.sin(turn),
                      math.cos(polar))
            normals.append(normal)
            positions.append(tuple(center[axis] + radius * normal[axis] for axis in range(3)))
    triangles = []
    for row in range(rows):
        for column in range(columns):
            a = row * columns + column
            b = row * columns + (column + 1) % columns
            c, d = a + columns, b + columns
            triangles.append((a, c, d))
            triangles.append((a, d, b))
    builder.add(np.asarray(positions), np.asarray(normals), rgba,
                np.asarray(triangles, dtype=np.int64))


def _flat(builder: _Builder, polygon: _F64, rgba: Rgba, lift: float) -> None:
    """A convex polygon (counter-clockwise, seen from above) lying flat at ``lift``."""
    count = len(polygon)
    positions = np.zeros((count, 3))
    positions[:, :2] = polygon
    positions[:, 2] = lift
    normals = np.tile([0.0, 0.0, 1.0], (count, 1))
    triangles = np.asarray([(0, k, k + 1) for k in range(1, count - 1)], dtype=np.int64)
    builder.add(positions, normals, rgba, triangles)


def sun_path_mesh(arcs: Sequence[DayArc], center: tuple[float, float], radius_cm: float, *,
                  hour_marks: Sequence[SunPoint] = (), sun: SunPoint | None = None) -> Mesh:
    """The arcs as tubes on the dome, beads at ``hour_marks``, and the sun as a ball at
    ``sun`` when it is above the horizon (module docstring). Scene frame."""
    builder = _Builder.new()
    tube = TUBE_SHARE * radius_cm
    for arc in sorted(arcs, key=lambda arc: arc.kind == "today"):  # the plan date's last
        rgba = ARC_ENGINE_RGBA.get(arc.kind, ARC_ENGINE_RGBA["today"])
        width = tube * (TODAY_TUBE_FACTOR if arc.kind == "today" else 1.0)
        for segment in arc.segments:
            points = np.asarray([dome_point(center, radius_cm, p.elevation_deg, p.azimuth_deg)
                                 for p in segment], dtype=np.float64)
            _tube(builder, points, width, rgba)
    for mark in hour_marks:
        if mark.elevation_deg > 0.0:
            _ball(builder, dome_point(center, radius_cm, mark.elevation_deg, mark.azimuth_deg),
                  BEAD_SHARE * radius_cm, ARC_ENGINE_RGBA["today"], rows=4, columns=6)
    if sun is not None and sun.elevation_deg > 0.0:
        _ball(builder, dome_point(center, radius_cm, sun.elevation_deg, sun.azimuth_deg),
              SUN_SHARE * radius_cm, SUN_RGBA)
    return builder.mesh()


def hour_marks(arc: DayArc, tz: tzinfo | None) -> tuple[SunPoint, ...]:
    """The plan date's whole local hours at which the sun is up — read off the arc's
    own samples (every whole hour of wall time is one of them)."""
    marks = []
    for segment in arc.segments:
        for point in segment:
            wall = SimInstant.from_datetime(point.utc, tz).wall
            if wall.minute == 0 and wall.second == 0 and point.elevation_deg > 0.0:
                marks.append(point)
    return tuple(marks)


def _radial(bearing_deg: float) -> tuple[float, float]:
    a = math.radians(bearing_deg)
    return (math.sin(a), math.cos(a))


def _bar(center: tuple[float, float], bearing: float, inner: float, outer: float,
         half_width: float) -> _F64:
    """A radial bar from ``inner`` to ``outer`` (counter-clockwise from above)."""
    out = np.array(_radial(bearing))
    across = np.array([out[1], -out[0]])  # 90° clockwise of outward: right of the bar
    c = np.array(center)
    return np.array([c + out * inner - across * half_width, c + out * inner + across * half_width,
                     c + out * outer + across * half_width, c + out * outer - across * half_width])


def _oriented_regions(rings: Sequence[GlyphRing]) -> tuple[Region, ...]:
    """Glyph outlines as regions: a ring inside an even number of other rings is an
    outer ring (made counter-clockwise), inside an odd number a hole (clockwise) —
    whatever winding the font gave them."""
    cleaned = [tuple((float(x), float(y)) for x, y in ring) for ring in rings if len(ring) >= 3]
    oriented = []
    for index, ring in enumerate(cleaned):
        depth = sum(1 for other, candidate in enumerate(cleaned)
                    if other != index and point_in_ring(ring[0][0], ring[0][1], candidate))
        outer = depth % 2 == 0
        if (ring_area(ring) > 0.0) != outer:
            ring = tuple(reversed(ring))
        oriented.append(ring)
    return group_rings(oriented)


def compass_mesh(center: tuple[float, float], radius_cm: float,
                 glyphs: Mapping[float, Sequence[GlyphRing]] | None = None) -> Mesh:
    """The compass rose on the ground at the dome's rim (module docstring).

    ``glyphs``: by bearing (``CARDINAL_BEARINGS``), each letter's outlines in em
    units — centred on (0, 0), one unit high, y up the letter. They lie flat, their
    top pointing away from the centre. A letter whose outlines cannot be filled is
    left out (logged); the rest of the rose stands.
    """
    builder = _Builder.new()
    lift = COMPASS_LIFT_CM
    rim = RIM_SHARE * radius_cm
    segments = 128
    angles = np.linspace(0.0, 2.0 * math.pi, segments, endpoint=False)
    inner = np.stack([center[0] + (radius_cm - rim) * np.sin(angles),
                      center[1] + (radius_cm - rim) * np.cos(angles)], axis=1)
    outer = np.stack([center[0] + (radius_cm + rim) * np.sin(angles),
                      center[1] + (radius_cm + rim) * np.cos(angles)], axis=1)
    positions = np.zeros((2 * segments, 3))
    positions[:segments, :2], positions[segments:, :2] = inner, outer
    positions[:, 2] = lift
    triangles = []
    for k in range(segments):
        a, b = k, (k + 1) % segments
        # the angle runs clockwise seen from above (a compass bearing): wind accordingly
        triangles.append((a, b + segments, a + segments))
        triangles.append((a, b, b + segments))
    builder.add(positions, np.tile([0.0, 0.0, 1.0], (2 * segments, 1)), COMPASS_RGBA,
                np.asarray(triangles, dtype=np.int64))
    for step in range(24):
        bearing = step * 15.0
        cardinal = step % 6 == 0
        length = (CARDINAL_TICK_SHARE if cardinal else TICK_SHARE) * radius_cm
        width = rim * (1.6 if cardinal else 1.0)
        _flat(builder, _bar(center, bearing, radius_cm - length, radius_cm, width), COMPASS_RGBA,
              lift)
    out = np.array(_radial(0.0))
    across = np.array([out[1], -out[0]])
    c = np.array(center)
    base = c + out * (radius_cm + 2.0 * rim)
    arrow = np.array([base - across * ARROW_SHARE * radius_cm * 0.45,
                      base + across * ARROW_SHARE * radius_cm * 0.45,
                      c + out * (radius_cm + 2.0 * rim + ARROW_SHARE * radius_cm)])
    _flat(builder, arrow, NORTH_RGBA, lift + 0.1)
    for bearing, rings in (glyphs or {}).items():
        _letter(builder, center, radius_cm, float(bearing), rings, lift)
    return builder.mesh()


def _letter(builder: _Builder, center: tuple[float, float], radius_cm: float, bearing: float,
            rings: Sequence[GlyphRing], lift: float) -> None:
    try:
        regions = _oriented_regions(rings)
        size = LETTER_SHARE * radius_cm
        reach = radius_cm + 2.0 * RIM_SHARE * radius_cm + ARROW_SHARE * radius_cm + 0.9 * size
        out = np.array(_radial(bearing))
        right = np.array([out[1], -out[0]])
        anchor = np.array(center) + out * reach
        for outer, holes in regions:
            points, triangles = triangulate_region(outer, holes)
            local = np.asarray(points, dtype=np.float64).reshape(-1, 2)
            placed = anchor + local[:, :1] * size * right + local[:, 1:] * size * out
            count = len(placed)
            positions = np.zeros((count, 3))
            positions[:, :2] = placed
            positions[:, 2] = lift
            rgba = NORTH_RGBA if bearing == 0.0 else COMPASS_RGBA
            # the placement is a rotation (right, out) of a counter-clockwise outline:
            # still counter-clockwise from above
            builder.add(positions, np.tile([0.0, 0.0, 1.0], (count, 1)), rgba,
                        np.asarray(triangles, dtype=np.int64))
    except (ValueError, RegionTooLargeError) as error:
        _log.warning("3D compass: the letter at %s degrees was left out (%s)", bearing,
                     type(error).__name__)


def probe_pin_mesh(point: tuple[float, float], radius_cm: float) -> Mesh:
    """A pin where the ground was probed: a thin stem with a ball on top, as tall as a
    share of the dome so it is found at any zoom."""
    builder = _Builder.new()
    height = max(0.03 * radius_cm, 30.0)
    stem = np.array([[point[0], point[1], 0.0], [point[0], point[1], height]])
    _tube(builder, stem, max(TUBE_SHARE * radius_cm * 0.6, 1.0), PIN_RGBA)
    _ball(builder, (point[0], point[1], height), max(BEAD_SHARE * radius_cm * 1.4, 4.0), PIN_RGBA)
    return builder.mesh()
