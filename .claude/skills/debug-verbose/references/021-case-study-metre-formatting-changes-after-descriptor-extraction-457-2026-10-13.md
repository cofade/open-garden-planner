## Case study: metre formatting changes after descriptor extraction (#457, 2026-10-13)

**Symptom.** Review found 17.5 cm displaying 0.18 m after extraction, previously
0.17 m. Six formatting-boundary regressions failed before correction.
**Wrong theory.** Algebraically equivalent multiply/divide operations need not
produce identical binary floats. Translation and numeric precision were unchanged.
**Evidence.** `[A5-ROUND] 17.5 division 0.17 multiplication 0.18`;
`[A5-ROUND] 20.5 division 0.20 multiplication 0.21`.
**Root cause.** Target multiplication by 0.01 replaced the existing division by
100.0, changing the last binary bit at display rounding ties.
**Fix.** The descriptor stores a divisor (100.0 for metres, 1.0 for degrees) and
preserves division. Pinned by `test_constraint_descriptors.py` distance/edge/tangent
boundary tests; all temporary diagnostics removed.
**Lesson.** Presentation equivalence includes the arithmetic operation at rounding
boundaries, not only the number of formatted decimal places.

