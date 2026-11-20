"""Regular rectangular grid offsets shared by array and planting tools."""

from collections.abc import Iterator


def grid_offsets(
    rows: int, columns: int, row_step: float, column_step: float,
) -> Iterator[tuple[int, int, float, float]]:
    """Yield row, column and XY offset from the first centre in row order.

    The sign of each step sets its direction in the caller's coordinate frame.
    """
    for row in range(rows):
        for column in range(columns):
            yield row, column, column * column_step, row * row_step
