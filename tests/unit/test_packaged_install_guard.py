"""A Store (MSIX) install must not be offered the GitHub installer (ADR-073 item 6a).

The update bar's "Download && Install" launches the NSIS installer; inside a
packaged install that would put a second, unsigned copy next to the packaged one
through the SmartScreen wall the Store channel exists to avoid. The guard is the
package-identity probe plus an early return in the application's update start.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import pytest

from open_garden_planner.services import update_checker

ROOT = Path(__file__).resolve().parents[2]


def test_an_unpackaged_process_reports_no_identity() -> None:
    """This test process is never a Store install."""
    assert update_checker.has_package_identity() is False


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows API is the thing under test")
def test_the_probe_asks_the_app_model_api_and_reads_its_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """ERROR_INSUFFICIENT_BUFFER with a length means 'packaged'; NO_PACKAGE means not."""
    calls: list[int] = []

    class _Kernel32:
        @staticmethod
        def GetCurrentPackageFullName(length_ref, _buffer):
            calls.append(1)
            target = length_ref._obj
            target.value = 60
            return update_checker._ERROR_INSUFFICIENT_BUFFER

    class _WinDll:
        kernel32 = _Kernel32()

    monkeypatch.setattr(ctypes, "windll", _WinDll(), raising=False)
    assert update_checker.has_package_identity() is True
    assert calls == [1]

    class _NoPackage:
        @staticmethod
        def GetCurrentPackageFullName(_length_ref, _buffer):
            return update_checker._APPMODEL_ERROR_NO_PACKAGE

    _WinDll.kernel32 = _NoPackage()
    assert update_checker.has_package_identity() is False


def _start_update_check_on(fake_app: object) -> None:
    """Run the application's method on a stand-in: only the guard path is exercised."""
    from open_garden_planner.app.application import GardenPlannerApp

    GardenPlannerApp._start_update_check(fake_app)  # type: ignore[arg-type]


def test_a_packaged_frozen_app_starts_no_github_update_checker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Behaviour, not source layout: frozen + package identity -> no UpdateChecker is built."""
    from types import SimpleNamespace

    created: list[object] = []

    class _Checker:
        def __init__(self, parent: object) -> None:
            created.append(parent)
            self.update_available = SimpleNamespace(connect=lambda _slot: None)

        def start(self) -> None:
            created.append("started")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(update_checker, "UpdateChecker", _Checker)
    fake_app = SimpleNamespace(_on_update_available=lambda _release: None)

    monkeypatch.setattr(update_checker, "has_package_identity", lambda: True)
    _start_update_check_on(fake_app)
    assert created == [] and not hasattr(fake_app, "_update_checker")

    monkeypatch.setattr(update_checker, "has_package_identity", lambda: False)
    _start_update_check_on(fake_app)
    assert created == [fake_app, "started"], "the NSIS/frozen exe keeps its GitHub update check"
