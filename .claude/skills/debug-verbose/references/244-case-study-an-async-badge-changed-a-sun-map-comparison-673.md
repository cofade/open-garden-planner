## Case study: an async badge changed a sun-map comparison (#673, fixed 2026-11-13)

**Symptom**: the full Windows suite failed the Hours of Sun workflow's exact
before/after image comparison when changing only the time of day. The isolated
test passed.

**Wrong theory**: a different daily heatmap or a newly painted time-of-day shadow
was changing the plan. The failure did not show which pixels differed.

**Evidence**: tagged image diagnostics first reported `[673-SUN-DIFF] 0 None
badges []`. A controlled run waited for the already-required warning badge
between screenshots and reproduced `[673-SUN-DIFF] 9 (162, 238, 166, 240)` with
`sun_warning` visible. Both images were inspected: only the badge appeared.

**Root cause**: heatmap readiness and mismatch-badge readiness are independent.
The test waited for the badge after comparing screenshots, so its arrival
between captures was attributed to the clock change.

**Fix**: move the existing semantic badge-readiness wait before the first map
capture. Keep the exact whole-image equality assertion and the badge checks.
No production code or image tolerance changes. Pin:
`tests/integration/test_sun_map_workflow.py::test_hours_of_sun_from_the_button_to_the_export_and_back`.

**Lesson**: await every independently computed visible layer before recording a
reference image. A readiness future for one layer does not settle another.
