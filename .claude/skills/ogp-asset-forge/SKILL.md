---
name: ogp-asset-forge
description: "Dev-time discipline for adding or regenerating Open Garden Planner textures and 2D art (US-E9, #264). Load when: adding a fill-pattern texture; regenerating a texture (e.g. the known-seamed flagstone.png/glass.png); generating object art or 3D-era materials; choosing texture prompts/post-processing; or answering how assets get provenance and license clearance. The skill prescribes the house style, the mechanical tileability gate, and the provenance rules — assets without provenance don't merge."
---

# OGP Asset Forge — texture & art generation discipline

**This is dev tooling.** Nothing here runs in the shipped app; assets are
static PNGs/SVGs wired through the existing loaders. The skill exists so
any capable model (or human) can add an asset that (a) looks native,
(b) tiles perfectly, (c) has bulletproof provenance.

## 1. The house style (STYLE contract — derived from the shipped set, not invented)

Read 3–4 of the 22+ existing textures (`src/open_garden_planner/resources/textures/`)
before generating anything. Their shared properties, which every new asset
MUST match:

- **256×256 px PNG**, RGB (no alpha in the base texture — tinting handles color).
- **Flat illustrative, not photoreal**: soft shapes, few tones per material
  (4–6), no lighting direction, no specular highlights, no text, no
  perspective — strictly **top-down**.
- **Muted naturalistic palette**: garden-plan colors (greys, browns,
  greens, terracotta); saturation low enough that the runtime color TINT
  (`core/fill_patterns._tint_texture` overlays the user color at ~80/255
  alpha) still reads.
- **Detail scale**: features 4–40 px — readable at typical canvas zoom,
  not noise, not one giant motif.
- Reference exemplars: `wood.png` (structured), `gravel.png` (organic
  scatter), `decking.png`/`corten.png` (the US-E9 pilots, procedurally
  generated — see `scripts/generate_asset_forge_textures.py`).

## 2. Generation methods (in order of preference)

1. **Procedural (preferred)** — extend `scripts/generate_asset_forge_textures.py`:
   deterministic seed, pure Pillow, wrap-stamped primitives (draw at every
   ±W/±H offset) and `_wrap_blur` (blur a 3×3 tiling, crop the center —
   Pillow's plain blur clamps at edges and paints a seam). Seamless BY
   CONSTRUCTION, provenance = the script itself, reproducible bytes.
2. **AI image generation** — any model the developer has access to (the
   skill hardwires NO paid service/MCP; that was #264's explicit rejection
   of the external game-assets skill). Prompt skeleton:
   *"seamless tileable top-down texture of {material}, flat illustrative
   style, muted {palette} tones, no lighting, no perspective, no text,
   256x256"*. Post-process: downscale to 256×256, palette-flatten toward
   4–6 tones (posterize or median-cut), then FIX THE SEAM (offset by
   half-width/half-height and heal, or regenerate) until the mechanical
   gate passes.
3. **CC0/public-domain sources** — allowed (§11.1), but record the exact
   source URL + license snapshot in PROVENANCE.md.

## 2b. SVG sprite forge (object & plant canvas art — the #281 technique)

Plant/object canvas art is SVG **code**, not raster — layered vector shapes
rendered by `core/plant_renderer.py` / `core/furniture_renderer.py`. The
workflow (validated in the #281 style lab, 2026-07-26):

1. **Generate, don't hand-write**: beyond a handful of elements, emit the SVG
   from a seeded procedural generator (rings of leaf paths, per-ring gradients,
   deterministic jitter). The generator is simultaneously the provenance
   record and what makes the whole set regenerable from style parameters.
2. **QtSvg subset only** (QSvgRenderer ≈ SVG 1.2 Tiny): linear/radial
   gradients, opacity, nested transforms, stroke-linecap are safe; **no
   filters, no masks, no clipPath, no CSS classes, no `<text>`** — they
   silently drop or render wrong.
3. **Rotation-safe radial shading**: every plant gets a stable random rotation
   at render time (`plant_renderer._stable_random_for_item`), so never bake a
   directional light. Top-down = light from straight above: dark rim → light
   crown, occlusion shadows radially outward. Per-leaf/per-fruit highlights
   live in the leaf's local frame and stay coherent under any rotation.
4. **The visual self-review loop** — the step that makes results good: render
   with the app's REAL engine (QSvgRenderer offscreen, 256 px and ~64 px),
   actually view the PNGs, grade against the style contract, iterate (cap ~3
   rounds, then owner sign-off). Never judge an SVG by reading its XML, and
   never judge by a browser render — browser ≠ QtSvg.
5. **Owner sign-off on a contact sheet** (HTML: before/after, real canvas
   sizes, simulated rotation, lawn + soil backgrounds) before wiring anything —
   style is sovereign, same as §3.
6. **Object sprites are generated too (Package 3a, #308, ADR-042).**
   `scripts/generate_object_sprites.py` is the single source of every
   furniture/infrastructure SVG ("Lush Object" — contract in
   `resources/objects/README.md`): a `MATERIALS` anchor table + reusable
   material primitives (`plank`/`wood_surface`, `disc`/`ring`, `fabric`,
   `metal_bar`, `glass_pane`, `water_fill`, `granular_fill`, `glow`/`flame`,
   `frame_box`) composed by one builder per object. Two rules that differ
   from plants: furniture rotation is USER-controlled, so **no baked shadow**
   at all (the item-level painted shadow is the single source); and the
   **viewBox is the default footprint in cm** (circle-tool objects ship
   square art). Gates mirror the plant set (`--check` determinism, allowlist,
   budgets ≤ 460 elements / 44 KB, visual-weight band through the real
   renderer). Adding an object TYPE touches 8 source files + 3 translation
   contexts — checklist in §8.23. Watch for a full-rect occlusion halo over
   an interior (it murks the glass/soil under it — halo only under the parts).

## 3. The mechanical gates (no eyeballing)

| Gate | Command | Pass |
|---|---|---|
| Tileability | `venv/Scripts/python.exe scripts/check_texture_tileability.py <file>` | seam/98th-percentile ratio ≤ 1.6 both axes (metric doc in the script header) |
| Suite | `venv/Scripts/python.exe -m pytest tests/unit/test_texture_tileability.py tests/ -q` | green — incl. the legacy-seam list (may only SHRINK) |
| Style | compare side-by-side against the exemplars in §1 | owner's manual sign-off (sovereign) |

## 4. Wiring a new texture (all steps, no parallel loader)

1. PNG into `src/open_garden_planner/resources/textures/<name>.png`.
2. `FillPattern.<NAME> = auto()` + `_TEXTURE_FILES` row (`core/fill_patterns.py`).
3. Display name in `properties_panel.py` `_pattern_names` via `self.tr()`.
4. German translation in `scripts/fill_translations.py` (PropertiesPanel
   context) → run fill + compile → i18n gate green.
5. **PROVENANCE.md entry** (same folder as the textures) — generator/model,
   date, prompt-or-script, license basis, GPL-3 rationale. **No entry, no
   merge** (`ogp-external-positioning`).
6. Full battery + senior review + draft PR (`ogp-change-control`).

## 5. Known regeneration candidates (audit 2026-07-20)

`flagstone.png` and `glass.png` fail the tileability gate (real wrap
seams). Regenerating them is sanctioned FUTURE work for this skill — but
only with explicit owner sign-off per #264 (visual regression risk), and
the legacy-seam list in `tests/unit/test_texture_tileability.py` must
shrink accordingly.

## 6. Fenced wrong paths (#264)

- Adopting the external `agent-skill-game-assets-enhancer` wholesale
  (paid fal.ai API + MCP dependency + game styling — rejected in epic #255).
- Shipping an asset with unclear license basis “temporarily”.
- Baking text, watermarks, lighting direction or non-tileable macro
  features into textures.
- A parallel texture loader — everything goes through `FillPattern`.
- Making any other US wait on asset work (off critical path by design).
