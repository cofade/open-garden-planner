# ADR-047 evidence files

`metrics.json` of the temporary Windows evidence workflow (`spike-q3d.yml`, windows-latest, no GPU, so Qt picks Direct3D 11 on WARP). They were extracted from the job logs, because the artifact host was unreachable from the analysis container and CI logs expire. Each file carries a `_provenance` block with the run, commit, runner and mode.

| File | Run | Commit | Notes |
|---|---|---|---|
| `windows-v2-unfrozen.json` | [37187375015](https://github.com/cofade/open-garden-planner/actions/runs/37187375015) | 65d0df2 | First logged run; shows the ~100 s grab |
| `windows-v2-frozen.json` | same | 65d0df2 | Failed in 1 s: the bundle has no test fixtures and no `--plan` was given |
| `windows-v3-unfrozen.json` | [37188274098](https://github.com/cofade/open-garden-planner/actions/runs/37188274098) | 2b69923 | `QSG_RENDER_LOOP=basic` A/B |
| `windows-v3-frozen.json` | same | 2b69923 | Full set; picks 0/20 (the re-attach bug), so its soak measured an empty garden |
| `windows-v4-unfrozen.json` | [37189802755](https://github.com/cofade/open-garden-planner/actions/runs/37189802755) | 337be91 | |
| `windows-v4-frozen.json` | same | 337be91 | After the re-attach fix: picks 20/20 and 20/20 after re-attach |

Same code on different runner instances differs by up to 2× in timings; compare ranges, not single values.
