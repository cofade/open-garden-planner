## Case study: an angle dialog was migrated as a length (#673, fixed 2026-11-13)

**Symptom**: the target angle read as feet in Imperial; typing 90 changed it to
27.432 degrees. The independent senior probe recorded a 90-degree initial value
shown as `295' 3 1/4"`.

**Wrong theory**: every `self._spin = QDoubleSpinBox()` in the constraint dialog
module represented a distance. The shared variable name hid the angle dialog.

**Evidence**: `test_angle_entry_is_degrees_in_imperial` failed because the actual
angle widget was a `LengthSpinBox`; the existing tests only exercised metric mode.

**Root cause**: a constructor replacement included `AngleInputDialog`.

**Fix**: restore its ordinary `QDoubleSpinBox`. Pin the real Imperial text and
Return-key entry path in `tests/ui/test_unit_dialogs.py::test_angle_entry_is_degrees_in_imperial`.

**Lesson**: classify each numeric field by quantity before migrating it; shared
widget names do not imply shared dimensions.
