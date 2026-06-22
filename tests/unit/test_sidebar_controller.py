"""Unit tests for SidebarController — the hover-peek/click-to-pin state machine.

Hover transitions go through asymmetric debounce timers; tests either drive the
commit slots directly (deterministic) or wait on the real timer via qtbot to
exercise the wiring. Equalize uses ``QTimer.singleShot(0, ...)`` so tests that
assert on splitter sizes pump the event loop first.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel

from open_garden_planner.ui.widgets import CollapsiblePanel
from open_garden_planner.ui.widgets.panel_stack import (
    PanelState,
    PinSource,
    SidebarController,
)

_KEYS = ["a", "b", "c", "d"]


def _make_controller(qtbot, keys: list[str] | None = None) -> SidebarController:
    keys = keys or _KEYS
    ctrl = SidebarController()
    qtbot.addWidget(ctrl)
    for key in keys:
        panel = CollapsiblePanel(f"Panel {key}", QLabel(f"content {key}"))
        ctrl.add_panel(key, panel)
    ctrl.resize(300, 800)
    ctrl.show()
    return ctrl


def test_startup_all_collapsed(qtbot):
    ctrl = _make_controller(qtbot)
    for key in _KEYS:
        assert ctrl.state_of(key) is PanelState.COLLAPSED
    assert ctrl.pinned_keys() == []


def test_panels_returns_canonical_order(qtbot):
    ctrl = _make_controller(qtbot)
    titles = [p._title for p in ctrl.panels()]
    assert titles == ["Panel a", "Panel b", "Panel c", "Panel d"]


def test_click_pins_and_unpins(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("b")
    assert ctrl.state_of("b") is PanelState.PINNED
    assert ctrl.pinned_keys() == ["b"]

    ctrl._on_title_click("b")
    assert ctrl.state_of("b") is PanelState.COLLAPSED
    assert ctrl.pinned_keys() == []


def test_hover_peeks_then_leave_collapses(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_hover_enter("a")
    assert ctrl.state_of("a") is PanelState.COLLAPSED  # not yet — debounced
    qtbot.waitUntil(lambda: ctrl.state_of("a") is PanelState.PEEKING, timeout=1000)

    ctrl._on_hover_leave("a")
    assert ctrl.state_of("a") is PanelState.PEEKING  # still — close debounced
    qtbot.waitUntil(lambda: ctrl.state_of("a") is PanelState.COLLAPSED, timeout=1000)


def test_reenter_cancels_pending_close(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_hover_enter("a")
    ctrl._commit_pending_open()
    assert ctrl.state_of("a") is PanelState.PEEKING

    ctrl._on_hover_leave("a")  # schedules close
    assert ctrl._pending_close_key == "a"
    ctrl._on_hover_enter("a")  # re-enter cancels it
    assert ctrl._pending_close_key is None
    # Pending-close slot is now a no-op; panel stays peeking.
    ctrl._commit_pending_close()
    assert ctrl.state_of("a") is PanelState.PEEKING


def test_pinned_panel_ignores_hover(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("a")
    assert ctrl.state_of("a") is PanelState.PINNED

    ctrl._on_hover_enter("a")
    assert ctrl._pending_open_key is None  # never scheduled
    ctrl._on_hover_leave("a")
    assert ctrl.state_of("a") is PanelState.PINNED


def test_peek_while_pinned_does_not_touch_splitter(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("a")  # pin a
    splitter = ctrl._splitter
    assert splitter is not None and splitter.count() == 1

    ctrl._on_hover_enter("b")
    ctrl._commit_pending_open()
    assert ctrl.state_of("b") is PanelState.PEEKING
    assert splitter.count() == 1  # peek never enters the splitter


def test_two_pins_share_equally(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("a")
    ctrl._on_title_click("c")
    qtbot.wait(50)  # let the deferred equalize run

    sizes = ctrl._splitter.sizes()
    assert len(sizes) == 2
    assert abs(sizes[0] - sizes[1]) <= 1  # equal up to int-division remainder


def test_pinned_subset_keeps_canonical_order(qtbot):
    ctrl = _make_controller(qtbot)
    # Pin out of canonical order: d, then b, then a.
    ctrl._on_title_click("d")
    ctrl._on_title_click("b")
    ctrl._on_title_click("a")

    # pinned_keys() is canonical; the splitter widgets must match it.
    assert ctrl.pinned_keys() == ["a", "b", "d"]
    splitter = ctrl._splitter
    splitter_titles = [
        splitter.widget(i)._title for i in range(splitter.count())
    ]
    assert splitter_titles == ["Panel a", "Panel b", "Panel d"]


def test_selection_autopin_and_clear(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl.set_selection_pinned("b", True)
    assert ctrl.state_of("b") is PanelState.PINNED
    assert ctrl._entries["b"].pin_source is PinSource.SELECTION

    ctrl.set_selection_pinned("b", False)
    assert ctrl.state_of("b") is PanelState.COLLAPSED


def test_user_click_upgrades_selection_pin(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl.set_selection_pinned("b", True)
    ctrl._on_title_click("b")  # upgrade SELECTION -> USER
    assert ctrl.state_of("b") is PanelState.PINNED
    assert ctrl._entries["b"].pin_source is PinSource.USER

    # A selection-clear must NOT unpin a user-pinned panel.
    ctrl.set_selection_pinned("b", False)
    assert ctrl.state_of("b") is PanelState.PINNED


def test_selection_clear_does_not_unpin_user_pin(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("b")  # USER pin
    ctrl.set_selection_pinned("b", False)
    assert ctrl.state_of("b") is PanelState.PINNED


def test_collapse_all(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("a")
    ctrl.set_selection_pinned("c", True)
    ctrl._on_hover_enter("d")
    ctrl._commit_pending_open()

    ctrl.collapse_all()
    for key in _KEYS:
        assert ctrl.state_of(key) is PanelState.COLLAPSED
    assert ctrl.pinned_keys() == []
    assert ctrl._splitter is None  # splitter torn down when empty


def test_reequalize_on_unpin(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("a")
    ctrl._on_title_click("b")
    ctrl._on_title_click("c")
    qtbot.wait(50)
    assert ctrl._splitter.count() == 3

    ctrl._on_title_click("b")  # unpin the middle one
    qtbot.wait(50)
    sizes = ctrl._splitter.sizes()
    assert len(sizes) == 2
    assert abs(sizes[0] - sizes[1]) <= 1


def test_duplicate_key_rejected(qtbot):
    ctrl = _make_controller(qtbot, keys=["a"])
    import pytest

    with pytest.raises(ValueError, match="already registered"):
        ctrl.add_panel("a", CollapsiblePanel("dup", QLabel("x")))
