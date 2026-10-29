## Case study: re-promoting a release counted its downloads twice (ADR-067 chart review)

**Symptom.** A final release at count 5, temporarily marked prerelease at 6 and
restored to final at 7, produced a chart total of 12 instead of 7.
**Wrong assumption.** The immediately preceding prerelease flag was treated as
proof that the counter had never been admitted to the regular-release chart.
**Evidence.** The isolated instrumented report printed
`[DL-ADMIT] count=7 old_count=6 old_pre=True admitted=7 kind=new`, with a
`[DL-ADMIT-STACK]` traceback at re-admission; `[DL-TOTAL] 12.0 expected=7`.
**Root cause.** Last observation and last counted observation shared one map.
A mutable visibility flag erased the distinction between initial promotion and
re-promotion of an already-counted asset.
**Fix.** Keep independent observed and admitted counter maps. Re-promotion adds
only the delta since last admission, retaining that real multi-date window as
an estimate. First promotion still admits its full counter once. Pinned by
`tests/unit/test_download_stats_report.py` (temporary-prerelease regression).
**Lesson.** A current classification is not a lifetime admission record. Track
what was actually counted independently of whether the asset is currently visible.


**Reset follow-up.** Comparing only with the last admitted counter still lost a reset
if the hidden counter recovered: `[DL-RESET] count=12 last_counted=10
last_observed=3 admitted=2 kind=normal` yielded 12 instead of 22. For assets
already admitted, accumulate increments and resets against EVERY observed counter,
including excluded rows, then publish the pending sum on restoration. Two hidden
resets (10 -> 3 -> 2 -> 12) total 25, not 22 or 12. Both recovered-above-old and
multiple-reset cases are pinned in the same report test module. Observation,
admission and pending increments are three different pieces of accounting state.


