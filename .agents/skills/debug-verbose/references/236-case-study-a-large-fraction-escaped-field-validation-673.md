## Case study: a large fraction escaped a numeric field's refusal path (#673, fixed 2026-11-12)

**Symptom**: a 400-digit numerator followed by `/1` raised `OverflowError` from
`_amount`, rather than the parser's promised `ValueError`. The field catches
`ValueError` to refuse invalid input, so this exception could escape a Qt virtual.

**Wrong theories**: none adopted; the adversarial regression failed directly at
Python's integer-to-float division, before the existing finite-result check.

**Key evidence**: `test_overflowing_fraction_is_a_parse_error` produced
`OverflowError: integer division result too large for a float` at `_amount` for
both length and volume. The normal decimal overflow already returned a non-finite
float and reached the existing refusal, whereas integer division raised first.

**Fix**: normalize that arithmetic overflow to `ValueError` in the amount parser.
Pinned by `tests/unit/test_units.py::test_overflowing_fraction_is_a_parse_error`.

**Lesson**: a finite-result check does not catch an operation that raises before
producing its result. Exercise fractions as well as decimal spellings.
