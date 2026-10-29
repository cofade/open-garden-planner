## 11. Symptom → cause (spike chronicle)

| Symptom | Cause | Fix |
|---|---|---|
| Segfault at start | `idealSurfaceFormat()` before `QGuiApplication` | call nothing Quick-3D before the app object |
| Frame renders nothing 3D under CI | `offscreen` QPA → software scene graph | xvfb + xcb + `QSG_RHI_BACKEND=opengl` |
| QML: non-existent property `castsShadow` | Model vs Light naming | `castsShadows` on Models |
| QML: `lookAt is not a function` | only cameras have it | quaternion from Python |
| Whole garden pale blue, no shadows | the light was never oriented | `rotationTo((0,0,-1), travel)` |
| Lawn white, gravel around the beds | ground texture upside down | `flipV: true` |
| Sky sun stuck after a sun change | probe cached per Texture object | new Texture per change |
| Ultra preset black | SSGI on Mesa | SSGI opt-in |
| `'QJSValue' object is not iterable` | QML function returned a JS object | `.toVariant()` |
| QQuickWidget never reports frames | it has no `frameSwapped` | `quickWindow().afterRendering` |
| QQuickWidget renders only once | `widget.update()` re-composites | `quickWindow().update()` |
| Windows run "hangs" for an hour | `grabWindow()` ~100 s on WARP, no output | time every grab; log + watchdog |
| Frozen spike fails in 1 s | default plan path is the source tree | pass `--plan` explicitly |
| Models blank and unpickable after a list change | geometry outlived its Model; array `Repeater3D` recreates all delegates | re-upload on re-attach; one geometry per Model lifetime |
| A sun change stalls for a minute (WARP) | new sky light probe is prefiltered | rebuild only on noticeable sun moves; no IBL on software |
| Windows RSS reads `None` | ctypes default `int` restype truncates the process pseudo-handle | declare `HANDLE` restype/argtypes |
| `--iou` crashes / `--orient` says mirrored at 150 % display scale | pixel grid built from the logical size | build it from the grabbed image and `devicePixelRatio()` |
| A measurement changes when the flag order changes | a probe left camera/preset/ground/sun behind | run probes inside `SpikeRenderer.preserved_state()` |
| "Open time 2 s" but the first grab takes a minute (WARP) | `frameSwapped` marks submission | time request → first finished readback (`open_ms`) |
| A custom material renders the wrong colour, run "ok" | shader compile error is a `QtWarningMsg` | record Qt messages; fail on shader/QML errors |
| "Cold" open time on the second run of the day | Qt/Mesa disk caches from the first | `--cold`, and read `shader_caches.found_before_run` |
| RSS climbs ~30 MB per project reload | append-only keep-alive list of ground textures | hold only the shown texture; judge by the tail slope |
| Private bytes climb by one ground upload per cycle, and fall back when the view closes | `grab()` on a Direct3D 11 hardware window that presents no frame: the grabbed frame's uploads stay committed until a Present | not a lifetime bug if `textures_alive()` stays ≤ 2 generations; take the grab out of the loop — the curve is flat; screenshots through the offscreen path (§5) |
| A ground tile turns WHITE after another tile was re-baked, or one frame after its own re-bake | its `Texture` element was pointed at a second `QQuick3DTextureData`; destroying the first reset `textureData` to null | one texture per `Texture`, for life: a re-baked tile is a new Model (§5) |
| A tile border shows as a line only on patterned ground | the tile texture repeats: its opposite edge is blended in | `tilingModeHorizontal` / `Vertical: Texture.ClampToEdge` (§5) |
| A re-baked tile keeps its old picture | its `QQuick3DTextureData` was updated in place | a NEW Model with a new texture object per change (§5) |
| Plan ground white after a probe; the second window "differs" by ~10 luma | the same `QQuick3DTextureData` re-attached after being detached | re-upload it on re-attach; assert `probe_restore_frame_diff` < 1 |
| The second offscreen frame is an empty sky (L1.2) | a never-shown window renders one frame, then its scene is gone | one host per offscreen frame |
| A wait for frames times out although the window is visible (L1.2) | display asleep: no vertical blank, no update requests | never wait for presented frames; `grab()` |
| QML: Cannot assign to non-existent property "exposure" (L1.2) | plain `SceneEnvironment` | `ExtendedSceneEnvironment` |
| A broken shader raises, but the run's summary counts 0 errors (L1.2) | a nested message recorder replaced the outer one | recorders forward to the handler they replaced |
| `--selftest` fails with `RenderError: Qt Quick runs on the Software backend` (L1.2) | it ran under `QT_QPA_PLATFORM=offscreen` | run it with a real platform |
| "wrapped C/C++ object of type QQuickView has been deleted" on close (L1.2) | the widget that parented the window container was destroyed first | the host asks `sip.isdeleted` and reads `closed` (what a closed host answers: the contract, §12) |
| The process dies a moment AFTER a grab that returned a good image (L1.2) | the window was shown but not exposed yet (no scene graph), or was shown after its one offscreen grab | `wait_ready()` (check its answer) before `grab()`; a spent host is replaced, never shown |
| `TypeError` / `ValueError` / "not a live part" from a sink's `clear()` after the window closed (L1.2) | two owners of Model lifetime: the sink destroyed part by part with handles the dead host no longer knew | the host owns every Model; `clear()` asks it once and forgets in a `finally` |
| A file of 30+ engine tests reports only skips (L1.2) | its canary ran product code, and the product was broken | a canary of bare Qt; a positive control that a broken scene FAILS the file |
| `'OpenGL'` is not in a list that says `'OpenGLRhi'` (L1.2) | PyQt's enum member names are inconsistent | map the enum member, not a string |
| Foliage drawn beside its mesh although the clock stands still (L1.2) | the wind shader's sway is not 0 at time 0 | a rest factor that is exactly 0 at time 0 |
| `io.UnsupportedOperation: fileno` when a watchdog is armed (L1.2) | `faulthandler` writes to a descriptor; stderr was captured or replaced | dump into the log's own handle, else into the null device — the exit still happens |
| A CI step prints its verdict and nothing after it (L1.2) | `Write-Error` under GitHub's pwsh (`$ErrorActionPreference = 'stop'`) ends the step | `Write-Host "::error::…"`, the log in `try`/`catch`, `exit 1` at the end |
| Two identical frames around an edit (L1.2) | the edited item was hidden behind another | edit something the camera sees |
| `hide()` (or `close()`) never returns; the watchdog's stack dump is in the log and the process is still there (L1.2 r2) | a Python Qt message handler + Qt's render thread + the GIL | no Python message handler beside a shown Qt Quick window; `health()` for a shown host |
| A segfault on Linux one event-loop pass after an offscreen grab that worked on Windows (L1.2 r2) | the window had been shown and hidden: it has a platform window | only a window whose platform window was NEVER created has the offscreen frame |
| A blank frame of the old size, a pick that hits nothing real, `project()` == (0, 0) (L1.2 r2) | the pane is collapsed (0 px wide), or was resized a moment ago | through the host there is no such frame: `grab()` / `pick()` / `project()` answer for the window's current size or raise `HostStateError`. `wait_ready()` (act on its answer) when you need the frame; else just call and take the refusal |
| A modal "Failed to initialize graphics backend" box, then the app is gone (L1.2 r2) | nothing connected to `QQuickWindow.sceneGraphError` | connect it; read `health().scene_graph_error` |
| `reset()` "succeeds" and the old Models are still drawn (L1.2 r2) | a QML function that threw returned `None`, taken for success | a Model leaves the books only when the engine confirms it; `None` is an `EngineError` |
| A test run is killed minutes after a watchdog test passed (L1.2 r2) | a supervising process that found its release event already gone and waited on the process alone | a missing event means "released" |
| An empty folder appears in the real `%APPDATA%` after a test (L1.2 r2) | the test set `APPDATA`; Qt's standard paths follow `USERPROFILE` | give the child a profile of its own; ask `writableLocation` before anything is created |
| "The host is ready" — and the next grab is an image of the OLD size (L1.2 r3) | `showFullScreen()` delivers its resize inside the call; the swap chain is resized by the NEXT expose | the host takes a frame and compares its size with the window's, by Qt's own rounding (half a device pixel) — another size is a refusal; `wait_ready()` delivers pending events and proves "ready" with such a frame. (r3 waited for that expose instead: the next row) |
| A shown pane never becomes ready, `wait_ready()` burns its whole timeout — on a small CI screen only (L1.2 r4) | a state fact that only an `Expose` could set; no expose reaches a pane that grows or is shown beyond the screen's edge | no fact an OS paint message must set: the frame is the witness. `wait_ready()` gives up 0.5 s after the last sign of progress, whatever its timeout |
| `wait_ready(0)` takes a second (L1.2 r4) | a `processEvents()` pass outside the deadline; one Qt expose handler can take 1 s | the delivery of events is inside the timeout; a zero timeout runs none. What cannot be cut short is the ONE handler already running |
| A pick right after a resize misses; the projection is right (L1.2 r4) | the engine picks with the viewport of the frame it rendered last | take a frame first — `host.pick()` / `host.project()` do when the host knows of none for the window's size: one after a resize, none in the steady state, ONE per refusal while the target stays behind (r5: it was one per call) |
| A stale frame handed out at 125 % only; every tier green at 100 %, 150 %, 200 % (L1.2 r5) | the size check was "less than one pixel off"; Qt rounds a render target to `qRound(logical × ratio)` — and the tests' judge used the host's inequality | `abs(frame − logical × ratio) <= 0.5`; a ratio strictly between 1 and 1.5 in the tests; a judge that computes `qRound` itself and never imports the host's rule |
| A tick that projects 200 labels takes 0.4 to 0.8 s and draws nothing (L1.2 r5) | `pick()` / `project()` took a probe frame per call while the render target was behind | one probe per refusal — renewed by a sign of progress, by other facts, or after 0.25 s; the caller's tick stops at its first `HostStateError` |
| `wait_ready(5)` says False after 0.75 s, and True when asked again (L1.2 r5) | the stall bound counted wall time; the GUI thread was busy in another handler, the repaint queued behind it | count silence pass by pass: a pass of the event loop that overran its step was busy, not silent |
| `wait_ready(0.2)` returns after 1.8 s (L1.2 r5) | one pass of Qt's event loop delivers the WHOLE queue (six handlers of 0.3 s), not one event | nothing to fix from that thread: it is a nested event loop that takes user input — the workspace calls it nowhere on the GUI thread |
| A lifecycle matrix green on the dev box, red on the runner (L1.2 r4) | its windows were where the window system put them, sized for a large screen | place every window on purpose; cap sizes by `availableGeometry()`; run the walk once as on 1024 × 768; make "nothing draws the view" with an event filter instead of hoping for it |
| `[selftest_supervisor] ok=True` although the supervisor left 1.5 s into the block (L1.2 r4) | exit code 0 meant both "released" and "found nothing to wait for" | 4 for a supervisor that never supervised; the block keeps its signalled event until the supervisor has left, so "late" is 0 and "lost" is 4 |
| A healthy block is terminated a few seconds in, and ANOTHER block's log says why (L1.2 r3) | the supervisor's release event was named after the process: a finished block's late supervisor found the next block's event | a random nonce per block in the event's name; one armed watchdog per process |
| A bounded wait burns a core while the app is closing (L1.2 r3) | `QEventLoop.exec()` returns at once after `quit()` | check `exec()`'s return value; bound the passes |
| `--selftest` fails with "FAIL self-test supervisor" although every block passed (L1.2 r3) | on Windows its supervising process did not start, refused, or did not leave | that IS the failure: read the `[watchdog]` and `[selftest_supervisor]` lines of the log; a deadlock would not have been ended |

