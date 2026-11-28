---
title: "Canvas"
prefixes: ["FR-CANVAS", "FR-GRID", "FR-IMG"]
---

# Canvas

## Metric canvas

- **FR-CANVAS-01**: Canvas uses metric coordinate system (centimeters as base unit)
- **FR-CANVAS-02**: Display can show measurements in cm, m, or mixed (e.g., "2.35 m")
- **FR-CANVAS-03**: Canvas supports zoom from 1:1000 (overview) to 1:1 (detail) scale
- **FR-CANVAS-04**: Pan and zoom via mouse wheel, drag, and keyboard shortcuts — and, since issue #321, **touch**: Qt's own pinch recognizer turns two fingers into a zoom about the gesture centre (panning as they move), both through the same anchored-zoom and pan helpers as the mouse (so the clamping, the 1 px anchoring and the minimap/rulers/zoom label agree). A **single** finger is never claimed by the recognizer, so tap-to-select and one-finger drag stay on Qt's synthesised mouse path and behave exactly as before. A pinch **never drags** the object under the first finger: a move it had begun is put back with no undo step, a half-made shape is discarded (a tool that keeps a multi-press draft, Plant Grid, keeps the draft and undoes only that press; ADR-082), and a selection the press cleared on empty canvas is restored (it may still select the object under that finger, as a tap would); the one stated exception is a resize/rotate/vertex handle being dragged, whose normal release finalizes that edit as one undo step. Touch *drawing* with tools is out of scope. Trackpad pinch arrives as Qt's native zoom gesture and is handled too. The behaviour is the **Preferences → General → Canvas → "Enable touch gestures"** setting (`canvas/touch_gestures_enabled`, default on); off grabs no gesture at all, leaving the canvas as it was before #321.

## Grid

- **FR-GRID-01**: Optional visible grid overlay (toggleable via toolbar button). The grid lies on the ground: it is drawn inside the plan only, over the ground surfaces (lawn, terrace, path, in-ground bed) and under every object that stands on them, so no grid line crosses a plant, a building or a piece of furniture *(issue #793)*. It is a canvas aid and is in no export.
- **FR-GRID-02**: Grid spacing configurable (10cm, 25cm, 50cm, 100cm)
- **FR-GRID-03**: Snap-to-grid toggleable (independent of grid visibility)
- **FR-GRID-04**: Grid renders efficiently at all zoom levels (adaptive detail)
- **FR-GRID-05** *(#847, #878)*: After an edit, the first partial repaint refreshes the kept grid picture; later repaints reuse it. Pans at 125% and 150% display scaling reuse exact pixel phases within a shared 64 MB ceiling. Drawing previews reuse the snap index until plan geometry or visibility changes.

## Background images

- **FR-IMG-01**: Import background images (PNG, JPG, TIFF)
- **FR-IMG-02**: Calibrate image scale by marking a known distance (e.g., "this fence is 5.2m")
- **FR-IMG-03**: Two-point calibration: user clicks two points and enters the real-world distance
- **FR-IMG-04**: Adjust image opacity (0-100%)
- **FR-IMG-05**: Lock/unlock image layer to prevent accidental movement
- **FR-IMG-06**: Image stored as reference in project (path or embedded, user choice)
- **FR-IMG-07**: Multiple background images supported (e.g., different areas of property)
- **FR-IMG-08**: Load satellite imagery directly from Google Maps via an embedded picker dialog: address search (Places Autocomplete), navigate the map, drag a rectangle, fetch via Static Maps API. Available when a key is configured in Preferences (`api_keys/google_maps_key`) or through the `OGP_GOOGLE_MAPS_KEY` environment/`.env` fallback; a non-empty Preferences value takes precedence (ADR-019, Issue #342). When the Static API rejects the satellite request with the Google-canonical EEA 403 (“not available for your account and region”), the picker offers — and always provides via a “Capture view” action — a JS-API view capture: the live map is positioned over the rectangle, the embedded web view is grabbed at the widget level, and the image is scaled/cropped analytically (ADR-019 addendum #346).
- **FR-IMG-09**: Satellite imports land on the canvas at true real-world scale automatically (no manual two-point calibration), with `meters_per_pixel` derived analytically from the Web-Mercator zoom level and latitude. The manual `Calibrate Scale…` context-menu action remains available as an override.
- **FR-IMG-10**: Satellite imports persist in the `.ogp` project file with geo metadata (center, NW/SE bbox corners, zoom, source, timestamp) — older projects without this metadata continue to load unchanged. JS-capture imports additionally persist `source: google_js_view_capture` and an `attribution` line (additive keys, Issue #346).
- **FR-IMG-11**: The JS-API view capture raises the Static-mosaic resolution ceiling for large gardens: for rectangles wider than the map viewport at the best zoom, the picker pans the embedded map across up to a 3×3 grid of viewport positions at one integer zoom, grabs each frame, and stitches them seamlessly at analytic whole-pixel offsets; the result is cropped to the drawn rectangle and carries exactly one attribution strip regardless of grid size. Per-frame rendering failures are retried (2 attempts) and then fail with a clean message — a partially blank import is never accepted (ADR-019 addendum #347).
- **FR-IMG-12** (Issue #659): A background image whose **decoded** size exceeds Qt's process default (256 MB, about 67 megapixels at RGBA8) imports and reloads instead of degrading to a placeholder: the decode budget is raised to 512 MB for that one decode and restored afterwards, so no other decode in the session inherits it. An image above 120 megapixels is refused from its header, before allocation, with a translated message stating its size and the limit. The cap accounts for the item holding the pixmap twice (original plus the flipped copy it paints).
- **FR-IMG-13** (Issue #660): Reading a plan — an Agent API snapshot or an autosave — reuses the embedded base64 background image instead of re-encoding it. The bytes are encoded on first use and invalidated by the pixmap's revision, so an unchanged background costs no main-thread encode per read (measured 1.16-1.21 s at 9000 x 8000 before the cache).
