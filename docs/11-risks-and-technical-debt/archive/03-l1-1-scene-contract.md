# Archive 03: Phase 17 L1.1 scene contract

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.14 Four things measured while building the 3D scene contract (Phase 17 L1.1, #385)

None of these was reported by a user: each was found by measuring a claim before building on it
(ADR-059). Each would have shipped a diff that silently lies to the engine.

- **A hash is not an equality — `hash(-1.0) == hash(-2.0)` in CPython.** The first design compared
  two snapshots by three hash signatures alone ("cheap: a hash of already-normalised tuples"). A
  probe before writing it: `hash((-1.0, 3.0)) == hash((-2.0, 3.0))` is `True`. So a vertex moved from −1 cm to −2 cm
  (item-local coordinates are centred, hence often negative and often whole numbers) would have
  produced an empty diff, and the 3D view would have kept the old shape with nothing failing.
  Fix: `Record.same_geometry` / `same_transform` / `same_material` compare the signature first and
  the values second; `diff` uses only those. Pinned by
  `tests/unit/test_scene3d_contract.py::TestRecord::test_a_signature_is_only_an_accelerator`,
  which asserts the collision itself and then the detected edit. *A hash can prove two things
  different, never the same; when "same" means "skip the work", confirm it.*
  - **And then the confirmation itself had a hole.** `same_geometry` compares eight fields; the
    collision test pinned one of them. When `holes` became the eighth, the mutation check
    (`scripts/mutation_check_scene3d.py`) deleted its comparison and every test still passed.
    The collision is now asserted in each value-bearing field, and for the transform and the
    material (`test_every_geometry_value_is_compared_not_only_hashed`,
    `test_a_transform_and_a_material_are_compared_too`). Floats collide when they are equal
    modulo 2**61 − 1: besides −1.0 / −2.0, `hash(1.0) == hash(2.0**61)`.
- **Float dust is an edit unless you say otherwise: a HOUSE was rebuilt on 689 of 1,000 moves.**
  "Move → transform only" held for every shape in the first matrix and was false for the one item
  that owns another: a HOUSE's ridge is a separate item whose points the app re-writes by
  `+ delta` on each move (`PolygonItem._move_ridge_by_delta`). Read back into the HOUSE's own
  frame, `(p + d) − (c + d)` is not `p − c` in floats. Measured without snapping: 689 of 1,000
  random moves changed the HOUSE's geometry (the first one already), 271 the ridge item's own.
  Fix: every length of a record is snapped to 1e-7 cm (`core/scene3d/record.quantize_cm`) — 0
  changes in 20,000 moves, by which time the dust had grown to 1.1e-10 cm. Pinned by
  `tests/integration/test_scene3d_snapshot.py::TestHouseRidge::test_a_thousand_moves_never_leak_float_dust_into_the_geometry`.
  - **A second, coarser grid for the ridge was written first and then removed.** It was argued
    from "the error accumulates per move"; the mutation check showed the test passed without it,
    and the measurement above showed why. *An argument that a safeguard is needed is a hypothesis;
    delete the safeguard and see whether anything fails.*
  - **`round(x, 15)` is not "no rounding".** The first mutant meant to switch the grid off set
    the decimals to 15 and survived a test that depended on the grid: 1e-15 still absorbs dust of
    5e-17. A mutant has to remove the behaviour, not weaken it.
- **A polyline's 2D stroke polygon is not the same polygon after a move.** `polyline_footprint`
  inflates the centre line with pyclipper on a 1/1000 cm integer grid, and the 2D code calls it
  with *scene* coordinates. Move the line by a non-multiple of that grid and the polygon is not
  the old one translated — its vertices differ by up to the grid. A record derived from the scene
  polygon would therefore change geometry on every move. Fix: the record inflates the centre line
  in the item-local frame. Consequence, stated rather than hidden: for a polyline,
  `transform ∘ local footprint` matches the 2D stroke polygon only to that grid (measured
  1.6e-3 cm, asserted ≤ 3e-3), while the centre line — what fences and walls are built from —
  matches to 1e-7 like every other shape. Pinned by
  `test_scene3d_snapshot.py::TestTransformReproducesFootprint`.
- **Two things that looked like a diff bug and were the plan being right.** (1) Resizing the drawn
  circle of a *measured* plant produced an empty diff: correct — its footprint is the canopy
  (`plant_canopy_radius_cm`), not the circle, exactly as in the 2D shadow. (2) A resize that keeps
  a corner fixed is reported as geometry **and** transform: correct — the record's frame hangs on
  the item's centre, and that centre moved. Both are pinned as behaviour, not worked around.

**What the independent review then found behind a green suite** (same story, one day later).
Seven gates were green and the contract was wrong in two places other stories were already
building on.

- **A closed fence became a slab, and every gate passed.** `polyline_footprint` returns a closed
  stroke as TWO rings — an outer one and a hole, told apart only by their winding. The record
  carried both as `footprints` and the default builder extruded both. Measured on a 10 m × 8 m
  fence, 10 cm wide: rings of +818,062 and −782,100 cm², a solid over 81.8 m² of ground where the
  fence stands on 3.60 m², and an inner wall facing into the solid. "Every ring matches the 2D
  ring" was true, "the mesh validates" was true, "the top is the fence's height" was true. *No
  gate measured an extensive quantity.* Fix: `Record.holes`, orientation enforced by the record,
  a default builder that cuts holes out and checks its own cap area, a plan-view check in
  `verify_builder`, and a third committed plan made of the shapes the bench plans lack
  (ADR-059 decision 3 and 9; `tests/integration/test_scene3d_snapshot.py::TestClosedStrokes`,
  `test_scene3d_edge_plan.py`). A 2 cm gap **at a corner** does not help: the strokes of the two
  sides overlap there, and the loop closes anyway (35,952 cm², one hole).
  - **"A gap narrower than the stroke closes it" — written here first, and false.** A stroke
    has butt ends: it reaches half its width sideways and nothing past its end points. So a
    10 cm stroke closes a corner gap up to 5.000 cm, a 6 cm corner gap stays open, and a gap in
    the middle of a straight run stays open at 0.01 cm (the re-review measured all three). The
    sentence had been generalised from the one 2 cm fixture; the edge-case plan now holds a fence
    of each kind. *One measured case is one case — say what was measured, not the rule it
    suggests.*
  - **The same defect is live in the 2D shadow, and is NOT fixed here.** `item_footprints` hands
    both rings to `compute_scene_shadows` as solids, so the hole ring casts the shadow of a slab.
    Reproduction with `core/shadow_geometry` alone (no Qt): `polyline_footprint([(0, 0), (1000, 0),
    (1000, 800), (0, 800), (0, 0)], 10.0)` → two rings; `compute_scene_shadows([(ring, 120.0) for
    ring in rings], 60.0, 180.0)` → **88.8 m²** shaded. The stroke region cut into triangles and
    shaded the same way gives **17.5 m²**; the same fence with its west side removed (no hole,
    one ring) gives 16.7 m² both ways. The hours-of-sun heatmap reads the same footprints. It is
    left alone because `item_footprints` is pinned byte for byte by the golden fixture and the 2D
    shadow is shipped behaviour — the fix (shade `outer − holes`, as `group_rings` now makes
    easy) is a change of its own with its own before/after.
  - **Same family, also 2D, also left alone: a polygon that crosses itself.** `_caster_paths_int`
    assumes a simple ring ("normalize CCW for stable winding"). For the bow-tie
    `[(0, 0), (400, 300), (400, 0), (0, 300)]` at 300 cm, sun 60° / azimuth 180°, it shades
    80,000 cm²; its two lobes shaded as the two prisms they are give 129,282 cm² (measured; the
    mechanism was not investigated). The 3D record resolves such a polygon into its lobes; the 2D
    sweep does not.
  - **A plan-view check has its own blind spot.** The first version sampled each *triangle* at
    four points and summed the weights of the ones inside a hole. It read 205 % for a slab over
    the fence's hole (measured — a share above one), and it cannot see a small hole under large
    triangles at all: the two cap triangles of a 10 m slab have eight sample points, and none of
    them lies in an 80 cm hole at (80…160, 210…290) — 0 % covered. The check now samples the
    *hole* (a 24 × 24 lattice of its own interior points) against the triangles
    (`test_a_hole_under_two_huge_triangles_is_seen`, `test_half_a_hole_covered_is_half`).
    *Sample the thing you are asking about.*
- **Recovery was not expressible in the protocol, and the test hid it.** `SceneSync.reset()`
  forgot its records and touched no sink. After a sink call failed in mid-transaction the sink's
  transaction was still open, so the next `begin()` raised and the sync was poisoned again:
  there was no sequence of protocol calls that recovered. The test passed because it first called
  `RecordingSink.reset()` — a convenience of the test double that no engine has. Fix: a tenth
  protocol method, `clear()` (hold nothing; legal at any time, also inside a transaction), which
  `reset()` now calls. (That `reset()` forgets the sun and ground it deduplicates against — or the
  first sun after a recovery would be swallowed as "unchanged" — was already so; it is now pinned.) *A fake that is more
  capable than the real thing certifies behaviour the real thing does not have: test recovery
  with nothing but the interface.*
- **One malformed plant blanked the whole plan.** `plant_species = {"scientific_name": None}` on
  one item raised `AttributeError` out of `snapshot_records`, so no record reached the engine.
  The snapshot now contains any exception to its item, reports the item through `skipped=` and
  logs it once per item and kind of failure (the exception's type, not its message — a message
  can carry a value that changes with every mouse move, and the pipeline snapshots on every edit). *A loop
  over user data needs its `try` inside the loop — and a place where what it swallowed can be
  read.*
- **"Rotate → transform only" was false for the one item a house owns.** A `ROOF_RIDGE` item had
  a record; the app re-derives its points when the house turns (ADR-046), so that record changed
  *geometry* on 400 of 400 rotations. The test that should have seen it took its baseline after
  the rotation. Ridge items now get no record (the ridge is its house's param), and the test
  takes its baseline first.
- **(Re-review.) "Always simple rings a builder can triangulate" was written down and never
  checked.** Four HOUSE outlines, each five to seven vertices, each drawn crossing itself: one
  resolved into a single ring of ten vertices (so "several rings means resolved" was false and
  the house kept a ridge that belonged to another shape), one into an outer ring with a pocket
  the default builder could not cut ("only strokes have holes" was false), one into a ring that
  touched itself, one into nothing at all — its hole began on its outer ring, and ownership was
  decided by a point test at that very vertex. Over random such outlines 2–9 % got no record and
  4–14 % no solid. Fix: one predicate, `polygon.is_buildable_region` — the default builder's own
  triangulation, proven by area and orientation — asked for every region before it is handed on;
  `params["outline_resolved"]`; no ridge for a resolved house. Pinned at 0 of 7,500 random
  outlines and 0 of 4,500 random strokes (`test_random_self_crossing_outlines`,
  `test_random_strokes`). *A sentence that begins "a consumer can rely on …" needs a test that
  ends in a number.*
  - **The library the fix leaned on was wrong too.** The ruling said: take the ring hierarchy
    from pyclipper's `PolyTree`. For an outline that retraces one of its own edges, the strict
    tree handed a solid triangle of 357 cm² out as a hole, and the plain union returned rings
    whose signed areas sum to 33,133 cm² where the outline fills 36,704. Neither is a wrong
    *shape* at a glance. They were found because the check compared against a raster of the
    drawn outline's winding number — a dozen lines of numpy that know nothing of the clipper —
    and not against a second call into the same library. Every reading is now held to that
    raster (`_matches_outline`). *When the tool's answer is the thing in doubt, verify it with
    something that does not share its code.* (And then the mutation check let "the reading is
    taken on trust" SURVIVE: in every sampled outline — 19,500 — the wrong reading was also not
    buildable, so the other check had already turned it down. The safeguard is kept for the
    reading that is wrong and buildable, and pinned with a simulated one. *A safeguard nobody
    can trigger with real input still needs a test, or the next refactoring removes it.*)
  - **Zero-area triangles are not harmless in float32.** Along the edge of a diagonal stroke
    that other strokes cross, vertices of several rings lie on one line; an "ear" of three of
    them has a doubled area of 1e-14 cm² — float noise around zero, positive by luck. Rounded to
    float32 thirteen of them came out wound downwards and `Mesh.validate` refused the fence.
    The ear clipper now emits no triangle for a flat corner, and `prism_mesh` none below
    float32 resolution. Found by this round's own ladder test; the first round had no diagonal
    stroke crossed by another.
  - **The cost cliff was worse than reported, and elsewhere.** The reviewer measured 2.6 s for a
    ladder of 58 holes. One hole is enough: a closed fence along an outline traced with 400
    vertices took 12.6 s to triangulate, with 750 vertices 150 s — on every geometry tick. The
    bridge search tried boundary vertices one by one in Python against every edge. It is one
    array pass per hole now (45 ms and 89 ms for those two), with stated bounds beyond which
    the region is refused instead of built slowly.
- **(Fix round 3.) A bound that is checked after the work is a report, not a bound — and a
  bound on the largest element is not a bound on the sum.** The cost cliff above got "stated
  bounds beyond which the region is refused". They were judged after the quadratic simplicity
  test (2,700 traced points: 2.59 s to refuse where 2,600 took 1.86 s to build); then, as a
  counted work bound, applied to the largest ring of what the clipper had already inflated and
  the snapshot had already read (800 scribbled points: half a second and 53,000 rings before
  anything was asked); and the clipper itself was never priced — its last reading of a
  self-crossing outline of 800 vertices took ten seconds under a limit that counted vertices.
  Now one budget per item, every step paid before it runs, an item's stored vertex count asked
  before one vertex is read, and caches bounded by the vertices they hold (ADR-059 decision 9,
  §8.29.1, §8.11). Three things to keep: *(1) write the test that asserts what RAN before the
  refusal, not that the refusal came* — every earlier form passed "is the large thing
  refused?"; *(2) a library's cost follows its own variables* — pyclipper's are crossings and
  the edges a sweep line carries, not vertices: 4,000 teeth side by side cross nothing and
  took 1.6 s, the same teeth lying down 4 ms; *(3) price a step by what it does* — the
  simplicity test was priced at the square of its edges and cost a hundred times that for a
  ring whose every pair of edges lies close, found by measuring a refusal that took longer
  than its units allowed.
- **(Fix round 4.) A cache smaller than its working set is not a small cache — it is no
  cache, plus its bookkeeping.** Round 3 bounded what the ring memories hold (262,144 vertices,
  least recently asked dropped first) to stop an edit session from holding a gigabyte. A
  snapshot asks the plan in the same order on every tick, so in a plan larger than the cap each
  answer was the oldest when its turn came: nearly every lookup missed, and an UNCHANGED plan
  was recomputed on every tick — 160 polygons of 1,000 vertices 4.6 to 5.3 s per idle tick
  (0.2 s before the cap), 110 closed fences 14 s. Every test of the round ran far below the
  cap. Fix: a snapshot is one generation; what it asks for is live and never dropped; the cap
  bounds the stale rest (ADR-059 decision 9, §8.29.1). *Bound what is beyond the working set,
  never the working set; and test a cache at the size where it is full — shrink the cap in
  the test, count the recomputations on the second tick.*
- **(Fix round 5.) A fix made for the call a review named, not for the rule it found, leaves
  the next call standing.** Round 4 stopped asking the STRICT union for a tree. The PLAIN
  union, eight lines above it in the same function, went on being asked for one — a tree that
  was flattened on the next line — and a test pinned that as expected. One ring with 720 holes
  bridged to its wall held the GUI thread for 5.3 s inside the work budget (pyclipper alone,
  801 rings: 23 ms as a list, 7,078 ms as a tree). Fix: `_clip_tree` is split by what a
  caller may get — `_union_rings` cannot return a tree, `_band_tree` is the one call that
  does, and it is bounded for a stated reason (a band leaves nothing to join; measured the
  same as a list); the op-count test watches `pyclipper.Pyclipper` below every seam; and
  `scripts/measure_region_work.py` FAILS above 12 times the price instead of printing its
  worst row. *After a finding, write down the rule, then grep for every other place the same
  thing is done. And a table that only prints is not a gate: twice the hole was a family
  nobody had put in it.*
- **(Fix round 5.) The order of a clipper's output is not a property of the shape.** A
  record's regions came in the order pyclipper handed its rings out, and that changed when
  one call went from `Execute2` to `Execute`: the same regions, another order, another
  signature. They stand by the smallest vertex of their outer ring now, sorted before they
  are judged (regions are paid one after the other out of one budget, so the order decides
  where a budget runs out). *Whatever a library returns as a list has an order you did not
  choose; if it reaches a signature, choose one.*
- **(Fix round 4.) The same library call can cost a thousand times more for how it is asked.**
  pyclipper's union with `StrictlySimple`: 19 ms as a flat list (`Execute`), 4,382 ms as a tree
  (`Execute2`), same input — a closed zigzag of 340 vertices on two levels. The price was read
  off the rings that came back; the cost followed the splits the tree build tried. *When a
  call into a library is priced, measure that call on input built to hurt it, in each form it
  can be made; a price fitted on kind inputs is a guess.*
- **(Fix round 3.) "Unreachable" was a sample.** A fallback was reported as a path no real
  stroke takes because 0 of 4,500 random strokes took it. A fence whose two butt ends meet
  corner to corner takes it every time, and nothing tested it: replaced by "no regions", 694
  tests and 93 mutants stayed green. *A random sample says how often, never whether; for
  "can this branch run" construct the input from the branch's own condition.*
- **(Re-review.) A finite number is not a usable number.** `"object_height_cm": 1e300` in a
  hand-edited plan is positive and finite; it passed the record's check, and became infinity in
  the mesh's float32 — which a sink that does not validate hands to the engine. Fix: a domain
  bound in the record (`MAX_LENGTH_CM`, 10 km) for every length, and a mesh constructor that
  refuses what is not finite once it is float32. *Validate in the units and the precision of
  the place the number ends up, not of the place it came from.*
- **(Re-review.) A report object that holds an exception holds the world.** `SkippedItem`
  carried the exception it reported, and the caller is told to keep the list: the traceback
  keeps its frames alive, the frames hold the scene and the item. It holds two strings and a
  code now. The test that pins it had to switch pytest's own log capture off first — pytest
  keeps every log record, traceback included, which is the same leak one layer up.
- **A safeguard on the hot path costs what it costs at the size nobody tested.** Refusing a
  ring that crosses itself needs `is_simple_ring`, which compares every pair of edges. The bench
  plans' largest ring has 24 vertices (0.1 ms), so every budget stayed green — and a 500-vertex
  outline cost 72 ms per snapshot while one of its vertices was dragged (1,000 vertices:
  262 ms), because an edited ring misses the cache on every tick. Found by asking for the number
  at n = 500 before anyone drew such a polygon. From 32 vertices on the test now prunes edge
  pairs by bounding box and runs on numpy: 2.9 ms and 10.8 ms, same machine, same load
  (`tests/unit/test_scene3d_polygon.py::TestSimpleRingAtScale` pins that both versions agree).
  *A check that is linear in the plan can still be quadratic in one item: measure it on the
  largest single item a user could make, not on the largest plan.* The ear clipper the two 3D
  views share (`triangulate_polygon`) is quadratic too and was left as it is: it runs only when
  that item's geometry changed, and the Qt 3D view has paid it on every change since US-E6.
  - **One round later that sentence stopped being enough.** "Every region is buildable" is
    checked by cutting the region, so the ear clipper moved from the builder into the snapshot
    (cached; the builder reuses the cut). The total per edit tick was unchanged — and the
    snapshot of a 1,000-vertex outline with one vertex dragged went from 9 ms to 290 ms. Measured
    only because the rule above said to: the suite's budgets run on warm caches and on plans
    whose largest ring has 24 vertices. From 256 vertices on, a ring without holes is now cut by
    the array ear clipper written for regions with holes (1,000 vertices: 30 ms against 272),
    and snapshot plus build is 41 ms where the first version took 250. *Moving work to another
    function moves its cost too; re-measure the hot path at the large size after every such
    move.*
- **A styled polyline did not keep a stroke width across save and load** (observed while
  generating the edge-case plan). `core/project.py` restored `stroke_width` only when the
  polyline had no `path_fence_style` preset, so a fence with a preset came back at the preset's
  width whatever was saved; the edge-case plan therefore uses fences without a preset. *Changed
  by L1.5* (§11.4.17): the loader restores the saved stroke of a preset line too — a file saved
  by a version that did not, with a stroke that differs from the preset's, now shows the saved
  one.
