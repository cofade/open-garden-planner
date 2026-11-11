"""Display names for the harvest log's unit vocabulary (#863, #899).

A harvest record stores its unit as a stable, untranslated key (``"bunch"``,
``"kg"`` …): that string is the aggregation key in ``harvest_aggregation`` and
round-trips through the ``.ogp`` file. Translate it ONLY where a reader sees it,
never in the stored value — the rule of PF-I18-05.
"""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication

#: The units the dialog offers. A gardener may type another one; that custom
#: text is shown as typed in every language.
UNIT_CHOICES = ("kg", "g", "pcs", "bunch", "L")


def harvest_unit_label(unit: str) -> str:
    """*unit* in the UI language; an unknown/custom unit is returned unchanged.

    Literal ``translate`` calls (not a table lookup) so the source scanner sees
    every key and the catalog gate checks all registered locales.
    """
    if unit == "kg":
        return QCoreApplication.translate("HarvestUnits", "kg")
    if unit == "g":
        return QCoreApplication.translate("HarvestUnits", "g")
    if unit == "pcs":
        return QCoreApplication.translate("HarvestUnits", "pcs")
    if unit == "bunch":
        return QCoreApplication.translate("HarvestUnits", "bunch")
    if unit == "L":
        return QCoreApplication.translate("HarvestUnits", "L")
    return unit
