## Case study: a selected 16 384-vertex outline re-sampled on every scroll (#594)

**Symptom.** After #551 capped the dense overlay at 128 handles, dragging the scrollbar on a selected 16 384-vertex polygon hitched ~100 ms per step; master did not.
**Wrong theories.** Creating the handle items was the cost (only 128 exist); the selection highlight; the paint bound.
**Evidence.** `_dense_overlay_indices` walks every vertex, maps it through the item's device transform and buckets it into 24-px cells. A forced re-sample measured 98.58 ms; reusing the cached sample measured 0.01 ms. `CanvasView.scrollContentsBy` called `refresh_vertex_edit_overlay` on every step.
**Root cause/fix.** The sample is viewport-derived, and the code treated every pan as a new viewport. `_remember_dense_sample` stores the sampler's actual candidate region — the viewport grown by `DENSE_HANDLE_SPACING_PX` (24 px) — plus the zoom and the item pose; `_dense_sample_covers_view` skips the re-sample while the new viewport is inside it, the zoom is unchanged and the item has not moved. A pan translates the points, so their pairwise spacing is unchanged; a zoom, a pose/geometry change or a pan beyond the region samples again. The first version cached a region twice as large as the one the sampler tested, which left newly visible vertices without handles after a 25-px pan; the reviewer measured 276 such vertices after 300 px.
**Lesson.** A viewport-derived sample has a validity region, not just a validity moment. Cache the region, and pin the skip with a call count on the sampler, not a wall-clock assertion.

