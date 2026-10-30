# Archive 07: Phase 17 L1.5 ground bake

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.17 What the ground bake taught (Phase 17 L1.5, #385)

Each of these was measured while the bake (§8.29.5) was built or reviewed. The first section is
about the 2D APP: defects of the shipped canvas and project file that painting the same items a
second way brought to light. Three of them `master` fixed on its own while L1 was in work — the
loader's attributes (#438 / #469) by #502's `restore_stored_look`, the offset copy's look (#470)
by #501's `copy_visual_style` — and since the sync of 2026-10-19 the L1 branch uses master's
mechanism there (its own loader writes and its own copy helper are gone). The others were fixed on
the L1 branch, pinned in the 2D suites — each by a test that fails with master v1.30.13's code at
that place — and reached `master` with L1 in v1.30.14 (PR #484); v1.30.13 still has them.

#### 2D defects the bake found

**An item states its look twice, and nothing kept the two in step.** `fill_color`,
`fill_pattern`, `stroke_color`, `stroke_width`, `stroke_style` (`GardenItemMixin`) are what the
project file, the clipboard, the properties panel, the Agent API and (until #503 removed it) the
paint below 40 % zoom read; the live `brush()` and `pen()` are what the canvas paints. Every writer that set one half
was a defect nobody saw on the canvas:

| writer | what it left behind | what the user lost |
|--------|---------------------|--------------------|
| the project loader, rectangles (`core/project.py`) | the brush set, `fill_color` at the type's default | **a recoloured rectangle was written back in its type's default colour by the next save** — measured on `master`, load → save → load of `#ffc81e1e`: `#ff90ee90` (GENERIC_RECTANGLE), `#ff64b43c` (LAWN), `#ffdeb887` (TERRACE_PATIO), `#ff8b5a2b` (GARDEN_BED); the same wrong colour in the clipboard, in the Agent API's read and on the canvas below 40 % zoom. **Fixed on `master` by #502** (`restore_stored_look`); the L1 branch takes that fix |
| the project loader, rectangle / circle / ellipse / polygon | the pen set (colour, width and dash style all survive load → save → load), `stroke_color` / `stroke_width` at the type's defaults (`stroke_style` was set) — measured for `#dc1e50c8`, 7.5: the attributes read `#ff228b22` 2.5 (GARDEN_BED), `#ffdb7093` 2.0 (GENERIC_CIRCLE), `#ffc88c00` 2.0 (GENERIC_ELLIPSE), `#ff3c821e` 2.0 (LAWN) | the properties panel showed the type's default stroke colour and width of a loaded item; a command that takes its "old value" from the attribute puts the default back. **Fixed on `master` by #502**; the L1 branch takes that fix |
| the project saver, polylines | no `stroke_style` written | **a dashed line came back solid** (`DashDotLine` → `SolidLine`; its colour and width survive) |
| the project loader, polylines with a style preset | the saved stroke read for style NONE only | **a restyled path's own colour and width came back as the preset's** — a gravel path saved with `#dc1e50c8`, 7.5 loads as `#ffb4aa96`, 8.0, and the next save writes that |
| the offset tool (polygons, polylines), the chamfer and fillet tools, `PolylineItem.clone_with_points`, the trim tool's results | brush and pen copied, the attributes at the type's defaults | **the copy changed colour and pattern on save** (an offset copy of a blue brick terrace: default wood); in 3D it was baked as the default at once. The offset tool (and mirror) **fixed on `master` by #501** (#470, `copy_visual_style`, which also gave an offset rectangle, circle or ellipse its source's look); chamfer, fillet, `clone_with_points` and trim fixed on the L1 branch through the same module (#441) |
| `PolylineItem.__init__` / `_setup_styling` (found by review 2) | the pen built, the stroke attributes `None` until the line had been through a project file | **undo raised on a freshly drawn line** — in the shipped app: a stroke-width edit undone `TypeError: setWidthF(NoneType)` (the pen stays at the new width), a dash edit undone `AttributeError` (the pen stays dashed), a type change in the properties panel undone `TypeError` (the type goes back, the pen stays the new type's). The same line behaved after a reopen. Still in master v1.30.13: #523 |
| the properties panel's `_apply_item_state` (the undo and redo of a type change) | the attributes set, overwritten by `apply_style_preset`, then the pen built from the state | a re-stroked preset line after the undo of a type change: pen 12.0, stated 8.0 |
| `GardenItemMixin._dispatch_change_type` on a line (the context menu) | the attributes set from the state, the pen built from the TYPE | **undoing a context-menu type change reset a re-stroked line's pen to its type's** — a fence of 7.5 dashed came back 3.0 solid, stating 7.5 dashed |
| the project loader, all four filled shapes, for a file with a fill colour and NO fill pattern | the brush the constructor made recoloured — which does nothing to a texture — and the attribute set | **the picture changed across a save**: first the type's texture at the type's tint, after save and reopen at the saved colour (the middle of a lawn: (79, 144, 54) → (111, 97, 44)). On `master` for circles, ellipses and polygons; for rectangles since round 1 of this story |

*Fix:* one module, `core/item_look.py` — `master`'s since #501, with this branch's helpers added
in the sync of 2026-10-19 (the branch's own `core/item_style.py` is gone): `copy_visual_style`
(`master`'s) carries a look from item to item, `restore_stored_look` (`master`'s) writes a loaded
item's attributes, `adopt_pen(item, pen)` sets a pen together with the attributes that describe
it, `fill_brush` builds a fill in the item's own pattern, `style_gaps(item)` says where an item's
two statements part; every writer above goes through them — a line states the pen it is built
with, and `_setup_styling` builds a line's pen from the stroke it STATES, as the filled shapes
always did — and the saver writes a polyline's dash style when its pen has one. Merged, two
things met: `master`'s `copy_visual_style` copies the source's ATTRIBUTES as they are where this
branch's had read the stroke off the pen, so a source a test built out of step now hands its gap
on (one older test, `test_fillet_chamfer.py::test_fillet_arc_inherits_host_pen`, gave its host a
bare `setPen` — it uses `adopt_pen` now); and `restore_stored_look` raised on a saved stroke of no
kind (`null`, a list) before the branch's validated preset stroke ran, so a preset line with
`"stroke_width": null` was SKIPPED on the integration branch (and is on master v1.30.13: #527)
— it now leaves such an attribute alone (pinned: `TestAFileTheAppDidNotWrite`, whose `null`
cases fail with master's version).

*Guard for the class, not the instances — and the first guard was not one.* Round 1 guarded the
class by reading the source: an AST scan for functions that build an item from an item (a
"census"). A review planted six forgetful operations and the scan saw ONE: it knew the keyword
spelling `object_type=item.object_type` and two folders, and missed the type through a local, a
constant type, a `type(item)(…)` factory and a brush held in a variable. Its docstring said a new
tool "cannot ship without" the rule. The guard is now BEHAVIOUR: a teardown fixture
(`tests/integration/conftest.py::_every_item_says_what_it_paints`) tracks every `CanvasScene` an
integration test builds and fails the test if an item in one of them has `style_gaps(item) !=
[]`. Run over the folder for the first time — the four product writers of the table's last rows
already fixed — it failed 167 tests, every one for a hand-made `setPen` or `setBrush`: 31 call
sites in six test files and in the generator of the edge-case plan that built items no user can
make (a line that states its stroke is put out of step by a bare `setPen`). They go through the
helper now. Its first PRODUCT finding came with the first test that drove a type change on a
line: the line then states its new type's fill — a transparent grey — beside the transparent
black brush every line paints with. Both paint nothing, and the predicate now says so. With any
one of the four product fixes taken out again, the fixture fails the tests that drive that
writer (the round's mutants). `tests/integration/test_item_style_in_step.py`
keeps the operations by name (clipboard / duplicate / the four arrays, mirror, offset, chamfer /
fillet, trim, `clone_with_points`; the fresh line and its undos; hand-made files) and tests the
guard's teeth with the six planted operations; the scan is kept as a map of the derivation sites.
`tests/integration/test_item_roundtrip_matrix.py` pins load → save → load of a recoloured,
patterned rectangle for eleven object types and of a re-stroked item of every shape.

*One kind of item is exempt:* an item whose picture is a sprite (`GardenItemMixin.paints_sprite`
— a furniture rectangle, a plant or furniture circle). It draws its sprite and asks neither brush
nor pen for the picture; its pen is `NoPen` when it is built and a solid black 1.0 once it was
loaded (the saver writes the pen's colour and width, the loader gives the pen the saved
`stroke_style`). So `style_gaps` does not judge a sprite at all (first only its stroke half; the
fill half too since the sync, when `master`'s own `test_canvas_item_cache.py` gave three sprites a
texture brush they never paint), and `adopt_pen` does not write a sprite's stroke attributes from
a pen. What a LOADED sprite states is `master`'s rule since #502: what the file holds — that black
1.0 (round 1 of this story had read it off the pen; review 2 had asked for the type's stroke,
which `master` then decided otherwise). The owner kept `master`'s rule at the L1 pull request
(2026-10-19).

*Not changed, and inconsistent:* undoing a preset pick in the properties panel returns the style to "none" and leaves the preset's pen (a path of
`#ffa0522d` 5.0 stays `#ffb4aa96` 8.0; #524). The two ways to change a line's type disagree on a
preset line — the context menu keeps the preset's stroke, the panel gives the new type's — and
the context menu's undo gives a re-stroked preset line the preset's stroke back, not its own
(#525). A type change in the panel builds a new pen: a line's round caps and joins are square
and bevelled until the plan is reopened (#526). *Lesson:* an attribute that mirrors a Qt object's state is a
second source of truth; a second consumer finds where they parted — and the fix is one writer,
not one more reader. *And:* a guard that reads the source knows the spellings its author knew;
judge the objects a test leaves behind.

**A loader that starts to read a field must say what it does with a value it cannot use.** Round
1 made the loader restore a preset line's saved stroke; until then that field was not read for
such a line, so ANY value loaded — at the preset's stroke. Read unvalidated, a hand-made
`"stroke_width": null`, `"8"` or `[8.0]` and a `"stroke_color": null` raised, and the item was
skipped — gone after the next save; 0.0, -3.0 and 0.01 loaded as given, `"notacolour"` as black.
For a preset line a width that is no finite number of at least the panel's minimum (0.5) and a
colour Qt cannot read now keep the preset's value, each on its own, and nothing raises
(`TestAFileTheAppDidNotWrite`, 21 cases). A fully transparent colour is a colour — the panel's
own dialog offers the alpha channel — and loads as given. *Not changed:* a PLAIN line and the
four filled shapes apply a saved stroke as found, as `master` does: `null`, `"8"`, `[8.0]` and a
`null` colour skip the item; 0.0 and 0.01 load as given. And since `master`'s strict numeric plan
I/O (#453, `core/plan_io.py`) a width that is infinite, not a number or an integer no float holds
refuses the whole DOCUMENT before any item is built — for every shape
(`test_a_width_no_finite_number_can_hold_refuses_the_whole_plan`).

**Qt fills an open path with the brush that happens to be set.** *Symptom:* a bent boardwalk and
a bent stone wall filled the whole inside of the bend with one colour — over their own planks
and stones, out to the chord between the line's ends (measured for lines with legs of 3 m: up
to 66,449 px beyond anything the style draws).
*Root cause:* the rails and borders were stroked with `drawPath` while the brush of the last
plank or stone was still set; `drawPath` fills. *Fix:* `setBrush(NoBrush)` before the rails
(`path_style_paint.py`). A deliberate change of the 2D picture: of 528 renders through the real
`PolylineItem.paint` (11 styles × 3 shapes × 2 widths × selected or not × 2 scales × turned or
not) 464 are bit-identical to `master`, the 64 that differ are the bent boardwalk and stone wall.
Pinned on the canvas, not only in a 3D test: `tests/integration/test_polyline_style_paint.py`
(nothing beyond a style's reach; away from its bend a bent line is the straight line).

**The style painters cost every plain line a little.** Moving the ten painters out of
`PolylineItem.paint` (so that canvas and ground share them) first made EVERY paint build a
`PathStylePaint`, a copy of the line's points and a ten-entry table — also for style NONE, most
lines of a plan. Measured, interleaved, 100 plain three-point lines: 10.4 µs a paint on `master`,
13.1 with the object, 10.7 once a plain line builds nothing (`STYLES_PAINTED`). The 500-object
reference plan of NFR-PERF-01 holds no line at all, so its repaint numbers could not show it.

**Seen and not changed.** The live canvas paints an item through its device-coordinate cache,
which cuts whatever a path style draws beyond the item's `boundingRect()` (line + half a width
+ 2 cm): the bars of a metal fence reach 1.25 widths from the line and are cut at 30 cm width
(37.5 cm against 17 cm); an export paints without the cache and shows them whole. And a COMB
polygon — every tooth across the item — costs the canvas 10.5 s (1,024 vertices), 38 s (4,096)
and 186 s (16,384) for ONE paint: a plan file can freeze the 2D view.

#### The bake itself

**Adding 2,000 items to the scene one by one takes 45 s.** `CanvasScene.addItem` refreshes the
stacking order per item — quadratic. A plan file is loaded inside
`scene.suspend_z_refresh(renumber=True)`; a test that builds a large scene must do the same
(3.9 s). Not the bake's cost, but it looked like it.

**A line up to a pixel wide is rasterised per device.** Qt draws such a pen with its cosmetic
stroker, which clips the line to the image and then steps along it from the clipped start. A
tile is another image than the whole plan, so single pixels of a hairline differ (mean ≤ 0.016,
one pixel up to 142 of 255) — and nothing wider does. For the same pens a dash pattern AND its
offset are in **pixels**, not pen widths (measured for 0.25 to 1 px pens; offsetting a run in pen
widths puts its dashes elsewhere).

**Qt's dasher, handed a line that leaves the image, puts the dashes somewhere else.** It skips
what lies outside the device — cheaply: 19 km cost what 100 m cost — but the dashes it then draws
inside were measured off: over 9.5 km it agreed with the arithmetic at 261 of 393 places; for a
10 × 6 m dashed rectangle baked as six tiles 640 pixels differed from one whole render, for an
ellipse 7,564. *Fix:* the bake cuts a dashed line to the tile itself (`_runs_inside`) and strokes
each run with `setDashOffset(start / unit)`: 393 of 393, and 0 differing pixels for the
rectangle. An outline that lies wholly in one tile is drawn with the canvas's own call.

**An attached `QQuick3DTextureData` cannot be updated in place.** `setTextureData(new)` +
`update()` on a texture a `Texture` shows changed nothing on screen — also with
`textureDataNodeDirty` emitted by hand, and with the `Texture`'s property set to null and back in
the same turn (three variants, each rendered; the first picture stayed). A fresh object shows.

**… and a `Texture` element must never be pointed at a SECOND texture: the tile goes white.**
*Symptom:* the first run of the time budget on a real engine painted the plan over fourteen
transactions — and most tiles came out WHITE. *Wrong theory:* "a replaced texture was let go
before the scene had shown its successor; keep it one frame longer." Keeping it longer only moved
the white tile one frame later. *Measured* (RTX 4070 and WARP, Qt 6.11; two tiles, each sequence
ending in a frame, and one more frame after the replaced textures were let go):

| what was done to a tile | the frame after | one frame later |
|-------------------------|-----------------|-----------------|
| re-textured twice, no frame between | right | right — or white, when the replaced textures were let go after the frame |
| re-textured, then the OTHER tile re-textured, then a frame | **white** | white |
| re-textured, a frame, the replaced texture let go (what a presenting window does) | right | **white** |
| the same, with a new Model for every re-textured tile | right | right |

*Root cause:* when a `QQuick3DTextureData` that a `Texture` element once held is destroyed, Qt
resets that element's `textureData` to null — whatever it holds by then. The QML binding
`textureData: tileData` does not run again (its source did not change), so the tile is drawn
without a texture until its property is set once more. *Why nobody saw it:* every scenario of
the first delivery re-baked, took a frame and re-baked the SAME tiles, which sets the property
again; and its hardware window presented no frames, so the release after a frame never ran. In a
window that presents, every edited tile was white one frame after its edit, and an edit elsewhere
turned the tiles of the edit before it white. *Fix:* ONE TEXTURE PER `Texture`, FOR LIFE — a
re-baked tile is a new Model with a texture of its own, and its old Model is destroyed
(`quick3d/ground_tiles.py::_replace`). *Pinned:* five sequences on the render tier, each judged
right after its last update and again one frame later
(`test_scene3d_ground_render.py::test_a_re_textured_tile_keeps_its_picture`), and the budgeted
open against the one-pass ground, bit for bit. *Lesson:* "the object is alive" is not "the scene
shows it"; a test that always re-does what it just did cannot see what the second thing broke.

**What grows a Direct3D 11 process is `grab()` in a window that presents nothing — not the
re-bake.** *Symptom:* twenty full re-bakes of a 16 MB ground grew the process's private bytes by
16 MB each, although every replaced texture object was destroyed (two generations alive, never
more). *The first diagnosis was half right and its remedy wrong:* "Direct3D keeps every upload
while no frame is presented — apply edits no faster than frames are presented." The soak that
measured it called `grab()` after every re-bake. *Measured again, the same twenty re-bakes on the
RTX 4070 while its window presented 0 frames:*

| in the measured loop | private bytes per re-bake |
|----------------------|---------------------------|
| no `grab()` — what a live view does | **+0.00 MB** (the review); −0.10 and +0.01 MB (this box, two runs) |
| a `grab()` every fifth cycle | +3.2 MB (the review) |
| a `grab()` every cycle | **+16.1 MB** (the review); +16.1 and +17.4 MB (this box) |
| any of the three on WARP, 33 to 41 frames presented | flat (+0.01 to +0.19 MB) |
| a `grab()` every cycle on the RTX 4070, 38 frames presented | flat (+0.04 MB) |

*Reading:* Direct3D frees what was released when a frame is PRESENTED; a frame rendered by
`grab()` is rendered — its textures are uploaded for it — and never presented. So the growth
belongs to the grabbed frame: one generation of whatever changed since the last grab. Without a
grab nothing is rendered in a window that presents nothing, and nothing is uploaded. Pacing edits
changes nothing, and an agent-driven session that edits without grabbing does not grow. Why that
window presented no frame is NOT established: an OpenGL window on the same GPU presented 45
frames in the same session, so "the display was asleep" does not explain it.
*What follows:* (1) **the rule — no repeated `grab()` on a live host that is not presenting; a
screenshot goes through the offscreen path** (`offscreen.render_records`: a hidden view of its
own that is closed after its one frame, which gives everything back); (2) gate G6 measures what
a live view does — no frame in its loop, and since review 2 no call into the QML scene either —
and is UNCONDITIONAL on the machine's own adapter and on WARP; the grabbing soak is its
documented control
(`test_a_grab_a_cycle_is_what_grows_a_direct3d_window_that_presents_nothing`). *Lesson:* a soak
measures everything in its loop; before a growth is blamed on the thing under test, run the loop
without the instrument.

**… and a gate that cannot fail in one of its cells is half a gate.** "Flat on any adapter,
whether the window presents or not" was written from two measured cells: WARP, whose window
presents its frames (it renders, uploads and frees — flat), and the RTX 4070, whose window
presented NOTHING. Without a grab nothing is rendered in such a window, so nothing is uploaded
and nothing on the graphics side can grow: that cell shows that re-baking does not grow the
PROCESS side, and no more. A hardware window that presents its frames is not automated — it is
the owner's manual checklist item "watch Commit size while dragging a lawn with the display on" —
and the requirement says which cells were measured (FR-3D-GROUND-05).

**`frameSwapped` may never come.** The replaced textures are released when a frame was presented
— and, because that signal may never arrive, at the latest on the next ground update. A release
that only waits for the signal is the L0 spike's growing list again.

**A bound that keeps "the topmost N" drops what everything stands on.** With 256 pavers on a
lawn in one tile, the record `TILE_RECORDS` left out was the lawn: 138,240 px of a 5.12 m square
were bare meadow, one log line said so. The counts were all pinned; nothing asked WHAT was
dropped. The first fix — the walk ends at the first record that opaquely covers the tile, and
below the cut a tile keeps what covers it WHOLE — was pinned with a lawn that was the plan
rectangle, the one lawn that covers every tile whole, and passed. Ten centimetres inside the
plan's edge the same lawn was dropped again: 149,604 px bare, mean 24.4 of 255 against the canvas
(review 2). The rule is now stated by its outcome — a tile loses its SMALLEST records, ranked by
how much of the tile their paint box overlaps — and pinned for four lawns, three counts of pavers
and a real scene against the canvas (§8.29.5). *Lesson:* a rule worded as a mechanism ("keep
what covers the tile") can be followed to the letter and miss what it was for; state the
outcome, and test it on a geometry the mechanism was not written for.

**After a failure, "forget everything and start again" is not the safe choice.** A bake that
raised cleared the baker; the sink kept showing its sixteen painted tiles — until the next edit,
anywhere, re-baked from an empty baker under the time budget: ONE painted tile, fifteen passes to
refill, a traceback, and the same again for every edit while the failure lasted. A tile whose
paint fails now keeps its picture and its place in the books, and nothing else is touched; and
a bake that raises anywhere else RESTARTS the baker — books forgotten, pictures kept until each
tile is painted anew (§8.29.5). The first version of this fix covered only the raise site the
review had used (a tile's paint); the pin for "any other site" raises in the admission walk
instead. *Lesson:* test a failure path by what the user sees on the edit AFTER it, not by the
state right after the exception — and inject the failure in more than one place.

**Every cache release in Qt Quick 3D 6.11 keeps about half of the same-size tile textures —
OPEN (#532)** (L1.5 Part B, review 3). *Symptom:* with the ground bake wired in, the
workspace's G7 soak (twenty rebuilds of bench_small, ADR-060) grew dedicated GPU memory by
7.5 MB per rebuild with its release after quiet and by 19 with the release in the pass — 0.0
and −0.1 without the baker; two G7 gates failed (13.75 and 28.0 MB per rebuild against 10).
*Wrong theory:* "the tiles leak on a reset — `GroundTiles.clear()` lets their textures go
before a frame"; resets without a release are flat. *Isolated on WARP* (a 16-tile ground,
twenty cycles, private bytes per cycle): re-bake + `releaseResources()` each cycle +10.7 to
+13.3 MB; the same without mipmaps +7.4 to +8.7; re-bake alone 0.00; reset + re-bake alone
0.00; one release then twenty re-bakes +0.06; a release every fifth cycle a 10 to 25 MB step
at each release. (A control "new tile Models with the SAME textures + release −0.28" seemed to
show that it takes a re-bake; that control was broken — its frame was white, no texture ever
loaded.) *Root cause:* a Qt Quick 3D 6.11.0 bug, read in its source and proven by measurement
(#532): `QSSGBufferManager::clear()` walks `customTextureMap` with `++it` while
`releaseTextureData(it.key())` erases through its own lookup; Qt 6's `QHash` shifts the next
entry of a collision run back into the freed slot, `++it` skips it, and
`customTextureMap.clear()` drops the skipped entries unreleased. The key's hash covers only
size, depth, format and transparency, so same-size tiles all collide and about half leak per
release (WARP, 16 × 512²: +10.8 / +11.7 MB a cycle against a prediction of 8 × 1.333 MiB) —
static tiles too: every release leaks, re-bake or not. Tried and rejected: in-place updates,
distinct sizes (not flat at ≥ 32 tiles), `Texture.sourceItem` images. *The exposure:* the bake
never asks for a release (tile Models are not counted in `TickReport.retired` — they need
none), but every release the workspace makes for item changes leaks — 64 retired Models and
half a second of quiet, or 512 at once: a delete or regrow of that many, a document change, a
date change on a planted plan (every dated plant regrows). The largest ground (~4096² px,
~85 MB with mips) loses ~42 MB per release; bench_small's (19.5 MiB with mips) read
+9.3 to +11.4 MB of dedicated GPU memory per rebuild in eight runs of review 3. *Wrong first
answer* (a fallback taken before review 3, which replaced it): gate the leak with the bake OFF
and report the product against a "regression ceiling" of 60 MB per rebuild — the gate then
measured a configuration nobody ships, and a ceiling of about three grounds could not fail.
*State:* G7 measures the product (bake on) against the plain bound plus an allowance derived
from the soak's OWN ground (0.6 × tile-texture bytes per release × releases per reload,
§8.10.9); a non-strict `xfail` tripwire holds the GPU slope to the plain bound; the bake-off
run stays as Model churn alone. Whether 3D may become the default view while #532 is open was
the owner's decision (put to them with the measured exposure), not a roadmap blocker; they
shipped it at the L1 pull request (2026-10-19, ADR-060 addendum D5). The fix
is upstream Qt's (a report draft for the owner; filed on 2026-10-30 as
[QTBUG-151940](https://qt-project.atlassian.net/browse/QTBUG-151940), see §8.29.5 known limit 11
and TD-040) or a tile path outside the buffer manager's maps that also passes G7. The probe is
in the story's scratch (`probe_release_driver.diff`).
*Lesson:* a soak that passes alone (G6: re-bakes, no release) and one that passes alone (G7:
releases, no textures replaced) can both be green while their combination leaks — run the
product's own policy against the new kind of resource. And gate what ships: an allowance for a
known leak, derived from the run's own numbers, keeps the gate able to fail; switching the new
resource off, or a ceiling chosen by eye, does not.

**A slope estimator meant to ignore one bad reading does not ignore one STEP** (Ruling R41).
Theil–Sen — the median of all pairwise slopes — shrugs off a single outlier; a single step in
the middle of a window is not an outlier but a level change, and most pairs straddle it. G6's
WARP cell read +2.80 MB a cycle for a curve flat on both sides of one +20.6 MB step (bound 2.0;
re-runs +0.09, −0.01, +0.00). A leak is a property of every cycle, so the gate reads the median
of the per-cycle steps now (§8.10.10). *Lesson:* choose the statistic by the shape of the
failure it must reject AND the shape of the noise it must accept, and pin both with measured
curves.

**A flat item the solid path refuses is not "missing from 3D" any more.** The workspace's
problems list counted an in-ground bed traced with 6,000 points as not shown; with the ground
bake that bed is painted on the ground (FR-3D-GROUND-04), so the count — and a test that
expected it — changed with the merge (both stories' tests now trace a RAISED bed, which is
truly absent). *Lesson:* when one story makes something visible that another reports as
missing, the reporting side's test is the one that notices.

**A budget shared between new and old work starves the old.** One tile a pass, nearest to the
last edit first, and an edit before every pass: the edit's tile was painted, the budget was
spent, and 14 tiles stayed pending after 1, 5, 10, 20 and 40 edits — a drag over a just-opened
plan kept the rest of the ground bare for as long as it lasted. A call that brings an edit now
owes the backlog one tile.

**A painter that raises between `save()` and `restore()` poisons the next record.** A
stepping-stones path that raised at its third stone left the painter two levels deep, moved and
turned to that stone; the caller's one `restore()` popped the wrong level and the rectangle
painted next lost 5,476 of 44,104 px. Pose and opacity are now set absolutely for every record
and restored absolutely by `paint_record`, and a failing record's painter is ended and begun
anew. In the same place: a failure was cleared per TILE, so an item that failed in one tile and
painted cleanly in the next was reported as fine.

**A count is not a time.** The per-tile bounds are on counts, and Qt's cost per count spans three
orders of magnitude (0.7 µs a vertex for a wavy ring, 1.2 ms for a comb: 19 s for one record in
one tile). The first delivery stated "a tile at its bounds: 0.2 to 2.65 s" from the shapes it had
thought of. Only a time budget between tiles holds a pass to something, and it holds it to the
budget plus ONE tile — two when an edit arrives over a backlog (§8.11, §8.29.5).

**Qt paints the last row of a rectangle clipped to a narrow image one step lighter.** A lawn
over a 1100 × 700 cm plan, tile by tile, against the same lawn in one image: 76 values of the
76-px-wide last tile differ by 1 of 255. Tests that compare a tiled ground with an untiled one
allow that one step and say why.

**Four ways a bound can fail to bound** (the security passes; the patterns are §8.11):
a cap on VERTICES does not bound work that follows a LENGTH — two points 19 km apart are 475,001
gravel dots; a budget that charges what is handed out but not what is walked to find it lets 256
paths walk 20 million steps for a few hundred dots (charge the walk); `if budget:` treats a
budget of zero as "no budget" (a spent budget must mean "no more"); and a per-tile cap applied at
paint time sat behind bookkeeping that had already registered every record in every tile it
touched — 2,050,003 entries for 50,000 whole-plan rectangles, 55,201 once the tiles of a record
are four integers.

**PyQt notes.** `QQuick3DObject.update()` exists at runtime but not in PyQt6 6.11's stubs;
`markAllDirty()` is not exposed at all. A `QObject` subclass instance released by Python IS
destroyed on the C++ side (its `destroyed` signal fires) — count that, not Python's references.
`QPainter.end()` followed by `begin()` on the same image is the one way to drop saved levels a
failing painter left behind; there is no way to ask a painter how deep its stack is.
