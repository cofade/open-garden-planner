## Case study: unit feedback waited for a focused form rebuild (#673, fixed 2026-11-13)

**Symptom**: a container's VolumeSpinBox changed units but the effective-volume
QLabel stayed in litres while the field had actual focus.

**Wrong theory**: the existing deferred theme rebuild was a suitable unit refresh.
It deliberately skips rebuilding a form while an editor has focus.

**Evidence**: independent review showed a live focused container form still saying
`300.0 L` after Imperial was selected. The focused-editor guard returned after
`_rebuild_for_theme` had reset the form identity.

**Root cause**: a measurement label depends on the unit now; a stale theme icon can
wait for the next rebuild. Those refresh requirements are different.

**Fix**: defer the existing `_refresh_field_values` path, which updates derived
labels while protecting focused text and blocking incidental signals. The unit
fields already reformat themselves. Pin:
`tests/ui/test_units_surfaces.py::test_focused_container_form_switches_feedback_without_rounding_edits`.

**Lesson**: reuse the refresh with the correct focus contract, not simply the
nearest deferred callback.
