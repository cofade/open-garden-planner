"""What built parts are made of (#803): the surface classes, the one path from a palette
entry to the engine, and the drift guard between the Python table and the scene file.

Before #803 every built part reflected with one roughness (0.78) and one specular amount
(0.35), and a black rubber trampoline mat took a broad warm highlight from a low sun and
read tan (the 3D promo-readiness survey: luma 99, hue 23 degrees for #303336). Now each
palette entry names a surface (``builders/palette.py``), a tinted part names its own
(``MeshPart.surface``), a part of several surfaces lists them as runs
(``MeshPart.surface_runs``) and the engine draws one Model per run
(``mesh.surface_pieces``), whose numbers the host writes from
``core/scene3d/materials.SURFACES`` (``ui/view3d/quick3d/materials.surface_look``).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.scene3d import MeshPart
from open_garden_planner.core.scene3d.builders import palette, production_registry
from open_garden_planner.core.scene3d.builders.common import SURFACE_KINDS, with_surfaces
from open_garden_planner.core.scene3d.materials import (
    DEFAULT_SURFACE,
    DETAIL_PLANAR,
    DETAIL_UV,
    SURFACES,
    SurfaceDetail,
    detail_of,
)
from open_garden_planner.core.scene3d.mesh import surface_pieces
from open_garden_planner.ui.view3d.quick3d import materials as engine_materials
from tests.unit.scene3d_builder_cases import (
    CASES,
    STRAIGHT_PATH,
    circle_record,
    line_record,
    polygon_record,
    rectangle,
)
from tests.unit.test_scene3d_l4_objects import BOXED, ROUND, record_of

REGISTRY = production_registry()
QML = Path(engine_materials.__file__).resolve().parent / "qml" / "Garden.qml"
#: Qt Quick 3D switches a principled material's specular OFF at an amount of 0.01 or
#: less, and above it the amount barely moves a grazing highlight (measured, #803: a
#: black mat facing a 15-degree sun read luma 25.4 at 0.01, 62.8 at 0.015, 63.5 at 0.35).
SPECULAR_OFF_AT = 0.01


def _surface_of_triangles(part: MeshPart) -> list[str]:
    names = palette.surfaces_of_colours(part.mesh.colors[part.mesh.indices[:, 0]])
    return [name or DEFAULT_SURFACE for name in names]


def _all_parts() -> list[tuple[str, MeshPart]]:
    built = [(case.record.kind, part) for case in CASES for part in REGISTRY.build(case.record)]
    for kind, sizes in {**ROUND, **BOXED}.items():
        built += [(kind, part) for part in REGISTRY.build(record_of(kind, sizes[0], None))]
    return built


ALL_PARTS = _all_parts()


# ── the table ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("entry", palette.ALL, ids=lambda e: e.name)
def test_every_palette_entry_names_a_surface(entry: palette.PaletteColor) -> None:
    """The drift guard's first half: no 2D colour reaches the engine without saying what
    it is made of."""
    assert entry.surface in SURFACES


def test_the_colour_lookup_is_the_palette() -> None:
    assert len(palette.SURFACE_BY_COLOUR) == len(palette.ALL)
    for entry in palette.ALL:
        colours = np.asarray([entry.linear], dtype=np.float32)
        assert palette.surfaces_of_colours(colours) == [entry.surface]
    assert palette.surfaces_of_colours(np.ones((1, 4), dtype=np.float32)) == [None]  # TINT


@pytest.mark.parametrize("name", sorted(SURFACES))
def test_every_surface_is_a_physical_material(name: str) -> None:
    surface = SURFACES[name]
    assert surface.name == name
    assert 0.0 < surface.roughness <= 1.0
    assert 0.0 <= surface.specular <= 1.0
    if surface.detail is not None:
        assert surface.detail.mapping in (DETAIL_UV, DETAIL_PLANAR)
        assert surface.detail.tile_cm > 0.0 and surface.detail.fade_cm > 0.0
        assert 0.0 < surface.detail.contrast <= 1.0 and surface.detail.normal >= 0.0


def test_the_default_surface_is_the_look_every_built_part_had_before() -> None:
    assert (SURFACES[DEFAULT_SURFACE].roughness, SURFACES[DEFAULT_SURFACE].specular) == (0.78, 0.35)


def test_a_dull_dark_surface_takes_no_specular_at_all() -> None:
    """#803's defect, at the table: a rubber mat (and canvas) must have its specular
    OFF — any amount Qt does not switch off gives a grazing highlight in the sun's colour
    (the issue's 0.05 still read luma 62.8 against 25.4 without)."""
    for name in ("rubber", "canvas"):
        assert SURFACES[name].specular <= SPECULAR_OFF_AT, name


def test_only_roofs_and_walls_carry_a_picture_and_a_roof_s_tiles_are_the_plan_s_size() -> None:
    pictured = {name for name, surface in SURFACES.items() if surface.detail is not None}
    assert pictured == {"roof_tile", "shingle", "plaster", "masonry", "wood_cladding"}
    tiles = SURFACES["roof_tile"].detail
    assert isinstance(tiles, SurfaceDetail)
    # the canvas lays every pattern at 256 cm (core.scene3d.PATTERN_TILE_CM): one size in 2D and 3D
    assert (tiles.pattern, tiles.mapping, tiles.tile_cm) == ("ROOF_TILES", DETAIL_UV, 256.0)


def test_a_uv_picture_shows_on_roof_parts_only() -> None:
    assert detail_of("roof_tile", "roof") is not None
    assert detail_of("roof_tile", "vc") is None       # a block's tiled top has no roof uvs
    assert detail_of("plaster", "vc") is not None and detail_of("plaster", "roof") is not None
    assert detail_of("plaster", "glass") is None and detail_of("wood", "vc") is None


# ── the one path: builders -> parts -> pieces -> the Model's properties ──────


def test_every_built_part_knows_what_it_is_made_of() -> None:
    """Every vc and roof part a production builder makes names a surface, lists runs, or
    is a tinted / fill part (its builder's, else the default) - and every run is the
    palette's own reading of its triangles."""
    checked = 0
    for kind, part in ALL_PARTS:
        if part.material_kind not in SURFACE_KINDS:
            assert not part.surface_runs, (kind, part.name)
            continue
        if part.tinted or part.fill_texture:
            assert not part.surface_runs and (not part.surface or part.surface in SURFACES)
            continue
        assert bool(part.surface) != bool(part.surface_runs), (kind, part.name)
        per_triangle = _surface_of_triangles(part)
        if part.surface:
            # the palette's reading - or the surface its builder named (a house's
            # sandstone walls are rendered plaster: the recolour keeps the builder's)
            assert set(per_triangle) == {part.surface} or (kind, part.name) == ("HOUSE", "walls"),                 (kind, part.name)
        else:
            expected = [name for name, count in part.surface_runs for _ in range(count)]
            assert per_triangle == expected, (kind, part.name)
        checked += 1
    assert checked > 200


def test_the_pieces_keep_every_triangle_and_vertex_of_the_part() -> None:
    for kind, part in ALL_PARTS:
        pieces = surface_pieces(part)
        assert sum(piece.mesh.triangle_count for piece in pieces) == part.mesh.triangle_count
        if not part.surface_runs:
            assert pieces == (part,)
            continue
        assert [piece.surface for piece in pieces] == [name for name, _count in part.surface_runs]
        whole = part.mesh.positions[part.mesh.indices].reshape(-1, 3)
        joined = np.concatenate([piece.mesh.positions[piece.mesh.indices].reshape(-1, 3)
                                 for piece in pieces])
        assert np.array_equal(whole, joined), (kind, part.name)
        for piece in pieces:
            assert (piece.name, piece.material_kind, piece.casts_shadow, piece.tinted) == (
                part.name, part.material_kind, part.casts_shadow, part.tinted)
            piece.validate()


def test_the_trampoline_is_a_rubber_mat_a_plastic_pad_and_a_steel_frame() -> None:
    (part,) = REGISTRY.build(circle_record("TRAMPOLINE", 140.0, 90.0))
    assert part.name == "trampoline"                       # still ONE part for everything else
    by_surface = {piece.surface: piece for piece in surface_pieces(part)}
    assert set(by_surface) == {"plastic", "rubber", "steel"}
    mat = by_surface["rubber"].mesh.colors[:, :3]
    assert np.allclose(mat, palette.RUBBER.linear[:3])
    assert np.allclose(by_surface["plastic"].mesh.colors[:, :3], palette.PLASTIC_BLUE.linear[:3])


def test_walls_name_their_own_surface() -> None:
    house = REGISTRY.build(polygon_record("HOUSE", rectangle(900.0, 540.0), 450.0,
                                          params={"ridge": ((-450.0, 0.0), (450.0, 0.0))}))
    shed = REGISTRY.build(polygon_record("TOOL_SHED", rectangle(200.0, 150.0), 250.0))
    wall = REGISTRY.build(line_record("WALL", STRAIGHT_PATH, 200.0))
    assert next(p for p in house if p.name == "walls").surface == "plaster"
    assert next(p for p in shed if p.name == "walls").surface == "wood_cladding"
    assert wall[0].surface == "masonry"
    roof = next(p for p in house if p.name == "roof")
    assert [name for name, _count in roof.surface_runs] == ["roof_tile", "wood"]   # tiles, timber
    for style, surface in (("WOODEN_FENCE", "wood"), ("METAL_FENCE", "iron"), ("CHAIN_LINK", "steel")):
        (fence,) = REGISTRY.build(line_record("FENCE", STRAIGHT_PATH, 120.0, style=style))
        assert fence.surface == surface, style


def test_a_glasshouse_stays_glass_and_a_pergola_s_rafters_stay_timber() -> None:
    """#801's roof kinds without tiles: a glasshouse's roof and walls are the glass part
    (no surface, no picture) on a steel frame and a concrete base, and a pergola's rafters
    are plain timber - neither carries a detail picture."""
    glasshouse = REGISTRY.build(polygon_record("GREENHOUSE", rectangle(300.0, 200.0), 220.0))
    pergola = REGISTRY.build(polygon_record("PERGOLA", rectangle(300.0, 200.0), 240.0))
    glass = [part for part in glasshouse if part.material_kind == "glass"]
    assert glass and all(not part.surface and not part.surface_runs for part in glass)
    pieces = [(part.material_kind, piece.surface) for part in glasshouse + pergola
              for piece in surface_pieces(part)]
    assert {surface for _kind, surface in pieces} == {"", "steel", "concrete", "wood"}
    assert all(detail_of(surface or DEFAULT_SURFACE, kind) is None for kind, surface in pieces)


def test_a_part_already_grouped_by_surface_keeps_its_mesh() -> None:
    """``with_surfaces`` orders triangles only where a part is not grouped yet: a roof
    built tiles-first keeps the very mesh object its builder made."""
    roof = next(p for p in REGISTRY.build(polygon_record(
        "HOUSE", rectangle(600.0, 400.0), 450.0, params={"ridge": ((-300.0, 0.0), (300.0, 0.0))}))
        if p.name == "roof")
    again = with_surfaces([roof])[0]
    assert again is roof


# ── the drift guard: the scene file holds no table, and reads every number ───


def _component(name: str) -> str:
    code = QML.read_text(encoding="utf-8")
    start = code.index(f"id: {name}")
    end = code.index("    Component {", start)
    return code[start:end]


@pytest.mark.parametrize("component", ["vcPart", "roofPart"])
def test_the_scene_file_reads_every_surface_number_the_host_writes(component: str) -> None:
    """The drift guard's second half. The host writes ``surface_look``'s properties on
    the Model; a property the component does not declare fails at run time - so every
    property any surface can write must be declared, every material of the component
    must take roughness and specular from them (no literal left to drift from the Python
    table), and the defaults must be ``DEFAULT_SURFACE``'s."""
    block = _component(component)
    kind = "vc" if component == "vcPart" else "roof"
    written: set[str] = set()
    for name in SURFACES:
        look = engine_materials.surface_look(kind, name)
        assert look is not None
        written |= set(look.properties)
    for prop in written | {"detailMap"}:
        assert re.search(rf"property (real|var) {prop}\b", block), (component, prop)
    default = SURFACES[DEFAULT_SURFACE]
    assert f"property real surfaceRough: {default.roughness}" in block
    assert f"property real surfaceSpecular: {default.specular}" in block
    assert not re.search(r"roughness: \d", block) and not re.search(r"uRough: \d", block)
    assert not re.search(r"specularAmount: \d", block) and not re.search(r"uSpecular: \d", block)
    assert block.count("roughness: surfaceRough") == 1
    # every custom material reads them: the screen door, the detail material (#801), the
    # snowy look (#687) and, on vcPart, a plant's swaying wood (#800)
    assert block.count("uRough: surfaceRough") == block.count("uRough:") >= 3
    assert block.count("uSpecular: surfaceSpecular") == block.count("uSpecular:") >= 3


def test_a_part_of_no_surface_kind_gets_no_surface_look() -> None:
    for kind in ("glass", "water", "foliage", "grass"):
        assert engine_materials.surface_look(kind, "") is None
    look = engine_materials.surface_look("vc", "")
    assert look is not None and look.detail_pattern is None
    assert look.properties["surfaceRough"] == 0.78
