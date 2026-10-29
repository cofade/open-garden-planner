## Case study: cancel and queued API export abandonment (#315)

**Symptom.** Cancel could still write an export if readiness finished in the same
GUI event turn. A timed-out first API hop could later pause animation forever;
a timed-out render hop could later write a file after reporting failure.

**Wrong theories.** A completed readiness Future does not mean the user accepted
the dialog. The generic bridge timeout does not retract queued Qt delivery.

**Evidence.** The real-dialog probe logged `[F4-CANCEL] ready=True canceled=True`
but still ran the action. Real-bridge tests deliberately withheld Qt event delivery:
the old begin path retained one lease, and the old render path created the file.
All three regressions failed before the fix and pass afterward.

**Root cause.** Readiness completion masked cancellation. Stateful lease acquisition
preceded cleanup ownership, while queued callables outlived their callers.

**Fix.** Check dialog cancellation independently. A locked export operation owns its
request, abandonment and render admission. Late acquisition/render calls refuse;
a queued cleanup signal releases an acquired lease exactly once on Qt. If rendering
already began, return its actual outcome instead of a queue-timeout fiction.

**Lesson.** Future readiness, user consent and queued-call lifetime are independent
states. Exercise real queued delivery after timeout, not only mocked bridge returns.

