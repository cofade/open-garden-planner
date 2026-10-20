"""The crash marker of the 3D workspace (Phase 17 L1.3, ADR-060). Standard library only.

Building the first Qt Quick 3D window of a session creates a graphics device,
compiles shaders and renders a first frame — all inside the graphics driver, and
a driver that dies there takes the process with it: no exception, no dialog,
no log line. So the app leaves a note BEFORE it tries and removes it when the
first frame was presented. A note that is still there at the next start means
the last attempt died, and this session renders 3D on the software rasteriser
(WARP on Windows, llvmpipe on Linux) and says so. A start that dies THERE too
leaves nothing to fall back to: 3D is switched off, and says so.

Two small files in the app's log directory (beside ``app.log``):

- ``view3d-init-<pid>.marker`` — "process <pid> is building its first 3D window,
  in this mode". One per process, so two running instances never read each other's
  start as a crash and each removes only its own.
- ``view3d-compat.flag`` — "do not use the graphics card for 3D": render it in
  software (the file is empty, or says ``software``), or not at all (``off``). Set
  when a dead start is found, and by the user; removed ONLY by the user ("try
  hardware again"). Without it a machine whose driver crashes would alternate
  between a crash and a software session for ever; with it, nothing but a crash or
  the user ever moves a healthy machine off its graphics card.

The state machine — three outcomes, hardware, software and off; ``begin()``
decides, and exactly one outcome ends a start::

    begin()                  markers of starts that are not IN PROGRESS (the process is
                             gone, or the marker is older than MAX_INIT_S — or it carries
                             OUR pid and we have no start pending: the process that had
                             this id before us died) are deaths, each in the mode the
                             marker names:
                               a death in SOFTWARE mode → flag "off";
                               else a death in hardware mode → flag "software"
                               (a flag that says "off" already stays).
                             mode = what the flag says, HARDWARE without one.
                             HARDWARE / SOFTWARE: own marker written → pending.
                             OFF: nothing is started, nothing is written.
    confirm_first_frame()    a frame was presented            → own marker removed
    graphics_failed()        Qt reported "no graphics device" → own marker removed
                             (the process lives: NOT a crash; nothing is switched)
    init_failed()            Python caught an error (import, QML) → own marker removed
    abandon()                the start is no longer watched — the app closes, or the 3D
                             view was hidden before its first frame → own marker removed
    mark_again()             … and it is shown again, still without a first frame
                             → own marker written again (the mode stays)
    try_hardware_next_time() flag removed (takes effect at the next start)
    use_software_next_time() flag "software"

Why ``abandon()`` on hide: the first frame is confirmed by a poll that runs only
while the 3D view is shown. A view hidden before its first frame would keep its
marker for the rest of the session, and ``MAX_INIT_S`` later a second instance
would read it as a death — and take a healthy machine off its graphics card.

A session that never opens 3D calls none of these with a pending start: it reads
nothing and writes nothing, so a marker left by a dead process survives it and
the next session that does open 3D still learns of the death.

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
    """How the 3D window is started: on which adapter — or not at all."""

    HARDWARE = "hardware"
    SOFTWARE = "software"
    #: A start in software mode died as well: 3D is not started.
    OFF = "off"


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
        self._over = True  # no start is under way (none was begun, or it has ended)

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
        """True while a start of ours is watched: our marker is on disk."""
        return self._pending

    def requested_mode(self) -> RenderMode:
        """How the NEXT start will be made, by what the compat flag says right now:
        ``HARDWARE`` without a flag (and when the folder cannot be read), ``OFF`` for a
        flag that says so, ``SOFTWARE`` for any other flag — an empty one too, which is
        what a first delivery of this module wrote."""
        directory = self._directory
        if directory is None:
            return RenderMode.HARDWARE
        try:
            content = (directory / COMPAT_NAME).read_text(encoding="utf-8")
        except FileNotFoundError:
            return RenderMode.HARDWARE
        except (OSError, ValueError):
            # the flag is there and cannot be read: the careful reading of "do not
            # use the graphics card" is software, not hardware
            return (RenderMode.SOFTWARE if self._flag_exists() else RenderMode.HARDWARE)
        return RenderMode.OFF if content.strip() == RenderMode.OFF.value else RenderMode.SOFTWARE

    def software_requested(self) -> bool:
        """Whether the compat flag is on: the next start will NOT use the graphics
        card (software — or not at all). The user's way back is
        ``try_hardware_next_time()``."""
        return self.requested_mode() is not RenderMode.HARDWARE

    # ── the start ────────────────────────────────────────────────────────────

    def begin(self) -> RenderMode:
        """Decide the mode for the 3D window about to be built, and mark the start
        (module docstring). ``OFF``: build nothing."""
        deaths = self._collect_dead_starts()
        died = bool(deaths)
        if RenderMode.SOFTWARE in deaths:
            self._write_compat(RenderMode.OFF)
        elif died and self.requested_mode() is RenderMode.HARDWARE:
            self._write_compat(RenderMode.SOFTWARE)
        mode = self.requested_mode()
        self._mode = mode
        if mode is RenderMode.HARDWARE:
            self._reason = ModeReason.NORMAL
        elif died:
            self._reason = ModeReason.PREVIOUS_START_DIED
        else:
            self._reason = ModeReason.KEPT_FROM_AN_EARLIER_SESSION
        self._over = mode is RenderMode.OFF
        self._pending = not self._over and self._write_marker()
        return mode

    def confirm_first_frame(self) -> None:
        """A frame was presented: this start did not die."""
        self._resolve(over=True)

    def graphics_failed(self) -> None:
        """Qt reported that the graphics device could not be created. The process is
        alive, so this is not a crash, and nothing is switched for the next start."""
        self._resolve(over=True)

    def init_failed(self) -> None:
        """An error Python caught (an import, a scene file that did not load)."""
        self._resolve(over=True)

    def abandon(self) -> None:
        """The start is no longer watched: the app is closing in good order, or the
        3D view was hidden before its first frame (nothing confirms a frame while it
        is hidden — module docstring). ``mark_again()`` takes the watch up again."""
        self._resolve(over=False)

    def mark_again(self) -> None:
        """The 3D view is shown again and its first frame is still to come: write our
        marker again, in the mode ``begin()`` decided. Nothing for a start that is
        watched already, that has ended (a first frame, a failure), that was never
        begun, or that is switched off."""
        if self._pending or self._over:
            return
        self._pending = self._write_marker()

    # ── the user's switch ────────────────────────────────────────────────────

    def try_hardware_next_time(self) -> bool:
        """Remove the compat flag. True when it is gone — the next start will use the
        graphics card; False when it could not be removed (logged)."""
        directory = self._directory
        if directory is None:
            return True  # no books: nothing ever asked for anything but hardware
        try:
            (directory / COMPAT_NAME).unlink(missing_ok=True)
        except OSError as error:
            _LOG.warning("3D start guard: cannot remove %s (%s)", COMPAT_NAME, _said(error))
        return not self._flag_exists()

    def use_software_next_time(self) -> bool:
        """Ask for software rendering from the next start on. True when the flag says
        so now; False when it could not be written (logged)."""
        self._write_compat(RenderMode.SOFTWARE)
        return self.requested_mode() is RenderMode.SOFTWARE

    # ── internals ────────────────────────────────────────────────────────────

    def _flag_exists(self) -> bool:
        directory = self._directory
        if directory is None:
            return False
        try:
            return (directory / COMPAT_NAME).is_file()
        except OSError:
            return False

    def _resolve(self, *, over: bool) -> None:
        """Remove our marker if a start of ours is watched. ``over``: the start has
        ENDED (a first frame, a failure) — it cannot be marked again."""
        self._over = self._over or over
        if not self._pending:
            return  # no start of ours is watched: touch nothing
        self._pending = False
        directory = self._directory
        if directory is None:
            return
        try:
            (directory / marker_name(self._pid)).unlink(missing_ok=True)
        except OSError as error:
            _LOG.warning("3D start guard: cannot remove the start marker (%s)", _said(error))

    def _collect_dead_starts(self) -> set[RenderMode]:
        """Remove the markers of starts that died; the modes they died in (empty: none)."""
        directory = self._directory
        if directory is None:
            return set()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            names = [entry.name for entry in directory.iterdir()]
        except OSError as error:
            _LOG.warning("3D start guard: %r cannot be used (%s); 3D starts without a crash "
                         "marker", str(directory), _said(error))
            return set()
        deaths: set[RenderMode] = set()
        for name in names:
            pid = marker_pid(name)
            if pid is None:
                continue
            marker = directory / name
            if pid == self._pid:
                if self._pending:
                    continue  # our own start, watched right now
                # our id and no start of ours: the process that had this id BEFORE us
                # left it — and "does that process run?" would be asking about ourselves
            elif self._in_progress(marker, pid):
                continue  # a second instance of the app is starting its 3D view right now
            deaths.add(self._mode_of(marker))
            with contextlib.suppress(OSError):
                marker.unlink(missing_ok=True)
        return deaths

    @staticmethod
    def _read(marker: Path) -> dict[str, object]:
        try:
            content = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return content if isinstance(content, dict) else {}

    def _mode_of(self, marker: Path) -> RenderMode:
        """The mode a start was made in, by its marker. A marker that does not say
        (unreadable, or written by something else) is read as a hardware start: the
        answer to that is software, the milder of the two."""
        mode = self._read(marker).get("mode")
        return RenderMode.SOFTWARE if mode == RenderMode.SOFTWARE.value else RenderMode.HARDWARE

    def _in_progress(self, marker: Path, pid: int) -> bool:
        if not self._is_running(pid):
            return False
        started = self._read(marker).get("started")  # unreadable: nobody can say it is recent
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

    def _write_compat(self, mode: RenderMode) -> None:
        directory = self._directory
        if directory is None:
            return
        try:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / COMPAT_NAME).write_text(mode.value, encoding="utf-8")
        except OSError as error:
            _LOG.warning("3D start guard: cannot write %s (%s)", COMPAT_NAME, _said(error))
