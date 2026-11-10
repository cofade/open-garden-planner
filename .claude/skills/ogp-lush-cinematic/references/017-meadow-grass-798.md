# The meadow's grass — values (#798)

The meadow round the plan, and the plan's OPEN ground (no item covers it), were one flat
colour: 73–80 % of the default framing was flat green (the 3D survey's felt table; local luma
std of the meadow 0.54–0.62). Decisions and the before/after tables: ADR-048 addendum "the
meadow's grass"; lessons PF-L3D-30, PF-L3D-31; engine facts: `ogp-3d-renderer` reference 027.
Measured with the board's `--meadow` phase (High, the noon shot's sun, RTX 4070).

| Value | Where | Why |
|---|---|---|
| ONE shader for every piece of ground: tiles, bare plan rectangle, meadow | `Garden.qml` (`ground.frag` three times), `test_quick3d_qml.py` | the plan's edge is the same function on both sides: no step to tune away |
| the canvas's GRASS texture, untinted, one texel a centimetre, in WORLD space | `core/scene3d/meadow.py` `GRASS_REPEAT_CM`, `ground.frag` `grassUvA` | no new asset (`ogp-asset-forge`); its own hue spread (blades, dry tips) is what a lawn painted with the tinted pattern does not have, so open ground and a planned lawn stay apart by colour |
| linear colour over its own mean, RGBA16F | `meadow.grass_detail`, `GrassDetailTexture` | the mean is the meadow's albedo at every distance and mip; 8-bit sRGB mips would make minified grass 1.7 % darker (PF-L3D-30) |
| its mottle taken out: Gaussian sigma 16 cm, wrapped | `meadow.GRASS_HIGH_PASS_CM` | the mottle repeats every 2.56 m and drew a lattice seen from 60 m above (folded amplitude 2.15 luma; after: 0.86, no visible lattice) |
| sampled twice: as it lies, and turned 37° at 1.618×, summed around the mean (× 0.707) | `ground.frag` `grassUvB` | the variance of one sample, the repeat of neither |
| brightness 4 % at 3.1 m, 6 % at 9 m, 7 % at 41 m; hue 3.5 % at 17 m (value noise −1..1, each octave turned) | `meadow.GRASS_VARIATION` | stands in for the mottle without repeating; about ±7 % brightness and ±3° hue at two sigma (the issue asked ±7 % / ±4°). Rounds 2 and 3 (9 / 41 m at 4.5 / 5.5 % against 6 / 7 %) read the same flat share (13.3 / 13.1 %); 3 kept for a little more far variation |
| each octave fades as a pixel's reach on the ground grows from 0.05 to 0.15 of its wavelength | `ground.frag` `meadowOctave` | value noise has no mips; without it the board's distant-horizon rows read 3.80 at 403 m / 15° (flat 3.48, gate 3.6); with it 3.48, and the far meadow is the flat mean |
| relief 0.2 per unit of `detailNormals` | `meadow.GRASS_RELIEF` | the texture is a linear ratio around 1 where the tiles read sRGB codes around 0.43, and a ratio swings about 2.2× its code |
| the truth view flat | `Garden.qml` `groundSurface` | IoU and north-up measure against flat ground |
| Low without the variation (`MEADOW_GRASS`), Medium and up with it | `look.PRESET_SPECS` | on the software adapter (the compatibility mode is Low) the value noise cost 2.1 ms of a 960 × 540 frame; the flat share at Low 0.135 without it, 0.125 with it |
| the weather in the shader only | `weather.apply_weather` leaves `meadow_albedo` | the meadow takes the ground's one tint (rain) and cover (snow), as the tiles always did |

What it looks like: from the default framing a grass field with soft patches, fading into the
fog; at eye height grass with blades where the plan has open ground, and a planned lawn beside
it is lighter and lime (its own fill colour) with its blades at High — a lawn edge, not a
football pitch against felt. The remaining flat share of the default framing (0.0–13.7 % at
1280 × 720, 0.0–5.9 % at 1080p) is the fogged band at the top: the haze flattens it, as it
should. The far meadow flickers 0.23–0.33 luma RMS in an orbit and 0.09–0.10 in a low flight
(flat 0.03–0.10; without mipmaps 3.4 / 5.4).

Open for the owner (not decided): whether the plan's open ground takes the grass at all
(`look.OPEN_GROUND_GRASS`; at L0 the owner kept "unplanned ground" flat as "an honest 'no lawn
here'"), and whether the meadow should be less saturated than the noon lime it shares with
`MEADOW_ALBEDO`.

Under the owner's veto (`OPEN_GROUND_GRASS = False`) the plan's open ground is flat beside the
varied meadow: the twin edge probe reads a step of 1.84 and a line of 7.5 there, so the edge
gate as it stands would fail — a veto needs the gate (or the meadow's variation near the plan)
adjusted too.
