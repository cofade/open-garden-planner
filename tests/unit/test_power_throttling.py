"""Tests for Windows power throttling opt-out (#616)."""

import sys
from unittest.mock import patch

from tests.conftest import (
    disable_windows_power_throttling,
    get_windows_power_throttling_state,
)


def test_windows_power_throttling_on_current_platform() -> None:
    """On Windows, opt-out succeeds and reports unthrottled state; on other OSes, returns False/None."""
    if sys.platform == "win32":
        res = disable_windows_power_throttling()
        assert res is True
        state = get_windows_power_throttling_state()
        assert state is not None
        control_mask, state_mask = state
        # StateMask indicates active throttling flags; execution speed (bit 0) must NOT be throttled
        assert state_mask & 1 == 0
    else:
        assert disable_windows_power_throttling() is False
        assert get_windows_power_throttling_state() is None


def test_disable_windows_power_throttling_non_windows_mocked() -> None:
    """When platform is not win32, functions safely return False / None."""
    with patch("sys.platform", "linux"):
        assert disable_windows_power_throttling() is False
        assert get_windows_power_throttling_state() is None


def test_disable_windows_power_throttling_handles_exceptions() -> None:
    """Unexpected ctypes/Windows API error returns False rather than crashing."""
    with patch("sys.platform", "win32"), patch("ctypes.WinDLL", side_effect=OSError("API unavailable"), create=True):
        assert disable_windows_power_throttling() is False
        assert get_windows_power_throttling_state() is None
