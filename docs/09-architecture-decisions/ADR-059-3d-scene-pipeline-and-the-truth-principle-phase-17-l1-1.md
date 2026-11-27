---
id: ADR-059
title: "3D scene pipeline and the truth principle (Phase 17, L1.1)"
status: "Accepted (2026-10-11, #385 story L1.1, epic #383). This is the scene-pipeline ADR the epic reserved as \"ADR-049\" (that number went to frost dates; ADR-053 announced it for L1.1). It was written as \"ADR-054\", then carried as \"ADR-056\" and as \"ADR-064\", and renumbered each time before it reached master, where Package F and the audit packages had taken those numbers while this package was in work (likewise its concept section, written as 8.26, 8.27 and 8.32 before it became 8.29, and its requirements bucket, written as FR-32, FR-33 and FR-36 before it became FR-33) — an older note or branch that says \"ADR-054\", \"ADR-056\" or \"ADR-064, 3D scene pipeline\" means this record, and \"ADR-065\" in a note older than L4 (#388) means ADR-060 (since L4, ADR-065 is the built world's record). The same renumber moved the test-policy sections 8.10.23–31 to 8.10.5–13 and the pitfall sections, now the PF entries of §11.4. It builds on ADR-048 (Qt Quick 3D, GO) and ADR-053 (one sim clock). Nothing is rendered by this story: it is the Qt-free foundation L1.2–L1.7 build on. **Amended the same day by the independent review of the story** (two interface defects and a list of smaller ones — decisions 1, 3, 8, 9, 10 and 12 and the section \"What the first version got wrong\" below); the text here is the contract as it stands after that round."
legacy_anchor: adr-059-3d-scene-pipeline-and-the-truth-principle-phase-17-l11
---

# ADR-059: 3D scene pipeline and the truth principle (Phase 17, L1.1)

**Status**: Accepted (2026-10-11, #385 story L1.1, epic #383). This is the scene-pipeline ADR the
epic reserved as "ADR-049" (that number went to frost dates; ADR-053 announced it for L1.1). It
was written as "ADR-054", then carried as "ADR-056" and as "ADR-064", and renumbered each time before it
reached master, where Package F and the audit packages had taken those numbers while this package was in work
(likewise its concept section, written as 8.26, 8.27 and 8.32 before it became 8.29, and its requirements
bucket, written as FR-32, FR-33 and FR-36 before it became FR-33) — an older note or branch that says
"ADR-054", "ADR-056" or "ADR-064, 3D scene pipeline" means this record, and "ADR-065" in a note older than L4 (#388) means ADR-060 (since L4, ADR-065 is the built world's record). The
same renumber moved the test-policy sections 8.10.23–31 to 8.10.5–13 and the pitfall sections, now the PF entries of §11.4. It
builds on ADR-048 (Qt Quick 3D, GO) and ADR-053 (one sim clock). Nothing is rendered by this
story: it is the Qt-free foundation L1.2–L1.7 build on. **Amended the same day by the independent
review of the story** (two interface defects and a list of smaller ones — decisions 1, 3, 8, 9, 10
and 12 and the section "What the first version got wrong" below); the text here is the contract as
it stands after that round.

## Context

- **The shipped 3D view rebuilds everything.** `collect_scene3d_records` returns scene-space
  prisms and decals, and `Qt3DAdapter.rebuild` replaces every entity and re-frames the camera on
  each change. L1's workspace ("Plan / 3D / Split without camera resets") and live sync need the
  opposite: the engine must receive only what changed.
- **The engine punishes rebuilds.** L0 measured (ADR-048, `ogp-3d-renderer` §2–§3): one geometry
  per Model lifetime, a full re-upload on re-attach, ~10 ms per 100k vertices, and an
  array-driven `Repeater3D` that recreates every delegate when one element changes.
- **The spike built its world from private canvas helpers at absolute scene positions** (TD-036),
  with hacks a product cannot keep (a chair "facing the first table").
- **Beautiful wrong frames happened in L0.** The first board lit the wrong roof slope (each slab
  stored the other slope's normal), a December board showed June plants, a BBQ stood 15.6 % too
  tall. Each looked fine. A planning tool that misstates the plan is broken however good it looks,
  so "truth" has to be something a test can fail, not a sentence in a style guide.
- **The Qt-free cores are the NO-GO insurance** of ADR-048 and must not depend on the engine.

## Decision

1. **One pipeline; everything after the snapshot is Qt-free** — the package `core/scene3d/`
   (standard library, numpy and Qt-free `core` siblings only; pinned by an AST scan over every
   module that also follows those siblings):

   ```
   live canvas items ──snapshot_records()──▶ {item_id: Record}        ui/view3d/snapshot.py (GUI thread)
                                                  │ diff() against the last snapshot       scene_diff.py
                                                  ▼
                             SceneSync.apply ──▶ builders, for added + geometry only       build.py, sync.py
                                                  │ MeshPart (item-local frame)             mesh.py, polygon.py
                                                  ▼
                                              EngineSink                                    sink.py
                                  Qt Quick 3D (L1.2) · RecordingSink (tests, NO-GO path)
   ```

   "Qt-free" is a statement about this package's SOURCE: no module of it, and none of the `core`
   siblings it imports, imports Qt. It is not a statement about the interpreter: importing
   `open_garden_planner.core.scene3d` runs `core/__init__.py`, which loads PyQt6 for other
   modules of `core`. A process that must stay Qt-free needs that package `__init__` untangled
   first; the scan guarantees only that nothing here *uses* Qt.

   The former `core/scene3d.py` became `core/scene3d/legacy.py` — the Qt 3D view's record, its
   scene-space extruder and its frame helper — and the package re-exports every name, so the Qt 3D
   window, the dormant spike and their tests did not change. **L1.10 deletes exactly that file**
   (and its re-exports). The two functions of the old module that the new pipeline uses as well
   moved out of it: the ear clipper `triangulate_polygon` to `polygon.py`, `sun_direction_scene`
   to `frame.py`; `legacy.py` imports them back.
2. **Item-local geometry plus a rigid transform.** A record's `footprints` / `path` are
   centimetres relative to the item's own anchor — the circle's centre, `rect().center()` of an
   ellipse or rectangle (the geometric centre, never the decoration-expanded `boundingRect()`:
   #219), the centre of the vertex bounding box of a polygon or polyline — and
   `transform = (east_cm, north_cm, rotation_deg, base_cm)` places that frame:
   `scene = T + R(θ)·local`, θ counter-clockwise seen from above with north up. Moving or rotating
   an item changes the transform and nothing else, so the engine re-poses a Model.
   - The transform is **derived from `item.sceneTransform()`**, never from `pos()` + `rotation()` +
     `transformOriginPoint()` (the #218/#219 lesson). Qt's matrix is
     `m11 = cos a, m12 = sin a, m21 = −sin a, m22 = cos a`, so `θ = atan2(m12, m11)`; on the Y-up
     canvas Qt's `setRotation(+90)` takes local +x (east) to scene +y (north). Measured, not
     assumed: the matrix reproduces `mapToScene` bit for bit, and `transform ∘ local footprint`
     reproduces `item_footprints` to **1.5e-7 cm** over 96 cases (gate: 1e-6) — for every shape
     compared vertex by vertex, and for a polyline's centre line. **One thing is outside that
     number: a polyline's stroke polygon**, which agrees only to pyclipper's 1/1000 cm grid
     (measured 1.6e-3 cm; see the rejected alternative "the 2D stroke polygon of a polyline").
   - **A circle's rotation is 0 by construction.** The 2D footprint polygonises a circle around its
     mapped centre and does not turn with the item; a record that turned would either disagree with
     the 2D shadow or make a rotation a geometry change.
   - **A scene transform that is not rigid is baked.** Scale, mirror or shear (an item in a scaled
     group) cannot live in a rigid transform, so the whole linear part goes into the local
     coordinates and the rotation is 0. `scene = T + local` still holds; the price is that rotating
     such an item rebuilds it. The app never produces such a transform on a garden item today.
3. **A record is everything a builder needs**, as plain immutable data (`record.py`): `kind`
   (ObjectType name), `shape`, `footprints` and `holes`, a polyline's centre line `path` and
   `path_width_cm`, `height_cm` — the 2D shadow's own `effective_height_cm(..., at_date)`, `None`
   meaning decoration that casts no shadow, exactly as in 2D — and `params`, a sorted immutable
   mapping: the seed (item id), a circle's radius, a HOUSE's ridge ends in the HOUSE's frame read
   from the live ridge item (ADR-046), the canonical species key and common name, the plant
   category, a path/fence style, a container's material. `material` holds the item's own sRGB
   fill, stroke and pattern. Not captured: what only the spike's hacks needed.
   - **`footprints` are OUTER rings; `holes` are what is cut out of them.** An outer ring is a
     simple polygon, counter-clockwise (positive signed area); `holes[i]` are the clockwise rings
     inside `footprints[i]`; both orientations are enforced by `Record` itself. The ground an item
     covers is the outers minus the holes (`Record.regions`, `Record.plan_area_cm2`). A polyline's
     stroke is sorted into both — a fence that closes on itself is one outer ring and one hole, a
     ladder drawn as one stroke one outer ring and a hole per cell. `holes` is part of
     `geometry_sig`. Holes are not a stroke's alone: a polygon drawn crossing itself can enclose
     a pocket.
   - **When a stroke that almost closes does close.** A stroke has butt ends
     (`polyline_footprint`: `ET_OPENBUTT`): it reaches half its width to either side of the centre
     line and not at all past its end points. Two ends that stop short of each other AT A CORNER
     therefore close the loop only while the gap is at most half the stroke's width — a 10 cm
     stroke closes a corner gap of up to 5 cm, and one of 6 cm stays open — and a gap in the
     middle of a straight run never closes, however small. (The first version of this text said
     "a gap narrower than the stroke"; measured, that is wrong by a factor of two at a corner and
     altogether in a straight run.)
   - **Every region of a record is one a builder can build — as a checked fact.** ONE predicate
     says what that means: `polygon.is_buildable_region(outer, holes)`, true exactly when
     `polygon.cut_region` — the triangulation the default builder itself uses — cuts the region
     and proves the cut (every triangle counter-clockwise, their areas summing to the region's).
     The snapshot asks it for every outline it turns into rings and hands on nothing for which
     it does not hold; `prism_mesh` calls the same cached function, so "the predicate holds" and
     "the default builder builds it" cannot come apart. An outline for which no reading holds
     gets no record and is reported (decision 12): measured over 7,500 random self-crossing
     polygons and 4,500 random strokes, none.
   - **A polygon that crosses itself is resolved in the snapshot, and the record says so.** It
     becomes buildable regions by the non-zero rule: one ring, several, or rings with holes —
     the ring COUNT says nothing (measured: one outline of five vertices resolves into a single
     ring of ten). What says it is `params["outline_resolved"]` (`PARAM_OUTLINE_RESOLVED`), True
     and present only for such a record — and **a HOUSE resolved this way carries no `ridge`**:
     the drawn ridge belongs to the drawn outline, not to the regions that replace it, so a
     house builder's "no usable ridge" path fires and builds `record.regions`. Its vertices sit
     on pyclipper's 1/1000 cm grid; where two parts of it meet in a single point and the region
     cannot be cut as it stands, they are drawn apart by 0.002 cm (11 % of random outlines; the
     rest keep the clipper's exact coordinates). A vertex placed twice in a row — a double click,
     a closing vertex that repeats the first — is dropped first and resolves nothing: such an
     outline stays the drawn ring, vertex for vertex.
   - **pyclipper's reading of such an outline is checked, not trusted.** The ring hierarchy is
     taken from its `PolyTree` (who is whose hole is the clipper's answer, not a point test on a
     boundary vertex), and every reading is held against the DRAWN outline: its winding number
     on a 48 × 48 lattice must agree with what the regions cover. Needed, because for an outline
     that retraces one of its own edges the clipper's answer is sometimes wrong — measured: a
     solid triangle of 357 cm² handed out as a hole (`StrictlySimple`), and a plain union whose
     signed ring areas sum to 33,133 cm² for an outline that fills 36,704. Three readings are
     tried in order (the strict tree; the union with a 0.002 cm band cut away along its rings;
     the drawn rings with that band cut away along every edge), and the first that is buildable
     AND matches the outline is taken. Stated as measured: in 19,500 random outlines every wrong
     reading of the clipper's was also not buildable, so the buildability check alone turned it
     down and the outline check never decided — the mutation check showed that by letting "the
     reading is taken on trust" survive. The outline check stays as the safeguard for a reading
     that is wrong AND buildable, and is pinned with a simulated one.
   - Non-zero because it is the rule the 2D shadow fills a caster's own
     footprint with — measured at a vertical sun: both lobes of a bow-tie, the whole star of a
     pentagram — and the solid must stand where its shadow starts. It is *not* what the canvas
     paints for every such polygon: Qt fills by odd-even, which leaves a pentagram's centre open
     (7,757 against 11,226 cm² for a star of radius 1 m); for a bow-tie the two rules agree. A
     drawn self-crossing polygon is an accident more often than a plan, and of the two readings
     the shadow's is the one a truth gate compares against.
   - **No length beyond what a plan can hold.** `record.MAX_LENGTH_CM` = 1e6 cm (10 km): a
     height, a stroke width, a radius, every coordinate of `footprints`, `holes` and `path`, the
     position and base of the transform, and every float param is held to it by `Record`,
     `Transform` and `Params` themselves (`RecordRangeError`, a `ValueError`). The bound is from
     the domain — nothing in a garden plan is taller, wider or farther from its origin — and it
     is decided in the record, once, because of what it prevents: a plan file edited by hand can
     hold `"object_height_cm": 1e300`, a positive finite float that is infinity in a mesh's
     float32. It passed "positive and finite" and reached a sink that does not validate as
     non-finite positions, for the default prism and for every other builder alike (found by the
     plant story's review, at the pipeline level). An infinite height falls under the same rule
     (the first version turned it into "no height", silently). The mesh layer refuses the same
     thing on its own: `Mesh.from_arrays` raises for a value that is not finite once it is
     float32, and `prism_mesh` for such a height or coordinate before computing with it — so a
     hand-made call cannot emit one either.
   - **A ROOF_RIDGE item has no record.** The ridge reaches the pipeline as its HOUSE's `ridge`
     param. As a record of its own it changed *geometry* whenever the house turned (the app
     re-derives the ridge item's points: measured on 400 of 400 rotations), which would have made
     "rotate → transform only" false for the one item a house owns.
4. **Three signatures — and a signature is only an accelerator.** `geometry_sig` covers what
   changes a mesh, `transform_sig` the transform, `material_sig` the material. `item_id`, the
   display `name` and `parent_id` are in none; selection and hover are not in the record at all.
   Signatures are Python hashes, and **`hash(-1.0) == hash(-2.0)`**: a vertex moved from −1 cm to
   −2 cm has the same tuple hash. `Record.same_geometry` therefore compares the signature first
   and the values second; a pure-hash diff would have hidden that edit from the engine.
5. **One record grid.** Every length is snapped to 1e-7 cm and every angle to 1e-9°. An unchanged
   scene snapshots identically without it, but the same geometry reached along another float path
   must not read as an edit. Measured: the app re-writes a HOUSE's ridge points by `+ delta` on
   every move, and unsnapped **689 of 1,000 moves changed the HOUSE's geometry**; snapped, 0 of
   20,000 (the dust had reached 1.1e-10 cm). The grid is far below anything the UI can express and
   below float32 vertex resolution beyond ~1 cm from the origin, so it cannot hide an edit. When
   dust does straddle a grid line the cost is one redundant sink call, never a wrong frame.
6. **`diff(old, new) → SceneDiff(added, removed, transform, material, geometry, reordered)`** —
   three *independent* comparisons per surviving item: it is listed under each aspect that changed
   and under no other (all eight combinations are pinned). `reordered` reports a changed paint
   order; it is never a geometry change and causes no engine call, but the ground bake (L1.5)
   paints flat surfaces in that order.
7. **Meshes live in the item-local frame**, in the spike's vertex layout (`mesh.py`).
   `Mesh.validate()` rejects wrong dtypes or shapes, non-finite values, out-of-range indices,
   non-unit normals, and a flat face whose stored normal is not its winding normal (dot < 0.99 —
   the L0 roof bug); foliage and grass are exempt from the last by design. A `MeshPart` names a
   material kind, whether it casts a shadow, and whether it is **tinted**: the builder leaves the
   vertex colours neutral and the sink multiplies them with the item's material, so a recolour is
   an `update_material` and never a rebuild.
8. **The engine boundary is ten methods** (`sink.py`): `begin`, `commit`, `add`, `remove`,
   `update_transform`, `update_material`, `replace_geometry`, `set_sun`, `set_ground` — and
   `clear`. (Eleven since L1.8: `set_selection`, the selection ring — ADR-060 addendum
   "selection, info card and walk".) `RecordingSink` implements it with a list and a dict, answers "what would the engine
   hold now?", and enforces the protocol — every call but `clear` inside `begin`/`commit`, no
   `add` of a held id, no update of an unknown one. `set_sun` takes plain solar data from
   `core/solar` (light = −sun vector, ADR-037); `set_ground` a deliberately minimal plan rectangle
   that L1.5 extends.
   - **`clear()` is the verb recovery needs.** After it the engine holds nothing — no items, no
     sun, no ground — and no transaction is open. It is legal at any time: inside a transaction
     (it aborts it), outside one, on an empty sink. Without it "tear the scene down" could not be
     said through the protocol, and a sink that failed in mid-transaction could not be brought
     back by anything `SceneSync` is allowed to call.
9. **A builder is a pure function of one record's geometry part** (`build.py`):
   `Builder = Callable[[Record], tuple[MeshPart, ...]]`, looked up by `kind` in a
   `BuilderRegistry` *instance*. It may not read the transform, the material, the id, the name or
   the parent — the pipeline calls it only when `geometry_sig` changed, so anything else it read
   would go stale. `verify_builder` enforces that in tests. The default builder is the honest v0: a
   prism of the footprint — outer rings minus their holes, with walls around each hole that face
   into the hole — whose top is exactly the resolved height, and nothing for an item without one.
   - **The default builder never emits a wrong solid.** `prism_mesh` refuses a ring that is not a
     simple polygon (`ValueError`: `SceneSync` then shows the item without a solid and reports it)
     and checks its own cap before returning it: every triangle faces up and their areas sum to
     the region's (`polygon.cut_region`, the function behind `is_buildable_region`). Two kinds of
     triangle are left out because they are nothing: an ear whose three corners lie on one line
     (vertices of different rings along the edge of a diagonal stroke — its area is float noise
     around zero), and a cap triangle below the resolution of the engine's float32 coordinates
     (a doubled area under 5e-7 · the largest coordinate · its two edges). Either would come out
     wound downwards in the mesh as often as not — measured on a ladder drawn as one stroke:
     13 of 239 cap triangles. `prism_mesh` takes any sequence of `(x, y)` pairs for a ring —
     tuples, lists, numpy rows.
   - **What an outline may cost is bounded — as work, as a sum, and before the work.** Each hole
     is joined to the boundary by a bridge found in one pass over the edges (holes × vertices),
     then the merged ring is ear-clipped in array passes. Measured (the first version in
     brackets): a closed fence along 400 traced vertices, one hole, 1,201 ring vertices 45 ms
     (12.6 s); a ladder of 58 holes 43 ms (2.5 s). The bound went through three forms, and the
     first two are on record because each looked finished:
     1. *Two size limits for regions with holes* (fix round 2: 8,000 vertices, holes × vertices
        = 500,000). Judged AFTER the quadratic simplicity test, so refusing cost more than
        building (2,700 traced points: 2.59 s to say no); rings without holes had no limit (a
        comb of 5,004 vertices: 1.5 s per tick); and it was no bound on work at all (7,187
        vertices and 61 holes, inside both limits: 4.0 s). The example this ADR quoted for it —
        "400 holes in a mesh 0.31 s" — was itself beyond the second limit.
     2. *One work bound per region, counted* (`MAX_REGION_WORK`, first half of fix round 3):
        work units paid as the cut goes, the size judged first. Right for a region. But the
        snapshot applied it to the LARGEST outer ring of a stroke, after the clipper had
        inflated the path and every ring had been read — and the clipper's own work has no
        bound: 800 points scribbled across a plan took it half a second and came back as 53,000
        rings, 4,000 teeth standing side by side 1.6 s without one crossing, the last reading
        of a self-crossing outline of 800 vertices ten seconds (a security review of that
        commit found the pattern; the numbers are this round's).
     3. *One budget per ITEM, every step paid before it runs* (now). `polygon.WorkBudget`,
        `MAX_REGION_WORK` = 150,000,000 units: counting the pairs of a path
        (`touching_pairs`), the clipper (priced from the points, their stack — `stack_height` —
        and the pairs that cross or lie within a stroke's reach), reading what it returns
        (counted first), sorting it (holes × outer rings), every region's cut out of what the
        item has LEFT (`pay_for_region`), every union, band and comparison of a resolution.
        Before all of it, an item's stored vertex count: more than `MAX_ITEM_VERTICES` =
        16,384 is one comparison. What the budget does not cover is `RegionTooLargeError`
        inside and the skip code `outline_too_large` outside. Section 8.29.1 has the table of
        what fits and what a refusal costs; section 8.11 the two patterns.
        *Corrected in fix round 4:* the strict union was asked for a tree (`StrictlySimple`
        with `Execute2`), whose cost follows the rings it makes and the splits it tries, not
        anything this price list reads — a two-level zigzag of 340 vertices took it 3.6 s
        inside the budget. It is asked for a flat list now and `group_rings` sorts it (19 ms).
        And a level segment is no longer counted into a path's stack: the sweep walks along a
        level edge, so a straight fence costs the same in either direction (it fitted 1,416
        posts east–west and 6,645 north–south).
        *Corrected again in fix round 5:* the PLAIN union was still asked for a tree — and the
        tree flattened on the next line. ONE ring with 720 holes bridged to its wall, 4,324
        vertices, took it 5.3 s inside the budget (as a list: the whole item in 0.25 to
        0.31 s, the same answer for the same units). `_clip_tree` is split so that it cannot
        be written again: `_union_rings` (`Execute`) serves both unions, and `_band_tree`
        (`Execute2`) is called only by the two band readings that read a hierarchy. A band's
        tree is not priced by its rings and need not be — a band leaves nothing to join, and
        the call costs the same as a list and as a tree (801 rings 1.8 / 3.0 ms, 1,600 rings
        123 / 144 ms).
     The clipper cannot be counted, only priced, and a price is a measurement: each is the
     dearest case found (`scripts/measure_region_work.py` prints units charged against time for
     every family it knows — and, since fix round 5, FAILS when a row costs more than 12 times
     its price: a union as a tree stood at 14 to 76). A family nobody has drawn yet can be
     dearer than its price — the simplicity test was, by a factor of a hundred, for a ring
     whose every pair of edges lies close, until its near pairs were priced; and a second family
     was, until #451 re-priced it: a ring whose holes touch its outer ring stood at 3.6 to 8.1
     in the cut's bridge search (110 such holes: refused after 0.6 to 1.5 s). A block of bridge
     candidates now costs 600 units per edge, the dearest row of the table is 1.3 to 1.5, and 110
     such holes are refused in about 0.07 s - at the price of capacity (a slab of 49 touching
     holes now fits, 89 before; triangular 117, 146 before; square 88, 105 before; and an
     outlined region with many holes has a higher pre-cut floor: a crafted 25 x 25 line grid
     is now refused from its size, a 22 x 22 one still resolves). *Rejected:* a time-out (the verdict would depend on
     the machine and the moment, and Python cannot interrupt the clipper); a cap on vertices
     alone (it admits the scribble and refuses the long honest fence); a budget across the whole
     plan (a record would depend on what else is on the plan).
   - **What is remembered: what the plan asks for, and a bounded rest.** The verdict and the
     cut of a region, a ring's area, a record's ring facts and the regions of an outline are
     remembered by `polygon.ring_keyed`. A snapshot is one generation; an answer asked for by
     the snapshot being taken or the one before is live and never dropped; the STALE answers
     are bounded — 262,144 vertices per function, keys and answers together, the least recently
     asked dropped first — and a ring of more than `MAX_ITEM_VERTICES` is never hashed. Two
     forms came before. Each was an `lru_cache` of 2,048 to 8,192 ANSWERS: an outline of 4,000
     vertices dragged for a minute was a gigabyte (this ADR had it at "16 kB per entry": it had
     counted two floats per vertex; a tuple of two Python floats and its place in the ring are
     104 bytes). Then (fix round 3) a cap on ALL vertices held, least recently asked first —
     which bounded the memory and recomputed an unchanged plan on every tick once the plan was
     larger than the cap, because a snapshot asks in the same order each time (160 polygons of
     1,000 vertices: all 160 regions cut again per idle tick, 4.6 to 5.3 s). *Rejected now:* a
     larger cap (the cliff moves, it does not go); no cap (the gigabyte); a cap per item (an
     edit session of one item is the case to bound).
     Two things this leaves, stated since fix round 5. What a LIVE plan holds has no cap —
     linear in the plan, 130 bytes a vertex (400 accepted polygons of 3,000 vertices: 156 MB),
     112 bytes a point for a refused line, at most about 1.8 MB an item. And the generation
     is the process's clock: **one snapshotting scene per process is the supported case**
     (three scenes in turn recompute each other), and a plan that is gone stays held until
     two more snapshots have run. No redesign: `ui.view3d.snapshot.clear_outline_cache()` is
     the one public call that drops everything, live and stale; the workspace calls it on a
     document change and when the 3D view closes. *Rejected:* a generation per scene (a
     second mechanism, for a case the app does not have).
   - **The regions of a record stand in a stated order** (fix round 5): by the smallest vertex
     of the outer ring, put in that order before they are judged. The order had been whatever
     the clipper handed out, and it changed with a clipper mode — seven outlines of 13,740
     when the plain union became a list. A signature must not follow that. Over those 13,740:
     no verdict changed, 9,077 answers are identical, 4,663 are the same regions in the
     stated order. A region's holes keep the reading's order (the cut that was proven joins
     them in it).
   - **A ring that is convex by construction is judged without a cut** (fix round 4): a circle
     from 1e-3 cm by its radius, an ellipse or a rectangle by arithmetic on its corners
     (`is_convex_ring`), and only a ring that is not convex on the record grid by the cut — so
     no verdict changed. The predicate had been asked of every circle since fix round 3, which
     cut a 24-gon per new radius: scrubbing the date on `bench_large` went from 11.6 to 33 ms a
     snapshot; 12.7 now. The arithmetic had to learn one thing from the cut before it could
     stand in for it — a bed of 120 m by 2 µm turns left at every corner and fails the cut's
     proof on float noise — and a sweep of 120,000 shapes found no second.
   - **Where the cap is cut, and what that costs an outline under edit.** Because the predicate
     needs the triangulation, it is computed in the snapshot and cached; the builder reuses it.
     A ring that is being edited misses the cache on every tick, as before — only now in the
     snapshot rather than in the builder. With the ear clipper the two 3D views share that is
     272 ms for 1,000 vertices, so from `ARRAY_EAR_CLIP_FROM` = 256 vertices a ring without
     holes is cut by the array ear clipper as well: snapshot plus build of a traced outline
     with one vertex dragged takes 22 ms at 500 vertices and 41 ms at 1,000, where the first
     version took 51 ms and 250 ms. Below 256 the shared clipper stays (it is faster there, and
     the cap is the Qt 3D view's, triangle for triangle); above it the same polygon is cut into
     other triangles. A ring the array clipper cannot finish is NOT handed to the shared one
     (whose work is not counted): the region is not buildable.
   - The simplicity test is quadratic in the vertex count and misses its cache on
     every tick while a ring is being edited, so from 32 vertices on it prunes edge pairs by
     bounding box and runs on arrays (500 vertices: 72 ms in a plain loop, 2.9 ms now; 1,000:
     262 ms → 10.8 ms) — with a test that both versions agree.
   - **`verify_builder` looks at the solid from above — and bounds EXCESS only.** Beside
     determinism, purity, mesh validity and the height, it refuses a builder that covers more
     than `hole_cover_limit` (default one half) of a HOLE of the footprint (a hole sampled on a
     lattice of its own points; a hole narrower than `HOLE_MIN_WIDTH_CM` = 10 cm — one into which
     no circle of that diameter fits — is not judged: a 12 cm panel on a 10 cm stroke covers the
     2 cm sliver between two runs and is right. A hole of 10 cm and more is judged whole, as
     before), or puts more than 1 % of the footprint's area as top surface
     further than `plan_margin_cm` (default 50 cm, for eaves) outside it. Each bound is a
     keyword the caller tunes or switches off with `None`. Neither asks a mesh to *cover* its
     footprint: a flower, a grass tuft, the posts and pickets of a fence fill a fraction of
     theirs and are right — a lower bound would have rejected every honest sparse mesh. The
     height tolerance is a fraction of the height by default (1 % built, 3 % plants) or, with
     `height_tolerance_cm`, absolute centimetres (L1.6's gate is ±0.5 cm).
   - **A registry may change after the first apply.** `SceneSync` remembers which builder built
     each item; the next `apply` rebuilds the items whose builder is no longer that one. Freezing
     the registry was the alternative; it would have made the order in which builder packages
     register a correctness condition. The comparison is IDENTITY, and that is a contract on the
     registry: `builder_for(kind)` returns the same object for the same kind until a `register`
     changes it, and every `register` moves `BuilderRegistry.version`. `SceneSync` looks for
     items to rebuild only when the version moved — so a registry that hands out a fresh
     callable per call no longer rebuilds every item on every idle apply (measured before), and
     an idle apply asks the registry nothing.
10. **`SceneSync` keeps the sink in step** (`sync.py`). All builders run **before** the sink is
    touched; then one `begin`/`commit` — or no call at all. Invariant: after any sequence of
    applies the sink holds exactly what one apply of the latest snapshot puts into an empty sink
    (`SceneSync.expected_state()` is that reference — built with the registry as it is at the
    moment of asking, so between a registration and the next `apply` it is ahead of the sink).
    - *One transaction per tick.* `apply(records, sun=…, ground=…)` sends the records, the ground
      and the sun in the same `begin`/`commit`: a sim-clock tick that moves the sun and grows the
      plants never shows a frame with the new sun over the old plants. `set_sun` / `set_ground`
      remain for a change of the sun or ground alone.
    - *A builder that raises is contained*: the item gets no parts, the failure is logged and
      listed in `failures`, the rest of the scene is applied, and the builder is not run again
      until that item's geometry (or its builder) changes.
    - *A sink that raises poisons the sync*: the engine's state is unknown — and its transaction
      is still open — so every later call raises `SyncStateError` until `reset()`.
    - *`reset()` is the recovery, and it goes through the protocol*: it calls `sink.clear()` and
      forgets the records, the failures, the poison flag and the sun and ground it deduplicates
      against, so the next `apply` re-adds every item and re-sends sun and ground. If `clear()`
      itself raises, the sync stays poisoned. What the sync cannot see is a sink that *ignores*
      `clear()` — it returns nothing; a test catches that by comparing the sink's own account of
      itself with `expected_state()`.
    - *When `reset()` is needed*: after a sink failure, and when the engine's scene was destroyed
      behind the sync's back (the 3D view was torn down and rebuilt around the same sink, the
      graphics device was lost). **Not for a new or newly opened plan**: a plain `apply` of the new
      snapshot removes what is gone and adds what is new, in one transaction. A new sink gets a
      new `SceneSync`.
11. **One footprint extraction.** `ui/canvas/footprints.py` is the public home of
    `item_footprints` and `plant_canopy_radius_cm`, and of `item_outline` — the same vertex
    enumeration in item coordinates, from which both the scene-space footprints (2D shadows,
    heatmap, Qt 3D) and the item-local records are made. Closes TD-036.
12. **The snapshot never lets one item blank the view** (`ui/view3d/snapshot.py`).
    `snapshot_records` returns the plain `dict` it always did; what it had to leave out is
    reported through an optional keyword-only out-parameter, `skipped=` — a list the caller
    passes and the snapshot appends `SkippedItem`s to. An item whose record cannot be built
    (malformed metadata, geometry that is not finite: any exception is contained to that item) is
    left out, appended, and logged once per item and kind of failure (the exception's type) — not
    once per edit. A `SkippedItem` is plain data a caller may keep: the item's id and kind, a
    `SkipReason` CODE (`record_failed`, `duplicate_id`, `outline_unbuildable`,
    `outline_too_large`, `out_of_range` —
    a UI maps a code to a translated text; the value is never shown as it is), and the exception's type name and
    message as strings. It never holds the exception: a traceback keeps its frames alive, and
    they hold the scene and the item. The exception goes to the log, and the log is bounded in
    volume as well as memory — after 2,048 different failures one line says that further ones
    are not logged, and none are. A second item carrying an id already taken is skipped
    the same way, with a warning; the lower one wins. Items left out by design (invisible,
    without an object type, covering no ground, a roof ridge) are not reported. (An
    out-parameter rather than a richer return type: a dict subclass carrying the report was
    written first, and loses it in the first `dict(...)` or comprehension a later step applies —
    the very silence the report exists to prevent.)
13. **The truth principle: a beautiful wrong frame is a P0.** The contract is the gate table of
    `ogp-lush-cinematic` §1, and from this story on each gate that does not need pixels is a test
    a builder cannot pass by looking good:

    | Gate | Where it is enforced now |
    |---|---|
    | Height: mesh top = resolved height | `verify_builder` (±1 % built, ±3 % plants, or absolute cm); default prism exact |
    | Faces: the sun lights the face that faces it | `Mesh.validate` winding rule |
    | Footprint / spread: the 2D footprint | golden fixture + `transform ∘ local == item_footprints` over every ring: ≤ 1e-6 cm vertex for vertex — except a polyline's stroke polygon, which matches to pyclipper's grid (≤ 3e-3 cm; its centre line to 1e-6) |
    | Ground covered: the solid stands where the plan has something | `verify_builder` plan view (holes, overreach); default prism's cap area = footprint area |
    | North / nothing mirrored | `frame.SCENE_TO_ENGINE` has determinant +1; one mapping |
    | Sun: only `core/solar` | `SunState` carries angles, nothing art-directed |
    | Date: the plan's sim date | `snapshot_records(scene, at_date)` feeds the 2D resolvers |

    A builder reads plan data only through the record, so it has no way to tune a domain number.
    The pixel gates (shadow IoU, sky azimuth, orientation) arrive with the engine in L1.2/L1.4.

## Alternatives considered (rejected)

- **Scene-space meshes at absolute positions** (the legacy collector and the spike). Every move
  rebuilds a mesh, and float32 vertices lose precision far from the origin.
- **Qt's item coordinates verbatim, no centring.** The same shape would give different records
  depending on its history (after an undo that re-bases, a save and reload, a centred resize),
  vertices would sit at plan-scale coordinates in float32, and a Model's pivot would be nowhere
  near its item.
- **Signatures as the only equality.** Refuted by the measured hash collision (decision 4).
- **No quantisation.** Refuted by the ridge measurement (decision 5).
- **A second, coarser grid for a HOUSE's ridge.** Built first, then measured as unnecessary: the
  ridge dust stays three orders below the one grid. Removed.
- **Carrying a circle's rotation, or the 2D stroke polygon of a polyline.** Both make the record
  disagree with one of two truths. The 2D code inflates a polyline's centre line in *scene* space
  on pyclipper's 1/1000 cm integer grid, so that polygon is not translation-equivariant: a record
  derived from it would change on every move. The record inflates the centre line in the local
  frame instead; the two polygons differ by that grid (measured 1.6e-3 cm), while the centre line
  itself — what fences and walls are built from — agrees to 1e-7.
- **Telling outer rings and holes apart by orientation alone, inside `footprints`.** It is what
  pyclipper returns, and it is how the defect below happened: nothing in the type said that the
  second ring of a closed fence is not a solid. A separate field makes the wrong reading a
  deliberate act; `footprints` kept its name and type so that code written against the first
  contract still reads the outer rings.
- **Letting the snapshot raise.** One plant with `plant_species = {"scientific_name": None}` took
  the 3D view of the whole plan with it. And **swallowing it silently**: the user would see a
  plan with a hole in it and no one would know why — hence the `skipped=` report plus one log
  line.
- **Aborting the whole apply when a builder fails.** One broken archetype would freeze the 3D
  view for the whole plan. Containment keeps the plan visible; running builders before the sink
  keeps the transaction whole either way.
- **A module-level registry filled at import time.** Import-order coupling between builder
  packages; an instance handed to each package's `register(registry)` has none.
- **Validating every mesh in production.** Linear in vertices on every build; it is an opt-in of
  `SceneSync` and the default of `verify_builder`.
- **A polar decomposition for non-rigid transforms.** It would keep rotation in the transform for
  a scaled item — a case the app does not produce.
- **A `QObject` sink or signals in `core/`.** Qt in the layer ADR-048 keeps Qt-free.

## Consequences

- New: `core/scene3d/{record,scene_diff,frame,mesh,polygon,sink,build,sync,color}.py`,
  `ui/canvas/footprints.py`, `snapshot_records` in `ui/view3d/snapshot.py`. Moved:
  `core/scene3d.py` → `core/scene3d/legacy.py` (minus the two shared functions, decision 1).
  `sun_shadow_controller` keeps two underscore aliases for the two frozen test suites that import
  them, until L1.10. The module that holds `diff` is `scene_diff`, so that
  `open_garden_planner.core.scene3d.diff` is one thing — the function.
- **The 2D shadow has the defect the 3D pipeline had, and this story does not touch it.**
  `item_footprints` hands a closed fence's two rings to `compute_scene_shadows` as two solids, so
  a 10 m × 8 m fence 1.2 m high shades 88.8 m² at a 60° sun where its stroke shades 17.5 m². The
  golden footprint fixture pins `item_footprints` byte for byte, so the fix is a follow-up of its
  own (PF-L3D-02 has the reproduction). Until it lands, 2D and 3D disagree ON PURPOSE for a closed
  stroke and for a polygon that crosses itself: the 3D record is the stroke, or the resolved
  regions; the 2D footprint is every ring as a solid, or the ring as drawn. That follow-up should
  also move "resolve an outline" and "sort rings into regions" into one `core` function both
  views call — today `ui/view3d/snapshot.py` is a second place that knows the clipper's scale.
- No `.ogp` change, no `FILE_VERSION` bump, no user-visible string, no new dependency, no app
  wiring (L1.3) and nothing rendered.
- `SceneDiff` has a sixth field, `reordered`, beyond the five the issue names.
- **A resize that keeps a corner fixed is geometry *and* transform** (the frame hangs on the
  centre); a centred resize, a height change, a vertex edit inside the bounding box and a plant
  growing with the date are geometry alone.
- **A measured plant's drawn circle is not its footprint** — its canopy is, as in the 2D shadow —
  so resizing that circle changes nothing in 3D.
- A circle item's own rotation is not in the record. If round furniture ever needs a facing (L4),
  it becomes a param.
- ADR-048 (entries 5 and 6) expected L1.1 to measure the full edit-to-frame path (≤ 50 ms p95).
  That needs an engine and moves to L1.2/L1.3. What L1.1 measures is its own share: a snapshot
  takes 2.2 ms (98 records) / 9.6 ms (424 records) median against budgets of
  15 / 60 ms, a diff 0.08 / 0.37 ms; a third of the snapshot is the shared height and
  canopy resolvers.
- **Open for later stories**: L1.2 implements `EngineSink` — all ten methods, `clear()` included —
  and proves `engine_pose` against the engine (one geometry per Model lifetime); L1.3 owns the
  debounced tick, sends sun and records in one `apply`, passes a `skipped=` list to the snapshot
  and shows it and `SceneSync.failures` somewhere a user can find them, and calls `reset()` only after a sink
  failure or a rebuilt engine scene — not on project load; L1.4 extends `SunState` with the look;
  L1.5 extends `GroundSpec`, consumes `reordered` and paints `Record.regions`, not `footprints`;
  L1.6 fills `transform.base_cm` from `parent_id` and registers built-world builders; L1.7
  registers plant builders and adds a resolved "in season" param (it needs the plan's location,
  which a record does not carry).

## Validation

- **`tests/unit/test_scene3d_contract.py`, `test_scene3d_frame.py`, `test_scene3d_mesh.py`,
  `test_scene3d_polygon.py`, `test_scene3d_sync.py`** (Qt-free): the field groups of `Record`
  (every field in exactly one), ring orientation, the hash collision in every value-bearing
  field, all eight diff combinations, determinant +1 and winding, the legacy scalar mapping, one
  failing mesh per defect class, triangulation with holes, the plan-view check, the sink
  protocol, builder containment, sink poisoning, **recovery through the protocol only** (a sink
  that fails on `add` / `update_transform` / `set_sun` / `commit`, then `reset()` and one apply,
  compared with a from-scratch apply), a sink that ignores `clear()`, a registry that changes
  late, and incremental == full rebuild over random edit sequences.
- **`tests/integration/test_footprints_golden.py`**: 120 footprint cases with exact float reprs,
  generated before the move, byte-identical after it.
- **`tests/integration/test_scene3d_snapshot.py`**: the diff matrix over every footprint shape
  through the app's own commands; `transform ∘ local == item_footprints` for every shape ×
  rotation × position × pivot; the non-rigid rule; 1,000 moves of a ridged HOUSE; every bench-plan
  record through `verify_builder`; 100 identical snapshots on both bench plans; a closed fence, a
  nearly closed one and an open U (cap area = stroke area; walls face away from the solid; the
  first default builder, reconstructed, is refused); a bow-tie house; one malformed item per
  record field group; two items with one id; a house turned with its ridge; the four outlines of
  the re-review, each with a ridge item; 7,500 random self-crossing outlines on three grids
  (0 without regions, 0 the default builder cannot build, every mesh valid in float32, the ground
  covered equal to the outline's winding-number raster); 4,500 random strokes the same way; two
  outlines pyclipper itself misreads; a vertex placed twice; a height of 1e300, one just over
  the bound and an infinite one, each through snapshot → `SceneSync` → an unvalidated sink.
- **`tests/integration/test_scene3d_edge_plan.py`** over the third committed plan,
  `tests/fixtures/plans/scene3d_edge_cases.ogp` (`scripts/make_scene3d_edge_plan.py`): the same
  gates — 100 identical snapshots, every mesh valid with its cap area equal to the footprint's,
  `transform ∘ local == item_footprints` over every ring — on the shapes the bench plans lack:
  16 items, among them a closed fence, a ladder drawn as one stroke (four holes), a fence whose
  ends stop 2 cm apart at a corner (closes) and one whose ends stop 6 cm apart (does not), and
  a house whose outline crosses itself around a pocket.
- **`tests/integration/test_scene3d_pipeline.py`** (§8.10): draw with the real tools, then move,
  rotate, recolour, resize, select, delete, undo, redo — the exact sink calls and incremental ==
  full rebuild after every step; the same on a real `GardenPlannerApp` with the sim clock; and
  the diff matrix again as a table of 70 edit × shape cases through `SceneSync` and
  `RecordingSink`, each with its exact sink calls and builder invocations.
- **`tests/perf/test_scene3d_snapshot_budget.py`**: the snapshot budget.
- **`scripts/mutation_check_scene3d.py`** — 180 single-rule breaks (mirrored frame, flipped
  rotation, no grid, no value compare, colour baked into the mesh, a prism 1 % too tall, holes
  ignored, `reset()` that clears no sink, a bad item that raises, a ridge with a record, a
  resolved house that keeps its ridge, a reading of pyclipper's taken on trust, a hole given to
  the island inside it, a height of 1e300 taken for a height …), each run against the tests that must notice. Not part of the suite
  (it rewrites source files); run by hand after changing the pipeline or its tests. Every mutant
  is killed — and "killed" means pytest ran the tests and one failed (exit code 1), not that it
  exited with anything but zero. What CAN rot between two runs is in the suite
  (`tests/unit/test_scene3d_mutation_script.py`): every pattern still matches its file exactly
  once, and every test a mutant names exists.

## What the first version got wrong (independent review, same day)

Recorded because each of these passed every gate the story had set itself:

- **A closed fence became a slab.** `footprints` carried the hole ring of a closed stroke, and
  the default builder extruded it: 3.6 m² of fence turned into a solid over 81.8 m² of garden with
  an inside-out inner wall. G4 compared ring by ring (both rings were "right"), G7 validated the
  mesh (it was a valid mesh) and `verify_builder` checked the height (it was the right height).
  No gate asked **how much ground the solid covers** — and neither bench plan contains a stroke
  that closes on itself. The fix is decision 3 and the plan-view check of decision 9; the lesson
  is the fourth row of the gate table and the third committed plan.
- **Recovery could not be said through the protocol.** `reset()` forgot the sync's records but
  touched no sink, so after a mid-transaction failure the next `begin()` raised "a transaction is
  already open". The tests passed because they called the recording double's own `reset()` first —
  a method no real engine has. The fix is `clear()`; the lesson is that a recovery test may only
  use what the protocol offers.
- **(Re-review, one round later.) "Simple rings a builder can always triangulate" was a
  promise, not a fact.** The snapshot handed pyclipper's output on unchecked, and four HOUSE
  outlines measured through `snapshot_records` showed what that is worth: one became a single
  ring of ten vertices that passed for an ordinary house, with a ridge that belonged to another
  shape; one an outer ring with a pocket the default builder could not cut; one a ring that
  touched itself; one got no record at all — its hole started on the outer ring, and `group_rings`
  asked a point test, documented as undefined on a boundary, who owned it. Every failure was
  honest (reported, or a build failure) and every one contradicted a sentence other stories were
  coding against. The fix is the predicate of decision 3; the lesson is that *a statement about
  what a consumer may rely on is a gate to write, not a sentence to write* — and that "0 of N
  random inputs" is a number a test can hold (N = 7,500 here).
- **(Re-review.) And the tool the fix leaned on was itself wrong, twice.** Taking the ring
  hierarchy from pyclipper's `PolyTree` — the ruling's own remedy — produced a solid piece handed
  out as a hole, and the plain union produced an area 10 % short, both on outlines that retrace
  an edge. Found only because the first attempt compared the result with an independent raster
  of the drawn outline's winding number instead of with another call into the same library.
  *When a library's answer is the thing in doubt, the check must not ask the library.*
- **(Re-review.) A test written for this round found a defect of the first one.** The ladder the
  reviewer drew to show a cost cliff also has vertices of five rings on one line; the cap had
  thirteen triangles of zero area, wound downwards in float32, and `Mesh.validate` refused the
  fence. No earlier test had a diagonal stroke crossed by others. (Decision 9.)
- **(Fix round 3.) "No real stroke takes this path" was a count, not a proof.** The fallback
  that resolves a stroke whose rings touch was reported as unreachable: 0 of 4,500 random
  strokes took it. A fence drawn back to a point one stroke width beside its start has two
  butt ends that meet corner to corner; pyclipper returns ONE ring that touches itself, and
  every such fence takes the fallback (18 of 18 here, 15 of 15 the reviewer drew). With the
  fallback replaced by "no regions", 694 tests and all 93 mutants of that round still passed.
  It is pinned now through real items and in `scene3d_edge_cases.ogp` ("Fence that meets
  itself": one ring of 20 vertices, 0.002 cm inside the drawn stroke, no flag — a stroke's
  rings never were the drawn vertices, and what builds a fence reads `path`). *Random input
  does not find a shape that needs two exact coincidences; ask what would make the branch
  run, and draw that.*
- **(Fix round 3.) A bound was added three times before it bounded.** See decision 9: a limit
  judged after the work it was to prevent; a work bound on the largest element of a sum; and
  then a budget — and inside the budget one quadratic priced by its size where its cost was
  the pairs it had to look at. Each form passed its tests, because each test asked "is the
  large thing refused?" and none asked "what ran before it was?". The tests that hold now
  assert what was called, to the unit of the budget, and read no clock.
- **(Fix round 3.) A mutant that breaks the collection is not a kill.** One mutant made the
  test file fail while pytest collected it (the file sorts a ladder's rings in a
  `parametrize` list): exit code 2, which the script reports as BROKEN — it was built to, since
  round 2. Two further mutants of the first half of the round survived a run nobody had waited
  for (the cut's own size check, shadowed by its caller's; the size check of
  `triangulate_region`, shadowed by the budget running out twenty bridges later). All three
  have a test now. *Run the mutation script before the report, not after it.*
- **(Fix round 5.) The same defect, one call away.** Round 4 took the tree from the strict
  union and left it on the plain one — eight lines above, in the same function, with a test
  that pinned `("tree", False)` as EXPECTED. The fix was made for the call the review named,
  not for the rule the review found. Now the rule is in the code's shape (one function makes
  unions and cannot return a tree; one makes the band's tree), a test watches
  `pyclipper.Pyclipper` itself below every seam, and the measuring script fails instead of
  printing. *When a review finds a defect, fix the rule and then search for every other place
  the same thing is done — the next one is usually within sight.*
- **(Fix round 4.) The bound of round 3 had two holes, and the suite was green over both.**
  A memory that drops the least recently asked answer recomputes the whole plan every tick
  once the plan outgrows it; every test of round 3 used a plan far below the cap. And one call
  of the clipper was priced by what came back while its cost followed how it was asked
  (`StrictlySimple` as a tree). Both were found by a reviewer who built the input the
  mechanism's own comment described as its limit. Now pinned by counting what an UNCHANGED
  plan does on its second and third tick with the cap shrunk under it (zero cuts, zero
  inflations), and by a clipper stand-in that records whether a strict union was ever asked
  for a tree. *For a cache, test at the size where it is full; for a priced call, measure the
  call, not its answer.*
- **One malformed plant blanked the plan**, a roof ridge had a record that broke "rotate →
  transform only", a late builder registration left stale geometry, and a clock tick took two
  transactions. Decisions 3, 9, 10 and 12.

## Addendum (L1.7, 2026-10-11): plant art v0 — one recipe table for 2D and 3D

**Context.** What a plant looks like on the plan is a *recipe*: an archetype (`canopy`, `mound`,
`rosette` … thirteen of them), a palette and a few numbers per species. The recipes lived in a
script (`scripts/generate_plant_sprites.py`), the rule that picks a plant's sprite lived privately
in `core/plant_renderer` (a Qt module), and the L0 spike had copied the palettes and kept a
species table of its own, keyed by common name. A 3D plant built from a second table can disagree
with the sprite on the plan about its shape or its green, and no test would notice.

**Decision.**

1. **The tables have one home: `core/plant_art/recipes.py`** (standard library only). `PALETTES`,
   `FRUITS`, `FLOWERS`, `SPECIES` and `CATEGORIES` were sliced out of the script by line, not
   retyped; the script executes that file by its path and keeps the drawing code — by path, so
   that it still needs nothing but the standard library (importing the package by name runs
   `core/__init__.py` and with it PyQt6) and cannot be led to another checkout by an editable
   install. Its output is byte-identical to the committed blobs over all 123 SVGs (5,833,889
   bytes) before and after. The one palette that was a literal
   in the drawing code, the hedge's, became data too (`HEDGE_PALETTE`).
2. **The resolution is one function: `core/plant_art/resolve.py::resolve_sprite(kind, species,
   category, available=…)`** — the 2D rule extracted, with the sprite maps it reads.
   `plant_renderer._resolve_svg_path` calls it and asks "does the SVG exist?"; the 3D
   builder calls it and asks "do the tables hold a recipe?" (the two sets are the same 123 names,
   pinned). It is held to a golden of 1,562 answers — **regenerated from the rule when the rule
   changed** (#446, below) — and, with sprite files missing, to a statement-for-statement copy of
   the rule in the golden's generator (`scripts/make_sprite_resolution_golden.py`), which also
   keeps the rule it replaced as `legacy_resolve` for the before/after. A species the canvas
   draws with a category sprite gets the category's recipe in 3D.
   **Both callers hand it the same inputs** (orchestrator ruling R14): the item's type, its plant
   category and the item's OWN species string exactly as it is. The record carries that string
   for this purpose as `params["sprite_species"]` (`PARAM_SPRITE_SPECIES`: `item.plant_species`,
   not stripped; absent when empty). `species_name` and `species_key` stay in the record and
   describe the species DATA. **A species assigned from the plant database writes the item's
   string** (#445, below), so the assigned species is the one both views draw and build.
3. **One builder for the plant kinds, one silhouette per archetype**
   (`core/scene3d/builders/plants.py`, registered for `plant_art.PLANT_KINDS` — the table
   `plant_renderer.is_plant_type` answers from). Every archetype of the tables has a builder; a
   recipe with an unknown one raises, so a new 2D archetype fails a test instead of borrowing
   another one's shape. v0 is a few soft volumes and a shell of large geometric leaves: at most
   2,000 triangles a plant, bounded per archetype and by construction — counts are clipped
   functions of recipe numbers, never of the plant's size.
4. **Builders build to the data; the fit normalises the last millimetre and reports it.** A
   builder works at the plant's real height and radius and keeps to them: every archetype places
   its highest point AT the height; shell leaves are set by the lobe's own surface normal and stay
   inside the plant's cylinder by turning (lying down without headroom, quarter turns at the
   canopy circle), never longer than 0.6 canopy radii; bow, ripple and fold of a folded leaf are
   held to the height; a volume on the ground has no flat sole. `_fit` then pulls back what still
   strays beyond the canopy circle, centres the foliage on it (a trunk's foot stays on the plan
   position), presses what dips below the ground onto it, scales so the top is `height_cm` and
   the widest span the canopy diameter — exact to float32 — and, LAST, puts whatever FOLIAGE is
   still further than 1.09 canopy radii from the axis onto that circle (`REACH_MAX`, `_rein_in`:
   a vertex keeps its larger coordinate, so the widest span stays exact). Each earlier step
   undoes a little of the one before, so none of them says where a vertex ends; the last one
   does, for any builder output — for the foliage the story's gate (nothing more than 10 %
   outside the canopy circle) holds by construction, not by a sample. Wood is not moved (a
   flat-shaded face would keep a normal that is no longer its own); for the plant the gate rests
   on an invariant of the trunk builders — foliage is the outermost part: a trunk is built within
   0.32 canopy radii of the axis — which the tests hold for every recipe at every proportion
   step. It RETURNS what all of that took (`FitReport`;
   `fit_report()` for a built plant), including where the plant ends and whether the last step
   moved anything (3 plants in 63,099). The bounding box is the gate the issue names;
   the report and the foliage's area-weighted height quantiles are what make it mean something,
   because the box is exact for anything the fit is given. For the plan view to be honest as
   well, the elements that draw a plant's outline are regular (`_RIM_REACH`, `_RIM_JITTER`): with
   outlines of any reach at any angle a fitted plant left its canopy circle by up to 39 %. A
   plant is never *lifted* to put its lowest vertex at zero — that made a cushion float on one
   hanging leaf (PF-L3D-01).
5. **Foliage colours come from the recipe's palette alone, and their balance from the sprite.** A
   vertex is an sRGB mix of the palette's base anchors and tip anchors, in linear light times a
   hue-neutral depth shade. The mean tip weight of a plant is a constant per archetype, measured
   from the rendered sprites — a palette spans up to 41° of hue between its anchors, and where a
   sprite's foliage sits in that span is decided by its drawing code. Wood has no colour in the
   plant tables (a top-down sprite shows no trunk): v0 takes the mean colour of the 2D BARK fill
   texture in linear light, `#5d432d`, pinned against the PNG.
6. **v0 makes no seasonal claim.** No fruit, flowers, pods, umbels or bulbs (`FEATURE_KEYS`), no
   curd on the `head` archetype and no flower head on the `flower` archetype: the season gates
   need the plan's frost dates, which a record does not carry. A recipe stripped of those keys
   builds the identical mesh (pinned). "In season" is therefore **not** added to the record by
   this story; it arrives with Package L3.
7. **A plant without a height gets a placeholder, never a guess.** `height_cm is None` — no
   species data, no measurement, no typed height — builds one part: a smooth spherical cap over
   the canopy circle (48 sides: the rim covers 99.7 % of it), `min(0.12 × diameter, 25 cm)` high,
   in the 2D white × 0.5 in linear light (sRGB 170 / 167 / 158), material `vc`,
   `casts_shadow=False`, the same for every item.
8. **Seed.** `core.scene3d.item_seed(record.params["seed"], "plant")`, the function L1.1 ported;
   no second one. `core/plant_art` does not re-export it — that would make the package import
   numpy. Builders draw uniform numbers only (`Generator.random`), from a generator named by its
   bit generator — `Generator(PCG64(seed))`, not `default_rng(seed)`, whose bit generator numpy
   may change: every plant of every plan would change its shape. A plant's dice depend on its id
   alone, never on its proportions: a count that follows the proportion (a conifer's three to
   six whorls) rolls the dice of all it could have, so a plant that grows a step changes
   proportion, not form.
9. **A shape is built once and scaled.** `build_silhouette` builds a shape per (recipe form,
   seed, proportion step) and remembers it; the plan's exact height and radius are a scale of the
   remembered shape. The proportion (height over canopy radius) is rounded to a whole power of
   1.05 for the BUILD only, so the size is never misstated (the scale is exact) and the form is
   stretched by at most 2.5 % in one axis. The cache is bounded in BYTES (`SHAPE_CACHE_BYTES`,
   256 MB — about 3,500 average plants), not in a count, so it follows the plan; at the cap a new
   shape gets room only from shapes nobody asked for since it was last asked for, so a scrub over
   more plants than fit rebuilds the overflow and not everything (a least-recently-used cache of
   1,024 shapes rebuilt all 1,025 growing plants on every tick). The price, at the cap only: a
   shape that was dropped comes back in two builds — going back to a dropped plan costs two cold
   ticks, a backward scrub at the cap twice the forward one — which `clear_shape_cache()` on
   plan close avoids; the request log behind the rule (65,536 keys, 15–21 MB) is outside the
   cap. GUI thread only; untested under threads. It holds arrays on immutable
   memory, and its key is the very object a builder is handed as its recipe — a builder cannot
   read a recipe key the key lacks. The builder stays a pure
   function of its record. A daily date scrub of 320 plants is then 15 ms where it was 342 ms
   (busy machine); a first build is as slow as before and is L1.3's to schedule.

**Alternatives rejected.**

- **Copying the tables into the 3D code** (what the spike did). Two tables drift; the spike's copy
  is now drift-guarded against the shared one until it retires in L1.10.
- **A better resolver for 3D** — keyed on `species_key`, without the partial match. It would be a
  second rule: "Lemon Balm" takes the lemon tree's sprite in 2D (`"lemon" in "lemon balm"`),
  "Melon" the eggplant's, and a 3D view that knew better would show a different plant than the
  plan. Fixing the 2D rule changes sprites users see and is its own issue.
  *(Superseded by #446 — see "the species name is a whole name, and the assignment writes it" below:
  the rule was fixed in ONE place, and it is the same rule the 3D builder asks.)*
- **Scaling the farthest vertex onto the canopy circle** instead of fitting the bounding box. The
  box then spans as little as 72 % of the canopy diameter (measured, feathery), outside the ± 10 %
  spread gate. Bounding-box fit plus regular outlines keeps both — and the fit's last step
  makes the second one a fact: box exact, no foliage vertex beyond 1.09 canopy radii, by
  construction (and no wood either, by the trunk builders' radii — decision 4).
  (For one round that bound was a measurement, "at most 9.2 % over 117,000 builds", stated as a
  limit; one id in 300,000 read 10.06 %.)
- **Pulling a stray vertex straight toward the axis** as that last step. It shortens the
  bounding box when the vertex is the box's extreme — the spread would be exact only when
  nothing was moved. Keeping the larger coordinate keeps the widest span whatever is moved.
- **Stating where the foliage's mass is as a requirement.** It is a property of thirteen forms at
  171 proportions; enforcing a floor per archetype would mean designing the forms to the floor.
  It is stated as what it is — measured, with its sample — and held by a tripwire.
- **Resolving the 3D recipe from the species data** (`species_name`, as the first version did,
  or `species_key`). The data's name is not the string the plan draws from: a gallery "pumpkin"
  carries the bundled record "Winter Squash" and was built as a squash; a species assigned from
  the plant database changes the data and not the string. One rule on two inputs is two rules.
- **Squashing an over-tall plant into its height** (what the first fit did). Exact bounding box,
  wrong plant: its body ends where the squash factor puts it. See "what the first version got
  wrong".
- **Rebuilding a plant on every date tick.** 218 ms per daily tick for `bench_large` on a busy
  machine (the reviewer's measurement), every tick, on the GUI thread. A proportionally grown
  plant is the same shape scaled; decision 9.
- **A build budget in milliseconds on a shared machine.** The same build is 3.5 times slower
  with every core busy, in CPU time as much as in wall time. The budgets are stated in units of
  a reference workload timed alongside, and the counts that cause the time are asserted —
  exactly for a first build and a cold tick, as a bound (10 % of the plants that changed;
  measured 1.1–1.6 %) for a warm one.
- **A least-recently-used cache of N shapes.** It has a cliff at N + 1 growing plants (decision
  9), and N is a guess about plans. A cap in bytes with an admission rule has neither.
- **Checking the foliage hue against the palette's entries.** The palette is what the builder
  mixes from — the check would test the mixing against itself. The reference is the sprite as
  QSvgRenderer draws it: the shipped SVG minus the same sprite with a black palette is exactly
  the ink that depends on the palette (source-over compositing is linear per layer), so fruit,
  flowers and shadows cancel without a hand-made mask.
- **A box for the hedge section.** The record is a circle, and a circle has no heading; a box's
  orientation would be invented. It is a hand-clipped drum.
- **Building the curd and the sunflower's head.** They are flower heads; see decision 6.
- **A leaf-green or item-tinted placeholder.** It reads as a low plant. The neutral tone has a
  third of the saturation of the palest real foliage (0.07 against 0.21). The 2D white × 0.7 —
  the spike's rule for a sun-lit white, made for an upright trunk — rendered a dome that faces
  the noon sun at luma 232 through the spike's engine: unclipped, and the brightest thing in the
  garden. × 0.5 is a judgement, not a measurement of the production rig; the look pass decides.
- **Species-specific crowns and bark** (the spike's `CANOPY_FORM`, the white birch). Not in the 2D
  tables; Package L3.

**Consequences.**

- New: `core/plant_art/{__init__,recipes,resolve}.py`, `core/scene3d/builders/plants.py` (and a
  one-line `builders/__init__.py`; L1.6 owns the real one and its registry factory calls
  `plants.register`). Changed: the sprite generator (loads the tables by path, two palette
  defaults), `core/plant_renderer` (derives its three maps, calls `resolve_sprite`),
  `core/scene3d/record.py` (`PARAM_SPRITE_SPECIES`) and `ui/view3d/snapshot.py` (writes it). New
  scripts: `make_sprite_resolution_golden.py`, `measure_plant_art_3d.py`,
  `mutation_check_plant_art.py`. No `.ogp` change, no `FILE_VERSION` bump, no user-visible
  string, no new dependency, nothing wired into the app.
- **3D builds what 2D draws — including what 2D draws oddly.** A plant given a species from
  the plant database (`ApplySpeciesCommand` writes the data and leaves the item's string) keeps
  its old sprite on the plan, and so its old shape in 3D, at the new species' size. That was
  recorded as a known gap between the views in the first version (3D built the new species); it
  is now one behaviour, and a 2D question: should the sprite follow an assigned species?
  Follow-up issue material, with the partial-match quirks below — not a 3D matter.
  *(Superseded by #445 — see "the species name is a whole name, and the assignment writes it" below:
  the assignment now writes the item's string, so the sprite DOES follow the assigned species, in
  both views.)*
- **One 2D input is NOT followed: the item's fill colour.** The canvas lays it over a plant's
  sprite at 60 / 255 opacity; 3D foliage is the recipe's palette alone, so a recoloured plant
  differs in hue between the views and a recolour changes nothing in 3D. The hue gate's
  reference is the untinted sprite. An owner question for the look pass (§8.29.7).
- **The resolver's quirks are visible in 3D.** Lemon Balm (90 × 60 cm) is built as a `canopy` —
  a trunk and a crown 90 cm tall — because that is the sprite the plan shows; "Melon" takes the
  eggplant's recipe, "Bean (Bush)" a climber's, a string of blanks the rose's. Twelve of the 118
  bundled species have no sprite of their own and take their item type's category.
  *(Superseded by #446 — the melon and a string of blanks no longer take those sprites; "Lemon Balm"
  and "Bean (Bush)" still do, and that residue is pinned in the unit test.)*
- **Many plants are placeholders until someone says how tall they are.** A category plant from
  the gallery ("Round Deciduous", "Palm" …) has no species data and so no height: the 2D shadow
  model casts none for it either. A typed height, a measured one or a species turns the marker
  into the plant. The same holds for a plant whose species string names one of the twelve
  SPRITES the bundled database has no species for (squash, turnip, arugula, chard, okra,
  tarragon, lemongrass, marjoram, bay laurel, stevia, sorrel, lovage): its own sprite on the
  plan, a grey disc in 3D. The gallery offers none of them (all 86 gallery species have a record
  and a height); they come from plant lists, older plans, an agent or a typed species.
- **A sprite's tuning numbers move its 3D plant.** `leaf_scale` and `n_out` were tuned for the 2D
  drawing and are read by the 3D builders (within clipped ranges). `core/object_height` and
  `agent_api/creates.py` keep their own lists of the plant kinds; both are drift-guarded.
- One bark for every species (a birch is brown); a climber stands without its support; a
  `hedge_section` is a drum; sweet corn is a fountain of blades (its 2D archetype is `allium`).
- **Open for later stories**: L1.2 shows the parts (`foliage`, `vc`); L1.4's wind reads
  `uv.x` (0 at the ground, 1 at the top) and `uv.y` (phase); L1.6 stands plants on their bed and
  replaces `builders/__init__.py`; the combined look-dev pass renders the Beauty Board and the
  3D reviewer judges it — nothing here was approved by its author.

**Evidence.**

- **`tests/unit/test_plant_art.py`**: the package imports the standard library only; the
  generator executes the package's `recipes.py` and runs with PyQt6 and numpy blocked; the
  renderer holds the package's maps; `resolve_sprite` equals the 1,562 golden answers under each
  availability rule, the golden is what its generator writes, and old rule, new rule and
  renderer agree with sprite files missing; a plant whose sprite file is missing is painted with
  the next sprite in line; plant kinds, category names and recipe keys cannot drift; the spike's
  palette copy equals the shared table. `tests/unit/test_plant_sprite_conformance.py`
  (unchanged) regenerates all 123 SVGs.
- **`tests/unit/test_scene3d_plants.py`**: all 123 recipes × EVERY proportion step (171, from
  1 : 50 to 80 : 1; a different id in every cell — 21,033 plants) and × six real sizes × 5 ids
  through the pipeline's builder, and nine extreme sizes × three recipe forms per archetype.
  Asserted for every one: height, spread and base exact, no foliage vertex beyond 1.09 canopy
  radii (by construction — and the same for 500 hostile point clouds handed to the fit itself)
  and no wood vertex beyond 0.5 (the trunk builders' invariant). A size outside a micrometre …
  10 km is refused with `ValueError`; the corners of that range build an exact plant. Measured,
  as tripwires with stated headroom (`scripts/measure_plant_art_3d.py truth`: 63,099 plants):
  the builder's own top 1.0000 of the height before the fit; nothing pressed onto the ground;
  at most 2.18 % of the foliage vertices pulled back onto the canopy circle from at most 1.085
  radii; foliage area quantiles per archetype; no ground-flat triangle; at least six vertices
  on the ground. Triangles at most canopy 1,904, mound 1,608, climber 1,352, grass 1,120, ground
  1,092, hedge 900, feathery 792, conifer 664, rosette 560, allium 470, head 400, palm 356,
  flower 316. The foliage hue
  within 10° of the rendered sprite for all 123 (worst 5.0°), and the tip weights re-derived
  from the sprites. Same record → same mesh, built twice from nothing, every archetype. Two ids: twelve ids a recipe, no pair
  above 0.985 (measured over 30 ids: maximum 0.975, 99 % of 53,505 pairs below 0.952). The fit's
  report against hand-made plants. The shape cache: exact scale, exact size at 600 random
  sizes, shared arrays that cannot be made writeable, a key that is the builder's only view of
  a recipe, and its behaviour AT its cap (0 rebuilt), one plant past it (1 per tick) and far
  past it (the overflow). A plant one proportion step on is still itself. The
  placeholder; wind weights; `verify_builder` throughout.
- **`tests/integration/test_scene3d_plants.py`** (§8.10): fifteen plants planted through the real
  drop and tool paths, two dates, exact sink calls; ALL 100 gallery plants and all 222 species
  strings (and the odd ones) drawn and built from the same sprite, through the real scene and
  `snapshot_records`; a species assigned from the plant database.
- **`tests/perf/test_scene3d_plants_budget.py`**: both bench plans — 61 plants 68,402 triangles,
  320 plants 291,652; June → December reaches the sink as 29 / 80 `replace_geometry` calls and
  nothing else; a first build, and a daily scrub tick warm and cold, in milliseconds and in
  units of a reference workload (the numbers: §8.29.7); a warm tick holds what a cold build
  holds.
- **`scripts/measure_plant_art_3d.py`** prints every number above (`truth`, `reach`, `growth`,
  `clones`, `shapes`, `scrub`, `cache`); **`scripts/mutation_check_plant_art.py`** breaks one
  rule at a time on a copy of the tree: 94 mutants (73 before the second review, 87 before the
  third), every one killed — a kill being pytest's exit code 1 with a named FAILED test, held
  by `tests/unit/test_plant_art_mutation_script.py`. (Its first run on the reworked builder, in
  the first fix round, killed
  72: the survivor — the fit no longer sets a hovering plant down — showed that no builder hovers
  any more, so that safety net was exercised by nothing; the fit-report test now asserts it. The
  run before the review, 45 mutants, had found the placeholder's round rim unpinned the same
  way.)

## ADR-059 addendum: the species name is a whole name, and the assignment writes it (#446, #445)

**Context.** The "plant art v0" addendum above extracted the 2D sprite rule as it stood, quirks
included, and the alternative it rejected there was explicit: "a better resolver for 3D - keyed on
`species_key`, without the partial match ... Fixing the 2D rule changes sprites users see and is
its own issue." That issue is #446, and it is now decided. The rule matched a species name by
asking whether a key was CONTAINED in the name, or the name in the key - which is not a name
match: "Melon" took the eggplant's sprite ("melon" is inside "solanum melongena"),
"Petroselinum crispum" took the rose's, "peach_tree" took the pea's, and a string of blanks
took the rose's (the empty string is inside every key). A second, quieter half of the same
defect sat next door (#445): a species assigned from the plant database wrote the RECORD
(`metadata["plant_species"]`) and not the item's own species STRING, and the string is what the
resolver reads - so a plant assigned "Oak" kept the generic tree sprite in 2D and was built as a
tree in 3D.

**Decision.**

1. **A species name is matched as a whole name or alias, in three steps**: the whole name; else a
   key whose every word is a word of the name ("Broad Bean" -> bean, "Winter Squash" -> squash);
   else a key that holds every word of the name ("Solanum" -> tomato). A name no sprite knows
   falls back to the plant's CATEGORY sprite. The whole-name-only rule the issue proposed was
   MEASURED first and rejected: it changes 266 of the golden's 1,562 answers over 110 distinct
   names, and most of those are regressions - "Quercus robur", "Broad Bean", "Sweet Corn" have no
   exact key and would fall back to a generic sprite. The rule that shipped changes 74 answers
   over 37 names, and of the bundled species' 118 names exactly ONE changes - the melon, which
   was drawn as an eggplant. The rule stays ONE rule, shared by the 2D renderer and the 3D plant
   builder, and the golden is regenerated from it; the rule it replaced is kept as
   `legacy_resolve` in the golden's generator, which prints the before and after
   (`--legacy-diff`).
2. **What the fix does not do, stated here rather than left to be discovered**: "Lemon Balm",
   "Bean (Bush)" and "Sweet Potato" still take a fruit or vegetable sprite, because their names
   contain a whole word that is another plant's name ("lemon", "bean", "potato"). A curated
   alias table would fix them; the owner declined it, and the residue is pinned in
   `tests/unit/test_plant_art.py` so that a later change to the rule has to say so.
3. **An assignment writes the item's species STRING**, so the plant is drawn - and built - with
   the species it was assigned. The string is the plant's own name: the gallery writes it when the
   plant is created, and an assignment replaces it with the name of the species assigned (the
   record's common name, or its scientific name when the common name names no sprite). The
   record's DATA and the string can still differ - a gallery "Pumpkin" carries the data of "Winter
   Squash" while its own string is "pumpkin" - which is exactly why the resolver reads the string
   and never the record's name. The string is written inside the same `ApplySpeciesCommand`, so
   the record, the spacing override, the footprint radius and the string revert together in one
   undo step.

**Alternatives rejected.**

- **Whole-name-only** (the issue's own proposal): measured above - 266 answers over 110 names, and
  most of those regressions. A rule that is right for "Melon" and wrong for "Quercus robur" is not
  a rule.
- **A curated alias table** for the residue ("lemon balm" -> herb, "bean (bush)" -> vegetable):
  it fixes the last three cases exactly, at the price of a hand-maintained table that can rot and
  a second place where a name has to be taught. The owner declined it; the residue is pinned
  instead.
- **Resolving the sprite from the record's data name** (never writing the string): the item's
  string and the record's name are different things - a gallery "Pumpkin" carries the data of
  "Winter Squash" - so the record's name would draw the wrong plant, and the 2D/3D contract of
  "the item's own string, exactly as it is" would be lost.

**Consequences.** The 2D and the 3D view answer the same question the same way, and a species
assigned from the database is the species the plan shows - in the plan and in the 3D view alike.
The golden is no longer an independent oracle (it is regenerated from the rule), so the rule is
held by the mutation script instead: `scripts/mutation_check_plant_art.py` breaks one rule at a
time, and four new mutants pin the three matching steps and the normalisation of the name.

**Evidence.** `tests/unit/test_plant_art.py::TestTheNameIsMatchedAsAWholeName` (the rule and the
residue), `tests/integration/test_apply_database_species.py::test_the_assigned_species_is_the_sprite_the_plant_is_drawn_with`
(the assignment, through the real panel), `tests/integration/test_scene3d_plants.py::test_a_species_assigned_from_the_database_is_built_as_the_canvas_draws_it`
(2D and 3D agree), `scripts/make_sprite_resolution_golden.py --legacy-diff` (the before and
after), FR-PLANT-ART-05, FR-PLANT-21, PF-DOM-26, PF-DOM-27.


## What the second review found (same story, the fix round's own claims)

- **A sample's maximum, dressed as a guarantee — again, one level down.** The requirement said
  "no part more than 10 % outside the canopy circle" on the strength of a maximum over 117,000
  builds (1.092); one id in 300,000, at a proportion the sample did not hold, read 1.1006. It
  said the foliage's mass reaches "62–87 % of the height"; a rhubarb half as tall as wide read
  60.3 %. The reach is structural now (decision 4), the mass is stated as a measurement, and the
  tests sweep every proportion step instead of six sizes (§8.29.7, §8.10.6).
- **The shape cache had a cliff** at 1,025 growing plants (decision 9), **made the determinism
  tests vacuous** (a warm second build is a look-up: they passed with unseeded dice), and
  **handed out arrays whose read-only flag could be switched back on** — damage that every later
  build of that plant would then carry.
- **"A growing plant re-rolls its form at every step" was NOT so** — measured, a plant one step
  on is 0.99 … 1.00 itself against 0.71 … 0.92 for another id — except the conifer at the steps
  where it gains a whorl (decision 8).

## What the first version of the plant art got wrong (independent review, same day)

Recorded because each of these passed every gate the story had set itself (the entries with
their measurements: PF-L3D-01).

- **A squash was built 1.6 times too tall and squashed back.** The height gate compared the
  mesh's top with the plan's height after a fit that scales the top onto the height: it could
  not fail. Shell leaves faced along the ray from the plant's heart instead of along the lobe's
  surface, so on a flat plant they stood on edge; at 15 × 800 cm nine archetypes were 3.5 to 11.6
  times too tall. The test matrix scaled height and spread together and never saw another
  proportion. Decision 4, and the fourth test pattern of §8.10.6.
- **"2D and 3D agree for every plant from the gallery" was false.** The builder resolved from the
  species data's name; the canvas resolves from the item's string. Checked for 11 of 86 gallery
  species. Decision 2 (ruling R14).
- **The renderer's missing-file fall-through was pinned by nothing** — dropping it survived
  3,048 tests, because the shipped sprite set is complete. Decision 2's differential.
- **The generator needed Qt for the first time**, the no-clones gate was five fixed ids, the
  build budget was six times a quiet median with no scrub tick timed, and a daily scrub rebuilt
  every growing plant. Decisions 1, 8 and 9, and §8.29.7's numbers.

## ADR-059 addendum: builders v0 — the built world (Phase 17, L1.6)

**Status**: Accepted (2026-10-11, #385 story L1.6); amended the same day after the senior
review's first round (decisions 5, 7 and 9, the first consequence and its table) and after its
second (the table's reach column and what replaced a false sentence about shadow tips; the
conditions of three stated bounds; the run-time warning for an unknown style). Nothing is
rendered by this story either: the builders are judged by numbers on `Mesh` and `RecordingSink`;
the look is judged later, by the combined look-dev pass and the independent 3D reviewer.

**Context.** Decision 9 left every kind on the default prism. The L0 spike has builders for
buildings, fences, walls, beds and hedges (`spike_q3d/meshes.py`), measured and owner-signed, but
they build at absolute scene positions, take their colours from literals, handle convex footprints
only, and correct their heights with a fit after the fact.

**Decision.**

1. **A package of pure builders**, `core/scene3d/builders/`, one module per family with a
   module-level `register(registry)`; `production_registry()` returns a fresh registry holding all
   of them — and the plant builder: it calls `plants.register(registry)` (L1.7) after the built
   world's `register`; a test holds that no kind belongs to both families and that each of the
   15 kinds resolves to its own builder. The built world's kinds: `HOUSE`, `GARAGE_SHED`,
   `TOOL_SHED`, `FENCE`, `WALL`, `RAISED_BED`, `CONTAINER`, `WALL_PLANTER`, `CONTAINER_ROUND`,
   `GARDEN_BED`, `HEDGE_SECTION`, `HEDGE_POLYGON`. Every other kind keeps the default: paths,
   lawns and ridge items have no height (ground); furniture, glass, water and pergolas are L4.
2. **The top is the height, by construction.** Every builder shapes its item FOR a height and its
   highest vertex is that height to the float32 — posts are the top of a fence, the ridge tile's
   apex the top of a house, a pot's rim the top of a pot, the highest leaf of a hedge is put on
   its trim line. `fit_parts` (one z-scale for all parts, the spike's `fit_height`) stays as a
   safety net, and a test asserts every builder's fit scale is 1.0 ± 1e-6 over the whole matrix.
   The spike's builders decorated first and fitted afterwards; a fit hides a builder that is
   wrong.
3. **No height, no shadow.** `BuiltBuilder` wraps a shape function `(record, height) -> parts`:
   an item the plan gives no height is built at its kind's nominal height — ASKED of the 2D
   height resolver (`effective_height_cm(kind, None)`), never a table of kinds of its own — as
   decoration, every part `casts_shadow=False`. A kind without a nominal height (an in-ground
   bed) gets no solid. (Honestly: this path is almost never taken. The snapshot already resolves
   a height for every registered kind but `GARDEN_BED`, so only hand-made records reach it.)
   *Superseded for 3D by the owner in L4 (ADR-065, "Owner's manual pass"): what is built
   casts in 3D; the 2D sun study keeps "no height, no shadow".*
4. **A gable roof is two planes through the ridge LINE** (`roofs.gable_roof`):
   `z = top − cap rise − slope·|distance to the line|` over the footprint grown by the overhang.
   That is the model the 2D canvas paints (`_paint_with_ridge` splits the polygon along the
   infinite line), so it holds for concave footprints and for a ridge the user dragged. The walls
   are one trapezoid per footprint edge — split where an edge crosses the line — up to the slab's
   underside, so gable ends need no special case. **The ridge is consumed, never derived**
   (ADR-046): `params["ridge"]` is the live ridge item's ends; a HOUSE without a usable one is a
   plain block. The ridge tile's apex line lies ON that line and runs to the roof's edge:
   `overhang / cos θ` beyond a ridge end whose wall it meets at θ, exactly the 30 cm overhang
   where it meets the wall squarely. Sheds have no ridge item; theirs is the long axis of the
   bounding box **aligned with the footprint's longest edge**, in the item-local frame.
5. **Polylines are built from the centre line** (`record.path`, `record.path_width_cm`), segment
   by segment, never from the stroke outline in `record.footprints`: a fence round a garden is a
   closed loop, and its record holds the stroke's OUTER ring in `footprints` and the garden it
   encloses as a hole in `holes` (decision 3 of this ADR, as corrected). The outer ring taken for
   the fence's shape lays a slab over the garden; `verify_builder` refuses any solid that covers
   more than half of a hole, and every line solid is held to it on loops the size of a garden
   (the matrix's 8 m × 6 m loop, a nearly closed one and one with a 30° corner, in every style:
   a post fence or a plain panel covers ≤ 3 % of the hole, a wall or hedge ≤ 30 %). **The
   default bound does not fit a SMALL loop of a thick line.** A wall's section reaches 19 cm
   either side of its centre line where its stroke reaches 2, so of the 96 cm hole a 1 m square
   loop encloses it covers a 17 cm strip all round — 56 % measured — and the default refuses the
   production builder's own, correct solid. Such a loop is verified with an explicit
   `hole_cover_limit` and the reason (pinned at 0.65 for a 1 m loop; from 1.5 m on the default
   holds). The contract's gate also has a size floor (`build.HOLE_MIN_WIDTH_CM`, 10 cm — a hole
   narrower than that is not judged): the OTHER end of the range, a 12 cm loop of wall being one
   solid block that passes. **Measured for square loops at 1 cm steps of the side (6 – 200 cm),
   the default refuses: a WALL 15 – 120 cm, a stone-wall fence 16 – 118 cm, a hedge fence
   19 – 111 cm and again at 114 cm** — the gate samples the hole on a coarse grid, so its
   reading moves in steps (0.83 / 0.66 / 0.56 / 0.44 for a wall) and its verdict is not
   monotonic at the edge of a range. (Earlier versions of this paragraph printed readings taken
   at 10 cm and 2 cm steps as if they were exact.) A closed
   centre line is swept as a loop. **A builder that needs
   one simple outline checks that it has one**: one outer ring, no hole, and not
   `params["outline_resolved"]` — the contract's flag for a polygon drawn crossing or touching
   itself (`common.has_one_plain_ring`). Every other polygon-footprint record is built as
   `common.plain_block` — ALL regions, holes cut out — and that same function is every fallback
   block (a house without a usable ridge, with a ridge off the building, too low for a roof), so
   none of them takes `footprints[0]` for the whole (the first cut's house block extruded
   `footprints[:1]`). **The flag decides, not the ring count**: a resolved outline may be one
   plain ring, and until the flag existed such a HOUSE kept a gable roof. It is the block now —
   for every polygon kind, because a resolved ring can come within 0.002 cm of itself and no
   frame, inset or overhang is offset from that; and for a HOUSE also when a ridge IS handed in
   (the snapshot hands none on for a resolved outline; the builder does not rely on it). **What a line becomes is decided in ONE place**, `builders/lines.py`,
   from its kind and style; `fences.py` and `walls.py` are geometry only and do not import each
   other. A `FENCE` without a style is the default fence (posts, rails, pickets); a `WALL`
   without one is the wall; one of the five fence styles is that style whatever the kind. **A
   style no builder knows — a path style on a fence, or a fence style added to
   `PATH_FENCE_STYLES` later — is a plain panel**: the stroke as wide as it is drawn, up to the
   height, exactly the solid the 2D model casts. The first cut turned it into a picket fence
   without a word. A new fence style is caught before that: the mirror `fences.FENCE_STYLES` is
   pinned against the 2D table's "fence" category by a test. **And the fallback is not silent
   at run time:** the first build of a line in such a style writes ONE warning to the
   application's log per style name (`lines._report_plain`) — not one per build, since every
   edit rebuilds the items it touches. The memory of names is bounded at 64 and so is the log:
   after 64 names one line says that no more follow, and nothing further is logged for the
   session (the first version started the memory over when full, which logged every name again
   on every rebuild pass — the policy the snapshot's own log rejects).
6. **The plan's own colour is a tint; everything else is a mirrored 2D table entry.** Read from
   the code, not assumed: every 2D fence and wall style paints from the item's own pen colour (the
   style table only pre-sets it), and containers are filled in the item's colour. So fences,
   walls, building walls and containers are `tinted` parts with pure white vertices — a recolour
   never rebuilds them. What 2D draws from a fixed material is baked: roof tiles, shingles,
   timber, a raised bed's oak (it is SVG-rendered), soil, hedge greens. Those 13 colours live in
   `builders/palette.py`, each naming its source, and a drift guard loads both generator scripts
   and fails when a mirror and its source disagree.
7. **One soil rule.** The soil of every bed and container is at
   `object_height.soil_surface_cm(kind, height)` — the function that gives a plant its base
   (ADR-037 addendum above, decision 4): 2 cm under a bed's rim, AT a container's height. So
   for the bed builders a plant is on its soil by construction. (Not for a bed that is built as
   the plain block of decision 5 — an outline that is not one plain ring: that block's top is
   the rim, and its plants stand 2 cm inside it. Pinned as a stated limit.) A
   container has no lip in 3D — its top runs straight into its soil — because the plan holds
   none. A `GARDEN_BED` that carries a height gets a bed solid for the same reason: its plants
   stand 2 cm under its rim, so there must be soil there.
8. **Budgets are per metre and per corner**, and asserted as CEILINGS (`builders.triangle_budget`),
   never as exact counts: a picket fence ≤ 105 triangles per metre + 60 per segment, metal
   100 + 35, chain link 55 + 110; a wall 36 per segment + 20; a plain panel 12 per segment + 8;
   a building 80 + 30 per footprint corner; a hedge at most 6,000 leaves (12,000 triangles)
   whatever its size.
9. **A corner is mitred up to two offsets and bevelled beyond** (`primitives.BEVEL_BEYOND = 2.0`,
   a turn of 120°, an interior angle of 60°). A mitre at an interior angle φ is `1 / sin(φ / 2)`
   offsets long — 3.9 at 30°, 5.8 at 20°. On the side of a corner where the two offset edges run
   APART (the outside of a bend, an outward offset at a convex corner), a longer mitre is cut
   flat: `sweep` ends the section square on each segment and joins the two with a face,
   `offset_ring` returns two points for the corner. Where the edges run TOGETHER (the inside of a
   bend, an inset at an acute corner) their intersection is the true corner and is kept, up to
   `MITER_LIMIT` = 4 offsets from the joint. **Stated bound, with its condition:** nothing lies
   further than `BEVEL_BEYOND` offsets from the line or ring it was built on WHEN every leg of
   a line is at least `MITER_LIMIT` offsets long (76 cm for a wall's 19 cm of coping) —
   asserted over the whole matrix, whose legs are, and over 400 random zigzags. The kept inside
   corner lies `tan(turn / 2)` offsets back along each leg; where a leg is SHORTER than that,
   the corner lies beyond the leg's other end, and the real bound is the mitre's own length,
   `MITER_LIMIT` offsets: a wall zigzag with 25 cm legs reaches 2.62–2.70 offsets (50–51 cm), a
   bare 10 cm half width along 20 cm legs at 160° reaches 2.06 — both pinned. Such a wall is
   drawn with legs shorter than it is thick and overlaps itself; the plan describes no such
   wall, and v0 does not clamp it. The first cut only cut a mitre at 4 offsets: a 116 cm eave
   spike on an acute-triangle house with a 30 cm overhang, a 76 cm spike of coping on a hairpin
   wall.

**Alternatives considered (rejected).**
- *Moving `MATERIALS` out of `scripts/generate_object_sprites.py` into the package.* One table,
  no mirror — but the sprite generator would have to import the application (and Qt, through
  `core/__init__`), the provenance record of 24 shipped sprites would move (ADR-042), and the
  texture palettes are locals inside generator functions anyway. A 13-entry mirror with a drift
  guard is the smaller change; the precedent is `TRAMPOLINE_MAT`.
- *Baked fence and wall colours from the style table.* `core/object_types` imports Qt, and the
  table is only a preset: a recoloured fence would have stayed brown in 3D.
- *Shading weights on tinted parts* (posts darker than pickets). Not in any table; v0 carries
  none, and a look pass can add them with evidence.
- *Importing pyclipper for the roof's overhang.* The package's import rule allows the standard
  library, numpy and Qt-free `core` modules only. A mitre offset in numpy (every edge moves
  exactly the distance) is what a roof needs and all it needs.
- *The scene-frame bounding box for a shed's ridge* (the spike). Found by turning the local
  footprint in the test matrix: a shed drawn as a turned polygon got a ridge askew to its walls.
- *Clamping hedge leaves at the trim height vertex by vertex.* It flattened leaves into the
  plane and turned some inside out; a leaf is moved whole instead.
- *The stroke width as the wall's thickness.* See the first consequence.
- *An unknown style as the default picket fence, or a raised error* (which `SceneSync` turns into
  "no solid at all" plus a logged `BuildFailure`). The first invents a look, the second removes a
  fence the plan has. The plain panel is what the plan itself describes.
- *A mitre limit alone (the first cut), or bevelling the inside too.* Decision 9.
- *Thinner 3D bodies, or porosity in the 2D caster model, to close the gap of the first
  consequence.* Out of scope by ruling: the nominal sections stay (the owner answered "keep
  as-is" to path and wall widths on the L0 board), and the 2D model is the analysis.

**Consequences.**
- **The built world's 3D shadows are not the 2D model's shadows — and for fences the difference
  goes the other way from what this addendum first said.** The truth gate "Shadows"
  (`ogp-lush-cinematic` §1, IoU ≥ 0.85 against the analytic 2D shadow) is defined on a solid BOX
  caster, where both models are the same solid. The built world departs from the prism in four
  stated ways. Measured by the committed `scripts/measure_built_world_shadows.py`.
  **Measuring conditions:** one item on flat ground; each mesh projected ANALYTICALLY onto the
  ground along the sun ray — no shadow map, no texel — against `compute_scene_shadows` of the
  item's footprint and height; a straight 10 m line with the sun square to it, a building with
  the sun square to or along its ridge; a sun elevation of 15° / 35° / 60°. Three numbers: 3D
  area ÷ 2D area, intersection over union, and the **reach** — how much further (+) or less
  far (−) the 3D shadow extends along the shadow direction than the 2D one, in cm: where its
  TIP is.

  | Kind | 3D area ÷ 2D area | IoU | Reach 3D − 2D (cm) | Why |
  |---|---|---|---|---|
  | picket fence | 1.01 / 1.01 / 1.00 | 0.66 / 0.67 / 0.68 | +2.0 / +2.0 / +2.4 | porosity (weighted 2D area; IoU vs solid strip) |
  | metal fence | 0.99 / 0.99 / 0.98 | 0.19 / 0.20 / 0.24 | +0.8 / +0.8 / +0.8 | porosity (weighted 2D area; IoU vs solid strip) |
  | chain-link fence | 1.09 / 1.03 / 1.08 | 0.12 / 0.13 / 0.19 | +1.5 / +1.5 / +1.5 | porosity (weighted 2D area; IoU vs solid strip) |
  | hedge fence | 1.04 / 1.13 / 1.31 | 0.96 / 0.89 / 0.76 | +19.6 / +19.5 / +19.6 | nominal section |
  | stone-wall fence | 1.06 / 1.15 / 1.37 | 0.94 / 0.87 / 0.73 | +14.5 / +14.5 / +15.3 | nominal section |
  | wall | 1.04 / 1.10 / 1.24 | 0.96 / 0.91 / 0.81 | +15.0 / +15.0 / +15.8 | nominal section |
  | plain panel (unknown style) | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.0 / 0.0 / 0.0 | none: the stroke strip |
  | house, sun square to the ridge | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.0 / 0.0 / 0.0 | gable roof (#440: shared roof+wall triangles) |
  | house, sun along the ridge | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.0 / 0.0 / 0.0 | gable roof (#440: shared roof+wall triangles) |
  | shed, sun square to the ridge | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.0 / 0.0 / 0.0 | gable roof (#440: shared roof+wall triangles) |
  | raised bed | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | −0.6 / −0.6 / −0.3 | none: a prism |
  | container (box) | 1.00 / 0.99 / 0.99 | 1.00 / 0.99 / 0.99 | −0.6 / −0.6 / −0.3 | none: a prism |
  | terracotta pot | 0.83 / 0.81 / 0.81 | 0.83 / 0.81 / 0.81 | −0.6 / −0.6 / −0.3 | taper |
  | round tub | 0.91 / 0.89 / 0.89 | 0.91 / 0.89 / 0.89 | −0.5 / −0.5 / −0.3 | taper |
  | hedge (polygon) | 0.98 / 0.96 / 0.94 | 0.97 / 0.96 / 0.94 | +3.6 / +4.0 / +4.4 | leaf shell |
  | hedge (section) | 0.97 / 0.96 / 0.94 | 0.96 / 0.95 / 0.93 | +2.7 / +3.0 / +3.2 | leaf shell |
  | house, hip roof | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.0 / 0.0 / 0.0 | hip roof (#440: shared roof+wall triangles) |
  | house, single-slope roof | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.0 / 0.0 / 0.0 | single-slope roof (#440: shared roof+wall triangles) |
  | house, flat roof | 1.02 / 1.03 / 1.04 | 0.98 / 0.97 / 0.96 | +15.0 / +15.0 / +15.0 | flat roof: the prism (L4) |
  | table | 0.38 / 0.54 / 0.70 | 0.38 / 0.54 / 0.70 | −0.5 / −0.5 / −0.3 | porosity: a top on legs (L4) |
  | picnic table | 0.37 / 0.41 / 0.57 | 0.37 / 0.41 / 0.57 | −38.5 / −38.5 / −20.6 | porosity: boards and A-frames (L4) |
  | grill | 0.28 / 0.30 / 0.36 | 0.28 / 0.30 / 0.36 | −27.3 / −23.0 / −17.5 | porosity: a kettle on legs (L4) |
  | greenhouse | 1.00 / 1.00 / 1.00 | 0.33 / 0.28 / 0.29 | 0.0 / 0.0 / 0.0 | glass: the frame alone shades (#830) |
  | trampoline | 0.47 / 0.64 / 0.76 | 0.47 / 0.64 / 0.76 | −1.0 / −1.0 / −1.0 | porosity: a mat on legs (L4) |
  | table round | 0.35 / 0.50 / 0.67 | 0.35 / 0.50 / 0.67 | -1.2 / -1.2 / -0.7 | shape and porosity vs solid 2D prism |
  | chair | 0.49 / 0.54 / 0.62 | 0.49 / 0.54 / 0.62 | -4.3 / -4.3 / -4.0 | shape and porosity vs solid 2D prism |
  | bench | 0.39 / 0.45 / 0.54 | 0.39 / 0.45 / 0.54 | -7.6 / -7.6 / -7.3 | shape and porosity vs solid 2D prism |
  | lounger | 0.64 / 0.71 / 0.77 | 0.64 / 0.71 / 0.77 | -9.7 / -9.7 / -9.7 | shape and porosity vs solid 2D prism |
  | parasol | 1.06 / 1.00 / 0.96 | 0.89 / 0.93 / 0.96 | +60.3 / -2.0 / -2.0 | a raised canopy, not a prism (#830) |
  | fire pit | 0.94 / 0.94 / 0.93 | 0.94 / 0.94 / 0.93 | -2.1 / -2.1 / -2.1 | shape and porosity vs solid 2D prism |
  | planter pot | 0.83 / 0.81 / 0.81 | 0.83 / 0.81 / 0.81 | -0.6 / -0.6 / -0.3 | shape and porosity vs solid 2D prism |
  | sandbox | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.0 / 0.0 / 0.0 | shape and porosity vs solid 2D prism |
  | hot tub | 1.00 / 0.85 / 0.60 | 1.00 / 0.85 / 0.60 | 0.0 / 0.0 / 0.0 | shape and porosity vs solid 2D prism |
  | swing | 1.00 / 1.00 / 1.00 | 0.18 / 0.19 / 0.21 | 0.0 / 0.0 / 0.0 | open frame (#698 weighted, #855 reach-trimmed 2D area; IoU vs trimmed prism) |
  | hammock | 1.00 / 1.00 / 1.00 | 0.23 / 0.33 / 0.43 | 0.0 / 0.0 / 0.0 | open frame (#698 weighted, #855 reach-trimmed 2D area; IoU vs trimmed prism) |
  | compost bin | 0.93 / 0.94 / 0.89 | 0.93 / 0.94 / 0.89 | -0.8 / -0.8 / -0.5 | shape and porosity vs solid 2D prism |
  | cold frame | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.0 / 0.0 / 0.0 | shape and porosity vs solid 2D prism |
  | rain barrel | 0.81 / 0.79 / 0.76 | 0.81 / 0.79 / 0.76 | -20.1 / -10.9 / -7.5 | shape and porosity vs solid 2D prism |
  | water tap | 0.64 / 0.63 / 0.61 | 0.64 / 0.63 / 0.61 | -6.0 / -6.0 / -6.0 | shape and porosity vs solid 2D prism |
  | wheelbarrow | 0.44 / 0.45 / 0.46 | 0.44 / 0.45 / 0.46 | -22.0 / -22.0 / -22.0 | shape and porosity vs solid 2D prism |
  | bird bath | 0.40 / 0.47 / 0.61 | 0.40 / 0.47 / 0.61 | -0.8 / -0.8 / -0.8 | shape and porosity vs solid 2D prism |
  | pergola | 0.99 / 0.99 / 0.99 | 0.29 / 0.32 / 0.36 | -0.8 / -0.8 / -0.5 | open frame (#698 weighted, #855 reach-trimmed 2D area; IoU vs trimmed prism) |
  | trellis | 1.00 / 1.00 / 1.00 | 0.33 / 0.35 / 0.41 | 0.0 / 0.0 / 0.0 | open frame (#698 weighted, #855 reach-trimmed 2D area; IoU vs trimmed prism) |
  | garden light | 1.00 / 1.00 / 1.00 | 0.21 / 0.29 / 0.39 | 0.0 / 0.0 / 0.0 | open frame (#698 weighted, #855 reach-trimmed 2D area; IoU vs trimmed prism) |

  Follow-up #624 extends the analytic reference to all 24 L4 object kinds; Phase 17 L5.4
  (#389, ADR-070) adds the garden light. A string of lights casts no 2D shadow (ADR-070's
  addendum from the owner's manual test), so it has no row.
  The script uses each new case's production default height, its stated footprint
  in `L4_OBJECT_SIZES`, and a south sun at 15 / 35 / 60 degrees. The five OPEN
  FRAMES — pergola, trellis, swing, hammock, garden light — are weighted by their
  transmittance since #698 (the ADR-059 / ADR-070 addendum on open frames): their
  ratio column is 3D against the WEIGHTED 2D prism, and their IoU column still
  shows how little of the prism the frame shades. Every other object stays a
  solid prism; the mostly-air ones among them by recorded decision
  (`core.object_height.SOLID_2D_DECISIONS`).

  The four reasons: **(1) nominal section** — a polyline's stroke is a line weight (fence 3 cm,
  wall 4–5 cm, hedge 8 cm), the 2D model extrudes that strip, and the 3D bodies use the L0
  board's sections (a wall `max(stroke, 30)` cm, a hedge `max(stroke, 40)` cm): a WIDER shadow,
  more so the higher the sun — fine at 15° (IoU ≥ 0.94), under the box gate at 60° (0.73–0.81);
  **(2) porosity** (until #440) — a picket, metal or chain-link fence is mostly air, so its 3D
  shadow lies INSIDE the unweighted 2D strip's and was 67–70 %, 19–24 % and 13–19 % of it
  (the ratio column before #440, at its parent cc2b3eb7): the hours-of-sun map showed full shade behind a chain-link fence;
  **(3) gable against prism** (until #440) — 2D extruded a building's footprint flat-topped to
  its ridge height; **(4) taper and leaf shell** — a pot narrows to its foot, a hedge's block is its
  footprint drawn in by 4 cm. Which rows meet IoU 0.85 is the table's to say, not a sentence's.
  Since #440 reasons (2) and (3) no longer hold for the analysis: a picket, metal or
  chain-link fence is weighted by its transmittance (ratio 0.98–1.09), and a pitched building's roof and
  walls are projected — the gabled, hip and single-slope houses in the table above read IoU 1.00
  and a reach of 0.0. The analysis — overlay and heatmap — stays the 2D
  model's, draped onto the 3D ground (ADR-048, the scope note of criterion 8); the 3D shadow is
  a picture of the mesh.

  **Where the tip is — what agrees and what does not.** The height is the same number in both
  models, but the height alone does not place a tip: the tip is cast by the highest EDGE, and
  what counts is where that edge stands. *Agree within 2.5 cm at every elevation:* the prisms
  (raised bed and box −0.6 cm: the top edge's bevel; the plain panel 0.0), the pots (−0.6 and
  −0.5 cm: the rim's bevel) and the post fences (picket +2.0 to +2.4, metal +0.8, chain link
  +1.5 cm: a post is wider than the stroke). The hedge polygons pass the 2D tip by 2.7–4.4 cm
  (leaf tips). *Did not agree until #440 (cc2b3eb7's `DOCUMENTED`), which projects a pitched
  roof and its walls — the table's pitched houses now read a reach of 0.0:* **(a) a gabled
  building with the sun square to its ridge.** The 2D model extruded the whole footprint to the
  ridge height, so its highest edge was at the FAR WALL; a gable's ridge is mid-house. At a low
  sun the ridge cast the tip and the 3D shadow was exactly half the depth short — 270 cm on the
  5.4 m deep house, 150 cm on the 3 m shed; at a high sun the far eave cast it and the miss
  shrank to 108 cm and 21 cm at 60°. The roof was right; the difference was the 2D model's
  flat-topped prism, which #440 replaced. **(b) The same building with the sun along its
  ridge:** the 30 cm overhang carried the ridge height past the gable wall, +30 cm. *Still do
  not agree, among these L0 builder rows (the open objects of L4/L5 — a parasol, a swing, the
  garden lights — and the flat-roofed house are in the table):* **(c) Nominal sections:** a wall's coping edge stands 17 cm from the centre line
  where the 4 cm stroke's edge stands at 2, so its tip lies 15 cm further (stone-wall fence
  +14.5, hedge fence +19.5). An earlier version of
  this paragraph claimed the opposite of (a)–(c) in one universal sentence; **no sentence about
  shadows goes next to the gate unless the script prints the number behind it.**

  **What these numbers are for.** They are analytic references for the BUILDERS:
  `tests/unit/test_scene3d_shadow_agreement.py` holds the builders to this table within 0.05
  (a reach within 1 cm), and holds this table, §8.29.6's and the skill's to the script's
  `DOCUMENTED`; a builder that moves a number updates all of them. They are not what an engine
  render must read: a shadow map is judged on solid casters (the box gate), and a member near
  one shadow-map texel — a 0.8 cm chain-link wire, a 1.6 cm bar — can read lower in a render
  through no fault of the builder. Thin members are exempt from a per-pixel IoU.
  **Porous fences (answered by #440):** the 2D sun study no longer treats a chain-link, metal or
  picket fence as a solid strip — #440 weights it by its angle-dependent structural transmittance
  (the ADR-037 / ADR-048 addendum on the unified geometry-aware caster path), and projects a
  building's roof and walls. **Open frames (answered by #698):** a pergola, a trellis, a
  swing, a hammock and a garden light are weighted the same way, by the share of their prism
  their own members shade (the ADR-059 / ADR-070 addendum on open frames); a parasol, a
  greenhouse and the low furniture stay solid prisms by recorded decision.
- A HOUSE's fill colour tints its WALLS in 3D; in 2D it tints the roof texture (a 31 % overlay).
  And the tint rule is uneven for hedges: a hedge POLYGON is baked in the hedge texture's greens
  and ignores a recolour, while a hedge FENCE is tinted with the item's stroke. Both follow what
  2D draws from (a texture there, a pen here) and both are open look questions for the look pass
  and the owner — not decided here.
- Tinted parts are one flat colour; default fences are saddle brown and default walls dim grey —
  darker than the L0 board's literals, which were in no 2D table (plaster `#efe4cf`, roof
  `#b4553d`, fence `#a0744a`, wall `#9b9384`, bed `#9a6b3f`, soil `#4a3222`, pot `#c46a3c`,
  hedge core `#1f4a26`).
- A hedge whose shell exceeds 18 m² — about 5 m of a 1.5 m hedge — is at the leaf cap, and its
  coverage thins:
  bench_small's 10.5 m hedge has 47 % of the uncapped count, bench_large's 30 m hedge 17 %. The
  spike had the same cap; "larger leaves at the same coverage" is a look decision left to the
  look-dev pass.
- `MATERIAL_KINDS` has one opaque kind, so wood, plaster, stone and soil share its roughness until
  L1.4.
- Measured: both bench plans' built worlds build in 9.8 ms (15 items, 16,874 triangles) and
  18.7 ms (28 items, 22,482 triangles) median on an idle machine — 18 / 24 ms with a second test
  run sharing it, 25 / 50 ms with four agents working on it. Budgets 40 / 60 ms (×3 on a CI
  runner). Because that factor would let a per-vertex Python loop pass on CI, a second,
  clock-free tripwire stands next to the time: a builder makes the same number of Python-level
  calls for 5 m and for 50 m of fence (404), and at most 3,000 for any bench item.

**Validation.** `tests/unit/test_scene3d_builders_primitives.py` (outward winding, exact tops,
mitres and bevels, the lathe's ring = the 2D circle footprint); `tests/unit/test_scene3d_builders.py`
— a matrix of 466 records (every kind × sizes × local geometry turned by 0 / 17 / 90 / 213.5° ×
a straight, bent, closed, nearly closed, hairpin, zigzag and acute-loop line per style, the
styles including a path style and an unknown name × acute-triangle footprints × with and without
a height) through `verify_builder`, exact top, base 0, fit scale 1, budget, winding, the stated
footprint bound, colours → palette; `TestAcuteCorners`; the dispatch table of `lines.py`;
`tests/unit/test_scene3d_builders_palette.py` (palette → 2D sources, and the mirrored or shared
name sets: fence styles, container materials, nominal heights);
`tests/unit/test_scene3d_shadow_agreement.py` (the table above with its reach column, the rule
per kind, and every copy of the table against the script's); `TestAcuteCorners` also pins the
short-leg bound, and `TestPolylinesAreBuiltFromTheCentreLine` a 1 m closed loop per thick solid
with its explicit hole limit and the one-warning-per-style log; `scripts/mutation_check_built_world.py`
breaks one rule at a time (a kill is pytest exit 1 with a failed test); the merged contract's cases —
nothing built over a closed line's hole (`verify_builder`'s plan view, every style), a
self-crossing polygon's lobes as the default prism, a resolved ONE-ring outline as the block for
all ten polygon kinds (and a self-crossing HOUSE drawn in a real scene, with a ridge item: one
ring of ten, flagged, a block — with the flag taken away the same ring gets its roof), and the
committed `scene3d_edge_cases.ogp` — 16 items, 14 records: a turned house on its live ridge, a
house drawn crossing itself (three regions, one block), closed and nearly closed fences, a
ladder of a fence with four holes, a fence 6 cm short of closing, plants on a turned bed and in
a pot — through the production builders;
`tests/integration/test_scene3d_built_world.py` (§8.10: a garden drawn with the real tools, an
edit session with exact sink calls, the ridge in the mesh against the live ridge item for turned
and non-rectangular houses, ≤ 0.1 cm); `tests/perf/test_scene3d_built_world_budget.py`.

## ADR-059 addendum: looks, sky and the animation policy (Phase 17, L1.4)

**Status**: Accepted (2026-10-19, #385 story L1.4); amended the same day by fix round 1
after the code review (`senior-reviewer`) and the look review (`ogp-3d-reviewer`) — see
"Fix round 1" at the end; decisions 1, 3, 4, 5, 6 and 8 below are written as amended. The look itself is judged by the independent
3D reviewer and the owner on the production Beauty Board, not by this record; this record states
what was decided and what was measured.

**Context.** L1.2 shipped ONE fixed look (`NEUTRAL_DAY`: the spike's noon rig, a plain sky colour,
a flat fill light), no sky texture, no fog, no presets, and a wind clock standing still. The L0
spike had measured the rest — three day anchors joined by continuous ramps, a night rig, a
procedural sky rebuilt per sun change, fog = sky horizon × probe exposure × 0.8, four presets —
in one QML file, with every preset's settings inline, the sky regenerated at High quality on the
GUI thread for every sun change, and, on WARP, 40–85 s for each new light probe. Issue #385 row
L1.4: "look presets + auto with hysteresis, sky from the sun, animation policy. Key gates: light
= −sun vector; IoU ≥ 0.85 at 15°/35°/60°; night < ¼ luminance; fps table."

**Decision.**

1. **The look is data, Qt-free** (`core/scene3d/look.py`): `look_for(sun, preset) -> LookSpec` —
   plain, frozen, comparable — holds the mood (key-light colour and brightness, exposure, probe
   exposure, saturation, contrast), the sky's inputs (`SkySpec`), the shadow settings
   (`ShadowSpec`: the preset's map, cascades, filter and bias; the mood's darkness and blur), the
   fog, the flat fill and the plain sky (each in LINEAR light), and at night the moon's direction.
   The day rig is the spike's three anchors — noon at 30° and above, golden at 6°, low sun at
   0.5° — joined by continuous ramps (colours mixed in linear light, exposure in stops, the rest
   linearly); at `MIN_SUN_ELEVATION_DEG` (0.5°), the 2D shadow overlay's own threshold, the
   sun's key light goes; civil twilight down to `TWILIGHT_DEG` (−6°) fades the low-sun rig into
   the night rig (`twilight_rig`); night below.
   The values are the spike's, with their provenance, pinned against the spike's functions at
   every quarter degree until the spike retires. Two deliberate differences, each from a board:
   the night fog carries the night sky's energy (× 0.25), the night sky's ground hemisphere is
   drawn at that same energy (the spike: 0.15), and civil twilight is a ramp (the spike switched
   to night at 0.5°).
2. **Truth stays out of the look.** A day look has no direction in it (`moon_travel_scene` is
   None); a night look states its moon (azimuth 165°, elevation 38° — a look, not an ephemeris).
   The host aims the key light in ONE place (`Quick3DHost._apply_light`): the look's moon if it
   has one (twilight and night), else the sun the pipeline sent (light travel = −sun vector,
   `core/solar`), else none.
3. **A preset is cost, never mood.** `PRESET_SPECS`: low / medium / high / ultra differ in shadow
   map (VeryHigh / VeryHigh / VeryHigh / Ultra), cascades (1 / 1 / 2 / 3), PCF (4 / 8 / 16 / 32),
   bias (15 / 15 / 10 / 10), anti-aliasing (4x MSAA at low and medium, 4x at high, 8x at ultra),
   ambient occlusion and glow (medium up), screen-space reflections (ultra); no preset costs
   less than the one below it in any of these (pinned). Fog at every preset, no
   sharpening at any, SSGI at none. A preset change is ONE `set_look`: no camera, no geometry, no
   sky (pinned by the §8.10 test's sink log).
4. **The automatic preset** (the default, `auto`) is a Qt-free state machine, `AutoPreset`, fed
   with the host's count of PRESENTED frames (`health().frames_presented`, Qt's own frame
   signal), polled every 0.5 s and only while the wind animates — a view drawn on demand has no
   frame rate. It moves among low, medium and high (ultra only by choice): down when the median
   frame time of at least three samples over at least 3 s exceeds 1/27 s; up only when every
   sample is under 1/50 s, at least 10 s after the last change, and the level above is not
   barred; a level left for being slow is barred for 300 s, doubling up to 3,600 s. Ten seconds
   without a presented frame is NO DATA (the display asleep, a stall): what was collected is
   dropped and the preset holds. Where it settled and its bars (with their deadline in wall-clock
   seconds and the next bar's length) are stored (`view3d/auto_quality_level`,
   `view3d/auto_quality_bars`) and seed the next session; every session holds its level
   `hold_s` from its first poll before a first step up. Reduced motion freezes it (no animation,
   no frames). It measures PRESENTED frames under vsync: on a 30 Hz display or in a remote-desktop
   session it sits in the dead band or steps down for reasons that are not the GPU's.
5. **The sky follows the sun — when the sun moved noticeably.** `sky_is_stale`: a new sky when
   the sun stands 1° (great circle) or more from where the SHOWN sky draws it, at once on a
   change of the sky's phase (`sky_phase`: day, twilight, night — sunset, nightfall, dawn), one
   per degree through twilight, and never for the sun's position at night (a night sky draws no
   disc); the sky's sun is floored at −6°. A sky the engine cannot build is logged once and the
   session goes on with the plain sky; the look is sent separately and always. While the
   sun is dragged the sky is built once it has rested 300 ms (`SKY_SETTLE_MS`), and a sky
   that has been stale for 1 s is built at that pass whatever the timer says
   (`SKY_MAX_STALENESS_MS`): playback steps every 200 ms, so the old 150 ms timer fired
   between every two steps and a playing day rebuilt the atmosphere on almost every step
   (3.5 steps/s, #722); now the steps keep restarting the timer and the ceiling makes the
   sky follow the sun about once a second. Light, exposure and fog follow every instant;
   while the sky lags, the fog is computed for the sky ON SCREEN.
   Each build is a fresh `Texture` with its own `ProceduralSkyTextureData` as its child, every
   input set at the cheapest quality and Medium quality set last; the old pair is destroyed after
   the scene shows the new one (#476). `sunLongitude = azimuth + 90°`; the ground hemisphere takes
   the sky's horizon colour, curve 0.1 and the sky's energy. No sky before the first sun; no sky
   input bound live.
6. **One render mode on the software adapter: no sky, no wind, `auto` = low.** In compatibility
   mode (`LookController(software=True)`, the ONE parameter the workspace passes) no sky
   texture — and so no light probe — is ever created, nothing animates, and `auto` is `low`: a
   plain background in the fog's colour and a flat fill (the mean of the sky's top and horizon in
   linear light × probe exposure × the sky's energy × `FILL_OF_SKY` 0.5). The top-down truth view and the
   `--selftest` frame render the same; the self-test FAILS when its frame built a sky.
   `render_records(sky_light=True, prefer_software=True)` is refused.
7. **Colours derived in linear light reach the engine exactly.** The fog, the plain sky and the
   fill are handed over as `QColor.fromRgbF(engine_srgb(linear))`, the inverse of Qt Quick 3D's
   own polynomial linearisation of a colour property (PF-L3D-05 item 1).
8. **The animation policy.** The wind's clock (`windTime`, a `FrameAnimation`) runs only while
   the 3D pane is shown, reduced motion is off and the adapter is not a software one; hidden, it stops where it is (no tick);
   reduced motion RESTS it at 0 (`rest_wind`), so every vertex is drawn where its mesh puts it.
   The policy stops the clock rather than trust "hidden": the engine keeps a hidden window's
   animation running. Qt 6.11 exposes no operating-system "reduce motion" preference, so the
   setting `view3d/reduced_motion` (default off) is the application's own.
9. **Wiring.** One `LookController` per host (`ui/view3d/look_controller.py`, engine-free). The
   workspace hands it the sun the pipeline last sent (`Scene3DController.sync.sun`) after every
   pass, so the light and the look come from one moment and one solar path; a time-of-day change
   stays a light-only pass (no snapshot). Nothing in it takes a frame from the live host (ADR-060
   decision 17; a source scan pins it). The quality and reduced motion are a "3D View" group in
   Preferences, offered only where the window has a 3D workspace; "Save" re-reads them.
10. **A retired sky does not count towards the release policy for retired Models** (ADR-060
    decision 15): twenty sun changes, frames presented and withheld, leave no growth per change
    without a cache release (Evidence).
11. **The production Beauty Board** (`scripts/render_beauty_board.py`) replaces the spike as the
    board of record: the spike's shots, dates, times and cameras, through the production
    pipeline, one never-shown host per frame, with the truth rows in `metrics.json`
    (`ogp-lush-cinematic` §5). The spike's board remains the "before" until L1.10.

**Alternatives rejected.**

- *A sky per sun change (the spike).* Every step of a dragged time slider would hold the GUI
  thread for the generation (95 ms at Medium on the dev box's GPU, 215 ms at High) and, on WARP,
  for the probe's filtering (9–13 s on the dev box, 40–85 s on a CI runner).
- *Sky inputs bound live to the look.* One full generation per input change (the spike measured
  2,192 ms for a sun change that way against 344 ms set-then-raise).
- *High sky quality.* The same picture at 2.3× the GUI-thread time (round 3).
- *One Texture, a new data object per build.* A Texture loses its data when a data object it held
  earlier is destroyed (#476): a white or black sky after the second build.
- *The automatic preset from readback times.* A readback is a frame that is never presented and
  holds memory until a presented one ends (ADR-060 decision 17); on a sleeping display it never
  returns it.
- *The automatic preset from the frames of a still view.* A view drawn on demand presents nothing
  while nothing changes: "slow" for no reason.
- *Ultra as an automatic level.* It adds screen-space reflections and the largest shadow map for
  no gain in readability; a user may choose it.
- *The flat fill also beside a sky (L1.2's seam).* The sky is the fill; a second fill flattens the
  frame — the first spike renders read flat and blue for that reason. The fill now exists only
  where no sky texture lights the view.
- *The spike's night fog and night ground energy.* Each drew a line along the night horizon
  (PF-L3D-05 item 2).

**Consequences.**

- Truth and look are separable by construction: no look value can move a shadow, and a stale
  look aims nothing.
- The sky lags the sun by less than 1° and 0.3 s of rest, or at most 1 s while the sun keeps
  moving (`SKY_MAX_STALENESS_MS`); the light, the exposure and the fog
  never lag.
- On the dev box's display (60 Hz, vsync) every preset presents about 60 frames a second on both
  bench plans; what a frame COSTS is the readback number in the table below. An integrated GPU
  (the target the automatic preset's default `medium` is budgeted for) is unmeasured — the
  owner's manual check.
- The moon is fixed (a look); night shows no stars, no moon disc.
- Compatibility mode keeps the sun's direction, the shadows and the presets but has no sky
  picture and no light from the sky.

**Evidence** (RTX 4070, Direct3D 11, Windows 11; WARP = Direct3D's software adapter on the same
machine; 2026-10-19 unless stated).

| Gate | What | Measured |
|---|---|---|
| G1 | the light's rotation read back from the QML scene: (0, 0, −1) onto −sun, engine frame | 49 suns × 2 presets within 1e-5 (`TestKeyLight`); at night the moon's stated direction; through a scripted day on a real host, GPU and WARP |
| G2 | shadow IoU of a 100 × 100 × 200 cm box, azimuth 225°, PERSPECTIVE view with the preset's cascades, at 15° / 35° / 60° (gate ≥ 0.85) | bench_small board 960 × 540, GPU: low (1 cascade) 0.921 / 0.985 / 0.974, high (2) 0.976 / 0.986 / 0.978 (the L0 board of the same day, orthographic without cascades: 0.984 / 0.982 / 0.965 and 0.981 / 0.985 / 0.963). Render tier 640 × 360, all four presets: GPU low 0.919 / 0.968 / 0.962, medium 0.961 / 0.969 / 0.956, high 0.985 / 0.975 / 0.968, ultra 0.986 / 0.983 / 0.970; WARP (no sky, flat fill) low 0.919 / 0.971 / 0.964, medium 0.961 / 0.975 / 0.960, high 0.986 / 0.979 / 0.968, ultra 0.986 / 0.985 / 0.971 |
| G3 | night against noon, one camera and date, mean luminance in linear light (gate < 0.25) | 0.104 (low) / 0.093 (high) on bench_small, 0.098 / 0.088 on bench_large; the lower the sun, the darker the frame in every preset; ramp: no step between adjacent half degrees above the bounds of `test_scene3d_look.py` |
| G4 | the sky's sun disc read 25° off centre, sun in the east, south and west (gate < 6°) | max 0.07° (both bench plans); one sky per noticeable move and none below 1° (§8.10 test; on a real host 9 builds for the scripted day's 9 noticeable moves); the old sky released: twenty sun changes, committed memory per change over the second half (Theil–Sen; bound 1.0 MB, registered before the first run): 0.0 presenting, 0.125 with the frames withheld; dedicated GPU memory 0.008 / 0.0; positive control (no destroy) 8.2 MB per change; no cache release in the loop |
| G5 | fog against sky at eye height, per mood and preset: row-mean step / dip / ridge within 0.4° of the horizon (bounds 6.0 / 4.5 / 2.5 luma) | max 3.1 / 0.12 / 0.71 (bench_small and bench_large, low and high); speckle: isolated dark pixels at 640 × 360 medium: noon 194 (the far picket fence, the same with and without sharpening), December noon 2; the 0.08-sharpening control 315 / 150 (bounds 260 / 30, control at least +80) |
| G6 | auto preset on synthetic series; a preset change moves no camera and rebuilds nothing | `TestAutoPreset` (28 tests: slow, fast, noisy around each threshold, stalled, hitch, counter restart); the §8.10 test: a quality change is ONE `set_look`, zero sink calls, the camera pose object unchanged |
| G7 | hidden → no tick, reduced motion → no animation, at rest rendered = mesh | the controller tests; on the engine: rest, run, stop, stop again, rest again — the last frame equal to the first to the pixel; a hidden window's running clock advanced (why the policy stops it) |
| G8 | software adapter: no light probe; the self-test's wall time | 0 sky builds in every WARP frame; `--selftest` wall time (s, three alternating runs each, other test runs sharing the CPU): GPU base 10.00 / 6.72 / 5.80, head 6.29 / 6.43 / 4.83; WARP base 5.61 / 5.95 / 5.07, head 5.54 / 5.67 / 5.66 |
| G10 | the production board end to end | bench_small and bench_large, low and high, all seven shots: `status: ok`, 0 Qt errors and warnings, every `sun_date` = `build_date`, 0 build failures, `probe_restore_frame_diff` 0.0, `wind_time` 0.0 |

**G9 — the frame-rate table.** 1280 × 720, the golden-hour camera, the wind running, five seconds
per preset, frames PRESENTED to a 60 Hz display (vsync caps the GPU at 60); two runs on the GPU
(other agents' test runs were sharing the CPU), one on WARP. A readback's time (a new frame each,
`--fps-seconds`) is reported beside it in the board's `metrics.json`; on the GPU it is dominated
by the copy back and is not the frame's cost.

| Plan | Device | low | medium | high | ultra |
|---|---|---|---|---|---|
| bench_small (98 records) | RTX 4070 | 59.6 / 56.8 | 58.2 / 59.6 | 58.2 / 59.8 | 59.8 / 59.6 |
| bench_large (424 records) | RTX 4070 | 60.0 / 60.0 | 53.2 / 51.0 | 53.5 / 44.6 | 40.6 / 36.2 |
| bench_small | WARP | 22.6 | 14.2 | 9.6 | 4.7 |
| bench_large | WARP | 10.5 | 7.8 | 5.6 | 2.9 |

A first run under a heavier CPU load read bench_large 45.8 / 51.2 / 40.7 / 24.3: the frame rate
of the large plan on this machine is sensitive to CPU load (one 5-s window per preset). An
integrated GPU, the device `medium` is the automatic preset's start for, is unmeasured.

**Sky cost.** GUI-thread generation of one Medium sky: 95 ms against 215 ms at High in the round-3
A/B on a quiet machine; 123–301 ms (median 171–201) in the 2026-10-19 boards, a fresh host per
frame, the CPU shared. On WARP the first frame after a new sky took 11.1 / 13.2 / 12.3 s (the
probe's filtering; the generation 145–340 ms at High) — the reason for decision 6.

**Look-dev log** (bench_small, 960 × 540, `low` and `high`; boards in the story's scratch):
round 1 — the night fog carries the sky's energy and reaches the engine in linear light: night
horizon step 10.5 / 21.2 → 2.4 / 3.2; round 2 — bias 10 at high and ultra: a grazed lit wall's
hatch 1.15 % → 0.18 % of its luma, IoU unchanged; round 3 — Medium sky: same picture (mean luma
within 0.02, disc within 0.07°), 215 → 95 ms; round 4 — no change: the merged tree against the
L0 board of the same day (like for like: shots, dates, cameras, size); round 5 — the night ground
hemisphere at the sky's energy: night dip 2.07 / 1.04 → 0.01 / 0.12.

Tests: `tests/unit/test_scene3d_look.py`, `test_view3d_look_settings.py`, `test_board_probes.py`,
`test_render_beauty_board.py`, `test_quick3d_pure.py`; `tests/ui/test_quick3d_host.py`
(`TestKeyLight`, `TestSky`, `TestWind`); `tests/integration/test_view3d_look_controller.py`,
`test_view3d_looks.py` (§8.10); on a real device `tests/integration/test_view3d_looks_render.py`
with `view3d_looks_driver.py` (§8.10.11).

**Fix round 1** (2026-10-19, after the two reviews; numbers on the dev box, bench_small at
960 × 540 unless named).

- *Code review P0 — the wind ran in compatibility mode* (1,351 % of one core on WARP, 139 frames
  in 4 s; still: 1 frame, 18 %). The controller decided the sky by the render mode and the wind
  and the automatic preset by visibility alone. Now ONE parameter (`software`) decides all three
  (decision 6). Pinned: `test_a_software_adapter_never_animates_and_auto_is_low` (3 qualities),
  the §8.10 test's compatibility case, the render tier's `[software]` controller day (no wind).
- *P1 — a failing sky stopped every later look* (20 suns: 0 looks, 20 sky attempts, 20 ERROR
  lines). The sky has its own `try`; one error, the plain sky for the session, every look sent
  (20 looks, 2 sky calls, 1 error: `test_a_sky_that_cannot_be_built_never_keeps_the_look_…`).
- *P1 — the automatic preset forgot its bars* ("high too slow, medium fine" flipped once per
  session). Stored with their deadline and next length, seeded at the first poll; the first step
  up waits `hold_s` (`test_a_level_that_was_too_slow_stays_barred_in_the_next_session`: a session
  a minute later does not step; after the deadline one retry, and the next bar doubles).
- *P1 — Preferences → apply was untested.* The §8.10 test now drives `window._on_preferences()`
  with the dialog's `exec` patched; deleting the window's call fails 2 tests.
- *Look P1 — night was a switch at 0.5°* (luma 77 → 37 within 90 s of plan time; −0.5° … −6°
  all full night). The twilight ramp (decision 1), as the review's recipe: colours in linear
  light. Mixed in STOPS instead, the sky was smoother but the frame went darker than the night it
  ends in, then brighter (dusk sweep, low: 0.116 at 0.6° → 0.023 at −3°/−4° → 0.034 at −6°);
  linearly it darkens all the way — 0.116 → 0.105 (0.4°) → 0.099 (0°) → 0.052 (−3°) → 0.034
  (−6°) — and sunset's step (0.011) is under the largest half degree of the day ramp (0.027),
  low and high. In parameters the sky horizon moves at most 52 sRGB codes per half degree (its
  last, where the moon carries the frame's light) and the exposure 0.072 stops.
- *Look P1 — picket moiré at low* (the look review's P1). The review named 2x MSAA; measured, 2x
  does not resolve the pickets: the fences' luma error against a 2x-supersampled render FXAA
  20.0, 2x 12.0, 4x 6.2 (medium 7.2), and 2x's dark-pixel share 18.8 % is worse than FXAA's
  12.7 % (4x 13.1 %; medium 12.3 %). Low takes 4x (decision 3). Cost on the RTX 4070
  (bench_large, 1280 × 720, a new frame's readback; the display asleep, so no presented frames):
  FXAA 23–28, 2x 23–30, 4x 24–32 ms — inside the run-to-run spread; on WARP under a shared CPU
  FXAA 67–152, 2x 96–147, 4x 107–199 ms. An integrated GPU is unmeasured; the owner kept 4× at Low
  without that measurement (2026-10-19, ADR-060 addendum D5).
- *Look P2s.* The flat fill × 0.5 (compatibility mode read +22 luma over the GPU's sky-lit frame);
  the plan ground takes the meadow's material (roughness 1.0, specular 0.15): its step along the
  plan's edges ≤ 0.21 luma in every view, the old material up to 4.65 (the instrument fits both
  sides at the edge line — two band means read the view's gradient as a step); medium takes the
  2048 map: +4 % of a WARP frame on bench_large (183 → 191 ms), nothing measurable on the GPU;
  the horizon's CIE76 hue difference is reported (not gated; the noon ΔE ~60 is the lime band
  the owner kept on 2026-10-19, ADR-060 addendum D5); the board's date row is read back from the records rendered, the shot's day is the
  plan's local day (ADR-053), and a per-date digest of (item, height) must differ between June
  and December.
- *Recorded.* A soak of the default steady state (shown, wind running; the workspace soaks run
  with reduced motion): committed memory +2.6 MB per minute over 2 minutes, +2.09 over 6
  (linear, 21,594 frames, dedicated GPU memory flat; 0.81 with the QML engine's collector every
  5 s) — over the 2.0 registered before the first run: OPEN (FU-L14-2), kept as a strict `xfail`.
  *(L1.9, 2026-10-19: not reproduced — six alternating soaks, 0.46–2.03 MB a minute, the
  planned NumberAnimation clock no different; the xfail is removed and the gate stands at its
  bound — ADR-060 addendum "the default and the removal".)*
  The looks' render gates are not in CI's render job; L1.9 decides, with L1.8's selection file.

## ADR-059 addendum: low-sun shadows — a still frame's map fitted to the casters, pickets without a ramp (#734)

**Context.** At golden hour the family garden's outer fence threw a long shadow onto the meadow
whose edge showed coarse stair steps; at the 5.9° sunset the meadow behind it was strewn with
bright streaks; both reached promotional 4K pictures and the first frames of a time-lapse. The
issue asked which shadow setting decides it. Measured one variable at a time (`ogp-3d-renderer`
§23, `ogp-lush-cinematic` reference 13, the board's new `--stairs` probe): two mechanisms.

1. **The builder.** The L0 picket fence lowered each picket by `index * 7919 % 13 / 13 × 4` cm.
   `7919 mod 13 = 2`: a ramp of seven pickets climbing 0.6 cm, then a drop, every 13. A low
   sun turns each centimetre into `1 / tan(elevation)` of shadow (3.7 at 15°), so the fence's
   long shadow carried a regular staircase whatever the map — a 4096 map, a tighter reach
   and a 32-bit map left it pixel for pixel. Every picket fence of every plan was the same.
   This was the issue's staircase.
2. **The cascade fit.** `lockShadowmapTexels: true` sizes each cascade by the bounding sphere of
   its whole frustum slice (Qt 6.12's `setupCascadingCamerasForShadowMap`): with
   `shadowMapFar` ≥ 9000 cm, High's last cascade spans about 170 m on 2048 texels — 8.3 cm. A
   long edge 20–40 m out stepped, the foot of every caster showed lit teeth one texel tall in
   light space (`texel / sin(elevation)` long on the ground: the ground does not cast), and
   the 0.5 cm slits an oblique sun leaves between 2.2 cm thick pickets aliased into streaks.
   `pcfFactor` is a radius in scene units (2 cm by day) for every cascade; it cannot hide a
   larger texel. Unlocked, Qt spans each cascade by the casters' box clipped to the slice —
   about 1 cm texels on a 24 m plan — but that box moves with the camera: through the
   product's capture path, orbiting the family garden 0.5° a frame, the fence's edge crawled
   0.69 / 0.38 px a frame 0–10 / 10–20 m out (averaged over 30 cm) against 0.16 / 0.17 locked.
   A single cascade crawled as far (0.32 / 0.39): the hero view never holds the whole plan.

**Decision.**

1. **A frame whose camera does not move fits the shadow map to the casters; a moving camera
   keeps the locked fit.** `Garden.qml`: `lockShadowmapTexels: root.topDown ||
   !root.fittedShadows`. `Quick3DHost.capture(..., fitted_shadows=False)`: the default is the
   view's fit, so a capture that does not ask is the view to the level — the self-test's check,
   which a fitted default failed on the renderer by 24 levels. The still pictures ask by name:
   `WorkspaceCaptureCoordinator.write_photo`, `agent_picture` and the frames of a `HeldCamera`
   tour (a time-lapse: the light turns under either fit, and the fitted grid crawls less —
   measured below). An orbit, a flight and the live view keep the locked fit. The flag holds
   for the capture's own frame and is put back in its `finally`, like its AO scale (a capture's
   frame is never presented). `set_fitted_shadows` is the host's call for it;
   `render_records(fitted_shadows=)` and the board's `--photo-shadows` render a picture's fit.
   The orthographic truth view stays locked. `shadowMapFar`, the splits, the maps, the filters
   and the bias are unchanged.
2. **Each picket stops its own 0.5–1.5 cm under the posts** (`fences.PICKET_DROP_CM`), drawn
   by a hash of the item's seed (`unit_hash`, `picket_seed`): the posts stay proud, no two
   neighbours level, no period, no two fences alike. The fence's height (the posts) is the
   plan's; nothing in the data moved. It holds in every frame, the view's included.

**Measured** (RTX 4070, Direct3D 11, `--stairs` on bench_small at 1920 × 1080; the panel's edge
20–40 m out in the default framing, spread across it; the foot: the lit share of a line 15 cm
out from the panel's shaded face at 5.9°; streaks: the picket fence's 5.9° shadow,
one-pitch-filtered, over the shadow's contrast, the worse of two cameras):

| Setting (High, one at a time) | edge 15.2° | edge 5.9° | foot | streaks | cost / catch |
|---|---|---|---|---|---|
| locked, ≥ 9000 cm (the view, as before) | 5 cm / 2.24 px | 11 cm / 6.23 px | 0.339 | 0.49 | — |
| reach without the 9000 cm floor | 3 cm / 1.68 px | 9 cm / 5.70 px | — | — | the golden-hour camera's 10–20 m band worse (1.08 → 2.04 px) |
| `pcfFactor` 4 / 6 | 4 / 4 cm | 5 / 3 cm | — | smeared into bands | every contact softer |
| 4096 map | 2 cm / 0.99 px | 3 cm / 1.70 px | — | 0.29 | 4 × the shadow passes' texels |
| `csmSplit2` 0.45 | 3 cm | 5 cm | — | 0.76 | worse near (2.19 px at 10–20 m) |
| **fitted to the casters (a still frame)** | **1 cm / 0.32 px** | **2 cm / 1.40 px** | **0.011** | **0.12** | no measurable frame cost (below); crawls with a moving camera |

Ultra locked 1 / 2 cm, foot 0.011, streaks 0.30; fitted 1 / 2 cm, 0.011, 0.10. Low and medium
fitted: 1 / 2 cm, 0.009–0.011, 0.13–0.21. What is left at 5.9° is Qt's per-pixel PCF dither,
not texels. The final design in the render gate (2026-11-10, High / Ultra, every frame a still
picture's fit): the panel's far edge 0.64 / 0.63 cm at 15.2° and 2.24 / 2.27 cm at 5.9°, the
foot lit 0.023 at worst, streaks 0.165 / 0.136 at worst. The `--stairs` orbit (the golden-hour
camera round the plan, the panel and a 10 m column at each plan corner, 0.5° a frame, averaged
over 30 cm): locked 0.079 / 0.094 px at 0–10 / 10–20 m (Ultra 0.082 / 0.087), fitted 0.21 /
0.146 (Ultra 0.106 / 0.117). The `--stairs` time-lapse (the same scene, that camera held, the
sun stepping 0.4° / 0.55° a frame, each frame against its own sun's edge): 8 frames from 15.2° to 12.4°, locked 0.336 / 0.682 px at 0–10 / 10–20 m (Ultra 0.175 / 0.321), fitted 0.265 / 0.517 (Ultra 0.167 / 0.298); 24
frames from golden hour to sunset in the same scene: locked 0.66 / 0.79 px, fitted 0.35 /
0.37. The picket fence's golden-hour edge in the hero camera, 0–10 m: 6.65 px (the ramp) →
4.59 px (the posts' bumps, 0.5–1.5 cm proud; level pickets 2 cm under read 5.39). In a fitted
frame the far tree shadows show Qt's dither (high-pass spread in their penumbra 1.79 → 2.14
luma at 4K; the near shadows' 6.01 → 6.03). The picket fence against its 2D caster model
(`scripts/measure_built_world_shadows.py`): area ratio 1.01 / 1.01 / 1.00, IoU 0.66 / 0.67 /
0.68, tip +2.0 / +2.0 / +2.4 cm (before 1.00 / 1.00 / 1.00, 0.65 / 0.66 / 0.68, the same tips).
The family garden's board on the view's path against the base (High, 1920 × 1080, seven
shots): 0.03–0.12 levels mean, at most 0.27 % of pixels more than 8 apart (the fences' tops),
luma, clipping and dark-pixel counts unchanged; on the photo's path against the view's: 0.2–2.1
levels mean, 0.01–7.9 % of pixels (December noon's long shadows and the lawn blades' own).

**Cost.** Fitting changes which texels a cascade covers, not how many passes or pages there
are. Captures of the family garden at golden hour, fitted and locked strictly alternating in
one process, two warm-ups, the minimum of 12 each (the GPU was shared with two other renders,
which only add time): 1920 × 1080 fitted − locked −0.7 ms (low, 17.8 ms locked), +2.3 (medium,
21.0), −0.6 (high, 25.3), +2.1 (ultra, 40.3); 3840 × 2160 on High +2.9 ms minimum, +0.7 ms
median (54.2 / 57.0 against 51.3 / 56.3 ms, 12 pairs). No cost beyond that noise; the live
view's frames are the base's (it keeps the locked fit). The board's `--fps-seconds` readback
A/B swung 3 × between rounds under the shared GPU and decided nothing.

**Truth gates.** The view's fit is the base's: its shadow IoU in perspective with each preset's
cascades (640 × 360) stays low 0.919 / 0.967 / 0.962, medium 0.919 / 0.969 / 0.958, high
0.985 / 0.968 / 0.962, ultra 0.986 / 0.970 / 0.965 at 15° / 35° / 60° (gate 0.85). In a
picture's fit: low 0.985 / 0.975 / 0.970, medium 0.985 / 0.975 / 0.961, high 0.986 / 0.980 /
0.967, ultra 0.986 / 0.981 / 0.968; far plan (bench_large, 2× / 4× framing, High) 3,768 /
3,761 shadowed samples against 3,512 / 3,420, the outer row step 0.77 / 1.55 either way (gate 3.0).

**Consequences.** A picture's shadows are sharper than the view's at a low sun, the photo-mode
preview's included: ADR-072 decision 5's "all off is the view" holds for a capture that does
not ask (amended there). A recording that moves its camera shows the view's shadows. A fitted
map's texels depend on the plan's extent (a 50 m plan about 2.5 cm), not on the camera's
distance. Open: the live view at rest could take the fitted map too, at the cost of a visible
sharpening when the camera stops — a taste question for the owner (follow-up). The render
tier's `test_a_long_low_sun_shadow_has_no_stairs_no_lit_teeth_and_no_streaks` gates a
picture's fit, the view's orbit and the measured reasons for the routing (observed failing on
the base: 4.97 cm against 2.5 at High, 15.2°); the builder pin
`test_picket_tops_repeat_no_pattern_and_follow_the_items_seed` gates the ramp and the clones;
`test_directors_cut.py::test_a_still_camera_fits_its_shadows_and_a_moving_one_keeps_the_views`
the routing; `test_directors_cut_render.py::test_a_still_pictures_fitted_shadows_change_only_its_own_frame`
and the self-test that a fitted capture changes only its own frame and a default one is the
view. PF-L3D-24, PF-L3D-25.

## ADR-059 addendum: a recorded frame's own sky and the twilight fill (#799, #802)

**Status**: Accepted (2026-11-10, visual-polish package; the owner decided #802's direction:
"build the ground-only twilight fill; the night rig and the sunset shot stay"). Amends
decisions 1 and 5 of the L1.4 addendum above.

**Context.** Two faults of a day time-lapse, both found by the 3D promo-readiness survey and
re-measured on the family garden's default view (Berlin, 21 June, high, 640 × 360):

- *#799, flicker.* A 10 s, 30 fps lapse of 04:00–23:00 moves the sun 0.5–0.7° a frame. The
  tour's `settle_sky` used decision 5's 1° rule, so the sky texture, its light probe and the fog
  that follows the shown sky's horizon changed on alternate frames while the key light and the
  exposure changed every frame: the sky band's zigzag RMS was 3.86 luma at dawn (max 7.3),
  1.73 at dusk, 0.07 by day.
- *#802, a brighter night.* The garden's own light ROSE after sunset (ground luminance 0.0196 at
  a 0.5° sun, 0.0188 at −1°, 0.0379 at night) while the board's `--dusk` gate, which reads the
  whole frame (mostly sky), passed. The survey blamed the twilight ramp's linear moon and
  exposure. The cause is the anchors: the night rig is "day for night" (moon 0.32 at 38°,
  exposure 2.4) and lights flat ground about 0.95 EV above what a 0.5° sun's sky gives
  (probe 0.42, exposure 1.25; the 0.5° anchor is frozen against the L0 spike). With both
  anchors fixed no ramp between them can fall monotonically. A square-root moon ramp (the
  survey's proposal) only moves the rise earlier; a moon already on at sunset is a step up;
  more exposure or probe at the low sun brightens the sunset sky above the 6° sky; a darker
  night breaks the night rig the owner accepted.

**Decision.**

1. **A recorded frame gets the sky of its own sun exactly.** `sky_is_stale(shown, wanted,
   threshold_deg)` with a threshold of 0 or less rebuilds whenever the wanted sky differs from
   the shown one (`RECORDING_SKY_REBUILD_DEG` = 0); the same sky is never rebuilt and the night
   sky still never follows the sun's position. `LookController.settle_sky` — called only by a
   tour's frame (`workspace_capture._tour_settled`) — asks for it; the live settle timer and the
   1 s ceiling keep decision 5's 1°. A finer threshold is no cheaper: at dawn a 1° lag moved the
   band 10–16 luma, so an alternation under 0.3 luma needs a lag under about 0.03°.
2. **The twilight fill.** `LookSpec.twilight_fill_linear` is a flat ambient in the colour of the
   sky's top (what the probe gives the ground). `Garden.qml`'s existing fill light carries it
   where a sky lights the view (`ambientColor: view.skyShown ? root.twilightFill :
   root.fillColor`), so it lights the garden and never the skybox, adds no light count, no shadow
   and no direction; the compatibility mode and the top-down truth view keep their flat fill
   without it. It lifts a MODEL of the light on open ground (`look.ground_light`: the key at its
   height, the probe as 1.15 × probe exposure × sky energy × the sky top's luminance, an ambient
   at 1.2 × itself, all read as the meadow's albedo reflects them, × exposure) to a target in
   units of the SAME weather's night light (`look.twilight_fill`, the weather's anchors cached
   per `WeatherSpec`): in twilight a line through 1.07 at sunset, 1.05 at −3° and 1 at −6°; by
   day the sunset level plus 40 % of how far the look's own light lies above the weather's
   sunset light, so the ground keeps 40 % of its own fall. Black from 6° up and at night: the
   board's sunset shot (5.89°; the clear fill begins at about 5.65°) and the night keep the
   rig's own light. An overcast, rain and snow need none (their own light stays above their
   darker night). Unlit particles take the fill into their light.
3. **The garden's light is a gate.** The board's `--dusk` records `ground_luminance` (the rows
   below the horizon) per row: `ground_monotone` joins `monotone`, by the same noise rule
   (0.2 % + 1e-5), on both skies and in every weather of `--living`. The clear evening is also
   rendered from the view's own default framing for the first preset (`default_monotone`) —
   once per board, so `--living` stays inside its render-tier timeout. The board's presets
   after the first had been rendered from the set-sun probe's sky camera (the loop rebound
   `camera`); each now takes the golden-hour camera, as documented.

**Alternatives rejected.** For #799: interpolating two built skies (Qt cannot blend two light
probes) and a finer threshold (decision 1). For #802: the levers in the context; a fill shaped
like the moon (a second directional light from the night rig's moon): composition-proof in
twilight, but with the probe's 0.58 of the night still present at sunset it puts the sunset
ground above the 5.89° anchor; and a flat fill target near the night level (the first
prototype), which held the default framing but brightened the golden-hour camera 14 % from 4°
to 1°: that camera's vertical faces take 1.12 × the modelled lift while its fogged rows fall
only 0.8 × as fast, so the fill may make up only part of the day's own fall.

**Consequences.**

- A recorded lapse builds a sky per frame in twilight and by day: 147 → 291 builds and 158 →
  198 s of wall time for the 300-frame lapse (sky build median 139 ms). Flights build none.
- The garden at sunset and through twilight is brighter than before (default framing at 0.5°:
  0.0196 → 0.0421, 2.1 × — the ground now stands a little above the night it ends in) and the
  evening reads as a blue hour; the sky is unchanged. The owner has not judged this look yet.
- The fill is open-loop: the model fits the family garden's default framing; a view that is
  mostly open meadow takes less lift (balcony, raised bed: up to 1.2 % rise a step in twilight;
  before up to 140 %), and a view whose night outshines its own 6° frame (the balcony from the
  board's golden-hour camera: 0.0371 against 0.0316) cannot be monotone while both anchors
  stay. PF-L3D-29.
- The board's `--dusk` renders 16 more frames (the default framing, once): about 70 s at the
  4.4 s a frame measured with other agents on the GPU. Under that load the looks render tier's
  full board (`test_view3d_looks_render.py`, watchdog 780 s) reached its watchdog in the `high`
  dusk run; by its own timeline it would have needed about 820 s without these frames too.

**Evidence** (RTX 4070, Direct3D 11; family garden unless named; 640 × 360, high, painted).

| What | Before | After |
|---|---|---|
| #799 300-frame lapse: sky-band zigzag RMS dawn / dusk (luma) | 3.863 / 1.728 | 0.794 / 0.285 |
| #799 alternation, sky band, dawn / dusk (third difference / 8, outside the rig's corners) | 1.855 / 0.848 | 0.084 / 0.041 |
| #799 render tier, 42-frame dawn / dusk lapses: sky builds; alternation (sky band, frame) | 18 / 19 builds; 1.74, 0.80 / 0.89, 0.66 | 34 / 36 (every twilight and day frame); 0.04–0.07 |
| #802 ground at sunset → an hour later, lapse frame mean (luma) | 37.2 → 51.5 (+38 %) | 53.6 → 51.8 (−3 %) |
| #802 sweeps with a rise beyond noise: family default / golden, dusk + dawn | 16 / 11 | 0 / 0 |
| … December, 60° N, atmosphere sky, partly cloudy, bench_small, food forest (four series each) | 19–30 per run | 0 |
| … overcast | 0 (no fill: 108 frames pixel-identical) | 0 |
| … balcony default, raised bed default | 26, 23 | 17, 5 (worst −1.21 %, −0.52 % a step) |
| #802 board `--dusk`, bench_small high: ground monotone, golden / default | no / no | yes / yes |
| #802 board `--dusk`, all four presets, painted and atmosphere: frame, ground and (low) default monotone | — | yes on all 8 (sunset step 0.0053–0.0075 ≤ day ramp 0.0184–0.0201; 0 Qt errors) |
| #802 living board (medium), both skies: ground monotone under partly cloudy, overcast, rain, snow, clear | — | yes on all 10; render-tier test 2 passed |
| #802 board: sunset step against the largest day-ramp step | 0.0066 ≤ 0.0293 | 0.0053 ≤ 0.0199 |
| #802 night and 6° frames, sweeps and board | — | pixel-identical (max difference 0) |

Tests: `tests/unit/test_scene3d_look.py` (`TestSkyStaleness`, `TestTheTwilightFill`),
`tests/integration/test_view3d_look_controller.py`
(`test_a_recorded_frame_builds_the_sky_of_its_own_sun`), `tests/unit/test_quick3d_qml.py`; render
tier `tests/integration/test_directors_cut_render.py::test_a_day_lapse_does_not_flicker_at_dawn_or_dusk`
(the `daylapse` scenario), `test_view3d_looks_render.py::test_dusk_fades_and_sunset_is_no_cliff`,
`test_living_garden_render.py::test_the_living_board_renders_every_shot`. Pitfalls PF-L3D-28,
PF-L3D-29.

## ADR-059 addendum: the wind that shows, and the leaves' stripes (#800, #805)

**Status**: Accepted (2026-11-10, visual-polish package). Amends decision 6 of the L1.4 addendum
(the wind) and the #687 addendum's "clear keeps 55 / 14 / 0". The amplitude share, the AO floor's
effect on every clear frame and the leaf size are open to the owner (below).

**Context.** The 3D promo-readiness survey found two foliage faults that a camera tour shows at
once. *#800*: with the camera held for 2 s on the family garden's 9.5 m birch about 11 m out the
crown did not move. Measured (960 × 540, 4 s, the tour's clock): 0.03 px of sway; a 60 cm basil
3 m out moved more (0.32 px). `foliage.vert` moved every leaf by `windStrength × 0.35` = 0.875 cm
times its height fraction squared — the same for every plant — and took the phase from `0.011 ×`
the vertex's world x, 13 rad across a 12 m crown, so a crown rippled in place; the wood (a
PrincipledMaterial) did not move at all. *#805*: diagonal stripes 2–4 px apart across backlit
leaves at golden hour on High and Ultra, which the survey called shadow acne from the back-light
term at shadow bias 10.

**Decision.**

1. **A plant sways by its own size, as one** (`core/scene3d/wind.py`, the numpy statement of
   the shaders' `plantSway`, one text in `foliage.vert`, `foliage_door.vert` and
   `plant_sway.vert`, pinned to each other and to the module's numbers). In the engine frame,
   item-local: the amplitude at the top is `SWAY_SHARE` = 0.5 % of the plant's height under a
   clear day's wind, linear in the look's strength (`windSway` = downwind × strength / 2.5:
   calm still, rain × 2, snow × 0.6); a cantilever (`(y/h)²`: the foot stays where the plan
   puts it); the whole plant leans downwind (0.35 of the swing) and swings at
   `1.2 Hz / √(h / 1 m)` within 0.25–2.5 Hz, spread ±10 % by its phase, with a figure-of-eight
   across the wind at 0.71 of that; a branch term (0.45 of the amplitude at the outer top, a
   field smooth in space, so a twig and its leaves move together); a leaf flutter along its
   normal (0.25, 2–5.1 Hz — at least six frames a cycle at 30 fps); a gust (14 s, ±35 %)
   travelling downwind across the garden. Every frequency is a whole number of cycles an hour,
   so the clock's 3602 → 2 s wrap is seamless. At clock 0 every term is 0 (the rest ramp).
2. **Every part of an item with leaves takes the same frame.** `wind.sway_frame` gives an item
   with a `foliage` part its height (the top of its meshes — fitted to the data, so the data's),
   its reach and its phase (from its item id, never from its position); the adapter hands it
   on in `PartSpec.sway`, the host sets `swayFrame` on the foliage and vc Models. A plant's
   wood and fruit draw through `plant_sway.vert` + `built_snow.frag` (snow on bare branches
   included) **only while the clock runs** — `materials: … swayFrame.x > 0.0 && root.windBlowing ? [vcSway] : …`, a bool that
   changes only when the wind starts or rests (a binding on `windTime` itself would reassign
   every plant part's materials on every frame) — so every frame at rest is the principled
   look; the swap measured invisible. No vertex attribute was added; the frame is a uniform per Model. The lawn's blades
   keep their own wind (`windStrength`). The particles drift from the same direction
   (`wind.WIND_FROM_DEG`, moved from `weather.py`).
3. **The stripes are ambient occlusion, and the fix is its bias.** The stripes did not change
   with the shadow bias (10 / 14 / 20 / 40 cm) or with a still picture's fitted map and vanished
   with AO off; Low (no AO) never had them. Qt's SSAO takes a camera-facing normal, so a FLAT
   micro-leaf seen at a slant occludes itself in bands — #687's flat-ground self-occlusion on
   every leaf. `look.AO_FLAT_BIAS_CM` = 1 cm is the floor of every look's AO bias (a weather's
   own, 21 cm × its light share, stays where larger). The shadow bias, maps, cascades and IoU
   are untouched.

**Alternatives rejected.** The issue's shadow bias 10 → 14 (measured: no change); a normal-offset
of the leaf's shadow lookup and leaving the back-light share out of the self-shadow test (the
stripes are not in the shadow term); AO dither (bands became noise, 0.545); AO softness 90
(0.212, every contact softer); AO bias 2 cm (stripes 0.175, but a box caster's lit-side contact
halved, 0.0223 → 0.0086). For the wind: an attribute per vertex for the branch weight (the
position and the frame give it at no memory cost); a phase from the plant's position (the
id's phase is the same on every machine and in every pass); swaying only the leaves (they slid
over still twigs; the wood takes the same function).

**Consequences.**

- A tour, a held shot and the live view show the garden moving: the birch's upper crown sways
  about 1.4 px of a 1080-row picture at 11 m (the top leaves several px), slowly; a shrub
  less, a herb barely. Taste: whether 0.5 % reads strong enough on the owner's screen is the
  owner's to judge from the clips (the share is one constant).
- Every clear frame from Medium up is a little brighter on open flat ground (its self-occlusion
  16.9 → 11.4 levels at High) and in crowns (8 levels on a backlit crown) — what #687 left
  open ("whether clear gets the AO bias too"), decided here by the leaves; the owner may veto.
- X-ray: a faded plant's leaves sway (their screen door is the same shader), its wood not
  (`screen.vert` has no sway) — a small mismatch in an analysis view, left as is.
- A tour's first windy frame compiles nothing new (the shader warmer draws `plant_sway.vert`).
- The foliage render tier (`test_view3d_foliage_render.py`) is not in CI's `render3d` file list
  (a 3 s sequence on llvmpipe would take minutes); CI compiles both new shader paths through
  `test_quick3d_render.py` (the broken-shader controls and the rest controls).

**Evidence** (RTX 4070, Direct3D 11, family garden, painted sky; probes in the story's scratch,
the tier in the test).

| What | Before | After |
|---|---|---|
| Birch 9.5 m at 11 m: upper crown's downwind sway, half a swing (960 × 540, 30 / 60 fps) | 0.03 / 0.03 px | 0.86 / 0.86 px (1.7 px of a 1080-row picture) |
| … its period (zero crossings; rule 1 / 0.389 Hz ± 10 %) | — | 2.67 s |
| Lilac 1.74 m at 5 m / basil 0.6 m at 3 m: sway | 0.017 / 0.32 px | 0.78 / 0.38 px, periods 1.11 / 0.65 s |
| Render tier (640 × 360, 3 s): birch / lilac / basil, px of a 1080-row picture; cm | — | 1.43 / 1.58 / 0.84 px; 1.30 / 0.54 / 0.19 cm |
| Largest step a frame, 30 / 60 fps (960 × 540): birch, lilac, basil | — | 0.12 / 0.06, 0.19 / 0.10, 0.15 / 0.08 px |
| Motion above a third of the frame rate; zigzags on the downwind track | — | ≤ 0.2 % of the energy; 0 |
| Frame i at 30 fps against frame 2i at 60 fps; the same index twice | — | identical; 0 levels |
| Wind clock 0, three cameras (960 × 540), base against after | — | max difference 0 |
| The wood's swaying shader at zero amplitude against the principled look (1080p, four presets) | — | 0 levels (one pixel 1 level, Medium) |
| Shadow follows the crown (wind × 20): ground px changed, look / shadow pass without sway | — | 5,777 / 7,015 against 872 / 1,661 |
| Stripes inside the cherry's crown, golden hour, High, 1080p: look / AO off / AO bias 0 | 0.326 / 0.164 / — | 0.184 |
| Stripes, whole crop, High / Ultra at golden hour and sunset, locked and fitted | 0.127–0.177 | 0.093–0.126 (Low 0.089–0.134, unchanged) |
| Render tier (1280 × 720): look / AO off / bias 0, High and Ultra | — | 0.202 / 0.172 / 0.301, 0.195 / 0.172 / 0.302 |
| Clear AO on bench_small (1280 × 720, High): rim, far self-occlusion, open-ground darkening | 7.57, 12.5, 16.86 | 6.72, 9.93, 11.36 |
| … a box caster's contact, lit foot / shaded side | 0.0223 / 0.487 | 0.0214 / 0.478 |
| Frame cost 1080p with the wind running, minimum of 12 (then 16) captures strictly alternating in one process, the GPU shared with other renders: low / medium / high / ultra | 24.5 / 28.3 / 28.4 / 47.7 ms (20.3 / 26.6 / 38.4 / 52.6) | 26.2 / 28.4 / 30.8 / 49.7 ms (22.5 / 28.3 / 33.6 / 56.6): +0.1 to +4.0 ms, high once −4.8 — inside the run-to-run spread |
| Vertex data, family garden (the largest example, LOD0): 598,582 vertices × 48 B | 28.73 MB | 28.73 MB (+16 B of uniform per Model) |

**Open for the owner.** (1) The leaf size: at L0 the owner kept small-leaved crowns as they
are; the forge's LOD0 leaves are large because the coverage rule meets the crown's area with
few leaves (birch 1,857 leaves, median 42 cm long, 3,714 of its 25,000 triangles; cherry 2,507
at 31 cm) — halving the length at LOD0 would cost about four times the leaf triangles (still
inside the budget), lobed leaf meshes near the camera are the bigger step; kept as built. No
leaf lies isolated (nearest neighbour over two leaf lengths: 0 of 1,857–2,838) and at most
0.2 % touch the reach clamp, so "loose quads outside the silhouette" are the outer leaves of
that size, not strays. (2) The sway share 0.5 %. (3) The AO floor on clear frames.

Tests: `tests/unit/test_scene3d_wind.py`, `test_quick3d_adapter.py`
(`test_an_item_with_leaves_sways_as_a_whole_and_a_built_one_not_at_all`), `test_quick3d_qml.py`
(`test_a_plant_sways_as_one_by_its_own_frame_and_the_lawn_keeps_its_wind`), `test_scene3d_weather.py`;
render tier `test_view3d_foliage_render.py` (sway, smoothness and determinism, rest and the
wood's swap, the shadow with its control, the stripes with their control) and
`test_quick3d_render.py` (the rest control and a broken-shader control for `plant_sway.vert`). On
the base shaders the sway gate and the smoothness gate fail; the stripe gate's control (the bias
at 0) fails it. PF-L3D-32, PF-L3D-33.

## ADR-059 addendum: what built parts are made of — surfaces, roof tiles and wall pictures (#801, #803)

**Status**: Accepted (2026-11-10, visual-polish package; the surface values, the wall pictures and
the gate's definition are the creator's and open to the owner — see Consequences). Amends the
L1.6 builders addendum (one look for every vertex-coloured part) and ADR-065's roof and wall
materials.

**Context.** The 3D promo-readiness survey: every built part reflected with ONE roughness (0.78)
and specular amount (0.35), so the family garden's black trampoline mat (#303336) read tan facing
a golden-hour sun (luma 99, hue 23°) and its blue pad 32° off; the pond's morning glint was a
clipped white blob; the roofs were flat plates (noon luma std 0.57 against the 2D roof's 20.2)
and walls slabs (the balcony's wall a navy slab, luma 32, std 1.7). Measured here before deciding:

- Qt's `PrincipledMaterial` switches specular OFF at an amount of 0.01 or less, and above it the
  amount hardly scales a grazing highlight: the black mat facing a 15.2° sun read luma 25.4 at
  0.01, 62.8 at 0.015, 62.8 at 0.05, 63.5 at 0.35 (PF-E3D-32). The issue's proposed 0.05 for
  rubber would not have fixed the mat.
- The pond's blob is the direct light's GGX at roughness 0.02 (the sky reflection off changed
  the clipped share 4.48 → 4.47 %).
- The canvas lays its roof picture at 256 cm (1 px = 1 cm): tiles 16 cm wide and 21.3 cm a
  course in plan — not the issue's "25 cm along the eave, 18 cm up the slope".
- Facing a 15° sun the light alone moves a part's hue off its 2D colour (a plaster wall under the
  blue sky 27.6°, a red canvas 12.8°, measured with every specular off): the issue's line "every
  built part's hue within 10° of its 2D colour" cannot hold for every part (PF-L3D-34).

**Decision.**

1. **Surfaces.** `core/scene3d/materials.SURFACES` names what a built part is made of — default
   (0.78 / 0.35, the old look), wood, wood cladding, steel, iron, enamel, plastic (1.0 / 0.20),
   rubber and canvas (0.95 / 0: specular OFF), terracotta, stone, masonry, plaster, concrete,
   soil, roof tile, shingle, glass pane, water, leaf, ember — each with its roughness, specular
   amount and optional detail picture. ONE path carries a surface to the engine: a palette entry
   names it (`PaletteColor.surface`); a tinted part names its own in its builder; a part of
   several surfaces keeps ONE `MeshPart` with `surface_runs` (its triangles grouped run by run,
   `builders.common.with_surfaces`), and the sink creates one Model per run
   (`mesh.surface_pieces`) carrying its surface in `PartSpec`; the host writes
   `quick3d.materials.surface_look` on the Model. `Garden.qml` holds no table — every material of
   `vcPart` / `roofPart` reads `surfaceRough` / `surfaceSpecular` — and
   `tests/unit/test_scene3d_surfaces.py` fails when a palette entry has no surface, when a
   surface writes a property the scene file does not declare, or when a literal roughness or
   specular is left in those components.
2. **Roof tiles.** A roof's tile faces (and its ridge tile) carry uvs in centimetres: a gable's
   are the 2D brush's frame (`roof_paint.paint_roof_with_ridge`: u along the ridge from its
   middle, v the plan distance from the ridge line, the far half mirrored as the canvas mirrors
   it), so seen from above the 3D roof is the plan's picture tile for tile, and on a 38° slope a
   course is 27 cm long; a hip's faces and a shed's plane run u along their own eave and v down
   their own slope (the canvas draws no hips). The picture is the canvas's `ROOF_TILES` (a
   shed's shingles its `SLATE`), at 256 cm (shingles 100 cm).
3. **Wall pictures.** A house's walls are `plaster` (the canvas's `CONCRETE`), a shed's
   `wood_cladding` (`WOOD`, in the item's colour), a garden wall and a stone-wall fence `masonry`
   (`STONE`): laid by the face's own plane in the item's frame (`built_detail.vert`), courses
   level round a corner. No new asset: every picture is one the canvas ships (asset forge).
4. **The detail shader** (`built_detail.vert/.frag`): the picture reduced to a linear albedo
   multiplier of mean 1 and height slopes (`core/scene3d/surface_detail.py`, PF-L3D-35), one
   `Texture` per picture per scene; a cotangent frame from screen derivatives; the detail normal
   faded by camera distance, the albedo by its mipmaps (Qt's `Texture` has no anisotropy); per
   surface a contrast (roof 0.6, masonry 0.8, plaster 0.85) and a normal strength. It takes the
   ground's rain tint and the rain's roughness / specular shift (`wetRoughShift`,
   `wetSpecularShift`) and the living garden's snow on what faces up (`builtSnow`, the rule of
   `built_snow.frag`); any other built top keeps `built_snow.frag` under snow.
5. **The pond's glint**: `water.frag` writes the direct light's specular itself
   (`SPECULAR_LIGHT`): GGX with Schlick's Fresnel for water at roughness 0.02, soft-capped at
   0.6 / exposure (`uGlintCap`).
6. **The gate** (`tests/integration/test_built_materials_render.py`, in CI's render job): a
   class row facing the family garden's golden-hour sun, every part judged against ITS OWN frame
   with every specular off — the hue within 10° for a part whose 2D colour has a hue, a matte
   part at most 1.5x its specular-free luma — and the trampoline's pad held to the issue's own
   10° line against its 2D blue; the gable's tiles at noon and at a low sun, its noon colour, a
   hip's and a shed roof's tiles, a glasshouse untouched, three walls on their shaded side and the
   pond's glint — each against the same frame without the change.

**Alternatives rejected.** Splitting a part into one `MeshPart` per surface in the builders
(the first build): 94 tests destructure a building's parts by name, and the pick oracle, the
shadow walk and the height gates read parts — the split belongs at the sink, where one Model has
one material. A per-vertex roughness in the vertex layout (a stride change for every mesh of the
scene, plants included). A table of surface values in the QML (a second table that drifts). Roof
uvs computed from world position in the shader (the tiles slide when a house moves, and the
2D phase is lost). The issue's 25 × 18 cm tiles and its specular 0.05 for rubber (measured
above). A new plaster texture through the asset forge: the canvas's concrete reads as render,
and no new asset is needed.

**Consequences.**

- Models: the family garden's built records 43 → 71, `bench_large`'s 87 → 169 (one per surface);
  vertices and upload bytes unchanged (151,182 / 8.22 MB; 290,065 / 15.76 MB): the uvs ride in
  the slot every vertex had. Building the built records: the family garden 73.1 → 77.2 ms (+6 %), `bench_large` 125.2 → 137.7 ms (+10 %; medians of three alternating rounds of seven builds — `with_surfaces` finding the runs). A frame (the family garden at golden hour, a finished readback of a new frame, rounds alternating before / after): on the RTX 4070 at 1920 × 1080 Low 14.1 → 11.3 ms, Medium 13.5 → 10.7, High 15.2 → 13.8, Ultra 18.6 → 19.8 (medians of three rounds, inside their own spread of 8-31 ms); on WARP at 1280 × 720 Low 97 → 100 ms, Medium 152 → 152, High 222 → 213 (two rounds). A never-shown host's first frame, which compiles every pipeline it draws, 4.1 → 4.6 s median over the living board's 171 frames (810 → 850 s in all, one leg each on a shared machine) — likely the detail material's own shaders, not isolated: in one process, alternating, the frames with and without the pictures differed by less than their spread; a live view would pay such a cost once.
- Five 256² RGBA8 detail textures per scene (about 1.3 MB with mipmaps), made on first use.
- Looks that change by decision: a black mat reads dark and neutral; plastic is fully rough;
  windows (`glass_pane` 0.40 / 0.40) mirror the sky (luma 43 → 85 at golden hour); a low-sun roof
  reads 1-2 luma lighter (its tiles' edges catch the grazing sun); a garage shed filled
  "concrete" in 2D is boarded like a tool shed in 3D (a shed's walls are always cladding).
- The issue's acceptance is met as defined in decision 6; the literal "within 10° of the 2D
  colour" holds for the pad (8.0°), wood (1.3°), terracotta (1.7°), cladding (0.3°) and the
  windows (9.6°) in the class row, not for a plaster wall (13.6°, the light) or a near-grey part.
- Open to the owner: the plaster's speckle (the canvas's concrete picture), the masonry's dark
  joints in shade, plastic fully rough, the windows' reflection, cladding on a concrete shed.
- Not done: the hip roof's 2D picture is still the gable's (the canvas draws no hips).

**Evidence** (RTX 4070, Direct3D 11, high; render tier 640 × 360 unless named; the render tier passed every gate on WARP and
on OpenGL too).

| What | Before | After |
|---|---|---|
| Black mat facing a 15.2° sun: luma / its specular-free luma (class row) | 4.08x, hue 128° off (0.78 / 0.35 everywhere) | 1.00x |
| Pad: hue against #427bc2, saturation (class row) | 17.7°, 0.34 | 8.0°, 0.60 |
| Pond at the mirror angle of a 10 / 20 / 30° sun (1280 × 720): clipped share of the water, peak luma | 6.14 / 4.48 / 2.73 %, 255 | 0 %, 212.6 / 227.0 / 237.2 |
| Noon roof close-up: luma std (render tier) | 2.2 | 10.8 |
| Low-sun roof close-up: luma std | 2.3 | 6.8 |
| Noon roof's mean colour | (239.5, 136.1, 86.7) flat | (238.1, 135.3, 86.3): −0.6 % luma, 0.0° hue |
| Walls on their shaded side, luma std: masonry / plaster / cladding | 1.2 / 0.8 / 1.2 | 7.0 / 2.1 / 7.3 |
| Hip / shed roof at noon: fine luma detail (about the 5 × 5 local mean) | 1.5 / 0.9 (no picture) | 4.1 / 5.2 |
| Glasshouse with and without every picture: largest pixel difference | — | 0 (a pictured roof's box: 22-25) |
| Noon orbit of the family garden's roof, 12 frames 0.5° apart: temporal \|d²\| of the roof's luma, native 1280 × 720 against the 1920 × 1080 frames box-reduced to it | flat roof 2.5 (1080p) | 6.4 against 7.3 (0.87: the native frame shimmers less than the supersampled one — no aliasing beyond the tiles' own detail) |
| Beauty Board, 4 examples × 7 shots (high, 1280 × 720): mean luma per shot | — | −0.85 … +0.08 |
| Family garden at noon (board): clipped share | 0.41 % | 0.62 % (the roof's lit tile edges) |
| Family garden golden hour (1280 × 720): the mat's mean colour | (131, 105, 86), luma 109 | (26, 24, 29), luma 25 |
| Balcony golden hour (board): the wall, luma / std | 31.9 / 1.6 | 30.5 / 4.9 |
| Raised bed golden hour (1280 × 720): the tool shed's walls, luma std | 2.4 | 6.2 |
| Truth gates (family garden, 1280 × 720): shadow IoU of the box caster at 15 / 35 / 60°, Low; High | 0.928 / 0.976 / 0.970; 0.985 / 0.985 / 0.974 | the same to the fourth decimal |
| North-up (plan against top-down, NCC) and the sky's sun in 24 views: bearing / elevation error | 0.7786 identity; ≤ 0.07° / 0.13° | the same |
| Built geometry: 491 builder records' triangles, normals and part names | — | identical (at 0.001 cm) |

Tests: `tests/unit/test_scene3d_surfaces.py`, `tests/unit/test_scene3d_roof_uvs.py`,
`tests/unit/test_scene3d_surface_detail.py`, `tests/unit/test_quick3d_qml.py`; render tier
`tests/integration/test_built_materials_render.py` (observed failing first: with every surface at
0.78 / 0.35 and the old water shaders, 8 of its first 10 tests fail; the roof kinds' tests
compare against the same frame without the picture, and before there was none). Pitfalls PF-L3D-34, PF-L3D-35,
PF-E3D-32.

## ADR-059 addendum: built-material stability, night fill, resting live shadow fit and built-world polish (#883, #884, #887, #894, #953, #957, #958, #959, #961, #965)

**Status**: Shipped in v1.41.1 after owner acceptance (2026-11-22; [PR #990](https://github.com/cofade/open-garden-planner/pull/990)). Amends the L1.4, L1.6, #734, #799/#802 and #801/#803 addenda above.

**Context.** Ten focused 3D rendering and built-world issues found across the 13 example plans on Ultra, High and Low presets:
- `#883` / `#958`: Qt Quick 3D's Ultra SSR (`reflectionEnabled: true`) reflects aggressively below roughness `0.70`, causing shimmer on `steel`/`iron`/`enamel`/`glass_pane` and turning courtyard pools into sharp house mirrors.
- `#884`: Direct noon light plus IBL pushed bright terracotta tiles, pale plaster walls and wood decks into R-channel clipping (`255`).
- `#887`: Shed `shingle` detail (`100 cm`, default `contrast=1.0`) read as patchwork; ridge caps inherited roof tile detail instead of reading cleanly; `masonry` at `256 cm` produced ~60 cm blocks; grazing close-up fascia/plaster showed SSAO concentric rings at `AO_FLAT_BIAS_CM = 1.0`.
- `#894`: Live 3D views always used the texel-locked shadow sphere while saved photos used `fittedShadows=true`, leaving preview shadows softer than saved photos even when the camera rested.
- `#953`: At night, vertical faces turned away from the fixed moon received zero bounce and crushed to sRGB `<= 3`.
- `#957`, `#961`, `#965`, `#959`: Raised beds always rendered as oak planks regardless of 2D `FillPattern`; multi-vertex organic ponds rendered with polygonal grey rims and cobalt water; flat-roofed houses kept cottage windows and a pale concrete roof (`specular=0.15`) that took a golden-hour lilac cast; `pebbles` and `compost` textures had glossy spherical domes baked into the PNGs.

**Decision.**
1. **Ultra SSR roughness floor & decoupled water SSR (`#883`, `#958`).** Raise `steel`, `iron`, `enamel` and `glass_pane` to roughness `0.70`. In `water.frag` and `water_door.frag`, keep `uRough` (`0.02`) for direct GGX sun glints and IBL probe while writing `ROUGHNESS = uSsrRough` (`0.40`) in `MAIN()` so Ultra SSR renders soft, translucent water reflections rather than a sharp mirror (`0.02`) or flat unreflective blue (`0.75`).
2. **Per-surface linear albedo scaling (`#884`).** Add `Surface.albedo_scale` (`surfaceAlbedo` / `surfaceAlbedoSrgb` in `quick3d/materials.py` and `Garden.qml`, `uAlbedo` across every custom material in `vcPart`/`roofPart` including `screen.frag`), keeping `DEFAULT_SURFACE` at `1.0`. Exact surface table and GPU measurements live in `ogp-lush-cinematic` reference `021`.
3. **Cohesive roof/wall detail and SSAO floor (`#887`).** Set `shingle` to `SLATE` at `128 cm` (`normal=1.2`, `contrast=0.35`); point `ROOF_TILE_CAP` and `SHINGLE_CAP` at plain `"roof_cap"` (`detail=None`); tighten `masonry` to `128 cm`; raise `look.AO_FLAT_BIAS_CM` (and QML default `aoBias`) from `1.0` to `1.4` cm.
4. **Live shadow fitting at rest (`#894`).** Add `EngineHost.set_fitted_shadows(bool)` and a `250 ms` debounce (`SHADOW_FIT_DELAY_MS`) in `Workspace`: camera motion unlocks (`fittedShadows = false`) immediately; after `250 ms` at rest the view locks to `fittedShadows = true`. `Quick3DHost.capture(fitted_shadows: bool | None = None)` preserves the view's current fit when `None` and always restores `fitted_before` in `finally:`.
5. **Cool sky-tinted night minimum fill (`#953`).** Add `look.night_fill_linear(look)` (`NIGHT_FILL_SKY_SHARE = 0.75`, radiance-capped at `NIGHT.sky_top`, cloud-attenuated) folded into `twilight_fill` (keeping `TWILIGHT_FILL_DAY_SHARE = 0.4` and `TWILIGHT_FILL_TARGET = ((TWILIGHT_DEG, 1.0), (-3.0, 1.02), (NIGHT_BELOW_DEG, 1.035))`) so `5.89°` stays `(0, 0, 0)` and dusk/dawn stays monotone across all presets and weathers.
6. **Built-world fidelity (`#957`, `#961`, `#965`, `#959`) & clean 3D ground surfaces.**
   - Forward `PARAM_SURFACE_PATTERN` for `RAISED_BED` in `ui/view3d/snapshot.py`; `builders/beds.py` maps architectural fills (`CORTEN` -> `corten`, `STONE`/`BRICK`/`FLAGSTONE`/`SLATE` -> `masonry`, `CONCRETE`/`CLAY` -> `concrete_wall` with `CONCRETE` detail, `TERRACOTTA` -> `terracotta`) to a tinted frame while preserving exact `soil_surface_cm`. `modern-garden` now uses real `RAISED_BED` items for its three Corten beds instead of the `#940` metal-container workaround.
   - `builders/surfaces.py` treats ground polygons with `>= 5` vertices per ring as natural ponds (`is_natural_pond`): convex corners are smoothed inward via clamped quadratic Bézier fillets (`NATURAL_POND_MAX_CUT_CM = 5.5 cm`, skipping reflex corners), bordered by a low flush earth shore (`BANK_UP_CM = 1.35 cm`, strictly below `DECK_TOP_CM = 2.5 cm` so overhanging pond decks clear it cleanly) and darker olive-green natural water. Formal pools stay unchanged. Gravel path rims drop to `GRAVEL_RIM_CM = 1.8 cm` (`< DECK_TOP_CM`) so round end caps abutting wooden terraces stay underneath the deck boards.
   - `ui/view3d/ground_bake.py` suppresses 2D CAD outline strokes on `SURFACE_OUTLINE_KINDS` (`LAWN`, `GARDEN_BED`, `TERRACE_PATIO`, `DRIVEWAY`, `POND_POOL`) by default (`surface_outlines=False`) so neon-green/orange CAD borders do not bleed onto 3D ground tiles, while keeping `surface_outlines=True` available for 2D-canvas parity tests and preserving `GENERIC_*` and `PATH` strokes.
   - `builders/buildings.py` / `facade.py` give flat-roofed houses `MODERN_HOUSE_SPEC` (wide/tall single-pane dark-framed windows, modern door); explicit flat roofs carry `"flat_roof"` (`roughness=0.95, specular=0.0, albedo_scale=0.45`) for `CONCRETE`/`SOLID` fills while custom 2D fills (e.g. `GRASS` green roofs) switch to matte `"concrete"` (`roughness=0.95, specular=0.0, albedo_scale=0.85`) on the material path (`quick3d/materials.fill_surface_name`, `host.set_part_fill`) with no geometry rebuild, preserving `FR-3D-BUILT-02` alongside automatic ridge-less flat houses.
   - Re-author `generate_pebbles` and `generate_compost` matte (`gloss=0.0`) in `scripts/generate_asset_forge_textures.py` (`PROVENANCE.md` updated). `wildlife-garden` example paths, boardwalk and oak-shaded hammock updated for plausible, unobstructed flow.

**Evidence & tests.** Full RTX 4070 before/after numbers and Beauty Board gates are recorded in `ogp-lush-cinematic` reference `021`. Tests: `tests/unit/test_scene3d_materials_and_built_polish.py`, `tests/integration/test_view3d_materials_shadow_fit.py`, `tests/ui/test_quick3d_host.py`, updated `test_scene3d_surfaces.py` / `test_scene3d_look.py`, and GPU render-tier suites.

## ADR-059 addendum: ground bake — flat surfaces painted from records into ground tiles (Phase 17, L1.5)

**Status**: Accepted (2026-10-12, #385 story L1.5); amended the same day by the story's first
review — "Review round 1" below changes decisions 3, 7, 8 and 9 and withdraws the statement that
gate G6 is unmet.

**Context.** Decision 9 gave every item with a height a solid; everything without one — lawns,
terraces, driveways, paths, in-ground beds, flat furniture — had no place in the 3D scene. The L0
spike put them on the ground by hiding the other items and rendering the live `QGraphicsScene`
into one texture: that toggled item visibility, cleared the user's selection, fired
`scene.changed`, painted the canvas's beige where nothing was drawn, re-rendered the whole plan
for every edit, and kept every texture it ever made alive.

**Decision.**

1. **Paint from records, never from the scene.** `ui/view3d/ground_bake.GroundBaker` paints what
   `snapshot_records` handed over. No `QGraphicsItem` is read, hidden or created by a bake (an
   AST scan pins it), so the selection, item visibility and `scene.changed` cannot be touched —
   gate G4 is a property of the design, and a test with spies and a control holds it.
2. **The rule for what is on the ground:** a record that carries a paint description
   (`Material.paint`; every item but a plant) and for which the scene holds no solid
   (`SceneSync.solid_ids`). "No solid" is asked of the sync, not of the kind: an item a builder
   makes a solid for leaves the ground, one whose builder made nothing stays on it. Under a solid
   lies whatever flat item was drawn there, else meadow — the spike left that ground bare, and a
   house on a lawn stood in a hole.
3. **The paint description is additive record data.** `Paint` (pen width, style, cap, join; the
   item's opacity; a circle's paint turn — review round 1) lives in `Material` — a restyle is a
   material change; the anchor of the local
   frame in item coordinates is `params["paint_origin"]` — geometry; `Record.outline` holds a
   polygon as drawn where `footprints` cannot. The diff semantics of L1.1 hold unchanged: a move
   is a transform change, a recolour a material change. (A first design put the whole paint frame
   into the material: 29 of L1.1's diff cases failed — a move became a material change.)
4. **A flat item the solid path refuses still gets its record.** `outline_too_large` is a bound
   on the WORK of cutting regions; painting needs none. A polygon or polyline without a height
   whose outline is refused for work keeps a record with `footprints == ()`. The SIZE bound
   (`MAX_ITEM_VERTICES`) stays in front of everything.
5. **One implementation with the canvas.** The brush is `create_pattern_brush`, a sprite
   `render_furniture_pixmap`, and the path-style painters were moved out of `PolylineItem.paint`
   into `ui/canvas/items/path_style_paint.py`, which both call. Only single `QPainter` calls are
   mirrored. A second implementation of ten path and fence styles would have been a second place to be
   wrong; the extraction found two defects of the first (PF-L3D-03, PF-L3D-04 and PF-CAN-21).
6. **Tiles are crops of one pixel grid.** 512 px tiles; the finest of 1, ½, ¼ … px/cm within
   4096 × 4096 px and 256 tiles; whole-pixel offsets — seamless by construction, not by
   blending. A tile is a pure function of its records in order, so an untouched tile can be handed
   out as the same object and the sink uploads by identity.
7. **The baker is driven by `SceneSync`, with the geometry path's diff, in the same
   transaction.** `SceneSync(…, ground_baker=)`; the bake runs before the sink is touched; a baker
   that raises is contained (`ground_failure`, the ground stays as it was or bare) and never
   poisons the sync; `reset()` clears it. The protocol (`core.scene3d.GroundBaking`) is Qt-free:
   the sync logic is tested with a double.
8. **What a bake may cost is bounded per tile, each bound taken before its work** (§8.29.5 has
   the table): records and outline-vertex passes by admission, style elements and walk steps and
   dashes by one budget per tile, a sprite's image before the renderer is asked. The criterion
   is "the cost of what the file holds times a stated constant, no amplification, no bound behind
   its work" — not "nothing is ever slow".
9. **In the engine: one quad and one texture per tile; a changed tile gets a NEW Model with a
   new texture object** (review round 1: not a new texture on the old Model), and the replaced
   texture is held until the next presented frame — at the latest until the next update.
   `flipV`, `ClampToEdge`, quads 0.02 cm oversized, the bare rectangle hidden under tiles.

**Alternatives considered (rejected).**

- *Render the scene region* (`render_scene_region` with items hidden) — the spike's way; see
  Context. It remains the tests' REFERENCE, on a scene the test owns.
- *One texture for the whole plan* — every edit re-bakes and re-uploads up to 64 MB.
- *Meshes for flat items (decals above the ground)* — z-fighting or visible steps, and every
  texture, sprite and path style rebuilt as geometry: a third implementation.
- *A paint-only side channel beside the records* — a second snapshot with its own diff; one edit
  would be two diffs that can disagree.
- *Updating a tile's texture in place* — measured not to show (PF-L3D-04).
- *Hairline-exact tiles by rendering the plan in one image and cropping* — exact, but every edit
  costs the whole plan.

**Consequences.**

- `Record`, `Material` and `GroundSpec` grew (`outline`, `paint`, `tiles`); `EngineSink.set_ground`
  keeps its signature. `render_records` takes `ground_baker=`. Nothing is wired into the app by
  this story: the workspace (L1.3) constructs the baker.
- The engine package has a THIRD engine module: `quick3d/ground_tiles.py` imports
  `QQuick3DTextureData` (ADR-048's L1.2 addendum says "two engine modules"; the boundary test's
  `ENGINE_IMPORTERS` names all three). The baker itself is no engine module — QtGui only.
- Three changes to the 2D canvas, all defects found by painting the same items twice: a loaded
  rectangle keeps its saved `fill_color`; the rails of a bent boardwalk and the borders of a bent
  stone wall no longer fill the bend; the path-style walk refuses a spacing below 0.05 cm or
  above 100 km (a pen width that is no width).
- Known limits (§8.29.5 has the list with its measurements): arcs, Bézier curves and text have
  no record and are not on the ground; lines up to a pixel wide are rasterised per tile; the
  meeting corner of a cut dashed outline is blended twice; a dashed round outline cut by a tile
  is stroked along chords; coarse pixels on plans above 41 × 41 m; ground tiles are not pickable
  (a click on the ground hits no item, as before).
- **G6 is met in the two cells that were measured** (review rounds 1 and 2): twenty full
  re-bakes of a 16 MB ground do not grow the process on WARP, whose window presents its frames,
  nor on the hardware adapter, whose window presented NONE — where nothing is rendered, so that
  cell shows the process side only. A hardware window that presents is on the story's manual
  checklist. What the first version of this addendum reported as "unmet where no frame is
  presented" was its own soak calling `grab()` after every re-bake (PF-L3D-04, the grab() paragraph of archive/07-l1-5-ground-bake.md).

**Validation.** Default tier — `tests/integration/test_scene3d_ground_bake.py`: G1 parity for the
25 fill patterns × tinted/untinted × 0° / 33° × two tile-straddling positions (200 cases: not
turned mean 0 and max 0, turned mean ≤ 0.0002 and max 1, of 255; bound 6), every shape, the ten
path styles (one tile: bit-identical; six tiles: mean ≤ 0.016), sprites, pens, opacity; G2 on
`bench_small.ogp` (mean 0.00006, max 3; NCC 0.99999999 against −0.28 / −0.09 / 0.005); G3 on both
bench plans (≤ 2 tiles, 3.4 ms and 3.3 ms median, `last_examined == 1`, untouched tiles the same
objects); G4 with spies and a control; G5 a scripted session through the app's commands against
a from-scratch bake, bit for bit; G8 stacking and arrange; the refused-outline pins (3,000-point
path, 5,000-vertex lawn, clipper never called); the hostile corpus by counts.
`tests/unit/test_scene3d_ground.py` (grid, tiles, the sync with a double),
`tests/unit/test_path_style_paint.py` (the shared painters: the canvas's walk unchanged, the
clipped walk and its budget), `tests/ui/test_quick3d_ground_tiles.py` and
`tests/unit/test_quick3d_ground_tiles.py` (the engine's books, the QML component). Render tier —
`tests/integration/test_scene3d_ground_render.py`: the pipeline on a real renderer, shown and
through `render_records`; G2 in the engine (NCC 0.98 against 0.08 / −0.11 / −0.07); G7 (luma
spread 0.0 to 0.7 across every border; controls 48 and 7.9); G6 in objects (≤ 32 of 16 tiles
alive; control 320) and in memory on WARP (≤ 0.2 MB a cycle; control +32) and on the hardware
adapter (review round 1: −0.10 to +0.01 MB a cycle with 0 frames presented, no frame taken in
the loop; the grabbing control +16.1 to +17.4).

### Review round 1 (2026-10-12): what the first review changed

The story's independent review found no regression of the 2D canvas and no unbounded count, and
five places where the bake did not keep its promise. What was DECIDED in answer — the findings
themselves, with their measurements, are PF-L3D-03, PF-L3D-04 and PF-CAN-21:

- **Decision 3, amended — a circle's turn is paint.** A circle's record does not turn (decision 9
  of the contract: footprint and solid are the same whatever its rotation). What the canvas
  paints in its coordinates does, and the bake painted it unturned. `Paint.rotation_deg` carries
  that turn (`LocalFrame.paint_turn_deg`; 0.0 for every other shape). **The diff matrix changes
  in one cell:** a circle the canvas paints, turned about its centre, is now ONE material change
  (`update_material`), where it was no change at all; geometry and transform are unchanged, no
  builder runs, and a plant — never painted — still changes nothing. *Rejected:* making a
  circle's transform rotatable (every turned round solid would be re-posed, and L1.1's "a
  circle's footprint does not turn" would be false in the record); a param (params are
  geometry: a turn would rebuild the mesh).
- **Decision 7, amended — the `GroundBaking` seam knows about unfinished work, and the sync
  remembers a failed bake.** A baker MAY stop early: `bake` hands a tile it has not re-painted
  out as the object it was, `pending` says how many such tiles there are, and every later call —
  whatever its diff — goes on. The promise is stated on the END: once `pending` is 0 the tiles
  are those of one call on an empty baker, with a diff or without. `fresh()` is a baker without a
  budget. `SceneSync` gains `ground_pending` and `continue_ground()` (one bake with an empty
  diff, one transaction when a tile changed); every `apply` continues as well;
  `expected_state()` is the FINISHED ground, so while work is pending the sink is behind it in
  exactly the pending tiles and equal in everything else; `reset()` drops pending work; a sink
  that raises in a continuation poisons the sync like any sink call; a baker that raises is
  contained as before — and, new, is not asked again until a record, the set of solids or the
  plan's rectangle changes (three idle ticks after a failing bake had been three bakes and three
  tracebacks). *Rejected:* leaving the decision when to stop to the workspace — only the baker
  can stop between two tiles; a worker thread — the brushes and sprites are `QPixmap`s (GUI
  thread), and a second thread painting records the GUI thread replaces is a second story.
- **Decision 8, amended — a time budget between tiles, and a stated loss.** The bounds stay
  bounds on counts; what a count costs is Qt's and spans three orders of magnitude, so a `bake`
  paints for `BAKE_BUDGET_S` (10 ms, an injectable clock), at least one tile, nearest to the last
  edit first. And "the topmost 256 records of a tile" is replaced by a rule that says what is
  lost: the walk ends at the first record that opaquely covers the tile, and below the cut a tile
  keeps what covers it whole (four underlays, to the first opaque one) — a capped tile loses the
  records below its topmost 256 that do not cover the whole tile. (That rule kept a lawn only
  when it was the plan rectangle; review round 2, below, replaces it.) *Rejected:* dropping from the
  top (the newest items vanish); a bound on scanline crossings to cap a comb polygon's time (a
  fourth pass over every outline for a shape the 2D canvas cannot paint either — recorded as a
  scan not acted on).
- **Decision 9, amended — one texture per `Texture`, for life.** Found by the budget's first run
  on a real engine, not by the review: a tile whose `Texture` element was pointed at a second
  `QQuick3DTextureData` is drawn white once the first is destroyed. A re-baked tile is therefore
  a new Model, as a changed geometry has always been a new geometry. *Rejected:* keeping the
  replaced texture longer (it only moves the white frame); setting the property again after the
  release (the L0 spike measured that a texture detached and attached again draws white).
- **One writer for an item's look (2D).** The record's fill comes from the item's attributes, the
  canvas paints its brush, and three shipped tools and the loader set only one of the two.
  `core/item_style.py` is the one place that sets both; the 2D suite walks every operation that
  makes an item from an item. This is a change to the 2D app made by a 3D story, on purpose: the
  alternative — reading the brush back in the snapshot — cannot recover a pattern or a tint from
  a textured brush.
- **Gate G6 measures what a live view does.** No frame is taken in the soak's loop; the gate is
  unconditional (which cells it measured, and what the hardware cell cannot see: review round
  2, below). The rule that follows from what DID grow the process is for the workspace: no
  repeated `grab()` on a live host that is not presenting; a screenshot goes through the
  offscreen path.

Validation of the round: `tests/integration/test_scene3d_ground_rules.py` (42 tests by counts —
the lawn under 255, 256 and 2,000 pavers; six shapes of cover; the budget with a clock that
advances a second a reading; random edit sessions through three bakers; a raising painter),
`tests/unit/test_scene3d_ground.py::TestSyncWithAGroundBaker` (pending work, the remembered
failure, poisoning in a continuation), the 2D suites named in PF-CAN-21, the render tier's
budgeted open and five re-texture sequences on the RTX 4070 and on WARP, and 23 mutants of the
new rules, all killed.

### Review round 2 (2026-10-12): what the re-check changed

The re-check found the save / load work of round 1 clean, the round-1 rule for a full tile right
in its wording and wrong in its outcome, and several places where a rule had been guarded by
the one case its author thought of. What was decided in answer (the findings are PF-L3D-03, PF-L3D-04 and PF-CAN-21):

- **Decision 8, amended again — admission by outcome.** "The topmost 256, and under them what
  covers the WHOLE tile" kept a lawn only when it was the plan rectangle; 10 cm inside the plan's
  edge 149,604 px of the first tile were bare. The rule is now stated by what it must achieve:
  *when a bound bites, a tile loses its smallest records, never a large one.* A tile's members
  are ranked by how much of the tile their paint box overlaps (box against box; ties to the
  topmost) and the lowest-ranked go, for the record bound and the vertex bound alike; the kept
  ones are painted in z order; an opaque cover still ends the walk. `TILE_UNDERLAYS` is gone.
  *Rejected:* the smaller variant "keep as an underlay any filled record whose paint box covers
  at least half the tile" — a second threshold with the same kind of edge (a lawn over 30 % of
  the tile is dropped again), where a ranking has none; ranking by true covered area — it would
  read vertices for records that are then left out, which the security criterion forbids (no
  work behind the bound). The price is stated in §8.29.5: the ranking does not know a shape.
- **Decision 7, amended again — the backlog is owed a tile a pass, and a tile's failure is the
  tile's.** A call that brings an edit paints the edit's own tiles first and then one tile of
  the backlog whatever the budget says (a pass: the budget plus two tiles); without it a drag
  kept 14 of 15 tiles pending for as long as it lasted. And a tile whose paint raises as a whole
  keeps its picture, is listed (`GroundBaker.tile_failures`), is not pending, and is retried by
  the next call that brings a change — where clearing the baker made the NEXT edit blank fifteen
  of sixteen tiles. For a bake that raises anywhere else the seam gains `restart()`: the sync
  calls it instead of `clear()`, and the baker forgets its books and keeps its pictures until
  each tile is painted anew — the outcome ("the edit after a failure does not blank the
  ground") holds for every raise site, not only for the one the review used. *Rejected:*
  keeping the sink's tiles in the sync for the keys a cleared baker has not painted yet (the
  sync would need to know WHICH tiles are pending: a wider seam than one method); retrying a
  failed tile on every pass (a tile that cannot be
  allocated would be tried sixty times a second); reporting it through `ground_failure` (that
  is the whole bake's, and it stops all ground work until the plan changes).
- **One writer for an item's look — and a guard that does not read the source.** The census of
  derivation sites caught one of six planted forgetful operations. The guard is now a teardown
  fixture over every integration test: every item of every scene a test built must have style
  attributes that describe its brush and pen. It found the last writers that set one half —
  a freshly drawn polyline stated no stroke at all (undoing a width, dash or type edit on it
  raised, in the shipped app), the panel's undo of a type change — and 31 hand-made pens and
  brushes in the tests themselves. A sprite's pen is exempt: it says nothing about the picture
  (`GardenItemMixin.paints_sprite`). *Rejected:* widening the source scan (every new spelling
  is a new blind spot); scoping the fixture to the 2D suites only (the 3D suites build scenes
  and drive the same writers — and held 161 of the 167 first findings).
- **G6, restated by what was measured.** "Met … whether its window presents frames or not"
  claimed a cell nobody ran: measured are a software rasteriser whose window presents, and the
  hardware adapter whose window presented none and therefore rendered nothing. The requirement
  and the test now say so, and the presenting hardware window is a manual check.
- **The loader reads a preset line's stroke with care.** Reading it at all (round 1) made a
  hand-made `"stroke_width": null` skip the item, where every such file had loaded at the
  preset's stroke. A width that is no finite number of at least the panel's minimum (0.5) and a
  colour Qt cannot read keep the preset's value, each on its own; a fully transparent colour is
  a colour (the panel's dialog offers the alpha channel) and loads as given. A plain line's
  stroke is applied as it always was.

Validation of the round: `tests/integration/test_scene3d_ground_rules.py`
(`TestATileLosesItsSmallestRecords`, `TestATileThatCannotBePainted`, the backlog tests),
`tests/integration/test_item_style_in_step.py` (the fresh line and its undos, the hand-made
files, the guard's own teeth), the fixture across the integration folder (4,232 tests of the
integration and ui folders passed under it), and 63 mutants of the round's rules, all killed.
The review's own probes, run on the finished round: a lawn 10 cm and 0.5 cm inside the plan's
edge under 255, 256, 300 and 2,000 pavers — 0 lawn pixels bare in every case (149,604 and
158,721 before at 256); the real scene of 256 pavers on an inset lawn against the canvas —
mean 0.033 of 255 and 484 px off by more than 8, one paver and its outline (24.4 and 130,129
before); an edit a pass with one tile a pass — pending 13, 9, 4, 0, 0 after edits 1, 5, 10,
20 and 40 (14 at each before); the edit after a failing bake — 16 painted tiles shown (1
before).

### Sync with the integration branch and master v1.30.13 (2026-10-19)

`master` fixed three of the 2D defects this story had fixed on its own, with mechanisms of its own:
`core/item_look.py::restore_stored_look` (#502 — the loader writes the saved attributes, #438 /
#469) and `core/item_look.py::copy_visual_style` (#501 — offset and mirror, #470). **Where both
fixed the same defect, `master`'s mechanism wins:**

- `core/item_style.py` is deleted. Its helpers that `master` has no equivalent for — `adopt_pen`,
  `fill_brush`, `style_gaps`, `paints_sprite`, `saved_stroke_width` / `saved_stroke_colour`,
  `MIN_STROKE_WIDTH`, `stroke_style_of` — moved into `master`'s module, `core/item_look.py`, so
  that an item's look has ONE module again; this branch's own `copy_visual_style` is gone, and the
  corner tools and `PolylineItem.clone_with_points` call `master`'s.
- The loader calls `restore_stored_look` in every branch, as on `master`; this branch's own
  attribute writes there are gone, and the four filled shapes set their pen as `master` does. What
  `master` does not cover stays, each pinned by a test that fails with the integration branch's
  code at that place (10 of 10 checked by putting that code back): the saver writes a dashed
  line's dash style (#467); a preset line's own saved stroke is read — validated — and stated
  (#468); a file with a fill colour and no pattern is painted in the type's texture at the saved
  colour from the first load (`fill_brush`); chamfer / fillet copies, re-pointed lines and trim
  results carry their source's look (#441); a freshly drawn line states its stroke, and the panel's
  undo of a type change states the pen it builds; a bent boardwalk or stone wall does not fill its
  bend (#439).
- `restore_stored_look` leaves a stroke attribute alone where the file holds no colour or number
  at all (`null`, a list) instead of raising: merged as it was, it SKIPPED a preset line with
  `"stroke_width": null` — the regression review 2 had found in this story's round 1, now in
  `master`'s helper (#527). A plain shape still refuses such a value at its pen, as before.
- A loaded sprite states what its file holds (`master`'s rule), not its type's stroke as review 2
  had this branch do; `style_gaps` no longer judges a sprite at all (`master`'s
  `test_canvas_item_cache.py` gives three sprites a texture brush they never paint).
- `master`'s strict numeric plan I/O (#453) refuses a whole document whose stroke width is
  infinite, not a number or an integer no float holds: three of review 2's preset-stroke cases no
  longer reach an item.
- Gate G3's median is a wall-clock assertion and carries `@pytest.mark.perf` (ADR-058); it ran at
  11.58 ms beside eight workers. Its stopwatch moved to `tests/integration/ground_bake_support.py`:
  in the test module, `master`'s perf-marker guard (which keys a module's functions by their bare
  name) took every test that calls a baker's `bake` for a timing test.
- The identifiers are the placeholders (`renumber_385_v2.py`, before the merge): this addendum
  belongs to ADR-059; its concept section is §8.29.5, its test patterns §8.10.10, its lessons
  PF-L3D-03, PF-L3D-04 and PF-CAN-21, its requirements FR-33's `FR-3D-GROUND-*`.

### Part B: the bake wired into the workspace (2026-10-19)

- **The baker lives in the sync, not in a ground stage.** The workspace's controller gets
  `ground_baker=` and hands it to `SceneSync`, which bakes with the diff the builders run from
  AND the set of items a builder made a solid for (`solid_ids`) — what decides whether an item
  is ground. *Rejected:* the controller's ground stage (`set_ground_stage`), which runs BEFORE
  `apply` and cannot know which items get a solid in it.
- **Pending ground work is a pass of its own.** `SceneSync.continue_ground()` (one bake, no
  snapshot, no diff) is scheduled by the controller exactly like any pass and is preempted by
  an edit, paused while 3D is hidden, never scheduled after a pass that was given up. A ground
  pass that FAILS is rebuilt by a full pass once per change of the plan; the second failure
  gives up until the next change (review 3: rebuilding every time paints the first slice,
  goes through, and fails at the same tile again — 2,308 ground passes in 3 s). The workspace
  does not take a ground pass as a sun or as "the pipeline worked" (the stale-sky timer, the
  quiet-time release).
  *Rejected:* `mark_dirty()` per slice, as the controller's seam suggested — a whole-plan
  snapshot (O(total vertices), ADR-060) for every 10-ms slice; a timer of its own — the posted
  event was measured not to starve due timers (offscreen and Windows platforms: a 5 ms timer
  fired after the first of 40 slices of 10 ms).
- **What the bake could not do reaches the problems list** (`GroundProblems`): an item whose
  paint failed is listed by name, but it is SHOWN (cut off), so it is not counted with the
  objects "not shown in 3D" — it makes the ground incomplete (review 3; first delivered as an
  object problem); capped tiles, tiles that could not be painted, a failed bake and ground
  work given up are NOTES of the ground — rows of no item, first. *Rejected:* listing the
  records a capped tile left out by id — the admission walk keeps only what a tile keeps, and
  naming the rest would put work behind the bound.
- **A document change clears the baker**; an engine reset clears it through `SceneSync.reset()`.
- **Release policy: tiles are not counted.** First built conservatively — every tile Model a
  pass destroyed counted in `TickReport.retired` — and reversed by measurement: tile Models need
  no release (new tile Models with the same textures, twenty cycles, with or without a release:
  flat — a reading later found broken, its frame was white), and a `releaseResources()` leaves
  tile textures behind (+10.7 to +13.3 MB a cycle on WARP with a release each cycle; flat
  without). Counting tiles only called the leaking release more often; NOT counting them does
  not make the leak rarer — every release that item changes cause still leaks (review 3). The leak itself is
  OPEN (PF-L3D-04; the workspace's G7 soak with the baker in: GPU +7.5 MB per rebuild with its
  release after quiet, +19 with the release in the pass, against 0.0 and −0.1 without the
  baker; with tiles no longer counted, GPU +10.2 and private bytes +30.4 with the release in
  the pass). The cause is a Qt Quick 3D 6.11.0 bug, read in its source and proven by measurement (#532): `QSSGBufferManager::clear()` walks `customTextureMap` with `++it` while `releaseTextureData(it.key())` erases through its own lookup; Qt 6's `QHash` shifts the next entry of a collision run back into the freed slot, `++it` skips it, and `customTextureMap.clear()` drops the skipped entries unreleased. The key's hash covers only size, depth, format and transparency, so same-size tiles all collide and about half leak per release (WARP, 16 × 512²: +10.8 / +11.7 MB a cycle against a prediction of 8 × 1.333 MiB) — tried and rejected: in-place updates, distinct tile
  sizes, tiles as `Texture.sourceItem` images. Static tiles leak too: EVERY release leaks, up
  to ~42 MB for the largest ground (4096² px, ~85 MB with mips). *Gate (review 3, replacing a
  first fallback that gated with the bake OFF and reported the product against a 60 MB
  ceiling that could not fail):* the workspace's G7 soak measures the PRODUCT — ADR-060
  decision 15 makes it the leak half of ADR-048 criterion 10 — against
  `LEAK_BOUND_MB_PER_RELOAD` + 0.6 × the soak's own tile-texture bytes per release × releases
  per reload; a non-strict `xfail` tripwire holds the GPU slope to the plain bound; the
  bake-off run stays as Model churn alone. 3D became the default view with #532 open, on the
  owner's decision at the L1 pull request with the measured exposure (§8.29.5 limit 11; ADR-060
  addendum D5).
- **The tile's material is the endless meadow's** (roughness 1.0, specular amount 0.15), so a
  baked lawn meets the meadow without a step (the L1.4 look review: 0.92 / 0.2 measured 2 to 8
  luma darker; the combined look pass gates the edge at ≤ 1 luma).
- **The bake's log lines follow §8.11**: one normalised, capped line at ERROR, the traceback at
  DEBUG (they quoted an exception's message as it came).
- **Ruling R41:** gate G6 reads the median of the last ten cycles' growth instead of Theil–Sen
  over them (one +20.6 MB step read +2.80 MB a cycle); bound unchanged; §8.10.10.
- **The frozen `--selftest`** bakes one flat lawn with the product's baker over twelve tiles and
  as many passes, and fails on a wrong tile count, a bake that raised, or no lawn in the frame.

Validation: `tests/integration/test_scene3d_ground_wiring.py` (12 tests), the workspace's suites
with the baker in (two of their assertions said "a bare plan rectangle" and say "tiles" now),
`tests/unit/test_quick3d_selftest.py`, the render tier (GPU and WARP).

## Addendum (2026-10-23, issues #557/#558 — illustrative category heights, width propagation)

- **Estimated heights (#557)** are a deliberate product-policy change to the
  unknown-height contract: a plant with no usable height renders the matching
  plant form at a documented illustrative category fallback
  (`core/plant_height_estimate.py`: tree 400, shrub 150, perennial 60,
  vegetable 50 cm; category group first, then kind) instead of the pale
  marker. The plan keeps height unknown — nothing is written to species data,
  measurements or the saved file; the transient record carries
  `estimated_height_cm`, viewing 3D adds no undo step, and the info card shows
  "{height} (estimated)". The estimate drives decorative 3D geometry (and its
  shadow) only; the analytical 2D sun/shade model keeps treating the height as
  unknown (`effective_height_cm` still returns `None`). Known and measured
  heights keep their exact geometry; setting a real height replaces the
  estimate. Pinned by `tests/integration/test_plant_package_558_559_560_552_557.py`.
- **Maximum-width propagation (#558)** rides the same builder/record path:
  editing Max Spread on a species-sized plant resizes the 2D footprint and the
  3D canopy spread together (center and rotation pivot preserved,
  `set_radius_centered`), as one undo step with the metadata edit. Explicit
  spacing overrides, measured spreads and custom footprints win; a cleared
  maximum preserves geometry.

## Addendum (atmosphere-sky and render-tier integrity, #695/#696/#704/#714/#717/#718/#722)
- **The sky probe spans the day.** Gate G4's instrument now measures four sun elevations
  (6°, 12°, 30°, 60°) × three azimuths × two offsets on both sky models — 24 views. Its
  disc finder first takes the largest connected, compact white plateau (at least 20
  pixels, every channel ≥ 250 — luma ≥ 250 since #716, addendum L7.1 of ADR-048 — bounding
  box at most 4:1, at least 40 % filled) and its
  centroid, falling back to the old bright-and-warm peak: at a low sun the warm
  horizon band outscored the disc (#717), and the centroid of every white pixel merged
  two blobs into a false sun between them. Measured on the RTX 4070 at 640 × 360: worst
  bearing error 0.08° / 0.09° and worst elevation error 0.13° / 0.07° (painted /
  atmosphere), inside the 0.25° acceptance.
- **The set sun is measured.** `--dusk` now renders a sky-only camera at the sun's own
  bearing at +1.0, +0.4, 0.0, −1.0 and −3°, for clear and every cloudy weather;
  `sun_dip` compares the darkest pixel within 10° of that bearing with the median at the
  same world elevation 15–45° away, over the bands within 1.5° of the sun's own elevation
  (an image row is not a world elevation under a pitched camera: comparing rows read a
  false 20-luma dip; and an isolated cumulus 6° above the sun is weather, not a black
  sun — it read 48 luma). A dip over 10 luma fails the board (#695); `measured=False`
  when no band had both a near and an away sample, so "nothing measured" cannot pass as
  a clean sky.
- **The playback stall (#722).** `SKY_SETTLE_MS` is 300 ms — longer than playback's
  200 ms step, so the steps keep restarting the settle timer — and a sky stale for 1 s is
  built at that pass (`SKY_MAX_STALENESS_MS`), so a playing day still follows the sun
  about once a second instead of rebuilding on almost every step (3.5 steps/s under the
  atmosphere before).
- **The far-row bound is re-derived.** The distant-horizon gate measures 3.44 / 3.48 luma
  at 403 m / 15° and 3.11 at 67 m / 31.6° on the current scene (the issue #714 numbers),
  so `HORIZON_STEP_BOUND` goes from 3.0 to 3.6, and the render tier gates the per-mood
  step at the same 3.6 (covering #696's 3.13 low-sunset row). The scene was not shown to
  have regressed since L4: the with- and without-L7 readings are identical, so 3.0 was a
  bound from the earlier scene, not a defect this package hides.
- **The flood soak settles first, and a forge completion cannot outlive its sink (#718).**
  `scenario_soak` applies its `off` / `flood` release policy only after the initial settle:
  with the flood threshold active from the first pass, the LOD queue re-queued its own
  startup work (`pending` 34 after 60 s), so the soak never measured. The startup is the
  state opening a plan gives the workspace. The livelock it hid was real: a sink reset (a
  fresh engine or a recovery after a sink failure; the document path clears the queue
  itself) forgets every Model, and an in-flight forge
  completion then called `replace_geometry` for an item the sink no longer held — it raised,
  the workspace re-queued it, and the cycle repeated (clear, reset, queue again, fail
  again). `Scene3DController` now emits `scene_reset` on every reset, the workspace clears
  the Plant Forge queue, and `ForgeWorker` drops a completion whose item the sink no longer
  holds. Pinned by `test_a_reset_tells_the_forge_that_the_sink_is_stale`,
  `test_a_completion_that_crosses_a_sink_reset_is_dropped` and the existing sink-recovery
  test. Measured on the RTX 4070 (2026-11-05): the flood-release soak with the ground bake
  on read 3.03 MB/reload over 20 releases (1,396 frames presented, 20 releases); the churn
  variant with the bake off read 1.70 MB/reload (GPU slope 2.24 MB, 20 releases). Both
  were `['step EXCEPTION']` with `pending` 34 before.
- **The probe pin is sized for its camera (#704).** `--analysis` places its magenta pin
  on the nearest open ground whose WHOLE height is clear; the height is the product's
  dome share raised until the pin shows at least 60 px (the board's gate is 50), capped
  at 4×. On `bench_built`'s noon camera the old search's point read 38 px and the board
  raised before writing any sun-hours row; the whole-pin search's point, with the pin
  raised to 207 cm (4× the 52 cm share), reads 250 px (RTX 4070, 1280 × 720). The pin's
  position is still a measurement of the ground, not of the pin.

## Addendum (#701 — the shadow walk's roof meshes are cached; the per-owner union stays)

**Context.** `collect_identified_casters` projects every caster's pitched roof from its
3D structural triangles (#440). `_building_roof_triangles` built that mesh per item, per
walk: a 150-shed plan asked `roofs.gable_roof` for the same shed 750 times across five
collections (150 per collection; 600 of them repeats), and `_union_int` spent
1.48 s on 153 pyclipper unions. The sun-overlay test's first `waitUntil` then timed out
on a slow runner — a 150-shed plan blocked the GUI thread for seconds on every sun or
heatmap refresh.

**Decision.** `_cached_roof_triangles` (a 64-entry `lru_cache`) keys the **local**
triangles by kind, outline shape, ring (rounded to 10 nm), height, roof style, pitch,
overhang and ridge. A changed roof is a new key, never a stale hit; the caller poses the
same local triangles for every identical building. Measured: one mesh build for 150
identical sheds (`test_identical_buildings_build_their_roof_mesh_once`), and no second
build on a repeated walk.

The walk's per-owner `_union_int` was investigated as the other half and **kept**: with
the per-owner unions removed, the final union of all 3,750 unmerged roof-triangle paths
cost 3.25 s against 1.48 s for the whole 153-union profile — the per-owner union is what
keeps the global union small. `owned_shadows` has no production reader, but removing its
unions is a pessimisation, not an optimisation. Recorded so the next attempt starts from
the measurement.

## ADR-059 addendum: the 3D showcase follow-ups (#941, #943, #954, #955, #960, #992)

**Status**: Shipped in [v1.41.3](https://github.com/cofade/open-garden-planner/releases/tag/v1.41.3) after owner acceptance (2026-11-23; [PR #998](https://github.com/cofade/open-garden-planner/pull/998)).

**Context**: the independent 3D review of the bundled examples (#940) found looks that
were fixed values rather than the plan's own: one multiplier per channel turned green
crowns olive and salmon in autumn; a lawn and the meadow kept one green all year; a
stone-filled polygon was a flat concrete block; moss was a bright lawn; a sand court had
no rake; a tall timber fence was a picket fence; a Scots pine was a spruce cone; and at
Ultra a window pane was flat blue while the water reflected. The fixes must not move the
sun, a shadow, a footprint or a saved file's version.

**Decision**:
1. **Two-anchor autumn.** `PhenologyState` carries the summer and autumn palettes' dark
   (`b0`) and light (`t1`) linear anchors (`FR-3D-PLANT-07`, `PF-L3D-39`);
   `foliage.frag`/`foliage_door.frag` and falling leaves (`phenology.map_autumn_leaves`)
   apply the same two-anchor ramp (#941, #895) while the shader multiplier carries snow
   dust only (`foliage_snow_tint_linear`).
2. **The grass through the year.** `phenology.seasonal_ground_tint(date, latitude)` is the
   one sRGB lawn/meadow multiplier (`FR-3D-GROUND-09`), quantised by default on a shared
   4-day seasonal grid (`LAWN_TINT_STEP_DAYS`) so year playback avoids daily tile re-bakes
   while keeping baked lawns and the open-ground meadow bit-identical, time-lapse steps
   smooth, and summer exact. A
   grass lawn's fill is scaled in the snapshot (`snapshot._seasonal_fill`), while MOSS lawns
   stay evergreen; the open ground reads `meadowSeason` in `ground.frag` in sRGB before
   `groundLinear()` across every surface mode, eliminating any lawn-to-meadow colour-space
   seam. Covered surfaces stay untouched. `snapshot_records(..., latitude_deg=)` is additive,
   `Scene3DController` supplies `plan_latitude`, `Workspace.location_changed` dirties baked
   lawns on a hemisphere flip, and `offscreen.render_records` wires `set_meadow_season`
   alongside `forge_scene_plants`.
3. **A rock is a stone polygon's 3D form** (`surfaces.rock_parts`, `FR-3D-BUILT-10`):
   a low upright base (15 % of the height) and a domed top for convex stone polygons with
   a height; the widest ring sits at the ground, and a per-record ring-scale jitter
   (0.92–1.0) keeps the rocks distinct while staying inside the footprint. Concave or
   hostile outlines keep the prism. `GENERIC_POLYGON` joins the surfaces family so the
   builder is registered once.
4. **Materials with a look of their own.** `PathFenceStyle.BOARD_FENCE` (`FR-3D-BUILT-11`,
   exposed dynamically in `PropertiesPanel` from `PATH_FENCE_STYLES`), evergreen MOSS
   cushions and raked SAND surfaces (`FR-3D-BUILT-12`; 2.4 cm ridges 1.5 cm high on the
   13 cm pitch), Japanese maple / Scots pine / dwarf palm refinements
   (`FR-3D-PLANT-05/-06/-08`; the pine's recorded 6 cm needles cover each branch to its
   tip — the crown-area budget may lengthen them, not widen them — and the wood stops at
   85 %), and pergola-rafter climber training
   (`FR-3D-BUILT-13`, capping overhead vine height at the pergola deck).
5. **A window pane at Ultra** gets `vcGlass` (`built_snow.vert` + `glass.frag`, warmed in
   `shaderWarmer`): `MAIN()` sets `ROUGHNESS = uSsrRough` (`0.38` only while `ssrVisible`,
   `0.70` otherwise) and linearises `uTintSrgb` via `engineLinear()`, while `IBL_PROBE()`
   samples `qt_sampleGlossy(..., uRough)` at the #883 `0.70` flicker floor. Metalness stays
   0. Translucent greenhouse glass (`glassPart`, `NeverDepthDraw`) stays excluded from SSR.
6. **Hedges keep their density** (#954): a hedge's leaves are capped at 600 a metre of
   run (including the closing edge of a closed `HEDGE_FENCE` loop, and half-perimeter run
   length for polygon hedges — a strip polygon counts both sides), with a 30,000-leaf
   plan-wide budget shared by demand. The
   two bench plans grow 30,606 and 71,614 triangles; their build medians remain under
   40/60 ms, and the plan triangle tripwires are raised to 35,000/80,000 with those
   measurements.

**Alternatives rejected**: keeping the one-multiplier autumn (no single multiplier gives
a clean palette; reference 018); storing the season in the plan (the plan date already
drives every dated surface); a texture on the hedge core instead of more leaves (no
material path for a foliage-textured solid, and the issue's measured target is the leaf
coverage); raising the hedge leaf budget without a plan cap (unbounded triangles); a
second autumn field for the shader (the anchors already carry the palette).

**Consequences**: no `FILE_VERSION` change; one additive plan key (`weather`, ADR-070
addendum) and one additive tour field value range (`turns`, ADR-072 addendum). One new
shader (`glass.frag`) ships in the bundle. The plan-wide hedge budget is a new
performance bound; its evidence is `tests/perf/test_scene3d_built_world_budget.py`.
A CustomMaterial's uniforms are declared per material, not per shader: every material in
`Garden.qml` (warmers included) must declare every `u[A-Z]...` uniform referenced by its
bound vertex and fragment shaders and declare no dead uniform; this contract is now
statically pinned by `tests/unit/test_quick3d_qml.py::test_every_custom_material_declares_every_uniform_its_shaders_use`
in addition to the frozen `--selftest` and `Render 3D` runs.
Pinned by `tests/unit/test_phenology.py`, `tests/ui/test_quick3d_host.py`,
`tests/integration/test_scene3d_snapshot.py`, `tests/unit/test_scene3d_rock.py`,
`tests/unit/test_scene3d_l4_surfaces.py`, `tests/unit/test_scene3d_builders.py`,
`tests/unit/test_scene3d_materials_and_built_polish.py`, `tests/unit/test_quick3d_qml.py`,
`tests/unit/test_quick3d_packaging.py`, and the Japanese garden's example gate.

**Round 2 (independent 3D review, 2026-11-23, PR #998)**: the first build's Japanese
garden still read as a willow with bare brown spokes, plain paving and pale concrete
bollards. Three P1s were fixed at the source: the pine's needle spray now covers each
branch to its tip (the wood stops at 85 %, the needle is recorded at 6 cm with width
ratio 0.18 — the crown-area budget may lengthen it, not widen it — and the umbrella is
broad to 80 % of the crown); the rake is 2.4 cm wide and 1.5 cm high
with 1.0/0.78 shade bands on the 13 cm pitch; and a rock starts at a 15 % base with its
widest ring at the ground, rings at 42 % and 78 %, and a per-record 0.92–1.0 scale jitter
so the three example rocks are not clones. The lesson is the same for all three: a
relief or profile that is correct in centimetres can still be invisible or wrong at the
product's default framing; judge it on a rendered board, not on the builder's numbers.
The sand court's cut-outs now come from the same context pass as a lawn's
(`_lawn_cutouts` serves a SAND surface too), so the moss islands painted above it stop
the rake and no tan ridge crosses a green cushion. The owner's manual pass then caught
the same class of defect at a stepping stone: the canvas paints a stone centred on the
path's end, so its picture reaches 0.4 widths past the footprint while the cut-out was
only the footprint, and the rake ran across the painted stone. A first fix cut the
rounded stroke, which hid the rake but exposed the flat painted stone and cut a
corridor-shaped notch through the court, because the 3D relief had been slid 0.4 widths
onto the path. The final rule treats the stones as the path's painted surface: the 3D
stones mirror the 2D painter's walk exactly (the end stone stays centred on the end), and
the lawn/rake cut-out is each painted stone, not the path's footprint, so grass grows
and the rake runs between the stones. The winter tint's darkness,
the moss cushion's flatness and the board's hero camera outside a tall screen stay
recorded P2/owner questions.
