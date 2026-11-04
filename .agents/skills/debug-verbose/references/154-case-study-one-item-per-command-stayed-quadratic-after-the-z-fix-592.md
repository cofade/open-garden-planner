## Case study: one item per command stayed quadratic after the z fix (#592)

**Symptom.** 1 000 one-item `CreateItemCommand`s took 3.18 s even after #450 made the z derivation one-per-layer; 2 000 took 12.1 s. A direct `addItem` loop was linear.
**Wrong theories.** The z derivation was still per add; the command manager's signal fan-out was slow; item construction was the cost.
**Evidence.** cProfile of 600 commands: `CanvasScene.update_dimension_lines` 1.84 s (1 200 calls, each looping `self.items()` and calling `refresh_lock_badge` → `_is_item_fixed`, 360 600 badge refreshes) and `_restack_ground_changes` 1.03 s (600 × O(items)). A neutral `CreateItemCommand` cannot change any item's type, height or group, and no item had a FIXED constraint.
**Root cause/fix.** Two scene-wide listeners ran on every `stack_changed` regardless of what changed. `ConstraintGraph.fixed_item_ids()` bounds the badge refresh to fixed items plus badges already shown; `Command.changes_ground_band` (default true) lets the neutral commands skip the classification scan. 600 adds: 0.31 s → 0.11 s; the pin counts zero classifications and zero badge refreshes.
**Lesson.** A command-boundary listener must be scoped to what the command can change. Measure call counts per command, not only total time, and keep the default safe so a future command cannot silently opt out.

