"""Subscribing a QObject to the sim clock (Phase 17 L1.3; ADR-053, addendum).

``core/sim_clock`` is Qt-free: its channels hold a bound method weakly and prune a
receiver that was garbage-collected, but they cannot see the other way a Qt
object dies — its C++ half destroyed while the Python wrapper is still
referenced (a child deleted with its parent, a ``deleteLater``). The next clock
write then calls into the dead object and raises ``RuntimeError: wrapped C/C++
object … has been deleted``, and it does so on EVERY write (the channel
re-raises the first listener error after the last listener).

ADR-053 decision 4 stated the rule — a Qt subscriber disconnects in its own
teardown. ``connect_qobject`` is the mechanism, and it relies on nobody's
teardown: what the channel calls is a guard that asks Qt, at every delivery,
whether the receiver still exists (``sip.isdeleted``), and takes itself off the
channel instead of calling a dead object. Every QObject that listens to the
clock subscribes through it (``tests/unit/test_sim_clock_subscription.py`` scans
the product for a direct ``channel.connect``).

Lifetimes, exactly as before the helper: the guard lives as long as the
receiver's Python wrapper (a weak-keyed registry holds it) and the channel holds
the guard's method weakly — so a receiver that is garbage-collected leaves the
channel at once, and a subscription never keeps its receiver alive.

Why not ``receiver.destroyed.connect(<disconnect>)``, which is what "disconnect
on destroyed" suggests: it was built first and it crashed the suite. PyQt counts
a Python callable connected to an object's signal as that object's for the
cyclic garbage collector, so the collector clears the callable together with an
unreachable wrapper — while the C++ object, owned by its Qt parent, lives on and
later emits ``destroyed`` into the cleared function: an access violation
(``docs/11-risks-and-technical-debt`` §11.4.16; reproduced in twenty lines of
bare PyQt). A check at delivery has no such window.
"""

from __future__ import annotations

import contextlib
import weakref
from collections.abc import Callable
from types import MethodType
from typing import Any, Generic, TypeVar

from PyQt6 import sip
from PyQt6.QtCore import QObject

from open_garden_planner.core.sim_clock import Channel

T = TypeVar("T")

__all__ = ["connect_qobject", "disconnect_qobject"]


class _Guard(Generic[T]):
    """One subscription: ``deliver`` is what the channel calls."""

    __slots__ = ("__weakref__", "_receiver", "channel", "function")

    def __init__(self, channel: Channel[T], receiver: QObject,
                 function: Callable[..., object]) -> None:
        self.channel = channel
        self.function = function
        self._receiver: weakref.ref[QObject] = weakref.ref(receiver)

    def deliver(self, value: T) -> None:
        receiver = self._receiver()
        if receiver is None:
            return  # collected in this very emission; the channel prunes the rest
        if sip.isdeleted(receiver):
            # Qt destroyed it under a wrapper that still exists: this delivery is the
            # first chance to notice. Never call it, and never be asked again.
            _forget(receiver, self)
            return
        self.function(receiver, value)


#: receiver wrapper → its guards. Weak-keyed: a collected receiver takes its guards
#: along, and with them the channel's (weak) hold on ``deliver``.
_GUARDS: weakref.WeakKeyDictionary[QObject, list[_Guard[Any]]] = weakref.WeakKeyDictionary()


def _forget(receiver: QObject, guard: _Guard[Any]) -> None:
    with contextlib.suppress(ValueError):  # taken off by hand in the meantime
        guard.channel.disconnect(guard.deliver)
    guards = _GUARDS.get(receiver)
    if guards is not None and guard in guards:
        guards.remove(guard)
        if not guards:
            del _GUARDS[receiver]


def _parts(slot: Callable[[T], object]) -> tuple[QObject, Callable[..., object]]:
    receiver: Any = getattr(slot, "__self__", None)
    if not isinstance(slot, MethodType) or not isinstance(receiver, QObject):
        raise TypeError(
            f"connect_qobject needs a bound method of a QObject, got {slot!r}: for anything "
            "else there is no Qt object whose life could be asked")
    return receiver, slot.__func__


def _find(channel: Channel[T], receiver: QObject,
          function: Callable[..., object]) -> _Guard[T] | None:
    for guard in _GUARDS.get(receiver, ()):
        if guard.channel is channel and guard.function is function:
            return guard
    return None


def connect_qobject(channel: Channel[T], slot: Callable[[T], object]) -> None:
    """Connect ``slot`` — a bound method of a QObject — to ``channel`` so that it is
    never called after Qt destroyed that QObject.

    Like a Qt connection it never keeps the receiver alive, and a receiver that is
    garbage-collected leaves the channel at once. One that Qt destroyed under a
    living wrapper leaves at the next emission (until then ``receiver_count``
    still counts it). Connecting the same slot twice registers it once.
    ``TypeError`` for anything that is not a bound method of a QObject — a
    function, a lambda, or a bound signal's ``emit`` (a builtin the channel would
    hold strongly: the trap ADR-053 names). ``RuntimeError`` for a receiver Qt has
    already destroyed.
    """
    receiver, function = _parts(slot)
    if sip.isdeleted(receiver):
        raise RuntimeError(
            f"the receiver of {getattr(function, '__qualname__', function)!r} is already "
            "destroyed")
    guard = _find(channel, receiver, function)
    if guard is None:
        guard = _Guard(channel, receiver, function)
        _GUARDS.setdefault(receiver, []).append(guard)
    channel.connect(guard.deliver)  # idempotent for the same guard


def disconnect_qobject(channel: Channel[T], slot: Callable[[T], object]) -> None:
    """Undo ``connect_qobject``; ``ValueError`` when the slot is not connected."""
    receiver, function = _parts(slot)
    guard = _find(channel, receiver, function)
    if guard is None:
        raise ValueError("listener is not connected")
    channel.disconnect(guard.deliver)
    _forget(receiver, guard)
