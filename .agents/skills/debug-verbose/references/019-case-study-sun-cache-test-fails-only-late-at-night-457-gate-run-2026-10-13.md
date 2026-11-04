## Case study: sun-cache test fails only late at night (#457 gate run, 2026-10-13)

**Symptom.** Full validation and an isolated sun-mismatch workflow failed with
exposure_reason `absent` instead of `ready` after adding one hour.
**Wrong theories.** No localization or timing theory was adopted before tracing.
**Evidence.** `[A5-SUN-CLOCK] before= 2026-06-21 23:49:00 after=
2026-06-22 00:49:00 reason= ready`; caller stack identified the test's datetime write.
**Root cause.** The fixture set only the date, retaining the host time. After 23:00,
its alleged within-day edit changed the plan date and correctly invalidated the
heatmap (ADR-053). The test's expectation, not the cache, was wrong.
**Fix.** Set the fixture's time of day explicitly to noon. Retain real worker,
geometry, cache and invalidation assertions and all timeouts. Remove diagnostics.
**Lesson.** A test claiming a within-day edit must fix both date and time; a
set_date call does not fix the wall clock's hour.


