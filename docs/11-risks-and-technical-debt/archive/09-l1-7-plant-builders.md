# Archive 09: Phase 17 L1.7 plant builders

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.12 What the plant builders taught (Phase 17 L1.7, #385)

Most gates of the plant story passed the first time they ran. The entries below are about what
that did and did not prove (ADR-059 addendum "plant art v0", §8.29.7). Three of them were found by
looking at a render, not by a number.

- **A gate satisfied by the repair that broke the thing: a cushion floated 9 cm above the
  ground with `min z == 0`.** The base gate says the lowest vertex is at 0, and the first `_fit`
  guaranteed it by subtracting the minimum. Then shell leaves were allowed down to the ground:
  one leaf of a lavender dipped 9 cm below the cushion's base, the fit lifted the whole plant by
  those 9 cm — 13 % of its height — and the gate held: one vertex touched the ground and the
  plant hung in the air (a hydrangea 11 cm, a petunia 15 % of its height). Found on a sanity
  render (the side view); 59 of 123 recipes once counted. Fix: what dips
  below the ground is pressed onto it (as the lobes always were); a plant is only ever set
  *down*, never lifted. Pinned by counting, in
  `tests/unit/test_scene3d_plants.py::test_every_recipe_fits_the_plan_s_numbers`: at least six
  vertices within 0.5 % of the height above the ground (a trunk's foot ring has eight; the
  floating plants had one to three). *"The minimum is zero" is true of a floating object with one
  hanging thread. Ask how much of the thing meets the constraint, not whether its extreme does —
  and never make a constraint hold by translating the result.*
- **What a number cannot say: the crowns were bald on top.** Every gate was green — height,
  spread, triangles, hue, clones — and the first look through an engine (the dormant spike's
  renderer, a scratch script) showed mounds and crowns with a smooth bare top and a skirt of
  leaves. The shell leaves had been placed on an ellipsoid *envelope*; where a lobe reached the
  envelope they were inside it, and between lobes they hovered. Fix: `_on_lobes` casts each leaf
  from the crown's heart onto the outer surface of the lobes
  (`test_shell_leaves_are_set_on_the_lobes`). Moving the leaves onto the lobes then made the
  lobes the plant's outline, and the canopy-circle measure of the next entry went from 1.07 to
  1.20 for a climber and from 1.05 to 1.14 for a mound until their lobes were made regular too —
  the stress test caught that one. *Look-dev is a gate. A story that may not approve its own look
  still has to look.*
- **A fix made by eye stays unpinned until a number can see it: the placeholder's rim.** Through
  the same renderer the placeholder's rim read as a polygon at close range; 24 sides became 48,
  and nothing asserted it. A mutation check — one rule broken at a time on a copy of the tree, 45
  breaks, each run against the story's tests — killed 44. The survivor was a placeholder with
  *eight* sides: the bounding box, the farthest vertex and the smooth normals of an octagon are
  those of a circle. Pinned now by the area of the rim polygon, at least 99.5 % of the canopy
  circle (48 sides cover 99.7 %, 24 cover 98.9 %, 8 cover 90.0 %):
  `tests/unit/test_scene3d_plants.py::TestPlaceholder::test_its_rim_is_the_canopy_circle`. *After
  a fix made by looking, name the number that would have seen the defect. If there is none, the
  fix is a habit, not a gate.*
- **A bounding box that fits is not a footprint that fits: a "fitted" plant stood 39 % outside
  its canopy circle.** The spread gate is the bounding box (widest span = canopy diameter ± 10 %),
  and the first `_fit` made it exact for every archetype. An assertion the gate does not ask for —
  no vertex further than 1.10 canopy radii from the plant's axis — failed on the sixth recipe (a
  fig tree, 1.18). Measured for every archetype it read 1.39 for `feathery`, 1.37 for `allium`,
  1.23 for `flower`, ~1.2 for every leaf shell: a plant whose few long blades point anywhere fits
  its box and pokes out of its circle at the diagonals. Scaling the farthest vertex onto the circle instead only moves the lie — the box then
  spans 72 % of the diameter. Neither fit can repair an irregular outline. Fix: the elements that
  draw an outline are regular by construction (`_RIM_REACH`, `_RIM_JITTER` in
  `core/scene3d/builders/plants.py`), stray shell leaves are pulled back onto the circle before
  the fit, and the box stays exact. That left the reach a measurement — 1.092 radii at most over
  117,000 builds, because the fit's xy scale carries leaf tips that stood on the circle a little
  past it; what became of that number is under "what the second review found", below. *A truth
  gate measures one projection of the truth; measure the neighbouring one before trusting it.*
- **An instrument that under-samples reports a difference that is not there: two identical hedge
  drums "differed" by 26 %.** The no-clones gate compares side silhouettes of two ids on a
  32 × 32 occupancy grid. The first instrument sampled every triangle at 15 points; a hedge's
  side triangles span 27 rows of cells, so each silhouette was a different random sieve and two
  drums — the same shape, by design — scored an IoU of 0.74. The gate was green *because* the
  instrument was broken. Sampled on a lattice finer than half a cell, the same two drums scored
  0.999: clones. Fix, in this order: the instrument (`side_silhouette`), then the hedge (a batter,
  a bulging side, an uneven top; and after the review a shoulder cut higher or lower and
  squarer or rounder — over 30 ids a recipe two sections are 0.975 alike at most now, 0.981 in
  the second review's sample). *Give every metric a case whose answer you
  know: two builds of one id must score 1.0, and something you believe to be a clone should score
  close to it. A gate that has never failed has not yet been shown to work.*
- **"Byte-identical" needs to say against which bytes: on Windows the working tree is not the
  commit.** Regenerating the 123 sprites from the unchanged generator and diffing them against
  `resources/plants/` reported 123 of 123 files different — 10,650 bytes, one per line. With
  `core.autocrlf=true` the files on disk end in CRLF; the generator writes LF, and the committed
  blobs are LF. The reference for a byte comparison is the blob (`git cat-file blob HEAD:<path>`):
  identical, 123 of 123, 5,833,889 bytes, before and after the tables moved. The conformance gate
  never noticed because it compares text.
- **A script that imports the app imports whichever checkout the environment points at.** The dev
  venv's editable install resolves `open_garden_planner` to the main checkout (measured: without
  `PYTHONPATH`, `open_garden_planner.__file__` is the main checkout's, from any directory). A
  sprite generator that had simply gained `from open_garden_planner.core.plant_art.recipes import
  …` would, run from a worktree, have read the *other* checkout's tables as soon as that checkout
  has the package — and a before/after comparison in the worktree would then compare one
  unchanged table with itself and pass. The generator first put its own checkout's `src` first
  on `sys.path` (as `scripts/make_bench_plans.py` does); it now executes its checkout's
  `recipes.py` by file path, which no install can redirect and which needs no app import at all.
  The scratch dump printed the recipes module's path to prove which file was read.
- **A reference built from your own inputs agrees with you.** The first plan for the foliage-hue
  gate compared the mesh's mean hue with the mean hue of the palette's entries — the very colours
  the builder mixes from, so any mixing would have passed within a degree or two of whatever the
  palette's midpoint is. The palettes span up to 41° of hue between their anchors (`dark`: 105° to
  148°); where a sprite's foliage sits in that span is decided by the sprite's drawing code
  (conifers at the base anchors, alliums at the tips). The reference is therefore the rendered
  sprite: the shipped SVG drawn by QSvgRenderer, minus the same sprite drawn with a black palette,
  is exactly the ink that depends on the palette — no hand-made mask for fruit and flowers. A
  single mean tip weight for all plants would have put an onion 9° off; per-archetype weights
  measured from the sprites give 5.0° at worst (rosemary), 0.8° at the median.

**What the independent review then found behind a green suite** (same story, the same day; ADR-059
addendum "plant art v0", "what the first version got wrong"). All eight gates were green.

- **A gate that the code forces cannot fail: a squash was built 1.6 times too tall, and the
  height gate was exact.** The gate compared the mesh's top with the plan's height — after
  `_fit`, whose last step scales the top onto the height. It held for anything. Measured before
  the fit, a Winter Squash 60 × 360 cm was 1.4–1.6 times too tall, so its whole body ended at
  63–76 % of its height under a few leaf tips; at 15 × 800 cm nine archetypes were 3.5 to 11.6
  times too tall. Three causes, none of them visible at the sizes the tests used: shell leaves
  faced the way the RAY from the plant's heart ran, not the way the lobe's surface faces — on a
  flat cushion leaves stood on edge; a leaf's length grew with the plant's width and nothing held
  it to the height; and the size matrix scaled height and spread together, so each recipe was
  only ever built at the proportion it was tuned at. Fix: the builders build to the data (every
  archetype places its highest point at the height; leaves are set by the surface normal and stay
  inside by turning, never by squashing; bow, ripple and fold of a folded leaf are held to the
  height), `_fit` returns a `FitReport` of what it still repaired, and the tests assert the
  report, the area-weighted height quantiles of the foliage, and two off-proportion sizes per
  recipe (every proportion step since the second review). Measured after: the builder's own top
  is 1.0000 of the height in every one of 63,099 plants. Pinned by
  `tests/unit/test_scene3d_plants.py::test_every_recipe_at_every_proportion_step`,
  `::test_every_recipe_fits_the_plan_s_numbers`, `::test_extreme_sizes_and_proportions` and
  `::TestFitReport`. *If the last line of the code
  under test makes the assertion true, the assertion is about that line. Measure before the
  repair, make the repair report itself, and leave the diagonal of the test matrix.*
- **A sole that nobody sees still fights with the ground.** The same measurement found up to
  6.7 % of a mound's foliage triangles (12 % of its area) lying flat at z = 0: lobes that reach
  below the ground were pressed onto it, and their undersides became discs coplanar with the
  ground texture. Hidden from above, but two surfaces in one plane flicker from any angle that
  sees the plant's edge. Fix: `_lobes` leaves out the triangles within 1 % of the height above
  the ground; leaves keep a floor. Pinned by `ground_flat_triangles(...) == 0` for every build.
- **"For every plant from the gallery" was checked for 11 of 86 — and was false for the
  pumpkin.** The builder resolved its recipe from the record's `species_name`, which prefers the
  species DATA's common name; the canvas resolves the sprite from the item's own string. A
  gallery "pumpkin" finds the bundled record of "Winter Squash": the canvas drew `species/pumpkin`
  and 3D built `species/squash` (harmless today — same archetype, same palette — and wrong the
  day fruit arrives). A string of blanks diverged too: 2D answers the rose (its partial match of
  an empty needle), the snapshot stripped the string. The integration test had planted eleven
  species by hand. Fix (ruling R14): the record carries the item's own string, raw
  (`sprite_species`), and the builder hands the rule exactly what the renderer hands it. Pinned
  by `tests/integration/test_scene3d_plants.py::test_every_gallery_plant_is_built_as_the_sprite_the_canvas_draws`
  (all 100 gallery plants through the real drop) and `::test_every_species_string_...` (all 222
  keys and the odd strings). *Sharing a function is half of sharing a rule; the other half is
  its inputs. And a claim over a list is tested over that list.*
- **With every file shipped, nothing asks whether a file is there.** The extracted rule takes an
  `available` predicate; the renderer passes "the SVG exists". Dropping that argument survived
  3,048 tests: the shipped sprite set is complete, so the fall-through to the category sprite
  never ran, and the test of it exercised the pure function with a fake predicate. Without it a
  missing SVG gives a dead path, no renderer, and a plant painted as a bare circle. Fix: tests
  that patch `Path.exists` for one sprite and assert both the answer and what the plant item
  paints, and a differential of old rule against new rule and renderer over every missing-file
  set (`scripts/make_sprite_resolution_golden.py --differential`: 481,096 comparisons). The
  differential earned its keep at once: my own transcription of the old resolver into that script
  had dropped its last `exists()` — 3,582 mismatches, all in the default-category step. *I had
  written down a line I had not read.*
- **"Standard library only" was true of every file and false of the import.** `core/plant_art`
  imports nothing but the standard library, and an AST scan says so. The sprite generator
  imported it by name — which first runs `core/__init__.py`, PyQt6 and twenty app modules. The
  script, pure standard library until then, needed Qt, and two texts said otherwise. Fix: it
  executes `recipes.py` by file path; a test runs it with PyQt6 and numpy blocked. *A property
  of a module's source is not a property of importing it: the package's `__init__` runs first.*
- **Five ids are a claim about five ids.** The no-clones gate took five fixed ids and passed
  with 0.005 to spare; over 24 others a hedge section reached 0.984 and 2.2 % of its pairs
  exceeded the gate's own bound (the reviewer's numbers; over 30 ids I measured 0.983 and 4.1 %), and two texts stated the five-id maxima as properties of the
  builder. Fix: more variation where a shape repeats by nature (a hedge cut by hand in five ways,
  a ground cover with a lumpier skyline), a gate over twelve ids a recipe that bounds a
  distribution, and the measured table beside it (30 ids: maximum 0.975, 99 % of 53,505 pairs
  below 0.952).
- **On a shared machine a millisecond is not a unit.** The first budget was six times a median
  taken in a quiet minute; the review measured a daily scrub tick at 218 ms on the busy box. The
  same first build read 330 ms quiet and 1,200 ms with every core busy — and its CPU time rose
  with its wall time (828 ms against 916 ms), so the process was not waiting, it was slower.
  Neither a bound in milliseconds nor one in CPU time survives that. What does: the counts that
  cause the time (shapes built per tick: exact for a first build and a cold tick, bounded at
  10 % of the plants that changed for a warm one), a ratio measured in one process (warm against
  cold), and the time in units of a small reference workload timed alongside — the warm tick of
  `bench_large` read 0.134–0.138 units at a unit of 114–126 ms and 0.135 at a unit of 76 ms. The
  fix for the cost itself is the shape cache: a plant that only grew is scaled, not rebuilt
  (15 ms against 342 ms per tick on the busy box).

**What the second review found behind the fix round's own claims** (ADR-059 addendum "plant art
v0", "what the second review found").

- **A sample's maximum was written into a requirement as a limit — the first round's lesson,
  repeated one level down.** FR-3D-PLANT-02 said "no part more than 10 % outside the canopy
  circle" because 117,000 builds had read 1.092 at most; a pumpkin at a proportion its growth
  passes through read 1.1006 (one id in the review's 300,000). It said at least 5 % of the
  foliage's surface lies above "62–87 % of the height"; a rhubarb 46 cm tall and 2 m wide read
  60.3 %. Cause of the first: `_fit` pulled strays onto the circle, THEN centred, THEN scaled —
  each step undoing part of the one before, nothing saying where a vertex ends. And the sample
  stood on 43 of 171 proportion steps (since the shape cache, a recipe's seedling, mid and
  mature size are one shape). Fix: the fit's LAST step puts whatever is beyond 1.09 canopy radii
  onto that circle (`REACH_MAX`, `_rein_in`) and reports it — tested on 500 hostile point clouds,
  not on well-behaved builders; the mass is stated as measured; the tests sweep every proportion
  step. *A claim is structural or it is a measurement with its sample. A maximum is neither.*
- **A least-recently-used cache has a cliff exactly where its user stands.** 1,024 shapes, and a
  scrub that asks for every growing plant once per tick in the same order: with 1,024 growing
  plants a warm tick rebuilt none, with 1,025 it rebuilt all 1,025 on every tick (1.9 s against
  0.1 s; 6 s at 2,000) — the shape dropped is always the one needed next. No test stood at the
  cap. Fix: the cap is in bytes and the count follows the plan; a shape that was dropped comes
  back only in place of shapes nobody asked for since, so beyond the cap a tick rebuilds the
  overflow (1,025 plants: 1 per tick). Pinned at the cap, one past it and far past it:
  `tests/unit/test_scene3d_plants.py::TestShapeCache::test_at_its_cap_the_cache_has_no_cliff`.
  *Test a cache at capacity + 1 with its consumer's access pattern.*
- **Behind a cache, "build it twice and compare" compares a build with a look-up.** The
  determinism tests passed with UNSEEDED dice: the second build was a cache hit. Three archetypes
  were never built cold in any test. Fix: `build_cold` clears the cache; the determinism test
  asserts the second build was a build (0 hits, 1 miss; two different colour arrays) and covers
  every archetype. *When a cache is added, re-read every test that calls the cached function
  twice.*
- **A read-only flag is a request.** `Mesh.from_arrays` returned read-only VIEWS of writeable
  arrays; `mesh.colors.setflags(write=True)` succeeded. Before the cache that could damage one
  mesh; with shared arrays, every later build of that plant. Fix: the memory under a mesh's
  arrays is an immutable `bytes` object — the flag cannot be set on the array or on its base.
  Pinned by `TestShapeCache::test_remembered_arrays_cannot_be_written` and
  `::test_a_mesh_from_arrays_cannot_be_made_writeable`.
- **Dice that are rolled per thing built depend on how many things are built.** A conifer has
  three to six whorls by its proportions and rolled each whorl's dice as it built it; gaining a
  whorl moved every later number up the stream — the one plant that was re-rolled when it grew
  (the review suspected all of them; measured, a plant one proportion step on is 0.99–1.00 itself
  for every archetype, against 0.71–0.92 for another id). Fix: all six whorls' dice are rolled
  always. `::test_a_conifer_that_gains_a_whorl_keeps_the_ones_it_had`.
- **A review finding is a claim too: "twelve gallery species have no height" — the twelve are not
  in the gallery.** Checked against the gallery's own item list: all 86 gallery species have a
  bundled record and a height; the twelve named (squash, turnip, arugula, chard, okra, tarragon,
  lemongrass, marjoram, bay laurel, stevia, sorrel, lovage) are twelve SPRITES whose species the
  bundled database does not know, reachable by a species string from a plant list, an older plan,
  an agent or the keyboard. The substance stood — such a plant has its own sprite on the plan and
  a grey disc in 3D, and the docs had not said so — and the documents now say it with the right
  population. *Verify a finding against the code before acting on it, in both directions.*
- **A measuring script loaded two plans — and rewrote the owner's recent-files list.**
  `scripts/measure_plant_art_3d.py scrub` and three scratch probes of this story loaded fixture
  plans with `ProjectManager().load(...)` in a plain Python process. A load ends with
  `add_recent_file`; outside pytest the settings are the developer's real ones, and on Windows
  they are the registry (`HKCU\Software\cofade\Open Garden Planner`) — an `APPDATA` prefix on
  the command, which those runs did have from the second fix round on, does not touch it. The
  owner's ten recent files became fixture paths of agents' worktrees. Nothing in the suite could
  see it: `tests/conftest.py` rebinds the settings names for pytest only. Measured afterwards
  under isolation (a per-process test key): a load of each of the three plans writes exactly ONE
  settings key, `recent_files`, and no file in the profile; creating a canvas reads the settings
  and writes nothing; importing the app writes nothing. Fix: the committed script isolates
  itself at import (as conftest does) and refuses to load a plan unless its store is a test
  key; `tests/integration/test_scene3d_plants.py::test_the_measuring_script_keeps_out_of_the_owner_s_stores`
  runs it in a child process without conftest and checks where the write landed — with a driver
  that loads nothing if the isolation is broken. *Isolation that lives in the test harness
  protects the tests. Anything else that imports the app — a script, a probe, a benchmark —
  needs its own, before its first app import; and "which store does this write to?" is a
  question to ask of every `load`, not only of every `save`.*
