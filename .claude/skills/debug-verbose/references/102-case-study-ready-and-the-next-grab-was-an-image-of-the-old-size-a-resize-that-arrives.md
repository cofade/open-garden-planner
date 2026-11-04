## Case study: "ready" — and the next grab was an image of the old size: a resize that arrives inside the call (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: after `showFullScreen()` — of a standalone view, or of the main window that embeds
it — `host.wait_ready()` returned True and the very next `host.grab()` raised `EngineError: …
Qt rendered a 320 x 240 px image for a 5120 x 1440 window`. 20 of 20 in the review, on the GPU
and on WARP. The suite was green on three platforms; the lifecycle matrix had no full-screen
row, and `application.py` calls `showFullScreen()` on the window the 3D workspace is embedded in.

**Wrong theories**:

1. *"After every resize the QML root item lags the window by one event-loop pass — so a root
   item of the window's size means the host has caught up."* The rule of the fix before, by then
   written into nine documents. True for a splitter move; false here.
2. *"Then wait for `frameSwapped` after the resize."* That signal is queued from the render
   thread: one emitted BEFORE the resize can arrive after it. (And with the display asleep a
   window presents one frame and then none.)
3. *"`wait_ready()` taking a second after a resize is my wait loop."* It was ONE
   `processEvents()` pass, inside Qt's own expose handling.

**Key evidence**: an event filter on the view. Per call: what Qt delivered INSIDE the call,
then what each later pass delivered — with the size of a raw `grabWindow()` beside it. (The
`state=` column is the fixed host's; before the fix the first line read `live`.)

```
showFullScreen: sync events [Resize(5120x1440) Move State] window 5120x1440 root 5120x1440 state=starting raw grab 320x240
     pass 1: [Expose(exposed)] window 5120x1440 root 5120x1440 state=live raw grab 5120x1440
showNormal: sync events [Resize(320x240) Move Expose(exposed)] window 320x240 root 320x240 state=live raw grab 320x240
showMaximized: sync events [-] window 5120x1369 root 320x240 state=starting raw grab 320x240
     pass 1: [Resize(5120x1369) Move State Expose(exposed)] window 5120x1369 root 5120x1369 state=live raw grab 5120x1369
window.showMaximized: sync events [-] window 447x500 root 447x500 state=live raw grab 447x500
     pass 1: [Resize(2557x1369) Move Expose(exposed)] window 2557x1369 root 2557x1369 state=live raw grab 2557x1369
```

(The last pair is the embedded view while its main window is maximised: until the layout ran
NOTHING has changed for it, and it is — truthfully — live at its old size.)

**Root cause**: `showFullScreen()` delivers its resize synchronously — window and root item
agree before the call returns — while `grabWindow()` on a shown window renders into the swap
chain as it is, and Qt resizes the swap chain only when it handles the NEXT expose. The state
machine had no fact for "the render target has the window's size", so the host read "live" in
between. In every line above the grab is wrong exactly between a `Resize` event and the next
`Expose` event of the exposed window.

**Fix**: that fact, latched from the window's own events by the filter that already latched "a
platform window was created": `Resize` clears it, the next `Expose` of the exposed window sets
it, and "live" needs it. `wait_ready()` delivers what is pending once for ANY visible host
before it answers. A grab whose image has another size after all raises `HostStateError` — a
state, like every other "not now" — instead of `EngineError`. And the contract moved into ONE
docstring (`quick3d/lifecycle.py`); the nine copies had drifted apart. *(Review round 4: the
latch was the next defect — "a host that waited for a message that never came", below. The
size check stayed; the fact went.)*

**Lesson**: **"one event-loop pass" is not a unit.** Before writing a rule about "after a
resize", print what each CALL delivers before it returns — per call, per platform. And when a
hand-written matrix of orders has missed the failing order twice, **add an order nobody wrote**:
a seeded random walk whose judge knows only what Qt said about the window (it found nothing
more on the dev box — and on a 1024 px CI runner it found the defect of this very fix).

