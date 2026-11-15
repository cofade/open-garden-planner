## Case study: unmeasured sun diagnostics block selection (#927)

**Symptom:** Owner acceptance of PR #926 found the supplied four-object demo
almost unusable, including when selecting an ordinary tree or line. The plan
also contained an intentionally hostile 16,000-point zigzag.

**Wrong theories:** Canvas raster caching and hit testing did not explain the
ordinary selection delay: bounding-rect queries stayed below 16 ms, and an
unselected zoom repaint cost 51–57 ms. A full selected paint was expensive too,
but it could not explain selecting a different object.

**Key evidence:** An isolated real-window probe copied only the owner's display
settings into its own store and wrapped geometry, paints and exposure refreshes
with tagged timers. cProfile followed the delayed callback into the footprint
offset. The owner's app log had no exception explaining these stalls.

```text
[LAG-EXPOSURE] exit took=2.504s
[LAG] select-300-point wide line=2.578s
[LAG-EXPOSURE] exit took=2.602s
[LAG] select-Select me, zoom 200%, pan to bottom=2.671s
[LAG] paint points=16000 took=5.427s
[LAG] select-16000=8.447s
```

The ordinary selections each included a 100 ms event-loop wait. Across four
refreshes `polyline_footprint` cost 10.318 s. No result or requested exposure
snapshot existed, and the plan had no location.

**Root cause:** `SunExposureCoordinator._refresh` collected every caster before
asking whether a measurement existed to compare against. Selection and generic
scene repaint signals thus offset the hostile fence on the UI thread only to
discard the snapshot. The stated 60 ms was a debounce delay, not a cost bound.

**Fix and lesson:** Ask for the measured/requested snapshot first. Collect and
compare geometry only when it exists; unavailable evaluations, location hints
and canopy navigation still update. Keep the canonical collector and stale
measurement checks. The same unmeasured refresh fell below 1 ms. Both regression
parameters (with and without a location) were observed failing with two needless
collections before the guard. Ordinary acceptance must use a separate plan from
the hostile stress case: selected painting alone still costs about 5 seconds
because the selected/export contract preserves the stored wide stroke.

Pinned by
`tests/integration/test_sun_mismatch.py::test_unmeasured_selection_and_preview_do_not_collect_shadow_geometry`,
with the existing measured, invalidation, raised-soil and document-lifecycle
workflows as controls. See §8.27.
