## Case study: a device cache that cached nothing (#784, fixed 2026-11-09)

**Symptom**: with the sun-shadow overlay on, every repaint of the plan canvas cost 130-160 ms on the family-garden example; pan, wheel zoom and the timeline scrub stuttered at 6-8 fps. A probe that switched things off read 161 ms (default) -> 132 ms (spacing rings off) -> 10 ms (overlay off too).

**Theories entertained (wrong)**:
- "The overlay's `paint()` is the whole cost: cache it and the frame is cheap." Half true. Setting the overlay to `DeviceCoordinateCache` changed nothing at all.
- "The spacing rings are the second-largest cost (about 40 ms)." They cost nothing measurable.
- "An item with `DeviceCoordinateCache` is painted once and blitted afterwards" - what the NFR-PERF-01 work (#409), ADR-057 and three docs say.

**What instrumentation revealed** (a probe timing `viewport().repaint()` in the real app, overlay on and off in alternating rounds):

```
[cache]    QPixmapCache limit 10240 KB
[cache]    fit, rings on: on 146.3 ms off 51.8 ms     <- overlay now DeviceCoordinateCache: no change
[cache512] QPixmapCache limit now 524288 KB
[cache512] item caches needed at fit: 101 items, 17.0 MB
[cache512] fit, rings on: on 11.4 ms off 11.2 ms      <- same code, room in the cache
[cache512] fit, rings off: on 9.4 ms off 8.9 ms       <- and the rings were never the cost
```

**Root cause**: Qt stores every item's device-cache pixmap in the process-wide `QPixmapCache`, and nobody had ever raised its default limit of 10 MB. The plan's visible items need 17 MB (one lawn is 5.2 MB), so each frame evicted what the next frame needed: a "cached" repaint painted the items again. The overlay's own 5 MB picture was evicted by the next item painted after it. NFR-PERF-01 never saw it because its 990-item reference plan is made of small items.

**Fix**: `ui/canvas/item_cache.ensure_item_cache_budget()` (256 MB ceiling, called by `CanvasScene.__init__`), the overlay as `DeviceCoordinateCache`, and a kept picture shown scaled while a zoom is under way (`SunShadowOverlayItem`, `settle()`). Pinned by paint COUNTS (`tests/integration/test_sun_overlay_cache.py`, `TestPanIsCheap`) and by an on/off repaint RATIO on the quiet runner (`tests/perf/test_sun_overlay_repaint.py`: 16.9 before, 1.06 after).

**What it did not fix**: a timeline scrub at fit still costs one rasterisation of the overlay per solve (about 130 ms) - the cache makes a paint rarer, not cheaper.

**Lesson**: a cache mode is a request, not a fact. Count how often `paint()` runs, or time the same frame twice, before believing an item is cached - and when two unrelated things both look expensive (the overlay, the rings), suspect what they share. Two smaller traps on the same hunt: under `QT_QPA_PLATFORM=offscreen` a `set_zoom` without `centerOn` scrolls the items out of view and "no paints" looks like a perfect cache; and a pixmap drawn into an item-space rectangle under the canvas's Y-flip is mirrored - draw device-space pictures with the device transform made the identity.
