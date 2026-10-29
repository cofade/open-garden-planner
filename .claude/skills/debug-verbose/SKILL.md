---
name: debug-verbose
description: Evidence-based debugging via targeted verbose instrumentation. Apply at the first sign of any non-obvious bug — before theorising. Grows with each bug fixed in this project.
user_invocable: true
argument: "Optional: short description of the bug or area to instrument"
---

# debug-verbose reference guide

Read the scope/introduction and the relevant reference below **before acting**.
All rules in the references remain binding. Read method/runbook sections for
the task; load historical case studies only when the symptom matches. Search
the index by subsystem, issue or symptom. Do not infer current delivery status
from dated measurements. New lessons belong in a new reference and index row.

**At the first non-obvious bug:** load “When to apply”, “How to instrument”
and the templates below. Instrument with tagged prints and caller stacks,
reproduce, then fix from the output. Remove instrumentation before committing.
Add a case study in both libraries; preserve the historical lessons.

| Topic / symptom | Reference |
|---|---|
| Verbose Debug Instrumentation | [Read](references/000-verbose-debug-instrumentation.md) |
| When to apply (proactively, without being asked) | [Read](references/025-when-to-apply-proactively-without-being-asked.md) |
| How to instrument | [Read](references/026-how-to-instrument.md) |
| Template — event-driven method instrumentation | [Read](references/027-template-event-driven-method-instrumentation.md) |
| Template — async/deferred callback | [Read](references/028-template-async-deferred-callback.md) |
| How this skill grows | [Read](references/034-how-this-skill-grows.md) |
| Notes from the same sweep (no separate case study warranted) | [Read](references/048-notes-from-the-same-sweep-no-separate-case-study-warranted.md) |

[Search historical cases](references/case-index.md).
