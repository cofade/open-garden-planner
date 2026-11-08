"""The parametric pergola: one layout for its 2D picture and its 3D build (#769).

A pergola is four posts carrying a ring of beams, nine rafters across the depth
and five thin purlins laid across the rafters — the picture the old fixed
infrastructure sprite showed, now drawn from the item's own rectangle and built
as real timber. This module is the ONE layout:

- ``ui/canvas/items/pergola_paint.py`` draws its rectangles;
- ``core/scene3d/builders/structures.py`` extrudes them to their heights;
- the gallery's thumbnail paints the same picture.

All lengths are centimetres in the object's own frame, centred on ``(0, 0)``;
``width`` runs along local x and ``depth`` along local y. A member is a
``Rect`` in plan; each group also states the heights it spans, so the 3D build
needs no second table of constants. The top of the purlins is exactly the
item's height (ADR-037's "the top is the height"); the rafters carry them, the
beams carry the rafters, and the posts carry the beams.

The sizes follow the old sprite's proportions and the builder's caps: a post is
at most 14 cm square, the beams at most 18 cm deep, and every element is bounded
however large the plan's rectangle is. Qt-free: floats and dataclasses only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

#: A post's largest side, and its share of the footprint's shorter side.
POST_MAX_CM: Final = 14.0
POST_SHARE: Final = 0.06
#: How far a post's centre stands in from the footprint's edge.
POST_INSET_MAX_CM: Final = 10.0
POST_INSET_SHARE: Final = 0.04
#: The beams' largest depth and their share of the pergola's height.
BEAM_DEPTH_MAX_CM: Final = 18.0
BEAM_DEPTH_SHARE: Final = 0.08
#: A beam's plan width, and its share of the post's side.
BEAM_WIDTH_MAX_CM: Final = 10.0
BEAM_WIDTH_SHARE: Final = 0.8
#: The rafters: how many, their largest height and width, and how far the outermost
#: sits in from the side edge (the sprite's 10 %).
RAFTER_COUNT: Final = 9
RAFTER_DEPTH_MAX_CM: Final = 12.0
RAFTER_DEPTH_SHARE: Final = 0.06
RAFTER_WIDTH_MAX_CM: Final = 8.0
RAFTER_WIDTH_SHARE: Final = 0.03
RAFTER_INSET_MAX_CM: Final = 30.0
RAFTER_INSET_SHARE: Final = 0.1
#: A rafter stops this far short of the front and back edges (the old builder's 1 cm).
RAFTER_END_CLEAR_CM: Final = 1.0
#: The purlins: how many, how thick (vertically), how wide (in plan), and how far
#: the outermost line sits in from the front and back edges.
PURLIN_COUNT: Final = 5
PURLIN_DEPTH_MAX_CM: Final = 4.0
PURLIN_DEPTH_SHARE: Final = 0.02
PURLIN_WIDTH_MAX_CM: Final = 5.0
PURLIN_WIDTH_SHARE: Final = 0.02
PURLIN_EDGE_MAX_CM: Final = 18.0
PURLIN_EDGE_SHARE: Final = 0.06
#: The beams and rafters stop this far inside the footprint's side edges.
BEAM_END_CLEAR_CM: Final = 1.0


@dataclass(frozen=True, slots=True)
class Rect:
    """An axis-aligned member in plan, in the object's own frame (cm)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def depth(self) -> float:
        return self.y1 - self.y0

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def as_slab(self) -> tuple[float, float, float, float]:
        """The ``(cx, cy, size_x, size_y)`` form ``builders.kit.slabs`` takes."""
        cx, cy = self.centre
        return (cx, cy, self.width, self.depth)


@dataclass(frozen=True, slots=True)
class PergolaLayout:
    """Every member of a pergola, and the heights its layers occupy (cm).

    ``posts`` stand from the ground to ``beam_bottom``; the four ``beams`` fill
    ``beam_bottom`` … ``deck``; the ``rafters`` fill ``deck`` … ``rafter_top``;
    the ``purlins`` fill ``rafter_top`` … ``height``. ``deck`` is where a beam's
    top meets a rafter's underside.
    """

    width: float
    depth: float
    height: float
    post: float
    beam_depth: float
    rafter_width: float
    beam_bottom: float
    deck: float
    rafter_top: float
    posts: tuple[Rect, ...]
    beams: tuple[Rect, ...]
    rafters: tuple[Rect, ...]
    purlins: tuple[Rect, ...]

    @property
    def purlin_depth(self) -> float:
        return self.height - self.rafter_top


def layout(width: float, depth: float, height: float) -> PergolaLayout | None:
    """The layout of a pergola of these outer dimensions, or None when one of them
    is not a usable length (a non-finite or non-positive size)."""
    sizes = (width, depth, height)
    if not all(math.isfinite(size) and size > 0.0 for size in sizes):
        return None

    short = min(width, depth)
    post = min(POST_MAX_CM, POST_SHARE * short)
    inset = min(POST_INSET_MAX_CM, POST_INSET_SHARE * short)
    beam_depth = min(BEAM_DEPTH_MAX_CM, BEAM_DEPTH_SHARE * height)
    rafter_depth = min(RAFTER_DEPTH_MAX_CM, RAFTER_DEPTH_SHARE * height)
    purlin_depth = min(PURLIN_DEPTH_MAX_CM, PURLIN_DEPTH_SHARE * height)
    beam_width = min(BEAM_WIDTH_MAX_CM, BEAM_WIDTH_SHARE * post)
    rafter_width = min(RAFTER_WIDTH_MAX_CM, RAFTER_WIDTH_SHARE * width)
    purlin_width = min(PURLIN_WIDTH_MAX_CM, PURLIN_WIDTH_SHARE * width)
    deck = height - purlin_depth - rafter_depth
    beam_bottom = deck - beam_depth
    if post <= 0.0 or rafter_width <= 0.0 or beam_depth <= 0.0 or beam_bottom <= 0.0:
        return None

    post_x = width / 2.0 - inset - post / 2.0
    post_y = depth / 2.0 - inset - post / 2.0
    outer_x = width / 2.0 - BEAM_END_CLEAR_CM
    outer_y = depth / 2.0 - BEAM_END_CLEAR_CM

    posts = tuple(
        Rect(sx * post_x - post / 2.0, sy * post_y - post / 2.0,
             sx * post_x + post / 2.0, sy * post_y + post / 2.0)
        for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)
    )
    beams = tuple(
        Rect(-outer_x, sy * post_y - beam_width / 2.0,
             outer_x, sy * post_y + beam_width / 2.0)
        for sy in (-1.0, 1.0)
    ) + tuple(
        Rect(sx * post_x - beam_width / 2.0, -outer_y,
             sx * post_x + beam_width / 2.0, outer_y)
        for sx in (-1.0, 1.0)
    )

    span = width - 2.0 * min(RAFTER_INSET_MAX_CM, RAFTER_INSET_SHARE * width)
    xs = [-span / 2.0 + span * index / (RAFTER_COUNT - 1) for index in range(RAFTER_COUNT)]
    rafter_y = depth / 2.0 - RAFTER_END_CLEAR_CM
    rafters = tuple(
        Rect(x - rafter_width / 2.0, -rafter_y, x + rafter_width / 2.0, rafter_y)
        for x in xs
    )

    edge = min(PURLIN_EDGE_MAX_CM, PURLIN_EDGE_SHARE * depth)
    purlin_y = [
        -depth / 2.0 + edge + (depth - 2.0 * edge) * index / (PURLIN_COUNT + 1)
        for index in range(1, PURLIN_COUNT + 1)
    ]
    purlins = tuple(
        Rect(-outer_x, y - purlin_width / 2.0, outer_x, y + purlin_width / 2.0)
        for y in purlin_y
    )

    return PergolaLayout(
        width=width,
        depth=depth,
        height=height,
        post=post,
        beam_depth=beam_depth,
        rafter_width=rafter_width,
        beam_bottom=beam_bottom,
        deck=deck,
        rafter_top=height - purlin_depth,
        posts=posts,
        beams=beams,
        rafters=rafters,
        purlins=purlins,
    )


__all__ = [
    "BEAM_DEPTH_MAX_CM", "BEAM_DEPTH_SHARE", "BEAM_END_CLEAR_CM", "BEAM_WIDTH_MAX_CM",
    "BEAM_WIDTH_SHARE", "POST_INSET_MAX_CM", "POST_INSET_SHARE", "POST_MAX_CM", "POST_SHARE",
    "PURLIN_COUNT", "PURLIN_DEPTH_MAX_CM", "PURLIN_DEPTH_SHARE", "PURLIN_EDGE_MAX_CM",
    "PURLIN_EDGE_SHARE", "PURLIN_WIDTH_MAX_CM", "PURLIN_WIDTH_SHARE", "PergolaLayout",
    "RAFTER_COUNT", "RAFTER_DEPTH_MAX_CM", "RAFTER_DEPTH_SHARE", "RAFTER_END_CLEAR_CM",
    "RAFTER_INSET_MAX_CM", "RAFTER_INSET_SHARE", "RAFTER_WIDTH_MAX_CM", "RAFTER_WIDTH_SHARE",
    "Rect", "layout",
]
