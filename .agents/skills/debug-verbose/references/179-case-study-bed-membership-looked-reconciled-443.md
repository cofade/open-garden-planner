# Case study: bed membership looked reconciled (#443)

**Symptom.** The Properties panel, the soil-mismatch/companion logic and the
diagnostics followed a plant's `parent_bed_id` to a bed the plant no longer
stood in — or missed a bed it did stand in. Reproductions: resize a raised bed
away from its perennial (still linked); draw a bed around a standing plant (no
link, plant not lifted); move a plant in or out with the arrow keys (link never
changes); array-copy a linked plant (every copy carries the source's link while
the bed's `child_item_ids` holds none of them); move a bed by a typed
coordinate or align (the plants stay behind).

**Wrong theories.**

- *One of the three evaluators is wrong.* Reading each one: all called
  `find_smallest_bed_containing` with the same point. They agreed with each
  other and disagreed with the edit paths that never called them.
- *The badge margin is the bug.* It was a symptom: the link decisions asked the
  centre of `boundingRect()` (which the antagonist badge moves) while the LIFT
  asked the stable centre. Within 2.55 cm of an edge a plant could be linked
  but not lifted, or lifted but not linked. Fixing the margin alone would have
  left the stale links.
- *The array copies are a serialisation bug.* They are a copy-semantics bug:
  `_strip_item_ids` dropped `item_id` only, so `parent_bed_id` restored the
  source's link, and the array commands only added the items.

**Evidence.** A matrix of every `parent_bed_id` writer and every
`CommandManager.register_applied`/`execute` call site, against the pinned
`test_scene3d_base_stacking.py` reproductions (a)–(k). The tests already stated
the expected *wrong* values ("the link survives: bookkeeping"), which made the
gap between the rule and the paths visible instead of hidden.

**Root cause.** Membership was reconciled at three GUI seams, not by the
commands that mutate geometry; a fourth evaluator was duplicated in the agent.
A copy was not treated as a new item. Two points answered one question.

**Fix (one rule, applied by the commands).** A plant's link is the smallest
plant-parent containing its **standing point** — the same point the lift asks.
`set_parent_link` is the one mutator (both sides of the link). Move/align,
resize, rotate, live-applied resize/vertex paths, create/paste/duplicate, all
four arrays and mirror reconcile it inside the SAME undo entry; a copy drops
the link it was serialised with; a moved bed carries its plants. Explicit
`set_parent_bed` links are respected until the next geometry edit. Nesting and
the "inside includes the pen stroke" definition are unchanged, recorded as
decisions.

**Lesson.** "The app reconciles X" must be answerable as a list of *mutating
commands*, not a list of call sites that happened to remember. Put the rule in
the command, next to the geometry it depends on, so undo replays both. And
when two surfaces ask the same geometric question, make them ask the same
point — a tolerance between them is a bug with a comment.

**Review round (independent senior review, 2026-10-29).** Six P1s, all real, all
fixed. The lesson repeated itself one level up: the first pass had wired the
COMMAND paths and the live drag-release paths, but three other real entry points
were missed — the Properties panel's typed width/height (it registered a resize
without `notify_applied`, so a bed unlinked on redo but not on the original
action), the agent's `set_vertex`/`add_vertex`/`delete_vertex` (they execute the
vertex command directly, with no drag-release handler), and a ROTATED item's
constraint-corrected partners (a partner plant or bed moved by the solver was
never re-decided). The second review also caught the opposite failure: a
scene-wide "recompute every plant" tracker on a bed edit silently overruled a
plant's explicit link to a FAR-AWAY bed. The fix scopes a bed edit to plants
whose target or current parent is that bed (plus the plants the edit actually
moves), and the test now pins the unrelated-bed case. And the mirror-MOVE undo
lost the bed's child id because the mirrored replacement reuses the plant's id
while being a different object — `restore` now replays every tracked plant's
pre-edit link and the heal path restores the child list.
