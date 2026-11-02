"""Garden lights: a lantern on a post, and a string of lights between two posts
(Phase 17 L5.4, #389, ADR-070).

The 3D twins of their sprites (``scripts/generate_object_sprites.py``
``build_garden_light`` / ``build_string_lights``) under the rules of ``furniture``
(its module docstring). What the height is:

- **garden light**: the top of the lantern's cap; the post stands on the item's
  circle, the lantern's frame round a warm bulb under the cap. No glass pane: a
  pane is lit by the lamp's own light at its full near-field strength and drew the
  head as a cream-white box at night exposure (3D review of L5) — at night the
  bulb's glow (``ambient.frag``) is the lit lantern, by day a 28 % pane hardly showed;
- **string lights**: the tops of the two posts at the ends of the item's long side;
  the wire hangs between them with a sag of ``SAG_SHARE`` of the span, a bulb every
  ``BULB_SPACING_CM``.

WHERE THE LIGHT IS — the bulb of a lantern, the bulbs of a string — is ONE function
each (``lantern_bulb``, ``string_bulbs``), read by the builder that puts a bulb there
and by ``core/scene3d/lights.py`` that makes it glow and light the garden at night:
a light can never hang somewhere else than its bulb (one canonical path). The point
light that lights the garden stands just BELOW the lantern or the bulb (``lamp_light``):
inside the bulb it lit the ball from within — the ball drew dark (3D review of L5).
"""

from __future__ import annotations

from typing import Final

import numpy as np

from ..build import BuilderRegistry
from ..mesh import Mesh, MeshPart
from ..record import Record
from . import palette
from .common import BuiltBuilder, has_one_plain_ring, plain_block
from .kit import ObjectBox, ball, cylinder, object_box, placed, rod, slab

#: The kinds this module builds.
KINDS: Final[tuple[str, ...]] = ("GARDEN_LIGHT", "STRING_LIGHTS")
#: A string's wire hangs this share of its span below the posts' tops, at its middle.
SAG_SHARE: Final = 0.08
#: A bulb every this many centimetres along the span (at least two).
BULB_SPACING_CM: Final = 40.0
#: The most bulbs one string carries (a 60 m string would otherwise hang 150) — and with
#: low-poly bulbs the longest string stays inside ``OBJECT_TRIANGLE_BUDGET``.
MAX_BULBS_PER_STRING: Final = 40
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
    bulb of a string — None for a record the builder builds as a plain block."""
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


def _string_span(box: ObjectBox) -> tuple[np.ndarray, np.ndarray, float]:
    """The two post centres (item-local x, y, about the box's centre) along the box's
    long side, and the span between them."""
    if box.half_w >= box.half_d:
        inset = min(4.0, 0.3 * box.half_d) + 1.0
        a, b = np.array((-box.half_w + inset, 0.0)), np.array((box.half_w - inset, 0.0))
    else:
        inset = min(4.0, 0.3 * box.half_w) + 1.0
        a, b = np.array((0.0, -box.half_d + inset)), np.array((0.0, box.half_d - inset))
    return a, b, float(np.linalg.norm(b - a))


def _hang(span: float, height_cm: float, count: int) -> tuple[np.ndarray, np.ndarray]:
    """``count`` + 2 points (the two post tops and the points between) of the wire —
    a parabola through the tops, ``SAG_SHARE`` of the span deep — as (share, z)."""
    share = np.linspace(0.0, 1.0, count + 2)
    sag = min(SAG_SHARE * span, 0.45 * height_cm)
    top = height_cm - 2.0
    return share, top - 4.0 * sag * share * (1.0 - share)


def string_bulbs(record: Record, height_cm: float) -> np.ndarray | None:
    """The bulbs of a string of lights, item-local (n, 3) in cm — None for a record the
    builder builds as a plain block."""
    box = _box_of(record)
    if box is None:
        return None
    a, b, span = _string_span(box)
    count = min(MAX_BULBS_PER_STRING, max(2, int(span // BULB_SPACING_CM)))
    share, z = _hang(span, height_cm, count)
    inner = slice(1, -1)          # the bulbs hang between the posts, not on them
    xy = a[None, :] + (b - a)[None, :] * share[inner, None]
    out = np.empty((count, 3))
    out[:, 0] = xy[:, 0] + box.cx
    out[:, 1] = xy[:, 1] + box.cy
    out[:, 2] = z[inner] - BULB_RADIUS_CM - 1.0
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
    """Two slim wooden posts at the ends of the long side, a dark wire hanging between
    them, a warm bulb every ``BULB_SPACING_CM``."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    h = height_cm
    a, b, span = _string_span(box)
    post = min(4.0, 0.3 * min(box.half_w, box.half_d) + 1.0)
    wood = palette.GREY_WOOD_DARK.linear
    meshes = [slab(p[0] - post / 2.0, p[0] + post / 2.0, p[1] - post / 2.0, p[1] + post / 2.0,
                   0.0, h, wood, 0.4) for p in (a, b)]
    count = min(MAX_BULBS_PER_STRING, max(2, int(span // BULB_SPACING_CM)))
    share, z = _hang(span, h, max(2 * count, 8))
    xy = a[None, :] + (b - a)[None, :] * share[:, None]
    points = np.column_stack([xy, z])
    meshes.append(rod(points[:-1], points[1:], 0.35, palette.RUBBER.linear, sides=4))
    bulbs_at = string_bulbs(record, h)
    bulbs: list[Mesh] = []
    if bulbs_at is not None:
        for x, y, bz in bulbs_at - np.array((box.cx, box.cy, 0.0)):
            bulbs.append(rod([(x, y, bz + BULB_RADIUS_CM)], [(x, y, bz + BULB_RADIUS_CM + 1.2)],
                             0.5, palette.RUBBER.linear, sides=4))
            bulbs.append(ball(x, y, bz, BULB_RADIUS_CM, palette.CANVAS_CREAM.linear,
                              squash=BULB_SQUASH, rings=4, segments=8))
    return (_part(meshes, box, "string lights"),
            _part(bulbs, box, "bulbs", casts_shadow=False))


build_garden_light: Final = BuiltBuilder(_garden_light, "garden light")
build_string_lights: Final = BuiltBuilder(_string_lights, "string lights")

BUILDERS: Final[dict[str, BuiltBuilder]] = {
    "GARDEN_LIGHT": build_garden_light,
    "STRING_LIGHTS": build_string_lights,
}


def register(registry: BuilderRegistry) -> None:
    for kind, builder in BUILDERS.items():
        registry.register(kind, builder)


def light_height_cm(record: Record) -> float | None:
    """The height a garden light or a string is BUILT at (the builder's own rule)."""
    builder = BUILDERS.get(record.kind)
    return builder.height_for(record) if builder is not None else None
