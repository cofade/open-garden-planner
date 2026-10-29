## Case study: grouped guild navigation test picked a child instead of the group (F1/F2)

**Symptom.** A grouped-centre diagnostic assertion passed alone and failed in a combined run.
**Wrong theory.** The coordinator had failed to remap the centre to its enclosing group.
**Evidence.** `[GUILD-GROUP] selected` printed a `GroupItem` plus selected `CircleItem` child wrappers; their order varied. `centre.parentItem()` and the diagnostic agreed.
**Fix.** Address the group through the centre's actual parent, never `scene.selectedItems()[0]`. A second idempotence assertion printed `[GUILD-REFRESH] changed keys ['metadata']`: serialization stamps `modified` on every call. Compare content after removing only that volatile timestamp.
**Lesson.** Inspect framework state before changing correct production logic. Keep selection/serialization tests independent of unspecified ordering and wall-clock stamps. All temporary prints were removed.

