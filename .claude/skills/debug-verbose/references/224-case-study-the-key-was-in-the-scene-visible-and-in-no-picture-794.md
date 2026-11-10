## Case study: the key was in the scene, visible, and in no picture — an item that ignores transformations is found by its rectangle without the painter's flip (#794, fixed 2026-11-10)

**Symptom**: the key of the hours-of-sun map is a scene item at the plan's south-west corner that the export seam shows for the render (`SunMapLegendItem`). Three new tests failed in the same way: the PNG of the plan with the key in the scene was pixel for pixel the PNG with the key taken out. No error, no warning. The test that only asks the seam (`item.isVisible()` between hide and restore) passed.

**Theories on the table (wrong)**:
- *"The seam shows it too late, or the text retargeting hides it again."* Ruled out by the passing seam test: the item was visible for the whole render.
- *"Something is painted over it."* The item's z was 20,000, above every item, and the scene's foreground pass paints labels only.
- *"`paint()` is called and draws outside the picture."* It was the other way round, and only counting told: `paint()` was never called.

**What instrumentation revealed** (a probe with the key's own class and a twin whose `boundingRect()` is the painted rectangle alone, rendered through `render_scene_region`, the canvas's y-flip included):

```
[CULL] rect of the key only     : QRectF(8.8, -36.41, 452.65, 27.61)   sceneBoundingRect QRectF(8.8, -36.41, 452.65, 27.61)
[CULL]   in scene.items(plan)   : False   dark pixels in the picture: 0
[CULL] rect and its mirror image: QRectF(8.8, -36.41, 452.65, 72.82)
[CULL]   in scene.items(plan)   : True    dark pixels in the picture: 3236
```

**Root cause**: the canvas is y-up, so every picture is rendered through a painter that flips y. The key is drawn up and right of its anchor: `QRectF(margin, -margin - height, width, height)` in its own pixels, which on the flipped device is inside the plan. But `QGraphicsScene.render` first collects the items to draw with `items(sourceRect)`, and for an item with `ItemIgnoresTransformations` that lookup takes the item's rectangle at its position with NO transform at all — neither the painter's flip nor its scale. There, negative y is south of the plan: outside the source rectangle. The item is never handed to the painter. An object label never showed this, because it is centred on its anchor and so straddles it in either reading.

**Fix** (`ui/canvas/sun_legend.py`): `boundingRect()` is the key's rectangle united with its mirror image below the anchor, so the lookup finds the item whichever way y runs; `paint()` and the label pass's blocker use the key's own rectangle (`_key_rect`).

**Lesson**: an item that ignores transformations lives in two frames — its place in the plan, its extent in pixels — and Qt's item lookup mixes them without the painter's transform. If its extent lies on one side of its anchor, check that `scene.items(source_rect)` contains it before believing a blank picture is a painting problem. And count the paints first: "never painted" and "painted in the wrong place" need different fixes, and one line of evidence separates them.
