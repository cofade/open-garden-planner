## Case study: first-launch maximization capped a headless test window (PR #978)

**Symptom:** the Linux coverage shard saw an empty legend rectangle in the
Hours of Sun workflow after the map and warning badge had settled.

**Wrong theory:** a pending paint left the legend rectangle stale. Tagged
paint probes found that the key reached the painter on every frame.

**Evidence:** `[978-LEGEND] paint (0, 0, 0, 0)` showed a 796 × 796 window
and a 329 px viewport on the package and its master base. The full key was
too wide, the compact key hit the scale bar, and lifting it hit the minimap.

**Root cause:** the first-launch window was still maximized. The Linux offscreen
platform kept its virtual screen dimensions despite the fixture's resize request.

**Fix:** call `showNormal()` before `resize()`. The control then painted a
378 × 32 px legend in a 1033 px viewport and passed the original assertions in
`tests/integration/test_sun_map_workflow.py`.

**Lesson:** normalize window state before requesting a size for a geometry-sensitive
test. Exercise deliberate narrow-view fallback in a separate case.
