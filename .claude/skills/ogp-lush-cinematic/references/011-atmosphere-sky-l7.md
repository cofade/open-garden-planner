# The atmosphere sky — values and open taste questions (L7, #391)

Opt-in (Preferences → 3D View → Sky → Atmosphere with clouds); the painted sky stays the
default and the reference of every gate. The atmosphere only draws the sky: the painted sky
lights the garden under both models (PF-E3D-17, the owner's manual test: its own light crashed
Qt 6.12.0), so the garden's light never differs between the skies. Values (ADR-048 addendum L7
has the measurements):

| Value | Where | Why |
|---|---|---|
| haze band 6° | `look.ATMOSPHERE_HAZE_DEG` | at and below it the painted horizon shows: the fog meets the same horizon in every direction; 10° changed the far-horizon rows by < 0.05 luma |
| gain per sky | `atmosphere_lut.atmosphere_gain` | the painted sky's light on the ground (cosine-weighted upper hemisphere): the sky reads as bright as the light the painted probe casts — never brighten the atmosphere by hand |
| cloud light 0.064 × the atmosphere's gain | `look.ATMOSPHERE_CLOUD_GAIN`, `quick3d.look.cloud_light_gain` | a full Overcast lights the ground at noon as the painted Overcast (0.198 / 0.207, ~2 luma); the clouds take the one gain of the atmosphere — a scale of their own at a fixed high sun dimmed the deck twice (garden at a cloudy sunset 0.6–0.75 of painted) and deepened the horizon band |
| forward lobe × (1 − 0.8 × cover) | `atmosphere.frag` `CLOUD_DIFFUSION` | a thick deck diffuses: at full strength a full overcast was bright toward a low sun — a cloudy sunset at 0.96–1.0 of noon. Measured while the atmosphere still lit the garden: sunset over noon 0.750 / 0.776 / 0.668 against the painted 0.761 / 0.781 / 0.674. Since the revision the garden is lit by the painted sky, and the lobe shapes only the visible deck |
| silver lining × (1 − cover) | `atmosphere.frag` | the example's sun-side edge glow is an edge effect; at full strength across a thick deck it lit a cloudy evening |
| the deck's sunlight × (1 − twilight) | `atmosphere.frag` | the example clamps the sun's slant at the horizon: its deck kept the horizon sun down to −6° and a cloudy dusk brightened |
| cloud hue share 1 − (1 − cover) × (1 − closed) | `quick3d.look.cloud_hue_share`, `atmosphere.frag` | under a weather the deck is the weather's own grey (the example's clouds read beige to mustard); scattered clouds keep their own colour by the cover (0.4), Snow 0.955 — with the cover alone its deck read pink under a sun below 1° (reference 013) |
| cloud fade 120-240 km | `AtmosphereSky.qml` | the example's 80 km showed a bright stripe above the horizon |
| twilight weight 1 − twilight | `atmosphere_properties` | the night IS the painted night |
| Partly cloudy: cover 0.4, light 0.15, grey 0.25 | `weather.WEATHER_SPECS["partly_cloudy"]` | the owner saw no clouds: Clear has none and Overcast closes the deck. The cover sheet read scattered cumulus at 0.35 and 0.6. The sun stays out: at the full 0.4 share the painted sky read as a dull clear day (lawn lit/shadow 6.7 against 12.2), still a day mood |
| thin clouds' light × (1 + 4.2 × (1 − cover)²) | `look.ATMOSPHERE_THIN_CLOUD_LIFT` | the 0.064 was calibrated on a full deck; at 0.4 the noon clouds read as dark smoke. × 2.5 at 0.4, × 1 at Overcast and Rain, × 1.09 at Snow |
| disc 1 − max(cloud − 0.5, 0) / 0.5 | `atmosphere_properties` `sunAlpha` | the clouds themselves hide the disc; in a gap of a partial cover it stays whole |
| sky exposure 1 − exp(−c × e) | `atmosphere.frag` `skyExposed` | the skybox shader's curve, which Qt's screen path skips under our post effects: without it 1.8× too bright by day, 25–28 % of a low-sun frame clipped, no disc. Never replace it with a multiply: that leaves 13–14 luma by day |
| skybox Half | `AtmosphereSky.qml` `ScreenSpaceHalf` | drawn on screen per frame. At cover 0.4, 1280 × 720, sky-filled, three runs: 3.1-5.6 ms against Full's 4.5-8.9 (painted 2.1-2.3), and Half and Full look the same |
| aerosol turbidity 0.5 | `atmosphere_lut.EARTH_ATMOSPHERE` | the example's 1 read pale at noon and washed a camera facing a low sun to cream; 0.25 differed little more |
| disc energy × 4 | `look.ATMOSPHERE_DISC_ENERGY` | at × 1 the halo outshone the disc (240,239,237 under 248,244,230) and the sky probe found the glow 9° below the sun; at × 4 it reads the disc at 11.98° for a 12° sun; the ×4 is the core only — the glow around it keeps the painted disc's colour and energy (×4 there clipped a sunset disc to white) |

What it looks like: a hazier, more realistic blue than the painted sky, brightening toward the
horizon and the sun; a warm sunset band; a violet twilight; volumetric cumulus at partial
cover (Partly cloudy, 0.4), a grey deck at full cover.

**The mood order is read on the garden.** Facing a low sun, the atmosphere's whole frame reads its sunset brighter than its golden hour (the sun and its halo enter the frame) while the garden below darkens about a quarter, as under the painted sky. The render tier gates the order on `ground_luminance` (the rows below the horizon) on both skies, and on the whole frame on the painted sky only — no tolerance, no exemption.

**Known gaps** (#716, #719) are closed: the clear sky's low band and the cloud deck now meet the
painted haze band — reference 016 has the values. The probes now see both classes: the disc finder takes a clipped plateau (luma ≥ 250) of at least
20 pixels first (6°, 12°, 30° and 60° suns on both skies, worst 0.13° elevation error;
#717), and `--dusk` measures a sky-only camera at +1.0…−3° against its own elevation rows
(a dip over 10 luma fails; #695).

**Decided by the owner** (2026-11-03): keep the atmosphere, fix its crash, add Partly cloudy.
That also settles the cloudy-sunset question: the garden is lit the same under both skies.

**Open for the owner**: the default model; whether the atmosphere's hazier noon blue and its
cream sun-side glow at golden hour suit Lush Cinematic; a white-hot or a warm low sun disc; the
volumetric deck's structure or the painted sky's even grey under a full overcast.
