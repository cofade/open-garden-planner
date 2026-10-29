## Case study: a healthy block was terminated four seconds in — and another block's log said why (Phase 17 L1.2, fixed 2026-10-11)

**Symptom** (the review's measurement, never seen in a test): two supervised watchdog blocks in
one process. Block A, 1 s budget, an empty body. Then block B, 60 s budget, healthy. The process
was terminated 4.1 s into B — and the line that said why, "block A was still alive …", stood in
A's log.

**Wrong theory**: *"A missing release event means the block is over — so a supervisor that
comes up late can never act."* That was the fix for the trap before (a block that finishes
before its supervisor is up). True, and not enough: A's supervisor did not find a MISSING
event. It found B's.

**Key evidence**: the sequence against the previous head — the process ends with exit code 1
after 4.7 s, and this is block A's log:

```
    0.005s [watchdog] armed=True seconds=1.0 what=block A supervisor=process 78652, ends this one 4 s from now …
          [supervisor] fired=True what=block A reason=block A was still alive 4 s after its watchdog was armed — … terminated from outside, exit code 1
```

and after the fix — two supervising processes, each released by its own block, both gone with
exit code 0:

```
    0.009s [watchdog] armed=True seconds=1.0 what=block A supervisor=process 66160, ends this one 4 s from now …
    0.159s [watchdog] released=True what=block A supervisor_exit=0
    0.169s [watchdog] armed=True seconds=60.0 what=block B supervisor=process 80200, ends this one 63 s from now …
   20.189s [watchdog] released=True what=block B supervisor_exit=0
```

and the pin for it failing (the process ends with exit code 1 instead of 0) as soon as the
nonce is taken out of the event's name again.

**Root cause**: the event was named after the PROCESS — pid and creation time — which the next
block of the same process has too. "An event that exists is mine" was never true.

**Fix**: a random nonce per block in the event's name, handed to the supervising process on its
command line; one armed watchdog per process at a time (a second raises); and a supervisor that
checks whom it works for before it opens anything — validated arguments, its target must be its
own parent process, in the frozen build running the same image. And the gate's own blind spot:
a supervisor that could not be started used to be logged as `supervisor=none` while the
self-test passed; on Windows the self-test now FAILS without one.

**Lesson**: **something that may kill names its target by what nobody else can have** — a random
name it was handed — never by what the next user will have too. And **a safety net is a
subsystem**: if nothing checks that it started, the day it cannot start looks like every other
day until it is needed.

