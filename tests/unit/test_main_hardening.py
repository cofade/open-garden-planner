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
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **_k: calls.append(a))

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

    def test_returns_nonzero_on_version_mismatch(self, monkeypatch) -> None:
        """The load-bearing #277 detector: a Qt runtime that differs from the
        Qt3D wheel micro must fail (exit 1), even when the imports succeed."""
        import importlib.metadata as md

        real = md.version
        monkeypatch.setattr(
            md,
            "version",
            lambda name: "0.0.0-mismatch" if name == "PyQt6-3D-Qt6" else real(name),
        )
        assert _run_selftest() == 1


class TestMainUtilities:
    def test_get_icon_path(self) -> None:
        from open_garden_planner.main import get_icon_path

        p = get_icon_path()
        assert p.name == "OGP_logo.png"
        assert p.exists()

    def test_write_crash_log(self, tmp_path, monkeypatch) -> None:
        from PyQt6.QtCore import QStandardPaths

        from open_garden_planner.main import _write_crash_log

        monkeypatch.setattr(QStandardPaths, "writableLocation", lambda _loc: str(tmp_path))
        _write_crash_log("test crash entry")
        crash_log = tmp_path / "crash.log"
        assert crash_log.exists()
        assert "test crash entry" in crash_log.read_text(encoding="utf-8")

    def test_main_selftest_dispatch(self, monkeypatch) -> None:
        import open_garden_planner.main as ogp_main

        monkeypatch.setattr(ogp_main, "_run_selftest", lambda: 42)
        monkeypatch.setattr(sys, "argv", ["ogp", "--selftest"])
        assert ogp_main.main() == 42
