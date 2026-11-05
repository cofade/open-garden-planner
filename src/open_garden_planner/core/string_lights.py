"""A string of lights is a LINE (Phase 17 L5.4, #389; ADR-070 addendum after the
owner's manual test).

It is drawn like a fence: a post at least ``MIN_POST_GAP_CM`` apart along the line,
and between two posts the wire hangs with a bulb every ``BULB_SPACING_CM`` along the
whole string. A string has no width — the rectangle it was first drawn as gave it one,
and its 2D picture was stretched across it.

This is the ONE layout of a string. The canvas draws its posts and bulbs from it
(``ui/canvas/items/polyline_item.py``), the 3D builder builds them from it
(``core/scene3d/builders/lights.py``), and the lights of the night glow where its
bulbs hang (``core/scene3d/lights.py``): a bulb is never drawn in 2D where 3D has
none, or the other way round.

The bulbs are spaced along the WIRE, not per span: a real string's bulbs are evenly
spaced on its cable wherever the posts stand. ``bulb_count`` bulbs at the arc
lengths ``(k + ½) · L / n`` of a string of length ``L`` — never more than
``MAX_BULBS_PER_STRING``, however long the string (a 60 m string would otherwise hang 150).
A bulb is kept ``POST_CLEAR_CM`` from the posts of its span: an arc length that falls on
a post (the middle post of every symmetric string with an odd count) hung the ball inside
the post (3D review of the line). It moves at most that far, and along its own span it
keeps ``OTHER_POST_CLEAR_CM`` from every FOREIGN post (a line that doubles back can put
one in its way). A span shorter than two clearances keeps its middle: no share can clear
both of its own posts, so moving it would only make it worse.

A span whose straight chord would cut the drawn line by more than
``MAX_CHORD_DEVIATION_CM`` keeps the arc's own points, even where that means a span
shorter than the gap. The deviation promise applies to the kept points: a line above
``MAX_POSTS`` is thinned first, and the wire follows those points.

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
MAX_BULBS_PER_STRING: Final = 120
#: Two points of the line closer than this are one post.
MERGE_CM: Final = 1.0
#: A point becomes a post only this far along the line from the last kept post
#: (#709): a filleted corner bakes its arc as a dense run of 2 cm points, and a post
#: at every one turned the corner into a 2.5 m wall of overlapping posts. The wire
#: runs straight between posts, so an arc becomes chords (a 2 cm sagitta for a 40 cm
#: chord at r 100 cm). The line's last point always stays.
MIN_POST_GAP_CM: Final = 40.0
#: A span may be shorter than the gap when its chord would otherwise deviate from the
#: drawn line by more than this: the terminal point of a short fillet arc stays a post
#: (a 39.27 cm span at r 25) instead of being replaced by a 2.2 m chord across the
#: corner (#709, 3D review). A 40 cm chord at r 100 deviates ~2 cm, inside this.
MAX_CHORD_DEVIATION_CM: Final = 2.5
#: A bulb hangs at least this far from either post of its span (a 2.6 cm ball beside a
#: 4 cm post) — at the middle of a span shorter than twice it.
POST_CLEAR_CM: Final = 6.0
#: A bulb also keeps this far from every post of ANOTHER span: a self-crossing line
#: can land a bulb on a foreign post (#709). It is ``POST_CLEAR_CM`` plus the 3D
#: bulb's radius (2.6 cm, ``builders.lights.BULB_RADIUS_CM``) — a drift guard pins
#: the two (``test_post_clearance_exceeds_post_diagonal_plus_bulb_radius``).
OTHER_POST_CLEAR_CM: Final = 8.6
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

    @property
    def is_closed(self) -> bool:
        """Whether the line closes on itself (its last post spans back to the first)."""
        return bool(self.posts) and len(self.spans) == len(self.posts)

    def bulb_xy(self, bulb: Bulb) -> Point:
        """Where ``bulb`` hangs, seen from above."""
        span = self.spans[bulb.span]
        (ax, ay), (bx, by) = self.posts[span.a], self.posts[span.b]
        return (ax + (bx - ax) * bulb.share, ay + (by - ay) * bulb.share)

    def bulbs_xy(self) -> tuple[Point, ...]:
        return tuple(self.bulb_xy(bulb) for bulb in self.bulbs)


EMPTY: Final = Layout((), (), ())


def _chord_distance(point: Point, start: Point, end: Point) -> float:
    """Distance from ``point`` to the segment ``start``–``end``."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    share = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
                       / length_sq))
    return math.hypot(point[0] - (start[0] + dx * share), point[1] - (start[1] + dy * share))


def _refine_chords(posts: list[Point], kept: list[int], closed: bool) -> list[Point]:
    """Add the point of a span whose chord would cut the drawn line by too much (#709).

    The gap is a straight wire between posts. A short fillet arc has its far tangent
    only 39 cm after the near one, so the strict gap would drop it and stretch the wire
    2.2 m across the corner; the 3D reviewer measured the chord 22 cm off the plan.
    Recursively split any span whose intermediate points deviate more than
    ``MAX_CHORD_DEVIATION_CM``, so every wire follows the drawn line within it."""
    count = len(posts)
    order = [*kept, kept[0] + count] if closed else kept
    out = [order[0]]

    def emit(start: int, end: int) -> None:
        worst = 0.0
        at = -1
        for index in range(start + 1, end):
            distance = _chord_distance(posts[index % count], posts[start % count],
                                       posts[end % count])
            if distance > worst:
                worst, at = distance, index
        if at >= 0 and worst > MAX_CHORD_DEVIATION_CM:
            emit(start, at)
            emit(at, end)
        else:
            out.append(end)

    for start, end in zip(order, order[1:], strict=False):
        emit(start, end)
    if closed:
        out.pop()                       # the closing span repeats the first post
    return [posts[index % count] for index in out]


def _keep_post_gap(posts: list[Point], closed: bool) -> list[Point]:
    """The points that stand a post apart by ``MIN_POST_GAP_CM`` *along the line*.

    ``_posts`` has already merged near-duplicates and thinned a huge line to
    ``MAX_POSTS``; this keeps the first point, then every point at least the gap
    further along the wire. For an OPEN line the drawn last point always stays: when
    it is nearer than the gap to the previous post, it replaces that post (unless that
    post is the first). For a CLOSED line the closing span counts too: a last post
    nearer than the gap to the first is dropped, never the first. A line shorter than
    the gap keeps its first and last point — no placement can honour the gap on it.
    Every kept span is then refined by ``_refine_chords``: a wire never cuts a drawn
    arc by more than ``MAX_CHORD_DEVIATION_CM``, even when that needs a shorter span."""
    if len(posts) < 3:
        return posts
    steps = [0.0]
    for (ax, ay), (bx, by) in zip(posts, posts[1:], strict=False):
        steps.append(steps[-1] + math.hypot(bx - ax, by - ay))
    total = steps[-1]
    if closed:
        total += math.hypot(posts[0][0] - posts[-1][0], posts[0][1] - posts[-1][1])
    kept = [0]
    for index in range(1, len(posts)):
        if steps[index] - steps[kept[-1]] >= MIN_POST_GAP_CM:
            kept.append(index)
    if closed:
        while len(kept) > 2 and total - steps[kept[-1]] < MIN_POST_GAP_CM:
            kept.pop()
    else:
        last = len(posts) - 1
        if kept[-1] != last:
            if len(kept) == 1:
                kept.append(last)
            else:
                kept[-1] = last
    return _refine_chords(posts, kept, closed)


def _posts(points: Sequence[Point]) -> tuple[list[Point], bool]:
    """The posts of a line: its finite points, a point within ``MERGE_CM`` of the
    previous one merged into it, at most ``MAX_POSTS`` of them and at least
    ``MIN_POST_GAP_CM`` apart along the line; and whether the line closes on itself
    (its last point is its first — that post is then not repeated)."""
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
    return _keep_post_gap(posts, closed), closed


def bulb_count(length_cm: float) -> int:
    """How many bulbs a string of ``length_cm`` carries: one every
    ``BULB_SPACING_CM``, at least one, at most ``MAX_BULBS_PER_STRING``."""
    if not math.isfinite(length_cm) or length_cm <= 0.0:
        return 0
    return max(1, min(MAX_BULBS_PER_STRING, round(length_cm / BULB_SPACING_CM)))


def _clear_share(span: Span, posts: Sequence[Point], share: float) -> float:
    """``share`` moved along ``span`` until it is clear of every FOREIGN post (#709).

    The base share keeps ``POST_CLEAR_CM`` from the span's own posts when the span is
    long enough to allow it. A line that doubles back or crosses itself can stand
    another span's post in the bulb's way; the forbidden shares are the intervals where
    that post lies within ``OTHER_POST_CLEAR_CM``, and the nearest allowed share to the
    base is taken. A span shorter than two clearances keeps the base: moving it to
    clear a foreign post would push it into its own post. When no share is clear the
    base also stays: the layout cannot do better, and the picture still draws the bulb
    above the post.
    """
    if len(posts) < 3 or span.length_cm <= 0.0:
        return share
    length = span.length_cm
    # A span this short has no share that clears both its own posts: the ball and a
    # post cannot fit (a 7 cm span leaves at most 3.5 cm, under the 5.4 cm reach).
    # Moving it to clear a foreign post would only push it into its own post
    # (#709 review); keep the base, which is the best available, and let the 2D
    # painter's bulb-over-post order keep it visible.
    if length <= 2.0 * POST_CLEAR_CM:
        return share
    (ax, ay), (bx, by) = posts[span.a], posts[span.b]
    ux, uy = (bx - ax) / length, (by - ay) / length
    low = POST_CLEAR_CM / length
    high = 1.0 - low
    forbidden: list[tuple[float, float]] = []
    for index, (px, py) in enumerate(posts):
        if index in (span.a, span.b):
            continue
        along = (px - ax) * ux + (py - ay) * uy
        across = abs((px - ax) * uy - (py - ay) * ux)
        if across >= OTHER_POST_CLEAR_CM:
            continue
        reach = math.sqrt(OTHER_POST_CLEAR_CM * OTHER_POST_CLEAR_CM - across * across)
        start = max(low, (along - reach) / length)
        stop = min(high, (along + reach) / length)
        if stop > start:
            forbidden.append((start, stop))
    if not forbidden:
        return min(high, max(low, share))
    forbidden.sort()
    merged: list[tuple[float, float]] = []
    for start, stop in forbidden:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    allowed: list[tuple[float, float]] = []
    cursor = low
    for start, stop in merged:
        if start > cursor:
            allowed.append((cursor, start))
        cursor = max(cursor, stop)
    if cursor < high:
        allowed.append((cursor, high))
    if not allowed:
        return min(high, max(low, share))
    for start, stop in allowed:
        if start <= share <= stop:
            return share
    return min((start if abs(start - share) <= abs(stop - share) else stop
                for start, stop in allowed), key=lambda value: abs(value - share))


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
        if length > 2.0 * POST_CLEAR_CM:
            clear = POST_CLEAR_CM / length
            share = min(1.0 - clear, max(clear, (at - start) / length))
        else:
            share = 0.5
        bulbs.append(Bulb(index, share))
    cleared = tuple(Bulb(bulb.span, _clear_share(spans[bulb.span], posts, bulb.share))
                    for bulb in bulbs)
    return Layout(tuple(posts), spans, cleared)
