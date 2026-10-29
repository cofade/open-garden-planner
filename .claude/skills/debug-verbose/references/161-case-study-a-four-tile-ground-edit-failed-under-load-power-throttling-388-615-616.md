## Case study: a four-tile ground edit "failed under load" — power throttling (#388, #615, #616)

**Symptom.** G3's new four-tile case (a terrace where four bench_large tiles meet) read 13–15 ms
in two passes on the dev box against its 10 ms bound. On CI, one run passed it uninstrumented
while the same run's coverage job read 13.29 ms; the next run's uninstrumented Test job read
12.15 ms.
**Wrong theories.** (1) "Machine load": another user's llama-server was busy, so a 13.5 ms
reading was dismissed as noise, and the stand-in was moved off the corner. (2) "Coverage's
tracer": the clock check was skipped under a tracer for that one case, and the next CI run
failed uninstrumented. The tracer is a real cost (about 1.4×) and pushed that one coverage
reading over, but the corner also overruns without it. (3) "Master also needs two passes":
one master run at 15.0 ms in two passes was read as a property of the code.
**Evidence.** CI's own logs said "passes per move: median 1": one pass that can overrun the
budget by its last tile, as `BAKE_BUDGET_S`'s contract allows. Locally, the per-move cost
jumped from about 8 ms to about 15 ms partway through a run, and passes went from 1 to 2.
With the process opted out of Windows power throttling (`SetProcessInformation`,
`ProcessPowerThrottling`), the corner read 8.4 ms in one pass, while a game kept the
machine busy. `scripts/measure_ground_edit.py` (which opts out itself) then compared the
trees: master's four-tile edit costs the same within about 0.3 ms (ADR-065).
**Root cause/fix.** The product behaves as designed. The four-tile pass can overrun 10 ms on
CI hardware; its cost is master's (#615, owner decision). The dev
box's readings, about 1.8× too high, were EcoQoS throttling of the test process (#616). G3
states each case's bound as literals and prints its readings on every serial run.
**Lesson.** Before calling a local timing "load" or "the tracer", read the measuring tool's
own counters (passes per move) and compare a run with throttling switched off. A reading
that jumps once and stays high is the OS changing the process's speed, not the code. Never
write a dismissal ("loaded machine", "on master too") into an ADR without the run that
proves it, and commit that run as a script.
Pins: `tests/integration/test_scene3d_ground_bake.py::TestOneSmallEdit::test_a_small_move_repaints_few_tiles_within_its_bound`;
`scripts/measure_ground_edit.py`; §8.10.4 "A local perf reading on Windows may be a throttled
one".

