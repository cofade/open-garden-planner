## Case study: untouched Return wrote the rounded metric readout (#673, fixed 2026-11-13)

**Symptom**: a stored 30.48 cm container height was shown in Imperial, then the
field switched to Metric and read `30 cm`. Return without editing changed the
metadata to 30.0 and added an unwanted edit.

**Wrong theory**: retaining an exact-value shadow during the switch and protecting
only Imperial valueFromText was sufficient. Returning the exact value in Metric
alone also proved insufficient: Qt still emitted valueChanged on Return.

**Evidence**: the initial regression observed `valueChanged(30.0)` on untouched
Return. After adding the exact metric parse guard, the same test observed
`valueChanged(30.48)`: the numeric value was protected, but Qt's duplicate Return
emission remained. The real focused Properties test also pinned metadata and undo.

**Root cause**: Qt's Return-key handling deliberately emits the value again, even
when the readout is unchanged; coarse metric text can therefore become a write.

**Fix**: an unchanged readout returns its exact value in both systems. Its Return
handling blocks duplicate value signals while retaining normal key propagation
and editingFinished. Pins:
`tests/ui/test_unit_spin_box.py::test_untouched_metric_readout_after_switch_keeps_exact_value`;
`tests/ui/test_units_surfaces.py::test_focused_container_form_switches_feedback_without_rounding_edits`;
`tests/ui/test_unit_dialogs.py::test_unchanged_return_still_accepts_the_dialog`.

**Lesson**: test acceptance, not just focus/blur, and observe signals as well as
values when preserving a more precise model behind a rounded readout.
