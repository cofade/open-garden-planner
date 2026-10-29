## Case study: timeline state missed existing consumers and command paths (#315)

**Symptoms:** hidden-layer discovery changed a saved layer without undo; planting
age stayed stale on undo/rejection; MCP companions and soil tasks still warned about
removed plants; New retained the old hidden count. **Wrong theories:** a correct
canvas filter did not imply that domain readers or document reset followed it.
**Evidence:** independent tagged probes recorded `[F4-REVEAL] before False 0 0`
and `after True 0 0 True` (visibility, undo depth, stack signal count, selected),
and 2024 planting paired with the 2025 age after undo. Real MCP returned the absent
potato as an antagonist; a removed child produced a soil-mismatch task. New showed
one hidden plant after clearing all objects. **Root causes:** direct layer setter,
fast panel return, complete-population readers, and no post-clear timeline signal.
**Fixes:** canonical layer command, persisted-date age refresh, visible automatic
companions, reference-date soil-task presence, and post-clear notification. Each
workflow is pinned in tests/integration/test_plan_timeline.py; temporary logs removed.
**Lesson:** audit consumers and the completed document transition, not only the
filtering helper. Fresh creation must also stamp the active plan date, otherwise a
new guild disappears while planning the past (the full-suite F3 workflow exposed it).

