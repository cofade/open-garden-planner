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

Not here, on purpose: anything the ITEM colours. A fence, a wall, a house's
walls and a container are seen in the item's own stroke or fill colour in 2D, so
their parts are ``tinted`` — pure white vertices the sink multiplies with the
record's material (``TINT``) — and a recolour never rebuilds a mesh.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ...object_art.materials import MATERIALS
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
    that function).
    """

    name: str
    srgb: tuple[int, int, int]
    source: str
    table: str
    key: str

    @property
    def rgba8(self) -> Rgba:
        return (self.srgb[0], self.srgb[1], self.srgb[2], 255)

    @property
    def linear(self) -> tuple[float, float, float, float]:
        """Linear RGBA — what a vertex colour holds."""
        return srgb8_to_linear(self.rgba8)


def _sprite(name: str, _hex_color: str, material: str, tone: str) -> PaletteColor:
    value = MATERIALS[material][tone].lstrip("#")
    srgb = (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    return PaletteColor(name, srgb, SOURCE_OBJECT_SPRITES, material, tone)


def _texture(name: str, srgb: tuple[int, int, int], generator: str, what: str) -> PaletteColor:
    return PaletteColor(name, srgb, SOURCE_TEXTURE_FORGE, generator, what)


# ── roofs ────────────────────────────────────────────────────────────────────
#: Clay roof tiles — the 2D HOUSE fill pattern (``FillPattern.ROOF_TILES``).
ROOF_TILE: Final = _texture("ROOF_TILE", (178, 90, 62), "generate_roof_tiles", "reds[1]")
ROOF_TILE_CAP: Final = _texture("ROOF_TILE_CAP", (170, 86, 58), "generate_roof_tiles", "reds[3]")
#: Shingles — the roof of the 2D tool-shed sprite (``build_tool_shed``).
SHINGLE: Final = _sprite("SHINGLE", "#78695a", "shingle", "mid")
SHINGLE_CAP: Final = _sprite("SHINGLE_CAP", "#4b4037", "shingle", "dark")
#: Roof timber: the underside of the slab and its fascia.
TIMBER: Final = _sprite("TIMBER", "#66432c", "walnut", "mid")

# ── beds ─────────────────────────────────────────────────────────────────────
#: The raised-bed sprite's frame (``build_raised_bed``: oak) and its plank gaps.
PLANK: Final = _sprite("PLANK", "#b98350", "oak", "mid")
PLANK_GROOVE: Final = _sprite("PLANK_GROOVE", "#7d5029", "oak", "dark")
#: Soil in beds and containers (the sprites' ``granular_fill`` base).
SOIL: Final = _sprite("SOIL", "#573c26", "soil", "mid")

# ── hedges ───────────────────────────────────────────────────────────────────
#: The hedge texture (``FillPattern.HEDGE``): its ground and its four leaf greens.
HEDGE_CORE: Final = _texture("HEDGE_CORE", (16, 52, 30), "generate_hedge", "Tile base")
HEDGE_LEAVES: Final[tuple[PaletteColor, ...]] = (
    _texture("HEDGE_LEAF_0", (29, 84, 48), "generate_hedge", "bodies[2]"),
    _texture("HEDGE_LEAF_1", (35, 96, 55), "generate_hedge", "bodies[0]"),
    _texture("HEDGE_LEAF_2", (44, 112, 64), "generate_hedge", "bodies[1]"),
    _texture("HEDGE_LEAF_3", (51, 122, 71), "generate_hedge", "bodies[3]"),
)

#: Every mirrored colour — what the drift guard and gate G5 iterate.
ALL: Final[tuple[PaletteColor, ...]] = (
    ROOF_TILE, ROOF_TILE_CAP, SHINGLE, SHINGLE_CAP, TIMBER, PLANK, PLANK_GROOVE, SOIL,
    HEDGE_CORE, *HEDGE_LEAVES,
)
