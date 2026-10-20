# Archive 08: Phase 17 L1.6 world and stacking

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.13 What the built world and base stacking taught (Phase 17 L1.6, #385)

None of these reached a user. Each was caught by a test written to be able to fail — and each
passed the tests that only looked at one number.

- **A caster from the ground is not conservative — it hides the plant.** A plant in a raised bed
  was extruded from the garden floor *through* its bed. That looked like a harmless
  simplification ("its shadow is a little short"). Measured at a 35° sun: a 60 cm plant's tip
  reached 85.7 cm past its footprint, the 40 cm bed's own shadow 57.1 cm past the bed's edge — so
  a plant more than 28.6 cm from that edge cast nothing the bed did not cast already. Every plant
  in the middle of a raised bed was absent from the shadow overlay and the hours-of-sun map. Fix:
  a caster has a base (`core/shadow_geometry.ShadowCaster`, ADR-037 addendum); the tip moves
  `base / tan α` out (54.3 cm here). Pinned by
  `tests/unit/test_shadow_caster_base.py::TestSweptShadowDefinition::test_the_bed_casts_the_part_below`,
  which asserts the old tip was inside the bed's shadow. *"Slightly wrong" hid "missing": measure
  a simplification against what it is next to, not on its own.*
- **Changing shipped behaviour for one class of input: pin everything else first, and let an
  independent oracle say who is in the class.** The golden
  (`tests/fixtures/shadows/shadow_golden.json`) was generated from the unchanged code one commit
  before the change, and holds per bench plan the union of all shadows *and* the union of the
  casters the change must not touch. The test's own re-derivation of "which casters stand on
  raised soil" (it does not call the new function) found 22 of bench_small's 45 parented plants —
  the other 23 are in in-ground beds or on a trellis. The first assertion said 45. *An oracle
  that shares the implementation's assumption shares its mistakes.*
- **A closed polyline's stroke is a ring with a hole — and height, validity and budget all pass
  on a slab over the hole.** `polyline_footprint` of a fence drawn round a garden returns two
  rings. When this story was written both sat in `record.footprints` and the default builder laid
  a lid over all 48 m² of the test garden; the scene contract has since been corrected (§11.4.14,
  ADR-059): `footprints` holds the stroke's OUTER ring, the garden is a hole in `holes`, and
  `verify_builder` refuses a solid over it
  (`TestPolylinesAreBuiltFromTheCentreLine::test_the_gate_refuses_a_slab_over_the_garden`). The
  lesson for a builder is unchanged: the outer ring is not the fence's shape. Every built-world
  builder for a polyline reads `record.path` and works segment by segment; what catches a
  regression is plan-view AREA (`plan_area`: the union of the mesh's triangles seen from above ≈
  length × width), `covers(x, y)` at points inside the loop, and the hole-cover bound
  (`::test_nothing_is_built_over_the_hole`). The 2D shadow and heatmap still treat both rings as
  footprints; that is deliberately not fixed here (a separate issue; the golden pins it as is).
  - **The first `covers` probe sat on a diagonal.** It tested the centre of a symmetric loop,
    which lies exactly on an ear-clipping diagonal of the lid: "not covered", under a lid. Probe
    points go off every axis of symmetry.
- **A bounding box is aligned with the frame, not with the building.** The spike laid a shed's
  ridge along its scene-frame bounding box. In the item-local frame a *rectangle item* is
  axis-aligned and the rule looks right; a shed drawn as a *polygon* at an angle has its vertices
  turned inside the local frame, and the ridge came out askew to its walls. Found only because the
  builder matrix turns the local geometry by 17° and 213.5°, and only by a containment assertion
  (the ridge tile left the roof). Fix: the box aligned with the footprint's longest edge
  (`roofs.bounding_box_ridge`). Pinned by
  `tests/unit/test_scene3d_builders.py::TestShedRidge::test_it_turns_with_a_footprint_drawn_at_an_angle`.
  *A builder never sees the item's rotation, so "parametrise over rotation" must also mean the
  geometry inside the record.*
- **A ridge tile with square ends overshoots an eave it meets at an angle** — by
  `half width × tan θ` (2.4 cm on a dragged ridge, 3.2 cm on a trapezoid). The top was exact, the
  budget held, every face validated. Fix: each of the tile's two foot lines ends where *it*
  crosses the roof's edge. Caught by `outside_distance(plan points, eaves) ≤ 1e-3`.
- **Clamping a leaf's vertices at the trim height turns leaves inside out.** The first hedge
  brought every vertex above the height down onto it. A leaf standing mostly above the line was
  flattened into the plane and its winding flipped against its stored facing (24 matrix cases).
  Fix: a leaf that reaches too high is moved down *whole* (`hedges.leaf_shell`); the highest leaf
  sits on the height, so the top is still exact by construction.
- **`core/scene3d/` cannot import pyclipper** — the package's import rule (AST scan) allows the
  standard library, numpy and Qt-free `core` modules. A roof's overhang needs an outward offset;
  `primitives.offset_ring` is a mitre offset in numpy in which every edge moves exactly the
  distance (asserted per edge). If a builder ever needs polygon booleans, they go through a
  `core` module, not around the scan.
- **Six tests unpacked the caster as a pair.** `footprint, height = collect_shadow_casters(...)[0]`
  — the cost of a positional type is paid when it grows. `ShadowCaster` is a `NamedTuple`, so the
  third field is named from now on; the shadow functions still accept a bare pair (the spike's
  probes pass one) and treat it as standing on the ground.

Found by the senior review's first round, in code whose tests were all green:

- **A link is not a location.** The first cut lifted a plant onto its bed's soil whenever
  `parent_bed_id` named a raised bed. But the app keeps that link as bookkeeping: it is evaluated
  when a plant is created (also in bulk, also pasted), dropped, or moved by the agent — and by
  nothing that changes a bed — and `set_parent_bed` sets it on purpose
  without containment. Shrink a raised bed away from its plant and the link stays — the plant on
  the lawn then cast from 38 cm, and at a 15° sun its shadow began 141.8 cm away from it, with
  111.8 cm of lit ground in between. New wrong output in the shipped overlay and heatmap, from a
  change whose golden proved "nothing on the ground moved" (true — and beside the point). Fix:
  `item_base_cm` lifts only when the link holds AND the item's centre is inside the parent's
  shape, with the app's own point-in-bed construct, extracted once
  (`footprints.shape_contains`; WHICH point it is asked with was corrected in the second round,
  below). Pinned by
  `tests/integration/test_scene3d_base_stacking.py::TestTheLinkAloneNeverLifts`. *Before keying
  geometry on a relation, find out when the relation is re-evaluated — here: when a plant is
  created (also in bulk, also pasted), when one is dropped, when the agent moves one; never when
  a bed changes.*
- **"Bit-identical" has to say on which machine.** The golden compares exactly only on win32;
  the CI test jobs run on Linux, where the gate is structure plus 2e-3 cm. The ADR said
  "bit-identical, by construction and by proof". The proof that holds everywhere is a different
  test: the released module kept as an oracle next to today's (§8.10.7). *A claim about
  exactness names the platform, or it is the weakest platform's claim.*
- **"The body is wider" was reasoning; the measurement said the opposite for three of five fence
  styles.** The ADR compared a 3 cm stroke with 9 cm posts and concluded that 3D shadows are
  wider. Projecting the meshes onto the ground: a picket fence casts 0.67–0.70 of the 2D strip's
  shadow, a metal fence 0.19–0.24, a chain-link fence 0.13–0.19 — fences are mostly air, and the
  2D model casts a solid strip. Walls, stone-wall and hedge fences ARE wider (1.04–1.37). The
  table is now produced by a committed script and held by a test.
- **A mitre limit is not a bevel.** `MITER_LIMIT = 4` cut a hairpin's mitre at four offsets: a
  116 cm eave spike on an acute-triangle house, 76 cm of coping on a hairpin wall — and the
  footprint test's √2 bound only ever saw right angles. Fix: bevel beyond 2 offsets on the side
  where the edges run apart (`BEVEL_BEYOND`); keep the true intersection where they meet.
  Acute triangles and hairpins are in the matrix now. *A containment bound proven for the
  corners in the test matrix says nothing about the corners that are not in it.*
- **A mirrored name set without a guard chooses for the names it does not know.** The fence
  builder's own list of five fence styles sent every other value to the picket fence — a path
  style, and any fence style added to the 2D table later. Fix: one dispatch (`builders/lines.py`),
  a plain panel for what no builder knows, and the mirror pinned against the 2D table. The
  container material names are imported instead of retyped, and the nominal height asks the 2D
  resolver instead of keeping a third copy of the container set.
- **A lip the plan does not hold lowered the plan's soil by 2 cm.** The 2 cm soil drop under a
  rim suits a raised bed, whose height is a rim. A container's height is its soil FILL height —
  the resolver says so in a comment marked "known simplification". Applying the drop there put
  the plant under the plan's own soil level. Fix: `soil_surface_cm(type, height)` — at the
  height for a container, 2 cm under the rim for a bed — and the drop is documented as the
  assumption it is, with its effect on shadows (7.5 cm at a 15° sun).
- **A tuple's third element is whatever its maker meant.** `compute_scene_shadows` read
  `caster[2]` as a base for any sequence longer than two. Nothing passed one — yet. Fix:
  `caster_fields` unpacks by type and refuses everything but a `ShadowCaster` and an exact pair.
- **A budget raised to make a loaded machine pass stops being a budget.** The build budgets went
  from 40 / 60 to 60 / 90 ms in the last commit of the first cut, although the loaded medians it
  quoted were under the old ones. With the ×3 CI factor a per-vertex Python loop would have
  passed. They are back, and a clock-free call count stands next to them (§8.10.7).

Found by the senior review's second round, again with every test green:

- **The first fix made a shadow depend on a warning badge.** Round 1 asked "is the plant inside
  its bed" with the app's own membership point, the centre of `boundingRect()` — the review had
  prescribed exactly that, for consistency with auto-parenting. But `CircleItem.boundingRect()`
  grows towards +x / +y while the antagonist badge shows, so its centre moves by up to 1.8 cm
  along each axis (2.55 cm in all):
  a linked plant 1 cm inside a raised bed's east edge stood at 38 without the badge and at 0
  with it, in the 3D record and in the 2D caster. Fix: the LIFT asks the item's stable
  geometric centre (`footprints.standing_point`, the outline's anchor — the origin of the 3D
  record); the link decisions keep their shipped point; one predicate (`shape_contains`) serves
  both. *A bounding rect is a paint rect. Before using one as geometry, list everything that
  changes it: here a badge, a companion highlight, the shadow margin, the spacing ring.* And
  the "identical behaviour" of the refactor that extracted that point was true by reading
  only: swapping it for the geometric centre passed all 114 related tests, until one probe
  where the two points differ pinned each decision (`TestWhichPointEachDecisionAsks`).
- **A universal sentence stood next to a truth gate with no number behind it.** The gate row
  said that a 3D shadow ends where the 2D one ends, whatever the kind — reasoned from "the
  height is the same number". The tip is cast by the highest EDGE, and a gable's ridge stands
  mid-house while the 2D prism's top edge is at the far wall: asked for the reach, the story's
  own script printed −270 cm for the bench house with the sun square to its ridge, −150 cm for
  a shed, +30 cm along the ridge (the overhang), +15 cm for a wall (its section). A reviewer
  would have reported a 2.7 m truth-gate miss, or a creator would have "fixed" the roof. Fix:
  the sentence is deleted, the reach is a column of the script and of every copy of the table,
  and a test scans docs and skills for the claim. *Next to a gate, only numbers a script
  prints.*
- **"Every line solid is held to the bound" held for the sizes in the matrix.** `verify_builder`
  refuses a solid over more than half of a hole. The matrix's loops are 8 m × 6 m; a closed
  wall of 1 m side covers 56 % of what it encloses with its 38 cm section — correctly — and is
  refused. The bound is stated with its size now, and a 1 m loop is pinned with an explicit
  limit. The same shape of mistake as the corner bound: "nothing further than 2 offsets" held
  for legs longer than the section; a 25 cm-leg zigzag under a 38 cm wall reaches 2.7 offsets.
  *A bound asserted over a matrix is a bound for the matrix's parameter ranges; say the range.*
- **A lookup that is "one per walk" is the place for what a walk needs once.** The base rule
  called Qt's `contains` per plant, which rebuilds the parent's shape each time; with the
  plant's `boundingRect()` (a Python override) that was 6 µs of the 7.6 µs the rule cost per
  plant. `ItemLookup.shape_of` builds the shape once per parent and walk; the rule costs 2.8 µs.

Found by the senior review's third round — CI was red on a head whose every local run was green:

- **The fix for a fixed wait was a race.** Round 2 replaced `qtbot.wait(400)` by "wait for the
  recompute count, then for the debounce timer to be idle". CI: `assert 6 == 1 + 4` in the Test
  job, green in the Coverage job on the same commit, green in every local run. A recompute sets
  the overlay's path, the scene emits `changed` one event-loop round later, and `changed` is
  wired to the debounce: straight after a recompute the timer is idle and the echo is still on
  its way. Delivered late, it carried an edit nothing had announced into the negative control.
  Fix: `settled` waits for the count, then for the echo (a `scene.changed` delivered since that
  recompute), then for the debounce; and two tests hold both halves of the race still by
  running the recompute synchronously. *A timer being idle says nothing about what is queued.
  If a system answers its own action with a signal, that signal is the thing to wait for.*
- **A field's description is the contract an agent reads.** `link_is_geometric: false` on a
  LIFTED plant was pinned by a test and explained in an ADR addendum, while the tool schema
  still told an agent that false means "the plant sits outside the bed's outline". The
  description, the tool's docstring and FR-AGENT-16 now say what the field tests and where it
  can disagree with the sun study.
- **A cache with a lifetime needs more than a sentence.** `ItemLookup` holds each parent's
  shape for one walk; kept across a bed resize it answers 38 where the truth is 0. The guard is
  a source-reading test: constructed only in the two walks, never stored.
- **A range read at a coarse step is not a range.** "From 16 cm to 120 cm" came from readings
  2 cm and 10 cm apart; at 1 cm the wall starts at 15 and the hedge fence is refused again at
  114 after passing at 112. State the step, or pin the cases a test needs and no more.
- **A bounded memory can still be an unbounded log.** The unknown-style warning cleared its 64
  names when full, so 65 names wrote 65 lines on every rebuild pass. When full: one line, then
  silence — the policy the snapshot's log already had, three files away.

Found while merging the scene contract's second fix round (`9944012`):

- **A bound added in one layer opens a state in the layer above.** The contract began to refuse
  every length beyond 10 km (`MAX_LENGTH_CM`). A raised bed of 10 km + 1 cm then had no record —
  and its plant, whose base is the bed's soil 2 cm lower, had one: floating at 9,999.99 m over
  nothing. A taller bed took its plant out of the 3D scene with it (the plant's base was out of
  range too). Garbage in, but the rule "a parent that has no solid is not there" was mine and
  no longer held. First fix: `soil_surface_cm` gives no base beyond `MAX_PARENT_HEIGHT_CM`, the
  contract's bound mirrored and pinned. **That fixed one axis and named it a rule**: a raised
  bed 30 km WIDE has an ordinary height, got no record all the same, and its plant stood at 38
  over nothing (review round 3). The rule is settled where the fact is known: `snapshot_records`
  puts every record whose parent got none on the ground, for whatever reason the parent was
  left out; the height bound stays as what it is — no base from a height beyond the bound.
  *When an upstream contract starts refusing something, probe what your own rule derives from
  it — and put the consequence where the refusal is visible, not where one symptom of it was
  first seen.*
- **A flag beats an inference, and the builder must not lean on the producer.** Round 1 could
  not tell a self-crossing house that resolves to one ring from an ordinary one, and gave it a
  roof. The contract now says `outline_resolved`, and drops the ridge. The house builder reads
  the FLAG — a test hands it a resolved ring WITH a usable ridge and still gets the block — so
  the rule does not rest on a second module remembering to leave a param out.

Found by the last review pass and at the merge of the plant story (`5c44578`):

- **A requirement stated the mechanism where it meant the invariant.** FR-SUN-11 said that
  moving a plant into or out of a bed changes its shadow "only where the move also re-evaluates
  the link". False in both directions for a LINKED plant: the base is asked on every walk with
  the plant's own centre, so any move takes it 38 → 0 → 38 with the link untouched. What is
  limited is the LINK. *Write what holds for the user (where the plant stands follows its
  centre); put the mechanism's limits (which gestures link) next to it, as limits.*
- **The list of "how a link comes about" was two entries short.** All four array actions copy
  the source's `parent_bed_id` through serialisation (only `item_id` is stripped) and the bed's
  child list is not told; a plant mirror-copied without its bed gets no link at all. And "a bed
  that is moved takes its plants with it" holds for a mouse drag, the arrow keys and an agent
  move, not for a typed coordinate or align / distribute. Each is pinned now
  (`TestCopiesAndMovesThatDoNotEvaluateTheLink`) and is in the follow-up issue. *A list written
  from the call sites of three functions misses every path that calls none of them: also
  enumerate the ways an item is CREATED and the ways it MOVES.*
- **Two stories, one registry.** The plant builder and the built world were developed against
  separate registries; `production_registry()` now holds both. One test says that no kind
  belongs to both families, that each of the 15 kinds resolves to its own builder, and that
  the rest of the `ObjectType` enum falls to the default — over the enum, not over a sample of
  it (the earlier test checked eleven hand-picked kinds).

The rest of that pass is method and lives in §8.10.7: a running timer asserted as a fact, "up
to N" without the worst direction, a source guard without a census, a committed script outside
the suite's isolation.
