"""Worker lifecycle and retirement tracking to prevent premature destruction crashes.

When a QThread is unparented or superseded while still running (e.g. blocked in
a socket read or waiting on an OS resource), Python garbage collection of the
wrapper object invokes ~QThread() in C++, causing an immediate fatal abort:
    'QThread: Destroyed while thread is still running' (0xC0000409).

This module provides a process-wide retention registry ensuring Python wrapper
references remain alive until the underlying C++ thread emits `finished`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtCore import QThread

logger = logging.getLogger(__name__)

_RETIRING_WORKERS: set[QThread] = set()


def retain_worker_until_finished(worker: QThread) -> None:
    """Retain a Python reference to an active QThread until it finishes (#480, #483).

    Prevents Python GC from destroying the Python wrapper and triggering
    Qt C++ destructor ~QThread while isRunning() is True (which aborts
    the process with 0xC0000409).
    """
    _RETIRING_WORKERS.add(worker)

    def _cleanup() -> None:
        _RETIRING_WORKERS.discard(worker)

    worker.finished.connect(_cleanup)
    # Check after connecting to eliminate the race where the worker finished
    # immediately before or during signal connection.
    if not worker.isRunning():
        _RETIRING_WORKERS.discard(worker)

