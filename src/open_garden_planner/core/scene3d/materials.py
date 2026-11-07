"""3D materials classification and culling constants (Phase 17 L7, #720)."""

from __future__ import annotations

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
