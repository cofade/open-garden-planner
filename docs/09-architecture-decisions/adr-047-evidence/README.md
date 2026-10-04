# ADR-047 evidence files

`metrics.json` of the temporary Windows evidence workflow (`spike-q3d.yml`, windows-latest, no GPU, so Qt picks Direct3D 11 on WARP), plus one container run of v6's commit for the OpenGL side of the same probes. The Windows files were extracted from the job logs, because the artifact host was unreachable from the analysis container and CI logs expire. Each file carries a `_provenance` block with the run, commit, runner and mode.

| File | Run | Commit | Notes |
|---|---|---|---|
| `windows-v2-unfrozen.json` | [37187375015](https://github.com/cofade/open-garden-planner/actions/runs/37187375015) | 65d0df2 | First logged run; shows the ~100 s grab |
| `windows-v2-frozen.json` | same | 65d0df2 | Failed in 1 s: the bundle has no test fixtures and no `--plan` was given |
| `windows-v3-unfrozen.json` | [37188274098](https://github.com/cofade/open-garden-planner/actions/runs/37188274098) | 2b69923 | `QSG_RENDER_LOOP=basic` A/B |
| `windows-v3-frozen.json` | same | 2b69923 | Full set; picks 0/20 (the re-attach bug), so its soak measured an empty garden |
| `windows-v4-unfrozen.json` | [37189802755](https://github.com/cofade/open-garden-planner/actions/runs/37189802755) | 337be91 | |
| `windows-v4-frozen.json` | same | 337be91 | After the re-attach fix: picks 20/20 and 20/20 after re-attach |
| — | [37191065475](https://github.com/cofade/open-garden-planner/actions/runs/37191065475) (v5) | d84488a | Refactor-only re-run of v4's probes, green; not extracted |
| `windows-v6-unfrozen.json` | [37199625103](https://github.com/cofade/open-garden-planner/actions/runs/37199625103) | 6f0c4f4 | |
| `windows-v6-frozen.json` | same | 6f0c4f4 | First run judged by the driver's thresholds: 20 of 21 passed; the one FAIL was a driver bug (a measured 0.0 px read as 99) |
| `windows-v6-footprint.txt` | same | 6f0c4f4 | Criterion 9: branch and master dist sizes from the same job, delta +1.7 MB, the 6 files only in the branch |
| `windows-v7-unfrozen.json` | [37201554005](https://github.com/cofade/open-garden-planner/actions/runs/37201554005) | 7a4dcb6 | |
| `windows-v7-frozen.json` | same | 7a4dcb6 | `--soak 50` with 10 project reloads on D3D11: 31 of 32 checks passed; the leak gate read the noisy working set (see the file's provenance) |
| `windows-v8-unfrozen.json` | [37203468689](https://github.com/cofade/open-garden-planner/actions/runs/37203468689) | 06483be | `--cold` |
| `windows-v8-frozen.json` | same | 06483be | First launch of the bundle (no caches found); leak gate inconclusive (see provenance) |
| `windows-v8-frozen-warm.json` | same | 06483be | Second launch of the same shot; found the three caches the first launch wrote |
| `windows-v9-unfrozen.json` | [37206644502](https://github.com/cofade/open-garden-planner/actions/runs/37206644502) | 6ea2d17 | `--cold` |
| `windows-v9-frozen.json` | same | 6ea2d17 | First fully green run: the pre-registered 20-reload leak gate passes (1.5 MB/reload) |
| `windows-v9-frozen-warm.json` | same | 6ea2d17 | Warm relaunch (three caches found) |
| `windows-v9-frozen-leakctl.json` | same | 6ea2d17 | The leak gate's positive control: 25 MB kept per reload read 33.6 MB/reload and failed the gate, as it must |
| `windows-v9-footprint.txt` | same | 6ea2d17 | dist delta +1.8 MB |
| `container-6f0c4f4.json` | — | 6f0c4f4 | Cloud container, Mesa llvmpipe (OpenGL), 1280×720, all shots. Ran next to two reviewer renders: correctness numbers valid, timings inflated |

Same code on different runner instances differs by up to 2× in timings; compare ranges, not single values.
