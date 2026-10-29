## Case study: repaint events counted as idle (PR #645 CI)

**Symptom.** Coverage partition 0 measured one `scene_changed` event during
the audit driver's idle period. Other runs passed.
**Wrong theory.** A fixed delay after the initial fit guaranteed that the
later synchronous repaint loop left no queued work.
**Evidence.** A regression queued scene invalidation after the fifteenth
repaint. Tagged `[AUDIT-IDLE] changed regions=...` output and its caller stack
placed delivery in the idle `qWait`, after the repaint workload ended.
Draining scene events alone then left one debounced minimap render in idle.
**Fix.** Drain queued repaint events and wait for the real minimap timer to
retire before attaching the idle counters. Refuse a workload that cannot
settle within five seconds. No idle count assertion was relaxed.
**Pinned by.** Both parameter cases in
`tests/integration/test_audit_performance_driver.py`.
**Lesson.** A benchmark phase starts at an event-completion boundary, not
merely when the last synchronous call returns.
