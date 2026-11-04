## 1. Boundary rules (pinned by tests)

- The L0 spike was **dormant** — dispatched from `main()` on `--spike-q3d`, never imported at
  app start — and **L1.10 deleted it** (ADR-048's closing addendum);
  `tests/unit/test_quick3d_boundary.py::test_the_spike_is_gone_and_nothing_names_it` keeps it
  gone.
- **One engine module (L0).** Only the spike's `quick.py` imported `PyQt6.QtQuick3D`, `QtQuick`,
  `QtQml` or `QtQuickWidgets`. The production package inherited the rule as
  `ui/view3d/quick3d/`.
- **One engine package (L1.2).** In the product, only `ui/view3d/quick3d/` imports those
  bindings — and inside it only `geometry.py`, `host.py`, (L1.5, the ground's tile
  textures) `ground_tiles.py` and (#628, the items' own fill pictures) `patterns.py` do;
  `selftest.py` names them as strings to import them one by one. Pinned over the
  WHOLE tree, imports by name included
  (`__import__("PyQt6.QtQuick3D")` is an import), by `tests/unit/test_quick3d_boundary.py`,
  which also pins that app start loads neither the bindings nor the package and that the
  package never uses a `QQuickWidget`.
- **QML carries no user-visible strings** — `pylupdate6` does not extract `qsTr`, so any text
  goes through a QWidget overlay with `self.tr()` (§8.3).
- The spike's `meshes.py` was **Qt-free numpy**; it graduated into `core/scene3d/` (L1.1,
  L1.6, L1.7).
- **`core/scene3d/` is Qt-free** (standard library + numpy; AST scan in
  `tests/unit/test_scene3d_contract.py`). That is a rule about its source — no module there uses
  Qt — not about the interpreter: importing the package runs `core/__init__.py`, which loads
  PyQt6 for other `core` modules. It is the production side of the engine boundary since
  L1.1 (ADR-059, §8.29.1): an engine adapter implements `core/scene3d/sink.py::EngineSink` and is
  driven by `SceneSync`; builders are tested against `RecordingSink` with no GPU.
- **`EngineSink` has eleven methods (the eleventh, `set_selection`, is the selection ring —
  §14), and `clear()` is the one an adapter gets wrong.** After
  `clear()` the engine holds nothing — no items, no sun, no ground, no open transaction — and it
  must work at any time: inside a transaction (abort it), on an empty scene, and after one of the
  adapter's own calls failed half way. `SceneSync.reset()` recovers through it and through
  nothing else. Test an adapter's recovery the way `tests/unit/test_scene3d_sync.py` tests the
  double: fail a call in mid-transaction, `reset()`, apply, and compare with a from-scratch
  apply (`sync.expected_state()`).
- **A record's `footprints` are outer rings only; its `holes` are cut out of them.** A closed
  fence is one outer ring and one hole. Anything that gives a footprint area — a mesh, the ground
  bake, a pick shape — iterates `record.regions`. `verify_builder` refuses a solid built over a
  hole.
- **`core/plant_art/` is standard library only** (no Qt, no numpy; AST scan in
  `tests/unit/test_plant_art.py`): the plant recipe tables and the species → sprite rule, read by
  the sprite generator script (which executes `recipes.py` by file path — importing the package
  by name runs `core/__init__.py` and loads PyQt6), by `core/plant_renderer` and by the plant
  builder `core/scene3d/builders/plants.py` (L1.7, §8.22.4, §8.29.7).
- **A plant's 3D recipe is resolved from the record's `sprite_species`** — the item's own
  species string, raw — its `plant_category` and its kind: the 2D renderer's three inputs.
  `species_name` / `species_key` describe the species DATA and are for labels and lookups; a
  builder that resolved a look from them built a squash where the plan drew a pumpkin.
- **The plant builder remembers shapes** (`PROPORTION_STEP`, `SHAPE_CACHE_BYTES` in
  `builders/plants.py`): the mesh arrays it hands a sink are read-only and their colours, uvs and
  indices are SHARED between the meshes of one plant at different sizes (the same array objects;
  pinned by `tests/unit/test_scene3d_plants.py::TestShapeCache`). An adapter must copy what it
  wants to change — and cannot do otherwise: every array of a `Mesh.from_arrays` mesh sits on
  immutable memory (`setflags(write=True)` raises, on the array and on its base). The cache is
  capped in bytes (256 MB); beyond the cap a date scrub rebuilds only the plants that do not fit,
  and `shape_cache_info()` says how many shapes were built. Call `clear_shape_cache()` when a
  plan is closed: it forgets the shapes AND the request log (which lives outside the cap, up to
  about 20 MB) — at the cap a shape that was dropped comes back in two builds, so going back to
  a dropped plan costs two cold ticks and a backward scrub twice the forward one. GUI thread
  only; the cache is untested under threads.
- **The production builders are `core/scene3d/builders/`** (L1.6, ADR-059 addendum):
  `production_registry()` returns the `BuilderRegistry` the wiring hands to `SceneSync` — the
  built world's twelve kinds (`register`) and the plant builder's three (`plants.register`,
  above), no kind in both. The built world's
  rules (the top is the height by construction, polylines from the centre line — `lines.py`
  decides what a fence or wall line becomes, an unknown style is a plain panel — a polygon
  record that is not ONE plain outline (several rings, a hole, or `params["outline_resolved"]`)
  is the plain block of its regions and gets no roof, frame or leaves — corners
  bevelled beyond a mitre of two offsets, tinted parts, the mirrored palette) and the how-to
  are §8.29.6; a record's `transform.base_cm` — where a plant stands on its bed — reaches the
  engine through `engine_pose`, never through a mesh. Their shadows are NOT the 2D model's:
  the measured table (`scripts/measure_built_world_shadows.py`) is in §8.29.6 and next to the
  Shadows gate of `ogp-lush-cinematic` §1.

