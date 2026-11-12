"""Pure display/input conversions over the centimetre model (ADR-078).

The system and decimal mark are explicit; this module has no application state
or Qt dependency. Rounding here describes text, never stored geometry.
"""

from __future__ import annotations

import math
import re
from enum import Enum, StrEnum, auto


class UnitSystem(StrEnum):
    METRIC = "metric"
    IMPERIAL = "imperial"


class LengthStyle(Enum):
    AUTO = auto()
    METRES = auto()
    CENTIMETRES = auto()
    COORDINATE = auto()
    RULER = auto()
    SCALE_BAR = auto()
    PLANT_SIZE = auto()
    DEPTH = auto()
    FEET = auto()


CM_PER_INCH_NUM = 254
CM_PER_INCH_DEN = 100
LITRES_PER_US_QUART = 0.946352946
LITRES_PER_US_GALLON = 3.785411784
CM2_PER_SQ_FOOT = 929.0304
CM2_PER_SQ_INCH = 6.4516
CUBIC_METRES_PER_CUBIC_FOOT = 0.028316846592
SQUARE_METRES_PER_SQUARE_FOOT = 0.09290304


def cm_to_inches(cm: float) -> float:
    return cm * CM_PER_INCH_DEN / CM_PER_INCH_NUM


def inches_to_cm(inches: float) -> float:
    return inches * CM_PER_INCH_NUM / CM_PER_INCH_DEN


def _feet_inches(
    cm: float, den: int, *, depth: bool = False, omit_zero_inches: bool = False
) -> str:
    ticks = math.floor(abs(cm_to_inches(cm)) * den + 0.5)
    sign = "-" if cm < 0 and ticks else ""
    feet, rest = divmod(ticks, 12 * den) if not depth else (0, ticks)
    whole, numerator = divmod(rest, den)
    part = str(whole) if whole or not numerator else ""
    if numerator:
        gcd = math.gcd(numerator, den)
        part += (" " if part else "") + f"{numerator // gcd}/{den // gcd}"
    if feet:
        if omit_zero_inches and rest == 0:
            return f"{sign}{feet}'"
        return f"{sign}{feet}' {part}\""
    return f'{sign}{part}"' if ticks or not omit_zero_inches else "0"


def format_length(
    cm: float,
    system: UnitSystem = UnitSystem.METRIC,
    style: LengthStyle = LengthStyle.AUTO,
    *,
    fraction: int = 8,
    decimal_mark: str = ".",
) -> str:
    """Format centimetres. Fraction denominators are positive integers."""
    if fraction < 1:
        raise ValueError("fraction must be positive")
    if system == UnitSystem.IMPERIAL:
        if style == LengthStyle.FEET:
            feet = math.floor(abs(cm_to_inches(cm)) / 12 + 0.5)
            return f"{'-' if cm < 0 and feet else ''}{feet} ft"
        if style == LengthStyle.SCALE_BAR:
            inches = cm_to_inches(cm)
            result = (
                f"{round(inches, 3):g} in" if abs(inches) < 12 else f"{round(inches / 12, 3):g} ft"
            )
        else:
            return _feet_inches(
                cm,
                1 if style in (LengthStyle.PLANT_SIZE, LengthStyle.RULER) else fraction,
                depth=style == LengthStyle.DEPTH,
                omit_zero_inches=style == LengthStyle.RULER,
            )
    elif style == LengthStyle.METRES:
        result = f"{cm / 100.0:.2f} m"
    elif style == LengthStyle.CENTIMETRES:
        result = f"{cm:.1f} cm"
    elif style == LengthStyle.COORDINATE:
        result = f"{cm:.2f} cm"
    elif style == LengthStyle.RULER:
        result = f"{cm / 100:g}m" if abs(cm) >= 100 else f"{cm:g}"
    elif style == LengthStyle.SCALE_BAR:
        result = (
            f"{cm / 100000:g} km"
            if cm >= 100000
            else f"{cm / 100:g} m"
            if cm >= 100
            else f"{cm:g} cm"
        )
    elif style == LengthStyle.PLANT_SIZE:
        result = f"{cm:.0f} cm"
    elif style == LengthStyle.DEPTH:
        result = f"{cm} cm"
    elif style == LengthStyle.FEET:
        result = f"{cm / 100:.0f} m"
    else:
        result = f"{cm / 100:.2f} m" if cm >= 100 else f"{cm:.1f} cm"
    return result.replace(".", decimal_mark)


def format_area(
    cm2: float, system: UnitSystem = UnitSystem.METRIC, *, decimal_mark: str = "."
) -> str:
    if system == UnitSystem.IMPERIAL:
        result = (
            f"{cm2 / CM2_PER_SQ_FOOT:.2f} ft²"
            if cm2 >= CM2_PER_SQ_FOOT
            else f"{cm2 / CM2_PER_SQ_INCH:.1f} in²"
        )
    else:
        result = f"{cm2 / 10000:.2f} m²" if cm2 >= 10000 else f"{cm2:.1f} cm²"
    return result.replace(".", decimal_mark)


def format_volume(
    litres: float, system: UnitSystem = UnitSystem.METRIC, *, decimal_mark: str = "."
) -> str:
    if system == UnitSystem.IMPERIAL:
        result = (
            f"{litres / LITRES_PER_US_QUART:.1f} qt"
            if litres < LITRES_PER_US_GALLON
            else f"{litres / LITRES_PER_US_GALLON:.1f} gal"
        )
    else:
        result = f"{litres:.1f} L"
    return result.replace(".", decimal_mark)


_DECIMAL = r"(?:\d+(?:[.,]\d*)?|[.,]\d+)"
_AMOUNT = rf"(?:\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|{_DECIMAL})"
_LENGTH = re.compile(rf"([+-]?)\s*({_AMOUNT})\s*(mm|cm|m|inches|inch|in|feet|foot|ft|\"|')?", re.I)
_COMPOUND = re.compile(
    rf"([+-]?)\s*({_AMOUNT})\s*(?:feet|foot|ft|')\s*({_AMOUNT})\s*(?:inches|inch|in|\")?", re.I
)
_VOLUME = re.compile(
    rf"([+-]?)\s*({_AMOUNT})\s*(ml|litres?|liters?|l|quarts?|qt|gallons?|gal)?", re.I
)


def _amount(text: str) -> float:
    if "/" not in text:
        return float(text.replace(",", "."))
    left, denominator = text.split("/")
    whole_parts = left.split()
    denominator_value = int(denominator)
    if denominator_value == 0:
        raise ValueError("zero denominator")
    return (int(whole_parts[0]) if len(whole_parts) > 1 else 0) + int(
        whole_parts[-1]
    ) / denominator_value


def default_bare_unit_cm(system: UnitSystem) -> float:
    return 2.54 if system == UnitSystem.IMPERIAL else 1.0


def parse_length(
    text: str, system: UnitSystem = UnitSystem.METRIC, *, bare_unit_cm: float | None = None
) -> float:
    """Accept explicit metric or imperial units in either system; return cm."""
    compound = _COMPOUND.fullmatch(text.strip())
    if compound:
        sign, feet, inches = compound.groups()
        value = inches_to_cm(_amount(feet) * 12 + _amount(inches))
    else:
        match = _LENGTH.fullmatch(text.strip())
        if not match:
            raise ValueError("invalid length")
        sign, amount, unit = match.groups()
        number = _amount(amount)
        unit = (unit or "").lower()
        if unit in ("in", "inch", "inches", '"'):
            value = inches_to_cm(number)
        elif unit in ("ft", "foot", "feet", "'"):
            value = inches_to_cm(number * 12)
        else:
            factor = {"mm": 0.1, "cm": 1.0, "m": 100.0}.get(
                unit, default_bare_unit_cm(system) if bare_unit_cm is None else bare_unit_cm
            )
            value = number * factor
    value = -value if sign == "-" else value
    if not math.isfinite(value):
        raise ValueError("non-finite length")
    return value


def parse_volume(text: str, system: UnitSystem = UnitSystem.METRIC) -> float:
    match = _VOLUME.fullmatch(text.strip())
    if not match:
        raise ValueError("invalid volume")
    sign, amount, unit = match.groups()
    unit = (unit or ("gal" if system == UnitSystem.IMPERIAL else "l")).lower()
    factor = (
        0.001
        if unit == "ml"
        else LITRES_PER_US_QUART
        if unit.startswith(("q",))
        else LITRES_PER_US_GALLON
        if unit.startswith("g")
        else 1.0
    )
    value = _amount(amount) * factor * (-1 if sign == "-" else 1)
    if not math.isfinite(value):
        raise ValueError("non-finite volume")
    return value


def imperial_step_inches(metric_step_cm: float, style: LengthStyle) -> float:
    if style == LengthStyle.DEPTH:
        return 0.125
    if style == LengthStyle.FEET:
        return 12.0
    candidates = (0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 6.0, 12.0)
    if style == LengthStyle.PLANT_SIZE:
        candidates = tuple(c for c in candidates if c >= 1)
    target = cm_to_inches(max(metric_step_cm, 1e-12))
    return min(candidates, key=lambda c: abs(math.log(c / target)))


def nice_distances(system: UnitSystem) -> tuple[float, ...]:
    if system == UnitSystem.METRIC:
        return (
            1.0,
            2.0,
            5.0,
            10.0,
            20.0,
            50.0,
            100.0,
            200.0,
            500.0,
            1000.0,
            2000.0,
            5000.0,
            10000.0,
        )
    return tuple(inches_to_cm(x) for x in (1, 2, 3, 6, 12, 24, 60, 120, 300, 600, 1200, 3000, 6000))


def grid_size_cm(system: UnitSystem) -> float:
    return 30.48 if system == UnitSystem.IMPERIAL else 50.0


def nudge_fine_cm(system: UnitSystem) -> float:
    return 0.635 if system == UnitSystem.IMPERIAL else 1.0
