"""How the built world's 3D shadows compare with the 2D shadow model, kind by kind.

Committed (Phase 17 L1.6, review round 1) so the table in ADR-059's builders
addendum, §8.29.6, FR-SUN-11 and the Shadows row of ``ogp-lush-cinematic`` §1 has a
source a reader can re-run. From the repo root:

    venv/Scripts/python.exe scripts/measure_built_world_shadows.py           # the table
    venv/Scripts/python.exe scripts/measure_built_world_shadows.py --check   # exit 1 on drift

What is compared, for one item at a sun elevation:

* **2D** — what the sun & shade overlay and the hours-of-sun map cast for it:
  ``core.shadow_geometry.compute_scene_shadows`` of its footprint (for a line item
  the STROKE strip, ``polyline_footprint``) extruded to its height. A solid prism.
* **3D** — the ground shadow of the mesh its production builder makes: every
  triangle projected along the sun ray onto the ground, united. What a shadow map
  of that mesh shows, without the map's resolution.

and three numbers: the 3D area divided by the 2D area, the intersection over
union (IoU) of the two, and the REACH difference — how much further (+) or less
far (-) the 3D shadow extends along the shadow direction than the 2D one, in cm:
where the shadow's TIP is. The truth gate "Shadows" (``ogp-lush-cinematic`` §1,
IoU >= 0.85) is defined on a solid box caster, where both models are the same
solid. The built world departs from the prism in four stated ways, and this table
is what each costs:

* a LINE has no thickness in the plan (its stroke is a line weight), so the 3D
  body has a nominal section: wider than the stroke for a wall, a stone-wall or
  hedge fence — a wider shadow, more so at a high sun;
* a PICKET, METAL or CHAIN-LINK fence is mostly air: its 3D shadow is the bars'
  and wires', a fraction of the solid strip the 2D model casts;
* a HOUSE or shed has a gable roof where 2D extrudes a flat-topped prism to the
  ridge height — less shadow square to the ridge, and eaves that overhang. The
  2D prism's top edge is at the FAR WALL, the gable's ridge is mid-house: with the
  sun square to the ridge the 3D tip is short by up to half the depth minus the
  overhang (270 cm less 30 on a 5.4 m deep house);
* a POT tapers and a hedge is a leaf shell drawn in from its outline.

A raised bed and a box are prisms in both: IoU 1.00, reach equal. A plain panel
(a line in a style no builder knows) is the stroke strip itself: IoU 1.00.

**Measuring conditions.** One item on flat ground, the sun square to a straight
10 m line (or to / along the ridge, as the case says), the mesh projected
ANALYTICALLY — no shadow map, no texel. The numbers are references for the
BUILDERS. An engine render reads lower for members near one shadow-map texel
(0.8 cm wires, 1.6 cm bars) through no fault of the builder.

Uses numpy, pyclipper and the Qt-free ``core`` modules, and constructs nothing of Qt.

**It keeps out of the owner's settings and data — measured, not assumed.** Importing
the ``core`` package does load the app's settings module, its project loader and
PyQt6's modules into this process. But run as above the script constructs no
``QSettings`` and no Qt application, opens no plan and writes no file:
``tests/unit/test_scene3d_shadow_agreement.py`` runs both forms in a process of its
own with each of those watched. A change that makes it load a plan or ask a setting
must isolate it first, before its first app import (the pattern: ``isolate`` in
``scripts/measure_plant_art_3d.py``) — outside pytest the settings are the owner's.
"""
from __future__ import annotations

import logging
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pyclipper  # noqa: E402

from open_garden_planner.core.scene3d import (  # noqa: E402
    Material,
    MeshPart,
    Params,
    Record,
    Transform,
    group_rings,
)
from open_garden_planner.core.scene3d.builders import production_registry  # noqa: E402
from open_garden_planner.core.shadow_geometry import (  # noqa: E402
    circle_footprint,
    compute_scene_shadows,
    polyline_footprint,
    shadow_direction_scene,
)

ELEVATIONS_DEG = (15.0, 35.0, 60.0)
#: Clipper grid: 1 unit = 0.001 cm, as ``core.shadow_geometry``.
SCALE = 1000.0
#: ``--check`` and the test fail when a number has moved by more than this.
TOLERANCE = 0.05
#: The same for a reach difference, in cm.
REACH_TOLERANCE_CM = 1.0
#: A straight 10 m line running east-west; the sun due south is square to it.
LINE = ((-500.0, 0.0), (500.0, 0.0))
SOUTH, EAST = 180.0, 90.0

Point = tuple[float, float]
Ring = tuple[Point, ...]


@dataclass(frozen=True)
class Case:
    """One item and the sun bearing it is measured at."""

    name: str
    record: Record
    azimuth_deg: float
    why: str


@dataclass(frozen=True)
class Row:
    """One case's result: per elevation, 3D area / 2D area, the IoU, and how much
    further the 3D shadow reaches along the shadow direction than the 2D one (cm)."""

    name: str
    why: str
    ratio: tuple[float, ...]
    iou: tuple[float, ...]
    reach_cm: tuple[float, ...]


def _rectangle(width: float, depth: float) -> Ring:
    w, d = width / 2.0, depth / 2.0
    return ((-w, -d), (w, -d), (w, d), (-w, d))


def _line(kind: str, style: str | None, stroke_cm: float, height_cm: float) -> Record:
    """A polyline record as the snapshot makes it: centre line, stroke width, and
    the stroke strip — the 2D caster's footprint — as its (outer) footprint ring."""
    regions = group_rings([tuple(ring) for ring in polyline_footprint(list(LINE), stroke_cm)])
    assert len(regions) == 1 and not regions[0][1]  # an open straight line: one ring, no hole
    params: dict[str, object] = {"seed": f"{kind}-{style}"}
    if style is not None:
        params["path_style"] = style
    return Record(f"{kind}-{style}", kind, "polyline", (regions[0][0],), Transform(),
                  Material(kind, None, (139, 69, 19, 255)), height_cm=height_cm, path=LINE,
                  path_width_cm=stroke_cm, params=Params(params))


def _polygon(kind: str, ring: Ring, height_cm: float, **params: object) -> Record:
    return Record(kind, kind, "polygon", (ring,), Transform(), Material(kind, (200, 180, 140, 255)),
                  height_cm=height_cm, params=Params({"seed": kind, **params}))


def _circle(kind: str, radius_cm: float, height_cm: float, **params: object) -> Record:
    ring = tuple((round(x, 7) + 0.0, round(y, 7) + 0.0)
                 for x, y in circle_footprint(0.0, 0.0, radius_cm))
    return Record(kind, kind, "circle", (ring,), Transform(), Material(kind, (170, 110, 70, 255)),
                  height_cm=height_cm,
                  params=Params({"seed": kind, "radius_cm": radius_cm, **params}))


#: Stroke widths are the 2D style presets' (``PATH_FENCE_STYLES`` / ``OBJECT_STYLES``;
#: ``core/object_types.py`` imports Qt, so they are repeated here and pinned by
#: ``tests/unit/test_scene3d_shadow_agreement.py``). Heights are the type defaults.
STROKE_CM = {"WOODEN_FENCE": 3.0, "METAL_FENCE": 2.5, "CHAIN_LINK": 2.0, "HEDGE_FENCE": 8.0,
             "STONE_WALL": 5.0, "WALL": 4.0}
RIDGE = ((-450.0, 0.0), (450.0, 0.0))


def cases() -> tuple[Case, ...]:
    porous, section = "porosity", "nominal section"
    return (
        Case("picket fence", _line("FENCE", "WOODEN_FENCE", STROKE_CM["WOODEN_FENCE"], 120.0),
             SOUTH, porous),
        Case("metal fence", _line("FENCE", "METAL_FENCE", STROKE_CM["METAL_FENCE"], 120.0),
             SOUTH, porous),
        Case("chain-link fence", _line("FENCE", "CHAIN_LINK", STROKE_CM["CHAIN_LINK"], 120.0),
             SOUTH, porous),
        Case("hedge fence", _line("FENCE", "HEDGE_FENCE", STROKE_CM["HEDGE_FENCE"], 120.0),
             SOUTH, section),
        Case("stone-wall fence", _line("FENCE", "STONE_WALL", STROKE_CM["STONE_WALL"], 120.0),
             SOUTH, section),
        Case("plain panel (unknown style)", _line("FENCE", "GRAVEL_PATH", 3.0, 120.0),
             SOUTH, "none: the stroke strip itself"),
        Case("wall", _line("WALL", None, STROKE_CM["WALL"], 200.0), SOUTH, section),
        Case("house, sun square to the ridge",
             _polygon("HOUSE", _rectangle(900.0, 540.0), 450.0, ridge=RIDGE), SOUTH,
             "gable roof vs prism"),
        Case("house, sun along the ridge",
             _polygon("HOUSE", _rectangle(900.0, 540.0), 450.0, ridge=RIDGE), EAST,
             "gable roof vs prism"),
        Case("shed, sun square to the ridge", _polygon("GARAGE_SHED", _rectangle(400.0, 300.0), 250.0),
             SOUTH, "gable roof vs prism"),
        Case("raised bed", _polygon("RAISED_BED", _rectangle(300.0, 120.0), 40.0), SOUTH,
             "none: a prism"),
        Case("container (box)", _polygon("CONTAINER", _rectangle(80.0, 40.0), 30.0,
                                          container_material="wood"), SOUTH, "none: a prism"),
        Case("terracotta pot", _circle("CONTAINER_ROUND", 25.0, 30.0, container_material="terracotta"),
             SOUTH, "taper"),
        Case("round tub", _circle("CONTAINER_ROUND", 25.0, 30.0, container_material="plastic"),
             SOUTH, "taper"),
        Case("hedge (polygon)", _polygon("HEDGE_POLYGON", _rectangle(400.0, 60.0), 150.0), SOUTH,
             "leaf shell"),
        Case("hedge (section)", _polygon("HEDGE_SECTION", _rectangle(200.0, 50.0), 150.0), SOUTH,
             "leaf shell"),
        # Phase 17 L4 (#388): the roof styles and the objects that cast
        Case("house, hip roof", _polygon("HOUSE", _rectangle(900.0, 540.0), 450.0, ridge=RIDGE,
                                         roof_style="hip"), SOUTH, "hip roof vs prism"),
        Case("house, single-slope roof", _polygon("HOUSE", _rectangle(900.0, 540.0), 450.0,
                                                  ridge=RIDGE, roof_style="shed"),
             SOUTH, "single-slope roof vs prism"),
        Case("house, flat roof", _polygon("HOUSE", _rectangle(900.0, 540.0), 450.0, ridge=RIDGE,
                                          roof_style="flat"), SOUTH, "flat roof: the prism"),
        Case("table", _polygon("TABLE_RECTANGULAR", _rectangle(160.0, 90.0), 75.0), SOUTH,
             "porosity: a top on legs"),
        Case("picnic table", _polygon("PICNIC_TABLE", _rectangle(180.0, 150.0), 75.0), SOUTH,
             "porosity: boards and A-frames"),
        Case("grill", _circle("BBQ_GRILL", 30.0, 90.0), SOUTH, "porosity: a kettle on legs"),
        Case("greenhouse", _polygon("GREENHOUSE", _rectangle(300.0, 200.0), 220.0), SOUTH,
             "porosity: the glass casts nothing"),
        Case("trampoline", _circle("TRAMPOLINE", 150.0, 90.0), SOUTH, "porosity: a mat on legs"),
    )


def _to_grid(polygon: Sequence[Sequence[float]]) -> list[tuple[int, int]]:
    return [(round(x * SCALE), round(y * SCALE)) for x, y in polygon]


def _area_cm2(paths: Sequence[Sequence[tuple[int, int]]]) -> float:
    return float(sum(pyclipper.Area(path) for path in paths)) / (SCALE * SCALE)


def _clip(subject: Sequence[Sequence[tuple[int, int]]], clip: Sequence[Sequence[tuple[int, int]]],
          operation: int) -> list[list[tuple[int, int]]]:
    clipper = pyclipper.Pyclipper()
    clipper.AddPaths(subject, pyclipper.PT_SUBJECT, True)
    clipper.AddPaths(clip, pyclipper.PT_CLIP, True)
    result: list[list[tuple[int, int]]] = clipper.Execute(
        operation, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    return result


def mesh_shadow(parts: Sequence[MeshPart], elevation_deg: float,
                azimuth_deg: float) -> list[list[tuple[int, int]]]:
    """The ground shadow of the shadow-casting parts: every triangle moved along the
    sun ray onto z = 0 (a point at height z lands ``z / tan a`` along the shadow
    direction), united. Item-local frame; +y is north, as in the scene."""
    reach = 1.0 / math.tan(math.radians(elevation_deg))
    direction = shadow_direction_scene(azimuth_deg)
    clipper = pyclipper.Pyclipper()
    added = False
    for part in parts:
        mesh = part.mesh
        if not part.casts_shadow or not mesh.vertex_count:
            continue
        corners = mesh.positions.astype(np.float64)[mesh.indices]  # (t, 3, 3)
        x = corners[:, :, 0] + corners[:, :, 2] * reach * direction[0]
        y = corners[:, :, 1] + corners[:, :, 2] * reach * direction[1]
        grid = np.rint(np.stack([x, y], axis=2) * SCALE).astype(np.int64)
        for triangle in grid.tolist():
            path = [tuple(point) for point in triangle]
            if abs(pyclipper.Area(path)) < 1.0:
                continue  # seen edge-on from the sun
            if not pyclipper.Orientation(path):
                path.reverse()
            clipper.AddPath(path, pyclipper.PT_SUBJECT, True)
            added = True
    if not added:
        return []
    union: list[list[tuple[int, int]]] = clipper.Execute(
        pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    return union


def caster_shadow(record: Record, elevation_deg: float,
                  azimuth_deg: float) -> list[list[tuple[int, int]]]:
    """The 2D model's shadow of the record: its footprint ring(s) to its height."""
    polygons = compute_scene_shadows(
        [(list(ring), record.height_cm) for ring in record.footprints], elevation_deg, azimuth_deg)
    return [_to_grid(polygon) for polygon in polygons]


def reach_cm(paths: Sequence[Sequence[tuple[int, int]]], azimuth_deg: float) -> float:
    """How far the shadow extends along the shadow direction, from the item's origin:
    the position of its TIP, in cm."""
    east, north = shadow_direction_scene(azimuth_deg)
    return max(x * east + y * north for path in paths for x, y in path) / SCALE


def measure(selected: Sequence[Case] | None = None) -> tuple[Row, ...]:
    registry = production_registry()
    rows = []
    for case in selected if selected is not None else cases():
        parts = registry.build(case.record)
        ratios, ious, reaches = [], [], []
        for elevation in ELEVATIONS_DEG:
            in_3d = mesh_shadow(parts, elevation, case.azimuth_deg)
            in_2d = caster_shadow(case.record, elevation, case.azimuth_deg)
            both = _area_cm2(_clip(in_3d, in_2d, pyclipper.CT_INTERSECTION))
            either = _area_cm2(_clip(in_3d, in_2d, pyclipper.CT_UNION))
            ratios.append(_area_cm2(in_3d) / _area_cm2(in_2d))
            ious.append(both / either)
            reaches.append(reach_cm(in_3d, case.azimuth_deg) - reach_cm(in_2d, case.azimuth_deg))
        rows.append(Row(case.name, case.why, tuple(ratios), tuple(ious), tuple(reaches)))
    return tuple(rows)


#: The table as documented (ADR-059 builders addendum, §8.29.6, ``ogp-lush-cinematic``
#: §1): name -> (3D / 2D area, IoU, reach 3D - 2D in cm), each at 15 / 35 / 60 degrees.
#: Measured by this script on 2026-10-11; ``--check`` and the test hold the builders to
#: it within ``TOLERANCE`` (``REACH_TOLERANCE_CM`` for the reach). A builder change that
#: moves a number updates this table AND the docs.
Triple = tuple[float, float, float]
DOCUMENTED: dict[str, tuple[Triple, Triple, Triple]] = {
    "picket fence": ((0.67, 0.68, 0.70), (0.65, 0.66, 0.68), (2.0, 2.0, 2.4)),
    "metal fence": ((0.19, 0.21, 0.24), (0.19, 0.20, 0.24), (0.8, 0.8, 0.8)),
    "chain-link fence": ((0.13, 0.14, 0.19), (0.12, 0.13, 0.19), (1.5, 1.5, 1.5)),
    "hedge fence": ((1.04, 1.13, 1.31), (0.96, 0.89, 0.76), (19.6, 19.5, 19.6)),
    "stone-wall fence": ((1.06, 1.15, 1.37), (0.94, 0.87, 0.73), (14.5, 14.5, 15.3)),
    "plain panel (unknown style)": ((1.00, 1.00, 1.00), (1.00, 1.00, 1.00), (0.0, 0.0, 0.0)),
    "wall": ((1.04, 1.10, 1.24), (0.96, 0.91, 0.81), (15.0, 15.0, 15.8)),
    "house, sun square to the ridge": ((0.92, 0.81, 0.92), (0.85, 0.74, 0.82),
                                       (-270.0, -270.0, -108.2)),
    "house, sun along the ridge": ((0.90, 0.99, 1.06), (0.82, 0.86, 0.88), (30.0, 30.0, 30.0)),
    "shed, sun square to the ridge": ((0.92, 0.93, 1.03), (0.85, 0.83, 0.88),
                                      (-150.0, -81.4, -21.0)),
    "raised bed": ((1.00, 1.00, 1.00), (1.00, 1.00, 1.00), (-0.6, -0.6, -0.3)),
    "container (box)": ((1.00, 0.99, 0.99), (1.00, 0.99, 0.99), (-0.6, -0.6, -0.3)),
    "terracotta pot": ((0.83, 0.81, 0.81), (0.83, 0.81, 0.81), (-0.6, -0.6, -0.3)),
    "round tub": ((0.91, 0.89, 0.89), (0.91, 0.89, 0.89), (-0.5, -0.5, -0.3)),
    "hedge (polygon)": ((0.98, 0.96, 0.94), (0.97, 0.96, 0.94), (3.6, 4.0, 4.4)),
    "hedge (section)": ((0.97, 0.96, 0.94), (0.96, 0.95, 0.93), (2.7, 3.0, 3.2)),
    # Phase 17 L4 (#388), measured 2026-10-26
    "house, hip roof": ((0.83, 0.80, 0.92), (0.79, 0.74, 0.83), (-270.0, -270.0, -105.3)),
    "house, single-slope roof": ((1.06, 1.08, 1.10), (0.94, 0.93, 0.91), (30.0, 30.0, 30.0)),
    "house, flat roof": ((1.02, 1.03, 1.04), (0.98, 0.97, 0.96), (15.0, 15.0, 15.0)),
    "table": ((0.38, 0.54, 0.70), (0.38, 0.54, 0.70), (-0.5, -0.5, -0.3)),
    "picnic table": ((0.37, 0.41, 0.57), (0.37, 0.41, 0.57), (-38.5, -38.5, -20.6)),
    "grill": ((0.28, 0.30, 0.36), (0.28, 0.30, 0.36), (-27.3, -23.0, -17.5)),
    "greenhouse": ((0.30, 0.23, 0.25), (0.30, 0.23, 0.25), (-97.5, -93.3, -38.3)),
    "trampoline": ((0.47, 0.64, 0.76), (0.47, 0.64, 0.76), (-1.0, -1.0, -1.0)),
}


def drift(rows: Sequence[Row]) -> list[str]:
    """What differs from ``DOCUMENTED`` by more than ``TOLERANCE`` (a reach: by more
    than ``REACH_TOLERANCE_CM``), as sentences."""
    problems = []
    if {row.name for row in rows} != set(DOCUMENTED):
        problems.append(f"cases differ: measured {sorted(row.name for row in rows)}, "
                        f"documented {sorted(DOCUMENTED)}")
    for row in rows:
        if row.name not in DOCUMENTED:
            continue
        ratio, iou, reach = DOCUMENTED[row.name]
        for label, measured, documented in (("area ratio", row.ratio, ratio), ("IoU", row.iou, iou)):
            for elevation, got, want in zip(ELEVATIONS_DEG, measured, documented, strict=True):
                if abs(got - want) > TOLERANCE:
                    problems.append(f"{row.name} at {elevation:g} deg: {label} {got:.2f}, "
                                    f"documented {want:.2f}")
        for elevation, got, want in zip(ELEVATIONS_DEG, row.reach_cm, reach, strict=True):
            if abs(got - want) > REACH_TOLERANCE_CM:
                problems.append(f"{row.name} at {elevation:g} deg: reach {signed(got)} cm, "
                                f"documented {signed(want)} cm")
    return problems


def signed(value_cm: float) -> str:
    """A reach difference as the tables print it: one decimal, signed, a plain 0.0."""
    return "0.0" if abs(value_cm) < 0.05 else f"{value_cm:+.1f}"


def cells(ratio: Sequence[float], iou: Sequence[float], reach: Sequence[float]) -> tuple[str, str, str]:
    """The three number cells of a table row, as every copy of the table writes them."""
    return (" / ".join(f"{value:.2f}" for value in ratio),
            " / ".join(f"{value:.2f}" for value in iou),
            " / ".join(signed(value) for value in reach))


def table(rows: Sequence[Row]) -> str:
    lines = ["each at a sun of 15 / 35 / 60 deg",
             "| Kind | 3D area / 2D area | IoU | Reach 3D - 2D (cm) | Why they differ |",
             "|---|---|---|---|---|"]
    for row in rows:
        ratio, iou, reach = cells(row.ratio, row.iou, row.reach_cm)
        lines.append(f"| {row.name} | {ratio} | {iou} | {reach} | {row.why} |")
    return "\n".join(lines)


def main(argv: Sequence[str]) -> int:
    # One case IS a line in a style no builder knows (the plain panel); the builders'
    # one-warning-per-style line about it is not news here.
    logging.getLogger("open_garden_planner.core.scene3d.builders.lines").setLevel(logging.ERROR)
    rows = measure()
    print(table(rows))
    if "--python" in argv:
        for row in rows:
            ratio = ", ".join(f"{value:.2f}" for value in row.ratio)
            iou = ", ".join(f"{value:.2f}" for value in row.iou)
            reach = ", ".join(f"{value + 0.0:.1f}" for value in row.reach_cm)
            print(f'    "{row.name}": (({ratio}), ({iou}), ({reach})),')
    if "--check" in argv:
        problems = drift(rows)
        for problem in problems:
            print("DRIFT:", problem)
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
