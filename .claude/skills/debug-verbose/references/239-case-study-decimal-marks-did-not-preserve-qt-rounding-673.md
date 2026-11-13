## Case study: decimal marks did not preserve Qt rounding (#673, fixed 2026-11-13)

**Symptom**: metric values changed at rounding ties: 45.25 cm read `45.2 cm`
instead of `45.3 cm`; 112.5 cm read `1.12 m` instead of `1.13 m`.

**Wrong theory**: Python's fixed formatting followed by a decimal-mark replacement
would preserve the current Qt display exactly.

**Evidence**: the senior's direct Qt probe and failing characterizations in
`tests/unit/test_measurement_display.py` pinned both length and area ties.

**Root cause**: `QLocale.toString` and Python's fixed formatter have different
rounding policies. Locale is more than the decimal separator.

**Fix**: the pure formatters accept explicit numeric-format callbacks; the UI adapter
supplies the existing Qt helpers. The pure module still imports only the standard
library. Keep Python's whole-number rounding where the shopping summary used it.

**Lesson**: characterize tie values before moving a formatting seam. The relevant
pins are `test_metric_length_keeps_qt_rounding`, `test_metric_area_keeps_qt_rounding`
and `test_shopping_plant_summary_keeps_its_whole_number_rounding` in
`tests/unit/test_measurement_display.py`.
