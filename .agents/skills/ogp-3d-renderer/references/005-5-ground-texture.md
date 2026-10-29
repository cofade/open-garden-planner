## 5. Ground texture

- **The ground tiles' material is the endless meadow's** (roughness 1.0, specular amount 0.15,
  `Garden.qml`'s `groundTile`): PrincipledMaterial scales the sky's diffuse light by
  (1 − specular amount), and 0.92 / 0.2 measured 2–8 luma darker than the meadow at the plan's
  edge (L1.4 look review, 2026-10-19). Pinned by
  `tests/unit/test_quick3d_ground_tiles.py::TestTheTileComponent::test_its_material_is_the_meadows_so_the_plan_edge_shows_no_step`.
- **Slices of work on the GUI thread may chain posted events.** A chain of 40 posted events of
  10 ms each starved no timer: a 5 ms `QTimer` fired after the first slice, offscreen and on the
  Windows platform (L1.5 Part B, 2026-10-19) — the controller's ground passes rely on it.
- A `QImage` → `QQuick3DTextureData` (RGBA8) on a `#Rectangle` needs **`flipV: true`**: texture
  rows are north-up. Orientation probe (`--orient`): NCC identity 0.94 vs flip_v −0.10.
- **Re-attach renders white** (the texture twin of the geometry rule in §2): the IoU and
  orientation probes set `groundTexture` to null, which detaches the `QQuick3DTextureData`;
  setting the same object back left the plan ground white until the next reload (mean luma
  difference 13.1 on the frame, all of it in the ground half; llvmpipe, 640×360).
  `preserved_state()` re-uploads a detached ground. It was caught only because
  `--second-window` compared frames, then misdiagnosed once as a stale reference by a run
  without `--iou`; check a restore in pixels (`probe_restore_frame_diff` < 1), not by object
  identity.
- `QGraphicsScene.render()` always paints the canvas background — the spike swaps that exact
  colour for meadow; the production bake paints records directly (plan L1.5).
- **Ownership:** a texture created in Python is owned by Python, so something must hold it
  while QML shows it — exactly the one shown. An append-only keep-alive list grew RSS by one
  baked ground (2400×1600 RGBA ≈ 15 MB + GPU copy) per project reload, linearly; holding only
  the shown texture and releasing the old one *after* the scene shows the new one settled
  (A/B, 10 reloads, llvmpipe). Judge leaks by `leak_slope_mb_per_reload` (Theil–Sen over the
  second half of the reloads), never by total growth — the first reload adds ~70 MB either way
  — in committed memory (private bytes on Windows: its working set is trimmed and regrown, so
  v7 could not judge a leak at all), over **20 reloads**: at 10, five points could not resolve
  10 MB/reload against ±30–60 MB swings (WARP v8; llvmpipe once read 14.3 at ±35 MB). Trust
  the gate only with its positive control on the same machine (`--soak-leak-mb 25` must fail
  it). Private bytes do not see VRAM: on a discrete GPU the gate is blind to GPU-side leaks.
  The gate answers "a trend over the last ten reloads?", not "did memory grow?". On WARP every
  run (v9–v19) first dips 94–146 MB (consistent with memory the probes held: the probe-less
  controls, at a smaller window, never dip), then rises 5–10 MB per reload; the tail gate read
  1.5–9.0 (1.8 and 9.0 for identical code), and the controls read 28–34 MB/reload for the 25
  MB they hold. Longer soaks (v13–v19; v15–v19 ran 100 reloads): identical code rose +196 and
  +62 MB by reload 50, and over reloads 51–100 the five 100-reload runs (the same soak path)
  had slopes of 0.21, 2.03, 3.05, 0.08 and 3.50 MB/reload, the 0.08 an interval that includes
  zero. Over reloads 11–20 llvmpipe RSS read 0.00–0.46 MB/reload where WARP read 1.5–9.0, so
  over that window it is not Python-side growth of WARP's size (no Linux soak runs past reload
  20); a D3D11 resource retained per reload is not ruled out (WARP keeps GPU memory in private
  bytes; a discrete GPU keeps it in VRAM, unseen). Cause unidentified; locate it with an A/B
  soak, not a longer one. Record the whole curve (`leak_curve_mb`) with the verdict, and write
  numbers, not shapes: "ceiling", "slowing" and "threefold" each overreached on these curves.
- **Production ground (L1.5): tiles, not one texture.** `ui/view3d/ground_bake.py` paints the
  flat records into 512 px tiles (`core/scene3d/ground.py`: the finest of 1, ½, ¼ … px/cm within
  4096 × 4096 px and 256 tiles; every tile a crop of ONE pixel grid);
  `ui/view3d/quick3d/ground_tiles.py` shows one `#Rectangle` quad and one `QQuick3DTextureData`
  per tile, and uploads only a tile whose `bytes` changed. Concept and bounds: docs §8.29.5.
  Measured on bench_small (20 tiles, RTX 4070): first show 20 uploads; a 3 m item moved: ≤ 2
  uploads, bake 3–6 ms, a finished `grab()` 4–10 ms later.
- **The ground arrives in PASSES.** `GroundBaker()` paints for 10 ms a call (`BAKE_BUDGET_S`; at
  least one tile, nearest to the last edit first) and leaves the rest pending — stale tiles, the
  same objects as before, bare on first open. `SceneSync.ground_pending` says so;
  `sync.continue_ground()` is one more pass (one transaction when a tile changed). bench_small
  opens in 2 passes, bench_large in 8; one tile a pass on the RTX 4070: 14 transactions, each
  uploading the tile it painted. A test or a screenshot that needs the FINISHED ground uses
  `GroundBaker(budget_s=None)` or loops until nothing is pending (`render_records` loops); a
  test of the budget injects a clock (`clock=`), never sleeps. Two rules of the queue: a call
  that brings an EDIT while older tiles are pending paints the edit's own tiles first and then
  one tile of the backlog whatever the budget says (a drag used to keep 14 of 15 tiles pending
  for as long as it lasted) — so a pass is the budget plus up to two tiles; and a tile whose
  paint raises as a whole keeps its picture, is listed in `GroundBaker.tile_failures`, is NOT
  pending, and is retried by the next call that brings a change (clearing the baker instead
  made the next edit blank 15 of 16 tiles). A bake that raises anywhere else is the sync's
  `ground_failure`, and the sync calls `baker.restart()` — books forgotten, PICTURES kept until
  each tile is painted anew — never `clear()`, which is for a new plan.
- **A full tile loses its SMALLEST records, never a large one.** More than 256 records (or
  262,144 vertex passes) in a tile: the members are ranked by how much of the tile their paint
  box overlaps — box against box, ties to the topmost — and the lowest go; the rest is painted
  in z order and the tile is in `GroundBaker.capped`. A lawn under 2,000 pavers stays wherever
  its edge runs. The ranking does not know a shape: a thin diagonal line counts as large, and a
  small item on top of 256 larger ones is lost.
- **`ClampToEdge` on both axes of a tile texture.** With the default Repeat, linear filtering at
  a tile's edge blends in its OPPOSITE edge. Invisible on a uniform lawn; on a lawn with another
  colour at the tiles' far edges the luma spread at a four-tile corner was 7.9 (and 24.9 along a
  border, minified) against 0.0 clamped. A seam test needs that second lawn.
- **Lay each quad a hair wider than its tile** (`SEAM_OVERLAP_CM` = 0.02): two quads whose
  shared edge is computed twice in float32 must not leave a line of the meadow below. The
  control — quads 1 cm SHORT on every side — reads a luma spread of 48 magnified and a line dip
  of 29 in a low oblique view (0.46 without the gap). The bare plan rectangle is hidden while
  tiles lie on it (two coplanar surfaces fight for the depth buffer).
- **An attached `QQuick3DTextureData` cannot be updated in place.** `setTextureData(new)` +
  `update()` on a texture a `Texture` shows changed nothing on screen; nor did emitting
  `textureDataNodeDirty` by hand, nor setting the `Texture`'s property to null and back in the
  same turn (each variant rendered and read back: twelve cycles, the first picture every time).
  A fresh object per change shows. (`markAllDirty()` is not exposed by PyQt6 6.11.)
- **A solid's own fill is a picture per (pattern, colour) (#628 follow-up).** A lawn, path,
  terrace, driveway, generic shape or garden bed that the user gives a HEIGHT stops being
  painted by the ground bake (it is a solid), so its faces show the fill the canvas gave it:
  `MeshPart.fill_texture` -> `vcPart.baseColorMap: patternMap`, the picture being
  `core.fill_patterns.tinted_pattern_pixels` — the 2D brush's own tinted texture, RGBA8 and
  opaque, its mean the fill colour. Measured, Direct3D 11, 1000 x 400 top-down, two 300 cm
  squares at 40 cm: luma std 26.0 with `GRASS` against 0.0 with `SOLID`, at the same mean
  (121.3 / 120.8). One `Texture` per (pattern, colour), made with its data at birth and never
  re-pointed (the white rule below), shared by every Model that shows it; the sink refcounts
  the pictures and calls `EngineScene.release_fill` with the last user, so a recolour leaves no
  texture behind (`PatternTexture.uploads` 1 -> 2, `textures_alive()` 0 after the removal).
  A `var`-typed map must bind as `patternMap ? patternMap : null`: `baseColorMap: patternMap`
  with no picture logs "Unable to assign [undefined] to QQuick3DTexture*" and fails the render
  gate (PF-L3D-17). UVs are `(position + paint_origin) / 256` on the CAP — `paint_origin` is
  the record's anchor (its footprint is centred on it, so the canvas's item coordinate is
  `position + paint_origin`); `tests/integration/test_scene3d_fill_phase.py` correlates the
  mesh's own UVs against the ground bake (NCC 0.995; the opposite sign 0.759 / 0.866). The
  SIDES of a raised surface are the item's TINT (`walls_mesh`, no UVs): the canvas paints no
  texture down an edge, and one fill prism smeared a lawn's grass and a bed's soil down the
  walls (the owner's second pass) — so the default solid is TWO Models, `prism_sides` and the
  fill cap. Relief rides above the solid: a raised lawn keeps its blades, lifted to the new
  top, and `top_cm`/`fit_scale`/`verify_builder` measure only non-`ground_detail` parts (the
  blades stand 0.3-9.4 cm over the requested height, swept h = 1..200; counting them failed
  G1 for every raised lawn).
  A `fill_texture` part is not tinted (the picture carries the colour), but `set_part_fill`
  still writes `tintLinear` from the fill colour: the X-ray screen door samples no picture, and
  a white tintLinear ghosted a faded lawn white (max 255). The render gate
  `tests/integration/test_quick3d_render.py` measures a raised GRASS square's top (std > 5
  against a SOLID twin's < 0.5 at the same mean), the faded ghost (max < 235) and the lifetime
  counts (1 picture, 2 after a recolour, 0 after the removal) — a QML string match cannot see
  a white slab.

- **Water has a second albedo source (`uFill`) on a raised pool (#627).** `water.frag` keeps
  its hue rule: `BASE_COLOR` is `VAR_COLOR * uTint` — unless the part carries the plan's water
  picture (`fill_texture` on a `water` part), when it samples `texture(uFill, UV0)` and
  linearises it with the ground's polynomial. A ground pond has no picture. `water_door.frag`
  is the same shader plus the dither, and `test_quick3d_qml` pins the two apart only by that
  block: change both or neither.

- **ONE texture per `Texture` element, for life — a re-pointed `Texture` goes WHITE.** When a
  `QQuick3DTextureData` that a `Texture` once held is destroyed, Qt resets that element's
  `textureData` to null, whatever it holds by then (a QML binding `textureData: someProperty`
  does not run again). Measured, two tiles, RTX 4070 and WARP: tile A re-textured, then tile B,
  then a frame — A is white; a tile re-textured, a frame, its replaced texture let go — white one
  frame later. Hidden for a whole story because every scenario re-baked the SAME tiles after each
  frame (which sets the property again) and the hardware window presented no frames (so the
  release after a frame never ran). So a re-baked tile is a NEW Model with its own texture
  (`ground_tiles._replace` = drop + create), like "one geometry per Model". Test updates WITHOUT
  a frame between them, on different objects, and look again one frame later.
- **Count texture objects on the C++ side, not Python references.** `ground_tiles.textures_alive()`
  counts the textures made (held in a weak set) whose C++ object `sip.isdeleted` says still
  exists: over twenty full re-bakes of 16 tiles it never exceeds 32 (the shown generation and
  the one it replaced), and reads 320 with the spike's keep-alive list. A Python-owned `QObject`
  subclass instance IS destroyed when Python lets go of it. (It first counted down on Qt's
  `destroyed` signal; a Python callable on `destroyed` may never run once the cyclic collector
  reached the wrapper first, so the product hangs none — `test_sim_clock_subscription.py`.)
- **No repeated `grab()` on a live host that is not presenting — it is the grab that grows a
  Direct3D 11 process, not the upload.** Direct3D frees what was released when a frame is
  PRESENTED; a frame rendered by `grab()` is rendered (its textures are uploaded for it) and
  never presented. Twenty full re-bakes of a 16 MB ground on the RTX 4070 while its window
  presented 0 frames, private bytes per re-bake: a `grab()` after every re-bake **+16 to
  +17 MB** (one generation, given back only when the view closes; 32 texture objects alive, never
  more); a `grab()` every fifth **+3.2**; NO `grab()` **+0.0** (nothing is rendered, so nothing is
  uploaded). Flat in all three on WARP (33–41 frames presented), on OpenGL, and on the same
  hardware window once it presented (38 frames, a grab a cycle: +0.04). The first diagnosis here
  — "keeps every upload until a frame is presented; apply edits no faster than frames" — came
  from a soak that grabbed every cycle, and its remedy targeted the wrong variable. So: (1) a
  leak soak takes NO frame in its measured loop (a live view takes none) — and asks the QML
  scene nothing there either: per cycle it reads counters on the Python side — and is then an
  unconditional gate; the grabbing soak is its control. Say which CELL a run measured: in a
  hardware window that presents nothing the soak renders nothing, so it shows the process side
  only (half a gate); a hardware window that presents is a manual check ("watch Commit size
  while dragging a lawn with the display on"). (2) A still picture of a live view goes
  through the offscreen path (`offscreen.render_records`: its own hidden view, closed after one
  frame — everything is given back), never through repeated `host.grab()`. (3) Record
  `host.health().frames_presented` with every memory curve. Why that window presented nothing is
  not established (an OpenGL window on the same GPU presented 45 frames in the same session).
- **Compare a top-down frame with a baked image like with like.** The truth view is linear
  light and each frame pixel covers several texels: the bake against the frame scored NCC 0.93
  compared naively and 0.98 after linearising the bake and averaging the texels a pixel covers
  (flips: 0.08 / −0.11 / −0.07 either way).

