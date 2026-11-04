## Case study: an excluded observation completed an uncovered chart day (ADR-067)

**Symptom.** A historical baseline ending at 17:00 lost its partial-day label after
a later snapshot contained only an excluded prerelease observation.
**Wrong assumption.** A newer global snapshot was treated as chart coverage even
when none of its observations had been admitted.
**Evidence.** An isolated instrumented copy printed `[DL-COVERAGE] baseline=
2026-08-02T17:00:00Z latest_global=2026-08-03T00:17:00Z last_day=2026-08-02`;
`[DL-PARTIAL] before False`, whereas coverage still ended at 17:00. The corrected
counterpart printed `[DL-PARTIAL] after True` without changing any counts.
**Fix.** Track the endpoint of admitted coverage separately from the newest raw
snapshot. Keep the raw timestamp for freshness and use the admitted endpoint for
the partial label. Pinned by `tests/unit/test_download_stats_report.py` (excluded
observations do not complete the baseline day; restored admission does).
**Lesson.** Fresh input is not necessarily additional coverage of an output series.
