## Case study: a dormant optimisation, the measurement that killed it, and a fix that was the wrong fix twice (#503, 2026-10-17)

**Symptom.** Nothing. The LOD flat fill's comment and tests say it fires below 0.4 zoom during
interactive painting; the product never showed it. The issue was measured by review, not by a
failure.

**Wrong theories.** That the threshold was the problem; that the polygon-bound fix had already
covered "the same trap" because its issue said so; and - the one that cost the most - that
"the cheap correct fix is one discriminator", so deleting the branch was dismissed as losing
#409's design intent rather than repairing it. That reasoning was reasonable, unmeasured, and
wrong: the branch was carried to production on the strength of an argument about a guard rather
than a number about the workload.

**Evidence, in two rounds.** Round 1 - reachability. A real `CanvasScene` + `CanvasView`, one
textured `GARDEN_BED` rectangle: `should_use_lod_flat_fill` is called once per paint with **no**
widget at `fit_in_view` and after four `zoom_out()`s, and returns `False` every time; a
`NoCache` control item - a state no unselected canvas item is ever in - sees a widget and
returns `True`. Keying the guard on the cache mode made it fire: a rendered-pixel measure
(fill-intensity spread of a deep-blue tint over the roof-tile texture) went **13.61 -> 0.00** at
0.25 zoom, with textured controls at 20.1.

Round 2 - the question reachability cannot answer. Measured on the reference plan the branch was
written for (990 scene items, 1600x1000 view, seven rounds of fifteen repaints), both scenarios
below the 0.4 threshold: `fit_in_view` at zoom 0.316 read **10.61 and 11.50 ms median with the
flat fill disabled, 10.87 ms with it live** - the arms' ranges overlap entirely; `zoom_step` at
0.348 read **7.97 / 7.98 ms disabled, 8.20 ms live**. All six `tests/perf/test_nfr_budgets.py`
cases pass with the branch stubbed to `return False`, worst reading 12.21 ms against the 16.70 ms
budget. The reason is structural and was visible in the code all along: `DeviceCoordinateCache`
rasterises a textured item **once** and every later frame is a cheap blit, so the expensive
textured `paint()` the LOD existed to avoid was already amortised by the sibling fix from the
same PR. The branch could only pay per *cache regeneration*; the acceptance metric is
steady-state repaint.

What the measurement establishes is that the effect sits **below this harness's noise**:
within-arm variation is 8 % against a 0.26 ms between-arm difference, and no reversed-order run
was taken, so no claim about which arm is faster survives. An earlier single-pair reading
(10.58/10.64, 8.21/7.40) is **superseded** - it put the `zoom_step` sign the other way round, and
a draft of this very case study asserted the ordering it implied and was wrong on its own
numbers. *A conclusion drawn from one ordering of a noisy measurement is the same class of
mistake as a guard whose condition was never true: both are confident and both are unfounded.*

**Root cause, twice over.** The `widget is not None` idiom, for the third recorded time (#472's
first draft, then the LOD guard, then #472's suite) - Qt passes `widget = 0` for every
*cached* paint and every unselected canvas item is `DeviceCoordinateCache`, while the tests
called the helper directly with a fabricated widget. And beneath that, a second defect no guard
could fix: the branch's *premise* was never tested. It assumed the textured paint was a
per-frame cost, and the cache that shipped beside it had already made that false.

**Fix.** Deleted: `should_use_lod_flat_fill`, `get_lod_fill_color`, `LOD_FLAT_FILL_THRESHOLD` and
seven call sites across the rectangle, circle, ellipse and polygon items. Kept:
`is_interactive_paint`, which the #472 paint bound needs for real (a cached 1,024-vertex comb is
44.7 ms at full detail, 589 ms at 16,384); its docstring now says it classifies paints and does
not decide detail. `tests/integration/test_canvas_item_cache.py` (renamed) renders a textured,
tinted `RectangleItem` through a real `CanvasView` at five zoom levels plus the export path and
asserts the texture's luminance spread survives - **lower bound only**, so a future change may
soften a texture but cannot delete it. Re-introducing a `< 0.4` flat fill fails the 0.1, 0.25 and
export cases.

**The sibling suite's part, in both directions.** With the branch live,
`tests/integration/test_polygon_paint_bound.py` failed 3 of 12: its below-budget polygons carry
`LAWN`'s pre-seeded `GRASS` pattern and a *test-only* magenta brush, so at the harness's
fit-in-view zoom (0.35 < 0.4) the canvas now *correctly* painted the designed flat fill and the
magenta count went to zero. The harness was moved to 100 % zoom and a low-zoom seam pair was
added. When the branch was then deleted, **all of that work was reverted** - the suite is back to
its pre-#507 state in full. A seam test for a deleted feature encodes the deletion as a contract.

**The pin took two rounds and was vacuous for most of it.** The replacement is
`tests/integration/test_canvas_item_cache.py`, parametrised over rectangle, circle, ellipse and
polygon, each rendered through a real `CanvasView` at five zoom levels plus the export path, with
the interior sampled from the item's own `QGraphicsItem.shape()` rather than its bounding box: the
box's corners are page background for three of the four shapes, so a *solid* circle measured as
high-contrast and the pin passed while the branch was firing. Then two further holes. The seven
deleted call sites were not seven instances of one thing - two sat behind `if is_plant` and two
behind `if is_furniture_type`, which a `GENERIC_*` fixture never enters, so four shapes watched
four of seven and the three unwatched were exactly the sprite paths; a flat fill in a plant branch
took a `TREE` circle from interior std 43.09 to 0.00 while 212 tests in the repo stayed green.
And the export mask applied the render scale but forgot the `-source.topLeft()` translation
`QGraphicsScene.render` composes in, so the circle's export case passed at spread 45.97 with a
flat fill live and read 1.67 once aligned. All seven sites are caught now, mutation-verified per
site, and `TestTheMaskIsTheItem` asserts the invariant every other test silently depends on: the
masked interior must be measurably darker than the page behind it. The calibration tells the same
story from the other side - the four textured shapes' export column *converges* on 15.47-16.02
once aligned, where the displaced mask gave 15.83 / 37.27 / 49.85 / 16.37.

**CI's part, and the lesson it bought.** The first pixel regression found its sample region by
matching blue-ish pixels image-wide, and the Linux/offscreen CI failed it at spread 62.59 (Windows
measured 0.00) because the scene's faint background passed the filter. One red CI job taught the
rule that then had to be re-taught twice more: *a sampler that reads background does not fail - it
reports the contrast between background and fill, which is precisely what the statistic was built
to see.* Sampling must be computed from geometry and checked, never discovered from the pixels.
cannot fail for being small rather than wrong. One red CI job bought that lesson.

**Lesson.** Reachability is necessary, not sufficient - before promoting a dormant path, ask
whether it earns the degradation it costs, on the workload it was written for, and treat a
number you have not taken as an argument you have not had. "The cheap fix is one shared
predicate" was true *as a repair of the guard* and wrong *as a decision about the feature*:
fixing the guard is what made the feature's cost visible, and the cost is information. Deleting
a feature leaves no test that fails when it returns, so replace its tests with a negative pin
rather than dropping them. And when a fix makes a dead branch live, run the sibling suites - then
be willing to revert the collateral if the branch does not survive.

