# Texture Provenance (US-E9 #264 → Package 3b #309, ADR-042 / FR-30)

Every texture in this folder MUST have an entry here before it merges
(`ogp-external-positioning`: assets without provenance don't ship). Since
Package 3b (2026-08-18) the entry is the same for all 24 files, because they
all come out of one generator:

- **Generator**: `scripts/generate_asset_forge_textures.py` — procedural,
  in-repo, **numpy float64 painter on a torus** (analytic anti-aliased
  coverage, radial rim → crown shading, concentric occlusion halos, periodic
  lattice/fBm noise, torus Voronoi, in-repo wrap-aware Gaussian blur); Pillow
  is used only to encode/decode PNG. **No external model, service, photo or
  third-party asset was used for any texture.**
- **Seed**: one deterministic string per texture, `ogp-<name>-lush`
  (`seed_for()`), fed to `random.Random` — stream-stable across CPython
  versions and platforms.
- **Date**: 2026-08-18 (all 24 regenerated in the "Lush" language; the
  US-E9 pilots decking/corten of 2026-07-20 and the #281 hedge of
  2026-07-27 were re-rendered through the same painter — their pixels
  changed, their look and seeds were kept).
- **Reproduction**: run the script; `--check` regenerates in memory and
  compares the DECODED PIXELS of every committed PNG (pinned by
  `tests/unit/test_texture_forge_conformance.py`). Pixels — not file bytes —
  are the contract: PNG is lossless, but the deflate stream depends on the
  zlib build Pillow bundles, so a Windows wheel and a Linux CI wheel may
  encode identical pixels to different bytes. Regeneration rewrites a file
  only when its pixels change (no cross-platform git noise).
- **License basis**: original work generated in-repo; distributed under the
  project license (GPL-3.0-or-later).
- **Tileability**: seamless BY CONSTRUCTION (every primitive is painted with
  torus-wrapped window indices; noise fields are periodic; structured
  layouts divide the tile exactly, so a joint either straddles the wrap
  symmetrically or lies clear of it — never near it asymmetrically);
  mechanically verified by `scripts/check_texture_tileability.py`
  (seam-vs-98th-percentile metric, threshold 1.6 unchanged since #264),
  pinned for ALL 24 files by `tests/unit/test_texture_tileability.py`
  (parametrized over every file — the #264 grandfather list was emptied and
  deleted) and on the real canvas brush (both axes) by
  `tests/integration/test_texture_forge_rendering.py`.
- **Style**: the "Lush" texture contract — `ogp-asset-forge` skill §1 and
  docs §8.24. Owner sign-off: contact sheets (legacy · new · 2×2 tiled ·
  tinted with the real default fill colour) sent 2026-08-18; final sign-off is
  the Package-3b manual test of the draft PR.

## Per-file register (all: generator above, seed `ogp-<name>-lush`, 2026-08-18)

| File | Material recipe (builder) | Notes |
|---|---|---|
| `bark.png` | `generate_bark` — 12 wavy ridges, wandering sub-ridges that split/merge, fissures, short cross-cracks, lenticels | replaces 2026-03 legacy |
| `brick.png` | `generate_brick` — 24 running-bond courses × 8, six reds, bevelled, mortar grain (a joint straddles the wrap symmetrically) | replaces legacy |
| `clay.png` | `generate_clay` — ochre mottle, two-scale Voronoi shrinkage cracks (low contrast), pits | replaces legacy |
| `compost.png` | `generate_compost` — dark crumb, clumps with occlusion, straw, leaf bits, eggshell, twigs | replaces legacy |
| `concrete.png` | `generate_concrete` — cloudy mottle, aggregate speckle, pits | replaces legacy |
| `corten.png` | `generate_corten` — three-scale rust mottle, faint vertical weather streaks, speckle | US-E9 pilot re-rendered (2026-07-20 → 2026-08-18) |
| `decking.png` | `generate_decking` — 4 boards (64 cm), grain, knots, gap shadow, screw heads on 64-cm joists; joints at x = 32 + 64k | US-E9 pilot re-rendered |
| `flagstone.png` | `generate_flagstone` — domain-warped torus Voronoi slabs, sandy joints, rim → crown slabs | replaces legacy; its wrap seam (3.35/3.82) is gone |
| `glass.png` | `generate_glass` — 4×2 panes (64×128 cm), glazing bars, sheen bands mirror-symmetric about the pane centre, screws | replaces legacy; its wrap seam (2.14/2.20) is gone — default greenhouse fill |
| `grass.png` | `generate_grass` — mottled ground, dark blade shadow layer, 2400 two-tone blades | replaces legacy |
| `gravel.png` | `generate_gravel` — 2000 shaded stones with halos, greys/tans/whites | replaces legacy |
| `hedge.png` | `generate_hedge` — 300 occluded pointed almond leaves, two-tone (#281 language) | #281 pilot re-rendered (2026-07-27 → 2026-08-18) |
| `lattice.png` | `generate_lattice` — two analytic diagonal lath families (8 each), woven over/under with contact occlusion, foliage ground | replaces legacy |
| `mulch.png` | `generate_mulch` — 640 layered flakes/chunks in eight browns, occlusion, splinters | replaces legacy |
| `pebbles.png` | `generate_pebbles` — 370 shaded river pebbles (14 tones), soft gloss, halos, sand ground | replaces legacy |
| `roof_tiles.png` | `generate_roof_tiles` — 12 staggered courses of beaver-tail tiles, overlap occlusion; wrapped overhang repainted (same RNG state) for seam-correct layering and tone | replaces legacy; overhang RNG replay fixed after senior review 2026-08-18 |
| `sand.png` | `generate_sand` — pale ground, dune mottle, fine grain, quartz glints | replaces legacy |
| `slate.png` | `generate_slate` — 5 courses of random-width slabs (one wraps), cleft streaks, bevels | replaces legacy |
| `soil.png` | `generate_soil` — warm mottle, damp patches, 700 crumbs + 120 clods (soft halos), stones, specks | replaces legacy |
| `stone.png` | `generate_stone` — 10 running-bond courses × 6 sandstone pavers, bevels, speckle, chips | replaces legacy |
| `terracotta.png` | `generate_terracotta` — 6×6 tiles (42 cm) with grout, per-tile tone, bevels, firing speckle | replaces legacy |
| `water.png` | `generate_water` — depth mottle, two-scale ridged-fBm caustics (calm), ripple bands, sparkles | replaces legacy |
| `wildflower.png` | `generate_wildflower` — looser warm grass, small leaves, 58 flower heads in seven colours, buds | replaces legacy |
| `wood.png` | `generate_wood` — 8 golden planks (32 cm), wavy grain, knots, bevelled joints at x = 16 + 32k | replaces legacy |

## History

- **2026-03**: 22 legacy textures painted with `QPainter` by
  `scripts/generate_textures.py` (Phase 1 asset pipeline; grandfathered
  without per-file provenance). Removed in #309.
- **2026-07-20 (US-E9, #264)**: `decking.png` / `corten.png` pilots from the
  first Pillow forge (fixed seed 42, `ImageFilter.GaussianBlur` — reproducible
  per Pillow version only); tileability gate + this file introduced;
  `flagstone.png` / `glass.png` recorded as seamed regeneration candidates.
- **2026-07-27 (#281 / PR #282)**: `hedge.png` regenerated in the Lush leaf
  language (seed `ogp-hedge-lush`).
- **2026-08-18 (#309, Package 3b)**: all 24 textures regenerated by the
  numpy torus painter; Pillow blur removed; pixel-exact `--check`; seam list
  emptied; legacy Qt generator deleted.
