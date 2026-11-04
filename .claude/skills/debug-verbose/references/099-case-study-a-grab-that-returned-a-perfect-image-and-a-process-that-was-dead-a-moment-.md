## Case study: a grab that returned a perfect image, and a process that was dead a moment later (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: found by an independent reviewer, not by the suite (the render tier was green):
`host.show(); host.grab()` returned a correct frame, and the process ended a moment later with
exit code 3, `0xC0000005` or `0xC0000374` — in whatever ran next. 5 of 5. No Python exception
anywhere, so no `pytest.raises` could ever have seen it.

**Wrong theories** — all mine, and three of them were written into the code or the docs:

1. *"Visible" is the condition for a frame.* `grab()` guarded on `isVisible()`. Between
   `show()` and the first expose a window is visible and has no scene graph.
2. *A never-shown host that took its one frame can be shown afterwards.* The error message for
   the second hidden grab recommended exactly that. It is the second killing order.
3. *The L0 run's "access violation in `grab()`" belongs to the sleeping-display family.*
   Stated in the risk log without evidence.
4. *(While building the positive control)* "the two orders no longer kill" — the control
   survived 6 of 6.

**Key evidence**: Qt's own predicates, printed after every step, ONE CALL ORDER PER CHILD
PROCESS (a death is then an exit code instead of the end of the test run):

```
                         visible exposed scene-graph
new                         F       F       F
show()                      T       F       F      <- grab here: good image, dead process
one processEvents()         T       T       T
hide()                      F       T       T      <- still "exposed" until the loop ran
hide() + events             F       F       T
minimised                   T       F       T
```

For theory 4: the control returned from its function, its host went out of scope, and Python
destroyed the `QQuickView` BEFORE the event loop ran again. With the host kept alive across the
next second of event loop, the same script died 3 of 3 on the GPU and 3 of 3 on WARP.

**Root cause**: `grabWindow()` on a window that has no scene graph renders one throwaway frame
and tears the scene graph down again. For a window that is never shown, that is the one
offscreen frame it has. For a window that is shown — or is shown afterwards — the window's own
first expose then meets what the grab tore down. The condition is
`isSceneGraphInitialized()`; `isVisible()` is neither necessary nor sufficient.

**Fix**: `Quick3DHost` is a state machine over Qt's predicates (new / starting / live / hidden
/ spent / closed); every call answers for the state or raises `HostStateError`; `wait_ready()`
pumps to the first expose and reports. The tests run one call order per child process and take
"the last line is `END`" as survival; two controls do the forbidden thing on the raw view and
must die (`tests/integration/test_quick3d_lifecycle.py`). *This fix was itself incomplete —
three predicates were too few, and the tests judged the host by its own word: the case study
"a state machine that was right on Windows" below.*

**Lesson**: **when the failure is a dead process, the evidence channel must be another
process** — and a control must keep alive the thing whose death it demonstrates. And print the
engine's own predicates before choosing one by its name.

