## Case study: a state machine that was right on Windows, and a judge that asked the suspect (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: two findings of the same review. (1) The Linux CI job was red: a call order the
lifecycle matrix PINNED AS SAFE — `show(); hide(); grab()` — segfaulted one event-loop pass
after a correct grab. (2) In a splitter pane dragged shut the host said "live" and handed out
a blank frame, a bogus pick and a projection of (0, 0) — and the matrix was green.

**Wrong theories**:

1. *"No scene graph and not visible means never shown."* Measured on Direct3D 11, where that
   order survives. On xcb the window has a platform window by then, and that is what counts.
2. *"Scene graph, visible and exposed means a frame can be had."* A collapsed pane is all
   three and 0 px wide.
3. *"The matrix checks every answer."* It checked every answer against the state THE HOST
   reported. A host that reports the wrong state passes.

**Key evidence**: Qt's facts printed per step — this time with the geometry, and with the
platform-window event:

```
                              surface visible exposed scene-graph  window   root item
show(); hide() (no event)        1       F       F       F        320x240   320x240   <- "new"? xcb says no
pane collapsed                   1       T       T       T          0x500   447x500   <- visible AND exposed
pane reopened (no event)         1       T       T       T        447x500     0x500   <- the scene lags one pass
1 px wide                        1       T       T       T          1x500     1x500   <- draws no 3D at all
```

and the same matrix run in a container with the CI job's stack: the four killing orders die 5
of 5 on xcb.

**Root cause**: three predicates named after what they sound like, chosen on one platform; and
a test that derived its expectation from the output of the code under test.

**Fix**: the state is a pure function of nine facts (ten since the case study after next;
`quick3d/lifecycle.py`): "new" = Qt never
created a platform window (the `PlatformSurface` event; PyQt6 does not bind
`QWindow.handle()`); "live" also needs an area of 2 × 2 px and a root item that has the
window's size. The judge has a table of what a TRUTHFUL host must answer per step and checks
the pixels; a control hands it the raw view's blank frames and requires it to reject them.

**Lesson**: **a measurement belongs to the platform it was made on** — "harmless, also
measured" needs the platform's name next to it, and the other platform's control. And **an
oracle must not be computed from the answer it judges**: if the expected value comes out of
the code under test, the test can only fail when the code disagrees with itself.

