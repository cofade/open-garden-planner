## 6. Find Plants selection flakiness — two rounds (#212/#215)

Source: §11.4 (the #212 entry + its manual-test-round-2 follow-up).

- Round 1 symptom: clicking a plant in the Find Plants list selected it "only sometimes".
  Two compounding causes: (1) rows cached live `QGraphicsItem` refs — stale after
  undo/redo/delete/reparent, `setSelected` silently no-ops on a detached item; (2)
  `scene.changed` (fires on every repaint, including the repaint *caused by selecting*)
  was wired straight to a destructive full list rebuild, which could destroy the row
  mid-click. Fix: store `item_id` only, resolve at click time, defer the scene mutation
  with `QTimer.singleShot(0, …)`, debounce the refresh (~150 ms).
- Round 2 symptom (manual test): "list jumps back to the top a moment after I stop
  scrolling"; "single-click sometimes needs a second/third click". **The debounce was
  not enough** — it coalesces a burst but still fires once the burst settles, and
  selecting a plant triggers its own burst (selection → overlap/companion visuals →
  repaint → more `scene.changed`), so every selection still ended in a destructive
  rebuild.
- Fix: `_update_results_display` computes a **signature** of the visible rows and
  early-returns when unchanged; real rebuilds capture+restore scroll and re-select by
  `item_id`. Row widgets set `WA_TransparentForMouseEvents`.
- Lesson (verbatim spirit of §11.4): a debounce limits *how often* you rebuild, not
  *whether you needed to* — a list driven by the repaint firehose must be idempotent
  (diff before rebuild). The signature guard is explicitly a **band-aid**; the firehose
  smell is the same one as #206 (see Open section).
- Status: closed (workaround-grade). Pinned by
  `tests/integration/test_find_plants_selection.py`
  (`test_row_survives_interleaved_refresh_and_first_click_selects` names the signature
  guard in its docstring).

---

