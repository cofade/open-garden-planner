## 12. The production package — `ui/view3d/quick3d/` (L1.2)

Concept and module map: §8.29.2 of `docs/08-crosscutting-concepts/README.md`; the decision and
every measurement: ADR-048, addendum L1.2. What you need at the keyboard:

- **Sink and host.** `adapter.Quick3DSink(host)` is the `EngineSink`; `host.Quick3DHost(size)`
  is the `QQuickView` and implements the sink's `EngineScene` — it OWNS every Model.
  `SceneSync(Quick3DSink(host)).apply(records, sun=…, ground=…)` is the whole wiring.
  `host.container()` embeds it; `host.pick(x, y)` returns a `PickHit` in the SCENE frame;
  `host.engine_parts()` reads the Models back from the QML scene (what the engine holds, not
  what the sink believes).
- **The host's states.** `host.state` is `lifecycle.state_of` over the facts the host reads
  from Qt on every call. **The contract — the facts, the six states, what each promises,
  which call is legal in which, what `wait_ready()` means, what raises what — is the module
  docstring of `src/open_garden_planner/ui/view3d/quick3d/lifecycle.py`. Read it THERE; it
  is deliberately written down nowhere else** (it stood in nine places once, this skill
  among them, and three were wrong; a test now fails a second copy of the state table). At
  the keyboard: **the workspace needs `wait_ready()` nowhere on the GUI thread** — it is a
  NESTED EVENT LOOP that takes user input. A click, a hover, a tick that draws just calls
  `host.pick(x, y)` / `host.project(...)` in `try` / `except HostStateError`, and **a tick
  stops at its first `HostStateError`** (while the render target is behind, the next call
  gets the same refusal without another frame). Where a frame must be HAD and the caller
  can wait — an export, a tool, a test — `if not host.wait_ready(): …`, and act on the
  answer; never count event-loop passes (§6). It starts no pass once its timeout is up
  (1 s by default) and returns within that plus whatever was queued on the event loop —
  one pass delivers the whole queue — and the first show of a process takes 0.7 to 1.7 s;
  it says False after 0.5 s of silence. Never from a timer slot, a sync tick, a paint or a
  resize handler. `grab()`, `pick()` and `project()` never pump; each answers for the
  window's current size or refuses. A
  refusal is a `HostStateError` whose text names what is missing and what to do. Under
  the software scene graph `host.renders_3d()` is False and `grab` / `pick` raise
  `EngineError`.
- **Recovery.** After a sink call raised: `sync.reset()` (it calls `Quick3DSink.clear()`, which
  is legal in a half-applied transaction and on a dead host), then `sync.apply(...)`. When the
  host itself died: `sink.attach(fresh_host)` in between. Check with
  `sink.state() == sync.expected_state()` AND against the engine: `host.part_count()`,
  `host.engine_parts()`. A LIVE engine that cannot destroy a Model keeps it in the host's
  books and raises — `reset()` stays poisoned and the next one tries again; the sink refuses
  `begin()` until a `clear()` went through. One sink per host: a host that holds Models is
  refused by `Quick3DSink(host)` and by `attach`.
- **Trouble in a SHOWN view: `host.health()`** — poll it on the GUI thread (a timer). It
  returns `HostHealth(frames_presented, qml_warnings, qml_warning_count, scene_graph_error)`
  with `.ok`, in every state; each item was also logged when it arrived. There is NO message
  watch (`watch_messages` / `engine_errors` were removed: they deadlock, §6). A shader of a
  shipped material that does not compile is NOT in it — that is checked before release: the
  render tier and `--selftest` compile every shipped shader under a recorder.
- **One frame without a window:** `offscreen.render_records(records, shot=TopDownShot(...),
  sun=SunState(...), ground=GroundSpec(...), size=(w, h))` → `OffscreenFrame` (`.image`,
  `.rgba()`, `.open_ms`, `.build_failures`, `.adapter` with `graphics_info=True`). A QML or
  shader error, or a backend without 3D, raises `RenderError`. For processes that own
  themselves — a tool, a test, the self-test — NOT for the running app: it blocks 0.4–1.3 s
  and builds and destroys a graphics device per call. Silent unless `log=` is passed. It
  records Qt's messages with a Python handler, so it REFUSES (`RenderError`) while a Qt Quick
  window is shown in the process; `frame.qt["other_threads"]` must be 0 (the render tier and
  the self-test both require it).
- **The engine boundary without a GPU.** Under the offscreen platform `Garden.qml` loads and
  Models are created, posed and read back — no pixels, but every sink call, the state rules,
  the teardown orders and the recovery are checkable: `tests/ui/test_quick3d_host.py` (default
  tier). Its canary is bare Qt with inline QML — NO product code — so a broken scene file
  fails the tests instead of skipping them; `render_records` raises `RenderError` naming the
  `Software` backend there.
- **The render tier** (opt-in, opens windows):

  ```bash
  # Windows (Git Bash) — the real GPU, then WARP
  OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_quick3d_render.py \
      tests/integration/test_quick3d_engine.py tests/integration/test_quick3d_selftest.py \
      tests/integration/test_quick3d_lifecycle.py
  OGP_RENDER3D=1 QSG_RHI_PREFER_SOFTWARE_RENDERER=1 venv/Scripts/python.exe -m pytest \
      tests/integration/test_quick3d_render.py tests/integration/test_quick3d_lifecycle.py
  # Linux
  OGP_RENDER3D=1 QSG_RHI_BACKEND=opengl LIBGL_ALWAYS_SOFTWARE=1 \
    xvfb-run -a -s "-screen 0 1920x1080x24" venv/bin/python -m pytest \
    tests/integration/test_quick3d_render.py tests/integration/test_quick3d_engine.py
  ```

  No Linux machine? The CI job's stack fits in a container: `ubuntu:24.04`, the job's apt
  packages plus what a bare image lacks for Qt (fontconfig, dbus, nss, the X11 and xcb
  libraries), `uv sync --locked --python 3.11 --all-extras --group build`, then the Linux
  command above inside it. That is how xcb was measured before a push in review round 2 —
  the Windows numbers had said nothing about it. The matrix's children get their environment
  from `quick3d_render_support.isolated_env` / `render_env` only: never hand a child the
  developer's `APPDATA` or profile (`USERPROFILE` on Windows, `HOME` elsewhere). The app's
  SETTINGS are a registry key on Windows, which no variable moves: the helper puts a
  `sitecustomize.py` first on every child's path, which rebinds the store's names the
  moment the child imports `app/settings.py` (docs §8.8). A probe you run by hand gets
  none of this — rebind `app.settings.ORGANIZATION_NAME` / `APPLICATION_NAME` to a test
  key BEFORE anything builds a store, or loading a plan writes your own Recent Files. And
  pytest-qt installs a Python Qt message handler for every test: a test that shows a host IN
  the pytest process is marked `@pytest.mark.no_qt_log`. (Under `offscreen` Qt names no
  render loop and nothing ever hung — an absence, not a guarantee; on a real platform it is
  a deadlock.) Real-platform hosts live in child processes.

  The driver alone, to look at frames (`<out>/*.png`, `result.json`, `render.log`):
  `venv/Scripts/python.exe tests/integration/quick3d_render_driver.py --out <out> --scenarios
  truth,materials,rest,states,edits,recovery,pick,sun,integration,embed`. One call order of the
  host's lifecycle, in a process of its own: `venv/Scripts/python.exe
  tests/integration/quick3d_lifecycle_child.py show_grab` (it lists the orders when called
  without one). From a git worktree set `PYTHONPATH` to that checkout's `src` first for
  anything that is not pytest.
- **The self-test's 3D block:** `quick3d/selftest.py::run_selftest()`; the log is
  `OpenGardenPlanner-selftest-3d.log` in the app's log directory (beside `app.log`), or
  `OGP_SELFTEST_LOG`. The whole `--selftest` runs under ONE watchdog (300 s, the reason in the
  log before the exit) — `faulthandler` has a single timer per process, so ONE watchdog per
  process at a time: a second `runlog.watchdog` while one is armed raises `WatchdogError`.
  It is SUPERVISED: a second process (the exe with the INTERNAL flag `--selftest-supervisor`;
  from source the base interpreter running `runlog.py`) terminates the first at 310 s if it
  is still there. It acts for one block of its own parent process only — pid, creation time,
  a random nonce per block — and refuses anything else with exit code 2. Its exit code says
  what it did: 0 it held the block's release event (released, or it ended a hang), 4 it
  found no block to wait for and never supervised (review round 4: that used to be 0), 3
  it failed itself (round 5: also when its own wait fails — that was 0 too). The log's `[watchdog] armed=True … supervisor=process <pid>` line says
  it started, `[selftest_supervisor] ok=True` that it was released and left, a
  `[supervisor] fired=True` line that it had to act. On Windows the self-test FAILS without
  it (`FAIL self-test supervisor -> …`). There is no start timeout while the block runs;
  the block waits 15 s at its end for the supervisor to have come up and left. Never run
  `--selftest` under `QT_QPA_PLATFORM=offscreen`.
- **Numbers** (RTX 4070 / WARP, 2026-10-11): open of `bench_small.ogp` (98 records, 87 Models)
  to the first finished readback 0.40–1.11 s / 0.17–0.39 s (the device creation varies);
  edit → finished readback median 7.1–7.5 ms (p95 18.0) / 23.2–26.5 ms; pick 0.01–0.2 ms;
  shadow IoU vs the analytic 2D shadow 0.976–0.978 at 35° and 480 × 360; engine import 17 ms
  on top of 17 ms for `core/scene3d`. The render tier after review round 2: 96 tests, about
  four minutes on either adapter (237 s / 251 s, the machine busy); on xcb + llvmpipe in a
  container 88 passed and 8 skipped in under two minutes. After round 3 (100 tests, the
  seeded random walk among them): 99 passed and one control reported in 321 s on the GPU;
  97 passed, the two hardware-only budgets skipped and the control reported in 244 s on
  WARP; 92 passed and 8 skipped in 184 s in the container. After round 4 (104 tests: a
  second walk as on 1024 × 768, rows for the pane beyond the edge, a 2 × 60 px pane and a
  view that nothing draws): 103 passed and one control reported, not asserted, in 458 s on the GPU; 101 passed, the two hardware-only budgets skipped and the control reported, in 355 s on WARP; 96 passed and 8 skipped in 241 s
  in the container. After round 5 (105 tests: the 125 % row joined): 104 passed and one control reported, not asserted, in 411 s on the
  GPU; 102 passed, the two hardware-only budgets skipped and the control reported, in 287 s on WARP; the lifecycle file on xcb in the container 41 passed, 4 skipped in 159 s.
- **Not measured:** real display scaling of the operating system (the ratios between 1 and 3
  were set with `QT_SCALE_FACTOR` on a 100 % screen); what the one frame `pick()` /
  `project()` take after each resize costs with the display awake (asleep: about 1 s a
  step on the GPU, 25 ms on WARP); platforms that un-expose an occluded window (macOS, Wayland) — a visible,
  covered host may read `starting` there (`wait_ready()` then says False after 0.5 s, as
  for every other cause); a change of the device pixel ratio in mid-session (L1.3's manual
  checklist: drag the window between two monitors); what GitHub's Windows runner does with
  a pane beyond its screen under the round-4 tree; `frozen-selftest.yml` on any runner —
  the FROZEN exe as its own supervisor never ran on one (from source the supervising
  process does start inside a GitHub job); macOS; an integrated GPU; a display scale other
  than 100 %; a failed device creation on OpenGL or Vulkan.

