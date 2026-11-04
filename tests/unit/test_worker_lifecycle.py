"""Unit tests for open_garden_planner.core.worker_lifecycle."""

from __future__ import annotations

import time

from PyQt6.QtCore import QThread

from open_garden_planner.core.worker_lifecycle import (
    _RETIRING_WORKERS,
    retain_worker_until_finished,
)


class _DummyWorker(QThread):
    def __init__(self, duration_s: float = 0.1) -> None:
        super().__init__()
        self.duration_s = duration_s

    def run(self) -> None:
        time.sleep(self.duration_s)


def test_retain_worker_holds_until_finished(qtbot) -> None:
    worker = _DummyWorker(duration_s=0.15)
    worker.start()
    assert worker.isRunning()

    retain_worker_until_finished(worker)
    assert worker in _RETIRING_WORKERS

    worker.wait(1000)
    assert not worker.isRunning()
    qtbot.waitUntil(lambda: worker not in _RETIRING_WORKERS, timeout=1000)


def test_retain_worker_discarded_if_already_stopped(qtbot) -> None:
    worker = _DummyWorker(duration_s=0.01)
    worker.start()
    worker.wait(1000)
    assert not worker.isRunning()

    retain_worker_until_finished(worker)
    assert worker not in _RETIRING_WORKERS
