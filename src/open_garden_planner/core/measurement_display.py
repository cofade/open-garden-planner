"""Locale-aware UI adapters to the pure units module.

Keep the active preference and Qt locale out of the conversion functions.
Agent API schemas and internal diagnostics use core.units explicitly instead.
"""

from open_garden_planner.core.i18n import current_locale
from open_garden_planner.core.unit_preference import active_unit_system
from open_garden_planner.core.units import (
    LengthStyle,
    UnitSystem,
    format_area,
    format_length,
    format_volume,
)


def length_text(
    cm: float, system: UnitSystem | None = None, style: LengthStyle = LengthStyle.AUTO
) -> str:
    return format_length(
        cm,
        active_unit_system() if system is None else system,
        style,
        decimal_mark=current_locale().decimalPoint(),
    )


def area_text(cm2: float, system: UnitSystem | None = None) -> str:
    return format_area(
        cm2,
        active_unit_system() if system is None else system,
        decimal_mark=current_locale().decimalPoint(),
    )


def volume_text(litres: float, system: UnitSystem | None = None) -> str:
    return format_volume(
        litres,
        active_unit_system() if system is None else system,
        decimal_mark=current_locale().decimalPoint(),
    )
