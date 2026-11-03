# The atmosphere sky — values and open taste questions (L7, #391)

Opt-in (Preferences → 3D View → Sky → Atmosphere with clouds); the painted sky stays the
default and the reference of every gate. Values (ADR-048 addendum L7 has the measurements):

| Value | Where | Why |
|---|---|---|
| haze band 6° | `look.ATMOSPHERE_HAZE_DEG` | at and below it the painted horizon shows: the fog meets the same horizon in every direction; 10° changed the far-horizon rows by < 0.05 luma |
| gain per sky | `atmosphere_lut.atmosphere_gain` | the painted sky's light on the ground (cosine-weighted upper hemisphere); the sunlit grass reads the same under both skies — never brighten the atmosphere by hand |
| cloud light 0.06 at a 50° sun, make-up 0.7 | `look.ATMOSPHERE_CLOUD_GAIN`, `look.ATMOSPHERE_CLOUD_MAKEUP`, `quick3d.look.cloud_light_gain` | a full Overcast lights the ground at noon as the painted Overcast (0.211 / 0.207); toward sunset the clear sky's gain rises ~7× to make up for the physical sky's dimming, but the deck dims less — the whole make-up lit a cloudy sunset at 0.83–0.87 of noon (1.0 before the twilight and silver fades), none dimmed it twice (0.47–0.59). At 0.7 a cloudy evening dims as under the painted sky (sunset over noon 0.740 / 0.772 / 0.621 against 0.761 / 0.781 / 0.674); the garden at a cloudy sunset reads ~¼ darker than painted — owner's call |
| silver lining × (1 − cover) | `atmosphere.frag` | the example's sun-side edge glow is an edge effect; at full strength across a thick deck it lit a cloudy evening |
| the deck's sunlight × (1 − twilight) | `atmosphere.frag` | the example clamps the sun's slant at the horizon: its deck kept the horizon sun down to −6° and a cloudy dusk brightened |
| cloud hue share = cover | `atmosphere.frag` | under a weather the deck is the weather's own grey (the example's clouds read beige to mustard) |
| cloud fade 120-240 km | `AtmosphereSky.qml` | the example's 80 km showed a bright stripe above the horizon |
| twilight weight 1 − twilight | `atmosphere_properties` | the night IS the painted night |
| aerosol turbidity 0.5 | `atmosphere_lut.EARTH_ATMOSPHERE` | the example's 1 read pale at noon and washed a camera facing a low sun to cream; 0.25 differed little more |
| disc energy × 4 | `look.ATMOSPHERE_DISC_ENERGY` | at × 1 the halo outshone the disc (240,239,237 under 248,244,230) and the sky probe found the glow 9° below the sun; at × 4 it reads the disc at 11.98° for a 12° sun; the ×4 is the core only — the glow around it keeps the painted disc's colour and energy (×4 there clipped a sunset disc to white) |

What it looks like: a hazier, more realistic blue than the painted sky, brightening toward the
horizon and the sun; a warm sunset band; a violet twilight; volumetric cumulus at partial
cover (the self-test's 0.7 reads best), a grey deck at full cover.

**The mood order is read on the garden.** Facing a low sun, the atmosphere's whole frame reads its sunset brighter than its golden hour (the sun and its halo enter the frame) while the garden below darkens about a quarter, as under the painted sky. The render tier gates the order on `ground_luminance` (the rows below the horizon) on both skies, and on the whole frame on the painted sky only — no tolerance, no exemption.

**Known gaps** (filed): the low band reads 1.43–1.83× the painted sky's luminance — a cream
wash and a horizon that darkens toward 0.5° (#716); the sky probe's disc finder misses an 8° sun
(#717).

**Open for the owner** (none decided): the default model; a "partly cloudy" weather (no preset
produces partial cover); whether the atmosphere's hazier noon blue and its cream sun-side glow
at golden hour suit Lush Cinematic; whether a cloudy sunset's garden may read a quarter darker
than under the painted sky.
