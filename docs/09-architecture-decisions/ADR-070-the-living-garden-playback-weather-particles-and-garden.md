---
id: ADR-070
title: "The living garden — playback, weather, particles and garden lights"
status: "Accepted (issue #389, epic #383) — all four slices, the two optional ones included. Shipped in v1.35.0 ([PR #699](https://github.com/cofade/open-garden-planner/pull/699)) after the owner's manual acceptance (two rounds; 2026-11-02)."
refs: ["Phase 17 L5", "#389"]
legacy_anchor: adr-070-the-living-garden--playback-weather-particles-and-garden-lights-phase-17-l5-389
---

# ADR-070: The living garden — playback, weather, particles and garden lights

**Status**: Accepted (issue #389, epic #383) — all four slices, the two optional ones included. Shipped in v1.35.0 ([PR #699](https://github.com/cofade/open-garden-planner/pull/699)) after the owner's manual acceptance (two rounds; 2026-11-02).

**Context**: After L4 the 3D view showed the plan's garden in a mood that followed the sun's
height alone (`core/scene3d/look.py`, ADR-059 addendum L1.4), with wind as a shader clock and a
reduced-motion setting. Issue #389 asked for year and day playback through the shared
`SimClock` (ADR-053), named moods (morning dew, golden hour, overcast, night), weather presets
and particles (rain, snow, autumn leaves, butterflies at flowering plants, fireflies on summer
evenings) with three gates — at most 5,000 particles, at most 15 % of the frame at Medium,
and with reduced motion an idle frame counter of 0 — and, optionally, "today's weather" only
when the plan date is today and garden lights as a new object type (2D sprite, §8.23
registration, 3D light). The forces: truth before beauty (no weather may move a sun or a
shadow), the engine rules L1–L4 paid for (a destroyed Model leaves graphics state behind —
ADR-060; a light that comes and goes recompiles every lit material), the software adapter's
cost (nothing animates there), and one canonical path per behaviour.

**Decision**:
1. **Playback is a writer of the one clock.** `core/playback.py` is the Qt-free arithmetic of
   one step: the DAY mode advances the time of day and wraps at midnight onto the SAME date (no
   `date_changed`); the YEAR mode advances the plan date at the same time and wraps inside the
   plan's year. Three speeds (5 / 10 / 30 minutes, 1 / 2 / 7 days per 200 ms step; "normal"
   day = Phase 14's Animate). The Plan & Sun toolbar's Animate button carries the choice
   (`SunSimToolbar`, a menu on the button) and writes through its existing paths — the slider
   (time) and `date_requested` (date) — so the 2D overlay, the hours-of-sun map, the 3D light
   and the 3D growth follow on their own subscriptions; the 3D regrowth stays throttled by
   `DATE_REGROW_MIN_MS`. Session state only, like the sim moment (FR-SUN-04).
2. **Weather is a LOOK.** `core/scene3d/weather.py`: `living_look(sun, preset, weather) =
   apply_weather(look_for(sun, preset), weather, sun)`. Overcast greys the sky towards a hue
   whose horizon is as bright as the clear one (a cloudy night stays a night), hides the disc,
   cuts the key light to 22 % and its shadows to 30 % darkness with a softer filter, raises the
   probe and the exposure a little and lowers saturation; rain adds wetness, a nearer haze and
   more wind; snow a snow cover. The sun's direction is not in a look and the moon is unchanged;
   a clear look outside the morning is `look_for`'s field for field except the new
   `LookSpec.atmosphere` (pinned). The 2D sun study, the hours-of-sun map and every truth gate
   read clear geometry and are unaffected. A new weather's sky is built at once
   (`look.sky_must_build_now`, `SkySpec.cloud`); `sky_phase` is now read from the sun's
   elevation, not the disc's energy, so an overcast day is still day.
3. **Moods are names of the look.** `weather.mood_of(look, sun)` — night, twilight, rain, snow,
   overcast, morning dew, golden hour (a clear sun at or below 12°), day — read from the look so
   the name can never disagree with the picture. Morning dew is east of the meridian (azimuth in
   (0°, 180°) at every latitude) from the end of civil twilight until the sun is 18° up: a
   nearer mist, a wet sheen on leaves and blades, a little less colour.
4. **Particles are geometry a shader moves.** No CPU simulation and no Qt Quick 3D particle
   module: `core/scene3d/particles.py` builds two buffers — the precipitation (3,600 seeded
   quads, the same for every plan) and the ambient life (falling leaves under turned trees and
   shrubs that are dropping them, butterflies at plants in flower up to 3.5 m tall, fireflies in
   the hemisphere's midsummer, and the bulbs of the garden lights) — each loaded into ONE
   declared Model for the scene's life (`ReloadableGeometry`, like the selection ring).
   `precipitation.vert` / `ambient.vert` place every particle from its seeds and the WIND'S
   CLOCK (`windTime`). So the L1.4 animation policy runs them: hidden, nothing ticks; reduced
   motion rests the clock at 0 — every particle stands where its seed puts it, a photograph,
   and an idle view presents no frame; the compatibility mode draws them still. Rain and snow
   are world-anchored in a box around the camera's target (`precipitation_volume`), so an orbit
   never drags them. WHICH plants have life is the buffer's (rebuilt with the plants'
   phenology, i.e. at most twice a second during a date playback); WHEN it shows — by day, dry,
   at dusk — is the look's (`AtmosphereSpec.leaves / butterflies / fireflies / lamps`), a
   uniform, so a time-of-day step rebuilds nothing. Budget: precipitation 3,600 + leaves 560 +
   butterflies 80 + fireflies 360 + bulbs 360 = 4,960 ≤ 5,000 (pinned).
5. **Wind is a shader value the weather sets.** `LookSpec.wind_strength` (clear 2.5 — L1.4's —,
   overcast 3.5, rain 5, snow 1.5) sways foliage and grass; `AtmosphereSpec.wind_drift_scene`
   carries rain, snow and leaves (from the west-south-west). No meteorology is claimed.
6. **Wet and snowy ground is ONE set of values.** The meadow, the bare plan and both tile
   materials bind the same `groundRoughness` / `groundSpecular` / `groundTint` (and the tile
   shader `snowCover`), so the plan meets the meadow without a step in every weather (the L1.4
   plan-edge rule). Roofs and a bed's soil (principled `vc` parts) are not snow-covered — an
   accepted limitation (amended by the #687 addendum below: built tops lie under snow).
7. **Today's weather follows the app's forecast, only on today.** The Planting Calendar's
   weather widget already fetches Open-Meteo's daily forecast; `forecast_days_ready` fans its
   `(ISO date, WMO code)` days out to the workspace (no second fetch, nothing from the 3D view to
   the network). `weather.todays_weather` maps the plan date's code — only when the plan date is
   today — onto a preset (`weather_from_wmo`: 0–2 clear, 3/45/48 overcast, drizzle/rain/showers/
   storms rain, snow and snow showers snow); on any other date "Today's Weather" shows clear and
   its tooltip says why.
8. **Garden lights are objects, their light a fixed pool.** `GARDEN_LIGHT` (circle tool, a
   lantern on a post) and `STRING_LIGHTS` (a LINE, drawn like a fence: a post at every point,
   the wire hanging between them — the owner's addendum below) are registered on every §8.23
   surface (default heights 110 / 250 cm; the lantern's sprite from
   `scripts/generate_object_sprites.py`, the string drawn by the canvas) and built by
   `builders/lights.py`. Where a bulb is is ONE function per kind (`lantern_bulb`,
   `string_bulbs` — the string's from `core/string_lights.layout`, which the canvas draws
   too), read by the builder that places the bulb and by `core/scene3d/lights.py` that makes
   it glow (an ambient `bulb` particle) and light (`pose_points`, the Model's own pose). The scene declares `lampSlots` (6) point lights once;
   the nearest six lamps to the camera's target light the garden after dusk
   (`AtmosphereSpec.lamps` ramps in over twilight), the rest glow. No point-light shadows.
   `foliage.frag`, `foliage_door.frag` and `lawn.frag` gain a `POINT_LIGHT` that lights leaves
   the way their `DIRECTIONAL_LIGHT` does.

**Alternatives considered**:
- *Qt Quick 3D's `ParticleSystem3D`.* A CPU simulation per frame, a further QML module to
  bundle and pin in the frozen exe, and particles that tick on their own clock — a second
  animation policy to keep in step with reduced motion and with a hidden pane. The shader route
  reuses the clock the policy already owns.
- *Weather in the sun study.* Rejected by the truth principle: shading in 2D is a geometric
  analysis of where the sun's direct light falls; a cloudy day does not move a shadow.
- *A light per lamp.* Every visible light is computed for every lit pixel and changes the shader
  of every lit material; a plan with dozens of lamps would recompile and slow the view. Six
  nearest, the rest glowing, keeps the cost bounded.
- *Persisting the weather.* The sim moment is not persisted (FR-SUN-04); the weather is part of
  that simulated moment, so every session starts clear.

**Consequences**: New modules `core/playback.py`, `core/scene3d/weather.py`, `particles.py`,
`lights.py`, `builders/lights.py`, `ui/view3d/workspace_living.py`; shaders
`precipitation.vert/.frag`, `ambient.vert/.frag`; two object types added to `ObjectType`
(appended) and `ToolType` (beside the other furniture tools — `ToolType` values are never
persisted; `ObjectType` NAMES are serialized — no `FILE_VERSION` bump: an older version loads
a garden light as a generic shape, but a string as a fence, because its loader gives every line
of an unknown type `ObjectType.FENCE` (`project.py`, `object_type or ObjectType.FENCE`) — a
120 cm fence that casts a 2D shadow, builds as a fence in 3D, and stays one if saved
there); one sprite, the lantern's (§8.23 now 25 artifacts; the string is a line drawn by
the canvas); `bench_built.ogp` gained one of each (appended last, every earlier id and seed
kept; the string's middle post moved from y 1290 to y 1210 after the owner's manual test,
where the old point stood inside the deck at y ≥ 1260). `LookSpec` gained `atmosphere`
(`CLEAR_STILL` by default), `SkySpec` `cloud`. Measured (RTX 4070, Direct3D 11, bench_small at
1280 × 720, Medium, interleaved readbacks): clear with life +0.6 %, snow +1.9 %, rain +3.7 % of a
frame; with reduced motion 0 frames over 2.5 s after the first build. A garden light's
3D shadow is a small share of its solid 2D prism, as every open object's without a porosity
model is — a pergola's about a quarter, a swing's about a sixth; #440 gave one to fences
only, its roof projection to buildings; the open objects' is #698 — the shadow table of
ADR-059's builders addendum. A string of lights casts no 2D shadow at all (the owner's
addendum). Tests:
`tests/unit/test_playback.py`, `test_scene3d_weather.py`, `test_scene3d_particles.py`,
`tests/unit/test_string_lights.py`, `tests/integration/test_living_garden.py` (§8.10),
`tests/integration/test_string_lights_line.py` (the string as a line: the tool, its 2D
picture, no 2D shadow, Change Type and undo, 2D and 3D bulbs at one place however it is
turned), the render tier
`tests/integration/test_living_garden_render.py` (the two issue gates and the board), the
Beauty Board's `--living` shots, and the frozen `--selftest`: a second small frame — a rainy
night with one garden light, in perspective — compiles the particle shaders and the point-light
path from the bundle and must show the lamp's warm glow (`selftest.judge_living_frame`; a broken
particle shader fails it, `test_quick3d_selftest.py`). Cross-refs: FR-3D-LIVE-01 … 09, §8.29.13, §8.10.16,
PF-L3D-18.

**Addendum (3D review of the L5 board, before the draft PR)**: The `ogp-3d-reviewer`'s first
pass rejected the board: one P0 and three P1s. Truth was intact (38 truth frames bit-identical
to the merge base but two pixels by 1 luma; no weather moved a shadow centroid by more than
3.3 cm). The fixes:
1. **A weather pauses under an Analyze drape (P0).** The drapes are alpha-blended over a
   ground the weather recolours: under snow the hours-of-sun drape's saturation fell to 0.31
   of the clear look's and its hue moved by up to 59° (p90), so its colour key no longer read
   as its legend. Decision 2's "the drapes are untouched" must hold for their PIXELS: while a
   drape lies on the ground (2D shadows or hours of sun; Sweep the Day included) the look is
   `living_look(sun, preset, "clear", dew=False)` — the sun's own look (`LookController.
   set_analysing`, told by the workspace on every drape change). The Weather button keeps the
   chosen weather and adds "(paused while analysing)"; Nothing on the Ground brings it back
   (FR-3D-LIVE-09). The drape frames are then the clear frames, so the review's hue gate (≤ 2.7°)
   holds by construction. Rejected: opaque drapes under a weather (they would hide the ground
   the analysis is about).
2. **The fog under a cloud (P1).** `FOG_OF_HORIZON` was calibrated on the clear sky's texture;
   an overcast sky draws its horizon row otherwise, so the fog drew 4 luma above the overcast
   noon horizon and 3.6 under its night — a seam in every cloudy weather that the board's
   distant-horizon gate raised. `weather.weather_fog` scales the fog by 1 + cloud × (−0.045 by
   day … +0.23 at night, by `twilight`); the look controller's lagging-sky fog uses it with the
   SHOWN sky's `cloud`. The board's `--living --horizon` now runs the horizon probe under
   overcast, rain and snow too (`HORIZON_WEATHERS`). Measured (high, 1280 × 720): near steps at
   most 1.86 luma in every cloudy mood (night 4.08 → 0.56), every distant row ≤ 2.87; clear
   unchanged (max 3.0).
3. **Lanterns and bulbs (P1).** The heads drew as neutral white boxes with dark cores: the
   point light stood inside the bulb's ball (a culled sphere lit from within renders dark) and
   lit the lantern's glossy pane at full strength. The light now stands `LIGHT_BELOW_CM` (3 cm)
   under the lantern or a string's middle bulb (`builders.lights.lamp_light` — the one function
   the light reads); `constantFade` 4 with brightness 9.4 keeps the 1.5-m pool of 1 / 3.5 / 7
   while the near field drops to a third; the glow is drawn 6 cm towards the camera, in front of
   its own ball, as a small hot centre in a warm halo kept under the tone curve's shoulder. The
   pane went: the constant fade is a floor, so a pane round its lamp is lit at the near-field
   strength wherever the light stands, and through Filmic at night exposure it drew cream
   (hue ~50°) whatever its tint. Dark speckles in the lantern heads (luma < 40 inside a ring
   > 110, the review's speckle probe) 41 → 1 — the board's `isolated_dark_px` reads 41 → 36,
   the lantern's black post and bars against its own glow; clipped pixels in the heads 55 % →
   6.6 % (round 2). The glow adds light of hue 12–31° (the head with the lamp-lit wall behind
   it: hue 46–53°, saturation 0.27, was a neutral white).
4. **Life is a count (P1).** The look's life shares were opacities; blended in linear HDR a
   wing at 9 % still lifted a dark lawn by 39 luma (80 ghost butterflies under overcast, 67 at
   dawn → 25 and 3, every one opaque). A share now collapses the particles whose seed lies
   above it. Wings stand in a 0.9-rad V at rest (flat they read as slivers), the white wing
   is a cream (0.70, 0.70, 0.64), and a leaf or butterfly near the camera is not drawn (the
   1,278-px white blade; largest butterfly blob now 403 px) — round 2 made both a SIZE ramp.

Smaller fixes of the same review: the dew rises over 4° from dawn instead of switching on;
fireflies stay under 2.5 m and fade over the last 25° of azimuth before solar midnight (either
hemisphere); falling leaves tumble well out of the horizontal; rain streaks are at least
1.3 px wide (alpha 0.27, the same total brightness) and flakes at least 2.6 px. Deferred to
#687: overcast contact shade, fading lamp pools, snow on roofs and bed soil, a dew ground mist,
the leaf colour from the tree. Left to the owner (the PR): how far a weather may fade a shadow,
the rain sky's brightness, whether snow may fall on any date.

**Addendum (3D review, round 2)**: The round-1 fixes held (drape pause, cloudy horizon,
lantern heads, ghost wings), and the round-2 review looked where round 1 had not — a cloudy
sky facing the sun, a rainy low sun, a moving walk view, a winter noon:
1. **No black sun.** The overcast sky set `sun_energy` × (1 − cloud); Qt's
   `ProceduralSkyTextureData` blends the disc and its falloff towards sun colour × energy, so
   energy 0 drew a BLACK disc with a dark halo (luma 0 at the sun, 150 around it, under
   overcast and rain). The energy stays; the disc's COLOUR fades into the horizon by cloud.
2. **No sun glint on wet ground.** At roughness 0.55 the dimmed key light still left a crisp
   specular lobe on the wet meadow at a low sun — a cream glint carved by the shadows — and a
   1.75-luma plan-edge step; the round-1 specular change (0.40 → 0.25) did not move it.
   Roughness is the lever: 0.8 (specular 0.25) gives an edge step of 0.32, no glint, and rain
   shadows of IoU 0.64 / 0.94 / 0.94 at 15 / 35 / 60° (overcast 0.77 / 0.95 / 0.94; rain
   0.24 / 0.66 / 0.93 before: most of the "rain fades the shadow" was the glint).
3. **A whole particle shrinks; none is cut.** Round 1 cut leaves and butterflies within 2 m
   PER VERTEX: a wing straddling the line sent some corners beyond the far plane and tore
   into a sliver (40 % of animated walk frames). The size now ramps to zero by the ANCHOR's
   depth (`smoothstep(150, 250, depth)` — closer bands read a cabbage white as a 728-px
   blade). The same for the life share: a particle whose seed lies above it shrinks away over
   a narrow band instead of popping; and a firefly is no longer dimmed on top of its count
   (its light faded as the share squared).
4. **The dew fades before noon.** On a winter day whose sun never reaches 18° the dew lay until
   solar noon and went out at once (0.33 at noon in Berlin on 21 December, 0.97 in Helsinki);
   it now fades over the last 25° of azimuth before the meridian, in either hemisphere.

**Addendum (senior review, round 1)**: The garden's life had no end-to-end path under test:
the test bench builds no Plant Forge, so `season_sink` never ran, and the tooling assembles
the life by hand. `test_living_garden.py` now drives a lavender in flower and an oak turning
through the PRODUCTION Plant Forge to the engine (June butterflies, October leaves, January
nothing; it fails when `season_sink` bypasses the coordinator), and the render tier reloads
the ambient buffer into the same live host (glow A, nothing, glow B — on the GPU and on WARP:
ADR-069's withdrawn first attempt, a new geometry object on a live Model, drew it as nothing). The living-garden host calls
(`set_plant_seasons`, `set_ambient`, `set_life_enabled`, `set_lamps`) are declared in
`EngineHost` — no silent fallback for a host without them. Today's Weather now works in the
default flow: the 3D view ASKS for the forecast (`Workspace.forecast_wanted` →
`PlantingCalendarView.request_forecast`, the weather part of the calendar's refresh, so still
one fetch path) when Today's Weather is chosen and for a new location (a new or opened document
brings its own; the document itself only forgets the old forecast — round 2); the calendar
emits an EMPTY forecast without a location or after a failed fetch; the tooltip names which of the plan date,
the location or the forecast is missing. Smaller: a precipitation that cannot be loaded no
longer skips the moon's handover and is logged once; the lights are read again only when a
pass touched a light (500 lights cost ~40 ms per pass); the drape's callback is disconnected
before the analysis shuts down. Left as stated: a string of lights casts the solid 2D prism
of its footprint (ADR-059's policy; 2 % of it is its 3D shadow) — an owner question (#698),
answered in the owner's addendum: it casts none. Measured
for the review: a night frame with six lamps lit costs +2.3 % on the GPU and +11.9 % on WARP
(bench_small, Medium, interleaved readbacks). Deferred to #689: the lamp pool's shader
permutations at the first dusk, the wind clock's precision in long sessions, Today's Weather
past midnight, the firefly season's date, one life assembly for the product and the tools.

**Addendum (senior review, round 2; 3D review, round 3)**:
1. **A new or opened plan never follows the old place's forecast.** `document_replaced`
   comes while the old document's location is still set, so round 1's ask from that slot
   fetched the OLD place; the result then reached Today's Weather, the calendar's strip
   (with no location) and the new plan's frost alerts. The document now only forgets the
   forecast; the ask waits for the new location's `location_changed`, which always follows.
   `WeatherWidget.set_location` cancels and DISCONNECTS the old place's fetch and forgets
   its forecast (the disconnect is what keeps a queued result from landing: PF-LIF-12 states
   the rule and its limit). The widget follows EVERY location change, also while its tab is
   hidden (`PlantingCalendarView.follow_location`; round 4 found the old place's late forecast
   landing on a plan at another place when Today's Weather was not chosen), and the forecast
   carries the place it was fetched for: the 3D view drops another place's instead of
   guessing (`forecast_days_ready(place, days)`, one reader `solar.plan_place`).
   An edit at the same coordinates (a frost date) keeps the forecast. No zero-timer: a fetch
   for the same place already on its way is not started again (`WeatherWidget.refresh`). The forecast as app-owned data keyed by place: #693; the
   calendar's frost alerts, which keep the old plan's after a cleared location: #694.
   **#693 addendum (forecast as app-owned data)**: the forecast is decoupled from `WeatherWidget`
   into `ForecastHolder` (`services/forecast_holder.py`), which invalidates on `document_replaced`,
   updates coordinates without fetching on `location_changed` until asked, coalesces repeat asks
   via a zero-timer, drops stale results by generation/coordinates, and re-emits synchronously
   when a fresh forecast is held without starting a thread or rebuilding hidden dashboards.
2. **Where noon stands is the place's.** The dew's noon fade and the fireflies' midnight
   read the meridian from the plan's hemisphere (`noon_azimuth`; `LookController.set_southern`,
   told by the workspace) — not from both: a summer dawn north of ~60° stands near due north,
   and round 2's fade dimmed its dew ×0.04 as if it were noon.
3. **A cloudy evening is an evening.** The low sun's exposure lift (+0.44 EV at a golden
   hour) makes up for a clear key light; under cloud it made a sunset 98 % as bright as noon.
   The cloudy day now holds NOON's exposure in the share of its cloud (in stops, like
   `mix_rig`), the mood's own returning with twilight: an overcast sunset is 0.77 of noon
   (rain 0.79, snow 0.68; a clear one 0.57; in luma 0.84 / 0.85 / 0.81, clear 0.67; the
   high preset at 1280 × 720 — the render tier's medium run at 640 × 360 reads
   0.76 / 0.78 / 0.67) — mean LINEAR
   luminance of the board's mood
   camera, `render_beauty_board.py --living --moods --dusk` (`moods_<weather>` /
   `sunset_over_noon`), re-measured at the final head with the stop blend and the matched set
   sun; every dusk monotone (`dusk_<weather>`).
4. **Wet leaves are not glossier than 0.6.** At roughness 0.38 a low sun left cream glints
   on the leaves in the rain; at 0.6 the golden hour's cream pixels fall 1,005 → 5, the sunset's
   707 → 38, the sun-facing walk views 413–468 → 0–23 (`foliage.frag`, `foliage_door.frag`,
   `lawn.frag`).
5. **Smaller:** a particle's seed spans [0, 11/12), so at a full share every particle is
   whole (a seed above 11/12 stayed undersized); the reload test adds a reload WHILE SHOWN and
   stands on both of CI's render lines (OpenGL on llvmpipe, Direct3D 11 on WARP); the host
   protocol carries the real types; the seasons' host call is contained like every living
   call; the plan's latitude has ONE finite-checked reader (`phenology.plan_latitude`) for
   the Forge, the garden's life and the hemisphere; the Weather button forgets the pause
   with its engine. Filed: #692 (the
   board's access violation at exit, also on the merge base). Owner questions (the PR): a
   cloudy evening darker than a clear one, and a glossier dew than the rain.

**Addendum (3D review, round 4; senior review, rounds 4–5)**:
1. **A set sun MATCHES the sky.** `look_for` drew no sun below 0.5° by `sun_energy` 0 — master's
   line, which Qt's procedural sky draws as a BLACK disc with a dark halo: luma 0 against a
   170–182 sky at +0.4°, through all of twilight, in every weather. The board's dusk camera has
   the sun behind the poplar, so three reviews missed it (#695: a sky-facing probe). A set sun
   is now the horizon's colour at the sky's own energy (`look.py`; a weather keeps it matched):
   dip ≤ 1.6 luma and no halo at +0.4 / 0 / −1 / −3°, clear, overcast and snow, and no glow at
   night — the energy-1 alternative left 23 luma at −3°. Dusk sunset steps halved
   (0.011 → 0.006).
   **Probe correction (#886).** The infinite meadow covered the below-horizon rays
   even with the plan rectangle removed. The probe now omits both ground surfaces.
   It keeps the sky model, camera, five elevations and 10-luma limit. At 1280 × 720
   on Direct3D 11, the worst dip across the measured clear and cloudy runs on the
   painted and atmosphere skies was 1.8 luma.
   The correction shipped in v1.40.7 after owner acceptance of PR #937.
2. **The dew rises from solar midnight.** Round 2's symmetric fade had also been the dew's ramp
   at the midnight meridian; the hemisphere fix removed it, and north of ~61° in June the dew
   switched 0 → 1 in one frame. It now rises over 15° of azimuth after solar midnight
   (Tromsø, 21 June, 2-minute steps: max 0.031, was 1.0).
3. **The producer says where it fetched** (round 4): the weather widget follows every location
   change, also with its tab hidden, and `forecast_days_ready(place, days)` carries the
   coordinates; the 3D view drops another place's forecast (PF-LIF-12).
4. **One validity rule for a place** (round 5): `solar.plan_place` — real numbers, finite,
   in range — for the calendar's forecast, Today's Weather, the Forge's phenology, the
   garden's life and the hemisphere (older readers: #697).
5. **String Lights' 2D shadow, stated truly** (round 5): #440, merged from master, made fences
   porous in 2D, so "a solid strip, as a picket fence's" no longer held. Like every open
   object without a porosity model, a string casts a solid 2D prism; its 3D shadow is 2 % of
   it. #440's transmittance hook could make all of them honest — an owner decision (#698;
   for the string answered in the owner's addendum: no 2D shadow). Cloudy horizon steps at
   the final head: ≤ 1.97 (snow sunset), night 0.56–0.94; the clear
   horizon unchanged (its low-preset sunset step of 3.13 was over the then-3.0 bound: #696;
   the bound is 3.6 since the re-measurement in ADR-059's addendum).

**Addendum (the owner's manual test of L5)**: The owner confirmed the day and year playback,
the garden's life, a new plan's forecast and the 3D lights, and changed two things:
1. **A string of lights is a LINE.** "A Lichterkette needs to be a 1D object like a fence or
   wall … it doesn't have an actual width", and its 2D picture, a sprite stretched over the
   rectangle, was distorted. `STRING_LIGHTS` is drawn with the line tool: every point is a
   post, the wire hangs between two posts (`SAG_SHARE` of the span), and a bulb hangs every
   40 cm along the WIRE, not per span — `core/string_lights.layout`, one layout for the
   canvas's picture (`ui/canvas/items/string_lights_paint.py`: wire, glowing bulbs, a post per
   point, sized by the line's width, 12 cm by default), the 3D builder and the night's lights.
   At most 120 bulbs a string; its triangle budget grows with the line as a fence's does
   (`lights.string_triangle_budget`). The string has no sprite (the gallery's picture is the
   same painter's) and no path or fence style. Change Type, the smart-symbol member table and
   the agent's `create_object` offer it with the lines. A string read from a file as a
   rectangle (a hand-edited plan; no plan with one has shipped) is the line along its long
   side: two posts.
2. **A string of lights casts no 2D shadow** — the answer to the open question #698 asked for
   strings: "Their shadow is not required in 2D sunlight studies, because the shadowed area
   is basically irrelevant." `object_height.NO_2D_SHADOW_TYPE_NAMES` /
   `casts_2d_shadow` is the one rule: the caster walk (`collect_identified_casters`, and
   with it the overlay, the hours of sun and the plants' sun estimates) leaves the string
   out, and its record says `has_2d_caster` False. Its 3D model keeps the thin shadow of its
   posts and wire. ADR-059's table has no row for it. #698 stayed open for the other open
   objects; they are answered in the addendum on open frames at the end of this ADR.
3. **The 3D strip's menu buttons read as buttons.** "Wetter: Klar" was not found: a
   text-only `QToolButton` that only opens a menu has its arrow drawn under its last letter
   by the app's style, and reads as a label. The Weather and the Analyze buttons carry the
   `menuChevron` property; the theme's chevron rule gives the arrow room beside the text
   (PF-UI-33).
4. Found along the way: the forecast cards' weekday names and the task list's month names
   are English in every language (`strftime`; #702).

Its reviews then settled what the line left open. **A bulb keeps 6 cm from its span's posts**
(`string_lights.POST_CLEAR_CM`): arc-length spacing put the middle bulb of every symmetric
string with an odd count ON its middle post — a 2.6 cm ball inside a 4 cm post (3D review);
no bulb moves further. The symbol's post is wider than 3D's 4 cm (a full stroke width), so
the 2D painter draws the wire and posts UNDER the bulbs and caps the post's drawn side at
`2 × POST_CLEAR_CM`: a clamped ball is visible on top of the post (59 % was buried at the
default width, 96 % at 24 cm) and a widened stroke cannot swallow it (senior review round
12). A string's point light stays under its middle bulb, which the clearance now keeps off
the posts of its span: the bulbs' centroid, tried in round 11, stood inside the middle post
of a straight string (senior review round 12); a bulb can still meet a foreign post on a
line that doubles back, where the paint order keeps it visible. Where a loop's or an L's
light should stand is a follow-up. The wire's radius is 0.5 cm
(0.35 broke into dashes at 7 m on Low). **The line's width sizes the 2D symbol only**, as a
fence's stroke does: the 3D model builds real 4 cm posts and 2.6 cm bulbs at the same places;
a width of 0, which a file may hold, is drawn at 12 cm by the bounds and the paint alike
(`string_lights_paint.drawn_width`). The string's style has no fill, as no line has one —
Change Type from a fence kept the string's cream style fill from its rectangle days, out of
step with the line's empty brush — and its Type-dropdown icon is the gallery's painted
picture, not the warning triangle. A crafted line of any length stands on at most
`MAX_POSTS` (512) posts, and a paint reads the layout the item keeps (security review;
general vertex caps at load: #703).
`NO_2D_SHADOW_TYPE_NAMES` is for a kind whose shade is negligible, never for an open frame
that overstates its own: a pergola or a swing is cast honestly through #440's transmittance
(#698). **Older versions**: no file-format change, but an older loader gives every line of an
unknown type `ObjectType.FENCE` — a string opens there as a 120 cm fence that casts a 2D
shadow, and stays one if saved there. A string drawn as a rectangle by this PR's first build
(the owner's test plans only; none shipped) opens as the two-post line along its box in 3D
and as a box on the canvas — draw it again.

**Addendum L7 (#391, the owner's manual test, 2026-11-03): Partly cloudy.** A fifth weather
between Clear and Overcast: `WEATHER_SPECS["partly_cloudy"]` is cloud 0.4, dry, wind 3.0 and
haze 0.9. The cloud is the atmosphere sky's cover; the look takes smaller shares of decision
2's overcast, 0.15 for the light (`WeatherSpec.light`: the key light × 0.88, the shadows' factor
× 0.90) and 0.25 for the sky's grey (`WeatherSpec.grey`). At the full 0.4 the painted sky read as
a dull clear day (3D review). The sun and its shadows stay where `core/solar` puts them, as in
every weather. Every other weather has one share for all three, so no accepted look moved under
the painted sky. Its mood stays day, golden hour
or dew (`mood_of` names overcast from cloud 0.5). It exists because the atmosphere sky's
volumetric clouds show as scattered clouds only at partial cover; Clear has none and Overcast
closes the deck (ADR-048 addendum L7, revision). Today's Weather maps WMO code 2 (partly
cloudy) to it; codes 0 and 1 stay clear. The board's cloudy-weather gates (horizon, mood strip,
dusk) and the render tier's cloudy-evening gate run on it (`HORIZON_WEATHERS`). Pinned by
`tests/unit/test_scene3d_weather.py::test_a_partly_cloudy_day_keeps_its_sun` and the WMO table.

**Addendum (#709/#705, the filleted string and its light).** Two follow-ups of the line
contract above, both in `core/string_lights.layout` and `builders.lights`:

- **A post every 40 cm, not every point (#709).** A fillet bakes its arc into the line at
  2 cm chords; a post at every point put 21 posts in a 39 cm arc (r 25) and 41 in a
  157 cm arc (r 100), and the bulbs sank into them. `MIN_POST_GAP_CM = 40` keeps the
  first point, the drawn last point and every point at least the gap further along the
  line; a closed loop also checks the closing span. A span shorter than the gap is
  allowed where its chord would cut the drawn line by more than
  `MAX_CHORD_DEVIATION_CM = 2.5`: a 40 cm chord at r 100 deviates ~2 cm, while the r 25
  fillet is followed by 17–19 cm spans (a 39 cm chord at r 25 would cut 9.5 cm; the
  first cut let a 2.2 m chord run 22 cm off the plan — 3D review). A bulb moves along
  its own span until it clears every **foreign** post by `OTHER_POST_CLEAR_CM` (8.6 cm,
  the 6 cm span clearance plus the 2.6 cm ball), so a self-crossing line cannot hide one
  in a post. A span shorter than two clearances keeps its middle: no share can clear both
  of its own posts, so moving it would only push it into one.
- **Where a string's light stands (#705).** An open line takes the bulb nearest the
  bulbs' centroid (linked to the line's middle, clear of every post), a closed loop
  takes the centroid itself — the middle of the space it hangs round — and falls back
  to that nearest bulb if a concave loop's centroid lands in a post. The light is laid
  out once per pass: `lamp_sources` computes the layout once and passes it to both
  `string_bulbs` and `lamp_light` (measured 13 ms per 16,384-vertex string, was
  29.5 ms with the second layout).

Pinned by `tests/unit/test_string_lights.py` (gap, filleted L at r 25/100, self-crossing
clearance) and `test_scene3d_particles.py` (open/closed light, the one-layout call).

**Addendum (#687, the L5 polish: occlusion under cloud, snow on built tops, leaves, lamp
pools, the dew mist).** The five deferred P2 findings of the L5 review and the snow comment
of the 3D survey. Measured on the board's `--living` shots (high, 1280 x 720, family garden)
with its new `living_occlusion` phase, and through `Quick3DHost.capture` for #831. Truth is
untouched: no sun, shadow, plant or date moves, and every clear frame is the same to the
level (the board's clear shots and every Low frame: max difference 0).

1. **Under cloud the ambient occlusion is the weather's.** Qt's pass reads a camera-facing
   normal (`ogp-3d-renderer` reference 24): flat ground seen at a slant occludes itself
   wherever no nearer object stands in its samples. At the clear values every open surface
   under cloud was grey (snow's lawn 17 levels under Low — the survey's 160 against 180 —,
   the overcast lawn 15.6 under its own frame without occlusion) and the meadow straight
   above every silhouette was 9.5-10 levels LIGHTER than far away: the survey's light rim.
   The issue's proposal (strength 99, reach 35, no bias) made both worse (snow -49). A weather
   now takes its light share (`WeatherSpec.light`) of strength 55 → 99, reach 14 → 70 cm and
   bias 0 → 21 cm (`AtmosphereSpec.ao_*`), and the bias follows the capture's AO scale. At 0.3
   of the reach the bias ends the self-occlusion near and far (0.16: rim 6-8; 0.25: 3.1 on
   snow; 0.5: no occlusion at all, a caster's lit-side foot 0.004). Result: rim 1.92 / 1.21 /
   2.07 (overcast / rain / snow), far self-occlusion 2.64 / 1.93 / 2.79, snow's lawn 2.93
   under Low, partly cloudy rim 4.92 (its 0.15 share); at 1080p 1.00 / 1.00 / 0.28, snow 0.58
   over Low. The cloudy frames are brighter for it (1080p board luma: overcast 116.9 → 126.1,
   rain 132.7 → 137.8, snow 154.2 → 174.9, the snow tops included). Clear, the dew and an Analyze drape
   keep 55 / 14 / 0 — the clear look keeps its own 8-level rim (below).
2. **The overcast contact gate compares the LIT sides — decided on the evidence.** The issue
   asked for "contact darkness under overcast at least that of the clear look at 15°". On the
   box caster's shadow side the clear look's 0.49 is its cast shadow; an occlusion that
   matched it would be a dark ring on every side, a shadow the sun does not cast. On the lit
   side occlusion alone darkens in both looks. So the gate: the lit-side foot under overcast
   ≥ the clear look's (0.040 ≥ 0.022 at 720p; at the render tier's 360 px ≥ 2× clear: 0.144
   against 0.044), with the rim ≤ 3 and the far self-occlusion ≤ 3 (720p) / 0.75 (360 px) for
   overcast, rain and snow. Stated plainly: today's 0.031 already passed the literal lit-side
   comparison, because the old "contact" was mostly the self-occluded ground round it; the
   shadow side reads 0.044 (was 0.063) for the same reason. The geometry of a 1 x 1 x 2 m box
   under a sky-lit day predicts 0.10-0.17 (sky view factor of its foot ring against the open
   ground, display luma); Qt's pass cannot give more without the rim. Looked at, the overcast
   box stands on darker ground at its foot and the ground round it is no longer grey. **At
   1080p the gate FAILS by a hair**: Qt's foot shrinks with the picture in every look (clear
   0.044 / 0.022 / 0.0096 at 360 px / 720p / 1080p), and the overcast foot reads 0.0065 against
   clear's 0.0096 (today's values 0.0156) — about 0.4 levels, while the rim falls 11.71 → 1.00,
   the open overcast ground's self-occlusion 15.63 → 0.21 and snow against Low -17.42 → +0.58.
   An open question for the review: a foot that is invisible at 1080p in both looks, or a grey
   ground with a rim.
3. **Snow lies on built tops** (decision 6 amended). While snow lies (`AtmosphereSpec.built_snow`
   = min(1, snow cover / 0.75): smooth tops lie white where the meadow's 0.75 still shows
   grass — at 0.75 a terracotta roof read pink and the mat lilac), every `vc` part and roof
   swaps to ONE material (`built_snow.vert/.frag`; no shader per part, ADR-060); snowless, every
   frame is the principled look. Its albedo is the principled look's: the vertex colour through
   its own vertex stage (read as `VAR_COLOR` a roof pixel came out 136 / 46 / 39 against the
   principled 187 / 99 / 71; through `COLOR` 187 / 99 / 71), the tint and fill picture through
   the engine's polynomial; snow mixes in by `built_snow × smoothstep(0.35, 0.75, NORMAL.y)`
   with the snowy ground's roughness and specular. A building's floor (under its roof, shown
   by Cutaway), glass (heated or not is not in the plan), water (frozen or not likewise) and an
   X-ray door stay as they are. The board's snow shot whitens 2 % or more of the frame against
   the same frame with bare tops (render gate).
4. **A falling leaf is its crown's colour.** `ambient_emitters` gives each dropping tree eight
   samples of the Forge's leaf colours for its own palette (outer, upper leaves) times the
   season's tint (`foliage_tint_linear`, the crown's `seasonTint`), seeded by the item id;
   `LEAF_PALETTE` is gone. A red Japanese maple drops red leaves (hue under 20°), every leaf within 10° of
   its crown's mean hue (unit test), two trees of one species drop different samples. In the
   frame a falling leaf reads 8-12° yellower than its crown (the board's autumn shot, the best
   measured tree: 47.8° against 36.0°; the literal's amber read 39.6° there by chance): the
   colour data are the crown's (39.7° against 39.1°), but a leaf particle is drawn in the
   look's flat particle light while the crown's own leaves are shaded and occluded — a
   follow-up for the particle light, not for the colours.
5. **Lamp pools fade at the edge of the lit six, and a picture lights its own.** Each lit
   lamp is weighted `smoothstep(0, 200 cm, d_out − d)` by how much nearer it is than the nearest
   lamp left out (`lights.lit_lamps`): at a swap both are dark, so no pool switches in a frame;
   no clock, so a recorded tour repeats; six lamps or fewer keep weight 1; a slot never turns
   invisible, so no shader recompiles. Measured with a fixed night camera over ten lanterns and
   the lamp target walking along them: the largest frame-to-frame step of a pool, 60 cm of
   target travel a frame, 61.3 levels with the hard set and 49.0 faded; at 15 cm a frame (a
   pan, a tour's path) 61.3 against 14.9 (p99 41.4 / 13.1) — the fade's step grows with the
   travel per frame (up to 1.5 × 2 × travel / 200 cm of a pool), the hard set's does not. Found while designing it: a camera tour's frames were lit
   by the six lamps of the PANE's target (`camera_moved` follows the view only). A tour's frame
   and an agent's `render_3d_view` with a camera now light by their own target
   (`WorkspaceCaptureCoordinator` → `WorkspaceLivingCoordinator.aim_lamps`; PF-E3D-29).
6. **No dew mist.** Qt 6.12's height fog is a slab: on the morning-dew shot the ground at the
   camera's feet +121.6 levels (fully fogged), the far rows +0.8, and density 1 / 0.3 and curve
   1 / 4 drew the same frame. A sheet mist would be a new blended Model sorted against the
   particles and the glass, and a post effect cannot join a chain that already holds the photo
   blur with glow on (PF-E3D-21): left out, the morning dew stays "a nearer haze and a sheen".
7. **Picture size (#831), measured, not fixed.** Pane-sized (640 x 360) against 1080p of the
   same camera, overcast at medium (#831's setup): the mean gap +4.14 → +0.73, but the 40-row
   bands now swing both ways (+13.4 / -11.7 at 360 px, +5.1 / -7.5 at 720p, +11.1 / -7.9 at 4K;
   at the clear values +10.5 / 0, +3.9 / 0, +2.1 / -4.0): the self-occlusion the bias leaves
   lies in a ring of far meadow whose distance moves with the picture (PF-E3D-28). Not scaling
   the bias at 4K: +4.51 mean. A bias scaled by 1080/height below 1080p over-corrected. The
   clear look (#831's own numbers +4.74 / +12.27) is unchanged.

Taste calls left to the owner: full snow on built tops against the meadow's 0.75; partly
cloudy's 4.9-level rim; whether the clear look should take the bias too (its 8-level rim
would go, every clear frame would change, and its far meadow would brighten by up to 13
levels). Rejected: the issue's 99 / 35 without a bias (above), a bias without the stronger
pass (55 / 14 / 3: the contact went from 0.022 to 0.007), Qt's height fog (a slab). Tests:
`test_scene3d_weather.py` (the occlusion and the built snow per weather), `test_quick3d_qml.py`
(the bindings, the one snow shader, its warmer, the bias's capture scale),
`test_scene3d_particles.py` (a leaf's crown colour, the lamp fade's continuity),
`test_scene3d_living.py`, `test_directors_cut.py` (a tour's lamps), `test_board_probes.py`
(the rim, open ground, a caster's foot), and the render tier
`test_living_garden_render.py` (the 360 px occlusion bounds, the built snow, and
`test_under_cloud_open_snow_has_no_rim_and_stays_with_low` at 720p). Lessons PF-L3D-26,
PF-L3D-27, PF-E3D-28, PF-E3D-29; debug-verbose case study 216.
## ADR-059 / ADR-070 addendum — open frames are weighted, not solid (#698, 2026-11-09)

**Status**: Shipped in v1.38.0 (PR #838), confirmed in the owner's manual test of 2026-11-10; decided on #440's precedent, and **the owner may revisit it**
(per kind: move its name from `OPEN_FRAME_TYPE_NAMES` to `SOLID_2D_DECISIONS`, with the
reason; the rows of the shadow table follow) | **Context**: issue #698. The
owner's part of it — a string of lights — was answered in the addendum above (no 2D
shadow). This is the rest.

**Context.** The 2D sun study casts every object as its footprint prism. For five kinds
that prism is mostly air: a pergola, a trellis, a swing, a hammock and a garden light shade
15–39 % of the ground their prism shades (the table below). The shadow overlay drew them as
slabs, the hours-of-sun map put the ground under a pergola in full shade all day, and a
runner bean tied to a trellis read 0 h of sun and wore a "too little sun" badge.

**Decision.**

1. **Five kinds are OPEN FRAMES** — `core.object_height.OPEN_FRAME_TYPE_NAMES`: `PERGOLA`,
   `TRELLIS`, `SWING`, `HAMMOCK`, `GARDEN_LIGHT`. An open frame's 2D caster keeps its
   footprint prism — that is where its shade can fall — and carries a **transmittance**:
   `1 − A(frame) ÷ A(prism)`, the ground shadow of the frame's own solid members over the
   ground shadow of the prism, **for the sun of the moment**
   (`core.shadow_geometry.open_frame_transmittance`). The shade the 2D model reports,
   area times depth, is then the frame's real shadow area.
2. **Nothing is tabulated.** The members are the 3D builder's own, read as #440 reads a
   pitched roof's triangles (`core.scene3d.builders.open_frames`): a pergola's are the 22
   boxes of `core.pergola.layout` — the one layout its 2D picture and its 3D timber come
   from — and the other four kinds' are the shadow-casting parts of their production
   builder, built for the item's own footprint and height. So the weight follows the item's
   size, its height, its turn and the sun's elevation and azimuth. A table of shares per
   kind was rejected: the members' sizes are capped, so the share falls as the item grows
   (a pergola: 0.32 at 3 × 3 m, 0.24 at 6 × 4 m, both at a 35° sun from the south), and it
   moves with the sun (a trellis 2 m long: 0.34 square to a 35° sun, 0.47 at 75° off it).
   Over the sizes, elevations (8–78°) and azimuths the unit test sweeps, the weight ranges
   0.22–0.47 for a pergola, 0.19–0.70 for a trellis, 0.10–0.25 for a swing, 0.18–0.37 for a
   hammock and 0.13–0.45 for a garden light.
3. **One place, one hook.** The caster walk (`collect_identified_casters`) gives an open
   frame's `IdentifiedCaster` its members as `frame` (`core.shadow_geometry.OpenFrame`);
   `caster_transmittance` — #440's hook — reads them. The overlay, the 3D analysis drape,
   the hours-of-sun grid and the per-plant estimates all ask that hook and nothing else;
   for a plant on raised soil the frame is cut at the plant's plane like every other
   caster. Where the 3D builder has no frame for a footprint and builds its plain block (a
   round pergola), the 2D caster is the solid prism too.
   **A frame is kept in the item's own coordinates, its turn beside it** — not posed into
   the scene. What a frame lets through depends on the sun's bearing relative to it, not
   on where it stands: every identical item is handed the very same `OpenFrame` object,
   is weighed once per sun position and gets the very same number, so a row of garden
   lights is ONE region for the overlay and the map, not fifty a hair apart.
4. **Every mostly-air kind has a recorded decision.** Eleven more object kinds shade less
   than half of their prism at one of the table's elevations and stay SOLID —
   `SOLID_2D_DECISIONS`, each with its reason: the tables, the picnic table, the trampoline,
   the bench and the chair (a solid top or seat on legs, at most 90 cm up), the grill, the
   wheelbarrow and the bird bath (one compact body smaller than its footprint), the
   **parasol** and the **greenhouse**. None of them is a frame: their surplus is SHAPE, and
   a transmittance would smear a shade that is dark in one place and absent in another. A
   test holds every object kind whose 3D model is mostly air to one of the three lists
   (open frame / solid by decision / no 2D shadow), so a new open kind cannot become a
   solid prism by being forgotten.
5. **The overlay edges a light shade lightly.** The overlay's soft edge was stroked at the
   strength of the DARKEST region on the plan, so beside a house a swing's shade (alpha 20
   of 255) wore a rim six times darker than itself — an outline round a shadow. Each
   weighted region is now edged at its own strength. This also changes how a porous fence's
   shade is drawn beside a solid's (#440).

**Measured** (`scripts/measure_built_world_shadows.py`; one item of the stated footprint at
its default height, the sun due south, at 15° / 35° / 60°):

| Kind (footprint, height) | IoU, 3D vs trimmed 2D | Transmittance | 3D ÷ weighted 2D |
|---|---|---|---|
| pergola (300 × 300 cm, 250 cm) | 0.29 / 0.32 / 0.36 | 0.71 / 0.67 / 0.64 | 0.99 / 0.99 / 0.99 |
| trellis (200 × 20 cm, 180 cm) | 0.33 / 0.35 / 0.41 | 0.67 / 0.65 / 0.59 | 1.00 / 1.00 / 1.00 |
| swing (200 × 150 cm, 220 cm) | 0.18 / 0.19 / 0.21 | 0.82 / 0.81 / 0.79 | 1.00 / 1.00 / 1.00 |
| hammock (300 × 120 cm, 110 cm) | 0.23 / 0.33 / 0.43 | 0.77 / 0.67 / 0.57 | 1.00 / 1.00 / 1.00 |
| garden light (radius 20 cm, 110 cm) | 0.21 / 0.29 / 0.39 | 0.78 / 0.70 / 0.59 | 1.00 / 1.00 / 1.00 |

The last column is the issue's gate — within 10 %, as #440 held fences — and it is the
ratio column of the builders addendum's table for these five rows. It is 1.00 where the 2D
model reads the very mesh the measurement projects; the pergola's 0.99 is the layout's
plain boxes against the chamfered timber. The gate is not trivially met for that reason:
the measurement unites every triangle of the mesh in its own code, and
`tests/unit/test_open_frames.py` holds the 2D weight to it within 0.02 over three sizes,
five elevations and seven azimuths per kind. The table's reach column now reads 0.0 cm
for the four frames whose top member is their far member and −0.8 cm for the pergola:
since #855 the prism is trimmed to the frame's own far member tip, so the shade no
longer ends 4-71 cm past the real shadow (a swing's top beam is mid-frame).

**What changes for existing plans.** No file-format change; a plan with one of the five
kinds shows more sun under and behind it the next time the map is computed. On the bundled
examples, hours of sun per 10 cm cell, before → after:

| Plan (open frames) | Day | Cells changed | Largest gain | Mean gain, changed cells | Mean, all cells | Plants changed (largest) |
|---|---|---|---|---|---|---|
| family-garden (pergola, trellis) | 21 June | 14.1 % | +6.9 h | +1.1 h | +0.16 h | 8 (+3.2 h) |
| | 20 March | 14.5 % | +4.5 h | +0.7 h | +0.10 h | 15 (+2.7 h) |
| | 21 December | 3.9 % | +1.2 h | +0.2 h | +0.01 h | 6 (+0.4 h) |
| food-forest (trellis) | 21 June | 1.9 % | +5.2 h | +0.9 h | +0.02 h | 4 (+4.4 h) |
| | 20 March | 3.8 % | +6.8 h | +0.7 h | +0.03 h | 6 (+6.1 h) |
| | 21 December | 6.8 % | +3.0 h | +0.4 h | +0.02 h | 4 (+2.6 h) |
| balcony, raised-bed (none) | all three | 0 | 0 | 0 | 0 | 0 |

**Four sun-requirement diagnostics flip, all from "too little sun" to none:** in
family-garden a cucumber (full sun) on 21 June, 3.8 h → 6.9 h, and a lettuce (partial sun)
on 20 March, 1.5 h → 3.2 h; in food-forest two runner beans (full sun) at their trellis on
20 March, 0.0 h → 6.1 h and 0.0 h → 5.0 h. None flips the other way. One or two cells of a
plan read one sample (15 min) DARKER: a seam of #440's weighted path, which rasterises
each weighted region on its own, where the solid path rasterised their union — not a model
term. The balcony example holds a parasol and is unchanged.

**Cost.** One weighing is one numpy projection and one clipper union of the members that
face the sun: 0.4–2.2 ms a frame and sun (a pergola 0.9 ms, a hammock's cloth 2.2 ms), kept
per frame, height and sun — the map does not weigh a sample twice, and identical items
share the answer. Two costs of #440's weighted path showed once garden lights were on it
(many small weighted casters, where fences are few), and both are changed here:

- **The partition of the weighted shades clipped every pair** — 0.8 s a sun position at
  500 lights. It now asks a clip only of two shades whose boxes overlap, with the boxes
  made once and turned WITH THE SUN (every shade is swept the same way, so a long shade's
  box is as narrow as its caster); a shade that meets no other is its own region without a
  clip. The regions are the pairwise partition's (`tests/unit/test_open_frames.py` holds
  them to it on random plans, at a high and at a grazing sun).
- **A day's aggregation swept a weighted plan twice** — the grouped sweep for the plants'
  estimates beside the weighted one for the grid. The weighted result holds every owner's
  own shadow already, the very polygons (pinned), so it is swept once.

Measured on the dev box (ratios; the machine drifts): one sun position with 50 / 200 / 500
garden lights 4.3 / 22 / 76 ms solid → 6.4 / 24 / 72 ms weighted (before the two changes:
36 / 240 / 1063 ms); their day's aggregation without rasterising 0.30 / 1.3 / 4.0 s solid →
0.57 / 3.4 / 9.6 s (before: 3.4 / 26 / 137 s) — what is left is the grazing samples, where
long shades really do overlap. A first open frame still puts a plan on the weighted path:
food-forest's day map 1.5 s → 2.0 s, family-garden's (porous fences already) 2.3 s → 2.9 s.

**Left as it was, and why.**

- **Parasol** — shipped as a RAISED CANOPY in #830 (see the addendum below): the
  canopy's rim band from its lower edge to the rim, the pole and finial left out.
  Measured on the balcony example: the 21-June map mean 4.57 h → 6.12 h.
- **Greenhouse** — shipped as its FRAME ALONE in #830 (see the addendum below): glass
  counts as direct sun, and the caster reads the same frame triangles the 3D builder
  casts. A tomato inside reads the open sky minus the frame instead of 0 h.
- **Low furniture** — at most 90 cm tall; the surplus is a strip `h ÷ tan α` wide beside
  the piece.

**Tests**: `tests/unit/test_open_frames.py` (the lists and the drift guard, the weight
against the independent measurement, the turn, the weighted regions, the hours-of-sun grid,
the plant estimate also on raised soil), `tests/integration/test_open_frame_shade.py`
(§8.10: the caster walk on real items at three turns, the painted overlay against a solid
twin, the soft edge, the heatmap worker, a pergola placed through the command stack and
undone), `tests/unit/test_scene3d_shadow_agreement.py` (the five rows).



**Addendum (issue #855): the prism is trimmed to the frame's own far tip.** The
weighted model above spread the frame's shade over the whole `height / tan a` prism.
That prism ends at the shadow of the frame's nominal height, not at its topmost
member: a swing's top beam is mid-frame, so its shade ran 71 cm past the beam's
shadow (4-71 cm across the five kinds). `core.shadow_geometry.open_frame_effective_length`
now trims the swept length to the largest `x·dx + y·dy + z / tan a` of the frame's
own members, minus the footprint's reach; the transmittance is measured against that
trimmed prism, so its tip is the frame's while the frame's own shadow is spread over
the smaller prism as before. The table's reach column reads 0.0 cm for the four frames whose top
member is their far member and -0.8 cm for the pergola; the ratio column is 3D against
the weighted, trimmed 2D area. The 3D analysis drape, the hours-of-sun map, the overlay
and the per-plant estimates all read the same trimmed caster. Less than one minute can
still be lost in a cell or two at a weighted-region seam (the #440 limitation, 0.997 min
measured); that is a seam, not a solid's shade. Tests:
`tests/unit/test_open_frames.py` (the reach versus the measuring script's mesh shadow,
the transmittance against the trimmed prism, and the turned frame) and
`tests/integration/test_open_frame_shade.py` (the real overlay and map). FR-SUN-13,
§8.29.6 and the shadow table carry the new numbers.

## ADR-059 addendum: a parasol is a raised canopy and a glasshouse is its frame (#830)

**Status**: Shipped in v1.43.2 with #830's package (PR #1027; owner decision
2026-11-24; see the issue's "Owner decision" section).

**Decision.** Three 2D-sun-study models change, all toward the 3D view:

1. **A parasol is a raised slab**, not a prism from the ground. The slab is the canopy's
   rim band — its lower edge to the rim (185.6–193.6 cm on the default 150 cm / 250 cm
   parasol) — and the thin pole and finial are left out. This is the geometry the
   owner's IoU gate was measured with; a slab up to the item's top covers the cone's
   air and reads 0.53 / 0.70 / 0.84. Measured: 3D ÷ 2D 1.06 / 1.00 / 0.96, IoU
   0.89 / 0.93 / 0.96 at 15 / 35 / 60° (was 0.24 / 0.41 / 0.60). On the balcony example
   the 21-June map mean is 6.12 h (was 4.57 h; 6.36 h with no parasol). The 2D caster
   carries `base_cm` = the lower edge and `height_cm` = the band's thickness; the prism
   is not used.
2. **A glasshouse is its frame alone; glass counts as sun.** The map counts hours of
   DIRECT sun, a yes/no per sample, and glass weakens light without stopping it. The
   caster carries the same frame triangles the 3D builder casts
   (`core.scene3d.builders.open_frames.glasshouse_frame_triangles`, the builder's
   `casts_shadow` parts) and is weighted through #698's transmittance path; a gabled
   greenhouse whose builder has no shadow-casting frame is transparent, exactly as 3D
   is. Measured: 3D ÷ weighted 2D 1.00 / 1.00 / 1.00 at the three elevations (was
   0.30 / 0.23 / 0.25); a tomato inside reads the open sky minus the frame instead of
   0 h. A framed glasshouse is no longer spared as a soil parent in the per-plant
   estimate or the map's plant cells — its frame is between the plant and the sun.
3. **A plant does not shade the cells inside its own footprint.** The rule the plant's
   own estimate already used (`SunReceiver`: its own solid and the soil parent it stands
   in are left out) now applies to the map's grid: those cells are shaded without the
   plant and without a `holds_plants` caster whose outline contains it. The map's cell at
   the plant now equals the plant's estimate; there is no dark dot under each plant.
   A plan with a framed glasshouse is the exception stated above: its frame still shades.

**Existing plans.** All three change hours-of-sun maps: the parasol and glasshouse rows
of the balcony/family-garden examples read sunnier, and the dark dot under every plant is
gone. The release note must say so. The map means in ADR-065's examples are re-measured
in `scripts/measure_built_world_shadows.py` and the table above.

**Tests**: `tests/unit/test_open_frames.py` (the five decision lists and the drift guard),
`tests/integration/test_open_frame_shade.py` (the parasol slab's raised shadow, the
greenhouse frame with a plant inside, the map-equals-estimate rule, the plant cell in a
plan with an open frame), the seeded example checks, and #1007's seam test.

## ADR-070 addendum: the weather is the plan's, not the session's (#944)

**Status**: Shipped in [v1.41.3](https://github.com/cofade/open-garden-planner/releases/tag/v1.41.3) after owner acceptance (2026-11-23; [PR #998](https://github.com/cofade/open-garden-planner/pull/998)).

**Context**: L5 made the weather session state: `WorkspaceLivingCoordinator` started
clear and the note said "not stored". A bundled example or a stored camera tour could
therefore not open in snow or rain, so a winter showcase could not be shipped. The
issue's direction was "an optional weather on the showcase moment of an example, or on
a stored tour". The tour is the wrong home: a tour is a camera and a clock (ADR-072
addendum), and the weather is a property of the whole plan's look, not of one flight.

**Decision**:
1. **One additive top-level plan key, `weather`.** `ProjectData.weather` defaults to
   `"clear"`, is written only when it is not clear, and is read through
   `weather.normalise_weather` — an unknown value, a missing key or `today` opens clear.
   No `FILE_VERSION` change; an older app ignores the key.
2. **The choice is the user's and dirties the plan.** `ProjectManager.set_plan_weather`
   stores the weather and marks the plan dirty; the window's
   `_store_plan_weather` stores every concrete weather the toolbar emits and refuses
   `today` (a forecast, not a plan fact); `_restore_project_metadata` normalises through
   `_plan_weather` so `today` can never leak into `plan_weather`. Opening a plan calls
   `_apply_plan_weather`, which applies the stored weather — **clear included** — with an
   `_applying_plan_weather` guard so the feed-back does not dirty the document. `File -> New`
   preserves `today` (session-only) while resetting any previous plan's concrete weather to
   `clear` so the 3D view and `plan_weather` never desynchronise.
3. **A portable template keeps it.** `weather` joins `KEEP_PROJECT_FIELDS`: it is part
   of the plan's look, not personal site data.
4. **A tour keeps no weather.** A tour rendered from a plan uses that plan's weather
   (FR-3D-TOUR-04); the weather still belongs to the view/plan at render time.

**Alternatives rejected**: a tour-only field (one flight would own the whole plan's
sky, and a still picture or the live view would not see it); a session setting (the
issue's whole point); writing clear explicitly (the plan key is additive and absent
means clear, so a file stays small and old plans stay byte-compatible); treating an
unknown weather as an error (a file from a future build must still open).

**Consequences**: one additive plan key; no new UI string (the
Weather menu exists). Pinned by `tests/unit/test_plan_weather.py` (the key, the range,
unknown values), `tests/integration/test_plan_weather.py` (the real window: the menu
stores, save/reopen applies, Today is not stored), and
`tests/integration/test_autosave_recovery.py` (recovery keeps it).
