# Texture Provenance (US-E9, #264 — asset-forge discipline)

Every texture added from US-E9 onward MUST have an entry here before it
merges (`ogp-external-positioning`: assets without provenance don't ship).
Format: file · generator/model · date · prompt-or-script · license basis ·
GPL-3 distribution rationale.

## decking.png
- **Generator**: `scripts/generate_asset_forge_textures.py` (procedural,
  pure Pillow, deterministic seed 42) — no external model or service.
- **Date**: 2026-07-20
- **Reproduction**: run the script; identical bytes for the same seed
  AND Pillow version (verified on Pillow 12.1.0 — `GaussianBlur` output
  is not contractually stable across Pillow releases, so reproducibility
  is in-practice per environment, not in-principle).
- **License basis**: original work generated in-repo; no third-party
  input. Distributed under the project license (GPL-3.0-or-later).
- **Tileability**: mechanically verified — `scripts/check_texture_tileability.py`
  (seam-vs-98th-percentile metric, threshold 1.6), pinned by
  `tests/unit/test_texture_tileability.py`.

## corten.png
- Same generator/date/license/verification as `decking.png`
  (`generate_corten`, seed shared).

## Legacy set (bark … wood, 22 files, pre-US-E9)
- Created before this provenance discipline (Phase 1 asset pipeline,
  §8.5: "AI-generated illustrations in consistent style"; §11.1 sanctions
  AI-generated/CC0 textures). Grandfathered — not retroactively documented.
- Mechanical audit 2026-07-20: `flagstone.png` and `glass.png` FAIL the
  tileability check (visible wrap seams) — recorded as regeneration
  candidates for the `ogp-asset-forge` skill; do NOT regenerate without
  owner sign-off (visual regression risk, issue #264 rule).
