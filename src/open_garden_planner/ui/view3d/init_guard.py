"""The crash marker of the 3D workspace (Phase 17 L1.3, ADR-065). Standard library only.

Building the first Qt Quick 3D window of a session creates a graphics device,
compiles shaders and renders a first frame — all inside the graphics driver, and
a driver that dies there takes the process with it: no exception, no dialog,
no log line. So the app leaves a note BEFORE it tries and removes it when the
first frame was presented. A note that is still there at the next start means
the last attempt died, and this session renders 3D on the software rasteriser
(WARP on Windows, llvmpipe on Linux) and says so.

Two small files in the app's log directory (beside ``app.log``):

- ``view3d-init-<pid>.marker`` — "process <pid> is building its first 3D window".
  One per process, so two running instances never read each other's start as a
  crash and each removes only its own.
- ``view3d-compat.flag`` — "render 3D in software". Set when a dead start is
  found, and by the user; removed ONLY by the user ("try hardware again").
  Without it a machine whose driver crashes would alternate between a crash and
  a software session for ever; with it, nothing but a crash or the user ever
  moves a healthy machine off its graphics card.

The state machine — ``begin()`` decides, exactly one outcome ends a start::

    begin()                  other processes' markers: one that is not IN PROGRESS
                             (its process is gone, or it is older than MAX_INIT_S)
                             is a death → compat flag on, marker removed.
                             mode = SOFTWARE if the compat flag is on else HARDWARE.
                             Own marker written → pending.
    confirm_first_frame()    a frame was presented            → own marker removed
    graphics_failed()        Qt reported "no graphics device" → own marker removed
                             (the process lives: NOT a crash; nothing is switched)
    init_failed()            Python caught an error (import, QML) → own marker removed
    abandon()                the app closes while the start is pending → removed
    try_hardware_next_time() compat flag off (takes effect at the next start)
    use_software_next_time() compat flag on

A session that never opens 3D calls none of the first four with a pending start:
it reads nothing and writes nothing, so a marker left by a dead process survives
it and the next session that does open 3D still learns of the death.

False alarms, stated: a process the user killed (or a power cut) inside the
start leaves a marker like a crash does — one click on "try hardware again"
undoes it. Nothing here ever raises into the app: a folder that cannot be read or
written means hardware rendering and no books.
"""

from __future__ import annotations

import contextlib
import enum
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

_LOG: Final = logging.getLogger(__name__)

COMPAT_NAME: Final = "view3d-compat.flag"
_MARKER_PREFIX: Final = "view3d-init-"
_MARKER_SUFFIX: Final = ".marker"
#: No first 3D start takes this long (measured: 0.4–1.2 s on a GPU, a few seconds
#: on a software rasteriser). A marker older than this whose process id "runs"
#: belongs to a process that died and whose id was handed out again.
MAX_INIT_S: Final = 600.0


class RenderMode(enum.Enum):
    """Which adapter the 3D window is asked to use."""

    HARDWARE = "hardware"
    SOFTWARE = "software"


class ModeReason(enum.Enum):
    """Why ``begin()`` chose its mode — what the workspace's notice says."""

    NORMAL = "normal"
    PREVIOUS_START_DIED = "previous_start_died"
    KEPT_FROM_AN_EARLIER_SESSION = "kept_from_an_earlier_session"


def marker_name(pid: int) -> str:
    return f"{_MARKER_PREFIX}{pid}{_MARKER_SUFFIX}"


def marker_pid(name: str) -> int | None:
    """The process id a marker file is named after; None for any other file."""
    if not (name.startswith(_MARKER_PREFIX) and name.endswith(_MARKER_SUFFIX)):
        return None
    digits = name[len(_MARKER_PREFIX):-len(_MARKER_SUFFIX)]
    return int(digits) if digits.isdecimal() else None


def process_is_running(pid: int) -> bool:
    """Whether a process with this id exists right now (it may be another program
    that was given the id later — ``MAX_INIT_S`` bounds that mistake)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        query_limited_information, access_denied, still_active = 0x1000, 5, 259
        handle = kernel32.OpenProcess(query_limited_information, False, pid)
        if not handle:
            return bool(ctypes.get_last_error() == access_denied)  # it exists; it is not ours
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return bool(code.value == still_active)
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def default_directory() -> Path | None:
    """The app's log directory — where ``app.log`` lives — or None if there is none."""
    try:
        from open_garden_planner.core.logging_config import resolve_log_dir

        return resolve_log_dir()
    except Exception as error:  # noqa: BLE001 - no folder means no books, never no 3D
        _LOG.warning("3D start guard: the log directory is not available (%s)", _said(error))
        return None


def _said(error: BaseException) -> str:
    """An error for ONE log line: its type and its message, quoted (``repr`` keeps a
    line break in a path or a message inside the record — §8.11). No traceback:
    every caller here is a file operation whose failure the message describes."""
    return f"{type(error).__name__}: {str(error)!r}"


class Init3DGuard:
    """The marker state machine (module docstring). One per main window.

    ``directory``: where the two files live (None: keep no books). ``pid``,
    ``is_running`` and ``now`` are this process, "does that process run?" and the
    wall clock — handed in by the tests.
    """

    def __init__(self, directory: Path | None, *, pid: int | None = None,
                 is_running: Callable[[int], bool] = process_is_running,
                 now: Callable[[], float] = time.time) -> None:
        self._directory = directory
        self._pid = os.getpid() if pid is None else pid
        self._is_running = is_running
        self._now = now
        self._mode: RenderMode | None = None
        self._reason = ModeReason.NORMAL
        self._pending = False

    # ── reads ────────────────────────────────────────────────────────────────

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def mode(self) -> RenderMode | None:
        """What ``begin()`` decided; None while 3D was never started this session."""
        return self._mode

    @property
    def reason(self) -> ModeReason:
        return self._reason

    @property
    def pending(self) -> bool:
        """True between ``begin()`` and its outcome: our marker is on disk."""
        return self._pending

    def software_requested(self) -> bool:
        """Whether the NEXT start will be in software mode (the compat flag is on)."""
        directory = self._directory
        if directory is None:
            return False
        try:
            return (directory / COMPAT_NAME).is_file()
        except OSError:
            return False

    # ── the start ────────────────────────────────────────────────────────────

    def begin(self) -> RenderMode:
        """Decide the mode for the 3D window about to be built, and mark the start."""
        died = self._collect_dead_starts()
        if died:
            self._write_compat()
        software = self.software_requested()
        self._mode = RenderMode.SOFTWARE if software else RenderMode.HARDWARE
        if died and software:
            self._reason = ModeReason.PREVIOUS_START_DIED
        elif software:
            self._reason = ModeReason.KEPT_FROM_AN_EARLIER_SESSION
        else:
            self._reason = ModeReason.NORMAL
        self._pending = self._write_marker()
        return self._mode

    def confirm_first_frame(self) -> None:
        """A frame was presented: this start did not die."""
        self._resolve()

    def graphics_failed(self) -> None:
        """Qt reported that the graphics device could not be created. The process is
        alive, so this is not a crash, and nothing is switched for the next start."""
        self._resolve()

    def init_failed(self) -> None:
        """An error Python caught (an import, a scene file that did not load)."""
        self._resolve()

    def abandon(self) -> None:
        """The app is closing in good order while the start is still pending."""
        self._resolve()

    # ── the user's switch ────────────────────────────────────────────────────

    def try_hardware_next_time(self) -> None:
        directory = self._directory
        if directory is None:
            return
        try:
            (directory / COMPAT_NAME).unlink(missing_ok=True)
        except OSError as error:
            _LOG.warning("3D start guard: cannot remove %s (%s)", COMPAT_NAME, _said(error))

    def use_software_next_time(self) -> None:
        self._write_compat()

    # ── internals ────────────────────────────────────────────────────────────

    def _resolve(self) -> None:
        if not self._pending:
            return  # no start of ours is pending: touch nothing
        self._pending = False
        directory = self._directory
        if directory is None:
            return
        try:
            (directory / marker_name(self._pid)).unlink(missing_ok=True)
        except OSError as error:
            _LOG.warning("3D start guard: cannot remove the start marker (%s)", _said(error))

    def _collect_dead_starts(self) -> bool:
        """Remove the markers of starts that died; True if there was one."""
        directory = self._directory
        if directory is None:
            return False
        try:
            directory.mkdir(parents=True, exist_ok=True)
            names = [entry.name for entry in directory.iterdir()]
        except OSError as error:
            _LOG.warning("3D start guard: %r cannot be used (%s); 3D starts without a crash "
                         "marker", str(directory), _said(error))
            return False
        died = False
        for name in names:
            pid = marker_pid(name)
            if pid is None or pid == self._pid:
                continue
            if self._in_progress(directory / name, pid):
                continue  # a second instance of the app is starting its 3D view right now
            died = True
            with contextlib.suppress(OSError):
                (directory / name).unlink(missing_ok=True)
        return died

    def _in_progress(self, marker: Path, pid: int) -> bool:
        if not self._is_running(pid):
            return False
        try:
            started = json.loads(marker.read_text(encoding="utf-8")).get("started")
        except (OSError, ValueError, AttributeError):
            return False  # unreadable: nobody can say it is recent
        if isinstance(started, bool) or not isinstance(started, (int, float)):
            return False
        return bool(0.0 <= self._now() - float(started) < MAX_INIT_S)

    def _write_marker(self) -> bool:
        directory = self._directory
        mode = self._mode
        if directory is None or mode is None:
            return False
        content = json.dumps({"pid": self._pid, "started": self._now(), "mode": mode.value})
        try:
            with open(directory / marker_name(self._pid), "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())  # the reader is a process started after a crash
        except OSError as error:
            _LOG.warning("3D start guard: cannot write the start marker (%s); a crash during "
                         "this start would go unnoticed", _said(error))
            return False
        return True

    def _write_compat(self) -> None:
        directory = self._directory
        if directory is None:
            return
        try:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / COMPAT_NAME).write_text("", encoding="utf-8")
        except OSError as error:
            _LOG.warning("3D start guard: cannot write %s (%s)", COMPAT_NAME, _said(error))
