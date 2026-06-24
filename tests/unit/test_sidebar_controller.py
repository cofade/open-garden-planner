"""Unit tests for SidebarController — the hover-peek / click-to-toggle accordion.

Panel state is set synchronously at the start of each transition (the
``maximumHeight`` tween that follows is cosmetic), so tests assert on
``state_of`` / ``is_open`` without waiting on the animation. Hover transitions
go through debounce timers, so those tests wait on the committed state.
"""

from __future__ import annotations

import pytest
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


def test_panels_and_keys_canonical_order(qtbot):
    ctrl = _make_controller(qtbot)
    assert ctrl.panel_keys() == _KEYS
    assert [p._title for p in ctrl.panels()] == [f"Panel {k}" for k in _KEYS]
    assert ctrl.panel("c") is ctrl.panels()[2]
    assert ctrl.panel("nope") is None


def test_click_opens_then_closes(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("b")
    assert ctrl.state_of("b") is PanelState.PINNED
    assert ctrl._entries["b"].pin_source is PinSource.USER
    assert ctrl.panel("b").is_expanded()

    ctrl._on_title_click("b")  # click again closes
    assert ctrl.state_of("b") is PanelState.COLLAPSED


def test_pinning_does_not_reorder_panels(qtbot):
    """The original bug: opening a panel moved it to the bottom. Panels now
    keep their fixed layout slot regardless of state."""
    ctrl = _make_controller(qtbot)
    panels = ctrl.panels()
    before = [ctrl._layout.indexOf(p) for p in panels]

    ctrl._on_title_click("a")  # pin the FIRST panel
    ctrl._on_title_click("c")  # and a middle one
    after = [ctrl._layout.indexOf(p) for p in panels]

    assert before == after, "panels must not move in the layout when toggled"
    assert ctrl.is_open("a") and ctrl.is_open("c")


def test_open_panel_gets_stretch_to_fill_space(qtbot):
    """An open panel takes a (content-weighted) layout stretch factor so it
    absorbs surplus sidebar space instead of leaving an empty gap (US-226)."""
    ctrl = _make_controller(qtbot)
    layout = ctrl._layout
    panel = ctrl.panel("a")

    assert layout.stretch(layout.indexOf(panel)) == 0  # collapsed: no stretch
    ctrl._on_title_click("a")
    assert layout.stretch(layout.indexOf(panel)) > 0  # open: fills surplus
    ctrl._on_title_click("a")
    assert layout.stretch(layout.indexOf(panel)) == 0  # collapsed again


def test_open_panels_share_surplus_weighted_by_content(qtbot):
    """Two open panels: the one with more content gets a larger stretch factor,
    so it receives proportionally more of the surplus space (US-226)."""
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    def content(rows: int) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        for i in range(rows):
            label = QLabel(f"row {i}")
            label.setMinimumHeight(20)
            lay.addWidget(label)
        return w

    ctrl = SidebarController()
    qtbot.addWidget(ctrl)
    ctrl.add_panel("big", CollapsiblePanel("big", content(20)))
    ctrl.add_panel("small", CollapsiblePanel("small", content(3)))
    ctrl.resize(300, 800)
    ctrl.show()

    ctrl.set_selection_pinned("big", True)
    ctrl.set_selection_pinned("small", True)

    layout = ctrl._layout
    big = layout.stretch(layout.indexOf(ctrl.panel("big")))
    small = layout.stretch(layout.indexOf(ctrl.panel("small")))
    assert big > small  # taller content → larger share of the surplus


def test_hover_peeks_then_leave_collapses(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_hover_enter("a")
    assert ctrl.state_of("a") is PanelState.COLLAPSED  # debounced
    qtbot.waitUntil(lambda: ctrl.state_of("a") is PanelState.PEEKING, timeout=1000)

    ctrl._on_hover_leave("a")
    assert ctrl.state_of("a") is PanelState.PEEKING  # close debounced
    qtbot.waitUntil(lambda: ctrl.state_of("a") is PanelState.COLLAPSED, timeout=1000)


def test_reenter_cancels_pending_close(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_hover_enter("a")
    ctrl._commit_pending_open()
    assert ctrl.state_of("a") is PanelState.PEEKING

    ctrl._on_hover_leave("a")
    assert ctrl._pending_close_key == "a"
    ctrl._on_hover_enter("a")  # re-enter cancels the close
    assert ctrl._pending_close_key is None
    ctrl._commit_pending_close()  # now a no-op
    assert ctrl.state_of("a") is PanelState.PEEKING


def test_click_promotes_peek_to_pin(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_hover_enter("a")
    ctrl._commit_pending_open()
    assert ctrl.state_of("a") is PanelState.PEEKING

    ctrl._on_title_click("a")  # clicking a peek pins it
    assert ctrl.state_of("a") is PanelState.PINNED
    assert ctrl._entries["a"].pin_source is PinSource.USER


def test_pinned_panel_ignores_hover(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("a")
    assert ctrl.state_of("a") is PanelState.PINNED

    ctrl._on_hover_enter("a")
    assert ctrl._pending_open_key is None
    ctrl._on_hover_leave("a")
    assert ctrl.state_of("a") is PanelState.PINNED


def test_selection_autopin_and_clear(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl.set_selection_pinned("b", True)
    assert ctrl.state_of("b") is PanelState.PINNED
    assert ctrl._entries["b"].pin_source is PinSource.SELECTION

    ctrl.set_selection_pinned("b", False)
    assert ctrl.state_of("b") is PanelState.COLLAPSED


def test_click_closes_selection_pinned_panel(qtbot):
    """Regression: a selection-opened panel (e.g. Companion on a plant) must be
    closable with a single click — the old code upgraded it instead."""
    ctrl = _make_controller(qtbot)
    ctrl.set_selection_pinned("b", True)
    assert ctrl.state_of("b") is PanelState.PINNED

    ctrl._on_title_click("b")  # one click closes it
    assert ctrl.state_of("b") is PanelState.COLLAPSED
    assert ctrl._entries["b"].selection_dismissed is True


def test_dismissed_panel_does_not_reopen_until_selection_changes(qtbot):
    """After the user closes a selection panel, a selection *re-notify* (scene
    move / undo, same selection) must not reopen it; a real selection change does."""
    ctrl = _make_controller(qtbot)
    ctrl.set_selection_pinned("b", True)
    ctrl._on_title_click("b")  # user closes it → dismissed
    assert ctrl.state_of("b") is PanelState.COLLAPSED

    ctrl.set_selection_pinned("b", True)  # re-notify for the SAME selection
    assert ctrl.state_of("b") is PanelState.COLLAPSED  # stays closed

    ctrl.reset_selection_dismissals()  # genuine selection change
    ctrl.set_selection_pinned("b", True)
    assert ctrl.state_of("b") is PanelState.PINNED  # reopens for the new selection


def test_user_pin_survives_selection_clear(qtbot):
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("b")  # USER pin
    ctrl.set_selection_pinned("b", False)  # selection clears
    assert ctrl.state_of("b") is PanelState.PINNED


def test_set_panel_visible_hides_and_shows(qtbot):
    """A contextual panel's bar can be hidden entirely (not just collapsed)."""
    ctrl = _make_controller(qtbot)
    ctrl.set_panel_visible("b", False)
    assert ctrl.panel("b").isHidden()
    ctrl.set_panel_visible("b", True)
    assert not ctrl.panel("b").isHidden()


def test_hiding_an_open_panel_collapses_it(qtbot):
    """Hiding an open panel collapses it first so it reopens clean (US-226)."""
    ctrl = _make_controller(qtbot)
    ctrl._on_title_click("b")
    assert ctrl.is_open("b")
    ctrl.set_panel_visible("b", False)
    assert ctrl.panel("b").isHidden()
    assert ctrl.state_of("b") is PanelState.COLLAPSED


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


def test_duplicate_key_rejected(qtbot):
    ctrl = _make_controller(qtbot, keys=["a"])
    with pytest.raises(ValueError, match="already registered"):
        ctrl.add_panel("a", CollapsiblePanel("dup", QLabel("x")))
