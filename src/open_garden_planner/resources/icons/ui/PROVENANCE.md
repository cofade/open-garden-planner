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
| vertical_container.svg | plant-2 |
| wall.svg | wall |
| zoom_fit.svg | zoom-scan |
| zoom_in.svg | zoom-in |
| zoom_out.svg | zoom-out |


### Package 3c additions (#310) — fetched 2026-08-18 by the same script, same tag v3.45.0

88 glyphs for the comprehensive iconography overhaul (status bar, dashboard
tabs, Plants/Garden/File/Edit/View/Help residue, View-menu submenus, emoji /
unicode pseudo-icon replacements, layers panel, weather card, sun-sim toolbar).

| file | Tabler outline glyph |
| ---- | -------------------- |
| about_qt.svg | info-square |
| align.svg | layout-grid |
| align_bottom.svg | layout-align-bottom |
| align_center_h.svg | layout-align-center |
| align_center_v.svg | layout-align-middle |
| align_left.svg | layout-align-left |
| align_right.svg | layout-align-right |
| align_top.svg | layout-align-top |
| amendment.svg | flask |
| autosave.svg | clock-play |
| background_image.svg | photo |
| camera.svg | camera |
| canvas_size.svg | dimensions |
| check.svg | check |
| chevron_down.svg | chevron-down |
| chevron_right.svg | chevron-right |
| chevron_up.svg | chevron-up |
| clock.svg | clock |
| companion.svg | heart-handshake |
| companion_warnings.svg | alert-circle |
| compare_overlay.svg | history-toggle |
| constraints_overlay.svg | link |
| cross.svg | x |
| distribute_h.svg | layout-distribute-horizontal |
| distribute_v.svg | layout-distribute-vertical |
| dynamic_input.svg | keyboard-show |
| exit.svg | door-exit |
| export_csv.svg | file-type-csv |
| export_dxf.svg | file-vector |
| export_pdf.svg | file-type-pdf |
| export_png.svg | file-type-png |
| export_svg.svg | file-type-svg |
| eye.svg | eye |
| eye_off.svg | eye-off |
| frost.svg | snowflake |
| fullscreen.svg | maximize |
| go_to.svg | arrow-right |
| grid.svg | grid-dots |
| guides.svg | line |
| help.svg | help-circle |
| labels.svg | tag |
| language.svg | language |
| location.svg | map-2 |
| lock.svg | lock |
| lock_open.svg | lock-open |
| minimap.svg | map-search |
| overlays.svg | stack-2 |
| plant_manage.svg | leaf |
| plant_search.svg | database-search |
| player_pause.svg | player-pause |
| player_play.svg | player-play |
| recent.svg | history |
| refresh.svg | refresh |
| satellite.svg | satellite |
| scale_bar.svg | ruler |
| season.svg | calendar |
| seasons.svg | calendar-cog |
| seedling.svg | seedling |
| shadows.svg | shadow |
| shopping_list.svg | shopping-cart |
| snap_grid.svg | grid-4x4 |
| snap_intersections.svg | arrows-cross |
| snap_midpoints.svg | point |
| snap_nearest.svg | focus-centered |
| snap_objects.svg | target |
| snap_tangent.svg | circle-dot |
| snapping.svg | magnet |
| soil_overlay.svg | color-filter |
| soil_test.svg | test-pipe |
| spacing_circles.svg | circles-relation |
| star.svg | star |
| status_coords.svg | crosshair |
| status_input.svg | terminal-2 |
| status_tool.svg | tool |
| status_zoom.svg | zoom |
| sun.svg | sun |
| sun_sim.svg | sun-high |
| tab_calendar.svg | calendar-event |
| tab_harvest.svg | basket |
| tab_plan.svg | map |
| tab_tasks.svg | checklist |
| view3d.svg | cube |
| walk.svg | walk |
| warning.svg | alert-triangle |
| weather_fog.svg | cloud-fog |
| weather_rain.svg | cloud-rain |
| weather_snow.svg | cloud-snow |
| weather_storm.svg | cloud-storm |

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

Added 2026-08-18 (Package 3c, #310), same contract and normalizer:

- `lawn.svg` — ground line with four grass blades (the `properties_panel`
  had requested a non-existent `lawn.svg` since Phase 5; the provider
  silently returned `None`)
- `partly_cloudy.svg` — sun with three rays behind a cloud (weather card;
  Tabler v3.45.0 has no `cloud-sun`)

Added 2026-08-23 (issue #338, per-object stacking order), same contract and
normalizer — two offset squares (align_*-style), accent on the square that
moves, chevrons indicating the step:

- `arrange.svg` — two offset squares, the front one accented (Edit ▸
  Arrange submenu icon; no chevron)
- `arrange_front.svg` — front square accented, double chevron pointing up
  (Bring to Front)
- `arrange_forward.svg` — back square accented, single chevron pointing up
  (Bring Forward)
- `arrange_backward.svg` — front square accented, single chevron pointing
  down (Send Backward)
- `arrange_back.svg` — back square accented, double chevron pointing down
  (Send to Back)
