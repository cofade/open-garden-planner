"""The built world's colours — a Qt-free mirror of the 2D tables (Phase 17 L1.6).

Style contract (``ogp-lush-cinematic`` §2 "Colour"): 3D takes colours only from
the 2D tables. Those tables are not importable at run time — the object-sprite
``MATERIALS`` live in ``scripts/generate_object_sprites.py`` and the texture
palettes are literals inside ``scripts/generate_asset_forge_textures.py``, and
neither script ships in the package — so the entries the builders need are
mirrored here, each naming its source. ``tests/unit/test_scene3d_builders_palette.py``
loads both generators and fails when a mirrored value and its source disagree,
and maps every vertex colour every builder emits back to an entry of this module
(gate G5). A colour that is in no 2D table does not belong here: report it.

Not here, on purpose: anything the ITEM colours. A fence, a wall, a shed's
walls and a container are seen in the item's own stroke or fill colour in 2D, so
their parts are ``tinted`` — pure white vertices the sink multiplies with the
record's material (``TINT``) — and a recolour never rebuilds a mesh. A HOUSE's
walls are not: its fill is drawn as its roof, so its walls are ``SANDSTONE``
(``buildings.HOUSE_WALL``, L4's owner pass).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

import numpy as np
from numpy.typing import NDArray

from ...object_art.materials import EMBER, MATERIALS
from ..color import Rgba, srgb8_to_linear

#: Vertex colour of a ``tinted`` part: the sink multiplies it with the item's tint.
TINT: Final[tuple[float, float, float, float]] = (1.0, 1.0, 1.0, 1.0)

#: Where a mirrored colour comes from.
SOURCE_OBJECT_SPRITES: Final = "scripts/generate_object_sprites.py"
SOURCE_TEXTURE_FORGE: Final = "scripts/generate_asset_forge_textures.py"


@dataclass(frozen=True, slots=True)
class PaletteColor:
    """One mirrored 2D colour.

    ``srgb``: the 8-bit sRGB value. ``source``: the generator script.
    ``table`` / ``key``: for the object sprites ``MATERIALS[table][key]``; for
    the texture forge the generator FUNCTION (``table``) and what the literal is
    there (``key`` — documentation; the drift guard checks the literal occurs in
    that function). ``surface``: what a part of this colour is MADE of — a key of
    ``core.scene3d.materials.SURFACES`` (#803): it decides how the part reflects, and
    ``common.with_surfaces`` splits a builder's part by it.
    """

    name: str
    srgb: tuple[int, int, int]
    source: str
    table: str
    key: str
    surface: str

    @property
    def rgba8(self) -> Rgba:
        return (self.srgb[0], self.srgb[1], self.srgb[2], 255)

    @property
    def linear(self) -> tuple[float, float, float, float]:
        """Linear RGBA — what a vertex colour holds."""
        return srgb8_to_linear(self.rgba8)


def _sprite(name: str, _hex_color: str, material: str, tone: str, surface: str) -> PaletteColor:
    value = MATERIALS[material][tone].lstrip("#")
    srgb = (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    return PaletteColor(name, srgb, SOURCE_OBJECT_SPRITES, material, tone, surface)


def _texture(name: str, srgb: tuple[int, int, int], generator: str, what: str,
             surface: str) -> PaletteColor:
    return PaletteColor(name, srgb, SOURCE_TEXTURE_FORGE, generator, what, surface)


# ── roofs ────────────────────────────────────────────────────────────────────
#: Clay roof tiles — the 2D HOUSE fill pattern (``FillPattern.ROOF_TILES``).
ROOF_TILE: Final = _texture("ROOF_TILE", (178, 90, 62), "generate_roof_tiles", "reds[1]", "roof_tile")
ROOF_TILE_CAP: Final = _texture("ROOF_TILE_CAP", (170, 86, 58), "generate_roof_tiles", "reds[3]", "roof_tile")
#: Shingles — the roof of the 2D tool-shed sprite (``build_tool_shed``).
SHINGLE: Final = _sprite("SHINGLE", "#78695a", "shingle", "mid", "shingle")
SHINGLE_CAP: Final = _sprite("SHINGLE_CAP", "#4b4037", "shingle", "dark", "shingle")
#: Roof timber: the underside of the slab and its fascia.
TIMBER: Final = _sprite("TIMBER", "#66432c", "walnut", "mid", "wood")

# ── beds ─────────────────────────────────────────────────────────────────────
#: The raised-bed sprite's frame (``build_raised_bed``: oak) and its plank gaps.
PLANK: Final = _sprite("PLANK", "#b98350", "oak", "mid", "wood")
PLANK_GROOVE: Final = _sprite("PLANK_GROOVE", "#7d5029", "oak", "dark", "wood")
#: Soil in beds and containers (the sprites' ``granular_fill`` base).
SOIL: Final = _sprite("SOIL", "#573c26", "soil", "mid", "soil")

# ── hedges ───────────────────────────────────────────────────────────────────
#: The hedge texture (``FillPattern.HEDGE``): its ground and its four leaf greens.
HEDGE_CORE: Final = _texture("HEDGE_CORE", (16, 52, 30), "generate_hedge", "Tile base", "leaf")
HEDGE_LEAVES: Final[tuple[PaletteColor, ...]] = (
    _texture("HEDGE_LEAF_0", (29, 84, 48), "generate_hedge", "bodies[2]", "leaf"),
    _texture("HEDGE_LEAF_1", (35, 96, 55), "generate_hedge", "bodies[0]", "leaf"),
    _texture("HEDGE_LEAF_2", (44, 112, 64), "generate_hedge", "bodies[1]", "leaf"),
    _texture("HEDGE_LEAF_3", (51, 122, 71), "generate_hedge", "bodies[3]", "leaf"),
)

# ── objects (Phase 17 L4, #388): the sprites' own materials ─────────────────
# Each object is coloured like its 2D sprite (``scripts/generate_object_sprites.py``
# ``build_<object>``): the light / mid / dark tones of the sprite's materials, the
# light tone on faces that look up, the dark one on undersides and grooves. A tone
# below the albedo floor (luma 40: ``rubber.dark``, ``enamel_black.dark``) is not
# used. Reused from above: PLANK (oak mid), PLANK_GROOVE (oak dark), TIMBER (walnut
# mid), SHINGLE (shingle mid), SOIL (soil mid).
OAK_LIGHT: Final = _sprite("OAK_LIGHT", "#dcae70", "oak", "light", "wood")
TEAK: Final = _sprite("TEAK", "#a06a3a", "teak", "mid", "wood")
TEAK_LIGHT: Final = _sprite("TEAK_LIGHT", "#c98f56", "teak", "light", "wood")
TEAK_DARK: Final = _sprite("TEAK_DARK", "#69401c", "teak", "dark", "wood")
PINE: Final = _sprite("PINE", "#d4b471", "pine", "mid", "wood")
PINE_LIGHT: Final = _sprite("PINE_LIGHT", "#efd8a0", "pine", "light", "wood")
PINE_DARK: Final = _sprite("PINE_DARK", "#9e7c40", "pine", "dark", "wood")
WALNUT_DARK: Final = _sprite("WALNUT_DARK", "#3f2617", "walnut", "dark", "wood")
WALNUT_LIGHT: Final = _sprite("WALNUT_LIGHT", "#8f5f3c", "walnut", "light", "wood")
GREY_WOOD: Final = _sprite("GREY_WOOD", "#918a7a", "grey_wood", "mid", "wood")
GREY_WOOD_LIGHT: Final = _sprite("GREY_WOOD_LIGHT", "#bdb7aa", "grey_wood", "light", "wood")
GREY_WOOD_DARK: Final = _sprite("GREY_WOOD_DARK", "#5f584b", "grey_wood", "dark", "wood")
STEEL: Final = _sprite("STEEL", "#adb4bc", "steel", "mid", "steel")
STEEL_LIGHT: Final = _sprite("STEEL_LIGHT", "#eaedf0", "steel", "light", "steel")
STEEL_DARK: Final = _sprite("STEEL_DARK", "#626b73", "steel", "dark", "steel")
IRON: Final = _sprite("IRON", "#4c525a", "iron", "mid", "iron")
IRON_LIGHT: Final = _sprite("IRON_LIGHT", "#7e838a", "iron", "light", "iron")
BRASS: Final = _sprite("BRASS", "#cca84e", "brass", "mid", "steel")
ENAMEL_BLACK: Final = _sprite("ENAMEL_BLACK", "#313538", "enamel_black", "mid", "enamel")
ENAMEL_BLACK_LIGHT: Final = _sprite("ENAMEL_BLACK_LIGHT", "#70757a", "enamel_black", "light", "enamel")
ENAMEL_GREEN: Final = _sprite("ENAMEL_GREEN", "#3f7c3e", "enamel_green", "mid", "enamel")
ENAMEL_GREEN_LIGHT: Final = _sprite("ENAMEL_GREEN_LIGHT", "#83b67e", "enamel_green", "light", "enamel")
ENAMEL_RED: Final = _sprite("ENAMEL_RED", "#cb3b2d", "enamel_red", "mid", "enamel")
PLASTIC_GREEN: Final = _sprite("PLASTIC_GREEN", "#3e7c3c", "plastic_green", "mid", "plastic")
PLASTIC_GREEN_LIGHT: Final = _sprite("PLASTIC_GREEN_LIGHT", "#73ab6e", "plastic_green", "light", "plastic")
PLASTIC_BLUE: Final = _sprite("PLASTIC_BLUE", "#427bc2", "plastic_blue", "mid", "plastic")
PLASTIC_BLUE_LIGHT: Final = _sprite("PLASTIC_BLUE_LIGHT", "#84b6ea", "plastic_blue", "light", "plastic")
PLASTIC_YELLOW: Final = _sprite("PLASTIC_YELLOW", "#e9c33f", "plastic_yellow", "mid", "plastic")
RUBBER: Final = _sprite("RUBBER", "#303336", "rubber", "mid", "rubber")
RUBBER_LIGHT: Final = _sprite("RUBBER_LIGHT", "#5c5f63", "rubber", "light", "rubber")
CANVAS_CREAM: Final = _sprite("CANVAS_CREAM", "#eee1c6", "canvas_cream", "mid", "canvas")
CANVAS_CREAM_DARK: Final = _sprite("CANVAS_CREAM_DARK", "#cbba95", "canvas_cream", "dark", "canvas")
CANVAS_BLUE: Final = _sprite("CANVAS_BLUE", "#5e89bf", "canvas_blue", "mid", "canvas")
CANVAS_RED: Final = _sprite("CANVAS_RED", "#d65d4b", "canvas_red", "mid", "canvas")
CANVAS_TEAL: Final = _sprite("CANVAS_TEAL", "#4f9d97", "canvas_teal", "mid", "canvas")
TERRACOTTA: Final = _sprite("TERRACOTTA", "#ca7341", "terracotta", "mid", "terracotta")
TERRACOTTA_DARK: Final = _sprite("TERRACOTTA_DARK", "#8c4523", "terracotta", "dark", "terracotta")
STONE: Final = _sprite("STONE", "#a29d93", "stone", "mid", "stone")
STONE_LIGHT: Final = _sprite("STONE_LIGHT", "#d2cdc3", "stone", "light", "stone")
STONE_DARK: Final = _sprite("STONE_DARK", "#68645c", "stone", "dark", "stone")
SANDSTONE: Final = _sprite("SANDSTONE", "#c4ae86", "sandstone", "mid", "stone")
SANDSTONE_LIGHT: Final = _sprite("SANDSTONE_LIGHT", "#e5d5b6", "sandstone", "light", "stone")
SANDSTONE_DARK: Final = _sprite("SANDSTONE_DARK", "#8c7756", "sandstone", "dark", "stone")
CONCRETE: Final = _sprite("CONCRETE", "#abaca8", "concrete", "mid", "concrete")
CONCRETE_LIGHT: Final = _sprite("CONCRETE_LIGHT", "#d5d5d2", "concrete", "light", "concrete")
ASH: Final = _sprite("ASH", "#8f8b83", "ash", "mid", "soil")
ASH_DARK: Final = _sprite("ASH_DARK", "#57544e", "ash", "dark", "soil")
GLASS: Final = _sprite("GLASS", "#c0dcf0", "glass", "mid", "glass_pane")
GLASS_DARK: Final = _sprite("GLASS_DARK", "#82accb", "glass", "dark", "glass_pane")
GLASS_OCC: Final = _sprite("GLASS_OCC", "#476f8f", "glass", "occ", "glass_pane")
WATER: Final = _sprite("WATER", "#43a3d2", "water", "mid", "water")
SOIL_LIGHT: Final = _sprite("SOIL_LIGHT", "#7d5c3e", "soil", "light", "soil")
COMPOST: Final = _sprite("COMPOST", "#4c3521", "compost", "mid", "soil")
COMPOST_LIGHT: Final = _sprite("COMPOST_LIGHT", "#725232", "compost", "light", "soil")
SAND: Final = _sprite("SAND", "#e4d0a0", "sand", "mid", "soil")
SAND_DARK: Final = _sprite("SAND_DARK", "#bfa872", "sand", "dark", "soil")
GRASS_BIT: Final = _sprite("GRASS_BIT", "#5f9a3c", "grass_bit", "mid", "leaf")


def _ember(name: str, index: int, surface: str) -> PaletteColor:
    value = EMBER[index].lstrip("#")
    srgb = (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    return PaletteColor(name, srgb, SOURCE_OBJECT_SPRITES, "EMBER", str(index), surface)


#: The fire pit's glowing coals: the sprites' ``EMBER`` triad, mid and dark.
EMBER_MID: Final = _ember("EMBER_MID", 1, "ember")
EMBER_DARK: Final = _ember("EMBER_DARK", 2, "ember")

#: Every object colour above, in declaration order.
OBJECT_COLORS: Final[tuple[PaletteColor, ...]] = (
    OAK_LIGHT, TEAK, TEAK_LIGHT, TEAK_DARK, PINE, PINE_LIGHT, PINE_DARK, WALNUT_DARK,
    WALNUT_LIGHT, GREY_WOOD, GREY_WOOD_LIGHT, GREY_WOOD_DARK, STEEL, STEEL_LIGHT, STEEL_DARK,
    IRON, IRON_LIGHT, BRASS, ENAMEL_BLACK, ENAMEL_BLACK_LIGHT, ENAMEL_GREEN, ENAMEL_GREEN_LIGHT,
    ENAMEL_RED, PLASTIC_GREEN, PLASTIC_GREEN_LIGHT, PLASTIC_BLUE, PLASTIC_BLUE_LIGHT,
    PLASTIC_YELLOW, RUBBER, RUBBER_LIGHT, CANVAS_CREAM, CANVAS_CREAM_DARK,
    CANVAS_BLUE, CANVAS_RED, CANVAS_TEAL, TERRACOTTA, TERRACOTTA_DARK, STONE, STONE_LIGHT,
    STONE_DARK, SANDSTONE, SANDSTONE_LIGHT, SANDSTONE_DARK, CONCRETE, CONCRETE_LIGHT, ASH,
    ASH_DARK, GLASS, GLASS_DARK, GLASS_OCC, WATER, SOIL_LIGHT, COMPOST, COMPOST_LIGHT, SAND,
    SAND_DARK, GRASS_BIT, EMBER_MID, EMBER_DARK,
)

#: Every mirrored colour — what the drift guard and gate G5 iterate.
ALL: Final[tuple[PaletteColor, ...]] = (
    ROOF_TILE, ROOF_TILE_CAP, SHINGLE, SHINGLE_CAP, TIMBER, PLANK, PLANK_GROOVE, SOIL,
    HEDGE_CORE, *HEDGE_LEAVES, *OBJECT_COLORS,
)


def _colour_key(rgb: tuple[float, float, float]) -> bytes:
    """A vertex colour's identity: its float32 RGB bytes (what ``Mesh`` stores)."""
    return np.asarray(rgb, dtype=np.float32).tobytes()


#: Each entry's linear vertex colour (float32 RGB bytes) -> its surface. Two entries of one
#: colour would have to agree; the palette's colours are unique (its own test).
SURFACE_BY_COLOUR: Final[Mapping[bytes, str]] = MappingProxyType(
    {_colour_key(entry.linear[:3]): entry.surface for entry in ALL})


def surfaces_of_colours(colors: NDArray[np.float32]) -> list[str | None]:
    """The surface of each vertex colour (n, 4) — None for a colour in no entry (a tinted
    part's white or shading weight: its builder names the part's surface)."""
    rgb = np.ascontiguousarray(colors[:, :3], dtype=np.float32)
    return [SURFACE_BY_COLOUR.get(row.tobytes()) for row in rgb]
