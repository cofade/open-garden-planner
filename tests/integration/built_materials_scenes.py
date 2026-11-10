"""The built world's materials on a real renderer (#801, #803) — scenes for the render tier.

Not a test module. ``quick3d_render_driver.py`` runs ``scenario_built_materials`` (scenario
``built_materials``) in its real-QPA process; ``test_built_materials_render.py`` judges the
frames. The scene definitions are plain, engine-free functions both halves import.

THE CLASS ROW: one item of every surface the builders name — a trampoline (rubber mat,
plastic pad, steel frame), a bench (iron, teak), a grill (enamel), a parasol (canvas), a
terracotta pot, a bird bath (stone), a house (plaster, roof tiles, timber, window panes),
a tool shed (wood cladding, shingles), a garden wall (masonry) and a raised bed (wood,
soil) — under the family garden's golden-hour sun (15.2 degrees, azimuth 288.8, its
board's sun), the camera FACING it: the configuration in which a specular sheen in the
sun's colour is strongest (#803: a black mat read tan there).

THE MASKS are the engine's own frames: every surface painted white or black by a
registry that wraps the production one (``KeyRegistry``), one frame per bit of the
surface's number (``CLASS_IDS``) plus an all-black frame — a pixel whose difference to
the black frame is clearly on or off in every bit frame belongs to that surface. The
geometry is the production geometry, so a mask cannot describe another scene.

THE REFERENCES: the same frame with every surface's specular off (``diffuse``: what the
light alone does to a part's colour — the judge compares a material's look against it),
and frames with the roofs' and walls' detail picture off (``flat``: what #801 changed).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from types import MappingProxyType
from typing import Any

import numpy as np

from open_garden_planner.core.scene3d import (
    GroundSpec,
    Material,
    Mesh,
    MeshPart,
    Record,
    SunState,
    Transform,
)
from open_garden_planner.core.scene3d.materials import DEFAULT_SURFACE, SURFACES
from open_garden_planner.core.scene3d.mesh import surface_pieces
from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot
from tests.unit.scene3d_builder_cases import circle_record, line_record, polygon_record, rectangle

SIZE = (640, 360)
GROUND = GroundSpec(width_cm=3000.0, depth_cm=3000.0)
#: The family garden's board sun at golden hour (Berlin, 21 June 17:30 UTC).
GOLDEN_SUN = SunState(elevation_deg=15.2, azimuth_deg=288.8)
NOON_SUN = SunState(elevation_deg=60.9, azimuth_deg=176.1)
#: Facing the sun: 6.5 m from the trampoline along the sun's azimuth, 2.6 m up - the
#: board camera's angle on the family garden's trampoline (the survey's tan mat). Every
#: item stands inside that view (``row_records``).
ROW_SHOT = PerspectiveShot(eye=(2215.0, 1241.0, 260.0), target=(1400.0, 1518.0, 100.0), fov_deg=52.0)
#: Close on the house's south roof slope, from the south-east (the board's roof shots).
ROOF_SHOT = PerspectiveShot(eye=(1296.0, 1985.0, 820.0), target=(896.0, 2651.0, 360.0), fov_deg=40.0)
#: The pond seen at the mirror angle of a 20-degree morning sun from the east.
POND_SUN = SunState(elevation_deg=20.0, azimuth_deg=90.0)
#: Three walls close, each on its SHADED side under the golden-hour sun (the survey's navy
#: slab): the garden wall's south face, the house's east gable, the shed's east wall. The
#: middle of each frame is wall only (``WALL_BOX``: the judge's mask).
WALL_SHOTS = {
    "masonry": PerspectiveShot(eye=(1257.0, 2060.0, 80.0), target=(1257.0, 2306.0, 75.0), fov_deg=40.0),
    "plaster": PerspectiveShot(eye=(1546.0, 2641.0, 180.0), target=(1196.0, 2641.0, 170.0), fov_deg=40.0),
    "wood_cladding": PerspectiveShot(eye=(918.0, 982.0, 120.0), target=(748.0, 982.0, 110.0), fov_deg=40.0),
}
#: (x0, y0, x1, y1) as shares of each wall shot's frame where it shows wall only (the
#: house's gable has a window in its middle: the box is left of it).
WALL_BOXES = {"masonry": (0.25, 0.25, 0.75, 0.75), "plaster": (0.08, 0.2, 0.3, 0.9),
              "wood_cladding": (0.33, 0.25, 0.67, 0.9)}


def _placed(record: Record, item_id: str, east: float, north: float, **params: Any) -> Record:
    merged = dict(record.params)
    merged.update(params)
    merged["seed"] = item_id
    return dataclasses.replace(record, item_id=item_id, transform=Transform(east_cm=east, north_cm=north),
                               params=type(record.params)(merged))


def row_records() -> dict[str, Record]:
    """The class row (module docstring)."""
    pot = dataclasses.replace(circle_record("CONTAINER_ROUND", 30.0, 40.0),
                              material=Material("CONTAINER_ROUND", fill_rgba=(202, 115, 65, 255)))
    shed = dataclasses.replace(polygon_record("TOOL_SHED", rectangle(200.0, 150.0), 250.0, shape="rectangle"),
                               material=Material("TOOL_SHED", fill_rgba=(160, 130, 90, 255)))
    wall = dataclasses.replace(line_record("WALL", ((-150.0, 0.0), (150.0, 0.0)), 150.0, width=5.0),
                               material=Material("WALL", stroke_rgba=(130, 130, 120, 255)))
    # each at a distance along the sun's azimuth from the camera and a side offset inside
    # its view (computed once: d = 420 ... 1700 cm); the house, the shed and the wall stand
    # to the sides, so their low-sun shadows (cast toward the camera) miss the small things
    items = [
        _placed(circle_record("TRAMPOLINE", 140.0, 90.0), "trampoline", 1600.0, 1450.0),
        _placed(polygon_record("BENCH", rectangle(180.0, 60.0), 85.0, shape="rectangle"), "bench",
                1266.0, 1247.0),
        _placed(circle_record("BBQ_GRILL", 30.0, 90.0), "grill", 1684.0, 1232.0),
        _placed(circle_record("PARASOL", 140.0, 230.0), "parasol", 1406.0, 1812.0),
        _placed(pot, "pot", 1785.0, 1282.0, container_material="terracotta"),
        _placed(circle_record("BIRD_BATH", 25.0, 90.0), "bath", 1837.0, 1528.0),
        _placed(polygon_record("HOUSE", rectangle(600.0, 400.0), 450.0,
                               params={"ridge": ((-300.0, 0.0), (300.0, 0.0))}), "house", 896.0, 2641.0),
        _placed(shed, "shed", 648.0, 982.0),
        _placed(wall, "wall", 1257.0, 2306.0),
        _placed(polygon_record("RAISED_BED", rectangle(300.0, 120.0), 40.0), "bed", 1631.0, 1884.0),
    ]
    return {record.item_id: record for record in items}


def pond_records() -> dict[str, Record]:
    record = circle_record("POND_POOL", 160.0, None)
    return {"pond": dataclasses.replace(
        _placed(record, "pond", 1500.0, 1500.0),
        material=Material("POND_POOL", fill_rgba=(77, 146, 197, 255), pattern="WATER"))}


def pond_shot() -> PerspectiveShot:
    """Looking toward the morning sun, pitched down by its elevation: the mirror angle."""
    distance = 900.0
    height = distance * float(np.tan(np.radians(POND_SUN.elevation_deg)))
    return PerspectiveShot(eye=(1500.0 - distance, 1500.0, height), target=(1500.0, 1500.0, 0.0), fov_deg=40.0)


#: Every surface a mask can name, numbered from 1 (0 is "no built part"); the judge reads
#: the numbers back from ``result.json``.
CLASS_IDS: Mapping[str, int] = MappingProxyType(
    {name: index + 1 for index, name in enumerate(sorted(SURFACES))})
BITS = max(CLASS_IDS.values()).bit_length()
#: Which item and 2D colour (sRGB) stands for each class in the row, for the hue judge:
#: the colour of the part as the canvas draws it (a tinted part: the item's own colour).
ROW_CLASS_COLOURS: Mapping[str, tuple[int, int, int]] = MappingProxyType({
    "rubber": (0x30, 0x33, 0x36), "plastic": (0x42, 0x7B, 0xC2), "steel": (0xAD, 0xB4, 0xBC),
    "iron": (0x4C, 0x52, 0x5A), "wood": (0xA0, 0x6A, 0x3A), "enamel": (0x31, 0x35, 0x38),
    "canvas": (0xD6, 0x5D, 0x4B), "terracotta": (202, 115, 65), "stone": (0xA2, 0x9D, 0x93),
    "plaster": (0xC4, 0xAE, 0x86), "glass_pane": (0x47, 0x6F, 0x8F),
    "wood_cladding": (160, 130, 90), "shingle": (0x78, 0x69, 0x5A), "masonry": (130, 130, 120),
    "soil": (0x57, 0x3C, 0x26),
})


def _painted(part: MeshPart, value_of: Callable[[str], float]) -> MeshPart:
    """``part`` with every triangle painted ``value_of(its surface)`` (0..1), untinted."""
    pieces = surface_pieces(part)
    if len(pieces) == 1:
        name = part.surface or DEFAULT_SURFACE
        colours = np.full_like(part.mesh.colors, value_of(name))
        colours[:, 3] = 1.0
        mesh = part.mesh
        return dataclasses.replace(part, tinted=False, fill_texture=False, mesh=Mesh.from_arrays(
            mesh.positions, mesh.normals, colours, mesh.uvs, mesh.indices))
    colours = np.array(part.mesh.colors, dtype=np.float32)
    first = 0
    for name, count in part.surface_runs:
        rows = np.unique(part.mesh.indices[first:first + count])
        colours[rows, :3] = value_of(name)
        first += count
    mesh = part.mesh
    return dataclasses.replace(part, tinted=False, mesh=Mesh.from_arrays(
        mesh.positions, mesh.normals, colours, mesh.uvs, mesh.indices))


class KeyRegistry:
    """The production registry with each built part's surfaces painted by ``value_of``
    (plants and other kinds black: they are no class)."""

    def __init__(self, base: Any, value_of: Callable[[str], float]) -> None:
        self._base = base
        self._value_of = value_of
        self._builders: dict[str, Callable[[Record], tuple[MeshPart, ...]]] = {}
        self.version = getattr(base, "version", None)

    def builder_for(self, kind: str) -> Callable[[Record], tuple[MeshPart, ...]]:
        if kind not in self._builders:
            inner = self._base.builder_for(kind)

            def build(record: Record, inner: Callable[[Record], tuple[MeshPart, ...]] = inner
                      ) -> tuple[MeshPart, ...]:
                return tuple(_painted(part, self._value_of) if part.material_kind in ("vc", "roof")
                             else part for part in inner(record))

            self._builders[kind] = build
        return self._builders[kind]

    def build(self, record: Record) -> tuple[MeshPart, ...]:
        return self.builder_for(record.kind)(record)

    def kinds(self) -> frozenset[str]:
        return frozenset(self._base.kinds())


@contextmanager
def surfaces_as(change: Callable[[Any], Any]) -> Iterator[None]:
    """Every surface ``change``d while the block runs — what the host reads
    (``quick3d.materials.SURFACES``; a detail picture is looked up in the core table)."""
    from open_garden_planner.core.scene3d import materials as core_materials
    from open_garden_planner.ui.view3d.quick3d import materials as engine_materials

    saved = engine_materials.SURFACES, core_materials.SURFACES
    table = MappingProxyType({name: change(surface) for name, surface in saved[0].items()})
    engine_materials.SURFACES = table
    core_materials.SURFACES = table
    try:
        yield
    finally:
        engine_materials.SURFACES, core_materials.SURFACES = saved


def no_specular(surface: Any) -> Any:
    return dataclasses.replace(surface, specular=0.0)


def no_detail(surface: Any) -> Any:
    return dataclasses.replace(surface, detail=None)


def scenario_built_materials(ctx: Any) -> dict[str, Any]:
    """#801 / #803 (module docstring): the class row facing a golden-hour sun with its
    diffuse reference and its masks, the house's roof close at noon and at the low sun
    with flat controls, and a pond at the mirror angle of a morning sun."""
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.core.scene3d.look import look_for

    registry = production_registry()
    out: dict[str, Any] = {"class_ids": dict(CLASS_IDS), "bits": BITS}

    def frame(name: str, records: Mapping[str, Record], shot: PerspectiveShot, sun: SunState,
              reg: Any = registry) -> dict[str, Any]:
        return ctx.offscreen(name, records, shot=shot, sun=sun, ground=GROUND, size=SIZE, registry=reg,
                             look=look_for(sun, "high"), sky_light=True)

    row = row_records()
    out["row"] = frame("bm_row", row, ROW_SHOT, GOLDEN_SUN)
    with surfaces_as(no_specular):
        out["row_diffuse"] = frame("bm_row_diffuse", row, ROW_SHOT, GOLDEN_SUN)
    with surfaces_as(no_detail):
        out["row_flat"] = frame("bm_row_flat", row, ROW_SHOT, GOLDEN_SUN)
    out["row_black"] = frame("bm_row_black", row, ROW_SHOT, GOLDEN_SUN, KeyRegistry(registry, lambda _n: 0.0))
    for bit in range(BITS):
        def value(name: str, bit: int = bit) -> float:
            return 1.0 if (CLASS_IDS[name] >> bit) & 1 else 0.0
        out[f"row_bit{bit}"] = frame(f"bm_row_bit{bit}", row, ROW_SHOT, GOLDEN_SUN, KeyRegistry(registry, value))

    for name, sun in (("noon", NOON_SUN), ("low", GOLDEN_SUN)):
        out[f"roof_{name}"] = frame(f"bm_roof_{name}", row, ROOF_SHOT, sun)
        with surfaces_as(no_detail):
            out[f"roof_{name}_flat"] = frame(f"bm_roof_{name}_flat", row, ROOF_SHOT, sun)
    for tag, level in (("white", 1.0), ("black", 0.0)):
        out[f"roof_key_{tag}"] = frame(
            f"bm_roof_key_{tag}", row, ROOF_SHOT, NOON_SUN,
            KeyRegistry(registry, lambda name, level=level: level if name == "roof_tile" else 0.5))

    for surface, shot in WALL_SHOTS.items():
        out[f"wall_{surface}"] = frame(f"bm_wall_{surface}", row, shot, GOLDEN_SUN)
        with surfaces_as(no_detail):
            out[f"wall_{surface}_flat"] = frame(f"bm_wall_{surface}_flat", row, shot, GOLDEN_SUN)

    pond = pond_records()
    out["pond"] = frame("bm_pond", pond, pond_shot(), POND_SUN)
    for tag, level in (("white", 1.0), ("black", 0.0)):
        # the water part is no surface kind: its key is its tint (the item's fill colour)
        tinted = {"pond": dataclasses.replace(
            pond["pond"], material=Material("POND_POOL", fill_rgba=(255, 255, 255, 255) if level else (0, 0, 0, 255),
                                            pattern="WATER"))}
        out[f"pond_key_{tag}"] = frame(f"bm_pond_key_{tag}", tinted, pond_shot(), POND_SUN)
    return out
