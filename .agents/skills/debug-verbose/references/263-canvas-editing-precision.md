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

### Review-driven regressions

The first independent review reproduced four defects: inline document edits did
not move the retained annotation revision; an 80-character crop name reduced the
compact marker below one pixel high; a handle kept its drag-only visibility after
release; and rebuilding selected decorations per tree made 60 ring paints cost
116 ms versus 14 ms without clipping. Each received a failing regression before
its fix. Document `contentsChanged` now invalidates the annotation room, compact
markers have a fixed square aspect independent of text, release refreshes handle
visibility, and one retained device-space exclusion path serves every ring.
`test_selected_ring_paints_prepare_decoration_exclusions_once` counts one selected
subtree traversal for two paints of 30 selected trees. A badge placement carries
its compact/full variant explicitly instead of inferring it from transform scale.


### Second review: retained paint needs geometry and content ownership

Entering vertex mode left the new exclusion cache unchanged while a fresh path
included another 314 by 121 px of annotation room. `EditDecorationMixin` now
invalidates at scene/parent/visibility/position/transform mutations for handles
and annotations; measured-text setters also invalidate. This covers mode changes
and dense overlay resampling without claiming that a plan edit occurred.

A native same-size replacement found another omission: rotated tag `AAAA` to
`BBBB` left 814 stale channel values, and edge-clamped text/colour changes left
1333 / 480. Repeated full paints differed by zero. Retained foreground entries
now keep immutable paint signatures as well as boxes; text, font, ink/halo and
badge variant changes damage the actual placement even when its size is equal.
All three native partial/full controls now match exactly. Pins are
`test_vertex_mode_and_decoration_mutations_invalidate_the_retained_path` and
`test_same_size_content_changes_repaint_relocated_foreground` in the package's
integration files.

### Third review: selection changes can outlive cached plant paint

A warmed, unselected tree retained its old warning arc when a rectangle gained
handles. A viewport repaint alone left 528 stale RGBA channel values. Updating
the tree cleared the difference. Warning arcs now use live paint while they are
shown. The existing plant raster cache still supplies the sprite. The viewport
regression warms the tree before selecting the neighbouring rectangle.

The collision pass treated occupied rectangles as label candidates. An overlap
could therefore discard part of a still-painted succession tag's reserved room.
The index now admits every occupied rectangle before considering labels. The
regression places a name in the part of a tag extending past a view blocker.
Measured angles use the same dimension placement path as lengths and radii.
