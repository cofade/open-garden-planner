"""Seasonal phenology evaluator for 3D plants (Phase 17 L3.5, #387).

Computes shader/material values (`leaf_density`, `autumn_color`, `bloom`,
`ripeness`, `snow`, plus linear/sRGB foliage and accent tints) for any plant on
a given `plan_date` and `latitude_deg`:

- **Hemisphere shift**: Southern Hemisphere latitudes (`latitude_deg < 0`) shift
  the seasonal cycle by 6 months (`+182.5` days / `+6` calendar months), so
  deciduous trees are bare in January at `52° N` and in July at `35° S`.
- **Evergreens never bare**: When `traits.deciduous` is `False`, `leaf_density`
  is `1.0` and `autumn_color` is `0.0` on every day of the year in both
  hemispheres.
- **Existence boundary (`#315`)**: Whether a plant exists at all on `plan_date`
  is decided exclusively by `#315` (`core.plan_timeline`); this module only
  evaluates seasonal appearance for existing plants and never hides or removes
  a plant item.
- **60 fps date scrub**: Scrubbing 300 plants across dates updates shader/material
  values without rebuilding meshes (`<= 16 ms` budget).

Qt-free: standard library + NumPy + `core.plant_art` + `core.scene3d` only.
"""

from __future__ import annotations

import datetime
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from .calendar_windows import calendar_windows
from .frost_dates import parse_frost
from .plant_art import (
    PALETTES,
    PLANT_KINDS,
    SpriteRef,
    Traits3D,
    recipe_for,
    traits_for,
)
from .scene3d import Record, srgb_to_linear
from .scene3d.builders.plants import plant_sprite

#: Default temperate Northern-Hemisphere latitude when a plan has no coordinates set.
DEFAULT_LATITUDE_DEG: Final[float] = 52.0

#: Snow highlight colour in linear light (shaded below 1.0 so low winter sun never clips).
SNOW_LINEAR_RGB: Final[tuple[float, float, float]] = (0.68, 0.71, 0.75)


def _linear_channel_to_srgb8(val: float) -> int:
    c = min(max(float(val), 0.0), 1.0)
    srgb = c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055
    return int(min(max(round(srgb * 255.0), 0), 255))


def _linear_to_srgb8(rgba: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return (
        _linear_channel_to_srgb8(rgba[0]),
        _linear_channel_to_srgb8(rgba[1]),
        _linear_channel_to_srgb8(rgba[2]),
        int(min(max(round(float(rgba[3]) * 255.0), 0), 255)),
    )


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 == edge0:
        return 1.0 if x >= edge1 else 0.0
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def seasonal_day_of_year(plan_date: datetime.date, latitude_deg: float = DEFAULT_LATITUDE_DEG) -> float:
    """Return 0-based seasonal day-of-year in `[0.0, 365.0)`, shifted by 6 months when `latitude_deg < 0`."""
    doy0 = float(plan_date.timetuple().tm_yday - 1)
    # Normalise leap years onto a 365-day seasonal circle
    is_leap = (plan_date.year % 4 == 0 and plan_date.year % 100 != 0) or (plan_date.year % 400 == 0)
    if is_leap:
        doy0 = doy0 * (365.0 / 366.0)
    if float(latitude_deg) < 0.0:
        doy0 = (doy0 + 182.5) % 365.0
    return doy0


def seasonal_month(plan_date: datetime.date, latitude_deg: float = DEFAULT_LATITUDE_DEG) -> int:
    """Return seasonal month `(1..12)`, shifted by 6 months in the Southern Hemisphere (`latitude_deg < 0`)."""
    m = int(plan_date.month)
    if float(latitude_deg) < 0.0:
        return ((m - 1 + 6) % 12) + 1
    return m


@lru_cache(maxsize=64)
def _palette_autumn_multiplier(summer_pal_name: str, autumn_pal_name: str) -> tuple[float, float, float]:
    """Compute linear-light RGB multiplier that shifts `summer_pal_name` toward `autumn_pal_name`."""
    s_pal = PALETTES.get(summer_pal_name, PALETTES["fresh"])
    a_pal = PALETTES.get(autumn_pal_name, PALETTES["autumn"])

    sr0, sg0, sb0 = srgb_to_linear(s_pal["t0"])[:3]
    sr1, sg1, sb1 = srgb_to_linear(s_pal["b1"])[:3]
    ar0, ag0, ab0 = srgb_to_linear(a_pal["t0"])[:3]
    ar1, ag1, ab1 = srgb_to_linear(a_pal["b1"])[:3]

    s_mean = (0.5 * (sr0 + sr1), 0.5 * (sg0 + sg1), 0.5 * (sb0 + sb1))
    a_mean = (0.5 * (ar0 + ar1), 0.5 * (ag0 + ag1), 0.5 * (ab0 + ab1))

    if summer_pal_name == autumn_pal_name:
        # Warm golden-amber boost when the base palette is already `autumn` or `redleaf`
        return (1.15, 0.86, 0.62)

    mr = min(max(a_mean[0] / max(s_mean[0], 0.03), 0.35), 2.10)
    mg = min(max(a_mean[1] / max(s_mean[1], 0.03), 0.35), 1.60)
    mb = min(max(a_mean[2] / max(s_mean[2], 0.03), 0.25), 1.35)
    return (float(mr), float(mg), float(mb))


@dataclass(frozen=True, slots=True)
class PhenologyState:
    """Evaluated seasonal shader and material parameters for one plant on a date."""

    leaf_density: float
    autumn_color: float
    autumn_tint_linear: tuple[float, float, float]
    bloom: float
    ripeness: float
    snow: float
    foliage_tint_linear: tuple[float, float, float]
    foliage_tint_rgba: tuple[int, int, int, int]
    accent_opacity: float
    accent_tint_linear: tuple[float, float, float]
    accent_tint_rgba: tuple[int, int, int, int]

    @property
    def autumn_mix(self) -> float:
        """Alias for `autumn_color` (`0.0 .. 1.0`)."""
        return self.autumn_color

    @property
    def foliage_opacity(self) -> float:
        """Screen-door opacity (`uOpacity` / `fade`) for `PART_FOLIAGE`."""
        return self.leaf_density

    def shader_values(self) -> dict[str, float | tuple[float, float, float]]:
        """Return shader uniform dictionary for `PART_FOLIAGE` and `PART_ACCENTS`."""
        return {
            "leaf_density": self.leaf_density,
            "autumn_color": self.autumn_color,
            "autumn_tint_linear": self.autumn_tint_linear,
            "bloom": self.bloom,
            "ripeness": self.ripeness,
            "snow": self.snow,
            "uOpacity": self.leaf_density,
            "uTint": self.foliage_tint_linear,
            "accent_uOpacity": self.accent_opacity,
            "accent_uTint": self.accent_tint_linear,
        }


def _month_window_weight(
    plan_date: datetime.date,
    latitude_deg: float,
    months_nh: tuple[int, ...],
    *,
    ramp_from: float = 1.0,
) -> float:
    """Evaluate `[0.0 .. 1.0]` weight for `plan_date` against Northern-Hemisphere `months_nh`."""
    if not months_nh:
        return 0.0
    s_month = seasonal_month(plan_date, latitude_deg)
    if s_month not in months_nh:
        return 0.0
    if len(months_nh) == 1 or ramp_from >= 1.0:
        return 1.0
    idx = months_nh.index(s_month)
    day_frac = min(max((plan_date.day - 1) / 30.0, 0.0), 1.0)
    progress = (idx + day_frac) / max(len(months_nh), 1)
    return float(min(max(ramp_from + (1.0 - ramp_from) * progress, 0.0), 1.0))


def _frost_window(frost_dates: Mapping[str, object] | None) -> tuple[str | None, str | None]:
    if not frost_dates:
        return None, None
    spring = frost_dates.get("last_spring_frost")
    fall = frost_dates.get("first_fall_frost")
    return (spring if isinstance(spring, str) else None, fall if isinstance(fall, str) else None)


def _record_harvest(record: Record) -> tuple[float, float] | None:
    values = [record.params.get(key) for key in ("harvest_start", "harvest_end")]
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
           for v in values):
        return float(values[0]), float(values[1])  # type: ignore[arg-type]
    return None


def _inside_frost_free_season(day: datetime.date, spring: str | None, fall: str | None) -> bool:
    start, end = parse_frost(spring, day.year), parse_frost(fall, day.year)
    if start is None or end is None:
        return True  # Missing/invalid inputs cannot make an analytical seasonal claim.
    if start <= end:
        return start <= day <= end
    return day >= start or day <= end


@lru_cache(maxsize=4096)
def _harvest_ripeness(day: datetime.date, weeks: tuple[float, float], frost_mmdd: str) -> float:
    # Derive every possible anchor year from the offsets, including multi-year
    # establishment windows and those that cross New Year (task generator #414).
    lo, hi = weeks
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
        return 0.0
    # Recorded week offsets can be arbitrarily large. Outside datetime's range
    # no representable frost anchor can produce a window for this date.
    earliest = day.toordinal() - math.ceil(hi * 7)
    latest = day.toordinal() - math.floor(lo * 7)
    if latest < 1 or earliest > datetime.date.max.toordinal():
        return 0.0
    first = datetime.date.fromordinal(max(1, earliest)).year
    last = datetime.date.fromordinal(min(datetime.date.max.toordinal(), latest)).year
    offsets = {"harvest_start": lo, "harvest_end": hi}
    for year in range(first, last + 1):
        frost = parse_frost(frost_mmdd, year)
        if frost is None:
            continue
        try:
            windows = calendar_windows(offsets.get, frost)
        except OverflowError:
            continue
        for _, start, end in windows:
            if start <= day <= end:
                share = (day - start).days / max((end - start).days, 1)
                return 0.55 + 0.45 * share
    return 0.0


@lru_cache(maxsize=4096)
def _evaluate_cached(
    sprite: SpriteRef,
    plan_date: datetime.date,
    lat_q: float,
    last_frost: datetime.date | None,
    snow_q: float | None,
    frost_window: tuple[str | None, str | None] = (None, None),
    harvest_override: tuple[float, float] | None = None,
) -> PhenologyState:
    traits = traits_for(sprite)
    recipe = recipe_for(sprite)
    doy = seasonal_day_of_year(plan_date, lat_q)
    s_month = seasonal_month(plan_date, lat_q)

    # 1. Leaf density & autumn colour (Evergreens never bare; deciduous bare in winter)
    if not traits.deciduous:
        leaf_density = 1.0
        autumn_color = 0.0
    else:
        # Winter bare: Dec 1 (doy >= 334) through end of Feb (doy < 60), covering Jan (52 N) & Jul (35 S)
        if s_month in (12, 1, 2) or doy < 60.0 or doy >= 334.0:
            leaf_density = 0.0
        elif doy < 115.0:
            # Spring budburst ramp (March - mid April)
            leaf_density = _smoothstep(60.0, 115.0, doy)
        elif doy <= 285.0:
            # Full summer canopy (late April - mid October)
            leaf_density = 1.0
        else:
            # Autumn leaf drop (mid October - November 30)
            leaf_density = 1.0 - _smoothstep(285.0, 334.0, doy)

        if 258.0 <= doy < 334.0 and s_month in (9, 10, 11):
            autumn_color = _smoothstep(258.0, 295.0, doy)
        else:
            autumn_color = 0.0

    autumn_mult = _palette_autumn_multiplier(traits.palette, traits.autumn_palette)

    # 2. Bloom (0..1)
    bloom = _month_window_weight(plan_date, lat_q, traits.bloom_months, ramp_from=1.0)

    # 3. Ripeness (0..1)
    harvest_weeks = harvest_override if harvest_override is not None else traits.harvest_weeks
    frost_mmdd = frost_window[0] or (last_frost.strftime("%m-%d") if last_frost else None)
    if frost_mmdd and harvest_weeks is not None:
        # Calendar frost dates already describe local seasons. Do not apply the
        # hemisphere phase shift to them again, or round windows to whole months.
        ripeness = _harvest_ripeness(plan_date, harvest_weeks, frost_mmdd)
    else:
        ripeness = _month_window_weight(plan_date, lat_q, traits.fruit_months, ramp_from=0.55)
    if (frost_window[0] and frost_window[1]
            and not _inside_frost_free_season(plan_date, *frost_window)):
        bloom = 0.0
        if harvest_weeks is None:
            ripeness = 0.0

    # 4. Snow (0..1)
    if snow_q is not None:
        snow = min(max(float(snow_q), 0.0), 1.0)
    else:
        abs_lat = abs(float(lat_q))
        if abs_lat >= 40.0 and s_month in (12, 1, 2):
            lat_factor = min(max((abs_lat - 40.0) / 25.0, 0.0), 1.0)
            month_peak = 1.0 if s_month == 1 else 0.65
            snow = round(lat_factor * month_peak * 0.55, 4)
        else:
            snow = 0.0

    # 5. Effective foliage linear tint (1.0 -> autumn_mult -> snow dust)
    ft_r = 1.0 + autumn_color * (autumn_mult[0] - 1.0)
    ft_g = 1.0 + autumn_color * (autumn_mult[1] - 1.0)
    ft_b = 1.0 + autumn_color * (autumn_mult[2] - 1.0)
    if snow > 0.0:
        ft_r = ft_r * (1.0 - 0.45 * snow) + SNOW_LINEAR_RGB[0] * (0.45 * snow)
        ft_g = ft_g * (1.0 - 0.45 * snow) + SNOW_LINEAR_RGB[1] * (0.45 * snow)
        ft_b = ft_b * (1.0 - 0.45 * snow) + SNOW_LINEAR_RGB[2] * (0.45 * snow)

    foliage_tint_linear = (
        round(min(max(ft_r, 0.05), 2.1), 5),
        round(min(max(ft_g, 0.05), 2.1), 5),
        round(min(max(ft_b, 0.05), 2.1), 5),
    )
    foliage_tint_rgba = _linear_to_srgb8((*foliage_tint_linear, 1.0))

    # 6. Accent opacity & tint (`PART_ACCENTS`)
    has_bulb = "bulb" in recipe
    has_fruit_or_pod = "fruit" in recipe or "fruit2" in recipe or "pods" in recipe
    has_blossom_or_umbel = (
        "flowers" in recipe
        or "clusters" in recipe
        or "puffs" in recipe
        or "umbels" in recipe
        or traits.blossom_spec is not None
    )

    if has_bulb:
        accent_opacity = max(leaf_density, ripeness, 0.65)
    elif has_fruit_or_pod and has_blossom_or_umbel:
        accent_opacity = max(bloom, ripeness)
    elif has_fruit_or_pod:
        accent_opacity = ripeness
    elif has_blossom_or_umbel:
        accent_opacity = bloom
    else:
        accent_opacity = 1.0

    # Unripe fruits tint slightly greener when ripeness is early (`0 < ripeness < 1`)
    if has_fruit_or_pod and 0.0 < ripeness < 0.95:
        unripe_mix = 1.0 - ripeness
        at_r = 1.0 - 0.25 * unripe_mix
        at_g = 1.0
        at_b = 1.0 - 0.20 * unripe_mix
    else:
        at_r, at_g, at_b = 1.0, 1.0, 1.0

    accent_tint_linear = (round(at_r, 5), round(at_g, 5), round(at_b, 5))
    accent_tint_rgba = _linear_to_srgb8((*accent_tint_linear, 1.0))

    return PhenologyState(
        leaf_density=round(float(leaf_density), 5),
        autumn_color=round(float(autumn_color), 5),
        autumn_tint_linear=autumn_mult,
        bloom=round(float(bloom), 5),
        ripeness=round(float(ripeness), 5),
        snow=round(float(snow), 5),
        foliage_tint_linear=foliage_tint_linear,
        foliage_tint_rgba=foliage_tint_rgba,
        accent_opacity=round(float(accent_opacity), 5),
        accent_tint_linear=accent_tint_linear,
        accent_tint_rgba=accent_tint_rgba,
    )


def evaluate_phenology(
    plant: Traits3D | SpriteRef | Record,
    plan_date: datetime.date,
    *,
    latitude_deg: float = DEFAULT_LATITUDE_DEG,
    last_frost: datetime.date | None = None,
    snow_override: float | None = None,
    frost_dates: Mapping[str, object] | None = None,
) -> PhenologyState:
    """Evaluate `PhenologyState` for `plant` (`Traits3D`, `SpriteRef`, or `Record`) on `plan_date`."""
    if isinstance(plant, Traits3D):
        sprite = plant.sprite
    elif isinstance(plant, SpriteRef):
        sprite = plant
    elif isinstance(plant, Record):
        resolved = plant_sprite(plant)
        sprite = resolved if resolved is not None else SpriteRef("categories", "round_deciduous")
    else:
        raise TypeError(f"Expected Traits3D, SpriteRef, or Record, got {type(plant).__name__}")

    lat_q = round(float(latitude_deg), 2) if math.isfinite(latitude_deg) else DEFAULT_LATITUDE_DEG
    snow_q = round(float(snow_override), 3) if snow_override is not None else None
    frost_window = _frost_window(frost_dates)
    override = _record_harvest(plant) if isinstance(plant, Record) else None
    return _evaluate_cached(sprite, plan_date, lat_q, last_frost, snow_q, frost_window, override)


def evaluate_phenology_batch(
    plants: Sequence[Traits3D | SpriteRef | Record],
    plan_date: datetime.date,
    *,
    latitude_deg: float = DEFAULT_LATITUDE_DEG,
    last_frost: datetime.date | None = None,
    snow_override: float | None = None,
    frost_dates: Mapping[str, object] | None = None,
) -> list[PhenologyState]:
    """Evaluate `PhenologyState` for a batch of plants (`<= 16 ms` for 300 plants)."""
    return [evaluate_phenology(
        plant, plan_date, latitude_deg=latitude_deg, last_frost=last_frost,
        snow_override=snow_override, frost_dates=frost_dates,
    ) for plant in plants]


def evaluate_phenology_for_records(
    records: Sequence[Record],
    plan_date: datetime.date,
    *,
    latitude_deg: float = DEFAULT_LATITUDE_DEG,
    last_frost: datetime.date | None = None,
    snow_override: float | None = None,
    frost_dates: Mapping[str, object] | None = None,
) -> dict[str, PhenologyState]:
    """Evaluate `{item_id: PhenologyState}` for all plant records in `records`."""
    return {rec.item_id: evaluate_phenology(
        rec, plan_date, latitude_deg=latitude_deg, last_frost=last_frost,
        snow_override=snow_override, frost_dates=frost_dates,
    ) for rec in records if rec.kind in PLANT_KINDS}


__all__ = [
    "DEFAULT_LATITUDE_DEG",
    "SNOW_LINEAR_RGB",
    "PhenologyState",
    "evaluate_phenology",
    "evaluate_phenology_batch",
    "evaluate_phenology_for_records",
    "seasonal_day_of_year",
    "seasonal_month",
]
