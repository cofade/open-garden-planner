# ADR-048 evidence files

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
| `windows-v10-unfrozen.json` | [37209726610](https://github.com/cofade/open-garden-planner/actions/runs/37209726610) | a275da2 | `--cold`; the sky fix on D3D11: QML load 1705 → 52 ms, preset + mood + sun ~3.0 s → 0.39 s |
| `windows-v10-frozen.json` | same | a275da2 | All 39 checks of the time green, but the second-window frame read 9.72: the white ground no check covered yet (ADR-048 entry 4); leak gate 3.8 MB/reload |
| `windows-v10-frozen-warm.json` | same | a275da2 | Warm relaunch (three caches found) |
| `windows-v10-frozen-leakctl.json` | same | a275da2 | Positive control: 25 MB held per reload read 29.5 MB/reload and failed the gate. dist delta +1.8 MB, the same six files as v9 (no separate footprint file) |
| `windows-v11-unfrozen.json` | [37213201005](https://github.com/cofade/open-garden-planner/actions/runs/37213201005) | 479d78c | `--cold` |
| `windows-v11-frozen.json` | same | 479d78c | All 41 checks, including the two frame checks added in senior pass 4: probe restore 0.0 and second window 0.0 on D3D11 (v10: 9.72); leak gate 4.0 MB/reload |
| `windows-v11-frozen-warm.json` | same | 479d78c | Warm relaunch (three caches found) |
| `windows-v11-frozen-leakctl.json` | same | 479d78c | Positive control: 25 MB held per reload read 28.7 MB/reload and failed the gate. dist delta +1.8 MB (no separate footprint file) |
| `windows-v12-unfrozen.json` | [37216442834](https://github.com/cofade/open-garden-planner/actions/runs/37216442834) | e862785 | `--cold`; the first run with 3D creator round 3 |
| `windows-v12-frozen.json` | same | e862785 | All 41 checks; probe restore and second window 0.0; leak gate 9.0 MB/reload, a pass near the bound (ADR-048 entry 10: the dip-then-rise table) |
| `windows-v12-frozen-warm.json` | same | e862785 | Warm relaunch (three caches found) |
| `windows-v12-frozen-leakctl.json` | same | e862785 | Positive control: 25 MB held per reload read 28.3 MB/reload and failed the gate. dist delta +1.8 MB (no separate footprint file) |
| `windows-v13-unfrozen.json` | [37285285890](https://github.com/cofade/open-garden-planner/actions/runs/37285285890) | cf7eb66 | `--cold`; spike code identical to v12 |
| `windows-v13-frozen.json` | same | cf7eb66 | All 41 checks; leak gate 1.8 MB/reload for the code that read 9.0 in v12 |
| `windows-v13-frozen-warm.json` | same | cf7eb66 | Warm relaunch (three caches found) |
| `windows-v13-frozen-leakctl.json` | same | cf7eb66 | Positive control: 25 MB held per reload read 32.9 MB/reload and failed the gate |
| `windows-v13-frozen-longsoak.json` | same | cf7eb66 | **Experiment, not a gate:** 50 reloads at 640×360, no probes; +87 MB by reload 50 (ADR-048 entry 10). dist delta +1.7 MB (no separate footprint file) |
| `windows-v14-unfrozen.json` | [37293091187](https://github.com/cofade/open-garden-planner/actions/runs/37293091187) | f1b998e | `--cold`; the first run with 3D creator round 4 |
| `windows-v14-frozen.json` | same | f1b998e | All 41 checks; low IoU 0.984 / 0.982 / 0.964 with the VeryHigh map; isolated dark pixels 0 / 5 on golden-hour frames (not a sharpening check); leak gate 3.4 MB/reload |
| `windows-v14-frozen-warm.json` | same | f1b998e | Warm relaunch (three caches found) |
| `windows-v14-frozen-leakctl.json` | same | f1b998e | Positive control: 25 MB held per reload read 30.9 MB/reload and failed the gate |
| `windows-v14-frozen-longsoak.json` | same | f1b998e | **Experiment, not a gate:** 50 reloads; +196 MB by reload 50 (ADR-048 entry 10). dist delta +1.7 MB |
| `windows-v15-unfrozen.json` | [37296804412](https://github.com/cofade/open-garden-planner/actions/runs/37296804412) | 831f808 | `--cold`; spike code identical to v14 |
| `windows-v15-frozen.json` | same | 831f808 | All 41 checks; leak gate 7.5 MB/reload for the code that read 3.4 in v14 |
| `windows-v15-frozen-warm.json` | same | 831f808 | Warm relaunch (three caches found) |
| `windows-v15-frozen-leakctl.json` | same | 831f808 | Positive control: 25 MB held per reload read 31.2 MB/reload and failed the gate |
| `windows-v15-frozen-longsoak.json` | same | 831f808 | **Experiment, not a gate:** 100 reloads; +62 MB by reload 50, 0.21 MB/reload over reloads 51–100 (ADR-048 entry 10). dist delta +1.7 MB |
| `windows-v16-unfrozen.json` | [37301609487](https://github.com/cofade/open-garden-planner/actions/runs/37301609487) | f71cdef | `--cold`; after the merge with master and senior pass 5's fixes |
| `windows-v16-frozen.json` | same | f71cdef | All 41 checks, the restore check now required whenever the probes ran; probe restore and second window 0.0; leak gate 4.2 MB/reload |
| `windows-v16-frozen-warm.json` | same | f71cdef | Warm relaunch (three caches found) |
| `windows-v16-frozen-leakctl.json` | same | f71cdef | Positive control: 25 MB held per reload read 32.4 MB/reload and failed the gate |
| `windows-v16-frozen-longsoak.json` | same | f71cdef | **Experiment, not a gate:** 100 reloads, the same soak path as v14 and v15; +134 MB by reload 50, flat over reloads 48–71, then +85 MB; 2.03 MB/reload over reloads 51–100 (ADR-048 entry 10). dist delta +1.8 MB |
| `container-6f0c4f4.json` | — | 6f0c4f4 | Cloud container, Mesa llvmpipe (OpenGL), 1280×720, all shots. Ran next to two reviewer renders: correctness numbers valid, timings inflated |
| `container-f71cdef-soak.json` | — | f71cdef | Render tier (llvmpipe, 640×360): the leak gate's two runs on Linux RSS. Clean 20-reload soak 1878.5 → 1883.7 MB, Theil–Sen over reloads 11–20 0.0 MB/reload; control 28.2 MB/reload for 25 MB held |

Same code on different runner instances differs by up to 2× in timings; compare ranges, not single values.
