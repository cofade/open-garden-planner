# Archive 06: Phase 17 L1.4 looks, sky and wind

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.18 What the looks, the sky and the wind taught (Phase 17 L1.4, #385)

Symptom → root cause → fix, for the things that cost time while the looks (ADR-059 addendum
"looks, sky and the animation policy", §8.29.4) were built. Engine facts are also in the
`ogp-3d-renderer` skill §14; art-direction fixes in `ogp-lush-cinematic` §7.

1. **A colour derived in linear light came out three times too dark at night.** *Symptom:* the
   night fog met the night sky as a black line (luma 3 where the sky above it read 13), although
   the fog's sRGB code was the exact encoding of the linear value the look derived. *Root cause:*
   Qt Quick 3D does not linearise a `color` property with the sRGB curve but with a polynomial
   (`x·(x·(x·0.3053 + 0.6822) + 0.0125)`) — the two agree from about 0.3 up and differ threefold
   for very dark colours: code 5 is 0.0015 by the sRGB curve and 0.0005 to the engine (measured
   with a flat ambient light on a white box in the un-tone-mapped truth view). *Fix:* the three
   colours the look derives in linear light (fog, plain sky, fill) are handed over as
   `QColor.fromRgbF(engine_srgb(linear))` — the inverse of the engine's own conversion, as floats
   (8 bits are steps of a fifth down there). **A colour property is not "sRGB, linearised by the
   engine" for dark values — compute what the engine will make of it.**
2. **The night horizon was a bright line — the spike's own formula.** *Symptom:* at eye height
   the fogged meadow met the night sky with a one-row step of 10.5 luma (high) and 21.2 (low).
   *Root cause:* the spike's fog was horizon × probe exposure × 0.8 in every mood, while the night
   SKY is drawn × 0.25 (`skyEnergy`): the fog was four times brighter than what it met. Nothing
   on the L0 board looked at the horizon at night. *Fix:* the fog carries the sky's energy
   (`fog_linear`): 2.4 / 3.2. And in round 5 the night sky's ground hemisphere (the sliver under
   the far-clipped meadow) at the sky's energy, 0.25, instead of the spike's 0.15 — the same day
   lesson carried to night: dip 2.07 / 1.04 → 0.01 / 0.12. **A rule measured by day (ground
   energy = sky energy; fog = what the sky draws) must be re-measured where the inputs change —
   at night they did.**
3. **The engine animates a hidden window.** *Symptom:* none yet — found by the render tier
   before it could become one: with the window hidden and the wind's `FrameAnimation` still
   running, `windTime` went on advancing (0.59 s of clock in 0.6 s hidden; RTX 4070).
   *Root cause:* a hidden `QQuickView` keeps its animation driver ticking. *Fix:* the animation
   policy STOPS the clock when the pane is hidden (`set_wind_running(False)`) rather than trust
   "hidden"; hidden means zero ticks. And stopped is not rest: a paused non-zero clock keeps the
   sway of that moment in the frame — reduced motion and every truth probe RESET it to 0
   (`rest_wind`).
4. **A sky texture must be a fresh pair, and released with its data.** *Symptom (avoided,
   measured by the sky sequence A → B → C):* the ground bake found that a `Texture` whose
   `textureData` is re-pointed loses its data when a data object it held EARLIER is destroyed
   (#476: a white tile). The spike's sky re-pointed one Texture. *Fix:* every build is a new
   `Texture` with a new `ProceduralSkyTextureData` as its CHILD; only the Texture is ever
   destroyed, after the scene shows the new one, so a pair lives and dies together. A frame
   after the old pairs are gone is the same sky, its sun at the solar azimuth. Measured over
   twenty sun changes, frames presented and withheld: no growth per change in committed memory
   and in dedicated GPU memory — no cache release needed, unlike a retired Model (§11.4.16
   item 2); the positive control (a `buildSky` that never destroys the old Texture) reads 8.2 MB per
   change (presenting: 0.0; frames withheld: 0.125; the bound 1.0).
5. **A sun-grazed lit wall hatched only on Direct3D 11.** *Symptom:* at high and ultra, on the
   dev box's GPU, a wall the sun lit at n·l 0.33 showed a fine diagonal hatch (pixel noise
   1.15 % of its luma, the face 3.7 luma darker). *Root cause:* the spike's shadow bias of 5 was
   measured on llvmpipe with smaller maps and fewer cascades. *Fix:* bias 10 at high and ultra
   (0.18 %, the dither's floor; IoU unchanged). **Shadow acne is a function of the backend, the
   map size and the cascade split — re-measure the bias on the real GPU per preset.**
6. **A view that draws on demand has no frame rate.** *Symptom (by design, before it was
   built):* an automatic preset fed with "frames per second" of a still view would read a
   sleeping display, a hidden pane or an idle scene as "slow" and step down for nothing.
   *Fix:* `AutoPreset` reads presented frames only while the wind animates (the view draws
   continuously), and ten seconds without a presented frame is no data: what was collected is
   dropped and the preset holds. Never a readback to measure (ADR-060 decision 17).
7. **The wind ran in compatibility mode** (fix round 1, review P0). *Symptom:* on a software
   adapter the view with the wind running drew 139 frames in 4 s at 1,351 % of one core (still:
   1 frame, 18 %); the GUI's 10 ms timer ran 19.9 ms late. *Root cause:* the controller decided
   the sky by the render mode (`sky_light=not software`) but the wind and the automatic preset
   by visibility alone — three decisions about one fact, made in two places; and a render-tier
   test asserted the bug for `[software]`. *Fix:* ONE parameter, `LookController(software=...)`,
   decides sky, wind and the automatic preset together. **When one fact gates several
   behaviours, pass the fact, not one of its consequences.**
8. **A failing sky stopped every later look** (review P1). *Symptom:* a host whose sky could
   not be built got 20 suns, 0 looks, 20 sky attempts and 20 ERROR lines. *Root cause:* the sky
   build and `set_look` shared one `try`; the sky was retried in every pass and failed first.
   *Fix:* the sky in its own `try`; on failure one ERROR, the plain sky for the session; the
   look always sent (20 looks, 2 sky calls — the build and the clean-up —, 1 error).
9. **A per-session memory forgot what it learned** (review P1). *Symptom:* "high is too slow,
   medium is fine" stepped medium -> high -> medium in every session. *Root cause:* the bar on a
   level that proved too slow lived in memory; the first step up of a session needed only one
   window. *Fix:* the bars are stored with their deadline and next length, seeded at the first
   poll, and the first step up waits the hold time. *And the store is hostile input* (re-check):
   a 400-digit integer made `math.isfinite` raise and the 3D view refused to start on every
   start; a bar of 1e18 s barred the level for good. Now an unconvertible number drops the bar,
   and a seeded bar is clamped to `max_retry_s` (both pinned).
10. **Judge a fade by the frame, not by one of its inputs** (look review P1, the twilight
    ramp). *Symptom:* the twilight colours mixed in linear light move the sky horizon 8 codes in
    the first half degree and 52 in the last (the drawn horizon 1.1x and 3.4x) — so they were
    mixed in STOPS instead (1.34–1.48x every half degree). The render tier's dusk sweep then
    failed: the frame went from 0.116 (0.6°) down to 0.023 (−3°/−4°) and UP to 0.034 at −6°,
    because the sky faded faster than the moon came in. *Root cause:* the frame's light is the
    sky AND the fading-in moon, at a rising exposure; a smooth sky alone is not a smooth frame.
    *Fix:* back to linear colours (the ruling's recipe): the frame darkens all the way, 0.116 ->
    0.099 (0°) -> 0.052 (−3°) -> 0.034 (−6°); the sky band's late step is carried by the moon.
    *Tolerance, stated* (re-check): at 0.25° sampling `low` rises by 1.2 % over the last half
    degree (−5.5° 0.0338 -> −6.0° 0.0342; `high` stays flat) — invisible, and below what the 1°
    rows and `test_dusk_never_brightens` (sky term only) can see.
    **Measure the composite the viewer sees before "improving" one ingredient.**
11. **FXAA cannot resolve a picket fence** (look review P1, #529). *Symptom:* a moiré band on
    the fence at low. Measured against a 2x-supersampled render: FXAA's luma error 20.0, 2x MSAA
    12.0 (and its dark-pixel share 18.8 %, worse than FXAA's 12.7 %), 4x MSAA 6.2 (medium 7.2).
    *Fix:* low takes 4x MSAA; on the RTX 4070 its cost was inside the run-to-run spread.
12. **Memory grows while the wind runs — intermittent (FU-L14-2, #534; item 1 of §11.4.20).** *Symptom:* the first soak of the
    default steady state (the plan shown, the wind running; fix round 1) reads 2.6 MB per minute
    of committed memory over 2 minutes and 2.09 over 6 (linear: 1034.2 -> 1045.9 MB, 21,594
    frames, about 0.55 kB a frame); dedicated GPU memory flat. With the QML engine's collector
    called every 5 s: 0.81 MB per minute, in steps. *Root cause:* not isolated — per-frame
    garbage of the `FrameAnimation` handler (`windTime += frameTime`) the V4 collector reclaims
    late, and something it does not. *State:* the registered bound (2.0) is kept as a strict
    `xfail` in `test_view3d_looks_render.py`. Untried: the clock as a `NumberAnimation` (no
    JavaScript per frame). The soak runs with timer-paced frames (`QT_D3D_NO_VBLANK_THREAD=1`,
    which the product does not set); the product's vblank-paced path is unmeasured (the
    re-check's display was asleep: 0 frames presented without the flag).
13. **Qt has no "reduce motion" preference to honour.** `QStyleHints` in Qt 6.11 exposes none
   (checked against the binding; a drift guard in `tests/unit/test_view3d_look_settings.py`
   fails the day one appears), so the setting is the application's own
   (`view3d/reduced_motion`).
