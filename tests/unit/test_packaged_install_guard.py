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


def test_the_application_skips_the_github_update_check_in_a_packaged_install() -> None:
    """Pinned at the source: the early return sits before the checker is created,
    behind the same `frozen` gate that already keeps dev runs quiet."""
    text = (ROOT / "src/open_garden_planner/app/application.py").read_text(encoding="utf-8")
    start = text.index("def _start_update_check(self) -> None:")
    body = text[start: text.index("def _on_update_available", start)]
    frozen_gate = body.index('if not getattr(sys, "frozen", False):')
    guard = body.index("if has_package_identity():")
    checker = body.index("self._update_checker = UpdateChecker(self)")
    assert frozen_gate < guard < checker, body
    assert "return" in body[guard: checker]
