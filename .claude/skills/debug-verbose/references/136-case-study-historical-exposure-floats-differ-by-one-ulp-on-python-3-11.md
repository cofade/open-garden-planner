## Case study: historical exposure floats differ by one ULP on Python 3.11

**Symptom/evidence.** Both clean master and the line branch failed the same six
day-ramp comparisons against frozen JSON on Windows Python 3.11.9. Every difference
was exactly one binary64 ULP; the other 256 lighting cases passed.
**Wrong theory.** The line-style changes did not alter lighting; master reproduced
the identical values. **Fix.** Permit one ULP for nonlinear exposure only. Keep
colors, brightness, fog and linear probe exposure exact. All 262 lighting tests
pass; production code and reference JSON are unchanged. **Lesson.** Use the measured
numeric representation's precision for cross-platform frozen float references,
not a broad default relative tolerance.

