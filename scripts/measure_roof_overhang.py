"""Measure the roof overhang search of ``core/scene3d/builders/buildings.py``.

A pitched roof's overhang is shortened when it would take the roof's lowest edge below
``EDGE_FLOOR_SHARE`` of the eave floor (``_kept_up``, ADR-065, §8.29.12). This script
builds every case of a panel grid and reports, for each case the search shortens:

- the overhang found against the LONGEST that holds (a 30-step bisection on the same
  builder), and how many found less than 97 % of it;
- how many roofs the search built (the count of ``_pitched`` calls);
- whether any roof's lowest edge is below the floor (a violation), and whether a
  roof was lost (the search returned None where an overhang of 0 builds one).

The grid: HOUSE, TOOL_SHED and GARAGE_SHED; a 60 x 100, 240 x 180 and 900 x 540 cm
rectangle, an L, a U (its ridge crosses the courtyard), a hexagon (r 300 cm) and a
64-gon (r 400 cm); heights 20, 25, 40, 60, 90, 150, 250, 450 and 700 cm; the gable, hip
and shed styles; pitch 5, 30, 45 and 60°; overhang 25, 50, 100 and 150 cm. Cases whose
longest holding overhang is under 5 cm are counted but kept out of the share
statistics (a share of a few millimetres says nothing). Last, it times the worst case
the reviews used: a 64-corner hip, r 250 cm, 700 cm, 60°, 150 cm.

Run: ``venv/Scripts/python.exe scripts/measure_roof_overhang.py`` (about a minute).
"""

from __future__ import annotations

import dataclasses
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from open_garden_planner.core import roof_style as rs  # noqa: E402
from open_garden_planner.core.scene3d import Material, Params, Record, Transform, ccw  # noqa: E402
from open_garden_planner.core.scene3d.builders import buildings  # noqa: E402
from open_garden_planner.core.scene3d.builders.roofs import RoofStyle, eave_floor  # noqa: E402

Point = tuple[float, float]


def _rectangle(width: float, depth: float) -> tuple[Point, ...]:
    w, d = width / 2.0, depth / 2.0
    return ((-w, -d), (w, -d), (w, d), (-w, d))


def _round(corners: int, radius: float) -> tuple[Point, ...]:
    return tuple((radius * math.cos(2.0 * math.pi * k / corners), radius * math.sin(2.0 * math.pi * k / corners))
                 for k in range(corners))


OUTLINES: dict[str, tuple[str, tuple[Point, ...]]] = {
    "rect 60x100": ("rectangle", _rectangle(60.0, 100.0)),
    "rect 240x180": ("rectangle", _rectangle(240.0, 180.0)),
    "rect 900x540": ("rectangle", _rectangle(900.0, 540.0)),
    "L": ("polygon", ((-450.0, -300.0), (450.0, -300.0), (450.0, 100.0), (0.0, 100.0), (0.0, 300.0),
                      (-450.0, 300.0))),
    "U": ("polygon", ((-450.0, -300.0), (450.0, -300.0), (450.0, 300.0), (250.0, 300.0), (250.0, -100.0),
                      (-250.0, -100.0), (-250.0, 300.0), (-450.0, 300.0))),
    "hexagon": ("polygon", _round(6, 300.0)),
    "64-gon": ("polygon", _round(64, 400.0)),
}
KINDS = ("HOUSE", "TOOL_SHED", "GARAGE_SHED")
HEIGHTS = (20.0, 25.0, 40.0, 60.0, 90.0, 150.0, 250.0, 450.0, 700.0)
STYLES = ("gable", "hip", "shed")
PITCHES = (rs.MIN_PITCH_DEG, 30.0, 45.0, rs.MAX_PITCH_DEG)
OVERHANGS = (25.0, 50.0, 100.0, rs.MAX_OVERHANG_CM)
SHARE_FLOOR_CM = 5.0   # a longest holding overhang under this is kept out of the shares


def record(kind: str, shape: str, ring: tuple[Point, ...], height: float, style: str, pitch: float,
           overhang: float) -> Record:
    params = {"seed": "roof", "roof_style": style, "roof_pitch_deg": pitch, "roof_overhang_cm": overhang}
    return Record("roof", kind, shape, (ccw(ring),), Transform(), Material(kind, (200, 180, 140, 255)),
                  height_cm=height, params=Params(params))


def main() -> int:
    real = buildings._pitched
    tried: list[tuple[object, float]] = []

    def counting(rec: Record, chosen: str, height_cm: float, style: RoofStyle) -> object:
        built = real(rec, chosen, height_cm, style)
        tried.append((None if built is None else built.roof, style.overhang_cm))
        return built

    cases = shortened = violations = lost = 0
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
                            rec = record(kind, shape, ring, height, style, pitch, overhang)
                            used = buildings.style_for(rec, base)
                            chosen = style
                            floor = buildings.EDGE_FLOOR_SHARE * eave_floor(used, height)
                            tried.clear()
                            buildings._pitched = counting
                            try:
                                roof = buildings._kept_up(rec, chosen, height, used)
                            finally:
                                buildings._pitched = real
                            cases += 1
                            builds.append(len(tried))
                            if roof is None:
                                if real(rec, chosen, height, dataclasses.replace(used, overhang_cm=0.0)) is not None:
                                    lost += 1
                                continue
                            found = next(cm for mesh, cm in tried if mesh is roof.roof)
                            lowest = float(roof.roof.positions[:, 2].min())
                            without = real(rec, chosen, height, dataclasses.replace(used, overhang_cm=0.0))
                            if lowest < floor - 1e-3 and not (found == 0.0 and without is not None):
                                violations += 1
                            if found >= used.overhang_cm - buildings.OVERHANG_NUDGE_CM - 1e-9:
                                continue

                            def holds(cm: float, rec: Record = rec, chosen: str = chosen,
                                      used: RoofStyle = used, floor: float = floor,
                                      height: float = height) -> bool:
                                built = real(rec, chosen, height, dataclasses.replace(used, overhang_cm=cm))
                                return built is not None and float(built.roof.positions[:, 2].min()) >= floor - 1e-6

                            low, high = 0.0, used.overhang_cm
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
    print(f"floor violations {violations}; roofs lost {lost}")
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
