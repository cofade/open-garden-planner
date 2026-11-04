## Case study: green on every dev run, red on the Linux runner — a fixed wait for a pass the product holds (Phase 17 L1.3, fixed 2026-10-19)

**Symptom**: `tests/integration/test_view3d_workspace.py::test_a_plan_with_a_refused_item_shows_the_indicator_and_fixing_it_clears_it`
read `workspace.problems_text() == ''` 120 ms after the switch to Split — on CI only; green in
every local run.

**Wrong theory**: *"the indicator is filled late — a race in the product"*. It was not tested,
it was measured.

**Key evidence**: the CI log had the refused item's snapshot line in the test's **teardown**
(the pass ran after the assertion). A probe that recorded `problems_text()` inside a slot on
the controller's `applied` signal: set in the same call, 10 of 10. Time from the switch to the
pass: 53–62 ms when the "Building the 3D view…" label paints, 295–307 ms when its paint is
withheld (the pass is held for the paint, or 250 ms, then 25 ms). A scratch pytest plugin that
withholds the label's paint from the workspace's filter made the slow path deterministic: the
old test failed with CI's exact message — and so did **21 widget tests and the §8.10 workflow**,
because the shared helpers (`Bench.settle()`, `_calls()`) waited a fixed 80 ms.

**Root cause**: test helpers guessed how fast a deliberately HELD pass would run.

**Fix**: one condition (`pipeline_settled`: no first pass held, none posted, none timed), waited
for; the indicator asserted at the signal that sets it.

**Lesson**: **force the slow path to prove a timing test** — a plugin that withholds one event
turned a once-a-week CI failure into 23 deterministic ones. A fixed wait in a test is a guess
about the slowest machine it will ever run on.

