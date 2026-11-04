## Case study: Coverage became the delivery bottleneck (#601)

**Symptom.** The required Coverage job took 16–17 minutes as the suite grew to
18,748 cases, including 116 serialized perf cases.
**Wrong theories.** Dropping the CLI branch flag would disable branch tracing
(TOML independently enabled it); most host wait tests were mocks (30 of 47
actually depended on real time); CLI startup explained the sweep hotspot (the
wide sweep's computation dominated).
**Evidence.** A tagged probe recorded `[601-GC] 52` full collections, with the
unexpected repeated caller's `traceback.format_stack()` pointing into the fifty
receiver rounds. cProfile recorded 1,069 parses for 528 test modules. Two sweep
consumers cost 37.47 s locally. Collection showed 27 deterministic cases inherited
a class perf marker. Controlled runner measurements live in the #601 audit report.
**Root cause/fix.** Repeated suite-wide work and unnecessary serialization compounded
the larger traced suite. Reuse AST indices, apply invariant/prose assertions to one
CLI sweep result, assert immediate acyclic receiver cleanup, and retain one cyclic-GC
case. Mark methods individually. Measure two stable test-ID coverage partitions and
the serial perf set concurrently, then require all three inputs under the protected
Coverage check. Keep branch data and the uninstrumented Test budgets.
**Lesson.** Measure the effective configuration and each expensive operation before
claiming a saving. A shorter required check must still fail on every missing or failed
measurement. The real xdist/coverage fixture needs perf-only code, or a full combined
report does not prove the perf input mattered. No diagnostic prints remain.


