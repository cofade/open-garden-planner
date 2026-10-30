## 13. The engine inside the app — the workspace (L1.3)

Concept: docs §8.29.3; decisions and every number: ADR-060 and the ADR-048 addendum "L1.3"; the
test patterns: docs §8.10.9. What the ENGINE taught once it ran inside the real app:

- **`releaseResources()` LEAKS same-size `QQuick3DTextureData` textures (Qt 6.11.0, #532).**
  `QSSGBufferManager::clear()` (`qssgrenderbuffermanager.cpp` ~2049–2052) iterates
  `customTextureMap` with `++it` while `releaseTextureData(it.key())` erases through its own
  lookup (~1516); Qt 6's `QHash` back-shifts the next entry of a collision run into the freed
  slot, `++it` skips it, and the final `clear()` of the map drops it unreleased. The key's hash
  (~2290; `qssgrendertexturedata_p.h` 74–77) is size / depth / format / transparency only, so
  same-size textures all collide: about half leak per release (WARP, 16 × 512²: +10.8 MB a
  cycle). Static textures too (release, then a redraw). Distinct sizes only help below ~16
  textures; in-place `setTextureData` updates show a STALE picture; `Texture.sourceItem` images
  avoid the map but still kept one generation per rebuild in the workspace (holder unknown).
  The `imageMap` loop (~2043–2046) has the same pattern; the mesh branch copies keys first.
  Measured on the L1.5 branch, 2026-10-19 (probes in the plans' `scratch/L1.5/fu22/`).
  **In the product EVERY release leaks** (the bake asks for none, but item changes do —
  64 retired Models + 0.5 s quiet, or 512 at once; a date change on a planted plan retires
  every plant): up to ~42 MB per release for the largest ground (4096² px, ~85 MB with
  mips). Gate what ships: the workspace's G7 soak runs with the bake ON against
  `LEAK_BOUND` + 0.6 × its OWN tile-texture bytes per release × releases per reload
  (the driver reports `ground_texture_mb`) — not with the bake off, not against a fixed
  ceiling (L1.5 review 3).
- **#532 upstream: QTBUG-151940 (filed 2026-10-30); a bump to 6.11.3 or 6.12.0 does not fix
  it.** Read on 2026-10-30, the `clear()` loop is unchanged in qtquick3d v6.11.3, v6.12.0 and
  `dev` (eaf90eeb8c32). The report's reproducer
  (`docs/09-architecture-decisions/adr-048-evidence/qtbug-151940/`, no project code) leaks the
  same on 6.12.0 as on 6.11.0, with the official `qml.exe` 6.12.0 and with the PyQt6 6.11.0 /
  6.12.0 wheels: 6 to 8 of 16 same-size 512² textures per release on D3D11 (hardware and
  WARP), Vulkan and OpenGL; none without the release. The share depends on the process's
  `QHash` seed (`QT_HASH_SEED=0`: 6 of 16 in every run). The re-check after a Qt bump: docs
  §8.29.5 known limit 11 and TD-040. How the reproducer counts: reference 18.
- **Qt keeps graphics state for every Model it ever drew — release it.** After a Model is
  destroyed, Qt Quick 3D still holds its cached per-draw-call state: about 62 kB per Model, about
  190 kB when it casts into the sun's two shadow cascades, independent of the mesh's size
  (measured with 300, 3,000 and 12,000 vertices). Only `QQuickWindow.releaseResources()` gives
  it back — `Quick3DHost.release_cached_resources()`, 2 to 10 ms, and the next frame is the same
  frame. More frames, the QML engine's garbage collection, `clear()` instead of single
  destroys: no effect. The workspace counts what each pass destroyed (`TickReport.retired`)
  and releases when 64 piled up and the pipeline is quiet, or at once at 512
  (`src/open_garden_planner/ui/view3d/workspace.py`). **Anything new that creates and destroys
  engine objects per edit or per tick — a ground texture per bake, a selection outline, plants
  regrown by an animated date — must be counted the same way, or measured to leave nothing.**
  20 rebuilds of `bench_small` in the production host, the view presenting, no readback:
  19 MB per rebuild without the release, 2.0 with it (the large plan 65 and 6.4; WARP 20 and
  3.3; over 60 rebuilds 1.8).
- **Creating and destroying a Model is never free.** After the release 15 to 20 kB per
  destroyed Model remain (2 MB per rebuild of 98 Models, linear over 60) — and it is not
  graphics state: the same rebuilds in a view that draws nothing leave 1.5 MB each. Bare Qt,
  no product code, nothing drawn, `createObject()` then `destroy()`, the QML engine's
  collector called every round: 0.78 kB per `QtObject`, 2.2 per `Model`, 3.4 per `Model`
  with a `PrincipledMaterial` — straight lines over 120 rounds. So: do not design a feature
  around replacing many Models per tick (a date played back regrows every dated plant).
  Untried ways out: keep the Model and hand it a new geometry; scale instead of rebuilding.
- **Never take a frame from a live, shown host by yourself — a readback is a frame that is
  never presented.** `grab()` (and `wait_ready()`, `pick()`, `project()`, which need a frame)
  renders a frame of its own: `grabWindow()` emitted `afterFrameEnd` 0 times in 40 grabs.
  What that frame holds comes back when a PRESENTED frame ends — and with the display asleep
  Windows presents one frame and no more (§6). Twenty rebuilds with the view's frames
  withheld: 1.5 MB per rebuild without a readback (nothing is drawn, dedicated GPU memory
  does not move), 8.5 with one readback per rebuild, 26 without the release; on WARP 1.2 and
  6.2. So no steady path of the workspace — the pass, the health poll, a timer, a resize,
  the splitter — calls any of the four (a recording stand-in host and a source scan pin it);
  a picture for a file goes through `quick3d/offscreen.py`; a click that picks is a user's
  action, once. **The pipeline is NOT paced or held for a view that presents nothing** — that
  was built and taken out again: it fixed nothing and added a way to get stuck.
- **A memory soak takes no frame inside its measured loop.** One before, one after (they must
  be equal), and in between it waits on `health().frames_presented`. A soak that reads back
  every cycle measures the readback — this one did, twice, and a wrong rule was built on
  it. Judge it presenting AND with frames withheld (`scenario_soak(frames="withheld")`), and
  let the children present by timer (`run_gate` sets `QT_D3D_NO_VBLANK_THREAD=1` by default)
  so that no scenario depends on whether the box's display is awake.
- **Software rendering is chosen per window, not per process.**
  `QSG_RHI_PREFER_SOFTWARE_RENDERER=1` is read ONCE: set before the first Qt Quick window it
  selects WARP, set after it does nothing. `QQuickGraphicsConfiguration.setPreferSoftwareDevice(True)`
  on the window works at any time (`Quick3DHost(prefer_software=True)`; Qt's log then names
  "Microsoft Basic Render Driver"). That is the workspace's compatibility mode after a start
  that died (`src/open_garden_planner/ui/view3d/init_guard.py`).
- **Nothing overlays the view; its input is its own.** The view is a native window: a sibling
  widget is drawn UNDER it. Notices go into a strip above it or replace it. Mouse, wheel and
  keys go to the native window — `host.install_event_filter(watcher)` sees them; pass on every
  key you do not use and Qt's shortcut map keeps working with the keyboard in the 3D window
  (measured: Ctrl+Z, Alt+1).
- **Embedding does not cost the 2D side.** The main window stays a raster window
  (`surfaceType() == RasterSurface`); a pan step of the canvas beside the live view costs 1.04
  times what it costs alone (bound 1.3).
- **A pass is a posted event.** `QTimer.singleShot(0)` waits behind every timer that is due
  (the large bench plan: 5 % of the passes more than 228 ms late); a posted event at HIGH
  priority overtakes the scene's own queued `changed` and costs a second snapshot per edit.
  Normal priority.
- **Measure edit → frame inside the pass.** The readback is taken in a slot on the controller's
  `applied` signal. "Edit, `processEvents()`, grab" measures the 2D side's turn with it (56.6
  ms p95 instead of 17.6). `bench_small`, Split at 1600 × 900, RTX 4070: p50 15.2 / p95 20.6 ms;
  maximised at 5120 × 1369: 18.5 / 29.2; `bench_large`: 29.9 / 80.3 (the snapshot alone is 15
  ms there — a whole-plan snapshot is O(total vertices) even fully cached, so it runs on a
  real change only, never on a timer).
- **The first pass of a plan freezes the GUI thread for the sum of its items.** The workspace
  starts it from the PAINT of "Building the 3D view…", not from a timer that hopes the paint
  came first.
- **Dedicated GPU memory can be read without a counter.** `IDXGIAdapter3::QueryVideoMemoryInfo`
  through `ctypes` — `tests/integration/workspace_gate_measure.py`, `gpu_dedicated_mb()` — gives
  the calling process's usage on the adapter's local segment. With the release in place it
  rises ONCE, by about 90 MB over the first releases (289 → 378 MB), and is flat after; in a
  view that presents nothing it does not move at all.

Running the workspace's tiers:

```bash
# default tier (no GPU): the engine replaced at Workspace.engine_factory
venv/Scripts/python.exe -m pytest tests/integration/test_view3d_workspace.py \
    tests/integration/test_view3d_workspace_widget.py tests/integration/test_view3d_sync_controller.py
# render tier: the app's own main() in a child, on a throw-away settings store (about 9 minutes)
OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_view3d_workspace_render.py -s
# the frozen gate build (the product recipe plus one runtime hook), then its three scenarios
venv/Scripts/python.exe -m PyInstaller installer/workspace_gate.spec --noconfirm --distpath <dir> --workpath <dir>
OGP_RENDER3D=1 OGP_WORKSPACE_GATE_EXE=<dir>/OpenGardenPlannerGate/OpenGardenPlannerGate.exe \
    venv/Scripts/python.exe -m pytest tests/integration/test_view3d_workspace_render.py -k frozen
```

**Never script the product exe or `-m open_garden_planner` onto a plan.** A plan load writes
Recent Files and a clean close the window geometry, into the user's own settings. The gate's hook
(`tests/integration/workspace_gate_hook.py`) moves the store first and ends the process (exit
code 97) before a store under any other organisation exists.

**Not measured (L1.3):** where the 15 to 20 kB per destroyed Model go beyond Qt's own floor; why
dedicated GPU memory and committed memory step up ONCE with the first releases; the soak in a frozen
exe or on a CI runner (the workspace's render tier is not in CI's render job); time to photons
(edit latency ends at a finished readback); a change of the device pixel ratio in mid-session
and OS display scaling (manual checklist); the real map picker beside the 3D view (the
automated check uses its engine on a local page).

