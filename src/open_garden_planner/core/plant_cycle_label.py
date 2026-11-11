"""The translated label of a plant's life cycle (#869).

One vocabulary used by the Plant Details panel, the custom-plant table, the
plant search and the PDF report's plant list. The PDF used to print the canvas
object type ("Perennial") for every vegetable, because the gallery creates all
plants as ``ObjectType.PERENNIAL``; the species' own ``cycle`` is the truth.
"""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication

from open_garden_planner.models.plant_data import PlantCycle


def plant_cycle_label(cycle: object, *, unknown: str = "") -> str:
    """*cycle* in the UI language; ``unknown`` decides what an absent cycle says.

    Accepts a :class:`PlantCycle` or its stored string value. A value that is
    not in the vocabulary is shown as written (a hand-edited plan must not turn
    into an empty cell).
    """
    value = getattr(cycle, "value", cycle)
    if value == PlantCycle.ANNUAL.value:
        return QCoreApplication.translate("PlantCycle", "Annual")
    if value == PlantCycle.BIENNIAL.value:
        return QCoreApplication.translate("PlantCycle", "Biennial")
    if value == PlantCycle.PERENNIAL.value:
        return QCoreApplication.translate("PlantCycle", "Perennial")
    if value in (None, "", PlantCycle.UNKNOWN.value):
        return unknown
    return str(value)
