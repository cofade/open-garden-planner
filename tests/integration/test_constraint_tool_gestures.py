"""Registered constraint gestures through real activation and command wiring."""
import pytest

from tests.constraint_tool_helpers import SCENARIOS, run_gesture


@pytest.mark.parametrize("name", SCENARIOS)
def test_registered_tool_workflow(canvas, monkeypatch, name):
    run_gesture(canvas, monkeypatch, name, integration=True)


def test_every_registered_constraint_tool_has_a_gesture(canvas):
    view = canvas
    registered = {type(tool) for tool in view._tool_manager._tools.values()
                  if type(tool).__module__.endswith("constraint_tool")}
    assert registered == {cls for cls, _ in SCENARIOS.values()}
