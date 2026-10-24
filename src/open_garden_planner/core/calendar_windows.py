"""Shared frost-relative calendar windows for tasks and 3D phenology (Qt-free)."""

from __future__ import annotations

import datetime
from collections.abc import Callable

CALENDAR_TASK_DEFS = (
    ("indoor_sow", "indoor_sow_start", "indoor_sow_end"),
    ("direct_sow", "direct_sow_start", "direct_sow_end"),
    ("transplant", "transplant_start", "transplant_end"),
    ("harvest", "harvest_start", "harvest_end"),
)


def calendar_windows(
    offset_of: Callable[[str], float | None], last_frost: datetime.date,
) -> list[tuple[str, datetime.date, datetime.date]]:
    """``(task_type, start, end)`` of every calendar window a species defines, for one
    last-frost date — THE frost-relative window arithmetic (``generate_calendar_tasks``
    and the 3D info card's sowing/harvest windows, Phase 17 L2.3, both call it).

    ``offset_of(field)`` answers a species' week offset (``indoor_sow_start`` …,
    ``harvest_end``; ``CALENDAR_TASK_DEFS``) or None; a window needs both ends.
    """
    windows: list[tuple[str, datetime.date, datetime.date]] = []
    for task_type, start_attr, end_attr in CALENDAR_TASK_DEFS:
        start_weeks, end_weeks = offset_of(start_attr), offset_of(end_attr)
        if start_weeks is None or end_weeks is None:
            continue
        windows.append((task_type, last_frost + datetime.timedelta(weeks=start_weeks),
                        last_frost + datetime.timedelta(weeks=end_weeks)))
    return windows

