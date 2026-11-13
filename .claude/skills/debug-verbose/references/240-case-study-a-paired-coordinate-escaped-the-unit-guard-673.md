## Case study: a paired coordinate escaped the unit guard (#673, fixed 2026-11-13)

**Symptom**: a vertex annotation still read `(2.44, 1.22) m` in Imperial while
edge lengths converted correctly.

**Wrong theory**: checking a unit immediately after a formatted value covered
all inline length text.

**Evidence**: the senior identified `_format_coordinate`; the real helper failed
`test_vertex_coordinates_follow_units_and_preserve_metric_pairs` under Imperial.
Its literal suffix was `) m`, so the original guard did not match it.

**Root cause**: paired coordinates had their own metric formatter, and the guard
ignored a closing parenthesis between the last value and the unit.

**Fix**: a pure `format_coordinates` owns the pair, with a locale adapter for the
separator and Qt numeric policy. The guard accepts a closing bracket/parenthesis
before the unit. Pins: `tests/unit/test_measurement_display.py::test_vertex_coordinates_follow_units_and_preserve_metric_pairs`;
`tests/unit/test_units_guard.py::test_guard_catches_paired_coordinate_units`.

**Lesson**: test the guard against actual formatting structures, and test the
annotation as well as the nearby measurement label.
