"""The living garden's weather, dew, moods and life (Phase 17 L5, #389, ADR-070). Qt-free.

``core/scene3d/look.py`` paints a frame from the sun alone (``look_for``). This module
paints the WEATHER over it — and the morning dew, the time of day the garden's life
keeps, and the garden lights:

    living_look(sun, preset, weather, ...) = apply_weather(look_for(sun, preset), ...)

TRUTH BEFORE BEAUTY. The weather is a look and nothing else (ADR-070 decision 1): it
never moves the sun, never moves a shadow, never touches the 2D sun study, the
hours-of-sun map or a plant. Under an overcast sky the key light still travels
where ``core/solar`` says; its shadows are softer and fainter, not elsewhere. A
``clear`` look outside the morning is EXACTLY ``look_for``'s, field for field
(only its ``atmosphere`` carries the time of day's life), so every truth gate of
L1–L4 reads what it read.

The presets (``WEATHER_SPECS``):

- **clear** — the reviewed L1.4 look.
- **partly_cloudy** (L7, #391) — the sun out between scattered clouds: ``cloud`` 0.4 is
  the atmosphere sky's cover (``AtmosphereSky.qml``, the clouds themselves), while the
  light takes only 0.15 of the overcast's changes and the sky 0.25 of its grey, so the
  shadows stay crisp and the painted sky stays blue.
- **overcast** — a grey sky as bright as the clear one at its horizon (so a night
  stays a night), no sun disc, the key light down to a fifth with soft, faint
  shadows, the sky's light up, a little less colour.
- **rain** — overcast, wet leaves and ground, a nearer haze, more wind, falling rain.
- **snow** — a pale overcast, snow on the ground and the leaves, falling snow, less wind.

The MOODS (``mood_of``) are names for what the frame shows — night, twilight,
golden hour, morning dew, overcast, rain, snow, day — read from the look itself,
so the name can never disagree with the picture.

"Today's weather" (L5.3, optional) maps the app's own daily forecast (Open-Meteo's
WMO code) onto a preset — ONLY while the plan date is today (``todays_weather``):
a forecast says nothing about another date.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from types import MappingProxyType
from typing import Final

import numpy as np

from .color import srgb_to_linear
from .look import (
    GOLDEN_DEG,
    NIGHT_BELOW_DEG,
    NOON,
    TWILIGHT_DEG,
    WIND_STRENGTH,
    AtmosphereSpec,
    LookSpec,
    fill_linear,
    fog_linear,
    ground_light,
    linear_to_srgb_hex,
    look_for,
    mix_linear,
    twilight_fill,
)
from .sink import SunState

__all__ = [
    "DEW_FULL_DEG", "DEW_GONE_DEG", "MOODS", "TODAY", "WEATHERS", "WEATHER_CHOICES",
    "WEATHER_SPECS", "WeatherSpec", "apply_weather", "dew_amount", "is_evening", "is_morning",
    "living_look", "mood_of", "noon_azimuth", "normalise_weather", "todays_weather",
    "weather_fog", "weather_from_wmo",
]

WEATHERS: Final = ("clear", "partly_cloudy", "overcast", "rain", "snow")
#: The weather choice that follows the forecast for today (L5.3).
TODAY: Final = "today"
WEATHER_CHOICES: Final = (*WEATHERS, TODAY)


@dataclass(frozen=True, slots=True)
class WeatherSpec:
    """One weather preset — its numbers are art direction (``ogp-lush-cinematic``)."""

    name: str
    #: How overcast the sky is, 0..1.
    cloud: float
    #: ``none`` | ``rain`` | ``snow``.
    precipitation: str
    #: The shaders' sway amplitude (``LookSpec.wind_strength``): the wind is a shader
    #: value, no simulation (``foliage.vert``, ``grass.vert``, the particles).
    wind_strength: float
    #: How wet leaves and ground look, 0..1.
    wetness: float
    #: The depth fog's distances x this.
    haze: float
    #: Snow on the ground and the leaves, 0..1.
    snow_cover: float = 0.0
    #: How much of the overcast's LIGHT changes it takes (key, shadows, probe, exposure,
    #: saturation), 0..1; None: ``cloud``. Separate clouds leave the sun out.
    light: float | None = None
    #: How far its sky goes to the overcast's grey (and the fog with it), 0..1; None: ``cloud``.
    grey: float | None = None

    def __post_init__(self) -> None:
        if self.precipitation not in ("none", "rain", "snow"):
            raise ValueError(f"WeatherSpec.precipitation: {self.precipitation!r}")
        for name in ("cloud", "wetness", "snow_cover", "light", "grey"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"WeatherSpec.{name} lies in 0..1, got {value!r}")
        if not 0.0 < self.haze <= 1.0 or self.wind_strength < 0.0:
            raise ValueError(f"WeatherSpec: haze in (0, 1], wind >= 0 ({self!r})")

    @property
    def sky_grey(self) -> float:
        """How far its sky and fog go to the overcast's grey: ``grey``, else ``cloud``."""
        return self.cloud if self.grey is None else self.grey


WEATHER_SPECS: Final = MappingProxyType({
    "clear": WeatherSpec("clear", 0.0, "none", WIND_STRENGTH, 0.0, 1.0),
    # the atmosphere's clouds read as scattered up to about 0.6 and close above it (the
    # cover sheet of L7's owner pass: 0.35 and 0.6 against 1.0). The sun stays out: at the
    # full share the painted sky read as a dull clear day (lawn lit/shadow 6.7 against
    # clear's 12.2; at 0.15 about 9.3 - 3D review)
    "partly_cloudy": WeatherSpec("partly_cloudy", 0.4, "none", 3.0, 0.0, 0.9,
                                 light=0.15, grey=0.25),
    "overcast": WeatherSpec("overcast", 1.0, "none", 3.5, 0.0, 0.8),
    "rain": WeatherSpec("rain", 1.0, "rain", 5.0, 1.0, 0.6),
    "snow": WeatherSpec("snow", 0.85, "snow", 1.5, 0.0, 0.55, snow_cover=0.75),
})


def normalise_weather(value: object, default: str = "clear") -> str:
    """A stored weather choice as one of ``WEATHER_CHOICES`` (anything else: ``default``)."""
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if text in WEATHER_CHOICES else default


# ── today's weather (L5.3) ───────────────────────────────────────────────────

def weather_from_wmo(code: int) -> str:
    """A WMO weather interpretation code (Open-Meteo's daily ``weathercode``) as a
    preset: 0–1 clear (clear sky, mainly clear), 2 partly cloudy, 3 overcast, 45/48
    (fog) overcast, drizzle, rain, showers and thunderstorms rain, snow and snow showers
    snow. An unknown code is clear."""
    code = int(code)
    if code == 2:
        return "partly_cloudy"
    if code in (3, 45, 48):
        return "overcast"
    if 51 <= code <= 67 or 80 <= code <= 82 or 95 <= code <= 99:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    return "clear"


def todays_weather(days: Iterable[tuple[str, int]], plan_date: date, today: date) -> str | None:
    """The preset for ``plan_date`` from a daily forecast ``(ISO date, WMO code)`` —
    ONLY when ``plan_date`` is ``today`` and the forecast has that day; else None
    (the caller shows clear and says why)."""
    if plan_date != today:
        return None
    wanted = today.isoformat()
    for day, code in days:
        if str(day) == wanted:
            return weather_from_wmo(code)
    return None


# ── the time of day ──────────────────────────────────────────────────────────

def is_morning(sun: SunState) -> bool:
    """The sun is EAST of the meridian — before solar noon — whatever the latitude:
    east of the north–south plane is exactly a compass bearing in (0°, 180°)."""
    azimuth = float(sun.azimuth_deg) % 360.0
    return 0.0 < azimuth < 180.0


def is_evening(sun: SunState) -> bool:
    """The sun is WEST of the meridian — after solar noon, before solar midnight."""
    azimuth = float(sun.azimuth_deg) % 360.0
    return 180.0 < azimuth < 360.0


#: The morning dew: it comes in over ``DEW_RISE_DEG`` from dawn (the end of civil
#: twilight) — a dawn is no switch (3D review of L5) —, lies full until the sun is
#: ``DEW_FULL_DEG`` high and is gone by ``DEW_GONE_DEG``: linear ramps (ogp-lush-cinematic).
DEW_RISE_DEG: Final = 4.0
DEW_FULL_DEG: Final = GOLDEN_DEG
DEW_GONE_DEG: Final = 18.0
#: ... and fades over this many degrees of azimuth before NOON's meridian: on a winter
#: day whose sun never reaches ``DEW_GONE_DEG`` it lay until solar noon and then went out
#: at once (3D review of L5, round 2: 0.33 at noon in Berlin on 21 December, 0.97 in
#: Helsinki). Noon is due south in the northern hemisphere and due north in the southern
#: — which one is the PLACE's, not the sun's: a summer dawn north of ~60° stands near
#: due north, the other meridian (senior review of L5: faded x0.04 as if it were noon).
_DEW_NOON_FADE_DEG: Final = 25.0
#: ... and rises over this many degrees of azimuth after solar MIDNIGHT's meridian: north
#: of ~61° in June the dawn twilight begins right at midnight, and without a ramp there the
#: dew switched on in one frame (0 -> 1.0 in Tromsø; 3D review of L5, round 4).
_DEW_MIDNIGHT_RISE_DEG: Final = 15.0


def noon_azimuth(southern: bool) -> float:
    """The compass bearing of solar noon: due south (180°), or due north (0°) in the
    southern hemisphere — solar midnight is the opposite one."""
    return 0.0 if southern else 180.0


def _to_meridian(sun: SunState, meridian_deg: float) -> float:
    """Degrees of azimuth between the sun and ``meridian_deg`` (0..180)."""
    return abs((float(sun.azimuth_deg) - meridian_deg + 180.0) % 360.0 - 180.0)


def dew_amount(sun: SunState, weather: str = "clear", *, southern: bool = False) -> float:
    """How much morning dew lies on the garden, 0..1: in the morning only, from the
    end of civil twilight until the sun stands ``DEW_GONE_DEG`` high, fading before
    noon (``southern``: the place lies south of the equator); never in rain (wet
    anyway) or snow."""
    if weather in ("rain", "snow") or not is_morning(sun):
        return 0.0
    elevation = float(sun.elevation_deg)
    if elevation < TWILIGHT_DEG or elevation >= DEW_GONE_DEG:
        return 0.0
    if elevation <= DEW_FULL_DEG:
        amount = _ramp(elevation, TWILIGHT_DEG, TWILIGHT_DEG + DEW_RISE_DEG)
    else:
        amount = (DEW_GONE_DEG - elevation) / (DEW_GONE_DEG - DEW_FULL_DEG)
    noon = noon_azimuth(southern)
    return (amount * _ramp(_to_meridian(sun, noon), 0.0, _DEW_NOON_FADE_DEG)
            * _midnight_fade(sun, southern, _DEW_MIDNIGHT_RISE_DEG))


def _ramp(value: float, low: float, high: float) -> float:
    """0 at ``low``, 1 at ``high``, linear and clamped (``low`` > ``high`` ramps down)."""
    if high == low:
        return 1.0 if value >= high else 0.0
    return min(max((value - low) / (high - low), 0.0), 1.0)


# ── the weather on a look ────────────────────────────────────────────────────

#: The overcast sky's hue (linear, luminance 1): a cool, slightly blue grey.
_REC709: Final = np.array((0.2126, 0.7152, 0.0722))
_OVERCAST_HUE: Final = np.array((0.94, 0.99, 1.07)) / float(np.array((0.94, 0.99, 1.07)) @ _REC709)
#: Its top is darker than its horizon (a thick layer is darkest overhead) — and the
#: horizon as bright as the clear sky's own: a cloudy noon is no dusk, a cloudy night
#: no brighter than a clear one.
_OVERCAST_TOP_SHARE: Final = 0.78
_OVERCAST_HORIZON_GAIN: Final = 1.0
#: Overcast: the key light down to this share (a disc of sun behind the layer), its
#: shadows this much fainter and softer; the sky's light and the exposure up.
_KEY_UNDER_CLOUD: Final = 0.22
_SHADOW_UNDER_CLOUD: Final = 0.30
_PCF_UNDER_CLOUD: Final = 8.0
_PROBE_UNDER_CLOUD: Final = 1.45
#: The exposure under cloud: NOON's, plus this — never the low sun's lift (0.85 → 1.15 at
#: a golden hour, +0.44 EV), which makes up for a clear key light that cloud has taken
#: away: inherited, it made an overcast sunset 98 % as bright as noon (a clear one: 57 %;
#: 3D review of L5, round 3). Towards night the mood's own exposure returns (twilight).
_EXPOSURE_UNDER_CLOUD_EV: Final = 0.15
_SATURATION_UNDER_CLOUD: Final = 0.80
#: The ground in the rain: darker (wet earth and stone) and a little shinier. Roughness
#: is the lever, not specular: at 0.55 the dimmed key light still left a crisp lobe on
#: the wet meadow at a low sun — a cream glint carved by the shadows, a sunlit look in
#: the rain — and drew the plan's edge as a 1.75-luma step; at 0.8 the step is 0.32 and
#: the glint is gone (3D review of L5, round 2).
_WET_GROUND_DARKEN: Final = 0.22
_WET_GROUND_ROUGHNESS: Final = 0.8
_WET_GROUND_SPECULAR: Final = 0.25
#: Snow on the ground (linear): a cool white — ``ground.frag`` mixes the same (pinned).
SNOW_LINEAR: Final = (0.80, 0.84, 0.89)
#: The dew: a morning mist (the haze), and a little less colour in it.
_DEW_HAZE: Final = 0.62
_DEW_SATURATION: Final = 0.94
_DEW_WETNESS: Final = 0.6
#: Where the wind blows the particles: from the west-south-west (a prevailing
#: westerly), this many cm/s per unit of the shaders' wind strength. A look, not
#: meteorology.
_WIND_FROM_DEG: Final = 250.0
_DRIFT_PER_WIND: Final = 22.0
#: The share of the precipitation's particles a preset draws.
_PRECIP_DENSITY: Final = MappingProxyType({"none": 0.0, "rain": 1.0, "snow": 1.0})
#: The fog under a cloud layer, x (1 + cloud x this): ``FOG_OF_HORIZON`` was calibrated
#: on the CLEAR sky's texture, and an overcast sky draws its horizon row otherwise — the
#: fog drew 4 luma above the overcast noon horizon and 3.6 under the overcast night's: a
#: seam in every cloudy weather (3D review of L5). Fitted on the board's ``horizon``
#: probe per weather (``--living --horizon``): noon +1.5, sunset -1.5 luma by day; 0.55 at
#: night overshot to +4.5, 0.23 meets it. Between the two by the look's ``twilight``.
_FOG_UNDER_CLOUD_DAY: Final = -0.045
_FOG_UNDER_CLOUD_NIGHT: Final = 0.23
#: Fireflies fade out over this many degrees of azimuth before solar midnight (the sun
#: crossing the meridian below the horizon), instead of all going out at once.
_FIREFLY_FADE_DEG: Final = 25.0


def _luminance(linear: np.ndarray) -> float:
    return float(linear @ _REC709)


def _overcast(top: str, horizon: str, cloud: float) -> tuple[str, str]:
    """The sky's top and horizon under ``cloud``: mixed in linear light towards a grey
    whose horizon is as bright as the clear sky's horizon."""
    if cloud <= 0.0:
        return top, horizon
    level = _luminance(srgb_to_linear(horizon).astype(np.float64)) * _OVERCAST_HORIZON_GAIN
    grey_horizon = linear_to_srgb_hex(_OVERCAST_HUE * level)
    grey_top = linear_to_srgb_hex(_OVERCAST_HUE * level * _OVERCAST_TOP_SHARE)
    return mix_linear(top, grey_top, cloud), mix_linear(horizon, grey_horizon, cloud)


def weather_fog(sky_horizon: str, probe_exposure: float, sky_energy: float, cloud: float,
                twilight: float) -> tuple[float, float, float]:
    """``look.fog_linear`` for a sky under ``cloud`` (linear rgb): the clear sky's fog,
    corrected for how an overcast sky draws its horizon (``_FOG_UNDER_CLOUD_*``). The
    clear sky (``cloud`` 0) gets ``fog_linear`` exactly."""
    fog = fog_linear(sky_horizon, probe_exposure, sky_energy)
    if cloud <= 0.0:
        return fog
    share = _FOG_UNDER_CLOUD_DAY + (_FOG_UNDER_CLOUD_NIGHT - _FOG_UNDER_CLOUD_DAY) * twilight
    gain = 1.0 + float(cloud) * share
    return (fog[0] * gain, fog[1] * gain, fog[2] * gain)


def _midnight_fade(sun: SunState, southern: bool, width_deg: float) -> float:
    """0 at solar midnight's meridian — due north in the northern hemisphere, due south in
    the southern — rising to 1 over ``width_deg`` of azimuth on either side: the
    fireflies go out towards it in the evening (``is_evening``), the dew rises from it in
    the morning (``_DEW_MIDNIGHT_RISE_DEG``)."""
    midnight = (noon_azimuth(southern) + 180.0) % 360.0
    return _ramp(_to_meridian(sun, midnight), 0.0, width_deg)


def _particle_light(look: LookSpec) -> tuple[float, float, float]:
    """The light an unlit particle is drawn in: half the key light — the sun, or once
    it is down the look's moon (a drop is lit from one side) — plus the sky's light and
    the twilight fill that lights the garden around it (#802), all in linear light."""
    mood, sky = look.mood, look.sky
    key = srgb_to_linear(mood.sun_color).astype(np.float64) * mood.sun_brightness * 0.5
    ambient = ((srgb_to_linear(sky.top) + srgb_to_linear(sky.horizon)).astype(np.float64) / 2.0
               * mood.probe_exposure * sky.sky_energy * 0.9)
    light = key + ambient + np.asarray(look.twilight_fill_linear, dtype=np.float64)
    return (float(light[0]), float(light[1]), float(light[2]))


def apply_weather(look: LookSpec, weather: str | WeatherSpec, sun: SunState, *,
                  dew: bool = True, southern: bool = False) -> LookSpec:
    """``look`` (``look_for(sun, …)``) under ``weather`` at ``sun`` — module docstring.

    The sun's direction is not touched (it is not in a look); the sky, the light's
    colour and strength, the shadows' darkness and softness, the grade, the fog, the
    wind and the atmosphere are. Clear weather outside the morning changes nothing
    but the atmosphere. ``dew`` False: no morning dew either — clear weather is then
    the sun's own look at any hour (an Analyze drape on the ground: ``LookController``).
    ``southern``: the place lies south of the equator — where noon and midnight stand.
    The twilight fill (#802) is the weathered look's own, held to the SAME weather's
    night (``look.twilight_fill``): a cloudy night is darker than a clear one.
    """
    spec = weather if isinstance(weather, WeatherSpec) else WEATHER_SPECS[weather]
    weathered = _weathered(look, spec, sun, dew=dew, southern=southern)
    weathered = replace(weathered, twilight_fill_linear=twilight_fill(
        weathered, *_anchor_lights(spec)))
    particle_light = _particle_light(weathered)
    return replace(weathered, atmosphere=replace(weathered.atmosphere,
                                                 particle_light_linear=particle_light))


#: Each weather's twilight-fill anchors (``_anchor_lights``), by spec.
_ANCHOR_LIGHTS: dict[WeatherSpec, tuple[float, float]] = {}


def _anchor_lights(spec: WeatherSpec) -> tuple[float, float]:
    """``look.ground_light`` of ``spec``'s night and of its look at sunset
    (``NIGHT_BELOW_DEG``), no dew, no fill: the anchors of its twilight fill
    (``look.twilight_fill``). Computed once per weather."""
    if spec not in _ANCHOR_LIGHTS:
        lights = []
        for elevation in (-30.0, NIGHT_BELOW_DEG):
            sun = SunState(elevation_deg=elevation, azimuth_deg=0.0)
            lights.append(ground_light(_weathered(look_for(sun), spec, sun, dew=False,
                                                  southern=False), with_fill=False))
        _ANCHOR_LIGHTS[spec] = (lights[0], lights[1])
    return _ANCHOR_LIGHTS[spec]


def _weathered(look: LookSpec, spec: WeatherSpec, sun: SunState, *, dew: bool,
               southern: bool) -> LookSpec:
    """``apply_weather`` before its twilight fill and its particles' light."""
    cloud = spec.cloud
    light = cloud if spec.light is None else spec.light
    grey = spec.sky_grey
    dew_share = dew_amount(sun, spec.name, southern=southern) if dew else 0.0
    mood, sky, shadow = look.mood, look.sky, look.shadow
    if cloud > 0.0:
        top, horizon = _overcast(sky.top, sky.horizon, grey)
        # the disc fades INTO the cloud — its colour towards the horizon's; its energy
        # stays: Qt's procedural sky blends the disc and its falloff towards sun colour x
        # sun energy, so energy 0 drew a BLACK sun with a dark halo (3D review of L5,
        # round 2: luma 0 at the sun, 150 around it, under overcast and rain)
        sky = replace(sky, top=top, horizon=horizon,
                      ground_bottom=mix_linear(sky.ground_bottom, "#5a5f62", grey * 0.6),
                      sun_disc=(horizon if not sun.is_up       # a set sun stays matched (look_for's test)
                                else mix_linear(sky.sun_disc, horizon, light)),
                      cloud=cloud)
        held = light * (1.0 - mood.twilight)           # how much of NOON's exposure holds
        mood = replace(
            mood,
            sun_brightness=mood.sun_brightness * (1.0 + (_KEY_UNDER_CLOUD - 1.0) * light),
            probe_exposure=mood.probe_exposure * (1.0 + (_PROBE_UNDER_CLOUD - 1.0) * light),
            # in stops, like ``mix_rig``
            exposure=2.0 ** (math.log2(mood.exposure) * (1.0 - held)
                             + math.log2(NOON.exposure) * held
                             + _EXPOSURE_UNDER_CLOUD_EV * light),
            saturation=mood.saturation * (1.0 + (_SATURATION_UNDER_CLOUD - 1.0) * light))
        shadow = replace(shadow,
                         factor=shadow.factor * (1.0 + (_SHADOW_UNDER_CLOUD - 1.0) * light),
                         pcf_factor=shadow.pcf_factor + (_PCF_UNDER_CLOUD - shadow.pcf_factor)
                         * light)
    if dew_share > 0.0:
        mood = replace(mood, saturation=mood.saturation
                       * (1.0 + (_DEW_SATURATION - 1.0) * dew_share))
    fog = weather_fog(sky.horizon, mood.probe_exposure, sky.sky_energy, grey, mood.twilight)
    fill = fill_linear(sky.top, sky.horizon, mood.probe_exposure, sky.sky_energy)

    wetness = max(spec.wetness, _DEW_WETNESS * dew_share)
    haze = spec.haze * (1.0 + (_DEW_HAZE - 1.0) * dew_share)
    darken = 1.0 - _WET_GROUND_DARKEN * spec.wetness      # the rain's, not the dew's
    # the meadow keeps its ONE albedo (#798): the rain's darkening and the snow are the
    # ground's tint and cover below, which ground.frag applies to the meadow's grass and
    # to the plan's tiles alike - weathering the albedo too would weather the meadow twice
    meadow = look.meadow_albedo
    elevation = float(sun.elevation_deg)
    sun_up = sun.is_up        # the ONE test of "the sun is down" (look_for, the 2D shadows)
    blowing = math.radians(_WIND_FROM_DEG + 180.0)     # the wind blows TOWARDS this
    drift = spec.wind_strength * _DRIFT_PER_WIND
    dry = spec.precipitation == "none"
    twilight = look.mood.twilight
    atmosphere = AtmosphereSpec(
        weather=spec.name, cloud=cloud, dew=dew_share, wetness=wetness,
        snow_cover=spec.snow_cover,
        haze=haze, ground_tint_linear=(darken, darken, darken),
        ground_roughness=1.0 + (_WET_GROUND_ROUGHNESS - 1.0) * spec.wetness,
        ground_specular=0.15 + (_WET_GROUND_SPECULAR - 0.15) * spec.wetness,
        precipitation=spec.precipitation, precip_density=_PRECIP_DENSITY[spec.precipitation],
        wind_drift_scene=(math.sin(blowing) * drift, math.cos(blowing) * drift),
        particle_light_linear=(0.0, 0.0, 0.0),   # set below, from the weathered look
        # falling leaves in any weather but snow; butterflies by day, dry, not under a
        # full overcast; fireflies on dry evenings, from sunset towards solar midnight
        leaves=0.0 if spec.precipitation == "snow" else 1.0,
        butterflies=(_ramp(elevation, GOLDEN_DEG, 14.0) * (1.0 - 0.7 * cloud)) if dry else 0.0,
        fireflies=(_ramp(twilight, 0.15, 0.6) * _midnight_fade(sun, southern, _FIREFLY_FADE_DEG)
                   if (dry and is_evening(sun)) else 0.0),
        # the lights come on with dusk and stay on through the night
        lamps=_ramp(twilight, 0.05, 0.5) if not sun_up else 0.0)
    weathered = replace(look, mood=mood, sky=sky, shadow=shadow, fog_linear=fog,
                        fill_linear=fill, plain_sky_linear=fog, meadow_albedo=meadow,
                        wind_strength=spec.wind_strength, atmosphere=atmosphere)
    if cloud == 0.0 and dew_share == 0.0 and spec.precipitation == "none" and spec.name == "clear":
        # clear and dry: the sun's own look, field for field — but its atmosphere
        weathered = replace(look, atmosphere=atmosphere)
    return weathered


def living_look(sun: SunState, preset: str = "high", weather: str = "clear", *,
                dew: bool = True, southern: bool = False) -> LookSpec:
    """THE look of a living frame: ``look_for(sun, preset)`` under ``weather``
    (``dew``, ``southern``: ``apply_weather``)."""
    return apply_weather(look_for(sun, preset), weather, sun, dew=dew, southern=southern)


# ── the moods ────────────────────────────────────────────────────────────────

MOODS: Final = ("night", "twilight", "rain", "snow", "overcast", "morning_dew", "golden_hour",
                "day")
#: Up to this sun elevation a clear evening or morning is the golden hour.
_GOLDEN_HOUR_DEG: Final = 12.0


def mood_of(look: LookSpec, sun: SunState) -> str:
    """The name of what the frame shows (``MOODS``) — read from the look, first match
    wins: night, twilight, then the weather (rain, snow, overcast), then the dew, the
    golden hour of a low clear sun, and day."""
    if look.mood.night:
        return "night"
    if look.mood.twilight > 0.0:
        return "twilight"
    atmosphere = look.atmosphere
    if atmosphere.precipitation in ("rain", "snow"):
        return atmosphere.precipitation
    if atmosphere.cloud >= 0.5:
        return "overcast"
    if atmosphere.dew >= 0.5:
        return "morning_dew"
    if float(sun.elevation_deg) <= _GOLDEN_HOUR_DEG:
        return "golden_hour"
    return "day"
