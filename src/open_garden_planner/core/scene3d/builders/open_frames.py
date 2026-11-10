"""The solid members of an OPEN FRAME, for the 2D sun study (#698).

The 2D sun study casts every object as its footprint prism. For a pergola, a
trellis, a swing, a hammock or a garden light that prism is mostly air, and the
2D model weights its shadow by a transmittance (``core.object_height.
OPEN_FRAME_TYPE_NAMES``, ADR-059's open-frames addendum). The weight has to come
from somewhere, and a table of shares per kind would be a second model that
drifts from the first — it would also be wrong for every item that is not the
table's size, and for every sun that is not the table's.

So this module hands out the frame's own MEMBERS, as triangles in the record's
local frame, and ``core.shadow_geometry.open_frame_transmittance`` measures them
against the prism for the sun of the moment. The precedent is #440's pitched
roofs (``buildings.pitched_roof_triangles_for_record``): the 2D model reads the
3D builder's geometry instead of repeating it.

- **PERGOLA**: the one layout of ``core.pergola`` — the layout its 2D picture is
  painted from and its 3D timber is built from — as plain boxes
  (``structures.pergola_members``).
- **TRELLIS, SWING, HAMMOCK, GARDEN_LIGHT**: the shadow-casting parts of the
  production builder, built for this item's own footprint and height.

``None`` means "not an open frame here": a kind that is none, or an item whose
builder made the plain block instead of its model (a footprint that is no box, an
outline of several rings). Such an item is the solid prism in 2D, as it is a solid
in 3D.

Qt-free; numpy and the builders only.
"""

from __future__ import annotations

from typing import Final

import numpy as np

from ...object_height import OPEN_FRAME_TYPE_NAMES
from ..mesh import Mesh
from ..record import PARAM_RADIUS_CM, SHAPE_CIRCLE, Material, Params, ParamValue, Record, Transform
from . import lights, play, structures
from .common import PLAIN_BLOCK_NAME, BuiltBuilder

__all__ = ["FrameTriangle", "OPEN_FRAME_BUILDERS", "open_frame_triangles",
           "open_frame_triangles_for_record"]

FramePoint = tuple[float, float, float]
FrameTriangle = tuple[FramePoint, FramePoint, FramePoint]

#: The production builder of every open-frame kind (a test holds this to
#: ``OPEN_FRAME_TYPE_NAMES``: a kind listed there without a builder here would be
#: cast solid without a word).
OPEN_FRAME_BUILDERS: Final[dict[str, BuiltBuilder]] = {
    kind: builder
    for module in (structures, play, lights)
    for kind, builder in module.BUILDERS.items()
    if kind in OPEN_FRAME_TYPE_NAMES
}


def _triangles(meshes: list[Mesh]) -> tuple[FrameTriangle, ...]:
    corners = [mesh.positions.astype(np.float64)[mesh.indices.reshape(-1, 3)]
               for mesh in meshes if mesh.vertex_count]
    if not corners:
        return ()
    flat = np.concatenate(corners).reshape(-1, 9).tolist()
    return tuple(((t[0], t[1], t[2]), (t[3], t[4], t[5]), (t[6], t[7], t[8])) for t in flat)


def open_frame_triangles_for_record(record: Record) -> tuple[FrameTriangle, ...] | None:
    """The record's solid members as triangles in its local frame (z from its own
    ground), or None when it is not cast as an open frame (module docstring)."""
    builder = OPEN_FRAME_BUILDERS.get(record.kind)
    if builder is None:
        return None
    height = builder.height_for(record)
    if height is None or not height > 0.0 or builder.uses_the_plain_block(record):
        return None
    if record.kind == "PERGOLA":
        members = structures.pergola_members(record, height)
        return None if members is None else (_triangles([members]) or None)
    parts = builder(record)
    if any(part.name == PLAIN_BLOCK_NAME for part in parts):
        return None  # the builder had no model for this footprint: a solid, in 2D too
    return _triangles([part.mesh for part in parts if part.casts_shadow]) or None


def open_frame_triangles(
    kind: str,
    shape: str,
    local_footprint: tuple[tuple[float, float], ...],
    height_cm: float,
    *,
    radius_cm: float | None = None,
) -> tuple[FrameTriangle, ...] | None:
    """``open_frame_triangles_for_record`` of a local record made of these — what the
    2D caster walk knows of an item (the pattern of ``buildings.pitched_roof_triangles``).
    ``radius_cm``: a circle item's radius, which is how a builder reads a round footprint.
    """
    if kind not in OPEN_FRAME_BUILDERS or len(local_footprint) < 3 or not height_cm > 0.0:
        return None
    params: dict[str, ParamValue] = {}
    if shape == SHAPE_CIRCLE and radius_cm is not None:
        params[PARAM_RADIUS_CM] = radius_cm
    record = Record(
        item_id="shade-frame",
        kind=kind,
        shape=shape,
        footprints=(local_footprint,),
        transform=Transform(),
        material=Material(kind, None, None),
        height_cm=height_cm,
        params=Params(params),
    )
    return open_frame_triangles_for_record(record)
