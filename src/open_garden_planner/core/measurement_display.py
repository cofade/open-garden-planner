"""Locale-aware UI adapters to the pure units module.

Keep the active preference and Qt locale out of the conversion functions.
Agent API schemas and internal diagnostics use core.units explicitly instead.
"""

from open_garden_planner.core.i18n import (
    current_locale,
    format_decimal,
    format_trimmed,
    list_separator,
)
from open_garden_planner.core.unit_preference import active_unit_system
from open_garden_planner.core.units import (
    LengthStyle,
    UnitSystem,
    format_area,
    format_coordinates,
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
        # Shopping-list plant-size summaries previously used whole-number
        # Python formatting; the other fixed styles used Qt's rounding policy.
        number_format=None if style == LengthStyle.PLANT_SIZE else format_decimal,
        compact_format=format_trimmed,
    )


def area_text(cm2: float, system: UnitSystem | None = None) -> str:
    return format_area(
        cm2,
        active_unit_system() if system is None else system,
        decimal_mark=current_locale().decimalPoint(),
        number_format=format_decimal,
    )


def volume_text(litres: float, system: UnitSystem | None = None) -> str:
    return format_volume(
        litres,
        active_unit_system() if system is None else system,
        decimal_mark=current_locale().decimalPoint(),
        number_format=format_decimal,
    )


def coordinate_text(x_cm: float, y_cm: float, system: UnitSystem | None = None) -> str:
    return format_coordinates(
        x_cm,
        y_cm,
        active_unit_system() if system is None else system,
        decimal_mark=current_locale().decimalPoint(),
        separator=list_separator(),
        number_format=format_decimal,
    )
