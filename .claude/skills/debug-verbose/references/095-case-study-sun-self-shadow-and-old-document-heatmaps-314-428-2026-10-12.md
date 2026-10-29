## Case study: sun self-shadow and old-document heatmaps (#314/#428, 2026-10-12)

**Symptom.** Both reference tomatoes read zero hours, and a heatmap worker finishing after New/Open/recovery repainted the replacement plan.
**Wrong theories.** The centre-lookup acceptance assumption was rejected by the measured self-shadow probe. No alternative solar formula, date owner or per-caller reset was adopted. Date-only clearing and `is_running` checks do not establish document ownership.
**Key evidence.** The planning probe recorded `north=0 h south=0 h` with all casters and `north=0 h south=16.5 h` excluding each receiver only. Six deterministic controlled-worker regressions failed on `assert not heatmap.heatmap_visible()` with actual True before the reset fix; malformed-load preservation already passed. Queued timing waits for run() to return without delivering success to the GUI, proving thread completion is not queued-signal completion.
**Root cause.** A solid plant shadows its own ground centre. The old controller lacked the canonical document-reset subscription and result-generation/signature ownership checks.
**Fix/lesson.** Retain the displayed grid policy; accumulate sparse owner-aware receiver sun in the same explicit worker. Reset on `CanvasScene.document_replaced` before teardown, reject stale result ownership and retain the worker until finished. Test missing/stale values as unavailable, not zero/pass; compare against the independent point reference and measured constants. General Diagnostics needs one publisher for all cached producers. No debug instrumentation remains in committed application code.


