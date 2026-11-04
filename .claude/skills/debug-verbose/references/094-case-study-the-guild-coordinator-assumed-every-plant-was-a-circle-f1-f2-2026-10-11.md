## Case study: the guild coordinator assumed every plant was a circle (F1/F2, 2026-10-11)

**Symptom.** The complete suite reported Qt event-loop errors in existing agent task/soil workflows even though the guild-specific tests passed.
**Wrong theories.** None adopted; the captured exception identified the accessed property before any lifecycle theory was pursued.
**Evidence.** The traceback ended at `GuildCoordinator.refresh`, reading `item.radius`: `AttributeError: 'RectangleItem' object has no attribute 'radius'`. A focused regression printed `[GUILD-GEOMETRY] plant RectangleItem has_radius False` and failed both directly and at Qt teardown before the fix.
**Root cause.** The plant ObjectType predicate is semantic; saved/imported or directly constructed plant records need not use CircleItem. Badge-signature calculation unnecessarily inspected geometry even for unassigned plants.
**Fix.** Skip badge geometry for plants with neither a missing-role status nor an existing badge. For a badge that needs updating, use the item's rectangle or bounding rectangle, retaining the circle radius where provided. The regression also pins a rectangular centre's badge and unchanged serialized geometry.
**Lesson.** A semantic type predicate does not prove a concrete graphics-item class. Run the complete suite to exercise representations absent from the new subsystem fixtures. The temporary print was removed.

**Follow-up: imported polygon centres.** Review then exercised the real save/load/picker path, not only badge refresh. A temporary regression printed `[GUILD-CENTRE] loaded_type PolygonItem eligible_index 1`; Insert refused with `PolygonItem object has no attribute rect`. An initial probe omitted a layer and correctly found no eligible centre; the decisive probe persisted a valid visible/unlocked layer. `guild_plant_bounds()` now supplies base-shape bounds to existing-centre placement, whole-layout preflight, preview and badges. Polygon/path bounds exclude painted shadows and cosmetic children. Round-trip insertion and exact undo restoration are pinned at 0?, 45? and 215?, including the centre-relative mature-spacing layout. All probe prints were removed.

