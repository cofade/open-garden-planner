# UI Icon Provenance (#279 — asset-forge discipline)

Every icon in this directory MUST have an entry here (a table row or a
section) before it merges — same rule as the texture set (`ogp-asset-forge`:
no provenance, no merge). `scripts/check_icon_conformance.py` cross-checks
both directions (icon without entry, entry without icon).

## Tabler-vendored icons (MIT)

- **Source**: https://github.com/tabler/tabler-icons — outline variant,
  release **v3.45.0**, license MIT (full text: `LICENSE-tabler-icons.txt`).
- **Fetched**: 2026-07-26 by `scripts/vendor_tabler_icons.py` (the script is
  the reproduction recipe: pinned tag + mapping + normalizer).
- **Normalization**: `scripts/normalize_icons.py` (strip reset path/editor
  junk, canonical serialization). Geometry unchanged.

| file | Tabler outline glyph |
| ---- | -------------------- |
| about.svg | info-circle |
| arc.svg | vector-spline |
| bezier.svg | vector-bezier-2 |
| callout_annotation.svg | message |
| circle.svg | circle |
| connect_ai.svg | sparkles |
| constraint_angle.svg | angle |
| constraint_distance.svg | arrows-horizontal |
| constraint_edge_length.svg | ruler-2 |
| constraint_equal.svg | equal |
| constraint_fixed.svg | lock |
| constraint_h_distance.svg | arrow-autofit-width |
| constraint_v_distance.svg | arrow-autofit-height |
| construction_circle.svg | circle-dashed |
| construction_line.svg | line-dashed |
| copy.svg | copy |
| cut.svg | cut |
| delete.svg | trash |
| driveway.svg | car |
| duplicate.svg | copy-plus |
| ellipse.svg | oval |
| fence.svg | fence |
| file_export.svg | file-export |
| file_import.svg | file-import |
| file_new.svg | file-plus |
| file_open.svg | folder-open |
| file_save.svg | device-floppy |
| file_save_as.svg | files |
| fillet.svg | border-radius |
| find_replace.svg | list-search |
| flower.svg | flower |
| furniture.svg | armchair |
| house.svg | home |
| infrastructure.svg | tools |
| journal_pin.svg | map-pin |
| measure.svg | ruler-measure |
| mirror.svg | flip-horizontal |
| offset.svg | box-margin |
| paste.svg | clipboard |
| path.svg | route |
| polygon.svg | polygon |
| pond.svg | ripple |
| preferences.svg | settings |
| print.svg | printer |
| rectangle.svg | rectangle |
| redo.svg | arrow-forward-up |
| select.svg | pointer |
| select_all.svg | select-all |
| shed.svg | building-warehouse |
| shortcuts.svg | keyboard |
| shrub.svg | plant |
| text_annotation.svg | typography |
| theme.svg | sun-moon |
| tree.svg | tree |
| trim_extend.svg | scissors |
| undo.svg | arrow-back-up |
| vegetable.svg | carrot |
| wall.svg | wall |
| zoom_fit.svg | zoom-scan |
| zoom_in.svg | zoom-in |
| zoom_out.svg | zoom-out |

## Bespoke icons (original work, GPL-3.0-or-later)

Hand-authored in-repo 2026-07-26 on the house contract (24×24, stroke-2
line style, currentColor + accent sentinel), normalized by
`scripts/normalize_icons.py`. No third-party input — Tabler has no
equivalent glyph for these garden/CAD-specific concepts:

- `garden_bed.svg` — top-down bed outline, three accent seedling dots
- `greenhouse.svg` — gabled glass house with glazing bars
- `terrace.svg` — decking square with plank lines
- `constraint_horizontal.svg` — horizontal line, filled endpoints
- `constraint_vertical.svg` — vertical line, filled endpoints
- `constraint_coincident.svg` — concentric circle + center dot
- `constraint_parallel.svg` — two parallel slanted lines
- `constraint_perpendicular.svg` — perpendicular lines + corner square
- `constraint_symmetric.svg` — dashed mirror axis, two mirrored dots
  (Tabler `symmetry-vertical` does not exist at v3.45.0 — 404)
- `chamfer.svg` — beveled corner, accent on the cut segment
