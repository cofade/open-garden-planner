"""Plan snapshot for the 3D view (US-E6) — live items → plain data.

Runs on the GUI thread; the output contains no Qt object references (the
same snapshot-boundary discipline as the US-E4 worker). Footprints reuse
the US-E3 extraction (rotation/position are Qt's answer via ``mapToScene``)
so the 3D solids can never disagree with the 2D shadow footprints.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.object_height import effective_height_cm
from open_garden_planner.core.scene3d import Scene3DRecord, records_from_raw
from open_garden_planner.ui.canvas.sun_shadow_controller import _item_footprints

_FALLBACK_COLOR = (158, 158, 148, 255)


def _item_color_rgba(item: Any) -> tuple[int, int, int, int]:
    color = getattr(item, "fill_color", None)
    if isinstance(color, str):
        color = QColor(color)
    if isinstance(color, QColor) and color.isValid():
        return (color.red(), color.green(), color.blue(), 255)
    return _FALLBACK_COLOR


def collect_scene3d_records(
    scene: QGraphicsScene, at_date: date | None = None
) -> list[Scene3DRecord]:
    """Every visible item with a footprint → an engine-ready record.

    Items with an effective height become extruded prisms; the rest
    (lawns, paths, in-ground beds …) become thin ground decals, so the
    2D layout stays recognizable from above. ``at_date`` (US-E8) projects
    dated plants to their grown height and canopy spread — scrub the sim
    date and trees grow in 3D.
    """
    raw: list[dict] = []
    for item in scene.items():
        if not item.isVisible():
            continue
        object_type = getattr(item, "object_type", None)
        if object_type is None:
            continue
        metadata = getattr(item, "metadata", None)
        height = effective_height_cm(object_type, metadata, at_date=at_date)
        color = _item_color_rgba(item)
        name = str(getattr(item, "name", "") or object_type.name)
        for footprint in _item_footprints(item, at_date):
            if len(footprint) >= 3:
                raw.append(
                    {
                        "footprint": footprint,
                        "height_cm": height,
                        "color_rgba": color,
                        "name": name,
                    }
                )
    return records_from_raw(raw)
