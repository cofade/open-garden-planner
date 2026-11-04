## Case study: six wrong theories, five of them instruments that did not reach the code (#509, 2026-10-18)

**Symptom.** The test suite took 912.6 s serially and gated every iteration between a change
and the owner's hands-on pass. Issue #509 proposed `pytest-xdist`, and the diagnosis was
supposed to be straightforward: measure where the time goes, then parallelise.

**Wrong theories, and each one cost real time.**

1. *"`apply_theme()` costs 2-3 s per call and the icon cache clear dominates."* Refuted by
   ablation: removing the `clear_cache` listener changed nothing, 1.0x. The benchmark had
   built synthetic `QLabel`/`QWidget` trees, which request no icons at all - the cache was
   `svg=0 icon=0 pixmap=0`. **The instrument never reached the mechanism it was testing.**
2. *"`gc.collect()` will reclaim the leaked widgets."* It freed 8 337 objects and moved the
   widget count only 38 271 -> 37 638, so they are not reachable as collectable cycles
   and the plausible one-liner would have been useless. **What holds them is NOT
   identified** - the referrer probe walked into PyQt6/sip bookkeeping and stopped - so
   "strong references" is the reading consistent with the `gc` measurement, not a proven
   mechanism. The chokepoint does not need it to be true, and claiming it would repeat
   this file's own first case study: an instrument that asserts a mechanism it never saw.
3. *"The chokepoint cannot reclaim them either."* `sendPostedEvents(None, 0)` - the shape
   that looks right - flushes nothing; `DeferredDelete` must be named explicitly. **A
   measurement that mis-invokes its instrument refutes the call, not the idea**, and I was
   one step from discarding a correct fix on that basis.
4. *"`-n 8 --dist worksteal` now takes 740 s, so parallelising made it worse."* 740 s is
   suspiciously close to the 673 s **serial** figure. `$args` is a PowerShell *automatic*
   variable, so `function Time-Run($label, $args)` + `@args` splatting meant the flags never
   reached pytest: three serial runs were reported as parallel, and the two runs disagreed on
   failure count for no scheduler-related reason.
5. *"'CI no longer pays for the suite twice, so that is 31 minutes of wall clock."* The `test`
   and `coverage` jobs have no `needs:` between them and run concurrently. What doubles is
   runner-minutes, not the wait.
6. *"`--cov` and the perf tests are mutually exclusive, so the `Coverage` job has been
   measuring something it cannot gate."* The repaint budget fails locally under tracing -
   20.29 ms against a 16.70 ms budget - and that is true. But
   `tests/perf/test_nfr_budgets.py:56-57` reads `_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"` and
   `FRAME_BUDGET_MS = 50.0 if _IS_CI else 16.7`, so **on CI the budget is 50 ms**. The
   20.29 ms was measured against the LOCAL budget and then generalised to a configuration
   nobody ran; `gh run view 39076508170` records master's `Coverage` job **succeeded**.
   One variable, both ways: `CI=true` -> 6 passed, unset -> 1 failed. **An instrument
   pointed at the right code can still answer a different question than the one you carry
   to the next file.** The corollary cost a fifth review round, and the same claim had
   already been corrected in four documents by the time it was found a fifth time in
   11.4 - so the real instrument here is `git grep`, not the measurement.

**Key evidence.** The one measurement that mattered was the cheapest: re-run the slow file
**on its own**. `test_iconography_3c.py` takes 2.14 s alone and 96.7 s in the suite; the same
file right after `test_main_window.py` takes 447 s with individual theme tests at 60-66 s.
That contradiction sends you straight to the cause, and probing `QApplication` closed it: a
clean process holds **0** widgets and one `apply_theme()` round-trip costs **1.3 ms**; after
`test_main_window.py` it holds **38 271** widgets and **1 580** top-level widgets, **0 % of
them visible**, and the round-trip costs **22 478 ms**. `qtbot.addWidget` closes a widget and
closing is not deleting, so 30 apps leaked their C++ widget graphs into the process and every
later theme switch paid for all of them.

**Lesson.** *A per-test duration table says which tests are slow, not which files are.* The
expensive tests here were the **victims** - they were the only ones calling the one global,
cache-destroying, widget-count-proportional operation in a loop. And a second lesson, from
reading the scheduler results wrong: **total call time is summed per test and inflates under
parallel execution.** The same suite read 620.6 s of call time serially and 1 700 s under
`-n auto` while its wall clock *fell* from 673.6 s to 182 s - a 2.7x "regression" that was
actually a 3.7x speed-up. Compare wall clock and ratios; the per-test table is useful for its
shape, not its sum. Finally: this box drifts. Two files that were never touched moved 37-63 %
across the session, so a single run's absolute seconds are evidence about the machine as much
as about the suite.

**Two hazards found only because parallel execution made them visible, both pre-existing.**
A test staged a canary file in the **real git working tree** and scanned it, while another
globbed that tree and read what it found - two moments, so a parallel run could read a file
that no longer existed. And two autouse fixtures, one merely *depending* on the other, left an
instant in which the settings key did not exist at all, so a read returned the production
default (`True`) and the port read 8765, and a deferred `_maybe_start_agent_api` timer landing
there started a **real** server. Neither was created by parallel execution; serial runs made
both windows too narrow to hit. `@pytest.mark.xdist_group` would have scheduled around the
first one and left it exactly as dangerous for the two-concurrent-pytest-process case that
`conftest.py` already documents for QSettings. Fix the shared state, not the schedule.

