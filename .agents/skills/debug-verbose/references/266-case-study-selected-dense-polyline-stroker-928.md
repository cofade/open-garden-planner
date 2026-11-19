## Case study: selected dense polyline blocked for 5–10 s in QPainterPathStroker (#928) (2026-11-17)

**Symptom:** Selecting a 16,000-vertex polyline tightly alternating between `y=100` and `y=400` over `x=0..300 cm` stalled canvas repaints for seconds (`10,838.6 ms` with shadows on: `5,381.0 ms` shadow + `5,457.6 ms` stroke on Windows/Qt 6.12), even though `#848` had already capped unselected polylines.

**Theories entertained (wrong):**
- Assuming `WalkBudget` (`CANVAS_PATH_ELEMENTS = 1500`, `CANVAS_PATH_STEPS = 2500`) or viewport clipping bounded selected polyline painting. (All 16,000 vertices fell inside the 300 cm visible extent, so clipping dropped nothing, and `PathStylePaint` / `_paint_shadow` / `super().paint` still handed the full 16,000-vertex `QPainterPath` to Qt's non-cosmetic stroker.)
- Replacing selected strokes with a 1-px cosmetic pen (rejected: violates `#848`'s contract that selection and exports preserve the stored line width and style).

**Key evidence:** Timing each stage of `PolylineItem.paint` on the selected 16,000-point `NONE` polyline showed two separate ~5.4 s stalls in Qt's `QPainterPathStroker`: `_paint_shadow` (wide round-cap non-cosmetic shadow pen) and the base/style stroke, plus non-cosmetic selection highlighting.

**Root cause:** `QPainterPathStroker` builds segment joins and self-intersection winding edges across all 16,000 tightly packed vertices inside one `strokePath`/`drawPath` call whenever a non-cosmetic pen strokes the un-decimated `self.path()`, and `PolylineItem` bypassed the dense fast path whenever `isSelected()` was True without caching the selected body raster.

**Fix (`src/open_garden_planner/ui/canvas/items/path_style_paint.py`, `polyline_item.py`):**
- Added `bounded_stroke_points()` (O(N) envelope-preserving bucket decimation capping paths `> 256` vertices to `<= 50` envelope points) for `_paint_shadow`, `_paint_roof_ridge`, `shape()`, and `PathStylePaint` stroke/offset helpers while leaving stored `self._points` untouched.
- Made `_paint_selection` pen cosmetic (`setCosmetic(True)`), painted selected dense bodies with stored width/style under `WalkBudget`, and cached the selected dense body in a zoom-keyed `QPixmap` (`61.1 ms` cold / `2.17 ms` warm for `NONE`, `1.65–2.26 ms` warm across fence/path styles).

**Lesson:** Bounding `WalkBudget` element counts does nothing if the underlying base/shadow/rail `strokePath` still passes 16,000 tightly packed vertices into Qt's non-cosmetic `QPainterPathStroker`. Decimate the stroked path envelope cleanly while keeping `self._points` intact for geometry/serialization, and cache the selected body per zoom. Pinned by `tests/integration/test_polyline_style_paint.py::test_selected_dense_polyline_bounds_shadow_stroke_and_selection` and `test_dense_polyline_exports_preserve_width_and_bound_paths`.
