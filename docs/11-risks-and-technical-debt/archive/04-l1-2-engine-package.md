# Archive 04: Phase 17 L1.2 engine package

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.15 What the engine taught while the production package was built (Phase 17 L1.2, #385)

The first six were found by measuring before building on them; the rest by two independent
reviews and by CI's runs of the branch — each of those is a thing a green suite did not see
(ADR-048 addendum L1.2, "Review round 1" and "Review round 2"; the round-2 entries are marked).
Machine: Windows 11, RTX 4070 and WARP, PyQt6 6.11.0, 2026-10-11; xcb + OpenGL on llvmpipe in
a container with the CI job's packages.

- **Grabbing a Qt Quick window that has no scene graph is safe exactly once — and only if the
  window is never shown.** `grabWindow()` on a window without a live scene graph renders one
  frame offscreen and tears everything down again. What that means depends on the window:
  - *Never shown.* The frame is right — pixel-identical to a grab of the same scene in a shown
    window — and it is the only one: the second such grab returned the bare clear colour, every
    Model gone, even the built-in `#Rectangle` ground (mean absolute difference 161 of 255 on a
    320 × 240 frame; Direct3D 11 on the GPU and on WARP alike). `View3D.pick()` finds nothing
    on such a window.
  - *Shown, first expose pending* — `show()`, then `grabWindow()` with no pass of the event loop
    in between. **The grab returns a correct image, and the process dies in the next passes of
    the event loop**: exit code 3 (abort), `0xC0000005` (access violation) or `0xC0000374` (heap
    corruption). 3 of 3 here; 5 of 5 on the GPU, 3 of 3 on WARP and 4 of 4 embedded in a
    splitter in the review that found it.
  - *Shown afterwards* — one hidden grab, then `show()`: the same death (3 of 3). So does an
    embedded, never-shown view that is grabbed and then shown by its parent (2 of 2, 1 of 1 on
    WARP).
  - *Not* when the window is destroyed before the event loop runs again (6 of 6 survived). That
    is why offscreen rendering with one host per frame never met the crash, and why a control
    whose host goes out of scope cannot demonstrate it.

  *Root cause (inferred from the behaviour, not read in Qt's source):* the throwaway render
  device of such a grab and the window's own first expose each set up, and tear down, the same
  scene graph. *What the first version got wrong:* `Quick3DHost.grab()` asked `isVisible()`.
  The engine's condition is `isSceneGraphInitialized()`, and between `show()` and the first
  expose the two disagree: visible, no scene graph. The error message of the hidden case even
  recommended `show()`. And a Python flag "was shown" could not have been right either: the
  parent of an embedded container shows and hides it without telling the host. *Fix:* the host
  is a state machine over what Qt reports — a host that waits for its first expose refuses to
  grab, one that took its offscreen frame refuses `show()` and `container()`, an embedded host
  has no offscreen frame, `wait_ready()` pumps to the first expose and reports. (The contract
  in full is the module docstring of `ui/view3d/quick3d/lifecycle.py`, and only there; the
  entries below say what each of its facts cost.) Pinned by one call order per child process in
  `tests/integration/test_quick3d_lifecycle.py`, with controls that must die; the rule
  itself runs in the default tier too (`tests/ui/test_quick3d_host.py::TestStateMachine`,
  `tests/unit/test_quick3d_lifecycle_states.py`).
- **(Round 2) "Never shown" means "no platform window was ever created" — on xcb anything less
  kills.** The first state machine called a window "new" when it had no scene graph and was
  not visible. `show(); hide()` with no event in between is exactly that — and the window HAS
  a platform window. The one offscreen frame taken then is correct, and on xcb the process
  segfaults in the next event-loop pass (5 of 5; the red CI job); on Direct3D 11 it survives,
  which is why the matrix had pinned that order as safe. So does a window the user closed with
  its X button: its platform window is destroyed, its scene graph kept, and a raw grab of it
  is an access violation on Direct3D 11 and a segfault on xcb. *Fix:* `NEW` is "Qt never sent
  `PlatformSurface/SurfaceCreated` for this window" — latched by an event filter, because
  `QWindow.handle()`, the same fact, is not bound by PyQt6, and `winId()` would create the
  window it asks about. *Lesson:* a crash that was measured not to happen on one backend is
  not a fact about another; the control for it must run where it was measured, and be reported
  — not assumed — elsewhere.
- **Qt's window predicates do not mean what their names suggest, and two backends disagree.**
  Measured as (visible, exposed, scene graph initialised) on Direct3D 11: a new `QQuickView`
  F F F; after `show()` T F F; after ONE `processEvents()` T T T; right after `hide()` F **T** T
  — still "exposed" until the event loop ran — then F F T; shown again T F T; minimised
  **T** F T. So "a frame can be had" needs all three, and "visible" alone is neither necessary
  nor sufficient. Under the software scene graph (`QT_QPA_PLATFORM=offscreen`)
  `isSceneGraphInitialized()` is True from the window's birth and nothing 3D is ever drawn:
  the default test tier can check the state machine's logic, never Qt's behaviour.
  `Quick3DHost.renders_3d()` is False there, and `grab` / `pick` raise instead of returning a
  frame without the garden — so does `render_records`, which makes the self-test's failure
  under that platform name the backend instead of saying "the box is not there".
- **(Round 2) Visible, exposed and scene-graph-initialised is still not "a frame can be had":
  geometry.** A `QSplitter` pane dragged shut leaves the embedded window visible, exposed,
  with a scene graph — and 0 px wide. A raw grab returns an image of the OLD size without one
  pixel of the scene; a raw pick returns a hit; `mapFrom3DScene` returns (0, 0). The first
  state machine said "live". Two more facts of the same family: after an ASYNCHRONOUS change
  of size (a splitter move, `resize()`, `showMaximized()`) the QML root item keeps the old
  size until the event loop delivered the resize event (a pane reopened from 0 is still 0
  wide in the scene, and a frame taken then is blank); and a window ONE pixel wide or high
  draws no 3D at all — the bare clear colour — while 2 px draws the scene. And a pane
  re-shown inside a splitter keeps its stale, empty geometry until the pending layout request
  is delivered. *Fix:* a live host also needs an area of at least 2 × 2 px and a root item
  that has the window's size; `wait_ready()` first delivers what is already pending, then
  waits; and `grab()` rejects an image that does not have the window's size. *Corrected in
  review round 3:* this entry said "after EVERY change of size … until one pass of the event
  loop ran". False twice — the next entry.
- **(Round 3) A resize can arrive INSIDE the call that caused it — and then the scene has
  the new size and the render target the old one.** *Symptom:* `wait_ready()` answered True
  and the very next `grab()` raised `EngineError` ("Qt rendered a 320 × 240 px image for a
  5120 × 1440 window") — after every `showFullScreen()`, 20 of 20, standalone and embedded,
  on the GPU and on WARP. `application.py` calls `showFullScreen()` on the very window the
  workspace embeds the host into. *Wrong theory (round 2's, the entry above):* "after every
  resize the root item lags by one pass, so a root item of the window's size means the host
  has caught up". *Measured, with an event filter on the view:* `showFullScreen()` delivers
  `Resize`, `Move` and `WindowStateChange` inside the call — window and root item agree at
  once — and `Expose` only in the next pass of the event loop; `grabWindow()` on a shown
  window renders into the swap chain as it is, and Qt resizes the swap chain when it handles
  that expose. `showNormal()` delivers its expose inside the call too (the grab is right at
  once); `showMaximized()` and a splitter move deliver nothing inside the call; and a main
  window that was maximised has not touched the embedded view at all until its layout ran —
  the view is, truthfully, live at its old size until then. In every case a grab has the
  wrong size exactly between a `Resize` event and the next `Expose` event of the exposed
  window. *Fix:* that is the tenth fact, latched by the event filter that already latches
  "a platform window was created": a resize event clears it, the next expose event of the
  exposed window sets it, and a live host needs it. `wait_ready()` delivers what is pending
  once for ANY visible host before it answers — also for one that reads live, whose parent's
  resize may still be in the queue. A grab whose image has another size after all is the
  same STATE, not an engine failure: `HostStateError`, counted (`stale_frames`, expected 0
  and 0 in every run so far), and the host reads "starting" until the next expose. Not
  derived from `frameSwapped`: that signal is queued from the render thread, and one emitted
  before a resize can arrive after it. *Lesson:* "one pass of the event loop" is not a unit
  of anything — which events a call delivers before it returns differs per call and per
  platform. Promise an ANSWER (`wait_ready()`), not a number of passes; and test the promise
  against orders nobody wrote down: the hand-written matrix had no full-screen row, the
  seeded random walk that joined it (250 operations) has found nothing since. Pinned by
  `test_after_wait_ready_the_frame_has_the_windows_new_size` and
  `test_a_seeded_random_order_never_yields_a_wrong_frame`. *Corrected in review round 4:
  the fix itself — a fact that an expose switches on — was the next defect, and "has found
  nothing since" lasted until the walk ran on a small screen. The entry below.*
- **(Round 4) A fact that only an OS paint message can set is a fact you may wait for for
  ever — the frame is the witness.** *Symptom:* CI red on `windows-latest` only: the seeded
  walk, 7 problems in 252 looks — three looks where Qt showed the pane and the host never
  came up, and `wait_ready()` taking its whole 5 s three times in a row on a 2 × 60 px
  pane. Green on the dev box, on the GPU and on WARP. *Wrong theory (round 3's fix, the
  entry above):* "a grab has the wrong size exactly between a `Resize` event and the next
  `Expose` — so wait for that expose". *Measured:* Windows sends NO expose to a pane that
  grows where no screen is, and none to one that is shown there. The walk asked for 1203
  and 1500 px wide windows on whatever screen it found; on the runner's 1024 px the pane
  lay beyond the edge. With the window placed like that, the dev box showed the same
  indices — while its display slept. With the display awake, the same pane beyond the same
  edge got an `UpdateRequest` (still no expose), Qt drew, and the frame was right; asleep
  again (the session idle for 25 min), stale again — and on WARP, in those same minutes,
  right. Whether a frame can be had there is not a fact of the platform: it changes with
  the adapter, and within a day on one machine. *Root cause:* the host had made a MESSAGE its evidence for something
  it can simply look at. Each round had added a fact to the state (three, then nine, then
  ten), and each new fact was a new way to be wrong about the one thing that matters: is
  the frame right? *Fix:* the frame answers that. `grab()`, `pick()`, `project()` and
  `wait_ready()` take a frame and compare its size with the window's, to the device pixel
  (*round 5:* "less than one pixel off" — not exact at 125 %; the entry below);
  another size is a refusal, never an answer, and nothing is remembered about it. The
  state is what Qt reports when asked, no more. `wait_ready()` starts no delivery of events
  once its timeout is up (a zero timeout runs none; *round 5:* "bounded by its timeout" was
  more than a nested event loop can promise — below), defaults to 1 s, and says
  False 0.5 s after the last sign of progress whatever the timeout — for every cause at
  once: no screen, no display, no painting. *Two things found on the way:* a pick right
  after a resize, with no frame in between, MISSES (the engine picks with the viewport of
  the frame it rendered last) — so `pick()` and `project()` take a frame of their own
  then; and the size check had a tolerance of two pixels, through which a 447 px frame
  passed for a 448 px window. *Lesson:* do not infer what you can observe; and a test must
  not let the window system decide where its windows are — the matrix places every window
  on the screen on purpose now, runs its walk once as on 1024 × 768, and reproduces "nothing
  draws the view" with an event filter instead of hoping for a machine in that condition.
  Pinned by `test_a_view_that_nothing_draws_is_refused_promptly_and_answers_when_painting_resumes`,
  `test_the_same_walk_where_a_small_screen_leaves_the_pane_beyond_the_edge`,
  `test_a_pane_beyond_the_screens_edge_gets_a_frame_or_a_prompt_refusal_and_answers_when_it_is_back`
  and, without a window, `tests/ui/test_quick3d_host.py::TestWaitReady`.
- **(Round 3) A contract written down in nine places is wrong in three.** The host's state
  table stood in `lifecycle.py`, `host.py`, §8.29.2, ADR-048, this section, the glossary, the
  building-block view and both copies of the `ogp-3d-renderer` skill; after round 2 three of
  them said "after every resize the host is starting for one pass", which the code did not
  do and Qt does not do. *Fix:* the module docstring of `lifecycle.py` IS the contract; every
  other text links to it, and `tests/unit/test_quick3d_packaging.py` fails a second copy of
  the state table. *Lesson:* a table a caller must obey belongs next to the function that
  implements it, once.
- **(Round 3) `QEventLoop.exec()` returns at once when the application is quitting, and a
  bounded wait built on it spins.** *Symptom:* `wait_ready()` on a host that was still
  starting while the app closed: 158,574 looks at Qt in 3.0 s. *Measured:* inside a running
  main loop after `QCoreApplication.quit()`, a local `QEventLoop.exec()` returns −1 in about
  2 µs; without a running main loop `quit()` does nothing, which is why no in-process test
  had met it. *Fix:* the pass reports whether the loop ran; `wait_ready()` answers False at
  once when it did not, and the number of passes is bounded by the timeout whatever a pass
  does. Pinned in a child process with a real main loop
  (`test_a_pass_of_the_event_loop_says_whether_it_ran`).
- **(Round 2) A judge that asks the suspect sees nothing.** The lifecycle matrix compared
  every frame with the state the host had reported for it: a host that says "live" must give
  a frame, one that says "hidden" must refuse. A host that reported the WRONG state passed —
  the blank frame of the collapsed pane was "a frame from a live host". *Fix:* the matrix
  states per order and step what a truthful host must answer, checks the pixels (the probe
  box at the predicted place, in a frame of the window's size), and only then looks at the
  state. The same family as the canary that ran the product (below).
- **With the display asleep, a visible window presents its first frame and then none.**
  *Symptom:* a shown, exposed, active `QQuickView` fired `frameSwapped` once; forty
  `view.update()` calls later the count was still 1 (threaded and basic render loop). A wait for
  two frames timed out after 20 s. *Root cause:* Qt 6.11 delivers update requests on Windows from
  a thread that waits for the display's vertical blank; a monitor in power-save has none. With
  `QT_D3D_NO_VBLANK_THREAD=1` frames flowed again, at about 4 per second (each present waited
  ~250 ms). On WARP frames flow either way. The machine also prints
  `qt.qpa.screen: "Unable to open monitor interface to \\.\DISPLAY1"` on every window.
  `grabWindow()` is unaffected: it renders and reads back synchronously in 1–9 ms. *Fix:* nothing
  in the package or its tests waits for a frame to be *presented*; `grab()` is the
  synchronisation point. (The L0 owner run's protocol note — a `wait_frames` timeout followed by
  an access violation in `grab()` — has two halves. The timeout is this entry. The access
  violation was attributed to it as well in the first version of this text, without evidence;
  a grab of a window whose scene graph was not up — the entry above — fits an access violation
  better. Neither attribution was checked against the L0 run.) The monitor warning is listed, exactly, as
  an `environment` message in `qt_messages._ENVIRONMENT`, so "a clean run records zero Qt
  warnings" stays assertable on that machine; an allow-list wider than what was measured would be
  a hole, and `tests/unit/test_quick3d_pure.py::TestClassify` pins that it is not.
- **A recorder that replaces Qt's message handler deafens the one before it.** *Symptom:* the
  positive control "a broken shader fails the render" raised `RenderError` as it should — and
  the run's own summary still counted 0 Qt errors. `render_records` installs a recorder for one
  frame; the driver had one for the whole run; `qInstallMessageHandler` keeps a single handler.
  *Fix:* `qt_messages.install` forwards every message to the handler it replaced and
  `uninstall(previous)` puts that one back. Inside the running app this is also what keeps the
  app's own logging intact during an offscreen render. Pinned by
  `tests/unit/test_quick3d_pure.py::test_nested_recorders_both_hear_an_error`.
- **(Round 2) A Python Qt message handler beside a shown Qt Quick window deadlocks the
  process.** *Symptom:* the host's "watch" for a live view's errors — a recorder installed
  with `qInstallMessageHandler` for the life of a shown host — and a `hide()` that never
  returned. 5 of 5 in the review, on the GPU and on WARP; later every run here, and on xcb.
  *Wrong theory (round 1's):* "the recorder takes a lock and never raises, so it is safe on
  Qt's render thread". *Root cause:* Qt Quick renders a shown window on a thread of its own
  (`qt.scenegraph.general` says "threaded render loop" on Direct3D 11 and on xcb + OpenGL).
  Qt's message handler is process-wide; PyQt calls a Python handler under the GIL on
  whichever thread emits the message. The GUI thread holds the GIL while it sits inside a
  Python-called Qt function; `hide()` waits there for the render thread; the render thread
  emits a message and waits for the GIL. Any render-thread message at that moment will do —
  the shader errors the watch existed to catch among them. The app installs no Python Qt
  message handler; the watch would have introduced this. *Fix:* no watch. A recorder only
  around rendering on the calling thread — the one-shot offscreen frame — where every message
  was measured to arrive on that thread (the recorder counts the others; the tier requires
  0), and never while a Qt Quick window is shown (`render_records` refuses). A shown host
  reports what Qt delivers on the GUI thread instead (`health()`, §8.29.2). *Lesson:* "thread
  safe" is not "safe to call from that thread" when the caller holds a lock you need — and
  the GIL is a lock. Pinned as a control that must hang
  (`test_a_python_message_handler_beside_a_shown_window_deadlocks`).
- **(Round 2) On Windows, `_exit` does not end a process that is deadlocked inside Qt.**
  `faulthandler.dump_traceback_later(exit=True)` wrote every thread's stack into the log — and
  the process stayed alive, every run (one for three minutes). Its C thread needs no GIL; but
  its `_exit` is `ExitProcess`, which runs every DLL's detach code, and that waited for the
  deadlocked threads. `ExitProcess` from a native timer thread hangs the same way (2 of 2). On
  Linux `_exit` ends the same deadlock at once (5 of 5). *Fix:* a second line of defence for
  the self-test, the render driver and anything else that owns its process:
  `runlog.watchdog(…, supervised=True)` starts a tiny second process that calls
  `TerminateProcess(handle, 1)` ten seconds after the deadline and writes the reason into the
  log first; in the frozen build it is the exe itself (`--selftest-supervisor`).
  *And the trap inside the fix:* the supervisor must know when the block is OVER. The block
  signals a named event and closes it; a block that finishes before the supervisor has even
  started leaves no event behind — and the first version, finding none, waited on the process
  alone and would have terminated it at the deadline: a pytest run, 310 s after the test that
  called the bounded self-test had passed. A missing event now means "released"; the
  supervisor also checks the process's creation time, so a reused pid is never touched.
  Pinned by `test_the_supervisor_leaves_a_process_alone_whose_block_finished_first`.
- **(Round 3) "A missing event means released" was right; "an event that exists is mine" was
  not.** The release event was named after the PROCESS (pid and creation time). *Symptom
  (the review's measurement):* block A — a supervised watchdog of 1 s around an empty body —
  then block B, 60 s, healthy, in the same process. A's supervising process came up after A
  was over, found B's event under the same name, waited on it, and terminated the process
  4.1 s into B, writing "block A was still alive …" into A's log. Latent: the self-test and
  the render driver arm one block per process; but `supervised=True` was advertised for
  reuse, and three texts said a supervisor could only ever act for its own block. *Fix:* a
  random nonce per block in the event's name, handed to the supervisor on its command line;
  one armed watchdog per process (a second raises `WatchdogError` — `faulthandler` has a
  single timer anyway); and a supervisor that checks who it is working for before it opens
  anything: validated arguments (a deadline of `nan` used to be a traceback, `-1` a wait of
  49 days, `0` an immediate terminate), its target must be its own PARENT process and, in the
  frozen build, run the same image, and it appends to the log it was handed and creates no
  file. *And the gate's own #291:* a supervisor that could not be started was logged as
  `supervisor=none` and the self-test passed — the day a build could not start it, nothing
  would have said so until a deadlocked self-test held a release job. On Windows the
  self-test now FAILS without a supervising process that started, was released and left.
  *Lesson:* something that may kill must name its target by what nobody else can have (a
  random name it was handed), never by what the next user will have too (the pid). Pinned by
  `test_a_finished_blocks_supervisor_cannot_end_the_block_after_it`,
  `test_the_supervisor_only_acts_for_the_process_that_started_it` and
  `test_without_its_supervisor_the_selftest_fails_on_windows`.
- **(Round 4) "It left with exit code 0" is not "it did its job".** A supervising process
  that could not find its block — a creation time that was not the process's — left 1.5 s
  into a 20 s block with exit code 0, the same code as one that was released; the block
  called itself supervised and the self-test logged `ok=True detail=started, released,
  left` for a run without a safety net. *Fix:* 0 only for a supervisor that held the
  block's release event; 4 for one that found nothing to wait for. And so that "came up
  late" is not mistaken for "lost": the block signals its event and KEEPS it until the
  supervisor has left (at most 15 s — the only start bound there is), so a late one finds
  it, signalled, and leaves as released. Also: everything that arms a watchdog is inside
  its `try` — a failure while arming had left the process "armed" (every later watchdog
  refused) with a live supervisor that would have ended it at the deadline. Pinned by
  `test_a_supervisor_that_never_supervised_says_so_in_its_exit_code` and
  `test_a_watchdog_that_cannot_be_armed_leaves_nothing_armed_and_no_supervisor`.
  *Round 5, the same lesson twice more:* a supervisor whose own wait FAILED also said 0 —
  the code read "not a timeout" as "released" — and `Armed.supervised` was True beside a
  gap that said the supervisor had not left. Only the two answers that mean "the process
  ended" and "released" are 0 now, and the two properties are one statement. Pinned by
  `test_a_supervisor_whose_wait_fails_says_so_and_terminates_nothing` and
  `test_what_a_block_says_about_its_supervisor`.
- **(Round 5) A judge that repeats the suspect's rule is blind exactly where the suspect is
  wrong — and "exact" needs a definition.** *Symptom:* none in any tier, on three platforms,
  on CI. Found by a reviewer who set `QT_SCALE_FACTOR=1.25`: a pane made one logical pixel
  wider, 442 → 443, with the render target behind, and `grab()` handed out the old frame —
  553 px — for the new pane, whose own frame is 554 px; `pick()` answered with the old
  viewport. *Wrong theory (round 4's own words):* "the size check is exact to the device
  pixel". It was "less than one pixel off `logical × ratio`", which IS exact when the ratio
  is 1, 1.5 or 2 — the three the tests had. *Measured:* Qt sizes a render target as
  `QSize(logical) * ratio`, `qRound` per side, so the right frame is at most HALF a pixel
  off; at 1.25 a 442 px pane has 552.5 → 553 px, and 553 is 0.75 off 553.75. 750 of 11,993
  neighbour frames passed at 1.25; every ratio strictly between 1 and 1.5 had some. *Why no
  test saw it:* the matrix's judge decided "a frame of the window's size" with the same
  inequality as the host. Round 1's judge had asked the host for its STATE and was blind to
  a wrong state; this one asked nothing — and had copied the rule. *Fix:* the host: at most
  half a device pixel off. The judge: what Qt makes for the window, computed by itself
  (`qt_round`), and equal to it. The arithmetic for every width from 2 to 3000 at twelve
  ratios, against `QSize * ratio` asked of Qt, in the default tier; one real-window row at
  125 % whose raw grab first proves that the render target is behind. *Lesson:* an oracle
  must be derived independently of what it judges — from the platform's definition, not from
  the implementation's tolerance; and when a claim says "exact", write down the rounding it
  is exact against, then test where rounding bites (between the round ratios), not where it
  cannot. Pinned by `test_the_size_check_is_qts_own_rounding_at_every_ratio`,
  `test_at_125_percent_a_pane_one_pixel_wider_does_not_get_its_old_frame` and
  `test_the_judge_knows_a_wrong_frame_when_it_sees_one`.
- **(Round 5) Three statements about time, each one measurement short.** (1) *"`wait_ready(t)`
  returns within `t`, plus the one handler that is running."* One pass of Qt's event loop
  delivers the whole queue: 0.2 s asked, 1.80 s taken behind six handlers of 0.3 s. Not
  fixable from the thread those handlers run on — so the contract states that bound, and
  states what the call is: a nested event loop that takes user input, which the workspace
  needs nowhere on the GUI thread. (2) *"False `STALL_S` after the last sign of progress"*
  counted WALL time: a GUI thread busy for 0.7 s in another handler looked like 0.7 s of
  silence, and the repaint queued right behind it was never looked at — False after 0.75 s,
  True when asked again. Silence is counted pass by pass now; a pass that overran its step
  was busy. (3) *"`pick()` and `project()` take a frame once per resize."* Once per CALL
  while the render target was behind: 200 `project()` of one tick, 200 frames, all refused.
  One per refusal now — renewed by a sign of progress, by other facts, or after 0.25 s — and
  the caller's rule is written down: a tick stops at its first `HostStateError`. *Lesson:*
  a bound that names "the one thing" was measured with one thing in the queue; measure the
  claim under load (N queued handlers, N calls in a row, a busy thread) before writing it
  into a contract. Pinned by `test_while_the_render_target_is_behind_a_tick_costs_one_frame`,
  `test_a_busy_pass_of_the_event_loop_is_not_silence`,
  `test_idle_passes_add_up_to_silence_whatever_a_busy_one_took` and
  `test_the_bounds_of_wait_ready_are_stated_once`.
- **(Round 2) Without a slot on `sceneGraphError`, a graphics device that cannot be created
  takes the whole app down.** Forced with `QT_D3D_ADAPTER_INDEX=9`. With a slot connected, Qt
  emits `(ContextNotAvailable, "Failed to initialize graphics backend for D3D11.")` and goes
  on: the window is visible and exposed and never gets a scene graph. With nothing connected,
  Qt opens a native modal dialog with that text, the process sits in it, and after OK it
  aborts (`0xC0000409`). Qt decides by asking whether the signal is connected. *Fix:* the host
  connects it (queued), `health().scene_graph_error` carries the text, and `wait_ready()`
  stops waiting. An 8-second "the process is still running" smoke test passes a process that
  sits in such a dialog — the self-test, not the smoke, is the gate (§7.4).
- **(Round 2) A QML function that throws returns `None` to Python, silently.**
  `QMetaObject.invokeMethod` on a MISSING function raises `RuntimeError`; on one that throws it
  returns `None` and the QML engine emits a warning. The host called `destroyPart` and took
  the return for success: with a failing `destroyPart` every `reset()` forgot one more Model,
  and the fourth "succeeded" with three Models still in the engine and
  `sink.state() == sync.expected_state()` true. *Fix:* a Model leaves the host's books only
  when the engine confirms it (deleted, or `retired`); `pick`, `project` and `engine_parts`
  turn a `None` into an `EngineError`; the QML warning reaches `health()`.
- **(Round 2) On Windows `QStandardPaths` follows `USERPROFILE`, not `APPDATA`.** The shell
  expands its known folders from the process's `USERPROFILE`; the `APPDATA` variable is not
  consulted. A test that set `APPDATA` to a temp directory and then let the app resolve its
  log directory wrote into the developer's real roaming profile — under a throwaway
  organisation name, which is how the empty directory it left behind was found. Qt Quick's
  shader cache and the graphics driver's caches hang on the same profile. *Fix:* the children
  of the engine tests get a profile of the test process's own (§8.10.8), and the one test
  that resolves the log directory first ASKS Qt where it would be — which creates nothing —
  and stops unless the answer is inside that profile.
- **`exposure` is not a property of `SceneEnvironment`.** Only `ExtendedSceneEnvironment`
  (`QtQuick3D.Helpers`) has it; on the plain type it is a QML load error ("Cannot assign to
  non-existent property"), reported with file and line by `Quick3DHost` — the loud path worked
  before the scene did. `Garden.qml` uses the extended environment for that one property, with
  every effect it offers switched off.
- **`TonemapModeNone` leaves LINEAR radiance in the frame — which makes a pixel computable.**
  In the top-down view a lit horizontal face reads
  `255 × tint_linear × (brightness × sin(elevation) × sun_linear + fill_linear)`: predicted 167.2,
  measured 171 (the difference is the material's small specular term). The frame looks dark to a
  human; it is a measurement view, and the render tier's truth checks rest on it
  (`test_a_lit_top_face_has_the_radiance_the_sun_predicts`). Related: a light with
  `brightness: 0` still contributes its `ambientColor`, which is how the fill stays on when the
  sun is switched off; and `PrincipledMaterial.baseColor` is linearised by the engine with an
  approximation of the sRGB curve — a tint through it and the same tint through a custom
  shader's exact uniform read 171 and 169.
- **A log with a fixed name in the temp directory is a hole on Linux (CWE-377).** The self-test
  first wrote `tempfile.gettempdir()/OpenGardenPlanner-selftest-3d.log`. `/tmp` is shared between
  users; a predictable name there can be pre-created or symlinked. Found in review, before any
  release. *Fix:* the log goes into the app's one per-user log directory
  (`core.logging_config.resolve_log_dir`), and `main._run_selftest` names the application first,
  because that directory hangs on Qt's application identity. Rule and tests: §8.11.
- **A guard that runs the thing it guards skips the defect it stands in front of.** The
  default-tier host tests began with a canary in a child process, so that a platform unable to
  create Qt Quick 3D objects would skip the file instead of crashing the run. The canary built
  a `Quick3DHost` — product code. A `Garden.qml` that did not load therefore failed the CANARY:
  32 skipped, 0 failed, a broken engine package, green. *Fix:* the canary is bare Qt with inline
  QML and may only say "this platform cannot"; the positive control runs the file against a
  broken scene and demands failures and no skip (now 9 failed, 43 errors, 0 skipped). The same
  family, found in the same round: a positive control whose host went out of scope before the
  event loop ran could not die; a timing budget that counted an UNKNOWN graphics adapter as a
  software rasteriser would have skipped itself green; Qt debug lines were run through the
  error patterns, so the wording of a debug message could have failed a release.
- **PyQt's enum member names are not a naming scheme.** `QSGRendererInterface.GraphicsApi` in
  PyQt6 6.11 has the members `OpenGL`, `Direct3D11Rhi`, `VulkanRhi`, `MetalRhi`, `NullRhi`,
  `Direct3D12` (plus `Unknown`, `Software`, `OpenVG`). A list of expected strings typed on
  Windows — `Direct3D11Rhi`, `OpenGLRhi`, … — failed the first Linux run, which reported
  `OpenGL`. *Fix:* the name comes from a table keyed by the enum MEMBER
  (`host.GRAPHICS_API_NAMES`: `Direct3D11`, `OpenGL`, …), and a test pins that every member
  has a name.
- **Three one-per-process facts behind a self-test that cannot hang.** `faulthandler` has ONE
  `dump_traceback_later` timer: a watchdog inside a watchdog replaces the outer one and cancels
  it on the way out — so when the whole `--selftest` is bounded, its 3D block arms none.
  `faulthandler` writes to a file DESCRIPTOR: a captured or replaced `sys.stderr` raises
  `io.UnsupportedOperation` (found by the test, under pytest's capture), and a windowed exe has
  no stderr at all — the watchdog then dumps into the null device and still ends the process.
  And under GitHub's `pwsh` (`$ErrorActionPreference = 'stop'`) `Write-Error` ends the step at
  once: a verdict printed with it is the last thing the step prints, so a log printed after it
  never appears — the gate steps print `::error::` with `Write-Host`. *(Round 2)* And a step
  that is cut off by its time limit prints nothing after the cut: the log is printed by a
  step of its own that always runs, not by the step that may hang.
- **A shader may not move a vertex at rest.** The wind shaders ported from the spike displaced
  a vertex by `sin(phase) × strength × weight` at time 0 — up to the full amplitude, with the
  clock standing still. Heights, spreads, picks and shadows are all measured on the mesh. By the
  shaders' arithmetic a leaf tip could sit up to 0.9 cm and a grass tip up to 2.5 cm away with
  the look's wind — invisible to every test — and measured in a wind 40 times stronger, boxes
  with full wind weight sat 20 cm and 38 cm off, with no message of any kind. *Fix:*
  both shaders multiply the sway by `smoothstep(0, 2, time)` — exactly 0 at rest. Pinned in
  pixels with vertices of full wind weight
  (`test_at_rest_a_vertex_with_full_wind_weight_is_where_its_mesh_puts_it`) and by a control
  with the factor removed.

Two measurements that are not traps but will be asked for: `Model.eulerRotation.y =
+rotation_deg` IS the counter-clockwise turn seen from above (mask IoU 0.9994 against the CPU
prediction at 17°, 0.288 against the opposite sense) — the proof L1.1 left open; and the engine's
shadow of a 100 × 100 × 200 cm box overlaps the analytic 2D shadow with IoU 0.976–0.978 at 35°
elevation and 480 × 360 (three azimuths, GPU and WARP within 0.0002), its direction within 0.02°.
