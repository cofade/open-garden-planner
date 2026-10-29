

# Qt Quick 3D renderer — measured facts and runbook

**Status:** v0, written from the Package L0 spike (ADR-048, *Accepted — GO 2026-10-05*). Every number below
was measured in this repo; the machine is named because software rasterisers (Mesa llvmpipe,
Windows WARP) say nothing about absolute GPU speed — only about correctness, ratios and
relative cost. Art direction lives in `ogp-lush-cinematic`; this skill is the engine.
Since L1.2 the production package `ui/view3d/quick3d/` exists: its measured facts and commands
are §12, and rows it added to the tables below say "(L1.2)". **L1.10 deleted the spike**
(`spike_q3d/`, `--spike-q3d`, `scripts/bench_view3d.py`): where a row below names a spike module,
flag or class, it names where the fact was measured. docs/05 §5.8 says where each spike part
lives now; the values production was drift-guarded against are frozen in
`tests/data/l0_spike_reference.json`.

