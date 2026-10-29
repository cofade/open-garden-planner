## Case study: a product frame budget measured coverage's tracer (#601)

**Symptom.** The fresh serial coverage producer failed the 300-plant phenology
batch at 17.85 ms against 16 ms. The protected Coverage check correctly failed.
**Wrong theory.** The new test-ID partition dropped data or changed the product;
the failed test was serial and no application file changed.
**Evidence.** The temporary wrapped-call probe recorded untraced scrubs at
1.89–2.36 ms and a 2.17 ms batch. With the same branch tracer it recorded
`[601-PHENO] scrub_date True 22.69`, then the original assertion failed. The
probe captured traceback.format_stack() when installing its wrappers and retained
all results; no event-loop or source behavior was substituted.
**Root cause/fix.** This single-sample gate had no tracer allowance, unlike the
snapshot budgets. It now reuses their `budget_factor` and `traced` with CI slack
disabled: the uninstrumented Test job still enforces 16 ms, while traced runs
retain every state/date assertion and a 160 ms tracer tripwire. Controls reject
17 ms untraced and 161 ms traced. No application or renderer change.
**Lesson.** Keep an uninstrumented product budget when collecting coverage; an
instrumented call measures the tracer too. Reuse the existing tracing policy,
and pin the unchanged real threshold rather than silently loosening it on CI.

