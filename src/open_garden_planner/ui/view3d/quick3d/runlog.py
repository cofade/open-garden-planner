"""A log that survives a hang, and a watchdog that ends one (L1.2). Engine-free.

A frozen GUI exe has no stdout and no stderr (#291 is the precedent), and a
software rasteriser can take a long time over one frame. The L0 spike's first
Windows evidence run "hung" for 56 minutes with no output; it was not hung. So
every headless render writes a line-flushed log, and may bound itself with a
watchdog that turns a real hang into a failed run with a stack trace.

TWO LINES OF DEFENCE, because the first one is not enough (ADR-048 addendum
L1.2, review round 2 — measured):

1. In the process: ``faulthandler.dump_traceback_later(exit=True)``. Its C thread
   needs no GIL, writes every thread's stack and calls ``_exit(1)``. That ends a
   plain hang, and on Linux also the deadlock below (5 of 5, exit code 1). On
   Windows it does NOT end a process whose threads are deadlocked inside Qt and
   the graphics driver: ``_exit`` is ``ExitProcess`` there, which runs every
   DLL's detach code, and that waited forever — the dump was written and the
   process stayed alive (every run, on the GPU and on WARP).
2. From outside (``supervised=True``, Windows): a second, tiny process waits on
   this one and calls ``TerminateProcess`` when it is still alive ``GRACE_S``
   after the deadline — which no state of this process can prevent (every run
   of the same deadlock: exit code 1). It writes the reason into the log first.

WHAT A SUPERVISOR MAY TOUCH (review rounds 2 and 3). It acts for ONE block of
ONE process, and it is built so that it cannot act for anything else:

- its process is identified by pid AND creation time, must be the supervisor's
  own PARENT, and in the frozen build must run the supervisor's own image;
- its block is identified by a random nonce in the name of the release event.
  The block signals that event when it ends, and keeps it until its supervisor
  has left (at most ``SUPERVISOR_EXIT_WAIT_S``). A supervisor that comes up
  late finds the event signalled and leaves: released. Because the name is per
  block, the event of a LATER block of the same process is never mistaken for
  it (it was, once: a finished block's late supervisor terminated the healthy
  block after it, 4.1 s in);
- one watchdog is armed per process at a time; a second one is refused
  (``WatchdogError``) — ``faulthandler`` has a single timer anyway;
- it says what it did in its exit code: 0 only when it held the block's event —
  it was released, the process ended while it watched, or it ended it (a wait
  that FAILS is 3, like every other failure of its own, and terminates nothing). A
  supervisor that found NOTHING to wait for (the process gone or not the one
  named, the block's event not there) leaves with ``SUPERVISOR_IDLE`` (4): it
  never supervised. It used to exit 0 like one that did its job — also when it
  left at once while its block still ran (measured: 1.5 s into a 20 s block);
- there is NO start timeout DURING the block: the block does not wait for its
  supervisor to be up (to end a hang it only has to be up before the deadline).
  The bound is at the block's END: the block waits ``SUPERVISOR_EXIT_WAIT_S``
  (15 s) for its supervisor to have come up, seen the release and left. One
  that needs longer counts as not having left. (Measured: it is up 0.1 s after
  the block began from source, 0.2 to 1.1 s in the frozen build);
- its arguments are validated before anything is opened (``supervisor_main``):
  a deadline that is not a finite number of seconds within
  ``MIN_SUPERVISED_S`` … ``MAX_SUPERVISED_S``, a malformed pid or nonce, a log
  path that is not an existing regular file — each ends it with exit code 2 and
  one line, never a traceback and never a terminate. It appends to the log the
  block passed, and creates no file.

This file is also that second process: ``python -I runlog.py <arguments>`` from
source, ``<exe> --selftest-supervisor <arguments>`` in the frozen build (``main``
dispatches to ``supervisor_main``). The flag is INTERNAL: nothing but
``start_supervisor`` is meant to pass it. The file imports nothing but the
standard library.
"""

from __future__ import annotations

import contextlib
import faulthandler
import math
import os
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Final

#: The frozen exe's command-line flag for the supervising process (``main.main``). Internal.
SUPERVISOR_FLAG: Final = "--selftest-supervisor"
#: How long after the in-process deadline the supervisor waits before it ends the
#: process: time for the stack dump to be written.
GRACE_S: Final = 10.0
#: The deadlines a supervisor accepts, seconds from its start: at least long enough for a
#: stack dump, at most a day. Zero would terminate at once, a negative number would wait
#: for 49 days, ``nan`` and ``inf`` are not deadlines.
MIN_SUPERVISED_S: Final = 0.5
MAX_SUPERVISED_S: Final = 86_400.0
#: How long a released supervisor may take to leave — which includes coming up, if the
#: block was over before it had: there is no other start timeout (module docstring).
SUPERVISOR_EXIT_WAIT_S: Final = 15.0
#: The supervising process's exit codes.
SUPERVISOR_DONE: Final = 0      # it held the block's event: released, the process ended, or it ended it
SUPERVISOR_REFUSED: Final = 2   # its arguments were not ones it may act on; nothing was touched
SUPERVISOR_FAILED: Final = 3    # it failed itself; nothing was terminated
SUPERVISOR_IDLE: Final = 4      # it found nothing to wait for and left: it never supervised
#: What an exit code other than ``SUPERVISOR_DONE`` means — in words, for the log and
#: for a caller that must not pass without a supervisor (``Armed.gap``).
_EXIT_MEANS: Final = {
    None: f"had not left {SUPERVISOR_EXIT_WAIT_S:g} s after its release",
    SUPERVISOR_REFUSED: "refused: this block was not one it may act for (exit code 2)",
    SUPERVISOR_FAILED: "failed itself (exit code 3)",
    SUPERVISOR_IDLE: ("left without having supervised: it found no block to wait for — the "
                      "process or the block's release event was not the one it was told "
                      "(exit code 4)"),
}


def _exit_means(code: int | None) -> str:
    return _EXIT_MEANS.get(code, f"ended with exit code {code}")
#: What stands in the log where no supervisor exists — and what bounds a deadlock there.
NOT_NEEDED_HERE: Final = ("none (not on this platform: _exit ends the process — measured on Linux; "
                          "beyond that the caller's own time limit is the bound, in CI the step's)")

_NONCE: Final = re.compile(r"[0-9a-f]{32}")
_ARGUMENT_COUNT: Final = 6


class WatchdogError(RuntimeError):
    """A watchdog was asked for while another one is armed in this process."""


class RenderLog:
    """Timestamped, line-flushed log — to ``path`` and to stdout when there is one.

    ``log(phase, key=value, …)``. With ``path=None`` it only mirrors to stdout
    (and is silent in a windowed frozen exe, which has none). ``mirror=False``
    keeps stdout for the caller's own summary.
    """

    def __init__(self, path: Path | None = None, *, mirror: bool = True) -> None:
        self.path = path
        self._mirror = mirror
        self._started = time.perf_counter()
        self._file: IO[str] | None = None
        self._crash_file: IO[str] | None = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")  # a fresh log, then append-only:
            self._file = path.open("a", encoding="utf-8", buffering=1)  # faulthandler appends too

    def __call__(self, phase: str, **fields: Any) -> None:
        detail = " ".join(f"{key}={value}" for key, value in fields.items())
        line = f"{time.perf_counter() - self._started:9.3f}s [{phase}] {detail}".rstrip()
        if self._file is not None and not self._file.closed:
            self._file.write(line + "\n")
            self._file.flush()
        if self._mirror and sys.stdout is not None:
            with contextlib.suppress(Exception):  # a closed or broken stdout must not fail a render
                print(line, flush=True)

    def crash_file(self) -> IO[str] | None:
        """Where ``faulthandler`` writes: its OWN handle on the log (never closed, so a
        crash in teardown still leaves its stack), else stderr, else None."""
        if self.path is not None:
            if self._crash_file is None:
                self._crash_file = self.path.open("a", encoding="utf-8")
            return self._crash_file
        return sys.stderr

    def close(self) -> None:
        if self._file is not None:
            self._file.close()


def _has_descriptor(stream: IO[str]) -> bool:
    """False for a stream that is not a real file (a captured or replaced stderr)."""
    try:
        stream.fileno()
    except Exception:  # noqa: BLE001 - io.UnsupportedOperation, ValueError (closed), AttributeError
        return False
    return True


@dataclass(slots=True)
class Armed:
    """What ``with watchdog(...) as armed`` hands out: whether the block is supervised
    from outside, and — once the block is over — how the supervising process ended."""

    seconds: float
    what: str
    #: The supervising process, or None (not asked for, not on this platform, or it
    #: could not be started — ``unsupervised_because`` says which).
    supervisor: Supervisor | None = None
    unsupervised_because: str = "not asked for"
    #: The supervising process's exit code after the block (``SUPERVISOR_DONE`` when it
    #: did its job); None while the block runs, when there was none, or when it had not
    #: left within ``SUPERVISOR_EXIT_WAIT_S`` — ``released`` tells the first from the last.
    supervisor_exit: int | None = None
    #: True once the block is over and its supervising process was told to go.
    released: bool = False

    @property
    def supervised(self) -> bool:
        """While the block runs: a supervising process was started. Once it is over: that
        process had held the block's event AND left — exactly when ``gap`` is "". (The
        two disagreed until review round 5: a supervisor that had not left after 15 s
        still read as "supervised".)"""
        return self.supervisor is not None and self.gap == ""

    @property
    def gap(self) -> str:
        """"" when nothing is known to be missing: the block still runs under a supervising
        process, or it was supervised from outside to its end. Else, in words, why not —
        for a caller that must not pass without a supervisor (the self-test): no process
        started, or it refused, failed, never supervised, or did not leave."""
        if self.supervisor is None:
            return self.unsupervised_because
        if not self.released or self.supervisor_exit == SUPERVISOR_DONE:
            return ""
        return f"its supervising process {_exit_means(self.supervisor_exit)}"


_ARMED: list[Armed] = []  # the ONE armed watchdog of this process, if any


@contextlib.contextmanager
def watchdog(seconds: float, log: RenderLog, what: str = "the run", *,
             supervised: bool = False) -> Iterator[Armed]:
    """Bound the block: after ``seconds`` every thread's stack is dumped into the
    log and the PROCESS exits with code 1 (``faulthandler``). A hang becomes a
    failed run with a stack, not a job that never ends.

    The reason is written to the log in words: when the watchdog is armed (what a
    ``Timeout`` below that line means), and — shortly before the end, from a
    helper thread — that it is about to fire. The helper needs the interpreter
    lock; a hang that holds it silences the helper, never the dump.

    ``supervised=True`` adds the second line of defence (module docstring): a
    process of its own that ends this one from outside when it is still alive
    ``GRACE_S`` after the deadline, and says so in the log. Windows only — that
    is where ``faulthandler``'s exit was measured to fail (on Linux it was
    measured to work); elsewhere the log says that there is none and what
    bounds a deadlock instead. The ``Armed`` the block is handed says whether a
    supervisor was started; after the block, how it ended.

    With neither a log file nor a stderr (a windowed exe whose log could not be
    opened) the stacks have nowhere to go — the process is ended all the same.

    For self-tests and scripts that own their process — never inside the running
    app: the exit is not negotiable. ONE watchdog per process at a time: a second
    one while this one is armed raises ``WatchdogError`` (``faulthandler`` has a
    single timer, and a supervisor acts for exactly one block). ``seconds <= 0``
    switches it off.
    """
    if seconds <= 0:
        log("watchdog", armed=False, what=what, reason="disabled")
        yield Armed(seconds, what)
        return
    if _ARMED:
        raise WatchdogError(
            f"a watchdog is already armed in this process ({_ARMED[0].what!r}): one at a time — "
            f"{what!r} was not armed")
    armed = Armed(seconds, what)

    def announce() -> None:
        with contextlib.suppress(Exception):  # a closed log must not turn into a second failure
            log("watchdog", fired=True, what=what,
                reason=f"{what} did not finish within {seconds:g} s — it hangs in the call at "
                       "the top of the main thread's stack below; ending the process, exit code 1")

    helper = threading.Timer(max(seconds - 1.0, seconds * 0.8), announce)
    helper.daemon = True
    nowhere = None
    # EVERYTHING that arms is inside the try: if any step of it raises — the log is
    # closed, the timer cannot be set — the finally disarms what was armed so far. (It
    # used to start the supervisor and mark the process armed BEFORE the try: a failure
    # after that left every later watchdog refused, and a live supervisor that ended the
    # process at the deadline.)
    try:
        _ARMED.append(armed)
        target = log.crash_file()
        if target is None or not _has_descriptor(target):  # faulthandler writes to a descriptor
            nowhere = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - closed in the finally
            target = nowhere
        if supervised:
            if sys.platform != "win32":
                armed.unsupervised_because = NOT_NEEDED_HERE
            else:
                try:
                    armed.supervisor = start_supervisor(seconds + GRACE_S, log.path, what)
                except Exception as error:  # noqa: BLE001 - no supervisor is a degraded run, not a crash
                    armed.unsupervised_because = (f"none (it could not be started: "
                                                  f"{type(error).__name__}: {error})")
                else:
                    if armed.supervisor is None:
                        armed.unsupervised_because = "none (it could not be started)"
        log("watchdog", armed=True, seconds=seconds, what=what,
            supervisor=(armed.supervisor.describe() if armed.supervisor is not None
                        else ("none" if not supervised else armed.unsupervised_because)),
            note=f"if {what} is not done by then: 'Timeout' and every thread's stack follow "
                 "here, and the process exits with code 1"
                 + (" (no log file and no stderr: the stacks are lost, the exit is not)"
                    if nowhere is not None else ""))
        faulthandler.dump_traceback_later(seconds, exit=True, file=target)
        helper.start()
        yield armed
    finally:
        faulthandler.cancel_dump_traceback_later()
        helper.cancel()
        if armed in _ARMED:
            _ARMED.remove(armed)
        if armed.supervisor is not None:
            armed.supervisor.release()
            armed.released = True
            armed.supervisor_exit = armed.supervisor.wait(SUPERVISOR_EXIT_WAIT_S)
            with contextlib.suppress(Exception):
                if armed.supervisor_exit == SUPERVISOR_DONE:
                    log("watchdog", released=True, what=what, supervisor_exit=armed.supervisor_exit)
                else:
                    log("watchdog", released=True, what=what, supervisor_exit=armed.supervisor_exit,
                        note=f"the supervising process {_exit_means(armed.supervisor_exit)}")
        if nowhere is not None:
            nowhere.close()


# ── the supervising process (Windows) ────────────────────────────────────────


class Supervisor:
    """The handle on a started supervising process (``start_supervisor``)."""

    def __init__(self, process: subprocess.Popen[bytes], event: int, seconds: float) -> None:
        self.process = process
        self._event = event
        self._seconds = seconds

    def describe(self) -> str:
        return f"process {self.process.pid}, ends this one {self._seconds:g} s from now"

    def release(self) -> None:
        """The supervised block is over: tell the supervisor to go, at once. The event is
        SIGNALLED and kept — a supervisor that is still coming up must find it, signalled,
        or it could not tell "released" from "there never was such a block". ``wait()``
        destroys it."""
        _signal(self._event)

    def wait(self, timeout_s: float) -> int | None:
        """The supervising process's exit code — None when it has not left in time. The
        release event goes with this call, whatever the answer."""
        try:
            return self.process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return None
        finally:
            _close(self._event)
            self._event = 0


def self_command() -> list[str]:
    """How to start THIS code as a process of its own: the frozen exe with the flag
    ``main`` dispatches on, or — from source — this very file under the interpreter
    behind the virtual environment (never ``-m open_garden_planner``: from a git
    worktree that could start another checkout's application).

    The BASE interpreter, isolated (``-I``): a virtual environment's ``python.exe`` is
    a launcher on Windows, whose child would be the supervisor's parent instead of the
    process it must watch — and this file needs nothing but the standard library.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, SUPERVISOR_FLAG]
    base = getattr(sys, "_base_executable", None) or sys.executable
    return [base if os.path.isfile(base) else sys.executable, "-I", str(Path(__file__).resolve())]


@dataclass(frozen=True, slots=True)
class SupervisorOrder:
    """A supervisor's validated command line."""

    pid: int
    created: int
    nonce: str
    seconds: float
    log_path: str | None
    what: str


def parse_supervisor_arguments(arguments: list[str]) -> SupervisorOrder:
    """``<pid> <creation time> <nonce> <seconds> <log | -> what:<what>`` — or
    ``ValueError`` saying which part is not one a supervisor may act on. Opens nothing."""
    if len(arguments) != _ARGUMENT_COUNT:
        raise ValueError(f"{_ARGUMENT_COUNT} arguments expected, {len(arguments)} given")
    pid_text, created_text, nonce, seconds_text, log_path, what = arguments
    if not (pid_text.isascii() and pid_text.isdigit() and 0 < int(pid_text) < 2**32):
        raise ValueError("the process id is not a positive number")
    if not (created_text.isascii() and created_text.isdigit() and int(created_text) > 0):
        raise ValueError("the creation time is not a positive number")
    if _NONCE.fullmatch(nonce) is None:
        raise ValueError("the block's nonce is not 32 hexadecimal digits")
    try:
        seconds = float(seconds_text)
    except ValueError:
        raise ValueError("the deadline is not a number") from None
    if not (math.isfinite(seconds) and MIN_SUPERVISED_S <= seconds <= MAX_SUPERVISED_S):
        raise ValueError(f"the deadline is not within {MIN_SUPERVISED_S:g} to {MAX_SUPERVISED_S:g} s")
    if not what.startswith("what:"):
        raise ValueError("the last argument does not name what is supervised")
    if log_path != "-":
        if not os.path.isabs(log_path):
            raise ValueError("the log path is not absolute")
        try:
            status = os.lstat(log_path)
        except OSError:
            raise ValueError("the log does not exist (a supervisor creates no file)") from None
        if not stat.S_ISREG(status.st_mode) or getattr(status, "st_file_attributes", 0) & 0x400:
            raise ValueError("the log is not a regular file")  # 0x400: a reparse point (a link)
    label = " ".join(what[len("what:"):].split())[:200] or "the run"
    return SupervisorOrder(int(pid_text), int(created_text), nonce, seconds,
                           None if log_path == "-" else log_path, label)


def _say(line: str) -> None:
    """One line for whoever started the supervisor by hand; a windowed exe has no stderr.

    In ASCII, whatever the line holds: a console's code page need not have the
    character, the print would raise, and the one line would be gone (a refusal once
    contained an ellipsis; the frozen exe printed it as a byte no UTF-8 reader took).
    """
    if sys.stderr is not None:
        with contextlib.suppress(Exception):
            text = f"{SUPERVISOR_FLAG}: {line}".encode("ascii", "backslashreplace").decode("ascii")
            print(text, file=sys.stderr, flush=True)


def supervisor_main(arguments: list[str]) -> int:
    """The supervising process (module docstring). Exit codes: ``SUPERVISOR_DONE`` — it
    waited: the block released it, the process ended while it watched, or it terminated
    it; ``SUPERVISOR_IDLE`` — there was nothing to wait for when it looked (the process
    gone, the block's event not there): it never supervised; ``SUPERVISOR_REFUSED`` — the
    arguments are not ones it may act on (one line, nothing opened, nothing terminated);
    ``SUPERVISOR_FAILED`` — it failed itself."""
    try:
        order = parse_supervisor_arguments(arguments)
    except ValueError as error:
        _say(f"refused: {error}. This flag is internal: only a supervised watchdog passes it.")
        return SUPERVISOR_REFUSED
    try:
        return _supervise(order)
    except Exception as error:  # noqa: BLE001 - never a traceback, never a terminate
        _say(f"failed: {type(error).__name__}")
        return SUPERVISOR_FAILED


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _SYNCHRONIZE: Final = 0x00100000
    _PROCESS_TERMINATE: Final = 0x0001
    _PROCESS_QUERY_LIMITED_INFORMATION: Final = 0x1000
    _EVENT_MODIFY_STATE: Final = 0x0002
    _WAIT_OBJECT_0: Final = 0x0   # the first handle of a wait is signalled; +1: the second
    _WAIT_TIMEOUT: Final = 0x102

    def _kernel32() -> Any:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.GetProcessTimes.restype = wintypes.BOOL
        k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                   ctypes.POINTER(wintypes.DWORD)]
        k32.CreateEventW.restype = wintypes.HANDLE
        k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k32.OpenEventW.restype = wintypes.HANDLE
        k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k32.SetEvent.argtypes = [wintypes.HANDLE]
        k32.WaitForMultipleObjects.restype = wintypes.DWORD
        k32.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
                                               wintypes.BOOL, wintypes.DWORD]
        k32.TerminateProcess.restype = wintypes.BOOL
        k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        return k32

    def _created(k32: Any, handle: Any) -> int:
        """When the process was created (100 ns units): with the pid, its identity."""
        times = [wintypes.FILETIME() for _ in range(4)]
        if not k32.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            return 0
        return (int(times[0].dwHighDateTime) << 32) | int(times[0].dwLowDateTime)

    def _image(k32: Any, handle: Any) -> str:
        """The executable a process runs ("" when Windows will not say)."""
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value

    def _event_name(pid: int, created: int, nonce: str) -> str:
        """One event per supervised BLOCK: the nonce is the block's."""
        return f"Local\\ogp-supervised-{pid}-{created}-{nonce}"

    def _signal(event: int) -> None:
        if event:
            _kernel32().SetEvent(wintypes.HANDLE(event))

    def _close(event: int) -> None:
        if event:
            _kernel32().CloseHandle(wintypes.HANDLE(event))

    def start_supervisor(seconds: float, log_path: Path | None, what: str) -> Supervisor | None:
        """Start the process that ends this one ``seconds`` from now unless ``release()`` is
        called first. Raises (``ValueError`` for a deadline out of range, ``OSError`` when
        the event or the process cannot be created) — ``watchdog`` says so in its log."""
        if not (math.isfinite(seconds) and MIN_SUPERVISED_S <= seconds <= MAX_SUPERVISED_S):
            raise ValueError(f"a supervisor's deadline is {MIN_SUPERVISED_S:g} to {MAX_SUPERVISED_S:g} s, "
                             f"not {seconds!r}")
        k32 = _kernel32()
        pid = os.getpid()
        created = _created(k32, k32.GetCurrentProcess())
        nonce = secrets.token_hex(16)  # this BLOCK's: no other block's supervisor can find its event
        event = k32.CreateEventW(None, True, False, _event_name(pid, created, nonce))
        if not event:
            raise OSError(ctypes.get_last_error(), "the release event could not be created")
        try:
            process = subprocess.Popen(  # noqa: S603 - our own code, fixed arguments
                # "what:" keeps a name like "--selftest" from reading as a flag of its own
                [*self_command(), str(pid), str(created), nonce, f"{seconds:g}",
                 str(Path(log_path).resolve()) if log_path is not None else "-", f"what:{what}"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
        except BaseException:
            k32.CloseHandle(wintypes.HANDLE(event))
            raise
        return Supervisor(process, int(event), seconds)

    def _supervise(order: SupervisorOrder) -> int:
        if os.getppid() != order.pid:
            _say("refused: the process named is not the one that started this supervisor.")
            return SUPERVISOR_REFUSED
        k32 = _kernel32()
        process = k32.OpenProcess(
            _SYNCHRONIZE | _PROCESS_TERMINATE | _PROCESS_QUERY_LIMITED_INFORMATION, False, order.pid)
        if not process:
            return SUPERVISOR_IDLE  # it is gone already (or may not be opened): nothing to watch
        try:
            if _created(k32, process) != order.created:
                return SUPERVISOR_IDLE  # another process has that pid now: not ours to touch
            if getattr(sys, "frozen", False):
                # the same question asked of both processes, so that both answers have one form
                own, theirs = _image(k32, k32.GetCurrentProcess()), _image(k32, process)
                if not own or os.path.normcase(own) != os.path.normcase(theirs):
                    _say("refused: the process named does not run this executable.")
                    return SUPERVISOR_REFUSED
            event = k32.OpenEventW(_SYNCHRONIZE | _EVENT_MODIFY_STATE, False,
                                   _event_name(order.pid, order.created, order.nonce))
            if not event:
                # The block created its event before it started us and keeps it, signalled,
                # until we have left. No event: this is not a block we can find — or we
                # came up more than SUPERVISOR_EXIT_WAIT_S after it ended. Waiting on the
                # process alone here would END A PROCESS THAT FINISHED ITS BLOCK and
                # simply lives on — a test runner, a tool. We never supervised: say so.
                return SUPERVISOR_IDLE
            try:
                handles = (wintypes.HANDLE * 2)(process, event)
                outcome = k32.WaitForMultipleObjects(2, handles, False, int(order.seconds * 1000))
            finally:
                k32.CloseHandle(event)
            if outcome in (_WAIT_OBJECT_0, _WAIT_OBJECT_0 + 1):
                return SUPERVISOR_DONE  # it ended by itself, or released us
            if outcome != _WAIT_TIMEOUT:
                # WAIT_FAILED, or anything else Windows may answer: this supervisor waited
                # for nothing. It must not read as "supervised" (it said 0 until review
                # round 5), and it must not terminate a process it never watched.
                _say(f"failed: the wait for the supervised process failed (0x{outcome:X}).")
                return SUPERVISOR_FAILED
            if order.log_path is not None:
                with contextlib.suppress(OSError):  # append to the block's log; never create one
                    descriptor = os.open(order.log_path, os.O_WRONLY | os.O_APPEND)
                    with os.fdopen(descriptor, "a", encoding="utf-8") as log:
                        log.write(
                            f"          [supervisor] fired=True what={order.what} reason={order.what} "
                            f"was still alive {order.seconds:g} s after its watchdog was armed — its "
                            "own watchdog could not end the process (see the stack dump above, if "
                            "any); terminated from outside, exit code 1\n")
            k32.TerminateProcess(process, 1)
            return SUPERVISOR_DONE
        finally:
            k32.CloseHandle(process)

else:

    def _signal(event: int) -> None:  # noqa: ARG001 - the Windows twin's signature
        return None

    def _close(event: int) -> None:  # noqa: ARG001 - the Windows twin's signature
        return None

    def start_supervisor(seconds: float, log_path: Path | None, what: str) -> Supervisor | None:  # noqa: ARG001
        """Not needed here: ``_exit`` ends the process at once — measured on Linux in the
        very deadlock the Windows supervisor exists for (module docstring)."""
        return None

    def _supervise(order: SupervisorOrder) -> int:  # noqa: ARG001
        _say("refused: there is no supervising process on this platform.")
        return SUPERVISOR_REFUSED


if __name__ == "__main__":
    sys.exit(supervisor_main(sys.argv[1:]))
