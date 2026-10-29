## Case study: three callback observations became an absolute scheduling promise (PR #597)

**Symptom.** An unchanged version-sync head failed its Windows seasonal budget
at 16.8508 ms while the matching PR job passed. Five independent local WARP
processes ranged from 10.59 to 24.21 ms under the maximum-of-three statistic.
**Wrong theory.** One hosted-runner hiccup would explain it; the repeated local
crossings refuted that. A slow QML hop alone did not prove render contention,
and Windows thread_time was quantized in 15.625 ms steps at this scale.
**Evidence.** All 300 plants occupied one pose, with no explicit steady-state
boundary. Settled collocated controls read 17.49/16.33 ms; settled grid controls
13.67/14.93 ms. The controls did not identify the cause of the wall-time tails.
**Fix.** Use the house NFR median protocol: a visible grid, warm/settle outside
timing, exactly 15 interleaved wall-time observations per date and one fixed
run. Keep the worst date median at 16.0 ms; publish all samples, p95/max and
adapter. Inject 20 ms into the actual uniform hop to prove rejection. Preserve
the production workspace route and independent no-geometry/no-churn assertions.
**Lesson.** State the statistic being guaranteed. Typical callback time is not
an absolute OS deadline; do not replace wall time with CPU time or retry until
green. No runtime code changed and no temporary production instrumentation remains.

