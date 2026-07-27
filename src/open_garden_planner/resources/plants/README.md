# Plant sprites — style contract (binding)

All SVGs in `species/` (108) and `categories/` (15) are **generated** by
`scripts/generate_plant_sprites.py`. **Do not hand-edit** — edit the recipe
table in the script and regenerate; `--check` (and the unit gate
`tests/unit/test_plant_sprite_conformance.py`) fails on any drift.

## The "Lush Sprite" style (user-approved 2026-07-26, issue #281)

1. **Top-down view, radial shading only.** Light comes from straight above:
   dark rim → light crown. Never bake a directional light — the canvas
   applies a stable random rotation per plant (`core/plant_renderer.py`),
   and radial shading stays correct under any rotation.
2. **Individual leaves in shingled rings.** Each leaf: dark occlusion copy
   underneath (the depth effect), body with a linear gradient from warm
   light tip to cool dark base, optional gloss inset + midrib.
3. **Signature features on top**: glossy fruit (radial gradient + occlusion
   ring + white specular), chunky bloom clusters/puffs, pods, umbels, and
   for root vegetables the bulb "shoulder" visible at the center.
4. **Recognizability beats botany** at plan scale: every species keeps one
   signature cue (fruit color, bloom shape, rib color, bulb, silhouette).
5. **QtSvg subset only** (QSvgRenderer ≈ SVG 1.2 Tiny): linear/radial
   gradients, opacity, transforms, stroke-linecap. **No** filters, masks,
   clipPath, CSS classes, `<text>`, `<image>`, external refs.
6. **Geometry**: viewBox `0 0 100 100`, content inside radius ≈46 around
   (50, 50). Exception: `categories/hedge_section.svg` keeps its legacy
   rectangular viewBox `10 25 80 50`.
7. **Deterministic**: every sprite is seeded by its name — regeneration
   reproduces identical bytes.

## Changing or adding a sprite

1. Edit `SPECIES` / `CATEGORIES` in `scripts/generate_plant_sprites.py`
   (archetype + palette + feature recipe; new species also need a
   `_SPECIES_FILES` alias in `core/plant_renderer.py`).
2. `venv/Scripts/python.exe scripts/generate_plant_sprites.py`
3. Visually review with the app's real engine (see the `ogp-asset-forge`
   skill, "SVG sprite forge": render grids offscreen, view, iterate — never
   judge by XML or a browser).
4. `pytest tests/unit/test_plant_sprite_conformance.py tests/integration/test_plant_sprite_rendering.py`
5. Owner sign-off on a contact sheet for style changes (style is sovereign).
