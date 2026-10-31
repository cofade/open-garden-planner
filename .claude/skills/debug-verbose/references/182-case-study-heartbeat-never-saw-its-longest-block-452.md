# Case study: a heartbeat that never saw its longest block (#452)

**Symptom.** After the whole-plan read was sliced into 4 ms steps, the measurement
script reported a maximum GUI heartbeat gap of 5.65 ms on a plan that took 2.37 s to
prepare ? while a profiler showed one `apply` of 2,127 ms. Both numbers came from the
same run.

**Wrong theories.** First: "the timer is not precise enough" (it was a
`Qt.TimerType.PreciseTimer` at 1 ms). Second: "the apply is not on the GUI thread" (it
was ? `SceneSync.apply` is called from `_finish_records`). Third: "the read is faster
than I think" (the wall clock said otherwise).

**Key evidence.** The gap list was built as
`[b - a for a, b in zip(beats, beats[1:])]`. A 2.1 s block that happens AFTER the last
timer tick produces no pair at all: the longest block of the run is outside the
distribution. The distribution stopped exactly where the interesting work started, and
its 69 ticks over 2.37 s (35 ms apart on average) were themselves impossible to
reconcile with a 5.65 ms maximum ? which is what gave the bug away: the two summaries
described different intervals.

**Root cause.** The measurement, not the product. Two independent defects: (1) the
tail after the last tick was never measured; (2) the script drove the pipeline with
`QApplication.processEvents()`, which can drain a chain of posted events inside one
call, so the slices never yielded to a timer.

**Fix.** Append the tail (`end - last_beat`) to the gaps, and run a real `QEventLoop`.
With the tail counted, the first honest reading was max 2.1 s ? and that is what
justified the geometry lane: with the builders on a worker, the same run reads
p95 1.7 ms, max 8 ms.

**Lesson.** A percentile over samples that stop before the work ends is a percentile
of the wrong interval. When a duration summary disagrees with the total wall time, the
total is right and the summary is missing an interval ? find which one before tuning
anything. (Pitfall: PF-E3D-11.)
