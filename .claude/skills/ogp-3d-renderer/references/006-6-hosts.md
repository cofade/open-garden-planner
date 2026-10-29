## 6. Hosts

| | `QQuickView` (+ window container) | `QQuickWidget` |
|---|---|---|
| Frame signal | `frameSwapped` | **none** — count `quickWindow().afterRendering` |
| Request a frame | `view.update()` | **`quickWindow().update()`**; `widget.update()` only re-composites the old texture |
| "Is it on screen?" | `isExposed()` — and "can it give a frame?" needs `isSceneGraphInitialized()` and `isVisible()` as well (the predicate bullets below) | `quickWindow().isExposed()` is **always False** (offscreen) → `isVisible()` |
| Screenshot | `grabWindow()` | `grabFramebuffer()` |

- **A `QQuickWidget` in a window moves the whole top-level window onto RHI composition.**
  2D canvas pan step, median: 5.5 ms without → 7.9 ms with a 3D widget beside it (**×1.42**,
  llvmpipe) and 2.8 → 15.9 ms (**×5.7**, Windows WARP, frozen) — `--pan-bench`; GO criterion 3
  asks ≤ ×1.3 on owner hardware. A synchronous
  `repaint()` does **not** include the flush/composition (it measured 0.08 ms "with 3D") —
  measure pan cost with `processEvents()`.
- **A second 3D window is not faster:** with the same view it took as long to its first
  finished readback as the first window (`--second-window`; WARP: 63.7 s vs 63.0 s) —
  consistent with per-window pipeline state (inferred, not verified). Keep one host alive and
  hide/show it: re-entry (show → next frame) median **7 ms** on llvmpipe, 31–53 ms on WARP
  (`--soak`; measured on a fully rendered scene — before the re-attach fix in §2, a soak that
  re-added models measured an empty garden).
- **The window container keeps the main window a raster surface (L1.2).** With
  `QWidget.createWindowContainer(view)` beside the 2D canvas, the top-level window's
  `surfaceType()` stays `RasterSurface` and a 2D pan step costs the same: median 2.56 ms with
  the container vs 2.63 ms without (×0.97; WARP ×0.92). The control — a `QQuickWidget` in the
  same place — turns the surface into `Direct3DSurface`. The surface type is the direct test;
  the timing only says what it would cost. A container belongs to its parent widget: when
  that widget is destroyed Qt destroys the view too, and a Python wrapper used afterwards
  raises "wrapped C/C++ object … has been deleted". `Quick3DHost` asks `sip.isdeleted` on
  every call: such a host reads `closed` and never raises sip's error (what a closed host
  answers is part of the contract, §12).
- **A window without a scene graph can be grabbed exactly once — and only if it is never
  shown (L1.2).** `create()` + `grabWindow()` on a never-shown `QQuickView` gives a correct
  frame once (pixel-identical to a shown grab); the second such grab is the bare clear colour —
  every Model gone, `#Rectangle` included (mean abs difference 161; GPU and WARP). `pick()`
  finds nothing on such a window. Offscreen rendering is therefore one host per frame
  (0.4–0.5 s with one material, 1.1–1.3 s with six).
- **`show()`, then `grabWindow()` before the first expose, kills the process (L1.2, review
  round 1).** The grab RETURNS A CORRECT IMAGE; the process dies in the next passes of the
  event loop — exit 3, `0xC0000005` or `0xC0000374` (3 of 3 on the GPU and 3 of 3 on WARP
  here; the review: 5 of 5, 3 of 3, and 4 of 4 embedded in a splitter). The same death: one
  hidden grab followed by `show()` (3 of 3 on each adapter), and an embedded, never-shown view
  grabbed and then shown by its parent (2 of 2, 1 of 1 on WARP). NOT when the window is
  destroyed before the event loop runs again (6 of 6 survived) — a test whose host goes out of
  scope proves nothing. The condition is `isSceneGraphInitialized()`, never `isVisible()`.
- **Qt's window predicates, measured as (visible, exposed, scene graph initialised) on
  Direct3D 11 (L1.2, review round 1):** new F F F · after `show()` T F F · after one
  `processEvents()` T T T · right after `hide()` F **T** T, then F F T · shown again T F T ·
  minimised **T** F T. Under `QT_QPA_PLATFORM=offscreen` the scene graph reports initialised
  from the window's birth and draws no 3D. These three are NOT enough to know whether a frame
  can be had (the bullets that follow); `Quick3DHost.state` derives new / starting / live /
  hidden / spent / closed from the facts it reads on every call (the contract: §12). There
  is no "was shown" flag, because the parent of an embedded container shows and hides it
  without asking.
- **"Never shown" means "no platform window was ever created" (L1.2, review round 2).**
  `show()` + `hide()` before any event leaves a window with no scene graph that is not visible
  — and that HAS a platform window. The one offscreen grab taken then is a correct image;
  on **xcb the process segfaults in the next event-loop pass** (5 of 5; it was the red CI
  job), on Direct3D 11 it survives. A window the user closed with its X button: platform
  window destroyed, scene graph kept; a raw grab is an access violation (Direct3D 11) or a
  segfault (xcb). The fact to ask is Qt's `PlatformSurface` / `SurfaceCreated` event, latched
  by an event filter: `QWindow.handle()` is not bound by PyQt6 6.11, and `winId()` creates
  the window it asks about.
- **A collapsed splitter pane is visible, exposed and 0 px wide (L1.2, review round 2).** A
  raw grab there returns an image of the OLD size without a pixel of the scene, a raw pick
  returns a hit, `mapFrom3DScene` (0, 0). After an ASYNCHRONOUS change of size (a splitter
  move, `resize()`, `showMaximized()`) the QML root item keeps the old size until the resize
  event is delivered (reopened from 0, the scene is still 0 wide — a blank frame). A window
  1 px wide or high draws no 3D (the bare clear colour); 2 px does. A pane re-shown in a
  splitter keeps its stale empty geometry until the pending layout request is delivered.
- **A resize can arrive INSIDE the call that caused it — `showFullScreen()` (L1.2, review
  round 3).** Measured with an event filter on the view, Direct3D 11: `showFullScreen()`
  delivers `Resize`, `Move` and `WindowStateChange` before it returns — window AND root item
  have the new size at once — and `Expose` in the next event-loop pass. `grabWindow()` on a
  shown window renders into the swap chain as it is, and Qt resizes the swap chain with that
  expose: a grab in between has the OLD size (20 of 20). `showNormal()` delivers its expose
  inside the call too; `showMaximized()` and a splitter move deliver nothing inside the
  call; a main window that was maximised has not touched an embedded view at all until its
  layout ran. In every one of those lines a grab has the wrong size between a `Resize` event
  and the next `Expose` event of the exposed window — **an observation, NOT a rule to wait
  on** (round 3 latched it with an event filter; the next bullet is what that cost). Never
  from `frameSwapped` either: it is queued from the render thread, and one emitted before a
  resize can arrive after it. And "one event-loop pass" is not a unit: that pass took
  6–13 ms, and up to about 1 s after a grab with the display asleep.
- **Qt resizes the render target when it next DRAWS the window — and nobody owes you a paint
  message. Take a frame and look at its size (L1.2, review round 4).** Measured, Direct3D 11:
  a pane that GROWS beyond the screen's edge got `Resize`, `Move` and nothing else while the
  display slept — a raw grab stayed 49 × 500 px for a 136 × 500 window for as long as the
  pane was there — and `Resize`, `Move`, `UpdateRequest` (still no expose) with a frame of
  the right size while the display was awake: same machine, same edge, both ways on one
  day; on WARP the update request came with the display asleep too. A pane SHOWN there
  was exposed in none of these. With an event filter that eats the view's `Expose` /
  `UpdateRequest` / `Paint` the same stale target appears ON the screen, on Direct3D 11 and
  on xcb + OpenGL: 447 × 500 px for a 600 × 500 and for a 200 × 500 window, for ever.
  So: no state fact that only an OS paint message can set (a host that waits for one waits
  for ever — CI was red on a 1024 px runner for exactly that), and no geometry test
  either ("is it on a screen?" does not say whether Qt draws). `grabWindow()` costs 0.7 to
  4 ms; compare its size with what QT makes for the window — `QSize(logical) * ratio`,
  `qRound` per side, so the right frame is at most HALF a device pixel off `logical ×
  ratio`. (Two pixels of tolerance handed out a 447 px frame for a 448 px window; "less
  than one pixel" handed out the 553 px frame of a 442 px pane for a 443 px one at 125 % —
  r5. 100 %, 150 % and 200 % are exact whatever the tolerance: test a ratio strictly
  between 1 and 1.5.) And a raw `pick()` right after a resize, with no frame
  in between, MISSES — the engine picks with the viewport of the frame it rendered last;
  `mapFrom3DScene` is right. One frame, even of the old size, and the pick hits.
- **`QEventLoop.exec()` returns −1 at once while the application is quitting (L1.2, review
  round 3)** — inside a running main loop after `QCoreApplication.quit()`, about 2 µs a
  call. A wait built on a local event loop spins then (158,574 passes in 3 s): check
  `exec()`'s return and bound the number of passes. Without a running main loop `quit()`
  does nothing, so no in-process test meets this — use a child that runs `app.exec()`.
- **Harmless, also measured:** a grab while hidden WITH a scene graph (a correct frame, 2 of 2
  on Direct3D 11 — the host refuses it all the same); wrapping a view that is live, starting
  or hidden in a window container.
- **NEVER install a Python Qt message handler while a Qt Quick window is shown (L1.2, review
  round 2).** Qt Quick renders a shown window on a thread of its own — `qt.scenegraph.general`
  says "threaded render loop" on Direct3D 11 (GPU and WARP) and on xcb + OpenGL (llvmpipe).
  `qInstallMessageHandler` is process-wide, and PyQt calls a Python handler under the GIL on
  whichever thread emits. The GUI thread holds the GIL inside a Python-called `hide()` and
  waits for the render thread; the render thread emits a message and waits for the GIL:
  **deadlock, every run**, on all three. A recorder is safe only around rendering on the
  calling thread — the one-shot offscreen grab of a never-shown window, where every message
  (shader errors included) was measured to arrive on that thread. To read a shown window's
  messages in a TEST, let Qt print them: `QT_FORCE_STDERR_LOGGING=1` (on Windows a process
  without a console logs to the debugger otherwise) + `QT_MESSAGE_PATTERN`, and parse the
  child's stderr. To see which loop runs: `QT_LOGGING_RULES=qt.scenegraph.general.debug=true`.
  The product's guard is static — `tests/unit/test_quick3d_boundary.py` scans all of `src/`:
  `qInstallMessageHandler` / `QLoggingCategory.installFilter` only in `quick3d/qt_messages.py`
  (and the dormant spike's own), the recorder's `install` only from `offscreen.py`, a
  render-thread signal (`frameSwapped`, `sceneGraphError`, the `afterRendering` family) only
  through `host._connect_queued`. Necessary, not sufficient: it cannot see a third-party
  handler, nor a Python override of a virtual Qt calls on the render thread.
- **A Windows process deadlocked inside Qt survives `_exit` (L1.2, review round 2).**
  `faulthandler.dump_traceback_later(exit=True)` writes the stacks and the process stays alive:
  `_exit` is `ExitProcess`, which waits in DLL detach code. On Linux `_exit` ends it. Only
  `TerminateProcess` from ANOTHER process ends it with a chosen exit code —
  `runlog.watchdog(…, supervised=True)`.
- **Connect `sceneGraphError`, or a missing graphics device takes the app down (L1.2, review
  round 2).** With a slot: `(ContextNotAvailable, "Failed to initialize graphics backend for
  D3D11.")`, the process lives, the window never gets a scene graph. With none: a native modal
  error box, then abort (`0xC0000409`). Force it with `QT_D3D_ADAPTER_INDEX=9`.
  (`QSG_RHI_BACKEND=bogus` just falls back.)
- **A QML function that throws returns `None` to `QMetaObject.invokeMethod`, silently** (L1.2,
  review round 2); a missing one raises `RuntimeError`. Check the return, and read the QML
  engine's `warnings` signal — it arrives on the GUI thread, with file and line.
- **On Windows `QStandardPaths` follows `USERPROFILE`, not `APPDATA`** (L1.2, review round 2):
  to keep a child process out of the real profile set `USERPROFILE` (Qt's shader cache and the
  driver's caches go with it); `APPDATA` alone redirects only code that reads the variable.
- **Do not wait for `frameSwapped` to be sure of a frame (L1.2).** On Windows, Qt 6.11
  delivers update requests from a thread that waits for the display's vertical blank. With the
  monitor asleep, a visible, exposed, active window presented its first frame and then none
  (1 frame after 40 `update()` calls; `QT_D3D_NO_VBLANK_THREAD=1` → about 4 per second; on WARP
  they flow). `grabWindow()` renders and reads back synchronously regardless (1–9 ms): it is
  the synchronisation point. A `QQuickWidget`'s window composition waited 262 ms per 2D pan
  step on that machine.

