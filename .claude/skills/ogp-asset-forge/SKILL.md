---
name: ogp-asset-forge
description: "Dev-time discipline for adding or regenerating Open Garden Planner textures and 2D art (US-E9 #264, Package 3b #309). Load when: adding or changing a fill-pattern texture (all 24 come out of scripts/generate_asset_forge_textures.py); generating object/plant art or 3D-era materials; judging texture style, tint-readability or tileability; or answering how assets get provenance and license clearance. The skill prescribes the Lush house style, the mechanical gates (pixel-exact --check, tileability, tint band), and the provenance rules — assets without provenance don't merge."
---

# OGP Asset Forge — texture & art generation discipline

**This is dev tooling.** Nothing here runs in the shipped app; assets are
static PNGs/SVGs wired through the existing loaders. The skill exists so
any capable model (or human) can add an asset that (a) looks native,
(b) tiles perfectly, (c) has bulletproof provenance.

## 1. The house style (STYLE contract — "Lush", binding since #309)

Read `scripts/generate_asset_forge_textures.py` and view 3–4 of the 24
shipped textures (`src/open_garden_planner/resources/textures/`) at 1:1 AND
2×2-tiled before generating anything. Every texture MUST match:

- **256×256 px PNG, RGB** (no alpha — tinting handles colour). **1 texture
  px = 1 cm on the canvas** (a tile is 2.56 m): design features at their
  real garden scale (bricks 32×8, beaver-tail tiles 16 wide, flagstones
  ~50 cm, pebbles 5–20 cm, gravel 2–8 mm reads as 2–4 px).
- **Lush, not flat**: visible material detail (grain, crumbs, leaves,
  glazing bars, caustics), **radial rim-dark → crown-light shading per
  element**, **concentric occlusion halos** where elements stack, mottled
  grounds — the man-made/organic sibling of the #281 plant sprites and the
  #308 object sprites. Richness is the brief ("it should be fun to design a
  garden in our planner").
- **Strictly top-down, NO directional light**: the canvas view flips Y and
  fills never rotate with anything, so every shading cue must be
  radial/concentric (halo grows around the body, never offset to a side).
  Symmetric sheen bands are fine; a "light from top-left" gradient is not.
- **Tint-readable contrast**: the runtime tint (`core/fill_patterns._tint_texture`,
  user colour at 80/255 alpha) must recolour the material without
  flattening it. Gated band (`tests/unit/test_texture_forge_conformance.py`):
  mean luminance 40–225, luminance std ≥ 4, local detail ≥ 2 (shipped set:
  compost 47 → glass 215; corten is the smoothest at 2.6). Verify tinted
  renders on the contact sheet with the object's real default fill colour.
- **Seamless by construction** (§3) — never "healed" after the fact.
- Reference exemplars: `wood.png` / `brick.png` (structured), `soil.png` /
  `gravel.png` (organic scatter), `flagstone.png` / `clay.png` (Voronoi),
  `water.png` / `glass.png` (analytic fields), `hedge.png` (leaf primitive).

## 2. Generation methods (in order of preference)

1. **Procedural in the numpy torus painter (the only sanctioned path for
   fill textures)** — extend `scripts/generate_asset_forge_textures.py`:
   add `generate_<name>(rng)` and a `TEXTURES` row. The painter (`Tile`)
   works in float64 on a 2× supersampled C×C torus: every primitive
   (`ellipse`/`blob`/`halo`, `capsule`, `rect` incl. full-height planks,
   `leaf`, `vgrain`) computes analytic anti-aliased coverage on a window
   whose indices are taken modulo C, so anything crossing an edge continues
   on the other side; noise (`lattice_noise`, `fbm`, `fine_grain`) is a
   periodic lattice; `voronoi` uses the torus metric (domain-warp for
   organic slabs); `wrap_blur` is an in-repo separable Gaussian with
   `np.roll`. Structured layouts (courses, planks, laths, panes) must divide
   256 exactly and put **no joint on the wrap** (offset by half a pitch).
   All randomness through the `rng` argument (`random.Random(seed_for(name))`,
   stream-stable across CPython versions); no numpy RNG, no ImageDraw, no
   Pillow filters — Pillow only encodes the PNG. Determinism is **pixel-exact**
   (`--check` decodes the committed PNG and compares arrays; file bytes are
   NOT the contract because the deflate stream depends on the zlib build
   Pillow bundles). Regeneration rewrites a file only when its pixels change.
2. **AI image generation / CC0 sources** — NOT for fill textures any more
   (they'd break the pixel gate and the provenance model). Still allowed for
   one-off illustrations elsewhere, with a PROVENANCE entry recording the
   exact source/model/prompt/license — and never a paid service/MCP (#264's
   explicit rejection of the external game-assets skill).

**Iteration loop (what actually makes them good)**: render → 2×2-tiled
half-scale contact sheet AND 1:1 crops → grade against §1 → fix → repeat
(cap ~3 rounds). Common first-pass failures seen 2026-08-18: round clods /
pebbles read as *bubbles* (too much rim + gloss → soften rim, gloss ≤ 0.12,
vary shapes/tones, densify); water caustics too stormy for a pond; chips too
sparse (ground must not dominate mulch); wavy ridges with full-width
cross-cracks read as *bamboo* (use wandering sub-ridges + short offset
cracks); square panes read as mosaic (glazing is taller than wide). A hidden
seam is located by measuring, not guessing: `|row0 − row255|` per column
(or the transpose) names the offending primitive — see debugging-playbook
row 36.

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
   renderer). Adding an object TYPE touches eight registration surfaces in
   six source files + 3 translation contexts — checklist in §8.23; the recipe's
   `shape` key is gate-checked against the "Change Type" menu. Watch for a full-rect occlusion halo over
   an interior (it murks the glass/soil under it — halo only under the parts).

## 3. The mechanical gates (no eyeballing)

| Gate | Command | Pass |
|---|---|---|
| Pixel determinism | `venv/Scripts/python.exe scripts/generate_asset_forge_textures.py --check` | every committed PNG decodes to the generator's pixels (pinned by `tests/unit/test_texture_forge_conformance.py`, which also pins registry ↔ `_TEXTURE_FILES` ↔ files, 256² RGB, the tint band, gate teeth, and that the legacy Qt generator stays deleted) |
| Tileability | `venv/Scripts/python.exe scripts/check_texture_tileability.py [file]` | seam/98th-percentile ratio ≤ 1.6 both axes for ALL 24 (`tests/unit/test_texture_tileability.py`; `KNOWN_SEAMED_LEGACY` is empty and gated empty — recalibrate the 1.6 only with a written rationale in the checker header + test) |
| On-canvas (§8.10) | `venv/Scripts/python.exe -m pytest tests/integration/test_texture_forge_rendering.py` | every pattern paints with detail through panel → brush → item → flipped `scene.render`; the wrap boundary of the item's real tinted brush is inside the fill's own edge family; red vs blue fill colours move the hue without flattening; thumbnails render; greenhouse tool draws GLASS |
| Style | contact sheet: legacy · new 1:1 · 2×2 tiled · tinted with the default fill colour | owner's manual sign-off (sovereign) |

## 4. Wiring a new texture (all steps, no parallel loader)

1. `generate_<name>(rng)` + `TEXTURES` row in `scripts/generate_asset_forge_textures.py`; run it → `src/open_garden_planner/resources/textures/<name>.png`.
2. `FillPattern.<NAME> = auto()` + `_TEXTURE_FILES` row (`core/fill_patterns.py`).
3. Display name in `properties_panel.py` `_pattern_names` via `self.tr()`.
4. German translation in `scripts/fill_translations.py` (PropertiesPanel
   context) → run fill + compile → i18n gate green.
5. **PROVENANCE.md entry** (same folder as the textures) — per-file register
   row (recipe, date). **No entry, no merge** (`ogp-external-positioning`).
6. The three gates in §3 + full battery + senior review + draft PR (`ogp-change-control`).

## 5. Regenerating an existing texture

Edit its `generate_<name>` recipe (never the PNG), run the generator (only
changed files are rewritten), run the three gates, build the contact sheet,
and record the change in `PROVENANCE.md` (per-file register + history). A
style-level change needs owner sign-off; the manual test of the PR is the
final one. Since #309 there are no grandfathered seams left — a texture that
fails the seam gate is a bug in its recipe, not a candidate list entry.

## 6. Fenced wrong paths (#264)

- Adopting the external `agent-skill-game-assets-enhancer` wholesale
  (paid fal.ai API + MCP dependency + game styling — rejected in epic #255).
- Shipping an asset with unclear license basis “temporarily”.
- Baking text, watermarks, lighting direction or non-tileable macro
  features into textures.
- A parallel texture loader — everything goes through `FillPattern`.
- A second texture generator or a hand-edited PNG — one forge, one pixel gate
  (the Qt-painted `scripts/generate_textures.py` was deleted in #309 and
  `test_legacy_qt_generator_is_gone` keeps it deleted).
- Byte-comparing PNGs as the determinism gate — the deflate stream is a
  property of the zlib build, not of the art; compare decoded pixels.
- Making any other US wait on asset work (off critical path by design).
