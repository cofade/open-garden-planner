## Case study: object frames and device pixels leaked into each other (#840, #841, #843, #844, #853, #867, #872, #874)

**Symptom:** Rings moved snap/alignment anchors; zoom stretched a rotation handle;
rotated beds lost their tags; notes depended on DPI; fitted edges lay under rulers.

**Theories checked:** Changing ring or saved geometry was unnecessary. The two
bounds have different jobs. Keeping an upright tag at a rotated corner cannot
make it contained. An offscreen hinting setting is not a Windows pixel oracle.

**Evidence (Qt 6.12.0, Windows, 2026-11-17):**

```text
[PRECISION] tree snap left: 539.5 -> 181.5 cm with its ring
[PRECISION] zoom 0.5 -> 4: rotation gap 25 -> 200 px
[TEXT-DPI] same point font, device heights: 17.875 / 26.797 / 35.75
[GRID-PRECISION] same scale/origin/area, 30 band moves: builds 1 -> 23
[NATIVE] letter-gap error: unhinted 0.5 / 0.5 px; hinted 2.0 / 2.5 px
```

**Root causes:** Paint bounds were used as geometry; a local offset was not
refreshed after zoom; point fonts resolved against device DPI; tags had only an
AABB room test. The ruler-aware fit also exposed inverse/forward roundoff:
29.9999999999999 versus 30 made a partial repaint request one pixel outside the
kept grid. The scale, origin and paint revision had not changed.

**Fix:** One core frame helper; selection/zoom refresh existing handles; fixed
96 dpi resolution of stored point sizes; outline-contained upright tags and
compact indicators in the shared collision pass. Intersect kept-layer exposure
with the whole picture in device space as well as scene space. Minimap diagnostic
suppression schedules no updates. Text-note exclusions are kept by paint revision.
The balcony note is wrapped clear of furniture in every bundled language, and
sun contours leave note bounds clear.

**Pins:** `tests/integration/test_canvas_editing_precision.py`,
`tests/integration/test_canvas_label_precision.py`,
`tests/integration/test_canvas_native_pixels.py`,
`tests/integration/test_tool_preview_repaint.py`, and
`tests/unit/test_item_geometry.py`.

**Scope boundary:** The native selected partial/full probe currently matches on
master and this branch; #879 remains open. A native harness must explicitly clear
its scenes and detach/delete its closed view before QApplication teardown.

**Lesson:** Derive geometry from geometry and screen distances through the full
transform. A changed fit scale can expose a cache boundary even when the cache's
key is unchanged. Prove a pixel oracle sees its negative control.
