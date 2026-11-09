# The atmosphere sky at the painted horizon — values (#716, #719)

Follows reference 011 (the atmosphere sky, L7). Both issues are one problem: at and below the
6° haze band the painted sky shows (the fog meets the same horizon in every direction), and
above it the atmosphere's level must meet it. Decisions and the before/after tables: ADR-048,
addendum "L7.1"; lessons PF-L3D-22, PF-L3D-23. Measured with the board's `--sky-bands` phase
(Medium, 640 × 360, RTX 4070, a 300° sun; binned by world elevation, PF-L3D-19).

| Value | Where | Why |
|---|---|---|
| per-elevation profile: each ring of the clear atmosphere = the painted GRADIENT's luminance × one glow factor | `atmosphere_lut.sky_profile`, the sky-view table's alpha | one gain left the 6–15° band at 1.37–1.60× the painted sky over the azimuth (up to 2.1× toward a low sun), the zenith at 0.5–0.8×, and a low band brighter than the painted horizon below it: the sky darkened 16.7–21.9 luma toward 0.5° away from a low sun. Now 0.94–1.05× and no darkening |
| the gradient, not the painted ring MEAN | `atmosphere_lut.painted_gradient` | the painted disc's glow sits within about 25° of the sun; normalising on ring means spread it into a bright ring at the sun's elevation (10 % at a 60° sun, PF-L3D-22) |
| glow factor 1.000–1.047 | `atmosphere_lut._balance` | what the painted sky's sun adds to its gradient's light: with it the drawn sky still sends the painted sky's light onto the ground (model 1.0002–1.0003); largest at noon |
| gain over the sky AS DRAWN | `atmosphere_lut.atmosphere_gain` | through the haze band only the atmosphere's share counts; within 0.9 % of L7's bare ratio, so the clouds' calibration holds |
| deck sun-side ambient × (1 − 0.8 × cover) toward 0.5 | `atmosphere.frag` (`CLOUD_DIFFUSION`) | its sample is the clear sky's aerosol glow beside a low sun: a closed deck read 138 / 120 / 102 luma toward / across / away at a 0.5° sun; 126 / 120 / 119 after |
| deck level 1.48 by how closed the deck is | `look.ATMOSPHERE_DECK_LEVEL` | the deck 10° up read 11–14 luma under the painted haze band from noon to a 6° sun (painted / deck luminance 1.21–1.27 at 10°) |
| deck sunset shape (1 by day, 2.08 at 0°, 0.53 at −4°) for every deck | `look.ATMOSPHERE_DECK_SUNSET` | the example lights its clouds by its sun through a ground airmass, which dies faster than the painted sky dims: the deck fell to 0.29 of its noon luminance at a 0° sun, the painted sky to 0.6, then the clear sky's gain lifted it again in twilight (37–45 luma at sunset) |
| a deck = cloud ≥ 0.5 | `quick3d.look.DECK_FROM_CLOUD` | the overcast mood's own boundary (`weather.mood_of`) and where `sunAlpha` starts; Partly cloudy (0.4) keeps the light the owner accepted |

How the anchor was measured (do it again after any change to the clouds' light): render the
deck at two known factors per sun elevation, solve for the factor in the frame from the local
response (`ln out / ln factor` was 0.53–0.94), check once. Never invert `skyExposed` to get a
radiance: the frame passes the scene's tone mapping after it (PF-L3D-23).

What it looks like now: by day the atmosphere keeps its hue (the hazier blue, the warm sun
side, the violet twilight) at the painted sky's brightness per elevation; a sunset toward the
sun is an orange glow round the disc instead of a wide cream wash; an Overcast or Rain deck
meets the haze band with no band at any sun (−1.7 … 7.6 luma from 60° to −5°).

**Open for the owner** (not changed here): a Snow deck at a sun under 1° keeps the pink tint
of master — `cloudHueShare` = cover leaves 15 % of the deck's own red-lit colour, now on a
brighter deck (`skyband_snow_0.5_toward_medium.png`); the colour step at the haze line went
from ΔE 8.8 to 3.5 (the painted sky's own: 4.1). A full deck is as flat as on master.
