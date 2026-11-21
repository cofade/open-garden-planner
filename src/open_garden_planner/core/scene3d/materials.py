"""3D materials: the two-sided kinds and the surface classes of built parts.

Two tables, both Qt-free:

- ``TWO_SIDED_KINDS`` (Phase 17 L7, #720): the material kinds whose look draws both
  sides of a triangle.
- ``SURFACES`` (#803, #801): what a built part is MADE of — rubber, canvas, plastic,
  wood, steel, masonry, plaster, roof tiles … — and so how it reflects: its roughness
  and specular amount (``ogp-lush-cinematic`` §4) and, for the few surfaces the plan
  shows as a pattern, the detail picture its faces carry (``SurfaceDetail``). A builder's
  palette entry names its surface (``builders/palette.py``), a tinted part names its own
  (``MeshPart.surface``), and the sink hands the surface's numbers to the engine with the
  part (``PartSpec.surface`` -> the Model's ``surfaceRough`` / ``surfaceSpecular`` /
  ``detailMap``). That is the ONE path: the scene file holds no table of its own.

Before #803 every built part reflected with one roughness 0.78 and one specular 0.35: a
black rubber trampoline mat facing a low sun took a broad warm highlight and read tan.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

#: The material kinds whose look draws BOTH sides of a triangle (cullMode:
#: Material.NoCulling in their part component). Since Qt 6.12 the engine's pick honours
#: a material's cull mode, so a ray picks these from behind too.
TWO_SIDED_KINDS: Final[frozenset[str]] = frozenset({"foliage", "grass", "glass"})


def two_sided_kinds(cutaway: bool = False) -> frozenset[str]:
    """Return the set of material kinds that are two-sided (not culled).

    Under Cutaway (roofs_hidden), the vertex-coloured ('vc') parts of house walls
    are drawn with NoCulling so inner wall faces are visible and pickable.
    """
    if cutaway:
        return TWO_SIDED_KINDS | frozenset({"vc"})
    return TWO_SIDED_KINDS


#: How a detail picture is laid onto a part's faces.
#: ``uv``: by the mesh's own uvs — a roof's tiles (``builders/roofs.py``: u along the
#: ridge, v away from it, both in cm / ``PATTERN_TILE_CM``, the 2D brush's frame);
#: ``planar``: by the face's own plane in the item's frame, computed in the shader from the
#: model-space position and normal — a wall's courses stay level round its corners.
DETAIL_UV: Final = "uv"
DETAIL_PLANAR: Final = "planar"


@dataclass(frozen=True, slots=True)
class SurfaceDetail:
    """A surface's detail picture (#801).

    ``pattern``: the ``FillPattern`` NAME whose texture it is (the canvas's own picture,
    ``resources/textures``: no new asset). ``mapping``: ``DETAIL_UV`` or
    ``DETAIL_PLANAR``. ``tile_cm``: how many centimetres one 256-px picture spans (the
    canvas lays every pattern at 256 cm; a roof's tiles keep that, so 2D and 3D tiles
    are one size). ``normal``: the detail normal's strength (0 = albedo only).
    ``fade_cm``: the camera distance from which the detail normal has faded to flat —
    from 40 % of it on (the albedo needs no fade: its mipmaps reach the flat mean).
    ``contrast``: how much of the picture's lighter and darker texels the albedo takes
    (1 = the canvas's own contrast; less keeps a bright face's light texels under the
    tone curve's top). The mean stays the part's colour at any contrast."""

    pattern: str
    mapping: str
    tile_cm: float
    normal: float
    fade_cm: float
    contrast: float = 1.0


@dataclass(frozen=True, slots=True)
class Surface:
    """What a built part is made of: its roughness, specular amount (PBR, 0-1),
    optional detail picture and linear albedo scale (1.0 = unscaled; < 1.0
    compensates for matte diffuse lift so bright noon tiles/walls stay unclipped)."""

    name: str
    roughness: float
    specular: float
    detail: SurfaceDetail | None = None
    albedo_scale: float = 1.0


def _surface(name: str, roughness: float, specular: float,
             detail: SurfaceDetail | None = None,
             albedo_scale: float = 1.0) -> tuple[str, Surface]:
    return name, Surface(name, roughness, specular, detail, albedo_scale)


#: The surface a metal container's walls and a steel frame are made of.
STEEL_SURFACE: Final = "steel"

#: The surface of a part that names none: the one look every built part had before
#: #803 (roughness 0.78, specular 0.35) — a raised surface's sides, the plain block, a
#: plant's wood. ``Garden.qml``'s part components default to exactly these numbers.
DEFAULT_SURFACE: Final = "default"

#: Every surface (#803, #883, #884, #887, #957, #965). The values sit in
#: ``ogp-lush-cinematic`` §4's ranges; glossy metals and glass panes sit at 0.70 so
#: Ultra SSR does not shimmer (#883), concrete keeps specular off so flat roofs do not
#: take a lilac sky-Fresnel cast at golden hour (#965), and bright matte mineral/tile
#: surfaces carry a linear ``albedo_scale`` so noon roofs and walls stay unclipped (#884).
SURFACES: Final = MappingProxyType(dict((
    _surface(DEFAULT_SURFACE, 0.78, 0.35),
    _surface("wood", 0.75, 0.25, albedo_scale=0.80),          # §4 wood 0.60-0.80 (#884: noon deck)
    _surface("wood_cladding", 0.80, 0.20,  # a shed's boarded walls (#801)
             SurfaceDetail("WOOD", DETAIL_PLANAR, 128.0, 1.5, 3000.0),
             albedo_scale=0.86),
    _surface("steel", 0.70, 0.50),         # #883: >= 0.70 suppresses Ultra SSR noise
    _surface("iron", 0.70, 0.35),          # #883: >= 0.70 suppresses Ultra SSR noise
    _surface("enamel", 0.70, 0.15),        # #883: >= 0.70 suppresses Ultra SSR noise
    _surface("corten", 0.82, 0.20,         # #957: weathered steel raised-bed frames
             SurfaceDetail("CORTEN", DETAIL_PLANAR, 128.0, 0.7, 2500.0, 0.8),
             albedo_scale=0.88),
    _surface("plastic", 1.0, 0.20),       # a pad facing a low sun: 8.0 degrees off its blue
    _surface("rubber", 0.95, 0.0),         # specular off (SPECULAR_OFF_AT): no grazing sheen
    _surface("canvas", 0.95, 0.0),
    _surface("terracotta", 0.85, 0.20),    # §4 terracotta pots 0.80-0.90
    _surface("stone", 0.90, 0.15, albedo_scale=0.85),
    _surface("masonry", 0.90, 0.15,        # #801, #884, #887: ~21 cm courses (128 cm / 6)
             SurfaceDetail("STONE", DETAIL_PLANAR, 128.0, 1.8, 3000.0, 0.75),
             albedo_scale=0.82),
    _surface("brick", 0.90, 0.15,          # #957: running-bond brick raised-bed frames
             SurfaceDetail("BRICK", DETAIL_PLANAR, 128.0, 1.5, 3000.0, 0.75),
             albedo_scale=0.82),
    _surface("plaster", 0.90, 0.15,        # #801, #884: §4 plaster walls 0.85-0.95
             SurfaceDetail("CONCRETE", DETAIL_PLANAR, 128.0, 1.0, 2000.0, 0.85),
             albedo_scale=0.80),
    _surface("concrete", 0.95, 0.0,        # #965: matte, no grazing sky Fresnel
             albedo_scale=0.85),
    _surface("flat_roof", 0.95, 0.0,       # #965: dark matte EPDM/gravel roof, no golden-hour lilac
             albedo_scale=0.45),
    _surface("soil", 0.95, 0.10),          # §4 bark, soil, mulch 0.85-0.95
    _surface("roof_tile", 0.80, 0.15,      # #801, #884: §4 roof tiles 0.70-0.85
             SurfaceDetail("ROOF_TILES", DETAIL_UV, 256.0, 1.5, 4000.0, 0.6),
             albedo_scale=0.76),
    _surface("roof_cap", 0.80, 0.15,       # #887: plain ridge cap so it stands out from tiles
             albedo_scale=0.76),
    _surface("shingle", 0.80, 0.15,        # #887: natural shingle scale & soft contrast (no patchwork)
             SurfaceDetail("SLATE", DETAIL_UV, 128.0, 1.2, 3000.0, 0.35)),
    _surface("glass_pane", 0.70, 0.40),    # #883: >= 0.70 suppresses Ultra SSR window flicker
    _surface("water", 0.30, 0.50),
    _surface("leaf", 0.82, 0.25),          # the foliage shaders' own values
    _surface("ember", 0.90, 0.10),
)))


def surface(name: str) -> Surface:
    """The surface called ``name`` — ``KeyError`` for a name no table entry has."""
    return SURFACES[name]


def detail_of(name: str, material_kind: str) -> SurfaceDetail | None:
    """The detail picture a part of surface ``name`` and ``material_kind`` shows, or None.

    A ``DETAIL_UV`` picture needs the uvs only a roof builder writes, so it is shown on
    ``roof`` parts alone (a house block's tiled top keeps the tile's numbers, not its
    picture); a ``DETAIL_PLANAR`` one on any ``vc`` or ``roof`` part."""
    detail = SURFACES[name].detail
    if detail is None or material_kind not in ("vc", "roof"):
        return None
    if detail.mapping == DETAIL_UV and material_kind != "roof":
        return None
    return detail
