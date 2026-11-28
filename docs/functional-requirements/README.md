# Functional Requirements

The functional requirements of Open Garden Planner, one topic file per area.

Every requirement has exactly one prefixed ID, `FR-<PREFIX>-nn`, and every prefix belongs
to exactly one topic file. **This index is generated** by `scripts/generate_doc_indexes.py`
from each file's front matter; do not edit it by hand. To add a requirement, append
`- **FR-<PREFIX>-nn**: …` with the prefix's next free number (table below) to the file that
owns the prefix. A new prefix goes into one file's `prefixes` list. The rules are in the
ADR-083 addendum; `--check` runs in the test suite.

## Topic files

| File | Title | Prefixes | Requirements |
|---|---|---|---|
| [3d/analyze.md](3d/analyze.md) | Analyze in 3D | FR-3D-ANALYZE | 8 |
| [3d/built.md](3d/built.md) | Built world in 3D | FR-3D-BUILT | 16 |
| [3d/forge.md](3d/forge.md) | Plant Forge | FR-3D-FORGE | 7 |
| [3d/ground.md](3d/ground.md) | 3D ground | FR-3D-GROUND | 9 |
| [3d/live.md](3d/live.md) | Living garden | FR-3D-LIVE | 10 |
| [3d/look.md](3d/look.md) | 3D look, sky and motion | FR-3D-LOOK | 9 |
| [3d/photo.md](3d/photo.md) | Photo mode | FR-3D-PHOTO | 3 |
| [3d/plants.md](3d/plants.md) | 3D plants | FR-3D-PLANT | 8 |
| [3d/preparation.md](3d/preparation.md) | 3D scene preparation | FR-3D-PREP | 2 |
| [3d/selection.md](3d/selection.md) | 3D selection | FR-3D-SELECT | 5 |
| [3d/tour.md](3d/tour.md) | Camera tours | FR-3D-TOUR | 5 |
| [3d/walk.md](3d/walk.md) | Walkthrough | FR-3D-WALK | 3 |
| [3d/workspace.md](3d/workspace.md) | 3D workspace | FR-3D-WS | 14 |
| [agent-api.md](agent-api.md) | Agent API | FR-AGENT | 32 |
| [canvas.md](canvas.md) | Canvas | FR-CANVAS, FR-GRID, FR-IMG | 22 |
| [distribution.md](distribution.md) | Distribution | FR-STATS | 4 |
| [editing.md](editing.md) | Drawing and editing | FR-DRAW, FR-EDIT, FR-SPLIT, FR-DRILL, FR-GROUP, FR-TOOL-ESC | 47 |
| [files-export.md](files-export.md) | Files, export and examples | FR-FILE, FR-EXP, FR-IMP, FR-SAFETY, FR-EXAMPLE | 38 |
| [garden-records.md](garden-records.md) | Garden records | FR-SOIL, FR-HARVEST, FR-PEST, FR-JOURNAL, FR-SHOP, FR-TASK | 56 |
| [objects-layers.md](objects-layers.md) | Objects and layers | FR-OBJ, FR-LAYER, FR-STACK, FR-BED, FR-CONTAINER | 43 |
| [plants.md](plants.md) | Plants | FR-PLANT, FR-GUILD, FR-LIB, FR-TIMELINE | 42 |
| [precision.md](precision.md) | Precision | FR-SNAP, FR-INPUT, FR-REF, FR-MEAS | 32 |
| [sun-shade.md](sun-shade.md) | Sun and shade | FR-SUN | 17 |
| [ui-look.md](ui-look.md) | User interface and look | FR-UI, FR-UI-THEME, FR-UI-ICON, FR-UI-PREF, FR-UI-SIDEBAR, FR-ICON-3C, FR-VIS, FR-PLANT-ART, FR-OBJ-ART, FR-TEX, FR-I18N | 78 |

## Prefixes

| Prefix | File | Requirements | Next free ID |
|---|---|---|---|
| FR-3D-ANALYZE | [3d/analyze.md](3d/analyze.md) | 8 | FR-3D-ANALYZE-09 |
| FR-3D-BUILT | [3d/built.md](3d/built.md) | 16 | FR-3D-BUILT-14 |
| FR-3D-FORGE | [3d/forge.md](3d/forge.md) | 7 | FR-3D-FORGE-08 |
| FR-3D-GROUND | [3d/ground.md](3d/ground.md) | 9 | FR-3D-GROUND-10 |
| FR-3D-LIVE | [3d/live.md](3d/live.md) | 10 | FR-3D-LIVE-11 |
| FR-3D-LOOK | [3d/look.md](3d/look.md) | 9 | FR-3D-LOOK-10 |
| FR-3D-PHOTO | [3d/photo.md](3d/photo.md) | 3 | FR-3D-PHOTO-04 |
| FR-3D-PLANT | [3d/plants.md](3d/plants.md) | 8 | FR-3D-PLANT-09 |
| FR-3D-PREP | [3d/preparation.md](3d/preparation.md) | 2 | FR-3D-PREP-03 |
| FR-3D-SELECT | [3d/selection.md](3d/selection.md) | 5 | FR-3D-SELECT-06 |
| FR-3D-TOUR | [3d/tour.md](3d/tour.md) | 5 | FR-3D-TOUR-06 |
| FR-3D-WALK | [3d/walk.md](3d/walk.md) | 3 | FR-3D-WALK-04 |
| FR-3D-WS | [3d/workspace.md](3d/workspace.md) | 14 | FR-3D-WS-15 |
| FR-AGENT | [agent-api.md](agent-api.md) | 32 | FR-AGENT-32 |
| FR-BED | [objects-layers.md](objects-layers.md) | 5 | FR-BED-06 |
| FR-CANVAS | [canvas.md](canvas.md) | 4 | FR-CANVAS-05 |
| FR-CONTAINER | [objects-layers.md](objects-layers.md) | 9 | FR-CONTAINER-10 |
| FR-DRAW | [editing.md](editing.md) | 14 | FR-DRAW-15 |
| FR-DRILL | [editing.md](editing.md) | 3 | FR-DRILL-04 |
| FR-EDIT | [editing.md](editing.md) | 25 | FR-EDIT-26 |
| FR-EXAMPLE | [files-export.md](files-export.md) | 14 | FR-EXAMPLE-15 |
| FR-EXP | [files-export.md](files-export.md) | 8 | FR-EXP-09 |
| FR-FILE | [files-export.md](files-export.md) | 8 | FR-FILE-09 |
| FR-GRID | [canvas.md](canvas.md) | 5 | FR-GRID-06 |
| FR-GROUP | [editing.md](editing.md) | 1 | FR-GROUP-02 |
| FR-GUILD | [plants.md](plants.md) | 4 | FR-GUILD-05 |
| FR-HARVEST | [garden-records.md](garden-records.md) | 10 | FR-HARVEST-11 |
| FR-I18N | [ui-look.md](ui-look.md) | 13 | FR-I18N-14 |
| FR-ICON-3C | [ui-look.md](ui-look.md) | 6 | FR-ICON-3C-07 |
| FR-IMG | [canvas.md](canvas.md) | 13 | FR-IMG-14 |
| FR-IMP | [files-export.md](files-export.md) | 4 | FR-IMP-05 |
| FR-INPUT | [precision.md](precision.md) | 4 | FR-INPUT-05 |
| FR-JOURNAL | [garden-records.md](garden-records.md) | 8 | FR-JOURNAL-09 |
| FR-LAYER | [objects-layers.md](objects-layers.md) | 10 | FR-LAYER-11 |
| FR-LIB | [plants.md](plants.md) | 7 | FR-LIB-08 |
| FR-MEAS | [precision.md](precision.md) | 10 | FR-MEAS-11 |
| FR-OBJ | [objects-layers.md](objects-layers.md) | 9 | FR-OBJ-10 |
| FR-OBJ-ART | [ui-look.md](ui-look.md) | 5 | FR-OBJ-ART-06 |
| FR-PEST | [garden-records.md](garden-records.md) | 8 | FR-PEST-09 |
| FR-PLANT | [plants.md](plants.md) | 24 | FR-PLANT-27 |
| FR-PLANT-ART | [ui-look.md](ui-look.md) | 5 | FR-PLANT-ART-06 |
| FR-REF | [precision.md](precision.md) | 6 | FR-REF-07 |
| FR-SAFETY | [files-export.md](files-export.md) | 4 | FR-SAFETY-05 |
| FR-SHOP | [garden-records.md](garden-records.md) | 8 | FR-SHOP-09 |
| FR-SNAP | [precision.md](precision.md) | 12 | FR-SNAP-13 |
| FR-SOIL | [garden-records.md](garden-records.md) | 13 | FR-SOIL-14 |
| FR-SPLIT | [editing.md](editing.md) | 3 | FR-SPLIT-04 |
| FR-STACK | [objects-layers.md](objects-layers.md) | 10 | FR-STACK-11 |
| FR-STATS | [distribution.md](distribution.md) | 4 | FR-STATS-05 |
| FR-SUN | [sun-shade.md](sun-shade.md) | 17 | FR-SUN-18 |
| FR-TASK | [garden-records.md](garden-records.md) | 9 | FR-TASK-10 |
| FR-TEX | [ui-look.md](ui-look.md) | 5 | FR-TEX-06 |
| FR-TIMELINE | [plants.md](plants.md) | 7 | FR-TIMELINE-08 |
| FR-TOOL-ESC | [editing.md](editing.md) | 1 | FR-TOOL-ESC-02 |
| FR-UI | [ui-look.md](ui-look.md) | 23 | FR-UI-29 |
| FR-UI-ICON | [ui-look.md](ui-look.md) | 2 | FR-UI-ICON-03 |
| FR-UI-PREF | [ui-look.md](ui-look.md) | 1 | FR-UI-PREF-02 |
| FR-UI-SIDEBAR | [ui-look.md](ui-look.md) | 6 | FR-UI-SIDEBAR-07 |
| FR-UI-THEME | [ui-look.md](ui-look.md) | 3 | FR-UI-THEME-04 |
| FR-VIS | [ui-look.md](ui-look.md) | 9 | FR-VIS-10 |
