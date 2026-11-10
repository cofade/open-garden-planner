"""Material kinds → the QML part components, and the tint rule (L1.2). Engine-free.

A ``MeshPart`` names one of ``core.scene3d.MATERIAL_KINDS``; ``qml/Garden.qml``
declares one part ``Component`` per kind (a ``Model`` with its own material
instance), looked up by the same string. ``PART_COMPONENTS`` is the table both
sides are pinned against (``tests/unit/test_quick3d_qml.py``).

The tint rule, one for every kind::

    albedo = vertex colour x tint          (in linear light)

``tint`` is the item's ``Material.tint_rgba`` for a part with ``tinted=True``
and white for every other part. It is a property of the part's Model, never
baked into the vertex buffer — so a recolour is one property write and no
geometry upload (``EngineSink.update_material``).

How each material receives it (``Garden.qml``):

- ``vc``, ``roof``, ``glass`` — ``PrincipledMaterial.baseColor`` with vertex
  colours enabled. The engine linearises ``baseColor`` with its own polynomial
  approximation of the sRGB curve; it differs from the exact
  ``Material.tint_linear()`` by less than one 8-bit code.
- ``foliage``, ``grass``, ``water`` — a ``vec3`` uniform of the custom shader,
  computed here with the exact curve (``tint_uniform``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from open_garden_planner.core.scene3d import (
    Material,
    MeshPart,
    Rgba,
    pattern_texture_name,
    srgb8_to_linear,
)
from open_garden_planner.core.scene3d.materials import (
    DEFAULT_SURFACE,
    DETAIL_PLANAR,
    DETAIL_UV,
    SURFACES,
    TWO_SIDED_KINDS,
    detail_of,
    two_sided_kinds,
)

__all__ = [
    "DETAIL_MODES",
    "PART_COMPONENTS",
    "SURFACE_KINDS",
    "TWO_SIDED_KINDS",
    "WHITE",
    "SurfaceLook",
    "part_tint",
    "surface_look",
    "tint_uniform",
    "two_sided_kinds",
]

#: ``MeshPart.material_kind`` → id of the part ``Component`` in ``Garden.qml``. Its keys
#: are exactly ``core.scene3d.MATERIAL_KINDS`` (pinned, with the QML, by a test).
PART_COMPONENTS: Final = MappingProxyType({
    "vc": "vcPart",
    "roof": "roofPart",
    "foliage": "foliagePart",
    "grass": "grassPart",
    "glass": "glassPart",
    "water": "waterPart",
})

#: The tint of a part that is not tinted: the identity of the multiplication.
WHITE: Final[Rgba] = (255, 255, 255, 255)


def part_tint(part: MeshPart, material: Material) -> Rgba:
    """The sRGB tint the Model of ``part`` carries for an item with ``material``.

    THE rule — the engine read-backs (``quick3d_render_driver``, the engine test,
    the adapter's double) must call it rather than copy it. A ``fill_texture`` part
    shows the item's own picture, which carries the colour, so its tint is white —
    except for a SOLID fill, which has no picture and shows the fill colour through
    the same ``set_part_fill`` call. (``host.engine_parts`` reads the QML ``tint``
    property; it does not call this.)
    """
    if part.fill_texture:
        return WHITE if pattern_texture_name(material.pattern) is not None else material.tint_rgba
    return material.tint_rgba if part.tinted else WHITE


def tint_uniform(tint_rgba: Rgba) -> tuple[float, float, float]:
    """``tint_rgba`` as the linear RGB a custom shader multiplies with."""
    red, green, blue, _alpha = srgb8_to_linear(tint_rgba)
    return (red, green, blue)


#: The material kinds whose part component reads a surface (``vcPart``, ``roofPart``).
SURFACE_KINDS: Final = frozenset({"vc", "roof"})
#: ``SurfaceDetail.mapping`` as the part's ``detailMode`` (``built_detail.vert``).
DETAIL_MODES: Final = MappingProxyType({DETAIL_UV: 1.0, DETAIL_PLANAR: 2.0})


@dataclass(frozen=True, slots=True)
class SurfaceLook:
    """What the host writes on a part's Model for its surface (#803, #801): the QML
    properties, and the pattern NAME of the detail picture it shows (None: none)."""

    properties: Mapping[str, float]
    detail_pattern: str | None


def surface_look(kind: str, surface: str) -> SurfaceLook | None:
    """The surface look of a part of material ``kind`` made of ``surface`` (empty:
    ``DEFAULT_SURFACE``) — None for a kind whose component reads no surface. THE rule:
    the host applies it, the render tier's read-backs call it rather than copy it."""
    if kind not in SURFACE_KINDS:
        return None
    entry = SURFACES[surface or DEFAULT_SURFACE]
    properties: dict[str, float] = {"surfaceRough": entry.roughness,
                                    "surfaceSpecular": entry.specular}
    detail = detail_of(entry.name, kind)
    if detail is None:
        return SurfaceLook(MappingProxyType(properties), None)
    properties.update({"detailMode": DETAIL_MODES[detail.mapping], "detailTile": detail.tile_cm,
                       "detailNormal": detail.normal, "detailFade": detail.fade_cm,
                       "detailContrast": detail.contrast})
    return SurfaceLook(MappingProxyType(properties), detail.pattern)
