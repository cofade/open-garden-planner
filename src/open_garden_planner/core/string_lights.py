"""A string of lights is a LINE (Phase 17 L5.4, #389; ADR-070 addendum after the
owner's manual test).

It is drawn like a fence: every point of the line is a post, and between two posts
the wire hangs with a bulb every ``BULB_SPACING_CM`` along the whole string. A
string has no width — the rectangle it was first drawn as gave it one, and its 2D
picture was stretched across it.

This is the ONE layout of a string. The canvas draws its posts and bulbs from it
(``ui/canvas/items/polyline_item.py``), the 3D builder builds them from it
(``core/scene3d/builders/lights.py``), and the lights of the night glow where its
bulbs hang (``core/scene3d/lights.py``): a bulb is never drawn in 2D where 3D has
none, or the other way round.

The bulbs are spaced along the WIRE, not per span: a real string's bulbs are evenly
spaced on its cable wherever the posts stand. ``bulb_count`` bulbs at the arc
lengths ``(k + ½) · L / n`` of a string of length ``L`` — never more than
``MAX_BULBS``, however long the string (a 60 m string would otherwise hang 150).

Pure: floats in, floats out. No Qt, no numpy.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

#: A bulb every this many centimetres along the wire.
BULB_SPACING_CM: Final = 40.0
#: The most bulbs one string carries (a long string spaces them further apart).
MAX_BULBS: Final = 120
#: Two points of the line closer than this are one post.
MERGE_CM: Final = 1.0
#: The most posts one string stands on. A line with more points (a real string has a
#: few dozen; a crafted plan can hold millions — the security review of #389) keeps
#: ``MAX_POSTS`` of them, evenly chosen, its first and last among them, and the wire runs
#: straight between them. This bounds the canvas's picture, the 3D model and the lights.
MAX_POSTS: Final = 512

Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Span:
    """The wire between two posts: their indices in ``Layout.posts`` and its length."""

    a: int
    b: int
    length_cm: float


@dataclass(frozen=True, slots=True)
class Bulb:
    """A bulb on span ``span`` at ``share`` of its length (0 at post ``a``)."""

    span: int
    share: float


@dataclass(frozen=True, slots=True)
class Layout:
    """Where a string's posts stand and where its bulbs hang, in the line's own
    coordinates (cm)."""

    posts: tuple[Point, ...]
    spans: tuple[Span, ...]
    bulbs: tuple[Bulb, ...]

    @property
    def length_cm(self) -> float:
        return sum(span.length_cm for span in self.spans)

    def bulb_xy(self, bulb: Bulb) -> Point:
        """Where ``bulb`` hangs, seen from above."""
        span = self.spans[bulb.span]
        (ax, ay), (bx, by) = self.posts[span.a], self.posts[span.b]
        return (ax + (bx - ax) * bulb.share, ay + (by - ay) * bulb.share)

    def bulbs_xy(self) -> tuple[Point, ...]:
        return tuple(self.bulb_xy(bulb) for bulb in self.bulbs)


EMPTY: Final = Layout((), (), ())


def _posts(points: Sequence[Point]) -> tuple[list[Point], bool]:
    """The posts of a line: its finite points, a point within ``MERGE_CM`` of the
    previous one merged into it, at most ``MAX_POSTS`` of them; and whether the line
    closes on itself (its last point is its first — that post is then not repeated)."""
    posts: list[Point] = []
    for x, y in points:
        x, y = float(x), float(y)
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        if posts and math.hypot(x - posts[-1][0], y - posts[-1][1]) < MERGE_CM:
            continue
        posts.append((x, y))
    closed = (len(posts) > 2
              and math.hypot(posts[0][0] - posts[-1][0], posts[0][1] - posts[-1][1]) < MERGE_CM)
    if closed:
        posts.pop()
    if len(posts) > MAX_POSTS:
        last = len(posts) - 1
        posts = [posts[round(i * last / (MAX_POSTS - 1))] for i in range(MAX_POSTS)]
    return posts, closed


def bulb_count(length_cm: float) -> int:
    """How many bulbs a string of ``length_cm`` carries: one every
    ``BULB_SPACING_CM``, at least one, at most ``MAX_BULBS``."""
    if not math.isfinite(length_cm) or length_cm <= 0.0:
        return 0
    return max(1, min(MAX_BULBS, round(length_cm / BULB_SPACING_CM)))


def layout(points: Sequence[Point]) -> Layout:
    """The posts, spans and bulbs of a string drawn through ``points`` (module
    docstring). A line of fewer than two distinct points has no wire: its posts, if
    any, and no bulbs."""
    posts, closed = _posts(points)
    if len(posts) < 2:
        return Layout(tuple(posts), (), ())
    pairs = list(zip(range(len(posts) - 1), range(1, len(posts)), strict=True))
    if closed:
        pairs.append((len(posts) - 1, 0))
    spans = tuple(Span(a, b, math.hypot(posts[b][0] - posts[a][0], posts[b][1] - posts[a][1]))
                  for a, b in pairs)
    total = sum(span.length_cm for span in spans)
    count = bulb_count(total)
    bulbs: list[Bulb] = []
    index, start = 0, 0.0   # the span the walk is on, and the arc length where it starts
    for k in range(count):
        at = (k + 0.5) * total / count
        while index < len(spans) - 1 and at > start + spans[index].length_cm:
            start += spans[index].length_cm
            index += 1
        length = spans[index].length_cm
        share = min(1.0, max(0.0, (at - start) / length)) if length > 0.0 else 0.5
        bulbs.append(Bulb(index, share))
    return Layout(tuple(posts), spans, tuple(bulbs))
