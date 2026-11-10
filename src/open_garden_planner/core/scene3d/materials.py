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
    """What a built part is made of: its roughness and specular amount (PBR, 0-1) and
    its optional detail picture."""

    name: str
    roughness: float
    specular: float
    detail: SurfaceDetail | None = None


def _surface(name: str, roughness: float, specular: float,
             detail: SurfaceDetail | None = None) -> tuple[str, Surface]:
    return name, Surface(name, roughness, specular, detail)


#: The surface a metal container's walls and a steel frame are made of.
STEEL_SURFACE: Final = "steel"

#: The surface of a part that names none: the one look every built part had before
#: #803 (roughness 0.78, specular 0.35) — a raised surface's sides, the plain block, a
#: plant's wood. ``Garden.qml``'s part components default to exactly these numbers.
DEFAULT_SURFACE: Final = "default"

#: Every surface (#803). The values sit in ``ogp-lush-cinematic`` §4's ranges; where §4
#: has none, the issue's measured proposal (rubber / canvas, plastic, steel).
SURFACES: Final = MappingProxyType(dict((
    _surface(DEFAULT_SURFACE, 0.78, 0.35),
    _surface("wood", 0.75, 0.25),          # §4 wood 0.60-0.80
    _surface("wood_cladding", 0.80, 0.20,  # a shed's boarded walls (#801)
             SurfaceDetail("WOOD", DETAIL_PLANAR, 128.0, 1.5, 3000.0)),
    _surface("steel", 0.45, 0.50),         # §4 aluminium frames 0.30-0.50
    _surface("iron", 0.60, 0.35),
    _surface("enamel", 0.60, 0.15),
    _surface("plastic", 0.95, 0.20),
    _surface("rubber", 0.95, 0.0),         # specular off (SPECULAR_OFF_AT): no grazing sheen
    _surface("canvas", 0.95, 0.0),
    _surface("terracotta", 0.85, 0.20),    # §4 terracotta pots 0.80-0.90
    _surface("stone", 0.90, 0.15),
    _surface("masonry", 0.90, 0.15,        # a garden wall's courses (#801)
             SurfaceDetail("STONE", DETAIL_PLANAR, 256.0, 2.0, 4000.0)),
    _surface("plaster", 0.90, 0.15,        # §4 plaster walls 0.85-0.95 (#801)
             SurfaceDetail("CONCRETE", DETAIL_PLANAR, 128.0, 1.0, 2000.0)),
    _surface("concrete", 0.90, 0.15),
    _surface("soil", 0.95, 0.10),          # §4 bark, soil, mulch 0.85-0.95
    _surface("roof_tile", 0.80, 0.15,      # §4 roof tiles 0.70-0.85 (roofMat's values)
             SurfaceDetail("ROOF_TILES", DETAIL_UV, 256.0, 1.5, 4000.0, 0.6)),
    _surface("shingle", 0.80, 0.15,
             SurfaceDetail("SLATE", DETAIL_UV, 100.0, 1.5, 3000.0)),
    _surface("glass_pane", 0.40, 0.40),    # an opaque window pane in a facade
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
