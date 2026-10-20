# Archive 05: Phase 17 L1.3 workspace

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.16 What the 3D workspace taught (Phase 17 L1.3, #385)

Symptom → root cause → fix, for the things that cost time while the workspace (ADR-060, §8.29.3)
was built. The engine's own traps are §11.4.15; these are about wiring an engine into an app and
about measuring it.

1. **A Python callable on a QObject's `destroyed` signal crashes a test that has nothing to do
   with it.** *Symptom:* after "disconnect a clock subscriber when its QObject is destroyed" was
   built as `receiver.destroyed.connect(<closure>)`, the suite died with an access violation in
   `test_sim_clock_wiring.py::TestHeatmapMidComputeDateChange`. *Root cause* (bare PyQt 6.11,
   four ways to let such an object go): freed by refcount — the hook runs once; the wrapper in a
   reference cycle and collected — the hook runs **0 times**, silently; the same with Qt owning
   the object and a `deleteLater()` pending — **access violation** inside the hook when the
   deferred delete runs. The callable lives and dies with Python's idea of the wrapper, not
   with the C++ object; the collector clears it and the connection stays behind. *Fix:* nothing
   hangs on `destroyed`. The clock's channel calls a guard that asks `sip.isdeleted()` at every
   delivery (`ui/sim_clock_subscription.py`, ADR-053 addendum). *(Fix round 1: master's sun
   coordinator, v1.30.1, had the same shape — a closure on its own `destroyed` holding a bound
   method of itself. In bare PyQt that closure runs 0 times in the deferred order, 5 of 5:
   its clean-up silently does not happen. It listens through the helper now, and a scan
   refuses a new `….destroyed.connect(…)` anywhere in the product; the one older site, the
   global search field, is listed there by name.)* **Do not hang clean-up on a
   QObject's `destroyed` signal from Python: the callable can be collected before the signal
   fires. Ask at the moment of use.**
2. **Qt keeps graphics state for every Model it ever drew.** *Symptom:* the memory soak read
   34.6 MB per reload against a bound of 10, with nothing growing in Python (`tracemalloc`: 0.045
   MB per reload) and nothing in VRAM (DXGI: flat). *Root cause:* two retentions inside Qt Quick
   3D — per-draw-call state kept for every destroyed Model until
   `QQuickWindow.releaseResources()` (about 0.2 MB each with shadow passes, independent of the
   mesh: 19 MB per rebuild of the small bench plan, 65 of the large), and what a frame holds
   for destroyed Models, which comes back only at the end of a PRESENTED frame (item 3). *Fix:*
   the workspace counts retired Models and releases (ADR-060 decision 15): 2 MB per rebuild
   instead of 19. *How it was found:* a bare host, 100 Models per round, ONE thing changed per
   run — buffers only, geometries only, Models never drawn, drawn by readback, drawn in
   presented frames, sun on, shadows off, embedded, another material, 300 or 12,000 vertices
   (ADR-048 addendum "L1.3" has the table). The vertex-count runs said "not the mesh"; the sun
   run said "per pass". What the release does NOT give back: 15 to 20 kB per destroyed Model
   (2 MB per rebuild of the small plan, linear over 60 rebuilds) — which is not graphics
   state at all (a view that draws nothing leaves 1.5 MB per rebuild), and bare Qt alone
   keeps 3.4 kB per `Model` with a material that is created with `createObject()` and
   destroyed, never drawn, the engine's collector called. Churn of QML objects is not free;
   a feature that replaces many Models per tick has to avoid the replacing.
3. **A soak that reads back every cycle measures the readback — a lesson that was filed
   wrongly twice before it was filed right.** `grabWindow()` renders a frame of its own and
   reads it back; that frame is never presented (`afterFrameEnd` fired 0 times in 40 grabs),
   and what it holds comes back only when a PRESENTED frame ends. With the display asleep
   Windows presents no frame at all (update requests come from a vblank thread), so on this
   machine at night every frame of every soak was a readback and everything stayed.
   *First filing:* "a property of my instrument" — the soak's child was made to present by
   timer (`QT_D3D_NO_VBLANK_THREAD=1`) and went on reading back once per rebuild. *Second
   filing,* after the ground story read +16 MB per re-bake in a view that did not present:
   "a view that presents nothing keeps every byte uploaded to it" — and a rule was built on
   that sentence (the pipeline paced by presented frames, one generation for a dark view).
   The independent review of the ground story then took the readback out of its loop and
   read +0.0 MB per cycle. The same here, with the pacing gone: twenty rebuilds with the
   view's frames withheld cost 1.5 MB each without a readback and 8.5 with one readback per
   rebuild (26 without the cache release) — and dedicated GPU memory does not move at all
   without the readback, because nothing is drawn. The growth was per frame RENDERED BY A
   READBACK AND NEVER PRESENTED; never per upload, never per edit. The pacing was taken out
   again: it fixed nothing and added a way to get stuck. *Fix:* nothing in the product takes
   a frame from the live view (ADR-060 decision 17), and the soak takes none inside its
   measured loop — one before, one after. **Before a memory curve is read, and before a
   rule is built on it: list every frame the measuring loop itself renders, and run the
   loop once without them.**
4. **`processEvents()` after an edit measures the 2D side.** The first edit-to-frame number
   (p95 56.6 ms) was taken as "edit, `processEvents()`, readback": it contained the rest of the
   event-loop turn — the canvas repainting itself, the minimap, the panels. *Fix:* the readback
   is taken inside a slot on the pipeline's `applied` signal, the moment the pass committed
   (p95 17.6 to 20.6 ms at 1600 × 900; 29.2 ms on the maximised 5120 × 1369 window).
   Also there: a scripted `redo` with nothing to redo "measured" about 200 ms — the time-out of
   waiting for a pass that never came. A measuring script counts the edits that reached the
   engine and reports misses.
5. **A zero timer is not "next turn".** A pass scheduled with `QTimer.singleShot(0)` waited
   behind every timer that was due — on the large bench plan 5 % of the passes started more
   than 228 ms late, behind the 2D side's debounced work. A posted event is delivered first.
   And at HIGH priority it is delivered too early: before the scene's own queued `changed` for
   the same edit, which then starts a second pass (four tests met two snapshots per edit).
   Normal priority, and the two signals share one pass.
6. **The pan comparison was wrong three times.** (a) Two long blocks one after the other —
   Split, then Plan — measured the machine's drift: 1.10 to 1.28 for the same build while other
   suites ran. (b) Short alternating blocks that walked on from where the last one stopped
   compared lawn with dense beds: per-round ratios between 0.16 and 7.2. (c) A walk that reaches
   the end of the scroll range "pans" for 0.001 ms a step. *Now:* six alternating rounds, every
   block from the same position along the same pixels, every step asserted to have scrolled:
   0.83, 1.04 and 1.09 in three runs on the same busy machine (the fastest tenth: 1.05).
7. **An editing tool wrote three `\u` escapes as the characters themselves.** The module that
   DEFINES the line separators (U+2028, U+2029) then contained two of them, invisibly, and so
   did two tests. *Fix:* named escapes (`\N{LINE SEPARATOR}`), and a test that scans `src/` and
   `tests/` for characters a reader cannot see
   (`tests/unit/test_plain_text.py`; its own control caught that the first version missed
   U+FFFD).
8. **Importing the gate's hook into the test process moved the test process off its own
   settings key.** The hook's job is to rebind the settings names of the process that imports
   it — a child. A test that imported it to read a constant rebound pytest's own; conftest's
   per-test check caught it. *Fix:* tests READ the file; a test pins the two modules that may
   import it.
9. **Two delegating import finders asked each other for ever.** The gate's finder and the test
   children's own settings finder both "ask the other finders and wrap the loader they name".
   Each found the other. *Fix:* a re-entrancy guard per module name.
10. **A value read back from a child's store after the child left was empty** — the child's exit
    hook empties its throw-away key. What a run wrote (Recent Files, the saved geometry) is
    recorded INSIDE the child at its last step.
11. **`QSG_RHI_PREFER_SOFTWARE_RENDERER` is read once per process.** Set before the first Qt
    Quick window it selects WARP; set after, it does nothing — and the workspace learns that it
    needs software rendering long after start-up. *Fix:*
    `QQuickGraphicsConfiguration.setPreferSoftwareDevice(True)` on the window, which works at
    any time (the adapter read from Qt's own log: "Microsoft Basic Render Driver").
12. **A test that waits for a memory to shrink must use shapes that differ.** The record
    layer remembers outlines by shape: three identical hedges are one entry, and "fewer entries
    after the plan changed" compared 4 with 4.
13. **Two tests were green in every run of the story's own files and red in the whole suite.**
    *(a)* "The Split position is kept for the next session" restored the saved state into a
    bare `QSplitter` that was never shown and compared its sizes with the workspace's: equal —
    until an earlier test (a theme test) had left an application style sheet behind. A widget
    that was never shown is not polished, so its handle kept the platform's 4 px while the
    shown one's had the theme's 1 px: `[797, 399] != [799, 400]`. *Fix:* the test restores
    into a second real workspace in a second window, the product's own path. *(b)* "The
    subscription books do not grow" asserted that the process-wide table of clock subscribers
    was EMPTY at its end; in the suite two receivers of earlier tests were still alive.
    *Fix:* the test holds what was there before it and compares against that. **A test owns
    no process-wide state: compare with what was there before, never with zero. Compare a
    widget only with one in the same state (shown, polished). And run the whole suite in its
    own order before a story's files are believed — the order is part of the test.**
14. **A "before the document changes" hook ran before the change could fail.** This story fixed
    #428 with a hook of the main window in front of each document path: clear the
    hours-of-sun map, uncheck its button. In `_load_project_file` that is in front of
    `ProjectManager.load()`, whose first phase validates the file and can raise — so opening a
    damaged file, a recent file that had moved, or an agent's `open_plan` on a bad file left
    the plan open and threw its map away (found by the independent review; master, fixing #428
    at the same time through `CanvasScene.document_replaced`, pins the opposite). *Fix:* the
    hooks are gone; the scene's signal — emitted in the COMMITTING phase — is the one
    mechanism, for the map and for the 3D workspace. **Tie clean-up to the event that says
    the thing happened, not to the call that is about to try. And when two changes fix one
    issue, one of them goes.**
15. **An estimate "at ground level under the plant" is inside whatever the plant stands in.**
    Merged from master: the per-plant hours of sun sample the ground cell under the plant's
    centre and leave out the plant's own solid. A raised bed is a solid too. *Measured on
    v1.30.1:* a tomato in a 40 cm raised bed in the open, Berlin, 21 June: 0.0 hours and a
    "too little sun" warning — on every plant of every raised bed. The reference plan of
    that feature has a tree and two tomatoes on open ground; no bed. *Fix:* the receiver
    names the soil parent it stands in (the membership half of the base rule the casters and
    the 3D records already used) and that parent is spared like the plant's own solid: 16.5
    hours. **When a sample point is "under" an object, ask what else is under the object.
    And the first plan a sun feature must be tried on is the one the feature is for: a
    vegetable garden is raised beds.**
16. **A repaint is not an edit.** *Symptom* (the independent review, counting in the real
    window with a recording sink): with the sun simulation on, 10 time changes cost 10
    whole-plan snapshots; 20 mouse moves of the polygon tool's preview, nothing created, 20;
    three selections and a clear, 4; "Animate" is a timer — a snapshot per tick. A preview
    mouse-move turn cost 6.7 ms in Split against 1.0 in Plan (small bench plan), 18.3 against
    0.7 (large). The gates had passed: they changed the time with the sun simulation OFF, and
    the only toolbar that holds the time slider is shown while it is ON. *Root cause:*
    `QGraphicsScene.changed` — a REPAINT — was wired straight to "the plan is dirty". *Fix:*
    the scene's plan revision for what is announced, one quiet-time pass for what is not
    (ADR-060 decision 5); a preview move now costs the same in both modes (median ratio 0.94 and 0.98 on a quiet machine).
    **A signal named "changed" says what it changes: here the pixels, not the plan. And a gate
    that a toolbar's visibility can switch off has to be run with the toolbar shown.**
17. **Qt says "shown" one turn after an item was added — to an item that was visible all
    along.** The scene polishes a new item in the next turn and sends
    `ItemVisibleChange` / `ItemVisibleHasChanged(true)` (`_q_polishItems`); announced as a
    change of the plan, every added item cost a second whole-plan pass. *Fix:* the item hook
    remembers at the PRE-change notice what the item was, and a "change" to what it already
    was is not announced (`garden_item.announce_plan_change`).
18. **A test helper waited a fixed time for a pass the product holds.** *Symptom:* on the Linux
    CI runner `test_a_plan_with_a_refused_item_shows_the_indicator_and_fixing_it_clears_it`
    read `problems_text() == ''` 120 ms after the switch to Split; the log line of the pass
    that refuses the item was in the test's TEARDOWN. Green on the dev box in every run.
    *Root cause:* the first pass of a document is held until its notice was painted — or for
    250 ms when it is not — and runs 25 ms later (decision 7): about 55 ms with the paint,
    300 ms without. The product is not late: the indicator is set by the very pass that
    finds the problem, in the same call. The tests were early — and not one test: the shared
    helpers (`Bench.settle()`, 57 uses, and `_calls()`) waited a fixed 80 ms; with the
    notice's paint withheld on purpose, 23 tests of two files failed. *Fix:* one condition
    (`pipeline_settled`) waited for, not a time (§8.10.9). **A fixed wait in a test is a
    guess about the slowest machine the test will ever run on. Wait for the condition the
    product itself waits for — and to prove the test, run it with the slow path forced.**
19. **A count of a shared list measured every other test.** *Symptom:* under xdist (and in
    CI's coverage job) `test_a_destroyed_coordinator_is_never_called_and_takes_its_theme_listener_along`
    failed with `assert 1 == 3 - 1`. *Root cause:* `ui/theme._theme_listeners` is the
    process's; the dead coordinators of earlier tests in the same worker had their listeners
    on it, and the first theme change takes every dead one off. *Fix:* the coordinator keeps
    its listener by name (`theme_listener`); the test asks whether THAT entry is on the list.
    Item 13's rule, again, in a new place: **assert about your own object.**
20. **A sentence on a button is cut where a label would wrap.** The strip's notices were moved
    to rows of their own with word-wrapping labels, and it was believed fixed; a test at the
    review's size (1366 px window, a 455 px pane) with every notice at once found two that
    were still sentences on buttons — "2 objects are not shown in 3D", and "Try Hardware Next
    Time", whose German text alone is 456 px wide: squeezed to 220 px, cut, no ellipsis. A
    button with a long text and a fixed policy does the opposite: it makes the pane as wide
    as the sentence. *Fix:* sentences are labels; buttons hold a short command, never
    narrower than their text, on a row of their own after a sentence; a click's outcome is
    said in a label, never written onto the button. **Pin a layout at the size where it
    broke, with everything on screen at once, in every shipped language.**
21. **The un-paced close gates prove less than they look.** Every render gate runs with
    `QT_D3D_NO_VBLANK_THREAD=1`, so that no scenario depends on whether the dev box's display
    is awake. The three close gates were added once more as the product starts — paced by the
    display — and pass; but on a SLEEPING display such a view presents its first frame and no
    more, so "close with 3D visible" there closes a view that presented once, not one that
    presents frame after frame. That case stays on the owner's checklist (display on).
22. **`QGraphicsScene.changed` comes twice for one `item.update()` — the second time empty.**
    *Symptom:* a hand mutant of the net ("an explained repaint arms the net too") survived
    every test; the test written to kill it found the PRODUCT doing what the mutant did: a
    write that nudged first and repainted after was in 3D at once — and 400 ms later a second
    whole-plan snapshot ran and found nothing. *Root cause*, from a probe of the signal order:
    the announced pass ran, then `changed([rect])` (explained: the revision had moved), then
    `changed([])` — which compared the revision with the one the first `changed` had just
    recorded, and so looked unexplained. With a listener on `changed` Qt emits an item's
    update at once from `_q_processDirtyItems`; the queued `_q_emitUpdated` that update had
    asked for arrives afterwards and emits what is left: nothing. *Fix:* an empty `changed`
    reports no repaint and is ignored. **A signal can carry "nothing happened" — read its
    argument before treating the emission as an event. And a surviving mutant is a question
    about the product as much as about the tests.**
