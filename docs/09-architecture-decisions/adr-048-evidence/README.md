# ADR-048 evidence files

`metrics.json` of the temporary Windows evidence workflow (`spike-q3d.yml`, windows-latest, no GPU, so Qt picks Direct3D 11 on WARP), plus container runs (Mesa llvmpipe, OpenGL): one of v6's commit for the OpenGL side of the same probes, and the render tier's leak-gate soaks of five commits. The Windows files were extracted from the job logs, because the artifact host was unreachable from the analysis container and CI logs expire. Each Windows JSON file carries a `_provenance` block with the run, commit, runner and mode; the footprint text files and `container-6f0c4f4.json` name their commit (and run, where there is one) in their own header, and `container-render-tier-soaks.json` names it per run.

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
| `windows-v16-frozen-longsoak.json` | same | f71cdef | **Experiment, not a gate:** 100 reloads, the same soak path as v14 and v15; +134 MB by reload 50, within 15 MB over reloads 48–71, then 768.1 → 848.0 MB (reload 71 → 99); 2.03 MB/reload over reloads 51–100 (ADR-048 entry 10). dist delta +1.8 MB |
| `windows-v17-unfrozen.json` | [37308218700](https://github.com/cofade/open-garden-planner/actions/runs/37308218700) | 308c773 | `--cold`; the first run that records its parsed flags (`args`) |
| `windows-v17-frozen.json` | same | 308c773 | All 41 checks; probe restore and second window 0.0; leak gate 5.1 MB/reload |
| `windows-v17-frozen-warm.json` | same | 308c773 | Warm relaunch (three caches found) |
| `windows-v17-frozen-leakctl.json` | same | 308c773 | Positive control: 25 MB held per reload read 29.2 MB/reload and failed the gate |
| `windows-v17-frozen-longsoak.json` | same | 308c773 | **Experiment, not a gate:** 100 reloads, the soak path of v14–v16; +210 MB by reload 50; 3.05 MB/reload over reloads 51–100, its maximum at reload 100 (ADR-048 entry 10). dist delta +1.8 MB |
| `windows-v18-unfrozen.json` | [37312863784](https://github.com/cofade/open-garden-planner/actions/runs/37312863784) | 46d88ff | `--cold`; the PR head when draft #413 was opened |
| `windows-v18-frozen.json` | same | 46d88ff | All 41 checks; probe restore and second window 0.0; leak gate 3.5 MB/reload |
| `windows-v18-frozen-warm.json` | same | 46d88ff | Warm relaunch (three caches found) |
| `windows-v18-frozen-leakctl.json` | same | 46d88ff | Positive control: 25 MB held per reload read 28.3 MB/reload and failed the gate |
| `windows-v18-frozen-longsoak.json` | same | 46d88ff | **Experiment, not a gate:** 100 reloads, the soak path of v14–v17; +103 MB by reload 50; 0.08 MB/reload over reloads 51–100, an interval that includes zero, its maximum at reload 82 (ADR-048 entry 10). dist delta +1.8 MB |
| `windows-v19-unfrozen.json` | [37317036835](https://github.com/cofade/open-garden-planner/actions/runs/37317036835) | 123f0af | `--cold` |
| `windows-v19-frozen.json` | same | 123f0af | All 41 checks; probe restore and second window 0.0; leak gate 1.5 MB/reload |
| `windows-v19-frozen-warm.json` | same | 123f0af | Warm relaunch (three caches found) |
| `windows-v19-frozen-leakctl.json` | same | 123f0af | Positive control: 25 MB held per reload read 29.9 MB/reload and failed the gate |
| `windows-v19-frozen-longsoak.json` | same | 123f0af | **Experiment, not a gate:** 100 reloads, the soak path of v14–v18; +222 MB by reload 50; 3.50 MB/reload over reloads 51–100, its maximum at reload 100 (ADR-048 entry 10). dist delta +1.8 MB |
| `container-6f0c4f4.json` | — | 6f0c4f4 | Cloud container, Mesa llvmpipe (OpenGL), 1280×720, all shots. Ran next to two reviewer renders: correctness numbers valid, timings inflated |
| `container-render-tier-soaks.json` | — | 36e3d18, a64ae9e, f71cdef, 308c773, 46d88ff | Render tier (llvmpipe, 640×360): the leak gate's clean run and control on Linux RSS, per commit. Clean slopes 0.46 / 0.01 / 0.00 / 0.00 / 0.00 MB/reload, controls 26.97 / 27.85 / 28.24 / 24.5 / 26.28 for 25 MB held (479d78c's run, 0.02 and 25.0, was not kept) |

Same code on different runner instances differs by up to 2× in timings; compare ranges, not single values.

**Owner-GPU run (2026-10-05).** The temporary workflow and its driver (`spike-q3d.yml`, `scripts/spike_q3d_ci.py`, `tests/unit/test_spike_q3d_ci_verdict.py`) were deleted when ADR-048 was accepted (GO). The decision also rests on the owner's dedicated-GPU run at 1920×1080 (Direct3D 11, frozen bundle of `e1794e8`), committed here (the JSON files carry a `_provenance` block):

| File | Mode | Notes |
|---|---|---|
| `owner-gpu-cold.json` | cold full set (all probes + `--soak 100`) | `status: ok`, exit 0; the leak tail slope 15.73 MB/reload over reloads 11–20, above the <10 gate |
| `owner-gpu-cold-spike.log` | the same run | the per-phase log; ends `[done] status=ok` |
| `owner-gpu-warm-a.json` / `owner-gpu-warm-b.json` | warm runs 1 and 2 (`golden_hour`, low) | `open_ms` 1140.3 / 1149.2 (the second is the warm number) |

The numbers are summarised in ADR-048 entry 19.
