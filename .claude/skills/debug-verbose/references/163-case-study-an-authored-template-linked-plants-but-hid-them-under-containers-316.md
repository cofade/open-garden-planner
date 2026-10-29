## Case study: an authored template linked plants but hid them under containers (#316)

**Symptom.** The first balcony PNG showed soil and no herbs while the file loaded.
**Wrong theory.** A successful serializer/load round trip was sufficient to validate
curated content. No production stacking change was justified by that observation.
**Evidence.** `[F5-Z] CONTAINER layer None z 0.00002384` versus plants on the active
layer UUID at smaller z values. A test then failed because a bed had no child list.
**Root cause.** The authoring script built rectangles without a layer and inserted
plants directly, bypassing the creation command's bidirectional parent relation.
**Fix.** Give rectangles the active layer and create plants through CreateItemsCommand.
Render the saved plan with stable IDs through the production scene renderer. Keep the
same-layer/child-list regression in test_templates.py. Use the already documented
minimal:enable_fonts platform for Windows thumbnail fonts; no engine change.
**Lesson.** Inspect content rendered through the real path. A parent UUID is not the
whole parent contract, and deriving z-order only clamps inside a shared layer.


