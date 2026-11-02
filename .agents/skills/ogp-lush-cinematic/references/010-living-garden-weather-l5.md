# The living garden — weather, dew and life values (L5, #389, ADR-070)

The values of `core/scene3d/weather.py`, chosen on the L5 board (`render_beauty_board.py
--living`) and the reasons they hold. Truth first: none of them moves the sun or a shadow.

| Look | Value | Why |
|---|---|---|
| Overcast sky | towards a cool grey (hue 0.94 / 0.99 / 1.07, luminance 1) whose horizon is as bright as the clear horizon, top x0.78 | a cloudy noon is no dusk; a cloudy night no brighter than a clear one |
| Overcast key light | x0.22; shadow factor x0.30, PCF factor → 8 | the sun behind a layer: soft, faint shadows where the sun says |
| Overcast grade | probe x1.45, +0.15 EV on NOON's exposure by day (towards night the mood's own: by twilight), saturation x0.80 | the first board (x0.86, +0.30 EV) read as a slightly dim clear day; the low sun's lift (+0.44 EV at a golden hour) makes up for the clear key light — inherited, an overcast sunset was 98 % as bright as noon |
| Rain | overcast + wetness 1 (leaves roughness 0.6, specular 0.6, x0.88 — at 0.38 a low sun left cream glints on wet leaves), ground x0.78 / roughness 0.8 / specular 0.25, haze 0.6, wind 5.0 | wet and dark, a nearer haze; roughness is the lever: at 0.55 a low sun left a cream glint on the wet meadow and a 1.75-luma plan-edge step (specular did not move it) |
| Overcast sun | the disc's colour fades into the horizon by cloud; its ENERGY stays | Qt's procedural sky blends the disc towards colour x energy: energy 0 drew a black sun |
| Set sun (below 0.5°) | the disc is the horizon's colour at the sky's own energy, in every weather | energy 0 drew a black disc through all of twilight; energy 1 left a glow |
| Fog under cloud | x (1 + cloud x (-0.045 by day ... +0.23 at night, by twilight)) | the clear sky's `FOG_OF_HORIZON` drew a 4-luma seam on the overcast horizon (fitted on `--living --horizon`) |
| Snow | cloud 0.85, snow cover 0.75 (meadow, tiles, leaves) toward (0.80, 0.84, 0.89) linear, haze 0.55, wind 1.5 | the snow ground meets the meadow without a step: one target colour |
| Morning dew | rises over 4° from dawn (-6°), full to 6°, gone at 18°, east of the meridian and fading over the last 25° of azimuth before the PLACE's noon (due north south of the equator; a summer dawn north of 60° stands near the other meridian), and rising over the first 15° after solar midnight: haze x0.62, wetness 0.6, saturation x0.94 | a mist and a sheen, not a new sky; a dawn is no switch, nor a winter noon, nor a white night's midnight (Tromsø's dew switched 0 -> 1 in a frame) |
| Particles | rain streaks 28–52 cm (≥ 1.3 px wide, alpha 0.27), flakes 1.4–2.6 cm (≥ 2.6 px), leaves 7–11 cm (≥ 3 px, tumbling well out of the horizontal), butterflies 5–7.5 cm (wings in a 0.9-rad V at rest, the white a cream 0.70 / 0.70 / 0.64), fireflies under 2.5 m | legible at board distance, never thinner than a pixel; at 0.9 px streaks broke into dashes, flat leaves read as dashes, a flat white wing as a blade |
| Life shares | a COUNT: a particle whose seed lies above the share shrinks away over a band of 1/12; only the bulbs' glow fades by it | an opacity lifted a dark lawn by 39 luma (ghost butterflies); a hard cut popped; a firefly dimmed too faded as the share squared |
| Near the camera | a leaf or butterfly's SIZE ramps to 0 by its anchor's depth, 2.5 m → 1.5 m | a per-vertex cut tore wings into slivers; closer bands read a cabbage white as a blade |
| Garden lights | `#ffc98a`, brightness 9.4, constant fade 4, quadratic fade 3.5, the light 3 cm under the lantern; bulbs glow: a hot centre (2.6, 1.7, 0.75) x1.6 inside r 0.35 in a warm halo (1.0, 0.48, 0.13), 6 cm towards the camera; the lantern has no pane | a pool of a few metres; 1.0 lit the whole lawn; inside the bulb it drew white heads with dark cores; a pane lit by its own lamp drew a cream box |

Butterflies only at plants in flower up to 3.5 m: on the first board they fluttered over a
tall tree's crown against the sky.

While an Analyze drape lies on the ground the weather and the dew pause (the look is the
sun's own): under snow the hours-of-sun drape's saturation fell to 0.31 of clear and its hue
moved up to 59° — a drape is read against its legend, so nothing may recolour the ground
under it (3D review of L5, P0).
