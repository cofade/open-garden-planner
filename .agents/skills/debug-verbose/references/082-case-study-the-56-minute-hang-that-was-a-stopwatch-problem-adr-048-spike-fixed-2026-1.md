## Case study: the 56-minute "hang" that was a stopwatch problem (ADR-048 spike, fixed 2026-10-04)

**Symptom**: the temporary Windows workflow built the frozen exe, passed `--selftest`, then ran
the spike for 56 minutes until the job limit killed it — no output, no metrics, 7 PNGs in the
uploaded artifact (which could not be downloaded from the analysis container anyway).

**Wrong theories**. (1) A deadlock in the threaded render loop. (2) The window never exposed on
a headless runner, so no frame ever arrived. Neither could be tested: there was no evidence at
all, because a GUI-subsystem exe has no stdout (`print` is a no-op — the #291 precedent) and
`Start-Process -Wait` has no timeout.

**Key evidence**: after the spike learned to write a flushed, timestamped `spike.log`, rewrite
`metrics.json` after every phase and arm `faulthandler.dump_traceback_later` (verified first by
forcing a 12 s watchdog, which named the exact `wait_frames` call), the next run said:

```
 12.61s [wait] label=first_frame want=2 got=3 ms=6247.4 timeout=False exposed=True
 26.39s [wait] label=golden_hour_low want=6 got=6 ms=6344.1 timeout=False exposed=True
 97.03s [grab] label=golden_hour_low ms=69156.5 px=960x540
```

Frames arrived about once a second; one `grabWindow()` of the sky-lit scene took ~69–100 s.
Later grabs of the same sky took 20–500 ms; every *new* sky light probe cost 40–85 s again.

**Root cause**: not a hang — software rendering (WARP) of a freshly prefiltered sky light probe,
paid in the first frames or grab after each sun change, times the many shots of run v1.

**Fix**: headless evidence tooling writes its own log, per-phase metrics and a watchdog; the CI
driver bounds the run with a hard timeout and prints the evidence into the job log; every grab
is timed on its own.

**Lesson**: **without timestamps, "slow" and "hung" are indistinguishable** — instrument
before theorising, and give any process that must run headless its own evidence channel.

