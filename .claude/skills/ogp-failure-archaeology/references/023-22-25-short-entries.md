## 22–25. Short entries

**22 — Same-z stacking flips after save/load** (US-12.10/F2.7, debug-verbose case
study): plant on a bed rendered correctly live, hidden behind the bed after reload. Both
had `zValue() == 0`; Qt tie-breaks equal z by **insertion order**, which differs between
live mutation order and JSON-load order. Fix: explicit `parent.zValue() + 1` pass in
`_update_items_z_order`. Never rely on insertion order across a persistence boundary.
Pinned by `tests/unit/test_plant_bed_zorder.py`. **Closed (further, #338):** this entry's
band-aid (`ensure_z_above_parent`, one explicit `+1` for the plant/bed and ROOF_RIDGE
cases only) covered exactly those two relationships; every *other* same-layer pair had
no such band-aid and silently inverted on every save/load too — nobody had noticed
because nothing gave a user reason to care which of two untied objects rendered in
front. #338's per-object stacking order root-causes the whole family: `zValue()` is now
always **derived** from a persisted sparse rank (never stored as raw intent), save order
flipped from `scene.items()` (top-first) to bottom→top, and the plant/bed +
ROOF_RIDGE/owner-polygon relationships are a **derive-only reorder** (`core/stacking.py`,
ADR-043, §8.25) instead of a one-off z bump — `ensure_z_above_parent` itself is deleted.
See §11.4 and the new entry 25 below for the two design mistakes this fix's own design
review caught before either shipped.

**23 — Bed-menu wiring regressed twice** (#173, US-12.8): four independently-implemented
bed shape classes meant every new bed-only context action had to be hand-added to each;
pest log missed Polygon/Ellipse, succession missed three of four. Fix: central
`build_bed_context_menu` + `dispatch_bed_action` (ADR-017, §8.14) gated by the
parametrised `tests/integration/test_bed_context_menu.py` — adding a bed feature means
adding one assert line per shape there. Closed; read §8.14 + ADR-017 BEFORE adding any
bed feature (CLAUDE.md says the same).

**24 — `max()` is left-biased on ties** (US-12.10/F2.10a, debug-verbose case study):
`SoilTestHistory.latest = max(records, key=r.date)` returned the *first* same-day
record, hiding a newer Lab record behind an older Kit record. When a sort key has limited
resolution (date, not datetime), assume ties and design the tie-break explicitly.
Pinned by `tests/unit/test_soil_test_history_latest.py`. Closed.

**25 — Two stacking-order designs failed before implementation, caught in design
review** (#338, 2026-08-23 — not a bug found in shipped code, a design-review catch
worth recording the same way): (a) a first draft had the per-layer z-refresh *also*
renumber every item's rank as a side effect of running (convenient — one pass does
both). Rejected because the refresh runs on many paths that have nothing to do with an
explicit arrange (a layer visibility toggle, an opacity-preview commit, any unrelated
command's cleanup pass) — if it renumbered ranks, a command's undo snapshot taken
*before* `execute()` would no longer match the ranks in force by the time `undo()` ran,
silently breaking Ctrl+Z for any command unlucky enough to trigger a refresh in between.
(b) a second draft assigned a provisional z at add time, to be finalized into a real
rank lazily. Rejected because it breaks the moment an item is deleted from the middle of
a layer — the reserved provisional slots stop describing a contiguous order and a later
finalize pass can't tell a genuine gap from a slot it's free to reuse. The shipped design
(ADR-043) keeps rank-writing to exactly four call sites (`CanvasScene.addItem`,
`MoveToLayerCommand`, `ArrangeItemsCommand`, the post-load renumber) and makes every
refresh a pure read of whatever ranks already exist. Lesson, generalized: any code path
that both (a) runs unconditionally/opportunistically and (b) can be reached between a
command's `execute()` and its `undo()` must never mutate the state an undo snapshot
depends on — if it needs to run there, make it *derive* its output instead of *writing*
it. Recorded in ADR-043's rejected-alternatives table and §11.4.

Other settled one-liners worth knowing exist (all in §11.4, all closed): QLineEdit
Return bubbling to the canvas finalizing the polyline (US-A4); the Dynamic Input overlay
chasing the cursor away from the mouse (US-A4); grid snap silently overriding anchor
snap (pinned by
`tests/integration/test_anchor_snap.py::test_grid_snap_does_not_override_anchor_snap`);
the status-bar startup reminder invisible behind the modal Welcome dialog → persistent
`TaskReminderBar` + deferred `singleShot(0)` (pinned by
`tests/integration/test_tasks.py::TestOverdueReminderBar`); shopping-list price ids must
encode the display unit (g vs kg) or a price silently multiplies 1000×; trellis gallery
thumbnails fell through to the round fallback because a SOLID fill has no texture
(PR #236 manual-test fix, CLAUDE.md C3 row).

---

