# CI latency investigation (#601, 26 October 2026)

## Ground truth and scope

The baseline is `712df90d` (master, v1.32.1). Issue #601 names historical run
40310815603: 18,380 parallel passes plus 252 skips in 733.84 s under coverage,
then 103 serial passes plus 13 skips in 190.29 s. Those 18,748 collected cases
include skips; they are not 18,748 passes. The issue's 116 perf cases are real.
The job, rather than the entire runner pool's CPU time, bounds delivery latency.

This change covers #601 only. It changes test scheduling and repeated test work,
not application code, coverage floors, the locked Python 3.11 interpreter or the
render tier's scope. #540, #600 and #603 remain separate renderer investigations.

## Corrections to the initial hypotheses

- Removing `--cov-branch` alone does nothing: `[tool.coverage.run] branch = true`
  independently enables it. The controlled experiment explicitly sets this false
  for its line-only arm. The production workflow retains branch tracing.
- The 47 `TestWaitReady` cases are not mostly mock contracts. Thirty need the
  quiet runner; seventeen signature/spy/fake-clock/count/behavior cases do not.
- The documentation guard's wide task sweep is expensive computation, rather
  than simply interpreter startup: locally the sweep-consuming tests cost
  18.45 s and 19.02 s, while the harvest-only CLI check cost 0.13 s. Keep real
  subprocess execution and all assertions; run each sweep once instead of twice.
- The marker guard parses its main input and its support-import input separately.
  A cProfile probe recorded 1,069 `ast.parse` calls across 528 test modules.
  The shared AST/index now supplies class ownership and marker ancestry as well.
- A tagged GC probe recorded 52 full collections, 50 from one receiver loop.
  Those acyclic wrappers die immediately; every one of the fifty rounds now
  asserts weak-reference, registry and channel cleanup. A separate self-cycle
  still requires and exercises real cyclic collection.
- Coverage's faster `sys.monitoring` core is unavailable on the locked Python
  3.11 runtime. An interpreter migration is a different change; see the
  [coverage.py core reference](https://coverage.readthedocs.io/en/7.13.5/config.html#run-core).

## Scheduling decision

Keep the uninstrumented `Test` job, including its `--durations=0` artifact and
quiet serial performance run. Traced budgets deliberately allow additional slack;
a traced run cannot replace that uninstrumented evidence. Required check names
and `quality/master-protection.json` stay unchanged.

Split non-perf coverage onto two Linux runners, each with its normal four xdist
workers. `scripts/ci_coverage_shard.py` maps each UTF-8 test node ID through SHA-256
to partition 0 or 1. Membership does not depend on collection order or Python's
hash randomization. The perf coverage run gets its own quiet serial runner.
Each producer uploads one visible data filename. The existing required `Coverage`
check runs even if a producer fails or skips; it first requires both producer job
results to be successful, then combines three explicit filenames before emitting
XML and enforcing the unchanged package and per-file line floors. Missing data
cannot silently become a smaller report. Branch data remains available.

The tradeoff is additional runner setup/collection and potentially more total
runner minutes. This is a latency change, not a claim of lower total CPU cost.
No paid/larger runner, new dependency, floor reduction or removed test scenario
is needed. The two duplicate harness tests were consolidated into their existing
lint consumers, retaining every invariant and both measured populations.

## Local measurements

Windows 11, Python 3.11.9; sequential targeted samples, not CI estimates:

| Measurement | Before | After |
|---|---:|---:|
| Three hotspot files together | 50 passes, 54.15 s | 53 passes, 32.46 s |
| Marker guard's repository scan | 10.64 s | 5.83 s |
| Task-sweep consumer call time, summed | 37.47 s | 21.42 s |
| Perf collection | 116 cases | 89 cases |

The absolute samples drift with machine load; no duration lower bound is added.
Mechanical pins assert one parse per input, marker placement, complete disjoint
partitions, real xdist selection and a full branch-data merge. The merge fixture
has code only perf executes: a control omitting perf has incomplete line coverage.
The original workflow mutation replay remains 16 cases (14 caught, 2 controls).
Six additional topology mutations reject a missing shard, missing perf dependency,
advisory/conditional measurement, removed branch flag and lost merge input.

## Runner evidence

[Controlled run 40325455208](https://github.com/cofade/open-garden-planner/actions/runs/40325455208)
checks out the full immutable `712df90d` master SHA, uses the locked Python 3.11.9
environment on one `ubuntu-latest` runner, and runs branch then line-only tracing
sequentially. Both arms run the full parallel suite and append the serial perf
set before enforcing every existing floor. It passed.

| External process wall time (`/usr/bin/time`) | Branch | Line only |
|---|---:|---:|
| Non-perf suite | 984.19 s | 918.90 s |
| Serial perf append | 251.52 s | 233.85 s |
| Sum | 1,235.71 s | 1,152.75 s |

Line-only saved **82.96 s (6.7%)** in this one pair, below the issue's proposed
2–3 minutes. It is not a randomized multi-round trial: line ran second and the
shared runner's load can drift. The result does not justify a universal speed-up
claim. Each arm passed 18,380 parallel and 103 serial cases, with 252 and 13 skips.
Both covered exactly **63,209 of 73,148 statements (86.4%)**, with zero unresolved
statements and zero floor regressions. Branch tracing additionally reported
**15,035 of 21,014 branches (71.5%)**. Retaining it avoids deleting that diagnostic
information for the modest measured saving.

The experiment workflow is preserved in temporary commit `84a9e759`, not in the
delivery diff. Its commands use `--durations=0 --cov=open_garden_planner`, then
`-m perf -n 0 --cov-append`; `branch = false` is set explicitly in the line arm.
Its artifact contains both XML reports, JUnit reports, full duration logs,
external process times and floor summaries. Failed harness setup runs are excluded
from timing claims: the initial harness omitted readable action version comments;
its replacement used an abbreviated checkout SHA, which checkout treated as a ref
name. Neither completed a valid comparison.

The first partitioned run (40324923512, before the hash refinement) caught stale
eight-job documentation in its tests. Both measurement failures propagated to the
required Coverage check; the aggregation did not report a partial green result.
The final delivery's current-head CI results are attached to its draft PR.

## Perf-marker audit

All 116 collected baseline cases were inspected. Twenty-seven deterministic cases
return to the parallel pool: seventeen host contracts, eight plant-build contracts
and two line-scenario checks. The remaining 89 include actual elapsed-time bounds,
real timer/throttle scenarios and shared render-measurement scenarios. Offscreen
render-tier skips remain skips; moving their markers would not shorten Coverage.

The file inventory below records baseline case counts and the disposition. Counts
include parameter expansions; they are not counts of Python function definitions.


| File | Before | Serial after | Reason |
|---|---:|---:|---|
| `tests/integration/test_agent_api_shutdown.py` | 2 | 2 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_map_picker_dialog.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_plant_forge.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_plant_forge_workspace.py` | 2 | 2 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_scene3d_ground_bake.py` | 2 | 2 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_scene3d_ground_render.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_shadow_overlay.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_sun_heatmap.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_timeline_quick3d.py` | 2 | 2 | real elapsed-time regrowth throttle across lifetime boundaries |
| `tests/integration/test_view3d_default_render.py` | 5 | 5 | shared real-app startup/frame/playback measurement scenarios; offscreen skips |
| `tests/integration/test_view3d_looks_render.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_view3d_plan_revision.py` | 7 | 7 | real quiet-gap and preview-latency bounds |
| `tests/integration/test_view3d_selection_workspace.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/integration/test_view3d_sync_controller.py` | 2 | 2 | real held-key/timer cadence, including the no-throttle control |
| `tests/integration/test_view3d_workspace_render.py` | 3 | 3 | edit/pan latency bounds and an explicit large-plan latency measurement; offscreen skips |
| `tests/perf/test_nfr_budgets.py` | 6 | 4 | 4 repaint/line-cost bounds retained; 2 scenario checks parallel |
| `tests/perf/test_scene3d_built_world_budget.py` | 2 | 2 | real duration/budget or timer-driven measurement retained |
| `tests/perf/test_scene3d_plants_budget.py` | 12 | 4 | 4 timed build/scrub cases retained; 8 deterministic geometry/cache contracts parallel |
| `tests/perf/test_scene3d_snapshot_budget.py` | 6 | 6 | real duration/budget or timer-driven measurement retained |
| `tests/perf/test_sun_receiver_budget.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/perf/test_view3d_selection_walk_budget.py` | 2 | 2 | real duration/budget or timer-driven measurement retained |
| `tests/ui/test_quick3d_host.py` | 47 | 30 | 30 real timer/duration cases retained; 17 deterministic contracts parallel |
| `tests/unit/test_phenology.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/unit/test_plant_forge_l31.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/unit/test_plant_forge_l32.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/unit/test_plant_forge_l33.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/unit/test_plant_forge_l34.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/unit/test_point_snapper.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
| `tests/unit/test_quick3d_selftest.py` | 1 | 1 | child supervisor must have exited during a measured real-time window |
| `tests/unit/test_snap_spatial_index.py` | 1 | 1 | real duration/budget or timer-driven measurement retained |
