## Case study: finite operands overflow after Qt geometry composition (#453)

**Symptom.** Independent review loaded finite rectangles/groups and an embedded
image whose computed scene bounds contained infinity. Opaque metadata value="NaN"
also failed even though it was ordinary text.
**Wrong theories.** Raw finite values and individually finite extents were not
sufficient evidence of finite transformed/grouped geometry.
**Evidence.** Five regressions failed first: translated group bounds, aggregate
group bounds, a 45-degree rectangle, a decoded 4x4 image scaled by 1e308, and opaque
metadata. The four real application tests failed DID NOT RAISE ValueError while
the metadata test raised PlanValidationError on text.
**Root cause.** Raw validation omitted derived Qt geometry and propagated numeric-
string semantics into arbitrary nested metadata.
**Fix.** Validate Qt-computed local/mapped bounds and transform coefficients across
the detached graph before active-scene mutation and across live items before saves.
Check decoded image dimensions before calibration; propagate PlanValidationError
instead of skipping an item or replacing it with a placeholder. Scope numeric-
string checks to geometry containers while rejecting actual non-finite numbers
everywhere. The focused preservation/image/atomicity run passed 63 tests.
**Lesson.** Finite operands need a checked composition boundary. Let Qt compute
its own transforms, then validate the detached result before publishing it.

