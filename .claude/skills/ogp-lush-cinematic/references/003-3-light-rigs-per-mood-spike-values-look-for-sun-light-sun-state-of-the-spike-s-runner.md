## 3. Light rigs per mood (*spike* values, `look_for` / `sun_light` / `sun_state` of the spike's `runner.py`, frozen in `tests/data/l0_spike_reference.json`)

**In production** (L1.4) the rig is DATA in `core/scene3d/look.py` (`NOON`, `GOLDEN`, `LOW_SUN`,
`NIGHT`, `day_rig`, `look_for(sun, preset) -> LookSpec`), ported with these values and pinned
against the spike's functions at every quarter degree until the spike retires. Deliberate
differences, each from a board: the night fog carries the night sky's energy (× 0.25); the
night sky's ground hemisphere is drawn at the sky's energy (0.25, the spike 0.15); and civil
twilight is a ramp (fix round 1) — the sun's key light goes where the 2D shadow overlay ends
(`core.shadow_geometry.MIN_SUN_ELEVATION_DEG`, 0.5°), night begins at −6° (`TWILIGHT_DEG`) — §7.

By day the rig is three **anchors** joined by **continuous ramps** (`runner._day_ramp`):
low → golden over 0.5° → 6°, golden → noon over 6° → 30°, the noon rig above. Every value
ramps — sun colour and brightness, sky top / horizon, sun disc, probe, exposure (fog follows
the horizon) — colours mixed in linear light, exposure in stops (log2), the rest linearly.
Night is a separate rig below 0.5°. Steps made moods jump: the sun colour at 15°/6° (a
14° December noon warmer than a 15° June golden hour), exposure 1.15 → 0.85 within a
degree at 20°, sky/fog/probe at 8° and 20°. The key light is **never brighter than at
noon** (a low sun crosses more air): the golden mood is its exposure and colour.

| Anchor | Sun elevation | Sun colour / brightness | Sky top / horizon (sun disc) | Probe / exposure |
|---|---|---|---|---|
| Noon | ≥ 30° | `#fff1dc` / 1.9 | `#3f78c9` / `#cfe2f2` (`#fff0d8`) | 0.55 / 0.85 (0.92 clipped a channel on 4.6 % of noon_low) |
| Golden | 6° | `#ffb878` / 1.9 (2.1 put a 2.03 sun into the 14° December noon and clipped the roof) | `#4f7fc8` / `#f4d2a6` (`#ffd09a`) | 0.50 / 1.15 |
| Low sun | 0.5° | `#ff9655` / 1.7 | `#4a6fb0` / `#f2b47c` (`#ffb070`) | 0.42 / 1.25 |
| Twilight (production, L1.4) | 0.5° → −6° | the low-sun rig mixed into the night rig by t = (0.5 − e) / 6.5 (colours in linear light, exposure in stops); the key light is the moon at 0.32 · t — none, and no shadow, just under 0.5° | mixed; no sun disc; sky and ground energy 1 → 0.25 | mixed; saturation 1.06 → 0.6 |
| Night | < 0.5° (spike), < −6° (production) | moonlight `#8ea4d6` / 0.32 from az 165°, elev 38°; soft faint moon shadows (factor 25, PCF 8); saturation 0.6 | `#070d22` / `#1b2747` (`#9fb2e0`) | 0.35 / 2.4 |

On the board (bench_small, Berlin): golden_hour 15.23° → sun `#ffd0a8` / 1.9, horizon
`#e7d8c8`, probe 0.519, exposure 1.024 (was 1.15: mean luma 109.8 → 105.2, low);
december_noon 14.04° → sun `#ffcda3` / 1.9, exposure 1.039 (clipped 2.45 → 1.56 → 0.27 % of
the frame, low; 1.11 → 0.45 → 0.27 % high — what is left is the south wall and the birch
trunk, near-white faces a 14° sun lights at n·l ≈ 0.97); sunset 5.89° → the golden anchor
(`#ffb777` / 1.896, exposure 1.152, probe 0.498); morning 26.16° → 0.892 (was 0.85); noon
60.9° and walk 42.2° keep the noon rig. A 15° "golden hour" is between rigs — truthfully
less golden than the 6° anchor, which `sunset` shows.

