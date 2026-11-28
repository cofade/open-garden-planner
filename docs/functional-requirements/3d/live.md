---
title: "Living garden"
prefixes: ["FR-3D-LIVE"]
---

# Living garden

Day and year playback, weather and garden lights (#389, ADR-070).

- **FR-3D-LIVE-01** (L5.1): The Plan & Sun toolbar's **Animate** plays either **the day**
  (the time of day advances and wraps at midnight onto the same plan date — plant presence
  and growth never change while it plays) or **the year** (the plan date advances at the
  same time of day and wraps inside the plan's year), chosen in the menu beside the button,
  at **Slow / Normal / Fast** (day: 5 / 10 / 30 minutes per step; year: 1 / 2 / 7 days per
  step; a step every 0.2 s; "Normal" day is Phase 14's Animate). Every step is a write of
  the one simulation clock: the 2D shadows, the hours of sun, the 3D light and the 3D
  growth follow it (3D regrowth at most twice a second, with seasonal plant shader uniforms
  evaluated on every date step; #995). While playback runs, the 3D workspace holds its
  automatic quality preset and defers `QQuickWindow.releaseResources()` cache drops until
  playback pauses, and pure 3D mode (without the 2D shadow drape) skips 2D shadow polygon
  solves and defers heavy 2D date diagnostic sweeps until playback stops or 2D is shown
  again (#996). Not stored: every session starts
  with the day at Normal.
- **FR-3D-LIVE-02** (L5.1): The 3D view names its **mood** in the Weather button's
  tooltip — Night, Twilight, Rain, Snow, Overcast, Morning dew (a morning, from the end of
  civil twilight until the sun is 18° up: a mist and a wet sheen on the leaves), Golden hour
  (a clear sun at or below 12°) or Day — read from the frame's own look.
- **FR-3D-LIVE-03** (L5.2; Partly cloudy L7): The 3D strip's **Weather** menu picks
  **Clear**, **Partly cloudy**, **Overcast**, **Rain** or **Snow**. Weather changes how the garden LOOKS and nothing else: the sun's
  position, the shadows' places, the 2D sun study and the hours-of-sun map stay as they
  are. Partly cloudy: the sun stays out, its shadows crisp and only a little fainter, the
  sky a little greyer; with the atmosphere sky (FR-3D-LOOK-08) scattered white clouds cross
  it, golden toward sunset.
  Overcast: a grey sky, no sun disc, soft and faint shadows; what an object hides of the sky
  darkens the ground at its foot (a stronger ambient occlusion under cloud, #687) while open
  ground stays as bright as it is. Rain: overcast, wet leaves and ground, a nearer haze,
  stronger wind and falling rain. Snow: a pale sky, snow on the ground and the leaves, and
  on the TOPS of what is built — roofs, a bed's soil, decks, the trampoline's mat, a bench's
  seat (#687; walls, glass and water stay as they are) — falling snow, little wind. A new
  weather shows at once. The weather is the plan's since #944 (FR-3D-LIVE-10): a plan without
  one opens clear, and a concrete choice is saved with it. Today's Weather is a forecast and
  is never stored.
- **FR-3D-LIVE-04** (L5.2): Particles: rain and snow around the point the camera looks at;
  **falling leaves** under trees and shrubs that are dropping their leaves on the plan
  date, each in its own tree's turned colour (a red Japanese maple drops red leaves, #687); **butterflies** at plants in flower (up to 3.5 m tall) by day in dry weather;
  **fireflies** among the plants on summer evenings (the hemisphere's June–August or
  December–February, from dusk). At most **5,000** particles at once. "Wildlife and Falling
  Leaves" in the Weather menu switches the leaves, butterflies and fireflies off and on.
  The wind is a shader value the weather sets (sway and drift), not a simulation.
- **FR-3D-LIVE-05** (L5.2): With **reduced motion** (Preferences → 3D View) nothing moves:
  rain, snow and the garden's life are drawn still where they are, and an idle 3D view
  presents no frame. While the 3D pane is hidden nothing ticks. In compatibility mode
  (software rendering) they are drawn still. On the graphics card at Medium the particles
  cost at most 15 % of a frame (measured: rain +3.7 %, snow +1.9 %).
- **FR-3D-LIVE-06** (L5.3): **Today's Weather** follows the forecast the app shows in the
  Planting Calendar (Open-Meteo, one fetch path: choosing Today's Weather asks the calendar's
  weather widget for it, also while that tab is hidden) — clear, partly cloudy (WMO code 2),
  overcast, rain or snow from the day's weather code — **only while the plan date is today**; on any other date, or
  without a forecast (no garden location, offline, not loaded yet), it shows clear and its
  tooltip says which. A new location or document forgets the old forecast.
- **FR-3D-LIVE-07** (L5.4): **Garden Light** (a lantern on a post; circle tool) and **String
  Lights** (a LINE drawn like a fence: a post at every click, the wire hanging between two
  posts with a bulb every 40 cm along it, kept 6 cm from the posts of its span where the
  span is longer than 12 cm) are placeable objects with a gallery entry, translated name,
  Change Type membership for their shape (circles; lines), default height (110 cm / 250 cm)
  and 3D model. The lantern has a sprite; a string is drawn ALONG its line — its wire,
  glowing bulbs and a post at every point, the bulbs where its 3D model hangs them, sized by
  the line's width (the 2D symbol only; the 3D posts and bulbs keep their real size) — and
  has no path or fence style. No file-format change: an older version loads a garden light
  as a generic shape, but a string as a **fence** — its loader turns every line of an
  unknown type into one — standing 120 cm high, casting a 2D shadow and built as a fence in
  3D; saved there, it stays a fence.
- **FR-3D-LIVE-08** (L5.4): From dusk on, every bulb of a garden light **glows** in 3D and
  the six lights nearest to the point the camera looks at **light** the garden around them
  (leaves, lawn and ground included); a light at the edge of those six fades as the camera
  turns away, so no pool switches on or off in one frame, and a camera tour's frame or an
  agent's picture is lit by the lights nearest the point IT looks at (#687); the lights go
  off at sunrise. In 2D a garden light
  casts the usual solid-footprint shadow (ADR-059's table); a **string of lights casts no 2D
  shadow** — not in the overlay, the hours-of-sun map or a plant's sun estimate (the owner's
  decision: the shade of a wire is no planning fact). In 3D both cast their own thin
  shadows.
- **FR-3D-LIVE-09** (L5.2): While an Analyze drape lies on the 3D ground (2D Shadows on the
  Ground, or Hours of Sun on the Ground — Sweep the Day included), the weather and the
  morning dew **pause**: the garden shows the clear sun's look, so the drape's colours read
  as its legend's. The Weather button keeps the chosen weather's name and adds "(paused
  while analysing)"; with Nothing on the Ground the chosen weather returns.
- **FR-3D-LIVE-10** (#944): A **plan stores the concrete weather it opens in** — clear,
  partly cloudy, overcast, rain or snow — as an additive top-level `weather` key. Choosing
  one in the 3D strip's Weather menu marks the plan dirty; saving stores it; opening the plan
  applies it, clear included, so a plan can open in the sky it was built with and a
  snowy example followed by a clear one does not leave snow on the second. A **new untitled
  plan** has no weather of its own: it keeps **Today's Weather** (session-only live forecast)
  when active, and resets any previous plan's concrete weather to clear so the 3D view and
  `plan_weather` stay in sync. It is the plan's
  look, not a personal fact, so a portable template keeps it. A file without the key, an
  unknown value, or `today` opens clear; **Today's Weather** is a live forecast and is never
  written. No `FILE_VERSION` change: an older app ignores the key and writes the plan without
  it. Pinned by `tests/unit/test_plan_weather.py`,
  `tests/integration/test_plan_weather.py` (save/reopen through the real window and its
  Weather menu), and `tests/integration/test_autosave_recovery.py` (recovery keeps it).
  The weather is still not part of a **tour**: a tour rendered from a plan uses the plan's
  weather (FR-3D-TOUR-04).

Acceptance: `tests/integration/test_living_garden.py` (§8.10 — the toolbar's day and
year playback through the real app and its clock; the Weather menu, the life switch and
Today's Weather through the workspace; the lamps drawn with their tools and told to the
engine), the unit suites `tests/unit/test_playback.py`, `test_scene3d_weather.py` and
`test_scene3d_particles.py`, the render tier `tests/integration/test_living_garden_render.py`
(the reduced-motion idle gate, the 15 % frame-cost gate and the board's `--living` shots) and
`tests/integration/test_object_sprite_rendering.py` (the two tools draw items that paint).
