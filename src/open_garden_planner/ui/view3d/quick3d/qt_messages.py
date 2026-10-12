"""Every Qt message of a render, recorded; a shader or QML error fails it (L1.2).

Ported from the L0 spike (``spike_q3d/qt_messages.py``, ADR-048 entry 17).
Why it exists: a custom shader that does not compile is only a ``QtWarningMsg``
— ``QSpirvCompiler: Failed to parse shader`` goes to stderr, the frame still
renders, in another colour. Measured in the spike: one renamed call in
``water.frag`` changed 449 pond pixels, exit code 0. A frozen GUI exe has no
stderr at all, so the only way to notice is to listen.

Four classes:

- ``error`` — the frame on screen is not the frame the QML and its shaders
  describe (shader compile/parse/link, QML load and binding errors, anything Qt
  itself calls critical or fatal). A render with one of these FAILS.
- ``warning`` — any other Qt warning. A clean render has none.
- ``environment`` — warnings measured to come from the machine, not from the
  render (``_ENVIRONMENT``, exact and short on purpose). Counted and reported,
  never a failure.
- ``info`` — debug and info output (the graphics adapter is read from it).

The LEVEL decides first: only a warning can be promoted to ``error`` by its
text. Debug and info output is never an error, whatever it says — the self-test
switches Qt's ``qt.rhi.general`` debug output on, and the wording of a Qt debug
line must not be able to fail a release.

WHERE THE RECORDER MAY BE INSTALLED — and where it must not (ADR-048 addendum
L1.2, review round 2). Qt's message handler is process-wide, and PyQt calls a
Python handler under the GIL on WHICHEVER thread Qt emits the message. Qt Quick
renders a shown window on a thread of its own (the threaded render loop;
measured on Direct3D 11, GPU and WARP). If that thread emits a message while
the GUI thread sits in a Python-called Qt function that waits for it —
``hide()`` does — both wait forever: 5 of 5. So:

- ``install`` only around rendering that happens ON THE CALLING THREAD: the
  one-shot offscreen frame of a never-shown window (``offscreen.render_records``,
  the self-test). Measured there: every message, the shader errors included,
  arrives on the calling thread. ``QtMessages.other_threads`` counts what did
  not — it must stay 0, and the render tier asserts it on every platform.
- Never beside a shown Qt Quick window. ``render_records`` refuses to run next
  to one; a shown host reports through ``Quick3DHost.health()`` instead, which
  only uses what Qt delivers on the GUI thread.

The classifier and the recorder are Qt-free (unit-tested without a GPU); only
``install`` / ``uninstall`` / ``graphics_info`` touch Qt — ``QtCore``, which is
not an engine module.
"""

from __future__ import annotations

import contextlib
import re
import sys
import threading
from collections.abc import Callable, Iterable, Iterator
from typing import Any, Final

# A message matching one of these means the frame on screen is not the frame the
# QML and its shaders describe: a shader that did not compile, a pipeline that
# could not be built, a QML error. Each alternative names a shader, a pipeline or
# a QML location — on purpose: the recorder listens to the whole process, and a
# bare "Failed to load" or "TypeError" also matched an image a widget could not
# load and the JavaScript console of a web page (review round 2).
_ERROR: Final = re.compile(
    r"QSpirvCompiler|QShaderBaker"
    r"|Failed to (compile|parse|link|build|load|create)[^\n]*(shader|pipeline|program)"
    r"|shader[^\n]*(fail|error)|\.(frag|vert|glsl):\d+"
    r"|\.qml:\d+(:\d+)?: |QQmlComponent"
    r"|is not a type|non-existent property|Cannot assign",
    re.IGNORECASE,
)

# Not ours at any level: QtWebEngine forwards a web page's JavaScript console under
# the category "js" (its text starts with "js: " where the category was lost).
_FOREIGN_CATEGORIES: Final = frozenset({"js"})

# Warnings of the MACHINE, each measured, each (category, pattern) exact. Checked
# AFTER the error rules, so nothing here can hide a broken shader. Do not widen an
# entry to a whole category: an allow-list wider than what was measured is a hole.
_ENVIRONMENT: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    # Qt 6.11 on Windows asks SetupAPI for the monitor's EDID when a window opens;
    # with the display asleep (the L1.2 dev box, 2026-10-11) that fails on every run:
    #   qt.qpa.screen: "Unable to open monitor interface to \\.\DISPLAY1:" "Unknown error 0xe0000225."
    ("qt.qpa.screen", re.compile(r'^"?Unable to open monitor interface to ')),
)

_KEEP: Final = 100  # per class: enough to read, bounded for a long session
CLASSES: Final = ("error", "warning", "environment", "info")

_ADAPTER: Final = re.compile(r"Adapter \d+: '([^']*)'")
_GRAPHICS_INFO_DEPTH: Final = [0]  # nesting depth of graphics_info() blocks (GUI thread)
_GL_RENDERER: Final = re.compile(r"OpenGL VENDOR: .*? RENDERER: (.*?) VERSION: ")


def classify(kind: str, text: str, category: str = "") -> str:
    """``"error"``, ``"warning"``, ``"environment"`` or ``"info"`` for one Qt message.

    ``kind`` is the Qt message type in lower case (``debug``, ``info``,
    ``warning``, ``critical``, ``fatal``).
    """
    if category in _FOREIGN_CATEGORIES or text.startswith("js: "):
        return "info"  # a web page's console: never a statement about the 3D frame
    if kind in ("critical", "fatal"):
        return "error"
    if kind != "warning":
        return "info"  # debug / info output is never an error, whatever its wording
    if _ERROR.search(text):
        return "error"
    for wanted, pattern in _ENVIRONMENT:
        if category == wanted and pattern.search(text):
            return "environment"
    return "warning"


class QtMessages:
    """A record of Qt messages. Create it on the thread that renders (module docstring).

    It takes a lock, so a message from another thread cannot corrupt it — but such a
    message is exactly what must not happen where a recorder is installed:
    ``other_threads`` counts them.
    """

    def __init__(self, log: Callable[..., None] | None = None) -> None:
        self._log = log
        self._lock = threading.Lock()
        self._thread = threading.get_ident()
        self.counts: dict[str, int] = dict.fromkeys(CLASSES, 0)
        self.kept: dict[str, list[str]] = {name: [] for name in CLASSES}
        #: Messages delivered on a thread other than the one that created the recorder.
        self.other_threads = 0

    def add(self, kind: str, text: str, category: str = "") -> None:
        """Record one message. Never raises: it runs inside Qt's message handler,
        where PyQt turns an exception into ``qFatal`` — an abort (the spike
        reproduced exit 134 with a write to a closed log)."""
        try:
            cls = classify(kind, text, category)
            line = f"{kind}: {category + ': ' if category else ''}{text}"
            with self._lock:
                if threading.get_ident() != self._thread:
                    self.other_threads += 1
                self.counts[cls] += 1
                n = self.counts[cls]
                if len(self.kept[cls]) < _KEEP:
                    self.kept[cls].append(line[:600])
            if self._log is not None and cls != "info" and n <= _KEEP:
                suffix = " (further ones only counted)" if n == _KEEP else ""
                self._log("qt", level=cls, msg=line[:300].replace("\n", " ") + suffix)
        except Exception:  # noqa: BLE001, S110 - see the docstring
            pass

    @property
    def errors(self) -> list[str]:
        with self._lock:
            return list(self.kept["error"])

    @property
    def warnings(self) -> list[str]:
        with self._lock:
            return list(self.kept["warning"])

    @property
    def clean(self) -> bool:
        """No error and no warning (environment and info do not count)."""
        with self._lock:
            return self.counts["error"] == 0 and self.counts["warning"] == 0

    def info_lines(self) -> list[str]:
        with self._lock:
            return list(self.kept["info"])

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {"counts": dict(self.counts), "errors": list(self.kept["error"]),
                    "warnings": list(self.kept["warning"][:30]),
                    "environment": list(self.kept["environment"][:30]),
                    "other_threads": self.other_threads}


def graphics_adapter(info_lines: Iterable[str]) -> str | None:
    """The graphics device Qt chose, read from ``qt.rhi.general`` (see
    ``graphics_info``) — or None when the lines do not say.

    Direct3D lists every adapter and marks one with ``using this adapter``; the
    marker follows the adapter it means. OpenGL prints the context's
    ``RENDERER``. The last device created wins.
    """
    chosen: str | None = None
    last_listed: str | None = None
    for line in info_lines:
        if (match := _ADAPTER.search(line)) is not None:
            last_listed = match.group(1)
        elif "using this adapter" in line:
            if last_listed is not None:
                chosen = last_listed
        elif (match := _GL_RENDERER.search(line)) is not None:
            chosen = match.group(1).strip()
    return chosen


@contextlib.contextmanager
def graphics_info() -> Iterator[None]:
    """Make Qt name its graphics device (``qt.rhi.general``) for the block — as debug
    output, which the recorder files under ``info`` — and switch it off again after.
    Enter it before the Quick window is created.

    ``QLoggingCategory.setFilterRules`` holds ONE rule set per process and has no
    getter: entering replaces rules set the same way, leaving clears them. Nothing
    in the app sets any (2026-10); a caller that does must not use this. Blocks
    may nest (a recorded run around a recorded frame): the outermost one switches.
    """
    from PyQt6.QtCore import QLoggingCategory

    if _GRAPHICS_INFO_DEPTH[0] == 0:
        QLoggingCategory.setFilterRules("qt.rhi.general.debug=true")
    _GRAPHICS_INFO_DEPTH[0] += 1
    try:
        yield
    finally:
        _GRAPHICS_INFO_DEPTH[0] -= 1
        if _GRAPHICS_INFO_DEPTH[0] == 0:
            QLoggingCategory.setFilterRules("")


def install(messages: QtMessages) -> Any:
    """Route every Qt message through ``messages``, then on to whoever listened
    before (a recorder further out, the app's own handler) — or to stderr when
    nobody did. Returns that previous handler: give it to ``uninstall``.

    ONLY around rendering on the calling thread, never beside a shown Qt Quick
    window (module docstring: it deadlocks against the render thread)."""
    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

    names = {QtMsgType.QtDebugMsg: "debug", QtMsgType.QtInfoMsg: "info",
             QtMsgType.QtWarningMsg: "warning", QtMsgType.QtCriticalMsg: "critical",
             QtMsgType.QtFatalMsg: "fatal"}
    outer: list[Any] = [None]

    def handler(mode: Any, context: Any, text: str | None) -> None:
        category = getattr(context, "category", None) or ""
        if isinstance(category, bytes):
            category = category.decode("utf-8", "replace")
        if category == "default":
            category = ""
        kind = names.get(mode, "warning")
        messages.add(kind, text or "", category)
        # never raise in here: PyQt turns an exception in a message handler into qFatal
        with contextlib.suppress(Exception):
            if outer[0] is not None:
                outer[0](mode, context, text)
            elif sys.stderr is not None and kind != "debug":
                print(text, file=sys.stderr, flush=True)

    outer[0] = qInstallMessageHandler(handler)
    return outer[0]


def uninstall(previous: Any = None) -> None:
    """Put ``previous`` back (Qt's default handler when None) — BEFORE the log the
    recorder writes to closes."""
    from PyQt6.QtCore import qInstallMessageHandler

    qInstallMessageHandler(previous)
