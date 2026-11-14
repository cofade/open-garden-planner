## Case study: profile header clipped wrapped content (#905, fixed 2026-11-14)

**Symptom**: the compact Plant Details header clipped a longer description.

**Wrong theory**: capping the header at sizeHint proved that its content fitted.

**Evidence**: the pre-fix branch at 414 px panel width, with a larger UI font,
printed `[PROFILE] width=306 height=88 needed=110`. The test compared each label's
allocated height with its heightForWidth(actual width) and failed before the fix.

**Root cause**: a Maximum vertical policy capped a header containing wrapped
labels at an unwrapped size hint.

**Fix**: Preferred vertical policy with height-for-width explicitly enabled;
the details scroll area retains the stretch. Regression tests check both full
wrapped content and surplus space going to details, at a larger UI font too.

**Lesson**: measure whether content fits at the actual width. A sizeHint cap is
not a readability assertion. Pin:
`tests/ui/test_plant_database_panel.py::test_wrapped_header_content_is_fully_readable`.
