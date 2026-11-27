---
id: ADR-065
title: "The built world complete — objects, roofs, facades, surfaces and ground detail"
status: "Accepted; shipped in [v1.34.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.0) via [PR #613](https://github.com/cofade/open-garden-planner/pull/613), after the owner's third manual pass (\"all perfect\") confirmed every decision below, including the \"Owner's second manual pass\" addendum (every object without a 2D default height gets a real, settable one; detail-normal strength 3.0) and the two re-review fixes (the AO fade switched SSAO on at Low, PF-L3D-15; a plain-block house had a sandstone top instead of roof tiles)."
refs: ["Phase 17 L4", "#388"]
legacy_anchor: adr-065-the-built-world-complete--objects-roofs-facades-surfaces-and-ground-detail-phase-17-l4-388
---

# ADR-065: The built world complete — objects, roofs, facades, surfaces and ground detail

**Status:** Accepted; shipped in [v1.34.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.0) via [PR #613](https://github.com/cofade/open-garden-planner/pull/613), after the owner's third manual pass ("all perfect") confirmed every decision below, including the "Owner's second manual pass" addendum (every object without a 2D default height gets a real, settable one; detail-normal strength 3.0) and the two re-review fixes (the AO fade switched SSAO on at Low, PF-L3D-15; a plain-block house had a sandstone top instead of roof tiles).
**Date:** 2026-10-26
**Naming note:** older branches used "ADR-065" as a working name for ADR-060 (see
ADR-059's status line). This record is the L4 one.
**Context:** after L1–L3 every plant had a species model, but most built things were
still flat: the 24 furniture, play, utility and structure objects were painted
sprites on the ground, every house had a gable whatever the user wanted, walls had no
windows or doors, paths were 6–10 cm lines with nothing on them, and lawns were a
flat texture. Issue #388 asked for all of it under the truth gates of ADR-048/059
(the top of a thing is its resolved height; nothing reaches more than 10 cm past
its footprint), with one shared material table and no new texture assets. The
owner added that a path capped at 20 px is not a path.

**Decisions:**

1. **Every object kind gets a builder; one material table.** `builders/furniture.py`,
   `play.py`, `utility.py` and `structures.py` build the 24 `OBJECT_KINDS` from the
   bevelled pieces in `builders/kit.py`, in the colours of `builders/palette.py`,
   which mirrors the 2D object `MATERIALS` (drift guard in
   `test_scene3d_builders_palette.py`). Each is bounded by construction
   (`OBJECT_TRIANGLE_BUDGET` 4,000; slats, staves, bays and lattice cells are
   capped, so a hostile 9 km object stays bounded). Every object goes through
   `BuiltBuilder`: its top is its resolved height by construction.
2. **An object without a height is built at an illustrative one.** A parasol, fire
   pit, planter pot, cold frame, rain barrel, water tap, swing, hammock or pergola has
   no 2D default height (`core/object_height.py`). In 3D it is built at an
   illustrative height (`core/object_height_estimate.py`, carried as
   `params["estimated_height_cm"]`, as #557 does for plants), and the 2D sun study
   sees no caster. It first cast no shadow in 3D either; the owner reversed that
   (addendum "Owner's manual pass"): it casts in 3D, as a #557 plant estimate does.
   **Superseded** by the owner's second pass: the nine kinds have real default
   heights in the 2D resolver, and the estimate module is gone.
3. **Roof style is additive item metadata.** `roof_style` (gable, hip, shed, flat),
   `roof_pitch_deg` (5–60°) and `roof_overhang_cm` (0–150) on HOUSE, GARAGE_SHED and
   TOOL_SHED (`core/roof_style.py`). There is no FILE_VERSION bump: an older app
   ignores the keys. Missing keys mean automatic: a gable along the live ridge
   where there is one, otherwise a flat roof on a house. A hip on a footprint that
   is not convex falls back to a gable. The properties panel edits each key with one
   `ChangePropertyCommand`; "Automatic"/"Auto" removes the key. The roof's top
   stays the building's height (ADR-037: the height is the ridge's), so a steeper
   pitch lowers the eaves. **The 2D plan and its sun study do not read these
   keys.** A roof-aware 2D caster is #440's work, not L4's.
4. **The facade is a heuristic, and its context is a wall index.** Windows go on
   every wall long and tall enough to hold them; the door goes on the wall that
   faces the nearest PATH (a garage's nearest DRIVEWAY first), centred on that
   wall. The snapshot's new context pass (`core/scene3d/context.py`, `with_context`)
   writes the wall's INDEX into `params["door_wall"]` in the building's own frame,
   not a point. A building moved along its path keeps the same index, so the move
   stays a transform only (ADR-059: "move → transform only").
5. **Relief on painted ground is a `ground_detail` part.** Stepping stones (where
   the 2D painter's walk places them, slid onto the path at its ends and dropped at a
   bend they would overhang), boardwalk planks, paving kerbs, gravel edging (its
   pebbles went in the owner's manual pass), terrace kerbs or deck boards, a pond's water and coping, and lawn blades
   are `MeshPart(ground_detail=True)`. Such a part casts no shadow (enforced in
   `MeshPart`), is never picked and never makes its item a solid, so the ground
   bake still paints the item and the 2D picture stays the ground. A surface the
   user gave a height is a solid as before (a raised deck, a raised pool, the
   prism).
6. **The build-only params do not re-bake the ground.** The roof keys,
   `door_wall`, `surface_pattern`, `lawn_cutouts` and `lawn_blades` are
   `record.BUILD_ONLY_PARAMS`. They are geometry for `SceneSync`, so a change
   rebuilds the one item, but `Record.same_ground_geometry` ignores them. A terrace
   moved across a lawn rebuilds the lawn's blades and re-bakes only the terrace's
   tiles.
7. **Lawn blades are bounded and cut out.** 220 blades per m², at most 36,000 per
   lawn and 60,000 per plan, shared by area with what a capped or small lawn cannot
   use going to the others. They grow nowhere under a flat item painted above the
   lawn, nor inside an enclosed building on it (at most 96 cut-outs per lawn, the
   largest first). They are built at every preset, because a preset step changes no
   geometry, and drawn from High up (QML `lawnBlades`). A flat item moved over a lawn
   rebuilds its blades; the blades are remembered whole (64 MB cap), so that rebuild
   re-masks them in 4.6–12.8 ms on the bench plans (median of 15) instead of
   regrowing them in 11.7–28.2 ms.
8. **Detail normals come from the baked ground, in a shader.** From Medium up, the
   ground tiles use `ground.frag`, which tilts the normal by the luminance gradient
   of the tile's own texture (strength 3.0 since the owner's second pass, first 1.0;
   slope clamped to ±0.35). No normal-map
   asset is generated or shipped, and PBR texture sets remain ADR-042's subject.
   Measured: a `CustomMaterial`'s `TextureInput` does not apply the `Texture`'s
   `flipV`, so the tiles drew mirrored north–south until the shader flipped `v`
   itself.
9. **No order-independent transparency.** Scene-wide `OITWeightedBlended` was
   measured to break L2's multiply drapes (pixels up to 243 levels lighter: the
   PF-L3D-06/07 P0 class). Greenhouse and cold-frame glass therefore use the
   existing `glass` material.
10. **A path's width is its width on the ground.** The path presets are 70–100 cm
    and the PATH default is 80 cm. The properties panel sets a line's width in cm
    up to `MAX_LINE_WIDTH_CM` (5 m); a shape's outline keeps its 20 px range. Saved
    plans keep the width they were saved with, and so do the older bench plans
    (`LEGACY_PATH_WIDTH_CM`). The new `bench_built.ogp` shows every L4 kind, path
    style and roof style.
11. **The Beauty Board shows the bake (#586).** Its shot, mood and horizon frames
    pass a `GroundBaker` with no time budget. The IoU and orientation probes stay
    bare, because their oracles are the records' own footprints.

**Deferred:** smart-symbol builders (#599; a smart symbol is a group of ordinary items,
which L4 already builds item by item) and roof-aware 2D shadow casters (#440).

**Alternatives rejected:** a door point instead of a wall index (every move rebuilt
the house); a ground-detail part as a solid (the bake stopped painting paths and
lawns); per-lawn blade caps without a plan cap (2,000 stacked lawns, 72 M blades);
an even per-area share (a small lawn next to a capped one got 594 of its 7,920
blades while the budget went unused); OIT (decision 9); a generated normal-map asset
(a second picture of the ground that can drift from the bake).

**Consequences:** No new dependency, asset or setting. The ground bake paints fewer
items (objects are solids now), which changes the counts that the bake and render
tests pin. Every L4 builder passes `verify_builder` on hostile input, and the
integration story `tests/integration/test_l4_built_world.py` drives the panel,
undo, snapshot, context pass and production registry end to end.

**3D review round 1 (2026-10-26).** The independent `ogp-3d-reviewer` board found:
- **P0, older than L4:** the endless meadow lay 1 cm under the plan and won the depth
  test from 14 of 36 orbit cameras on `bench_built`, so the pond, terraces and paths
  vanished. #586's baked board made it visible, and it showed in the live view too. The
  meadow now lies 5 cm under the plan; a render-tier gate keys the meadow's colour and
  finds it on no plan pixel in 36 orbit views (`test_the_meadow_never_shows_through_the_plan`;
  at −1 cm it read up to 21,141 key pixels).
- **P1:** path relief reached 15–18.6 cm past the path. Boardwalk end planks were centred
  on the path's ends, and rails were swept on the mitred centre line where the outline
  (`polyline_footprint`) squares a bend off at half the width. Now end planks stand half a
  plank in, each rail runs on its own offset line chorded outside a bend, and a path is
  open at a loop's first point (its outline is). The per-area `verify_builder` check could
  not see this, so a per-vertex and per-triangle reach test holds every surface to
  footprint + 10 cm.
- P2s fixed: lawn blades at the lawn's own value (they read as dark stubble), deck boards
  2.5 cm high (chairs sank 6 cm into them), round ponds from 64 segments, splayed legs and
  rods lifted where their end caps dipped under the ground, a low parasol's canopy and pole
  bounded by its height, the pergola's rafters in mid oak, the orientation probe without
  relief, and the eight L4 shadow cases in the measured table. Left as owner questions:
  roof colour (terracotta, or the item's fill as the walls), windows beside a centred
  door on a long wall, and object porosity (as for the fences).

**3D review round 2 (2026-10-26).** Round 2 rejected again with one P0: the round-1 fix
had only moved the failing views.
- **P0:** from the workspace's own default framing, a few wheel notches out, the meadow
  still drew over the plan in 13 of 120 views on the three bench plans (on `bench_built`
  at ×1.5, over 52 % of it). The reviewer measured the cause: the meadow was ONE quad of
  two triangles, 4 km across, and its interpolated depth was more than 5 cm off at
  55–90 m. The same quad cut into 100 m cells failed no view. 24-bit depth precision
  (about 0.3 cm at 50 m) is not the limit.
- **P1:** the 5 cm step drew a ±14 luma ambient-occlusion line along every plan edge,
  and shadows jumped where they crossed it.
- **Decision:** the meadow is a frame IN the plan's plane (`core/scene3d/meadow.py`).
  - It is a 4 km square around the plan, in cells of at most 100 m, with the plan cut out.
  - The cut-out is smaller than the plan on each side (1 cm at first, 1 mm after round 3),
    so no crack opens along the edge where the tiles' and the frame's vertices differ.
  - Its one geometry belongs to the host, which loads it at start and whenever the plan
    rectangle changes, like the selection ring (`Quick3DHost._show_meadow`, a
    `ReloadableGeometry`).
  - Two QML routes were tried first and measured wrong: a `ProceduralMesh` whose lists are
    replaced in place kept drawing its first data, and one created later drew nothing
    (PF-L3D-14).
- **Gates:**
  - The meadow gate now covers the workspace's own camera on the three bench plans:
    156 views, worst 1 key pixel.
  - The old quad at −5 cm, re-created as a mutation, reads 27,726 key pixels.
  - The gate also asserts that the meadow is drawn at all, because a missing meadow passes
    the first half (one attempt during this fix did).
  - `board_probes.plan_edge_step` gained `line`: the largest deviation within 3 px of the
    edge. Under the ±14 luma line the fitted step had read 0.45. The board gates `line` at
    2 luma (PF-L3D-13).
- **P2s fixed in the same pass:**
  - A deck's boards lie on the ground; they floated 1.25 cm above it.
  - No blade grows through a pond's coping or a gravel or dirt path's round ends. The
    cut-outs are now the coping's outline and the rounded stroke the canvas paints.
  - A closed path loop, or a surface with a hole, keeps the lawn inside it. A cut-out was a
    filled ring, so the hole's blades were cut too; it is now one keyhole ring per region.
  - The `bench_built` deck, loungers and hammock no longer overlap anything.
- **Left as follow-ups:**
  - Blade back faces lit from below, which still read as stubble at High: #604.
  - The 2D painter's outer bends, mitred fill against chord border lines: #605 (with an
    owner question).

**3D review round 3 (2026-10-26): approved, no P0 or P1.**
- **Verified fixed:**
  - The meadow drew on the plan in 0 of 264 views of the workspace's framing on the three
    bench plans: 8 yaws × 11 zoom factors, worst 2 px. The gate also passes on D3D11,
    OpenGL and WARP.
  - The edge line now reads 1.22–1.43 luma. The new probe reads 5.49–10.21 on round 2's
    frames, so it would have caught round 2.
  - Shadows cross the plan edge unbroken.
  - Every round-2 P2 holds.
- **P2s taken in the same pass:**
  - The meadow's strip under the plan's edge is now 1 mm. In that strip the meadow wins
    the equal depth test, and at 1 cm it took the outer centimetre of a surface painted to
    the edge (4 px at 0.5 m).
  - A 100 m cell line within 5 mm of a plan edge is dropped for the edge. Kept in its
    place, a line just outside the plan opened a gap there.
  - The bench rain barrel stands clear of the tool shed.
  - The board's 2× fence reference is skipped and reported when the screen cannot hold
    the window. Before, it ended the board in an error on a 2560 × 1440 display.
- **Owner question added:** from far out (×3 the default distance, about 7 wheel notches)
  the fog washes the garden out. Should the fog follow the camera distance?

**Senior review round 1 (2026-10-26): three P1s, none visible on the board.**
- **A drag over a lawn rebuilt the lawn at every step.**
  - A lawn's cut-outs are the other items' outlines in its frame. So every drag step of a
    flat item over it (and of the lawn itself) replaced the lawn's blade Model: 30 of 30
    steps, Model churn of about 15–20 kB each (#531).
  - Decision: `CONTEXT_PARAMS` (door wall, lawn cut-outs, lawn blades), changing alone, are
    applied at most once per `CONTEXT_REBUILD_MIN_MS` (400 ms). The first change goes at
    once and the last in a trailing pass, like date playback; the item's own move is never
    held back.
  - Pinned with a fake controller clock: 12 steps give 1 rebuild, then the trailing pass.
    Without the throttle: 12.
- **The deck builder was unbounded.**
  - A 402-vertex comb took 14 s and built 446,364 triangles; an 8,002-vertex one never
    finished.
  - Decision: board runs come from numpy crossings, and `MAX_DECK_BOARDS` caps the total
    before any mesh is built. A capped deck falls back to a kerb, or to the plain solid when
    raised.
  - Relief along an outline is capped at `MAX_RELIEF_VERTICES`: a kerb of 64,000 vertices
    was 768,000 triangles.
- **Roof eaves went below the ground at the panel's own extremes.**
  - At 60° and 150 cm a small shed reached −91.5 cm, and "Hip" fell back to a gable that
    sank the same.
  - Decision: the overhang is shortened by bisection until the roof's lowest edge is at
    least half the eave floor above the ground. Style and pitch are kept, and a hip falls
    back to a gable only when its outline cannot hold one.
  - No default roof is affected: 0 of 180 default cases change.
- **P2s fixed:**
  - Objects without a height cut a lawn only when they cover the ground
    (`GROUND_COVERING_KINDS`).
  - Fences and walls are capped at 100 cm wide; their builds reached a metre past the line
    at 200 cm.
  - The pitch spin shows only stored values.
  - The agent's polyline text now gives a path's width.
  - `same_ground_geometry` derives from `GEOMETRY_FIELDS`.
  - The window cap's comment now says what the code counts.
  - Test nits.
- **Left, in #607:** lawn masking per edge in Python, blades built at presets that draw
  none, the two copies of the roof clamp, and degenerate sizes under 1 cm.

**Senior review round 2 (2026-10-26): one P1, introduced by the round-1 throttle.**
- **P1:** the blade share is a context param, so a held lawn kept its old, larger share
  while new lawns got theirs. Two lawns created within one interval put 80,000 blades in
  the scene, against a plan budget of 60,000.
  - Fix: a held share is never above its new one. **Not enough, round 3:** a MISSING
    held share escaped the rule; one budget check replaced it.
  - Pinned with the fake clock; without the fix the test reads 30,000 + 30,000 + 20,000.
- **P2s fixed:**
  - The hold now ends at a document change (its first pass is a plain apply), at a pause
    and at `shutdown()`. A recovery from scratch applies the plan unheld.
  - The deck's work is bounded too: `MAX_DECK_ROWS` counts row scans over all regions, and
    regions narrower than 1 cm are skipped. A 601-region sawtooth took 2.8 s and now
    takes 0 ms.
  - The roof's overhang search tries a secant's guess first: about three builds instead of
    twelve. A 64-corner hip went from 472 ms to 175 ms. (Rounds 3 and 4 replaced the
    search; the round-4 search takes that hip in 3 roofs, 266 ms.)
  - Ground-covering objects cut a lawn whatever their height and paint order.
  - Smaller fixes:
    - `same_geometry` stays a list by hand: `scripts/mutation_check_scene3d.py` deletes its
      comparisons one by one, so each one is pinned.
    - The pond case left the relief-cap test, and the raised pool's total-vertex guard was
      deleted as dead code. **Reversed by the security review:** the water's work bound
      holds per region, so a pond of many small regions passed it and swept walls along
      all their vertices. The guard is back (`_raised_pool`), pinned by a many-regions
      test; the coping has the same total cap.
    - The hip check asserts four slopes instead of comparing the builder with itself.
    - The FR wording is corrected.
    - The glossary gained "Context playback".
- **Left as smells, not defects:** the throttle keeps one timestamp for all records (an
  unrelated context change may wait up to 400 ms), and the caps bound each builder's output
  one at a time, not a per-record work budget (#607).

**Senior review round 3 (2026-10-26): two P1s.**
- **P1, the blade budget:** the round-2 rule skipped a held share that was MISSING. A
  terrace turned into a lawn inside the interval was built with its own count: 75,637
  blades against 60,000.
  - Fix: one budget check in `_hold_context`. The old shares are kept while the lawns'
    total fits `MAX_PLAN_BLADES`; otherwise no held share is above its new one. A lawn of
    the new plan without a held share counts as unbounded.
  - The same check closes a round-3 P2: a lawn resized next to another (the budget
    binds) rebuilt the OTHER lawn at every drag step, 12 of 12. It is left alone now.
  - Pinned with the fake clock: a type change to lawn, a resize beside another lawn, and
    a recovery from scratch inside a hold, which applies the snapshot unheld. Each test
    fails with its fix reverted.
- **P1, this addendum:** round 2's text still said the raised-pool guard was gone (the
  reversal above), and the `_pond` comment said the water refuses first. Both are
  corrected.
- **P2s fixed:**
  - The round-2 overhang search dropped its bracket after a failed guess and halved from
    there. A hexagonal hip kept 37.5 cm of overhang where 73.9 cm holds, and a shed whose
    edge the slope clamp curves kept 40.3 where 76.9 holds. The search is a regula falsi
    on the measured edge heights, with Illinois halving. Over 6,048 panel cases it finds
    at least 97 % of the longest overhang that holds (it was 51 %), in 1.3 roofs on
    average and 6 at most. Pinned against a 30-step bisection. **Wrong, round 4:** those
    6,048 cases had no U outline. Its gable builds no roof at exactly 100 cm, and the
    search took that as a sunk roof and kept 50–94 cm.
  - `_kept_up` no longer returns a roof it never checked: when even a roof without an
    overhang is below the floor, it returns None and the caller falls back. Of the 6,048
    cases this changes four, the unreachable tool shed with an L outline and a rectangle
    shape. **Wrong, round 4:** it also took the roof off every gabled building 18.5–21.5 cm
    tall.
  - The FR's eave sentence states the floor's numbers instead of "a door still fits".
  - An AST test pins every `GEOMETRY_FIELDS` name in `same_geometry`'s hand-written list.
  - Nits: a second timer stop, a test name, the `context_deferrals` comment.
- **Left as a smell:** the hold builds records that never existed (new geometry with old
  context), so every plan-wide invariant over context params needs its own check in
  `_hold_context`. The blade budget is the only one today.

**Senior review round 4 (2026-10-26): no P0. One P1: round 3's measured claims.**
- **Confirmed fixed:** the reviewer fuzzed `_hold_context` with 3,000 random plans through
  6 chained held passes each (12,292 held passes, with type changes, heights toggled, and
  lawns added and removed). The worst total was exactly 60,000; round 3's controller went
  over in 1,135 passes, up to 123,151.
- **P1:** round 3 wrote two numbers into this addendum, §8.29.12 and a code comment that
  the code did not meet (the two "Wrong, round 4" notes above), and the measurement was
  not in the repo.
- **Decisions:**
  - `_kept_up` tells "no roof" from "sunk". A guess stays `OVERHANG_NUDGE_CM` (0.5 cm)
    short of an overhang that built no roof. With no roof at the long end, the edge's fall
    per centimetre comes from the last two roofs that held, or at first from the pitch.
  - The search stops on overhang, not on edge height: once its next step would gain
    under 2.5 % of the overhang found, or under a centimetre.
  - A building too low for the floor even without an overhang keeps that roof, as before
    round 3, because there is no overhang left to shorten. The function returns None
    only when the style builds no roof at all. **Wrong, round 5:** a gable is also no
    roof at exactly no overhang when the ridge lies on an edge (an L drawn on a grid),
    and the house lost its roof.
  - The measurement is committed: `scripts/measure_roof_overhang.py` (9,072 cases, the
    grid in its docstring). Of the 569 cases it shortens to at least 5 cm, the worst
    found 97.0 % of the longest overhang that holds, with 0 floor violations and 0 roofs
    lost. It builds 1.30 roofs per case on average and 6 at most. **Wrong, round 5:** its
    "lost" counted only cases whose zero overhang builds, and its grid had no L drawn on
    a grid and no small shed roof. Round 5's numbers replace these.
  - A 64-corner hip at 700 cm, 60° and 150 cm takes 3 roofs, 266 ms (round 3: 6 roofs,
    527 ms; the long end builds no roof).
- **P2s fixed:**
  - One reading of a lawn's blade share, `record.lawn_blade_share`, now serves the
    builder and the budget check.
  - A lawn with a height grows no blades and now takes no share, so the real lawn beside
    a raised one gets its 36,000.
  - A record whose kind changed is not held: a lawn turned into a terrace no longer
    carries blade params onto the terrace.
  - The trailing-pass tests emit the timer's signal instead of waiting on a real timer.
  - The glossary and §8.29.12 now agree on what ends a hold.
  - Docstrings that round 3 made false are corrected, and the review history is trimmed
    from code comments (#516).
- **Pins:** the U outline and the 64-corner hip join the overhang test at 97 %. Each of
  these is pinned:
  - the None path (a style with no roof at all, then the plain block);
  - low buildings keeping their own roof;
  - the raised lawn's share;
  - a raised lawn lowered inside a hold;
  - a lawn turned into a terrace inside a hold.

  Eight mutants, one per fix, each fail their test.

**Senior review round 5 (2026-10-26): no P0. One P1, the same trap at the other end.**
- **P1:** a builder also returns no roof on an exact coincidence at NO overhang. An L
  drawn on a grid with the HOUSE tool has its ridge on the inner edge. At 700 cm, 60° and
  100–150 cm the house lost its roof and facade, although every overhang from 0.01 cm to
  about 100 cm holds. Round 4's "lost" could not see the case, and its test pinned it as
  right.
- **Decisions:**
  - The short end is tried at `OVERHANG_NUDGE_CM` too, and a guess, 1 % short of its
    estimate, never lands on the long end. None means no roof at either end. (Round 4's
    nudge at the long end is gone: the shading does its work, and a mutant without it
    survived every test.)
  - A guess is the nearer of two estimates: the chord to a roof that sank, and the line
    from the last roof that held at its measured fall (that roof's own `slope`, then two
    roofs). On a curve that flattens or steepens, the nearer is short of the root. After
    a guess sank, the next goes at most halfway. **Wrong, round 6:** `slope` is the edge's
    fall per cm only for a hip and a gable square to its ridge, so neither estimate is
    sure to be short. The halving after a sink carried the worst case.
  - `OVERHANG_TRIES` is 5. A single-slope roof on a small shed kinks where its slope
    clamp starts, and with 4 tries it ended at 87 % of the longest overhang that holds.
  - The walls' own roof stays. A gable holds its eaves to 0.75 × (top − ridge cap −
    slab), lower than `eave_floor`, so a gable 18–22 cm tall cannot reach the floor
    without an overhang. `eave_floor`'s docstring now says so. Unifying the two floors
    would change the roofs of buildings under about 3.1 m, so they are left as they are.
- **The measurement now:** `scripts/measure_roof_overhang.py` covers 17,424 cases.
  - The grid gained an L and a U drawn on a grid, small sheds of 100 × 50 and
    150 × 60 cm, and 400 and 600 cm heights.
  - "Lost" now means no roof although one of 31 overhangs in range holds.
  - Results: 0 violations, 0 lost, and 528 gables at 20 cm that keep the walls' own
    roof.
  - Of 1,482 shortened cases the median is 99.0 % of the longest overhang that holds and
    the worst is 95.5 %. The 6 under 97 % are those small shed roofs at 4 m.
  - It builds 1.46 roofs per case, 7 at most, and 3 for the 64-corner hip.
  - Round 4 cited a reviewer's sweep that is not in the repo; that line is gone.
- **P2s fixed:**
  - A record whose context gains or loses a param is not held. This replaces the kind
    filter: a lawn given a height carried its blade params onto the prism, the twin of
    the terrace case. **Wrong, round 6:** a lawn's cut-outs come and go as an item
    crosses its box, so this switched the drag throttle off there.
  - The budget check's guard for a held lawn without a share is pinned directly.
  - The script-isolation exemption states the import facts correctly.
  - The round numbers are gone from this branch's code comments. Measured facts keep
    their source, as elsewhere in the code.
  - The tests count every build, and the hexagon case is a polygon.
- **Pins:** the overhang test covers 11 cases at 95 % of the longest overhang that holds,
  including the L on a grid and the two small sheds. These are pinned too:
  - an L on a grid, and a tool shed with an L outline, keep a roof and facade;
  - a hip on an L is None, and the caller builds the gable;
  - a lawn given a height inside a hold carries no lawn params.

**Senior review round 6 (2026-10-26): no P0. Two P1s.**
- **Confirmed fixed:** the L drawn on a grid keeps its roof and facade, and every number
  in §8.29.12 matched the script's output on re-run.
- **P1, the drag throttle:** round 5's "same keys" rule was defeated at a lawn's
  bounding-box edge. A flat item wiggled across it rebuilt the lawn's blades on every
  step: 12 of 12, 0 deferrals.
  - Fix: only a record that becomes or stops being a lawn (its blade share appears or
    goes) skips the hold. An absent cut-out is held at its old state.
  - Pinned by an edge-wiggle test, which fails under the round-5 rule.
- **P1, a false description:** round 5 said `slope` is the edge's fall per cm and that
  the nearer estimate is short "either way".
  - The reviewer measured otherwise: a hip falls exactly at `slope`; a gable with an
    oblique ridge falls √2 faster at 45°; a shed falls at twice `slope` until its clamp
    and slower after it.
  - The code comment, §8.29.12 and this ADR now say what holds. Only a roof that holds
    is kept, a guess after a sink goes at most halfway, and the quality is what the
    script measures.
- **P2s fixed:**
  - The chord was neither pinned nor measured; deleting it moved nothing. The HOUSE
    tool's ridge follows the bounding box, so a house drawn turned has an oblique ridge.
    The grid now has two such houses, and a test asserts that a straight edge takes
    three roofs. Without the chord it takes five.
  - The stop now uses the larger estimate within the bracket, not the nearer one. The
    150 × 60 cm shed had stopped at 95.5 % with tries unused. `OVERHANG_GAIN_SHARE` is
    pinned by the same test: stopping at a centimetre alone takes four roofs.
  - The walls'-own-roof branch says it only makes the loop's result explicit.
  - The script's leftover long-end filter is gone, and its runtime note is fixed.
- **The measurement now:** 20,592 cases. Results:
  - 0 violations and 0 lost;
  - 624 gables at 20 cm keep the walls' own roof;
  - of 1,581 shortened cases, the median is 99.0 % and the worst 96.5 %. The 3 under
    97 % are one small shed roof at 4 m, once for each kind;
  - 1.40 roofs per case, 7 at most;
  - 3 roofs for the 64-corner hip.
- **Pins:** the overhang test's floor is 96 %. Ten mutants each fail a test: the
  key-set rule, holding every record, the round-2 min rule, no chord, a stop at a
  centimetre, a stop on the nearer estimate, no short-end nudge, no halving, no
  measured fall, and four tries.
- **Left as the reviewer advised:** the search is not tuned further. A closed form per
  roof style would replace it, but the overhang is cosmetic, and the guarantee that
  matters (no edge below the floor, no roof lost) is measured on 20,592 cases.

**Senior review round 7 (2026-10-26): no P0, no P1. The 3D delta review approves.**
- Round 7 confirmed both round-6 fixes by running them, and every doc number matched the
  script. Its four P2 nits are fixed: the stop's comment, a pin of the "starts being a
  lawn" half of the rule, the edge-wiggle test's trailing pass, and a docstring.
- The runtime view (docs/06) now describes the context hold.
- **Left as follow-ups:**
  - #611: hold only the params that both the old and the new record take, and
    pin the stop's bracket cap.
  - #612: the Properties panel shows the overhang that was asked for, while 3D builds a
    shorter one when it must. This is an owner question.
- **The 3D delta review at 032b08d0:** the round-3 approval still holds.
  - Against 514eee80, every Low frame and every probe is byte-identical.
  - At High, blades now grow under the swing and the hammock (the bald patches are gone).
  - Default roofs, decks, kerbs and ponds keep identical mesh digests.
  - At the panel's extremes, sunk eaves are lifted: on a 60 × 100 cm shed from
    −101.5 cm to +78.7 cm.
- **G3** (`test_scene3d_ground_bake.py`) had placed its stand-in terrace where four tiles
  meet; this round moved it across one tile border, as master's furniture item did. The
  reason given (13.5 ms for four tiles "under load") was wrong; see "G3, corrected" below.

**Senior review of the merge with master (2026-10-26): one P1, fixed.**
- The review compared every line on both sides of the merge and found nothing lost. It
  also checked the CR CR LF normalisation (#614): only line endings changed.
- **P1:** master's #596 put every short Properties input in one 120 px column. The three
  roof rows were written before that rule and the merge missed them (111, 54 and 79 px
  under a 120 px height field). They now use the shared helpers. A combo's tooltip is
  its own text (#596), so the "Shapes the roof in the 3D view" hint is on each row's
  label as well, set through `labelForField`; the label stays the field's buddy.
  `test_properties_panel.py::TestRoofRows` checks every input of each building kind in
  the shape the app draws it (a HOUSE as a polygon). Before, only a raised bed was
  checked, so the suite stayed green.
- **P2s, fixed:**
  - The raised-lawn and "gets a height" hold tests change the height through the panel's
    own command. A bare metadata write skipped the ground-band restack and reached a 2D
    order no user can reach.
  - The trailing-pass helper's cumulative counter is replaced by `_held`: the applied
    context differs from a fresh snapshot. The callers assert it where it holds.
  - §8.29.12 now says that the cut-outs follow the 2D paint order, which is right only
    after the restack scan. The scan is skipped when `last_command` is marked
    `changes_ground_band = False` (#592).
- **G3, corrected (after four more review rounds).** bench_large has no flat item of its
  own since L4, so the gate moves a stand-in terrace, placed from the plan's middle, across
  one tile border (two tiles) and where four tiles meet (four). Every move must repaint
  exactly those tiles.
  - **A four-tile edit does not reliably hold 10 ms on CI.** It can run over the budget by
    its last tile, as `BAKE_BUDGET_S`'s contract allows ("the budget plus ONE tile").
    CI run 40405246734 passed it uninstrumented, at ≤ 10 ms, and read 13.29 ms under
    coverage (passes median 1, max 1). Run 40407192860 read 12.15 ms uninstrumented
    (median 1, max 2). Until this PR, G3 printed its readings only when it failed. It now
    prints them in every serial (`-n 0`) run's log, as CI's perf steps run, so #615 can be
    decided on a distribution.
  - **Master (fee03ea3) against the branch,** measured with `scripts/measure_ground_edit.py`
    (committed: it opts out of power throttling and takes the other tree through
    `OGP_MEASURE_TREE`). Unthrottled, 61 moves a run, on the dev box:
    - Five alternating pairs on Qt's Windows platform gave medians of 3.50 ms on master and
      3.78 ms here across a border, and 6.73 against 7.02 ms on the corner. The branch was
      slower in 4 of 5 border pairs and 5 of 5 corner pairs.
    - Two pairs on the offscreen platform (CI's) showed no difference: corner 7.81 / 7.74 ms
      on master, 7.98 / 6.80 ms here.

    So L4 adds at most about 0.3 ms per move, and the work behind it differs. Per move the
    branch examines 2 records where master examines 1, because the terrace is a lawn's
    cut-out. On the corner it paints 14 records where master paints 20, because L4 builds
    furniture as solids: bench_large has 25 painted records against master's 45. Across a
    border both paint 7. The four-tile cost is master's. CI has never run a four-tile
    case on master.
  - Readings of 14–17 ms in two passes on the dev box came from Windows power throttling
    (EcoQoS), not from load or the code (#616). The first fix blamed machine load.
    e7916be7 then blamed the coverage job's 13.29 ms on the tracer and skipped the clock
    under a tracer. Its own CI run then failed uninstrumented, at 12.15 ms. The tracer is a
    real cost (about 1.4× on bench_large, §8.10.10) and pushed that one coverage reading
    over the bound, but the corner overruns without it too.
  - **The gate:** each case states its tiles, passes and median bound as literals.
    - Two tiles: a median of one pass and at most 10 ms, as on master, also under coverage.
    - Four tiles: a median of at most 20 ms and two passes. The last tile can fall into a
      second pass: CI's coverage run 40426416434 took 2 passes in the median (14.57 ms),
      after a commit that had briefly asserted one. A third pass would need 20 ms first.
    - **Owner decision (2026-10-29, #615):** a four-tile pass does not have to hold 10 ms
      on CI. The 20 ms / two-pass bound is final: it is the `BAKE_BUDGET_S` contract ("costs
      at most the budget plus ONE tile") measured on CI, 7.29–12.15 ms uninstrumented and
      10.57–14.57 ms under coverage. Two-tile edits keep 10 ms in one pass.
    - The test is renamed `test_a_small_move_repaints_few_tiles_within_its_bound`, because
      the old name promised four tiles in 10 ms. FR-3D-GROUND-03 now states this gate.
- The roof hint stays a tooltip (on the row labels and the spin boxes, and as the
  inputs' accessible description). The review proposed a visible hint row instead, but
  that would add a line of text to every building's panel, while the other 3D-only rows
  (Object height's source) explain themselves in a tooltip too.
- The merge commit's message says "three unused noqa directives". There were nine, in
  four files. The merge commit is pushed and not rewritten; ruff is clean.

**Owner's manual pass (2026-10-27).** The owner ran the checklist on the frozen exe:
everything passed except two path styles. They answered the eight questions:
1. **Objects without a height cast in 3D.** "In 3D they are also displayed with some
   height." Decision 2 is reversed for 3D: `BuiltBuilder` no longer clears
   `casts_shadow` on a build at a nominal or estimated height (and ADR-059's L1.6
   decision 3, "no height, no shadow", holds for the 2D sun study only). The 2D sun
   study and the hours-of-sun map are unchanged: the plan holds no height, as for a
   #557 plant estimate. (The second pass gave these objects real heights, which
   cast in 2D as well.)
2. **Detail-normal strength:** not decided. The owner asked how to see it; the PR
   shows the same walk-height views at 1.0 and 3.0. The value stays 1.0. (The
   second pass chose 3.0.)
3. **Roof colour: "2D should also be terracotta."** The HOUSE's default fill is now
   the 3D roof tiles' `palette.ROOF_TILE` (178, 90, 62), so a new house is the same
   terracotta in 2D and 3D. The 3D roof keeps its own material, as the owner chose
   over "follow the item colour". The walls took the fill colour, which would have
   made a new house one terracotta block. A house's walls are now
   `palette.SANDSTONE` (196, 174, 134), close to the tan the default walls had
   (210, 180, 140). A shed's walls still take its fill. A house's 2D colour no
   longer changes its 3D walls. Saved plans keep their stored fill, so an older
   house stays tan in 2D.
4. **Object porosity:** kept. Tables, the grill, the greenhouse and the trampoline
   cast their members' shadows in 3D, as fences do.
5. **Windows beside a centred door: yes.** `facade.window_columns` spaces the
   ground row on each side of the door's clear stretch. The upper row runs over
   those windows and over the door. Before, a 5.2 m wall had one window place, in
   its middle, and the door took it.
6. **The fog follows the camera.** "When entering the 3D view, I usually only ever
   see fog, until I zoom in." The fog's 26 m and 160 m were fixed, so a plan framed
   from 80 m lay a third of the way into it.
   - `look.fog_depth_cm(distance)` begins the fog at 1.5 times the camera's distance
     to its target and makes it full at 6 times that.
   - The floors are the old 26 m and 160 m, so close views keep their reviewed look.
   - The fog is full by 760 m. (The 800 m far plane's cut still showed from about 400 m;
     the second pass moved the far plane to 3 km.)
   - Near that cap the fog begins at most three quarters of the way to it.
   - `Quick3DHost.set_camera` sets `fogNear` and `fogFar`.
   - Five plan sizes and aspects lie in front of the fog from their framing distance
     and from three times it (`TestFogDepth`).
7. **The silent overhang clamp is acceptable.** #612 is closed.
8. **The "mushroom" shed stays** an honest result of its input.

**Owner finding: soil and gravel did not look like soil and gravel.** The 2D
painters were made for 6–10 cm lines:
- gravel was the colour at 100 / 255 over the ground, so a gravel path on a lawn was
  green, with stipple dots;
- dirt was the colour at 140 / 255, with a darker core.

The ground bake paints what the canvas paints, so 3D showed the same.
- **Painters:** both are now their fill textures (`FillPattern.GRAVEL` / `SOIL`, 1 px =
  1 cm in the item's frame, tinted like an area), opaque.
- **Gravel edging:** the stroke's own rim, the 3D edging's width and shade (three
  constants, held equal by a test). Two offset lines drew a spike inside every bend
  (#605 for gravel).
- **Dirt margin:** a faint 3 cm margin.
- **Dirt preset:** new dirt paths start in the sprites' light soil (125, 92, 62);
  150, 110, 60 read orange over the texture.
- **3D relief:** the gravel pebbles are gone. They read as little tents on a lawn, and
  the texture is the gravel.
- **Element budget tests:** gravel's dots were the densest walk, so the bake's
  element-budget tests now use a chain-link path 5 cm wide, which places an element
  every 4 cm, the dots' spacing. The hostile numbers hold unchanged (5 × 16,001 steps).
- **Pin:** `test_gravel_and_dirt_are_their_textures_and_hide_what_lies_under` renders
  each path over white and over black. Its inside must be the same picture with the
  texture's grain, and the old painters fail it.

**Owner's second manual pass (2026-10-27).** The owner confirmed the gravel and dirt
paths, the house colours, the camera and the fog, and decided the two open points:
1. **Every standing object has a real height.** "Why don't we simply allow setting a
   height for these objects as well? Doesn't make sense for me e.g. that a parasol
   doesn't have a height, while a trampoline has it."
   - The nine kinds of decision 2 have rows in `DEFAULT_HEIGHTS_CM`, at the values the
     3D estimate used: parasol 250 cm, fire pit 30, planter pot 50, cold frame 45,
     rain barrel 100, water tap 80, swing 220, hammock 110, pergola 250.
   - Each shows the "Object height" field with its default. It casts in the 2D sun
     study, in the hours-of-sun map and in 3D.
   - `core/object_height_estimate.py`, the snapshot's object estimate and
     `BuiltBuilder`'s estimate branch are deleted. The plants' estimate (#557) is
     unchanged.
   - `test_every_standing_object_kind_has_a_default_height` holds every object kind
     to a height without data, except the ground surfaces, the roof ridge, generic
     shapes, annotations and plants. A new object kind cannot slip back.
   - This supersedes ADR-042's roster note for swing, pergola and hammock. The 2D
     shadow model extrudes the whole footprint as a solid prism, so in 2D a pergola
     shades its footprint completely (a picket fence did too, until #440 gave fences a
     transmittance). A plant under a pergola reads as shaded in 2D. A footprint-fill
     factor — #440's caster transmittance — is still the way to honest frame shadows
     (#698).
   - A plant inside a cold frame or a planter pot now lies in its holder's 2D shadow.
     The per-plant sun estimate spares only a soil parent the plant stands on, and a
     plant cannot be linked to either kind. Measured at 50°N on 21 June: 0 minutes,
     975 without the holder. A greenhouse did this before. In 3D the cold frame's glass
     casts no shadow. Follow-up #621 spares a holder that stands around the plant.
   - Saved plans store no default, so an existing parasol resolves to 250 cm and
     casts in 2D after the update. Nothing in the file changes.
2. **Detail-normal strength 3.0** (`look.DETAIL_NORMALS`; `Garden.qml`'s default
   follows, held equal by `test_quick3d_qml.py`). In the walk-height comparison the
   gravel, the clods of earth and the paving joints stand out without noise. The
   slope clamp (±0.35) is unchanged. The 3D review recommended 1.0: at a 15° sun,
   43.6 % of the gravel's and 31.4 % of the lawn's texels reach the clamp at 3.0, and
   the lawn reads 6.7 luma darker. The owner chose from the views, so 3.0 stands.

**3D review and senior review of the first pass's changes.** The fog had hidden three
engine limits, which showed once it followed the camera:
- **Shadows ended at 90 m** (`shadowMapFar` 9000): a plan framed from 134 m lay clear and
  shadowless at golden hour. The shadow map now reaches as far as the fog begins
  (`Math.max(9000, fogNear)`); the top-down truth view keeps 9000. The shadow IoU gate's
  camera is a perspective camera 7.6–14.5 m from its target, where the fog begins at
  26 m, so its map still reaches 9000. `test_render_beauty_board.py` pins that distance;
  past 60 m the gate would measure another map. The board's shots are 25 m or closer, so
  their shadow map is unchanged; the far plane below still moves their cascades (re-review
  below).
- **Ambient occlusion drew a hard line about 101.5 m out** (6.6 luma at twice the default
  framing). Its strength fades out between 45 m and 90 m from the camera's target
  (`aoFade`).
- **The far plane cut the meadow in view.** At 800 m the cut showed from about 400 m
  (41.6 luma a row at 403 m, 76.8 at 600 m): the fogged meadow ended against the sky's
  darker lower half. The perspective camera's far plane is 3 km: from the camera's
  farthest 600 m it lies past the midpoints of the meadow's edges, 2 km out, so the
  meadow ends in full fog. Its corners, 2.83 km out, can lie past the far plane; the
  fog is full by 760 m. Measured 0.86 luma a row at 600 m.
- Not taken here: the gravel edging's chord at outer bends and square rail ends (#605),
  the horizon probe that cannot see the fog's change (#618), and the gravel texture's
  highlights in shade (#619).

The senior review found what the raster gates could not:
- **Gravel and dirt exported to SVG as black bars.** A texture-brush pen is written as its
  colour, and a texture brush's colour is black. The painters now fill the stroker's
  outline with the texture (PF-CAN-27); `test_path_style_export.py` exports every style.
- **Two routes still tinted a house's walls:** the roofless block and the plain block of a
  house that is not one plain outline. `BuiltBuilder` takes a `recolour` step that sees the
  parts of every route, and the HOUSE builder's makes every tinted part sandstone.
- **The facade's window bounds:** a long door wall now spreads its windows on both sides
  (half the wall's places each), and the upper row runs only over the ground windows
  built and the door, so a facade has at most twice its places plus one.
- Not taken here: with a layer's opacity under 100 %, the gravel rim and the dirt margin
  show through the texture drawn over them (#617).

**Re-reviews of the second pass's changes.** The 3D re-review confirmed the three engine
fixes at the default camera: on bench_large at golden hour 69–71 % of the plan lies in
shadow at twice the framing distance (0 % before), the AO line is gone, and the far-plane
step fell from 71 to 3.2 luma at 403 m. It found two regressions of this pass, both fixed:
- **The AO fade switched SSAO on at Low.** Qt's `setAoStrength` turns AO on whenever the
  strength is not 0, whatever `aoEnabled` says, so Low and compatibility mode drew SSAO
  once the camera stood 45–90 m out (PF-L3D-15). The strength is now 0 wherever AO is off.
- **A house's plain block had a sandstone top**, where the 2D plan draws roof tiles (24°
  of hue apart). The block's top is the roof seen from above, so it is `ROOF_TILE`; the
  walls under a real roof have no top.
- **Correction:** this pass's commit said the board was bit-identical. It is not. The
  3 km far plane moves the cascaded shadow fit: 1–6 % of every board frame changes by more
  than 8 luma, and the shadow IoU by at most 0.0023. Every gate still passes.
- The senior re-review found the consequence above for plants in a cold frame or planter
  pot (#621), and stale far-plane and no-height text, which is fixed.
- Not taken here: shadows still end inside the plan for a camera aimed at a plan corner
  or 600 m out, and the meadow's edge draws a 10–18 luma line at a pitch of 15° or less
  from 400–600 m (#624). Detail 3.0's pits and sky-blue crescents under a low sun are
  measured on #619.


## Addendum — L4 hardening (#611, #607, #604, #617, #624, #618, #609, #600, #603, #626, #536)

**Status:** Accepted; owner acceptance confirmed on 27 October 2026, shipped in [v1.34.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.1) via [PR #630](https://github.com/cofade/open-garden-planner/pull/630).

**Decision (27 October 2026).** Hold context only for parameters applicable to both
records, derived from door targets and the lawn predicate. Type changes apply
newly relevant or irrelevant parameters immediately. Quality changes admit lawn
geometry only when its preset draws it. Lawn normals use a dedicated material;
plant grass keeps its own material. Roof clamping remains in `core/roof_style.py`;
objects too small for detail use the plain verified prism. Mask batching retains
the original even-odd membership, holes and exact root positions.

Perspective shadows use reach from the eye to all four plan corners plus a
margin, bounded by fog reach with the existing floor. The meadow and clip plane
hold the full far frame including its corners. Distant horizon rows cover
67/202/403/600 m at default and 15 degree pitch; the outer-column adjacent-row
luma step is bounded by 3. The two-row statistic is retained separately. Far-plan
probes pin shadow presence and AO continuity at two and four times framing.
The shadow-agreement table now measures all 24 L4 object kinds; porous structures
retain the documented difference from solid analytical shadows.

For translucent paths, raster-mask only the rim in bounded 512-pixel device
tiles. A pair of odd-even stroke contours fails at overlaps; exact subtraction
was measured at 6.6 seconds for 4,096 points. DestinationOut removes the complete
inner stroke before one opacity composition. Opaque items retain the fast path;
textures remain vector pattern fills for SVG/PDF. The mask follows the painter's
device transform, clip and viewport, with bounded temporary memory.

Render oracles export actual sink-held meshes while keeping independent CPU ray
math. They rest the wind and wait for ground, camera LOD and forge admissions.
Document replacement legitimately re-admits forged meshes; unchanged same-document
passes still upload none. Geometry budgets count v0 and forge stages separately.
G6 retains its 20 cycles, 2 MB/cycle bound, positive control and median statistic,
but samples after two presented frames rather than a fixed 20 ms pump. No
readbacks are introduced into the memory loop. Fractional-DPR probes pin both
Qt scale factors, desktop windows fit their work area, and startup drivers retry
short idle refusals within one total deadline; the product host's idle contract
is unchanged. Evidence: `audits/2026-10/3d-hardening-611.md` in the risk chapter.

## ADR-065 addendum: Plant holders and per-plant sun exposure (#621)

**Context:** Phase 17 L4 gave every standing object a default height (ADR-065). Two of those kinds hold plants: `COLD_FRAME` (45 cm) and `PLANTER_POT` (50 cm), joining `GREENHOUSE` (220 cm) as 2D shadow casters. `collect_exposure_snapshot` previously spared only soil parents (`is_solid_soil_parent`). Because cold frames, planter pots, and greenhouses are not soil parents (they hold no soil test history or crop rotation links), plants growing inside them were covered by their solid prism all day, reading 0 hours of sun and generating false `sun_mismatch` warnings.

**Decision:** The caster walk (`ui.canvas.footprints.holds_plants`) now marks casters of type `COLD_FRAME`, `PLANTER_POT`, and `GREENHOUSE` with a positive finite height as `holds_plants=True`. `core.shade_aggregation._aggregate_day` automatically spares casters with `holds_plants=True` for any receiver point inside their footprints via static polygon containment. Plants growing inside a cold frame, planter pot, or greenhouse read open-ground sun (~16.5 h in Berlin summer solstice), while plants outside on the shadow side remain properly shaded. A drift guard pins the exhaustive set of placeable kinds with a default height that hold plants.

## ADR-065 addendum: a fillet is one smooth span, not a segment per vertex (#675)

**Context:** PR #672 baked a fillet's tangent arc into its host polyline as a dense run
of chords sampled at `FILLET_ARC_TOLERANCE_CM = 0.02` (2–4 cm each). The 3D fence and
wall builders spaced posts, pickets and chain-link wires **per drawn segment**: every
2 cm chord got its own posts (a shared corner once) and its own pickets, so a rounded
corner rendered as a solid curved block of planks. A chamfer was fine (one straight
chord); a wall's swept solid was always smooth (it has no posts).

**Decision:** a polyline vertex turning less than `CORNER_DEG = 20°` belongs to a
smooth span; the builder spaces posts, pickets, bars and chain-link wires by **arc
length across the span**, at the same pitch as a straight run, and breaks only at real
corners (90°, a chamfer's 45°). Rails stay one box per drawn segment — together they
follow the arc. The 2D geometry, hit-testing, undo and constraints are untouched: the
path is unchanged. The 2D **shadow** model does change: `fence_transmittance` groups the
same smooth spans and passes the builder's post count, so a curved fence no longer reads
as nearly opaque (wooden circle 0.21 against 0.33 straight; it read 0.00 before). A
filleted L (r 25 / 100 cm) now stands 5–6 posts, not 21–41; a smooth closed loop spaces
its posts around the whole perimeter. Pinned by `test_scene3d_builders.py` (post pitch
and count, no wall-of-planks, chamfer unchanged, smooth loop, dense/curved shadow
transmittance) and `test_string_lights.py` (#709's 40 cm gap and 2.5 cm chord rule on
the same sampled arc).

## ADR-065 addendum: a WILDFLOWER lawn is a flower meadow (#940)

**Context:** The bundled example plans of #940 need a wildflower meadow that reads as one
in 3D. A fill pattern reached 3D only as the baked ground picture (the 2D tint makes the
WILDFLOWER texture a light-specked green), and a LAWN with that fill grew the plain 7 cm
blades.

**Decision:** For this one case the pattern is geometry: the snapshot writes
`surface_pattern` (a build-only param, as for a deck) into a LAWN's record only when it is
WILDFLOWER, and the lawn builder grows a meadow — the lawn's blade share as taller, looser
blades, and flower heads on about one blade in six, in drifts, in `plant_art.FLOWERS`
colours, as a second untinted part named `lawn_blades`. No QML, shader, asset, setting or
file-format change. The rule and its pins: §8.29.12.

**Consequences:** Below High a meadow is only its painted picture. The heads flower all
year (#943). Grass up to 38 cm and heads up to 44 cm hide a plant lower than that standing
in the meadow: a plant does not cut a lawn (`context._NOT_A_CUTOUT`). A meadow costs about
+22 % of a lawn's triangles of the same area and its first build about 1.6 times the lawn's;
the plan's blade budget bounds both.
