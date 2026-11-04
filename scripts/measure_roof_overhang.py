"""Measure the roof overhang search of ``core/scene3d/builders/buildings.py``.

A pitched roof's overhang is shortened when it would take the roof's lowest edge below
``EDGE_FLOOR_SHARE`` of the eave floor (``_kept_up``, ADR-065, §8.29.12). This script
builds every case of a grid and reports:

- for each case the search shortens: the overhang found against the LONGEST that holds
  (a 30-step bisection on the same builder, between the short end that builds — 0, or
  ``OVERHANG_NUDGE_CM`` — and the style's overhang), and how many found less than 97 %;
- how many roofs the search built (every ``_pitched`` call, a roof or not);
- floor violations: a roof whose lowest edge is below the floor, except the walls' own
  roof without an overhang (a gable 18-22 cm tall, which no overhang can lift);
- roofs lost: the search returned None although some overhang in its range builds a
  roof that holds (31 overhangs scanned from 0.01 cm to the style's).

The grid: HOUSE, TOOL_SHED and GARAGE_SHED, each with a gable, hip and shed roof. The
outlines:
- rectangles of 60 x 100, 100 x 50, 150 x 60, 240 x 180 and 900 x 540 cm;
- an L and a U whose ridge crosses them;
- an L and a U drawn on a grid, whose ridge lies on an edge of the outline (the
  HOUSE tool's ridge: the bounding box's centre line);
- a hexagon (r 300 cm) and a 64-gon (r 400 cm);
- a 600 x 400 cm rectangle turned 30° and a 900 x 540 cm one turned 45°, whose HOUSE gets
  the HOUSE tool's ridge (`core/roof_ridge.py`: the bounding box's long axis, so
  oblique to the walls).

Heights are 20, 25, 40, 60, 90, 150, 250, 400, 450, 600 and 700 cm; pitches 5, 30, 45
and 60°; overhangs 25, 50, 100 and 150 cm. Cases whose longest holding overhang is under
5 cm are counted but kept out of the shares, since a share of a few millimetres says
nothing. Last, it times the worst case the reviews used: a 64-corner hip, r 250 cm,
700 cm, 60°, 150 cm.

Run: ``venv/Scripts/python.exe scripts/measure_roof_overhang.py`` (several minutes).
"""

from __future__ import annotations

import dataclasses
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from open_garden_planner.core import roof_style as rs
from open_garden_planner.core.scene3d import Material, Params, Record, Transform, ccw
from open_garden_planner.core.scene3d.builders import buildings
from open_garden_planner.core.scene3d.builders.roofs import GableRoof, RoofStyle, eave_floor

Point = tuple[float, float]


def _rectangle(width: float, depth: float) -> tuple[Point, ...]:
    w, d = width / 2.0, depth / 2.0
    return ((-w, -d), (w, -d), (w, d), (-w, d))


def _round(corners: int, radius: float) -> tuple[Point, ...]:
    return tuple((radius * math.cos(2.0 * math.pi * k / corners), radius * math.sin(2.0 * math.pi * k / corners))
                 for k in range(corners))


def _turned(ring: tuple[Point, ...], degrees: float) -> tuple[Point, ...]:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return tuple((x * c - y * s, x * s + y * c) for x, y in ring)


def tool_ridge(ring: tuple[Point, ...]) -> tuple[Point, Point]:
    """The HOUSE tool's ridge (``core/roof_ridge.compute_roof_ridge_endpoints``): the
    bounding box's long axis through its centre, clipped to the outline."""
    xs, ys = [x for x, _y in ring], [y for _x, y in ring]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    along_x = max(xs) - min(xs) >= max(ys) - min(ys)
    crossings = []
    for (x0, y0), (x1, y1) in zip(ring, (*ring[1:], ring[0]), strict=True):
        if along_x and y0 != y1 and (y0 - cy) * (y1 - cy) <= 0.0:
            crossings.append(x0 + (cy - y0) / (y1 - y0) * (x1 - x0))
        elif not along_x and x0 != x1 and (x0 - cx) * (x1 - cx) <= 0.0:
            crossings.append(y0 + (cx - x0) / (x1 - x0) * (y1 - y0))
    low, high = min(crossings), max(crossings)
    return ((low, cy), (high, cy)) if along_x else ((cx, low), (cx, high))


OUTLINES: dict[str, tuple[str, tuple[Point, ...]]] = {
    "rect 60x100": ("rectangle", _rectangle(60.0, 100.0)),
    "rect 100x50": ("rectangle", _rectangle(100.0, 50.0)),
    "rect 150x60": ("rectangle", _rectangle(150.0, 60.0)),
    "rect 240x180": ("rectangle", _rectangle(240.0, 180.0)),
    "rect 900x540": ("rectangle", _rectangle(900.0, 540.0)),
    "L": ("polygon", ((-450.0, -300.0), (450.0, -300.0), (450.0, 100.0), (0.0, 100.0), (0.0, 300.0),
                      (-450.0, 300.0))),
    "L on a grid": ("polygon", ((-450.0, -300.0), (450.0, -300.0), (450.0, 0.0), (0.0, 0.0), (0.0, 300.0),
                                (-450.0, 300.0))),
    "U": ("polygon", ((-450.0, -300.0), (450.0, -300.0), (450.0, 300.0), (250.0, 300.0), (250.0, -100.0),
                      (-250.0, -100.0), (-250.0, 300.0), (-450.0, 300.0))),
    "U on a grid": ("polygon", ((-450.0, -300.0), (450.0, -300.0), (450.0, 300.0), (250.0, 300.0),
                                (250.0, 0.0), (-250.0, 0.0), (-250.0, 300.0), (-450.0, 300.0))),
    "hexagon": ("polygon", _round(6, 300.0)),
    "64-gon": ("polygon", _round(64, 400.0)),
    "rect 600x400 turned 30°": ("polygon", _turned(_rectangle(600.0, 400.0), 30.0)),
    "rect 900x540 turned 45°": ("polygon", _turned(_rectangle(900.0, 540.0), 45.0)),
}
#: The outlines whose HOUSE gets the HOUSE tool's ridge (an oblique one).
TOOL_RIDGE = frozenset({"rect 600x400 turned 30°", "rect 900x540 turned 45°"})
KINDS = ("HOUSE", "TOOL_SHED", "GARAGE_SHED")
HEIGHTS = (20.0, 25.0, 40.0, 60.0, 90.0, 150.0, 250.0, 400.0, 450.0, 600.0, 700.0)
STYLES = ("gable", "hip", "shed")
PITCHES = (rs.MIN_PITCH_DEG, 30.0, 45.0, rs.MAX_PITCH_DEG)
OVERHANGS = (25.0, 50.0, 100.0, rs.MAX_OVERHANG_CM)
SHARE_FLOOR_CM = 5.0   # a longest holding overhang under this is kept out of the shares


def record(kind: str, shape: str, ring: tuple[Point, ...], height: float, style: str, pitch: float,
           overhang: float, ridge: tuple[Point, Point] | None = None) -> Record:
    params: dict[str, object] = {"seed": "roof", "roof_style": style, "roof_pitch_deg": pitch,
                                 "roof_overhang_cm": overhang}
    if ridge is not None:
        params["ridge"] = ridge
    return Record("roof", kind, shape, (ccw(ring),), Transform(), Material(kind, (200, 180, 140, 255)),
                  height_cm=height, params=Params(params))


def main() -> int:
    real = buildings._pitched
    tried: list[tuple[GableRoof | None, float]] = []

    def counting(rec: Record, chosen: str, height_cm: float, style: RoofStyle) -> GableRoof | None:
        built = real(rec, chosen, height_cm, style)
        tried.append((built, style.overhang_cm))
        return built

    cases = shortened = violations = lost = own_roofs = 0
    shares: list[float] = []
    builds: list[int] = []
    worst: list[tuple[float, str]] = []
    for kind in KINDS:
        base = buildings.HOUSE_ROOF if kind == "HOUSE" else buildings.SHED_ROOF
        for name, (shape, ring) in OUTLINES.items():
            for height in HEIGHTS:
                for style in STYLES:
                    for pitch in PITCHES:
                        for overhang in OVERHANGS:
                            ridge = tool_ridge(ring) if kind == "HOUSE" and name in TOOL_RIDGE else None
                            rec = record(kind, shape, ring, height, style, pitch, overhang, ridge)
                            used = buildings.style_for(rec, base)
                            floor = buildings.EDGE_FLOOR_SHARE * eave_floor(used, height)

                            def at(cm: float, rec: Record = rec, style: str = style, used: RoofStyle = used,
                                   height: float = height) -> GableRoof | None:
                                return real(rec, style, height, dataclasses.replace(used, overhang_cm=cm))

                            def holds(cm: float, at=at, floor: float = floor) -> bool:
                                built = at(cm)
                                return built is not None and float(built.roof.positions[:, 2].min()) >= floor - 1e-6

                            tried.clear()
                            buildings._pitched = counting
                            try:
                                roof = buildings._kept_up(rec, style, height, used)
                            finally:
                                buildings._pitched = real
                            cases += 1
                            builds.append(len(tried))
                            if roof is None:
                                scan = [0.01] + [used.overhang_cm * k / 30.0 for k in range(1, 31)]
                                if any(holds(cm) for cm in scan):
                                    lost += 1
                                    worst.append((-1.0, f"LOST {kind} {name} h{height:g} {style} {pitch:g}° "
                                                        f"{overhang:g} cm"))
                                continue
                            found = next(cm for built, cm in tried if built is roof)
                            lowest = float(roof.roof.positions[:, 2].min())
                            if lowest < floor - 1e-3:
                                if found <= buildings.OVERHANG_NUDGE_CM:
                                    own_roofs += 1
                                else:
                                    violations += 1
                            if found >= used.overhang_cm - 1e-9:
                                continue   # the style's own overhang holds
                            short = 0.0 if at(0.0) is not None else buildings.OVERHANG_NUDGE_CM
                            if not holds(short):
                                continue   # the walls' own roof: no overhang holds
                            low, high = short, used.overhang_cm
                            for _step in range(30):
                                middle = (low + high) / 2.0
                                low, high = (middle, high) if holds(middle) else (low, middle)
                            shortened += 1
                            if low < SHARE_FLOOR_CM:
                                continue
                            share = found / low
                            shares.append(share)
                            worst.append((share, f"{kind} {name} h{height:g} {style} {pitch:g}° {overhang:g} cm: "
                                                 f"{found:.1f} of {low:.1f} cm, {len(tried)} roofs"))
    shares.sort()
    print(f"cases {cases}; shortened {shortened}; with a longest holding overhang >= {SHARE_FLOOR_CM:g} cm: "
          f"{len(shares)}")
    print(f"floor violations {violations}; roofs lost {lost}; the walls' own roof (no overhang holds) {own_roofs}")
    if shares:
        tenth = shares[len(shares) // 10]
        print(f"found / longest: min {shares[0]:.3f}, p10 {tenth:.3f}, median {statistics.median(shares):.3f}; "
              f"below 0.97: {sum(1 for s in shares if s < 0.97)}")
    print(f"roofs built per case: mean {statistics.fmean(builds):.2f}, max {max(builds)}")
    for share, text in sorted(worst)[:8]:
        print(f"  {share:.3f}  {text}")

    rec = record("HOUSE", "polygon", _round(64, 250.0), 700.0, "hip", 60.0, 150.0)
    used = buildings.style_for(rec, buildings.HOUSE_ROOF)
    timings = []
    for _run in range(3):
        started = time.perf_counter()
        buildings._kept_up(rec, "hip", 700.0, used)
        timings.append((time.perf_counter() - started) * 1000.0)
    tried.clear()
    buildings._pitched = counting
    try:
        buildings._kept_up(rec, "hip", 700.0, used)
    finally:
        buildings._pitched = real
    print(f"64-corner hip, r 250 cm, 700 cm, 60°, 150 cm: {min(timings):.0f} ms (best of 3), {len(tried)} roofs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
