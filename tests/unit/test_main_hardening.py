"""Issue #277 hardening in ``main.py``: the frozen ``--selftest`` and the
uncaught-exception backstop that together stop a lazily-imported subsystem
failure from silently killing the process and discarding unsaved work.
"""

from __future__ import annotations

import sys

import pytest

from open_garden_planner.main import _install_excepthook, _run_selftest


class TestExceptHook:
    def test_installs_and_shows_dialog_without_reraising(
        self, qtbot, monkeypatch  # noqa: ARG002
    ) -> None:
        from PyQt6.QtWidgets import QMessageBox

        calls: list[tuple] = []
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: calls.append(a))

        original = sys.excepthook
        try:
            _install_excepthook()
            assert sys.excepthook is not original
            # Simulate PyQt handing an uncaught slot exception to the hook.
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                sys.excepthook(*sys.exc_info())
        finally:
            sys.excepthook = original

        assert calls, "excepthook should have shown a recoverable dialog"


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="importing the Qt3D bindings needs the bundled Qt runtime "
    "(the Windows dev/CI-release environment)",
)
class TestSelfTest:
    def test_passes_on_a_consistent_qt_stack(self) -> None:
        assert _run_selftest() == 0
