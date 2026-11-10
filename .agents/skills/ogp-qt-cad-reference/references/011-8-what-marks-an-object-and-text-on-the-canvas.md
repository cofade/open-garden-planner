## 8. What marks an object, and text on the canvas (#786, #790, #793)

Three rules, each with the mistake behind it. Full text: `docs/08-crosscutting-concepts/README.md` §8.9.15 to §8.9.17.

**1. `boundingRect()` is the repaint region, never the object.** It holds the outline plus the drop shadow, the pen, a plant sprite's leaf overflow, a companion ring, a warning badge and the spacing ring. Whatever marks the object reads `selection_frame_rect(item)` in `src/open_garden_planner/ui/canvas/items/handle_geometry.py`: `rect()` for a circle, rectangle or ellipse, the vertex hull for a polygon. Resize handles, the rotation handle and the label anchor use it. The mistake: a magnolia drawn 2.20 m wide had its handles on an 8.64 m box while its spacing ring was on show. Still open: `core/snapping.py` and `core/alignment.py` read `sceneBoundingRect()`, so a decoration moves a plant's snap and align anchors.

**2. An `ItemIgnoresTransformations` item has its position in plan units and its size in pixels.** An offset of half its size written into `setPos` is right at one zoom only. Centre or stack such an item in its own pixel frame: `HaloTextItem(centered=True)` and `stack_under` in `src/open_garden_planner/ui/canvas/items/halo_text.py`, `AnnotationLabel.set_screen_offset`, or the item's own transform (the inline name editor). Two labels anchored at two plan points overlap as soon as the points are closer on screen than the text is wide; hang them on one anchor.

**3. Text on the canvas carries its own surround.** Use `paint_halo_text`, `HaloTextItem` or `PlanLabelItem`; never `drawText` with a wide pen (it outlines nothing) and never a bare `QGraphicsSimpleTextItem`. The colours come from `src/open_garden_planner/core/legibility.py`: `MIN_TEXT_CONTRAST` 4.5 is what a label shows as painted, `INK_CONTRAST_TARGET` 7.0 is what the colour pair is given. Measure a label's contrast on pixels (`tests/integration/test_canvas_legibility.py` has the helper); do not judge it by eye.

**Object labels are painted by the scene, after the items.** `PlanLabelItem.paint` does nothing in a `CanvasScene`; `CanvasScene.drawForeground` calls `src/open_garden_planner/ui/canvas/plan_labels.py`. The view and `scene.render()` both run it. `src/open_garden_planner/core/label_layout.py` leaves out the labels that have no room; the layout always covers the whole scene, never a repainted region. A label is drawn from a kept picture on screen and as vectors everywhere else.

**A diagnostic decoration is no part of a picture of the plan.** One seam: `ExportService._hide_overlay_items` in `src/open_garden_planner/services/export_service.py`. A badge item gets its own type and joins the tuple there. A decoration painted by a garden item asks `_diagnostics_painted()` first and is listed in `has_diagnostic_decoration()`.

**The canvas grid is clipped, not reordered.** `CanvasView._grid_region` cuts every drawn object that is not a ground surface out of the region the grid lines are clipped to. A view-level pass is in no export.

**Fonts.** A `TextItem` or a callout is scaled by the view, so its font is unhinted (`PreferNoHinting`); an exact point size and the document's design metrics were measured to add nothing. The offscreen platform does not hint: a pixel test cannot show a hinting defect there (debug-verbose case study, #793).
