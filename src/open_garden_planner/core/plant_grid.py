"""Qt-free geometry for the Plant Grid draft (#1005).

The tool owns the scene transform, snapping, hit-testing and painting; this
module owns the arithmetic: where the cell centres are, where a resize edge
lands, and where each handle sits in the draft's local frame. Keeping it here
makes the geometry unit-testable without a QApplication, the same split
``core/grid_offsets.py`` already established for the array tool.

All coordinates are centimetres in the draft's own frame: the rectangle is
centred on ``(0, 0)`` and its angle is applied by the caller.
"""

from __future__ import annotations

from open_garden_planner.core.grid_offsets import grid_offsets

Point = tuple[float, float]
HandleKey = str | tuple[int, int]

#: Corner and edge handles, in painting order, as unit directions.
HANDLE_DIRECTIONS: tuple[tuple[int, int], ...] = (
    (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0),
)

#: The smallest extent a draft may have, in cm.
MIN_SPAN_CM = 2.0

#: The step a snapped resize rounds the per-cell spacing to, in cm. A whole
#: centimetre keeps the spacing readable and typable instead of leaving an
#: arbitrary fraction after one handle drag (#1003).
SNAP_SPACING_CM = 1.0


def first_cell_center(
    rows: int, columns: int, width: float, height: float,
) -> Point:
    """The top-left cell's centre in the draft's local frame."""
    return (
        -width / 2 + width / (2 * columns),
        -height / 2 + height / (2 * rows),
    )


def cell_centers(
    rows: int, columns: int, width: float, height: float,
) -> list[Point]:
    """Every cell centre, row-major, in the draft's local frame."""
    first_x, first_y = first_cell_center(rows, columns, width, height)
    return [
        (first_x + x, first_y + y)
        for _row, _column, x, y in grid_offsets(
            rows, columns, height / rows, width / columns,
        )
    ]


def resize_edges(
    span: float, direction: int, position: float, *, min_span: float = MIN_SPAN_CM,
) -> tuple[float, float]:
    """The new low/high edges of one axis while its handle is dragged.

    ``direction`` is the handle's sign on that axis (``-1`` low edge, ``+1``
    high edge, ``0`` no change). The opposite edge stays put and the moving
    edge cannot cross it closer than ``min_span``.
    """
    low, high = -span / 2, span / 2
    if direction < 0:
        low = min(position, high - min_span)
    elif direction > 0:
        high = max(position, low + min_span)
    return low, high


def snap_cell_span(
    span: float, cells: int, *, step: float = SNAP_SPACING_CM,
    min_span: float = MIN_SPAN_CM,
) -> float:
    """Round *span* to whole ``step``-cm cells, never below ``min_span``.

    The smallest legal value is one ``step`` per cell (so the spacing is never
    zero), raised to ``min_span`` when a tiny grid has more cells than that.
    """
    if cells <= 0 or step <= 0:
        return max(min_span, span)
    unit = cells * step
    snapped = round(span / unit) * unit
    return max(min_span, unit, snapped)


def handle_positions(
    width: float,
    height: float,
    *,
    rows: int,
    columns: int,
    diameter: float,
    rotation_offset: float,
) -> dict[HandleKey, Point]:
    """Every handle's position in the draft's local frame.

    ``rotation_offset`` is the screen-constant gap above the top edge,
    expressed in cm by the caller (it depends on the view's zoom).
    """
    handles: dict[HandleKey, Point] = {
        (x, y): (x * width / 2, y * height / 2) for x, y in HANDLE_DIRECTIONS
    }
    handles["rotate"] = (0.0, -height / 2 - rotation_offset)
    handles["move"] = (0.0, 0.0)
    first_x, first_y = first_cell_center(rows, columns, width, height)
    handles["diameter"] = (first_x + diameter / 2, first_y)
    return handles
