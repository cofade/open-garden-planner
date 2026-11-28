---
id: ADR-060
title: "The 3D workspace — Plan / 3D / Split in the main window, one kept engine host (Phase 17, L1.3)"
status: "Accepted (2026-10-12, #385 story L1.3, epic #383). Behind the internal switch `OGP_QUICK3D=1` until L1.9 made the workspace the default and deleted the switch (addendum \"the default and the removal\" at the end of this ADR; decision 1 below is superseded by it). Builds on ADR-048 (the engine), ADR-053 (the clock) and ADR-059 (the pipeline), and closes the two things ADR-048 left to this story: criterion 2's deferred half and criterion 10's leak half (addendum there)."
legacy_anchor: adr-060-the-3d-workspace--plan--3d--split-in-the-main-window-one-kept-engine-host-phase-17-l13
---

# ADR-060: The 3D workspace — Plan / 3D / Split in the main window, one kept engine host (Phase 17, L1.3)

**Status**: Accepted (2026-10-12, #385 story L1.3, epic #383). Behind the internal switch
`OGP_QUICK3D=1` until L1.9 made the workspace the default and deleted the switch (addendum
"the default and the removal" at the end of this ADR; decision 1 below is superseded by it). Builds on ADR-048 (the engine), ADR-053 (the clock) and ADR-059 (the pipeline), and closes
the two things ADR-048 left to this story: criterion 2's deferred half and criterion 10's leak half
(addendum there).

## Context

L1.1 built a pipeline (records → diff → builders → sink) and L1.2 an engine host; nothing connected
either to the app. The shipped 3D view is a second window that rebuilds its whole scene on every
change. The epic wants 3D to be a **mode of the main window** — Plan, 3D, or both side by side — in
which an edit appears while the user watches.

Five facts shaped the design:

- **The engine's view is a native window** (`QQuickView` in `QWidget.createWindowContainer`,
  ADR-048 criterion 3). No sibling widget paints over it; a notice "on top of 3D" cannot exist.
- **The host must be built lazily and never built twice.** Importing and starting it costs 0.4 to
  1.2 s on the GUI thread, and ADR-048 criterion 10 demands zero aborts over hide / show cycles —
  which the host delivers when it is kept and only hidden.
- **A first 3D start can kill the process inside the graphics driver** — no exception, no dialog,
  no log line. A user whose driver does that must still reach 3D at the next start.
- **The default test tier has no GPU** (`QT_QPA_PLATFORM=offscreen` selects the software scene
  graph, where Qt Quick 3D draws nothing). Whatever is a decision and not a Qt Quick call must be
  testable without the engine.
- **A whole-plan snapshot is O(total vertices) even when every record is cached** (3 to 4 ms on
  the small bench plan, 13 to 15 ms on the large one, measured below), and the first pass of a
  plan costs the sum of its items — seconds for a hostile plan.

## Decision

1. *(Superseded by L1.9: no switch — addendum "the default and the removal", D1.)* **One
   internal switch.** `app/settings.py::quick3d_workspace_enabled()` was the only read of
   `OGP_QUICK3D`; exactly `"1"` switches the workspace on. Off, the app is what it was: no
   workspace object, nothing of `ui/view3d/workspace` or of Qt Quick imported, the canvas area's
   widget tree unchanged. No setting, no menu entry, no persisted value: the switch leaves with
   L1.9.
2. **`Workspace` holds the canvas and, from the first switch to 3D or Split on, a 3D pane beside
   it** (`ui/view3d/workspace.py`). Three modes: *Plan* (the canvas alone, at the size and with the
   pixels it had without the workspace), *3D* (the pane alone), *Split* (a splitter; neither side
   collapses, the pane is at least 220 px wide — a collapsed 3D pane would be a third way of saying
   "Plan" in which the engine keeps running). The mode is three checkable, exclusive actions:
   **Alt+1 / Alt+2 / Alt+3**, a *Workspace* submenu of the View menu with "Reset 3D View", and a
   small button row — floating over the canvas in Plan and Split, in the pane's strip in 3D. The
   Split position is kept through the UI-state store (ADR-041), and only when the session really
   was in Split — saved the moment Split is LEFT, and when the app closes in it (FR-3D-WS-01
   says "remembered between sessions"; it used to be saved only by an app closed in Split).
   **Entering 3D mode cleared the canvas selection** — a stopgap with an owner,
   `Workspace.clear_selection_hidden_by_3d_mode`: 3D mode hides the canvas, and the app's
   shortcuts stay, so Delete, Ctrl+X and Ctrl+D would have acted on what nobody could see.
   **Removed by the selection story (L1.8 addendum)**: the selection is shown in 3D — the ring
   round every selected item and the info card below the view — so 3D mode keeps it and the
   shortcuts act on what is shown (`test_view3d_workspace.py::test_3d_mode_keeps_the_selection_and_shows_it_so_its_shortcuts_act_on_what_is_seen`).
3. **Nothing overlays the native 3D window.** Every control, notice and message of the 3D pane
   sits in a strip ABOVE the view or REPLACES the view (a message page in a stacked widget). The
   floating switch is the one overlay there is, and it floats over the canvas, an ordinary widget.
   L1.8's info card goes into the same pane, beside or below the view. **The strip is a row of
   controls with the notices below it, one per line; a sentence is a label that wraps, and a
   button holds a short command, is never narrower than its text and, after a sentence, has a
   row of its own.** Measured on the first delivery: one row of non-wrapping labels needed 785
   px, and Split in a 1366 px window gives the pane 455 — the compatibility sentence was cut
   with no ellipsis and no tooltip. After the labels were made to wrap, two sentences were
   still on BUTTONS (the problems count; "Try Hardware Next Time", whose German text alone is
   456 px): squeezed to 220 px, cut. A click's outcome is said in a label of the strip, never
   written onto a button (a sentence on a button of fixed size made the pane as wide as the
   sentence). Pinned at 1366 px with every notice at once, in English, German and Spanish.
4. **One engine host per main window, built on first use, kept, only hidden and shown.**
   `Workspace.engine_factory(prefer_software) -> (host, sink)` builds it — by default
   `Quick3DHost` and `Quick3DSink`, imported inside the factory — and is THE test seam: the
   default tier hands in a recording sink and a stand-in host. The workspace module imports no Qt
   Quick binding. Shutdown runs in the main window's `closeEvent`, while the window exists:
   pipeline, start marker, host.
5. **The pipeline's controller is engine-free** (`ui/view3d/sync_controller.py::Scene3DController`):
   the scene's PLAN REVISION, the clock's two channels and one quiet timer in — at most ONE pass
   per turn of the event loop out. **What starts a pass is an announced change of the plan, not
   a repaint** (two layers):
   - *The fast path — the plan revision.* `CanvasScene.plan_revision` / `plan_changed(int)` move
     exactly when plan CONTENT changed, at the chokepoints the scene and the undo stack already
     have: an item added or removed; a command executed, undone or redone
     (`CanvasScene.set_command_manager` → `stack_changed`); a `GardenItem`'s position,
     transform, visibility, z or parent changing (`garden_item.handle_item_change`, THE hook
     every item's `itemChange` calls first — a census of `ui/canvas/items` pins it; a group,
     whose members Qt tells nothing when it moves, has one too); a layer added, removed,
     reordered, shown, hidden, locked or made translucent (`layers_changed`); the canvas
     resized; the scene cleared; every mouse move of the four handles that change a geometry
     in place; and **THE nudge, `CanvasScene.note_plan_changed()`**, for a writer that goes
     round all of those (the plant panel's instance fields — its shipped ad-hoc `item.update()`
     "nudge" calls it now — and the Properties panel's seven direct writes). A moved revision
     marks the records dirty at once. Qt's polish of a new item (`ItemVisibleHasChanged(true)`
     one turn after it was added, to an item that was visible all along) is not announced: the
     hook remembers at the pre-change notice what the item was.
   - *The net — what is not announced.* A `scene.changed` that no revision move explains
     snapshots nothing: it (re)starts ONE single-shot timer, `NET_QUIET_MS` = **400 ms** (twice
     the sun animation's tick, pinned, so that "Animate" never reconciles between two ticks),
     only while 3D is visible. When the scene has been quiet that long, ONE reconciliation pass
     runs (`TickReport.reconciled`). It normally finds nothing; when it finds a difference an
     edit path forgot its announcement — the pass applies it, `unannounced_changes` counts it
     and one DEBUG line names the kinds that differed, with no id. So no edit stays out of 3D
     for longer than the quiet time, whatever wrote it. No `changed`, no timer; a scene that is
     never quiet is reconciled every `NET_MAX_WAIT_S` (5 s); a repaint while 3D is hidden
     leaves a flag, and coming back starts the timer once. A `changed` with an EMPTY list is
     not a repaint and is ignored: with a listener on `changed`, Qt reports an item's
     `update()` at once from its dirty-item pass, and the queued `_q_emitUpdated` the same
     update asked for arrives afterwards and finds nothing (measured: every `item.update()` gave
     `changed([rect])`, then `changed([])`). Taken as a repaint, that echo of an announced write
     whose repaint lands after its pass (the Properties panel repaints, then nudges) was
     "unexplained" and cost a second snapshot a quiet time later — found by a hand mutant that
     survived, not by a gate. **An announcement explains repaints for one turn after its pass,
     no longer** (`_expire_explanation`, scheduled at the end of every records pass): an
     announcement that repaints nothing (a typed height through its command, the bare nudge)
     otherwise left "the revision moved" standing, and the NEXT unannounced write's repaint read
     as explained — no timer, and the write stayed out of 3D until some unrelated repaint
     (measured by the scoped re-check: 3D height 250 against 777 in the plan after 1.5 s). The
     guarantee above holds only with the expiry; pinned by
     `test_an_unannounced_write_after_an_announcement_that_repainted_nothing_is_still_found`.
     The one write the net cannot see is a write to an item on an opacity-0 layer: Qt emits no
     `changed` at all (a limit of a repaint-driven net, recorded). While "Animate" runs, the
     `NET_MAX_WAIT_S` bound reconciles every 5 s (a whole-plan snapshot that finds nothing) — a
     stated cost.
   - *Measured* in the real window (Split, a recording sink): a time sweep with the sun
     simulation on, 20 preview moves of the polygon tool, three selections and a clear, a hover
     over handles, "Animate" for 2 s — 0 snapshots while each happens and 1 after the quiet
     time, which found nothing (first delivery: 10, 20, 4, …, one per tick). 31 edit paths —
     the §8.10 workflow's, undo / redo, layer visibility / lock / opacity, arrange, group /
     ungroup, paste, duplicate, a handle drag, an Agent API write, the Properties-panel edits,
     the plant panel's instance AND species fields (the species fields were missing their
     nudge until the scoped re-check found them) — each moves the revision and reaches 3D by a pass it announced; `unannounced_changes == 0`.
     A preview mouse-move turn costs in Split what it costs in Plan: median ratio **0.94** on
     the small bench plan (0.58 against 0.62 ms) and **0.98** on the large one (0.76 against
     0.77 ms), 0 snapshots in 160 moves in Split — the `perf` run on a quiet machine; 1.01 and
     1.01 in a run beside other suites (1.86 / 1.84 and 2.69 / 2.66 ms); first delivery: 6.7
     against 1.0 and 18.3 against 0.7. One whole-plan snapshot costs 3.4 and 14.3 ms. The gate
     is ≤ 2.0 (`perf`).

   The pipeline's other rules:
   - *Paused while 3D is hidden*: two flags and nothing else — no snapshot, no diff, no sink call,
     no timer. Showing 3D runs one catch-up pass, which `SceneSync` guarantees equals a
     from-scratch apply.
   - *One pass, one transaction*: records, sun and ground travel in one `sync.apply`. A
     time-of-day change is LIGHT ONLY (one `set_sun`, no snapshot); a date change regrows the dated
     plants; writes faster than passes coalesce in the flags — an animated date never queues more
     than one regrow.
   - *A snapshot only on an announced change of the plan, or once after a quiet time — never on
     a timer that spins, and never per repaint* (above).
   - *A pass that keeps failing is tried again when something changed, and says so once.* The
     next change of the plan, of the date or of the light tries again; a repaint does not (the
     net stands down while a pass is owed). The log gets ONE ERROR line per distinct failure of
     an outage (the same failure again is a DEBUG line; the next pass in which nothing failed
     ends the outage). It used to be 2 to 3 ERROR lines per change, with no backoff.
   - *A document change is not a reset.* A new or opened plan is another snapshot; `apply` removes
     what is gone. `SceneSync.reset()` is RECOVERY: after a sink call raised or the sync is
     poisoned the controller resets, applies once more, logs one line, and never lets the error
     reach the event loop; if that fails too it gives up for this pass and the next change tries
     again.
   - *One snapshotting scene per process* — the record layer's outline memories ride a
     process-wide generation clock (ADR-059); the workspace has one canvas scene and one
     controller.
   - *What 3D remembers per plan is dropped in one place* (`_drop_plan_memories`: the plant
     builder's shapes, the record layer's outlines) — on a document change and when the view
     closes.
   - *The ground seam*: `set_ground_stage(stage)` — `stage(previous_records, records, width_cm,
     depth_cm) -> GroundSpec` runs BEFORE `apply`, so what it returns rides the same transaction
     (L1.5's baker).
6. **A pass is a posted event of normal priority, not a zero timer.** Measured in the real app
   with the real engine (RTX 4070, window 1600 × 900, 3D pane 574 × 734, 120 scripted edits, clock
   from before the command to a finished readback taken the moment the pass committed):

   | scheduling | `bench_small` p50 / p95 | `bench_large` p50 / p95 | wait for the pass, p95 (large) |
   |---|---|---|---|
   | timer, 1 ms | 16.1 / 24.5 ms | 38.4 / 257.4 ms | 228.5 ms |
   | posted event, high priority | 14.0 / 18.9 ms | 29.7 / 45.5 ms | 0.1 ms |
   | **posted event, normal priority** | 13.0 / 17.6 ms | 29.2 / 66.7 ms | 34.9 ms |

   A zero timer waits behind the timers that are due — the 2D side's own debounced work
   (spacing, companions, the minimap). A posted event is delivered before them. At HIGH priority
   it also overtakes the scene's own queued `changed` for the same edit, which then costs a
   SECOND whole-plan snapshot per edit; at normal priority the undo stack's signal and the
   scene's share one pass.
7. **The first pass of a document is started by the PAINT of its notice.** "Building the 3D
   view…" is set, and an event filter on that label starts the pipeline after the label painted
   — not a timer that hopes the paint came first. A label that is never painted releases the
   pipeline after 250 ms; with the controls hidden (fullscreen preview) nothing is waited for.
   The same on a document change while 3D is shown, and for a catch-up pass after hidden edits
   (which may be a whole new plan).
8. **The camera is a Qt-free value with one owner** (`core/scene3d/camera.py::OrbitCamera`): a
   goal pose that input moves and a pose that follows it as a critically damped spring,
   integrated exactly (a stalled timer lands where many short steps would have). Target on the
   ground, distance 0.5 to 600 m, pitch 5° to 89°, the target kept within the plan plus 10 m.
   **It is moved by four things only — user input, "Reset 3D View", the first open and a
   document change — and "edits never move the camera" is therefore a property of the code:
   there is no other call site.** The step timer (16 ms) runs only while the camera is still
   moving and the pane is shown. Home (and "Reset 3D View") takes the SHORTEST turn to the
   default side: yaw is free while orbiting, and aiming at the default yaw itself unwound every
   turn (six turns, then Home: 2,477.5° back to 317.5°). The goal is the equivalent angle
   nearest to where the camera is; a snap (first open, new document) lands on the default
   itself.
9. **Input is an event filter on the native window** (`ui/view3d/orbit_input.py`,
   `Quick3DHost.install_event_filter`): the shipped view's gestures — left or middle drag pans,
   right drag orbits, both buttons or the wheel zoom, arrows pan, Alt+arrows orbit, PageUp /
   PageDown zoom, Home resets. Escape and every other key are passed on: the app's shortcuts
   work with the keyboard in the 3D window (measured: Ctrl+Z undoes, Alt+1 leads back to the
   plan), and Escape stays free for L1.8's walk mode.
10. **A start guard instead of a crash** (`ui/view3d/init_guard.py`, standard library only). Two
    small files in the app's log directory, beside `app.log`: `view3d-init-<pid>.marker`, written
    before the first 3D window of a session is built and removed when a frame was presented (or
    Qt reported "no graphics device", or Python caught an error, or the app closed in good
    order); and `view3d-compat.flag`. A marker whose process is gone means the start died: the
    flag goes on and 3D renders on the software adapter — **per window**
    (`QQuickGraphicsConfiguration.setPreferSoftwareDevice`), because
    `QSG_RHI_PREFER_SOFTWARE_RENDERER` is read once per process and does nothing after the first
    Qt Quick window (measured both ways). The pane says so, and offers "Try Hardware Next Time";
    ONLY the user removes the flag — a machine whose driver crashes would otherwise alternate
    between a crash and a software session for ever. A marker is per process, so a second
    running instance is not a crash; one older than 600 s whose process id "runs" is (the id was
    handed out again). A session that never opens 3D reads and writes nothing. **Three outcomes,
    not two — hardware, software, off.** A start that died in SOFTWARE mode switches 3D off (the
    flag says `off`; nothing is built or marked; the pane says why) — before, such a machine
    died at every 3D open, because the marker's mode was written and never read. A marker with
    this process's OWN id and no start of ours pending is a death (the process that had the id
    before us). And the poll that confirms the first frame runs only while 3D is shown: 3D
    hidden before its first frame takes its marker away (`Init3DGuard.abandon`), and shown
    again puts it back (`mark_again`) — a marker left pending was read as a death by a second
    instance 601 s later, and a healthy machine was put into compatibility mode. The notice and
    "Try Hardware Next Time" are on screen in EVERY state of the pane while the flag is on
    (running, failed to start, no device, switched off), and the button reports what happened
    to the file, not what was asked.
11. **"No graphics device" is a message, not a retry loop.** `health().scene_graph_error` ends
    the view for the session: the pane shows the message and — once, on hardware — "Use
    Compatibility Mode Next Time". Clicked, the button goes and the strip says what happens
    next, with the way back beside it; a setting that cannot be written is said in the strip
    and the button stays. An error raised in-process (an import, the scene file) is a message
    with "Try Again". Opening 3D never takes the 2D app down.
12. **What 3D could not show is said.** The record layer refuses some items the canvas draws
    (`SkipReason`), and a builder can fail: the strip shows a quiet, persistent count ("3 objects
    are not shown in 3D", with "Show List") and, on demand, a non-modal list — name, kind, a
    translated text per reason code — whose rows select the item on the canvas. The list shows
    at most `MAX_PROBLEM_ROWS` (200) rows and then "… and N more"; a fill walks the scene ONCE
    for every name (it walked it per row: 300 rows over 3,000 items took 0.55 s, 3,000 rows
    3.1 s, on the GUI thread, again on every change while the list was open — and duplicated
    ids, one hostile plan, are a reason code). The German reasons name no possessive ("der
    Umriss", not "sein Umriss"): they follow objects of every gender. A notice of the ENGINE
    ("The 3D view reported a problem") stays until that engine is gone — a pass used to erase
    it.
13. **Plan text is text** (`core/plain_text.py`, §8.11). A plan file is untrusted and Qt decides
    "rich text or plain" by LOOKING at a string. Everything plan-derived that reaches a tooltip,
    a label or a log goes through one helper: normalise (every line boundary `str.splitlines()`
    knows becomes one line break; other control characters and the bidi overrides become
    U+FFFD), THEN cap (lines and length, on what the consumer will see), THEN escape. Labels are
    `PlainText`; list rows are plain by the default delegate. This story's own log records are
    one normalised line at ERROR / WARNING with the traceback at DEBUG only.
14. **`connect_qobject` is how a QObject listens to the clock** (`ui/sim_clock_subscription.py`,
    ADR-053 addendum): the channel calls a guard that asks `sip.isdeleted` at every delivery. A
    scan of the product refuses a direct connect.
15. **What a destroyed Model leaves behind is released.** Qt Quick 3D keeps per-draw-call
    graphics state for every Model it ever drew, after the Model is destroyed — about 0.2 MB
    each on Direct3D 11 with the sun's shadow passes on, independent of the mesh — and only
    `QQuickWindow.releaseResources()` gives it back (`Quick3DHost.release_cached_resources()`,
    2 to 10 ms, the next frame unchanged). Every pass says how many items lost their Models
    (`TickReport.retired`: removed, geometry replaced, cleared by a reset); the workspace counts
    them and releases when 64 piled up and the pipeline has been quiet for half a second, or at
    once at 512 — an animated date regrows every dated plant per tick and is never quiet.
    **This is the leak half of ADR-048 criterion 10** (numbers in the addendum there).
16. **One mechanism says "the document was replaced" — the scene's.**
    `CanvasScene.document_replaced` fires when the old document is about to go — in `clear()`
    and at the start of the second, committing phase of a load; never for a load that failed
    its validation. master's fix of #428 rides on it (ADR-056: `_reset_sun_document`), and the
    workspace listens to the same signal (`Workspace.connect_plan` → `document_changed`); the
    main window tells the workspace nothing by hand. The slot reads nothing from the scene —
    it sets flags, and the pass they ask for runs with a later turn of the event loop, when
    the new document is in. *This story's first delivery had a mechanism of its own — a pair
    of hooks of the main window around the three document paths — and it was wrong: the first
    hook cleared the hours-of-sun map BEFORE `ProjectManager.load()` could fail, so opening a
    damaged file threw away the map of the plan that stayed open (master pins the opposite).
    It is gone.* An open that fails leaves the 3D view, its camera and what it remembers of
    the plan exactly as they were — pinned on the three paths a load can fail on (File → Open,
    Open Recent on a moved file, the agent's `open_plan`).
17. **Nothing takes a frame from the live view.** A readback of the shown host — `grab()`, and
    `wait_ready()` / `pick()` / `project()`, which need a frame — renders a frame of its own
    that is never presented, and what such a frame holds is given back only when a PRESENTED
    frame ends. In a view that presents nothing (the display asleep, a session that does not
    present) that is never: twenty rebuilds of the small bench plan with the view's frames
    withheld grew by 1.5 MB per rebuild without a readback and by 8.5 MB with one readback
    per rebuild — 26 without the release of decision 15 (ADR-048 addendum "L1.3"). So the
    workspace's steady paths — the pass, the health poll, the timers, a resize, the splitter
    — ask the host for none of them: the workspace tells the engine what the plan is, and
    Qt draws it when it draws. A picture of the 3D view for a file or a thumbnail goes
    through `quick3d/offscreen.py` (a host of its own, which gives everything back when it
    closes), never through repeated readbacks of the shown host. A click that picks (L1.8)
    is the user's own action, once. **The pipeline is NOT held back in a view that presents
    nothing**: it applies as always, nothing is drawn, nothing is uploaded (dedicated GPU
    memory did not move in those twenty rebuilds), and the first frame after the dark spell
    shows the plan as it is. Pinned twice — a stand-in host that records every frame-taking
    call through all the steady paths, and a scan of the five modules' source — and the
    memory soak keeps the same rule: no readback inside its measured loop, one frame before
    and one after.

## Alternatives considered (rejected)

- **A stacked widget instead of a splitter.** Split is the mode that makes the feature (an edit on
  the left, its solid on the right); a stack has no Split.
- **The mode switch in the toolbar, the tab bar or the status bar.** The toolbars are the tools';
  the tab bar belongs to the tabs. A switch on the surface it switches needs no finding, and in
  3D mode it must be in the pane anyway. Cost: one small overlay on the canvas in Plan mode — the
  canvas view's own pixels stay identical (pinned), the area's do not.
- **A notice over the 3D view.** Not possible over a native window; `QQuickWidget` would allow
  it and was rejected by ADR-048 (an offscreen round trip per frame).
- **Building the host at start-up, or rebuilding it per show.** The first costs every session
  half a second and a graphics device it may never use; the second is the abort ADR-048
  measured.
- **Polling the scene on a timer.** A snapshot per tick is O(total vertices): 13 ms of the GUI
  thread per tick on the large plan, for nothing, also while idle.
- **A timer of interval zero, or a high-priority event** — decision 6's table.
- **`scene.changed` as "the plan is dirty"** (the first delivery). `changed` is a REPAINT: a
  hover, a selection, a tool's preview under the mouse, the sun's shadow while the time slider
  moves. Measured by the independent review: a snapshot per repaint, a preview mouse-move turn
  6.7 ms in Split against 1.0 in Plan (large plan: 18.3 against 0.7). Its gates had passed only
  because they changed the time with the sun simulation off — and the toolbar that holds the
  time slider is shown while it is on.
- **The plan revision alone, without the net.** Every writer that goes round the chokepoints
  would have to be found — and the next one written would not be. The net turns a missing
  announcement from "3D silently stale" into "3D right after the quiet time, and a number".
- **The net alone, without the plan revision** (reconcile after every quiet time). Every edit
  would reach 3D 400 ms late; the gate is 50 ms.
- **Pacing the pipeline by presented frames** ("no second pass before the view has presented
  the first", so that a view that presents nothing is given one generation). Built (commit
  `f02c5f6`), measured, and taken out again. It was aimed at "a view that presents nothing
  keeps every byte uploaded to it", read from a soak that READ BACK once per rebuild — and
  the growth belonged to the readbacks. Without them the same dark view, with no pacing at
  all, grows by 1.5 MB per rebuild (the cost of replacing 98 QML Models, which a held pass
  only postpones), and nothing is uploaded. What the rule added was a way to get stuck: a
  pass that waits for a frame which nothing asks for. Decision 17 is what the measurement
  supports.
- **A pair of hooks of the main window around every document path** (this story's first
  delivery: "before the scene is cleared" / "after the new document is in"). Two mechanisms
  for one fact, and the "before" hook ran before a load could fail (decision 16). The scene
  already says when a document is replaced, and says it only when it is.
- **Keeping the start marker in the settings store.** The marker must be on disk before the
  engine is imported and must survive a process that dies without flushing anything; it is a
  fact about a process (it carries a pid), and it belongs where support looks — beside
  `app.log` and `crash.log`. A registry value is none of these.
- **Falling back to software automatically, within the session.** A device that could not be
  created is reported by Qt in good order (`sceneGraphError`), and a second host built at once
  on the software adapter would be a second engine in a session that was promised one. A dead
  PROCESS cannot fall back at all. Both lead to the same place: the next start, and a choice
  the user can undo.
- **Disconnecting a clock subscriber on its own `destroyed` signal.** Built first; it crashed
  the suite with an access violation — the cyclic collector clears a Python callable connected
  to `destroyed` while Qt still owns the object, and Qt then calls what is left (PF-E3D-07, item 1 of archive/05-l1-3-workspace.md).
- **Releasing the engine's caches on every pass, on a timer, or never.** Every pass: 2 to 10 ms
  per edit plus a frame that rebuilds what was dropped. A timer: wake-ups while idle, and no
  relation to what was destroyed. Never: 19 MB per rebuild of the small bench plan and 65 of
  the large (measured), and a date animation that keeps hundreds of megabytes per minute.

## Consequences

- **For L1.4 (looks, sky):** subscribe with `connect_qobject`; a look is applied through the host
  (`set_look`), never through the pipeline. Whatever animates `windTime` makes frames differ from
  one another — the soak's "the frame after the loop is the frame before it" check and the
  camera rule's readbacks assume a still scene and must pin the wind clock to 0.
- **For L1.5 (ground bake):** `Scene3DController.set_ground_stage(stage)` is the seam; the stage
  runs on the GUI thread inside the pass and is contained when it raises (the bare rectangle is
  sent). A bake that replaces a texture per pass destroys no Model and so does not count as
  retired; if it creates and destroys engine objects of its own, they need the same release.
- **For every writer of plan content:** a change that goes round the command stack, the item
  hook and the scene's other chokepoints calls `CanvasScene.note_plan_changed()` (or
  `garden_item.note_plan_changed(item.scene())`) — and `item.update()` if the canvas shows it.
  Forgetting it is not silent: the net applies it after 400 ms and counts it.
- **For L1.8 (selection, walk):** `Workspace.clear_selection_hidden_by_3d_mode` is yours to
  remove or replace once the selection is shown in 3D (decision 2) — removed, see the L1.8
  addendum. `OrbitInput` passes Escape and unknown keys on;
  `Workspace.select_item(id)` is how the problems list selects on the canvas; a click on the 3D
  view is `try: host.pick(...) except HostStateError` — never `wait_ready()` (the workspace calls
  it nowhere); the info card goes beside or below the view.
- **The workspace needs three things of the host beyond the engine story's contract:**
  `Quick3DHost(prefer_software=…)`, `install_event_filter(watcher)` and
  `release_cached_resources()` (with the `cache_releases` counter).
- **How the workspace is measured follows from decision 17.** A readback is the measuring
  device of the latency and picture scenarios (edit → finished readback; the camera rule;
  WebEngine beside 3D) and costs memory of its own, so the memory soak takes none inside its
  measured loop — one frame before and one after, which must be equal — and is judged
  twice: with the view presenting and with its frames withheld (`frames="withheld"`: the
  engine story's no-paint filter on the view). The gate's children run with Qt's
  `QT_D3D_NO_VBLANK_THREAD=1` by default (`run_gate(timer_paced=True)`): on Windows update
  requests come from a display-vblank thread, with the display asleep a visible window
  presents its first frame and no more, and no scenario may depend on whether the dev box's
  display is awake. The three close gates run once more as the product starts — paced by the
  display (`timer_paced=False`) — which proves less than it seems: on a sleeping display such
  a view presents one frame, so "close with 3D visible" there is not a view presenting frame
  after frame while it closes. That case stays on the owner's checklist.
- **Wall-clock gates carry the `perf` marker** (ADR-058): the strict repaint gate and the
  preview-move cost ratio (default tier: their load-proof half — no repaint starts a pass of
  its own, the net finds nothing), and G2 / G11 of the render tier, whose whole file is run
  with `-m "perf or not perf" -n 0`.
- **The ground bake (L1.5) plugs in at two places and is not wired here.** Where the pass hands
  a ground to the engine: `Scene3DController.__init__` builds `SceneSync(sink, registry)` — the
  bake's `ground_baker=` goes there — and `_pass_records` passes `ground=` from `_ground()`
  (`set_ground_stage` if a stage function is preferred). Where its problems join the list:
  `problems_dialog.problems_of(skipped, failures)` and `Scene3DController._set_problems` /
  `problem_count` are the one path from "something is missing in 3D" to the count in the
  strip — `GroundBaker.capped`, `.failures` and `sync.ground_failure` become a third source
  there, with their own reason codes in `View3DProblemsDialog.reason_text`. **The pass is
  re-runnable while a bake has work left**: `mark_dirty()` — also from inside the stage, or
  from a slot on `applied` — asks for another pass in the next turn of the event loop
  (pinned with a ground made in four slices), at the price of one snapshot per pass (3.6 ms
  on the small bench plan, 15 on the large). Nothing here builds on one pass painting the
  whole ground; the "Building the 3D view…" notice, though, goes with the FIRST pass.
- **Known limits, stated.** The Keyboard Shortcuts dialog does not list Alt+1 / 2 / 3 while the
  workspace is behind its switch (L1.9). Edit latency is measured to a finished READBACK; the
  time to photons is not measured. The real map picker (it needs the network and a key) is on
  the manual checklist; the automated check uses its engine on a local page. A change of the
  device pixel ratio in mid-session, and OS display scaling, are unmeasured (manual checklist).
  With the release in place, dedicated GPU memory rises once, by about 90 MB over the first
  releases (289 → 378 MB), and is flat after; committed memory rises with it once, by about
  100 MB (ADR-048 addendum "L1.3"). The workspace's render tier is not part of CI's render
  job: it was measured on the dev box only (GPU, and the soak on WARP by hand).
- **A residual remains: 15 to 20 kB per destroyed Model** (2 MB per rebuild of the small bench
  plan, 6.4 of the large, linear over 60 rebuilds). It is not graphics state — the same
  rebuilds in a view that draws nothing leave 1.5 MB each — and its floor is Qt's own cost of
  creating and destroying a QML object (3.4 kB for a bare `Model` with a material, measured
  without product code); the rest is not located. It is inside the gate and small for
  editing; it is NOT small for a story that replaces many Models per tick (date playback) —
  ADR-048 addendum "L1.3" has the numbers and two ways out.
- The builder-failure record of `core/scene3d/sync.py` and the record layer's `record_failed`
  record still attach the exception at ERROR (they are the scene contract's, and pinned by its
  tests): decision 13's "one line" holds for this story's five modules.

## Validation

Default tier (no GPU; the engine replaced at the seam):

- `tests/unit/test_scene3d_camera.py` (62) — pose, clamps, framing, the exact spring; the module
  is standard library only.
- `tests/unit/test_sim_clock_subscription.py` (23), `tests/unit/test_view3d_init_guard.py` (44 —
  every transition in a temp directory; the default folder under pytest is inside the test
  root), `tests/unit/test_plain_text.py` (71), `tests/unit/test_view3d_workspace_i18n.py` (40),
  `tests/unit/test_view3d_workspace_packaging.py` (4).
- `tests/ui/test_view3d_orbit_input.py` (21), `tests/ui/test_view3d_host_seams.py` (7).
- `tests/integration/test_view3d_sync_controller.py` (39) — through the real `scene.changed`,
  `stack_changed` and clock channels: **G4** (28 hidden edits: 0 snapshots, 0 sink calls; one
  catch-up pass equal to a from-scratch apply), **G9** (time → light only; date → the dated
  plants and nothing else; a destroyed subscriber is never called), the ground seam (the
  stage sees both snapshots; a stage that raises is contained; a ground made in four slices
  asks for its next pass from inside the pass and then stops asking).
- `tests/integration/test_view3d_workspace_widget.py` (44) — modes, the kept host, **G3** (the
  pose compared exactly around each of 100 edits of every kind, a date and a time change; a
  document change frames once), **G6** (the marker and its notices), the notice painted
  before the first snapshot, the release thresholds, hostile names — and decision 17: a
  stand-in host that records `grab` / `wait_ready` / `pick` / `project` sees none of them
  through passes, polls, the camera's timer, a resize, the splitter, a release, mode
  switches and a document change; a scan finds no such call in the five modules (and finds
  one in the offscreen driver, its control).
- `tests/integration/test_plan_revision.py` — the scene's plan revision: every chokepoint
  moves it (an edit matrix), no repaint does, Qt's polish of a new item is not a second edit, a
  census pins THE hook in every item class's `itemChange` and in every geometry handle's mouse
  move. `tests/integration/test_view3d_plan_revision.py` — in the real window with a recording
  sink: the gates (five activities; default tier: no repaint starts a pass of its own; `perf`:
  0 snapshots while it happens, ≤ 1 after the quiet time), the announcement matrix (31 edit
  paths, `unannounced_changes == 0`), the container's height and material through the real
  Properties panel (by an ANNOUNCED pass), the net applying and counting a write nobody
  announced, and the preview-move cost ratio (`perf`).
- `tests/integration/test_view3d_workspace.py` (22) — the §8.10 workflow through a real
  `GardenPlannerApp`; **G1** in two fresh processes (without the switch: no engine import and
  the canvas view's pixels identical to the build with it in Plan mode); what **G10** leaves
  to this story — #428 itself is master's fix and master's tests
  (`tests/integration/test_sun_document_lifecycle.py`): a replaced document reaches the
  workspace through the scene's signal alone (one emission, one slot call, the camera framed
  once, on four ways of replacing it), and an open that fails on any of three paths leaves
  the view, the camera, the per-plan memories and the hours-of-sun map as they were.
- `tests/integration/test_workspace_gate.py` (11) — the gate's own safety: `main()` on a plan
  builds every store on the throw-away key; a decoy organisation is refused with exit code 97.

Render tier (`OGP_RENDER3D=1`), `tests/integration/test_view3d_workspace_render.py` (24) — the
app's own `main()` in a child, on Direct3D 11 (RTX 4070), 2026-10-12; the numbers of the tier's
run on the final code unless a cell says "by hand" (the same scenario started from a script):

| Gate | Measured | Bound |
|---|---|---|
| G2 edit → finished readback, `bench_small`, Split at 1600 × 900, 120 edits of seven kinds | p50 14.8 / **p95 19.7** / max 52.4 ms (edit 0.9, wait 0.9, snapshot 3.6, apply 0.4, readback 8.6 at the median; an earlier run of the tier: 15.2 / 20.6 / 43.4) | p95 ≤ 50 ms |
| the same on `bench_large` (424 records) | p50 31.3 / p95 71.8 / max 105 ms (snapshot 13.6 ms at the median, 21.4 at p95; wait p95 39 ms; an earlier run: 29.9 / 80.3 / 150) | reported |
| the same on the maximised window (5120 × 1369, 3D pane 2334 × 1203), `bench_small`, by hand | p50 18.5 / p95 29.2 / max 51.2 ms (the readback alone 12.9 ms at the median) | reported |
| G3 twin: 100 edits of nine kinds on the real host | the engine's camera was set 0 times; a new document set it once | exact |
| G5 never / visible / hidden | exit 0, 0 Qt warnings, no ERROR in `app.log`, nothing of Qt Quick imported before 3D is asked for | — |
| G5 in the frozen build (`installer/workspace_gate.spec`: the product recipe plus the gate's runtime hook; PyInstaller 6.18, Python 3.12) | the same three: exit 0, 0 Qt warnings, 98 parts drawn on the GPU; every store the exe built is the throw-away one. The product exe from the same tree: the 8-second smoke stays up, `--selftest` exit 0 in 4.2 s | — |
| G6 twin: died → next start → try hardware → next start | compatibility mode on "Microsoft Basic Render Driver" by Qt's own log, then "NVIDIA GeForce RTX 4070" again | — |
| G7 soak, 20 rebuilds, the view PRESENTING, no readback inside the measured loop | **1.56 MB / rebuild** (rebuilds 11–20; 2.00 in a run by hand), growth +121 MB, 20 releases, the frame after the loop equal to the frame before it | < 10 |
| G7 the same with the view's frames WITHHELD (paint events eaten; 0 frames presented) | **1.32 MB / rebuild** (1.48 by hand), growth +36 MB, 20 releases; dedicated GPU memory did not move; the view presents again → the same frame | < 10 |
| G7 rebuild off / positive control (+25 MB per rebuild) / release out of reach | 0.33 / 26.8 (fails, as it must) / 18.8 (by hand: 0.01 / 27.3 / 19.3, and 1.54 without the release with frames withheld) | < 10 / ≥ 10 / reported |
| G7 dedicated GPU memory (DXGI, this process), presenting | 289 → 346 → 362 → 378 MB over the first releases, then flat (slope 0.0) | < 10 |
| G7 elsewhere, with the release (one run each, by hand) | the large plan (421 parts): 6.38 MB / rebuild (65.5 without the release); WARP: 3.32 (20.1 without), 1.23 with frames withheld | < 10 |
| G7 over 60 rebuilds (by hand); and with the release inside every pass (20 rebuilds) | 1.78 MB / rebuild over rebuilds 31–60 (60 releases, the frame after equal to the frame before); 1.88 (1.82 by hand) | < 10 |
| What a readback per rebuild adds — why decision 17 (reported, never judged) | frames withheld: 8.63 MB / rebuild with the release (8.48 by hand), 26.0 without (WARP: 6.20 with); presenting, by hand: 3.85 and 16.4 | — |
| G8 a Qt WebEngine page before and after the 3D host exists | painted both times (`#1e90ff` at its centre); 138 distinct colours in the 3D frame beside it | — |
| G11 pan step, Split against Plan at the same canvas size (874 × 967) | 1.04 (the fastest tenth: 1.04) | ≤ 1.3 |

Hand mutation (one text mutant at a time, the tests that should notice run, the tree restored;
a scratch tool, point-in-time, not a gate): on the final code **every mutant killed** in 18
sets — controller 14, workspace 19, plain text in the dialog 3 and in the workspace 5, the
plain-text helper 14, log lines 5 + 2 + 2, the application's wiring 11, the switch 2, retired
counts and plan memories 11, the release 9, the notice 7, the host seam 3, workspace paths
that moved 6, a pass asked for from inside the pass 1 (114 mutants), and six mutants that ADD
a frame-taking call to a steady path — a readback in the health poll, a `wait_ready()` there,
a readback after every pass, a `project()` per camera step, a readback after a release, a
`pick()` on a moved splitter — each killed by the recording stand-in host ALONE and by the
source scan ALONE. Two findings of the tool itself are worth
keeping: every mutant of `application.py` was once "killed" by the same unrelated test, which
was failing on the unmutated tree (a mutation verdict is only worth something on a green
tree — run the story's tests first); and one set listed too few test files and reported a
survivor that a test in the missing file kills.

## ADR-060 addendum: selection, info card and walk (L1.8)

**Status**: Accepted (2026-10-12, #385 story L1.8). Behind `OGP_QUICK3D=1`, like the workspace
(until L1.9 made it the default).

### Context

The workspace shows the plan in 3D and nothing connects the two views: what is selected on the
plan is not marked in 3D, a click in 3D does nothing, and the garden can only be looked at from
outside. Six facts shaped what was built:

- **Selection is in none of a record's three signatures** (ADR-059). Whatever marks a selected
  item must not rebuild, re-pose or re-tint its model.
- **A destroyed Model is never free** (15 to 20 kB stay, decision 16 above). A marker made of
  Models that come and go with the selection is retired work on every click.
- **`pick()` takes a frame from the live view** (decision 17): on a click, once — never on a
  move, a timer or a resize.
- **The view is a native window.** Nothing can be drawn over it; whatever is shown beside it
  takes room from it — and a view that changes its size re-scales its picture.
- **The built world is thicker than the plan's strokes.** A wall drawn with a 5 cm line is built
  30 cm thick with a 38 cm coping (ADR-059 addendum L1.6). Whoever reasons from the footprint —
  an outline to mark, an obstacle to stop at — reasons about something the user does not see.
- **The canvas has selection rules, and none of them is written down.** What a click through a
  locked item does, what Shift does, what a click on a group member selects: measured with real
  clicks on the real canvas before anything was decided
  (`tests/integration/test_view3d_selection_bridge.py`).

### Decision

**S1. One selection: the canvas scene's.** 3D keeps none. A click in the 3D view becomes a
canvas selection — through `QGraphicsItem.setSelected` / `clearSelection`, the canvas's own
path, so the property panel, the status bar and the undo stack behave as after a click on the
plan (a selection is no command: the undo stack does not move). The canvas's `selectionChanged`
becomes the ring in 3D and the info card. Selecting by id is ONE path for the whole app,
`ui/canvas/select_by_id.py` (revision of 2026-10-19): which item an id names (`item_with_id`),
what selecting it selects (`click_target`, the outermost group), whether it can be selected
(`is_selectable`, which a locked layer answers) and `select_by_ids` on top. The Diagnostics,
Canopy and Guilds panels (`ObjectNavigator`, which had a resolver and a group rule of its own),
the plant search, the 3D "Not Shown in 3D" list (`Workspace.select_item(item_id, *,
toggle=False, center=True)`) and a click in 3D (`ui/view3d/selection_bridge.py`, which adds
only the ray's rule) all go through it, so a row of a panel and a click in 3D cannot disagree
about an id. The panels' behaviour is unchanged (their tests pass as they were).

**S2. The rules are the canvas's, as measured.**

| A click … | on the canvas (measured) | in 3D |
|---|---|---|
| on an item | selects it alone | the same |
| with Ctrl, or with Shift | toggles it; the rest stays | the same |
| on nothing (the ground, the sky) | clears — with any modifier | the same |
| on an item of a LOCKED layer | the item is transparent: what lies behind it is selected; with nothing behind, a plain or Shift click clears and a CTRL click keeps the selection (Qt's Ctrl rule) | the same, along the ray (`PickHit.behind`) — the bridge is told which modifier was held, not only "toggle" (fix round 1) |
| on an item of a HIDDEN layer | cannot happen: it is not drawn | cannot happen: it has no record |
| on a member of a group | selects the outermost group | the same; the ring runs round every member |
| with Shift THROUGH a locked item | acts as a PLAIN click: the selection is replaced | toggles, as Shift does everywhere else |

The last row is the one deliberate difference: the canvas's behaviour there is a defect of the
select tool (its Shift branch looks at the top item only), reported as a follow-up, and 3D does
not copy it. A flat item — a lawn, a path: no height, no solid — cannot be selected from 3D: it
has no mesh to hit. Selecting it on the plan still rings it.

**S3. A click is a press and a release of the left button within 4 px and 0.4 s**
(`orbit_input.CLICK_SLOP_PX`, `CLICK_MAX_S`); inside that slop the press does not pan. Anything
else is a drag and never selects. `OrbitInput._release` is the ONE place of the workspace's
modules that calls `host.pick` (the scan test allows exactly that call, by module, function and
name). `HostStateError` — the host cannot answer now — is no click: nothing changes and nothing is
said. Any other exception is one ERROR line. `picked` carries the click's modifiers (fix round 1:
Ctrl and Shift differ on a locked item). In walk mode a left drag turns the view only once it
leaves the same slop, and a drag that turned cancels the click (`WalkMode.turned` →
`OrbitInput.cancel_click`): a look never selects.

**S4. `pick()` answers with the whole chain.** `PickHit.behind` holds what the ray meets after
the first hit, nearest first (`View3D.pickAll`). A second host call (`pick_all`) would have been
a second frame-taking call to allow in the scan and to keep off the steady paths; a field costs
neither.

**S5. The seam is the sink: `EngineSink.set_selection(Selection)`** — the eleventh method, inside
`begin` / `commit` like every other. Not a method of the host, for three reasons: a selected item
that moves must take its ring along in the move's own transaction (one frame, never the model
here and the ring there); recovery must restore it (`SceneSync.reset()` forgets what was sent
and keeps what is asked for); and `RecordingSink` logs it, so "what did a selection change tell
the engine" is a default-tier question with an exact answer. A `Selection` is the sorted ids
that have a record plus ONE merged mesh in the scene frame, built by the Qt-free
`core/scene3d/selection.py` from the records' own regions — every outer ring and every hole —
at the item's standing base plus 1 cm (a plant on a raised bed: at the bed's soil).

**S6. The sync remembers a wish and sends a difference.** `SceneSync.select(ids)` calls nothing.
The ring goes out with the next `apply` — in its transaction — or alone (`send_selection`). It
is rebuilt only when the wish changed or the diff touches a selected item's outline or pose (a
recolour does not), and sent only when it then differs from the ring the sink has. While 3D is
hidden a selection change is a flag (`Scene3DController.set_selection`).

**S7. Engine side: one Model, one geometry, for the life of the host.** `Garden.qml` declares
ONE static ring Model; the first selection creates ONE `ReloadableGeometry` for it; every later
selection re-loads that geometry in place, and an empty selection hides the Model.
`host.clear()` hides it; nothing destroys it. **A selection change creates 0 engine objects and
destroys 0** (measured: 120 changes in the real workspace — 120 loads, one geometry, the count
of Models and of model-geometry uploads unchanged). Nothing counts towards `TickReport.retired`.

**S8. The ring is a band of 3 px on screen, in the canvas's selection blue, drawn in front.**
Constant width on screen (a vertex shader moves each outline point outward by band widths —
`ring.vert`), so it is a hair neither with the whole garden framed nor a plank in walk mode;
outside the outline; unlit, casting no shadow, not pickable; the colour is the select tool's
`#0078d7`, handed over in linear light. **In front of everything** — its depth is pulled to a
hundredth of its distance from the near plane, wherever the backend has that plane
(`mix(NEAR_CLIP_VALUE * POSITION.w, POSITION.z, 0.01)`) — because of the fifth fact above:
measured from above, the depth-tested ring of a wall shows 3.6 % of its outline; it lies
inside the masonry.

**S9a. 3D mode keeps the selection** (fix round 1, after the workspace's plan revision landed).
The workspace's stopgap — `clear_selection_hidden_by_3d_mode`, which cleared the canvas
selection on entering 3D-only mode so that Delete could not act on what nobody saw — is
REMOVED, not replaced: what is selected is shown in 3D (the ring; the card, which also names
an item 3D does not show and counts several). The problems list still switches 3D-only mode to
Split before it selects: an item of that list is one 3D does not show, so no ring can mark it.

**S9. The info card has a place of ONE height.** `ui/view3d/info_card.py`: `View3DInfoCard` in a
`View3DCardSlot` below the view. The card is shown while exactly one item is selected and the
3D pane is visible; the slot is there with the engine view whether or not a card is, and holds
a line of hint text otherwise. Every number on the card is read from the item's APPLIED record
(`height_cm`, `params["radius_cm"]`, its regions) — the numbers the model was built from, no
second computation; an item without a model shows why, in the words of the "Not Shown in 3D"
list. Every label is `Qt.TextFormat.PlainText`, plan text goes through `clip_line`, no tooltip
carries plan text, and no label asks for the width of its text — a plan cannot widen or
heighten the pane. One action: "Show in Plan" (from 3D-only mode it switches to Split).

**S10. Walking is a Qt-free core** (`core/scene3d/walk.py`: standard library and numpy, plain
frozen data, pure functions) and a thin input filter (`ui/view3d/walk_mode.py`).

- *The walker*: a vertical cylinder of radius 22.5 cm (shoulders 45 cm); eye heights 165 / 150 /
  110 cm; 140 cm/s, twice that with Shift; no head bob, no smoothing — reduced motion has
  nothing to switch off.
- *What blocks*: every record of a built-world kind (`BUILT_WORLD_KINDS`) or a greenhouse whose
  shown top is more than a step of 25 cm above the ground — over its footprint (outer rings
  minus holes: a courtyard is free ground) AND over the plan-view edges of the mesh the view
  shows for it between 25 cm and a headroom of 200 cm. The second half is what makes a wall
  stop the walker at the masonry and not at the stroke. Plants other than hedges, furniture and
  flat items are walked through or over in v0. The plan rectangle is the world's edge.
- *Motion*: fixed ticks of 1/120 s (2.3 cm at a run: a tenth of the radius — no tunnelling), the
  time not yet ticked carried and shown one resolved partial step ahead; each tick is "move,
  then be pushed out along the normal of what the circle entered", which is sliding; a
  position that is still not free after 8 pushes refuses the tick, so a narrow gap stops the
  walker and never traps it. A uniform grid over the outline segments finds the candidates.
- *The camera*: `Workspace._apply_camera` stays the one place that tells the host where the
  camera is — it asks walk mode while walking. Field of view 60°, the engine's near plane
  5 cm: the farthest corner of the near rectangle is 6.94 cm from the eye at 4:3 and under the
  walker's radius up to an aspect of 7:1, so a walker pressed against a solid cannot look
  through it.
- *Entering and leaving*: the "Walk" toggle in the pane's strip puts the walker where the orbit
  camera looks (the nearest free spot, if that is inside a solid), facing the way it looks.
  Walk mode never touches the orbit camera, the plan or the undo stack: Escape, the toggle,
  "Reset 3D View" and a new document leave it, and the orbit pose is the one the user had.
  W A S D / the arrow keys move, a drag looks (pitch within ±80°), a click still selects, the
  wheel does nothing. A hidden view lets go of every key and keeps the walker; an edit while
  walking rebuilds the walker's world (from the parts the sink holds — nothing is built twice —
  and only when a solid moved) and moves it to free ground if something was put where it stands.
- *The keyboard* (fix round 1, review P0 / P1-2). **While walking, the walk keys belong to the
  walker; every key with Ctrl or Alt, and every other key, is passed on.** The walk keys are
  `walk_mode.WALKER_KEYS` — W A S D, the arrows, Shift, Escape — stated once. They are claimed
  at `ShortcutOverride`, which Qt sends to the view's window BEFORE it looks for a shortcut
  (measured on the real main window: the override reaches the `QQuickView` first, then its
  active focus item; accepted at the view's filter, no shortcut fires). Without that the main
  window's Snap to Grid (`S`) fired and the walker never saw S. "Walk" gives the 3D view the
  keyboard (`Quick3DHost.focus`: `requestActivate`; measured: the focus window is the view and
  its container is the focus widget) — else W picked the Wall tool on the plan and Escape
  went to the canvas — and leaving gives it back to where it was, while the view still has it
  (`Quick3DHost.has_focus`).

### Alternatives considered (rejected)

- **A highlight by tinting or scaling the selected model.** Selection would enter the material
  signature — every selection change a material update on every part, and a "selected" look
  that depends on the item's own colour.
- **A ring Model per selected item (a pool).** More objects for the same picture; one merged
  mesh in one geometry needs no pool and no policy for its size.
- **A world-space ring width.** 3 cm is invisible with the garden framed and 3 cm is a plank at
  eye height; the canvas's own selection outline is a pen of constant width.
- **A depth-tested ring.** Measured: inside the masonry of a wall (3.6 % visible).
- **Pulling the ring forward by scaling clip z** (`POSITION.z *= 0.01`) — the first version.
  Right where clip z runs 0..1 (Direct3D); where it runs −1..1 (OpenGL) it moves the ring to
  the middle of the depth range, behind the ground of the orthographic truth view: 0 ring
  pixels in every top-down frame. Found by one run with `QSG_RHI_BACKEND=opengl`; the
  perspective frame had hidden it.
- **A card that comes and goes with the selection** — the first version. Measured on the real
  engine: 152 px taken from the view each time, the picture re-scaled under the pointer, and
  a Ctrl+click on the neighbour of the item just selected cleared the selection. Also a new
  swapchain per selection, and a view that answers no click while it is between two sizes.
- **A card over the view.** Not possible over a native window (decision 2 above).
- **Colliding with footprints alone.** The walker would stand 12.5 cm inside a wall's masonry.
- **Stepping per frame.** The path would depend on the frame rate, and a slow frame could step
  over a thin wall. (Pinned: the same inputs at 30 and 144 Hz end within a micrometre.)
- **Plants as obstacles in v0.** A canopy circle is not where a trunk is; stopping at it would
  fence off half of a planted bed. Out of scope by the story; stated on the manual checklist.

### Consequences

- **`EngineSink` has eleven methods.** An adapter that does not implement `set_selection` is not
  a sink; `Quick3DSink` and `RecordingSink` do, and `expected_state()` includes the selection.
- **The 3D view is 80 to 94 px lower** (the slot: a title line and three lines of facts in the
  desktop's font — 94 px in Segoe UI 9 pt) — permanently, card or no card. That is the price
  of a view that never jumps.
- **`host.pick()` calls `pickAll`**: one probe frame as before, and it returns more.
- **The frozen `--selftest` selects one swatch** and judges the ring's band: the ring's shaders
  are compiled only when something is selected, and a release must not ship one that does
  not compile.
- **For L1.4 (looks)**: the ring's colour goes through the exposure and the tone curve (the
  canvas blue arrives as rgb(0, 142, 226), hue 202° against 206°); a look that changes the
  exposure changes its brightness. The ring writes a near depth: a depth-reading post effect
  will see it.
- **For L1.5 (ground)**: ground tiles are not pickable — a click on the ground is "nothing" and
  clears the selection.
- **Known limits, stated.** Flat items cannot be selected from 3D. Plants, furniture and
  pergolas do not stop the walker; there are no stairs, slopes or doors, and no pointer
  capture. A selection change costs NO snapshot, also with the canvas visible — since the
  workspace's plan revision (before it: 6 snapshots for 4 selection changes, the canvas's
  repaints read as edits; after it: 0, the repaints go to the quiet-time net, which finds
  nothing — `test_a_canvas_selection_in_split_takes_no_snapshot`, a strict `xfail` until the
  plan revision landed). The ring is drawn in front of
  everything, the item's own model included: it reads as an outline seen through the model.
  A device pixel ratio other than 1 was not exercised through the real window.
- **One open doubt.** In the first WARP run of the timing loop one selection change of 120 did
  not reach the engine within two seconds, and the ring was loaded 121 times instead of 120.
  It did not happen again in 3,240 changes on WARP and 480 on the GPU; the cause is not known
  (PF-E3D-08, item 11). The driver records every pass of a change that misses.

### Validation

Default tier (no GPU): `tests/unit/test_scene3d_walk.py`, `test_scene3d_pick_oracle.py`,
`test_scene3d_selection.py`, `test_quick3d_selection_ring.py`; `tests/ui/test_view3d_click.py`,
`test_view3d_walk_mode.py`, `test_view3d_info_card.py`, `test_view3d_selection_ring_host.py`;
`tests/integration/test_view3d_selection_bridge.py` (the canvas's rules, with real clicks),
`test_view3d_selection_workspace.py` (also the one select-by-id path: a panel row and a 3D list
row give the same selection, and a structure scan), `test_view3d_selection_controller.py`,
`test_view3d_walk_bench.py`, `test_view3d_selection_walk.py` (the §8.10 workflow through a real
`GardenPlannerApp`); `tests/perf/test_view3d_selection_walk_budget.py`.

Render tier (`OGP_RENDER3D=1`), `tests/integration/test_view3d_selection_render.py`, on
Direct3D 11 — RTX 4070 and WARP ("Microsoft Basic Render Driver"), 2026-10-12:

| Gate | Measured (GPU; WARP where it differs) | Bound |
|---|---|---|
| G1 twenty seeded picks against the CPU oracle, `bench_small` and the edge-case plan | 20 / 20 and 20 / 20; all 400 seeded positions: 360 of 360 and 362 of 362 off the silhouette edges, 36 of 40 and 38 of 38 on one; a plant on a bed, a polygon's hole, the sky: as the oracle says | 20 / 20 |
| what lies behind a hit (`PickHit.behind`) | 349 of 349 and 362 of 362 whole chains equal to the oracle's | exact |
| G2 sixty real clicks on the `QQuickView` of the real workspace | 54 of 54 off the edges select on the canvas what the ray meets (11 items of 8 kinds, 39 on nothing); plain / Ctrl / Ctrl / Shift / plain: {a}, {a, b}, {a}, {a, b}, {a} | exact |
| G4 the ring from above: a turned rectangle, a polygon with a hole, a circle, a plant on a bed | every ring pixel within 3.82 / 3.54 / 2.97 / 2.88 px of our projection of the outline; the outline covered 100 % | ≤ 5.24 px; ≥ 98 % |
| G4 the height of a plant's ring | 1.64 px (mean) from the outline at the bed's soil height, 16.77 px from the one on the ground | ≤ 3 px; ≥ 4 × |
| the ring depth-tested (the control of S8) | 3.6 % of a wall's outline visible (48 px of 1,548) | — |
| the ring on the OpenGL backend | the outline covered 100 %; with clip z plainly scaled (the first version): 0 px | ≥ 98 % |
| a selection change in the engine | 0 Models, 0 model uploads, one ring geometry for 120 loads | 0 |
| G7 walk mode with real keys | W held 0.70 s: 139.9 cm/s, straight ahead; a drag of 60 px: 18°, nothing selected; Escape: the engine's camera equal to the last digit, the frame equal (mean difference 0.02 of 255) | — |
| standing against a wall (S10) | 288 frames at the wall and in the inside corner: 0 marker pixels; the control 2 cm from the masonry: 114,560 | 0 |
| G8 a selection change → the engine has its ring, 120 changes, no readback in the loop | median 11.5, p95 17.7, max 22.9 ms (with the display asleep and no frame presented meanwhile: 6.8 / 9.9 / 10.7); WARP over 28 runs: median 11 to 13, p95 15 to 30, max 22 to 51 | p95 ≤ 50 ms |

Re-run on the merged tree (the integration branch with master v1.30.13), 2026-10-19, on the GPU
and on WARP: every pick, chain, ring, depth, look-through and click number of the table is
unchanged (the plant's ring at soil height on WARP: 584 px, 16.75 px from the ground's outline);
G8 to the real engine, GPU median 15.5, p95 19.3, max 21.1 ms, WARP 14.4 / 24.3 / 50.0 ms; G7 W
held 0.71 s: 138.1 cm/s on the GPU, 139.9 cm/s on WARP.

Fix round 1 (review 1, 2026-10-19): the walker's keys in the FULL main window, real engine
(`test_view3d_selection_render.py::test_in_the_full_main_window_every_walkers_key_walks_and_no_shortcut_fires`)
and with a stand-in engine whose view is a real `QWindow`, keys delivered by `QTest` to the
window that has the keyboard (`test_view3d_selection_walk.py`): of the main window's 12
single-key shortcuts — derived from the live app — the one on a walker's key is Snap to Grid
(S); all eight movement keys walk and none fires; the control (not walking, S into the 3D view)
toggles Snap to Grid. Ctrl on a locked item with nothing behind: the canvas keeps
`['free']`, 3D the same (`test_view3d_selection_bridge.py`, two new measured rows). The
self-test's ring share through `run_selftest`: 1.00 on the GPU and 1.00 on WARP.

Default-tier numbers: G5 — a 20 cm gap blocks and a 60 cm gate passes; diagonally into a wall
the walker keeps 100 % of its tangential speed; an inside corner does not trap; the same
inputs at 30 and 144 Hz end within 10⁻⁶ cm; 20,000 seeded steps on each bench plan (841 m and
945 m walked, 5,469 and 3,664 of them in contact) never leave free ground by a brute-force
judge that uses no index. G8 — a walk tick's collision resolve on the large plan (32,548
outline segments): 0.02 to 0.03 ms at the median, 0.03 to 0.04 in contact (bound 0.5); a
selection change to the end of its pass on the recording sink: 10.3 ms at the median, 14.9 at
p95 (bound 50).

Hand mutation of the walk core (six text mutants, each killed by the default tier): no
push-out; one step per frame; footprints only; no sliding; a walker 5 cm thinner; the carried
time thrown away.

## ADR-060 addendum: the default and the removal (L1.9 / L1.10)

**Status**: Accepted (2026-10-19, #385 stories L1.9 and L1.10); shipped in v1.30.14 (PR #484)
with #532 open, the owner's decision at the L1 pull request (D5). Two commit groups: every L1.9 commit (the flip;
the tree after them still holds the Qt 3D code, reachable from no menu) strictly before every
L1.10 commit (the removal), so that shipping the flip without the removal is one revert.

### Context

L1.3 built the workspace behind `OGP_QUICK3D=1`, and L1.4 – L1.8 filled it: looks and sky, the
built world, plants, selection, the info card and walk mode (L1.5's ground bake, built in parallel,
joined on the integration branch before L1.10). The product still opened the Qt 3D window of US-E6 / E7 (ADR-038), which
ADR-048 replaced as a decision. What was left: make the workspace THE 3D view; bound what the
view costs in its steady state before it is the default (L1.4's wind soak, FU-L14-2; a held key
in the date field, #531); show that what FR-SUN-06 / 07 / 08 promised is kept or knowingly
changed; then delete Qt 3D.

### Decision

**D1. One code path, no switch, no escape hatch.** `quick3d_workspace_enabled()` and the
variable are gone; `_setup_central_widget` builds the workspace always. An escape hatch was
considered and rejected: a flag must name a failure the existing net does not cover, and none is
left. The workspace module imports no engine, the engine starts only when the user asks for 3D
(the import scan pins it, G1), the app starts in Plan mode in every session (the mode is not
saved), and a start that fails is caught at every depth (§8.29.9's table: an import that fails →
a message in the pane; a device that cannot be created → a message and compatibility mode next
time; a driver that kills the process → the start marker → compatibility mode; a death in
compatibility mode too → 3D switched off with the way back on screen). The one case the marker
does not see — a crash AFTER the first frame — leaves the next session in Plan mode with
"Use Compatibility Mode Next Time" in the strip; an environment variable would not reach a user
any sooner than that button.

**D2. View → Sun & 3D → "3D View" shows the 3D pane.** From Plan mode it switches to Split — the
plan stays on screen, and the 3D view appears beside it, where the old window used to open; in 3D
or Split it changes nothing. Its place, icon and (absent) shortcut are kept; its text lost the
ellipsis (it opens no window) and its status tip says "beside the plan" (en / de / es). The mode
actions stay as they were (Alt+1 / 2 / 3). Help → Keyboard Shortcuts lists them, the camera's
mouse and keys, Home, a click that selects and walk mode's keys. Preferences → 3D View is shown in
every window (`PreferencesDialog` lost its `show_view3d` parameter: one path).

**D3. Date playback is throttled** (#531, `sync_controller.DATE_REGROW_MIN_MS` = 500): a date
regrows the dated plants at once when the last regrowth for a date was at least 500 ms ago,
otherwise ONE trailing regrowth is booked for the end of the interval and runs only if the
clock's date is not the one the last records pass read. The light follows every step. Rejected:
reusing the Models (a geometry re-loaded in place, as the selection ring does — no destroyed
Model, nothing left behind): it would change the adapter's "one geometry per Model lifetime"
rule for every replace_geometry and its picking, measured nowhere yet; a debounce that regrows
only when the key is released (no growth seen while holding); a rate limit in the toolbar (it
would hold back the 2D shadows too). Measured (60 s, a step every 33 ms, 20 dated trees, RTX 4070): 90 and 97 regrowth passes
(1,800 and 1,940 Models) against 312 and 452 — one per step — without the interval; the view
ended on the last date every time.

**D4. The wind's clock stays a `FrameAnimation`.** The planned fix for FU-L14-2 — the clock as a
C++ `NumberAnimation`, no JavaScript per frame — was built and measured against the unchanged
code in six alternating soaks (§8.29.9): no difference, and the growth L1.4 measured did not
reproduce on either. Reverted. The final render tier the same day read 2.637 MB a minute (bound
2.0): intermittent, not gone — the gate is a non-strict `xfail` citing #534.

**D5. The flip ships with #532 open — the owner's call, made 2026-10-19.** #532 (Qt 6.11's `QSSGBufferManager::clear()`
skips hash entries, so about half of the same-size ground-tile textures leak on every cache
release) is L1.5's known limitation; the flip ships the ground with it. The exposure is measured
by L1.5 (up to ~42 MB per release on a 4096² ground) and, on the default's own path, after the
merge: a held date key on bench_small keeps 41–63 MB of dedicated GPU memory a minute (5–6
releases of 8–10 MB each) with D3's interval, 76–112 without it (§8.29.9 "With the ground"); the
consolidated checklist of the L1 pull request asked the owner to choose. **Decided 2026-10-19:**
the owner accepted the L1 pull request after its manual checklist and chose (a), ship the flip
with #532 open. The six other decisions put to them there were kept as built: the twilight fade
(FR-3D-LOOK-01), the noon horizon's lime band, 4× MSAA at Low (FR-3D-LOOK-07), the flat sky in
compatibility mode, `master`'s rule for a loaded sprite's stated stroke (PF-CAN-21), and the new
view's cost over the old window (§8.29.9) with no lighter default preset.

### Alternatives rejected

- **Keep `OGP_QUICK3D` as an "off" switch** — D1: no failure left that it would cover; a second
  code path to test for nothing.
- **"3D View" opens 3D-only mode** — it would hide the plan the user was editing; the old window
  opened BESIDE the plan, and Split is that.
- **A `NumberAnimation` wind clock** — D4: measured, no difference.

### Consequences

- Every main window carries the workspace widget; nothing of the engine is loaded before 3D is
  asked for.
- The parity of FR-SUN-06 / 07 / 08 is a table of tests and stated differences (§8.29.9); the
  three FRs are rewritten for the new view and point to the FR-3D-* requirements.
- What the default costs is measured against the old view (§8.29.9 "What the default costs").

### Evidence

All on the dev box (Windows 11, RTX 4070 / Direct3D 11; WARP = Direct3D's software adapter), the
product's own `main()` in a child process on a throw-away settings store, 2026-10-19; the full
table, with what it says, is §8.29.9 "What the default costs".

| What | Measured |
|---|---|
| start-up to the first event-loop turn, 3D never opened (median of 5) | 2.20 s; the tree before the flip 2.19 s; 0 engine modules in both |
| first 3D click → first presented frame / first finished readback | small plan 1.10 / 2.29 s (first run of the day 1.88 / 4.49), large 1.81 / 3.25 s; the old window 0.57 s (small) / 0.74 s (large) to a drawn frame on screen |
| edit → finished frame, p95 (2334 × 1105 pane) | small 45.9 ms (bound 50), large 180 ms (no bound) |
| committed / dedicated GPU memory after the first frame | small +550–800 / 312 MB, large +950 / 312 MB; the old window +328 / 45 MB and +696 / 47 MB |
| date playback, 60 s | the interval: 1.5–1.6 regrowth passes a second; without it one per step (312 and 452) |
| the wind soak (FU-L14-2), 6 alternating runs of 4–5 min | 0.46–2.03 MB a minute overall, second-half slopes 0.0–1.51, both clocks; a seventh run (the final render tier) 2.637 — intermittent, #534 |
| after L1.5 joined (the ground on) | first readback small 2.68–2.96 s, large 4.21–4.33 s; GPU memory 332 / 428 MB; edit → frame p95 small 41.5 ms; a held date key keeps 41–63 MB of GPU memory a minute through #532 (76–112 without the interval) |

### L1.10: the removal, and the scars it retires

**D6. Qt 3D leaves the product.** Deleted: the US-E6 / E7 window and its adapter
(`ui/view3d/view3d_window.py`, `qt3d_adapter.py`), the pre-L1.1 scene module
(`core/scene3d/legacy.py`: the Qt 3D record, scene-space extrusion, decals,
`collect_scene3d_records`), the walkthrough helper (`core/walk_camera.py`, replaced in L1.8 by
`core/scene3d/walk.py`), every path of the main window that drove them, the L0 spike with its
flag and its benchmark script, the two wheels (`PyQt6-3D`, `PyQt6-3D-Qt6`) from the manifest,
the lock and the bundle, and `--selftest`'s Qt 3D import block. ADR-048's closing addendum has
the bundle and the lock before and after; `tests/unit/test_no_qt3d_left.py` keeps the code
areas free of the names, and documentation names them only where history is kept (§8.10.13).

Each workaround the old window carried existed because of how Qt 3D hosted its scene; the
workspace's host does not need it:

| Scar in the old view | Why it was there | Why the workspace does without it |
|---|---|---|
| `closeEvent` hid every 3D window before quitting | the viewer was a parentless top-level `Qt3DWindow`; a visible one kept the process alive under `quitOnLastWindowClosed` | the engine's window is a child of the main window (`QWidget.createWindowContainer` in the 3D pane); `Workspace.shutdown()` closes the host while the main window still exists (§6.9, G5: no warning, no ERROR line, from source and frozen) |
| a new window on every open, the old one kept hidden for later | a hidden and re-shown `Qt3DWindow` painted white — Qt 3D never rebuilt its swapchain for the re-exposed surface | ONE host for the session, hidden and shown (L1.3: re-entry 7–53 ms); a hidden pane does no work and catches up once |
| the closed window retired with `deleteLater` only at the NEXT open | deleting it at close raced its live render thread and segfaulted (#230 class) | Models are created and destroyed on the GUI thread through the sink; no Python runs on the render thread (signals from it are queued, §8.29.2) |
| a "3D View Unavailable" dialog around the import | a Qt 3D wheel built for another Qt micro failed to load (#277) and would otherwise have killed the process | `Workspace._start_engine` turns anything the start raises into a message in the pane with "Try Again" (§8.29.9's safety-net table); `--selftest` RENDERS the engine in the frozen artifact |
| the app forwarded the sun to the window (`_apply_sun_to_3d`), with a fixed 50° / 180° sun without a location | the window had no clock of its own | the controller subscribes to the one sim clock (ADR-053) and keeps the same fallback as `NO_LOCATION_SUN` |
| a Refresh button and a rebuild on open | no live sync | live: every change of the plan within one pass (FR-3D-WS) |

**Values that outlive their producer are frozen first.** The production look, sky, fog,
materials, meshes and probe geometry were ported from the spike and drift-guarded against it.
Before the spike was deleted, a scratch tool ran it on the L1.9 tree and wrote everything those
guards compared with into `tests/data/l0_spike_reference.json` (provenance inside the file); the
guards read the file now. A production value that leaves it is a deliberate, documented change,
as before — only the comparison no longer needs the spike's code.

Rejected: keeping the spike as "evidence tooling" (it was the last importer of Qt 3D's era of
the code and a second QML scene to keep compiling — the Beauty Board and the render tier
measure the product itself); deleting the drift guards with the spike (the values they pin are
the L0 measurements the look was accepted on).

## ADR-060 addendum: L1 follow-ups #537, #539, #541, #542

**Status**: Accepted; owner acceptance confirmed, shipped in [v1.30.19](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.19) via [PR #565](https://github.com/cofade/open-garden-planner/pull/565).

Four small follow-ups from the L1.9/L1.10 review, shipped together:

- **#537 - L1.10 leftovers.** The workspace gate no longer passes the retired OGP_QUICK3D switch to its child or names it in the render-tier docstring; the no-reader guard stays. The main window assigns walk.svg to the Walk action so theme switches replay it; the pane button shows text beside the icon. The exact stale-DPR warning is classified as environment, with and without Qt's QTBUG-report suffix. [Qt 6.11.0 processExposeEvent()](https://github.com/qt/qtbase/blob/v6.11.0/src/gui/kernel/qguiapplication.cpp#L3222) corrects the cache before warning and delivering expose; the missing earlier notification's cause remains unproven. Other text/categories and critical reports retain their severity, pinned by tests/unit/test_quick3d_pure.py::TestClassify.
- **#539 - the main window owns show the 3D view.** View -> '3D View' selects Garden Plan first, then switches Plan to Split; existing 3D/Split modes remain. Global Workspace actions also select Garden Plan: Alt+1 shows Plan, Alt+2 shows 3D, Alt+3 shows Split. The integration workflow fires the action from Calendar and real Alt+1/2/3 keys from Seed Inventory.
- **#541 - Home uses Qt's native key translation.** The shortcuts dialog and Reset tooltip obtain the key name through QKeySequence(Qt.Key.Key_Home).toString(NativeText). German Qt translations supply 'Pos1'; the tooltip's surrounding text and {key} placeholder are compiled in all three app catalogs.
- **#542 - the trailing check stamps only a real regrowth.** _regrow_if_the_date_moved stamps _regrown_at only when it calls mark_dirty(). Deterministic controller tests replace only that module's clock, preserving real event-loop waits and performance measurements. Three clock origins pin no-op timestamp preservation, immediate admission through the next date_changed signal, and the real trailing pass. Replaying the old unconditional stamp fails all three cases. A constant 1000-second stamp previously booked a long timer on a young CI VM; a fixed 70-ms wait never proved idle. See PF-TST-25 and the runtime view. No file-format or dependency change.

## ADR-059 addendum: line history restores values; cache bounds contain paint (#524–#526, #471)

The owner selected one type-change rule for both UI surfaces: use the new type's
defaults and clear the old preset. This supersedes the L1.5 expectation that a
Properties type change retains its preset. Undo restores the old type and preset,
including a custom stroke. Existing project files retain their stored presets;
this policy applies only to a new type-change gesture. No file-format bump is needed.

`LineLook` in the existing `core.item_look` module holds copied appearance values.
Both controls use one restore function rather than rebuilding defaults on undo.
Reapplying a preset during restoration was rejected: it overwrites user stroke
changes and makes Properties and context-menu history disagree. Preserving the old
appearance through a type change was considered and not selected by the owner.

The shared style painter now also owns its conservative geometric reach. The
canvas contains that reach in its cache rectangle; the ground baker retains its
previous formula and pixel allowance through the shared helper. Disabling caches,
changing painters and deriving expected pixels from the rectangle under test were
rejected. Width/preset geometry notifications precede mutation. Regression coverage
is documented in section 8.30; the existing ground hairpin/tile-border gates remain.

## ADR-060 addendum L6: pictures on request are not a steady path (#390, ADR-072)

Decision 17 stands: nothing the workspace does by itself takes a frame from the live view. A
picture for a file, a tour or an agent is someone's own action and is now made through
`Quick3DHost.capture`, in `workspace_capture.py`, nowhere else. The scan test lists its three
call sites by name next to the click and the growth jump. It replaces "a picture for a file goes
through `offscreen.py`", which refuses while the view is shown. A frame of a tour IS paced by a
timer, one the user started and can stop. What such a frame holds comes back with the next
presented frame: the session soak (300 pictures at 1080p, 100 at 4K) stayed flat on GPU and WARP.

**Addendum L6a (2026-11-25, #1015 — the view says when it is at rest).** Every render
measurement needs "the 3D view is at rest", and that rule lived in
`tests/integration/workspace_render_state.workspace_settled`, where it had to know each
private timer the workspace runs (the forge's admission queue and timer, the camera, and
#894's shadow fit — added after a soak read a frame inside the unfitted window).
`Workspace.at_rest()` is now the one place, beside the timers it reads: the pipeline's own
`Scene3DController.idle`, the forge queue and timer, the camera, the held first pass and the
shadow fit. `workspace_settled` delegates to it, and `workspace_gate_measure.rest_state()`
reports it with the components. A new deferred step is one line there; it cannot be missed
by a test helper again. A unit test pins each step.
