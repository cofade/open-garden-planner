# Object Sprite Provenance (Package 3a, #308 — asset-forge discipline)

Every SVG under `furniture/` and `infrastructure/` MUST be covered here before
it merges (`ogp-external-positioning`: assets without provenance don't ship).

## All 24 sprites (regenerated / created 2026-08-17)
- **Generator**: `scripts/generate_object_sprites.py` — procedural, pure Python
  (stdlib `random`/`math`/`colorsys`), no external model, service, or input
  asset. **The generator IS the provenance record**: every shape, color and
  jitter is derived from the `MATERIALS`/`EMBER`/`FLAME` tables and a
  per-object seed (`"ogp-object-<name>"`).
- **Reproduction**: run the script; identical bytes on every run (pinned by
  `--check` and `tests/unit/test_object_sprite_conformance.py::TestDeterminism`,
  verified on Windows; CI's ubuntu run of the same gate is the cross-platform
  evidence — the generator formats libm-dependent trig at 0.1-unit precision,
  so a 1-ULP platform difference is expected to be invisible, and the gate is
  fail-safe if it is not).
- **License basis**: original in-repo work; distributed under the project
  license (GPL-3.0-or-later).
- **Style contract**: `README.md` (this folder) — "Lush Object", the man-made
  sibling of the #281 "Lush Sprite" plant art. Owner review via contact sheet
  (real QtSvg engine) during the Package-3a manual test.
- **Replaces**: the 15 hand-authored SVGs of 2026-02 (Phase 6, US-6.8/6.9),
  which carried no provenance record and baked a directional drop shadow.

## Files
| Directory | Files |
|---|---|
| `furniture/` | bbq_grill, bench, chair, fire_pit, hammock, hot_tub, lounger, parasol, picnic_table, planter_pot, sandbox, swing, table_rectangular, table_round, trampoline |
| `infrastructure/` | bird_bath, cold_frame, compost_bin, pergola, rain_barrel, raised_bed, tool_shed, water_tap, wheelbarrow |
