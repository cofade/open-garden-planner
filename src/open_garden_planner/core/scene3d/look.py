"""The look of a 3D frame as DATA: moods by sun elevation, presets, the auto preset (L1.4).

Qt-free (stdlib + numpy), so every decision in here runs in the GPU-less test
tier. Art direction only — what is truth (where the sun stands, how high a wall
is) never lives here: the sun comes in as a ``SunState`` from ``core/solar``,
and nothing in this module changes its direction.

Four things:

- **The rig** — three day anchors (noon at and above 30°, golden at 6°, low sun
  at 0.5°) joined by continuous ramps, and a separate night rig below 0.5°
  (``day_rig``, ``NIGHT``). Colours are mixed in LINEAR light, exposure in stops
  (log2), everything else linearly. The values are the L0 spike's, measured on
  its boards (``ogp-lush-cinematic`` §3); a drift-guard test compares this module
  with the spike's answers, frozen in ``tests/data/l0_spike_reference.json`` when L1.10
  deleted the spike.
- **The presets** — low / medium / high / ultra as data (``PRESET_SPECS``): what
  a preset may change is cost (shadow map, cascades, filtering, anti-aliasing,
  ambient occlusion, glow), never the mood and never the truth.
- **``look_for(sun, preset)``** — the one function that turns a sun and a preset
  into a ``LookSpec``: plain data the engine package maps onto its scene
  (``ui/view3d/quick3d/look.py``).
- **``AutoPreset``** — the preset chosen from measured frame times, with a dead
  band, a hold time and a growing bar on a level that proved too slow, so that
  it cannot oscillate; and ``sky_is_stale`` — when the sky texture, which is
  expensive to rebuild, has to follow the sun.

Night is where the 2D shadow overlay says it is: ``NIGHT_BELOW_DEG`` IS
``core.shadow_geometry.MIN_SUN_ELEVATION_DEG`` (the spike's ``SUN_LOW_DEG`` has
the same value; pinned).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

import numpy as np

from ..shadow_geometry import MIN_SUN_ELEVATION_DEG
from .color import srgb_to_linear
from .frame import sun_direction_scene
from .sink import SunState

__all__ = [
    "AUTO", "AUTO_LEVELS", "DAY", "FILL_OF_SKY", "FOG_OF_HORIZON", "GOLDEN", "GOLDEN_DEG",
    "LOW_SUN", "MEADOW_ALBEDO", "MOON_AZIMUTH_DEG", "MOON_ELEVATION_DEG", "NEUTRAL_DAY", "NIGHT",
    "NIGHT_BELOW_DEG", "NIGHT_SKY_ENERGY", "NOON", "NOON_DEG", "PRESETS", "PRESET_SPECS",
    "QUALITY_CHOICES", "SKY_MIN_ELEVATION_DEG", "SKY_REBUILD_DEG", "TWILIGHT_DEG", "AutoPolicy",
    "AutoPreset", "LookSpec", "MoodSpec", "PresetSpec", "Rig", "ShadowSpec", "SkySpec", "day_rig",
    "fill_linear", "fog_color", "fog_linear", "linear_to_srgb_hex", "look_for", "mix_linear",
    "mix_rig", "moon_travel_scene", "normalise_quality", "scale_linear", "sky_is_stale",
    "sky_phase", "sky_separation_deg", "twilight_fraction", "twilight_rig",
]

# ── the rig ──────────────────────────────────────────────────────────────────

#: Below this geometric sun elevation it is night — the 2D shadow overlay's own
#: threshold, so 2D and 3D never disagree about whether the sun is up.
NIGHT_BELOW_DEG: Final = MIN_SUN_ELEVATION_DEG
#: Where civil twilight ends: from ``NIGHT_BELOW_DEG`` down to here the day's last
#: rig (the low sun) fades into the night rig — a ramp, not a switch (L1.4 fix round
#: 1: the switch at 0.5° dropped the frame from luma 77 to 37 within 90 s of plan
#: time and drew all of civil twilight as full night). Below it, night.
TWILIGHT_DEG: Final = -6.0
#: The golden anchor, and where the noon rig begins (it holds above).
GOLDEN_DEG: Final = 6.0
NOON_DEG: Final = 30.0

#: ONE albedo for the endless meadow and for plan ground no item covers (the linear
#: mean of ``resources/textures/grass.png``, hue 104°). Night comes from the light
#: and the exposure, never from a darker albedo: the L0 board's per-mood meadow
#: colours made the plan glow as an island at night (5.6x its surround).
MEADOW_ALBEDO: Final = "#487f34"
#: Fog = sky horizon x probe exposure x this factor, in LINEAR light. The skybox is
#: drawn x probe exposure and the fog is not; "horizon x 0.6" still sat 20-26 luma
#: over the sky row above the horizon, x probe x 0.8 measured -0.7 / -0.5 / +1.4
#: (golden hour, morning, walk; high — spike).
FOG_OF_HORIZON: Final = 0.8
#: The flat fill that stands in for the sky's light where no sky texture lights the
#: view is HALF the sky's mean radiance: at full strength the compatibility mode
#: read +22 luma brighter than the GPU's sky-lit frame at golden hour, sunset and in
#: the walk (the sky lights a surface from one hemisphere, a flat ambient from all
#: directions). L1.4 fix round 1.
FILL_OF_SKY: Final = 0.5
#: Amplitude of the foliage and grass sway, in the shaders' units (spike).
WIND_STRENGTH: Final = 2.5
#: The moon of the night rig: fixed, high in the south (spike). It is a LOOK, not an
#: ephemeris — the plan's sun is below the horizon, and the scene still needs a key.
MOON_ELEVATION_DEG: Final = 38.0
MOON_AZIMUTH_DEG: Final = 165.0
#: The procedural sky is never asked for a sun further below the horizon than the end
#: of civil twilight: through twilight its colours follow the elevation (one rebuild
#: per degree); the night sky does not.
SKY_MIN_ELEVATION_DEG: Final = TWILIGHT_DEG


@dataclass(frozen=True, slots=True)
class Rig:
    """One anchor of the rig: the key light, the sky, the exposures."""

    sun_color: str
    sun_brightness: float
    sky_top: str
    sky_horizon: str
    sun_disc: str
    exposure: float
    probe_exposure: float


#: Noon, at and above 30°. Exposure 0.85: 0.92 clipped a channel on 4.6 % of noon_low
#: (the sun-lit roof at R 254); 0.85: 0.26 %, lawn luma 163 -> 158.
NOON: Final = Rig("#fff1dc", 1.9, "#3f78c9", "#cfe2f2", "#fff0d8", 0.85, 0.55)
#: Golden, at 6°. Brightness 1.9, the noon value: 2.1 put a 2.03 sun into the 14°
#: December noon and clipped the roof (1.56 % of the frame). The golden mood is its
#: exposure and its colour — a low sun crosses more air, it is never brighter.
GOLDEN: Final = Rig("#ffb878", 1.9, "#4f7fc8", "#f4d2a6", "#ffd09a", 1.15, 0.50)
#: Low sun, at 0.5°.
LOW_SUN: Final = Rig("#ff9655", 1.7, "#4a6fb0", "#f2b47c", "#ffb070", 1.25, 0.42)
#: Night, below 0.5°: moonlight ``#8ea4d6`` / 0.32, a dim sky, exposure 2.4.
NIGHT: Final = Rig("#8ea4d6", 0.32, "#070d22", "#1b2747", "#9fb2e0", 2.4, 0.35)
#: The three day anchors with the elevation each sits at, low to high.
DAY: Final[tuple[tuple[float, Rig], ...]] = (
    (NIGHT_BELOW_DEG, LOW_SUN), (GOLDEN_DEG, GOLDEN), (NOON_DEG, NOON))


def linear_to_srgb_hex(rgb: object) -> str:
    """Linear rgb (clamped to 0..1) -> ``#rrggbb`` (IEC 61966-2-1), to 8 bits."""
    linear = np.clip(np.asarray(rgb, dtype=np.float64), 0.0, 1.0)
    encoded = np.where(linear <= 0.0031308, linear * 12.92,
                       1.055 * np.power(linear, 1.0 / 2.4) - 0.055)
    return "#" + "".join(f"{round(float(channel) * 255):02x}" for channel in encoded)


def _linear(color: str) -> np.ndarray:
    return srgb_to_linear(color).astype(np.float64)


def mix_linear(first: str, second: str, t: float) -> str:
    """``#rrggbb`` ``first`` -> ``second`` at ``t``, mixed in LINEAR light. The ends
    come back exactly (never through a round trip)."""
    if t <= 0.0:
        return first
    if t >= 1.0:
        return second
    low, high = _linear(first), _linear(second)
    return linear_to_srgb_hex(low + (high - low) * t)


def scale_linear(color: str, factor: float) -> str:
    """``#rrggbb`` scaled by ``factor`` in LINEAR light."""
    return linear_to_srgb_hex(_linear(color) * factor)


def fog_linear(sky_horizon: str, probe_exposure: float,
               sky_energy: float = 1.0) -> tuple[float, float, float]:
    """The fog that meets a sky at its horizon, in LINEAR rgb: the sky is DRAWN as its
    horizon colour x its own energy x the probe exposure, and the fog must be what
    is drawn (x ``FOG_OF_HORIZON``).

    ``sky_energy`` is 1 by day and 0.25 at night. The spike's formula had no energy
    in it, so its night fog was four times brighter than the night sky it met: a
    bright line along the whole horizon (a 10.5-luma cliff at high, 21.2 at low,
    L1.4 round 1 — ``ogp-lush-cinematic`` §7).

    Linear and not ``#rrggbb``: a night fog is a few thousandths in linear light,
    where 8 bits of sRGB are steps of a fifth — and where the engine's own
    linearisation of a colour property is far off the sRGB curve
    (``quick3d/look.py``: ``engine_srgb``)."""
    value = _linear(sky_horizon) * (probe_exposure * sky_energy * FOG_OF_HORIZON)
    return (float(value[0]), float(value[1]), float(value[2]))


def fog_color(sky_horizon: str, probe_exposure: float, sky_energy: float = 1.0) -> str:
    """``fog_linear`` as ``#rrggbb`` — to read, to log, to compare; never to render."""
    return linear_to_srgb_hex(fog_linear(sky_horizon, probe_exposure, sky_energy))


def fill_linear(sky_top: str, sky_horizon: str, probe_exposure: float,
                sky_energy: float = 1.0) -> tuple[float, float, float]:
    """The flat fill that stands in for a sky's diffuse light where no sky texture
    lights the scene (the top-down truth view, the software fallback): the mean of
    the sky's top and horizon in linear light, x probe exposure x the sky's energy
    x ``FILL_OF_SKY``."""
    mean = ((_linear(sky_top) + _linear(sky_horizon)) / 2.0 * probe_exposure * sky_energy
            * FILL_OF_SKY)
    return (float(mean[0]), float(mean[1]), float(mean[2]))


def _ramp(elevation_deg: float) -> tuple[Rig, Rig, float]:
    """The two anchors ``elevation_deg`` lies between and how far (0..1), clamped."""
    (low_at, low), (mid_at, mid), (high_at, high) = DAY
    if elevation_deg < mid_at:
        t = (elevation_deg - low_at) / (mid_at - low_at)
        return low, mid, min(max(t, 0.0), 1.0)
    return mid, high, min((elevation_deg - mid_at) / (high_at - mid_at), 1.0)


def mix_rig(low: Rig, high: Rig, t: float) -> Rig:
    """Two rigs mixed at ``t`` (0..1, the ends exact): colours in linear light,
    exposure in stops, brightness and probe exposure linearly."""
    if t <= 0.0:
        return low
    if t >= 1.0:
        return high
    return Rig(
        sun_color=mix_linear(low.sun_color, high.sun_color, t),
        sun_brightness=low.sun_brightness + (high.sun_brightness - low.sun_brightness) * t,
        sky_top=mix_linear(low.sky_top, high.sky_top, t),
        sky_horizon=mix_linear(low.sky_horizon, high.sky_horizon, t),
        sun_disc=mix_linear(low.sun_disc, high.sun_disc, t),
        # in stops: 1.15 -> 0.85 is -0.44 EV, and a linear mix would spend it unevenly
        exposure=float(2.0 ** (math.log2(low.exposure) * (1.0 - t) + math.log2(high.exposure) * t)),
        probe_exposure=low.probe_exposure + (high.probe_exposure - low.probe_exposure) * t,
    )


def day_rig(elevation_deg: float) -> Rig:
    """The day rig at a sun elevation: an anchor exactly at its own elevation, a
    continuous mix in between, the noon rig above ``NOON_DEG``, the low-sun rig at
    and below ``NIGHT_BELOW_DEG`` (below it ``look_for`` takes ``twilight_rig``)."""
    low, high, t = _ramp(elevation_deg)
    return mix_rig(low, high, t)


def twilight_fraction(elevation_deg: float) -> float:
    """How far into the night a sun elevation is: 0 while the sun is up (at and above
    ``NIGHT_BELOW_DEG``), 1 at and below ``TWILIGHT_DEG``, linear in between."""
    if elevation_deg >= NIGHT_BELOW_DEG:
        return 0.0
    if elevation_deg <= TWILIGHT_DEG:
        return 1.0
    return (NIGHT_BELOW_DEG - elevation_deg) / (NIGHT_BELOW_DEG - TWILIGHT_DEG)


def twilight_rig(elevation_deg: float) -> Rig:
    """The rig of a sun under ``NIGHT_BELOW_DEG``: the low-sun rig mixed into the
    night rig by ``twilight_fraction`` (``mix_rig``: colours in linear light, exposure
    in stops) — and the key light is the moon (the sun is down, as the 2D shadows
    say), its brightness the night rig's times the fraction: no key, and no shadow,
    just under 0.5°, the full moon at −6°.

    Colours in linear light, not in stops: in stops the sky faded faster than the
    moon came in, and the frame went DARKER than the night it ends in, then brighter
    again (mean luminance 0.116 at 0.6° -> 0.023 at −3/−4° -> 0.034 at −6°, bench_small,
    the golden-hour camera). Linearly the frame darkens all the way (0.116 -> 0.099 at
    0° -> 0.052 at −3° -> 0.034 at −6°); the sky band itself moves most in its last
    half degree, where the moon already carries the frame's light."""
    t = twilight_fraction(elevation_deg)
    mixed = mix_rig(LOW_SUN, NIGHT, t)
    return Rig(mixed.sun_color, NIGHT.sun_brightness * t, mixed.sky_top, mixed.sky_horizon,
               mixed.sun_disc, mixed.exposure, mixed.probe_exposure)


def moon_travel_scene() -> tuple[float, float, float]:
    """The unit vector the night rig's moonlight travels along, scene frame (E, N, up)."""
    east, north, up = sun_direction_scene(MOON_ELEVATION_DEG, MOON_AZIMUTH_DEG)
    return (-east, -north, -up)


# ── presets ──────────────────────────────────────────────────────────────────

PRESETS: Final = ("low", "medium", "high", "ultra")
AUTO: Final = "auto"
#: What the quality setting may hold.
QUALITY_CHOICES: Final = (AUTO, *PRESETS)
#: The presets ``AutoPreset`` moves between. Ultra is a choice a user makes: it adds
#: screen-space reflections and the largest shadow map for no gain in readability.
AUTO_LEVELS: Final = ("low", "medium", "high")


@dataclass(frozen=True, slots=True)
class PresetSpec:
    """What a preset costs — and nothing else. Measured values: ``ogp-3d-renderer`` §4."""

    name: str
    #: ``high`` (1024 texels), ``very_high`` (2048), ``ultra`` (4096).
    shadow_map_quality: str
    #: Cascade splits of the perspective view (the top-down truth view has none).
    shadow_cascades: int
    #: ``pcf4`` | ``pcf8`` | ``pcf16`` | ``pcf32``.
    soft_shadows: str
    #: 1024-texel maps at bias 5 left a sun-grazed roof acned and stair-stepped
    #: (33-40 % of the slope); 15 measured clean with the IoU gate unchanged. Low keeps
    #: 15 on its 2048 map. High and ultra: 10 — at the spike's 5 a sun-grazed LIT wall
    #: was hatched on Direct3D 11 (L1.4 round 2, RTX 4070, a wall at n.l 0.33: pixel
    #: noise 1.15 % of its luma and the face 3.7 luma darker; 8 and above: 0.18 %, the
    #: dither's own floor; a grazed top face needs 10 down to a 12-degree sun), with
    #: the shadow IoU unchanged (0.976 / 0.986 at 15 / 35 degrees).
    shadow_bias: float
    #: ``fxaa`` (a post effect, with specular anti-aliasing) | ``msaa``.
    antialiasing: str
    #: ``medium`` (2x) | ``high`` (4x) | ``very_high`` (8x) — MSAA's sample count.
    antialiasing_quality: str
    ambient_occlusion: bool
    ao_sample_rate: int
    glow: bool
    glow_high_quality: bool
    #: Screen-space reflections.
    reflections: bool
    #: Depth fog in the sky horizon's colour — at EVERY preset: without it low drew a
    #: one-row cliff where the meadow meets the sky (84.5 luma at golden hour).
    fog: bool = True
    #: Never: 0.08 overshot every thin lit edge into near-black dots (1,500-3,100
    #: isolated dark pixels per daytime frame), 0.03 is nearly as bad.
    sharpening: float = 0.0
    #: SSGI renders a black frame on Mesa llvmpipe: opt-in only, no preset turns it on.
    global_illumination: bool = False
    #: L4.5 (#388): a lawn's grass blades are drawn (they are built at every preset —
    #: a preset step changes no geometry — and shown from High up: they cost fill rate).
    lawn_blades: bool = False
    #: L4.5: how strongly the ground's shading follows its texture's luminance (detail
    #: normals derived from the baked ground itself, no new asset), 0 = flat.
    detail_normals: float = 0.0

    def __post_init__(self) -> None:
        if self.shadow_map_quality not in ("high", "very_high", "ultra"):
            raise ValueError(f"PresetSpec.shadow_map_quality: {self.shadow_map_quality!r}")
        if self.soft_shadows not in ("pcf4", "pcf8", "pcf16", "pcf32"):
            raise ValueError(f"PresetSpec.soft_shadows: {self.soft_shadows!r}")
        if self.antialiasing not in ("fxaa", "msaa"):
            raise ValueError(f"PresetSpec.antialiasing: {self.antialiasing!r}")
        if self.antialiasing_quality not in ("medium", "high", "very_high"):
            raise ValueError(f"PresetSpec.antialiasing_quality: {self.antialiasing_quality!r}")
        if not 0 <= self.shadow_cascades <= 3:
            raise ValueError(f"PresetSpec.shadow_cascades: {self.shadow_cascades!r}")


#: Low: a 2048 map with ONE cascade — Medium-sized without cascades stair-stepped and
#: acned the roof, and the 1024 map still cut ~25 px scallops of ~11 luma under the
#: ridge cap. 4x MSAA (L1.4 fix round 1, #529): FXAA let the picket fences alias into a
#: moiré — the fence's luma error against a 2x-supersampled render 20.0 (medium: 7.2) —
#: and 2x MSAA still 12.0, its dark-pixel share 18.8 % (medium 12.3 %); 4x: 6.2 and
#: 13.1 %. Its cost on the RTX 4070 (bench_large, a new frame's readback) is inside the
#: run-to-run spread (FXAA 23-28 ms, 4x 24-32 ms); on WARP 2x and 4x read 96-199 ms
#: against FXAA's 67-152 under a shared CPU. No ambient occlusion, no glow — fog stays.
#: Medium: the 2048 map too (it had 1024, smaller than low's): on bench_large it cost
#: +4 % of a WARP frame (183 -> 191 ms) and nothing measurable on the GPU (30-40 ms).
#: The ground's detail-normal strength from Medium up (L4.5). North-up with it is the
#: render tier's G2 gate (``test_scene3d_ground_render.py``, High preset); the board's
#: ``--edge`` and ``--orient`` probes render bare ground and do not run it.
DETAIL_NORMALS: Final = 1.0
PRESET_SPECS: Final[Mapping[str, PresetSpec]] = MappingProxyType({
    "low": PresetSpec("low", "very_high", 1, "pcf4", 15.0, "msaa", "high", False, 2, False,
                      False, False),
    "medium": PresetSpec("medium", "very_high", 1, "pcf8", 15.0, "msaa", "high", True, 2, True,
                         False, False, detail_normals=DETAIL_NORMALS),
    "high": PresetSpec("high", "very_high", 2, "pcf16", 10.0, "msaa", "high", True, 3, True,
                       False, False, lawn_blades=True, detail_normals=DETAIL_NORMALS),
    "ultra": PresetSpec("ultra", "ultra", 3, "pcf32", 10.0, "msaa", "very_high", True, 4, True,
                        True, True, lawn_blades=True, detail_normals=DETAIL_NORMALS),
})


def normalise_quality(value: object, default: str = AUTO) -> str:
    """A stored quality choice as one of ``QUALITY_CHOICES`` (anything else: ``default``)."""
    text = str(value).strip().lower() if isinstance(value, str) else ""
    return text if text in QUALITY_CHOICES else default


# ── the look ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SkySpec:
    """The inputs of ONE procedural sky texture. Two equal specs are the same sky."""

    #: Where the sky draws its sun (the plan's sun, elevation floored at
    #: ``SKY_MIN_ELEVATION_DEG``). Truth: the disc sits at the solar azimuth.
    sun_elevation_deg: float
    sun_azimuth_deg: float
    top: str
    horizon: str
    sun_disc: str
    #: The far end of the ground hemisphere; its horizon end is ``horizon``.
    ground_bottom: str
    sky_energy: float
    #: The sky's own energy, by day AND at night, with ``ground_curve`` 0.1: the sliver
    #: of ground hemisphere under a far-clipped meadow is drawn at the sky's horizon
    #: colour, so at any other energy it is a line. By day the spike measured 0.9 / 0.02
    #: as a 1-3 px dark line (dip 9-10 luma -> 0.1-0.2 at 1.0 / 0.1). At night the
    #: spike's 0.15 under a sky at 0.25 left the same line (L1.4 round 5, bench_small
    #: at eye height, 960 x 540: dip 2.07 / 1.04 luma at low / high -> 0.01 / 0.12;
    #: the fog step 2.51 / 2.50 -> 2.75 / 2.80; night luminance +0.2 %).
    ground_energy: float
    #: 0 at night: no disc (the moon is a light, not a picture).
    sun_energy: float
    night: bool
    ground_curve: float = 0.1


@dataclass(frozen=True, slots=True)
class ShadowSpec:
    """The key light's shadow settings: the preset's cost, the mood's softness."""

    map_quality: str
    cascades: int
    soft_shadows: str
    bias: float
    #: How dark a shadow is, 0-100. Night 25 (day 82): the fixed moon grazes a wall
    #: at n.l ~ 0.2 and the map stair-stepped there at 40.
    factor: float
    #: The blur radius of the filter. Night 8 (day 2), for the same staircase.
    pcf_factor: float


@dataclass(frozen=True, slots=True)
class MoodSpec:
    """The part of a look that follows the sun alone (no preset in it)."""

    #: Full night: the sun at or below ``TWILIGHT_DEG``.
    night: bool
    sun_color: str
    sun_brightness: float
    exposure: float
    probe_exposure: float
    #: Colour saturation of the graded frame. Night 0.6: 0.85 measured MORE saturated
    #: than noon (0.550 vs 0.537) — a dimmed day, not a night.
    saturation: float
    contrast: float
    #: How far into the night (``twilight_fraction``): 0 while the sun is up, 1 at
    #: night; in between the key light is the fading-in moon and the sky draws no sun.
    twilight: float = 0.0


@dataclass(frozen=True, slots=True)
class LookSpec:
    """Everything about a frame that is art direction — plain, comparable data.

    Made by ``look_for``; mapped onto the engine's scene by
    ``ui/view3d/quick3d/look.py``. Colours are ``#rrggbb`` sRGB unless the name says
    ``_linear``: the three colours that are DERIVED in linear light — and can be
    very dark, at night — are kept there, at full precision.
    """

    preset: PresetSpec
    mood: MoodSpec
    sky: SkySpec
    shadow: ShadowSpec
    #: Depth fog: the sky horizon x the sky's energy x probe exposure x
    #: ``FOG_OF_HORIZON`` (``fog_linear``).
    fog_linear: tuple[float, float, float]
    #: Where NO sky texture lights the view (the top-down truth view, the software
    #: fallback): a flat fill that stands in for the sky's light …
    fill_linear: tuple[float, float, float]
    #: … and the plain background: the fog's colour, so that the fogged meadow
    #: meets it without a line.
    plain_sky_linear: tuple[float, float, float]
    #: The night rig's key light travels along this (scene frame) — at night and in
    #: twilight, when the sun is down; None while the sun is up: then the key is the
    #: sun, whose direction is not part of any look.
    moon_travel_scene: tuple[float, float, float] | None
    meadow_albedo: str = MEADOW_ALBEDO
    wind_strength: float = WIND_STRENGTH

    @property
    def night(self) -> bool:
        return self.mood.night

    @property
    def fog_color(self) -> str:
        """``fog_linear`` as ``#rrggbb`` (to read and to compare; the engine gets the
        linear value)."""
        return linear_to_srgb_hex(self.fog_linear)

    @property
    def fill_color(self) -> str:
        """``fill_linear`` as ``#rrggbb``."""
        return linear_to_srgb_hex(self.fill_linear)

    @property
    def plain_sky(self) -> str:
        """``plain_sky_linear`` as ``#rrggbb``."""
        return linear_to_srgb_hex(self.plain_sky_linear)


#: Saturation and contrast of the graded frame by day (spike).
_DAY_SATURATION: Final = 1.06
_NIGHT_SATURATION: Final = 0.6
_CONTRAST: Final = 1.04
_DAY_SHADOW: Final = (82.0, 2.0)     # factor, pcf factor
_NIGHT_SHADOW: Final = (25.0, 8.0)
_DAY_GROUND_BOTTOM: Final = "#3c4d2e"
_NIGHT_GROUND_BOTTOM: Final = "#0a0f14"
#: The night sky is drawn at a quarter of its energy (spike); twilight ramps 1 -> this.
NIGHT_SKY_ENERGY: Final = 0.25


def look_for(sun: SunState, preset: str = "high") -> LookSpec:
    """The look of a frame under ``sun`` at ``preset`` (one of ``PRESETS``).

    Three phases. DAY while the sun is up (``sun.is_up``: at and above
    ``NIGHT_BELOW_DEG``, where the 2D shadows end): the day rig, the key light is the
    sun — and its DIRECTION is not in the look: the engine takes it from the
    ``SunState`` the pipeline sends, never from a look. TWILIGHT down to
    ``TWILIGHT_DEG``: the low-sun rig fades into the night rig (``twilight_rig``),
    the sky draws no sun, the key is the moon fading in. NIGHT below: the night rig.
    """
    if preset not in PRESET_SPECS:
        raise ValueError(f"unknown preset {preset!r}; choose from {list(PRESETS)}")
    cost = PRESET_SPECS[preset]
    t = 0.0 if sun.is_up else twilight_fraction(sun.elevation_deg)
    sun_down = not sun.is_up
    night = t >= 1.0
    rig = twilight_rig(sun.elevation_deg) if sun_down else day_rig(sun.elevation_deg)
    # the sky dims by its energy (the ground hemisphere at the same energy:
    # ``SkySpec.ground_energy``); it draws a sun only while the sun is up
    sky_energy = 1.0 + (NIGHT_SKY_ENERGY - 1.0) * t
    sun_energy = 0.0 if sun_down else 1.0
    factor, pcf_factor = _NIGHT_SHADOW if sun_down else _DAY_SHADOW   # the moon's, from 0.5°
    fog = fog_linear(rig.sky_horizon, rig.probe_exposure, sky_energy)
    return LookSpec(
        preset=cost,
        mood=MoodSpec(night=night, sun_color=rig.sun_color, sun_brightness=rig.sun_brightness,
                      exposure=rig.exposure, probe_exposure=rig.probe_exposure,
                      saturation=_DAY_SATURATION + (_NIGHT_SATURATION - _DAY_SATURATION) * t,
                      contrast=_CONTRAST, twilight=t),
        sky=SkySpec(
            sun_elevation_deg=max(float(sun.elevation_deg), SKY_MIN_ELEVATION_DEG),
            sun_azimuth_deg=float(sun.azimuth_deg) % 360.0,
            top=rig.sky_top, horizon=rig.sky_horizon, sun_disc=rig.sun_disc,
            ground_bottom=mix_linear(_DAY_GROUND_BOTTOM, _NIGHT_GROUND_BOTTOM, t),
            sky_energy=sky_energy, ground_energy=sky_energy, sun_energy=sun_energy,
            night=night),
        shadow=ShadowSpec(cost.shadow_map_quality, cost.shadow_cascades, cost.soft_shadows,
                          cost.shadow_bias, factor, pcf_factor),
        fog_linear=fog,
        fill_linear=fill_linear(rig.sky_top, rig.sky_horizon, rig.probe_exposure, sky_energy),
        plain_sky_linear=fog,
        moon_travel_scene=moon_travel_scene() if sun_down else None,
    )


#: What a host shows before anyone hands it a look: the noon rig at ``high`` — the
#: one look L1.2 had. (The sun position in it is a placeholder for a sky nobody
#: builds: a sky is built only from a look made for a real sun.)
NEUTRAL_DAY: Final = look_for(SunState(elevation_deg=60.0, azimuth_deg=180.0), "high")


# ── when the sky has to follow the sun ───────────────────────────────────────

#: A sky texture is rebuilt when the sun moved this far from where the SHOWN sky
#: draws it (great-circle degrees). The light, the exposure and the fog follow every
#: instant; only the picture of the sky — and the light probe filtered from it —
#: lags, by at most this.
SKY_REBUILD_DEG: Final = 1.0


def sky_separation_deg(first: SkySpec, second: SkySpec) -> float:
    """Great-circle angle between the suns two skies draw, degrees."""
    a = sun_direction_scene(first.sun_elevation_deg, first.sun_azimuth_deg)
    b = sun_direction_scene(second.sun_elevation_deg, second.sun_azimuth_deg)
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return math.degrees(math.acos(min(1.0, max(-1.0, dot))))


def sky_phase(sky: SkySpec) -> str:
    """``"day"`` (the sky draws its sun), ``"twilight"`` (no sun; its colours still
    follow the sun's elevation) or ``"night"`` (the night sky, whatever the sun does)."""
    if sky.night:
        return "night"
    return "day" if sky.sun_energy > 0.0 else "twilight"


def sky_is_stale(shown: SkySpec | None, wanted: SkySpec,
                 threshold_deg: float = SKY_REBUILD_DEG) -> bool:
    """True when the sky on screen must be rebuilt to show ``wanted``.

    No sky yet; the phase changed (``sky_phase``: sunset at 0.5°, the end of civil
    twilight at −6°, and back — the caller builds those at once); by day and in
    twilight, the sun moved ``threshold_deg`` or more (in twilight the sky draws no
    sun, but its colours follow the elevation: one rebuild per degree). A night sky
    is never rebuilt for the sun's position.
    """
    if shown is None or sky_phase(shown) != sky_phase(wanted):
        return True
    if wanted.night:
        return False
    return sky_separation_deg(shown, wanted) >= threshold_deg


# ── the auto preset ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AutoPolicy:
    """The numbers of ``AutoPreset``. Frame times in seconds per frame."""

    #: Slower than this — under 27 frames a second — is too slow (the budget is 30;
    #: the kill criterion of ADR-048 is 20).
    slow_frame_s: float = 1.0 / 27.0
    #: Faster than this — 50 frames a second and more — has headroom for a step up.
    #: Between the two nothing happens: the dead band.
    fast_frame_s: float = 1.0 / 50.0
    #: A decision needs this much continuous data.
    window_s: float = 3.0
    #: No step UP sooner than this after any change of preset.
    hold_s: float = 10.0
    #: After a step down from a level, that level is not tried again before this
    #: long — doubled every time it fails again, up to ``max_retry_s``.
    retry_s: float = 300.0
    max_retry_s: float = 3600.0
    #: Longer than this without a presented frame is NO DATA (the display asleep, a
    #: stall) — never "slow": what was collected before it is dropped, and measuring
    #: starts again with the next frame.
    stall_s: float = 10.0
    #: A decision needs at least this many samples, and "slow" is their MEDIAN: one
    #: hitch (a plan load that holds the GUI thread for some seconds) decides nothing.
    min_samples: int = 3

    def __post_init__(self) -> None:
        if not 0.0 < self.fast_frame_s < self.slow_frame_s:
            raise ValueError("AutoPolicy needs 0 < fast_frame_s < slow_frame_s (a dead band)")
        if min(self.window_s, self.hold_s, self.retry_s, self.stall_s) <= 0.0:
            raise ValueError("AutoPolicy times must be positive")
        if self.min_samples < 1:
            raise ValueError("AutoPolicy.min_samples must be at least 1")


class AutoPreset:
    """Chooses among ``AUTO_LEVELS`` from presented-frame counts. A state machine,
    no clock of its own and no Qt: the caller feeds it.

    ``observe(now_s, frames_presented)`` — POLLED while the view draws
    continuously (an animation runs): the cumulative count of presented frames at
    ``now_s``. It returns the new preset when it steps, else None. ``pause()`` when
    continuous drawing ends (hidden, the animation stopped): what was collected is
    dropped, so that a still view is never read as a slow one.

    A SAMPLE runs from one poll that saw a new frame to the next one that did:
    its frame time is its seconds over its frames, so time without any frame is
    in no sample's denominator — it either ends as a (long) frame time or, past
    ``stall_s``, as a gap.

    Rules: a decision needs ``window_s`` of samples and ``min_samples`` of them.
    It steps DOWN when their median frame time is above ``slow_frame_s``. It steps
    UP when every one of them is below ``fast_frame_s``, ``hold_s`` has passed
    since the last change — or since the FIRST poll, so a new session never steps
    up before it has held a level that long — and the level above is not barred. A
    level it had to leave is barred for ``retry_s``, doubling each time. No data
    never moves it.

    The bars outlive a session: ``bars`` seeds them — ``{level: (remaining_s,
    next_retry_s)}``, the seconds still to wait from the first poll and how long
    the next bar on that level will be — and ``bars_at(now_s)`` hands them back in
    the same form for the caller to store. Without that, "high is too slow, medium
    is fine" stepped up and down once in every session.
    """

    def __init__(self, start: str = "medium", policy: AutoPolicy | None = None,
                 bars: Mapping[str, tuple[float, float]] | None = None) -> None:
        self._policy = policy if policy is not None else AutoPolicy()
        self._level = AUTO_LEVELS.index(start if start in AUTO_LEVELS else "medium")
        self._seen: tuple[float, int] | None = None    # the last poll: (time, count)
        self._open: tuple[float, int] | None = None    # where the open sample began
        self._window: list[tuple[float, int]] = []     # closed samples: (seconds, frames)
        self._changed_at: float | None = None          # set at the first poll
        self._barred_until: dict[int, float] = {}
        self._retry_s: dict[int, float] = {}
        #: The seeded bars, waiting for the first poll to give them a time base.
        self._seed: dict[int, tuple[float, float]] = {}
        for level, (remaining, retry) in (bars or {}).items():
            if level in AUTO_LEVELS and math.isfinite(remaining) and math.isfinite(retry):
                # a stored bar never reaches further than the longest retry: a
                # hand-edited 1e18, or a wall clock that jumped, would bar a level for good
                self._seed[AUTO_LEVELS.index(level)] = (
                    min(max(0.0, remaining), self._policy.max_retry_s),
                    min(max(retry, self._policy.retry_s), self._policy.max_retry_s))
        #: Every step so far, as ``(now_s, from, to)`` — a diagnostic.
        self.steps: list[tuple[float, str, str]] = []

    def bars_at(self, now_s: float) -> dict[str, tuple[float, float]]:
        """Every level that was left for being slow: ``(seconds still barred from
        now_s — 0 once the bar is over, next bar's length)``. The next bar's length
        is kept after a bar is over: a level that fails again waits longer."""
        out: dict[str, tuple[float, float]] = {}
        for index, retry in self._retry_s.items():
            until = self._barred_until.get(index, now_s)
            out[AUTO_LEVELS[index]] = (max(0.0, until - now_s), retry)
        for index, (remaining, retry) in self._seed.items():   # not polled yet
            out.setdefault(AUTO_LEVELS[index], (remaining, retry))
        return out

    @property
    def preset(self) -> str:
        return AUTO_LEVELS[self._level]

    @property
    def policy(self) -> AutoPolicy:
        return self._policy

    def pause(self) -> None:
        """Continuous drawing ended: drop the open sample and the window."""
        self._seen = self._open = None
        self._window.clear()

    def observe(self, now_s: float, frames_presented: int) -> str | None:
        policy = self._policy
        if self._changed_at is None:       # the first poll: the session's time base
            self._changed_at = now_s
            for index, (remaining, retry) in self._seed.items():
                self._barred_until[index] = now_s + remaining
                self._retry_s[index] = retry
            self._seed.clear()
        seen = self._seen
        if seen is None or now_s < seen[0] or frames_presented < seen[1]:
            # the first poll — or a clock or a counter that began again (a fresh host)
            self.pause()
            self._seen = (now_s, frames_presented)
            return None
        self._seen = (now_s, frames_presented)
        began = self._open
        if frames_presented == seen[1]:  # no frame since the last poll
            if began is not None and now_s - began[0] > policy.stall_s:
                self._open = None        # a stall: no data, and what came before it is stale
                self._window.clear()
            return None
        self._open = (now_s, frames_presented)
        if began is None:
            return None                  # the first frame after nothing: a sample begins here
        seconds, frames = now_s - began[0], frames_presented - began[1]
        if seconds > policy.stall_s:
            self._window.clear()         # a gap ended by this frame: not a frame time
            return None
        self._window.append((seconds, frames))
        covered = sum(row[0] for row in self._window)
        while len(self._window) > policy.min_samples and covered - self._window[0][0] >= policy.window_s:
            covered -= self._window.pop(0)[0]
        if covered < policy.window_s or len(self._window) < policy.min_samples:
            return None
        times = sorted(row[0] / row[1] for row in self._window)
        median = times[len(times) // 2]
        if median > policy.slow_frame_s and self._level > 0:
            return self._step(now_s, -1)
        top = len(AUTO_LEVELS) - 1
        if (times[-1] < policy.fast_frame_s and self._level < top
                and now_s - self._changed_at >= policy.hold_s
                and now_s >= self._barred_until.get(self._level + 1, -math.inf)):
            return self._step(now_s, +1)
        return None

    def _step(self, now_s: float, direction: int) -> str:
        policy = self._policy
        before = self._level
        if direction < 0:  # this level proved too slow: bar it, longer each time
            wait = min(self._retry_s.get(before, policy.retry_s), policy.max_retry_s)
            self._barred_until[before] = now_s + wait
            self._retry_s[before] = min(wait * 2.0, policy.max_retry_s)
        self._level = before + direction
        self._changed_at = now_s
        self._window.clear()
        self.steps.append((now_s, AUTO_LEVELS[before], AUTO_LEVELS[self._level]))
        return AUTO_LEVELS[self._level]
