"""The baked ground on its way into the engine, without an engine (Phase 17 L1.5, #385).

Two things can be read without a GPU: the adapter maps a ground tile into the
engine frame — once, in one place — and ``Garden.qml``'s tile component says
what the measurements demand (north-up rows need ``flipV``; a repeating texture
bleeds its opposite edge into a tile border). What the engine then DRAWS is the
render tier's (``tests/integration/test_scene3d_ground_render.py``), and the
host's bookkeeping of tile Models and textures is ``tests/ui/
test_quick3d_ground_tiles.py``.
"""

from __future__ import annotations

import re

import pytest

from open_garden_planner.core.scene3d import GroundSpec, GroundTile, SinkProtocolError
from open_garden_planner.ui.view3d.quick3d.adapter import (
    GroundPlacement,
    Quick3DSink,
    TilePlacement,
)
from tests.unit.test_quick3d_adapter import FakeScene
from tests.unit.test_quick3d_qml import SCENE, strip_comments


def _tile(column: int, row: int, *, east: float, north: float, width_cm: float = 512.0,
          depth_cm: float = 512.0, px: tuple[int, int] = (4, 4), shade: int = 90) -> GroundTile:
    return GroundTile(column, row, east, north, width_cm, depth_cm, px[0], px[1],
                      bytes((shade, 120, 60, 255)) * (px[0] * px[1]))


class TestTilesInTheEngineFrame:
    def test_a_tile_lies_where_its_rectangle_lies_with_north_towards_minus_z(self) -> None:
        """Scene (east, north, up) is engine (x, y, −z): a tile's centre is mapped like
        every other point of the scene, and its extents are lengths — unsigned."""
        scene = FakeScene()
        sink = Quick3DSink(scene)
        south_west = _tile(0, 0, east=0.0, north=0.0)
        north_east = _tile(1, 1, east=512.0, north=512.0, width_cm=188.0, depth_cm=88.0, px=(3, 2))
        spec = GroundSpec(700.0, 600.0, tiles=(south_west, north_east))
        sink.begin()
        sink.set_ground(spec)
        sink.commit()
        assert scene.ground == GroundPlacement(
            center=(350.0, 0.0, -300.0), width_cm=700.0, depth_cm=600.0, tiles=(
                TilePlacement(key=(0, 0), center=(256.0, 0.0, -256.0), width_cm=512.0,
                              depth_cm=512.0, width_px=4, height_px=4, pixels=south_west.pixels),
                TilePlacement(key=(1, 1), center=(606.0, 0.0, -556.0), width_cm=188.0,
                              depth_cm=88.0, width_px=3, height_px=2, pixels=north_east.pixels)))
        assert sink.ground is spec  # what the sink says it shows is what it was given

    def test_the_pixels_are_handed_on_not_copied(self) -> None:
        """An engine scene tells an unchanged tile by the ``bytes`` object itself: a
        copy on the way would upload every tile on every edit (and hold the ground
        twice — up to 64 MB)."""
        scene = FakeScene()
        sink = Quick3DSink(scene)
        tile = _tile(0, 0, east=0.0, north=0.0)
        sink.begin()
        sink.set_ground(GroundSpec(512.0, 512.0, tiles=(tile,)))
        sink.commit()
        assert scene.ground.tiles[0].pixels is tile.pixels
        assert "pixels" not in repr(scene.ground.tiles[0])  # 1 MB of bytes is no log line

    def test_a_ground_without_tiles_is_the_bare_plan_rectangle(self) -> None:
        scene = FakeScene()
        sink = Quick3DSink(scene)
        sink.begin()
        sink.set_ground(GroundSpec(2400.0, 1600.0))
        sink.commit()
        assert scene.ground == GroundPlacement((1200.0, 0.0, -800.0), 2400.0, 1600.0)
        assert scene.ground.tiles == ()

    def test_the_tiles_go_with_the_ground_and_only_inside_a_transaction(self) -> None:
        scene = FakeScene()
        sink = Quick3DSink(scene)
        with pytest.raises(SinkProtocolError):
            sink.set_ground(GroundSpec(512.0, 512.0, tiles=(_tile(0, 0, east=0.0, north=0.0),)))
        assert scene.ground == "unset"
        sink.begin()
        sink.set_ground(GroundSpec(512.0, 512.0, tiles=(_tile(0, 0, east=0.0, north=0.0),)))
        sink.commit()
        sink.clear()
        assert scene.ground is None and sink.ground is None  # clear() releases the tiles


def test_the_frozen_exe_ships_the_baker_and_the_tile_module() -> None:
    """Nothing imports the baker until the workspace wires it (L1.3), and the engine
    modules are loaded lazily: both are named to PyInstaller."""
    spec = (SCENE.parents[6] / "installer" / "ogp.spec").read_text(encoding="utf-8")
    assert '"open_garden_planner.ui.view3d.ground_bake",' in spec
    assert '"open_garden_planner.ui.view3d.quick3d.ground_tiles",' in spec


# ── Garden.qml, read as text ──────────────────────────────────────────────────

CODE = strip_comments(SCENE.read_text(encoding="utf-8"))


def _block(code: str, opening: str) -> str:
    """The body of the ``{ ... }`` block whose opening the pattern ``opening`` finds (the
    pattern ends with the block's brace)."""
    found = re.search(opening, code)
    assert found is not None, f"Garden.qml has no {opening!r}"
    start = found.end()
    depth, index = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(code[index], 0)
        index += 1
    return code[start:index - 1]


TILE = _block(CODE, r"Component\s*\{(?=\s*id:\s*groundTile)")


class TestTheTileComponent:
    def test_it_is_a_flat_quad_with_its_own_texture(self) -> None:
        assert re.search(r'source:\s*"#Rectangle"', TILE)
        assert re.search(r"eulerRotation\.x:\s*-90\b", TILE)  # the plan's plane, like the bare ground
        assert re.search(r"textureData:\s*tileData\b", TILE)
        for name in ("tileColumn", "tileRow", "tileData", "retired"):
            assert re.search(rf"property\s+\w+\s+{name}\b", TILE), name

    def test_its_rows_are_flipped_north_up(self) -> None:
        """A tile's pixel row 0 is its NORTH edge; the engine samples v from the
        bottom. Without ``flipV`` the plan is mirrored north-south (measured in the
        L0 spike; the render tier holds the frame against the bake)."""
        assert re.search(r"flipV:\s*true\b", TILE)

    def test_it_clamps_at_its_edges_on_both_axes(self) -> None:
        """The default is Repeat: linear filtering at a tile's edge then blends in the
        texels of the OPPOSITE edge — a line along every tile border."""
        assert re.search(r"tilingModeHorizontal:\s*Texture\.ClampToEdge\b", TILE)
        assert re.search(r"tilingModeVertical:\s*Texture\.ClampToEdge\b", TILE)
        assert "Repeat" not in TILE

    def test_a_click_on_the_ground_hits_no_item(self) -> None:
        """Like the bare plan rectangle: the ground is not pickable — a pick that hits
        nothing above it answers "no item"."""
        assert "pickable" not in TILE and "itemId" not in TILE

    def test_it_takes_shadows_and_casts_none(self) -> None:
        assert re.search(r"receivesShadows:\s*true\b", TILE)
        assert re.search(r"castsShadows:\s*false\b", TILE)

    def test_its_material_is_the_meadows_so_the_plan_edge_shows_no_step(self) -> None:
        """The L1.4 look review: PrincipledMaterial scales the sky's diffuse light by
        (1 - specularAmount), so a tile of other values than the endless meadow's puts
        a luma step where a baked lawn meets the meadow at the plan's edge (0.92 / 0.2
        measured 2-8 luma darker). The tile takes the meadow's roughness and
        specular amount, whatever they are."""
        # the endless meadow: the Model 4 x 4 km wide (comments are stripped from CODE)
        (meadow,) = [block for found in re.finditer(r"Model\s*\{", CODE)
                     if "4000, 4000" in (block := _block(CODE[found.start():], r"Model\s*\{"))]
        values = {}
        for name, block in (("tile", TILE), ("meadow", meadow)):
            roughness = re.search(r"roughness:\s*([0-9.]+)", block)
            specular = re.search(r"specularAmount:\s*([0-9.]+)", block)
            assert roughness and specular, name
            values[name] = (float(roughness.group(1)), float(specular.group(1)))
        assert values["tile"] == values["meadow"] == (1.0, 0.15)

    def test_the_tiles_are_drawn_instead_of_the_bare_rectangle_never_with_it(self) -> None:
        """Two coplanar surfaces fight for the depth buffer: while tiles lie on the
        plan the bare rectangle is not drawn."""
        assert re.search(r"property\s+bool\s+groundTiled:\s*false\b", CODE)
        assert re.search(r"visible:\s*root\.groundVisible\s*&&\s*!root\.groundTiled\b", CODE)
        assert len(re.findall(r"root\.groundTiled", CODE)) == 1  # the one reader

    def test_the_scene_has_the_four_calls_the_python_side_makes(self) -> None:
        source = (SCENE.parents[1] / "ground_tiles.py").read_text(encoding="utf-8")
        for name in ("createGroundTile", "placeGroundTile", "destroyGroundTile", "listGroundTiles"):
            assert re.search(rf"function\s+{name}\s*\(", CODE), name
            assert f'"{name}"' in source, name
        assert re.search(r"Node\s*\{\s*id:\s*groundTiles\s*\}", CODE)

    def test_a_destroyed_tile_lets_go_of_its_texture_first(self) -> None:
        """``destroy()`` is deferred: until Qt deletes the Model it would still name a
        texture Python has released."""
        body = _block(CODE, r"function\s+destroyGroundTile\s*\([^)]*\)\s*\{")
        assert body.index("tileData = null") < body.index(".destroy()")
        assert "retired = true" in body and "visible = false" in body

