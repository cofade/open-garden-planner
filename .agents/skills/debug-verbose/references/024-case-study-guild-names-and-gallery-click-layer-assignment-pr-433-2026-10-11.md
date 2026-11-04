## Case study: guild names and gallery-click layer assignment (PR #433, 2026-10-11)

**Symptom.** A German guild picker showed Apple Tree/Runner Bean/Borage/Strawberry. With auto-assignment enabled, a gallery-selected blueberry drawn on the canvas still used the active layer.
**Wrong theories.** No theory adopted before tracing; a failed checkbox or missing shrub trait was ruled out by the runtime values.
**Evidence.** `[F1] auto=True species=shrub chosen=<active-id> active=<active-id>`; `traceback.format_stack()` identified `CircleTool._finalize_circle -> CanvasView.add_item -> CreateItemCommand.execute`. `[F2] centre=Apple Tree members=['Runner Bean', 'Borage', 'Strawberry']` reproduced the German widget contents.
**Root cause.** The existing drop test bypassed gallery-click circle creation, which constructed its own plant with the active layer. Guild controls directly displayed catalog common_name values without translation.
**Fix.** Reuse `build_plant` for circle-based plant placement; translate guild catalog labels at display time in the existing GalleryData context and register all missing bundled common names. Preserve explicit user names and canonical saved species identity. Remove all probe prints before committing.
**Lesson.** Test each actual creation surface, and assert displayed translated data as well as static labels. A green drop workflow and a complete translation table cannot establish click-placement or data-label behavior.

**Core principle**: stop theorising, start observing. The first step for any non-trivial bug is to instrument the code so the actual runtime sequence is printed to stdout, then reproduce with manual testing and read what happened. Fix from evidence, not assumptions.

---

