# Test-suite latency baseline — issue #509

Measured 17 October 2026 against `132f6715` (v1.30.9) on the development box:
Windows, **Python 3.12.9**, PyQt6 6.11.0 (Qt runtime 6.11.0), 20 logical cores,
63.8 GB RAM, `QT_QPA_PLATFORM=offscreen`. CI differs on both axes that matter:
**Python 3.11.9** on `ubuntu-latest` (**4 vCPU**). The two environments are not
directly comparable in either direction, which is why the local and CI figures
below are reported side by side rather than merged.

## Why this document exists

Issue #509 was filed with the claim that the battery "takes ~15.5 minutes and runs
serially on one core". Two of its four proposed remedies were costs, not speedups, and
its central number had never been decomposed. This records the decomposition, so the
next change to the suite is chosen from measurement instead of guessed.

Reproduce — and note the two flags that are load-bearing, because without either the
command produces a report that silently cannot reproduce this document's own tables.

* **`-n 0`.** Without it `addopts` supplies `-n auto --dist worksteal`, and this
  document's tables are a SERIAL measurement: per-test call time inflates under parallel
  execution (620.6 s of call time serially against ~1 700 s under `-n auto`), so a
  parallel run cannot be compared with them.
* **`-o addopts=""`.** Without it `addopts` supplies both `-n auto --dist worksteal`
  *and* `-m 'not perf'`, and the run deselects the whole `perf` layer — 14 tests, so the
  `perf` row in the layer table below cannot be produced at all and every total, share and
  concentration figure shifts. (`-m ''` is the intuitive way to clear a marker filter and
  it does **not** work: pytest answers `argument -m: expected one argument`.) Measured:
  `tests/ -n 0` collects 8 614 of 8 628 with 14 deselected; with `-o addopts=""` it
  collects all 8 628. (Counts measured at `4d1cd992`. They move with every commit
  that adds a test - this change's own last commit moved them by one - so the
  durable statement is "14 of the total are deselected", not the absolute numbers.)

```powershell
$env:QT_QPA_PLATFORM='offscreen'
venv/Scripts/python.exe -m pytest tests/ -q -n 0 -o addopts="" --durations=0 --timeout=180 > durations.txt
venv/Scripts/python.exe scripts/measure_test_suite_latency.py durations.txt
```

> **These numbers are machine-relative, and this box drifts.** Measured across one
> session on the same tree and the same code, two files that were never touched
> changed by `test_retracted_figures.py` 30.0 s → 49.0 s and `test_main_window.py`
> 21.7 s → 29.8 s, a 37–63 % swing with no code change involved. Treat a
> single run's absolute numbers accordingly, and compare **ratios** rather than
> seconds when asking whether a change helped.
>
> **Two figures in this document must never be compared across runs.** Total *call*
> time is measured per test and therefore inflates under parallel execution — the
> suite's 620.6 s of call time serial became 1 700 s of call time under `-n auto`,
> while its *wall clock* fell from 673.6 s to 182 s. The useful quantity is wall
> clock; the useful reading of the per-test table is its shape, not its sum.
> (That 182 s was the under-load measurement behind the false 740 s "regression" in the
> case study at the end of this document. This box later measured the same code at
> 68–90 s across this change's own runs, so treat any single wall-clock figure here as one
> sample of a machine that drifts, and quote the ratio instead. Where the tables cannot
> avoid a single number, it is labelled with the configuration that produced it.)

The CI `Test` job now writes the same report and uploads it as the
`test-durations-linux` artifact. **That artifact is a parallel run with the perf tests
deselected, so it is a shape signal only** — which tests are relatively expensive, whether
a file's share moved — and deliberately *not* a replacement for the serial table below.
Nothing parses it yet; that is a stated limitation, not automation.

## The run

| Fact | Value |
|---|---|
| Collected tests | **8 548** at `132f6715` |
| Collected tests on this branch's head | **8 628** at `4d1cd992` (+80: this change adds 23, #507 adds 57) |
| Default run (`-m 'not perf'`) | **8 614** collected, 14 deselected |
| Result | `1 failed, 8506 passed, 41 skipped in 912.60s (0:15:12)` |
| Collection overhead alone | 3.4 s |
| Local wall clock, unit layer only | **192.6 s** (3 min 12 s) |

**The one failure is not a product defect and it is not intermittent.**
`tests/unit/test_distribution_inventory.py::test_real_frozen_bundle_passes_the_inventory_check`
asserts `interpreter == "3.11"` ("run frozen verification in the locked builder
interpreter"). This box's venv is Python 3.12.9, so the test fails by design on a
non-locked interpreter. The practical consequence for the development loop is worth
stating plainly: **on this box the full suite is never green**, independent of the
code under test, which erodes the signal the run is supposed to carry.

`--durations=0` reports every phase of 5 ms or more; 20 872 sub-5 ms phases are
hidden. That does not weaken the conclusions below — the visible phases account for
868 s of the 912 s wall clock — but a per-test total from this report is a lower
bound, not the whole cost.

## Phase split

| Phase | Seconds | Share of wall clock |
|---|---|---|
| `call` (test bodies) | 620.6 s | 68 % |
| `teardown` | 128.1 s | 14 % |
| `setup` | 119.4 s | 13 % |
| collection, reporting, hidden sub-5 ms phases | ~44 s | 5 % |

**27 % of the run is pytest's own per-test fixture overhead** across 8 548 tests —
cost proportional to test *count*, not to what any test asserts. That is a different
lever from the one below and should not be attributed to it.

## Where the test time actually is

Measured over the 1 849 tests with a `call` phase above the 5 ms threshold
(958 + 797 + 89 + 5, the rows below):

| Layer | Tests timed | Seconds | Share | Mean |
|---|---|---|---|---|
| integration | 958 | 415.8 s | 67.0 % | 0.434 s |
| unit | 797 | 166.8 s | 26.9 % | 0.209 s |
| ui | 89 | 27.4 s | 4.4 % | 0.308 s |
| perf | 5 | 10.5 s | 1.7 % | 2.100 s |

### The time is concentrated, not spread

| Concentration metric | Value |
|---|---|
| Median test | **0.030 s** |
| Mean test | 0.339 s (**11.3× the median**) |
| Slowest 1 test | 14.9 s |
| Slowest 10 tests | 21.1 % of measured call time |
| Slowest 50 tests | **50.9 %** |
| Slowest 200 tests | 72.4 % |
| Top decile of files | **71.8 %** |

**The same two metrics across the three configurations this change measured.** ADR-058 quotes
the middle and right columns; this is the table they come from, so the figures have a home
outside the ADR and their provenance is a row rather than a citation:

| Metric | serial, before the leak fix (`132f6715`) | serial, after the leak fix | parallel (`-n auto`) |
|---|---|---|---|
| Slowest 50 tests | 50.9 % | **37.9 %** | **32.2 %** |
| Mean/median | 11.3× | **6.8×** | **20.7×** |

The columns are not comparable with each other and the parallelism column is not an
improvement in concentration — it is the opposite, and that is the point: per-test *call*
time inflates when tests contend (620.6 s serial against ~1 700 s under `-n auto`), so the
parallel column's higher mean/median is a statement about the scheduler rather than about
the tests. Wall clock is the quantity to compare; this table is a shape reading.

Ten files out of 228 hold **57 %** of all measured test time:

| Seconds | Share | File |
|---|---|---|
| 96.7 s | 15.6 % | `tests/integration/test_iconography_3c.py` |
| 41.9 s | 6.8 % | `tests/integration/test_theme_switch_chrome.py` |
| 37.2 s | 6.0 % | `tests/integration/test_icon_system.py` |
| 29.7 s | 4.8 % | `tests/unit/test_retracted_figures.py` |
| 28.9 s | 4.7 % | `tests/integration/test_agent_api_default_on.py` |
| 25.8 s | 4.2 % | `tests/unit/test_gate_commands.py` |
| 24.6 s | 4.0 % | `tests/unit/test_texture_forge_conformance.py` |
| 24.5 s | 3.9 % | `tests/integration/test_agent_api_writes.py` |
| 23.5 s | 3.8 % | `tests/integration/test_idle_scene_quiescence.py` |
| 22.1 s | 3.6 % | `tests/ui/test_main_window.py` |

**This is the fork in the road that issue #509 left open, and it now has an answer.**
A suite whose cost is spread evenly across 8 548 independent tests is a suite that
parallel execution fixes. A suite where half the time sits in fifty tests is not —
that is a suite where those fifty tests are doing something expensive, and the right
first move is to find out what.

> **These per-file numbers are position-dependent, and the table must not be read
> as "these files are slow".** It is measured — see "The real cause is an
> accumulation, not a slow file" below for the measurement that overturns the naive
> reading, and for why the same file costs 2.14 s alone and 96.7 s in the suite.

## The real cause is an accumulation, not a slow file

The ten files above share a signature worth chasing, and chasing it overturned the
attribution. The leading file constructs **no full application**: it builds
individual widgets and calls `apply_theme()` two or three times per test.

`tests/integration/test_iconography_3c.py` **alone**:

```
36 passed in 2.14s          # every call time <= 1.04s
```

The **same file**, immediately after `tests/ui/test_main_window.py` (which builds
~30 full `GardenPlannerApp`s):

```
447s total; individual theme tests 60-66s each
```

and in the full suite it costs 96.7 s. Identical test code, **~45× the cost**,
decided entirely by what ran before it. A single test isolated from its own file:

```
1 passed in 0.16s
```

So the theme tests are not intrinsically heavy. They are **victims of a leak in
other files**. Probing `QApplication` state directly, before and after
`test_main_window.py`:

| Probe | Live widgets | Visible | `apply_theme` round-trip |
|---|---|---|---|
| alone | **0** | — | **1.3 ms** |
| after `test_main_window.py` | **38 271** | **0 (0.0 %)** | **22 478 ms** |

Thirty apps leak **38 271 widgets and 1 580 top-level widgets** into the process.
`apply_theme()` walks `app.allWidgets()` on every call, so every later theme switch
pays for all of them — and the surviving widgets are `QLineEdit`s and the like that
nobody can see.

**`gc.collect()` is not the fix.** It freed 8 337 objects and moved the widget count
only from 38 271 to 37 638; the round-trip did not improve. So the widgets are held
by *strong* references, not by collectable cycles. A referrer probe found the holder
to be a plain `list` — i.e. PyQt6/sip's own bookkeeping, which does not identify an
application-level holder. **The holder is therefore not yet established**, and this
document does not claim it is.

### What follows, and what does not

- **A visibility-filtered walk would cost 0.0 ms** against the leaked-state round-trip
  above — measured twice, at **22 478 ms** and **21 825 ms**, the two being separate runs
  of the same probe on a box this document elsewhere says drifts 37–63 % — and 0 % of the
  surviving widgets are visible. That is a tempting one-function product
  change — and it is *not* obviously safe: a widget that is hidden now and shown
  later would have skipped its re-tint, so the fix is only correct if hidden widgets
  re-tint lazily (e.g. on `showEvent`) instead. That is a behaviour change to
  visible UI and needs its own review and its own evidence.
- **The leak is the cause, so the leak is the correct primary target.** It lives in
  test hygiene, not in the product, and fixing it preserves product semantics
  exactly. The chokepoint question is whether one conftest-level teardown can
  reclaim top-level widgets and their children, rather than thirty-four files each
  having to remember to.
- **A suite whose cost depends on test order has a measurement problem before it has
  a performance problem.** The per-test table above is a valid record of one run in
  one order; it is not a per-file cost. Re-running a slow file alone is the cheapest
  diagnostic available and would have found this immediately.

## Three mechanisms, at three different levels of confidence

### 1. A global theme switch, called in a loop — measured, and the largest single cause

`tests/integration/test_iconography_3c.py` (96.7 s, the most expensive file in the
suite) constructs **no full application**. It builds individual widgets
(`LayerListItem`, `ConstraintListItem`, `PlantSearchPanel`, `CollapsiblePanel`,
`SunSimToolbar`) and calls `apply_theme(app, ThemeMode.LIGHT)` /
`ThemeMode.DARK` — two or three times per test, the third restoring the light theme.

What each of those calls costs, from the source:

- `src/open_garden_planner/ui/icons.py:52` registers
  `lambda _colors: clear_cache()` as a theme listener, so **every** `apply_theme()`
  empties `_icon_cache` and `_pixmap_cache` (`icons.py:42-49`);
- `apply_theme()` then walks `app.topLevelWidgets()` and, via
  `_propagate_theme_colors()`, `app.allWidgets()`, calling `apply_theme_colors()`
  and `refresh_theme_icons()` on every widget that opts in;
- each widget then re-requests its icons, and `_render_svg` puts each one through
  `QSvgRenderer` again (`icons.py:81`), because the cache that would have held it
  was just cleared;
- plus `generate_stylesheet()` (`theme.py:317`, a ~900-line generator) and a
  process-wide `app.setStyleSheet()`.

So one `apply_theme()` is **O(number of live widgets) and cache-destroying**. There
are 48 call sites across 7 test files
(`test_iconography_3c.py`, `test_icon_system.py`, `test_theme_switch_chrome.py`,
`test_icon_provider.py`, `test_theme_tokens.py`, `test_logging.py`,
`test_sun_mismatch.py`); the three most expensive files alone are **28 %** of the
suite's measured test time.

**Measured, and superseding the earlier guess here:** the per-call cost is not
intrinsic — it is the widget count, inflated by a leak in the app-building tests.
The same `apply_theme()` call that costs 1.3 ms in a clean process costs 22 478 ms
after 30 `GardenPlannerApp`s have leaked 38 271 widgets into it, **none of them
visible**. See "The real cause is an accumulation, not a slow file" above for the
full measurement. What this section still establishes is *why these files are the
victims*: they are the only ones that call the one global, cache-destroying,
widget-count-proportional operation in a loop.

### 2. Full application boots — measured

`tests/ui/test_main_window.py` (22.1 s) and `tests/ui/test_language_menu.py`
construct a real `GardenPlannerApp` per test; **51** test files construct one in total
(`git grep -l "GardenPlannerApp()" 132f6715 -- tests/`), 49 of which also register it
with `qtbot.addWidget` and therefore have its close-but-not-delete leak.
`pyproject.toml` already records the cost: "the slowest legitimate tests build the
full app in ~6 s". Sharing one app across tests would remove the repeated boot, but a
shared `GardenPlannerApp` is shared mutable state, and this repo's §11.4 record is
full of exactly that failure mode. Not attempted here; recorded as a known cost.

### 3. Live loopback servers — measured

`test_agent_api_default_on.py` (28.9 s), `test_agent_api_writes.py` (24.5 s) and
friends start a real `AgentApiServer` per test. Each does a real bind plus a
shutdown. These are the tests that make parallel execution non-trivial, see below.

## Corrections to issue #509's stated facts

Recorded rather than silently amended, because each changes what the work is worth:

1. **"Every push costs about 31 minutes of wall clock" was wrong.** The `test` and
   `coverage` jobs have no `needs:` between them, so they run concurrently on
   separate runners: wall clock is `max(Test, Coverage)`, not their sum. What doubles
   is **runner-minutes**.
2. **The suite is 8 548 tests, not 8 551.** The issue's `1 + 8513 + 37` matched a
   run on the #503 branch; `master` has drifted since.
3. **"CI's Test job is the faster environment" was confounded** by the interpreter
   (3.11.9 vs 3.12.9 here) and the core count (4 vCPU vs 20).
4. **The `QSettings` sharing risk is already mitigated.** `tests/conftest.py` derives
   `TEST_APPLICATION` from `os.getpid()`, added on 2026-08-17 (§11.4) precisely so two
   concurrent pytest processes cannot share one store. Parallel workers are separate
   processes, so each gets its own key by construction.
5. **The port risk was real, and this change closed it.** *This entry was written before
   the port helper landed and both halves of it are now stale — recorded here rather than
   silently corrected, because the correction is the point.* It originally read: every
   socket test uses `_free_port()` (`bind(("127.0.0.1", 0))`, then reads the OS-assigned
   port), so the only residual is a TOCTOU window since `_free_port()` closes before the
   server re-binds. Neither half holds for this tree: **no test calls `_free_port()` any
   more** — ten files each carried their own copy and all of them now go through
   `tests/agent_api_helpers.py::start_server()`, which **retries on a lost bind** and so
   absorbs the TOCTOU window rather than describing it. The TOCTOU was not theoretical:
   `test_agent_api_dns_rebinding.py` failed with `Agent API server failed to start` under
   20 workers, and that is the failure the retry exists for.
   Still true, and worth keeping: no test binds a fixed port. `8765` appears only in
   settings-default assertions and dialog URL strings, and `tests/integration/conftest.py`
   records that no test ever binds it.
6. **Criterion 2 (`-m "not perf"`) is worth ~1.7 %, not the ~0.5 % this entry used to
   claim.** The old figure was `tests/perf` "6.35 s of a 1 362 s run", and both halves were
   wrong on inspection: 6.35 s is `test_nfr_budgets.py` **alone** (6 tests, timed directly),
   not the `tests/perf/` directory, and 1 362 s appears nowhere else in this document or in
   issue #509. This document's own layer table above puts the `perf` layer at **10.5 s of a
   620.6 s measured-call-time total**, i.e. 1.7 %, which is the figure to use. The 14 marked
   tests are also spread across the suite now rather than confined to `tests/perf/`, so the
   number will move again. It has independent merit — a plain run becomes deterministic, per
   §11.4's #354 entry about not letting timing assertions share a runner with correctness
   tests — but it is not a speed lever.
7. **`Coverage` was not a required check when this was written.** Branch protection then
   required eight contexts (`Agent context parity`, `Lint`, `Test`, `Security`,
   `Dependencies` ×2, `Types` ×2). De-duplicating the two runs therefore buys
   runner-minutes, not gate latency — and any restructuring must keep a check literally
   named `Test`. **(19 Oct 2026: #514 made `Coverage` a required check; see the ADR-058
   addendum.)**

## Parallel execution: measured, what blocked it, and what the modes are worth

All figures on the same box, `pytest-xdist` 3.8.0. Two tree states are reported,
because the widget-leak fix above changes the answer and would otherwise be read as
part of the speed-up:

| Run | Before the leak fix | After the leak fix |
|---|---|---|
| Full suite, serial | 912.6 s | **673.6 s** |
| Full suite, `-n 8 --dist worksteal` | — | **156.2 s** |
| Full suite, `-n 8 --dist loadfile` | 154.1 s | 186.3 s |
| Full suite, `-n 8 --dist load` | — | 250.2 s |
| Full suite, `-n 4 --dist worksteal` | — | 245.2 s |
| `tests/unit` only, serial | 192.6 s | — |
| `tests/unit` only, `-n 8 --dist loadfile` | 61.1 s | — |
| `tests/unit` minus its 3 slowest files, serial | 120.5 s | — |

The leak fix costs the parallel run about **32 s** — the reclaim fixture now runs in every
worker for every test, which is the whole of the 154.1 s → 186.3 s move in the only
before/after parallel pair in the table — and saves the serial run 239 s. It is a shift in
where the work sits, not a regression.

**`worksteal` is the mode.** It splits at test level, so no single slow file becomes one
worker's floor. That is only measurable *after* the leak fix: before it,
`test_iconography_3c.py` at 96.7 s was the binding constraint and whole-file granularity
looked essential. Its advantage over `loadfile` is the general one — a suite that grows a
slow file should not silently lose a worker.

The unit layer's parallel efficiency is the poorer of the two (3.15× against 4.31×),
which is what per-worker fixed cost predicts: every worker imports the app,
collects the tree and builds the session fixtures, and against 192 s of work that
overhead is a visible fraction. The full suite amortises it.

**8 514 of the tests passed under `-n 8` on the first attempt.** Every one of the
four failures was understood:

| Failure | Cause |
|---|---|
| `test_settings_chokepoint.py` ×3 | Working-tree race — see below |
| `test_distribution_inventory.py::test_real_frozen_bundle_passes_the_inventory_check` | The interpreter guard described above; unrelated to parallelism |

No port collision, no `QSettings` interference, no timing flake. **Three of the four
risks the issue named as blockers turned out to be already handled** (one
`QApplication` per worker, port binding, shared filesystem and `QSettings`); the
fourth - timing tests getting noisier under load - is real and is what the marker
exists for. The one blocker that actually stopped parallel runs was not on the list.

### The blocker: one test mutated the git working tree

`tests/unit/test_gate_commands.py::_scan_with_canary` staged a canary file at
`scripts/_canary_<tag>.py` in the **real** repository, scanned, then unstaged and
deleted it. It was the only test in the tree that mutated shared state, and serial
execution hid the consequence completely.

`tests/unit/test_settings_chokepoint.py::_python_sources` globs the working tree
(`root.rglob("*.py")`, line 250) and `_scan` reads what it found (line 273). Under
`-n 8` those are two different modules on two different workers, so:

- one worker's `rglob` listed the canary inside the window between the other
  worker's write and unlink, and the read then raised `FileNotFoundError` on
  `scripts\_canary_ghp.py` — three failures in one run;
- the same window ran the other way: `test_gate_commands.py`'s own whole-repo
  `check_repo(_REPO_ROOT) == []` assertion could read a **sibling worker's** staged
  canary and report a credential that was never committed anywhere.

Both are properties of *sharing one working tree*, not of the scheduler, so both
also applied to the two-concurrent-process case `tests/conftest.py` already
documents for `QSettings` (§11.4, 2026-08-17) — the same class of hazard, a second
instance.

The fix is the cause, not a schedule: the canary is now staged in a throwaway
`git init`-ed repo under `tmp_path`, so nothing outside the temp directory is ever
created, staged or deleted. `test_settings_chokepoint.py` scans strictly:
an earlier version of this paragraph said it absorbed `FileNotFoundError` for a file that
vanished after being listed, and that absorption was reverted — the test's own docstring
calls it leftover scaffolding. The direction is the safe one (the code is stricter than the
text was), but the sentence was false, and it is corrected here rather than annotated. Verified: 5 consecutive `-n 8` runs of the two colliding
modules, 98 passed each, no canary residue and a clean `git status`.

### Why grouping was not the answer

xdist can keep colliding tests together — `@pytest.mark.xdist_group(name)` with
`--dist loadgroup` — and it was considered. Three reasons against:

1. **The `--dist` modes are mutually exclusive.** `loadgroup` *replaces*
   `loadfile`; there is no combination. Since `--dist loadfile` is what produced
   the measured 5.92×, adopting `loadgroup` trades a measured result for a
   speculative one.
2. **The argument for `loadfile` that motivated this note is weak.** `loadfile`
   was originally chosen to protect module-scoped fixtures from being rebuilt per
   worker. The three files that have them (`test_spike_q3d_board.py`,
   `test_spike_q3d_render.py`, `test_dynamic_input_overlay.py`) all cost **under
   4.6 s** — they do not reach the slowest-30 list — so their duplication is a few
   seconds, not minutes.
3. **Grouping schedules around the symptom.** It makes the collision not happen
   *under xdist*, while the hazard persists for anyone running two pytest
   processes at once — the exact scenario the conftest comment and the 2026-08-17
   incident describe. Fixing the mutation removes it for every scheduler and for
   serial runs too.

With the mutation gone, no grouping is needed: nothing else failed under `-n 8`.

## Consequences for the choices ahead

- **The suite's shape suits parallel execution.** Only two session-scoped autouse
  fixtures and six module-scoped ones (in three files) exist in the whole tree;
  everything else is
  function-scoped and independent.
- **But `--dist load` (xdist's default) is not automatically right.** With
  `--dist loadfile` the longest file is a hard per-worker floor, and here that is
  `test_iconography_3c.py` at 96.7 s against a `total/8` of 77.6 s. `worksteal`
  splits at test level and would lift that ceiling, at the cost of splitting
  module-scoped fixtures — which the measurement above says is cheap. The mode to
  commit should therefore be measured, not assumed.
- **27 % of the run is pytest's own overhead**, proportional to test count rather
  than to what any test asserts. Parallel execution divides it; it does not remove
  it.
- **`pytest-timeout` changes meaning.** The 180 s guard must stay (#448, the
  2026-08-17 stall), but today a Windows timeout dumps stacks and aborts the run;
  under xdist it kills one worker, which is restarted, and the run continues. A hang
  would present as a crashed worker rather than a clean abort.
- **A parallel run's first visible failure mode would be coverage, not tests.**
  `quality/coverage-floors.json` holds exact integer floors per package
  (`covered * 100 // statements`) plus a per-file floor on
  `core/tools/constraint_tool.py`. Losing a single line fails that job, and when this was
  written `Coverage` was not required, so the red would sit there unblocking merges while
  looking authoritative. **(#514 made `Coverage` a required check; see the ADR-058
  addendum.)**
- **The honest instrument for the concentrated half is a fix, not a scheduler.**
  The `-n 8` projection of the 620 s of call time into 78 s is a floor: it ignores
  worker start-up, duplicated collection (3.4 s × N) and duplicated session
  fixtures, and the measured 154 s is what that floor actually looks like.
- **The cheapest large win needs no new dependency at all.** `pytest tests/unit` is
  3 min 12 s against 15 min for everything. A committed inner-loop convention
  captures most of the available speed-up before any dependency is added.

## Two findings that are not about speed

### `--cov` and the perf tests *do* combine on CI — an earlier draft of this file said they could not

**This section was wrong and is corrected rather than deleted, because the error is the
interesting part.** It originally read: the repaint budget "**fails** with the same flags
plus `--cov`" at 20.29 ms against a 16.70 ms budget, therefore the `Coverage` job "has been
**measuring something it cannot gate**".

The first half is true **locally** and the conclusion does not follow, because the budget
in that message is the LOCAL one. `tests/perf/test_nfr_budgets.py:56-57` reads
`_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"`
and `FRAME_BUDGET_MS = 50.0 if _IS_CI else 16.7`. GitHub Actions sets `CI=true`, so on
that job the budget is **50 ms**, not 16.70 ms, and 20.29 ms is comfortably inside it.

Same file, same `--cov`, same machine, one variable changed:

| `CI` | budget | result |
|---|---|---|
| `true` | 50.0 ms | **6 passed** |
| unset | 16.7 ms | 1 failed (20.29 ms) |

And the job's own history settles it: `gh run view 39076508170` (CI, master `412f01bd`)
records `Coverage` **success**, 8565 passed. So the job was never measuring something it
could not gate, and "it has always been broken" was a local number promoted to a claim
about a configuration nobody ran.

What #509 *does* to that job: it adds `-n auto` and it splits it into two steps. The
parallel step **keeps** the `-m 'not perf'` filter — an earlier draft of this section said
the filter was removed, which the shipped YAML contradicts — and a second, serial step runs
those fourteen tests with `-n 0 --cov-append`. The deselect is what removes **91.66%**'s
fourteen statements (2012 of 2195, against a 92% floor) from the parallel step; the append is
what puts them back (2026 of 2195, `regressions: []`). They are one decision, and the
fourteen are `stop()`'s forced escalation, not `start()`. Measured on CI with
`gh run view <id> --json jobs`, same workflow and runner class throughout:

| | master `412f01bd` (run 39076508170) | head `1b2398f7` (runs 39115631489 / 39115635791) |
|---|---|---|
| `Coverage` | 21m10s (1270 s) | **5m39s (339 s)** and **7m36s (456 s)** |
| `Test` | 17m27s (1047 s) | **5m54s (354 s)** and **4m05s (245 s)** |

The two head runs disagree with each other, so read the spread rather than the smaller
figure. Both are the same head (`1b2398f7`), the same workflow and the same runner class:

| job | master `412f01bd` | `1b2398f7` push `39115631489` | `1b2398f7` PR `39115635791` | spread |
|---|---|---|---|---|
| `Coverage` | 1270 s (21m10s) | 339 s (5m39s) | 456 s (7m36s) | **34 %** |
| `Test` | 1047 s (17m27s) | 354 s (5m54s) | 245 s (4m05s) | **44 %** |

The honest summary is **2.8x-3.7x on `Coverage`** and **3.0x-4.3x on `Test`**. An earlier
version of this paragraph computed 2.7x-3.6x / 2.6x-3.9x from runs at head `0c472149` - four
commits back, and printed without their head - which disagreed with the table above it and
with `ci.yml`. The figures are derived from the columns here, so a reader can check the
arithmetic; and because the spread is this wide, a single run is one sample of a shared
runner rather than a measurement of the change.

### Four instruments lied during this investigation, all the same way

Every wrong conclusion above came from a measurement that reported confidently about code
it never reached. This is §11.4's "a no-op measured by an instrument that bypasses the
code is not evidence of a no-op", and it cost four corrections:

| Instrument | It claimed | Reality |
|---|---|---|
| A benchmark of synthetic `QLabel`/`QWidget` trees | `apply_theme` costs 2–3 s per call; the icon cache is the cause | The widgets never requested an icon — `svg=0 icon=0 pixmap=0`, so the `clear_cache` ablation changed nothing (1.0×) |
| `gc.collect()` | the chokepoint cannot reclaim the leak | It freed 8 337 objects and moved the widget count only 38 271 → 37 638, so the survivors are not collectable cycles. **What holds them is NOT identified** — the referrer probe walked into PyQt6/sip bookkeeping — so "strong references" is the reading consistent with the measurement, not a proven mechanism |
| `sendPostedEvents(None, 0)` | the chokepoint is ineffective | `DeferredDelete` must be named explicitly; the call flushed nothing. A measurement that mis-invokes its instrument refutes the call, not the idea |
| A PowerShell `function Time-Run($label, $args)` + `@args` splat | `-n 8` takes 740 s, so parallelising made things worse | `$args` is a PowerShell **automatic** variable: the flags never reached pytest and three *serial* runs were reported as parallel. The tell was 740 s being suspiciously close to the 673 s serial figure, and two runs disagreeing on failure count for no scheduler-related reason |

The pattern is uniform: **a measurement instrument that does not reach the code produces
a confident number about it.** The defences that worked were unglamorous — read the cache
sizes, compare the failing count across runs, check the wall clock against a figure that
should be impossible.
