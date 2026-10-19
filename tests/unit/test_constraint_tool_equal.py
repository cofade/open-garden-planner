"""Mouse gestures for the equal constraint tool (#406)."""
import pytest

from tests.constraint_tool_helpers import assert_cancelled_gesture, make_canvas, run_gesture


@pytest.mark.parametrize("rotation", [0, 45, 215])
def test_gesture_round_trip(qtbot, monkeypatch, rotation):
    run_gesture(make_canvas(qtbot), monkeypatch, "equal", rotation=rotation)


@pytest.mark.parametrize("mode", ["escape", "cancel", "deactivate"])
def test_pending_gesture_cleanup(qtbot, monkeypatch, mode):
    assert_cancelled_gesture(qtbot, monkeypatch, "equal", mode)
