"""``connect_qobject`` — a QObject's slot on a ``SimClock`` channel (L1.3, ADR-053 addendum).

The clock's channels are Qt-free: they hold a bound method weakly, but they cannot
know that the C++ half of a QObject was destroyed while its Python wrapper lives —
which is what happens to a child when Qt deletes its parent. Calling such a slot
raises ``RuntimeError: wrapped C/C++ object … has been deleted`` on every clock
write. ADR-053 decision 4 made "a Qt subscriber disconnects in its own teardown" a
rule; the helper makes it a mechanism: a guard that asks Qt at every delivery.
"""

from __future__ import annotations

import ast
import gc
import weakref
from datetime import date, datetime, time
from pathlib import Path

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QObject

from open_garden_planner.core.sim_clock import Channel, SimChange, SimClock
from open_garden_planner.ui import sim_clock_subscription
from open_garden_planner.ui.sim_clock_subscription import connect_qobject, disconnect_qobject


class _Listener(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.seen: list[object] = []

    def on_value(self, value: object) -> None:
        # touches the C++ object: this is what raises once Qt deleted it
        self.objectName()
        self.seen.append(value)


def test_a_connected_slot_is_called(qtbot) -> None:  # noqa: ARG001 - Qt init
    channel: Channel[int] = Channel()
    listener = _Listener()
    connect_qobject(channel, listener.on_value)
    channel.emit(7)
    assert listener.seen == [7]
    assert channel.receiver_count() == 1


def test_a_destroyed_receiver_is_never_called(qtbot) -> None:  # noqa: ARG001 - Qt init
    """Qt deletes a child with its parent; the Python wrapper is still referenced
    here. Without the helper the next emit raises from inside the dead slot."""
    channel: Channel[int] = Channel()
    parent = QObject()
    listener = _Listener(parent)
    connect_qobject(channel, listener.on_value)
    channel.emit(0)
    assert listener.seen == [0]

    sip.delete(parent)

    assert sip.isdeleted(listener)
    channel.emit(1)  # must not raise, must not call
    channel.emit(2)
    assert listener.seen == [0]
    assert channel.receiver_count() == 0, "the first delivery after its death took it off"


def test_without_the_helper_the_same_teardown_raises(qtbot) -> None:  # noqa: ARG001 - Qt init
    """The control: a plain ``channel.connect`` keeps calling into the dead object."""
    channel: Channel[int] = Channel()
    parent = QObject()
    listener = _Listener(parent)
    channel.connect(listener.on_value)
    sip.delete(parent)
    with pytest.raises(RuntimeError, match="has been deleted"):
        channel.emit(1)


def test_deleting_the_receiver_itself_takes_it_off(qtbot) -> None:  # noqa: ARG001 - Qt init
    channel: Channel[int] = Channel()
    listener = _Listener()
    connect_qobject(channel, listener.on_value)
    sip.delete(listener)
    channel.emit(1)
    assert listener.seen == []
    assert channel.receiver_count() == 0


def test_a_live_listener_after_a_dead_one_still_hears_the_clock(qtbot) -> None:  # noqa: ARG001
    """The channel re-raises the first listener error after the last listener — a dead
    receiver that raised would not starve the others, but it would fail every write."""
    channel: Channel[int] = Channel()
    dead, alive = _Listener(), _Listener()
    connect_qobject(channel, dead.on_value)
    connect_qobject(channel, alive.on_value)
    sip.delete(dead)
    channel.emit(5)
    assert alive.seen == [5]
    assert channel.receiver_count() == 1


def test_the_subscription_does_not_keep_its_receiver_alive(qtbot) -> None:  # noqa: ARG001
    """An unparented controller still dies with its last reference (ADR-053)."""
    channel: Channel[int] = Channel()
    listener = _Listener()
    alive = weakref.ref(listener)
    connect_qobject(channel, listener.on_value)
    del listener
    gc.collect()
    assert alive() is None
    assert channel.receiver_count() == 0, "a collected receiver leaves at once, as in L1.0"
    channel.emit(1)


def test_connecting_twice_registers_once(qtbot) -> None:  # noqa: ARG001 - Qt init
    channel: Channel[int] = Channel()
    listener = _Listener()
    connect_qobject(channel, listener.on_value)
    connect_qobject(channel, listener.on_value)
    assert channel.receiver_count() == 1
    channel.emit(3)
    assert listener.seen == [3]


def test_two_receivers_of_one_class_are_two_subscriptions(qtbot) -> None:  # noqa: ARG001
    channel: Channel[int] = Channel()
    first, second = _Listener(), _Listener()
    connect_qobject(channel, first.on_value)
    connect_qobject(channel, second.on_value)
    channel.emit(4)
    assert (first.seen, second.seen) == ([4], [4])


def test_a_slot_can_be_taken_off_by_hand(qtbot) -> None:  # noqa: ARG001 - Qt init
    channel: Channel[int] = Channel()
    listener = _Listener()
    connect_qobject(channel, listener.on_value)
    disconnect_qobject(channel, listener.on_value)
    channel.emit(1)
    assert listener.seen == []
    assert channel.receiver_count() == 0
    with pytest.raises(ValueError, match="not connected"):
        disconnect_qobject(channel, listener.on_value)


def test_a_dead_subscription_never_stands_in_for_a_new_receiver(qtbot) -> None:  # noqa: ARG001
    """Receivers come and go on one channel (every test builds a main window on a
    clock of its own; a long session rebuilds controllers): each new one subscribes,
    whatever is left of the ones before it, and the books do not grow."""
    channel: Channel[int] = Channel()
    # The books are the process's: a receiver some EARLIER test left alive is in them
    # too (seen in the whole suite: two). Hold those for the length of this test, so
    # that "do not grow" is an exact count and not a guess about other tests.
    others = list(sim_clock_subscription._GUARDS.keys())
    for round_number in range(50):
        listener = _Listener()
        connect_qobject(channel, listener.on_value)
        assert len(sim_clock_subscription._GUARDS) == len(others) + 1, "this receiver is booked"
        channel.emit(round_number)
        assert listener.seen == [round_number]
        if round_number % 2:
            sip.delete(listener)  # destroyed by Qt, wrapper still referenced here
        del listener
        gc.collect()
    channel.emit(-1)  # the Qt-destroyed ones leave at this delivery
    assert channel.receiver_count() == 0
    assert len(sim_clock_subscription._GUARDS) == len(others), "not one of the fifty is left"
    del others


@pytest.mark.parametrize("bad", ["function", "lambda", "plain_object", "builtin"])
def test_only_a_bound_method_of_a_qobject_is_taken(qtbot, bad: str) -> None:  # noqa: ARG001
    """For anything else there is no Qt object whose life could be asked — and a bound
    signal's ``emit`` is the trap ADR-053 names: a builtin, held strongly."""

    class Plain:
        def on_value(self, value: object) -> None:
            """Not a QObject."""

    def function(value: object) -> None:
        """Not a method."""

    listener = _Listener()
    slots = {"function": function, "lambda": lambda _value: None,
             "plain_object": Plain().on_value, "builtin": listener.destroyed.emit}
    channel: Channel[int] = Channel()
    with pytest.raises(TypeError, match="bound method of a QObject"):
        connect_qobject(channel, slots[bad])
    assert channel.receiver_count() == 0


def test_a_receiver_that_is_already_gone_is_refused(qtbot) -> None:  # noqa: ARG001 - Qt init
    channel: Channel[int] = Channel()
    listener = _Listener()
    slot = listener.on_value
    sip.delete(listener)
    with pytest.raises(RuntimeError, match="already destroyed"):
        connect_qobject(channel, slot)
    assert channel.receiver_count() == 0


def test_both_clock_channels_take_a_qobject(qtbot) -> None:  # noqa: ARG001 - Qt init
    class Both(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.days: list[date] = []
            self.changes: list[SimChange] = []

        def on_day(self, day: date) -> None:
            self.days.append(day)

        def on_change(self, change: SimChange) -> None:
            self.changes.append(change)

    clock = SimClock(datetime(2026, 6, 21, 12, 0))
    both = Both()
    connect_qobject(clock.date_changed, both.on_day)
    connect_qobject(clock.instant_changed, both.on_change)
    clock.set_time_of_day(time(15, 0))
    clock.set_date(date(2026, 6, 22))
    assert both.days == [date(2026, 6, 22)]
    assert len(both.changes) == 2
    sip.delete(both)
    clock.set_date(date(2026, 6, 23))  # nobody left, nothing raises
    assert clock.date_changed.receiver_count() == 0
    assert clock.instant_changed.receiver_count() == 0


# ── every QObject on the clock goes through the helper ───────────────────────

_SRC = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"
_CHANNELS = {"date_changed", "instant_changed"}
_HELPER = _SRC / "ui" / "sim_clock_subscription.py"


def _direct_clock_connects(source: str) -> list[int]:
    """Lines of ``<…>.date_changed.connect(…)`` / ``<…>.instant_changed.connect(…)``."""
    return [
        node.lineno for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect" and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr in _CHANNELS
    ]


def test_no_module_of_the_product_connects_to_a_clock_channel_directly() -> None:
    """ADR-053 decision 4 as a mechanism: a subscription written as
    ``clock.instant_changed.connect(self._slot)`` works — until Qt destroys the
    receiver with its parent. The three subscribers of L1.0 and the 3D controller
    all go through ``connect_qobject``."""
    offenders = {
        str(path.relative_to(_SRC)): lines
        for path in sorted(_SRC.rglob("*.py")) if path != _HELPER
        for lines in [_direct_clock_connects(path.read_text(encoding="utf-8"))] if lines
    }
    assert offenders == {}


@pytest.mark.parametrize(("source", "found"), [
    ("clock.instant_changed.connect(self._on_change)\n", 1),
    ("self._clock.date_changed.connect(slot)\n", 1),
    ("connect_qobject(self._clock.date_changed, self._on_day)\n", 0),
    ("self._detail.steps_date_changed.connect(self._on_steps)\n", 0),  # a Qt signal of that name
    ("clock.instant_changed.disconnect(slot)\n", 0),
])
def test_the_scan_sees_a_direct_connect_and_nothing_else(source: str, found: int) -> None:
    assert len(_direct_clock_connects(source)) == found


def test_the_helper_hangs_nothing_on_the_destroyed_signal() -> None:
    """The first version did (``receiver.destroyed.connect(<closure>)``) and crashed the
    suite with an access violation: the cyclic collector had cleared the closure
    before Qt called it (§11.4). The guard asks at delivery instead."""
    tree = ast.parse(_HELPER.read_text(encoding="utf-8"))
    names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "destroyed" not in names


def _destroyed_connects(source: str) -> list[int]:
    """Lines of ``<…>.destroyed.connect(…)`` — a Python callable on an object's
    ``destroyed`` signal."""
    return [
        node.lineno for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect" and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "destroyed"
    ]


#: The one shipped site that still hangs a Python closure on its own ``destroyed``
#: signal (the global search field's focus listener). Known and written up as a
#: follow-up; it is not a clock subscriber and is not this story's to change. A NEW
#: site fails the test below — master's sun coordinator (v1.30.1) was one until it
#: was routed through ``connect_qobject``.
_KNOWN_DESTROYED_HOOKS = {"ui/widgets/global_search.py": 1}


def test_nothing_new_hangs_clean_up_on_a_destroyed_signal() -> None:
    """Measured in bare PyQt 6.11 (§11.4, the workspace's lessons, item 1): a closure
    on an object's own ``destroyed`` signal runs 0 times when the cyclic collector
    reaches the wrappers before Qt's deferred delete — the clean-up silently does not
    happen — and on a Qt-owned object in that order it is an access violation."""
    offenders = {
        path.relative_to(_SRC).as_posix(): len(lines)
        for path in sorted(_SRC.rglob("*.py"))
        for lines in [_destroyed_connects(path.read_text(encoding="utf-8"))] if lines
    }
    assert offenders == _KNOWN_DESTROYED_HOOKS


@pytest.mark.parametrize(("source", "found"), [
    ("self.destroyed.connect(disconnect)\n", 1),
    ("receiver.destroyed.connect(lambda *_: forget(receiver))\n", 1),
    ("self.destroyed.disconnect(slot)\n", 0),
    ("worker.finished.connect(self._on_destroyed)\n", 0),
    ("if sip.isdeleted(receiver):\n    return\n", 0),
])
def test_the_scan_sees_a_callable_on_destroyed_and_nothing_else(source: str, found: int) -> None:
    assert len(_destroyed_connects(source)) == found
