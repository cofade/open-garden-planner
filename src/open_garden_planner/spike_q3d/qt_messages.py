"""Every Qt message the spike's process emits, recorded; shader and QML errors fail the run.

Without this, a broken custom shader was invisible to the evidence: renaming one
function in ``water.frag`` printed ``QSpirvCompiler: Failed to parse shader`` to
stderr, the run exited 0 with ``status: ok``, and 449 pond pixels silently
changed colour (senior review, measured). A frozen GUI exe has no stderr at all.

The classifier is Qt-free (unit-tested); only ``install`` touches Qt.
"""

from __future__ import annotations

import re
import sys
import threading
from collections.abc import Callable
from typing import Any

# A message matching one of these means the frame on screen is not the frame the
# QML and its shaders describe: a shader that did not compile, a QML error.
_ERROR = re.compile(
    r"QSpirvCompiler|QShaderBaker|Failed to (compile|parse|link|build|load)"
    r"|shader[^\n]*(fail|error)|\.(frag|vert|glsl):\d+"
    r"|\.qml:\d+(:\d+)?: |QQmlComponent|ReferenceError|TypeError"
    r"|is not a type|non-existent property|Cannot assign",
    re.IGNORECASE,
)
_KEEP = 100  # per class: enough to read, bounded for a long soak


def classify(kind: str, text: str) -> str:
    """``"error"``, ``"warning"`` or ``"info"`` for one Qt message.

    ``kind`` is the Qt message type in lower case (``debug``, ``info``,
    ``warning``, ``critical``, ``fatal``).
    """
    if kind in ("critical", "fatal") or _ERROR.search(text):
        return "error"
    return "warning" if kind == "warning" else "info"


class QtMessages:
    """Thread-safe record of Qt messages (Qt may call from its render thread)."""

    def __init__(self, log: Callable[..., None] | None = None) -> None:
        self._log = log
        self._lock = threading.Lock()
        self.counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
        self.kept: dict[str, list[str]] = {"error": [], "warning": [], "info": []}

    def add(self, kind: str, text: str, category: str = "") -> None:
        """Record one message. Never raises: it runs inside Qt's message handler,
        where PyQt turns an exception into ``qFatal`` — an abort (senior review:
        a write to the closed log after the run reproduced exit 134)."""
        try:
            cls = classify(kind, text)
            line = f"{kind}: {category + ': ' if category else ''}{text}"
            with self._lock:
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

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {"counts": dict(self.counts), "errors": list(self.kept["error"]),
                    "warnings": list(self.kept["warning"][:30])}


def install(messages: QtMessages) -> None:
    """Route every Qt message through ``messages`` (and on to stderr when there is one)."""
    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

    names = {QtMsgType.QtDebugMsg: "debug", QtMsgType.QtInfoMsg: "info",
             QtMsgType.QtWarningMsg: "warning", QtMsgType.QtCriticalMsg: "critical",
             QtMsgType.QtFatalMsg: "fatal"}

    def handler(mode: Any, context: Any, text: str | None) -> None:
        category = getattr(context, "category", None) or ""
        if isinstance(category, bytes):
            category = category.decode("utf-8", "replace")
        if category == "default":
            category = ""
        messages.add(names.get(mode, "warning"), text or "", category)
        if sys.stderr is not None:
            print(text, file=sys.stderr, flush=True)

    qInstallMessageHandler(handler)


def uninstall() -> None:
    """Give Qt its default handler back — before the log the recorder writes to closes."""
    from PyQt6.QtCore import qInstallMessageHandler

    qInstallMessageHandler(None)
