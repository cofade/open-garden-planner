## Case study: offline search inherited another test's custom apple

**Symptom.** Linux CI expected one offline apple result and got two, while the
local full suite and an independent coverage run passed. **Evidence.** A temporary
tagged search wrapper with stack tracing on unchanged master returned bundled
Malus domestica plus a distinct-ID custom apple and reproduced the same assertion.
**Wrong theory.** The line appearance code did not change catalog search; the
baseline reproduction rules it out. **Cause/fix.** Data directories are isolated
per process, not per test. The existing test relied on an empty process-wide custom
library. A module-local empty-library stub preserves real bundled filtering and
all exact assertions. All five cases pass with the global library deliberately
primed. The particular earlier CI writer remains unconfirmed. **Lesson.** Isolate
the inputs a scenario assumes; never relax the result count or reset a production
singleton to hide test contamination. Temporary tracing remains outside source.

