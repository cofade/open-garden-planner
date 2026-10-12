"""Registered constraint gestures through real activation and command wiring."""
import pytest

from tests.constraint_tool_helpers import SCENARIOS, run_gesture


@pytest.mark.parametrize("name", SCENARIOS)
def test_registered_tool_workflow(canvas, monkeypatch, name):
    run_gesture(canvas, monkeypatch, name, integration=True)


def test_every_registered_constraint_tool_has_a_gesture(canvas):
    view = canvas
    registered = {kind: type(tool) for kind, tool in view._tool_manager._tools.items()
                  if kind.name.startswith("CONSTRAINT")}
    assert len(registered) == len(SCENARIOS)
    assert set(registered.values()) == {cls for cls, _ in SCENARIOS.values()}
