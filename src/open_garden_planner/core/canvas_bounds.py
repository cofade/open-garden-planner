"""Canvas clamping math — the one shared rule for keeping objects on-plan.

The GUI has clamped objects to the canvas at five sites for a long time:
interactive drag, arrow-key nudge, the properties panel's numeric X/Y, the
mirror tool, and the resize handle. The Agent API did **not** clamp, so an agent
could create or move an object entirely off-plan where it became invisible and
un-deletable through the GUI (issue #380).

Rather than add a sixth copy of the rule, this module holds it once, Qt-free,
over plain tuples. ``CanvasView._clamp_items_to_canvas`` /
``_clamp_delta_to_canvas`` call it, and so does the agent write path — so the two
cannot drift.

A rect is ``(left, top, right, bottom)`` in scene cm. A canvas spans
``(0, 0)`` to ``(width, height)``.
"""

from __future__ import annotations

Rect = tuple[float, float, float, float]


def _union(rects: list[Rect]) -> Rect:
    """The bounding rect of every rect in *rects*."""
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    right = max(r[2] for r in rects)
    bottom = max(r[3] for r in rects)
    return (left, top, right, bottom)


def clamp_shift_within_canvas(
    rects: list[Rect], canvas_width: float, canvas_height: float
) -> tuple[float, float]:
    """Return ``(dx, dy)`` to move the union of *rects* minimally inside the canvas.

    The edge selection mirrors ``CanvasView._clamp_items_to_canvas`` exactly: an
    overflow on the left/top wins over one on the right/bottom, and a rect larger
    than the canvas aligns its left/top edge to 0. An empty list returns
    ``(0.0, 0.0)``.
    """
    if not rects:
        return 0.0, 0.0
    left, top, right, bottom = _union(rects)

    dx = 0.0
    dy = 0.0
    if left < 0.0:
        dx = -left
    elif right > canvas_width:
        dx = canvas_width - right

    if top < 0.0:
        dy = -top
    elif bottom > canvas_height:
        dy = canvas_height - bottom

    return dx, dy


def clamp_delta_within_canvas(
    rects: list[Rect],
    dx: float,
    dy: float,
    canvas_width: float,
    canvas_height: float,
) -> tuple[float, float]:
    """Restrict a proposed shift so the union of *rects* stays inside the canvas.

    Mirrors ``CanvasView._clamp_delta_to_canvas``. An empty list returns the
    proposed delta unchanged.
    """
    if not rects:
        return dx, dy
    left, top, right, bottom = _union(rects)

    moved_left = left + dx
    moved_right = right + dx
    moved_top = top + dy
    moved_bottom = bottom + dy

    out_dx = dx
    out_dy = dy
    if moved_left < 0.0:
        out_dx = -left
    elif moved_right > canvas_width:
        out_dx = canvas_width - right

    if moved_top < 0.0:
        out_dy = -top
    elif moved_bottom > canvas_height:
        out_dy = canvas_height - bottom

    return out_dx, out_dy


def rect_intersects_canvas(
    rect: Rect, canvas_width: float, canvas_height: float
) -> bool:
    """True when *rect* overlaps the canvas rect at all.

    An empty/zero-size canvas (width or height <= 0) returns True so a
    degenerate plan does not flag every object as off-plan.
    """
    if canvas_width <= 0 or canvas_height <= 0:
        return True
    left, top, right, bottom = rect
    return not (right <= 0.0 or left >= canvas_width or bottom <= 0.0 or top >= canvas_height)
