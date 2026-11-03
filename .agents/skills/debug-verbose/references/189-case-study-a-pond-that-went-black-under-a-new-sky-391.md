## Case study: a pond that went black under a new sky (#391)

- **Symptom:** with the atmosphere sky (a Qt 6.12 `SkyMaterial`) the garden's ponds turned
  near-black at golden hour, sunset and under cloud; under the painted sky they were fine.
  Every board gate stayed green — none measures water. The `ogp-3d-reviewer` pass found it.
- **Wrong theories:** the atmosphere's light probe too dim for water (the lit grass read the
  same under both skies, so the probe's level was right); the water's own colour constants.
- **Key evidence:** the render tier's raised pool rendered with the water shader's sky term
  guarded two ways, everything else equal: (1, 18, 32) at a 4° sun with the guard on
  `QSSG_ENABLE_LIGHT_PROBE` alone, (6, 41, 65) with it widened, the painted sky's
  (5, 40, 65) identical either way.
- **Root cause:** under a `SkyMaterial` Qt calls the custom material's `IBL_PROBE()` and
  includes the probe samplers, but leaves `QSSG_ENABLE_LIGHT_PROBE` false; the guard L1.2
  wrote for "no probe at all" compiled the sky term out. Nothing warned.
- **Fix:** `#if QSSG_ENABLE_LIGHT_PROBE || defined(SAMPLE_PROBE_GLSLLIB)` in `water.frag` and
  `water_door.frag` (PF-E3D-15), pinned by a QML unit test.
- **Lesson:** when a new engine path feeds an old shader, render the old shader's surface
  under it and measure THAT surface — a gate that reads only the sky and the grass cannot
  see a material that silently lost a term.
