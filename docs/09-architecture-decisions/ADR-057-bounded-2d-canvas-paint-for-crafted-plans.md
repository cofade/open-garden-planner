---
id: ADR-057
title: "Bounded 2D canvas paint for crafted plans"
status: "Accepted."
refs: ["#472"]
legacy_anchor: adr-057-bounded-2d-canvas-paint-for-crafted-plans-472
---

# ADR-057: Bounded 2D canvas paint for crafted plans

**Status:** Accepted.

**Context.** A plan file may hold a polygon with any number of vertices, and the 2D canvas paints it whatever that costs. A reflex-heavy outline (a "comb" whose teeth span its full height) makes one antialiased *fill* quadratic in vertices: measured on a 512x512 painter with the item's own 2.0 solid pen, one such outline costs ~38 ms at 256 vertices, ~322 ms at 1,024, ~1.4 s at 4,096 and ~5.6 s at 16,384 (the bug report measured 10.5 s at 1,024 on its box). Nothing bounded the vertices on load and nothing degraded the paint, so a crafted `.ogp` froze the window and the loader accepted an unbounded item.

Two measurements decided the remedy, and both were needed:

* the cost is a function of **reflex geometry and pen width**, not vertex count alone — a convex 4,096-vertex outline fills in a few milliseconds, and a comb's fill only stops growing quadratically above ~32k vertices because the geometry collapses sub-pixel (it still takes ~10 s at 65,536);
* Qt strokes a **wide solid pen by building a fill**, so "just draw the outline" is only cheap with a **cosmetic** pen: measured, the same 1,024-vertex comb takes 319 ms stroked with the item's 2.0 pen and 4 ms with a cosmetic 1-px pen.

**Decision.** One vertex bound governs full-detail painting; a separate ceiling guards the ingestion seam.

- `MAX_FULL_DETAIL_VERTICES = 256` (`ui/canvas/items/polygon_item.py`). At or below it an unselected polygon paints exactly as before.
- Above it, an **interactive, unselected** paint draws the exact outline with a **cosmetic 1-px pen and no fill** — linear in vertices and independent of the item's own pen width (measured ~4 ms at 1,024, ~20 ms at 4,096, ~69 ms at 16,384).
- The degrade is **interactive-only, and "interactive" is the item's cache mode, not Qt's `widget`.** Qt passes `widget = 0` for every *cached* paint and every unselected canvas item is `DeviceCoordinateCache`, so a `widget is not None` guard (the LOD flat fill's own idiom) is never true on the path that paints the user's canvas — the first shipped version of this fix therefore never degraded anything (measured through a real view: 44.7 ms at 1,024 vertices, 589 ms at 16,384, on every cache regeneration). Every export, report, print and agent render path disables caches first (`ExportService._disable_item_caches`), so those stay exact, while the cached interactive view degrades; a **selected** item is excluded and paints the exact fill, so editing sees the truth.
- `MAX_POLYGON_VERTICES = 16_384` refuses a polygon above it at the load seam (`ProjectManager._deserialize_item_core`), non-fatally: the item is skipped (logged, and counted for the app's existing skipped-item notice) and the rest of the plan loads. At the ceiling the degraded 2D outline is ~69 ms, not minutes, and no legible garden outline comes near it.

**Alternatives rejected.** Filling the polygon's bounding box or convex hull is O(1) but *over*-covers — a comb would paint as a solid block and hide items beneath — and the hull costs an O(n log n) pass; outline-only under-covers, which is the safer error and keeps the exact boundary visible. **Reusing the item's own pen for the outline was the first attempt and is quadratic** (the pen-width measurement above); it does not bound the cost, and the earlier draft's "~4 ms at 1,024" was measured with a hairline pen, not the item's. A reflex-count or convexity test to keep large *convex* shapes at full detail needs an O(n) pass per paint; it was rejected as machinery for a case (more than the bound of vertices that is also convex) the outline covers acceptably. A low load ceiling that refuses every polygon above the full-detail bound was rejected because it would refuse legitimate traced or imported outlines — the paint bound protects the frame, the ceiling only protects the loader from hostile memory.

**Consequences (limitations, stated).** Full detail is a bounded, stated budget, **per item per paint — not a plan-wide one**. Above the bound, *all* polygons — including a large convex one whose fill would be cheap — render as an outline interactively; a future refinement could exempt convex outlines. Full-detail paths that stay open above the bound, each capped only by the load ceiling: at exactly the bound a pathological comb still costs about two frames (~31 ms at 256 vertices); a **selected** over-budget item paints full detail on every interactive frame (5.6 s at 16,384); and every export/report/print/agent render, which disables caches and renders through `QGraphicsScene.render`, keeps the exact fill and can stall at the ceiling. The **minimap** renders through `scene.render` *without* disabling caches, so it degrades like the canvas — desirable for a thumbnail, and the one render path whose full-fidelity convention is deliberately different. The same `widget`-based idiom lived in `should_use_lod_flat_fill` (#409); it was re-checked on report and the LOD flat fill was **removed** rather than repaired — it never ran and bought no measurable time, so `should_use_lod_flat_fill` and `get_lod_fill_color` no longer exist and `is_interactive_paint` now serves the paint bound above alone (see the ADR-057 addendum, #503). The two constants are plain module values so a future measurement can retune them in one place.

**Evidence.** The committed `tests/integration/test_polygon_paint_bound.py` pins that an over-budget polygon paints an outline (not a fill) on screen, that the degraded paint is many times cheaper than full detail **with the item's own wide pen**, that a polygon at the bound, an offscreen render and a selected item paint the exact fill, and that a hostile polygon is refused at the seam without dropping the rest of a plan. The cost table above is reproducible with the shapes in that test file.

## ADR-057 addendum — a dense vertex-edit sample is reused until the viewport leaves its region (#594, 2026-10-25)

**Context.** §8.9.11's #551 sample caps the number of overlay handles, not the CPU that
chooses them. `_dense_overlay_indices` maps every vertex through the item's device
transform to decide which 128 to show, and `CanvasView.scrollContentsBy` asked for a
fresh sample on every scrollbar step. The senior review of PR #585 measured a selected
16 384-vertex polygon (the loader's cap) at ~100 ms per scrollbar step and ~176 ms per
zoom step; master did no per-scroll re-sampling, so the scroll cost was new.

**Decision.** The sample is still viewport-derived, but it is **cached with the scene
region it actually covered**. `_remember_dense_sample` records the sampler's own
candidate region — the viewport grown by `DENSE_HANDLE_SPACING_PX` (24 viewport
pixels), the same rect `_dense_overlay_indices` tests candidates in — together with
the zoom and the item's pose. `_dense_sample_covers_view` lets
`refresh_vertex_edit_overlay` return immediately while the current viewport is
inside that region, the zoom is unchanged and the item has not moved. A pan
translates the points, which does not change their pairwise distances, so the
chosen indices keep their 24-px spacing; every vertex now visible was a candidate
when the sample was taken. A zoom change, a pose/geometry change, or a pan beyond
the region samples again. The cache lives on the item (polygon and polyline
mixins) and is cleared when the outline is no longer dense, on a geometry update,
and on leaving edit mode.

**Measurements (dev box, 2026-10-25).** 16 384-vertex polygon at 1100×650, zoom 1.0:
**98.58 ms** per forced re-sample, **0.01 ms** with the cache. The pin is a call count on
`_dense_overlay_indices` after ten 2-px scrollbar steps (zero), a 100-px pan beyond the
24-px candidate margin (>0, and the new viewport gets handles), a far pan (>0) and a
zoom (>0), for both a polygon and a polyline; not a timer.

**Pins.** `tests/integration/test_dense_polygon_edit.py::test_a_pan_inside_the_sampled_region_does_not_resample`.
PF-CAN-26 records the rule. The saved geometry is unchanged; entering, zooming and leaving
edit mode still compare the polygon before and after.
