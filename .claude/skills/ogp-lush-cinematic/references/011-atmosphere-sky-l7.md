# The atmosphere sky — values and open taste questions (L7, #391)

Opt-in (Preferences → 3D View → Sky → Atmosphere with clouds); the painted sky stays the
default and the reference of every gate. Values (ADR-048 addendum L7 has the measurements):

| Value | Where | Why |
|---|---|---|
| haze band 6° | `look.ATMOSPHERE_HAZE_DEG` | at and below it the painted horizon shows: the fog meets the same horizon in every direction; 10° changed the far-horizon rows by < 0.05 luma |
| gain per sky | `atmosphere_lut.atmosphere_gain` | the painted sky's light on the ground (cosine-weighted upper hemisphere); the sunlit grass reads the same under both skies — never brighten the atmosphere by hand |
| cloud gain 0.06 | `look.ATMOSPHERE_CLOUD_GAIN` | a full Overcast lights the ground as the painted Overcast (±5 luma at 50°/25°/8°); the deck reads a little darker than the painted grey — a cloud base |
| cloud hue share = cover | `atmosphere.frag` | under a weather the deck is the weather's own grey (the example's clouds read beige to mustard) |
| cloud fade 120-240 km | `AtmosphereSky.qml` | the example's 80 km showed a bright stripe above the horizon |
| twilight weight 1 − twilight | `atmosphere_properties` | the night IS the painted night |
| aerosol turbidity 0.5 | `atmosphere_lut.EARTH_ATMOSPHERE` | the example's 1 read pale at noon and washed a camera facing a low sun to cream; 0.25 differed little more |
| disc energy × 4 | `look.ATMOSPHERE_DISC_ENERGY` | at × 1 the halo outshone the disc (240,239,237 under 248,244,230) and the sky probe found the glow 9° below the sun; at × 4 it reads the disc at 11.98° for a 12° sun |

What it looks like: a hazier, more realistic blue than the painted sky, brightening toward the
horizon and the sun; a warm sunset band; a violet twilight; volumetric cumulus at partial
cover (the self-test's 0.7 reads best), a grey deck at full cover.

**Measured deviation:** facing a low sun, the atmosphere's sunset frame reads up to 1.9 %
brighter than its golden hour (its light sits toward the sun; the ground's light is the painted
sky's). The render tier allows that swap within 3 % on the atmosphere only.

**Open for the owner** (none decided): the default model; a "partly cloudy" weather (no preset
produces partial cover); whether the atmosphere's hazier noon blue and its cream sun-side glow
at golden hour suit Lush Cinematic.
