"""Positive control for the black-hole tripwire in tests/conftest.py (2026-08-17).

A detector that silently stops matching turns a gate green forever (the norm
stated in test_settings_chokepoint.py) — so prove, on the Windows registry
backend, that the probe reports a store whose key another instance clear()ed
and destroyed, and stays quiet on a healthy one. Skipped where QSettings does
not use the registry (Linux/CI: INI backend caches same-instance writes).
"""

from __future__ import annotations

import gc
import sys

import pytest

import open_garden_planner.app.settings as settings_module


@pytest.mark.skipif(sys.platform != "win32", reason="registry-backend behaviour")
def test_probe_reports_a_black_hole_and_stays_quiet_when_healthy(qtbot) -> None:  # noqa: ARG001
    from open_garden_planner.app.settings import get_settings

    live = get_settings()  # the singleton _reset_app_settings will probe
    live._settings.setValue("_probe/healthy", 1)
    assert live._settings.value("_probe/healthy", None, type=int) == 1

    killer = settings_module.create_qsettings()
    killer.clear()
    del killer
    gc.collect()  # destruction deletes the registry key under `live`

    live._settings.setValue("_probe/after", 1)
    assert live._settings.value("_probe/after", None, type=int) != 1, (
        "expected the surviving instance to be a black hole after another instance's clear()"
    )
    # Hand `_reset_app_settings` a healthy singleton again so ITS tripwire does not
    # (correctly!) fail this test at teardown — the point here is the mechanism.
    settings_module._settings_instance = None  # type: ignore[attr-defined]
    fresh = get_settings()
    fresh._settings.setValue("_probe/fresh", 1)
    assert fresh._settings.value("_probe/fresh", None, type=int) == 1
