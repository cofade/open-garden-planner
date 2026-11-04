## Case study: a host that waited for a message that never came — red on the CI runner's small screen, green on the dev box (Phase 17 L1.2, fixed 2026-10-12)

**Symptom**: `Render 3D (windows-latest)` red, one test: the story's own seeded walk, 7 problems
in 252 looks. Three looks where Qt showed the pane and the host never came up, and
`wait_ready()` taking its whole 5 s three times in a row on a 2 × 60 px pane. The same commit:
green on the RTX 4070, green on WARP, green on xcb in a container, 99 of 100 each.

**Wrong theories**:

1. *"A grab has the wrong size exactly between a `Resize` event and the next `Expose` — so
   'live' waits for that expose."* The fix of the round before (the case study above the last
   one), measured in every order anyone had written. It made an OS paint message a condition
   of a state.
2. *"Then name the place: a state for 'no part of the view is on a screen'."* The review
   offered it. Measured before building it: beyond the SAME edge of the SAME screen the pane
   kept its old render target while the display slept and got the new one while it was awake
   — both ways on one day, and on WARP the new one either way. Geometry does not say whether
   Qt draws.
3. *"The local tiers pass, so it is the runner."* They passed because every window of the
   matrix fits on a 5120 px screen. The walk asked for 1203 and 1500 px wide windows on
   whatever screen it found.

**Key evidence**: the runner's own line — every fact Qt reports is in place, and the one the
host had invented is not:

```
[59] setSizes(.., 49) / pump window=[56, 701] state=starting: STUCK — Qt shows the window and the host does not come up:
     WindowFacts(surface_created=True, visible=True, minimised=False, width=56, height=701, scene_graph=True, exposed=True, root_width=56.0, root_height=701.0, target_synced=False)
```

and the events the view gets when the pane grows beyond the screen's right edge (an event
filter on the view, the raw `grabWindow()` beside it, then the FIXED host) — the same probe,
the same day, the display awake and, 25 idle minutes later, asleep:

```
grown to 137  : window 137x500 events ['Resize', 'Move', 'UpdateRequest'] exposed=True raw grab 137x500 ok; host: state=live wait_ready(5)=True
grown to 137  : window 137x500 events ['Resize', 'Move'] exposed=True raw grab 49x500 STALE; host: state=live wait_ready(5)=False
```

**Root cause**: the host had made a MESSAGE its evidence for something it can look at. Windows
sends no expose to a pane that grows where no screen is; a state that waits for one waits for
ever. And the test that should have caught it let the window system decide where its windows
were.

**Fix**: the frame is the witness. `grab()`, `pick()`, `project()` and `wait_ready()` take a
frame and compare its size with the window's, to the device pixel ("less than one pixel off"
— which round 5 found is not exact at 125 %: the next case study); another size is a refusal
and nothing is remembered. `wait_ready()` starts no delivery of events once its timeout is up
(a zero timeout runs none; it had taken 1.0 to 1.4 s), defaults to 1 s instead of 10,
and answers False 0.5 s after the last sign of progress — for every cause at once. In the
tests: every window is placed on the screen on purpose; the walk runs a second time where a
1024 × 768 screen leaves the window; and the condition is MADE, not hoped for — an event filter
that eats the view's `Expose` / `UpdateRequest` / `Paint`:

```
linux: grown live/refused; shrunk live/refused; wait_ready(5) after grown: False in 0.502 s, wait_ready(60) after long: False in 0.503 s, wait_ready(0) after zero: False in 0.002 s; frames refused for their size 20
```

**Lesson**: **do not infer what you can observe** — three rounds had each added a fact to the
state (three, nine, ten), and each new fact was a new way to be wrong about the one question
that matters: is the frame right? Ask the frame. **A test must not depend on where the window
system puts a window, or on how large the screen is**: place it, and run once as on the
smallest screen you ship to. And **a condition that differs between two days on one machine
cannot be a pin**: reproduce it on purpose (here: withhold the paint events), pin THAT, and
assert only what holds on every machine for the real thing.

