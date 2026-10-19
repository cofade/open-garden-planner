"""The built world's palette is the 2D tables' (Phase 17 L1.6, #385 — gate G5).

``core/scene3d/builders/palette.py`` MIRRORS colours whose home is a generator
script that does not ship in the package. This file is the drift guard that
makes the mirror safe: it loads both generators and fails when a mirrored value
and its source disagree —

- object sprites: ``scripts/generate_object_sprites.py`` ``MATERIALS[table][key]``
  (the module is executed, as the L0 spike's own tests did for it);
- texture forge: ``scripts/generate_asset_forge_textures.py`` — its palettes are
  literals inside the ``generate_*`` functions, so the function's source is
  parsed and the named literal read from the syntax tree (the script needs
  Pillow to run; the tree does not).

``test_scene3d_builders.py::test_every_vertex_colour_is_a_2d_table_entry`` closes
the chain: every vertex colour a builder emits is an entry of the palette.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

from open_garden_planner.core.scene3d.builders import palette
from open_garden_planner.core.scene3d.color import srgb8_to_linear, srgb_to_linear

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@cache
def _object_sprites() -> ModuleType:
    script = SCRIPTS / "generate_object_sprites.py"
    spec = importlib.util.spec_from_file_location("generate_object_sprites_for_palette", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def _texture_function(name: str) -> ast.FunctionDef:
    tree = ast.parse((SCRIPTS / "generate_asset_forge_textures.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"no generator {name} in the texture forge")


def _rgb(node: ast.expr) -> tuple[int, int, int] | None:
    if isinstance(node, ast.Tuple) and len(node.elts) == 3 and all(
            isinstance(e, ast.Constant) and isinstance(e.value, int) for e in node.elts):
        return tuple(e.value for e in node.elts)  # type: ignore[union-attr,return-value]
    return None


def _texture_literal(function: ast.FunctionDef, what: str) -> tuple[int, int, int]:
    """The colour literal ``what`` names inside a texture generator: ``name[i]`` is
    element i of the list assigned to ``name``; ``Tile base`` the argument of
    ``Tile(...)``."""
    indexed = re.fullmatch(r"(\w+)\[(\d+)\]", what)
    for node in ast.walk(function):
        if indexed and isinstance(node, ast.Assign) and isinstance(node.value, ast.List) and any(
                isinstance(t, ast.Name) and t.id == indexed.group(1) for t in node.targets):
            colour = _rgb(node.value.elts[int(indexed.group(2))])
            assert colour is not None
            return colour
        if what == "Tile base" and isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Tile":
            argument = node.args[0]
            if isinstance(argument, ast.Name):  # ``Tile(bg)``: follow the name once
                name = argument.id
                assigned = [other.value for other in ast.walk(function)
                            if isinstance(other, ast.Assign) and any(
                                isinstance(t, ast.Name) and t.id == name for t in other.targets)]
                assert assigned, f"{function.name}: {name} is never assigned"
                argument = assigned[0]
            colour = _rgb(argument)
            assert colour is not None
            return colour
    raise AssertionError(f"{function.name}: no literal for {what!r}")


@pytest.mark.parametrize("entry", palette.ALL, ids=lambda e: e.name)
def test_every_mirrored_colour_equals_its_2d_source(entry: palette.PaletteColor) -> None:
    if entry.source == palette.SOURCE_OBJECT_SPRITES:
        source = _object_sprites().MATERIALS[entry.table][entry.key]
        assert "#{:02x}{:02x}{:02x}".format(*entry.srgb) == source
    else:
        assert entry.source == palette.SOURCE_TEXTURE_FORGE
        assert _texture_literal(_texture_function(entry.table), entry.key) == entry.srgb


def test_the_guard_reads_what_it_says_it_reads() -> None:
    """The syntax-tree reader is not vacuous: it finds known literals and refuses
    unknown ones."""
    roof = _texture_function("generate_roof_tiles")
    assert _texture_literal(roof, "reds[0]") == (192, 100, 68)
    assert _texture_literal(roof, "Tile base") == (128, 62, 44)  # ``Tile(bg)`` through ``bg``
    assert _texture_literal(_texture_function("generate_hedge"), "bodies[3]") == (51, 122, 71)
    with pytest.raises(AssertionError):
        _texture_literal(roof, "blues[0]")
    with pytest.raises(AssertionError):
        _texture_function("generate_unobtainium")
    assert _object_sprites().MATERIALS["oak"]["mid"] == "#b98350"


def test_the_palette_is_complete_and_unique() -> None:
    names = [entry.name for entry in palette.ALL]
    assert len(names) == len(set(names)) == 13
    declared = {value.name for value in vars(palette).values()
                if isinstance(value, palette.PaletteColor)}
    declared |= {entry.name for entry in palette.HEDGE_LEAVES}
    assert declared == set(names)  # nothing declared outside ALL, nothing in ALL undeclared
    assert len({entry.srgb for entry in palette.ALL}) == len(palette.ALL)


@pytest.mark.parametrize("entry", palette.ALL, ids=lambda e: e.name)
def test_linear_values_and_the_albedo_range(entry: palette.PaletteColor) -> None:
    assert entry.linear == srgb8_to_linear(entry.rgba8) and entry.linear[3] == 1.0
    hex_color = "#{:02x}{:02x}{:02x}".format(*entry.srgb)
    assert entry.linear[:3] == pytest.approx(tuple(float(c) for c in srgb_to_linear(hex_color)), abs=1e-7)
    red, green, blue = entry.srgb
    luma = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    assert 40.0 <= luma <= 240.0  # style contract §2: no pure black or white surfaces


def test_the_tint_is_neutral_white() -> None:
    assert palette.TINT == (1.0, 1.0, 1.0, 1.0)


def test_hedge_greens_run_dark_to_light() -> None:
    lumas = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in (e.srgb for e in palette.HEDGE_LEAVES)]
    assert lumas == sorted(lumas)
    core = palette.HEDGE_CORE.srgb
    assert 0.2126 * core[0] + 0.7152 * core[1] + 0.0722 * core[2] < lumas[0]  # the core is darker


# ── name sets the builders mirror or share (review round 1, P2-5) ────────────


def test_the_fence_styles_are_the_2d_table_s_fence_category() -> None:
    """``fences.FENCE_STYLES`` mirrors the "fence" category of ``PATH_FENCE_STYLES``
    (``core/object_types.py`` imports Qt, so the builders cannot import it). A fence
    style added to the 2D table fails HERE until someone decides what it is built as;
    until then ``lines.py`` builds it as a plain panel, never as some other fence."""
    from open_garden_planner.core.object_types import PATH_FENCE_STYLES, PathFenceStyle
    from open_garden_planner.core.scene3d.builders import fences, lines

    in_2d = {style.name for style, info in PATH_FENCE_STYLES.items() if info.category == "fence"}
    assert in_2d == fences.FENCE_STYLES
    assert set(PATH_FENCE_STYLES) == set(PathFenceStyle)  # no style without a category entry
    assert fences.DEFAULT_FENCE_STYLE in fences.FENCE_STYLES
    assert set(lines.DEFAULT_SOLID.values()) <= fences.FENCE_STYLES
    assert fences.PLAIN not in {style.name for style in PathFenceStyle}  # never a real style name


def test_every_fence_style_has_a_solid_of_its_own() -> None:
    """Each mirrored style is really built: by the wall, the hedge or a post fence."""
    from open_garden_planner.core.scene3d.builders import fences

    built_here = set(fences._POST_FENCES) | {"HEDGE_FENCE"}
    assert built_here | {"STONE_WALL"} == fences.FENCE_STYLES
    assert built_here & {"STONE_WALL", fences.PLAIN} == set()


def test_the_container_materials_are_the_container_model_s() -> None:
    """``beds.py`` imports the material names; every material has a wall thickness."""
    from open_garden_planner.core import container_model
    from open_garden_planner.core.scene3d.builders import beds

    assert set(beds.WALL_THICKNESS_CM) == set(container_model.MATERIALS)
    code = ast.parse(Path(beds.__file__).read_text(encoding="utf-8"))
    literals = {node.value for node in ast.walk(code)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert literals.isdisjoint(container_model.MATERIALS)  # imported, not retyped


def test_the_nominal_height_is_the_resolver_s_answer() -> None:
    """``common.nominal_height_cm`` asks the 2D height resolver; it holds no table of
    kinds (round 0 kept a third copy of the container set)."""
    from open_garden_planner.core import object_height
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.core.scene3d.builders import BUILT_WORLD_KINDS, common

    for member in ObjectType:
        assert common.nominal_height_cm(member.name) == object_height.effective_height_cm(member, {})
    assert {kind: common.nominal_height_cm(kind) for kind in sorted(BUILT_WORLD_KINDS)} == {
        "CONTAINER": 30.0, "CONTAINER_ROUND": 30.0, "FENCE": 120.0, "GARAGE_SHED": 250.0,
        "GARDEN_BED": None, "HEDGE_POLYGON": 150.0, "HEDGE_SECTION": 150.0, "HOUSE": 450.0,
        "RAISED_BED": 40.0, "TOOL_SHED": 250.0, "WALL": 200.0, "WALL_PLANTER": 30.0,
    }
    code = ast.parse(Path(common.__file__).read_text(encoding="utf-8"))
    literals = {node.value for node in ast.walk(code)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert literals.isdisjoint({member.name for member in ObjectType})  # no kind is named there
