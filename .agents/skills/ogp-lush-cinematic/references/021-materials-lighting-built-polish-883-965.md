# Built-material stability, night fill, resting live shadow fit and built-world polish (#883–#965)

Summary of the measured values and rules landed in the 3D materials, lighting and built-world
polish package (`#883`, `#884`, `#887`, `#894`, `#953`, `#957`, `#958`, `#959`, `#961`, `#965`).
Where this reference updates a number from historical migrated references `003` (night/twilight
fill) or `004` (material roughness/specular), this reference is the current authority.

## Ultra SSR roughness floor & water SSR decoupling (#883, #958)

- Qt Quick 3D's Ultra SSR (`reflectionEnabled: true`) reflects aggressively below roughness
  `0.70`, causing shimmer on glossier built parts and turning courtyard pools into house mirrors.
- `steel`, `iron`, `enamel` and `glass_pane` sit at `roughness = 0.70` (keeping their specular
  amounts `0.50 / 0.35 / 0.15 / 0.40`).
- `water.frag` and `water_door.frag` expose `uSsrRough` (`0.40`) for `ROUGHNESS = uSsrRough` in
  `MAIN()`, while `SPECULAR_LIGHT` and `IBL_PROBE` keep reading `uRough` (`0.02`) for sun glints
  and sky reflections. At `0.02` pools mirrored walls like chrome; at `0.75` Ultra SSR dropped out
  completely leaving flat blue water; at `0.40` both `mediterranean-courtyard` and `modern-garden`
  show soft, realistic water reflections on Ultra.

## Linear albedo scale for noon clipping (#884)

- `Surface.albedo_scale` (`surfaceAlbedo` / `surfaceAlbedoSrgb` on `vcPart` / `roofPart`,
  `uAlbedo` in `built_detail.frag` / `built_snow.frag` / `screen.frag`) scales diffuse albedo
  linearly without touching `DEFAULT_SURFACE` (`1.0`):
  - `roof_tile` / `roof_cap`: `0.76`
  - `wood` / `plaster`: `0.80`
  - `masonry`: `0.82`
  - `stone` / `concrete`: `0.85`
  - `wood_cladding`: `0.86`
  - `corten`: `0.88`
  - `flat_roof`: `0.45` (`roughness=0.95, specular=0.0`)
- Measured on `family-garden` noon (`clip_r_255`): Low `1.169% -> 0.298%`, High `0.329% -> 0.029%`,
  Ultra `0.399% -> 0.031%`; close-up roof/plaster `4.942% -> 0.116%`; Beauty Board `noon_high.png`
  roof clip = 1 px (`+4.2°` vs 2D terracotta).

## Roof/wall detail scale and SSAO bias floor (#887)

- `shingle`: `SLATE` at `128 cm`, normal `1.2`, contrast `0.35`.
- `roof_cap`: plain surface (`detail=None`), used by `ROOF_TILE_CAP` and `SHINGLE_CAP`.
- `masonry`: `STONE` at `128 cm` (~21 cm courses), normal `1.8`, contrast `0.75`.
- `look.AO_FLAT_BIAS_CM` (and `Garden.qml` default `aoBias`): `1.0 -> 1.4 cm`, removing
  grazing close-up SSAO concentric bands on flat fascia/plaster.

## Live shadow fitting at rest (#894)

- `Workspace` unlocks `fittedShadows = false` immediately during camera motion (orbits/walks
  stay shimmer-free) and locks `fittedShadows = true` after `SHADOW_FIT_DELAY_MS = 250 ms` of
  camera rest so the live view matches saved photos. `Quick3DHost.capture(fitted_shadows=None)`
  preserves the view's current fit when `None` and always restores `fitted_before` in `finally:`.

## Night minimum ambient fill (#953)

- `look.night_fill_linear(look)` (`NIGHT_FILL_SKY_SHARE = 0.75`) is zero by day, ramps smoothly
  through twilight with `1 - 0.4 * cloud`, stays collinear with `look.sky.top` and is radiance-
  capped at `NIGHT.sky_top` so twilight never bumps upward. Folded into `twilight_fill`
  (keeping `TWILIGHT_FILL_DAY_SHARE = 0.4` and `TWILIGHT_FILL_TARGET = ((TWILIGHT_DEG, 1.0), (-3.0, 1.02), (NIGHT_BELOW_DEG, 1.035))`):
  `5.89°` sunset stays `(0, 0, 0)`, dusk/dawn stays monotone across every preset (`low`..`ultra`)
  and all five weathers, and moon-away walls on `modern-garden` at night (`sky_light=True`) move
  from `87.56%` `<= 3` (`p25 [0, 0, 0]`) to `0.65%` (`p25 [0, 2, 11]`, frame mean luma `16.52`).

## Built-world fidelity (#957, #959, #961, #965)

- `#957`: `RAISED_BED` architectural 2D fills (`CORTEN` -> `corten`, `STONE`/`BRICK`/`FLAGSTONE`/`SLATE`
  -> `masonry`, `CONCRETE`/`CLAY` -> `concrete_wall`, `TERRACOTTA` -> `terracotta`)
  render tinted perimeter walls in their surface while keeping `soil_surface_cm` exact;
  `SOLID`/`WOOD`/default stays oak planks. `modern-garden` uses real `RAISED_BED` Corten beds.
- `#959`: `pebbles` and `compost` textures re-authored matte (`gloss=0.0`) in
  `scripts/generate_asset_forge_textures.py` (`PROVENANCE.md` updated; tileability `compost`
  `0.43 / 0.49`, `pebbles` `0.70 / 0.61` vs `1.6` threshold).
- `#961`: ground `POND_POOL` polygons with `>= 5` vertices per ring (`is_natural_pond`) smooth
  convex corners inward via clamped quadratic Bézier fillets (`NATURAL_POND_MAX_CUT_CM = 5.5 cm`,
  `BANK_OUT_CM = 7.0 cm`, reflex corners skipped) with a low flush earth shore (`BANK_UP_CM = 1.35 cm`
  strictly below `DECK_TOP_CM = 2.5 cm` so overhanging pond decks clear it) and darker olive-green
  natural water (`NATURAL_POND_WATER_WEIGHT = (0.46, 0.58, 0.28, 1.0)`). Gravel path rims sit at
  `GRAVEL_RIM_CM = 1.8 cm` (`< DECK_TOP_CM`), and `GroundBaker(surface_outlines=False)` suppresses
  2D CAD outline strokes on `LAWN`/`GARDEN_BED`/`TERRACE_PATIO`/`DRIVEWAY`/`POND_POOL` in 3D.
- `#965`: flat-roofed houses use `MODERN_HOUSE_SPEC` (wide/tall single-pane dark-framed windows,
  no cottage crossbars, modern door). Explicit flat roofs carry neutral matte charcoal `flat_roof`
  (`roughness=0.95`, `specular=0.0`, `albedo_scale=0.45`) for `CONCRETE`/`SOLID` fills, while
  custom 2D fills (e.g. `GRASS` green roofs) switch to matte `concrete` (`roughness=0.95`,
  `specular=0.0`, `albedo_scale=0.85`) on the material path (`quick3d/materials.fill_surface_name`,
  `host.set_part_fill`) with no geometry rebuild, matching automatic ridge-less flat houses.
