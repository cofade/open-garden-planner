## Case study: frozen lighting replay differed by one binary64 ULP on Windows (#315 merge)

**Symptom.** Six quarter-degree exposure samples failed exact equality against the
frozen L0 JSON while the production lighting source was byte-identical to master.

**Wrong theories.** No garden-timeline lighting change was assumed: source identity
and all 160 replay samples were measured before changing any comparison.

**Evidence.** `[F4-FLOAT] lighting-source-identical-to-master True`; six exposure
mismatches at 7.75, 13.5, 16.5, 21, 22.25 and 22.75 degrees, each exactly one ULP.
For example 1.1249297944784713 versus 1.124929794478471. Probe exposure, colours,
brightness and the remaining exposure samples matched exactly.

**Root cause.** The frozen nonlinear exposure replay required identical binary64
answers across runtimes. That was stronger than this Windows replay could satisfy.

**Fix.** Permit exactly one math.ulp of the expected exposure with zero relative
tolerance. Keep every other field exact and leave production lighting untouched.
The six tests were observed failing before the comparison fix.

**Lesson.** Measure drift in representable units before choosing a numeric tolerance;
a generic relative tolerance would silently allow many more representable values.


