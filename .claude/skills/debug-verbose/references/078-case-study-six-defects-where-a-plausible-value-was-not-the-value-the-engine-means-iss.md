## Case study: six defects where a plausible value was not the value the engine means (issues #332/#333, fixed 2026-10-03)

**Symptom**: No symptom, in the usual sense - this is the case for writing tests
that compare against the ENGINE rather than against an expected literal. While
building US-D3.3 (task tools) and US-D3.4 (soil tools) six defects surfaced, five
of them in code I had just written, and not one of them announced itself as a
crash. Each produced a value that looked entirely reasonable.

**Wrong theories, in order.** (1) That the soil health ratings were a mapping bug -
`health_level(record, "ca")` returned `"poor"` for a healthy bed and I assumed the
secondary scale was being read wrongly. (2) That `get_effective_record` was
returning the wrong record. (3) That the Rapitest validation was too strict, since
`n_level=5` was refused. Theories (1) and (2) each would have justified editing
working code.

**Key evidence.** (a) `SoilService.health_level` has no `else` and no error for an
unknown parameter: `if parameter == PARAM_PH ... if PARAM_K ... # OVERALL`. A
sixth call **falls off the end and returns the overall rating**. So `ca`'s
"health level" was the whole bed's health - a real number, wrong subject. (b)
`grep 'source="' services/task_generator.py` returned eight hits with the values
`calendar, propagation, succession, succession, soil, soil, frost, manual` - **six**
distinct, while my `TASK_SOURCES` tuple had seven, because I had copied
`soil_amendment` / `soil_mismatch` out of the issue text. Both soil generators
emit `source="soil"`; `task_type` is what tells them apart. (c) `grep -rn "_ppm"
src/` showed hits only in `models/soil_test.py`, `soil_test_dialog.py` and one
comparison helper - **nothing in `services/` reads the ppm fields at all**.

**Two guards were themselves the bug.** The `TASK_SOURCES` drift guard asserted
`emitted <= TASK_SOURCES`, a **subset** check, which passes on extra entries - so
it green-lit two values no generator can emit. The field failure would have been
`source="soil"` refused as unknown while `source="soil_mismatch"` silently returned
nothing. Separately, the first version of that guard was fixture-driven, and four
of seven generators need live inputs a bare `PlanState` cannot supply, so it
would have under-reported and passed vacuously. It is now AST-based and asserts it
saw at least seven `Task(...)` constructions.

**Root cause**: every one of these is a **fall-through or a copied name**. A
default branch that answers a question nobody asked; an identifier taken from prose
instead of from code; a hierarchy applied inside a function so the caller cannot
see which branch ran; and a range that looks uniform and is three different ranges.
Nothing raises, and nothing looks wrong.

**Fix**: (a) route only `RATED_PARAMETERS` through `health_level` and make
`SoilReading.health_level` optional, where `None` means "no rating exists" -
distinct from `'unknown'`, which means "not tested"; (b) read the source values
from the module by AST and assert **equality both ways**; (c) refuse ppm by name
and take kit-only parameters whose names state the scale, with per-nutrient
ranges (`k_level` is `1-4`, the kit has no K0); (d) report `record_source`
alongside the reading, since `get_effective_record` applies its hierarchy
invisibly; (e) accept `credits` as the `(kind, current, target)` triple it is -
caught on the first call by the field-for-field equality test, which is exactly
what that test is for.

**Lesson**: (1) **Write the assertion against the engine, not against a literal
from the issue** - a test written from prose inherits prose's errors, and five of
these six would have shipped green under one. (2) A fall-through default is a
silent wrong answer; make the field that cannot be computed **nullable** rather
than letting a default fill it. (3) A drift guard must assert **equality in both
directions** and must assert that it observed something - a guard that can pass
vacuously reports success forever, which is worse than no guard because it is
trusted. (4) When a model carries two representations of one value (`*_level` and
`*_ppm`), check **which one the engine actually reads** before designing input for
it; the one that is stored but unread looks like a feature and behaves like a
trap.


