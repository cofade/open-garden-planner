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

from types import MappingProxyType
from typing import Final

from open_garden_planner.core.scene3d import Material, MeshPart, Rgba, srgb8_to_linear

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
    """The sRGB tint the Model of ``part`` carries for an item with ``material``."""
    return material.tint_rgba if part.tinted else WHITE


def tint_uniform(tint_rgba: Rgba) -> tuple[float, float, float]:
    """``tint_rgba`` as the linear RGB a custom shader multiplies with."""
    red, green, blue, _alpha = srgb8_to_linear(tint_rgba)
    return (red, green, blue)
