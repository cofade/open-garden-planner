# The living garden — weather, dew and life values (L5, #389, ADR-070)

The values of `core/scene3d/weather.py`, chosen on the L5 board (`render_beauty_board.py
--living`) and the reasons they hold. Truth first: none of them moves the sun or a shadow.

| Look | Value | Why |
|---|---|---|
| Overcast sky | towards a cool grey (hue 0.94 / 0.99 / 1.07, luminance 1) whose horizon is as bright as the clear horizon, top x0.78 | a cloudy noon is no dusk; a cloudy night no brighter than a clear one |
| Overcast key light | x0.22; shadow factor x0.30, PCF factor → 8 | the sun behind a layer: soft, faint shadows where the sun says |
| Overcast grade | probe x1.45, +0.15 EV, saturation x0.80 | the first board (x0.86, +0.30 EV) read as a slightly dim clear day |
| Rain | overcast + wetness 1 (leaves roughness 0.38, specular 0.6, x0.88), ground x0.78 / roughness 0.55 / specular 0.40, haze 0.6, wind 5.0 | wet and dark, a nearer haze |
| Snow | cloud 0.85, snow cover 0.75 (meadow, tiles, leaves) toward (0.80, 0.84, 0.89) linear, haze 0.55, wind 1.5 | the snow ground meets the meadow without a step: one target colour |
| Morning dew | full to 6°, gone at 18°, east of the meridian: haze x0.62, wetness 0.6, saturation x0.94 | a mist and a sheen, not a new sky |
| Particles | rain streaks 28–52 cm (≥ 6 px), flakes 1.4–2.6 cm (≥ 1.6 px), leaves 7–11 cm (≥ 3 px), butterflies 5–7.5 cm | legible at board distance, never thinner than a pixel |
| Garden lights | `#ffc98a`, brightness 7, quadratic fade 3.5; bulbs glow (2.6, 1.7, 0.75) x1.6 | a pool of a few metres; 1.0 lit the whole lawn |

Butterflies only at plants in flower up to 3.5 m: on the first board they fluttered over a
tall tree's crown against the sky.
