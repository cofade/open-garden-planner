## 8. Screenshots and CI rendering

- **Open time** (criterion 5) runs from the user's request to the first *finished readback*:
  ground bake, model build, QML load, scene apply, show → grab (`open_ms`,
  `open_breakdown_ms`). Never stop the clock at `afterRendering`/`frameSwapped`: that marks
  submission, and on a software rasteriser the real cost lands in the next grab.
- **Cold vs warm must be recorded, not assumed.** Qt keeps `q3dshadercache-*`,
  `qtpipelinecache-*` and `qmlcache` in the app's cache folder (`~/.cache/<argv0 basename>/`,
  `__main__.py` for `python -m`) and `qtshadercache-*` one level up; Mesa keeps
  `mesa_shader_cache`. The spike lists what it found (`shader_caches.found_before_run`).
  `--cold` sets `QT_DISABLE_SHADER_DISK_CACHE`, `QSG_RHI_DISABLE_DISK_CACHE`,
  `QT_QUICK3D_NO_SHADER_CACHE_LOAD`, `QML_DISABLE_DISK_CACHE` and `MESA_SHADER_CACHE_DISABLE`
  (all in the 6.11 runtime): nothing is loaded **or written**. GPU drivers keep their own
  shader caches, which no flag reaches. On llvmpipe cold vs warm is noise (first frame's
  render cost dominates); the GPU decides.
- **A shader that does not compile is only a warning.** `QSpirvCompiler: Failed to parse
  shader` and `Failed to compile fragment shader` arrive as `QtWarningMsg`, and the frame
  still renders (measured: one renamed call in `water.frag` changed 449 pond pixels' colour,
  exit 0, `status: ok`). Record every Qt message
  (`ui/view3d/quick3d/qt_messages.py` since L1.2 — the spike had its own:
  `qInstallMessageHandler`, into the log and `metrics.json`) and
  fail on shader/QML errors — a frozen exe has no stderr to read them from. A clean llvmpipe
  run emits no Qt messages at all, so the gate has no false alarms there.
- **Aim probes at the actual view size** (measured in the spike, `SpikeRenderer.view_size()`), not the requested
  one: a window larger than the screen is clamped.
- **Which device rendered? (L1.2)** `rendererInterface().graphicsApi()` names the API, not the
  adapter. Switch on Qt's `qt.rhi.general` debug output
  (`QLoggingCategory.setFilterRules("qt.rhi.general.debug=true")`) and read it from the message
  handler: Direct3D lists every adapter and prints `using this adapter` after the chosen one;
  OpenGL prints the context's `RENDERER`. `quick3d/qt_messages.py::graphics_adapter` does it.
  **Force the software rasteriser on Windows with `QSG_RHI_PREFER_SOFTWARE_RENDERER=1`** — the
  log then says `Microsoft Basic Render Driver` (WARP), which is what a GPU-less runner has.
- **A recorder that replaces the Qt message handler must forward (L1.2).**
  `qInstallMessageHandler` keeps ONE handler: a recorder installed for one frame hid a shader
  error from the recorder of the whole run. `qt_messages.install` chains to the handler it
  replaced. Warnings that belong to the machine are a class of their own, listed exactly —
  so far one: `qt.qpa.screen: "Unable to open monitor interface to …"` (display asleep).
- **Classify a Qt message by its level first (L1.2, review round 1).** Only a WARNING is
  promoted to an error by its text; debug and info lines are information whatever they say.
  With `qt.rhi.general.debug=true` switched on, the first version ran the error patterns over
  debug output — the wording of a Qt debug line could have failed a release. And switch that
  rule off again: `QLoggingCategory.setFilterRules` holds ONE rule set per process and has no
  getter; `qt_messages.graphics_info()` is a context manager that nests.

- **Linux:** the `offscreen` QPA selects the *software* scene graph, which cannot render 3D.
  Use `xvfb-run` + `QT_QPA_PLATFORM=xcb` + `QSG_RHI_BACKEND=opengl` (+ `LIBGL_ALWAYS_SOFTWARE=1`
  in a container). Packages: `libegl1` (the QtQuick3D binding links libEGL), `libxcb-cursor0`
  (xcb plugin). As root, Qt WebEngine needs `QTWEBENGINE_DISABLE_SANDBOX=1`.
- **Windows runner** (windows-latest, no GPU): `Direct3D11Rhi` on WARP (the spike printed
  PyQt's enum member name; the production host says `Direct3D11` — §2). Frozen exe: QML load
  1.0–2.7 s, first *presented* frame 2.0–3.0 s, 960×540 low 11.5–14.2 fps / high 4.3–4.8 fps
  (runs v3/v4, `docs/09-architecture-decisions/adr-048-evidence/`). `frameSwapped` marks
  submission, not completion — on a software rasteriser the real cost lands in the next
  readback, so time open-to-ready with a grab. **Each new sky light probe costs 40–85 s
  once** on WARP (in the frames or the grab right after a sun change); later
  grabs of the same sky take 20–500 ms, and `QSG_RENDER_LOOP=basic` changes nothing. Never
  rebuild the probe per frame; on software rendering drop image-based light. Evidence run
  v1's 56-minute "hang" was this cost, times many shots, with no log.
- **A frozen GUI exe has no stdout** (`print` is a no-op; #291 is the precedent). The spike
  writes `<out>/spike.log` (flushed per line), rewrites `metrics.json` after every phase, and
  `--watchdog-s N` arms `faulthandler` to dump every thread's stack into the log and exit
  non-zero. Use the same pattern for any headless render path.
- Commands (Linux render tier, opt-in):

  ```bash
  OGP_RENDER3D=1 QSG_RHI_BACKEND=opengl QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 \
    xvfb-run -a -s "-screen 0 1920x1080x24" \
    venv/bin/python -m pytest tests/integration/test_quick3d_render.py -n 0
  ```

  (Until L1.10 the tier's only file was the spike's `test_spike_q3d_render.py`; CI's `render3d`
  job runs the engine package's render files on Linux and on Windows WARP, §12.)

