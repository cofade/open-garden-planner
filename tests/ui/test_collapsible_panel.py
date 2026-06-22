"""Tests for collapsible panel widget."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from open_garden_planner.ui.widgets import CollapsiblePanel, PanelState


def test_collapsible_panel_creation(qtbot):  # noqa: ARG001
    """Test that a collapsible panel can be created."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=True)

    assert panel is not None
    assert panel.is_expanded()


def test_collapsible_panel_toggle(qtbot):
    """Test toggling the panel state."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=True)
    qtbot.addWidget(panel)
    panel.show()

    # Initially expanded
    assert panel.is_expanded()
    assert content.isVisible()

    # Toggle to collapse
    panel.toggle()
    assert not panel.is_expanded()
    assert not content.isVisible()

    # Toggle back to expand
    panel.toggle()
    assert panel.is_expanded()
    assert content.isVisible()


def test_collapsible_panel_expand_collapse(qtbot):
    """Test expand and collapse methods."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=False)
    qtbot.addWidget(panel)
    panel.show()

    # Initially collapsed
    assert not panel.is_expanded()
    assert not content.isVisible()

    # Expand
    panel.expand()
    assert panel.is_expanded()
    assert content.isVisible()

    # Collapse
    panel.collapse()
    assert not panel.is_expanded()
    assert not content.isVisible()


def test_collapsible_panel_set_content(qtbot):
    """Test setting content after creation."""
    panel = CollapsiblePanel("Test Panel", expanded=True)
    qtbot.addWidget(panel)
    panel.show()

    # No content initially
    assert panel._content_widget is None

    # Set content
    content = QLabel("New Content")
    panel.set_content(content)

    assert panel._content_widget is content
    assert content.isVisible()


def test_collapsible_panel_signal(qtbot):  # noqa: ARG001
    """Test that expanded_changed signal is emitted."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=True)

    # Track signal emissions
    expanded_states = []

    def on_expanded_changed(expanded: bool):
        expanded_states.append(expanded)

    panel.expanded_changed.connect(on_expanded_changed)

    # Toggle should emit signal
    panel.toggle()
    assert len(expanded_states) == 1
    assert expanded_states[0] is False

    # Another toggle
    panel.toggle()
    assert len(expanded_states) == 2
    assert expanded_states[1] is True


def test_collapsible_panel_pin_toggled_on_header_click(qtbot):
    """A left-click on the header bar emits pin_toggled (US-226)."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=True)
    qtbot.addWidget(panel)
    panel.show()

    clicks: list[bool] = []
    panel.header.pin_toggled.connect(clicks.append)

    qtbot.mouseClick(panel.header, Qt.MouseButton.LeftButton)
    assert clicks == [True]


def test_header_child_widget_click_does_not_pin(qtbot):
    """A click on a header child widget (e.g. the Constraints delete-all button)
    must not emit pin_toggled — the child consumes its own press (US-226)."""
    from PyQt6.QtWidgets import QToolButton

    panel = CollapsiblePanel("Test Panel", QLabel("content"))
    qtbot.addWidget(panel)
    button = QToolButton()
    panel.add_header_widget(button)
    panel.show()

    pins: list[bool] = []
    panel.header.pin_toggled.connect(pins.append)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert pins == []  # the button consumed the click; the header never pinned


def test_collapsible_panel_visual_state_property(qtbot):
    """set_visual_state sets the dynamic panelState property (US-226)."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=True)
    qtbot.addWidget(panel)
    panel.show()

    panel.set_visual_state(PanelState.PEEKING)
    assert panel.property("panelState") == "peeking"

    panel.set_visual_state(PanelState.PINNED)
    assert panel.property("panelState") == "pinned"

    panel.set_visual_state(PanelState.COLLAPSED)
    assert panel.property("panelState") == "collapsed"


def test_collapsible_panel_header_height(qtbot):
    """header_height() returns the header's natural pixel height (US-226)."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=True)
    qtbot.addWidget(panel)
    panel.show()

    assert panel.header_height() > 0
