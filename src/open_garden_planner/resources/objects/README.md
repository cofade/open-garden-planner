# Object sprites — style contract (binding)

All SVGs in `furniture/` and `infrastructure/` are **generated** by
`scripts/generate_object_sprites.py`. **Do not hand-edit** — edit the builder /
`OBJECTS` recipe in the script and regenerate; `--check` (and the unit gate
`tests/unit/test_object_sprite_conformance.py`) fails on any drift.

## The "Lush Object" style (Package 3a, issue #308 — the man-made sibling of the #281 plant art)

1. **Top-down view, light from straight above.** Every part shades rim-dark →
   crown-light: symmetric gradients across a part's short axis, radial for
   round parts. **No directional drop shadow is baked** — the canvas item
   paints the single shadow (`GardenItem.SHADOW_OFFSET`, View › Shadows), so
   the art stays correct under the USER-controlled rotation of furniture
   (rule pinned by `test_no_baked_directional_shadow`).
2. **Full Lush parity.** Per-part gradients; a dark **occlusion halo** wherever
   a part sits on another (armrest on seat, lid rim on body, beam on post);
   **material micro-detail** (wood grain + plank gaps + knots, brushed-metal
   crown line, weave hatch + puff shading on fabric, ripples + caustic
   sparkles on water, clumps + highlights on soil/sand/compost, rivets/screws);
   gloss on glossy materials (enamel, brass, glass, water). Objects read as
   rich as the plant sprites, not as calmer "lite" versions.
3. **Palette lives in the generator.** Colors come exclusively from the
   `MATERIALS` anchor table (light/mid/dark/occ/line per material) plus the
   `EMBER`/`FLAME` triads, derived via `mix()`/`lighten()`/`darken()` — never
   hand-edited into an SVG. Enforcement is transitive through byte-determinism.
4. **Geometry.** Each sprite's `viewBox` is `0 0 W H` where `(W, H)` are the
   object's default footprint in cm (`FURNITURE_DEFAULT_DIMENSIONS` — gate:
   `test_default_dimensions_match_viewboxes`). The canvas stretches the art to
   the user's rect (unchanged behaviour), so the art must degrade gracefully
   under mild non-uniform stretch — footprints are rounded rects, round parts
   are generously sized. Circle-tool objects (`table_round`, `parasol`,
   `fire_pit`, `planter_pot`, `bbq_grill`, `rain_barrel`, `water_tap`,
   `trampoline`, `bird_bath`) use a **square** viewBox — a circle item renders
   into a square footprint.
5. **QtSvg subset only** (QSvgRenderer ≈ SVG 1.2 Tiny): `svg defs g path line
   ellipse circle rect linearGradient radialGradient stop`; attributes limited
   to geometry, `fill`/`fill-opacity`/`opacity`/`stroke*`, `transform`,
   gradient stops. **No** filters, masks, clipPath, CSS classes, `<text>`,
   `<image>`, external refs. Rings are drawn as two-subpath paths (nonzero
   winding), circle-clipped planks are computed analytically — there is no
   clipPath.
6. **Deterministic.** Every sprite is seeded by its name
   (`random.Random("ogp-object-<name>")`) — regeneration reproduces identical
   bytes; discrete decisions downstream of float math stay off exact integer
   boundaries.
7. **Budgets (gated).** ≤ 460 elements and ≤ 44 KB per file (~1.2× the densest
   shipped sprite, `hot_tub` at 380 elements / 35,910 bytes, measured 2026-08-17).
8. **Visual weight (gated).** Ink coverage through the real render path
   (`render_furniture_pixmap` at the default footprint, alpha > 10, 2-px
   sampling) within **[0.18, 1.00]**; ≥ 0.25 at 24 px (gallery-thumbnail
   scale, 1-px sampling); and a luminance-spread floor (std ≥ 0.05) so a
   sprite can never degrade to one flat fill. Open structures are legitimately
   airy (swing 0.205, hammock 0.426, pergola 0.530); solid ones fill their
   footprint (sandbox 0.999). Enforced by
   `tests/integration/test_object_sprite_rendering.py`.
9. **Bed/container interiors stay calm.** `raised_bed`, `planter_pot`,
   `cold_frame` are soil containers — plants get placed on them and the grid
   overlay is drawn on top, so their soil is textured but low-contrast.

## Roster

| Directory | Sprites |
|---|---|
| `furniture/` (15) | table_rectangular, table_round, chair, bench, parasol, lounger, bbq_grill, fire_pit, planter_pot, **sandbox, trampoline, hot_tub, swing, picnic_table, hammock** |
| `infrastructure/` (9) | raised_bed, compost_bin, cold_frame, rain_barrel, water_tap, tool_shed, **wheelbarrow, pergola, bird_bath** |

Bold = added in Package 3a (#308). Adding an object type touches eight
registration surfaces in six source files (enum + styles + valid-shape list in
`object_types.py`, ToolType, canvas tool registration, renderer maps + default
dims, height default, gallery entry) plus the three translation contexts — the
checklist lives in §8.23; the `OBJECTS` recipe's `shape` key is cross-checked
by the conformance gate against the "Change Type" menu and square art.

## Changing or adding a sprite

1. Edit the builder (`build_<name>`) or add one + an `OBJECTS` row
   (`view=(W, H)`, `dir`, `build`, `shape`) in `scripts/generate_object_sprites.py`.
2. `venv/Scripts/python.exe scripts/generate_object_sprites.py` (or `--only <name>`).
3. Visually review with the app's real engine (see the `ogp-asset-forge`
   skill, "SVG sprite forge": render grids offscreen, view, iterate — never
   judge by XML or a browser).
4. `pytest tests/unit/test_object_sprite_conformance.py tests/integration/test_object_sprite_rendering.py`
5. New object types: walk the registration checklist (§8.23) and the i18n gate.
