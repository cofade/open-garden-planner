## Case study: a preset name is not an appearance snapshot (#524–#526, #471)

**Symptom.** Preset undo returned the name NONE but retained gravel's 8 cm stroke;
context-menu undo discarded a custom 12 cm stroke. Properties rebuilt square caps
and bevel joins. Metal and acute paved/stone details exceeded cached paint bounds.

**Wrong theories.** A pen/attribute agreement check alone cannot prove undo restored
the previous appearance. The historical issue's 17 cm bound was not assumed current.
Neither disabling caches nor changing painters addresses the geometric contract.

**Evidence.** In-memory `[LINE-PLAN]` logs with caller stacks observed preset
application through `apply_pfs` during undo and through `_setup_styling` on context
restoration. The changed Properties line was gray 4 cm SquareCap/BevelJoin; context
was gravel 8 cm RoundCap/RoundJoin. Fixed-image uncached pixels exceeded bounds.

**Root cause and fix.** Preset names and reconstructed defaults lost prior values.
Copied LineLook snapshots restore through one panel-independent callback and
adopt_pen. Owner-selected type changes clear presets and use the new defaults.
The canvas and ground baker share one conservative reach. Geometry notification
precedes mutation. Temporary instrumentation is not committed.

**Lesson.** Assert exact before/after appearance, not only internally consistent
attributes. An oracle cropped to the bounds under test cannot detect clipping.
Do not invalidate a cache while measuring its reuse; rotated Qt transforms may
regenerate it. Pins: tests/integration/test_line_appearance_history.py and
tests/integration/test_styled_line_bounds.py; crosscutting section 8.30.

**Review follow-up.** A dynamic cached edit/history/move test exposed a weak pixel
mask: absolute darkness counted the outside-page background, and a threshold
assuming white could not classify the cream page as cleared. Empty-scene contrast
separates the line from both backgrounds and sees faint subpixel rails. Test a
populated cache through edits, undo/redo and movement; assert vacated pixels clear.


