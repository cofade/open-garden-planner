## Case study: throttle regression depends on machine uptime (#542, PR #565)

**Symptom.** CI Test and Coverage failed the new no-op regression's idle assertion;
the workstation passed it.
**Wrong theory.** A fixed 1000-second stamp and 70-ms settle were assumed independent
of the host. No product scheduling change was justified by that failure.
**Evidence.** External tagged instrumentation and caller stacks showed
`[565-TRACE] _on_date_changed ... regrown_at=1000.0 date_timer=True` at controlled
monotonic 900 seconds. The same test passed with the host above 74000 seconds.
Calling the trailing slot manually retained the booked timer. Replaying the old
unconditional no-op stamp failed all three replacement clock-origin cases.
**Root cause.** The test put its timestamp in the future on a young VM. The product
correctly booked a long delay; a direct slot call does not consume a QTimer.
The original product bug was distinct: a no-op trailing check advanced the throttle
stamp even though the last snapshot already covered that date.
**Fix.** Stamp only when regrowth is owed. Replace only the controller's clock
binding, preserve real Qt waits/performance clocks, and assert that the next real
date signal books no timer and completes the expected snapshot. Stop a manually
consumed timer before firing its slot. Temporary probes stay outside production.
**Lesson.** A fixed timestamp is not a controlled clock; assert the user-triggered
path and all timers that participate in idle. See PF-TST-25.
Second review also found that Qt's real 500-ms timer could expire during the
held-burst event loop despite a fixed monotonic clock. That test now records the
requested product delay, postpones physical delivery beyond its test timeout,
and manually consumes the real timer at the controlled clock boundary.

