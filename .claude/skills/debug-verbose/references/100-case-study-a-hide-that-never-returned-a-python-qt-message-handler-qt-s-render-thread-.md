## Case study: a `hide()` that never returned — a Python Qt message handler, Qt's render thread and the GIL (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: found by the second independent review, not by the suite. The engine host had a
"watch" for a shown view's errors: a recorder installed with `qInstallMessageHandler` for the
host's lifetime. With it, `host.hide()` — and so `close()` — sometimes never came back; with a
debug category switched on, 5 of 5. And the self-test's watchdog, armed for exactly this kind
of hang, wrote its stack dump and **the process stayed alive**.

**Wrong theories** — the first is in the round-1 code and docs, in my words:

1. *"The recorder takes a lock and never raises, so it is safe to call from Qt's render
   thread."* Thread-safe is not the question. The question is which lock the CALLER holds.
2. *"`faulthandler.dump_traceback_later(exit=True)` needs no GIL, so the exit is certain."* The
   dump needs no GIL. The exit is `_exit`, which on Windows is `ExitProcess`.
3. *(while fixing)* "Then end the process from a native timer thread." `ExitProcess` from
   there hangs the same way; `TerminateProcess` on itself works, with an exit code that is
   not ours.
4. *(in my own fix)* "A supervising process that waits on the process and on a release
   event." It would have killed a process that had FINISHED its block (below).

**Key evidence**: the watchdog's own dump of the control that reproduces it — two threads,
and the one that is NOT in Python is the telling one:

```
Timeout (0:00:04)!
Thread 0x00001dd0 (most recent call first):
  <no Python frame>                         <- Qt's render thread: about to call the Python
                                               handler, waiting for the GIL — no frame yet
Thread 0x0000c45c (most recent call first):
  File "…/ui/view3d/quick3d/host.py", line 550 in hide     <- the GUI thread: inside
  File "…/quick3d_lifecycle_child.py", line 771 in deadlock   QWindow.hide(), holding the GIL,
  …                                                           waiting for the render thread
```

and one line of Qt's own log, read from stderr (`QT_FORCE_STDERR_LOGGING=1`,
`QT_LOGGING_RULES=qt.scenegraph.general.debug=true`): `threaded render loop` — on Direct3D 11
(GPU and WARP) and on xcb + OpenGL. For theory 2: the process list, a minute after the dump.
For theory 4: a child whose block is `pass`, sleeping six seconds after it — exit code 1.

**Root cause**: Qt Quick renders a shown window on its own thread. Qt's message handler is
process-wide; PyQt calls a Python handler under the GIL on whichever thread emits. The GUI
thread holds the GIL while it is inside a Python-called Qt function; `hide()` waits there for
the render thread; the render thread emits a message and waits for the GIL. Then: `_exit` =
`ExitProcess` runs DLL detach code that waits for those threads. And the supervisor: a block
that ends before the supervising process has started signals and DESTROYS the release event;
the late supervisor found no event, waited on the process alone, and terminated it at the
deadline.

**Fix**: no message handler beside a shown window, ever — the watch is gone; a shown host
reports what Qt delivers on the GUI thread (`Quick3DHost.health()`: the QML engine's
`warnings`, the window's `sceneGraphError`, a frame count, the latter two connected queued).
A recorder only around rendering on the calling thread, and it counts messages that arrive
elsewhere. The watchdog got a second line of defence — another process that calls
`TerminateProcess(handle, 1)` — for which a missing release event means "released", and which
identifies its process by pid and creation time. Pinned by controls that must fail the old
way: `test_a_python_message_handler_beside_a_shown_window_deadlocks`,
`test_the_supervised_watchdog_ends_the_deadlock`,
`test_the_supervisor_leaves_a_process_alone_whose_block_finished_first`.

**Lesson**: **the GIL is a lock, and a callback from a foreign thread acquires it** — before
handing Python to another thread's callback, ask what the thread that holds the GIL may be
waiting for. And a watchdog is only as good as its exit: test it against the hang it is for,
not against `time.sleep`. And every "wait for A or B" needs an answer for "B is already
gone".

