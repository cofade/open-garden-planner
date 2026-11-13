## Case study: prefixed fields refused partial fractions (#673, fixed 2026-11-13)

**Symptom**: the owner could enter a fractional inch value in object height but
could not type the numerator after a space in the Family Garden greenhouse's
width. The width had a `W: ` caption; height had none.

**Rejected explanations**: range limits or a missing mixed-fraction grammar.
Complete-value parsing already accepted the grammar. Actual keystrokes exposed
a different validation result for the same unfinished numeric text.

**Evidence**: tagged validation prints reported raw `12 1`, numeric `12 1`,
state Intermediate, then raw `W: 12 1`, numeric `12 1`, state Invalid. The regression
observed the editor remain at `W: 12 ` after the next digit was refused.

**Root cause**: the complete parser stripped the spin box prefix, but the fallback
character check examined the whole displayed field. The colon in the caption
made every incomplete fraction or unit token invalid.

**Fix**: normalize the numeric text once and use it for complete parsing and
partial-input validation. Preserve the original returned text/cursor and numeric
grammar. Pins: `tests/ui/test_unit_spin_box.py` types fractions, feet/inches and
metric overrides one character at a time with multiple prefixes and both Return
and focus-loss acceptance; `tests/integration/test_unit_system.py` edits the actual
bundled greenhouse, checks one undo step, repeated switches and save/reopen.

**Lesson**: test intermediate typing states through Qt with real field captions.
An unprefixed widget or a complete string passed to the parser misses this seam.
