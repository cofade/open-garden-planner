---
id: ADR-058
title: "The suite runs in parallel, and the timing tests do not"
status: "Accepted."
refs: ["#509"]
legacy_anchor: adr-058-the-suite-runs-in-parallel-and-the-timing-tests-do-not-issue-509
---

# ADR-058: The suite runs in parallel, and the timing tests do not

**Status:** Accepted.

**Context.** The full battery took 912.6 s serially on the development box and gated every
iteration between a change and the owner's hands-on pass. Three candidate causes were
separated by measurement, and only one of them is a scheduling problem.

The suite was **highly concentrated**: the median test took 0.030 s against a mean of
0.339 s (11.3×), and ten files of 228 held 57 % of measured call time. But the naive
reading of that table — "these files are slow" — was **wrong**. `test_iconography_3c.py`
alone runs 36 tests in 2.14 s; the same file immediately after
`tests/ui/test_main_window.py` takes 447 s, with individual theme tests at 60–66 s.
Probing `QApplication` directly: a clean process holds **0** widgets and one
`apply_theme()` round-trip costs **1.3 ms**; after `test_main_window.py` it holds
**38 271** widgets and **1 580** top-level widgets, **0 % of them visible**, and the
round-trip costs **22 478 ms**.

So the expensive tests were **victims**. Thirty apps leaked their widget graphs because
`qtbot.addWidget` *closes* a widget and closing is not deleting, and `apply_theme()`
walks `app.allWidgets()` on every call. Fixing the leak — one autouse fixture that
closes and `deleteLater()`s every top-level widget per test — took the serial suite from
912.6 s to **673.6 s** and flattened the distribution (slowest-50 share 50.9 % → 37.9 %;
mean/median 11.3× → 6.8×). It changes no product code and removes no test.

**One measurement detail worth stating, because the two halves of that pair come from
different runs.** The *before* figures are from the recorded serial run at `132f6715`; the
*after* figures are from the serial full-suite run immediately after the leak fix. They are
**not** comparable with a parallel run of the same tree, which measures 32.2 % and 20.7×
on the identical code: per-test call time inflates when tests contend, so one suite reads
620.6 s of call time serially and 1 700 s under `-n auto`. The distribution's shape is a
signal; its sum is a statement about the scheduler.
`docs/11-risks-and-technical-debt/audits/2026-10/test-suite-latency-2026-10.md` holds both runs and that
caveat.

**Decision.** `addopts` carries `-n auto --dist worksteal -m 'not perf'`, and
`pytest-xdist>=3.8.0` joins the `dev` extra.

Measured on the fixed tree, all four modes genuinely parallel:

| Mode | Wall clock |
|---|---|
| **`-n 8 --dist worksteal`** | **156.2 s** |
| `-n 8 --dist loadfile` | 186.3 s |
| `-n 8 --dist load` | 250.2 s |
| `-n 4 --dist worksteal` | 245.2 s |

**`worksteal` is chosen because it splits at test level**, so no single slow file
becomes one worker's floor. That distinction was only measurable *after* the leak fix:
before it, `test_iconography_3c.py` at 96.7 s was the binding constraint and
`loadfile`'s whole-file granularity looked essential. Its advantage over `loadfile` is
the general one — a suite that grows a slow file should not silently lose a worker.

**Alternatives rejected.**

- **Not parallelising, and only documenting an inner loop.** `pytest tests/unit` is
  192.6 s against 673.6 s for everything, so this captures a large part of the win with
  no new dependency. It does not help the case the owner actually described — running
  *everything* before testing by hand — and a convention nobody is forced to follow is
  the failure mode this repository has already paid for twice.
- **`@pytest.mark.xdist_group` + `--dist loadgroup` to keep the colliding tests
  together.** It works, and it was rejected for three reasons: the `--dist` modes are
  mutually exclusive, so `loadgroup` *replaces* `loadfile` rather than combining with it;
  the protection `loadfile` was originally chosen for turns out to be worth under 4.6 s
  (the three files with module-scoped fixtures do not reach the slowest-30 list); and
  grouping schedules around the symptom. The actual collision was a test writing into the
  git working tree, and that hazard also applied to two concurrently launched pytest
  processes — the 2026-08-17 §11.4 incident that made `TEST_APPLICATION` per-PID in the
  first place.
- **Fixing the leak in the 51 files that build an app.** Correct, and it is the reason the
  chokepoint exists: one place cannot be forgotten, and a 51-file diff would put the fix
  behind review of every unrelated line.

**The timing tests are excluded deliberately, and this is a scheduling principle rather
than a convenience.** Two tests were observed failing intermittently when they share a
runner with the parallel workers — the NFR repaint budget and the map-picker close bound among them — and
§11.4's #354 entry already holds that a performance test must protect a *sustained*
regression statistically rather than assert that one shared runner owns a quiet CPU. A
single-step gate here would have been a gate that cries wolf.

The marker means **wall-clock sensitive, not "lives in `tests/perf/`"**, and that
distinction is the load-bearing part of the decision. Seven of the 14 marked tests live
outside `tests/perf/`, which is why the runner command is
`pytest tests/ -m perf -n 0` and not a directory. All three details of that command are
load-bearing; the `-n 0` is easy to omit precisely because the command looks complete
without it. Two errors in this ADR were caught by review and are recorded because
they are the natural mistakes: an earlier version justified the marker by naming
`tests/integration/test_tasks.py`, which carries **no marker** and so is not covered by
the flag at all. Its hazard was real — two schedulers call `_check_overdue_tasks` — but it
is a shared-*state* defect and was fixed by isolating the arm, not by scheduling around it.

**Consequences (limitations, stated).**

- **`-n auto` in `addopts` makes a *small* targeted run slower**, because worker start-up
  dominates: one 11-test file measured 2.85 s serial against 5.48 s under `-n auto`.
  `-n 0` is the escape hatch. The trade is asymmetric and deliberate — 517 s saved on a
  full run against 2.6 s added to a small one — but it is a real cost and is the first
  thing to revisit if the inner loop starts using single-file runs heavily.
- **`pytest tests/` now deselects the perf tests**, so they must be invoked explicitly as
  `pytest tests/ -m perf -n 0` — three details, all load-bearing. It is `tests/`, because a directory-only form (`pytest tests/perf -m perf`)
  runs 7 of the 14 and **silently passes**, which is the worst failure mode available to a
  gate that exists to catch slow drift. It needs `-m perf`, or the `-m 'not perf'` in
  `addopts` wins and nothing is collected. It needs `-n 0`, because running the timing
  tests across workers is the thing the split exists to prevent.
  CI does this as its own step, so nothing stops being verified.
  `tests/unit/test_perf_marker_guard.py` fails the build if a wall-clock assertion is added
  without the marker, so this list cannot silently go stale — an audit written in prose had
  already been wrong twice by the time the third review found the two `TestPerf` classes.
- **A crashed worker is not a clean abort.** The 180 s `pytest-timeout` guard stays — #448
  and the 2026-08-17 stall both earn it — but on Windows it currently dumps stacks and
  aborts the run. Under xdist a timeout kills one worker, which is restarted, and the run
  continues: **a hang now presents as a crashed worker rather than as a failure.**
- **A parallel run's first visible failure mode is coverage, not tests.**
  `quality/coverage-floors.json` holds exact `covered * 100 // statements` integers per
  package plus a per-file floor, so losing a single line fails that job — and since
  `Coverage` is not a required check, that red would sit there unblocking merges while
  looking authoritative.
- **Coverage tracing and the perf tests are not in conflict; an earlier draft of this ADR
  said they were, and was wrong.** It claimed the repaint budget "fails under coverage
  tracing at 20.29 ms against a 16.70 ms budget" and concluded the `Coverage` job had
  "always been measuring something it cannot gate". Both steps fail. The 20.29 ms figure
  is a **local** measurement against the **local** budget:
  `tests/perf/test_nfr_budgets.py:56-57` reads
  `_IS_CI = os.environ.get("CI") == "true" or ... GITHUB_ACTIONS` and
  `FRAME_BUDGET_MS = 50.0 if _IS_CI else 16.7`, so on CI the budget is **50 ms** and the
  test passes under tracing. Verified both ways on one machine, same file, same
  `--cov`: `CI=true` → 6 passed; `CI` unset → 1 failed. And `gh run view 39076508170`
  (CI, master `412f01bd`) records the `Coverage` job **succeeded**, 8565 passed.
  The lesson is this ADR's own first rule about instruments: a measurement taken against
  one configuration does not describe another, and "locally it fails here" became "it has
  always been broken there" without anyone running the second half.
- **What #509 does to that job: two steps, and they are one decision.** The job now runs
  `pytest tests/ -m 'not perf'` with `-n auto`, and then a **second, serial** step runs the
  14 perf tests with `-n 0 --cov-append`. The parallel step **keeps** the `-m 'not perf'`
  filter. The deselect and the append are one decision:
  **step 1 alone is `agent_api` 2012 of 2195 with the gate exiting 1; step 1 plus the append
  is 2026 of 2195 with `regressions: []`**, a delta of exactly the fourteen `stop()`
  escalation lines. Drop the append and the job goes red on `agent_api`; drop the deselect
  and the append becomes redundant while three zero-slack budgets (map-picker close < 0.5 s,
  point-snapper mean < 16 ms, spatial-index medians < 200 ms / < 1 ms) run beside workers on
  a 4-vCPU runner. `-n auto` is 4 workers there and 20 on the dev box; the "eight" this ADR
  quotes elsewhere is the measurement harness, which matches neither.

**Evidence.** `scripts/measure_test_suite_latency.py` reproduces the concentration table
from a recorded `--durations` report (11 unit tests pin its arithmetic against a
hand-computable fixture, including the ways it could report a confident wrong number);
`docs/11-risks-and-technical-debt/audits/2026-10/test-suite-latency-2026-10.md` holds the full baseline,
the per-layer and per-file tables, the widget-leak measurement and the corrections to
issue #509's stated facts. The CI `Test` job uploads its `--durations=0` report as the
`test-durations-linux` artifact.

## ADR-058 addendum: scoped timing functions and attribute carriers (#528, PR #556)

The guard follows duration attributes into local support modules. Attribute ownership
alone did not fix the original same-module collision: the first implementation still
indexed functions and propagated calls by bare name. A tagged AST probe printed
`clock closure: ['bake', 'test_session']` for a test that called only the ordinary baker
and asserted a tile-count bound. A separate-module equality assertion could not expose it.

Both closures now use a cached lexical index whose keys preserve the class and enclosing
functions within each module. Calls resolve through lexical names, `self`/`cls`, explicit
classes and locally constructed or annotated instances; unresolved receivers never fall
back to another class's method name. Imported helper functions, dynamic receivers, instance
aliases and inherited methods remain outside this static analysis. Attribute ownership
retains its module/class/attribute identity. Regressions cover both class orders, duplicate
test/helper names, both call-graph closures and the real ground-bake AST with `TimedBaker`
restored inline. The G3 marker remains required; ordinary session count bounds stay on the
parallel runner. No application runtime, dependency or file-format change.

## ADR-058 addendum: the coverage floor blocks, and the perf pin is mutation-verified (#512–#516, 19 October 2026)

**Decision 1 — a coverage-floor regression blocks a merge (#514).** `Coverage` joins the
required checks; it is **not** folded into `Test`. The floor step already computes a
deterministic result (executed lines, not wall clock) and the job already runs on every push
in parallel with `Test` — it has no `needs:` on it, so promotion adds no wall clock to the
critical path and no runner-minutes. What changes is only whether the existing verdict is
enforced. The `agent_api` floor's margin is **six lines** (2026 covered of 2195 against
92% of 2195 = 2020), so an advisory red is precisely the signal that erodes silently. The
local inner loop never runs `--cov`; CI is the only place the floor is computed, and a sole
detector that cannot fail a merge is a measurement, not a gate. **Rejected:** folding
`Coverage` into `Test` — it re-serializes the suite into the required job, re-paying the
runner-minutes #509 removed, and blurs the check's identity. The floor gate also **fails
closed**: `check_coverage_floors.main` returns 2 when the XML is missing, malformed or does
not resolve into `src/open_garden_planner` (pinned by
`tests/unit/test_ci_quality_gates.py`), so the step's `if: always()` cannot report a pass
without a measurement. Mechanics: `quality/master-protection.json` gains `Coverage`, the job
display name is pinned as the protection context, and the owner applies the live payload and
confirms `scripts/check_branch_protection.py`. Until that application the verifier is
deliberately red.

**Decision 2 — the perf pin evaluates the command that gates the step (#513).** A `run:`
script may hold several commands, and the one whose exit status is the step's is the **last**.
The pin now identifies the command that selects the `perf` marker and requires it to be that
last command and to actually invoke pytest (a `pytest` head, or `python -m pytest`). This
closes, in one rule, the echo-smuggle, a here-doc body plus its executor, a delegating script
(`bash scripts/ci_perf.sh …`), and a trailing `|| true`/pipe. It also refuses collect-only
flags — directly or inside an `-o addopts=` value — and `PYTEST_ADDOPTS` on the step or job.
The rules are deliberately few: this matcher's history is five defects in one commit, so the
remaining shapes (`-k`/`--deselect` inside an override, a control operator embedded mid-token,
zero-combination matrices, `concurrency` cancellation) are re-listed as measured-open in the
pin rather than guessed at.

**Evidence — the pin is now re-runnable, not asserted (#512).** `scripts/replay_gate_mutations.py`
commits the harness that #509's review had to write in a scratch directory: sixteen
perturbations of `ci.yml`, each applied through a temp file, YAML-validated **structurally**
(an edit that YAML reads as something else is reported as an invalid mutation, never as an
honest "not caught"), replayed against the pin, and restored by **copy** with a byte-identity
assertion after every iteration. Fourteen must be caught and two must pass (a diamond in the
`needs` graph, and a comment that changes no configuration) — the passing controls are what
distinguish a working pin from one that fails everything. Run it after touching the matcher.

## ADR-042 addendum: a detail tile per texture, 2 px per cm (issue #785, 9 November 2026)

**Context.** A fill texture is a 256-px tile spanning 2.56 m: 1 texture pixel per
centimetre, the forge's contract. Above 100 % zoom — the balcony and raised-bed
examples open at 291 % and 340 % — and in a 300-dpi export that tile is enlarged
by the painter, and the fills are soft beside vector outlines. #785 makes every
bitmap follow the painter's resolution (§8.9.14); a sprite is a vector and can
be rasterised at any level, a texture has only the pixels it ships.

**Decision.** Each texture ships a second tile, `resources/textures/x2/<name>.png`:
**the generator's own 512-px canvas before the box downsample that makes the
256-px tile.** No recipe changes and no recipe knows about it; the 256-px tile
is, by construction, its 2 × 2 box average, and stays byte-for-byte what it was.
`core.fill_patterns.brush_for_painter` uses the detail tile when the painter
shows more than 1 px per cm, under a brush transform scaled by one half, and the
256-px tile otherwise — at 100 % zoom and below a fill is painted exactly as
before. The detail tile is tinted with the 256-px tile's mean luminance, so the
two levels are one picture.

**Alternatives, with what was measured.**

| Option | Sharpness above 100 % | Bytes | Why (not) |
|---|---|---|---|
| Keep 256 px, smooth filtering (status quo) | texture pixel = zoom px; gradient energy 1.0 | 0 | this IS the defect |
| **512-px detail tile from the painter's canvas (chosen)** | gradient energy x1.4-3.0 (median 1.6; water and stone, smooth by design, 1.15); a texture pixel is sharp to 200 % | **+5.17 MB** (24 files; the 256-px set is 1.70 MB) | zero recipe risk, same pixel gate, same seams |
| 1024-px tile (4 px per cm) | sharp to 400 % | about +15-18 MB (extrapolated, not built) and 4 MB per tinted tile in memory | the recipes are not supersample-independent: `fine_grain` draws `(C/2)^2` random numbers, so another supersample factor shifts every later draw and changes the picture; needs a recipe audit and an owner sign-off of 24 new looks |
| Sharpen an enlarged tile at run time | edges crisper, no new detail | 0 | invents halos; "sharp but wrong" |
| Coarser tiles (box averages) below 100 % | n/a - zoomed out | 0 | built and measured: removes moire (rms against the area average 12.3 -> 5.5 at 30 %) but lowers the contrast a texture reads by (luminance spread at 10 % 18.1 -> 6.5, under the #503 guard's floor of 8). A change of look at the owner's working zoom, left out: `raster_resolution.MIN_LEVEL` |

**Consequences.** Fills are twice as fine, not unboundedly fine: at 1000 % a
texture pixel still covers 5 screen pixels, where a sprite is exact. The 24
detail tiles are generated, gated (`--check`, `TestDetailTiles`, tileability)
and recorded in `PROVENANCE.md` like the tiles they come from. The 3D ground bake
keeps the 256-px tile (its grid is 1 px per cm at most). The SVG export records
the plan in 1/300-inch units (ADR-076), so above 1 unit per cm it embeds the
detail tile, as a 300-dpi PNG does. Tinted detail tiles are cached per
(pattern, colour) within 48 MB.

## ADR-042 addendum: the runtime tint becomes a luminance map (issue #502, 16 October 2026)

The forge's tint-readability band was written for a tint that could not do the job.
`_tint_texture` drew the texture and overlaid the user's colour at **80/255 (31 %)**;
over the brown roof-tile texture a light-green fill measured `#ca6846` -> `#b8925d` —
still brown, i.e. the "standard roof tile colour" the owner reported after setting a
green fill. Raising the overlay enough to read (160/255) flattened the low-contrast
materials (SAND luminance std 1.62 against the 2.0 floor), so overlay strength was the
wrong knob: a constant wash cannot recolour a saturated texture without destroying its
contrast.

**Decision.** `_tint_texture` now maps luminance: every pixel becomes the user's colour
scaled by the texture's **relative** luminance (`pixel_luminance / mean_luminance`).
Hue comes wholly from the user's colour, brightness is preserved on average, and the
result's coefficient of variation equals the texture's — the recolour is *provably*
non-flattening rather than tuned not to flatten. The colour's alpha still sets the
fill's opacity.

**Consequences.** Every textured fill in every plan changes appearance — the owner's
manual sign-off is the gate (`ogp-asset-forge`: "the owner's manual sign-off
(sovereign)"). The tint-readability band keeps its purpose but its rationale changes: it
now guarantees a texture has enough relative luminance structure for the map to show
detail. The §8.10 integration gate gained the case that was missing: a **pale** colour
over a strongly coloured texture must read (only red and blue — two saturated,
far-apart colours — were checked before, so both "passed" while the owner's light green
rendered brown), and "not flattened" is now asserted as **relative** contrast against
the same item's untinted render, so a legitimately dark fill colour is not mistaken for
a flat one.

**Related, same finding.** The report that exposed this also showed the Properties panel
disagreeing with the canvas after a reload: `ProjectManager._deserialize_item_core`
rebuilt each item's brush and pen but never wrote back the stored appearance attributes
(`fill_color`, `stroke_color`, `stroke_width`, `stroke_style`), which the item
constructors pre-seed with the object type's style — so the panel showed the type
defaults and the next save wrote them over the user's colours (#438/#469). The loader
now restores those attributes through `core/item_look.restore_stored_look`, and the
serializer no longer falls back to a texture brush's black `color()` for `fill_color`.

## ADR-057 addendum: the #409 LOD flat fill is removed, and the cache-mode discriminator is kept for the paint bound alone (issue #503, 17 October 2026)

ADR-057's consequences flagged the sibling directly: "The same `widget`-based idiom
lives in `should_use_lod_flat_fill` (#409), where it is worth re-checking for the same
reason." #501's independent review re-checked it, measured it, and filed #503.

**Finding.** Through a real `CanvasScene` + `CanvasView` (offscreen, one `GARDEN_BED`
rectangle with the `ROOF_TILES` pattern), `should_use_lod_flat_fill` was invoked once
per paint with **no** widget present — at `fit_in_view` and after four `zoom_out()`s —
and returned `False` every time; only a `NoCache` control item, a configuration no
unselected canvas item is ever in, saw a widget. The LOD branch therefore never ran in
the product, and its tests passed only because they called the helper directly with a
fabricated widget. The fit-in-view acceptance gain attributed to it at #409 came from
the `lru_cache` SVG-path resolution and the `DeviceCoordinateCache` shipped alongside.

**Decision.** The obvious repair was to key "interactive" on the item's **cache mode**
through one shared predicate, `items/garden_item.py::is_interactive_paint`, which the
over-budget paint bound above calls too. That predicate is **kept** — it is the one
correct definition of "which paint is this", and the paint bound needs it for real
(44.7 ms at 1,024 vertices, 589 ms at 16,384). Its docstring now records that it
classifies paints and does not decide how much detail to draw.

The **flat fill is removed**, with its rationale recorded. Issue #503 offered both
repairs explicitly; measurement on the reference plan the branch was written for chose
the second. On the 990-item audit plan, 1600x1000 view, best of seven rounds, both
scenarios below the 0.4 threshold). `fit_in_view` at zoom 0.316: **10.61 and 11.50 ms median
with the flat fill disabled, 10.87 ms with it live** — the two arms' ranges overlap
entirely. `zoom_step` at zoom 0.348: **7.97 / 7.98 ms disabled, 8.20 ms live**. What that
establishes is that the effect sits below this harness's noise — within-arm run-to-run
variation is 8 % against a 0.26 ms between-arm difference, and no reversed-order run was
taken, so no claim about which arm is faster survives. All six
`tests/perf/test_nfr_budgets.py` cases pass either way, worst reading 12.21 ms against the
16.70 ms budget. (An earlier single-pair reading — 10.58/10.64 and 8.21/7.40 — is
superseded and is not to be cited: it put the `zoom_step` sign the other way round.) The
cause is structural — `DeviceCoordinateCache` rasterises a textured item once and every
later frame is a blit, so the expensive textured `paint()` the LOD existed to avoid was
already amortised by the sibling fix. Deleting `should_use_lod_flat_fill`,
`get_lod_fill_color` and `LOD_FLAT_FILL_THRESHOLD` also removes seven call sites across
the rectangle, circle, ellipse and polygon items.

**Consequences.** No zoom-dependent simplification remains in the canvas: a textured
fill, a plant sprite and a furniture sprite paint their full detail at every zoom, and
the paint-level diagnostics that the removed early return would have skipped (a bed's
grid, crop-rotation indicator, soil-mismatch border and capacity badge; a plant's
spacing ring, companion highlight and antagonist badge) are now drawn at every zoom.
This is not a behaviour change relative to any shipped release — the branch never ran —
so it needs no visual acceptance pass, and it is a net removal of a risk. The #472
suite is restored to its pre-#507 state in full, including its fit-in-view harness
zoom; the low-zoom seam pair and the 100 %-zoom workaround existed only to serve the
removed branch and are gone with it.

**The pin is parametrised over branches, not classes.** `tests/integration/test_canvas_item_cache.py` (renamed from `test_canvas_item_lod_and_cache.py`) renders a textured, tinted item through a real `CanvasView` at five zoom levels — 0.1, 0.25, 0.4, 0.75, 1.0 — plus the export path, and asserts the interior still carries its texture's luminance spread. **Lower bound only, deliberately** — a future change may soften a texture and must not be able to do so by deleting it; there is no ceiling, and no absolute sample floor, because interior area runs 816 to 429 986 pixels across the cases and any constant fires on the smallest for being small. The seven deleted call sites were **not** seven instances of one thing: two sat inside `if is_plant` and two inside `if is_furniture_type`, so the table carries seven entries — the four generic shapes plus a plant circle and furniture rectangle/circle. Re-introducing a `< 0.4` flat fill is caught at **all seven**, mutation-verified per site. The sampled interior is the item's own `QGraphicsItem.shape()`: not its bounding box (the corners are page background for a circle, an ellipse or a polygon, so a solid circle measured as high-contrast and the pin was vacuous on three of four classes), not a second paint (any flat-fill branch overrides the brush on that pass), and not alpha (the scene paints an opaque background). `TestTheMaskIsTheItem` asserts that invariant, because a displaced mask does not fail — it reads background. The four textured shapes' export column converging on 15.47-16.02 is the calibration check that the instrument is right: with a forgotten `-source.topLeft()` translation those four read 15.83 / 37.27 / 49.85 / 16.37. The Linux/offscreen sampler lesson stands — samples come from a computed region, never a colour filter, which the CI background passed at spread 62.59 against 0.00 on Windows. The mask mechanics, the seven-entry shape list and the calibration table live in the test file rather than here; `venv/Scripts/python.exe scripts/verify_lod_removal_mutations.py` re-applies all seven deleted call sites and exits non-zero if one stops being watched, which is how a negative pin is kept honest between reviews.

**Lesson for ADR-057 itself.** This addendum records a decision that was nearly the
opposite of the one its first draft took, on the same measured evidence, because the
owner then exercised the thing that the measurement could not: at 20-25 % zoom — where
they work, well under the 0.4 threshold — every texture on the canvas would have become
a solid colour. *Reachability is necessary, not sufficient: before promoting a dormant
path, ask whether it earns the degradation it costs, and put the answer in front of the
person who has to look at it.*

## ADR-058 addendum: complete coverage on parallel runners (#601, 26 October 2026)

**Status.** Owner approved as a chore on 26 October 2026 (PR #606), without GUI
testing; no application release or version synchronization is needed.

**Decision.** Keep full line and branch tracing and the uninstrumented `Test`
job. Split non-perf coverage by a stable SHA-256 test-ID partition across two
Linux runners, with xdist within each. Measure the entire perf set serially on a
separate runner. `Coverage`, the existing protected check name, runs with
`if: always()`, rejects failed/skipped producers, combines three explicitly named
files and enforces the existing line floors. A missing producer or input fails;
there is no partial-report success. Required check names and protection do not change.

Only actual wall-clock-sensitive cases and shared measurement scenarios retain
`perf`; 27 deterministic cases return to parallel execution. Reuse the marker
guard's parsed AST/index, consolidate duplicate CLI sweep consumers, and separate
fifty acyclic receiver lifecycles from one real cyclic-GC check.

**Alternatives.** Merely dropping `--cov-branch` leaves TOML's `branch = true`
active. Line-only tracing is benchmarked explicitly but would remove diagnostic
branch data; it is not the delivery mechanism. Replacing `Test` with a forwarding
status would remove the uninstrumented budgets (traced budgets have slack).
Larger/paid runners and a Python migration are unnecessary here. Hash membership
avoids the collection-order assumption of an initial round-robin partition.

**Consequences.** Extra runner setup/collection may increase total runner minutes
while reducing latency. No dependency, runtime behavior, `.ogp` format, product
budget or floor changes. The phenology gate's reproduced tracer-only overrun uses
the existing snapshot-budget tracing factor with CI slack disabled: the real
16 ms gate remains in Test, with a 160 ms tripwire under tracing. Pins:
`tests/integration/test_ci_coverage_shards.py`,
`tests/unit/test_gate_commands.py`, `tests/unit/test_perf_marker_guard.py` and the
existing receiver/harness guards. Measurements and all 116 original marker cases
are in [the investigation](../11-risks-and-technical-debt/audits/2026-10/ci-latency-601.md).
