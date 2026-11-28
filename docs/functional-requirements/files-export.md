---
title: "Files, export and examples"
prefixes: ["FR-FILE", "FR-EXP", "FR-IMP", "FR-SAFETY", "FR-EXAMPLE"]
---

# Files, export and examples

## Project files

- **FR-FILE-01**: Native project format: `.ogp` (Open Garden Planner) - JSON-based
- **FR-FILE-02**: Project file contains all object data, metadata, layer configuration
- **FR-FILE-03**: Background images: option to embed (base64) or reference (path)
- **FR-FILE-04**: Project files are human-readable and version-control friendly
- **FR-FILE-05**: Save/Save As/Open dialogs with recent files list
- **FR-FILE-06**: Auto-save at a configurable interval keeps the complete plan through Save's canonical serializer, including pending property edits, dragged journal pins and every plan-level store (#797). It writes `~autosave_<name>__<document_uuid>.ogp` beside a saved plan or `~autosave_untitled__<document_uuid>.ogp` in the system temporary directory, reusing that document's path on timer ticks and preserving other documents' snapshots, without marking the document clean or changing its filename/recent files. Recovery loads that complete document and leaves it untitled and dirty.
- **FR-FILE-07**: Startup offers a newer autosave for an untitled plan and for the ten recent saved plans; opening a saved original through the GUI also offers its adjacent recovery (#797). Accepted recovery stays untitled and dirty, with its source retained until save/discard. No preserves the snapshot; Discard removes only that candidate. An accepted or failed recovery must not silently fall through to loading the old original. Cleanup only removes snapshots created or adopted by the current document, including the old untitled snapshot after Save As.
- **FR-FILE-08** (issue #199): Save/Open/export dialogs default to a safe, writable location — the open project's folder when one exists, otherwise `<Documents>/Open Garden Planner` (`app/paths.get_projects_dir()`). They must **never** default to the process working directory, which for a packaged build is the install folder; user data stored there is destroyed on upgrade/uninstall. Complemented installer-side by user-data preservation (see deployment view §7.2): the uninstaller backs up any `$INSTDIR\*.ogp` to `Documents\Open Garden Planner\Recovered Plans` before removing the install directory.

## Export

- **FR-EXP-01**: Export to PNG (configurable DPI: 72, 150, 300). Object labels are sized for the output; a text note keeps the size it has on the plan at every DPI and paper size (#789). A bed's succession badge has the object labels' size in every exported picture (#836).
- **FR-EXP-02**: Export to SVG (vector, scalable). The file states the requested physical size (`width`/`height` in mm) and is the picture the PNG export paints: textures, clipped shapes (roofs, glasshouses, shadows) and pattern angles included. Text stays editable text and names a generic fallback font family (#787, ADR-076). A raster picture drawn as a pixmap — a plant or furniture sprite, a shadow layer, a scene image — is written no finer than one pixel per 300-dpi unit, the resolution the drawing is stated at, and never enlarged: the canvas's power-of-two raster level does not reach those pictures (#850). Repeating fill-pattern brush tiles keep their periodic `fill_patterns.tile_level` tile (up to 512 × 512 px at `DETAIL_LEVEL`) rather than being non-periodically resampled.
- **FR-EXP-03**: Print support with scaling and page layout (Phase 6). At a fixed scale each sheet shows its tile of the plan and nothing else: nothing is printed on the margin or over the footer (#788). Object labels are readable at the printer's resolution; a text note keeps its plan size (#789). The page starts as A4 landscape with a 10 mm margin on every side; the Print Options dialog states the number of sheets the printout has, with or without the legend; a fitted printout states the scale it was fitted at (#836). The **Grid** checkbox paints the canvas grid at the canvas's own spacing over the plan, at a stated 0.15 mm line width (#868). A fixed-scale print's pages run **top row first**; a plan height that is not a whole number of tiles leaves the plan's short **bottom** row on the **last page**, its strip at the top of that sheet with blank paper below it (#871).
- **FR-EXP-04**: Export selected objects only or entire canvas
- **FR-EXP-05**: Export includes visible layers only (or all, user choice)
- **FR-EXP-06**: Plant list export: CSV with all plant metadata
- **FR-EXP-07**: Export to DXF (AutoCAD R2010+); shapes map to LWPOLYLINE/CIRCLE/ELLIPSE; layers preserved; 1 unit = 1 cm
- **FR-EXP-08**: Multi-page PDF report with configurable pages (cover, overview, bed details, plant list, legend); paper size A4/A3/Letter/Legal, landscape/portrait. Plan pictures are 300 dpi. The plant list runs over as many pages as it needs and names every plant (its own name, else its species). **Its Type column is the species' cycle** (Annual / Biennial / Perennial, in the UI language), falling back to the object type only when the plant has no species record — a species whose cycle is unknown shows "—" (#869). A bed-detail page shows the bed in context with a minimum extent of 150 cm; small beds next to each other share a page. The legend lists the object types and plants on the plan with a sample of each; **a plant's sample includes the full sprite** — its foliage is not clipped — and the swatch is 9 mm (#864). The cover carries the plan's title — for a plan opened from an example, the example's name (#788, ADR-076). The Harvest Summary and the Garden Notes also run over as many pages as they need; every page is counted by the progress and titled with its number; a plan that was never saved is named in the UI language (#836). **Harvest units are translated in the summary** while the stored unit stays a stable key (#899); the report's numbers (plant positions, money, totals) use the UI language's decimal mark (#860).

## Import

- **FR-IMP-01**: Import `.ogp` project files
- **FR-IMP-02**: Import SVG as editable objects (basic support, future)
- **FR-IMP-03**: Import plant list from CSV (batch add plants, future)
- **FR-IMP-04**: Import DXF (LINE, LWPOLYLINE, CIRCLE, ARC, ELLIPSE, SPLINE); configurable scale factor; layer selection; single undo action

## Data and download safety

- **FR-SAFETY-01**: Opening non-finite/overflowing numeric plan data refuses before
  replacing the active document; failed saves do not truncate existing plan/recovery files.
- **FR-SAFETY-02**: In-app installation requires exact release assets, permitted HTTPS
  origins/redirects, matching byte count and SHA-256; cancellation/refusal launches nothing.
- **FR-SAFETY-03**: Linux user settings have owner-only file access, preserve existing
  keys/values and fail startup clearly when protection cannot be established.
- **FR-SAFETY-04**: Thumbnail/Static Maps responses have byte/pixel limits and full
  decoding checks; failed input does not publish partial caches or replace the background.

## Examples and templates

- **FR-EXAMPLE-01**: Welcome and File offer thirteen offline examples (#940) in a fixed
  order, the same in every language, with localized names/descriptions, PNG previews and
  visible license attribution. User templates in the app-data templates directory appear
  after them.
- **FR-EXAMPLE-02**: Opening an example or any `.ogp` through New from template
  creates an untitled, dirty copy through the normal document loader. Saving asks
  for a destination; bundled bytes and modification times stay unchanged.
  Known bundled examples retain their public demonstration location, fictional
  soil tests and fictional harvest history; external templates use the portable subset. English, German and
  Spanish examples include localized object names, notes, hints and tour names. One gallery
  thumbnail serves every language: it shows the plan without its hint text (#940).
- **FR-EXAMPLE-03**: Save as template explains and removes site, history, task,
  inventory, preference and image data plus absolute paths. Geometry, species,
  layers, guilds, constraints and succession dates stay portable.
  Every current ProjectData field has an explicit keep/strip classification.
- **FR-EXAMPLE-04**: Template export leaves the live project identity, history and
  dirty state intact; it refuses to overwrite the live project or bundled examples.
- **FR-EXAMPLE-05**: `garden://examples` lists bundled names, tags, descriptions,
  paths and licenses read-only. Opening remains a GUI action. No online gallery.
- **FR-EXAMPLE-06**: Learning layouts use plausible planting densities and ages,
  group guild plants in cultivated soil, keep raised-bed plants inside the drawn
  soil, and explain a dated sun/soil/guild workflow with editable plan annotations.
- **FR-EXAMPLE-07** (#390): The examples include **Family garden**, a 24 × 16 m whole garden made to
  explore in 3D, the plan of the project's own renders. Its names are localized; its botany is not.
- **FR-EXAMPLE-08** (#795, #940): An example opens on its reference date with the sun above
  the horizon, however late the wall clock is, and never with the night overlay on the plan.
  Each example has its own date and its own light: midday, a morning, a late afternoon or
  golden hour (for example Family garden on 21 June 2026 at midday, the spring garden on
  18 April 2026, the Mediterranean courtyard on the evening of 21 June 2026). The Plan & Sun
  strip shows that moment. Opening or creating another
  document puts the clock back to the reading the user had before, and so does saving the
  copy (Save or Save As): it is the user's plan from then on, the status bar says that it
  now follows their own date and time, and a date or time they set afterwards stays when
  another document opens. The moment itself is never saved; a copy saved from an example
  opens like any plan of the user's. A plant added before the copy is saved is planted on
  the example's date, one added after it on the user's date.
- **FR-EXAMPLE-09** (#795, #940): An example with edible plants has a small harvest history
  that is marked as fictional, so the Harvest tab, a plant's harvest log and the report's
  harvest page show content. An ornamental example (the modern and the Japanese garden) has
  none. The Seed Inventory is the user's own and stays as it is; when it is empty the
  tab says what it is for and how to add a packet.
- **FR-EXAMPLE-10** (#795): For every plan, not only examples: Plant Details show a
  species without a photo as the plan draws it, and the Diagnostics panel lists the
  plants whose sun exposure is not evaluated for one reason as one row that counts and
  selects them.
- **FR-EXAMPLE-11** (#865): **File > Open** of a shipped example by its path is the
  same untitled copy the gallery opens: no Save or autosave is attached to the bundled
  file, it does not enter Recent, the report cover carries the sidecar's name, and the
  first save is a Save As. The bundled bytes are never written.
- **FR-EXAMPLE-12** (#940): Every example but Family garden carries one hint text that says
  what the plan shows and what to try. The hint lies alone on the top layer **Hints**:
  hiding that layer in the Layers panel leaves the plan without any text, ready for a
  picture.
- **FR-EXAMPLE-13** (#940): Every example stores a camera tour **Garden orbit** (one eased
  turn around the whole plan, starting with the showcase sun behind the camera). Three
  examples store a second tour: the modern garden's runs from evening into night and the
  garden lights come on, the terraced-house garden's holds the camera while a day's shadows
  pass, the spring garden's holds it while the year 2026 passes. A tour's time of day is
  read on the computer's clock. An example's 3D view opens on the side its orbit starts
  from, at the distance that fits the view; **Reset 3D View** goes to the default side.
- **FR-EXAMPLE-14** (#940): The examples lie in eleven German and Austrian places and in
  Valencia, and show, between them: a rotated north, guide lines and distance constraints, a
  succession plan, soil samples, three guilds, container planting, a flower meadow, garden
  lights, all four roof styles and a year time-lapse.

ADR-066, `tests/example_specs.py`, `tests/integration/test_example_plans.py`,
`tests/integration/test_templates_gallery.py` and
`tests/integration/test_example_showcase.py` own the behavior.
