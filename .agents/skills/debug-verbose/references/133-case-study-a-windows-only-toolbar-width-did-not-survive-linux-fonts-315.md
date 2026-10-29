## Case study: a Windows-only toolbar width did not survive Linux fonts (#315)

**Symptom.** CI's German combined strip wrapped into three rows while Windows
captures passed. A wider-font regression also caught a Spanish group outside its
content rectangle.

**Wrong theories.** A fixed 140-pixel narrow slider was not a portable fit proof.
No style-cache workaround was adopted before tagged size-hint measurements.

**Evidence.** The regression failed first for Verdana 9/10 German and 10 Spanish.
`[F4-PACK]` at 796 pixels showed group item hints stuck at 189/324 while their
actual layout hints had shrunk to 139/274. Unexpected-row stacks traced _reflow;
QWidgetItem's cached hints lagged the changed fixed-size child layouts.

**Root cause.** The slider width assumed one platform's font metrics, and deciding
fit immediately after changing width read stale group/item geometry constraints.

**Fix.** Use the flow's own placement calculation to count rows, compact sliders
only as needed down to 90 pixels, and activate group layouts/update geometry before
reading their hints. Actual placement and row-count planning share one algorithm.
Wider-font translated tests now pass without clipping; controls remain atomic.

**Lesson.** Plan wrapping with current geometry constraints, not guessed widths or
widget-item caches from the preceding layout pass. Test more than one font metric.

