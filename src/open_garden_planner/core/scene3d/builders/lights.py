"""Garden lights: a lantern on a post, and a string of lights on a line of posts
(Phase 17 L5.4, #389, ADR-070).

The 3D twins of their 2D pictures — the lantern's sprite (``scripts/
generate_object_sprites.py`` ``build_garden_light``) and the string's line
(``ui/canvas/items/string_lights_paint.py``; a string has no sprite) — under the rules
of ``furniture`` (its module docstring). What the height is:

- **garden light**: the top of the lantern's cap; the post stands on the item's
  circle, the lantern's frame round a warm bulb under the cap. No glass pane: a
  pane is lit by the lamp's own light at its full near-field strength and drew the
  head as a cream-white box at night exposure (3D review of L5) — at night the
  bulb's glow (``ambient.frag``) is the lit lantern, by day a 28 % pane hardly showed;
- **string lights**: the tops of its posts. A string is a LINE (owner's manual test of
  L5): a post at every point of it, the wire hanging between two posts with a sag of
  ``SAG_SHARE`` of the span, the bulbs where ``core/string_lights.layout`` hangs them —
  the layout the canvas draws too. A string read from a file as a rectangle (a
  hand-edited plan) is the line along its long side: two posts.

WHERE THE LIGHT IS — the bulb of a lantern, the bulbs of a string — is ONE function
each (``lantern_bulb``, ``string_bulbs``), read by the builder that puts a bulb there
and by ``core/scene3d/lights.py`` that makes it glow and light the garden at night:
a light can never hang somewhere else than its bulb (one canonical path). The point
light that lights the garden stands just BELOW the lantern or a string's middle bulb
(``lamp_light``): inside the bulb it lit the ball from within — the ball drew dark (3D
review of L5).
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from ...string_lights import Layout, layout
from ..build import BuilderRegistry
from ..mesh import Mesh, MeshPart
from ..record import Record
from . import palette
from .common import BuiltBuilder, has_one_plain_ring, plain_block
from .kit import ObjectBox, ball, cylinder, object_box, placed, rod, slab

#: The kinds this module builds.
KINDS: Final[tuple[str, ...]] = ("GARDEN_LIGHT", "STRING_LIGHTS")
#: A string's wire hangs this share of a span below the posts' tops, at its middle.
SAG_SHARE: Final = 0.08
#: The wire of one span is at most this many straight pieces of its parabola — one per
#: ``WIRE_PIECE_CM`` of span, at least two.
WIRE_PIECES: Final = 24
WIRE_PIECE_CM: Final = 25.0
#: The side of a string's square wooden post, cm.
STRING_POST_CM: Final = 4.0
#: The radius of a string's wire, cm — 0.35 broke into dashes at 7 m on Low (3D review
#: of the line).
WIRE_RADIUS_CM: Final = 0.5
#: The radius of a bulb, cm, and how much taller than wide a string's bulb is.
BULB_RADIUS_CM: Final = 2.6
BULB_SQUASH: Final = 1.25
#: A lamp's point light stands this far below the lantern's floor or the bulb.
LIGHT_BELOW_CM: Final = 3.0

Color = tuple[float, float, float, float]


def _part(meshes: list[Mesh], box: ObjectBox, name: str, kind: str = "vc", *,
          casts_shadow: bool = True) -> MeshPart:
    return MeshPart(placed(meshes, box), kind, casts_shadow=casts_shadow, name=name)


# ── where the light is (shared with core/scene3d/lights.py) ─────────────────


def _box_of(record: Record) -> ObjectBox | None:
    """The object's box — or None where the builder builds the plain block instead:
    a record that is not ONE plain ring (several rings, a hole, an outline drawn
    crossing itself — a hostile file can type any polygon a string of lights), or
    whose footprint is no box. The bulbs follow the builder's own rule, so a light
    never hangs where no bulb was built."""
    if not has_one_plain_ring(record):
        return None
    return object_box(record)

def _lantern(box: ObjectBox, height_cm: float) -> tuple[float, float, float, float]:
    """(post radius, lantern bottom, lantern top, lantern half width) of a lantern."""
    r, h = box.radius, height_cm
    half = min(0.55 * r, 0.12 * h, 14.0)
    cap = min(4.0, 0.08 * h)
    top = h - cap
    bottom = max(0.35 * h, top - 2.6 * half)
    post = min(0.22 * r, 3.5)
    return post, bottom, top, half


def lantern_bulb(record: Record, height_cm: float) -> tuple[float, float, float] | None:
    """The bulb of a garden light, item-local (cm; z up from its soil) — None for a
    record the builder builds as a plain block."""
    box = _box_of(record)
    if box is None:
        return None
    _post, bottom, top, _half = _lantern(box, height_cm)
    return (box.cx, box.cy, (bottom + top) / 2.0)


def lamp_light(record: Record, height_cm: float) -> tuple[float, float, float] | None:
    """Where the point light of a garden light or a string stands, item-local (cm; z up
    from its soil): ``LIGHT_BELOW_CM`` under the lantern's floor, or under the middle
    bulb of a string — which ``POST_CLEAR_CM`` keeps off the posts of its span (before it,
    that bulb hung on the middle post of a symmetric string; the bulbs' centroid, tried in
    review, stood inside the middle post of a straight one). None for a record the builder
    builds as a plain block."""
    if record.kind == "GARDEN_LIGHT":
        box = _box_of(record)
        if box is None:
            return None
        _post, bottom, _top, _half = _lantern(box, height_cm)
        return (box.cx, box.cy, bottom - LIGHT_BELOW_CM)
    bulbs = string_bulbs(record, height_cm)
    if bulbs is None or not len(bulbs):
        return None
    x, y, z = bulbs[len(bulbs) // 2]
    return (float(x), float(y), float(z) - BULB_RADIUS_CM * BULB_SQUASH - LIGHT_BELOW_CM)


def string_layout(record: Record) -> Layout | None:
    """Where a string's posts stand and its bulbs hang, item-local (cm) —
    ``core/string_lights.layout`` of its line: the polyline as drawn, or for a string
    read as a rectangle the line along its long side. None for a record the builder
    builds as a plain block."""
    if len(record.path) >= 2:
        return layout(record.path)
    box = _box_of(record)
    if box is None:
        return None
    if box.half_w >= box.half_d:
        inset = min(4.0, 0.3 * box.half_d) + 1.0
        ends = ((box.cx - box.half_w + inset, box.cy), (box.cx + box.half_w - inset, box.cy))
    else:
        inset = min(4.0, 0.3 * box.half_w) + 1.0
        ends = ((box.cx, box.cy - box.half_d + inset), (box.cx, box.cy + box.half_d - inset))
    return layout(ends)


def wire_pieces(length_cm: float) -> int:
    """How many straight pieces the wire of a span of ``length_cm`` is made of."""
    return min(WIRE_PIECES, max(2, math.ceil(length_cm / WIRE_PIECE_CM)))


def _wire_z(length_cm: float, height_cm: float, share: np.ndarray) -> np.ndarray:
    """The wire's height at ``share`` of a span of ``length_cm`` — a parabola through
    the two posts' tops, ``SAG_SHARE`` of the span deep at its middle."""
    sag = min(SAG_SHARE * length_cm, 0.45 * height_cm)
    return (height_cm - 2.0) - 4.0 * sag * share * (1.0 - share)


def string_bulbs(record: Record, height_cm: float) -> np.ndarray | None:
    """The bulbs of a string of lights, item-local (n, 3) in cm — hanging under the
    wire where ``string_layout`` puts them. None for a record the builder builds as a
    plain block."""
    lay = string_layout(record)
    if lay is None:
        return None
    out = np.empty((len(lay.bulbs), 3))
    for row, bulb in enumerate(lay.bulbs):
        x, y = lay.bulb_xy(bulb)
        length = lay.spans[bulb.span].length_cm
        z = float(_wire_z(length, height_cm, np.array(bulb.share)))
        out[row] = (x, y, z - BULB_RADIUS_CM - 1.0)
    return out


# ── the builders ─────────────────────────────────────────────────────────────

def _garden_light(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A black lantern on a slim post: a square lantern frame round a warm bulb, a
    pyramid-ish cap on top (no pane: the module docstring)."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    r, h = box.radius, height_cm
    post, bottom, top, half = _lantern(box, h)
    iron, iron_light = palette.ENAMEL_BLACK.linear, palette.ENAMEL_BLACK_LIGHT.linear
    foot = min(0.6 * r, 9.0)
    meshes = [cylinder(0.0, 0.0, foot, 0.0, min(3.0, 0.05 * h), iron, segments=12),
              cylinder(0.0, 0.0, post, 0.0, bottom, iron, segments=10),
              slab(-half, half, -half, half, bottom - 1.5, bottom, iron_light),
              slab(-half - 1.0, half + 1.0, -half - 1.0, half + 1.0, top, top + 1.2, iron),
              cylinder(0.0, 0.0, half + 1.0, top + 1.2, h, iron, top_radius=1.0, segments=4)]
    # four corner bars of the lantern
    bars = [(sx * (half - 0.6), sy * (half - 0.6)) for sx in (-1, 1) for sy in (-1, 1)]
    meshes.append(rod([(x, y, bottom) for x, y in bars], [(x, y, top) for x, y in bars], 0.6, iron))
    bulb_z = (bottom + top) / 2.0
    bulb = ball(0.0, 0.0, bulb_z, min(0.55 * half, 4.0), palette.CANVAS_CREAM.linear)
    return (_part(meshes, box, "garden light"),
            _part([bulb], box, "bulb", casts_shadow=False))


def _string_lights(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A slim wooden post at every point of the line, a dark wire hanging between two
    posts, a warm bulb wherever the layout hangs one (``string_layout``)."""
    lay = string_layout(record)
    if lay is None:
        return plain_block(record, height_cm)
    h, half = height_cm, STRING_POST_CM / 2.0
    wood = palette.GREY_WOOD_DARK.linear
    meshes = [slab(x - half, x + half, y - half, y + half, 0.0, h, wood, 0.4)
              for x, y in lay.posts]
    starts: list[np.ndarray] = []
    ends: list[np.ndarray] = []
    for span in lay.spans:
        (ax, ay), (bx, by) = lay.posts[span.a], lay.posts[span.b]
        share = np.linspace(0.0, 1.0, wire_pieces(span.length_cm) + 1)
        points = np.column_stack([ax + (bx - ax) * share, ay + (by - ay) * share,
                                  _wire_z(span.length_cm, h, share)])
        starts.append(points[:-1])
        ends.append(points[1:])
    if starts:
        meshes.append(rod(np.concatenate(starts), np.concatenate(ends), WIRE_RADIUS_CM,
                          palette.RUBBER.linear, sides=4))
    bulbs: list[Mesh] = []
    bulbs_at = string_bulbs(record, h)
    if bulbs_at is not None:
        for x, y, bz in bulbs_at:
            bulbs.append(rod([(x, y, bz + BULB_RADIUS_CM)], [(x, y, bz + BULB_RADIUS_CM + 1.2)],
                             0.5, palette.RUBBER.linear, sides=4))
            bulbs.append(ball(x, y, bz, BULB_RADIUS_CM, palette.CANVAS_CREAM.linear,
                              squash=BULB_SQUASH, rings=5, segments=12))
    parts = [MeshPart(Mesh.merge(meshes), "vc", name="string lights")]
    if bulbs:
        parts.append(MeshPart(Mesh.merge(bulbs), "vc", casts_shadow=False, name="bulbs"))
    return tuple(parts)


build_garden_light: Final = BuiltBuilder(_garden_light, "garden light")
build_string_lights: Final = BuiltBuilder(_string_lights, "string lights")

BUILDERS: Final[dict[str, BuiltBuilder]] = {
    "GARDEN_LIGHT": build_garden_light,
    "STRING_LIGHTS": build_string_lights,
}


def register(registry: BuilderRegistry) -> None:
    for kind, builder in BUILDERS.items():
        registry.register(kind, builder)


#: What one part of a string costs, in triangles (measured: a bevelled post 38, a wire
#: piece of 4 sides 8, a bulb's ball 120 and its cap 8; #710).
_POST_TRIANGLES: Final = 38
_WIRE_PIECE_TRIANGLES: Final = 8
_BULB_TRIANGLES: Final = 120 + 8


def string_triangle_budget(record: Record) -> int:
    """The most triangles a string of lights may have. It grows with the line — a post
    a point (``MAX_POSTS`` at most), at most ``WIRE_PIECES`` pieces a span,
    ``MAX_BULBS_PER_STRING`` bulbs at most — as a fence's budget grows with its (a garden
    light is one small object: ``OBJECT_TRIANGLE_BUDGET``). It is the builder's count
    part by part, so its ceiling is the line's own: at ``MAX_POSTS`` posts about
    77 000 triangles."""
    lay = string_layout(record)
    if lay is None:   # the plain block of its regions: a prism's two caps and its walls
        corners = sum(len(ring) for ring in record.footprints)
        return 4 * corners + 64
    pieces = sum(wire_pieces(span.length_cm) for span in lay.spans)
    return (_POST_TRIANGLES * len(lay.posts) + _WIRE_PIECE_TRIANGLES * pieces
            + _BULB_TRIANGLES * len(lay.bulbs))


def light_height_cm(record: Record) -> float | None:
    """The height a garden light or a string is BUILT at (the builder's own rule)."""
    builder = BUILDERS.get(record.kind)
    return builder.height_for(record) if builder is not None else None
