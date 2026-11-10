# The living garden's polish — occlusion under cloud, snow on built tops, leaves, lamp pools (#687)

The values #687 added to the living garden (`core/scene3d/weather.py`, `particles.py`,
`lights.py`, `qml/built_snow.*`) and the reasons they hold, measured on the board's `--living`
shots (high, 1280 x 720, family garden; the occlusion phase `living_occlusion`). Truth first:
none of them moves the sun, a shadow, a plant or a date; clear frames are unchanged.

| Look | Value | Why |
|---|---|---|
| Occlusion under cloud | the weather's light share of strength 55 → 99, reach 14 → 70 cm, bias 0 → 21 cm (overcast and rain 1.0, snow 0.85, partly cloudy 0.15); clear 55 / 14 / 0 | under cloud the sky is the light, and the sky an object hides grounds it; the bias at 0.3 of the reach ends the flat ground's self-occlusion (rim 9.5-10 → 1.2-2.1; snow's lawn 17 → 2.9 under Low) — at 0.5 of the reach the pass did nothing for a caster's foot |
| An overcast box's foot | lit side 0.031 → 0.040 (clear 0.022), shadow side 0.063 → 0.044 | the gate compares LIT sides: there occlusion alone darkens in both looks; the clear shadow side's 0.49 is the cast shadow, which no weather may imitate. The geometry predicts 0.10-0.17 for a sky-lit day; Qt's pass cannot give more without the rim |
| Snow on built tops | `built_snow` 1 under snow (full where the meadow's 0.75 shows grass), mixed by `smoothstep(0.35, 0.75, NORMAL.y)`, the snowy ground's roughness 1.0 and specular 0.15, the colour `SNOW_LINEAR` | a roof, a deck, a bed's soil or the trampoline's mat lies white under a fall; at 0.75 a terracotta roof read pink and the mat lilac; a 45° roof holds nearly all, a 60° one a third, a wall none |
| Not snow-covered | a building's floor (under its roof), glass, water | Cutaway would show snow indoors; whether a glasshouse is heated or a pond frozen is not in the plan |
| A falling leaf | eight samples of its own crown's Forge colours (outer, upper leaves) × the season's tint, seeded by the item id | the style table forbids a palette literal; the old amber / rust / ochre gave a red maple amber leaves |
| A lamp's pool at the edge of the lit six | × `smoothstep(0, 200 cm, d_out − d)` | at a swap of the sixth and seventh both are dark: no pool switches in one frame; no clock, so a tour repeats |
| A dew mist | none | Qt's height fog fogged the ground at the camera's feet as fully as the far garden (+121.6 levels at the bottom of the frame at any density): a slab, the look the brief forbids |

Taste calls left to the owner (none of these was said by the owner): full snow on built tops
(against the meadow's 0.75); partly cloudy keeps a 4.9-level rim (clear 8.0) because it takes
only 0.15 of the overcast's occlusion; the clear look keeps the spike's occlusion and its 8-level
rim (changing it changes every clear frame).
