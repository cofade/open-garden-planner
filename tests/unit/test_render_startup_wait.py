"""A driver's first-frame deadline survives the host's short idle refusal (#536)."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.integration import quick3d_render_driver as driver


def test_first_expose_can_be_quiet_for_longer_than_the_idle_cutoff(monkeypatch):
    clock = [0.0]
    host = SimpleNamespace(state=SimpleNamespace(value="starting"), close=Mock())

    def ready(timeout):
        clock[0] += 0.75
        return clock[0] >= 1.5

    host.wait_ready = ready
    monkeypatch.setattr(driver.time, "perf_counter", lambda: clock[0])
    driver.require_ready(host, "a freshly shown host")
    assert clock[0] == 1.5
    host.close.assert_not_called()


def test_first_expose_still_has_one_total_deadline(monkeypatch):
    clock = [0.0]
    host = SimpleNamespace(state=SimpleNamespace(value="starting"), close=Mock())

    def ready(timeout):
        clock[0] += min(0.75, timeout)
        return False

    host.wait_ready = ready
    monkeypatch.setattr(driver.time, "perf_counter", lambda: clock[0])
    with pytest.raises(RuntimeError, match="did not become live"):
        driver.require_ready(host, "a freshly shown host")
    assert clock[0] == driver.OPEN_TIMEOUT_S
    host.close.assert_called_once()
